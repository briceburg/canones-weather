from types import SimpleNamespace

import pytest

from canones_weather.jsonio import write_json
from canones_weather.publish import main, publish


@pytest.fixture
def snapshots(tmp_path):
    observed_at = "2026-11-25T20:25:00Z"
    deployment = {"phase": "pilot", "dataset_id": "pilot-check", "notice": "Pilot data"}
    live = {"schema_version": 1, "kind": "live"}
    documents = {
        "current.json": {
            **live,
            "deployment": deployment.copy(),
            "station": {"id": "canones"},
            "observed_at": observed_at,
            "outdoor": {"verified": False},
        },
    }
    for cadence, through in [
        ("daily", "2026-11-25T07:00:00Z"),
        ("hourly", "2026-11-25T20:00:00Z"),
        ("recent", observed_at),
    ]:
        documents[f"history/{cadence}.json"] = {
            **live,
            "station_id": "canones",
            "deployment": deployment.copy(),
            "record_started_at": "2026-11-24T20:00:00Z",
            "cadence": cadence,
            "through": through,
            "rows": [],
        }
    config = {
        "source_root": tmp_path / "public",
        "endpoint_url": "https://example.r2.cloudflarestorage.com",
        "bucket": "test-weather",
        "key_prefix": "canones/",
    }
    return config, documents, tmp_path / "publisher"


@pytest.mark.parametrize(
    "invalid",
    ["sample", "reference", "dataset", "observation", "future_history", "cadence", "unverified_production"],
)
def test_rejects_inconsistent_publication_before_connecting(snapshots, monkeypatch, invalid):
    config, documents, state_dir = snapshots
    current = documents["current.json"]
    recent = documents["history/recent.json"]
    daily = documents["history/daily.json"]
    if invalid in ("sample", "reference"):
        recent["kind"] = invalid
    elif invalid == "dataset":
        daily["deployment"]["dataset_id"] = "different-archive"
    elif invalid == "observation":
        recent["through"] = "2026-11-25T20:20:00Z"
    elif invalid == "future_history":
        daily["through"] = "2026-11-26T07:00:00Z"
    elif invalid == "cadence":
        daily["cadence"] = "hourly"
    else:
        for document in documents.values():
            document["deployment"]["phase"] = "production"
        assert current["outdoor"]["verified"] is False
    for name, data in documents.items():
        write_json(config["source_root"] / name, data)

    def forbidden_client(*args, **kwargs):
        pytest.fail("Invalid data must be rejected before opening a publishing client")

    monkeypatch.setattr("canones_weather.publish.boto3.client", forbidden_client)
    with pytest.raises(ValueError):
        publish(config, state_dir=state_dir)


def test_failed_publication_resumes_and_same_watermark_corrections_upload(snapshots, monkeypatch):
    config, documents, state_dir = snapshots
    for name, data in documents.items():
        write_json(config["source_root"] / name, data)

    uploaded = []
    interrupted = True

    def put_object(**request):
        if interrupted and request["Key"] == "canones/history/hourly.json":
            raise ConnectionError("Connection interrupted during hourly upload")
        uploaded.append(request["Key"])

    monkeypatch.setattr("canones_weather.publish.publishing_client", lambda _: SimpleNamespace(put_object=put_object))
    with pytest.raises(ConnectionError):
        publish(config, state_dir=state_dir)
    assert uploaded == ["canones/history/daily.json"]

    interrupted = False
    config_file = state_dir.parent / "config.json"
    write_json(config_file, {**config, "source_root": str(config["source_root"])})
    monkeypatch.setenv("STATE_DIRECTORY", str(state_dir))
    monkeypatch.setattr("sys.argv", ["publish", str(config_file)])
    main()
    assert uploaded == [
        "canones/history/daily.json",
        "canones/history/hourly.json",
        "canones/history/recent.json",
        "canones/current.json",
    ]
    uploaded.clear()
    publish(config, state_dir=state_dir)
    assert uploaded == []

    daily = documents["history/daily.json"]
    daily["rows"] = [{"at": "2026-11-24T07:00:00Z", "rain_mm": 2.5}]
    write_json(config["source_root"] / "history/daily.json", daily)
    publish(config, state_dir=state_dir)
    assert uploaded == ["canones/history/daily.json"]
