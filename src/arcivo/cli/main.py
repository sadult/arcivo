"""``arcivo`` command-line interface. Shares the same core as the GUI."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import APP_NAME, BUILD, __version__
from ..core.errors import ArcivoError
from ..domain.formatting import human_duration, human_size
from . import output as out

SEARCH_HELP = """Search syntax (combine freely; terms are AND-ed):
  words "exact phrase"        full-text in text, captions, file names, senders, chats, audio tags
  type:audio,voice            text photo image video video_note gif audio voice document file media
                              link sticker contact location poll dice …
  sender:@username | sender:"Name" | sender:me     from:  is an alias
  chat:"Channel name" | chat:@channel             channel: in:  are aliases
  ext:pdf,docx   mime:image/*   filename:report   caption:"some text"   domain:github.com
  after:2026-01-01  before:2026-02  date:2025 | date:2025-01..2025-06   (after is inclusive)
  size:>50MB  size:<1GB  size:10MB..100MB          duration:>5m  duration:1:30..10:00
  tag:work,music   has:link|media|caption|tag|note   is:flagged|starred|forwarded|album|edited|deleted
  -tag:archive  -type:sticker                      prefix "-" negates any clause
  type:audio OR type:voice                         OR combines neighbouring clauses
  sort:size | sort:date-asc | sort:duration  order:asc|desc
"""


def _ctx(args: argparse.Namespace):  # type: ignore[no-untyped-def]
    from ..context import AppContext
    if getattr(args, "demo", False) or os.environ.get("ARCIVO_DEMO") == "1":
        return demo_context()
    return AppContext(log_console=getattr(args, "verbose", False))


def demo_context():  # type: ignore[no-untyped-def]
    from ..context import AppContext
    from ..core.paths import resolve_paths
    from ..sample_data import generate
    from ..telegram.fake import FakeGateway
    base = resolve_paths()
    demo_root = base.data_dir / "demo"
    os.environ.setdefault("ARCIVO_HOME", str(demo_root))
    from ..core.paths import AppPaths
    paths = AppPaths(config_dir=demo_root / "config", data_dir=demo_root / "data", portable=True)
    ctx = AppContext(paths, gateway=FakeGateway(generate(int(os.environ.get("ARCIVO_DEMO_SIZE", "4000")))))
    ctx.config.settings.sync.request_delay_s = 0
    ctx.deleter.batch_delay = 0
    return ctx


def run(coro):  # type: ignore[no-untyped-def]
    # Telethon is happiest on a selector loop on Windows. Use a loop factory instead of the
    # event-loop-policy API, which is deprecated since Python 3.14.
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(coro)


# --------------------------------------------------------------------------- auth
def cmd_login(args: argparse.Namespace) -> int:
    from ..auth.base import AuthStep
    from . import tui
    ctx = _ctx(args)
    skipped: set[str] = set()
    status_msg: list[tuple[str, str]] = []  # (kind, text) shown under the panel on the next screen

    def screen(step: str, title: str, lines: list[str]) -> None:
        tui.clear()
        tui.banner()
        tui.steps(step, skipped)
        tui.panel(title, lines)
        for kind, text in status_msg:
            (tui.error if kind == "error" else tui.success)(text)
        status_msg.clear()

    async def flow() -> int:
        auth = ctx.auth
        if auth.api_credentials() is None or args.reset_api:
            api_id = args.api_id
            while True:
                screen("api", "Telegram API credentials", [
                    "Arcivo signs in with " + tui.accent("your own", False) + " API credentials (Telegram's rules).",
                    "",
                    "1. Open " + tui.teal("https://my.telegram.org", True) + " and log in",
                    "2. Choose " + tui.accent("API development tools", False),
                    "3. Create an app (any name, platform: Desktop)",
                    "4. Copy " + tui.accent("api_id", False) + " (number) and " + tui.accent("api_hash", False) + " (32 chars)",
                    "",
                    tui.dim(f"Stored in the {'OS credential vault' if ctx.store.name in ('keyring', 'dpapi') else ctx.store.name + ' store'};"
                            " never in config files or logs."),
                ])
                api_id = api_id or tui.prompt("API ID").strip()
                api_hash = tui.prompt("API Hash", secret=True, hint="(hidden while typing)").strip()
                try:
                    auth.save_api_credentials(api_id, api_hash)
                    status_msg.append(("ok", f"API credentials saved ({ctx.store.name})"))
                    break
                except ArcivoError as exc:
                    status_msg.append(("error", str(exc)))
                    api_id = None
        else:
            skipped.add("api")
        state = await auth.begin()
        phone_masked = ""
        while state.step != AuthStep.DONE:
            try:
                if state.step == AuthStep.PHONE:
                    screen("phone", "Phone number", [
                        "Enter the phone number of your Telegram account in international format,",
                        "including the country code, e.g. " + tui.accent("+98 912 345 6789", False) + ".",
                        "",
                        tui.dim("Telegram will send a login code to your Telegram app (or by SMS)."),
                    ])
                    value = args.phone or tui.prompt("Phone number")
                    args.phone = None
                    state = await auth.submit(value)
                    phone_masked = state.info.get("phone", "")
                elif state.step == AuthStep.CODE:
                    screen("code", "Login code", [
                        "A login code was sent to " + tui.accent(phone_masked or "your account", False) + ".",
                        "Look for a message from " + tui.accent("Telegram", False) + " in your Telegram app on another device.",
                        "",
                        tui.dim("Never share this code with anyone – Arcivo only sends it to Telegram."),
                    ])
                    state = await auth.submit(tui.prompt("Code", secret=True, hint="(hidden)"))
                    if state.step == AuthStep.DONE:
                        skipped.add("password")  # account has no two-step verification
                elif state.step == AuthStep.PASSWORD:
                    hint = f"Hint: {state.hint}" if state.hint else "No hint set."
                    screen("password", "Two-step verification", [
                        "Your account is protected with a cloud password.",
                        tui.dim(hint),
                        "",
                        tui.dim("The password is checked with SRP and never stored by Arcivo."),
                    ])
                    state = await auth.submit(tui.prompt("Password", secret=True, hint="(hidden)"))
            except ArcivoError as exc:
                if not exc.recoverable:
                    raise
                wait = f" (wait {int(exc.retry_after)}s)" if getattr(exc, "retry_after", None) else ""
                status_msg.append(("error", f"{exc}{wait} – please try again."))
        me = await ctx.gateway().get_me()
        ctx.accounts.ensure(me.user_id, me.display_name, me.username)
        skipped.discard("api")
        tui.clear()
        tui.banner()
        tui.steps("done", skipped)
        name = me.display_name + (f" (@{me.username})" if me.username else "")
        next_steps = (["  " + tui.accent("4  Sync now", False) + tui.dim("         index your Saved Messages"),
                       "  " + tui.accent("2  Open dashboard", False) + tui.dim("   browse, search and export")]
                      if getattr(args, "from_menu", False) else
                      ["  " + tui.accent("arcivo sync", False) + tui.dim("      index your Saved Messages"),
                       "  " + tui.accent("arcivo gui", False) + tui.dim("       open the desktop app"),
                       "  " + tui.accent("arcivo doctor", False) + tui.dim("    check the connection")])
        tui.panel("Signed in", [tui.teal("Welcome, ", True) + tui.accent(name, True), "", "Next steps:", *next_steps], tone="teal")
        await ctx.aclose()
        return 0

    try:
        rc = run(flow())
    except (KeyboardInterrupt, EOFError):
        print()
        out.warn("Login cancelled.")
        return 130
    except ArcivoError as exc:
        print()
        out.err(f"{exc.code}: {exc}")
        return 1
    if rc == 0 and args.open_gui:
        from ..gui.app import main as gui_main
        return gui_main([])
    return rc


def cmd_logout(args: argparse.Namespace) -> int:
    ctx = _ctx(args)
    if not args.yes and input("Log out and remove the local session? [y/N] ").lower() not in ("y", "yes"):
        return 1
    run(ctx.auth.logout(revoke_remote=not args.local_only, forget_api=args.forget_api))
    if ctx.config.settings.privacy.clear_cache_on_logout:
        ctx.cache.clear()
    out.ok("Logged out. The local index is kept; use `arcivo db reset-index` to remove it.")
    return 0


def _describe_connection(info: dict) -> str:
    conn = info.get("connection")
    if conn:
        state = "connected" if conn.get("connected") else "disconnected"
        parts = [state, f"DC {conn.get('dc_id')}" if conn.get("dc_id") else "", conn.get("server") or "",
                 f"layer {conn.get('layer')}" if conn.get("layer") else "",
                 f"{conn.get('latency_ms'):.0f} ms" if conn.get("latency_ms") else ""]
        return " · ".join(p for p in parts if p)
    err = info.get("connection_error") or ""
    return "not signed in (run `arcivo login`)" if err == "NotAuthenticatedError" else (f"unavailable ({err})" if err else "—")


def cmd_status(args: argparse.Namespace) -> int:
    from ..services.account import account_overview
    ctx = _ctx(args)

    async def go() -> dict[str, Any]:
        try:
            return await account_overview(ctx)
        finally:
            await ctx.aclose()

    info = run(go())
    if args.json:
        out.dump_json(info)
        return 0
    out.title(f"{APP_NAME} {__version__}")
    u = info.get("user") or {}
    rows = [("Account", f"{u.get('name', '—')} @{u.get('username') or '—'}  id {u.get('id', '—')}"),
            ("Phone", u.get("phone", "—")), ("Authorized", info.get("authorized")), ("Session", info.get("session_status")),
            ("Credential store", info.get("credential_store")),
            ("Connection", _describe_connection(info)),
            ("Messages indexed", info.get("messages", 0)), ("Database", f"{info['database_path']} ({human_size(info['database_bytes'])})"),
            ("Cache", human_size(info["cache"]["disk_bytes"]))]
    if info.get("sync"):
        s = info["sync"]
        fmt = lambda ts: datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "never"  # noqa: E731
        rows += [("Initial sync", "complete" if s["initial_complete"] else "incomplete"),
                 ("Last incremental", fmt(s["last_incremental"])), ("Last full", fmt(s["last_full_sync"]))]
    for k, v in rows:
        print(f"  {out.c(k.ljust(18), '2')} {v}")
    return 0


# --------------------------------------------------------------------------- jobs
async def _run_job(ctx, kind: str, title: str, params: dict[str, Any]) -> Any:  # type: ignore[no-untyped-def]
    job = ctx.jobs.submit(kind, title, params)
    while job.status.value not in ("completed", "partial", "failed", "cancelled", "interrupted"):
        p = job.progress
        extra = f" {human_size(p.bytes_done)}/{human_size(p.bytes_total)} {human_size(p.speed_bps)}/s" if p.bytes_total else ""
        eta = f" ETA {human_duration(p.eta_s)}" if p.eta_s else ""
        out.progress_line(f"{out.bar(p.fraction)} {p.phase:<8} {p.done + p.skipped}/{p.total or '?'} "
                          f"failed {p.failed}{extra}{eta}")
        await asyncio.sleep(0.25)
    print()
    return job


def cmd_sync(args: argparse.Namespace) -> int:
    ctx = _ctx(args)

    async def go() -> int:
        try:
            if not await ctx.gateway().is_authorized():
                out.err("Not logged in. Run `arcivo login` first.")
                return 2
            job = await _run_job(ctx, "sync", f"Sync ({args.mode})", {"mode": args.mode})
            if job.status.value != "completed":
                out.err(f"Sync {job.status.value}: {job.error}")
                return 1
            r = job.result
            out.ok(f"{r['mode']} sync: {r['fetched']} fetched, {r.get('updated', 0)} re-checked, {r['deleted']} removed, "
                   f"{r['total']} indexed in {r['duration_s']}s")
            return 0
        finally:
            await ctx.aclose()

    return run(go())


def _query(args: argparse.Namespace) -> str:
    return " ".join(args.query or [])


def cmd_search(args: argparse.Namespace) -> int:
    ctx = _ctx(args)
    aid = ctx.require_account()
    q = _query(args)
    total = ctx.search.count(aid, q)
    if args.count:
        print(total)
        return 0
    rows = ctx.search.page(aid, q, args.offset, args.limit, args.sort or "date", not args.asc)
    if args.json:
        out.dump_json([dict(r) for r in rows])
        return 0
    data = [{"id": r["id"], "date": datetime.fromtimestamp(r["date_ts"]).strftime("%Y-%m-%d %H:%M"), "type": r["media_type"],
             "size": human_size(r["file_size"]) if r["file_size"] else "", "from": r["sender_name"] or r["chat_name"] or "",
             "content": r["file_name"] or r["text"] or ""} for r in rows]
    out.table(data, [("id", "ID"), ("date", "Date"), ("type", "Type"), ("size", "Size"), ("from", "From"), ("content", "Content")])
    print(out.c(f"\n{len(rows)} of {total} result(s)", "2"))
    return 0


def _confirm_delete(ctx, aid: int, ids: list[int], yes: bool) -> str | None:  # type: ignore[no-untyped-def]
    plan = ctx.deleter.plan(aid, ids)
    if not plan.count:
        out.warn("Nothing to delete.")
        return None
    out.title("Deletion review")
    print(f"  Messages : {plan.count}")
    print("  Types    : " + ", ".join(f"{k} {v}" for k, v in sorted(plan.by_type.items(), key=lambda x: -x[1])))
    print(f"  Size     : {human_size(plan.total_bytes)}")
    if plan.first_ts:
        print(f"  Dates    : {datetime.fromtimestamp(plan.first_ts):%Y-%m-%d} → {datetime.fromtimestamp(plan.last_ts):%Y-%m-%d}")
    if plan.tagged:
        out.warn(f"{plan.tagged} of these messages have local tags.")
    out.warn("Messages will be permanently deleted from Telegram. This CANNOT be undone.")
    if yes and os.environ.get("ARCIVO_ALLOW_NONINTERACTIVE_DELETE") == "1":
        return plan.token
    typed = input(f"Type DELETE {plan.count} to confirm: ").strip()
    if typed != f"DELETE {plan.count}":
        out.warn("Cancelled — nothing was deleted.")
        return None
    return plan.token


def cmd_export(args: argparse.Namespace) -> int:
    from ..services.export import ExportSpec
    ctx = _ctx(args)
    aid = ctx.require_account()
    s = ctx.config.settings
    ids = None
    if args.ids_file:
        ids = [int(x) for x in Path(args.ids_file).read_text().split() if x.strip().isdigit()]
    spec = ExportSpec(output_dir=args.out or s.export_dir, query=_query(args), ids=ids, name=args.name,
                      formats=[f for f in args.format.split(",") if f] if args.format != "none" else [],
                      include_text=not args.no_text, include_metadata=not args.no_metadata, download_media=args.media,
                      media_types=args.types.split(",") if args.types else None,
                      folder_template=args.folder_template or s.export.folder_template,
                      file_template=args.file_template or s.export.file_template, propose_delete=args.delete_after,
                      sort_desc=False, language=s.appearance.language)
    spec.validate()
    pv = ctx.exporter.preview(aid, spec)
    out.title("Export preview")
    print(f"  Messages: {pv['messages']}   Files: {pv['files']}   Estimated download: {human_size(pv['estimated_bytes'])}")
    for p in pv["sample_paths"]:
        print(out.c(f"    {p}", "2"))
    if not pv["messages"]:
        out.warn("Nothing matches.")
        return 1

    async def go() -> int:
        try:
            if spec.download_media and not await ctx.gateway().is_authorized():
                out.err("Media download needs a Telegram session. Run `arcivo login`.")
                return 2
            job = await _run_job(ctx, "export", spec.name, {**spec.to_params(), "account_id": aid})
            r = job.result
            if job.status.value not in ("completed", "partial"):
                out.err(f"Export {job.status.value}: {job.error}")
                return 1
            out.ok(f"Exported {r['verified']} message(s) to {r['output_dir']}  (failed {job.progress.failed})")
            print(out.c(f"  Report: {r['report_html']}", "2"))
            if args.delete_after and r.get("delete_candidates"):
                print()
                out.title("Post-export deletion (optional)")
                print("Only messages whose export was fully verified are included.")
                token = _confirm_delete(ctx, aid, r["delete_candidates"], args.yes)
                if token:
                    plan = ctx.deleter.plan(aid, r["delete_candidates"])
                    params = ctx.deleter.job_params(aid, plan, token, reason="post-export", source_job=job.id)
                    dj = await _run_job(ctx, "delete", "Delete exported messages", params)
                    out.ok(f"Deleted {dj.result.get('deleted', 0)}; failed {dj.progress.failed}. Report: {dj.result.get('report_html')}")
            return 0 if job.status.value == "completed" else 3
        finally:
            await ctx.aclose()

    return run(go())


def cmd_delete(args: argparse.Namespace) -> int:
    ctx = _ctx(args)
    aid = ctx.require_account()
    ids = [int(i) for i in args.ids.split(",")] if args.ids else ctx.search.ids(aid, _query(args))
    if not args.ids and not _query(args):
        out.err("Refusing to delete everything without a query. Pass a query or --ids.")
        return 2
    token = _confirm_delete(ctx, aid, ids, args.yes)
    if not token:
        return 1

    async def go() -> int:
        try:
            plan = ctx.deleter.plan(aid, ids)
            job = await _run_job(ctx, "delete", "Delete messages", ctx.deleter.job_params(aid, plan, token))
            out.ok(f"Deleted {job.result.get('deleted', 0)}, failed {job.progress.failed}. Report: {job.result.get('report_html')}")
            return 0 if job.status.value == "completed" else 3
        finally:
            await ctx.aclose()

    return run(go())


# --------------------------------------------------------------------------- analytics
def cmd_stats(args: argparse.Namespace) -> int:
    from ..services.analytics import TimeRange
    ctx = _ctx(args)
    aid = ctx.require_account()
    days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365, "all": None}[args.range]
    rng = TimeRange.last(days)
    a = ctx.analytics
    data = {"overview": a.overview(aid, rng), "types": a.by_type(aid, rng), "top_senders": a.top(aid, "senders", 10, rng),
            "top_chats": a.top(aid, "chats", 10, rng), "extensions": a.top(aid, "extensions", 10, rng),
            "timeline": a.timeline(aid, args.bucket, rng), "hours": a.hours(aid, rng), "weekdays": a.weekdays(aid, rng),
            "size_distribution": a.size_distribution(aid, rng)}
    if args.json:
        out.dump_json(data)
        return 0
    ov = data["overview"]
    out.title(f"Overview ({args.range})")
    for k in ("messages", "files", "images", "videos", "audio", "voice", "documents", "links", "texts", "stickers", "senders",
              "channels", "forwarded", "last_7d", "last_30d"):
        print(f"  {k.replace('_', ' ').ljust(12)} {ov[k]:>10,}")
    print(f"  {'total size'.ljust(12)} {human_size(ov['total_bytes']):>10}")
    out.title("\nBy type")
    out.table([{**r, "bytes": human_size(r["bytes"])} for r in data["types"]], [("media_type", "Type"), ("n", "Count"), ("bytes", "Size")])
    out.title("\nTop senders")
    out.table(data["top_senders"], [("label", "Sender"), ("n", "Messages")])
    out.title("\nTop chats / channels")
    out.table(data["top_chats"], [("label", "Chat"), ("chat_type", "Kind"), ("n", "Messages")])
    out.title(f"\nTimeline ({args.bucket})")
    peak = max((r["n"] for r in data["timeline"]), default=1)
    for r in data["timeline"][-24:]:
        print(f"  {r['bucket']:<12} {out.bar(r['n'] / peak, 30)} {r['n']}")
    return 0


def cmd_storage(args: argparse.Namespace) -> int:
    ctx = _ctx(args)
    aid = ctx.require_account()
    if args.duplicates:
        groups = ctx.storage.duplicates(aid, args.duplicates, limit=args.limit)
        if args.json:
            out.dump_json([{"key": g.key, "confidence": g.confidence, "wasted": g.wasted, "members": g.members} for g in groups])
            return 0
        out.title(f"Duplicate groups ({args.duplicates}) — nothing is deleted automatically")
        for g in groups:
            print(f"  {out.c(g.confidence, '33')} {len(g.members)}× {human_size(g.size)} (wasted {human_size(g.wasted)}): "
                  + ", ".join(f"#{m['id']}" for m in g.members))
        return 0
    b = ctx.storage.breakdown(aid)
    if args.json:
        out.dump_json({"breakdown": b, "large": ctx.storage.large_files(aid, limit=args.limit)})
        return 0
    out.title(f"Storage — total {human_size(b['total_bytes'])}")
    for cat in b["categories"]:
        print(f"  {cat['category']:<10} {out.bar(cat['share'], 30)} {human_size(cat['bytes']):>10}  ({cat['n']} files)")
    out.title("\nLargest files")
    out.table([{**r, "size": human_size(r["file_size"])} for r in ctx.storage.large_files(aid, limit=args.limit)],
              [("id", "ID"), ("media_type", "Type"), ("size", "Size"), ("file_name", "Name")])
    return 0


# --------------------------------------------------------------------------- organisation
def cmd_tags(args: argparse.Namespace) -> int:
    ctx = _ctx(args)
    org = ctx.org
    if args.action == "list":
        out.table([t.__dict__ for t in org.list_tags()], [("id", "ID"), ("name", "Tag"), ("color", "Color"), ("count", "Messages")])
        return 0
    if args.action == "create":
        t = org.create_tag(args.name, args.color or "#7C83FD")
        out.ok(f"Created tag {t.name}")
        return 0
    tag = ctx.tags.get_by_name(args.name)
    if tag is None:
        out.err(f"No tag named {args.name!r}")
        return 1
    if args.action == "delete":
        org.delete_tag(tag.id)
        out.ok("Deleted tag (messages are untouched)")
        return 0
    aid = ctx.require_account()
    ids = ctx.search.ids(aid, _query(args))
    n = org.tag(aid, tag.id, ids, remove=args.action == "remove")
    out.ok(f"{'Removed' if args.action == 'remove' else 'Applied'} tag {tag.name} on {n} message(s)")
    return 0


def cmd_collections(args: argparse.Namespace) -> int:
    ctx = _ctx(args)
    aid = ctx.account_id
    if args.action == "list":
        out.table([c.__dict__ for c in ctx.org.list_collections(aid)], [("id", "ID"), ("name", "Name"), ("query", "Query"), ("count", "Matches")])
    elif args.action == "create":
        c = ctx.org.save_collection(args.name, _query(args))
        out.ok(f"Saved collection #{c.id} {c.name}")
    elif args.action == "delete":
        ctx.org.delete_collection(int(args.name))
        out.ok("Deleted")
    elif args.action == "run":
        col = ctx.collections.get(int(args.name))
        if not col:
            out.err("not found")
            return 1
        args.query = [col.query]
        args.offset, args.limit, args.sort, args.asc, args.json, args.count = 0, 50, col.sort_key, not col.sort_desc, False, False
        return cmd_search(args)
    return 0


# --------------------------------------------------------------------------- maintenance
def cmd_db(args: argparse.Namespace) -> int:
    from ..db.migrator import current_version, migrate, pending
    ctx = _ctx(args)
    db = ctx.db
    if args.action == "info":
        print(f"Path: {db.path}\nSize: {human_size(db.size_bytes())}\nSchema version: {current_version(db)}\n"
              f"Pending migrations: {len(pending(db))}\nMessages: {db.scalar('SELECT count(*) FROM messages')}")
    elif args.action == "migrate":
        out.ok(f"Applied: {migrate(db, ctx.paths.database_dir / 'backups') or 'nothing to do'}")
    elif args.action == "check":
        res = db.integrity_check()
        (out.ok if res == "ok" else out.err)(f"integrity_check: {res}")
    elif args.action == "vacuum":
        before = db.size_bytes()
        db.optimize_fts()
        db.vacuum()
        out.ok(f"Vacuumed: {human_size(before)} → {human_size(db.size_bytes())}")
    elif args.action == "backup":
        target = Path(args.path or ctx.paths.database_dir / "backups" / f"arcivo-{datetime.now():%Y%m%d-%H%M%S}.db")
        db.backup_to(target)
        out.ok(f"Backup written to {target}")
    elif args.action == "reset-index":
        if input("Remove all indexed messages (tags/collections are kept)? Type RESET: ") != "RESET":
            return 1
        with db.transaction() as c:
            c.execute("DELETE FROM messages")
            c.execute("DELETE FROM links")
            c.execute("UPDATE sync_state SET initial_complete = 0, checkpoint_id = 0, max_message_id = 0, total_synced = 0")
        out.ok("Index cleared. Run `arcivo sync` to rebuild it.")
    return 0


def cmd_cache(args: argparse.Namespace) -> int:
    ctx = _ctx(args)
    if args.action == "clear":
        n = ctx.cache.clear(args.kind)
        out.ok(f"Cleared {n} cache entr{'y' if n == 1 else 'ies'} (database and session untouched)")
    else:
        st = ctx.cache.stats()
        print(f"Path: {st['path']}\nOn disk: {human_size(st['disk_bytes'])} in {st['disk_files']} files (limit {human_size(st['limit_bytes'])})")
        for k, v in st["by_kind"].items():
            print(f"  {k}: {v['files']} files, {human_size(v['bytes'])}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    ctx = _ctx(args)
    if args.action == "path":
        print(ctx.paths.config_file)
        return 0
    data = ctx.config.settings.to_dict()
    if args.action == "show":
        out.dump_json(data)
        return 0
    keys = args.key.split(".")
    node: Any = data
    for k in keys[:-1]:
        node = node[k]
    if args.action == "get":
        out.dump_json(node[keys[-1]])
        return 0
    old = node[keys[-1]]
    val: Any = args.value
    if isinstance(old, bool):
        val = args.value.lower() in ("1", "true", "yes", "on")
    elif isinstance(old, int):
        val = int(args.value)
    elif isinstance(old, float):
        val = float(args.value)
    node[keys[-1]] = val
    from ..core.config import Settings
    ctx.config.settings = Settings.from_dict(data)
    ctx.config.save()
    out.ok(f"{args.key} = {val!r}")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    from ..core.paths import resolve_paths
    log_file = resolve_paths().logs_dir / "arcivo.log"
    if args.export:
        import shutil
        shutil.copy(log_file, args.export)
        out.ok(f"Logs copied to {args.export} (already redacted)")
        return 0
    if not log_file.exists():
        out.warn("No log file yet.")
        return 0
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    if args.level:
        lines = [ln for ln in lines if f" {args.level.upper()}" in ln]
    print("\n".join(lines[-args.tail:]))
    return 0


def cmd_menu(args: argparse.Namespace) -> int:
    from .menu import run_menu
    if args.demo:
        os.environ["ARCIVO_DEMO"] = "1"
    return run_menu()


def cmd_doctor(args: argparse.Namespace) -> int:
    from . import tui
    from .doctor import run_checks
    ctx = _ctx(args)
    tui.banner()

    async def go() -> int:
        try:
            return await run_checks(ctx)
        finally:
            await ctx.aclose()

    return run(go())


def cmd_proxy(args: argparse.Namespace) -> int:
    from ..telegram.proxy import parse_proxy_link
    ctx = _ctx(args)
    n = ctx.config.settings.network
    if args.action == "off":
        n.proxy_type = "none"
    elif args.action == "set":
        if args.link:
            data = parse_proxy_link(args.link)
            if not data:
                out.err("Unrecognised proxy link.")
                return 2
            for k, v in data.items():
                setattr(n, k, v)
        else:
            if not (args.type and args.host and args.port):
                out.err("Use --link, or --type with --host and --port.")
                return 2
            n.proxy_type, n.proxy_host, n.proxy_port = args.type, args.host, args.port
            n.proxy_username, n.proxy_password, n.proxy_secret = args.user or "", args.password or "", args.secret or ""
    if args.action in ("set", "off"):
        ctx.config.save()
        out.ok(f"Proxy: {n.describe()}")
        return 0
    print(f"Proxy: {n.describe()}" + (f"  user={n.proxy_username}" if n.enabled and n.proxy_username else ""))
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    from ..gui.app import main as gui_main
    return gui_main(["--demo"] if args.demo else [])


def cmd_version(args: argparse.Namespace) -> int:
    import platform
    import sqlite3
    try:
        import telethon
        tv = telethon.__version__
    except Exception:
        tv = "?"
    print(f"{APP_NAME} {__version__} (build {BUILD})\nPython {platform.python_version()} · SQLite {sqlite3.sqlite_version} · "
          f"Telethon {tv} · {platform.system()} {platform.release()}")
    return 0


# --------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="arcivo", description=f"{APP_NAME} — archive manager for your Telegram Saved Messages "
                                "(unofficial; uses the official Telegram API).",
                                epilog="Run `arcivo <command> -h` for details. Search syntax: `arcivo search-help`.")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="also log to the console")
    p.add_argument("--demo", action="store_true", help="use the offline demo account with synthetic data")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    def add(name: str, fn, help_: str, aliases: list[str] | None = None) -> argparse.ArgumentParser:  # type: ignore[no-untyped-def]
        sp = sub.add_parser(name, help=help_, description=help_, aliases=aliases or [])
        sp.set_defaults(func=fn)
        return sp

    sp = add("login", cmd_login, "Log in to Telegram (API ID/hash, phone, code, 2FA) and store the session securely")
    sp.add_argument("--api-id")
    sp.add_argument("--phone")
    sp.add_argument("--reset-api", action="store_true", help="re-enter API credentials")
    sp.add_argument("--open-gui", action="store_true", help="launch the desktop app after login")
    sp = add("logout", cmd_logout, "Log out and remove the local session")
    sp.add_argument("--forget-api", action="store_true", help="also remove API ID/hash")
    sp.add_argument("--local-only", action="store_true", help="do not revoke the session on Telegram's servers")
    sp.add_argument("-y", "--yes", action="store_true")
    sp = add("status", cmd_status, "Show account, session, connection and sync status", ["info"])
    sp.add_argument("--json", action="store_true")
    sp = add("sync", cmd_sync, "Synchronise Saved Messages into the local index")
    sp.add_argument("--mode", choices=["auto", "initial", "incremental", "full"], default="auto")

    sp = add("search", cmd_search, "Search the local index (offline)", ["find"])
    sp.add_argument("query", nargs="*")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--offset", type=int, default=0)
    sp.add_argument("--sort", choices=["date", "size", "name", "type", "sender", "chat", "duration", "id"])
    sp.add_argument("--asc", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--count", action="store_true", help="print only the number of matches")
    add("search-help", lambda a: print(SEARCH_HELP) or 0, "Explain the search syntax")

    sp = add("export", cmd_export, "Export messages (metadata and/or media)")
    sp.add_argument("query", nargs="*", help="search query selecting messages (empty = all)")
    sp.add_argument("--format", default="json", help="comma list: json,jsonl,csv,txt,html,md or 'none'")
    sp.add_argument("--out", help="output directory")
    sp.add_argument("--name", default="Arcivo Export")
    sp.add_argument("--media", action="store_true", help="download media files")
    sp.add_argument("--types", help="restrict downloaded media types, e.g. audio,document")
    sp.add_argument("--folder-template", help="e.g. '{chat}/{year}/{month}/{type}'")
    sp.add_argument("--file-template", help="e.g. '{date}_{sender}_{filename}'")
    sp.add_argument("--no-text", action="store_true", help="exclude message text/captions")
    sp.add_argument("--no-metadata", action="store_true", help="exclude metadata fields")
    sp.add_argument("--ids-file", help="file with message ids (whitespace separated)")
    sp.add_argument("--delete-after", action="store_true", help="after a verified export, offer to delete the exported messages")
    sp.add_argument("-y", "--yes", action="store_true", help=argparse.SUPPRESS)

    sp = add("delete", cmd_delete, "Delete messages from Telegram (with review and typed confirmation)")
    sp.add_argument("query", nargs="*")
    sp.add_argument("--ids", help="comma separated message ids")
    sp.add_argument("-y", "--yes", action="store_true", help=argparse.SUPPRESS)

    sp = add("stats", cmd_stats, "Statistics & analytics", ["statistics"])
    sp.add_argument("--range", choices=["24h", "7d", "30d", "90d", "1y", "all"], default="all")
    sp.add_argument("--bucket", choices=["day", "week", "month", "year"], default="month")
    sp.add_argument("--json", action="store_true")
    sp = add("storage", cmd_storage, "Storage analyzer, large files and duplicate detection")
    sp.add_argument("--duplicates", choices=["media_id", "hash", "name_size", "size_duration"])
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--json", action="store_true")

    sp = add("tags", cmd_tags, "Manage local tags")
    sp.add_argument("action", choices=["list", "create", "delete", "apply", "remove"])
    sp.add_argument("name", nargs="?")
    sp.add_argument("query", nargs="*")
    sp.add_argument("--color")
    sp = add("collections", cmd_collections, "Smart collections (saved searches)")
    sp.add_argument("action", choices=["list", "create", "delete", "run"])
    sp.add_argument("name", nargs="?", help="name (create) or id (delete/run)")
    sp.add_argument("query", nargs="*")

    sp = add("db", cmd_db, "Database management")
    sp.add_argument("action", choices=["info", "migrate", "check", "vacuum", "backup", "reset-index"])
    sp.add_argument("path", nargs="?")
    sp = add("cache", cmd_cache, "Cache management")
    sp.add_argument("action", choices=["info", "clear"])
    sp.add_argument("--kind", choices=["thumb", "preview"])
    sp = add("config", cmd_config, "Read or change settings")
    sp.add_argument("action", choices=["show", "get", "set", "path"])
    sp.add_argument("key", nargs="?")
    sp.add_argument("value", nargs="?")
    sp = add("logs", cmd_logs, "Show or export logs (secrets are redacted)")
    sp.add_argument("--tail", type=int, default=100)
    sp.add_argument("--level", choices=["debug", "info", "warning", "error"])
    sp.add_argument("--export")
    sp = add("menu", cmd_menu, "Interactive console home screen (default when started without a command)", ["tui", "home"])
    sp.add_argument("--demo", action="store_true", help=argparse.SUPPRESS)
    add("doctor", cmd_doctor, "Check the connection to Telegram step by step (credentials, proxy, servers, session)", ["check"])
    sp = add("proxy", cmd_proxy, "Show or change the proxy used for Telegram (SOCKS5, HTTP, MTProto)")
    sp.add_argument("action", choices=["show", "set", "off"], nargs="?", default="show")
    sp.add_argument("--link", help="tg://proxy?…, https://t.me/proxy?… or socks5://user:pass@host:port")
    sp.add_argument("--type", choices=["socks5", "http", "mtproto"])
    sp.add_argument("--host")
    sp.add_argument("--port", type=int)
    sp.add_argument("--user")
    sp.add_argument("--password")
    sp.add_argument("--secret", help="MTProto secret (hex)")
    sp = add("gui", cmd_gui, "Launch the desktop application")
    sp.add_argument("--demo", action="store_true")
    add("version", cmd_version, "Show version information")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        if sys.stdin.isatty() and sys.stdout.isatty():
            if args.demo:
                os.environ["ARCIVO_DEMO"] = "1"
            from .menu import run_menu
            return run_menu()
        parser.print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        out.err("Interrupted.")
        return 130
    except ArcivoError as exc:
        hint = {"not_authenticated": "Run `arcivo login`.", "session_invalid": "Your session expired or was revoked; run `arcivo login`.",
                "rate_limited": f"Telegram asked to wait {int(exc.retry_after or 0)}s. Try again later.",
                "network": "Check your internet connection (or VPN/proxy) and try again – `arcivo doctor` helps."}.get(exc.code, "")
        out.err(f"{exc.code}: {exc} {hint}".strip())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
