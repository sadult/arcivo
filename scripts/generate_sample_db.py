"""Create a standalone sample database filled with synthetic Saved Messages.

    python scripts/generate_sample_db.py [--out sample/arcivo-sample.db] [--messages 4000] [--seed 7]

Useful for UI work, bug reports and benchmarking without a Telegram account. The data is
entirely generated (fake names, files and links) – no real messages are involved.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


async def build(out: Path, n: int, seed: int) -> None:
    from arcivo.context import AppContext
    from arcivo.core.paths import AppPaths
    from arcivo.sample_data import generate
    from arcivo.telegram.fake import FakeGateway

    tmp = Path(tempfile.mkdtemp(prefix="arcivo-sample-"))
    paths = AppPaths(config_dir=tmp / "config", data_dir=tmp / "data", portable=True)
    ctx = AppContext(paths, gateway=FakeGateway(generate(n, seed=seed)), database=out, log_console=False)
    ctx.config.settings.sync.request_delay_s = 0
    try:
        result = await ctx.sync.sync("initial")
        aid = ctx.account_id
        tags = {t.name: t.id for t in ctx.org.list_tags()}
        if "Work" in tags:
            ctx.org.tag(aid, tags["Work"], ctx.search.ids(aid, "type:document")[:80])
        if "Music" in tags:
            ctx.org.tag(aid, tags["Music"], ctx.search.ids(aid, "type:audio")[:50])
        ctx.org.set_flag(aid, ctx.search.ids(aid, "size:>50MB")[:15], True)
        ctx.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        print(f"wrote {out} – {result['total']} messages")
    finally:
        await ctx.aclose()
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "sample" / "arcivo-sample.db"))
    ap.add_argument("--messages", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        Path(str(out) + suffix).unlink(missing_ok=True)
    asyncio.run(build(out, a.messages, a.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
