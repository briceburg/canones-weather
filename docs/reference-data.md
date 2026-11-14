# Local historical controls

Historical controls provide context for Secco Creek; they do not backfill its
archive or establish past conditions at the property. Select either or both in
the dashboard's Live mode to compare daily temperature ranges and precipitation
in 1y, All, Seasons, or Monsoon. Selecting a control from a short-period view
opens All. Current conditions always remain the local station's observations.
Sample mode disables real controls to keep synthetic and measured data separate.

| Control | What it represents | Elevation |
| --- | --- | --- |
| Daymet | Estimated weather for the 1 km grid cell requested at Secco Creek's coordinates | 2,328 m, as returned by the provider |
| Abiquiu Dam, USC00290041 | NOAA daily observations, about 10.2 km / 6.3 mi away | 1,944.6 m |
| Secco Creek | Local station, with provenance and pilot status in its JSON | 2,151.888 m |

Daymet incorporates station observations and terrain in a gridded model. A
nearby grid cell can still miss inversions, shade, exposure, and localized storms.
Its grid elevation is about 176 m above the supplied Secco Creek elevation;
Abiquiu Dam is about 207 m below. Neither reference is verified ground truth for
this property's microclimate. Compare both against commissioned local data.

## Variables and boundaries

Controls contain daily minimum/maximum temperature in degrees Celsius and daily
precipitation in millimetres. Neither downloaded record supplies the daily mean
used by the local chart; no mean is invented from highs and lows. Wind, humidity,
and solar controls are unavailable. Reference precipitation includes snow water
equivalent, which is different from the WS90's rainfall measurement.

Daily timestamps label the provider's reporting date in America/Denver; they do
not imply that NOAA's observation periods end at midnight. NOAA missing values,
quality-flagged values, and presumed-zero measurements are excluded. Trace
precipitation remains a flagged zero and is identified in daily tooltips.
Multiday precipitation is not divided into invented daily totals.

Daymet includes February 29 but omits December 31 in leap years. The exported
calendar retains that date with null values. All gaps stay visible and reduce
coverage counts. Seasonal and monsoon values are calculated separately for each
source; missing days are never counted as dry or extrapolated into a complete
season. Totals from different observation windows need not be directly comparable.

The two references have distinct colors and source-specific legends/tooltips.
Time-series overlays mark the local archive's `record_started_at`, identifying
pilot collection separately from verified production. Seasonal categories show
source-specific day counts instead of implying a precise date on a seasonal bar.
The collector must export `record_started_at` for this marker to appear; it is
never inferred from the oldest point in a rolling window. Imported values never
enter WeeWX or Wunderground/CWOP submissions.

## Retrieved comparison

The bundled controls cover 2016–2025. A comparison retrieved in November 2026,
using dates available in both sources and the NOAA exclusions above, found:

| Statistic, Daymet minus Abiquiu | Matched days | Difference |
| --- | --- | --- |
| Mean daily high temperature | 3,243 | −3.21°C / −5.78°F |
| Mean daily low temperature | 3,173 | −1.83°C / −3.29°F |
| Precipitation total on matched dates | 3,271 | 3,445.77 vs 2,232.70 mm: Daymet 54.3% higher |

For June 15–September 30, all 108 dates are available in each source:

| Monsoon | Daymet | Abiquiu Dam |
| --- | --- | --- |
| 2024 | 217.15 mm / 8.55 in | 143.20 mm / 5.64 in |
| 2025 | 201.65 mm / 7.94 in | 107.30 mm / 4.22 in |

These differences are comparisons between sources, not error estimates against
Secco Creek. Daymet uses station inputs, so comparing it to a nearby station is
not necessarily an independent model validation.

## Refreshing controls

Both provider downloads are free and the command needs no credentials. The
bundled JSON records download URLs, citations, elevations, retrieval time, and
source notes. Retain those attributions when redistributing it; the repository's
software license does not replace provider data terms.

```sh
uv run python -m canones_weather.reference \
  --latitude 36.150028 --longitude=-106.445500 \
  --start-year 2016 --end-year 2025
bin/build-site
```

The command downloads both datasets before replacing the bundled files. It does
not run during a Pages build, contact the gateway, or modify the station archive.
Select completed years available from Daymet; availability can lag the calendar.
Review changed data and coverage in a PR when refreshing. Files are hosted with
the static site, independently of the Pi's current/history publisher.

## Provider links

- [Daymet single-pixel extraction](https://daymet.ornl.gov/web_services) and
  [calendar conventions](https://daymet.ornl.gov/single-pixel-tool-guide).
- [Daymet Version 4 R1 citation](https://doi.org/10.3334/ORNLDAAC/2129).
- [NOAA Abiquiu Dam record](https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/USC00290041.dly),
  [station metadata](https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt),
  [format/quality flags](https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt),
  and [GHCN-Daily citation](https://doi.org/10.7289/V5D21VHZ).
- [NOAA data access and public-domain guidance](https://www.noaa.gov/office-education/outreach-communication/faq).
