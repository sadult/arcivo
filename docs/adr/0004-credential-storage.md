# ADR 0004 – Session and API credential storage

**Status:** accepted

**Context.** A Telegram session string is equivalent to a logged-in account. Telethon's default `.session`
SQLite file is unencrypted.

**Decision.** Use `StringSession` and store it, together with api_id/api_hash and the (masked) phone, in the
Windows Credential Manager via `keyring`; fall back to a DPAPI-encrypted file bound to the Windows user; a
0600 plain file is allowed only for development/CI. Logs redact all secret patterns.

**Consequences.** Sessions can't be copied to another Windows user or machine by copying files (intended).
Portable mode keeps the DPAPI file inside `ArcivoData\` – still bound to the Windows user.
