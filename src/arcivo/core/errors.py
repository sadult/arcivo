"""Domain errors with stable codes that the UI maps to translated messages.

Every error carries an i18n ``key`` (``errors.<code>``) plus formatting args, a
``recoverable`` flag and an optional ``retry_after`` (seconds) so that the GUI
and CLI can offer Retry/Recovery consistently.
"""

from __future__ import annotations


class ArcivoError(Exception):
    code = "unknown"
    recoverable = False

    def __init__(self, message: str = "", *, retry_after: float | None = None, **args: object) -> None:
        super().__init__(message or self.code)
        self.retry_after = retry_after
        self.args_map = args

    @property
    def i18n_key(self) -> str:
        return f"errors.{self.code}"


class ConfigError(ArcivoError):
    code = "config"


class NotAuthenticatedError(ArcivoError):
    code = "not_authenticated"


class AuthenticationError(ArcivoError):
    code = "auth_failed"


class InvalidCodeError(AuthenticationError):
    code = "invalid_code"
    recoverable = True


class InvalidPasswordError(AuthenticationError):
    code = "invalid_password"
    recoverable = True


class InvalidPhoneError(AuthenticationError):
    code = "invalid_phone"
    recoverable = True


class InvalidApiCredentialsError(AuthenticationError):
    code = "invalid_api_credentials"


class SessionInvalidError(AuthenticationError):
    code = "session_invalid"


class RateLimitError(ArcivoError):
    code = "rate_limited"
    recoverable = True


class NetworkError(ArcivoError):
    code = "network"
    recoverable = True


class TelegramApiError(ArcivoError):
    code = "telegram_api"
    recoverable = True


class PermissionDeniedError(ArcivoError):
    code = "permission"


class DownloadError(ArcivoError):
    code = "download"
    recoverable = True


class DatabaseError(ArcivoError):
    code = "database"


class SearchSyntaxError(ArcivoError):
    code = "search_syntax"
    recoverable = True


class ExportError(ArcivoError):
    code = "export"


class OperationCancelled(ArcivoError):
    code = "cancelled"
    recoverable = True


class ConfirmationRequired(ArcivoError):
    code = "confirmation_required"
    recoverable = True
