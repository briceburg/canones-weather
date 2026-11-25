"""Export WeeWX archive observations and summaries to the dashboard JSON format."""

import logging
import math
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
    for field, observation, aggregate, unit in fields:
        for row in rows.values():
            row[field] = None
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
                rows[timestamp][field] = number(weewx.units.convert(value, unit)[0])
    return list(rows.values())


def export(manager, record, output_root):
    # Recovery can insert old rows concurrently; all summaries need one snapshot.
    with weedb.Transaction(manager.connection):
        current, history = documents(manager, record)
    write_json(Path(output_root) / "history.json", history)
    write_json(Path(output_root) / "current.json", current)


def documents(manager, record):
    station = load_station()
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
        "station_id": station["id"],
        "through": iso(timestamp),
        "record_started_at": iso(first),
        "recent": recent,
        "hourly": history_rows(
            manager, max(int((first - 1) // 3600) * 3600, hourly_stop - 30 * 86400), hourly_stop, 3600
        ),
        "daily": history_rows(manager, start, daily_stop, "day"),
    }
    day_start = startOfDay(timestamp)
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
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def new_archive_record(self, event):
        try:
            manager = self.engine.db_binder.get_manager("wx_binding")
            export(manager, event.record, self.output_root)
            log.info("Exported pilot observation at %s", iso(event.record["dateTime"]))
        except Exception:
            log.exception("JSON export failed; archive collection continues")
