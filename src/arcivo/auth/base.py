"""Pluggable authentication contracts.

An :class:`AuthProvider` is a small state machine. Front-ends (CLI, GUI or a
future web UI) only render the requested :class:`AuthStep` and submit values;
they never touch Telegram directly. New methods (QR login, bot token, a remote
server-side broker…) are added by registering another provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AuthStep(StrEnum):
    API_CREDENTIALS = "api_credentials"
    PHONE = "phone"
    CODE = "code"
    PASSWORD = "password"
    DONE = "done"


@dataclass
class AuthState:
    step: AuthStep
    hint: str | None = None  # e.g. 2FA password hint
    info: dict[str, Any] = field(default_factory=dict)


class AuthProvider(ABC):
    id: str = "base"
    title_key: str = "auth.provider.base"

    @abstractmethod
    async def start(self) -> AuthState: ...

    @abstractmethod
    async def submit(self, step: AuthStep, value: str) -> AuthState: ...

    async def cancel(self) -> None:  # noqa: B027 - optional hook
        pass


PROVIDERS: dict[str, type[AuthProvider]] = {}


def register(cls: type[AuthProvider]) -> type[AuthProvider]:
    PROVIDERS[cls.id] = cls
    return cls
