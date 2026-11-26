# Iceburg Weather sites

The dark-only hub and dashboard share styles and assets. Apache ECharts renders
the history plots in the browser; both sites are static HTML, CSS, and JavaScript.

```sh
bin/build-site
python3 -m http.server 8000 --directory dist
```

Open `http://localhost:8000/hub/` and `http://localhost:8000/canones/`.
The build requires Python 3.11+ and only its standard library. It assembles each
site's source and common assets into `dist/hub` and `dist/canones`, rendering
station metadata into HTML and JSON. Cloudflare Pages runs the same command and
serves the respective directory. Generated `dist/` files are ignored by Git.

The shared Pages headers require asset revalidation. HTML entry points additionally
use `no-transform` to prevent automatic analytics injection; scripts and styles
remain eligible for compression.

`site/shared/assets/styles.css` defines the visual identity. `site-config.json`
contains public domain/feed settings and the default data mode; the build adds
shared station metadata. Source navigation works on the production and test
domains and in a local preview.

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
The data feed also includes a measured temperature mean.
Display units do not change stored data; see [the data contract](../docs/data.md).

Live presets end at the visitor's current time and show gaps if observations
are missing. Sample presets end at the sample timestamp. Drag the timeline
window to pan without changing its width. Earlier and Later step by the current
interval, using the station's local calendar for daily views. Drag the
handles, select across the plot, or open Set date range to enter both ends in
UTC. Short-range chart labels and tooltips show weekdays in Mountain Time.
A custom window retains its dates across measurement changes, unit changes, and
feed refreshes.
Select a period or data mode to reset it.
The address bar updates after chart controls change or a pan or zoom finishes.
The **Copy chart link** icon beside the chart title shares the same link.
Presets open relative to the latest chart cutoff. Custom date ranges retain
their selected dates.

The heading's clock uses the visitor's device time, displayed in the configured
station time zone. It is independent of observation timestamps.

## Station metadata

[`src/canones_weather/station.json`](../src/canones_weather/station.json) owns the
station's stable ID, display name, and IANA time zone. To rename the station,
edit only `name` there and rebuild both sites. The build updates headings, titles,
descriptions, accessibility labels, structured data, browser settings, and sample
display metadata. Source HTML uses `{{ station.name }}` and
`{{ station.timezone }}`; JSON string contents inside structured-data scripts use
`{{ station.name_json }}` for JSON escaping.

The browser uses the built name for live chart labels, so an older feed's display
name does not undo a rename. Station and dataset IDs remain authoritative for
matching data. Reprovision the collector to update the name in subsequent live
exports and the WeeWX location label. No archive or bucket migration is required.
See [station identity](../docs/data.md#station-identity) for the data contract.

Tracked sample fixtures are regenerated with `bin/generate-sample`; ordinary
builds update only their copied display metadata. Documentation prose, artwork,
and sample screenshots are maintained separately from the website build.

## Third-party software

`shared/assets/vendor/echarts/` contains the unmodified Apache ECharts 6.1.0
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

The chart-source checkboxes select station observations and references under
Regional, Coastal, and Places of Excellence in Sample or Live mode.
The chart starts with station observations. Selecting a reference that needs a
different resolution opens 7d for hourly observations or 30d for daily
summaries. A source without the chosen measurement shows **No data**. A loaded
source with a gap in the visible dates shows **No readings**. A preset retains
the reference selections it can show, and chart links include compatible
sources. Hide station observations for a reference-only
chart. The picker swatches match each source's chart color and dash pattern.
Temperature highs use a heavier line and lows use a lighter line in the same
color. Each source's map pin opens its station location. The
[reference guide](../docs/reference-data.md#station-locations) includes provider details.

Reference sources are labeled separately and never fill station gaps. Sample
station series and their start marker remain illustrative; references retain
their real provenance. See [reference data](../docs/reference-data.md) for source
coverage and refresh methods, and [publishing/discovery](../docs/publishing.md)
for indexing and weather-network requirements.
