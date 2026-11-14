import io
import json
import sys
from unittest.mock import patch
from urllib.error import URLError

from canones_weather.probe import main


def test_capture_preserves_gateway_fields(tmp_path):
    target = tmp_path / "capture.json"
    live = {"common_list": [{"id": "0x02", "val": "56.8", "unit": "F"}]}
    sensors = [{"img": "wh90", "id": "FFFFFFFF"}, {"img": "wh26", "id": "B9"}]
    responses = [io.BytesIO(json.dumps(value).encode()) for value in (live, sensors)]
    with (
        patch.object(sys, "argv", ["probe", "--gateway", "http://gateway.invalid", "--output", str(target)]),
        patch("canones_weather.probe.build_opener") as opener,
    ):
        opener.return_value.open.side_effect = responses
        assert main() == 0
    capture = json.loads(target.read_text())
    assert capture["responses"]["get_livedata_info"] == live
    assert capture["responses"]["get_sensors_info?page=1"] == sensors
    assert not capture["errors"]


def test_failure_retains_other_endpoint(tmp_path):
    target = tmp_path / "capture.json"
    with (
        patch.object(sys, "argv", ["probe", "--gateway", "http://gateway.invalid", "--output", str(target)]),
        patch("canones_weather.probe.build_opener") as opener,
    ):
        opener.return_value.open.side_effect = [URLError("offline"), io.BytesIO(b"[]")]
        assert main() == 1
    capture = json.loads(target.read_text())
    assert "get_livedata_info" in capture["errors"]
    assert capture["responses"]["get_sensors_info?page=1"] == []
