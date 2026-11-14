"""Export WeeWX archive observations and summaries to the dashboard JSON format."""

import json
import logging
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import weewx
import weewx.engine
import weewx.units
import weewx.xtypes
from weeutil.weeutil import TimeSpan, archiveDaySpan, intervalgen, startOfDay

log = logging.getLogger(__name__)


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def number(value):
    return round(float(value), 4) if value is not None and math.isfinite(float(value)) else None


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            json.dump(data, stream, allow_nan=False, separators=(",", ":"))
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def history_rows(manager, start, stop, interval):
    if start >= stop:
        return []
    recent = interval == 300
    rows = {
        (span.stop if recent else span.start): {"at": iso(span.stop if recent else span.start)}
        for span in intervalgen(start, stop, interval)
    }
    fields = [
        ("temperature_c", "outTemp", "avg", "degree_C"),
        ("humidity_pct", "outHumidity", "avg", "percent"),
        ("wind_speed_m_s", "windSpeed", "avg", "meter_per_second"),
        ("wind_gust_m_s", "windGust", "max", "meter_per_second"),
        ("rain_mm", "rain", "sum", "mm"),
    ]
    if not recent:
        fields += [
            ("temperature_min_c", "outTemp", "min", "degree_C"),
            ("temperature_max_c", "outTemp", "max", "degree_C"),
        ]
    for field, observation, aggregate, unit in fields:
        for row in rows.values():
            row[field] = None
        starts, ends, values = weewx.xtypes.get_series(
            observation,
            TimeSpan(start, stop),
            manager,
            aggregate_type=None if recent else aggregate,
            aggregate_interval=interval,
        )
        for timestamp, value in zip((ends if recent else starts)[0], values[0]):
            if timestamp in rows:
                converted = weewx.units.convert((value, values[1], values[2]), unit)[0]
                rows[timestamp][field] = number(converted)
    return list(rows.values())


def export(manager, record, output_root):
    metric = weewx.units.to_std_system(record, weewx.METRICWX)
    timestamp = record["dateTime"]
    first = manager.first_timestamp
    start = archiveDaySpan(first).start
    hourly_stop = int(timestamp // 3600) * 3600
    daily_stop = startOfDay(timestamp)
    deployment = {
        "phase": "pilot",
        "dataset_id": f"pilot-{first}",
        "notice": (
            "Pilot observations: sensor placement is provisional. Primary temperature and humidity may come "
            "from the garage WN32. Sensor mapping is unverified; Wunderground/CWOP publishing is disabled."
        ),
    }
    recent = history_rows(manager, max(int((first - 1) // 300) * 300, timestamp - 86400), timestamp, 300)
    history = {
        "deployment": deployment,
        "schema_version": 1,
        "kind": "live",
        "station_id": "canones",
        "through": iso(timestamp),
        "recent": recent,
        "hourly": history_rows(
            manager, max(int((first - 1) // 3600) * 3600, hourly_stop - 30 * 86400), hourly_stop, 3600
        ),
        "daily": history_rows(manager, start, daily_stop, "day"),
    }
    day_start = startOfDay(timestamp)
    rain_today = None
    covered, records, known_rain = manager.getSql(
        "SELECT COALESCE(SUM(interval), 0) * 60, COUNT(*), COUNT(rain) "
        "FROM archive WHERE dateTime > ? AND dateTime <= ?",
        (day_start, timestamp),
    )
    if timestamp == day_start:
        rain_today = 0.0
    elif covered >= timestamp - day_start and records == known_rain:
        aggregate = weewx.xtypes.get_aggregate("rain", TimeSpan(day_start, timestamp), "sum", manager)
        rain_today = weewx.units.convert(aggregate, "mm")[0]
    current = {
        "deployment": deployment,
        "schema_version": 1,
        "kind": "live",
        "station": {"id": "canones", "name": "Secco Creek", "timezone": "America/Denver"},
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
            "solar_w_m2": number(metric.get("radiation")),
            "uv_index": number(metric.get("UV")),
        },
    }
    write_json(Path(output_root) / "history.json", history)
    write_json(Path(output_root) / "current.json", current)


class JSONReport(weewx.engine.StdService):
    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        self.output_root = config_dict["CanonesJSON"]["output_root"]
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def new_archive_record(self, event):
        try:
            manager = self.engine.db_binder.get_manager("wx_binding")
            export(manager, event.record, self.output_root)
            log.info("Exported pilot observation at %s", iso(event.record["dateTime"]))
        except Exception:
            log.exception("JSON export failed; archive collection continues")
