"""Export WeeWX archive observations and summaries to the dashboard JSON format."""

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import weedb
import weewx
import weewx.engine
import weewx.units
import weewx.xtypes
from weeutil.weeutil import TimeSpan, archiveDaySpan, intervalgen, startOfDay

from canones_weather.jsonio import write_json
from canones_weather.station import load_station

log = logging.getLogger(__name__)


@dataclass
class ExportCache:
    """Cache closed history for one collector connection and export directory."""

    revision: tuple | None = None
    summaries: dict = field(default_factory=dict)


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def number(value):
    return round(float(value), 4) if value is not None and math.isfinite(float(value)) else None


def history_rows(manager, start, stop, interval):
    if start >= stop:
        return []
    recent = interval == 300
    spans = list(intervalgen(start, stop, interval))
    rows = {(span.stop if recent else span.start): {"at": iso(span.stop if recent else span.start)} for span in spans}
    fields = [
        ("temperature_c", "outTemp", "avg", "degree_C"),
        ("humidity_pct", "outHumidity", "avg", "percent"),
        ("wind_speed_m_s", "windSpeed", "avg", "meter_per_second"),
        ("wind_gust_m_s", "windGust", "max", "meter_per_second"),
        ("rain_mm", "rain", "sum", "mm"),
        ("solar_w_m2", "radiation", "avg", "watt_per_meter_squared"),
    ]
    if not recent:
        fields += [
            ("temperature_min_c", "outTemp", "min", "degree_C"),
            ("temperature_max_c", "outTemp", "max", "degree_C"),
        ]
    for key, observation, aggregate, unit in fields:
        for row in rows.values():
            row[key] = None
        if recent:
            _, ends, values = weewx.xtypes.get_series(observation, TimeSpan(start, stop), manager)
            samples = ((stamp, (value, values[1], values[2])) for stamp, value in zip(ends[0], values[0]))
        else:
            # get_series skips the span ending at the archive's very first record.
            samples = (
                (span.start, weewx.xtypes.get_aggregate(observation, span, aggregate, manager))
                for span in spans
                if aggregate != "sum" or weewx.xtypes.get_aggregate(observation, span, "count", manager)[0]
            )
        for timestamp, value in samples:
            if timestamp in rows and value[0] is not None:
                rows[timestamp][key] = number(weewx.units.convert(value, unit)[0])
    return list(rows.values())


def write_changed_json(path, data):
    try:
        if json.loads(path.read_bytes()) == data:
            return
    except (FileNotFoundError, ValueError):
        pass
    write_json(path, data)


def export(manager, record, output_root, *, cache=None):
    root = Path(output_root)
    revision = None
    previous = {}
    # Recovery can insert old rows concurrently; all summaries need one snapshot.
    with weedb.Transaction(manager.connection):
        if cache is not None and manager.connection.dbtype == "sqlite":
            # StdArchive uses this connection. A commit by recovery or another
            # writer invalidates closed tiers even if the boundaries are unchanged.
            revision = (manager.connection, manager.getSql("PRAGMA data_version")[0], root)
            if cache.revision == revision:
                previous = cache.summaries
        current, history = documents(manager, record, previous)
    for cadence, data in history.items():
        path = root / "history" / f"{cadence}.json"
        if data is not previous.get(cadence) or not path.is_file():
            write_changed_json(path, data)
    write_changed_json(root / "current.json", current)
    if revision is not None:
        cache.revision = revision
        cache.summaries = {cadence: history[cadence] for cadence in ("daily", "hourly")}


def documents(manager, record, previous=None):
    station = load_station()
    metric = weewx.units.to_std_system(record, weewx.METRICWX)
    timestamp = record["dateTime"]
    first = manager.firstGoodStamp()
    start = archiveDaySpan(first).start
    hourly_stop = int(timestamp // 3600) * 3600
    day_start = startOfDay(timestamp)
    deployment = {
        "phase": "pilot",
        "dataset_id": f"pilot-{first}",
        "notice": (
            "Pilot observations: sensor placement is provisional. Primary temperature and humidity may come "
            "from the garage WN32. Sensor mapping is unverified; Wunderground/CWOP publishing is disabled."
        ),
    }
    archive = {
        "deployment": deployment,
        "schema_version": 1,
        "kind": "live",
        "station_id": station["id"],
        "record_started_at": iso(first),
    }
    spans = {
        "daily": (start, day_start, "day"),
        "hourly": (max(int((first - 1) // 3600) * 3600, hourly_stop - 30 * 86400), hourly_stop, 3600),
        "recent": (max(int((first - 1) // 300) * 300, timestamp - 86400), timestamp, 300),
    }
    history = {}
    for cadence, (span_start, stop, interval) in spans.items():
        header = {**archive, "cadence": cadence, "through": iso(stop)}
        cached = (previous or {}).get(cadence)
        if cached and all(cached[key] == value for key, value in header.items()):
            history[cadence] = cached
        else:
            history[cadence] = {**header, "rows": history_rows(manager, span_start, stop, interval)}
    rain_today = number(metric.get("dayRain"))
    if rain_today is not None and rain_today < 0:
        rain_today = None
    rain_source = "ws90_daily_counter" if rain_today is not None else None
    if timestamp == day_start:
        rain_today, rain_source = 0.0, "local_midnight_reset"
    elif rain_today is None:
        covered, records, known_rain = manager.getSql(
            "SELECT COALESCE(SUM(interval), 0) * 60, COUNT(*), COUNT(rain) "
            "FROM archive WHERE dateTime > ? AND dateTime <= ?",
            (day_start, timestamp),
        )
        if covered >= timestamp - day_start and records == known_rain:
            aggregate = weewx.xtypes.get_aggregate("rain", TimeSpan(day_start, timestamp), "sum", manager)
            rain_today = weewx.units.convert(aggregate, "mm")[0]
            rain_source = "complete_archive"
    current = {
        "deployment": deployment,
        "schema_version": 1,
        "kind": "live",
        "station": station,
        "observed_at": iso(timestamp),
        "outdoor": {
            "source": "GW3000 primary outdoor (unverified)",
            "verified": False,
            "temperature_c": number(metric.get("outTemp")),
            "humidity_pct": number(metric.get("outHumidity")),
            "wind_speed_m_s": number(metric.get("windSpeed")),
            "wind_gust_m_s": number(metric.get("windGust")),
            "wind_direction_deg": number(metric.get("windDir")),
            "rain_today_mm": number(rain_today),
            "rain_today_source": rain_source,
            "solar_w_m2": number(metric.get("radiation")),
            "uv_index": number(metric.get("UV")),
        },
    }
    return current, history


class JSONReport(weewx.engine.StdService):
    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        self.output_root = config_dict["CanonesJSON"]["output_root"]
        self.cache = ExportCache()
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def new_archive_record(self, event):
        try:
            manager = self.engine.db_binder.get_manager("wx_binding")
            export(manager, event.record, self.output_root, cache=self.cache)
            log.info("Exported pilot observation at %s", iso(event.record["dateTime"]))
        except Exception:
            log.exception("JSON export failed; archive collection continues")
