import json
import re
from html import escape
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import weewx
import weewx.manager
import weewx.schemas.wview_extended

from canones_weather import station
from canones_weather.export import export
from canones_weather.publish import publish
from canones_weather.site import build_site, check_pages_history

ROOT = Path(__file__).resolve().parent.parent


def test_station_pages_waits_for_history_from_current_dataset(monkeypatch):
    monkeypatch.setenv("CF_PAGES", "1")
    monkeypatch.setenv("CF_PAGES_BRANCH", "main")
    live = {
        "kind": "live",
        "schema_version": 1,
        "deployment": {"phase": "pilot", "dataset_id": "pilot-check", "notice": "Pilot"},
    }
    timestamp = "2026-11-25T20:25:00Z"
    payloads = {
        "current.json": {**live, "station": {"id": "canones"}, "observed_at": timestamp, "outdoor": {"verified": False}}
    }
    history = {**live, "station_id": "canones", "through": timestamp, "record_started_at": timestamp, "rows": []}
    payloads.update({f"history/{cadence}.json": {**history, "cadence": cadence} for cadence in ("recent", "hourly")})

    def fetch(request, *, timeout):
        name = request.full_url.split("/canones/", 1)[1]
        if name not in payloads:
            raise FileNotFoundError(name)
        return BytesIO(json.dumps(payloads[name]).encode())

    monkeypatch.setattr("canones_weather.site.urlopen", fetch)
    monkeypatch.setenv("CF_PAGES_URL", "https://build.iceburg-weather.pages.dev")
    check_pages_history(ROOT)  # The hub can deploy while station data is unavailable.
    monkeypatch.setenv("CF_PAGES_URL", "https://build.canones-weather.pages.dev")
    with pytest.raises(SystemExit, match=r"history/daily\.json"):
        check_pages_history(ROOT)
    daily = {**history, "cadence": "daily"}
    payloads["history/daily.json"] = {**daily, "deployment": {"dataset_id": "different"}}
    with pytest.raises(SystemExit, match="does not match.*dataset"):
        check_pages_history(ROOT)
    payloads["history/daily.json"] = daily
    check_pages_history(ROOT)


def test_rename_updates_presentation_without_changing_observations_or_identity(tmp_path, monkeypatch):
    metadata = station.load_station()
    metadata_path = tmp_path / "station.json"
    metadata_path.write_text(json.dumps(metadata))
    monkeypatch.setattr(station, "METADATA_PATH", metadata_path)
    public = tmp_path / "public"
    site = tmp_path / "dist"
    record = {"dateTime": 1794626100, "usUnits": weewx.METRICWX, "interval": 5, "outTemp": 12.5}
    database = {"driver": "weedb.sqlite", "database_name": str(tmp_path / "archive.sdb")}
    uploads = []
    monkeypatch.setattr(
        "canones_weather.publish.publishing_client",
        lambda config: SimpleNamespace(put_object=lambda **obj: uploads.append(obj)),
    )
    publisher = {
        "source_root": str(public),
        "bucket": "test-weather",
        "key_prefix": "canones/",
        "endpoint_url": "https://example.r2.cloudflarestorage.com",
    }
    state = tmp_path / "publisher"
    history_files = ["history/daily.json", "history/hourly.json", "history/recent.json"]

    with weewx.manager.DaySummaryManager.open_with_create(
        database, schema=weewx.schemas.wview_extended.schema
    ) as manager:
        manager.addRecord(record)
        before_record = manager.getRecord(record["dateTime"])
        export(manager, record, public)
        build_site(ROOT, site)
        publish(publisher, state_dir=state)
        before_current = json.loads((public / "current.json").read_text())
        before_history = [(public / path).read_bytes() for path in history_files]
        before_sample = json.loads((site / "canones/data/sample/current.json").read_text())
        before_configs = {
            route: json.loads((site / route / "assets/site-config.json").read_text()) for route in ("hub", "canones")
        }
        before_page = (site / "canones/index.html").read_text()

        # Markup and template-like text must remain literal display text.
        name = 'Spring & "Ridge" </script> {{ station.timezone }}'
        metadata["name"] = name
        metadata_path.write_text(json.dumps(metadata))
        export(manager, record, public)
        build_site(ROOT, site)
        publish(publisher, state_dir=state)
        assert manager.getRecord(record["dateTime"]) == before_record

    current = json.loads((public / "current.json").read_text())
    assert current["station"]["name"] == name
    before_current["station"]["name"] = name
    assert current == before_current
    assert [(public / path).read_bytes() for path in history_files] == before_history
    assert [obj["Key"] for obj in uploads] == [
        f"canones/{path}" for path in [*history_files, "current.json", "current.json"]
    ]
    assert json.loads(uploads[-1]["Body"]) == current

    sample = json.loads((site / "canones/data/sample/current.json").read_text())
    before_sample["station"]["name"] = name
    assert sample == before_sample
    for path in history_files:
        relative_path = f"canones/data/sample/{path}"
        assert (site / relative_path).read_bytes() == (ROOT / "site" / relative_path).read_bytes()

    for route, heading in [
        ("hub", f"<h3>{escape(name)}</h3>"),
        ("canones", f'<h1 id="station-title">{escape(name)}</h1>'),
    ]:
        page = (site / route / "index.html").read_text()
        assert heading in page
        assert f'aria-label="View {escape(name)} station on OpenStreetMap"' in page
        config = json.loads((site / route / "assets/site-config.json").read_text())
        assert config["station"] == metadata
        before_config = before_configs[route]
        before_config["station"]["name"] = name
        assert config == before_config

    page = (site / "canones/index.html").read_text()
    assert f"<title>{escape(name)} — Iceburg Weather</title>" in page
    dataset_pattern = r'<script type="application/ld\+json">(.*?)</script>'
    before_dataset = json.loads(re.search(dataset_pattern, before_page, re.DOTALL)[1])
    dataset = json.loads(re.search(dataset_pattern, page, re.DOTALL)[1])
    assert dataset["name"] == f"{name} weather observations, Cañones, New Mexico"
    assert dataset["spatialCoverage"]["name"] == f"{name}, Cañones, New Mexico"
    assert dataset["@id"] == before_dataset["@id"]
    assert dataset["distribution"] == before_dataset["distribution"]
    assert metadata["id"] == current["station"]["id"] == "canones"
