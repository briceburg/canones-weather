from datetime import date

from canones_weather.reference import daymet_rows, document, noaa_rows


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


def test_daymet_leap_day_and_absent_december_31_preserve_calendar_gaps():
    text = """Elevation: 2328 meters
year,yday,prcp (mm/day),tmax (deg c),tmin (deg c)
2024,60,1.2,10,-3
2024,365,0,5,-5
"""
    start, end = date(2024, 2, 28), date(2024, 12, 31)
    rows, elevation = daymet_rows(text, start, end)
    assert elevation == 2328
    assert rows[date(2024, 2, 29)]["temperature_min_c"] == -3
    assert rows[date(2024, 12, 30)]["temperature_max_c"] == 5
    data = document({"id": "daymet", "type": "modeled"}, rows, start, end)
    assert data["kind"] == "reference"
    assert data["daily"][-1] == {
        "at": "2024-12-31T00:00:00-07:00",
        "temperature_min_c": None,
        "temperature_max_c": None,
        "rain_mm": None,
    }
    assert "temperature_c" not in data["daily"][-2]  # No invented daily mean.
