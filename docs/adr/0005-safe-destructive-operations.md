# ADR 0005 – Safe destructive operations

**Status:** accepted

**Context.** Telegram has no API to restore deleted messages.

**Decision.** Deletion is a two-phase job: `plan()` computes exactly what will be removed (count, types, size,
sample) and returns a token; the user reviews it and confirms by typing the number of messages (two-step confirmation, on by default);
the job deletes in batches of ≤100 with back-off, updates the local index only for ids Telegram accepted, and
writes an audit-log entry and JSON/HTML report. Post-export deletion is offered only for messages whose export
was verified.

**Consequences.** Slightly more friction by design; no "undo" for Telegram deletions (UI states this), while all
local operations (tags, flags, notes) are undoable.
