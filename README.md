# Uniqlo Sales Alerter (Abbaty Fork)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB.svg)](https://www.python.org/downloads/)
[![Container: ghcr.io](https://img.shields.io/badge/container-ghcr.io-181717.svg)](https://github.com/abbatykori/uniqlo-sales-alerter/pkgs/container/uniqlo-sales-alerter)

A self-hosted server that watches [Uniqlo](https://www.uniqlo.com)'s sale catalogue against your saved filters and notifies you when a match shows up. Talks directly to Uniqlo's Commerce API; no scraping. Mobile-first web UI, SQLite-backed state, ~80 supported notification services via [Apprise](https://github.com/caronc/apprise).

Forked from [kequach/uniqlo-sales-alerter](https://github.com/kequach/uniqlo-sales-alerter). See [NOTICE](NOTICE).

## What's different from upstream

- **Named saved filters** replace the single global filter. One household, one buyer, many sizes: "Me tops" + "Me bottoms" + "Kid 5y" + "Spouse" matches the real shape.
- **Apprise** replaces the four hand-rolled notification channels (Telegram + Email + Console + HTML preview). One URL list, ~80 services.
- **Snooze per filter** (1d / 7d / 30d / forever), **deal heatmap** (7 × 24 grid of deep-discount drops), **invoice-paste size extraction**.
- **HMAC-signed action URLs** in notifications: ignore / watch / unwatch / snooze from your inbox, valid for 30 days.
- **SQLite + Alembic** for durable state. `.seen_variants.json` retired.
- **HMTX + Tailwind + design tokens**, mobile bottom-tab + desktop sidebar, empty-state-first onboarding.
- **Multi-arch Docker** (`amd64` + `arm64`) published to `ghcr.io/abbatykori/uniqlo-sales-alerter` on every `v*` tag.
- **i18n architecture** with separated `store_country` and `ui_language`; English shipped, structured for translation PRs.

See [`docs/specs/`](docs/specs/) for the full design rationale.

## Quick start (Docker)

```bash
docker run -d --name uniqlo-alerter \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e STORE_COUNTRY=nl/nl \
  -e NOTIFICATIONS_APPRISE_URLS="tgram://BOT_TOKEN/CHAT_ID" \
  ghcr.io/abbatykori/uniqlo-sales-alerter:latest
```

Open <http://localhost:8000/ui/> for the Deals view. Add filters at `/ui/filters/new` or paste a Uniqlo order email at `/ui/filters/paste` to auto-detect your sizes.

For the docker-compose form, copy [`docker-compose.yml`](docker-compose.yml). For Portainer one-click deploy, see [`deploy/`](deploy/).

## Design

Mobile-first, calm, restrained. Off-white canvas, warm-gold accent, Noto Serif headings + Noto Sans body. Tokens live in `design/tokens/tokens.json` (W3C Design Tokens Format). The full design brief is in [`docs/specs/02-design-brief.md`](docs/specs/02-design-brief.md).

## Configuration

Two layers:

- **`config.yaml`** at the repo root (or mounted at `/app/config.yaml`) — store country, scheduling, quiet hours, server URL, Apprise URLs. The web UI auto-saves changes back to this file.
- **Environment variables** for first-run bootstrap and CI. Every YAML key has an env-var equivalent; see [`config.yaml`](config.yaml) for the full schema and `docs/i18n.md` for the i18n workflow.

The matcher reads filters from the SQLite `saved_filters` table — manage them in the web UI at <http://localhost:8000/ui/filters>, or via the REST API at `/api/v1/filters`. The legacy `config.yaml::filters` block is preserved for backward-compatibility but no longer drives matching after step 8; a one-shot bridge migration on first run seeds an "Imported" saved filter from it.

### Notifications

One config field replaces the four upstream channels:

```yaml
notifications:
  apprise_urls:
    - "tgram://<bot_token>/<chat_id>"
    - "mailto://user:app_password@gmail.com?to=user@gmail.com"
    - "ntfys://ntfy.example.com/uniqlo-alerts"
```

Set `NOTIFICATIONS_APPRISE_URLS=...,...` (comma-separated) as an env var for CI / first-run. Existing upstream-style `channels.telegram.enabled=true` + `channels.email.enabled=true` config blocks are auto-translated to `tgram://...` and `mailto://...` URLs at startup, so existing single-user installs work without manual migration.

Apprise covers ~80 services. See the [Apprise wiki](https://github.com/caronc/apprise/wiki) for the full URL syntax per service.

## Architecture

Single FastAPI process, single SQLite file, single container. Async end-to-end (httpx, aiosqlite, APScheduler `AsyncIOScheduler`). HTMX + Tailwind UI; no JavaScript build pipeline. The notification dispatcher renders Jinja-templated HTML/text/title bodies and dispatches via Apprise in a worker thread.

The full architecture brief is in [`docs/specs/03-tech-spec.md`](docs/specs/03-tech-spec.md).

## Development

```bash
# 3.12 venv via uv (or use your preferred tool)
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"

# Tests
.venv/bin/python -m pytest tests/ -m "not e2e"

# Lint
.venv/bin/python -m ruff check src/ tests/

# Local server
.venv/bin/python -m uniqlo_sales_alerter
```

Migrations and i18n compile at app boot from inside the container; for local development run `alembic upgrade head` and `pybabel compile -d src/uniqlo_sales_alerter/i18n/locale -l en` yourself if you've edited the schema or catalogues.

End-to-end tests against the live Uniqlo API are gated behind `pytest -m e2e` and run manually via the `workflow_dispatch` of the CI workflow.

## Contributing

Pull requests welcome. The general flow:

- Open an issue first for non-trivial changes so the design conversation is shared.
- Run `pytest` and `ruff check` before opening the PR; CI gates on both.
- Follow the project conventions in [`.cursor/rules/`](.cursor/rules/) — naming, no `print()` in production code, structured logging, CHANGELOG entry for user-visible changes.
- Design contributions land via Penpot edits in [`design/`](design/); see [Design Brief](docs/specs/02-design-brief.md).

## Attribution

Forked from [kequach/uniqlo-sales-alerter](https://github.com/kequach/uniqlo-sales-alerter) (original by Keven Quach, MIT). Additional fork contributions Copyright (c) 2026 Abbaty. See [NOTICE](NOTICE) for the full list of differences.

This project is not affiliated with, endorsed by, or sponsored by the original maintainer or by Uniqlo Co., Ltd.

## License

[MIT](LICENSE)
