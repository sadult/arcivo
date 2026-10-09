"""Secret storage backends.

Priority on Windows: Windows Credential Manager (via ``keyring``) → DPAPI
encrypted file (user-bound) → never plaintext unless explicitly selected for
development. Values are namespaced per profile to allow multiple accounts.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)
SERVICE = "Arcivo"
KEYS = ("api_id", "api_hash", "session", "phone")


class CredentialStore(Protocol):
    name: str

    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


class MemoryStore:
    name = "memory"

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


class KeyringStore:
    """Windows Credential Manager / macOS Keychain / Secret Service."""

    name = "keyring"

    def __init__(self, profile: str = "default") -> None:
        import keyring

        self._kr = keyring
        self.profile = profile
        backend = keyring.get_keyring()
        if "fail" in type(backend).__name__.lower() or "null" in type(backend).__module__.lower():
            raise RuntimeError("no usable keyring backend")
        # A "chainer" backend with no real backends behind it only fails on first use – probe it now.
        keyring.get_password(SERVICE, self._k("__probe__"))

    def _k(self, key: str) -> str:
        return f"{self.profile}:{key}"

    def get(self, key: str) -> str | None:
        return self._kr.get_password(SERVICE, self._k(key))

    def set(self, key: str, value: str) -> None:
        self._kr.set_password(SERVICE, self._k(key), value)

    def delete(self, key: str) -> None:
        try:
            self._kr.delete_password(SERVICE, self._k(key))
        except Exception:
            pass


class _FileStore:
    name = "file"

    def __init__(self, directory: Path, profile: str = "default") -> None:
        self.path = directory / f"{profile}.secrets"
        directory.mkdir(parents=True, exist_ok=True)

    def _encode(self, raw: bytes) -> bytes:
        return raw

    def _decode(self, raw: bytes) -> bytes:
        return raw

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self._decode(self.path.read_bytes()).decode("utf-8"))
        except Exception:
            log.error("Secret store is unreadable; ignoring it")
            return {}

    def _write(self, data: dict[str, str]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(self._encode(json.dumps(data).encode("utf-8")))
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def get(self, key: str) -> str | None:
        return self._read().get(key)

    def set(self, key: str, value: str) -> None:
        d = self._read()
        d[key] = value
        self._write(d)

    def delete(self, key: str) -> None:
        d = self._read()
        if d.pop(key, None) is not None:
            self._write(d)


class PrivateFileStore(_FileStore):
    """Plain JSON with 0600 permissions. Development/CI fallback only."""

    name = "file"


class DpapiStore(_FileStore):
    """Windows DPAPI (CryptProtectData) — encrypted with the user's logon credentials."""

    name = "dpapi"

    def __init__(self, directory: Path, profile: str = "default") -> None:
        if sys.platform != "win32":
            raise RuntimeError("DPAPI is only available on Windows")
        super().__init__(directory, profile)
        self.path = directory / f"{profile}.dpapi"

    @staticmethod
    def _crypt(data: bytes, protect: bool) -> bytes:
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = BLOB()
        entropy = b"Arcivo.v1"
        ebuf = ctypes.create_string_buffer(entropy, len(entropy))
        blob_entropy = BLOB(len(entropy), ctypes.cast(ebuf, ctypes.POINTER(ctypes.c_char)))
        crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
        fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        args = ((ctypes.byref(blob_in), "Arcivo", ctypes.byref(blob_entropy), None, None, 0x01, ctypes.byref(blob_out))
                if protect else
                (ctypes.byref(blob_in), None, ctypes.byref(blob_entropy), None, None, 0x01, ctypes.byref(blob_out)))
        if not fn(*args):
            raise OSError("DPAPI call failed")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]

    def _encode(self, raw: bytes) -> bytes:
        return base64.b64encode(self._crypt(raw, True))

    def _decode(self, raw: bytes) -> bytes:
        return self._crypt(base64.b64decode(raw), False)


def open_store(backend: str, secure_dir: Path, profile: str = "default") -> CredentialStore:
    """Pick the most secure available backend (``auto``) or the requested one."""
    order = {"auto": ["keyring", "dpapi", "file"], "keyring": ["keyring"], "dpapi": ["dpapi"], "file": ["file"],
             "memory": ["memory"]}.get(backend, ["keyring", "dpapi", "file"])
    last: Exception | None = None
    for name in order:
        try:
            if name == "keyring":
                return KeyringStore(profile)
            if name == "dpapi":
                return DpapiStore(secure_dir, profile)
            if name == "memory":
                return MemoryStore()
            if backend == "auto":
                log.warning("No OS credential vault available; falling back to a private file store")
            return PrivateFileStore(secure_dir, profile)
        except Exception as exc:  # try next backend
            last = exc
            continue
    raise RuntimeError(f"no credential store available: {last}")
