"""Stylesheet generation, colour helpers, fonts and the icon system.

The stylesheet recreates the macOS look (Apple HIG) with Qt style sheets:
flat sidebar with subtle selection, large titles, inset grouped cards,
6 px push buttons, segmented controls, alternating-row tables and thin
overlay-style scrollbars.
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ...core.paths import resource_path
from .tokens import FONT, RADIUS, Palette


def css(color: str) -> str:
    """Convert #RRGGBBAA (web order) into a Qt-compatible rgba() string."""
    c = color.lstrip("#")
    if len(c) == 8:
        r, g, b, a = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16)
        return f"rgba({r},{g},{b},{a})"
    return color


def qcolor(color: str) -> QColor:
    c = color.lstrip("#")
    if len(c) == 8:
        return QColor(int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16))
    return QColor(color)


def load_fonts() -> None:
    folder = resource_path("assets", "fonts")
    for f in sorted(folder.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))


def app_font(scale: float = 1.0) -> QFont:
    font = QFont()
    font.setFamilies(FONT["family"])
    font.setPixelSize(round(FONT["size"]["body"] * scale))
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


@lru_cache(maxsize=1024)
def _svg_pixmap(name: str, color: str, size: int, dpr: float) -> QPixmap:
    path = resource_path("assets", "icons", f"{name}.svg")
    data = path.read_text(encoding="utf-8") if path.exists() else resource_path("assets", "icons", "circle-help.svg").read_text()
    data = data.replace("currentColor", qcolor(color).name())
    renderer = QSvgRenderer(QByteArray(data.encode()))
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setOpacity(qcolor(color).alphaF())
    renderer.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    px.setDevicePixelRatio(dpr)
    return px


class Icons:
    """Theme-aware Lucide icons (ISC licensed), recoloured at runtime."""

    def __init__(self, pal: Palette, dpr: float = 2.0) -> None:
        self.pal = pal
        self.dpr = dpr

    def pixmap(self, name: str, color: str | None = None, size: int = 18) -> QPixmap:
        return _svg_pixmap(name, color or self.pal.text_muted, size, self.dpr)

    def icon(self, name: str, color: str | None = None, size: int = 18, active: str | None = None) -> QIcon:
        ic = QIcon()
        ic.addPixmap(self.pixmap(name, color, size), QIcon.Mode.Normal)
        ic.addPixmap(self.pixmap(name, active or color or self.pal.text, size), QIcon.Mode.Active)
        ic.addPixmap(self.pixmap(name, active or color or self.pal.text, size), QIcon.Mode.Selected)
        ic.addPixmap(self.pixmap(name, self.pal.text_subtle, size), QIcon.Mode.Disabled)
        return ic


ICON_SIZE = QSize(16, 16)

# ---------------------------------------------------------------- control glyphs (rendered to PNG for QSS url())
_GLYPHS = {
    "check": '<path d="M5 12.5l4.2 4.2L19 7" stroke-width="3.2"/>',
    "dash": '<path d="M6 12h12" stroke-width="3.2"/>',
    "updown": '<path d="M8 9.5l4-4 4 4M8 14.5l4 4 4-4" stroke-width="2.4"/>',
    "down": '<path d="M7 10l5 5 5-5" stroke-width="2.6"/>',
    "up": '<path d="M7 14l5-5 5 5" stroke-width="2.6"/>',
}


def _glyph_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "arcivo-ui"
    d.mkdir(parents=True, exist_ok=True)
    return d


@lru_cache(maxsize=64)
def glyph(name: str, color: str, size: int = 16) -> str:
    """Render a small control glyph to a PNG and return a QSS-friendly path."""
    path = _glyph_dir() / f"{name}-{qcolor(color).name().lstrip('#')}-{size}.png"
    if not path.exists():
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{qcolor(color).name()}" '
               f'stroke-linecap="round" stroke-linejoin="round">{_GLYPHS[name]}</svg>')
        img = QImage(size * 2, size * 2, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, size * 2, size * 2))
        p.end()
        img.save(str(path))
    return path.as_posix()


