# Public observation data

The dashboard data contract is version 1. It separates current readings from
chart history; neither file replaces the permanent WeeWX archive.

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
zero. The pilot exporter leaves daily rainfall unavailable when its archive
does not cover the local day. Site display units do not alter stored values.

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

Site configuration is in `site/shared/assets/site-config.json`. It selects data
hosts from the deployed hostname, keeping notprod separate from prod. Local
previews on localhost or loopback addresses can select the public production feed;
sample mode remains the default. A Pi snapshot overrides that selection with its
local capture. `default_mode` selects `sample` or `live`; live mode requires valid observation
and history feeds. The production hostname selects live mode; local previews select samples.
Live mode rejects sample envelopes and never
silently falls back to sample data. An observation older than 15 minutes is labeled
last-known data. Future timestamps are flagged. If a refresh fails, the previous
observation retains its original timestamp.

The synthetic sample is fixed at August 15, 2026. Regenerate it with
`bin/generate-sample`; it includes five-minute, hourly, daily, solar, and seasonal
data, with deliberate gaps and an ongoing monsoon.

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
Monsoon defaults to rainfall; other measurements remain selectable. All values
are derived in the browser from existing daily JSON, with no additional feeds.

Solar comparisons use the WS90 light-derived irradiance estimate in W/m², including
nighttime readings. The WS90 measures light and UV, not cloud-cover percentage.
Clouds, smoke, shading, sun angle, and day length affect the signal. No cloudiness
percentage or sunshine duration is inferred from it. See [Ecowitt's sensor specifications](https://shop.ecowitt.com/collections/wifi-sensor/products/ws90).

## Historical controls

Separately attributed daily reference files live under `data/reference/` in the
static station site. See [reference data](reference-data.md) for provenance, units,
quality flags, calendars, coverage, refresh commands, and overlay semantics. They
never enter the local archive or the current/history publisher.

For weather-network registration and web indexing, see [publishing and discovery](publishing.md).

## Timeline navigation

The 30d, 1y, and 3y buttons preset the latest 30, 365, or 1,095 days over the
full available daily history; older records remain available by panning. All resets to the full
record. Click and drag horizontally across the chart to zoom into a period. Move the
slider window to pan, drag its handles to resize, or use Ctrl + scroll to zoom.
The chart follows the latest data until the user changes
the window. A dragged time window retains its dates through unit/measurement
changes and refreshes; a period or data-mode button resets the preset. The footer
labels available history, which can extend beyond the visible window.
