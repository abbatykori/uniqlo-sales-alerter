# Agent Handoff Brief

**Status:** Draft v0.1
**Read this first.** This brief sits on top of the three substantive documents (PRD, Design Brief, Tech Spec) and provides reading order, build order, real test fixtures, a decisions log, working agreements, and questions to ask before starting.

## 1. How to use these documents

Read in this order:

1. **This brief** (sets the frame and flags open items)
2. **`01-prd.md`** (what and why, user-facing behaviour)
3. **`03-tech-spec.md`** (how, architecture and schema)
4. **`02-design-brief.md`** (look and feel, IA, design tokens)

The three substantive docs are the source of truth for their respective domains. If anything in this brief conflicts with them, the substantive doc wins.

## 2. Build order

The features in the PRD are independent enough to be built in different orders, but this sequence minimises rework:

1. **Repo skeleton**: project structure, `pyproject.toml`, Dockerfile (multi-stage), `docker-compose.yml`, `LICENSE`, `NOTICE`, README scaffold, GitHub Actions CI workflow stubs
2. **Healthcheck and minimal FastAPI app**: just `/health` returning 200, container builds and runs
3. **SQLite + Alembic**: initial migration creating all tables from Tech Spec section 3
4. **Config loading**: YAML parse, env var merge, write-back capability
5. **i18n bootstrap**: Babel set up, `messages.pot` extracted from an empty source, English catalogue scaffolded
6. **Saved filter CRUD**: DB models, SQLAlchemy session management, basic REST endpoints, basic Jinja templates with HTMX
7. **Uniqlo client**: port from upstream, wrap in a small abstraction that takes country and returns sale items. Keep the Uniqlo-specific logic isolated to one module.
8. **Matcher service**: with the full test suite (gender, sizes, discount, availability_mode, ignored keywords, snooze state). This is where the trouser-waist regression test goes.
9. **Scheduler + check loop**: APScheduler, periodic interval, quiet hours, scheduled times
10. **Notification dispatcher**: Apprise integration, HTML/text/title templates, log every dispatch to `notification_log`
11. **Action URLs**: HMAC signing, expiry, idempotent handlers for ignore / snooze / watch / unwatch
12. **Snooze, ignore, watch flows end-to-end**: from UI button click and from notification action button
13. **Heatmap**: observations table populated on every check, aggregation query, UI rendering with insufficient-data state
14. **Invoice paste parser**: regex against the real fixtures in section 5 below, suggested-chips UI
15. **Migration from upstream**: detection, parse, populate, move source files, write marker
16. **Web UI polish**: empty states for every section, filter chips, mobile-first verification on a real phone
17. **Multi-arch Docker build via GitHub Actions**: amd64 + arm64, push to ghcr.io, tagging strategy
18. **Portainer template + README updates with screenshots**

Sections 1 to 8 are the critical path; everything from 8 onward depends on a working matcher.

## 3. Things to ask the human before starting

Open these as a single message before the first commit:

