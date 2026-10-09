import pytest

from arcivo.auth.base import AuthStep
from arcivo.auth.credentials import MemoryStore, PrivateFileStore, open_store
from arcivo.auth.phone import normalize_phone
from arcivo.auth.service import AuthService, validate_api_credentials
from arcivo.core import errors as E

HASH = "0123456789abcdef0123456789abcdef"


class FakePhoneGateway:
    def __init__(self, needs_password=False):
        self.authorized = False
        self.needs_password = needs_password
        self.session = None

    def bind(self, on_session):
        self.on_session = on_session
        return self

    async def is_authorized(self):
        return self.authorized

    async def send_code(self, phone):
        if phone == "+10000000000":
            raise E.InvalidPhoneError("bad")
        return "hash123"

    async def sign_in_code(self, phone, code, h):
        if code != "12345":
            raise E.InvalidCodeError("bad code")
        if self.needs_password:
            return False
        self._done()
        return True

    async def sign_in_password(self, pw):
        if pw != "s3cret":
            raise E.InvalidPasswordError("bad")
        self._done()

    async def password_hint(self):
        return "pet name"

    def _done(self):
        self.authorized = True
        self.on_session("1SESSIONSTRING")

    async def log_out(self):
        self.authorized = False

    async def disconnect(self):
        pass


def make(needs_password=False):
    store = MemoryStore()
    gw = FakePhoneGateway(needs_password)
    return store, gw, AuthService(store, lambda api_id, api_hash, session, on_session: gw.bind(on_session))


async def test_full_login_with_2fa():
    store, _gw, auth = make(needs_password=True)
    assert (await auth.begin()).step == AuthStep.API_CREDENTIALS
    with pytest.raises(E.InvalidApiCredentialsError):
        auth.save_api_credentials("abc", HASH)
    auth.save_api_credentials("12345", HASH.upper())
    assert (await auth.begin()).step == AuthStep.PHONE
    st = await auth.submit("+98 912 123 4567")
    assert st.step == AuthStep.CODE and "•" in st.info["phone"]
    with pytest.raises(E.InvalidCodeError):
        await auth.submit("00000")
    st = await auth.submit("12345")
    assert st.step == AuthStep.PASSWORD and st.hint == "pet name"
    with pytest.raises(E.InvalidPasswordError):
        await auth.submit("wrong")
    assert (await auth.submit("s3cret")).step == AuthStep.DONE
    assert store.get("session") == "1SESSIONSTRING" and store.get("api_hash") == HASH
    assert await auth.is_authorized()
    await auth.logout()
    assert store.get("session") is None and store.get("api_id") == "12345"


def test_normalize_phone():
    assert normalize_phone("۰۰۹۸ ۹۱۲-۱۲۳-۴۵۶۷") == "+989121234567"
    with pytest.raises(E.InvalidPhoneError):
        normalize_phone("12")


def test_validate_api():
    assert validate_api_credentials(" 42 ", HASH).api_id == 42
    with pytest.raises(E.InvalidApiCredentialsError):
        validate_api_credentials(42, "nothex")


def test_file_store_permissions(tmp_path):
    s = PrivateFileStore(tmp_path)
    s.set("session", "abc")
    assert s.get("session") == "abc"
    import os
    import stat
    if os.name != "nt":
        assert stat.S_IMODE(os.stat(s.path).st_mode) == 0o600
    s.delete("session")
    assert s.get("session") is None
    assert open_store("memory", tmp_path).name == "memory"
