# Uniqlo Sales Alerter (Abbaty Fork): Technical Specification

**Status:** Draft v0.1
**Owner:** Abbaty
**Companion to:** PRD, Design Brief

## 1. Architecture Overview

```
                                ┌──────────────────────────┐
                                │   Uniqlo Commerce API    │
                                │  (per country / region)  │
                                └────────────┬─────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       FastAPI application                       │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐     │
│  │  Scheduler  │  │ Sale checker │  │   Matcher service   │     │
│  │ (APScheduler│─▶│  + stock     │─▶│ (per saved filter)  │     │
│  │  or asyncio)│  │  verifier    │  └──────────┬──────────┘     │
│  └─────────────┘  └──────────────┘             │                │
│                                                ▼                │
│  ┌──────────────┐  ┌──────────────────────────────────────┐     │
│  │  REST API    │  │     Notification dispatcher          │     │
│  │  + Web UI    │◀─│     (Apprise + signed actions)       │     │
│  │ (Jinja+HTMX) │  └──────────────────────────────────────┘     │
│  └──────┬───────┘                                               │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────┐         ┌─────────────────────────────┐       │
│  │  SQLite DB   │         │ i18n catalogues (Babel)     │       │
│  │ (/app/data)  │         │ locale/<lang>/messages.po   │       │
│  └──────────────┘         └─────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

One process, one container, one SQLite file. No external services required.

## 2. Stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | match or slightly bump upstream |
| Web framework | FastAPI | already used upstream |
| ASGI server | Uvicorn | standard |
| Templates | Jinja2 | server-rendered |
| Interactivity | HTMX + Alpine.js | no JS build pipeline |
| Styling | Tailwind CSS | preset generated from tokens.json |
| Tailwind build | tailwindcss CLI (standalone binary) | no Node required at runtime |
| Database | SQLite | single file, atomic, well-supported in Python |
| ORM | SQLAlchemy 2.x with `aiosqlite` driver | mature async story |
| Migrations | Alembic | versioned schema |
| Scheduler | APScheduler `AsyncIOScheduler` | survives process lifecycle in-app |
| HTTP client (Uniqlo) | httpx async | already used upstream |
| Notifications | Apprise | replaces hand-rolled channels |
| Templating for notifications | Jinja2 | shared with web UI |
| i18n | Babel + Jinja2 i18n extension | gettext-based |
| Testing | pytest, pytest-asyncio, httpx test client | upstream uses pytest already |
| Linting | ruff | upstream uses ruff |
| Type checking | mypy (strict on `services/`, lax elsewhere) | new |
| Logging | structlog over stdlib JSON formatter | new |
| Container base | `python:3.12-slim` | small footprint |

## 3. Data Model

SQLite database at `/app/data/alerter.db`. Schema versioned via Alembic, located in `src/uniqlo_alerter/db/migrations/`.

### Tables

```sql
-- Saved filters: the headline feature
CREATE TABLE saved_filters (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  gender          TEXT NOT NULL,          -- JSON array
  min_discount    REAL NOT NULL DEFAULT 0,
  sizes_clothing  TEXT NOT NULL DEFAULT '[]',  -- JSON array
  sizes_pants     TEXT NOT NULL DEFAULT '[]',  -- JSON array, mixed units OK
  sizes_shoes     TEXT NOT NULL DEFAULT '[]',  -- JSON array
  one_size_match  INTEGER NOT NULL DEFAULT 0,  -- boolean
  availability_mode TEXT NOT NULL DEFAULT 'both'
                  CHECK (availability_mode IN ('online', 'in_store', 'both')),
  ignored_keywords TEXT NOT NULL DEFAULT '[]', -- JSON array, filter-scoped
  enabled         INTEGER NOT NULL DEFAULT 1,
  snooze_until    TIMESTAMP NULL,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Specific variants the user wants tracked regardless of sale
CREATE TABLE watched_variants (
  id           INTEGER PRIMARY KEY,
  product_id   TEXT NOT NULL,
  color_code   TEXT NOT NULL,
  size_code    TEXT NOT NULL,
  added_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(product_id, color_code, size_code)
);

-- Permanent ignores by product ID
CREATE TABLE ignored_products (
  id           INTEGER PRIMARY KEY,
  product_id   TEXT NOT NULL UNIQUE,
  name         TEXT,                       -- cached for display
  added_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Permanent ignores by keyword (global scope; per-filter keywords live on saved_filters)
CREATE TABLE ignored_keywords (
  id           INTEGER PRIMARY KEY,
  keyword      TEXT NOT NULL UNIQUE COLLATE NOCASE,
  added_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Variant change tracking: drives "is this new?"
CREATE TABLE seen_variants (
  variant_key   TEXT PRIMARY KEY,          -- "<product_id>:<color>:<size>:<discount%>"
  product_id    TEXT NOT NULL,
  color_code    TEXT NOT NULL,
  size_code     TEXT NOT NULL,
  discount_pct  REAL,
  last_seen_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Check run history (for status display and debugging)
CREATE TABLE check_history (
  id              INTEGER PRIMARY KEY,
  ran_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  duration_ms     INTEGER NOT NULL,
  deals_scanned   INTEGER NOT NULL DEFAULT 0,
  deals_matched   INTEGER NOT NULL DEFAULT 0,
  deep_discounts  INTEGER NOT NULL DEFAULT 0,  -- count where discount >= threshold
  error           TEXT NULL
);

-- Granular deal observations for heatmap
CREATE TABLE deal_observations (
  id            INTEGER PRIMARY KEY,
  observed_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  product_id    TEXT NOT NULL,
  discount_pct  REAL,
  is_deep       INTEGER NOT NULL DEFAULT 0   -- boolean, denormalised for fast group-by
);

CREATE INDEX idx_deal_observations_observed_at ON deal_observations(observed_at);
CREATE INDEX idx_deal_observations_is_deep ON deal_observations(is_deep);

-- Notification dispatch log (history + debugging)
CREATE TABLE notification_log (
  id           INTEGER PRIMARY KEY,
  sent_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  channel      TEXT NOT NULL,              -- apprise scheme, e.g. "tgram", "mailto"
  filter_ids   TEXT NOT NULL,              -- JSON array of saved_filter IDs
  deal_count   INTEGER NOT NULL,
  status       TEXT NOT NULL,              -- "success" | "failed"
  error        TEXT NULL
);

-- Migration marker (idempotent upstream import)
CREATE TABLE migrations_applied (
  name         TEXT PRIMARY KEY,
  applied_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Indexes worth adding

```sql
CREATE INDEX idx_seen_variants_product ON seen_variants(product_id);
CREATE INDEX idx_check_history_ran_at ON check_history(ran_at);
CREATE INDEX idx_notification_log_sent_at ON notification_log(sent_at);
```

### Configuration storage

Application configuration (`config.yaml`) remains a YAML file mounted into the container. It is the user-facing source of truth for non-filter settings:

```yaml
store_country: "nl/nl"
ui_language: "en"

check_interval_minutes: 30
scheduled_checks: []
quiet_hours:
  enabled: false
  start: "01:00"
  end: "08:00"

server_url: ""
port: 8000

deep_discount_threshold: 50    # percent; for heatmap "is_deep" classification

notifications:
  apprise_urls: []
  send_digest_on_first_run: true
  notify_only_on_changes: true
  low_stock_threshold: 3
  suppress_low_stock_alerts: false
```

The UI writes back to this file on save. SQLite is for state, not configuration.

## 4. Notification System

### Apprise integration

All channels dispatched via Apprise. Configured Apprise URLs are passed to a single `AppriseNotifier` that:

1. Constructs an `Apprise` object on init
2. Adds each URL with validation
3. On dispatch, generates one HTML body, one plaintext body, and a Telegram-optimised caption from a shared template
4. Sends concurrently; logs success/failure per URL into `notification_log`

```python
class AppriseNotifier:
    def __init__(self, urls: list[str]):
        self.apprise = apprise.Apprise()
        for url in urls:
            self.apprise.add(url)

    async def send(self, deals: list[SaleItem], filters_matched: dict[int, list[str]]) -> None:
        html = render_email(deals, filters_matched)
        text = render_text(deals, filters_matched)
        title = render_title(deals)
        await asyncio.to_thread(
            self.apprise.notify,
            title=title,
            body=html,
            body_format=apprise.NotifyFormat.HTML,
        )
```

### Action URL signing

Action buttons embed signed URLs:

```
{server_url}/actions/ignore?product_id=E12345&exp=<unix>&sig=<hmac>
{server_url}/actions/snooze?filter_id=4&duration=7d&exp=<unix>&sig=<hmac>
{server_url}/actions/watch?product_id=E12345&color=09&size=004&exp=<unix>&sig=<hmac>
{server_url}/actions/unwatch?product_id=E12345&color=09&size=004&exp=<unix>&sig=<hmac>
```

Signature: HMAC-SHA256 over the query string (sorted, excluding `sig`), with a secret loaded from env var `ALERTER_SECRET` (auto-generated and persisted to `/app/data/.secret` on first run if not set).

Default expiry: 30 days. Expired or invalid actions render a friendly error page with a link back to the app.

Action handlers respond with a small confirmation page and an auto-redirect to the relevant settings view. They tolerate replay (idempotent) for ignore/watch/unwatch; snooze is also idempotent (re-applying the same snooze duration just refreshes the expiry).

## 5. i18n Architecture

### Strings sources

- Python source: wrapped in `gettext()` (alias `_`)
- Jinja2 templates: `{{ _("...") }}` via the i18n extension
- JS strings (rare, inside Alpine components): pulled from a `window.i18n` object server-rendered into the page

### Build process

`babel.cfg` defines extraction rules. `pybabel extract -F babel.cfg -o messages.pot src/` produces a template. `pybabel update -i messages.pot -d locale -l en` updates the English catalogue. Compile with `pybabel compile -d locale`.

Locale layout:

```
src/uniqlo_alerter/i18n/
├── babel.cfg
├── messages.pot
└── locale/
    └── en/
        └── LC_MESSAGES/
            ├── messages.po
            └── messages.mo (compiled, gitignored)
```

CI step: extract strings, fail build if `.po` files are out of date or have empty translations in shipped languages.

### Country and language separation

`config.store_country` (e.g. `nl/nl`, `de/de`, `us/en`) is fed to the Uniqlo API client only. It selects which catalogue to fetch.

`config.ui_language` (e.g. `en`, `nl`) is fed to the Babel context only. It selects which translation catalogue to load.

The two never auto-couple. Adding a Dutch UI translation in v2 means dropping `nl/LC_MESSAGES/messages.po` into the locale directory and offering "nl" in the UI language selector.

## 6. Heatmap Implementation

### Data flow

Every check run writes one row per matched deal to `deal_observations` with `is_deep = (discount_pct >= deep_discount_threshold)`.

### Query

```sql
SELECT
  strftime('%w', observed_at) AS day_of_week,    -- 0 = Sunday, 6 = Saturday
  strftime('%H', observed_at) AS hour_of_day,
  COUNT(*) AS deep_count
FROM deal_observations
WHERE is_deep = 1
  AND observed_at >= datetime('now', '-90 days')
GROUP BY day_of_week, hour_of_day;
```

Result is shaped into a 7 × 24 array in the service layer (filling zeroes for missing cells). Returned to the template as a list of cell objects with `day`, `hour`, `count`, `opacity` (count / max_count, clamped to [0.05, 1.0]).

### Retention

Deal observations older than 365 days are pruned by a daily housekeeping job.

## 7. Migration from Upstream

### Detection

On startup, before any service initialises, check for:

- `/app/config.yaml` with upstream filter structure
- `/app/.seen_variants.json` or `/app/data/.seen_variants.json`

If either is present and the `migrations_applied` table does not have an `upstream_v1` row, run the migration.

### Steps

1. Parse the YAML filter section
2. Create one `saved_filters` row named `"Imported"` with the upstream gender / min_discount / sizes
3. Import `filters.watched_urls` (upstream) or `filters.watched_variants` (jabescript) by parsing the URLs into `product_id`, `color_code`, `size_code`
4. Import `filters.ignored_products` and `filters.ignored_keywords` if present
5. Read `.seen_variants.json`, parse each variant key, populate `seen_variants`
6. Move source files to `/app/data/migrated/<timestamp>/`
7. Insert `("upstream_v1", now())` into `migrations_applied`

### Failure handling

The migration runs in a single SQLite transaction. If anything fails, the transaction rolls back, the migration marker is not written, and the app starts with a clear warning in logs and a visible banner in the UI: "Migration from upstream failed. Original config preserved. Check logs."

## 8. Deployment

### Dockerfile

Multi-stage build:

1. **builder stage**: `python:3.12-slim` + build deps, install pip dependencies, compile Babel `.mo` files, run `tailwindcss` CLI to build `static/app.css`, extract Tailwind preset from `design/tokens/`
2. **runtime stage**: `python:3.12-slim`, copy only built artifacts and source, set `USER alerter` (non-root), expose 8000

Resulting image target: under 200MB.

### Multi-arch build

GitHub Actions workflow on `push` to `main` and on tags:

- Set up QEMU + Buildx
- Build for `linux/amd64` and `linux/arm64`
- Push to `ghcr.io/<owner>/uniqlo-sales-alerter`
- Tags: `latest`, `vX.Y.Z`, `X.Y`

### Compose template

`docker-compose.yml`:

```yaml
services:
  alerter:
    image: ghcr.io/abbaty/uniqlo-sales-alerter:latest
    container_name: uniqlo-alerter
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/app/config.yaml
      - alerter-data:/app/data
    environment:
      - ALERTER_SECRET=${ALERTER_SECRET:-}
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
      interval: 60s
      timeout: 5s
      retries: 3
      start_period: 30s

volumes:
  alerter-data:
```

### Portainer stack template

`deploy/portainer-template.json` provides a one-click deploy entry for Portainer's "App Templates" feature. Documented in the README.

### Healthcheck

`GET /health` returns:

- `200 OK` if: SQLite is writeable, scheduler is running, last check (if any) is within `2 × check_interval_minutes`
- `503` otherwise, with a JSON body describing which check failed

## 9. Logging and Observability

### Structured logs

`structlog` over stdlib JSON formatter. Every log line has:

- `timestamp` (ISO 8601 UTC)
- `level`
- `event` (short string identifier)
- `request_id` (for HTTP requests)
- `filter_id`, `product_id`, `country` (when relevant)
- `error` (full traceback as one field when level=ERROR)

Output: stdout. Captured by Docker / Portainer / journalctl per deployment.

### Status endpoints

- `GET /health`: as above
- `GET /api/v1/status`: scheduler state, last check time, last check outcome, db size
- `GET /api/v1/check-history?limit=50`: recent runs
- `GET /api/v1/notification-log?limit=50`: recent notification dispatches

### UI surfacing

Footer status pill on every page shows: last check time, active filter count, snoozed count. Tapping opens a small overlay with full status details.

## 10. Testing Strategy

### Coverage target

70 percent line coverage minimum on `src/`, enforced by CI.

### Unit tests (must-have)

- `parsers/size.py`: every size category, every valid input form, edge cases (mixed units, blank, malformed)
- `parsers/invoice_paste.py`: Uniqlo invoice text → extracted size suggestions, across at least 3 invoice variants
- `services/matcher.py`: filter matching for every combination of gender, min_discount, sizes, availability_mode, ignored keywords, snooze state
- **`services/matcher.py` availability_mode**: tests for each of `online`, `in_store`, `both`, plus the fallback behaviour when the country API doesn't expose a reliable channel flag
- **`services/matcher.py` trouser-waist regression**: reproduce the reported bug as a failing test first, then fix
- `services/sale_checker.py`: variant key generation, seen-set diffing, change classification
- `notifications/templates.py`: HTML and text rendering with various deal counts (0, 1, many)
- `notifications/action_urls.py`: signing, verification, expiry, tampering rejection
- `db/migrations.py`: schema migration apply / rollback
- `services/migration.py`: upstream import with various source shapes

### Integration tests

- Full check loop: mocked Uniqlo API → matcher → notification dispatcher → DB rows written
- Migration: spin up app with upstream-style files, verify resulting DB state and that files are moved
- Heatmap: insert N observations across days/hours, verify aggregation
- Scheduler with quiet hours: verify no checks run during quiet window

### Test layout

```
tests/
├── conftest.py              -- pytest fixtures, test DB, mocked Uniqlo API
├── unit/
│   ├── parsers/
│   ├── services/
│   ├── notifications/
│   └── db/
└── integration/
    ├── test_check_loop.py
    ├── test_migration.py
    ├── test_heatmap.py
    └── test_scheduler.py
```

## 11. Project Structure

```
uniqlo-sales-alerter/
├── README.md
├── NOTICE                      -- attribution to upstream
├── LICENSE                     -- MIT
├── CHANGELOG.md
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── docker-compose.example.yml
├── .github/
│   └── workflows/
│       ├── ci.yml              -- lint, test, coverage
│       └── release.yml         -- multi-arch build & push to ghcr
├── deploy/
│   └── portainer-template.json
├── design/                     -- per Design Brief section 8
│   ├── README.md
│   ├── inspiration/
│   ├── tokens/
│   ├── flows/
│   ├── wireframes/
│   ├── mockups/
│   ├── exports/
│   └── scripts/
│       └── build-tokens.py
├── src/
│   └── uniqlo_alerter/
│       ├── __init__.py
│       ├── __main__.py
│       ├── app.py              -- FastAPI app factory
│       ├── config.py           -- YAML load + env merge + write-back
│       ├── secret.py           -- ALERTER_SECRET generation/load
│       ├── db/
│       │   ├── __init__.py
│       │   ├── engine.py
│       │   ├── models.py       -- SQLAlchemy
│       │   └── migrations/
│       │       └── versions/
│       ├── clients/
│       │   └── uniqlo.py
│       ├── services/
│       │   ├── sale_checker.py
│       │   ├── matcher.py
│       │   ├── snooze.py
│       │   ├── heatmap.py
│       │   ├── scheduler.py
│       │   └── migration.py
│       ├── parsers/
│       │   ├── size.py
│       │   └── invoice_paste.py
│       ├── notifications/
│       │   ├── apprise_notifier.py
│       │   ├── templates.py
│       │   ├── action_urls.py
│       │   └── jinja_templates/
│       │       ├── email.html.j2
│       │       └── email.txt.j2
│       ├── api/
│       │   ├── routes.py
│       │   ├── actions.py
│       │   └── schemas.py
│       ├── ui/
│       │   ├── routes.py
│       │   ├── templates/
│       │   │   ├── base.html
│       │   │   ├── deals.html
│       │   │   ├── filters/
│       │   │   ├── inbox/
│       │   │   ├── insights.html
│       │   │   ├── settings.html
│       │   │   └── help/
│       │   └── static/
│       │       ├── tokens.css
│       │       ├── app.css      -- Tailwind-generated
│       │       ├── htmx.min.js
│       │       ├── alpine.min.js
│       │       └── icons/       -- Phosphor SVGs as needed
│       └── i18n/
│           ├── babel.cfg
│           ├── messages.pot
│           └── locale/
│               └── en/LC_MESSAGES/messages.po
├── tests/                      -- per Testing Strategy
└── docs/                       -- Diataxis-organised user docs (mirrored at /help in app)
    ├── tutorials/
    ├── how-to/
    ├── reference/
    └── explanation/
```

## 12. Repo and Attribution

### Fork location

`abbaty/uniqlo-sales-alerter` on GitHub. Hard fork from `kequach/uniqlo-sales-alerter`.

### License

MIT, matching upstream. `LICENSE` retains the upstream copyright line and adds the fork's copyright line.

### NOTICE file

```
Uniqlo Sales Alerter (Abbaty Fork)

Forked from kequach/uniqlo-sales-alerter (original by Keven Quach, MIT licence).
Additional fork-specific contributions Copyright (c) 2026 Abbaty.

This fork is not affiliated with, endorsed by, or sponsored by the original
maintainer or by Uniqlo Co., Ltd.

Changes from upstream:
- Replaced single global filter with named saved filters
- Replaced hand-rolled notifiers with Apprise
- Added snooze per filter, deal heatmap, invoice-paste size extraction
- Added i18n architecture with separated store country and UI language
- Replaced JSON state files with SQLite + Alembic migrations
- Increased test coverage; added regression test for trouser-waist bug
- Reworked UI for mobile-first usage with empty-state-first onboarding
```

### README structure

1. Hero (one-line description, badges, screenshot)
2. **What's different from upstream** (the headline diffs as a bullet list)
3. **Quick start** (Docker compose, three commands)
4. **Design** (short paragraph + 2-3 screenshots + link to /design)
5. **Configuration** (link to reference docs)
6. **Architecture** (one-paragraph summary, link to this tech spec)
7. **Contributing** (PRs welcome, design contributions via Penpot)
8. **Attribution** (link to NOTICE)
9. **License**

### Upstream contributions

Where this fork's changes are general-purpose, open PRs to `kequach/uniqlo-sales-alerter`:

- Trouser-waist bug fix with regression test
- Increased unit test coverage in shared modules
- Apprise refactor (if jabescript or upstream want it)

The headline change (saved filters) likely stays fork-specific because it's a substantial restructure.

## 13. Open / TBD

- Confirm Python version (3.12 vs 3.13)
- Confirm whether Tailwind preset is generated by Python script or a small Node-on-build-only step
- Confirm Penpot MCP availability and document the exact integration during implementation
- Decide on a logo / wordmark, or leave text-only
