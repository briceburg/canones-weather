"""Build attributed daily and hourly comparisons without changing the station archive."""

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
HOUR = timedelta(hours=1)
USCRN_STATIONS = {
    "bodega": ("CA_Bodega_6_WSW", 2008, timezone(timedelta(hours=-8))),
    "valles-caldera": ("NM_Los_Alamos_13_W", 2004, timezone(timedelta(hours=-7))),
}
HOURLY_METRICS = ("temperature", "rain", "humidity", "solar")
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
        "additional_metrics": ("wind",),
        "latitude": 35.0419,
        "longitude": -106.6156,
        "elevation_m": 1618.5,
    },
    "santa-fe": {
        "name": "Santa Fe airport · NOAA observations",
        "station_id": "USW00023049",
        "additional_metrics": ("wind",),
        "latitude": 35.6108,
        "longitude": -106.0958,
        "elevation_m": 1916.3,
    },
    "gila-hot-springs": {
        "name": "Gila Hot Springs · RCC-ACIS observations",
        "station_id": "USC00293530",
        "latitude": 33.1975,
        "longitude": -108.2075,
        "elevation_m": 1717.9,
        "provider": "RCC-ACIS",
    },
    "charleston": {
        "name": "Downtown Charleston · NOAA observations",
        "station_id": "USW00013782",
        "additional_metrics": ("wind",),
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
        "additional_metrics": ("humidity",),
    },
    "valles-caldera": {
        "name": "Valles Caldera · NOAA USCRN observations",
        "station_id": "USW00003062",
        "latitude": 35.8584,
        "longitude": -106.5214,
        "elevation_m": 2656.6,
        "provider": "USCRN",
        "additional_metrics": ("humidity",),
    },
    "milwaukee": {
        "name": "Milwaukee Mitchell Airport · NOAA observations",
        "station_id": "USW00014839",
        "additional_metrics": ("wind",),
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
        "additional_metrics": ("wind", "humidity"),
    },
}
ACIS_URL = "https://data.rcc-acis.org/StnData"
USCRN_URL = "https://www.ncei.noaa.gov/pub/data/uscrn/products/daily01/"
USCRN_HOURLY_URL = "https://www.ncei.noaa.gov/pub/data/uscrn/products/hourly02/"
USCRN_PRODUCT = "https://www.ncei.noaa.gov/products/land-based-station/us-climate-reference-network"
USCRN_HOURLY_FIELDS = (
    ("temperature_c", 9, None),
    ("temperature_min_c", 11, None),
    ("temperature_max_c", 10, None),
    ("rain_mm", 12, None),
    ("humidity_pct", 26, 27),
    ("solar_w_m2", 13, 14),
)
AEMET_DAILY_URL = "https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos"
AEMET_ARCHIVE_START = date(2020, 9, 1)
FIELDS = {"TMIN": "temperature_min_c", "TMAX": "temperature_max_c", "PRCP": "rain_mm"}
ADDITIONAL_FIELDS = ("wind_speed_m_s", "humidity_pct")


def download(url, *, api_key=None):
    request = Request(url, headers={"User-Agent": "canones-weather/0.1 (reference-data)"})
    if api_key:
        request.add_unredirected_header("api_key", api_key)
    with urlopen(request, timeout=60) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8-sig")


def noaa_rows(text, start, end, station_id="USC00290041", *, include_wind=False):
    fields = FIELDS | {"AWND": "wind_speed_m_s"} if include_wind else FIELDS
    rows = {}
    for line in text.splitlines():
        if line[:11] != station_id:
            raise ValueError("Unexpected NOAA station")
        year, month, element = int(line[11:15]), int(line[15:17]), line[17:21]
        if element not in fields or not start.year <= year <= end.year:
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
                row[fields[element]] = value / 10
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
        if len(columns) < 18 or columns[0] != station_id[-5:]:
            raise ValueError("Invalid USCRN station record")
        day = date.fromisoformat(columns[1])
        if day <= previous or day.year != year:
            raise ValueError("Invalid USCRN reporting calendar")
        previous = day
        values = {}
        for field, index in (
            ("temperature_min_c", 6),
            ("temperature_max_c", 5),
            ("rain_mm", 9),
            ("humidity_pct", 17),
        ):
            value = float(columns[index])
            if not math.isfinite(value):
                raise ValueError("Invalid USCRN observation")
            if value != -9999:
                values[field] = value
        if values:
            rows[day] = values
    if complete_year and previous != date(year, 12, 31):
        raise ValueError("Incomplete USCRN annual file")
    return rows


