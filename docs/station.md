# Secco Spring station

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

The GW3000's SD card logs every five minutes, matching the WeeWX archive interval;
WeeWX polls live data every 20 seconds. The card records independently of the Pi
while the gateway has power and receives sensor data. It cannot recover readings
from before recording began or while power or reception was lost. Retain the
permanent WeeWX archive and off-device backups independently.

The pilot uses software archive generation with `no_catchup = True`, so SD data
is not imported automatically. The pinned driver's startup catch-up retrieves
records after the last archived timestamp; older holes require separate recovery.

Validate recovery against an archive copy before enabling catch-up or importing
files. Preserve original CSV files, units, local and epoch timestamps, sensor
provenance, and logging interval. Check clock changes, irregular boundaries,
missing coverage, and aggregation differences; equal intervals do not establish
that SD readings and WeeWX aggregates are equivalent.

The live solar correction divides the driver's lux values by 126.7. SD files can
already contain W/m², so that correction would make recovered irradiance wrong.
Recovery requires source-appropriate calibration and rain counter handling while
preserving the pilot's unverified provenance and disabled weather-network uploads.

The driver lists SD files through the gateway HTTP API on port 80 and downloads
them on TCP port 81. The Pi can retrieve them over the LAN when remote firewall
rules allow only port 80. See the
[GW3000 SD-card manual](https://oss.ecowitt.net/uploads/20260320/GW3000Manual.pdf#page=72)
and the [pinned driver's catch-up implementation](https://github.com/weewx-contrib/weewx-ecowitt_local_http/blob/6876b2ecbab88f825dde1b0b7c5874cb5fd3c25e/bin/user/ecowitt_http.py).

During internet outages, collection should continue while the Pi, gateway, LAN,
and sensor reception remain available. Compare archive and export observation
timestamps with collector and publisher logs to distinguish collection gaps from
delayed uploads.

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
