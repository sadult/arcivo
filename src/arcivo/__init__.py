"""Arcivo — local-first archive manager for Telegram Saved Messages.

Arcivo is an unofficial client that uses the official Telegram API. It is not
affiliated with or endorsed by Telegram.
"""

from .__version__ import BUILD, __version__

APP_NAME = "Arcivo"
APP_ID = "arcivo"
APP_TAGLINE = "Your Saved Messages, organised."
REPO_URL = "https://github.com/sadult/arcivo"
AUTHOR = "Bitologist"
TELEGRAM_URL = "https://t.me/Bitologist"
TELEGRAM_HANDLE = "@Bitologist"
WINDOWS_APP_USER_MODEL_ID = "Bitologist.Arcivo.Dashboard"

__all__ = ["APP_ID", "APP_NAME", "APP_TAGLINE", "AUTHOR", "BUILD", "REPO_URL", "TELEGRAM_HANDLE", "TELEGRAM_URL",
           "WINDOWS_APP_USER_MODEL_ID", "__version__"]
