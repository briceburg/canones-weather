"""Build attributed daily comparison data without changing the station archive."""

import argparse
import csv
import io
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/Denver")
NOAA_ID = "USC00290041"
NOAA_URL = f"https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/{NOAA_ID}.dly"
DAYMET_URL = "https://daymet.ornl.gov/single-pixel/api/data"
FIELDS = {"TMIN": "temperature_min_c", "TMAX": "temperature_max_c", "PRCP": "rain_mm"}


def download(url):
    request = Request(url, headers={"User-Agent": "canones-weather/0.1 (reference-data)"})
    with urlopen(request, timeout=60) as response:
        return response.read().decode()


def noaa_rows(text, start, end):
    rows = {}
    for line in text.splitlines():
        if line[:11] != NOAA_ID:
            raise ValueError("Unexpected NOAA station")
        year, month, element = int(line[11:15]), int(line[15:17]), line[17:21]
        if element not in FIELDS or not start.year <= year <= end.year:
            continue
        for i in range(31):
            value = int(line[21 + 8 * i : 26 + 8 * i])
            measurement, quality = line[26 + 8 * i], line[27 + 8 * i]
            if value == -9999 or quality.strip() or measurement == "P":
                continue
            try:
                day = date(year, month, i + 1)
            except ValueError:
                continue
            if start <= day <= end:
                row = rows.setdefault(day, {})
                row[FIELDS[element]] = value / 10
                if element == "PRCP" and measurement == "T":
                    row["precipitation_trace"] = True
    return rows


def daymet_rows(text, start, end):
    elevation = float(
        next(line.split(":", 1)[1].split()[0] for line in text.splitlines() if line.startswith("Elevation:"))
    )
    rows = {}
    table = text[text.index("year,yday,") :]
    for row in csv.DictReader(io.StringIO(table)):
        day = date(int(row["year"]), 1, 1) + timedelta(days=int(row["yday"]) - 1)
        if not start <= day <= end:
            continue
        values = {}
        for field, column in (
            ("temperature_min_c", "tmin (deg c)"),
            ("temperature_max_c", "tmax (deg c)"),
            ("rain_mm", "prcp (mm/day)"),
        ):
            value = float(row[column])
            if value != -9999:
                values[field] = value
        rows[day] = values
    return rows, elevation


def document(source, rows, start, end):
    daily = []
    day = start
    while day <= end:
        daily.append(
            {
                "at": datetime.combine(day, time(), ZONE).isoformat(),
                "temperature_min_c": None,
                "temperature_max_c": None,
                "rain_mm": None,
                **rows.get(day, {}),
            }
        )
        day += timedelta(days=1)
    if not any(row["temperature_min_c"] is not None for row in daily):
        raise ValueError("Reference download contains no temperature data")
    return {
        "schema_version": 1,
        "kind": "reference",
        "source": source,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "available_through": max(
            day for day, values in rows.items() if any(value is not None for value in values.values())
        ).isoformat(),
        "daily": daily,
    }


def fetch_reference(key, args):
    start = date(args.start_year, 1, 1)
    end = date(args.end_year, 12, 31) if args.end_year else date.today() - timedelta(days=1)
    citation, elevation = None, None
    if key == "daymet":
        url = (
            DAYMET_URL
            + "?"
            + urlencode(
                {
                    "lat": args.latitude,
                    "lon": args.longitude,
                    "vars": "tmax,tmin,prcp",
                    **(
                        {"years": ",".join(str(y) for y in range(args.start_year, args.end_year + 1))}
                        if args.end_year
                        else {}
                    ),
                    "format": "csv",
                }
            )
        )
        text = download(url)
        citation = re.search(r"https://doi\.org/[^\s;]+", text)
        if citation is None:
            raise ValueError("Daymet response is missing its dataset citation")
        rows, elevation = daymet_rows(text, start, end)
        latest_year = max(rows).year
        if args.end_year and latest_year < args.end_year:
            raise ValueError("Requested Daymet year is not available")
        end = date(latest_year, 12, 31)
    else:
        rows = noaa_rows(download(NOAA_URL), start, end)
        end = max(rows)
    sources = {
        "daymet": (
            {
                "id": "daymet",
                "name": "Daymet · Cañones grid estimate",
                "type": "modeled",
                "url": "https://daymet.ornl.gov/",
                "download_url": url if key == "daymet" else None,
                "citation": citation.group() if citation else None,
                "latitude": args.latitude,
                "longitude": args.longitude,
                "elevation_m": elevation,
                "notes": "1 km gridded estimate, not a station measurement. Grid elevation differs from Secco Creek. Leap-year December 31 is absent; gaps are preserved.",
            },
            rows,
        ),
        "abiquiu": (
            {
                "id": "abiquiu",
                "name": "Abiquiu Dam · NOAA observations",
                "type": "observed",
                "station_id": NOAA_ID,
                "url": "https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily",
                "download_url": NOAA_URL,
                "citation": "https://doi.org/10.7289/V5D21VHZ",
                "latitude": 36.2403,
                "longitude": -106.4278,
                "elevation_m": 1944.6,
                "notes": "Daily reporting dates may cover non-midnight observation periods. NOAA quality-flagged, missing, and presumed-zero values are excluded; trace precipitation is retained as flagged zero.",
            },
            rows,
        ),
    }
    source, _ = sources[key]
    return document(source, rows, start, end)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n").encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(body)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["daymet", "abiquiu", "both"], default="both")
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-year", type=int, help="Limit to this completed year; otherwise use available data")
    parser.add_argument("--output", type=Path, default=Path("tmp/reference"))
    parser.add_argument("--publish-config", type=Path, help="Publish validated references to this R2 destination")
    args = parser.parse_args()
    if not -90 <= args.latitude <= 90 or not -180 <= args.longitude <= 180:
        parser.error("Invalid coordinates")
    if not 1980 <= args.start_year <= (args.end_year or date.today().year) or (
        args.end_year and args.end_year >= date.today().year
    ):
        parser.error("Invalid year range; an explicit end year must be completed")
    config = json.loads(args.publish_config.read_text()) if args.publish_config else None
    failed = False
    for key in ["daymet", "abiquiu"] if args.source == "both" else [args.source]:
        try:
            data = fetch_reference(key, args)
            body = save(args.output / f"{key}.json", data)
            if config:
                from canones_weather.publish import publishing_client

                publishing_client(config).put_object(
                    Bucket=config["bucket"],
                    Key=f"{config['key_prefix'].strip('/')}/reference/{key}.json",
                    Body=body,
                    ContentType="application/json",
                    CacheControl="public, max-age=3600",
                )
            print(f"{key}: {data['start_date']} through {data['end_date']}")
        except Exception as error:
            print(f"{key} refresh failed: {error}", file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
