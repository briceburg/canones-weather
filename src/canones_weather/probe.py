"""Read-only GW3000 HTTP API capture. Never configures or publishes data."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gateway",
        default=os.environ.get("WEATHER_GATEWAY_URL"),
        help="Gateway HTTP(S) origin; overrides WEATHER_GATEWAY_URL",
    )
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--output", type=Path, help="Save raw JSON responses and errors locally")
    args = parser.parse_args()
    if not args.gateway:
        parser.error("provide --gateway or set WEATHER_GATEWAY_URL")
    url = urlsplit(args.gateway)
    if (
        url.scheme not in ("http", "https")
        or not url.hostname
        or url.username
        or url.password
        or url.path not in ("", "/")
        or url.query
        or url.fragment
    ):
        parser.error("--gateway must be an HTTP(S) origin without credentials or a path")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    # Bypass proxy environment variables for LAN access.
    opener = build_opener(ProxyHandler({}))
    capture = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "gateway": args.gateway,
        "responses": {},
        "errors": {},
    }
    for endpoint in ("get_livedata_info", "get_sensors_info?page=1"):
        try:
            request = Request(args.gateway.rstrip("/") + "/" + endpoint, headers={"Accept": "application/json"})
            with opener.open(request, timeout=args.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("response exceeds 2 MB")
            data = json.loads(raw)
            capture["responses"][endpoint] = data
            print(f"OK {endpoint}: JSON {type(data).__name__}", file=sys.stderr)
        except (HTTPError, URLError, OSError, ValueError) as exc:
            capture["errors"][endpoint] = str(exc)
            print(f"FAILED {endpoint}: {exc}", file=sys.stderr)
    rendered = json.dumps(capture, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 1 if capture["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
