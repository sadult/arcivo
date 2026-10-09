# Design system

Tokens live in `src/arcivo/gui/theme/tokens.py` (single source of truth); the Qt stylesheet is generated from
them in `theme/style.py`. Screenshots: [`images/screenshots/`](images/screenshots/).

## Brand

| Token | Value | Use |
|---|---|---|
| Primary | `#7C83FD` | accent, focus, selection, charts (dark) |
| Primary deep | `#5B5FEF` | accent on light theme, pressed states, logo gradient |
| Secondary | `#36C2B4` | logo dot, success-adjacent highlights, second chart series |
| Ink | `#0B0D12` | dark background, logo on light |

**Logo:** a bookmark (saved item) resting on stacked archive layers, with a teal "synced" dot, on a rounded-square
violet gradient. Files: `src/arcivo/assets/brand/` (SVG master `arcivo-mark.svg`, monochrome, wordmarks, PNG 16–1024,
`arcivo.ico`, installer bitmaps). Regenerate with `python scripts/make_brand.py`. Arcivo never uses the Telegram
logo or paper-plane motif.

## Visual language

Arcivo follows Apple's Human Interface Guidelines for macOS: a quiet sidebar, large page titles, grouped content
on rounded *inset* surfaces, system colours and restrained use of the accent colour. Windows title bars are
tinted to match (DWM dark mode / caption colours).

## Colour roles

| Role | Light | Dark |
|---|---|---|
| `bg` / `sidebar` | `#F5F5F7` / `#EAEAEF` | `#1C1C1E` / `#252527` |
| `surface` / `elevated` | `#FFFFFF` / `#FFFFFF` | `#2A2A2C` / `#323234` |
| `border` / `border_strong` | `#E5E5EA` / `#D1D1D6` | `#3A3A3C` / `#4A4A4D` |
| `text` / `muted` / `subtle` | `#1D1D1F` / `#6E6E73` / `#8E8E93` | `#F5F5F7` / `#A1A1A6` / `#7C7C82` |
| `accent` (system indigo) | `#5856D6` | `#5E5CE6` |
| `success` / `warning` / `danger` / `info` | `#28A745` / `#E08600` / `#FF3B30` / `#007AFF` | `#30D158` / `#FF9F0A` / `#FF453A` / `#0A84FF` |

Charts, message types and storage categories use Apple system colours (`SYSTEM`, `CHART`, `TYPE_COLORS`,
`CATEGORY_COLORS`) so a type looks the same in tables, charts and the media grid.

## Typography

- **Inter** (bundled, SIL OFL), falling back to SF Pro / Segoe UI Variable / Segoe UI.
- Scale (px): caption 11 · footnote 12 · body 13 · title3 15 · title2 17 · title1 22 · large title 26.
  The text-size setting scales everything (90–130 %).

## Spacing, radius, motion

- Spacing: 2 · 4 · 8 · 12 · 16 · 20 · 28 · 40. Page margins 32/26.
- Radius: 4 · 6 (controls) · 8 · 12 (tiles, inset lists) · 16 (sheets) · pill.
- Motion: 120 / 180 / 260 ms. *Settings → Appearance → Animations* turns motion off.

## Components

| Component | Notes |
|---|---|
| Sidebar | brand, sections (Overview, Library, Insights, Tasks, System) with 16 px accent icons; footer with account, sync status, sync button and jobs indicator; collapsible (Ctrl+B) |
| Page header | large title; search fields live on the pages themselves (Ctrl+F focuses them) |
| Stat tile | glyph, value, label – widget-style tile |
| Inset list | grouped rows with separators (Overview content, About credits, Settings) |
| Welcome sheet | first-run introduction; can be shown again from *Settings → Privacy* |
| Message table | virtualised model, checkbox column, type icon + colour, sortable, row height 32 |
| Bulk bar | appears with a selection: count, "select all N matching", Tag / Flag / Export / Delete |
| Detail panel | preview, metadata, tags (drop target), private note, actions |
| Chips | tags and filters; tinted background, coloured text |
| Buttons | `primary`, default (outlined), `ghost`, `danger`; icon 16 px |
| Charts | Qt Charts – area (timeline), bars, donut; no axis lines, light grid; palette `CHART`; hover tooltips; click drills into Explorer |
| Empty states | icon, title, one-line explanation, primary action |
| Toasts | bottom-right, auto-dismiss, optional action (Undo / Open) |
| Dialogs | destructive dialogs list consequences, show counts and sizes, ask the user to type the number of messages to confirm (two-step, configurable) |

## Icons

[Lucide](https://lucide.dev) (ISC), stroke 2, recoloured at runtime from SVG (`assets/icons/`). Sizes 14 / 16 / 20.