def stylesheet(p: Palette, scale: float = 1.0) -> str:
    r = RADIUS
    fs = lambda n: f"{round(n * scale)}px"  # noqa: E731
    mono = ", ".join(f'"{f}"' if " " in f else f for f in FONT["mono"])
    light = p.name == "light"
    check = glyph("check", "#FFFFFF")
    dash = glyph("dash", "#FFFFFF")
    updown = glyph("updown", p.text_muted)
    down, up = glyph("down", p.text_muted), glyph("up", p.text_muted)
    btn_border = p.border_strong if light else p.control
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {p.text}; background: transparent; selection-background-color: {p.selection}; selection-color: #FFFFFF; }}
QMainWindow, QDialog, #AppRoot, #Content {{ background: {p.bg}; }}
QToolTip {{ background: {p.elevated}; color: {p.text}; border: 1px solid {p.border_strong}; border-radius: {r['sm']}px; padding: 4px 8px; }}

/* ---------- sidebar (source list) ---------- */
#Sidebar {{ background: {p.sidebar}; border: none; border-right: 1px solid {p.border}; }}
#BrandName {{ font-size: {fs(15)}; font-weight: 700; }}
#DemoBadge {{ color: {p.text_muted}; background: {p.track}; border-radius: 4px; padding: 0 5px; font-size: {fs(10)}; font-weight: 600; }}
#NavSection {{ color: {p.text_subtle}; font-size: {fs(11)}; font-weight: 600; padding: 14px 10px 4px 10px; }}
QPushButton#NavButton {{ text-align: left; padding: 0 8px; min-height: 28px; max-height: 28px; border-radius: {r['sm']}px; border: none;
  background: transparent; color: {p.text}; font-weight: 400; }}
QPushButton#NavButton:hover {{ background: {css(p.shadow) if light else p.hover}; }}
QPushButton#NavButton:checked {{ background: {p.sidebar_selected}; font-weight: 500; }}
#SidebarFooter {{ border-top: 1px solid {p.border}; }}
#AccountName {{ font-weight: 600; font-size: {fs(12)}; }}
#SyncStatus {{ color: {p.text_subtle}; font-size: {fs(11)}; }}
QPushButton#JobsIndicator {{ text-align: left; border: none; background: {css(p.accent_soft)}; color: {p.accent};
  border-radius: {r['sm']}px; padding: 4px 8px; font-size: {fs(12)}; font-weight: 500; }}
QPushButton#JobsIndicator:hover {{ background: {p.sidebar_selected}; }}

/* ---------- page header ---------- */
#PageTitle {{ font-size: {fs(26)}; font-weight: 700; letter-spacing: -0.4px; }}
#PageSubtitle {{ color: {p.text_muted}; font-size: {fs(13)}; }}
#LargeValue {{ font-size: {fs(22)}; font-weight: 700; letter-spacing: -0.3px; }}

