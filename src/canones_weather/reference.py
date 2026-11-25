"""Build attributed daily comparison data without changing the station archive."""

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from canones_weather.jsonio import write_json

ZONE = ZoneInfo("America/Denver")
STATIONS = {
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
    "santa-fe": {
        "name": "Santa Fe airport · NOAA observations",
        "station_id": "USW00023049",
        "latitude": 35.6108,
        "longitude": -106.0958,
        "elevation_m": 1916.3,
    },
    "charleston": {
        "name": "Downtown Charleston · NOAA observations",
        "station_id": "USW00013782",
        "latitude": 32.7750,
        "longitude": -79.9239,
        "elevation_m": 3.0,
    },
    "crozier": {
        "name": "Crozier · RCC-ACIS observations",
        "station_id": "USC00442142",
        "latitude": 37.6664,
        "longitude": -77.8769,
        "elevation_m": 85.3,
        "provider": "RCC-ACIS",
    },
    "bodega": {
        "name": "Bodega Marine Laboratory · NOAA USCRN observations",
        "station_id": "USW00093245",
        "latitude": 38.3208,
        "longitude": -123.0747,
        "elevation_m": 19.2,
        "provider": "USCRN",
    },
    "milwaukee": {
        "name": "Milwaukee Mitchell Airport · NOAA observations",
        "station_id": "USW00014839",
        "latitude": 42.9550,
        "longitude": -87.9044,
        "elevation_m": 203.3,
    },
    "soller": {
        "name": "Port de Sóller · AEMET observations",
        "station_id": "B051A",
        "latitude": 39.7956,
        "longitude": 2.6914,
        "elevation_m": 5.0,
        "provider": "AEMET",
    },
}
ACIS_URL = "https://data.rcc-acis.org/StnData"
USCRN_URL = "https://www.ncei.noaa.gov/pub/data/uscrn/products/daily01/"
AEMET_DAILY_URL = "https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos"
AEMET_ARCHIVE_START = date(2020, 9, 1)
FIELDS = {"TMIN": "temperature_min_c", "TMAX": "temperature_max_c", "PRCP": "rain_mm"}


def download(url, *, api_key=None):
    request = Request(url, headers={"User-Agent": "canones-weather/0.1 (reference-data)"})
    if api_key:
        request.add_unredirected_header("api_key", api_key)
    with urlopen(request, timeout=60) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8-sig")


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


def acis_rows(station_id, start, end, *, excluded_months=()):
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
    rows = {}
    for record in data["data"]:
        day = date.fromisoformat(record[0])
        if day != previous + timedelta(days=1) or day > end:
            raise ValueError("Invalid ACIS reporting dates")
        previous = day
        for element, (value, flag) in zip(["TMIN", "TMAX", "PRCP"], record[1:], strict=True):
            if (day.year, day.month, element) in excluded_months or flag.strip() not in ["", "T"]:
                continue
            trace = flag == "T" or value == "T"
            if trace and element != "PRCP":
                continue
            converted = 0.0 if trace else float(value)
            converted = converted * 25.4 if element == "PRCP" else (converted - 32) * 5 / 9
            if not math.isfinite(converted) or (element == "PRCP" and converted < 0):
                raise ValueError("Invalid ACIS observation")
            field = FIELDS[element]
            row = rows.setdefault(day, {})
            row[field] = round(converted, 4)
            if trace:
                row["precipitation_trace"] = True
    if previous != end:
        raise ValueError("Incomplete ACIS reporting calendar")
    return rows, url


def supplement_abiquiu(text, rows, start, end):
    # Only absent monthly records are eligible; never override GHCN QC or explicit missing days.
    reported = {(int(line[11:15]), int(line[15:17]), line[17:21]) for line in text.splitlines()}
    supplement, url = acis_rows(STATIONS["abiquiu"]["station_id"], start, end, excluded_months=reported)
    for day, values in supplement.items():
        field_sources = {field: "rcc-acis" for field in FIELDS.values() if field in values}
        rows.setdefault(day, {}).update(values, field_sources=field_sources)
    return {
        "provider": "RCC-ACIS",
        "download_url": url,
        "notes": "Same-station supplemental reports for months absent from GHCN. May include preliminary data. GHCN values, QC exclusions and explicit missing days take precedence; no estimates or other stations fill gaps.",
    }


def uscrn_rows(text, station_id, year, *, complete_year=False):
    rows = {}
    previous = date(year, 1, 1) - timedelta(days=1)
    for line in text.splitlines():
        columns = line.split()
        if len(columns) < 10 or columns[0] != station_id[-5:]:
            raise ValueError("Invalid USCRN station record")
        day = date.fromisoformat(columns[1])
        if day <= previous or day.year != year:
            raise ValueError("Invalid USCRN reporting calendar")
        previous = day
        # The daily01 product reports Celsius and millimetres. Invalid inputs become missing values.
        values = {}
        for element, index in (("TMIN", 6), ("TMAX", 5), ("PRCP", 9)):
            value = float(columns[index])
            if not math.isfinite(value):
                raise ValueError("Invalid USCRN observation")
            if value != -9999:
                values[FIELDS[element]] = value
        if values:
            rows[day] = values
    if complete_year and previous != date(year, 12, 31):
        raise ValueError("Incomplete USCRN annual file")
    return rows


