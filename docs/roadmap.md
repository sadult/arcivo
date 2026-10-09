# Roadmap

Arcivo 1.0 covers the full local workflow: sign in, index, search, organise, analyse, export and clean up.
Ideas below are candidates – open a feature request to discuss priorities.

## 1.1 – polish
- Inline audio/voice player and video preview in the detail panel
- Saved-dialog (topic) view for Saved Messages sub-chats (`saved_peer_id`)
- Code-signing of `Arcivo.exe` and installer; winget manifest
- Per-collection auto-export (scheduled, opt-in)

## 1.2 – power features
- Content hashing in the background for exact duplicate detection of all downloaded files
- Rule-based auto-tagging (local rules, e.g. `domain:github.com → tag:dev`)
- Export profiles (named presets), ZIP output, incremental exports that only add new messages
- Import of Telegram Desktop JSON exports into the index (offline)

## Later
- Multi-account profiles
- macOS and Linux packages (the code is cross-platform; packaging and credential backends need work)
- Plugin API for custom exporters

## Non-goals
- Reading or scraping chats other than the user's own Saved Messages
- Cloud sync, telemetry, or any third-party server
- Using message content for AI/ML training
