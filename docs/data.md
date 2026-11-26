# Public observation data

The dashboard data contract is version 1. It separates current readings from
chart history; neither file replaces the permanent WeeWX archive.

## Station identity

[`src/canones_weather/station.json`](../src/canones_weather/station.json) is the
shared source for the station ID, display name, and IANA time zone. The exporter,
publisher, sample generator, website build, and Pi configuration use it.

`canones` is the permanent station ID. It identifies the station independently of
its nickname; current observations use `station.id` and history uses `station_id`.
The publisher and dashboard validate that ID, never the display name.
`station.name` is descriptive metadata and may differ in older exported files.

A rename changes only `name` in the metadata file. Rebuild both sites and
reprovision the collector to publish the new name; retain the station ID,
deployment dataset ID, archive, URLs, and `canones/` storage prefix. No observations
need rewriting, and the JSON schema stays at version 1. Changing an ID or time
zone is a separate data/configuration change, not a rename. A replacement archive
still requires the dataset boundary described below.

## Current observations

Publish `canones/current.json`, matching the shape of
[the sample observation](../site/canones/data/sample/current.json):

- `schema_version`: `1`.
- `kind`: `live` for observations, `sample` for illustrative fixtures.
- `station`: ID, display name, and IANA time zone. This dashboard uses `canones`
  and `America/Denver`.
- `observed_at`: the observation's original RFC 3339 timestamp, with an offset.
  Do not substitute the upload time; reconnecting must not make old data fresh.
- `outdoor`: sensor source, whether mapping has been verified, and readings.
- `deployment`: phase (`pilot` or `production`), a stable `dataset_id`, and a
  visitor-facing notice. Current and history must identify the same dataset.
  Pilot measurements carry an unverified source and a provisional-placement notice.

Units are explicit in field names: Celsius, percent, metres per second, degrees,
millimetres, watts per square metre, and UV index. `rain_today_mm` is the local-day
accumulation, not a lifetime counter. Keep unavailable readings as `null`, never
zero. The exporter prefers the WS90's measured daily counter, mapped to WeeWX's
standard `dayRain` field (last value, not an interval average). The gateway must
use the station time zone and a midnight daily reset. `rain_today_source` identifies
`ws90_daily_counter`, `complete_archive`, or `local_midnight_reset`; it is `null`
when the total is unavailable. Without the daily counter, the archive must cover
the local day with known rain values. The daily card can therefore show a measured
total while historical intervals remain missing. Site display units do not alter
stored values.

The source and verification fields describe provenance, not permission to upload
to Wunderground/CWOP. Those integrations need independently verified field mapping,
valid station metadata, and their own configuration. Sample data must never enter
production collection or network upload paths.

## Chart history

Publish the three snapshots under `canones/history/`. Each contains
`schema_version`, `kind`, `station_id`, `cadence`, `through`, `record_started_at`
(the first archived observation), and a `rows` array sorted by timestamp. Live
snapshots also carry the same `deployment` metadata as `current.json`.

| File | Window | `through` |
| --- | --- | --- |
| `recent.json` | Last 24 hours of five-minute observations | Latest archive observation |
| `hourly.json` | Last 30 days of hourly summaries | End of the last completed UTC hour |
| `daily.json` | Daily summaries for the full archive | End of the last completed station-local day |

[The synthetic fixtures](../site/canones/data/sample/history/) use this layout
with daily summaries beginning in January 2024.

Each row has `at` and these fields:

| Field | Aggregation |
| --- | --- |
| `temperature_c` | Mean |
| `humidity_pct` | Mean |
| `wind_speed_m_s` | Mean speed |
| `wind_gust_m_s` | Maximum observed gust |
| `rain_mm` | Interval total |
| `solar_w_m2` | Mean light-derived solar irradiance, including nighttime; optional on older feeds |
| `temperature_min_c`, `temperature_max_c` | Interval extrema; older hourly snapshots may omit them |

