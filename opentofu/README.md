# Weather hosting

The environment roots and shared `modules/weather-hosting` module own
Cloudflare Pages sites, weather DNS, and R2 observation storage. AWS state
buckets are managed separately by `iceburg-infra`.

| Purpose | Production location |
| --- | --- |
| Hub | https://weather.iceburg.net |
| Station | https://canones.weather.iceburg.net |
| JSON | https://data.weather.iceburg.net/canones/current.json |

```text
opentofu/
├── modules/weather-hosting/  # Pages, DNS, and R2 resources
└── environments/
    ├── prod/                # live station, main branch
    └── notprod/             # fixtures/replay, notprod branch
```

Each root owns its backend, provider, lock file, concrete module inputs in
`main.tf`, and forwarded outputs. The shared module owns resource definitions and
input types. It receives its provider from the root and has no backend.
This follows [Google's root-module guidance](https://docs.cloud.google.com/docs/terraform/best-practices/root-modules).
Use the default workspace; each environment has separate state.

| Setting | prod | notprod |
| --- | --- | --- |
| Hub | `weather.iceburg.net` | `weather-notprod.iceburg.net` |
| Dashboard | `canones.weather.iceburg.net` | `canones.weather-notprod.iceburg.net` |
| Data host | `data.weather.iceburg.net` | `data.weather-notprod.iceburg.net` |
| R2 bucket | `canones-weather` | `canones-weather-notprod` |
| State bucket suffix | `state-prod` | `state-nonprod` |
| State key environment | `prod` | `notprod` |
| Git branch | `main` | `notprod` |

Use the `notprod` Git branch for test deployments, with fixtures or replayed data
and separate
bucket-scoped publisher credentials. Do not configure weather-network uploads
from it. Both roots use the same hosting behavior, including protected buckets;
review any deliberate teardown separately. For reuse, edit a root's public
settings and provide your own backend configuration.

## Deploy

Install OpenTofu 1.9+ and AWS CLI. Enable R2 and authorize the GitHub repository
through Cloudflare's GitHub app. The selected branch must contain the site sources
and `bin/build-site`, which assembles `dist/hub` and `dist/canones` for the two
Pages projects. Preview deployments are disabled.

From `opentofu/environments/prod/` (or `notprod/` for a separate test deployment):

```sh
cp s3.tfbackend.example s3.tfbackend
aws sso login --profile briceburg-admin
read -rsp 'Cloudflare API token: ' CLOUDFLARE_API_TOKEN
printf '\n'
export CLOUDFLARE_API_TOKEN
tofu init -backend-config=s3.tfbackend
tofu plan -out=weather.tfplan
# Review the saved plan before applying.
tofu apply weather.tfplan
unset CLOUDFLARE_API_TOKEN
```

The token needs Pages Edit, Workers R2 Storage Edit, DNS Edit, and Zone Read for
the selected account/zone. Authentication for S3 state is independent of
Cloudflare. Keep tokens, local backend files, state, and plans outside Git; do
not put credentials in variable files. The example backend contains identifiers
only. Forks must use their own backend and settings.

Production state uses bucket `iceburg-infra-opentofu-state-prod` and key
`terraform/canones-weather/prod/terraform.tfstate`. Notprod uses the nonproduction
bucket and its own key, as shown in each root's backend example. This repository
owns the weather resources; `iceburg-infra` owns the state buckets.

## Publisher

`tofu output -json site_urls` gives website URLs. `tofu output -json publisher`
gives the bucket, S3 endpoint, region, `key_prefix`, and `public_base_url`.
Upload `canones/current.json` with `Content-Type: application/json` and
`Cache-Control: public, max-age=60`. Generate timestamped observations on the Pi
every five minutes; keep permanent archives there. These outputs contain no
write credentials. Provision a separate bucket-scoped R2 Object Read & Write
credential for the Pi, outside OpenTofu state and website assets.

The bucket has destruction protection. CORS permits public GET/HEAD from any
origin; r2.dev is disabled. R2's free allowances are not a spending cap.
After apply, verify HTTPS, Git deployments, CNAME targets, and JSON/CORS/cache
headers. A successful plan does not verify GitHub app access or deployment builds.
Network submissions must use verified WS90 observations regardless of what the
public dashboard displays.

## Validate without cloud credentials

From the repository root, run `bin/check-infra`. It uses a temporary OpenTofu
working directory so it does not disturb an initialized production backend.
