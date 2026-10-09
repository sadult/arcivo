"""Compose the README cover / GitHub social preview from the logo and a real screenshot.

    python scripts/make_cover.py   →  docs/images/cover.png (1280×640) and docs/images/banner.png (1600×560)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "src" / "arcivo" / "assets" / "brand"
FONTS = ROOT / "src" / "arcivo" / "assets" / "fonts"
SHOTS = ROOT / "docs" / "images" / "screenshots"
OUT = ROOT / "docs" / "images"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def background(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), "#141416")
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((-w * 0.25, -h * 0.9, w * 0.55, h * 0.9), fill=(124, 131, 253, 90))
    d.ellipse((w * 0.55, h * 0.35, w * 1.25, h * 1.6), fill=(54, 194, 180, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(int(h * 0.22)))
    img.paste(glow, (0, 0), glow)
    return img


def framed(shot: Image.Image, width: int) -> Image.Image:
    s = shot.convert("RGB").resize((width, int(width * shot.height / shot.width)), Image.LANCZOS)
    r = 18
    mask = Image.new("L", s.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s.width, s.height), r, fill=255)
    pad = 40
    out = Image.new("RGBA", (s.width + pad * 2, s.height + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 12, pad + s.width, pad + s.height + 12), r, fill=(0, 0, 0, 170))
    out = Image.alpha_composite(out, shadow.filter(ImageFilter.GaussianBlur(18)))
    out.paste(s, (pad, pad), mask)
    ImageDraw.Draw(out).rounded_rectangle((pad, pad, pad + s.width - 1, pad + s.height - 1), r, outline=(255, 255, 255, 40), width=2)
    return out


def compose(w: int, h: int, shot_w: int, name: str) -> None:
    img = background(w, h).convert("RGBA")
    shot = framed(Image.open(SHOTS / "dark-dashboard.png"), shot_w)
    sx = int(w * 0.47) - 40
    img.alpha_composite(shot, (sx, (h - shot.height) // 2 + 36))
    # soft left edge so the screenshot melts into the background
    edge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge)
    for i in range(90):
        ed.line([(sx + 40 + i, 0), (sx + 40 + i, h)], fill=(20, 20, 22, int(200 * (1 - i / 90) ** 2)))
    img.alpha_composite(edge)

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    scale = h / 640
    logo_s = int(84 * scale)
    logo = Image.open(BRAND / "arcivo-256.png").convert("RGBA").resize((logo_s, logo_s), Image.LANCZOS)
    left = int(64 * scale)
    block_h = int(330 * scale)
    top = (h - block_h) // 2
    overlay.alpha_composite(logo, (left, top))
    y = top + logo_s + int(16 * scale)
    d.text((left - 3, y), "Arcivo", font=font("Inter-Bold.ttf", int(68 * scale)), fill="#FFFFFF")
    y += int(86 * scale)
    d.text((left, y), "Your Saved Messages, organised.", font=font("Inter-Medium.ttf", int(25 * scale)), fill="#C9CCF8")
    y += int(40 * scale)
    d.text((left, y), "by Bitologist  ·  t.me/Bitologist  ·  github.com/sadult/arcivo", font=font("Inter-Medium.ttf", int(16 * scale)),
           fill="#8F94B8")
    y += int(52 * scale)
    f = font("Inter-SemiBold.ttf", int(15 * scale))
    x = left
    for c in ["Search", "Export", "Insights", "Duplicates", "Proxy"]:
        tw = d.textlength(c, font=f)
        cw = tw + 24 * scale
        if x + cw > sx + 20:
            break
        d.rounded_rectangle((x, y, x + cw, y + 30 * scale), int(15 * scale), fill=(124, 131, 253, 40), outline=(124, 131, 253, 130))
        d.text((x + 12 * scale, y + 5 * scale), c, font=f, fill="#E4E6FF")
        x += cw + 9 * scale
    img.alpha_composite(overlay)
    img.convert("RGB").save(OUT / name, optimize=True)
    print("wrote", OUT / name)


if __name__ == "__main__":
    compose(1280, 640, 980, "cover.png")
    compose(1600, 560, 1000, "banner.png")
