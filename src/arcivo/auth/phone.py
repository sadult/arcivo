"""Phone number + login code (+ optional Two-Step Verification password)."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Protocol

from ..core.errors import InvalidPhoneError
from ..core.redaction import mask_phone
from .base import AuthProvider, AuthState, AuthStep, register


class PhoneAuthCapable(Protocol):
    async def send_code(self, phone: str) -> str: ...
    async def sign_in_code(self, phone: str, code: str, phone_code_hash: str) -> bool: ...
    async def sign_in_password(self, password: str) -> None: ...
    async def password_hint(self) -> str | None: ...


def normalize_phone(raw: str) -> str:
    from ..domain.formatting import TO_ASCII_DIGITS

    digits = re.sub(r"[^\d+]", "", raw.translate(TO_ASCII_DIGITS))
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        digits = "+" + digits
    if not re.fullmatch(r"\+\d{7,15}", digits):
        raise InvalidPhoneError("phone must be in international format, e.g. +98912…")
    return digits


@register
class PhoneCodeProvider(AuthProvider):
    id = "phone"
    title_key = "auth.provider.phone"

    def __init__(self, gateway: PhoneAuthCapable, on_phone: Callable[[str], None] | None = None) -> None:
        self.gw = gateway
        self.phone: str | None = None
        self._hash: str | None = None
        self._on_phone = on_phone

    async def start(self) -> AuthState:
        return AuthState(AuthStep.PHONE)

    async def submit(self, step: AuthStep, value: str) -> AuthState:
        if step == AuthStep.PHONE:
            self.phone = normalize_phone(value)
            self._hash = await self.gw.send_code(self.phone)
            if self._on_phone:
                self._on_phone(self.phone)
            return AuthState(AuthStep.CODE, info={"phone": mask_phone(self.phone)})
        if step == AuthStep.CODE:
            assert self.phone and self._hash, "phone step must come first"
            code = re.sub(r"\D", "", value.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
            if await self.gw.sign_in_code(self.phone, code, self._hash):
                return AuthState(AuthStep.DONE)
            return AuthState(AuthStep.PASSWORD, hint=await self.gw.password_hint())
        if step == AuthStep.PASSWORD:
            await self.gw.sign_in_password(value)
            return AuthState(AuthStep.DONE)
        raise ValueError(f"unexpected step {step}")