1. **Repo created at `abbaty/uniqlo-sales-alerter` yet?** If not, please create the empty repo so the first commit can land.
2. **`ALERTER_SECRET`**: should the app auto-generate one on first run and persist it to `/app/data/.secret`, or do you want to set one yourself via env var?
3. **GHCR publishing**: confirm the repo will have a GitHub Personal Access Token or use the built-in `GITHUB_TOKEN` for ghcr.io pushes. Confirm the image visibility (public or private).
4. **Trouser-waist bug**: do you have a concrete repro yet? If not, the regression test will be marked as `@pytest.mark.skip(reason="awaiting repro")` and the matcher work proceeds without it.
5. **Penpot mockups**: are any screens mocked yet, or should the agent work from the Design Brief's token and pattern specs only?
6. **Python version**: confirm 3.12 vs 3.13.
7. **First country to support fully in tests**: PRD says "all countries upstream supports" for v1, but tests should anchor on one. Default suggestion: `nl/nl`. Confirm or override.
8. **Migration source files**: are your current upstream `config.yaml` and `.seen_variants.json` files in a known location, or should the agent build the migration against the upstream schema only (and you'll point it at your real files later)?

## 4. Out of scope for v1 (do not introduce)

These were discussed and explicitly deferred. Do not re-propose them without checking with the human first:

- Price history tracking and target-price wishlist mode
- Home Assistant integration (webhook, MQTT)
- Progressive Web App install support
- Email-forward size import (the paste-text flow covers this 80/20)
- PDF upload for size extraction (paste-text only in v1)
- Per-filter notification channel routing (channels are global in v1)
- Additional language packs beyond English (architecture is ready, content is not)
- Authentication, login, accounts (LAN-only deployment, no auth layer)
- Dark mode
- Em dashes in any user-facing copy (see working agreements)
- Multi-store support (Zara, Mango, etc.). The single-store assumption is baked into v1; revisit later.
- Per-product snooze (per-filter snooze only)
- Per-store physical-stock checking ("is it at the Amsterdam store?"). The availability filter only distinguishes online vs in-store channel, not specific stores.

## 5. Real Uniqlo invoice text (test fixtures)

Use this verbatim as a fixture for the invoice-paste parser. This is the actual text of a real Uniqlo NL order invoice. The parser must handle exactly this format to be considered working.

```
47492809120000, Track Joggers
BLACK, 5-6 Years (120cm)
Price: 1 x 9,90€
Subtotal: 9,90€
(VAT Rate 21%): 1,72€
46932256006000, AIRism Cotton Oversized Mock Neck T-Shirt (Half Sleeve)
OLIVE, XL
Price: 1 x 12,90€
Subtotal: 12,90€
(VAT Rate 21%): 2,24€
46518662007000, Crew Neck T-Shirt
BLUE, XXL
Price: 2 x 7,90€
Subtotal: 15,80€
(VAT Rate 21%): 2,74€
46518757006000, DRY Colour Crew Neck T-Shirt
OLIVE, XL
Price: 1 x 5,90€
Subtotal: 5,90€
(VAT Rate 21%): 1,02€
46549431006000, 100% Supima Cotton T-Shirt
BEIGE, XL
Price: 1 x 12,90€
Subtotal: 12,90€
(VAT Rate 21%): 2,24€
```

### Expected parser output for this fixture

The parser should extract these size suggestions from the above text:

- **Clothing sizes**: `XL`, `XXL` (deduplicated; XL appears 3 times in the source)
- **Kids sizes**: `120cm` (canonical form preferred over `5-6 Years`)

Optional information the parser may also surface (for the suggestion UI, not for filter sizing):

- Product IDs: `47492809120000`, `46932256006000`, `46518662007000`, `46518757006000`, `46549431006000`
- Unique colours: `BLACK`, `OLIVE`, `BLUE`, `BEIGE`

### Additional fixtures to author

The agent should derive additional fixtures from invoices in other countries and other size categories, with at least:

- A pants invoice line (e.g. `BLUE, 32inch`)
- A shoes invoice line (e.g. `BEIGE, 42` or `BLACK, 42.5`)
- A one-size accessory line (e.g. `BLACK, One Size`)
- A multi-line single-product order (qty > 1) to verify dedup
- An invoice with mixed encodings (text copied from PDF often has invisible Unicode)
- An invoice from a non-Euro store to verify the parser is currency-agnostic

If the human cannot provide additional samples, fabricate them in line with the format shown above and mark them as `# synthetic` in the fixture file.

## 6. Trouser-waist bug investigation

**Status: not yet reproduced.** The human has flagged a suspected bug in trouser waist size handling in the upstream code but has not provided a concrete repro.

When investigating, look at the upstream code in these places (the bug could be in any of them):

1. **Size parsing in the upstream client**: how does it parse waist sizes like `32inch`, `34inch`? Are there off-by-one issues with the range (women's start at 22, men's at 28)?
2. **Stock filtering**: when matching a user-requested `32inch` against in-stock variants, is there a string comparison subtly mismatching (e.g. `32inch` vs `32"` vs `32 inch`)?
3. **URL building**: are the colour and size codes in variant URLs correct for pants specifically?

The repro recipe will likely come from the human. When it does:

1. Write the failing test first in `tests/unit/services/test_matcher.py` (and possibly `tests/unit/parsers/test_size.py`)
2. Confirm the test fails on a known-bad input
3. Fix in source
4. Confirm test passes
5. Open a PR upstream with the fix and test, separately from this fork's main work, so the OG community benefits

## 7. Working agreements

These apply throughout the build:

- **All user-facing strings must go through `gettext`**. No hardcoded strings in templates or Python. Run `pybabel extract` after adding new strings; CI fails if catalogues are out of date.
- **No em dashes anywhere in user-facing copy.** This is the human's strict preference applied to all contexts, not just chat. Use commas, periods, colons, parentheses, or semicolons. Apply this to: UI strings, notification templates, README, help docs, error messages, and code comments visible to the user.
- **No italics in UI text (v1)**. Same rationale as the human's portfolio system. Bold and weight changes are fine.
- **TDD for parsers and matchers.** Write the failing test, then the implementation. These modules are bug-prone and benefit most from this discipline.
- **Migrations forward, never down.** Alembic migrations only apply, never roll back in production. Backwards-incompatible schema changes use a multi-step migration pattern (add new column, dual-write, backfill, switch reads, drop old column over multiple releases).
- **Never delete the `migrated/` directory.** Upstream import preserves source files; they're the user's backup if something went wrong. They stay forever unless the user manually removes them.
- **Idempotent action URLs.** Re-applying the same ignore / snooze / watch is a no-op or refresh, never an error.
- **Healthcheck reflects reality.** Don't return 200 if the scheduler stopped, the DB is unwriteable, or the last check is more than 2× the interval ago.
- **Structured logging at every boundary.** Every HTTP request, every check run, every notification dispatch, every action invocation emits at least one structured log line. No string concatenation in logs; use structlog's keyword arguments.
- **Tests pass before any merge.** CI gates: ruff clean, pytest passing, coverage at or above 70%, Babel catalogues up to date.

## 8. Decisions log (alternatives considered and rejected)

Quick reference for "why didn't we do X". Useful when the agent wonders if it should reintroduce something.

| Decision | Considered alternatives | Why we chose what we did |
|---|---|---|
| Saved filters | Profiles (with user-like semantics) | One buyer, multiple sizes is the real model. "Profile" implies multi-user and drags in auth. |
| Apprise for notifications | Hand-rolled per-channel | Apprise covers 80+ services with one library, well-maintained, removes hundreds of lines of channel-specific code. |
| SQLite | Keep JSON files / use Postgres | JSON has no atomic guarantees and no querying. Postgres is operationally overkill for a single-container side project. |
| Per-filter snooze | Per-product snooze | Filter-level matches the user's notification mental model. Ignore (perm, per-product) covers the per-product case. |
| FastAPI + HTMX + Alpine | React SPA / Next.js | No JS build pipeline, no `node_modules`, single-language stack, easier to maintain solo. |
| Paste-text invoice parser | PDF upload, email forward, Gmail OAuth | Paste is 80% of the value at 5% of the complexity. Upload deferred to v2 if ever. |
| English UI only at launch | Ship Dutch too / I18n later | English-only is realistic for the maintainer. Architecture is i18n-ready so adding Dutch later is a translation PR. |
| Decoupled `store_country` and `ui_language` | Single locale field | These are independent concerns (where do I shop vs what language do I read) and combining them is the source of countless localisation bugs in other apps. |
| GitHub Container Registry | Docker Hub | Free, no separate account, ties to the repo, supports multi-arch cleanly. |
| MIT license | Anything else | Matches upstream, simplest possible. |
| Hard fork at `abbaty/uniqlo-sales-alerter` | Soft fork / branch in upstream | The headline change (saved filters) is too large to land upstream. Small fixes get PR'd back. |
| Heatmap design: deep discount count by DoW × hour | Average discount, total deals, etc. | "When are deep discounts most likely" is the actionable question. The other metrics are noisier signals of the same thing. |
| No auth in v1 | Basic auth, OAuth, SSO | LAN-only deployment behind the user's reverse proxy. Adding auth complicates the UX and the user has not asked for it. |
| Notification action URLs via HMAC | Session-based, magic-link | HMAC is stateless, no session storage needed, works from email a week later, easy to expire. |
| Multi-arch (amd64 + arm64) | amd64 only | The deployment target is a Synology NAS (ARM CPU on many models, x86 on others). Multi-arch is the only correct call. |
| Phosphor icons | Heroicons, Lucide, Material | Phosphor is open source, has consistent weights, the human has already picked it for the portfolio. |
| Noto Serif + Noto Sans | Inter alone, Fraunces, Söhne | Open source, wide language coverage (matters for future translations), same designer for both faces (good metrics match), distinct from the portfolio system. |

## 9. Open items requiring human input during the build

The agent will hit these. Don't guess; ask.

1. **The Penpot mockups (if any)**: should the agent fetch them via the Penpot MCP server, or work from the Design Brief's token and pattern specs only?
2. **The actual accent colour value**: `#C2A56D` is the Design Brief proposal but the human may have refined it in Penpot. Confirm.
3. **The Apprise URL list for the human's own use**: needed only for end-to-end manual testing. The agent should never commit these URLs to the repo.
4. **The human's specific reverse-proxy setup**: deployment docs will reference Caddy at a minimum (the human uses Caddy on their Synology). Confirm.
5. **Whether `tokens.json` source is hand-written or exported from Penpot**: affects the `design/scripts/build-tokens.py` script direction.
6. **Whether the agent should run a real check against Uniqlo's API during development**: rate limit risk. Default suggestion: use recorded fixtures from upstream's test suite, run a live check only on the human's explicit request.

## 10. Quick reference

### Project directory pattern
```
/app
├── config.yaml             (mounted, user-edited)
├── data/                   (volume-mounted)
│   ├── alerter.db          (SQLite)
│   ├── .secret             (ALERTER_SECRET if auto-generated)
│   └── migrated/           (upstream source files, never delete)
└── (read-only source)
```

### Apprise URL examples (for docs)
- Telegram: `tgram://<bot_token>/<chat_id>`
- ntfy.sh self-hosted: `ntfys://<user>:<pass>@<host>/<topic>`
- Discord webhook: `discord://<webhook_id>/<webhook_token>`
- Gotify: `gotifys://<host>/<token>`
- Email (Gmail): `mailto://<user>:<app_password>@gmail.com?to=<recipient>`

### Healthcheck checks
1. SQLite is writeable (insert + delete a row in an internal table)
2. Scheduler is running (last heartbeat within 60 seconds)
3. Last check completed within 2 × `check_interval_minutes` (if any check has run)

### Common gotchas
- Uniqlo's API rate-limits aggressively; back off on 429s
- Some country APIs (Thailand, Philippines) use v3 / different URL params; the upstream client already handles this, preserve the abstraction
- Notification dispatch must be in a background task; never block the request handler on Apprise calls
- HTMX responses need to return partial HTML, not JSON, for the elements being swapped
- Tailwind purge needs to scan Jinja templates as well as Python files for `class_="..."` patterns
- The Babel `.mo` files are compiled artefacts and should be gitignored, generated in the Docker build step
