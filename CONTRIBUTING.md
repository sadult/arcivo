# Contributing to Arcivo

Thanks for helping! Arcivo is a small, privacy-focused project, so a few rules matter more than usual.

## Ground rules

1. **Never commit personal data.** No real `.session` files, API IDs/hashes, phone numbers, exported messages or
   screenshots of real accounts. Use `arcivo --demo` / `arcivo gui --demo` (synthetic data) for bug reports and
   screenshots.
2. **Respect the [Telegram API Terms of Service](https://core.telegram.org/api/terms).** Features must act only on the
   user's own Saved Messages and only after explicit user action. No scraping of other chats, no bulk automation
   of other accounts, no use of data for AI/ML training, no spam.
3. **Destructive actions need a review step and explicit confirmation.** Anything that changes data on Telegram
   goes through the job system with a dry-run/report and is written to the audit log.
4. Be kind – see the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

```bash
git clone https://github.com/sadult/arcivo && cd arcivo
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
arcivo gui --demo                                   # run the app with demo data
pytest                                              # unit + integration tests (GUI tests need a display or:)
QT_QPA_PLATFORM=offscreen pytest -m gui             # headless GUI smoke tests
ruff check src tests scripts
```

Useful scripts:

| Script | Purpose |
|---|---|
| `scripts/screenshots.py` | Regenerate `docs/images/screenshots/*` from demo data |
| `scripts/make_brand.py` / `scripts/make_cover.py` | Regenerate logo, icons, installer bitmaps, README cover |
| `scripts/generate_sample_db.py` | Create a synthetic sample database |
| `tools/build_catalogs.py` | Rebuild `src/arcivo/i18n/locales/*.json` from `tools/i18n_en.py` / `tools/i18n_fa.py` |
| `scripts/build.ps1` | Windows build: PyInstaller app, Inno Setup installer, portable ZIP |

## Project layout

See [docs/architecture.md](docs/architecture.md). In short: `core` (paths, config, logging, errors) → `db` +
`repositories` (SQLite) → `telegram` (gateway interface, Telethon implementation, fake for tests) → `services`
(sync, search, export, delete, analytics, storage, organisation) → `jobs` → `cli` / `gui`. The GUI never talks
to Telethon directly.

## Making changes

- **Strings:** every user-visible string goes through i18n. Add the key to *both* `tools/i18n_en.py` and
  `tools/i18n_fa.py`, run `python tools/build_catalogs.py`; `tests/unit/test_i18n.py` checks parity.
- **Database:** never edit an existing migration. Add `src/arcivo/db/migrations/NNNN_description.sql`; migrations
  run in a transaction after an automatic backup.
- **Telegram calls:** add them to the `TelegramGateway` protocol, implement them in `telethon_gateway.py` *and*
  `fake.py`, and route them through the back-off helper (FLOOD_WAIT is honoured, never bypassed).
- **Tests:** new behaviour needs tests. Services are tested against the fake gateway; nothing in the test suite
  may touch the network.
- **Style:** `ruff` (line length 110), type hints everywhere, small focused modules.

## Commits & pull requests

- Conventional-style commit subjects are appreciated (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `build:`).
- Fill in the PR template, link the issue, include before/after screenshots (demo data) for UI changes.
- Update `CHANGELOG.md` under *Unreleased*.

## Releasing (maintainers)

1. Bump `src/arcivo/__version__.py`, move *Unreleased* notes in `CHANGELOG.md` under the new version.
2. Tag: `git tag v1.2.3 && git push --tags`. The *Release* workflow builds the installer, portable ZIP and
   checksums on Windows and drafts a GitHub release.
