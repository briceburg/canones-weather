# Secco Creek station

| Setting | Value |
| --- | --- |
| Location | Cañones, New Mexico |
| Latitude, longitude | `36.150028, -106.445500` |
| Time zone | `America/Denver` |
| Outdoor array | Ecowitt WS90 |
| Gateway | GW3000, second-story room, Ethernet; address configured locally |
| WS90 mounting | Pole in a small clearing, about 16 ft (4.9 m) above ground |
| Ground elevation | 7,060 ft (2,151.888 m); distinct from mounting height |
| Collector host | Raspberry Pi shared with radio-pad |

Report wind at its measured mounting height and exposure; do not apply an
assumed height correction. Ground elevation is required for pressure calibration
and weather-network station metadata.

## Collection requirements

Configure WeeWX for 20-second gateway polling and five-minute SQLite archive
records. Use standard aggregation: average temperatures, vector-aggregated wind
direction, maximum observed gust, and interval rain totals. Verify field mapping,
units, timestamps, and gust capture against the gateway observations.

Keep the full archive on the Pi with consistent off-device backups. Publish
observations and chart summaries every five minutes using the
[public data contract](data.md), independently of website deployments.
Preserve the archive regardless of chart resolution or exported history windows.

## Sensor mapping

Use the WS90 for outdoor weather fields. A WN32 overrides WS90 temperature and
humidity in the gateway; use a WN31 auxiliary channel for garage readings instead.
Verify channel mapping and loss/fallback behavior using actual values, not sensor
IDs alone. Indoor and garage readings belong in separate fields.

Wunderground and CWOP submissions require verified outdoor observations,
supported derived values, and valid station metadata. Keep upload services
disabled until mapping is verified; exclude indoor and garage temperatures.

## Outages and recovery

The GW3000 has an SD card configured for five-minute logging, matching the
WeeWX archive interval. This is separate from WeeWX's 20-second live polling.
The card provides another local copy of sensor readings while the gateway has
power and receives them; it cannot recover periods before recording began or
while the gateway itself was unavailable. Retain the permanent WeeWX archive
and its off-device backups independently.

The pilot generates archive records in software and explicitly sets
`no_catchup = True`. Installing a card does not automatically backfill WeeWX.
The pinned driver supports SD-card startup catch-up, but it starts after the
last archived timestamp; it does not repair older holes followed by later
archive records.

Before enabling catch-up or importing files, validate recovery against a copy
of the archive. Keep the original CSV files and their unit headers, local time
labels, epoch timestamps, sensor provenance, and logging interval. Check for
restarts, irregular interval boundaries, and uncovered periods. Equal logging
intervals do not establish that SD readings and software archive aggregates are
equivalent.

The live-packet solar correction divides by 126.7 because the driver normalizes
live light readings to lux. SD files can already contain solar radiation in
W/m²; applying that same correction to these recovered records would make them
incorrect. Recovery needs source-appropriate calibration and validated rain
counter handling before it is enabled. Preserve the pilot's unverified status;
recovery does not verify sensor mapping or authorize weather-network uploads.

SD files are listed through the gateway HTTP API and downloaded on TCP port 81.
Access to the gateway's web interface on port 80 does not by itself provide
access to the download port. The Pi can retrieve files over its local LAN
connection without adding another remote firewall rule. See the
[GW3000 SD-card manual](https://oss.ecowitt.net/uploads/20260320/GW3000Manual.pdf#page=72)
and the [pinned driver's catch-up implementation](https://github.com/weewx-contrib/weewx-ecowitt_local_http/blob/6876b2ecbab88f825dde1b0b7c5874cb5fd3c25e/bin/user/ecowitt_http.py).

Local collection must continue during internet outages when the Pi, gateway,
sensor reception, and LAN remain available. A WAN interruption can delay
publishing without causing missing local archive records. Compare the archive,
export observation timestamps, collector logs, and publisher logs before
attributing a chart gap to internet connectivity.

## Commissioning

1. Install the WN31 auxiliary sensor and mount WS90 in its permanent location.
2. Validate primary temperature/humidity, channel mapping, sensor-loss behavior,
   rainfall, wind, elevation, and pressure configuration.
3. Take an off-device pilot backup and preserve its archive. Start a separate
   commissioned archive and dataset; do not backfill it with unverified pilot data.
4. Publish the new dataset at the existing URLs and verify its public values and
   timestamps. Remove the pilot notice only with verified sensor provenance.
5. Configure Wunderground/CWOP station identities and credentials separately,
   and inspect the actual outbound fields before enabling submissions.

After activation, verify CWOP/MADIS station lookup and quality-control results,
and add the assigned public station links to this document. Follow
[publishing and discovery](publishing.md) for contribution and indexing details;
CWOP distribution is separate from enrollment in GHCN-Daily.
