# Uniqlo Sales Alerter (Abbaty Fork): Design Brief

**Status:** Draft v0.1
**Owner:** Abbaty
**Companion to:** PRD, Technical Specification

## 1. Brand and Voice

### What this is
A self-hosted utility that watches Uniqlo's sale catalogue against the buyer's own saved filters and notifies them when something relevant shows up. It is a personal tool, not a commercial product, and not an extension of Uniqlo's brand.

### What it is not
- A shopping app (no checkout, no cart)
- A price-comparison or affiliate tool
- An official Uniqlo anything
- A flash-sale spammer

### Voice
Calm, precise, helpful. The app speaks like a museum docent or a research librarian, not a discount aggregator. It announces facts plainly: "AIRism Cotton T-Shirt is 60 percent off in your size." It avoids urgency-inducing language ("HURRY", "LIMITED TIME") even when surfacing time-bound information.

### Anti-patterns to avoid
- Red banners and shouty discount badges
- Countdown timers, FOMO copy, "X people are viewing this"
- Animated GIFs in notifications
- Marketing fluff ("amazing deals just for you")
- Anything that could be mistaken for an official Uniqlo communication

## 2. Inspiration Directions

References to collect into Penpot before locking decisions.

### Catalogue / lookbook (drives the Deals view)
- ARKET, Toteme, COS, MUJI online product pages
- SSENSE search results layout
- Common pattern: big imagery, generous whitespace, restrained type, prices presented as facts

### Editorial / restraint (drives Insights, Help, longer-form sections)
- Are.na block layouts
- MUJI online journal
- The Browser newsletter web view
- Common pattern: type-driven, slow rhythm, single column at narrow widths

### Utility (drives Settings, Filters, system surfaces)
- Linear (early restrained palettes especially)
- Plausible Analytics
- Umami
- Cron / Notion Calendar
- Common pattern: quiet density, friendly without being playful, generous focus states

### Notification cards
- Cron's event invites
- Things 3's action sheets
- Linear's email digests

### Empty states
- Vercel's deploy-nothing-yet illustrations
- Linear's first-run welcome
- Things 3's "no projects yet"

### Filter chips and tags
- Stripe Dashboard filter pills
- Vercel's tag inputs
- Apple Photos search filter chips
- Common pattern: clear selected vs unselected state, easy multi-select, no dropdown wrapping

Target: 20 to 30 reference screenshots in `/design/inspiration/`, organised by bucket.

## 3. Design Tokens