def aemet_rows(records, station_id, start, end):
    rows = {}
    previous = start - timedelta(days=1)
    for record in records:
        day = date.fromisoformat(record["fecha"])
        if record.get("indicativo") != station_id:
            raise ValueError("AEMET returned a different station")
        if day <= previous or day > end:
            raise ValueError("Invalid AEMET reporting calendar")
        previous = day
        values = {}
        for element, key in (("TMIN", "tmin"), ("TMAX", "tmax"), ("PRCP", "prec")):
            raw = record.get(key)
            if raw is None or raw == "":
                continue
            if element == "PRCP" and raw == "Acum":
                continue  # A multiday accumulation has no reliable one-day total.
            if element == "PRCP" and raw == "Ip":
                values.update(rain_mm=0.0, precipitation_trace=True)
                continue
            value = float(str(raw).replace(",", "."))
            if not math.isfinite(value):
                raise ValueError("Invalid AEMET observation")
            values[FIELDS[element]] = value
        if values:
            rows[day] = values
    return rows


def aemet_reference(station_id, start, end):
    key = os.environ.get("AEMET_API_KEY")
    if not key:
        raise ValueError("AEMET_API_KEY is required for Port de Sóller")
    rows, urls = {}, []
    start = max(start, AEMET_ARCHIVE_START)
    while start <= end:
        stop = min(end, start + timedelta(days=179))
        url = f"{AEMET_DAILY_URL}/fechaini/{start}T00:00:00UTC/fechafin/{stop}T23:59:59UTC/estacion/{station_id}"
        try:
            reply = json.loads(download(url, api_key=key))
        except HTTPError as error:
            if error.code != 404:
                raise
            reply = {"estado": 404}
        if reply.get("estado") == 404 and end - start < timedelta(days=7):
            break  # A new date window can start before AEMET has posted its first report.
        if reply.get("estado") != 200:
            raise ValueError(f"AEMET did not return data for {start} through {stop}")
        data_url = reply["datos"]
        address = urlsplit(data_url)
        if (address.scheme, address.netloc) != ("https", "opendata.aemet.es"):
            raise ValueError("Unexpected AEMET download origin")
        window = aemet_rows(json.loads(download(data_url)), station_id, start, stop)
        if not window:
            raise ValueError(f"Empty AEMET date window starting {start}")
        rows.update(window)
        urls.append(url)
        start = stop + timedelta(days=1)
    return rows, urls


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
            day for day, values in rows.items() if any(values.get(field) is not None for field in FIELDS.values())
        ).isoformat(),
        "daily": daily,
    }


def ghcn_reference(key, station, start, end):
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
        "notes": "Regional comparison, not local station measurements. Reporting dates may cover non-midnight periods. Quality-flagged, missing and presumed-zero values are excluded; trace precipitation is flagged zero.",
    }
    if key == "abiquiu":
        source["supplement"] = supplement_abiquiu(text, rows, start, end)
    return rows, source


def fetch_reference(key, args):
    start = date(args.start_year, 1, 1)
    station = STATIONS[key]
    provider = station.get("provider")
    today = datetime.now(ZoneInfo("Europe/Madrid")).date() if provider == "AEMET" else date.today()
    end = date(args.end_year, 12, 31) if args.end_year else today - timedelta(days=1)
    source = {"id": key, "type": "observed", **station}
    if provider == "RCC-ACIS":
        rows, url = acis_rows(station["station_id"], start, end)
        source.update(
            url="https://docs.rcc-acis.org/acisws/",
            download_url=url,
            citation="https://www.weather.gov/climateservices/nowdatafaq",
            notes="Crozier cooperative station reporting dates. Recent reports may be preliminary.",
        )
    elif provider == "USCRN":
        rows, urls = {}, []
        for year in range(max(start.year, 2008), end.year + 1):
            url = f"{USCRN_URL}{year}/CRND0103-{year}-CA_Bodega_6_WSW.txt"
            urls.append(url)
            annual = uscrn_rows(download(url), station["station_id"], year, complete_year=date(year, 12, 31) <= end)
            rows.update((day, values) for day, values in annual.items() if start <= day <= end)
        source.update(
            url="https://www.ncei.noaa.gov/products/land-based-station/us-climate-reference-network",
            download_urls=urls,
            citation=USCRN_URL + "README.txt",
            notes="NOAA USCRN daily01 observations. Dates retain the station's local standard time calendar.",
        )
    elif provider == "AEMET":
        rows, urls = aemet_reference(station["station_id"], start, end)
        source.update(
            url="https://www.aemet.es/en/eltiempo/observacion/ultimosdatos?l=B051A",
            download_urls=urls,
            citation="© AEMET (Agencia Estatal de Meteorología), daily climatological observations",
            reuse_terms="https://www.aemet.es/en/nota_legal",
            notes="Values retain AEMET's reporting dates. Trace precipitation is flagged zero and multiday accumulations are omitted.",
        )
    else:
        rows, source = ghcn_reference(key, station, start, end)
    if not rows:
        raise ValueError("Reference download contains no observations in the requested period")
    return document(source, rows, min(rows), max(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=[*STATIONS, "all"], default="all")
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-year", type=int, help="Limit to this completed year; otherwise use available data")
    parser.add_argument("--output", type=Path, default=Path("tmp/reference"))
    parser.add_argument("--publish-config", type=Path, help="Publish validated references to this R2 destination")
    args = parser.parse_args()
    if not 1 <= args.start_year <= (args.end_year or date.today().year) or (
        args.end_year and args.end_year >= date.today().year
    ):
        parser.error("Invalid year range; an explicit end year must be completed")
    config = json.loads(args.publish_config.read_text()) if args.publish_config else None
    failed = False
    for key in STATIONS if args.source == "all" else [args.source]:
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
