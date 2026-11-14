import copy
import json
from pathlib import Path

import pytest

from canones_weather.publish import publish


@pytest.mark.parametrize("invalid", ["sample", "mismatched_dataset", "unverified_production"])
def test_rejects_unsafe_publication_before_connecting(tmp_path, monkeypatch, invalid):
    current = json.loads(Path("site/canones/data/sample/current.json").read_text())
    current.update(kind="live", deployment={"phase": "pilot", "dataset_id": "pilot-check", "notice": "Pilot data"})
    history = {
        "schema_version": 1,
        "kind": "live",
        "station_id": "canones",
        "deployment": copy.deepcopy(current["deployment"]),
    }
    if invalid == "sample":
        current["kind"] = "sample"
    elif invalid == "mismatched_dataset":
        history["deployment"]["dataset_id"] = "different-archive"
    else:
        current["deployment"]["phase"] = history["deployment"]["phase"] = "production"
    for name, data in [("current", current), ("history", history)]:
        (tmp_path / f"{name}.json").write_text(json.dumps(data))

    def forbidden_client(*args, **kwargs):
        pytest.fail("Invalid data must be rejected before opening a publishing client")

    monkeypatch.setattr("canones_weather.publish.boto3.client", forbidden_client)
    with pytest.raises(ValueError):
        publish({"endpoint_url": "https://example.r2.cloudflarestorage.com", "source_root": str(tmp_path)})
