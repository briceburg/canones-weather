"""Shared station identity and public feed contract."""

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

METADATA_PATH = Path(__file__).with_name("station.json")
HISTORY_FILES = {cadence: f"history/{cadence}.json" for cadence in ("daily", "hourly", "recent")}


def load_station():
    station = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    for key in ("id", "name", "timezone"):
        if not isinstance(station.get(key), str) or not station[key].strip():
            raise ValueError(f"Station metadata requires a nonempty {key}")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", station["id"]):
        raise ValueError("Station ID must be a lowercase identifier, independent of its display name")
    ZoneInfo(station["timezone"])
    return {key: station[key] for key in ("id", "name", "timezone")}


def instant(value):
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed
    raise ValueError("Station timestamps must include a time zone")


def validate_live_feed(documents, *, check_watermarks=True):
    for path, data in documents.items():
        if not isinstance(data, dict) or data.get("kind") != "live" or data.get("schema_version") != 1:
            raise ValueError(f"{path} must contain version-1 live station data")
    current = documents["current.json"]
    station_id = load_station()["id"]
    deployment = current.get("deployment") or {}
    if (current.get("station") or {}).get("id") != station_id or not deployment.get("dataset_id"):
        raise ValueError("Current observations need the configured station and a dataset ID")
    phase = deployment.get("phase")
    if phase not in ("pilot", "production"):
        raise ValueError("Unknown deployment phase")
    if (current.get("outdoor") or {}).get("verified") is not (phase == "production") or (
        phase == "pilot" and not deployment.get("notice")
    ):
        raise ValueError("Observation provenance does not match the deployment phase")

    observed_at = instant(current.get("observed_at"))
    archive_start = instant(documents[HISTORY_FILES["recent"]].get("record_started_at"))
    if archive_start > observed_at:
        raise ValueError("Current observation predates the archive")
    for cadence, path in HISTORY_FILES.items():
        tier = documents[path]
        if tier.get("station_id") != station_id or tier.get("deployment") != deployment:
            raise ValueError(f"{path} does not match the current station or dataset")
        if tier.get("cadence") != cadence or not isinstance(tier.get("rows"), list):
            raise ValueError(f"{path} does not match its cadence")
        through = instant(tier.get("through"))
        if instant(tier.get("record_started_at")) != archive_start or (tier["rows"] and through < archive_start):
            raise ValueError(f"{path} does not match the archive start")
        if check_watermarks and (through > observed_at or (cadence == "recent" and through != observed_at)):
            raise ValueError(f"{path} does not match the current observation interval")
    return deployment