def uscrn_hourly_rows(text, station_id, year):
    rows = {}
    previous = datetime(year, 1, 1, tzinfo=timezone.utc) - HOUR
    for line in text.splitlines():
        columns = line.split()
        if len(columns) != 38 or columns[0] != station_id[-5:]:
            raise ValueError("Invalid USCRN hourly station record")
        # NOAA stamps the completed hour's end, including 00:00 of the next year.
        at = datetime.fromisoformat(f"{columns[1]}T{columns[2]}+00:00") - HOUR
        if at <= previous or at.year != year or at.minute or at.second or at.microsecond:
            raise ValueError("Invalid USCRN hourly reporting calendar")
        previous = at
        values, flags = {}, {}
        for field, index, flag_index in USCRN_HOURLY_FIELDS:
            value = float(columns[index])
            if not math.isfinite(value):
                raise ValueError("Invalid USCRN hourly observation")
            flag = columns[flag_index] if flag_index is not None else None
            if flag is not None:
                flags[field] = flag
            missing = -99999 if field == "solar_w_m2" else -9999
            values[field] = value if value != missing and flag in (None, "0") else None
        validate_ranges(values)
        rows[at] = {**values, "quality_flags": flags}
    if not rows:
        raise ValueError("Empty USCRN hourly file")
    return rows


def fetch_hourly_reference(key, *, now=None):
    now = now if now is not None else datetime.now(timezone.utc)
    end = now.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=30)
    station = STATIONS[key]
    name, _, _ = USCRN_STATIONS[key]
    rows, urls = {}, []
    for year in range(start.year, (end - HOUR).year + 1):
        url = f"{USCRN_HOURLY_URL}{year}/CRNH0203-{year}-{name}.txt"
        try:
            text = download(url)
        except HTTPError as error:
            if error.code != 404 or end.date() != date(year, 1, 1):
                raise
            break
        annual = uscrn_hourly_rows(text, station["station_id"], year)
        rows.update((at, values) for at, values in annual.items() if start <= at < end)
        urls.append(url)

    fields = tuple(field for field, _, _ in USCRN_HOURLY_FIELDS)
    latest = max((at for at, row in rows.items() if any(row[field] is not None for field in fields)), default=None)
    if latest is None:
        raise ValueError("USCRN hourly files contain no recent observations")
    first = min(rows)
    through = max(rows) + HOUR
    blank = dict.fromkeys(fields)
    hourly = []
    at = first
    while at < through:
        hourly.append({"at": at.isoformat(), **rows.get(at, blank)})
        at += HOUR
    return {
        "schema_version": 1,
        "kind": "reference",
        "source": {
            "id": key,
            "type": "observed",
            **station,
            "url": USCRN_PRODUCT,
            "download_urls": urls,
            "citation": USCRN_HOURLY_URL + "README.txt",
            "notes": "NOAA USCRN hourly02. UTC interval starts are one hour before NOAA's UTC timestamps.",
        },
        "retrieved_at": now.isoformat(),
        "start_at": first.isoformat(),
        "through": through.isoformat(),
        "available_through": (latest + HOUR).isoformat(),
        "hourly": hourly,
    }


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
        for field, key in (
            ("temperature_min_c", "tmin"),
            ("temperature_max_c", "tmax"),
            ("rain_mm", "prec"),
            ("wind_speed_m_s", "velmedia"),
            ("humidity_pct", "hrMedia"),
        ):
            raw = record.get(key, record.get(key.lower()))
            if raw is None or raw == "":
                continue
            if field == "rain_mm" and raw == "Acum":
                continue  # A multiday accumulation has no reliable one-day total.
            if field == "rain_mm" and raw == "Ip":
                values.update(rain_mm=0.0, precipitation_trace=True)
                continue
            value = float(str(raw).replace(",", "."))
            if not math.isfinite(value):
                raise ValueError("Invalid AEMET observation")
            values[field] = value
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


def validate_ranges(row):
    low, high = row.get("temperature_min_c"), row.get("temperature_max_c")
    humidity = row.get("humidity_pct")
    nonnegative = (row.get(field) for field in ("rain_mm", "wind_speed_m_s", "solar_w_m2"))
    if (
        (low is not None and high is not None and low > high)
        or (humidity is not None and not 0 <= humidity <= 100)
        or any(value is not None and value < 0 for value in nonnegative)
    ):
        raise ValueError("Invalid reference observation range")


