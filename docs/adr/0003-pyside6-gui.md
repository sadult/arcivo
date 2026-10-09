# ADR 0003 – PySide6 for the desktop UI

**Status:** accepted

**Context.** Requirements: native-feeling Windows app, high-density tables with 100k rows, charts,
theming, single language (Python) with the core.

**Decision.** PySide6 (Qt 6, LGPL) with Qt Charts, model/view tables, a generated stylesheet from design tokens,
and an asyncio worker thread bridged via signals.

**Consequences.** Larger bundle (≈200 MB unpacked, much smaller compressed; trimmed by excluding unused Qt modules). Qt Charts is GPL for open
source – compatible with our MIT-licensed public source (see THIRD_PARTY_NOTICES).
