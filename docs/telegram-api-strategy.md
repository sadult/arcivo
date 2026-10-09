# Telegram API strategy

Arcivo uses [Telethon](https://docs.telethon.dev) (MTProto, user account) – the only way to read a user's
*Saved Messages*. The Bot API cannot access them.

## Compliance with the Telegram API Terms of Service

| Requirement | How Arcivo complies |
|---|---|
| Use your own `api_id` / `api_hash` | Every user creates their own at <https://my.telegram.org/apps>; none is bundled |
| Don't use "Telegram" as the app name / don't use the logo | The app is called **Arcivo** with its own logo; "Telegram" appears only descriptively ("uses the Telegram API") |
| Tell users it's an unofficial app | Shown in the sign-in wizard, About page, installer notice and README |
| No actions without the user's knowledge | Arcivo only acts on explicit user commands; deletions require review + confirmation |
| Protect user data / privacy | Local-only, encrypted session storage, redacted logs, no telemetry, no third-party servers |
| No use of data for AI/ML training | Arcivo does not collect data; the project forbids such use in CONTRIBUTING |
| Respect flood limits | FLOOD_WAIT is honoured exactly; Arcivo never rotates accounts or retries aggressively |

## Calls used

| Feature | API (via Telethon) | Notes |
|---|---|---|
| Sign-in | `auth.sendCode`, `auth.signIn`, `account.getPassword` + `auth.checkPassword` (SRP) | 2FA via SRP; password never stored |
| Read Saved Messages | `messages.getHistory` on `InputPeerSelf` (`iter_messages('me', reverse=True, min_id=…)`) | batches of `sync.batch_size` (100), `sync.request_delay_s` between batches |
| Verify edits/deletions | `messages.getMessages(ids)` for the most recent `sync.recheck_recent` ids | missing → `remote_deleted` |
| Thumbnails/previews | `upload.getFile` (thumb sizes) | cached locally, LRU-limited |
| Download media | `upload.getFile` with offsets | resumable, `performance.download_concurrency` parallel files |
| Delete | `messages.deleteMessages(revoke=True)` | ≤100 ids per call, throttled, only after confirmation |
| Account info | `users.getFullUser(self)`, `help.getConfig` | status & connection pages |

## Sync algorithm

1. **Initial** – iterate history ascending from `checkpoint_id`; upsert each batch and store the checkpoint, so an
   interrupted run resumes where it stopped.
2. **Incremental** – fetch ids greater than `max_message_id`, then re-fetch the newest N indexed ids to pick up edits
   and deletions.
3. **Full re-scan** (on demand) – iterate everything and reconcile: indexed ids not seen are marked deleted (or
   removed, depending on `sync.keep_remote_deleted`).

## Rate limits & errors

- `FLOOD_WAIT_X` / `FLOOD_PREMIUM_WAIT_X` / slow mode → `RateLimitError(retry_after)`. The back-off helper sleeps
  exactly `X` seconds (+ jitter) if `X ≤ sync.max_flood_wait_s` (default 900 s) and shows a countdown; otherwise
  the job pauses with a clear message and can be resumed later.
- Network errors use capped exponential back-off with jitter (max 5 attempts).
- Auth errors (`AUTH_KEY_UNREGISTERED`, `SESSION_REVOKED`) stop work and ask the user to sign in again.
- Errors are translated to stable Arcivo codes (see `core/errors.py`) and shown in the user's language.

## Layer compatibility

Developed and tested with Telethon 1.4x (API layer ≥ 229). The mapper tolerates unknown media types
(`unsupported`) and new fields, and stores the saved-dialog peer (`saved_peer_id`) when present.