def document(source, rows, start, end):
    required = dict.fromkeys(FIELDS.values())
    fields = (*required, *ADDITIONAL_FIELDS)
    daily, latest = [], None
    day = start
    while day <= end:
        values = rows.get(day, {})
        validate_ranges(values)
        if any(values.get(field) is not None for field in fields):
            latest = day
        daily.append({"at": datetime.combine(day, time(), ZONE).isoformat(), **required, **values})
        day += timedelta(days=1)
    if latest is None:
        raise ValueError("Reference download contains no observations")
    return {
        "schema_version": 1,
        "kind": "reference",
        "source": source,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "available_through": latest.isoformat(),
        "daily": daily,
    }


def ghcn_reference(key, station, start, end):
    url = f"https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/{station['station_id']}.dly"
    text = download(url)
    rows = noaa_rows(
        text, start, end, station["station_id"], include_wind="wind" in station.get("additional_metrics", ())
    )
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
    reporting_zone = (
        USCRN_STATIONS[key][2] if provider == "USCRN" else (ZoneInfo("Europe/Madrid") if provider == "AEMET" else None)
    )
    today = datetime.now(reporting_zone).date()
    end = date(args.end_year, 12, 31) if args.end_year else today - timedelta(days=1)
    source = {"id": key, "type": "observed", **station}
    if provider == "RCC-ACIS":
        rows, url = acis_rows(station["station_id"], start, end)
        source.update(
            url="https://docs.rcc-acis.org/acisws/",
            download_url=url,
            citation="https://www.weather.gov/climateservices/nowdatafaq",
            notes="Cooperative station reporting dates. Recent reports may be preliminary.",
        )
    elif provider == "USCRN":
        rows, urls = {}, []
        name, first_year, _ = USCRN_STATIONS[key]
        for year in range(max(start.year, first_year), end.year + 1):
            url = f"{USCRN_URL}{year}/CRND0103-{year}-{name}.txt"
            try:
                text = download(url)
            except HTTPError as error:
                if error.code != 404 or year != today.year or end != date(year, 1, 1):
                    raise
                break  # NOAA can post the first annual file after the first reporting day.
            urls.append(url)
            annual = uscrn_rows(text, station["station_id"], year, complete_year=date(year, 12, 31) <= end)
            rows.update((day, values) for day, values in annual.items() if start <= day <= end)
        source.update(
            url=USCRN_PRODUCT,
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
    parser.add_argument("--hourly", action="store_true", help="Refresh the rolling 30-day USCRN hourly feeds")
    parser.add_argument("--start-year", type=int, default=2016, help="First year for daily history")
    parser.add_argument("--end-year", type=int, help="Last completed year for daily history")
    parser.add_argument("--output", type=Path, default=Path("tmp/reference"))
    parser.add_argument("--publish-config", type=Path, help="Publish validated references to this R2 destination")
    args = parser.parse_args()
    sources = USCRN_STATIONS if args.hourly else STATIONS
    if args.source != "all" and args.source not in sources:
        parser.error("--hourly requires a USCRN source")
    if not 1 <= args.start_year <= (args.end_year or date.today().year) or (
        args.end_year and args.end_year >= date.today().year
    ):
        parser.error("Invalid year range; an explicit end year must be completed")
    config = json.loads(args.publish_config.read_text()) if args.publish_config else None
    failed = False
    for key in sources if args.source == "all" else [args.source]:
        try:
            if args.hourly:
                data = fetch_hourly_reference(key)
                path = f"hourly/{key}.json"
                start, end = data["start_at"], data["through"]
            else:
                data = fetch_reference(key, args)
                path = f"{key}.json"
                start, end = data["start_date"], data["end_date"]
            body = write_json(args.output / path, data)
            if config:
                from canones_weather.publish import publishing_client

                publishing_client(config).put_object(
                    Bucket=config["bucket"],
                    Key=f"{config['key_prefix'].strip('/')}/reference/{path}",
                    Body=body,
                    ContentType="application/json",
                    CacheControl="public, max-age=900" if args.hourly else "public, max-age=3600",
                )
            print(f"{key}: {start} through {end}")
        except Exception as error:
            print(f"{key} refresh failed: {error}", file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