Recent timestamps identify five-minute interval ends, matching the archive and
current observation. Hourly and daily timestamps identify interval starts. Publish only completed history intervals;
current conditions may be newer. Use WeeWX aggregation for exports; do not
reconstruct archive records from instantaneous gateway snapshots. Represent
missing intervals with timestamped rows of `null` values so gaps remain visible
in plots. The dashboard displays times in the station's time zone.

Pilot history can include documented GW3000 SD samples for missing intervals.
These samples retain their source and logged timestamps in the private archive.
See [outages and recovery](station.md#outages-and-recovery) for their coverage
and aggregation limitations.
Hourly and daily temperatures include mean, minimum, and maximum; averaging must not discard
extremes or turn missing rainfall into a dry period.

The chart loads the active cadence, starting with `recent` in 24h and using
hourly rows in 7d. The longer presets use daily rows. Hourly and daily temperature
charts show recorded lows and highs.
The five-minute chart shows the measured temperature of each archive record.
All history includes the full daily history supplied by the feed.
Chart windows do not set archive
retention: retain the full five-minute archive and consistent off-device backups
independently of these exports.

## Serving and freshness

Serve JSON with `Content-Type: application/json` and public-read CORS. The
publisher checks for changed content every five minutes and publishes changed
history files before `current.json`. The five-minute snapshot and the current
observation share a watermark. Hourly and daily snapshots have independent
watermarks, and a recovery can change either file without advancing its
watermark. The dashboard revalidates the current observation and active chart
feed separately and keeps the last validated data for each.

[Site configuration](../site/README.md) selects feeds by hostname and supports
sample/live modes plus local Pi snapshots. Production defaults to live data;
local previews default to samples. Current and history feeds must match the
selected mode. Live mode rejects sample envelopes and never silently substitutes
sample data. An observation older than 15 minutes is labeled
last-known data. Future timestamps are flagged. If a refresh fails, the previous
observation retains its original timestamp.

## Dataset boundaries

Keep pilot and commissioned archives separate. A new archive creates a new dataset
identity; replacing both JSON files starts the public history for that dataset
without changing its URLs. The browser discards history whose identity differs
from the current observation. Retain the pilot archive and a consistent backup
rather than deleting or relabeling its measurements as verified.

## Seasonal comparisons

The Seasons view groups daily rows by meteorological season in America/Denver:
spring March–May, summer June–August, autumn September–November, and winter
December–February. Winter is labeled with both years. Monsoon compares June 15
through September 30 each year, following [NWS Albuquerque's designated window](https://www.weather.gov/abq/prepawaremonsoonhome). Actual monsoon onset varies.

These views average daily temperature highs and lows separately, average daily
means for humidity, wind speed, and solar irradiance, retain the peak gust, and
sum precipitation. Tooltips show coverage as a percentage of calendar days with
a reported value for each measurement. A reported zero counts toward coverage,
and a day with a value can itself be incomplete. Missing values stay missing,
and partial-season totals are never extrapolated. These are observations from
this station's dataset, not regional climate normals.

Spring wind comparisons use mean daily wind speed and maximum recorded gust.
Monsoon defaults to rainfall; other measurements remain selectable. Station
summaries use its daily JSON; reference sources are aggregated separately.

Solar comparisons use the WS90 light-derived irradiance estimate in W/m², including
nighttime readings. The WS90 measures light and UV, not cloud-cover percentage.
Clouds, smoke, shading, sun angle, and day length affect the signal. No cloudiness
percentage or sunshine duration is inferred from it. See [Ecowitt's sensor specifications](https://shop.ecowitt.com/collections/wifi-sensor/products/ws90).

## Historical controls

Separately attributed reference files are served from the configured R2 reference
feed, independently of the station's current/history pair and website builds.
They never enter the local archive or weather-network submissions. See
[reference data](reference-data.md) for source methods, coverage, and refreshes;
[chart navigation](../site/README.md#charts) for periods and zoom behavior; and
[publishing and discovery](publishing.md) for network registration and web indexing.
