"""``arcivo doctor`` – a step-by-step connection check with live spinners and plain-language hints.

Checks, in order: API credentials → proxy reachability → direct reachability of Telegram's
data centres → MTProto handshake (through the proxy, if any) → authorisation → account →
server details. Every step has a timeout so a filtered network never hangs the console.
"""

from __future__ import annotations

import asyncio
import socket
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from . import output as out
from . import tui

# Public addresses of Telegram's production data centres (port 443)
TELEGRAM_DCS = [(1, "149.154.175.53"), (2, "149.154.167.51"), (3, "149.154.175.100"), (4, "149.154.167.91"), (5, "91.108.56.130")]
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


@dataclass
class Result:
    status: str  # ok | fail | warn | skip
    detail: str = ""
    hint: str = ""


async def _tcp(host: str, port: int, timeout: float = 5.0) -> float:
    t0 = time.perf_counter()
    _r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    w.close()
    try:
        await w.wait_closed()
    except Exception:
        pass
    return (time.perf_counter() - t0) * 1000


async def _step(label: str, fn: Callable[[], Awaitable[Result]]) -> Result:
    uni = tui._unicode_ok()
    frames = SPIN if uni else "|/-\\"
    task = asyncio.ensure_future(fn())
    i = 0
    tty = sys.stdout.isatty()
    while not task.done():
        if tty:
            sys.stdout.write(f"\r  {tui.accent(frames[i % len(frames)])} {label}{tui.dim('…')}   ")
            sys.stdout.flush()
        i += 1
        await asyncio.sleep(0.08)
    try:
        res = task.result()
    except Exception as exc:
        res = Result("fail", _describe_exc(exc))
    marks = {"ok": ("✔", "+"), "fail": ("✖", "x"), "warn": ("!", "!"), "skip": ("–", "-")}
    mark = marks[res.status][0 if uni else 1]
    paint = {"ok": lambda s: tui.teal(s, True), "fail": lambda s: out.c(s, "1;31"), "warn": lambda s: out.c(s, "1;33"),
             "skip": tui.dim}[res.status]
    line = f"  {paint(mark)} {label}"
    if res.detail:
        line += "  " + tui.dim(res.detail)
    if tty:
        sys.stdout.write("\r" + " " * (tui._width() - 1) + "\r")
    print(line)
    return res


def _describe_exc(exc: BaseException) -> str:
    if isinstance(exc, asyncio.TimeoutError | TimeoutError):
        return "timed out"
    if isinstance(exc, socket.gaierror):
        return "name lookup failed"
    if isinstance(exc, ConnectionRefusedError):
        return "connection refused"
    if isinstance(exc, OSError) and exc.strerror:
        return exc.strerror
    text = str(exc) or type(exc).__name__
    return text if len(text) < 90 else text[:87] + "…"


async def run_checks(ctx: Any) -> int:
    net = ctx.config.settings.network
    hints: list[str] = []
    state: dict[str, Any] = {}

    demo = getattr(ctx, "_fixed_gateway", None) is not None

    async def creds() -> Result:
        if demo:
            return Result("ok", "demo account (offline, synthetic data)")
        c = ctx.auth.api_credentials()
        if c is None:
            return Result("fail", "not configured", "Choose “Sign in” first – it walks you through creating your API ID and hash.")
        return Result("ok", f"api_id {c.api_id} · stored in {ctx.store.name}")

    async def proxy() -> Result:
        if not net.enabled:
            return Result("skip", "no proxy configured")
        ms = await _tcp(net.proxy_host, int(net.proxy_port), 6)
        return Result("ok", f"{net.describe()} · {ms:.0f} ms")

    async def direct() -> Result:
        async def probe(dc: int, ip: str) -> tuple[int, float] | None:
            try:
                return dc, await _tcp(ip, 443, 4)
            except Exception:
                return None
        found = [r for r in await asyncio.gather(*(probe(dc, ip) for dc, ip in TELEGRAM_DCS)) if r]
        if not found:
            msg = "Telegram's servers are not reachable directly from this network."
            if net.enabled:
                return Result("warn", "blocked – using your proxy instead")
            return Result("fail", "no data centre answered", msg + " Turn on a VPN or set up a proxy (menu → Proxy settings).")
        best = min(found, key=lambda r: r[1])
        return Result("ok", f"{len(found)}/{len(TELEGRAM_DCS)} data centres · fastest DC{best[0]} {best[1]:.0f} ms")

    async def mtproto() -> Result:
        if not demo and ctx.auth.api_credentials() is None:
            return Result("skip", "needs API credentials")
        gw = ctx.gateway()
        state["gw"] = gw
        t0 = time.perf_counter()
        await asyncio.wait_for(gw.connect(), 30)
        state["connected"] = True
        via = f" via {net.proxy_type}" if net.enabled else ""
        return Result("ok", f"handshake {((time.perf_counter() - t0) * 1000):.0f} ms{via}")

    async def authorized() -> Result:
        if not state.get("connected"):
            return Result("skip", "not connected")
        ok = await asyncio.wait_for(state["gw"].is_authorized(), 20)
        state["authorized"] = ok
        if not ok:
            return Result("fail", "not signed in", "Choose “Sign in” to connect your Telegram account.")
        return Result("ok", "session is valid")

    async def account() -> Result:
        if not state.get("authorized"):
            return Result("skip", "not signed in")
        me = await asyncio.wait_for(state["gw"].get_me(), 20)
        return Result("ok", me.display_name + (f" (@{me.username})" if me.username else ""))

    async def server() -> Result:
        if not state.get("connected"):
            return Result("skip", "not connected")
        info = await asyncio.wait_for(state["gw"].connection_info(), 20)
        d = info.__dict__ if hasattr(info, "__dict__") else dict(info)
        parts = [f"DC{d.get('dc_id')}" if d.get("dc_id") else "", d.get("server") or "", f"layer {d.get('layer')}" if d.get("layer") else "",
                 f"ping {d['latency_ms']:.0f} ms" if d.get("latency_ms") else ""]
        return Result("ok", " · ".join(p for p in parts if p))

    steps = [("API credentials", creds), ("Proxy", proxy), ("Telegram servers reachable", direct), ("Secure connection (MTProto)", mtproto),
             ("Signed in", authorized), ("Account", account), ("Server", server)]
    failed = 0
    for label, fn in steps:
        res = await _step(label, fn)
        if res.status == "fail":
            failed += 1
            if res.hint:
                hints.append(res.hint)
            if label.startswith("Secure connection"):
                hints.append("The handshake failed. If Telegram is filtered where you are, enable a VPN or configure a SOCKS5 / "
                             "MTProto proxy (menu → Proxy settings), then run this check again.")
    gw = state.get("gw")
    if gw is not None:
        try:
            await asyncio.wait_for(gw.disconnect(), 5)
        except Exception:
            pass
    print()
    if failed:
        tui.panel("What to do", [h for h in dict.fromkeys(hints)] or ["See the log for details: arcivo logs --tail 50"], tone="warn")
    else:
        tui.success("Everything looks good – Arcivo can talk to Telegram.")
        print()
    return 1 if failed else 0
