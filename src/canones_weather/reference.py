"""Build attributed daily comparison data without changing the station archive."""

import argparse
import csv
import io
import json
import math
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from canones_weather.jsonio import write_json

ZONE = ZoneInfo("America/Denver")
NOAA_STATIONS = {
    "abiquiu": {
        "name": "Abiquiu Dam · NOAA + RCC-ACIS observations",
        "station_id": "USC00290041",
        "latitude": 36.2403,
        "longitude": -106.4278,
        "elevation_m": 1944.6,
    },
    "albuquerque": {
        "name": "Albuquerque airport · NOAA observations",
        "station_id": "USW00023050",
        "latitude": 35.0419,
        "longitude": -106.6156,
        "elevation_m": 1618.5,
    },
    "madrid": {
        "name": "Madrid 1.9 SE · NOAA/CoCoRaHS precipitation",
        "station_id": "US1NMSF0189",
        "latitude": 35.3845,
        "longitude": -106.1301,
        "elevation_m": 1923.6,
    },
}
ACIS_URL = "https://data.rcc-acis.org/StnData"
DAYMET_URL = "https://daymet.ornl.gov/single-pixel/api/data"
FIELDS = {"TMIN": "temperature_min_c", "TMAX": "temperature_max_c", "PRCP": "rain_mm"}


def download(url):
    request = Request(url, headers={"User-Agent": "canones-weather/0.1 (reference-data)"})
    with urlopen(request, timeout=60) as response:
        return response.read().decode()


def noaa_rows(text, start, end, station_id="USC00290041"):
    rows = {}
    for line in text.splitlines():
        if line[:11] != station_id:
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


def supplement_abiquiu(text, rows, start, end):
    # Only absent monthly records are eligible; never override GHCN QC or explicit missing days.
    reported = {(int(line[11:15]), int(line[15:17]), line[17:21]) for line in text.splitlines()}
    station_id = NOAA_STATIONS["abiquiu"]["station_id"]
    params = {
        "sid": f"{station_id} 6",
        "sdate": start.isoformat(),
        "edate": end.isoformat(),
        "elems": [{"name": name, "add": "f"} for name in ["mint", "maxt", "pcpn"]],
        "meta": "sids,name,ll,elev",
    }
    url = ACIS_URL + "?" + urlencode({"params": json.dumps(params)})
    data = json.loads(download(url))
    if f"{station_id} 6" not in data.get("meta", {}).get("sids", []):
        raise ValueError("ACIS returned a different station")
    previous = start - timedelta(days=1)
    for record in data["data"]:
        day = date.fromisoformat(record[0])
        if day != previous + timedelta(days=1) or day > end:
            raise ValueError("Invalid ACIS reporting dates")
        previous = day
        for element, (value, flag) in zip(["TMIN", "TMAX", "PRCP"], record[1:], strict=True):
            if (day.year, day.month, element) in reported or flag.strip() not in ["", "T"]:
                continue
            if flag == "T" and element != "PRCP":
                continue
            converted = 0.0 if value == "T" else float(value)
            converted = converted * 25.4 if element == "PRCP" else (converted - 32) * 5 / 9
            if not math.isfinite(converted) or (element == "PRCP" and converted < 0):
                raise ValueError("Invalid ACIS observation")
            field = FIELDS[element]
            row = rows.setdefault(day, {})
            row[field] = round(converted, 4)
            row.setdefault("field_sources", {})[field] = "rcc-acis"
            if flag == "T":
                row["precipitation_trace"] = True
    if previous != end:
        raise ValueError("Incomplete ACIS reporting calendar")
    return {
        "provider": "RCC-ACIS",
        "download_url": url,
        "notes": "Same-station supplemental reports for months absent from GHCN. May include preliminary data. GHCN values, QC exclusions and explicit missing days take precedence; no estimates or other stations fill gaps.",
    }


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
    if not any(row[field] is not None for row in daily for field in FIELDS.values()):
        raise ValueError("Reference download contains no observations")
    for row in daily:
        low, high = row["temperature_min_c"], row["temperature_max_c"]
        if (low is not None and high is not None and low > high) or (row["rain_mm"] is not None and row["rain_mm"] < 0):
            raise ValueError("Invalid reference observation range")
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
        source = {
            "id": "daymet",
            "name": "Daymet · Cañones grid estimate",
            "type": "modeled",
            "url": "https://daymet.ornl.gov/",
            "download_url": url,
            "citation": citation.group(),
            "latitude": args.latitude,
            "longitude": args.longitude,
            "elevation_m": elevation,
            "notes": "1 km gridded estimate, not a station measurement. Grid elevation differs from Secco Creek. Leap-year December 31 is absent; gaps are preserved.",
        }
    else:
        station = NOAA_STATIONS[key]
        url = f"https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/{station['station_id']}.dly"
        text = download(url)
        rows = noaa_rows(text, start, end, station["station_id"])
        source = {
            "id": key,
            "type": "observed",
            **station,
            "url": "https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily",
            "download_url": url,
            "citation": "https://doi.org/10.7289/V5D21VHZ",
            "notes": "Regional comparison, not Secco Creek weather. Reporting dates may cover non-midnight periods. Quality-flagged, missing and presumed-zero values are excluded; trace precipitation is flagged zero. ",
        }
        if key == "abiquiu":
            source["supplement"] = supplement_abiquiu(text, rows, start, end)
        start, end = max(start, min(rows)), max(rows)
    return document(source, rows, start, end)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["daymet", *NOAA_STATIONS, "all"], default="all")
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
    for key in ["daymet", *NOAA_STATIONS] if args.source == "all" else [args.source]:
        try:
            data = fetch_reference(key, args)
            body = write_json(args.output / f"{key}.json", data)
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
