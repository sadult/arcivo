# ADR 0002 – Local SQLite index with FTS5

**Status:** accepted

**Context.** Search, statistics, duplicate detection and bulk selection over tens of thousands of messages must
be instant and work offline, without hammering the API.

**Decision.** Mirror message metadata in SQLite (WAL) with FTS5 for full-text search and covering indexes for
filters; Telegram remains the source of truth and is reconciled by sync. Local-only data (tags, notes,
collections) lives in the same DB.

**Consequences.** Need a robust sync (checkpoints, recheck of recent ids, full reconcile) and migrations with
backups. The DB contains personal data, so it lives in the user profile and is never uploaded.
