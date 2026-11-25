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

Publish `canones/history.json` with `schema_version`, `kind`, `station_id`, and
`through` (the latest observation represented), optional `record_started_at`
(the first archived observation, used for the source-boundary marker), plus ascending `recent`, `hourly`, and `daily`
arrays. [The sample history](../site/canones/data/sample/history.json) illustrates
the shape with 24 hours of five-minute data, 30 days of hourly data, and
daily data beginning in January 2024.

Each row has `at` and these fields:

| Field | Aggregation |
| --- | --- |
| `temperature_c` | Mean |
| `humidity_pct` | Mean |
| `wind_speed_m_s` | Mean speed |
| `wind_gust_m_s` | Maximum observed gust |
| `rain_mm` | Interval total |
| `solar_w_m2` | Mean light-derived solar irradiance, including nighttime; optional on older feeds |
| `temperature_min_c`, `temperature_max_c` | Interval extrema; optional for older feeds |

Recent timestamps identify five-minute interval ends, matching the archive and
current observation. Hourly and daily timestamps identify interval starts. Publish only completed history intervals;
current conditions may be newer. Use WeeWX aggregation for exports; do not
reconstruct archive records from instantaneous gateway snapshots. Represent
missing intervals with timestamped rows of `null` values so gaps remain visible
in plots. The dashboard displays times in the station's time zone.
Hourly and daily temperatures include mean, minimum, and maximum; averaging must not discard
extremes or turn missing rainfall into a dry period.

The exporter supplies the last 24 hours at five-minute resolution in `recent`,
30 days of hourly summaries, and daily summaries for the full archive. The browser
uses recent rows for 24h, daily rows for 30d/1y/3y/All.
Older feeds without `recent` use hourly rows for 24h. All means
all daily history supplied by the feed. Chart windows do not set archive
retention: retain the full five-minute archive and consistent off-device backups
independently of these exports.

## Serving and freshness

Serve JSON with `Content-Type: application/json`, public-read CORS, and
`Cache-Control: public, max-age=60`. Upload history before the current observation
when publishing a batch. The publisher rejects pairs with different observation
timestamps, including files read across a local export. Browser requests may
still straddle two uploads; a notice identifies different update times. The browser refresh interval is five minutes;
current and history endpoints can fail independently.

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

These views average available daily means, preserve recorded temperature extrema
and peak gusts, and sum recorded rainfall. Tooltips report days with values for
the selected measurement against calendar days in the full window. A day with a
value can itself be incomplete; this is not a measure of archive uptime. Missing
values stay missing, and partial-season totals are never extrapolated. These are
observations from this station's dataset, not regional climate normals.

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
