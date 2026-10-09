# UI information architecture

```
Arcivo
├── Library
│   ├── Dashboard ........ greeting + archive summary, stat cards, activity chart, type donut, recent, largest, pinned collections
│   ├── Explorer ......... type tabs, query bar, filter panel, message table, bulk bar, detail panel
│   ├── Search ........... query builder with examples + syntax help, results table, "save as collection"
│   ├── Media ............ grid of thumbnails (photos, videos, GIFs, music, voice, files, stickers), preview panel
│   ├── Smart collections  list of saved queries with live counts → results browser, edit/export/delete
│   └── Tags ............. tag manager (colour, description, counts) → tagged messages
├── Insights
│   ├── Statistics ....... range (30 d / 90 d / 12 mo / all) × bucket; timeline, types, categories, hours, weekdays, heatmap, sizes, top senders/sources/domains
│   └── Storage .......... totals by category, largest file types, tabs: Large files · By extension · Duplicates
├── Operations
│   ├── Export center .... source (selection / query / everything), formats, media types, templates, preview, recent exports
│   ├── Jobs ............. active + history; pause / resume / cancel / retry; open report / folder
│   └── Sync center ...... status cards, modes (incremental / initial-resume / full re-scan), live log, schedule
└── System
    ├── Account .......... profile, connection (DC, latency, layer), session & security, local data, recent operations, log out
    ├── Settings ......... Appearance · Sync · Performance · Export defaults · Notifications · Privacy · Shortcuts · Storage & database · Advanced
    ├── Logs ............. level filter, search, copy/export (redacted)
    └── About ............ version/build, unofficial-client notice, licenses & credits, links
```

## Primary flows

1. **First run** → Welcome (what Arcivo is, Telegram API notice) → API keys → phone → code → (2FA) → initial sync
   starts automatically with progress on the Dashboard → Dashboard fills in.
2. **Find & act** → type in the global search (or Ctrl+K) → Explorer with the query → refine with filter panel →
   select (click, Shift-range, "select all matching") → Tag / Flag / Export / Delete from the bulk bar.
3. **Free up space** → Storage → Duplicates (pick method) → "Select extra copies" (keep oldest/newest) → Review &
   delete → typed confirmation → delete job with report.
4. **Export then clean up** → Export center → choose source + formats + media → Start → when the job finishes,
   optional *Delete exported messages* prompt (only for verified exports) → review → confirm.
5. **Collections** → any query → "Save as collection" → appears on Dashboard (pinned) and in the sidebar page.

## Navigation conventions

- Every chart element, stat card and list row is clickable and opens Explorer with the equivalent query, so the
  user can always see (and act on) the messages behind a number.
- Selection is global (shared by Explorer, Search, Media, Collections) and survives navigation; changing filters
  asks whether to keep or clear the selection (configurable).
- Destructive actions are never one click: review dialog → typed confirmation → job with report.
- Shortcuts: Ctrl+1…9 pages, Ctrl+K palette, Ctrl+F search, Ctrl+R sync, Ctrl+E export, Ctrl+T tag, Ctrl+D flag,
  Del delete, Ctrl+I details, Ctrl+B sidebar, Ctrl+Shift+L theme, F1 search help (all editable).
