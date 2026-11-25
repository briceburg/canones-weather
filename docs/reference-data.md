# Regional reference history

Reference history compares weather across locations: for example, Albuquerque's
monsoon rain against Secco Spring's. Sources need not share the station's climate;
they never backfill its archive or establish past conditions at the property.
Select references in the dashboard to compare daily temperature and precipitation
in 30d, 1y, 3y, All, Seasons, or Monsoon. You can also widen the 24h timeline past
24 hours to switch to daily summaries and show the selected references. The
dashboard disables reference selection in hourly history and for measurements
other than temperature and precipitation, and remembers your selections. Current
conditions show the local station's observations.
Sample mode can overlay the same real controls against an explicitly labeled
synthetic station series. Its archive-start marker is illustrative, not a station
commissioning date. Sample mode ends at its fixed fixture timestamp. Use Live
mode for dates after the sample timeline.

## Station locations

Station names link to the observing sites on OpenStreetMap.

| Station | Data source | Elevation |
| --- | --- | --- |
| [Abiquiu Dam, NM][abiquiu-map] (USC00290041) | NOAA daily observations with same-station RCC-ACIS reports, about 10.2 km / 6.3 mi away | 1,944.6 m |
| [Albuquerque airport, NM][albuquerque-map] (USW00023050) | NOAA daily observations | 1,618.5 m |
| [Santa Fe airport, NM][santa-fe-map] (USW00023049) | NOAA daily observations, about 68 km / 42 mi away | 1,916.3 m |
| [Gila Hot Springs, NM][gila-hot-springs-map] (USC00293530) | RCC-ACIS cooperative station observations about 48 km / 30 mi north of Silver City. Recent reports may be preliminary. | 1,717.9 m |
| [Downtown Charleston, SC][charleston-map] (USW00013782) | NOAA daily observations | 3 m |
| [Crozier, VA][crozier-map] (USC00442142) | RCC-ACIS cooperative station observations. Recent reports may be preliminary. | 85.3 m |
| [Bodega Marine Laboratory, CA][bodega-map] (USW00093245) | NOAA U.S. Climate Reference Network daily observations, coastal Sonoma County | 19.2 m |
| [Milwaukee Mitchell Airport, WI][milwaukee-map] (USW00014839) | NOAA daily observations in the Lake Michigan region | 203.3 m |
| [Port de Sóller, Mallorca][soller-map] (B051A) | AEMET OpenData daily observations from September 2020 in the exported record | 5 m |
| [Secco Spring, NM][secco-map] | Local station, with provenance and pilot status in its JSON | 2,151.888 m |

[abiquiu-map]: https://www.openstreetmap.org/?mlat=36.2403&mlon=-106.4278#map=14/36.2403/-106.4278
[albuquerque-map]: https://www.openstreetmap.org/?mlat=35.0419&mlon=-106.6156#map=14/35.0419/-106.6156
[santa-fe-map]: https://www.openstreetmap.org/?mlat=35.6108&mlon=-106.0958#map=14/35.6108/-106.0958
[gila-hot-springs-map]: https://www.openstreetmap.org/?mlat=33.1975&mlon=-108.2075#map=14/33.1975/-108.2075
[charleston-map]: https://www.openstreetmap.org/?mlat=32.7750&mlon=-79.9239#map=14/32.7750/-79.9239
[crozier-map]: https://www.openstreetmap.org/?mlat=37.6664&mlon=-77.8769#map=14/37.6664/-77.8769
[bodega-map]: https://www.openstreetmap.org/?mlat=38.3208&mlon=-123.0747#map=14/38.3208/-123.0747
[milwaukee-map]: https://www.openstreetmap.org/?mlat=42.9550&mlon=-87.9044#map=14/42.9550/-87.9044
[soller-map]: https://www.openstreetmap.org/?mlat=39.7956&mlon=2.6914#map=14/39.7956/2.6914
[secco-map]: https://www.openstreetmap.org/?mlat=36.150028&mlon=-106.445500#map=14/36.150028/-106.445500

