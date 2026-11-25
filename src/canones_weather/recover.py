"""Recover missing pilot archive intervals from the GW3000 SD card."""

import argparse
import csv
import fcntl
import hashlib
import io
import json
import logging
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo

import weedb
import weewx
import weewx.manager
import weewx.units
from configobj import ConfigObj

from canones_weather.station import load_station

log = logging.getLogger(__name__)
FILE_NAME = re.compile(r"\d{6}[A-Z]\.csv")
MAX_BYTES = 16_000_000
INTERVAL = 300
LOOKBACK = 31 * 86400
UPPER_LIMITS = {"outHumidity": 100, "windDir": 360}
FIELDS = {
    "Outdoor Temperature": "outTemp",
    "Outdoor Humidity": "outHumidity",
    "Wind": "windSpeed",
    "Gust": "windGust",
    "Wind Direction": "windDir",
    "Solar Rad": "radiation",
}
UNITS = {
    "°C": "degree_C",
    "℃": "degree_C",
    "°F": "degree_F",
    "℉": "degree_F",
    "%": "percent",
    "mph": "mile_per_hour",
    "m/s": "meter_per_second",
    "km/h": "km_per_hour",
    "knots": "knot",
    "deg": "degree_compass",
    "W/m2": "watt_per_meter_squared",
}


def sd_records(name, body, zone, missing):
    """Convert primary-sensor samples only for missing archive intervals."""
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")), strict=True)
    columns = {}
    for header in reader.fieldnames or []:
        match = re.fullmatch(r"(.+)\(([^()]*)\)", header)
        if match and match[1] in FIELDS:
            field, unit = FIELDS[match[1]], match[2]
            if field in columns or unit not in UNITS:
                raise ValueError(f"Ambiguous or unsupported SD column: {header}")
            target, group = weewx.units.getStandardUnitType(weewx.METRICWX, field)
            columns[field] = (header, UNITS[unit], target, group)
    if not {"Time", "Timestamp"}.issubset(reader.fieldnames or []) or len(columns) != len(FIELDS):
        raise ValueError("SD file lacks required primary sensor columns")
    for raw in reader:
        # The gateway can be appending the final CSV line during a download.
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError("Incomplete SD CSV row; retry a complete download")
        epoch = int(raw["Timestamp"])
        stamp = epoch - epoch % 60
        if stamp not in missing:
            continue
        local = datetime.fromtimestamp(epoch, zone)
        if local.strftime("%Y-%m-%d %H:%M") != raw["Time"]:
            continue
        if local.strftime("%Y%m") != name[:6]:
            raise ValueError("SD record date does not match its file month")
        values = {}
        for field, (header, unit, target, group) in columns.items():
            if raw[header] in ("", "--"):
                continue
            try:
                value = weewx.units.convert((float(raw[header]), unit, group), target)[0]
            except KeyError as error:
                raise ValueError(f"Unsupported units in {header}") from error
            if (
                not math.isfinite(value)
                or (field != "outTemp" and value < 0)
                or value > UPPER_LIMITS.get(field, math.inf)
            ):
                raise ValueError(f"Invalid SD observation in {header}")
            values[field] = value
        if values:
            yield {
                "dateTime": stamp,
                "usUnits": weewx.METRICWX,
                "interval": INTERVAL // 60,
                "_source_file": name,
                "_logged_at": epoch,
                **values,
            }


