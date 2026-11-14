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

`site/shared/assets/styles.css` defines the visual identity. `site-config.json`
contains public domain/feed settings and the default data mode. Source navigation
works on the production and test domains and in a local preview.

The dashboard supports separate sample and live data modes. The production
hostname selects the measured feed. Local previews start with samples; select
Live feed to read the public production JSON. `bin/pi snapshot` instead connects
the local build to a copied Pi feed.
Tabs select temperature, humidity, wind, rain, and solar irradiance; periods extend from 24 hours to
all available daily history. Display units can change without changing the feed.
Live mode has unavailable/stale states and no sample fallback. Pilot observations
retain a prominent provisional-placement and unverified-source notice.
See [the data contract](../docs/data.md) for feed requirements.
`bin/pi snapshot` connects a local build to a copied pilot feed; see the
[Pi guide](../deploy/raspberry-pi/README.md).

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

The shared Pages headers require asset revalidation. HTML entry points additionally
use `no-transform` to prevent automatic analytics injection; scripts and styles
remain eligible for compression.

## Historical controls

Select Daymet or Abiquiu Dam to overlay separately attributed daily controls
in either Sample or Live mode. Sample station series and their start marker are
explicitly labeled as illustrative; controls retain their real provenance.
These bundled reference files do not change local observations or the station
archive. See [reference data](../docs/reference-data.md) for refresh and
comparison details, and [publishing/discovery](../docs/publishing.md) for the
production sitemap, Dataset metadata, and CWOP commissioning requirements.