Abiquiu Dam is about 207 m below Secco Spring. Gila Hot Springs is about 434 m
below Secco Spring and provides a southwestern New Mexico monsoon comparison.
Differences in terrain, elevation, exposure, and storms are part of these comparisons.

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

Daily timestamps label the provider's reporting date in America/Denver. Crozier
and Gila Hot Springs retain their cooperative observer reporting dates. Bodega
retains the USCRN local standard time calendar. Port de Sóller retains AEMET reporting dates and its
07:00–07:00 precipitation reporting period. NOAA missing values,
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

| Monsoon | Abiquiu Dam | Albuquerque airport | Gila Hot Springs |
| --- | --- | --- | --- |
| 2024 | 143.20 | 97.80 | 229.87 |
| 2025 | 107.30 | 78.40 | 155.19 |

## Refreshing controls

NOAA and RCC-ACIS downloads need no credentials. Port de Sóller uses the free
[AEMET OpenData API key](https://opendata.aemet.es/centrodedescargas/altaUsuario).
Set `AEMET_API_KEY` in the environment or in the ignored local `.env` file. The
published JSON records download URLs, citations, elevations, retrieval time, and
source notes. Retain those attributions when redistributing it; the repository's
software license does not replace provider data terms.
Port de Sóller observations are © AEMET. See [AEMET’s reuse terms](https://www.aemet.es/en/nota_legal).

```sh
uv run --env-file .env python -m canones_weather.reference --start-year 2016 --output tmp/reference
# To publish, use uv run --group station, add --publish-config tmp/publisher.json,
# and provide bucket-scoped credentials.
```

Controls are generated outside Git and served from the configured R2 reference
feed, independently of Pages builds. The local default output is ignored
`tmp/reference/`. Pass `--source` to refresh a single reference. The available keys
are `abiquiu`, `albuquerque`, `santa-fe`, `gila-hot-springs`, `charleston`,
`crozier`, `bodega`, `milwaukee`, and `soller`. The default `all` processes every
source independently so a failure in one source leaves the others able to refresh. Each validated file
replaces its own R2 object only on successful upload; the last published data
survives a failed refresh. Missing or invalid downloads are not published.

Without an end-year limit, the refresh uses the latest available reporting dates.
`available_through` describes data
availability; `retrieved_at` describes the download time. The dashboard shows
the latest date for the selected measurement and revalidates selected controls
periodically in both modes.

[The reference workflow](../.github/workflows/reference-data.yml) checks every
reference daily, when reference code or workflow changes reach `main`, and on
manual dispatch. Its independent matrix jobs do
not run on the Pi or modify the weather archive. Configure repository secrets
`R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` with the existing bucket-scoped
publisher key, and repository variable `R2_PUBLISHER_CONFIG` with the non-secret
OpenTofu publisher output. The Sóller job uses the repository secret
`AEMET_API_KEY`. Keep source downloads out of Git.

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
- [NOAA Gila Hot Springs station record](https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/USC00293530.dly)
  and [RCC-ACIS data access](https://docs.rcc-acis.org/acisws/).
- [NOAA Downtown Charleston record](https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/USW00013782.dly),
  [NOAA Milwaukee Mitchell Airport record](https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/USW00014839.dly),
  [RCC-ACIS Crozier data access](https://docs.rcc-acis.org/acisws/),
  and [NOAA USCRN daily data and format](https://www.ncei.noaa.gov/pub/data/uscrn/products/daily01/).
- [AEMET Port de Sóller station](https://www.aemet.es/en/eltiempo/observacion/ultimosdatos?l=B051A)
  and [AEMET OpenData climatological observations](https://opendata.aemet.es/dist/).
- [NOAA data access and public-domain guidance](https://www.noaa.gov/office-education/outreach-communication/faq).
