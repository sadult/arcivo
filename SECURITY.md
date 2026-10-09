# Security policy

Arcivo handles a Telegram login session – which is equivalent to being logged in to the account – so we take
security reports seriously.

## Supported versions

| Version | Supported |
|---|---|
| 1.x (latest minor) | ✅ |
| older | ❌ – please upgrade |

## Reporting a vulnerability

**Please do not open a public issue.** Use
[GitHub private vulnerability reporting](https://github.com/sadult/arcivo/security/advisories/new).
Include steps to reproduce, affected version, and impact. Never include your real session file, API hash or
phone number – reproduce with `--demo` where possible.

We aim to acknowledge reports within 72 hours and to ship a fix for confirmed high-severity issues within
14 days. We are happy to credit reporters in the release notes.

## How Arcivo protects your data

- **Session & API credentials** are stored in the Windows Credential Manager (via `keyring`) or, as a fallback,
  encrypted with Windows DPAPI under your user profile. They are never written to the config file, logs or exports.
- **Logs are redacted**: phone numbers, API hashes, auth keys, login codes, passwords and session strings are
  masked before anything is written (`arcivo logs --export file.log` produces a shareable, redacted file).
- **Local-only:** the index, cache and exports stay on your computer. Arcivo talks only to Telegram's servers
  and never to third-party services; there is no telemetry.
- **Destructive operations** (deleting messages on Telegram) require a review list, explicit confirmation and are
  recorded in a local audit log with a JSON/CSV report.
- **Portable mode** keeps everything in `ArcivoData\` next to the executable – protect that folder like a password.

## If you think your session leaked

1. In any Telegram app: *Settings → Devices* → terminate the "Arcivo" session (or all other sessions).
2. Run `arcivo logout` (or *Account → Log out*) to delete the local copy.
3. Optionally revoke/regenerate your API credentials at <https://my.telegram.org/apps>.
