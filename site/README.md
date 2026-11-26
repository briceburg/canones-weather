# Iceburg Weather sites

The hub and station dashboard are static sites with shared styles and branding.
The station dashboard renders history plots with Apache ECharts.

```sh
bin/build-site
python3 -m http.server 8000 --directory dist
```

Open `http://localhost:8000/hub/` and `http://localhost:8000/canones/`.
The build uses Python 3.11+ and its standard library. It combines each site's
files with `site/shared/assets/` and renders station metadata into HTML and JSON.
Cloudflare Pages builds and serves `dist/hub` and `dist/canones`.

The shared Pages headers require asset revalidation. HTML entry points additionally
use `no-transform` to prevent automatic analytics injection; scripts and styles
remain eligible for compression.

The shared `site-config.json` sets domains, feed URLs, and data mode defaults.

The dashboard supports separate sample and live data modes. The production
hostname selects the measured feed. Local previews start with samples; select
Live feed to read the public production JSON. Live mode never substitutes samples
for unavailable observations; stale readings and unverified pilot sources retain
their notices. `bin/pi snapshot` connects the local build to a copied pilot feed;
see the [Pi guide](../deploy/raspberry-pi/README.md).

## Charts

Select temperature, humidity, wind, rain, or solar irradiance. The default 24h
view uses five-minute station observations. Current conditions load separately
from the chart, which loads as it approaches the viewport and requests only the
active history cadence. The 24h view switches to hourly summaries
when panned outside the five-minute archive or widened past 24 hours. The 7d
view starts with hourly summaries, with Bodega Marine and Valles Caldera
available for selected measurements. Windows wider than 7 days and the 30d,
1yr (365 days), and All history presets use daily summaries. Seasons and Monsoon
aggregate daily records.
See [the data contract](../docs/data.md) for stored units and aggregations.

Live presets end at the visitor's current time and show gaps if observations
are missing. Sample presets end at the sample timestamp. Drag the timeline
window to pan without changing its width. Earlier and Later step by the current
interval, using the station's local calendar for daily views. Drag the
handles, select across the plot, or open Set date range to enter both ends in
UTC. Short-range chart labels and tooltips show weekdays in Mountain Time.
A custom window retains its dates across metric changes, unit changes, and feed
refreshes. Select a period or data mode to reset the window. The address bar
updates when chart controls change or a pan or zoom finishes. The **Copy chart
link** icon shares the current view. Preset links reopen relative to the latest
chart cutoff, while custom links retain their selected dates.

The heading's clock uses the visitor's device time, displayed in the configured
station time zone. It is independent of observation timestamps.

## Station metadata

Source HTML uses `{{ station.name }}` and `{{ station.timezone }}` from
`src/canones_weather/station.json`. Use `{{ station.name_json }}` inside
structured-data scripts for JSON escaping. The build also sets the station name
in browser settings and the copied sample fixtures. See
[station identity](../docs/data.md#station-identity) for rename requirements.

## Third-party software

`canones/assets/vendor/echarts/` contains the unmodified Apache ECharts 6.1.0
common browser bundle with its upstream LICENSE and NOTICE. It is Apache-2.0
licensed and served locally. Original site code is covered by this repo's MIT
license. Update the pinned distribution and notices together.
[Apache ECharts 6.1.0 distribution](https://github.com/apache/echarts/tree/6.1.0/dist)

## Branding

The mountain favicon and weather identity were created for this project. The
footer links to Iceburg using its existing blue wordmark, preserved from the
original Iceburg website. Branding assets represent their respective owner.

## Synthetic samples

Run `bin/generate-sample` to recreate the fixed August 15, 2026 snapshot. It
contains complete 2024/2025 monsoon windows, an ongoing 2026 monsoon, leap-day and
daylight-saving boundaries, recent five-minute data, solar history, and deliberate
missing observations. Values are illustrative, not local climate estimates.
The sample generator uses only Python's standard library.

## Historical controls

Select references under **Chart sources** to compare them with station
observations, or hide station observations for a reference-only chart.
Selecting a reference that needs a different resolution opens 7d for hourly
observations or 30d for daily summaries. A source that lacks the selected metric
shows **No data**. A source with a gap across the visible range shows **No
readings**. Presets and chart links retain compatible selections. Map pins open
each station location.

Sample mode uses illustrative local observations alongside real reference
observations. See [reference data](../docs/reference-data.md) for source coverage
and refresh methods.
