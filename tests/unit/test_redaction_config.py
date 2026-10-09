import logging

from arcivo.core.config import ConfigStore, Settings
from arcivo.core.redaction import RedactingFilter, mask_phone, redact


def test_redact_secrets():
    s = redact("api_hash=0123456789abcdef0123456789abcdef phone +989121234567 password: hunter2")
    assert "0123456789abcdef" not in s and "hunter2" not in s and "1234567" not in s


def test_ids_not_mangled():
    assert redact("synced 123456789 messages") == "synced 123456789 messages"


def test_mask_phone():
    assert mask_phone("+989121234567") == "+98••••••••67"


def test_filter_scrubs_args():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "hash %s", ("0123456789abcdef0123456789abcdef",), None)
    RedactingFilter().filter(rec)
    assert "0123456789abcdef" not in rec.getMessage()


def test_config_roundtrip_and_bad_values(paths):
    cs = ConfigStore(paths)
    cs.load()
    cs.settings.appearance.theme = "light"
    cs.settings.performance.download_concurrency = 4
    cs.save()
    s2 = ConfigStore(paths).load()
    assert s2.appearance.theme == "light" and s2.performance.download_concurrency == 4
    s3 = Settings.from_dict({"appearance": {"theme": 5}, "unknown": 1, "shortcuts": {"export": "Ctrl+Shift+E"}})
    assert s3.appearance.theme == "dark" and s3.shortcuts["export"] == "Ctrl+Shift+E" and s3.shortcuts["refresh"] == "F5"


def test_broken_config(paths):
    paths.config_file.write_text("{not json")
    s = ConfigStore(paths).load()
    assert s.appearance.theme == "dark"
    assert paths.config_file.with_suffix(".broken.json").exists()
