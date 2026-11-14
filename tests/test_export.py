import json
import time

import pytest
import weewx
import weewx.manager
import weewx.schemas.wview_extended
from weeutil.weeutil import startOfDay

from canones_weather.export import export


def test_archive_export_preserves_units_gaps_and_unverified_provenance(tmp_path):
    today = startOfDay(1794626100)
    yesterday = startOfDay(today - 1)
    records = [
        {"dateTime": yesterday + 36300, "outTemp": 68.0, "rain": 0.1, "windGust": 6.0, "radiation": 100.0},
        {"dateTime": yesterday + 36600, "outTemp": 86.0, "rain": 0.2, "windGust": 10.0, "radiation": 300.0},
        {"dateTime": today + 300, "outTemp": None, "rain": None, "windGust": None, "radiation": None},
    ]
    for record in records:
        record.update(usUnits=weewx.US, interval=5, outHumidity=40.0, windSpeed=3.0)
    database = {"driver": "weedb.sqlite", "database_name": str(tmp_path / "archive.sdb")}
    with weewx.manager.DaySummaryManager.open_with_create(
        database, schema=weewx.schemas.wview_extended.schema
    ) as manager:
        manager.addRecord(records)
        export(manager, records[-1], tmp_path / "public")
    current = json.loads((tmp_path / "public/current.json").read_text())
    history = json.loads((tmp_path / "public/history.json").read_text())
    assert current["deployment"]["phase"] == "pilot"
    assert history["record_started_at"] == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(records[0]["dateTime"]))
    assert current["deployment"]["dataset_id"] == history["deployment"]["dataset_id"]
    assert current["kind"] == "live"
    assert current["outdoor"]["verified"] is False
    assert current["outdoor"]["temperature_c"] is None
    assert current["outdoor"]["rain_today_mm"] is None
    assert current["observed_at"] == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(records[-1]["dateTime"]))
    day = history["daily"][0]
    assert day["temperature_c"] == pytest.approx(25.0)
    assert day["temperature_min_c"] == pytest.approx(20.0)
    assert day["temperature_max_c"] == pytest.approx(30.0)
    assert day["rain_mm"] == pytest.approx(7.62)
    assert day["solar_w_m2"] == pytest.approx(200.0)
    assert day["wind_gust_m_s"] == pytest.approx(4.4704)
    assert any(row["temperature_c"] is None and row["rain_mm"] is None for row in history["hourly"])

    hour = next(row for row in history["hourly"] if row["temperature_c"] is not None)
    assert hour["temperature_c"] == pytest.approx(25.0)
    assert hour["temperature_min_c"] == pytest.approx(20.0)
    assert hour["temperature_max_c"] == pytest.approx(30.0)
    recent = [row for row in history["recent"] if row["temperature_c"] is not None]
    assert [row["temperature_c"] for row in recent] == [20.0, 30.0]
    assert recent[0]["at"] == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(records[0]["dateTime"]))
    assert history["recent"][-1]["at"] == current["observed_at"]


def test_first_boundary_observation_survives_hourly_and_dst_daily_summaries(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("America/Denver")
    midnight = int(datetime(2026, 3, 8, tzinfo=zone).timestamp())
    next_midnight = int(datetime(2026, 3, 9, tzinfo=zone).timestamp())
    end = int(datetime(2026, 3, 10, tzinfo=zone).timestamp())
    records = [
        {"dateTime": midnight, "outTemp": 10.0},
        {"dateTime": midnight + 300, "outTemp": 20.0},
        {"dateTime": next_midnight, "outTemp": 30.0},
        {"dateTime": end, "outTemp": None},
    ]
    for record in records:
        record.update(usUnits=weewx.METRICWX, interval=5, rain=None)
    try:
        with monkeypatch.context() as patch:
            patch.setenv("TZ", str(zone))
            time.tzset()
            database = {"driver": "weedb.sqlite", "database_name": str(tmp_path / "archive.sdb")}
            with weewx.manager.DaySummaryManager.open_with_create(
                database, schema=weewx.schemas.wview_extended.schema
            ) as manager:
                manager.addRecord(records)
                export(manager, records[-1], tmp_path / "public")
    finally:
        time.tzset()
    history = json.loads((tmp_path / "public/history.json").read_text())
    assert history["hourly"][0]["temperature_c"] == 10.0
    days = history["daily"]
    assert [row["temperature_c"] for row in days] == [10.0, 25.0, None]
    assert next_midnight - midnight == 23 * 3600
    assert days[1]["at"] == "2026-03-08T07:00:00Z"
    assert days[2]["at"] == "2026-03-09T06:00:00Z"
    assert all(row["rain_mm"] is None for row in days)


def test_daily_counter_uses_last_value_preserves_gaps_and_resets_at_midnight(tmp_path):
    import weewx.accum
    from weeutil.weeutil import TimeSpan

    today = startOfDay(1794672600)
    accumulator = weewx.accum.Accum(TimeSpan(today, today + 300))
    for offset, counter in [(20, 0.10), (280, 0.15)]:
        accumulator.addRecord({"dateTime": today + offset, "usUnits": weewx.US, "dayRain": counter, "rain": None})
    record = {**accumulator.getRecord(), "interval": 5}
    assert record["dayRain"] == 0.15  # Cumulative counter: last, not average or sum.
    database = {"driver": "weedb.sqlite", "database_name": str(tmp_path / "archive.sdb")}
    with weewx.manager.DaySummaryManager.open_with_create(
        database, schema=weewx.schemas.wview_extended.schema
    ) as manager:
        manager.addRecord(record)
        export(manager, record, tmp_path / "public")
        current = json.loads((tmp_path / "public/current.json").read_text())["outdoor"]
        history = json.loads((tmp_path / "public/history.json").read_text())
        assert current["rain_today_mm"] == pytest.approx(3.81)
        assert current["rain_today_source"] == "ws90_daily_counter"
        assert history["recent"][0]["rain_mm"] is None
        for stamp, counter, expected, source in [
            (today + 86400, 0.40, 0.0, "local_midnight_reset"),
            (today + 86700, 0.02, 0.508, "ws90_daily_counter"),
        ]:
            record = {"dateTime": stamp, "usUnits": weewx.US, "interval": 5, "rain": None, "dayRain": counter}
            manager.addRecord(record)
            export(manager, record, tmp_path / "public")
            current = json.loads((tmp_path / "public/current.json").read_text())["outdoor"]
            assert current["rain_today_mm"] == pytest.approx(expected)
            assert current["rain_today_source"] == source