/* ---------- grouped content ---------- */
#Card, QFrame#Card, QFrame#Hero {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: {r['lg']}px; }}
#Card:hover[clickable="true"] {{ background: {p.surface_alt if light else p.hover}; }}
#CardTitle {{ font-size: {fs(13)}; font-weight: 600; }}
#CardSubtitle, #Muted {{ color: {p.text_muted}; }}
#Subtle {{ color: {p.text_subtle}; font-size: {fs(12)}; }}
#StatValue {{ font-size: {fs(26)}; font-weight: 600; letter-spacing: -0.5px; }}
#StatLabel {{ color: {p.text_muted}; font-size: {fs(12)}; font-weight: 500; }}
#SectionTitle {{ font-size: {fs(15)}; font-weight: 600; }}
#GroupHeader {{ color: {p.text_muted}; font-size: {fs(12)}; font-weight: 600; padding: 0 4px; }}
#PlainList, #MediaGrid {{ background: transparent; border: none; }}
#PlainList::item {{ padding: 7px 6px; border-radius: {r['sm']}px; border-bottom: 1px solid {p.border}; }}
#PlainList::item:selected {{ background: {p.selection}; color: #FFFFFF; }}
QListWidget#SettingsNav {{ background: transparent; border: none; }}
QListWidget#SettingsNav::item {{ padding: 6px 8px; border-radius: {r['sm']}px; color: {p.text}; }}
QListWidget#SettingsNav::item:hover {{ background: {p.hover}; }}
QListWidget#SettingsNav::item:selected {{ background: {p.sidebar_selected}; color: {p.text}; }}
#LogView {{ font-family: {mono}; font-size: {fs(12)}; background: {p.surface}; }}
QCheckBox[dropTarget="true"] {{ background: {css(p.accent_soft)}; border-radius: 6px; }}
QPushButton#StatusPill {{ background: transparent; border: none; border-radius: {r['sm']}px; padding: 3px 6px; color: {p.text_muted};
  font-size: {fs(12)}; text-align: left; }}
QPushButton#StatusPill:hover {{ color: {p.text}; background: {p.hover}; }}
QPushButton#Mono {{ font-family: {mono}; font-size: {fs(12)}; color: {p.text_muted}; background: {p.surface};
  border: 1px solid {p.border}; border-radius: {r['sm']}px; padding: 3px 8px; }}
QPushButton#Mono:hover {{ color: {p.text}; border-color: {p.accent}; }}
QLineEdit#Mono {{ font-family: {mono}; }}
#WizardStep {{ color: {p.text_subtle}; font-size: {fs(12)}; font-weight: 600; }}
#WizardStep[active="true"] {{ color: {p.accent}; }}
#Mono {{ font-family: {mono}; }}
#Divider {{ background: {p.border}; max-height: 1px; min-height: 1px; }}
#Banner {{ background: {css(p.accent_soft)}; border: none; border-radius: {r['md']}px; }}
#DangerBanner {{ background: {css(p.danger_soft)}; border: 1px solid {css(p.danger_soft)}; border-radius: {r['md']}px; }}
#Pill {{ background: {p.track}; color: {p.text_muted}; border-radius: 5px; padding: 1px 7px; font-size: {fs(11)}; font-weight: 600; }}
#LegendDot {{ border-radius: 4px; }}
#InsetRow {{ border-radius: {r['sm']}px; }}
#InsetRow:hover {{ background: {p.hover}; }}

/* ---------- buttons (push buttons) ---------- */
QPushButton {{ background: {p.control}; border: 1px solid {btn_border}; border-radius: {r['sm']}px; padding: 4px 12px;
  min-height: 20px; font-weight: 500; }}
QPushButton:hover {{ background: {p.hover if light else p.pressed}; }}
QPushButton:pressed {{ background: {p.pressed if light else p.border_strong}; }}
QPushButton:disabled {{ color: {p.text_subtle}; background: {p.surface_alt if light else p.surface}; }}
QPushButton:focus {{ border: 1px solid {p.accent}; }}
QPushButton[variant="primary"] {{ background: {p.accent}; color: {p.accent_text}; border: 1px solid {p.accent}; }}
QPushButton[variant="primary"]:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {p.accent_pressed}; }}
QPushButton[variant="primary"]:disabled {{ background: {p.track}; border-color: {p.track}; color: {p.text_subtle}; }}
QPushButton[variant="danger"] {{ background: {p.danger}; color: white; border: 1px solid {p.danger}; }}
QPushButton[variant="danger"]:disabled {{ background: {css(p.danger_soft)}; color: {p.text_subtle}; border-color: {css(p.danger_soft)}; }}
QPushButton[variant="ghost"], QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: {r['sm']}px; padding: 4px 8px;
  color: {p.accent}; }}
