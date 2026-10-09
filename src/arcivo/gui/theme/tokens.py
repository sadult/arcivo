"""Arcivo design tokens (single source of truth, mirrored in docs/design-system.md).

The visual language follows Apple's Human Interface Guidelines for macOS: system
colours, a quiet translucent-looking sidebar, large titles, grouped content on
rounded "inset" surfaces and restrained use of the accent colour.
"""

from __future__ import annotations

from dataclasses import dataclass

SPACE = {"xxs": 2, "xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20, "xxl": 28, "xxxl": 40}
RADIUS = {"xs": 4, "sm": 6, "md": 8, "lg": 12, "xl": 16, "pill": 999}
FONT = {"family": ["Inter", "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "Arial"],
        "mono": ["SF Mono", "Cascadia Mono", "Consolas", "JetBrains Mono", "monospace"],
        "size": {"caption": 11, "footnote": 12, "body": 13, "headline": 13, "title3": 15, "title2": 17, "title1": 22,
                 "large_title": 26},
        "weight": {"regular": 400, "medium": 500, "semibold": 600, "bold": 700}}
MOTION = {"fast": 120, "base": 180, "slow": 260}
BRAND = {"primary": "#7C83FD", "primary_deep": "#5B5FEF", "secondary": "#36C2B4", "ink": "#0B0D12"}

# Apple system colours (dark-mode variants read well on both appearances at chart sizes)
SYSTEM = {"red": "#FF453A", "orange": "#FF9F0A", "yellow": "#FFD60A", "green": "#30D158", "mint": "#63E6E2",
          "teal": "#40C8E0", "cyan": "#64D2FF", "blue": "#0A84FF", "indigo": "#5E5CE6", "purple": "#BF5AF2",
          "pink": "#FF375F", "brown": "#AC8E68", "gray": "#98989D"}
CHART = [SYSTEM[k] for k in ("indigo", "teal", "orange", "pink", "blue", "purple", "green", "yellow", "red", "gray")]
TYPE_COLORS = {"text": SYSTEM["gray"], "link": SYSTEM["green"], "photo": SYSTEM["teal"], "video": SYSTEM["blue"],
               "video_note": SYSTEM["cyan"], "animation": SYSTEM["pink"], "audio": SYSTEM["purple"], "voice": SYSTEM["orange"],
               "document": SYSTEM["red"], "sticker": SYSTEM["yellow"], "contact": SYSTEM["indigo"], "location": SYSTEM["mint"],
               "venue": SYSTEM["mint"], "poll": SYSTEM["indigo"], "other": SYSTEM["brown"]}
CATEGORY_COLORS = {"images": SYSTEM["teal"], "videos": SYSTEM["blue"], "audio": SYSTEM["purple"], "voice": SYSTEM["orange"],
                   "documents": SYSTEM["red"], "stickers": SYSTEM["yellow"], "text": SYSTEM["gray"], "other": SYSTEM["brown"]}


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str  # window/content background
    sidebar: str
    surface: str  # grouped content (cards, tables)
    surface_alt: str  # alternating rows, subtle fills
    elevated: str  # menus, popovers, toasts
    hover: str
    pressed: str
    border: str  # separators
    border_strong: str  # control borders
    text: str
    text_muted: str
    text_subtle: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    accent_text: str
    success: str
    warning: str
    danger: str
    info: str
    danger_soft: str
    selection: str
    shadow: str
    chart_grid: str
    control: str  # push buttons, text fields
    track: str  # segmented control / progress track
    segment: str  # selected segment
    sidebar_selected: str
    field: str  # search field fill


LIGHT = Palette(
    name="light", bg="#F5F5F7", sidebar="#EAEAEF", surface="#FFFFFF", surface_alt="#F5F5F7", elevated="#FFFFFF",
    hover="#EDEDF0", pressed="#E3E3E8", border="#E5E5EA", border_strong="#D1D1D6", text="#1D1D1F", text_muted="#6E6E73",
    text_subtle="#8E8E93", accent="#5856D6", accent_hover="#6765E0", accent_pressed="#4B49C2", accent_soft="#5856D61F",
    accent_text="#FFFFFF", success="#28A745", warning="#E08600", danger="#FF3B30", info="#007AFF", danger_soft="#FF3B3014",
    selection="#5856D6", shadow="#0000001F", chart_grid="#ECECF0", control="#FFFFFF", track="#E3E3E8", segment="#FFFFFF",
    sidebar_selected="#D8D8DE", field="#E3E3E8",
)

DARK = Palette(
    name="dark", bg="#1C1C1E", sidebar="#252527", surface="#2A2A2C", surface_alt="#2F2F31", elevated="#323234",
    hover="#38383B", pressed="#414144", border="#3A3A3C", border_strong="#4A4A4D", text="#F5F5F7", text_muted="#A1A1A6",
    text_subtle="#7C7C82", accent="#5E5CE6", accent_hover="#7270F0", accent_pressed="#4E4CD4", accent_soft="#5E5CE633",
    accent_text="#FFFFFF", success="#30D158", warning="#FF9F0A", danger="#FF453A", info="#0A84FF", danger_soft="#FF453A22",
    selection="#5E5CE6", shadow="#00000080", chart_grid="#343437", control="#3A3A3D", track="#323235", segment="#5A5A5E",
    sidebar_selected="#3A3A3D", field="#323235",
)


def palette(name: str) -> Palette:
    return LIGHT if name == "light" else DARK
