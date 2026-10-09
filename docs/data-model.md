# Data model

SQLite database (`arcivo.db`, WAL mode, `foreign_keys=ON`). Schema changes are numbered migrations in
`src/arcivo/db/migrations/`; the migrator records applied versions in `schema_migrations`, takes a backup to
`database/backups/` before applying, and runs each migration in a transaction.

## Source of truth

| Data | Source of truth | Arcivo's copy | Notes |
|---|---|---|---|
| Message content, media, dates, forward info | **Telegram** | `messages` (index) | Re-synced; local edits are impossible |
| Media files | **Telegram** | `cache_entries` (thumbnails/previews), exports | Cache is disposable and size-capped |
| Message existence | **Telegram** | `messages.remote_deleted` | Incremental sync re-checks recent ids; full sync reconciles everything |
| Tags, flags, stars, notes | **Arcivo (local)** | `tags`, `message_tags`, `message_marks` | Never uploaded; undoable |
| Smart collections | **Arcivo (local)** | `collections` | Stored as query strings, evaluated live |
| Jobs, reports, audit log | **Arcivo (local)** | `jobs`, `job_items`, `reports`, `audit_log` | Support resume & accountability |
| Session, API ID/hash | **Credential vault** | – (never in the DB) | Credential Manager / DPAPI |
| Settings | **config.json** | – | No secrets |

## Tables

| Migration | Table | Purpose |
|---|---|---|
| 0001 | `accounts` | one row per Telegram account (`telegram_user_id`, display name, username) |
| 0001 | `messages` | the index: id, date, edit date, `media_type`, `category`, text/caption, file name/extension/mime/size, duration, dimensions, performer/title, media id + DC, sender, source chat, forward info, reply, album (`grouped_id`), `saved_peer_id` (saved-dialog), link count, thumbnail flag, `remote_deleted`, `synced_at` |
| 0001 | `messages_fts` | FTS5 external-content index over text, file name, sender, chat, performer, title (`unicode61`, diacritics removed) kept in sync by triggers |
| 0001 | `peers`, `links` | senders/sources and extracted URLs (with domain) |
| 0001 | `sync_state` | `initial_complete`, `checkpoint_id` (resume point), `max_message_id`, timestamps, total |
| 0002 | `tags`, `message_tags` | local tags (case-insensitive unique names, colours) |
| 0002 | `message_marks` | flagged / starred / private note |
| 0002 | `collections` | smart collections (query, icon, colour, pinned, sort, position) |
| 0003 | `jobs`, `job_items` | persisted jobs and per-message progress (status, bytes, output path) |
| 0003 | `reports` | export/delete reports (JSON + HTML paths, summary) |
| 0003 | `cache_entries` | thumbnail/preview cache with LRU timestamps |
| 0003 | `file_hashes` | optional content hashes for duplicate verification |
| 0003 | `audit_log` | append-only record of syncs, deletions, resets |

Key indexes: `(account_id, date_ts)`, `(account_id, media_type, date_ts)`, `(account_id, category, file_size)`,
`(account_id, extension)`, `(account_id, media_id)` (duplicates), `(account_id, grouped_id)` (albums).

## Media taxonomy

`media_type` (precise): `text, photo, video, video_note, animation, audio, voice, document, sticker, link,
contact, location, venue, poll, dice, game, invoice, story, unsupported`.
`category` (for storage charts): `images, videos, audio, documents, archives, apps, code, other`, derived from
type + MIME + extension.

## Duplicates

Detection methods (`StorageService.METHODS`):

| Method | Confidence | Rule |
|---|---|---|
| `media_id` | certain | same Telegram file (identical upload / forward) |
| `hash` | certain | identical SHA-256 of downloaded content (`file_hashes`) |
| `name_size` | likely | same file name and size |
| `size_duration` | possible | same size and duration |

Users choose which copy to keep (oldest/newest), review the list, and only then start a delete job.
