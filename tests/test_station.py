import json
import re
from html import escape
from pathlib import Path
from types import SimpleNamespace

import weewx
import weewx.manager
import weewx.schemas.wview_extended

from canones_weather import station
from canones_weather.export import export
from canones_weather.publish import publish
from canones_weather.site import build_site

ROOT = Path(__file__).resolve().parent.parent


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
    publisher = {"source_root": str(public), "bucket": "test-weather", "key_prefix": "canones/"}

    with weewx.manager.DaySummaryManager.open_with_create(
        database, schema=weewx.schemas.wview_extended.schema
    ) as manager:
        manager.addRecord(record)
        before_record = manager.getRecord(record["dateTime"])
        export(manager, record, public)
        build_site(ROOT, site)
        publish(publisher)
        before_current = json.loads((public / "current.json").read_text())
        before_history = (public / "history.json").read_bytes()
        before_sample = json.loads((site / "canones/data/sample/current.json").read_text())
        before_config = json.loads((site / "canones/assets/site-config.json").read_text())
        before_page = (site / "canones/index.html").read_text()

        # Quotes, ampersands, and a script end tag must remain literal display text.
        name = 'Spring & "Ridge" </script>'
        metadata["name"] = name
        metadata_path.write_text(json.dumps(metadata))
        export(manager, record, public)
        build_site(ROOT, site)
        publish(publisher)
        assert manager.getRecord(record["dateTime"]) == before_record

    current = json.loads((public / "current.json").read_text())
    assert current["station"]["name"] == name
    before_current["station"]["name"] = name
    assert current == before_current
    assert (public / "history.json").read_bytes() == before_history
    assert [obj["Key"] for obj in uploads] == ["canones/history.json", "canones/current.json"] * 2
    assert uploads[0]["Body"] == uploads[2]["Body"]
    assert json.loads(uploads[-1]["Body"]) == current

    sample = json.loads((site / "canones/data/sample/current.json").read_text())
    before_sample["station"]["name"] = name
    assert sample == before_sample
    assert (site / "canones/data/sample/history.json").read_bytes() == (
        ROOT / "site/canones/data/sample/history.json"
    ).read_bytes()

    for route, heading in [
        ("hub", f"<h3>{escape(name)}</h3>"),
        ("canones", f'<h1 id="station-title">{escape(name)}</h1>'),
    ]:
        page = (site / route / "index.html").read_text()
        assert heading in page
        assert f'aria-label="View {escape(name)} station on OpenStreetMap"' in page
        assert "{{ station." not in page
        config = json.loads((site / route / "assets/site-config.json").read_text())
        assert config["station"] == metadata
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
