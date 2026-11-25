"""Assemble static sites with the shared station metadata."""

import json
import re
import shutil
from html import escape

from canones_weather.reference import STATIONS
from canones_weather.station import load_station

REFERENCE_GROUPS = {
    "New Mexico": (
        ("abiquiu", "Abiquiu Dam", ""),
        ("santa-fe", "Santa Fe airport", ""),
        ("albuquerque", "Albuquerque airport", ""),
        ("gila-hot-springs", "Gila Hot Springs", ""),
    ),
    "Coastal": (
        ("bodega", "Bodega Marine", ", CA"),
        ("soller", "Port de Sóller", ", Mallorca · © AEMET"),
        ("charleston", "Downtown Charleston", ", SC"),
    ),
    "Places of Excellence": (
        ("crozier", "Crozier", ", VA"),
        ("milwaukee", "Milwaukee airport", ", WI"),
    ),
}


def reference_groups():
    groups = []
    for title, options in REFERENCE_GROUPS.items():
        groups.append(f'<fieldset class="reference-group"><legend>{escape(title)}</legend>')
        for key, name, place in options:
            reference = STATIONS[key]
            lat, lon = reference["latitude"], reference["longitude"]
            url = f"https://www.openstreetmap.org/?mlat={lat}&amp;mlon={lon}#map=14/{lat}/{lon}"
            name = escape(name)
            hint = f'<span class="muted">{escape(place)}</span>' if place else ""
            groups.append(
                f'<span class="reference-option"><label><input type="checkbox" data-control="{key}" data-name="{name}" /> '
                f'<span>{name}{hint}</span></label><a href="{url}" '
                f'aria-label="Map of {name} (opens in a new tab)" target="_blank" rel="noopener">📍</a></span>'
            )
        groups.append("</fieldset>")
    return "\n".join(groups)


def render_html(source, station):
    # JSON string contents need JSON escaping; HTML entities do not work in scripts.
    name_json = json.dumps(station["name"], ensure_ascii=False)[1:-1].replace("<", r"\u003c")
    values = {
        "name": escape(station["name"]),
        "name_json": name_json,
        "timezone": escape(station["timezone"]),
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
