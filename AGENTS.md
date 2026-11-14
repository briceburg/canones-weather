# Working in this repository

## Scope and layout

- Keep changes small, clear, and necessary for the current task. Remove disposable
  experiments rather than carrying them into production scaffolding.
- `src/canones_weather/` contains the gateway diagnostic CLI. Keep it dependency-free.
- `deploy/raspberry-pi/` owns Ansible provisioning and the isolated WeeWX pilot. Preserve the
  existing radio-pad service when working on the shared Pi.
- `opentofu/modules/weather-hosting/` owns reusable hosting resources. Thin
  `opentofu/environments/{prod,notprod}/` roots own settings, providers, and state.
- `site/` owns the original dark-only hub and station dashboard. Share visual
  assets across both; do not copy a third-party weather skin. Pinned third-party
  distributions must retain upstream licenses/notices. Sample fixtures are
  intentionally tracked and must be visibly distinguished from live observations.
  Documentation artwork and sample-preview screenshots are intentional source
  assets; generated site builds and real captures remain ignored.
- Write evergreen usage and reference documentation, not progress updates,
  conversation history, or roadmaps. Describe configuration requirements without
  implying that unimplemented services are operational. Keep the README concise;
  station-specific facts and operating requirements belong in `docs/`.

## Configuration and data

- Require explicit endpoint configuration; prefer local DNS names. Do not embed
  LAN IP addresses in code, defaults, tests, or documentation. Keep host/user
  settings in local configuration or inventory, not duplicated across files.
- `.env` holds `WEATHER_GATEWAY_URL` and `WEATHER_PI_SSH` (`user@host`);
  `.env.example` documents keys including `WEATHER_ELEVATION_M` without personal
  deployment values. uv loads it with `--env-file .env`; Ansible
  commands source it explicitly. Do not add a dotenv dependency or hidden loading.
- Keep personal login names, home-directory paths, and private SSH identities out
  of public files. Check commit author and committer identities as well as content.
  Public commits must use the owner's GitHub noreply email, not the workstation's
  configured email. For this repo use `490144+briceburg@users.noreply.github.com`
  with the public name `briceburg`, supplying Git's `-c user.name` and
  `-c user.email` options when committing if local settings differ.
- Keep bucket-scoped publishing credentials at `tmp/r2-publisher.env` (mode
  `0600`) and non-secret OpenTofu destination output at `tmp/publisher.json`.
  Use these fixed ignored paths rather than configuring a secret-file path in `.env`.
- Never commit credentials, captures, state, saved plans, or generated output.
- Test environments use separate state, buckets, projects, and publisher credentials.
- Weather-network uploads must use verified WS90 outdoor observations. Additional
  sensors must not override those fields. Validate provenance before enabling uploads.
- Use a WN31 auxiliary channel for garage readings; WN32 overrides primary WS90
  temperature/humidity. Verify sensor mapping before relying on it.

## Testing and validation

- Do not write retroactive tests merely to cover existing code or complete a change.
- Write tests only after the design has been validated, or deliberately use TDD.
- Keep tests sparing and meaningful: protect an important behavior or realistic
  failure mode, not implementation details, trivial wiring, or mocked call counts.
- Wire retained tests into the normal check command, `bin/ci`; do not add orphan tests.
- Prefer direct inspection or a bounded experiment while exploring a design.
- Run checks appropriate to the change. Avoid unrelated or repeated test runs once
  checks pass unless new changes or evidence justify them.
- `bin/ci` runs Ruff, focused Python tests, JavaScript syntax, site assembly, and
  backend-disabled OpenTofu validation.
  `bin/check-infra` runs infrastructure checks alone. Neither applies infrastructure.
- Do not claim deployment, live sensor verification, or Pi access based on static
  validation. State what was actually checked and what remains unverified.
