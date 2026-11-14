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

No gateway SD card is installed. A Pi outage can leave gaps in the archive.
Local collection must continue during internet outages. Verify gateway history
retrieval before relying on SD-card recovery.

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
