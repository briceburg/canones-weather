"""Assemble static sites with the shared station metadata."""

import json
import re
import shutil
from html import escape

from canones_weather.reference import STATIONS
from canones_weather.station import load_station

STATION_LOCATION = (36.150028, -106.4455)
SOURCE_STYLES = {
    "canones": ("#e4b17b", ()),
    "abiquiu": ("#66bfdc", (2, 4)),
    "santa-fe": ("#8ca4ff", (14, 5)),
    "albuquerque": ("#c3a3f8", (9, 4, 2, 4)),
    "gila-hot-springs": ("#b9d878", (2, 3, 2, 7)),
    "bodega": ("#5ad4b1", (7, 5)),
    "soller": ("#ed9bd1", (13, 4, 5, 4)),
    "charleston": ("#fc9089", (4, 5, 4, 8)),
    "crozier": ("#cad4e3", (17, 5, 2, 4, 2, 5)),
    "milwaukee": ("#a6dfeb", (11, 4, 3, 4, 3, 5)),
}

REFERENCE_GROUPS = {
    "Regional": (
        ("abiquiu", "Abiquiu Dam", "NM"),
        ("santa-fe", "Santa Fe airport", "NM"),
        ("albuquerque", "Albuquerque airport", "NM"),
        ("gila-hot-springs", "Gila Hot Springs", "NM"),
    ),
    "Coastal": (
        ("bodega", "Bodega Marine", "CA"),
        ("soller", "Port de Sóller", "Mallorca"),
        ("charleston", "Downtown Charleston", "SC"),
    ),
    "Places of Excellence": (
        ("crozier", "Crozier", "VA"),
        ("milwaukee", "Milwaukee airport", "WI"),
    ),
}


def map_url(latitude, longitude, zoom=14):
    return f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map={zoom}/{latitude}/{longitude}"


def source_option(key, name, place, url, *, metrics=None):
    color, dashes = SOURCE_STYLES[key]
    swatch = color
    if dashes:
        stops = []
        offset = 0
        for index, length in enumerate(dashes):
            fill = "transparent" if index % 2 else color
            stops.append(f"{fill} {offset}px {offset + length}px")
            offset += length
        swatch = f"repeating-linear-gradient(90deg, {', '.join(stops)})"
    pattern = " ".join(map(str, dashes))
    name = escape(name)
    input_id = f"reference-{key}" if metrics else "show-station-history"
    attributes = f'data-control="{key}" data-name="{name}" data-metrics="{metrics}"' if metrics else "checked"
    status = f'<span class="source-status" id="{input_id}-status" hidden>No data</span>' if metrics else ""
    return (
        f'<span class="reference-option" data-color="{color}" data-pattern="{pattern}" '
        f'style="--source-color: {color}; --source-swatch: {swatch}">'
        f'<input id="{input_id}" type="checkbox" {attributes} />'
        '<span class="source-swatch" aria-hidden="true"></span>'
        f'<span class="source-location"><span class="source-title"><label for="{input_id}">{name}</label>'
        f'<a class="source-map" href="{escape(url)}" aria-label="Map of {name} (opens in a new tab)" '
        f'target="_blank" rel="noopener"><span class="map-pin" aria-hidden="true"></span></a></span>'
        f'<span class="source-place">{escape(place)}</span>{status}</span></span>'
    )


def reference_groups():
    groups = []
    for title, options in REFERENCE_GROUPS.items():
        groups.append(f'<fieldset class="reference-group"><legend>{escape(title)}</legend><div class="reference-grid">')
        for key, name, place in options:
            reference = STATIONS[key]
            metrics = " ".join(("temperature", "rain", *reference.get("additional_metrics", ())))
            url = map_url(reference["latitude"], reference["longitude"])
            groups.append(source_option(key, name, place, url, metrics=metrics))
        groups.append("</div></fieldset>")
    return "\n".join(groups)


def render_html(source, station):
    # JSON string contents need JSON escaping; HTML entities do not work in scripts.
    name_json = json.dumps(station["name"], ensure_ascii=False)[1:-1].replace("<", r"\u003c")
    values = {
        "name": escape(station["name"]),
        "name_json": name_json,
        "timezone": escape(station["timezone"]),
        "latitude": str(STATION_LOCATION[0]),
        "longitude": str(STATION_LOCATION[1]),
        "map_url": escape(map_url(*STATION_LOCATION, zoom=15)),
    }

    return re.sub(r"\{\{ station\.(\w+) \}\}", lambda match: values[match[1]], source)


def build_site(repo_root, output_root):
    station = load_station()
    for name in ("hub", "canones"):
        source = repo_root / "site" / name
        target = output_root / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        shutil.copytree(repo_root / "site/shared/assets", target / "assets")
        shutil.copyfile(repo_root / "site/shared/_headers", target / "_headers")
        page = target / "index.html"
        html = render_html(page.read_text(encoding="utf-8"), station)
        if name == "canones":
            local_source = source_option(
                station["id"],
                station["name"],
                "NM",
                map_url(*STATION_LOCATION, zoom=15),
            )
            html = html.replace("{{ station_option }}", local_source)
            html = html.replace("{{ reference_groups }}", reference_groups())
        page.write_text(html, encoding="utf-8")
        config_path = target / "assets/site-config.json"
        config = json.loads(config_path.read_text())
        config["station"] = station
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if name == "canones":
            sample_path = target / "data/sample/current.json"
            sample = json.loads(sample_path.read_text())
            if any(sample["station"][key] != station[key] for key in ("id", "timezone")):
                raise ValueError("Regenerate sample fixtures after changing the station ID or time zone")
            sample["station"]["name"] = station["name"]
            sample_path.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
