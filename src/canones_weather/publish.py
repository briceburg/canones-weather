"""Publish a consistent observation/history pair to a bucket-scoped R2 destination."""

import argparse
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config

log = logging.getLogger(__name__)


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


def publish(config):
    root = Path(config["source_root"])
    payloads = {name: (root / f"{name}.json").read_bytes() for name in ["history", "current"]}
    documents = {name: json.loads(body) for name, body in payloads.items()}
    current, history = documents["current"], documents["history"]
    if not current.get("observed_at") or current["observed_at"] != history.get("through"):
        raise ValueError("Current and history must describe the same observation interval")
    deployment = current.get("deployment", {})
    if any(document.get("kind") != "live" or document.get("schema_version") != 1 for document in documents.values()):
        raise ValueError("Only version-1 measured observations can be published")
    if current.get("station", {}).get("id") != "canones" or history.get("station_id") != "canones":
        raise ValueError("Publisher station identity does not match")
    if not deployment.get("dataset_id") or deployment != history.get("deployment"):
        raise ValueError("Current and history must belong to the same deployment dataset")
    if deployment.get("phase") == "pilot":
        if not deployment.get("notice") or current.get("outdoor", {}).get("verified") is not False:
            raise ValueError("Pilot observations need a notice and unverified provenance")
    elif deployment.get("phase") == "production":
        if current.get("outdoor", {}).get("verified") is not True:
            raise ValueError("Production observations require verified provenance")
    else:
        raise ValueError("Unknown deployment phase")
    client = publishing_client(config)
    prefix = config["key_prefix"].strip("/")
    for name, body in payloads.items():
        client.put_object(
            Bucket=config["bucket"],
            Key=f"{prefix}/{name}.json",
            Body=body,
            ContentType="application/json",
            CacheControl="public, max-age=60",
            Metadata={"deployment-phase": deployment["phase"], "dataset-id": deployment["dataset_id"]},
        )
        log.info("Published %s.json for dataset %s", name, deployment["dataset_id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    publish(json.loads(args.config.read_text()))


if __name__ == "__main__":
    main()
