"""Account & technical information (sensitive values masked)."""

from __future__ import annotations

import sqlite3
from typing import Any

from .. import BUILD, __version__
from ..core.redaction import mask_phone


async def account_overview(ctx) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    info: dict[str, Any] = {"app_version": __version__, "build": BUILD, "sqlite": sqlite3.sqlite_version,
                            "credential_store": ctx.store.name, "portable": ctx.paths.portable,
                            "database_path": str(ctx.db.path), "database_bytes": ctx.db.size_bytes()}
    info["session_status"] = "present" if ctx.auth.has_session() else "missing"
    try:
        gw = ctx.gateway()
        authorized = await gw.is_authorized()
        info["authorized"] = authorized
        if authorized:
            me = await gw.get_me()
            info["user"] = {"id": me.user_id, "name": me.display_name, "username": me.username,
                            "phone": mask_phone(me.phone) if ctx.config.settings.privacy.mask_phone else me.phone,
                            "premium": me.is_premium, "lang": me.lang_code}
        conn = await gw.connection_info()
        info["connection"] = {"connected": conn.connected, "dc_id": conn.dc_id, "server": conn.server, "port": conn.port,
                              "layer": conn.layer, "library": conn.library,
                              "latency_ms": round(conn.latency_ms, 1) if conn.latency_ms else None}
    except Exception as exc:
        info["authorized"] = False
        info["connection_error"] = type(exc).__name__
    if ctx.account_id:
        info["sync"] = ctx.sync_state.get(ctx.account_id)
        info["messages"] = ctx.messages.total(ctx.account_id)
    info["cache"] = ctx.cache.stats()
    info["last_operations"] = [dict(r) for r in ctx.audit.list(10)]
    return info
