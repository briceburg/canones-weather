# Iceburg Weather sites

The dark-only hub and dashboard share styles and assets. Apache ECharts renders
the history plots in the browser; both sites are static HTML, CSS, and JavaScript.

```sh
bin/build-site
python3 -m http.server 8000 --directory dist
```

Open `http://localhost:8000/hub/` and `http://localhost:8000/canones/`.
The build copies each site's source plus common assets into `dist/hub` and
`dist/canones`. Cloudflare Pages runs the same command and serves the respective
directory. Generated `dist/` files are ignored by Git.

The shared Pages headers require asset revalidation. HTML entry points additionally
use `no-transform` to prevent automatic analytics injection; scripts and styles
remain eligible for compression.

`site/shared/assets/styles.css` defines the visual identity. `site-config.json`
contains public domain/feed settings and the default data mode. Source navigation
works on the production and test domains and in a local preview.

The dashboard supports separate sample and live data modes. The production
hostname selects the measured feed. Local previews start with samples; select
Live feed to read the public production JSON. Live mode never substitutes samples
for unavailable observations; stale readings and unverified pilot sources retain
their notices. `bin/pi snapshot` connects the local build to a copied pilot feed;
see the [Pi guide](../deploy/raspberry-pi/README.md).

## Charts

Select temperature, humidity, wind, rain, or solar irradiance. The 24h view uses
five-minute readings where available; 30d, 1y, 3y, and All use daily summaries,
including temperature mean/low/high. Seasons and Monsoon aggregate daily records.
Display units do not change stored data; see [the data contract](../docs/data.md).

Drag across the plot to zoom; move the slider window to pan or its handles to
resize. A custom window retains its dates across unit/measurement changes and
refreshes. Selecting a period or data mode resets it. The footer identifies the
available record, which may extend beyond the displayed window.

The heading's clock uses the visitor's device time, displayed in America/Denver.
It is independent of observation timestamps.

## Third-party software

`shared/assets/vendor/echarts/` contains the unmodified Apache ECharts 6.0.0
browser distribution from https://github.com/apache/echarts/tree/6.0.0/dist,
with its upstream LICENSE and NOTICE. It is Apache-2.0 licensed and served locally;
there is no runtime CDN dependency. Original site code is covered by this repo's
MIT license. Update the pinned distribution and notices together.

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

The chart-source checkboxes independently select station observations, Daymet,
and Abiquiu Dam in either Sample or Live mode. Station observations and Daymet
are selected by default. References appear only for historical temperature and
precipitation views; selections persist in unsupported views without changing
the period or measurement. Hide station observations for a reference-only chart.

Reference sources are labeled separately and never fill station gaps. Sample
station series and their start marker remain illustrative; references retain
their real provenance. See [reference data](../docs/reference-data.md) for source
coverage and refresh methods, and [publishing/discovery](../docs/publishing.md)
for indexing and weather-network requirements.
