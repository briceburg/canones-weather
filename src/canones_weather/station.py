"""Shared public station identity and editable display metadata."""

import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

METADATA_PATH = Path(__file__).with_name("station.json")


def load_station():
    station = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    for key in ("id", "name", "timezone"):
        if not isinstance(station.get(key), str) or not station[key].strip():
            raise ValueError(f"Station metadata requires a nonempty {key}")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", station["id"]):
        raise ValueError("Station ID must be a lowercase identifier, independent of its display name")
    ZoneInfo(station["timezone"])
    return {key: station[key] for key in ("id", "name", "timezone")}
