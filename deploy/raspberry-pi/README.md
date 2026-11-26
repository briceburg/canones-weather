# Raspberry Pi pilot

The Ansible deployment runs WeeWX 5.5.2 with a pinned Ecowitt HTTP driver, isolated
from radio-pad. The service polls every 20 seconds, archives every five minutes,
and exports local dashboard JSON after each archive record.

## Configure and deploy

With Ansible installed, set these values in the ignored `.env`:

- `WEATHER_PI_SSH`: the administrator's SSH target, in `user@host` form.
- `WEATHER_GATEWAY_URL`: the gateway HTTP origin. The pinned driver uses HTTP.
- `WEATHER_ELEVATION_M`: ground elevation in metres above sea level.

Prefer local DNS names for the gateway origin and SSH target. After router or
DHCP changes, verify DNS and gateway access from the Pi, then redeploy with the
updated local configuration. Correct reservations and DNS do not update an old
numeric address already installed in the collector configuration.

From repository root:

```sh
set -a
source .env
set +a
bin/pi preflight
bin/pi deploy
bin/pi status
```

Preflight reads host facts and gateway data. Deployment needs passwordless sudo
and an installed `/usr/local/bin/uv`. It creates the `canones-weather` service
account, syncs the locked `station` dependency group, and enables
`canones-weather-pilot.service`. It checks that radio-pad's service state, main
PID, and activation time are unchanged.

Station identity and display metadata come from
[`src/canones_weather/station.json`](../../src/canones_weather/station.json),
which deployment copies beside the Python modules. Ansible also uses it for the
WeeWX location label and service time zone. To rename the station, edit `name`
there, rebuild the websites, and run `bin/pi deploy` with the existing local
configuration. Subsequent exports carry the new name; station IDs, dataset IDs,
and archives stay unchanged.

| Path | Contents |
| --- | --- |
| `/opt/canones-weather` | Root-owned application, virtualenv, and pinned driver |
| `/var/lib/canones-weather/pilot/weewx.conf` | Collector configuration |
| `/var/lib/canones-weather/pilot/archive/weewx.sdb` | Pilot archive and daily summaries |
| `/var/lib/canones-weather/pilot/public/` | `current.json` and `history/{recent,hourly,daily}.json` |

The pilot archive is separate from verified production history. Its primary
outdoor temperature/humidity may be supplied by WN32; JSON identifies the source
as unverified. No REST upload services or station registration are loaded. The
collector exports local files. A separate publisher uses bucket-scoped R2
credentials; weather-network uploads remain disabled.

The [driver](https://github.com/weewx-contrib/weewx-ecowitt_local_http) is pinned
by commit and SHA-256. Rain uses the WS90 piezo year-counter delta, and solar
radiation maps to the gateway's light field. The driver normalizes that field
to lux; the collector reverses its 126.7 conversion to restore W/m². Verify units and mapping against the
raw gateway response. See [station requirements](../../docs/station.md).

## Recover missing pilot observations

`bin/pi deploy` enables the fifteen-minute recovery timer by default. Take a
consistent archive backup before enabling it on an existing pilot. To deploy
with scheduled recovery disabled, pass
`-e '{"weather_sd_recovery": false}'` to `bin/pi deploy`. The collector runs
independently of the timer.

To preview recovery on the Pi, run:

```sh
sudo -u canones-weather /opt/canones-weather/.venv/bin/python \
  -m canones_weather.recover /var/lib/canones-weather/pilot/weewx.conf --dry-run
```

The preview saves validated SD CSVs under the pilot's private `recovery/`
directory and reports the number of eligible records. The timer reports
insertions and download failures in `journalctl -u canones-weather-recover.service`.
The next successful collector export includes the recovered observations.
See [outages and recovery](../../docs/station.md#outages-and-recovery) for
coverage, provenance, and measurement limitations.

## Inspect the pilot in the local dashboard

```sh
bin/build-site
bin/pi snapshot
python3 -m http.server 8000 --directory dist
```

Open `http://localhost:8000/canones/`. Snapshot copies the Pi's JSON into the ignored
build output and selects it as the local feed. It retains the observation's time
and unverified source. Repeat `bin/pi snapshot` to refresh; this is a snapshot,
not a continuous connection. `bin/build-site` restores the sample preview.

## SSH authentication

The commands use your SSH agent or an existing shared connection. To authenticate
with a password in your own terminal and share a connection for 30 minutes:

```sh
mkdir -p tmp
ssh -F /dev/null -M -S "$PWD/tmp/pi-ssh.sock" \
  -o UserKnownHostsFile="$PWD/tmp/ssh_known_hosts" \
  -o PubkeyAuthentication=no -o ControlPersist=30m -fN "$WEATHER_PI_SSH"
```

`bin/pi` reuses this socket. Host keys are pinned in ignored `tmp/ssh_known_hosts`.
Close the connection with:

```sh
ssh -F /dev/null -S "$PWD/tmp/pi-ssh.sock" -O exit "$WEATHER_PI_SSH"
```

## Stop or recover

```sh
ssh -F /dev/null -S "$PWD/tmp/pi-ssh.sock" "$WEATHER_PI_SSH" \
  sudo systemctl disable --now canones-weather-pilot
```

Stopping the collector preserves its archive. `bin/pi backup` uses SQLite's online
backup API, downloads a consistent snapshot into ignored `tmp/`, and checks its
integrity. Run it from another machine to keep a copy off the Pi; it is an
operator command, not a scheduled backup. Keep these files separately from public
JSON and website assets. Do not copy an actively written database file.

## Publish to R2

Create an R2 Object Read & Write credential restricted to `canones-weather`.
Save these settings in `tmp/r2-publisher.env` with mode `0600`; `tmp/` is
ignored by Git:

```sh
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

Save the OpenTofu destination output to the separate, non-secret settings file
and deploy the publisher:

```sh
tofu -chdir=opentofu/environments/prod output -json publisher > tmp/publisher.json
bin/pi deploy
bin/pi publish
```

`bin/pi deploy` updates the unit for an already installed publisher. The
production station site build checks that the public feed has all three history
files for the current dataset. If the build is held, verify the Pi has published
the new layout and retry the station deployment in Pages.

The publisher credentials are installed root-only at `/etc/canones-weather/r2.env`
and passed to an isolated service. `canones-weather-publish.timer` checks for
changed exports every five minutes and uploads changed history before current
JSON. It rejects samples, mismatched datasets, and unverified production data.
The service keeps successful upload receipts in its private
`/var/lib/canones-weather-publisher/` state directory. Clearing the receipts
forces all four snapshots to be uploaded on the next run.
The broad Cloudflare infrastructure token belongs only on the deployment host.

Check `current.json`'s `observed_at`, each history file's `through`, the latest
archive record, and collector logs to assess freshness. Use the
[data contract](../../docs/data.md#chart-history) to interpret each watermark.
See [outages and SD recovery](../../docs/station.md#outages-and-recovery)
before importing gateway files or enabling catch-up.

Inspect publishing with `systemctl status canones-weather-publish.timer` and
`journalctl -u canones-weather-publish.service` on the Pi. Stop public updates with
`sudo systemctl disable --now canones-weather-publish.timer`; local collection
continues independently.
