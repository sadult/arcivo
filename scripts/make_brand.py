"""Generate Arcivo brand assets: SVG mark/wordmark, PNG sizes, multi-size ICO files.

Run:  python scripts/make_brand.py   (needs PySide6 + Pillow; works headless)
The mark is original artwork (a bookmark over archive layers) — it intentionally
does not resemble the Telegram logo, as required by the Telegram API terms.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "src" / "arcivo" / "assets" / "brand"
DOCS = ROOT / "docs" / "images"

MARK = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#9AA0FF"/>
      <stop offset="0.55" stop-color="#7C83FD"/>
      <stop offset="1" stop-color="#4F53E3"/>
    </linearGradient>
    <linearGradient id="page" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFFFFF"/>
      <stop offset="1" stop-color="#E9EAFF"/>
    </linearGradient>
  </defs>
  <rect x="8" y="8" width="240" height="240" rx="60" fill="url(#bg)"/>
  <!-- archive layers -->
  <rect x="58" y="70" width="140" height="22" rx="11" fill="#FFFFFF" fill-opacity="0.28"/>
  <rect x="50" y="100" width="156" height="22" rx="11" fill="#FFFFFF" fill-opacity="0.42"/>
  <!-- bookmark -->
  <path d="M86 124 Q86 112 98 112 L158 112 Q170 112 170 124 L170 206 Q170 213 164 209 L128 184 L92 209 Q86 213 86 206 Z" fill="url(#page)"/>
  <rect x="104" y="134" width="48" height="9" rx="4.5" fill="#7C83FD"/>
  <rect x="104" y="152" width="32" height="9" rx="4.5" fill="#7C83FD" fill-opacity="0.55"/>
  <circle cx="190" cy="66" r="13" fill="#36C2B4"/>
  <circle cx="190" cy="66" r="13" fill="none" stroke="#FFFFFF" stroke-opacity="0.6" stroke-width="3"/>
</svg>
"""

MONO = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect x="58" y="70" width="140" height="22" rx="11" fill="currentColor" fill-opacity="0.45"/>
  <rect x="50" y="100" width="156" height="22" rx="11" fill="currentColor" fill-opacity="0.7"/>
  <path d="M86 124 Q86 112 98 112 L158 112 Q170 112 170 124 L170 206 Q170 213 164 209 L128 184 L92 209 Q86 213 86 206 Z" fill="currentColor"/>
</svg>
"""


def wordmark(dark: bool) -> str:
    ink = "#E8ECF3" if dark else "#0B0D12"
    sub = "#9AA3B2" if dark else "#545D6E"
    mark = MARK.split(">", 1)[1].rsplit("</svg>", 1)[0]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="760" height="200" viewBox="0 0 760 200">
  <g transform="translate(10,22) scale(0.61)">{mark}</g>
  <text x="196" y="112" font-family="Inter, Segoe UI, Arial" font-weight="700" font-size="84" fill="{ink}" letter-spacing="-1">Arcivo</text>
  <text x="200" y="156" font-family="Inter, Segoe UI, Arial" font-weight="500" font-size="28" fill="{sub}">Your Saved Messages, organised.</text>
</svg>
"""


def main() -> int:
    from PySide6.QtCore import QByteArray, QRectF, Qt
    from PySide6.QtGui import QFontDatabase, QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    for f in (ROOT / "src" / "arcivo" / "assets" / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(f))
    BRAND.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    (BRAND / "arcivo-mark.svg").write_text(MARK, encoding="utf-8")
    (BRAND / "arcivo-mark-mono.svg").write_text(MONO, encoding="utf-8")
    (BRAND / "arcivo-wordmark-dark.svg").write_text(wordmark(True), encoding="utf-8")
    (BRAND / "arcivo-wordmark-light.svg").write_text(wordmark(False), encoding="utf-8")

    def render(svg: str, w: int, h: int, path: Path) -> None:
        r = QSvgRenderer(QByteArray(svg.encode()))
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r.render(p, QRectF(0, 0, w, h))
        p.end()
        img.save(str(path))

    sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
    for s in sizes:
        render(MARK, s, s, BRAND / f"arcivo-{s}.png")
    render(MARK, 128, 128, BRAND / "arcivo-mark-64.png")  # 64 px @2x for the sidebar
    render(MARK, 512, 512, BRAND / "arcivo-mark-256.png")  # 256 px @2x for About
    render(wordmark(True), 1520, 400, DOCS / "wordmark-dark.png")
    render(wordmark(False), 1520, 400, DOCS / "wordmark-light.png")
    render(MARK, 512, 512, DOCS / "logo.png")

    from PIL import Image
    big = Image.open(BRAND / "arcivo-256.png").convert("RGBA")
    ico_sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
    big.save(BRAND / "arcivo.ico", sizes=ico_sizes)
    big.save(BRAND / "installer.ico", sizes=ico_sizes)
    Image.open(BRAND / "arcivo-32.png").save(BRAND / "favicon.ico", sizes=[(16, 16), (32, 32)])
    # Inno Setup wizard images (BMP): large 164x314 and small 55x58 (scaled ×2 for HiDPI)
    for name, (w, h) in {"wizard-large.bmp": (328, 628), "wizard-small.bmp": (110, 116)}.items():
        canvas = Image.new("RGB", (w, h), (11, 13, 18))
        logo = Image.open(BRAND / "arcivo-512.png").convert("RGBA")
        side = int(min(w, h) * (0.55 if h > 300 else 0.8))
        logo = logo.resize((side, side), Image.LANCZOS)
        canvas.paste(logo, ((w - side) // 2, (h - side) // 2 - (60 if h > 300 else 0)), logo)
        canvas.save(BRAND / name)
    print("brand assets written to", BRAND)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
