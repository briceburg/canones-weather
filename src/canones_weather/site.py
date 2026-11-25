"""Assemble static sites with the shared station metadata."""

import json
import shutil
from html import escape

from canones_weather.station import load_station


def render_html(source, station):
    # JSON string contents need JSON escaping; HTML entities do not work in scripts.
    name_json = json.dumps(station["name"], ensure_ascii=False)[1:-1].replace("<", r"\u003c")
    values = {
        "name": escape(station["name"]),
        "name_json": name_json,
        "timezone": escape(station["timezone"]),
    }
    for key, value in values.items():
        source = source.replace("{{ station." + key + " }}", value)
    if "{{ station." in source:
        raise ValueError("Unresolved station metadata in HTML")
    return source


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
        page.write_text(render_html(page.read_text(encoding="utf-8"), station), encoding="utf-8")
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