QToolButton {{ color: {p.text}; padding: 4px; }}
QPushButton[variant="ghost"]:hover, QToolButton:hover {{ background: {p.hover}; }}
QPushButton[variant="ghost"]:pressed, QToolButton:pressed {{ background: {p.pressed}; }}
QToolButton:checked {{ background: {p.sidebar_selected}; }}
QToolButton::menu-indicator {{ image: none; }}
#Segmented {{ background: {p.track}; border: none; border-radius: 7px; }}
QPushButton[variant="segment"] {{ border-radius: 5px; padding: 3px 12px; min-height: 18px; background: transparent; border: 1px solid transparent;
  color: {p.text}; font-weight: 500; }}
QPushButton[variant="segment"]:hover {{ background: {css(p.shadow) if light else p.hover}; }}
QPushButton[variant="segment"]:checked {{ background: {p.segment}; border: 1px solid {p.border_strong if light else p.segment}; font-weight: 600; }}

/* ---------- text fields ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QKeySequenceEdit, QPlainTextEdit, QTextEdit {{
  background: {p.control if light else p.surface_alt}; border: 1px solid {p.border_strong}; border-radius: {r['sm']}px;
  padding: 4px 8px; min-height: 20px; selection-background-color: {p.selection}; }}
QPlainTextEdit, QTextEdit {{ padding: 6px 8px; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QKeySequenceEdit:focus {{ border: 1px solid {p.accent}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {p.text_subtle}; }}
QLineEdit[invalid="true"] {{ border: 1px solid {p.danger}; }}
#SearchField {{ padding: 5px 10px 5px 30px; border-radius: 7px; background: {p.field}; border: 1px solid {p.field}; font-size: {fs(13)}; }}
#SearchField:focus {{ background: {p.control if light else p.surface_alt}; border: 1px solid {p.accent}; }}
QComboBox {{ padding-right: 24px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({updown}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {p.elevated}; border: 1px solid {p.border_strong}; border-radius: {r['md']}px; padding: 4px;
  selection-background-color: {p.selection}; selection-color: #FFFFFF; outline: 0; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QDateEdit::up-button {{ subcontrol-position: top right; width: 18px; border: none; }}
QSpinBox::down-button, QDoubleSpinBox::down-button, QDateEdit::down-button {{ subcontrol-position: bottom right; width: 18px; border: none; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QDateEdit::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QDateEdit::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
QDateEdit::drop-down {{ border: none; width: 20px; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {p.border_strong}; background: {p.control}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {p.accent}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; image: url({check}); }}
QCheckBox::indicator:indeterminate {{ background: {p.accent}; border-color: {p.accent}; image: url({dash}); }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #FFFFFF, stop:0.35 #FFFFFF,
  stop:0.42 {p.accent}, stop:1 {p.accent}); border-color: {p.accent}; }}
QCheckBox::indicator:disabled {{ background: {p.track}; border-color: {p.border}; }}
QSlider::groove:horizontal {{ height: 4px; background: {p.track}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 18px; height: 18px; margin: -7px 0; border-radius: 9px; background: #FFFFFF; border: 1px solid {p.border_strong}; }}

/* ---------- tables & lists ---------- */
QTableView, QTreeView, QListView, QListWidget, QTreeWidget, QTableWidget {{ background: {p.surface}; border: 1px solid {p.border};
  border-radius: {r['md']}px; gridline-color: transparent; alternate-background-color: {p.surface_alt};
  selection-background-color: {p.selection}; selection-color: #FFFFFF; }}
QTableView::item, QTreeView::item, QListWidget::item {{ padding: 3px 6px; border: none; }}
QTableView::item:hover, QTreeView::item:hover, QListView::item:hover, QListWidget::item:hover {{ background: {p.hover}; }}
QTableView::item:selected, QTreeView::item:selected, QListView::item:selected, QListWidget::item:selected {{ background: {p.selection}; color: #FFFFFF; }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{ background: {p.surface}; color: {p.text_muted}; border: none; border-bottom: 1px solid {p.border};
  border-right: 1px solid {p.border}; padding: 5px 8px; font-weight: 500; font-size: {fs(12)}; }}
QHeaderView::section:last {{ border-right: none; }}
QHeaderView::section:hover {{ color: {p.text}; }}
QHeaderView::down-arrow {{ image: url({down}); width: 10px; height: 10px; subcontrol-position: center right; padding-right: 4px; }}
QHeaderView::up-arrow {{ image: url({up}); width: 10px; height: 10px; subcontrol-position: center right; padding-right: 4px; }}
QTableCornerButton::section {{ background: {p.surface}; border: none; }}
QTreeView::branch {{ background: transparent; }}

/* ---------- tabs (rendered as a segmented control) ---------- */
QTabWidget::pane {{ border: none; top: 4px; }}
QTabWidget::tab-bar {{ left: 0; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: {p.track}; color: {p.text}; padding: 4px 14px; margin: 0; border: 1px solid {p.track}; font-weight: 500; }}
QTabBar::tab:first {{ border-top-left-radius: 7px; border-bottom-left-radius: 7px; }}
QTabBar::tab:last {{ border-top-right-radius: 7px; border-bottom-right-radius: 7px; }}
QTabBar::tab:only-one {{ border-radius: 7px; }}
QTabBar::tab:selected {{ background: {p.segment}; border: 1px solid {p.border_strong if light else p.segment}; border-radius: 6px; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ color: {p.text}; background: {p.pressed if light else p.hover}; }}

/* ---------- scrollbars (thin, overlay-like) ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px 2px 2px 0; }}
QScrollBar::handle:vertical {{ background: {css('#00000038') if light else css('#FFFFFF38')}; border-radius: 3px; min-height: 32px; margin: 0 1px; }}
QScrollBar::handle:vertical:hover {{ background: {css('#00000066') if light else css('#FFFFFF66')}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0 2px 2px 2px; }}
QScrollBar::handle:horizontal {{ background: {css('#00000038') if light else css('#FFFFFF38')}; border-radius: 3px; min-width: 32px; margin: 1px 0; }}
QScrollBar::handle:horizontal:hover {{ background: {css('#00000066') if light else css('#FFFFFF66')}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- menus, progress, misc ---------- */
QProgressBar {{ background: {p.track}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}
QMenu {{ background: {p.elevated}; border: 1px solid {p.border_strong}; border-radius: {r['md']}px; padding: 5px; }}
QMenu::item {{ padding: 4px 24px 4px 10px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p.selection}; color: #FFFFFF; }}
QMenu::item:disabled {{ color: {p.text_subtle}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 8px; }}
QMenu::icon {{ padding-left: 6px; }}
QStatusBar {{ background: {p.bg}; border-top: 1px solid {p.border}; color: {p.text_muted}; }}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background: {p.border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
#Toast {{ background: {p.elevated}; border: 1px solid {p.border_strong}; border-radius: {r['lg']}px; }}
#ToastTitle {{ font-weight: 600; }}
#Palette {{ background: {p.elevated}; border: 1px solid {p.border_strong}; border-radius: {r['lg']}px; }}
#Kbd {{ background: {p.track}; border: none; border-radius: 4px; padding: 1px 6px; font-size: {fs(11)}; color: {p.text_muted}; }}
#EmptyTitle {{ font-size: {fs(17)}; font-weight: 600; }}
QGroupBox {{ border: 1px solid {p.border}; border-radius: {r['lg']}px; margin-top: 22px; padding: 14px; background: {p.surface}; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 4px; padding: 0 4px; color: {p.text_muted}; }}
QDialog#Welcome {{ background: {p.surface}; }}
#WelcomeTitle {{ font-size: {fs(28)}; font-weight: 700; letter-spacing: -0.5px; }}
#FeatureTitle {{ font-size: {fs(14)}; font-weight: 600; }}
#FeatureText {{ color: {p.text_muted}; font-size: {fs(13)}; }}
"""
