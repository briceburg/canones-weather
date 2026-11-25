import json
import sys
from datetime import date, datetime, timezone
from types import SimpleNamespace
from urllib.error import HTTPError

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
            line("AWND", [(1, 42, " ", " "), (2, 66, " ", "X")]),
        ]
    )
    rows = noaa_rows(text, date(2024, 2, 1), date(2024, 2, 29), include_wind=True)
    assert rows[date(2024, 2, 1)] == {"temperature_max_c": 12.5, "rain_mm": 2.5, "wind_speed_m_s": 4.2}
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
    for key in reference.STATIONS.keys() - {"abiquiu"}:
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


def test_uscrn_uses_native_daily_units_and_leaves_missing_fields_empty():
    text = """93245 20261119 2.622 -123.07 38.32 -9999.0 6.5 -9999.0 -9999.0 1.2 8.64 R 12.1 6.2 9.2 80.0 60.0 70.2
93245 20261120 2.622 -123.07 38.32 14.9 7.8 11.3 11.0 -9999.0 -9999.0 R 14.0 7.2 10.2 -9999.0 -9999.0 -9999.0
"""
    rows = reference.uscrn_rows(text, "USW00093245", 2026)
    assert rows == {
        date(2026, 11, 19): {"temperature_min_c": 6.5, "rain_mm": 1.2, "humidity_pct": 70.2},
        date(2026, 11, 20): {"temperature_min_c": 7.8, "temperature_max_c": 14.9},
    }
    with pytest.raises(ValueError, match="station"):
        reference.uscrn_rows(text, "USW00003062", 2026)
    with pytest.raises(ValueError, match="Incomplete USCRN annual file"):
        reference.uscrn_rows(text, "USW00093245", 2026, complete_year=True)


@pytest.mark.parametrize(("runner_day", "last_record"), [(1, 30), (2, 31), (3, 31)])
def test_bodega_refresh_handles_the_local_year_rollover(monkeypatch, runner_day, last_record):
    class RunnerTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, runner_day, 7, 17, tzinfo=timezone.utc).astimezone(tz or timezone.utc)

    def download(url):
        if "/2026/" in url:
            raise HTTPError(url, 404, "Not yet available", None, None)
        return (
            f"93245 202512{last_record} 2.622 -123.07 38.32 14.9 7.8 11.3 11.0 0.0 12.0 R 14.0 7.2 10.2 80.0 60.0 70.2"
        )

    monkeypatch.setattr(reference, "datetime", RunnerTime)
    monkeypatch.setattr(reference, "download", download)
    data = reference.fetch_reference("bodega", SimpleNamespace(start_year=2025, end_year=None))
    assert data["available_through"] == f"2025-12-{last_record}"
    assert len(data["source"]["download_urls"]) == 1


def test_aemet_parses_trace_and_skips_multiday_precipitation():
    first, last = date(2026, 11, 19), date(2026, 11, 20)
    records = [
        {"fecha": first.isoformat(), "indicativo": "B051A", "tmin": "7,8", "prec": "Ip", "hrMedia": "89"},
        {"fecha": last.isoformat(), "indicativo": "B051A", "tmax": "14,9", "prec": "Acum", "velmedia": "3,4"},
    ]
    assert reference.aemet_rows(records, "B051A", first, last) == {
        first: {"temperature_min_c": 7.8, "rain_mm": 0.0, "precipitation_trace": True, "humidity_pct": 89},
        last: {"temperature_max_c": 14.9, "wind_speed_m_s": 3.4},
    }
    with pytest.raises(ValueError, match="reporting calendar"):
        reference.aemet_rows([*records, records[-1]], "B051A", first, last)
