"""Translate :class:`~arcivo.core.config.NetworkSettings` into Telethon client arguments.

Supported proxy types:

* ``socks5`` / ``http`` – via ``python-socks`` (``proxy=dict(...)``)
* ``mtproto`` – Telegram MTProxy (``connection=ConnectionTcpMTProxyRandomizedIntermediate``)
"""

from __future__ import annotations

from typing import Any

PROXY_TYPES = ("none", "socks5", "http", "mtproto")


def normalise_secret(secret: str) -> str:
    """MTProxy secrets are hex (optionally ``dd``/``ee`` prefixed); strip whitespace and URL noise."""
    return "".join(secret.split()).removeprefix("secret=")


def telethon_proxy_kwargs(net: Any) -> dict[str, Any]:
    if net is None or not getattr(net, "enabled", False):
        return {}
    kind = net.proxy_type
    if kind == "mtproto":
        from telethon import connection
        return {"connection": connection.ConnectionTcpMTProxyRandomizedIntermediate,
                "proxy": (net.proxy_host, int(net.proxy_port), normalise_secret(net.proxy_secret))}
    proxy: dict[str, Any] = {"proxy_type": kind, "addr": net.proxy_host, "port": int(net.proxy_port), "rdns": bool(net.proxy_rdns)}
    if net.proxy_username:
        proxy["username"] = net.proxy_username
    if net.proxy_password:
        proxy["password"] = net.proxy_password
    return {"proxy": proxy}


def parse_proxy_link(link: str) -> dict[str, Any] | None:
    """Parse ``tg://proxy?server=…&port=…&secret=…`` / ``https://t.me/proxy?...`` and ``socks5://user:pass@host:port``."""
    from urllib.parse import parse_qs, urlparse

    link = link.strip()
    if not link:
        return None
    u = urlparse(link)
    if (u.scheme == "tg" and u.netloc in ("proxy", "socks")) or (u.netloc in ("t.me", "telegram.me") and u.path.strip("/") in ("proxy", "socks")):
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        kind = "mtproto" if (u.netloc == "proxy" or u.path.strip("/") == "proxy") else "socks5"
        try:
            port = int(q.get("port", "0"))
        except ValueError:
            return None
        return {"proxy_type": kind, "proxy_host": q.get("server", ""), "proxy_port": port, "proxy_secret": q.get("secret", ""),
                "proxy_username": q.get("user", ""), "proxy_password": q.get("pass", "")}
    if u.scheme in ("socks5", "socks5h", "http") and u.hostname and u.port:
        return {"proxy_type": "http" if u.scheme == "http" else "socks5", "proxy_host": u.hostname, "proxy_port": u.port,
                "proxy_username": u.username or "", "proxy_password": u.password or "", "proxy_secret": ""}
    return None
