"""Authentication orchestration shared by CLI and GUI."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from ..core.errors import InvalidApiCredentialsError, NotAuthenticatedError
from ..core.redaction import mask_phone
from . import phone as _phone  # noqa: F401  (registers the built-in "phone" provider)
from .base import PROVIDERS, AuthProvider, AuthState, AuthStep
from .credentials import CredentialStore

log = logging.getLogger(__name__)

GatewayFactory = Callable[[int, str, str | None, Callable[[str], None]], object]


@dataclass
class ApiCredentials:
    api_id: int
    api_hash: str


def validate_api_credentials(api_id: str | int, api_hash: str) -> ApiCredentials:
    try:
        iid = int(str(api_id).strip())
    except ValueError as exc:
        raise InvalidApiCredentialsError("API ID must be a number") from exc
    h = api_hash.strip().lower()
    if iid <= 0 or not re.fullmatch(r"[0-9a-f]{32}", h):
        raise InvalidApiCredentialsError("API hash must be 32 hexadecimal characters")
    return ApiCredentials(iid, h)


class AuthService:
    def __init__(self, store: CredentialStore, gateway_factory: GatewayFactory) -> None:
        self.store = store
        self.factory = gateway_factory
        self._gateway: object | None = None
        self._provider: AuthProvider | None = None
        self.state = AuthState(AuthStep.API_CREDENTIALS)

    # ------------------------------------------------------------- credentials
    def api_credentials(self) -> ApiCredentials | None:
        api_id, api_hash = self.store.get("api_id"), self.store.get("api_hash")
        if not api_id or not api_hash:
            return None
        return ApiCredentials(int(api_id), api_hash)

    def save_api_credentials(self, api_id: str | int, api_hash: str) -> None:
        creds = validate_api_credentials(api_id, api_hash)
        self.store.set("api_id", str(creds.api_id))
        self.store.set("api_hash", creds.api_hash)
        self._gateway = None

    def has_session(self) -> bool:
        return bool(self.store.get("session"))

    def masked_phone(self) -> str:
        return mask_phone(self.store.get("phone"))

    def _save_session(self, session: str) -> None:
        if session:
            self.store.set("session", session)

    # ------------------------------------------------------------- gateway
    def reset_gateway(self) -> None:
        """Forget the cached gateway so the next call builds a fresh client (e.g. after proxy changes)."""
        self._gateway = None

    def gateway(self) -> object:
        if self._gateway is None:
            creds = self.api_credentials()
            if creds is None:
                raise NotAuthenticatedError("API credentials are not configured")
            self._gateway = self.factory(creds.api_id, creds.api_hash, self.store.get("session"), self._save_session)
        return self._gateway

    async def is_authorized(self) -> bool:
        if self.api_credentials() is None or not self.has_session():
            return False
        return bool(await self.gateway().is_authorized())  # type: ignore[attr-defined]

    # ------------------------------------------------------------- login flow
    async def begin(self, provider: str = "phone") -> AuthState:
        if self.api_credentials() is None:
            self.state = AuthState(AuthStep.API_CREDENTIALS)
            return self.state
        if await self.is_authorized():
            self.state = AuthState(AuthStep.DONE)
            return self.state
        cls = PROVIDERS[provider]
        gw = self.gateway()
        self._provider = cls(gw, on_phone=lambda p: self.store.set("phone", p))  # type: ignore[call-arg]
        self.state = await self._provider.start()
        return self.state

    async def submit(self, value: str) -> AuthState:
        if self.state.step == AuthStep.API_CREDENTIALS:
            raise RuntimeError("use save_api_credentials() for this step")
        if self._provider is None:
            raise RuntimeError("call begin() first")
        self.state = await self._provider.submit(self.state.step, value)
        if self.state.step == AuthStep.DONE:
            log.info("Authentication completed")
        return self.state

    async def logout(self, *, revoke_remote: bool = True, forget_api: bool = False) -> None:
        gw = self._gateway
        if gw is None and self.has_session() and self.api_credentials():
            gw = self.gateway()
        if gw is not None and revoke_remote and hasattr(gw, "log_out"):
            await gw.log_out()  # type: ignore[attr-defined]
        if gw is not None:
            try:
                await gw.disconnect()  # type: ignore[attr-defined]
            except Exception:
                pass
        self.store.delete("session")
        self.store.delete("phone")
        if forget_api:
            self.store.delete("api_id")
            self.store.delete("api_hash")
        self._gateway = None
        self.state = AuthState(AuthStep.API_CREDENTIALS if forget_api else AuthStep.PHONE)
        log.info("Logged out; local session removed")
