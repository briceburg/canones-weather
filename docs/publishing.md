# Publishing and discovery

The public dashboard and JSON expose local station data independently of weather
networks. Historical controls have separate provenance and are never submitted
as local observations. Imported data cannot extend the station's observation
record or qualify its pilot measurements as verified.

## Scientific and operational discovery

[CWOP](https://www.weather.gov/fgz/cwop) is the primary route for contributing an
automated personal station to NOAA/NWS. Register a station identifier, report
accurate coordinates/elevation and sensor exposure, and complete the
[activation steps](https://madis.ncep.noaa.gov/cwop_signup.shtml). Registration is
free. Verify observations and quality-control results in
[MADIS](https://madis.ncep.noaa.gov/madis_cwop.shtml), and check station lookup/map
visibility after activation. Sending packets alone does not prove ingestion.

CWOP/MADIS distribution is separate from GHCN-Daily, the climate archive used for
Abiquiu Dam. CWOP membership does not promise a GHCN station identifier, permanent
GHCN archiving, use by every downstream service, or appearance in web searches.
Keep the local archive and backups independently.

Wunderground provides another public personal-station directory and observation
page. Use the same verified outdoor fields and station metadata. Keep the CWOP
and Wunderground identifiers and public station URLs in the station documentation
once assigned. Validate each service's received observations before describing
it as operational. The current pilot does not submit to either service.

Notify the MADIS support team about other distribution routes if requested in its
registration guidance, to help identify duplicate station reports. Registration
or contacting operators is an owner action; this repository does not enroll a
station automatically.

## Web discovery

The station page describes the location and its downloadable observations. Its
schema.org Dataset metadata identifies the local observation dataset and links
to the current/history JSON. Historical controls are linked and labeled
separately, with attribution and coverage. Canonical URLs, sitemaps, and public
robots files expose the production pages to crawlers.

[Dataset structured data](https://developers.google.com/search/docs/appearance/structured-data/dataset)
can help Google Dataset Search discover a dataset, but does not guarantee
indexing or rankings. After deployment, verify the canonical page and sitemap in
Search Console and validate the Dataset markup. Keep data licensing, source
metadata, station identifiers, and distribution links explicit as they evolve.

## Commissioning gate

Follow [station commissioning](station.md#commissioning) before network uploads:
verify WS90 field provenance, placement, altitude/pressure calculations, units,
and timestamps; preserve pilot history separately; start the verified dataset.
Then activate CWOP and Wunderground, inspect received fields, and add their public
station links. Never publish garage or indoor temperatures as outdoor weather.
