"""Publish changed weather snapshots to a bucket-scoped R2 destination."""

import argparse
import fcntl
import json
import logging
import os
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config

from canones_weather.jsonio import write_json
from canones_weather.station import load_station

log = logging.getLogger(__name__)
CADENCES = ("daily", "hourly", "recent")


def publishing_client(config):
    endpoint = urlsplit(config["endpoint_url"])
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or not endpoint.hostname.endswith(".r2.cloudflarestorage.com")
    ):
        raise ValueError("Publisher endpoint must be an R2 HTTPS origin")
    return boto3.client(
        "s3",
        endpoint_url=config["endpoint_url"],
        region_name="auto",
        config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}),
    )


def instant(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed
    except (TypeError, ValueError):
        pass
    raise ValueError("Publisher timestamps must include a time zone")


def validate_payloads(payloads):
    documents = {name: json.loads(body) for name, body in payloads.items()}
    if any(document.get("kind") != "live" or document.get("schema_version") != 1 for document in documents.values()):
        raise ValueError("Only version-1 measured observations can be published")
    current = documents["current.json"]
    recent = documents["history/recent.json"]
    observed_at = instant(current.get("observed_at"))
    record_started_at = instant(recent.get("record_started_at"))
    if observed_at != instant(recent.get("through")) or record_started_at > observed_at:
        raise ValueError("Current and recent history must describe the same observation interval")
    deployment = current.get("deployment", {})
    station_id = load_station()["id"]
    if current.get("station", {}).get("id") != station_id:
        raise ValueError("Publisher station identity does not match")
    for cadence in CADENCES:
        tier = documents[f"history/{cadence}.json"]
        if tier.get("station_id") != station_id:
            raise ValueError("Publisher station identity does not match")
        if not deployment.get("dataset_id") or deployment != tier.get("deployment"):
            raise ValueError("Current and history must belong to the same deployment dataset")
        if tier.get("cadence") != cadence or not isinstance(tier.get("rows"), list):
            raise ValueError("History payload does not match its cadence")
        if instant(tier.get("record_started_at")) != record_started_at:
            raise ValueError("History payloads must describe the same archive start")
        through = instant(tier.get("through"))
        if through > observed_at or (tier["rows"] and through < record_started_at):
            raise ValueError("History coverage does not match the observation interval")
    if deployment.get("phase") == "pilot":
        if not deployment.get("notice") or current.get("outdoor", {}).get("verified") is not False:
            raise ValueError("Pilot observations need a notice and unverified provenance")
    elif deployment.get("phase") == "production":
        if current.get("outdoor", {}).get("verified") is not True:
            raise ValueError("Production observations require verified provenance")
    else:
        raise ValueError("Unknown deployment phase")
    return deployment


def publish(config, *, state_dir):
    root = Path(config["source_root"])
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    prefix = config["key_prefix"].strip("/")
    destination = [config["endpoint_url"], config["bucket"], prefix]
    receipt = state_dir / (sha256(json.dumps(destination).encode()).hexdigest() + ".json")
    with receipt.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # The collector commits current last. Read it first, then reject a newer recent tier.
        current = (root / "current.json").read_bytes()
        paths = [f"history/{cadence}.json" for cadence in CADENCES]
        payloads = {name: (root / name).read_bytes() for name in paths}
        payloads["current.json"] = current
        deployment = validate_payloads(payloads)
        try:
            receipts = json.loads(receipt.read_bytes())
        except (FileNotFoundError, ValueError):
            receipts = {}
        if not isinstance(receipts, dict):
            receipts = {}
        client = None
        for name, body in payloads.items():
            digest = sha256(body).hexdigest()
            if receipts.get(name) == digest:
                continue
            if client is None:
                client = publishing_client(config)
            client.put_object(
                Bucket=config["bucket"],
                Key=f"{prefix}/{name}",
                Body=body,
                ContentType="application/json",
                CacheControl="public, max-age=60",
                Metadata={"deployment-phase": deployment["phase"], "dataset-id": deployment["dataset_id"]},
            )
            receipts[name] = digest
            write_json(receipt, receipts)
            log.info("Published %s for dataset %s", name, deployment["dataset_id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--state-dir", type=Path, default=os.getenv("STATE_DIRECTORY"), help="Private directory for upload receipts"
    )
    args = parser.parse_args()
    if args.state_dir is None:
        parser.error("set --state-dir when running outside the publisher service")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    publish(json.loads(args.config.read_text()), state_dir=args.state_dir)


if __name__ == "__main__":
    main()
