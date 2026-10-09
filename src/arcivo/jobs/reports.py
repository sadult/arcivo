"""Job report generator (JSON + self-contained HTML)."""

from __future__ import annotations

import html
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import APP_NAME, BUILD, __version__
from ..domain.formatting import human_duration, human_size
from ..repositories.system import ReportRepository

SENSITIVE_PARAM_KEYS = {"api_hash", "session", "password", "phone", "code"}


def build_summary(job: Any, ctx: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    p = job.progress
    started = job.started_at or time.time()
    summary = {
        "app": f"{APP_NAME} {__version__} ({BUILD})",
        "job_id": job.id, "kind": job.kind, "title": job.title,
        "status": str(getattr(job.status, "value", job.status)),
        "started_at": datetime.fromtimestamp(started).astimezone().isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
        "duration_s": round(time.time() - started, 2),
        "total": p.total, "succeeded": p.done, "failed": p.failed, "skipped": p.skipped,
        "bytes": p.bytes_done, "bytes_human": human_size(p.bytes_done),
        "params": {k: v for k, v in job.params.items() if k not in SENSITIVE_PARAM_KEYS and k not in ("ids", "exclude_ids")},
        "errors": ctx.item_errors[:1000],
    }
    if job.params.get("ids"):
        summary["params"]["ids_count"] = len(job.params["ids"])
    if extra:
        summary.update(extra)
    return summary


def write_report(summary: dict[str, Any], directory: Path, repo: ReportRepository | None = None) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = directory / f"report_{summary['kind']}_{stamp}_{summary['job_id']}"
    jpath, hpath = base.with_suffix(".json"), base.with_suffix(".html")
    jpath.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    hpath.write_text(render_html(summary), encoding="utf-8")
    if repo is not None:
        repo.add(summary["job_id"], summary["kind"], summary, str(jpath), str(hpath))
    return jpath, hpath


def render_html(s: dict[str, Any]) -> str:
    e = html.escape
    status_color = {"completed": "#2BB673", "partial": "#F5A524", "failed": "#F2545B", "cancelled": "#8B95A7"}.get(s["status"], "#7C83FD")
    cards = [("Total", s["total"]), ("Succeeded", s["succeeded"]), ("Failed", s["failed"]), ("Skipped", s["skipped"]),
             ("Data", s["bytes_human"]), ("Duration", human_duration(s["duration_s"]))]
    errors = "".join(f"<tr><td>{e(str(x.get('id')))}</td><td>{e(str(x.get('error')))}</td></tr>" for x in s.get("errors", []))
    params = "".join(f"<tr><td>{e(str(k))}</td><td>{e(json.dumps(v, ensure_ascii=False, default=str))}</td></tr>"
                     for k, v in s.get("params", {}).items())
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(s['title'])} — report</title><style>
body{{font:14px/1.5 Inter,"Segoe UI",system-ui,sans-serif;background:#0E1116;color:#E6EAF0;margin:0;padding:32px}}
.wrap{{max-width:960px;margin:auto}}.st{{display:inline-block;padding:2px 10px;border-radius:99px;background:{status_color}22;color:{status_color};font-weight:600}}
.g{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:20px 0}}.c{{background:#161B22;border:1px solid #262D38;border-radius:12px;padding:14px}}
.c b{{display:block;font-size:22px}}.c span{{color:#8B95A7;font-size:12px}}table{{width:100%;border-collapse:collapse;background:#161B22;border-radius:12px;overflow:hidden}}
td{{border-bottom:1px solid #262D38;padding:8px 12px;vertical-align:top;word-break:break-all}}h2{{margin-top:28px;font-size:16px}}</style></head>
<body><div class="wrap"><h1>{e(s['title'])}</h1><span class="st">{e(s['status'])}</span> <span style="color:#8B95A7">{e(s['started_at'])} → {e(s['finished_at'])}</span>
<div class="g">{''.join(f'<div class="c"><b>{e(str(v))}</b><span>{e(k)}</span></div>' for k, v in cards)}</div>
<h2>Parameters</h2><table>{params}</table><h2>Errors ({len(s.get('errors', []))})</h2><table>{errors or '<tr><td>None 🎉</td></tr>'}</table>
<p style="color:#8B95A7;margin-top:24px">{e(s['app'])} · job {e(s['job_id'])}</p></div></body></html>"""