All tokens defined in `tokens.json` using the [W3C Design Tokens Format Module](https://www.w3.org/community/design-tokens/) syntax. Generated outputs: `tokens.css` (CSS custom properties) and `tailwind.preset.js` (Tailwind config preset). Both regenerated from the JSON source on `npm run tokens` (or equivalent Python script).

### Colour palette

Source: Color Hunt palette image 3 (off-white, navy, steel blue, warm gold).

| Token | Hex | Role |
|---|---|---|
| `color.surface.canvas` | `#E8EDF2` | Page background |
| `color.surface.raised` | `#FFFFFF` | Cards, modals, raised surfaces |
| `color.surface.sunken` | `#DEE3E9` | Inputs, code blocks, sunken areas |
| `color.text.primary` | `#2C3947` | Body text, primary UI |
| `color.text.secondary` | `#547A95` | Supporting text, structural elements |
| `color.text.muted` | `#8B9AAB` | Captions, disabled, placeholders |
| `color.text.inverse` | `#FFFFFF` | On dark surfaces |
| `color.border.default` | `#CBD5DF` | Card borders, dividers |
| `color.border.strong` | `#547A95` | Active inputs, focused borders |
| `color.accent.primary` | `#C2A56D` | Discount badges, key accents (test desaturating to `#B69A66`) |
| `color.accent.primary.muted` | `#E8DDC4` | Accent backgrounds |
| `color.status.success` | `#3F8862` | Watched, in-stock, success states |
| `color.status.warning` | `#C2A56D` | Same as accent.primary, doubles as warning |
| `color.status.error` | `#A14040` | Errors, failures, removed |
| `color.status.info` | `#547A95` | Informational, same as text.secondary |

**Accessibility check required**: verify `text.primary` on `surface.canvas` and on `surface.raised` both pass WCAG 2.2 AA at 16px body size. Verify `accent.primary` on white meets at least 3:1 for non-text UI. Document any failures and shift tokens before lock.

### Typography

**Display and headings:** Noto Serif, weights 400, 500, 700
**Body and UI:** Noto Sans, weights 400, 500, 600
**Monospace (codes, SKUs, technical):** Noto Sans Mono, weight 400

Both are Google Noto family. SIL Open Font License. Wide language coverage (matters for future Dutch, Arabic).

Alternative to test in Penpot: Newsreader (Production Type, SIL OFL) for display. More character at large sizes, optical-size axis. Use Noto Sans for body.

### Type scale

| Token | Size / line-height | Family / weight | Use |
|---|---|---|---|
| `type.display` | 32 / 40 | Serif 500 | Hero copy, empty states |
| `type.h1` | 24 / 32 | Serif 500 | Page titles |
| `type.h2` | 20 / 28 | Serif 500 | Section titles |
| `type.h3` | 18 / 24 | Sans 600 | Card titles, subsections |
| `type.body` | 16 / 24 | Sans 400 | Body text, default |
| `type.body.strong` | 16 / 24 | Sans 600 | Emphasis in body |
| `type.small` | 14 / 20 | Sans 400 | Secondary text |
| `type.caption` | 12 / 16 | Sans 500 | Labels, badges, metadata |
| `type.mono` | 14 / 20 | Mono 400 | Codes, IDs |

Letter-spacing: -0.01em on display and h1, otherwise 0. No italics in v1 (matches portfolio system rule).

### Spacing scale

Base unit: 4px. Scale: 4, 8, 12, 16, 24, 32, 48, 64, 96.

Tokens: `space.1` (4) through `space.96` (96). Vertical rhythm aligns to 8px grid for body text, 4px for tight elements.

### Radius

`radius.xs` 4, `radius.sm` 8, `radius.md` 12, `radius.lg` 16, `radius.full` 9999.

Default for cards: `md`. Inputs and buttons: `sm`. Pills and chips: `full`.

### Shadow

Three levels, all warm-tinted to match the off-white canvas:

- `shadow.sm`: `0 1px 2px rgba(44, 57, 71, 0.06)`
- `shadow.md`: `0 4px 12px rgba(44, 57, 71, 0.08)`
- `shadow.lg`: `0 12px 32px rgba(44, 57, 71, 0.12)`

Cards use `sm` resting, `md` on hover. Modals use `lg`.

### Motion

Durations: `motion.fast` 120ms, `motion.base` 200ms, `motion.slow` 320ms.
Easing: `motion.ease.out` `cubic-bezier(0.16, 1, 0.3, 1)`, `motion.ease.inout` `cubic-bezier(0.65, 0, 0.35, 1)`.

Respect `prefers-reduced-motion: reduce`. When reduced, replace transitions with instant changes; never replace with longer fades.

### Iconography

[Phosphor Icons](https://phosphoricons.com/), regular weight by default. Bold for filled states (e.g. a snoozed filter card uses a bold filled `moon` icon).

Sizes: 16, 20, 24px. 20 is the default. Pair every icon with text or `aria-label`; no icon-only buttons without an accessible name.

## 4. Information Architecture

### Sitemap

```
/                          Deals (default landing)
/filters                   Saved filters list
/filters/new               Create filter wizard
/filters/:id               Filter detail / edit
/inbox                     Notification history
/inbox/snoozed             Snoozed filters
/inbox/ignored             Ignored products and keywords
/insights                  Heatmap and stats
/settings                  Country, language, schedule, channels, server URL
/help                      Diataxis index
/help/tutorials/*          Step-by-step learning
/help/how-to/*             Task-oriented
/help/reference/*          Schema, API, size taxonomy
/help/explanation/*        How matching works, how heatmap works
/api/v1/*                  REST API
/actions/*                 Signed notification action handlers
/health                    Healthcheck
```

### Top navigation

Mobile: bottom tab bar with five tabs (Deals, Filters, Inbox, Insights, More). "More" opens a sheet with Settings and Help.

Desktop: left sidebar, same five top-level items plus Settings and Help below a divider.

### Page-level structure

- Sticky header: page title, single primary action (e.g. "Add filter")
- Body: scrollable content
- Footer (status pill): "Last check: 12 minutes ago. 3 filters active. 1 snoozed."

## 5. Component Inventory

Components to design in Penpot and implement as Jinja2 partials or HTMX-friendly elements:

- **Button**: primary, secondary, ghost, destructive. Sizes sm / md / lg. States default, hover, focus, disabled, loading.
- **Chip**: filter chip with selected / unselected. Removable variant (with x icon). Pill shape, `radius.full`.
- **Card**: deal card (image, prices, discount badge, matched-filter tags, size chips with direct buy links). Filter card (name, active state, snooze state). Stat card.
- **Input**: text, number, select, textarea. Always paired with label and optional helper text.
- **Toggle**: switch with label. Used for enabled / disabled, filter on / off.
- **Modal**: small confirmation prompts (delete filter, clear ignores).
- **Drawer**: settings panels on mobile, slide-up sheet for actions.
- **Empty state**: large illustration or icon, headline, body copy, primary CTA, optional secondary CTA.
- **Toast**: confirmation after async actions ("Filter saved", "Snoozed for 7 days").
- **Badge**: discount percentage, "Watched", "Snoozed", filter name tag.
- **Heatmap cell**: square tile, opacity proportional to value, hover reveals tooltip.
- **Tooltip**: hover or focus reveal, no auto-dismiss on hover.
- **Status pill**: small inline indicator (e.g. "Snoozed until Friday", "Last check OK").
- **Breadcrumb**: simple text with chevron separator, for deep pages only.

## 6. Patterns

### First-run empty state

The first thing a user sees after deployment, before any filter exists. Single screen, mobile-first.

Layout:
1. Logo lock-up (small, top)
2. Display-size headline: "Watch Uniqlo sales in your sizes"
3. Body: one sentence explaining the saved-filter concept
4. Two prominent CTAs:
   - Primary: "Add my first filter" → opens wizard
   - Secondary: "Paste a recent invoice" → opens paste textarea
5. Below the fold: tiny help link, version pill

The paste-invoice path is positioned as the fast lane. The wizard path is the orthodox path.

### Add Filter Wizard

Three steps, each its own screen. Progress indicator shows 1 of 3, 2 of 3, 3 of 3.

1. **Name your filter** (text input + a row of suggested names from common patterns like "Me tops", "Kid 5y")
2. **Pick gender and sizes** (chip groups, with "paste invoice" inline button to add sizes from text)
3. **Set discount and availability** (discount chip group: 30%, 50%, 70%, custom; availability chip group: Online / In-store / Both, default Both) and review

A "Save and add another" button on the final screen for users who want to add several filters in one session.

The availability chip group is rendered as three mutually-exclusive chips. A small inline help link explains the in-store option: "In-store items are not shippable. Useful if you regularly visit a Uniqlo."

### Deals view

Default landing. Sectioned by saved filter (filters with current matches shown first). Each section:

- Filter name + match count badge + filter-level snooze button
- Horizontal scroll on mobile, grid on desktop
- Deal cards with image, prices, discount badge, matched size chips that link directly to in-stock variants

Top of page: filter chips for active filter names; tapping a chip scrolls to that section.

If no filters match anything today, the empty state appears with the same paste-invoice shortcut as first-run.

### Notification card (rendered in email and Apprise targets that support HTML)

Vertical card layout:

- Hero product image (with `loading=lazy`)
- Product name (Serif h3)
- Price line: strikethrough original, sale price in accent colour, discount percentage badge
- Colour name in small caps
- Matched sizes as chip row, each linking to its in-stock variant URL
- Filter tag row: which saved filter(s) triggered this
- Action buttons row at bottom: Ignore, Snooze 1d, Snooze 7d, Snooze 30d, Watch (or Unwatch), Open settings

If `server_url` is not set, action buttons are replaced with a one-line note: "Set server_url in settings to enable action buttons."

### Snooze interaction

In the UI:
- Each filter card has a "Snooze" button. Tapping opens a small popover with the four duration options plus "Custom date" and "Until I resume".
- Snoozed filters render in muted style and show "Snoozed until [date]. Resume now" inline.

In notifications:
- Snooze buttons in the action row apply to the filter(s) that matched the deal. If multiple filters matched, the user is asked to confirm which one to snooze (or "all matched filters").

### Heatmap

7 rows × 24 columns grid. Days down the left, hours across the top. Each cell is a square with opacity scaled to its count relative to the grid max.

Hover (or tap on mobile) reveals a tooltip: "Sundays 14:00, 12 deep discounts observed in the last 90 days".

Below the grid: a small legend ("Light = fewer drops, Dark = more drops") and a control to toggle the deep-discount threshold (30 / 50 / 70).

### Loading and skeleton states

Use shimmer-free, opacity-based skeleton placeholders for cards. Animation is a subtle pulse at `motion.slow` duration. Disabled if reduced-motion is preferred.

### Error states

- Uniqlo API unreachable: yellow banner at top of page: "Uniqlo's catalogue is unreachable. Last successful check: 23 minutes ago. Will retry automatically."
- Notification dispatch failure: red dot indicator on the Inbox tab, full details in the notification log view
- Filter save validation failure: inline messages next to the offending field

## 7. Accessibility

Target: WCAG 2.2 AA.

Non-negotiable:
- Visible focus rings on all interactive elements (2px outline in `color.border.strong`, offset 2px)
- Keyboard navigation works for every flow
- All icons paired with text or `aria-label`
- Form fields labelled, not placeholder-as-label
- Contrast verified for all token combinations
- Reduced-motion respected
- Touch targets minimum 44 × 44 px

Aspirational (best-effort, not gating):
- Screen reader pass through all major flows
- Live regions for async updates (notification arrived, snooze applied)

## 8. Penpot Workflow

### Files in `/design`

```
design/
├── README.md                    Open-in-Penpot instructions
├── inspiration/                 Reference screenshots, organised by bucket
├── tokens/
│   ├── tokens.json              Source of truth (W3C DTFM)
│   ├── tokens.css               Generated CSS custom properties
│   └── tailwind.preset.js       Generated Tailwind preset
├── flows/                       User flow diagrams (Penpot)
├── wireframes/                  Lo-fi layout (Penpot)
├── mockups/                     Hi-fi screens (Penpot)
└── exports/                     PNG previews for README and docs
```

### Token sync

`tokens.json` is the source of truth. A small script (`design/scripts/build-tokens.{py,sh}`) regenerates `tokens.css` and `tailwind.preset.js`. Run on every token change.

Penpot consumes `tokens.json` directly. The web app consumes `tokens.css` and the Tailwind preset. Both stay in sync because both derive from the same JSON.

### Penpot MCP usage

During implementation, the Penpot MCP server is used to:
- Fetch the latest mockup of a screen as PNG (to verify implementation matches)
- Pull component specs (sizes, spacing, colour assignments) when wiring up Tailwind classes
- Optionally programmatically create or update frames

Setup is not blocking: if Penpot MCP isn't available, mockups are referenced as PNGs from `/design/exports/`.

### Contributor workflow

Documented in `/design/README.md`:

1. Open the relevant `.penpot` file in [Penpot](https://penpot.app/) (hosted or self-hosted)
2. Make changes; export updated PNGs to `/design/exports/`
3. If tokens change, regenerate `tokens.css` and the Tailwind preset
4. Open a PR with both the Penpot file changes and the regenerated outputs

## 9. Main README Design Section

The main repo README will include a "Design" section with:

- A short description of the design system (palette, type, principles)
- 2 to 3 screenshot exports of key screens (Deals empty state, filter wizard, heatmap)
- A link to `/design` with a one-line "How to contribute to the design"

Purpose: someone discovering the fork on GitHub can immediately see the design quality and find the design files if they want to contribute.

## 10. Open Items Before Lock

1. Final accent colour (test `#C2A56D` vs slightly desaturated `#B69A66` vs `#A99063` in mockups)
2. Final display type choice (Noto Serif vs Newsreader vs both, test at h1 and display sizes)
3. Specific empty-state illustration style (geometric / line / abstract / none-and-just-type)
4. Logo / wordmark (does the fork get its own mark or stick with text-only?)
5. Exact icon weight per state (regular default, bold for active / filled, confirm in mockups)
