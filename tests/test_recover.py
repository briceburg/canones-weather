import csv
import io
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import weedb
import weewx
import weewx.manager
import weewx.schemas.wview_extended
import weewx.xtypes
from configobj import ConfigObj
from weeutil.weeutil import TimeSpan

from canones_weather import recover
from canones_weather.export import export

ZONE = ZoneInfo("America/Denver")
START = int(datetime(2026, 11, 21, 12, tzinfo=ZONE).timestamp())


@pytest.fixture(autouse=True)
def station_timezone(monkeypatch):
    with monkeypatch.context() as patch:
        patch.setenv("TZ", ZONE.key)
        time.tzset()
        yield
    time.tzset()


def sd_file(rows):
    stream = io.StringIO()
    fields = {
        "Outdoor Temperature(°F)": "68",
        "Outdoor Humidity(%)": "45",
        "Wind(mph)": "10",
        "Gust(mph)": "15",
        "Wind Direction(deg)": "180",
        "Solar Rad(W/m2)": "316.81",
    }
    writer = csv.DictWriter(stream, ["Time", "Timestamp", *fields])
    writer.writeheader()
    for stamp, overrides in rows:
        timestamp = datetime.fromtimestamp(stamp, ZONE).strftime("%Y-%m-%d %H:%M")
        writer.writerow({"Time": timestamp, "Timestamp": stamp + 26} | fields | overrides)
    return stream.getvalue().encode()


def record(stamp, temperature=3):
    return {"dateTime": stamp, "interval": 5, "usUnits": weewx.METRICWX, "outTemp": temperature, "rain": 0}


def test_recovery_preserves_existing_rows_units_and_atomic_provenance(tmp_path):
    database = {"driver": "weedb.sqlite", "database_name": str(tmp_path / "archive.sdb")}
    body = sd_file([(START, {"Wind(mph)": "invalid"}), (START + 300, {}), (START + 600, {"Outdoor Humidity(%)": "--"})])
    with weewx.manager.DaySummaryManager.open_with_create(
        database, schema=weewx.schemas.wview_extended.schema
    ) as collector:
        collector.addRecord([record(START), record(START + 1200)])
    with recover.RecoveryManager.open(database) as manager:
        original = manager.getRecord(START)
        missing = recover.missing_intervals(manager, START + 3600)
        planned = recover.plan_recovery([recover.sd_records("202611A.csv", body, ZONE, missing)])
        assert [row["dateTime"] for row in planned] == [START + 300, START + 600]
        # A live record arriving after planning must win the insert race.
        with weewx.manager.DaySummaryManager.open(database) as collector:
            collector.addRecord(record(START + 300, 7))
        watermark = manager._read_metadata("lastUpdate")
        assert recover.apply_recovery(manager, planned) == 1
        assert manager._read_metadata("lastUpdate") == watermark
        recovered = manager.getRecord(START + 600)
        assert recovered["outTemp"] == pytest.approx(20)
        assert recovered["windSpeed"] == pytest.approx(4.4704)
        assert recovered["radiation"] == pytest.approx(316.81)
        assert recovered["rain"] is None
        assert recovered["outHumidity"] is None
        assert manager.getRecord(START) == original
        assert manager.getRecord(START + 300)["outTemp"] == 7
        assert list(manager.genSql("SELECT * FROM canones_recovery")) == [(START + 600, START + 626, "202611A.csv")]
        missing = recover.missing_intervals(manager, START + 3600)
        assert not list(recover.sd_records("202611A.csv", body, ZONE, missing))

        # A provenance insert failure must also roll back the archive and summary writes.
        candidate = next(recover.sd_records("202611A.csv", sd_file([(START + 900, {})]), ZONE, missing))
        with weedb.Transaction(manager.connection) as cursor:
            cursor.execute("INSERT INTO canones_recovery VALUES (?, ?, ?)", (START + 900, START + 926, "existing.csv"))
        span = TimeSpan(START - 1, START + 1200)
        before = weewx.xtypes.get_aggregate("outTemp", span, "count", manager)[0]
        assert recover.apply_recovery(manager, [candidate]) == 0
        assert manager.getRecord(START + 900) is None
        assert weewx.xtypes.get_aggregate("outTemp", span, "count", manager)[0] == before


def test_recovery_leaves_ambiguous_timestamps_missing():
    rows = [
        (START + 480, {}),
        (START + 600, {}),
        (START + 900, {}),
        (START + 1200, {"Time": "2026-11-21 12:30"}),
    ]
    body = sd_file(rows)
    missing = set(range(START + 300, START + 1800, 300))
    parsed = recover.sd_records("202611A.csv", body, ZONE, missing)
    duplicate = sd_file([(START + 600, {"Solar Rad(W/m2)": "999"})])
    plan = recover.plan_recovery([parsed, recover.sd_records("202611B.csv", duplicate, ZONE, missing)])
    assert [row["dateTime"] for row in plan] == [START + 900]
    with pytest.raises(ValueError, match="unsupported SD column"):
        list(recover.sd_records("202611A.csv", body.replace(b"Wind(mph)", b"Wind(furlongs/day)"), ZONE, missing))


def test_failed_sd_file_retains_validated_cache_and_defers_its_month(tmp_path, monkeypatch):
    database = {"driver": "weedb.sqlite", "database_name": str(tmp_path / "archive.sdb")}
    with weewx.manager.DaySummaryManager.open_with_create(
        database, schema=weewx.schemas.wview_extended.schema
    ) as manager:
        manager.addRecord([record(START), record(START + 1200)])
        export(manager, record(START + 1200), tmp_path / "public")
    config = ConfigObj(
        {
            "WEEWX_ROOT": str(tmp_path),
            "EcowittHttp": {"ip_address": "gateway.example"},
            "CanonesJSON": {"output_root": str(tmp_path / "public")},
            "DataBindings": {
                "wx_binding": {
                    "database": "archive_sqlite",
                    "table_name": "archive",
                    "manager": "weewx.manager.DaySummaryManager",
                }
            },
            "Databases": {"archive_sqlite": {"database_name": "archive.sdb", "database_type": "SQLite"}},
            "DatabaseTypes": {"SQLite": {"driver": "weedb.sqlite", "SQLITE_ROOT": str(tmp_path)}},
        }
    )
    bodies = {"202611A.csv": sd_file([(START, {})]), "202611B.csv": sd_file([(START + 300, {})])}

    def download(url):
        if url.endswith("get_sdmmc_info"):
            return json.dumps(
                {
                    "sd_status": "normal",
                    "info": {"Interval": "5"},
                    "file_list": [{"name": name, "type": "file"} for name in bodies],
                }
            ).encode()
        value = bodies[url.rsplit("/", 1)[1]]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(recover, "download", download)
    assert recover.run(config, dry_run=True)["inserted"] == 0
    original = {path.name: path.read_bytes() for path in (tmp_path / "recovery").glob("*.csv")}
    bodies["202611A.csv"] = OSError("Gateway SD download unavailable")
    result = recover.run(config)
    assert result["failed_files"] == ["202611A.csv"]
    assert result["inserted"] == 0
    assert {path.name: path.read_bytes() for path in (tmp_path / "recovery").glob("*.csv")} == original
    bodies["202611A.csv"] = sd_file([(START, {})])
    assert recover.run(config)["inserted"] == 1
    assert recover.run(config)["inserted"] == 0
