import json
import sys
from datetime import date

import pytest

from canones_weather import reference
from canones_weather.reference import document, noaa_rows


def test_noaa_excludes_failed_quality_and_presumed_zero_but_retains_trace():
    def line(element, values):
        slots = ["-9999   "] * 31
        for day, value, measurement, quality in values:
            slots[day - 1] = f"{value:5d}{measurement}{quality}0"
        return f"USC00290041202402{element}" + "".join(slots)

    text = "\n".join(
        [
            line("TMAX", [(1, 125, " ", " "), (2, 333, " ", "X")]),
            line("PRCP", [(1, 25, " ", " "), (3, 0, "P", " "), (4, 0, "T", " ")]),
        ]
    )
    rows = noaa_rows(text, date(2024, 2, 1), date(2024, 2, 29))
    assert rows[date(2024, 2, 1)] == {"temperature_max_c": 12.5, "rain_mm": 2.5}
    assert date(2024, 2, 2) not in rows
    assert date(2024, 2, 3) not in rows
    assert rows[date(2024, 2, 4)] == {"rain_mm": 0.0, "precipitation_trace": True}


def test_failed_provider_preserves_its_cache_and_does_not_stop_peer(tmp_path, monkeypatch):
    prior = tmp_path / "abiquiu.json"
    prior.write_text("previous validated snapshot\n")
    data = document(
        {"id": "albuquerque"}, {date(2025, 1, 1): {"temperature_min_c": 1.0}}, date(2025, 1, 1), date(2025, 1, 1)
    )

    def fetch(key, args):
        if key == "abiquiu":
            raise OSError("Provider unavailable")
        return {**data, "source": {"id": key}}

    monkeypatch.setattr(reference, "fetch_reference", fetch)
    monkeypatch.setattr(sys, "argv", ["reference", "--output", str(tmp_path)])
    assert reference.main() == 1
    assert prior.read_text() == "previous validated snapshot\n"
    for key in reference.NOAA_STATIONS.keys() - {"abiquiu"}:
        assert json.loads((tmp_path / f"{key}.json").read_text())["source"]["id"] == key


def test_abiquiu_supplement_recovers_absent_months_without_overriding_ghcn(monkeypatch):
    slots = ["-9999   "] * 31
    slots[30] = f"{306:5d} S0"  # GHCN rejected this value, despite ACIS supplying it.
    text = "USC00290041202401TMAX" + "".join(slots)
    rows = reference.noaa_rows(text, date(2024, 1, 31), date(2024, 2, 2))
    response = {
        "meta": {"sids": ["USC00290041 6"]},
        "data": [
            ["2024-01-31", ["32", " "], ["87", " "], ["0.10", " "]],
            ["2024-02-01", ["14", " "], ["50", " "], ["T", "T"]],
            ["2024-02-02", ["M", "M"], ["M", "M"], ["0.50", "S"]],
        ],
    }
    monkeypatch.setattr(reference, "download", lambda url: json.dumps(response))
    reference.supplement_abiquiu(text, rows, date(2024, 1, 31), date(2024, 2, 2))
    assert "temperature_max_c" not in rows[date(2024, 1, 31)]
    recovered = rows[date(2024, 2, 1)]
    assert recovered["temperature_min_c"] == -10
    assert recovered["temperature_max_c"] == 10
    assert recovered["rain_mm"] == 0 and recovered["precipitation_trace"]
    assert recovered["field_sources"] == {field: "rcc-acis" for field in reference.FIELDS.values()}
    assert date(2024, 2, 2) not in rows
    response["data"].pop()
    with pytest.raises(ValueError, match="Incomplete"):
        reference.supplement_abiquiu(text, rows, date(2024, 1, 31), date(2024, 2, 2))
    response["meta"]["sids"] = ["USW00023050 6"]
    with pytest.raises(ValueError, match="different station"):
        reference.supplement_abiquiu(text, rows, date(2024, 1, 31), date(2024, 2, 2))


def test_reference_day_preserves_precipitation_when_temperature_is_missing():
    day = date(2025, 7, 1)
    data = document({"id": "abiquiu"}, {day: {"rain_mm": 2.54}}, day, day)
    assert data["daily"][0]["rain_mm"] == 2.54
    assert data["daily"][0]["temperature_min_c"] is None
    assert data["daily"][0]["temperature_max_c"] is None
