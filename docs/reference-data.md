# Regional reference history

Reference history compares weather across locations: for example, Albuquerque's
monsoon rain against Secco Spring's. Sources need not share the station's climate;
they never backfill its archive or establish past conditions at the property.
Select references in the dashboard to compare temperature and precipitation
in 30d, 1y, 3y, All, Seasons, or Monsoon. Unsupported views preserve source
selections without changing the period or measurement. Current conditions always
remain the local station's observations.
Sample mode can overlay the same real controls against an explicitly labeled
synthetic station series. Its archive-start marker is illustrative, not a station
commissioning date. Sample mode ends at its fixed fixture timestamp. Use Live
mode for dates after the sample timeline.

| Control | What it represents | Elevation |
| --- | --- | --- |
| Abiquiu Dam, USC00290041 | NOAA daily observations, supplemented by same-station RCC-ACIS reports; about 10.2 km / 6.3 mi away | 1,944.6 m |
| Albuquerque airport, USW00023050 | Regional NOAA temperature and precipitation observations | 1,618.5 m |
| Santa Fe airport, USW00023049 | Regional NOAA temperature and precipitation observations, about 68 km / 42 mi away | 1,916.3 m |
| Secco Spring | Local station, with provenance and pilot status in its JSON | 2,151.888 m |

Abiquiu Dam is about 207 m below Secco Spring. Differences in terrain, elevation,
exposure, and storms are part of these regional comparisons.

Use Albuquerque and Santa Fe airports for recent regional daily temperature and
precipitation comparisons. Their GHCN-Daily records can lag while NOAA processes
the observations. Abiquiu Dam is the closest historical comparison and can have
gaps within its record and at the most recent dates.

## Variables and boundaries

References contain daily minimum/maximum temperature in degrees Celsius and daily
precipitation in millimetres. No reference supplies
the daily mean used by the local chart; no mean is invented from highs and lows. Wind, humidity,
and solar controls are unavailable. Reference precipitation includes snow water
equivalent, which is different from the WS90's rainfall measurement.

Daily timestamps label the provider's reporting date in America/Denver; they do
not imply that NOAA's observation periods end at midnight. NOAA missing values,
quality-flagged values, and presumed-zero measurements are excluded. Trace
precipitation remains a flagged zero and is identified in daily tooltips.
Multiday precipitation is not divided into invented daily totals.

Missing dates stay visible and reduce coverage counts.
Seasonal and monsoon values are calculated separately for each
source; missing days are never counted as dry or extrapolated into a complete
season. Totals from different observation windows need not be directly comparable.

Chart legends and tooltips identify each reference source.
Time-series overlays mark the local archive's `record_started_at`, identifying
pilot collection separately from verified production. Seasonal categories show
source-specific day counts instead of implying a precise date on a seasonal bar.
The collector must export `record_started_at` for this marker to appear; it is
never inferred from the oldest point in a rolling window. Imported values never
enter WeeWX or Wunderground/CWOP submissions.

## Abiquiu gaps and supplemental reports

A November 2026 audit found 12 whole months absent from GHCN's Abiquiu file
across 2016–2025. These omissions are distinct from individual missing values and
quality exclusions; an absent file record does not establish why a report is missing.
RCC-ACIS, used by NWS NOWData, holds additional reports for the same station.

The refresh requests that exact GHCN station ID and validates the response identity
and daily calendar. GHCN remains primary. Only fields in absent monthly records
can be supplemented; existing values, explicit missing days, and quality rejections
are never overridden. Only unflagged observations and precipitation traces are
accepted. No interpolation, nearby stations, or divided multiday totals fill gaps.

For the audited 2016–2025 period (3,653 days):

| Daily field | GHCN alone | With RCC-ACIS supplements |
| --- | --- | --- |
| Minimum temperature | 3,175 | 3,436 |
| Maximum temperature | 3,245 | 3,509 |
| Precipitation | 3,273 | 3,541 |

July and August 2022 remain missing in both feeds. Supplemented daily values carry
`field_sources` provenance, shown in tooltips; source metadata retains the request
URL and policy. RCC-ACIS can include preliminary reports, so supplementation is
not a claim of finalized NCEI data. If its request fails or is incomplete, the
Abiquiu refresh fails without replacing its last published file; peers still refresh.
See [ACIS documentation](https://docs.rcc-acis.org/acisws/) and
[NWS's explanation of archive/preliminary differences](https://www.weather.gov/climateservices/nowdatafaq).

## Example monsoon comparison

For June 15–September 30, all 108 dates are available in each listed source (mm):

| Monsoon | Abiquiu Dam | Albuquerque airport |
| --- | --- | --- |
| 2024 | 143.20 | 97.80 |
| 2025 | 107.30 | 78.40 |

## Refreshing controls

Provider downloads are free and the command needs no credentials. The
published JSON records download URLs, citations, elevations, retrieval time, and
source notes. Retain those attributions when redistributing it; the repository's
software license does not replace provider data terms.

```sh
uv run python -m canones_weather.reference --start-year 2016 --output tmp/reference
# To publish, use uv run --group station, add --publish-config tmp/publisher.json,
# and provide bucket-scoped credentials.
```

Controls are generated outside Git and served from the configured R2 reference
feed, independently of Pages builds. The local default output is ignored
`tmp/reference/`. Use `--source abiquiu`, `albuquerque`, or `santa-fe` to refresh one source.
the default `all` processes every source independently;
failures in one source do not prevent processing the other. Each validated file
replaces its own R2 object only on successful upload; the last published data
survives a failed refresh. Missing or invalid downloads are not published.

Without an end-year limit, the refresh uses the latest available reporting dates.
`available_through` describes data
availability; `retrieved_at` describes the download time. The dashboard shows
the latest date for the selected measurement and revalidates selected controls
periodically in both modes.

[The reference workflow](../.github/workflows/reference-data.yml) checks all three
references daily, when reference code or workflow changes reach `main`, and on
manual dispatch. Its independent matrix jobs do
not run on the Pi or modify the weather archive. Configure repository secrets
`R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` with the existing bucket-scoped
publisher key, and repository variable `R2_PUBLISHER_CONFIG` with the non-secret
OpenTofu publisher output. Keep source downloads out of Git.

GitHub can disable public-repository schedules after 60 days without repository
activity. Watch workflow results and configure GitHub failure notifications;
manual dispatch is available after re-enabling a disabled schedule. Do not create
artificial commits as a keepalive. A fresh download cannot remove provider lag.

## Provider links

- [NOAA Abiquiu Dam record](https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/USC00290041.dly),
  [station metadata](https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt),
  [format/quality flags](https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt),
  and [GHCN-Daily citation](https://doi.org/10.7289/V5D21VHZ).
- [NOAA Albuquerque airport record](https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/USW00023050.dly)
  and [Santa Fe airport record](https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/USW00023049.dly).
- [NOAA data access and public-domain guidance](https://www.noaa.gov/office-education/outreach-communication/faq).
