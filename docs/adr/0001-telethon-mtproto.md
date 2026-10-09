# ADR 0001 – Use Telethon (MTProto user API)

**Status:** accepted

**Context.** Saved Messages are only reachable through the user API (MTProto); the Bot API cannot read them.
Options: Telethon, Pyrogram, TDLib (via bindings).

**Decision.** Telethon 1.x: mature, pure Python (easy PyInstaller bundling), asyncio-native, StringSession for
secure storage, actively maintained with recent layers. Optional `cryptg` for speed.

**Consequences.** All calls go through `TelegramGateway` so the library could be swapped (e.g. TDLib) without
touching services. We pin `telethon>=1.40,<2` and keep a fake gateway for tests.
