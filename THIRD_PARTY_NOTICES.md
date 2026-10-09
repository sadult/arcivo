# Third-party notices

Arcivo bundles or depends on the following open-source components. Their licenses apply to those components.

| Component | License | Use |
|---|---|---|
| [Telethon](https://github.com/LonamiWebs/Telethon) | MIT | Telegram API (MTProto) client library |
| [Qt for Python / PySide6](https://www.qt.io/qt-for-python) | LGPL-3.0 | Desktop UI toolkit (dynamically linked, unmodified) |
| [Qt Charts](https://doc.qt.io/qt-6/qtcharts-index.html) | GPL-3.0 / commercial (via PySide6-Addons) | Charts in Statistics, Storage and Dashboard |
| [keyring](https://github.com/jaraco/keyring) | MIT | Windows Credential Manager access |
| [python-socks](https://github.com/romis2012/python-socks) | Apache-2.0 | SOCKS5/HTTP proxy support |
| [platformdirs](https://github.com/platformdirs/platformdirs) | MIT | Per-user data/config folders |
| [cryptg](https://github.com/cher-nov/cryptg) (optional) | CC0 | Faster MTProto encryption |
| [Inter](https://rsms.me/inter/) | SIL OFL 1.1 | UI font (Latin) |
| [Lucide icons](https://lucide.dev) | ISC | Interface icons |
| [SQLite](https://sqlite.org) | Public domain | Local database (via Python's `sqlite3`) |

**Qt licensing note.** PySide6 is used under the LGPL-3.0: Qt libraries are shipped as separate, replaceable
shared libraries in the application folder. The Qt Charts add-on is available under GPL-3.0 for open-source
projects; Arcivo is MIT-licensed open source and its complete source code is published, which satisfies the
GPL's source-availability requirement for redistributed binaries. If you redistribute a closed-source fork,
replace the charts module or obtain a commercial Qt license.

Font license texts are included in `src/arcivo/assets/fonts/`.

"Telegram" is a trademark of Telegram FZ-LLC. Arcivo is an independent project and is not affiliated with,
endorsed or sponsored by Telegram.
