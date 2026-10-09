"""Platform integration: application icon, Windows taskbar identity and native title bar.

Windows picks the taskbar icon from (1) the process' AppUserModelID group and
(2) the window's ``WM_SETICON`` big/small icons. Qt sets those from the window
icon, but only from the sizes it can find; we therefore provide every standard
size explicitly and, on Windows, also send ``WM_SETICON`` with icons loaded from
the multi-resolution ``arcivo.ico`` so the taskbar, Alt+Tab and title bar are
always crisp (and never fall back to the generic Python icon).
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from typing import Any

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

from .. import WINDOWS_APP_USER_MODEL_ID
from ..core.paths import resource_path

log = logging.getLogger(__name__)
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256, 512)


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    icon = QIcon()
    ico = resource_path("assets", "brand", "arcivo.ico")
    for size in ICON_SIZES:
        png = resource_path("assets", "brand", f"arcivo-{size}.png")
        if png.exists():
            icon.addFile(str(png), QSize(size, size))
    if ico.exists():
        icon.addFile(str(ico))
    return icon


def set_app_user_model_id() -> None:
    """Give the process its own taskbar identity (otherwise Windows groups it under python.exe)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_USER_MODEL_ID)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - Windows only
        log.debug("SetCurrentProcessExplicitAppUserModelID failed: %s", exc)


def _hex_to_colorref(color: str) -> int:
    c = color.lstrip("#")[:6]
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return r | (g << 8) | (b << 16)


def style_window(widget: Any, pal: Any = None) -> None:
    """Apply native window icon + (Windows 10/11) dark title bar and caption colour."""
    widget.setWindowIcon(app_icon())
    if sys.platform != "win32":
        return
    try:  # pragma: no cover - Windows only
        import ctypes
        from ctypes import wintypes

        hwnd = int(widget.winId())
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        dwm = ctypes.windll.dwmapi  # type: ignore[attr-defined]
        # --- taskbar / title bar icons straight from the .ico (all resolutions)
        ico = resource_path("assets", "brand", "arcivo.ico")
        if ico.exists():
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            IMAGE_ICON, LR_LOADFROMFILE, WM_SETICON = 1, 0x10, 0x0080
            big_size = user32.GetSystemMetrics(11) or 32  # SM_CXICON
            small_size = user32.GetSystemMetrics(49) or 16  # SM_CXSMICON
            big = user32.LoadImageW(None, str(ico), IMAGE_ICON, big_size, big_size, LR_LOADFROMFILE)
            small = user32.LoadImageW(None, str(ico), IMAGE_ICON, small_size, small_size, LR_LOADFROMFILE)
            if big:
                user32.SendMessageW(hwnd, WM_SETICON, 1, big)  # ICON_BIG
            if small:
                user32.SendMessageW(hwnd, WM_SETICON, 0, small)  # ICON_SMALL
        if pal is None:
            return
        # --- title bar that matches the app appearance
        dark = ctypes.c_int(1 if pal.name == "dark" else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (Win11/20H1+, older 19)
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                break
        caption = ctypes.c_uint(_hex_to_colorref(pal.sidebar))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))  # DWMWA_CAPTION_COLOR (Win11)
        text = ctypes.c_uint(_hex_to_colorref(pal.text))
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text), ctypes.sizeof(text))  # DWMWA_TEXT_COLOR
        border = ctypes.c_uint(_hex_to_colorref(pal.border))
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))  # DWMWA_BORDER_COLOR
    except Exception as exc:
        log.debug("Native window styling failed: %s", exc)


class WindowStyler:
    """Application-wide event filter: styles every dialog/main window when first shown (Windows)."""

    def __init__(self) -> None:
        from PySide6.QtCore import QEvent, QObject
        from PySide6.QtWidgets import QDialog, QMainWindow

        styler = self

        class _Filter(QObject):
            def eventFilter(self, obj, event):  # type: ignore[no-untyped-def]
                if event.type() == QEvent.Type.Show and isinstance(obj, QDialog | QMainWindow) and not obj.property("_arcivo_styled"):
                    obj.setProperty("_arcivo_styled", True)
                    style_window(obj, styler.pal)
                return False

        self.pal: Any = None
        self.filter = _Filter()


_styler: WindowStyler | None = None


def install_window_styler(app: Any) -> WindowStyler:
    global _styler
    if _styler is None:
        _styler = WindowStyler()
        app.installEventFilter(_styler.filter)
    return _styler


def set_palette(pal: Any) -> None:
    if _styler is not None:
        _styler.pal = pal
