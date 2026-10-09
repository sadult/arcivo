## Summary

<!-- What does this change and why? Link the issue: Fixes #123 -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / performance
- [ ] Docs / translations
- [ ] Build / CI

## Checklist

- [ ] `ruff check src tests scripts` and `pytest` pass locally
- [ ] New/changed strings added to **both** `tools/i18n_en.py` and `tools/i18n_fa.py` (+ `python tools/build_catalogs.py`)
- [ ] Schema changes are a **new** migration file
- [ ] Telegram calls go through the gateway + back-off, and are implemented in the fake gateway for tests
- [ ] Destructive actions keep the review + confirmation + audit-log flow
- [ ] UI changes include before/after screenshots **made with demo data**
- [ ] `CHANGELOG.md` updated under *Unreleased*
- [ ] No personal data, sessions or API credentials in the diff
