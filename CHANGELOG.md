# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org).

## [Unreleased]

## [0.2.1] – 2026-10-08

### Added
- **Console home screen**: `Arcivo.exe` / `arcivo` without arguments opens an arrow-key menu (sign in, open
  dashboard, check connection, sync, account & storage, proxy settings, sign out, about).
- **`arcivo doctor`**: step-by-step connection diagnostics (credentials, proxy, data-center reachability, MTProto,
  session) with hints for filtered networks.
- **Proxy support**: SOCKS5, HTTP and MTProto (paste a `t.me/proxy` link) in *Settings → Network* and `arcivo proxy`.
- **Welcome sheet** on first launch of the dashboard; can be reopened from *Settings → Privacy*.
- New **About** page with developer info (Bitologist, Telegram @Bitologist), links and copyable diagnostics.

### Changed
- **Python 3.14 is now the minimum version** (PySide6 6.10+, PyInstaller 6.16+). `build.bat` for one-click builds;
  `build.ps1` finds Inno Setup via PATH, registry and Program Files (`-Iscc` to override).
- **macOS-style redesign**: Apple system colours, new sidebar with account/sync footer, large titles, widget tiles,
  inset lists, cleaner charts and tables; top bar and status bar removed.
- Two executables: `Arcivo.exe` (console) and `ArcivoDashboard.exe` (desktop app); installer shortcuts updated.
- Repository moved to `github.com/sadult/arcivo`; author Bitologist.

### Fixed
- Taskbar showed the Python icon instead of the Arcivo icon (AppUserModelID + native window icon); title bars
  now follow the app theme.

### Removed
- Persian translation, RTL layout, Jalali calendar and the Vazirmatn font.

## [1.0.0] – 2026-10-08

First public release.

### Added
- **Sign-in** from the CLI (`arcivo login`) or the desktop wizard: your own API ID/hash, phone number, login code
  and two-step-verification password. Sessions are stored in Windows Credential Manager / DPAPI.
- **Sync engine**: resumable initial indexing, fast incremental sync that re-checks recent messages for edits and
  deletions, FLOOD_WAIT-aware back-off, live progress.
- **Local index** in SQLite (WAL) with FTS5 full-text search, versioned migrations with automatic backups.
- **Search language**: `type:`, `ext:`, `size:`, `duration:`, `date:/after:/before:`, `sender:`, `chat:`,
  `domain:`, `tag:`, `has:`, `is:`, negation, `OR`, sorting – shared by GUI and CLI.
- **Desktop app** (PySide6): dashboard, explorer with bulk selection, search with syntax help, media grid,
  statistics, storage analyzer, duplicate finder, export center, jobs, smart collections, tags, account, sync
  center, settings (incl. shortcut editor), logs and about pages; dark/light themes; English and Persian (RTL,
  Persian digits, Jalali dates); command palette and keyboard shortcuts.
- **Export** to JSON, JSON Lines, CSV, plain text, HTML report and Markdown, with optional media download,
  folder/file-name templates, resume, and an optional post-export delete step with review.
- **Safe deletion** of Saved Messages with review list, typed confirmation, batch throttling, report and audit log.
- **Organisation**: local tags (drag & drop), flags, private notes, smart collections, undo.
- **CLI** covering login, status, sync, search, export, delete, stats, storage, tags, collections, db, cache,
  config and logs; `--demo` mode with synthetic data.
- **Windows packaging**: PyInstaller one-folder build (`Arcivo.exe` + console CLI), per-user Inno Setup
  installer, portable ZIP, GitHub Actions CI and release workflows.

[Unreleased]: https://github.com/sadult/arcivo/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/sadult/arcivo/releases/tag/v1.0.0