def missing_intervals(manager, now):
    """Find holes within existing pilot history and away from the live boundary."""
    if manager.first_timestamp is None:
        return set()
    start = max(manager.first_timestamp + 1, manager.last_timestamp - LOOKBACK)
    stop = min(manager.last_timestamp - INTERVAL, int(now // INTERVAL) * INTERVAL - 2 * INTERVAL)
    start = (start + INTERVAL - 1) // INTERVAL * INTERVAL
    existing = {
        row[0] for row in manager.genSql("SELECT dateTime FROM archive WHERE dateTime BETWEEN ? AND ?", (start, stop))
    }
    return set(range(start, stop + 1, INTERVAL)) - existing


def plan_recovery(snapshots):
    candidates = {}
    for records in snapshots:
        for record in records:
            stamp = record["dateTime"]
            candidates[stamp] = None if stamp in candidates else record
    return [record for _, record in sorted(candidates.items()) if record is not None]


class RecoveryManager(weewx.manager.DaySummaryManager):
    """Insert a recovered row and its provenance in the same SQLite transaction."""

    def _set_day_summary(self, day_accum, lastUpdate, cursor, key_set=None):
        # Historical inserts must not move the live summary watermark backwards.
        return super()._set_day_summary(day_accum, None, cursor, key_set)

    def _addSingleRecord(self, record, cursor, log_success=True, log_failure=True, update=False):
        if update:
            raise ValueError("Recovery cannot overwrite observations")
        source, logged_at = record["_source_file"], record["_logged_at"]
        record = {key: value for key, value in record.items() if not key.startswith("_")}
        cursor.execute("SAVEPOINT sd_record")
        try:
            super()._addSingleRecord(record, cursor, log_success, log_failure, update=False)
            cursor.execute(
                "INSERT INTO canones_recovery (dateTime, logged_at, source_file) VALUES (?, ?, ?)",
                (record["dateTime"], logged_at, source),
            )
        except Exception:
            cursor.execute("ROLLBACK TO sd_record")
            raise
        finally:
            cursor.execute("RELEASE sd_record")


def apply_recovery(manager, records):
    if not records:
        return 0
    with weedb.Transaction(manager.connection) as cursor:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS canones_recovery "
            "(dateTime INTEGER PRIMARY KEY, logged_at INTEGER NOT NULL, source_file TEXT NOT NULL)"
        )
    return manager.addRecord(records, log_success=False, update=False)


def download(url):
    request = Request(url, headers={"User-Agent": "canones-weather/0.1 (SD recovery)"})
    with build_opener(ProxyHandler({})).open(request, timeout=10) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("SD response exceeds the download limit")
    return body


def run(config, *, dry_run=False):
    """Run independently of the collector; the next normal export publishes recovery."""
    if config["DataBindings"]["wx_binding"]["manager"] != "weewx.manager.DaySummaryManager":
        raise ValueError("SD recovery requires the pilot daily-summary archive")
    manager_dict = weewx.manager.get_manager_dict_from_config(config, "wx_binding")
    database = manager_dict["database_dict"]
    if database["driver"] != "weedb.sqlite" or manager_dict["table_name"] != "archive":
        raise ValueError("SD recovery requires the pilot SQLite archive")
    host = config["EcowittHttp"]["ip_address"]
    address = urlsplit(f"//{host}")
    if not address.hostname or address.username is not None or address.netloc != host:
        raise ValueError("Explicit gateway host configuration is required")
    station = load_station()
    zone = ZoneInfo(station["timezone"])
    os.environ["TZ"] = zone.key
    time.tzset()
    cache = Path(config["WEEWX_ROOT"]) / "recovery"
    cache.mkdir(mode=0o750, parents=True, exist_ok=True)
    current = json.loads((Path(config["CanonesJSON"]["output_root"]) / "current.json").read_text())
    if (
        current.get("kind") != "live"
        or current.get("station", {}).get("id") != station["id"]
        or current.get("deployment", {}).get("phase") != "pilot"
        or current.get("outdoor", {}).get("verified") is not False
    ):
        raise ValueError("Automatic SD recovery is limited to the unverified pilot dataset")
    with (cache / "lock").open("w") as lock, RecoveryManager.open(database) as manager:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if manager.first_timestamp is None or current["deployment"]["dataset_id"] != f"pilot-{manager.first_timestamp}":
            raise ValueError("Recovery archive does not match the published pilot dataset")
        missing = missing_intervals(manager, time.time())
        records, failures = read_candidates(host, address.hostname, missing, zone, cache)
        inserted = 0 if dry_run else apply_recovery(manager, records)
        return {"candidates": len(records), "inserted": inserted, "failed_files": failures, "dry_run": dry_run}


def read_candidates(host, hostname, missing, zone, cache):
    if not missing:
        return [], []
    months = {datetime.fromtimestamp(stamp, zone).strftime("%Y%m") for stamp in missing}
    info = json.loads(download(f"http://{host}/get_sdmmc_info"))
    if info.get("sd_status") != "normal" or int(info["info"]["Interval"]) != INTERVAL // 60:
        raise ValueError("A healthy SD card with five-minute logging is required")
    snapshots, failures = {}, []
    downloaded = 0
    for item in info.get("file_list", []):
        name = item.get("name", "")
        if item.get("type") != "file" or not FILE_NAME.fullmatch(name) or name[:6] not in months:
            continue
        try:
            body = download(f"http://{hostname}:81/{name}")
            downloaded += len(body)
            if downloaded > MAX_BYTES:
                raise ValueError("SD recovery batch exceeds the download limit")
            if not body.endswith(b"\n"):
                raise ValueError("Incomplete SD CSV download")
            # The first header/data lines identify one append-only log generation.
            prefix = b"\n".join(body.splitlines()[:2])
            cache_name = name[:-4] + "-" + hashlib.sha256(prefix).hexdigest()[:16] + ".csv"
            cached = cache / cache_name
            previous = cached.read_bytes() if cached.exists() else b""
            if not body.startswith(previous):
                raise ValueError("Previously validated SD history was rewritten or truncated")
            parsed = list(sd_records(cache_name, body, zone, missing))
            if body != previous:
                temporary = cached.with_suffix(".tmp")
                temporary.write_bytes(body)
                temporary.replace(cached)
            snapshots[name] = parsed
        except (OSError, ValueError, csv.Error) as error:
            log.error("SD file %s could not be validated: %s", name, error)
            failures.append(name)
    failed_months = {name[:6] for name in failures}
    records = plan_recovery(rows for name, rows in snapshots.items() if name[:6] not in failed_months)
    return records, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Installed WeeWX configuration")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without inserting archive rows")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    result = run(ConfigObj(str(args.config)), dry_run=args.dry_run)
    print(json.dumps(result))
    return bool(result["failed_files"])


if __name__ == "__main__":
    raise SystemExit(main())
