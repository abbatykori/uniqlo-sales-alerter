# Uniqlo Sales Alerter (Abbaty Fork): Product Requirements

**Status:** Draft v0.1
**Owner:** Abbaty
**Upstream:** [kequach/uniqlo-sales-alerter](https://github.com/kequach/uniqlo-sales-alerter)

## 1. Context

The original Uniqlo Sales Alerter polls Uniqlo's Commerce API on a schedule, applies a single global filter set (gender, sizes, minimum discount), verifies real-time stock, and dispatches notifications via Telegram or email. The forks (Code0987, ostyq, jabescript) layered on Docker convenience, env-var bootstrapping, a settings web UI, ignored products, watched variants, quiet hours, and per-variant low-stock controls.

The remaining gap, and the reason for this fork: the buyer in a household typically shops for more than one person across more than one size system at once (e.g. men's XXL tops, men's XL trousers in inches, kids' 116cm). A single global filter cannot express this. Everyone has tried to work around it by stuffing every size into one filter list and getting noisy results.

This fork's purpose is to make multi-size, multi-person tracking first-class while keeping the project self-hostable and well-tested.

## 2. Goals and Non-Goals

### v1 Goals

1. Replace the single global filter with named, independent **saved filters**.
2. Externalise all notification channels behind Apprise (one URL list, ~80 supported services).
3. Add **snooze per saved filter** (1d / 7d / 30d / custom / forever-until-resumed).
4. Add **size extraction from pasted invoice/order text** as an onboarding accelerator.
5. Add a **deal heatmap** (day-of-week × hour-of-day, weighted by deep-discount count).
6. Add **notification action buttons** (ignore, snooze, watch, unwatch).
7. Ship a **mobile-first web UI** with empty-state-first onboarding, no dark mode.
8. Externalise all UI copy via i18n; ship English; structure for future translations.
9. Decouple **store country** from **UI language** as two independent settings.
10. Carry forward jabescript's good ideas: ignored products, ignored keywords, watched variants, quiet hours, scheduled checks, low-stock suppression.
11. Increase **unit test coverage** to 70 percent line coverage minimum, including a regression test for the reported trouser-waist bug.
12. Ship as a multi-arch Docker image on GitHub Container Registry with a Portainer-friendly compose template.

### v1 Non-Goals (Deferred to v2 or Later)

- Price history tracking and target-price wishlist mode
- Home Assistant integration (webhook / MQTT)
- Progressive Web App install support
- Email-forward size import (the paste flow covers this 80/20)
- Per-filter notification channel routing
- Additional language packs beyond English
- Authentication (LAN-only deployment behind a reverse proxy)

## 3. Mental Model

**One buyer, many filters.** The household has one person doing the buying and receiving notifications. That buyer maintains a set of named saved filters that each describe a "kind of thing I'm watching for". Examples:

- "Me tops" → men, XXL, ≥40% off
- "Me bottoms" → men, 34inch, ≥30% off
- "Kid 5y" → kids, 116cm, ≥50% off
- "Spouse" → women, M, ≥40% off

A deal matches if any saved filter matches. Notifications tag which filter(s) triggered, so the buyer can immediately tell why something showed up.

This abstraction does not require a multi-user system, accounts, or auth. Filters are a saved query, nothing more.

## 4. Features

### 4.1 Saved Filters (Headline)

Each saved filter has:

- `name` (required, unique)
- `gender` (multi-select from men / women / unisex / kids / baby)
- `min_discount` (percentage)
- `sizes_clothing`, `sizes_pants`, `sizes_shoes`, `one_size_match` (size lists, identical taxonomy to upstream)
- `availability_mode` (one of `online`, `in_store`, `both`; default `both`)
- `ignored_keywords` (filter-specific, in addition to global ignored keywords)
- `enabled` (toggle)
- `snooze_until` (timestamp, nullable)

A product matches a filter if it satisfies gender + min_discount + at least one in-stock size from any of the configured size lists + the availability_mode constraint, and none of the filter's ignored keywords appear in its name. Global ignored keywords and ignored products also apply.

**Availability semantics.** Uniqlo flags catalogue items by channel. Some products are online-only, some are store-only (typically physical-clearance items that may not appear in the online sale feed at all), most are available through both channels. The `availability_mode` filter:

- `online`: include only items available online (default for users who never visit a physical store)
- `in_store`: include only items flagged as in-store-only, useful for a buyer who is willing to visit their nearest Uniqlo
- `both`: include items available through either channel (recommended default)

When a deal matches via in-store availability, the notification labels it as "In store only" so the buyer knows it isn't shippable. Specific store-stock checking (e.g. "is this in the Amsterdam Kalverstraat store?") is **not** in v1 scope; the filter only distinguishes the channel, not the specific store.

A v1 prerequisite is verifying which fields in Uniqlo's Commerce API reliably expose the channel flag. If the flag is unreliable in certain country APIs, `availability_mode = in_store` falls back to `both` for that country with a logged warning.

A deal is notified if at least one enabled, non-snoozed filter matches it.

### 4.2 Size Extraction from Pasted Invoice Text

A textarea on the empty-state onboarding screen and inside the "add filter" flow accepts pasted text from a Uniqlo invoice email or PDF (copy-paste, not file upload).

Parser:

- Regex-matches lines of the form `<COLOR>, <SIZE>` immediately following a product code line (`<digits>, <product name>`)
- Recognises clothing sizes (XXS through 3XL), pants sizes (inches), shoe sizes (numeric, half sizes), kids sizes (`<age> Years (<cm>cm)`, `<cm>cm` alone)
- Deduplicates extracted sizes
- Categorises into clothing / pants / shoes / kids
- Presents as suggested chips the user can accept into the active filter

Failure case: shows the raw extracted lines so the user can pick manually if categorisation gets it wrong.

### 4.3 Notifications via Apprise

All notifications dispatched through [Apprise](https://github.com/caronc/apprise). Configuration is a list of Apprise URLs:

```yaml
notifications:
  apprise_urls:
    - "tgram://<bot_token>/<chat_id>"
    - "mailto://user:pass@smtp.gmail.com?to=user@gmail.com"
    - "ntfys://ntfy.example.com/uniqlo-alerts"
```

Two behavioural toggles replace the upstream three-mode trichotomy:

- `send_digest_on_first_run` (boolean, default true): on first run after start, send everything currently matched
- `notify_only_on_changes` (boolean, default true): after the first run, only notify on changes (new product, new size, new colour, discount change)

When both are true: behaves like upstream `all_then_new`.
When first is false, second is true: behaves like `new_deals`.
When second is false: behaves like `every_check`.

Per-filter channel routing is v2.

### 4.4 Notification Action Buttons

Each notification (HTML email, Telegram caption, Apprise variants that support links) includes deep-link buttons:

- **Ignore product** (permanent, adds to `ignored_products`)
- **Snooze filter for 1d / 7d / 30d** (sets `snooze_until` on the matched filter)
- **Watch this variant** (adds to `watched_variants`)
- **Unwatch** (only shown for variants already in `watched_variants`)
- **Open Settings**

Buttons are signed action URLs (HMAC). Server must have `server_url` set in config or buttons are omitted from notifications with a small explanatory note.

### 4.5 Snooze

Snooze sets a `snooze_until` timestamp on a saved filter. While snoozed, the filter is not evaluated and contributes nothing to notifications.

Durations exposed in UI and notification buttons: 1 day, 7 days, 30 days, custom (date picker), forever-until-resumed (no timestamp).

Resuming clears `snooze_until` immediately.

Snoozed filters appear in the Filters list with a muted card style and a clear "Resume now" button. The Inbox/Insights views show a footer pill listing currently snoozed filters.

### 4.6 Watched Variants

A specific `product_id` + `color_code` + `size_code` combination tracked regardless of sale status. Notified on any meaningful change (back in stock, new colour, new size, price change).

Adding a watched variant accepts a full Uniqlo product URL with `colorDisplayCode` and `sizeDisplayCode` query params, or the v3-style `colorCode` and `sizeCode` (for Thailand / Philippines).

Watched variants bypass all filters (they always notify) but respect global snoozes if a `watched_filter` is implicitly created.

### 4.7 Ignored Products and Keywords

Two distinct lists:

- **Ignored products**: by `product_id`. Permanent. Product is hidden from all results.
- **Ignored keywords**: case-insensitive substring match against product name. Permanent. Two scopes: global (apply everywhere) and per-filter (apply only to that filter).

Watched variants override ignores: a watched variant always notifies even if its product is ignored.

### 4.8 Quiet Hours and Scheduled Checks

Inherited from jabescript:

- `quiet_hours.enabled`, `start`, `end` (HH:MM, may cross midnight). During quiet hours, periodic checks and notifications pause; the scheduler resumes outside quiet hours.
- `scheduled_checks`: list of `HH:MM` strings. Fixed daily check times that ignore quiet hours.

Both can coexist with `check_interval_minutes`.

### 4.9 Heatmap (Insights)

A 7 × 24 grid:

- Rows: day of week (Mon at top)
- Columns: hour of day (00 to 23)
- Cell value: count of deep-discount deals first observed during that window over a configurable lookback (default 90 days)
- "Deep discount" threshold configurable (default 50 percent)

Cell opacity scales to the max value in the grid. Hover reveals exact counts and example products.

Purpose: show the user when historically Uniqlo has dropped good discounts so they can intuit when to expect future drops, and so the scheduler can be tuned.

Data accumulates from when the fork is installed. The heatmap shows "not enough data yet" with a progress indicator until at least 14 days of observations exist.

### 4.10 Web UI

Mobile-first. No dark mode in v1.

#### IA

- **Deals**: default landing. Current matched deals grouped by filter.
- **Filters**: list view, then detail per filter. Includes add/edit/snooze/duplicate/delete.
- **Inbox**: notification history, snoozed filters, ignored products and keywords as tabbed sub-views.
- **Insights**: heatmap and basic stats (checks today, deals seen this week, average discount).
- **Settings**: country, language, schedule, quiet hours, Apprise URLs, server URL, low-stock threshold.
- **Help**: Diataxis-organised (tutorials, how-to, reference, explanation).

#### Empty States (Each Section)

- First run: "Add your first saved filter to start tracking" + wizard CTA + paste-invoice shortcut
- Filters with no entries: as above
- Deals with no matches today: "Nothing matched today. Try adjusting a filter or paste a recent invoice to discover sizes."
- Inbox empty: "Notifications will appear here once a check runs"
- Snoozed empty: "Nothing snoozed. Snooze a filter to take a break from its notifications."
- Insights with insufficient data: "Heatmap will activate after 14 days of observations. Currently: N days."

#### Filter Chips

Sizes, genders, snooze durations rendered as toggleable chips, not nested checkboxes or dropdowns. The active state and disabled state are visually distinct.

### 4.11 Migration from Upstream

On first startup the app detects an upstream-style `config.yaml` and `.seen_variants.json` in the same directory or known paths. If found:

1. Parse `config.yaml` filter section into a single saved filter named "Imported"
2. Import `watched_urls` or `watched_variants` (jabescript format) into the new table
3. Import `ignored_products` and `ignored_keywords` if present
4. Import `.seen_variants.json` contents into the `seen_variants` table
5. Move old files to `migrated/` with a timestamp suffix
6. Write a migration marker so this only runs once

The migration is logged. If it fails partway, it rolls back cleanly and the app starts empty.

### 4.12 Country and Language Separation

`config.store_country` (e.g. `nl/nl`) and `config.ui_language` (e.g. `en`) are two unrelated fields. The default for both is set independently. Store country drives which Uniqlo API to call; UI language drives which translation catalogue to load.

v1 ships translation catalogues for `en` only. The codebase loads any `<lang>` catalogue from `locale/<lang>/LC_MESSAGES/messages.po` if present, so adding Dutch later is a translation PR with no code changes.

## 5. v1 Scope Summary

A user can:

1. On first run, see an empty-state screen with two paths: "Add a filter manually" or "Paste an invoice to extract sizes"
2. Paste a Uniqlo invoice and have sizes suggested as chips, with one-click acceptance into a new filter
3. Create, edit, enable/disable, snooze, and delete saved filters, each with gender, sizes, discount threshold, ignored keywords, and availability mode (online / in-store / both)
4. Configure Apprise URLs for notifications via the UI
5. Receive notifications matching any active filter, with action buttons that work
6. Snooze a filter from a notification button (1d / 7d / 30d) or from the filter list
7. Maintain a global ignore list (products and keywords) and per-filter keyword ignores
8. View a deal heatmap once 14+ days of observations exist
9. Migrate from upstream config on first start without losing prior history
10. Run on Synology + Portainer via a compose template, autoreloading config when changed via UI

## 6. Success Criteria

- All features above implemented and tested
- 70 percent unit test line coverage minimum
- Reported trouser-waist bug reproduced, fixed, and covered by a regression test
- Multi-arch (amd64, arm64) Docker image published to ghcr.io with semver and `latest` tags
- Portainer stack template lets a fresh user deploy in under 5 minutes from a clean Synology
- All UI strings live in `messages.po`, no hardcoded user-facing text in templates or Python
- Configuration changes via UI take effect without a container restart
- Healthcheck endpoint reflects real health (scheduler running, DB writeable, last check within 2× interval)

## 7. Open / TBD

- Final accent colour and any palette tweaks confirmed in Penpot
- Repo location confirmed (`abbaty/uniqlo-sales-alerter`)
- Final Apprise URL examples for the docs (Telegram, ntfy, Discord, Gotify, email)
- Verify which fields in Uniqlo's Commerce API expose the channel flag (online vs in-store) per country, and document fallback behaviour where the flag is unreliable

## 8. Notes on Upstream Contribution

Where this fork's changes are generally useful (trouser-waist bug fix, increased test coverage, possibly the Apprise refactor if jabescript wants it), open PRs upstream. The headline differentiator (saved filters) probably won't be upstreamed because it's a substantial restructure; the smaller wins should be.

Attribution stays in the fork README and a NOTICE file. License remains MIT.
