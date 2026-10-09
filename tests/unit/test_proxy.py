from arcivo.core.config import NetworkSettings, Settings
from arcivo.telegram.proxy import parse_proxy_link, telethon_proxy_kwargs


def test_parse_mtproto_links():
    d = parse_proxy_link("tg://proxy?server=1.2.3.4&port=443&secret=ee00ff")
    assert d["proxy_type"] == "mtproto" and d["proxy_host"] == "1.2.3.4" and d["proxy_port"] == 443 and d["proxy_secret"] == "ee00ff"
    d = parse_proxy_link("https://t.me/proxy?server=p.example&port=8443&secret=dd11")
    assert d["proxy_type"] == "mtproto" and d["proxy_host"] == "p.example"


def test_parse_socks_links():
    d = parse_proxy_link("socks5://bob:pw@127.0.0.1:1080")
    assert d == {"proxy_type": "socks5", "proxy_host": "127.0.0.1", "proxy_port": 1080, "proxy_username": "bob",
                 "proxy_password": "pw", "proxy_secret": ""}
    assert parse_proxy_link("tg://socks?server=h&port=9050")["proxy_type"] == "socks5"
    assert parse_proxy_link("not a link") is None
    assert parse_proxy_link("") is None


def test_kwargs():
    assert telethon_proxy_kwargs(NetworkSettings()) == {}
    n = NetworkSettings(proxy_type="socks5", proxy_host="h", proxy_port=1080, proxy_username="u", proxy_password="p")
    kw = telethon_proxy_kwargs(n)
    assert kw["proxy"] == {"proxy_type": "socks5", "addr": "h", "port": 1080, "rdns": True, "username": "u", "password": "p"}
    m = telethon_proxy_kwargs(NetworkSettings(proxy_type="mtproto", proxy_host="h", proxy_port=443, proxy_secret=" ee00 "))
    assert m["proxy"] == ("h", 443, "ee00") and "connection" in m


def test_settings_roundtrip_ignores_removed_keys():
    s = Settings.from_dict({"appearance": {"language": "fa", "calendar": "jalali", "theme": "light"},
                            "network": {"proxy_type": "http", "proxy_host": "x", "proxy_port": 8080}})
    assert s.appearance.theme == "light" and s.network.enabled and s.network.describe() == "http://x:8080"
    assert s.onboarding_done is False
