# Contributing

Issues, suggestions, and pull requests are welcome. Keep changes focused and run
checks relevant to the area you change. Cloud accounts and station hardware are
not required for documentation or sample-site contributions.

## Gateway tool

With Python 3.11+ and uv:

```sh
uv sync --locked
uv run ruff check
uv run ruff format --check
uv run --group station pytest -q
```

The `station` group supplies the pinned WeeWX runtime for the archive/export
integration check; no gateway is contacted by the tests.

## Website

Run `bin/build-site` and follow the [local preview guide](site/README.md).
For changed JavaScript, check syntax with Node.js 22.7+:

```sh
node --input-type=module --check < site/canones/assets/dashboard.js
```

Use the same command with the path of any other JavaScript file you change.
Run the focused chart calculation checks with
`node --test tests/test_*.mjs`.
Keep sample data clearly labeled and check layouts on mobile and desktop.

## Infrastructure

Only hosting changes need OpenTofu 1.9+ and `bin/check-infra`. It checks formatting
and validates both roots without accessing their state backends or applying
resources. Provider downloads need network access. Do not plan or apply the
project's production configuration as part of an ordinary contribution.

`bin/ci` runs all repository checks and requires the tools for each area above.
See [AGENTS.md](AGENTS.md) for repository conventions and the testing policy.

## Releases

Maintainers run **Actions → Create release → Run workflow**, selecting `main` and
providing a nickname. The workflow validates that commit, then publishes a GitHub
release with generated notes. Tags use the UTC date, `vYYYY.MM.DD-N`: the first
release of a day is `-0`, and later releases increment the largest existing suffix.
The nickname appears in the release title. No additional publishing token is needed.
