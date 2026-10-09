"""First-run welcome sheet (Apple "What's New" style) explaining privacy and how Arcivo works."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import APP_NAME
from ..core.paths import resource_path
from ..i18n.translator import T
from .theme.tokens import SYSTEM
from .widgets.common import button, label

FEATURES = [  # icon, colour, key
    ("laptop", SYSTEM["blue"], "local"),
    ("eye-off", SYSTEM["indigo"], "private"),
    ("send", SYSTEM["teal"], "direct"),
    ("hand", SYSTEM["orange"], "control"),
]


class WelcomeSheet(QDialog):
    def __init__(self, pal, icons, parent: QWidget | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        t = T()
        self.setObjectName("Welcome")
        self.setWindowTitle(t("welcome.window_title", app=APP_NAME))
        self.setModal(True)
        self.setFixedWidth(560)
        root = QVBoxLayout(self)
        root.setContentsMargins(56, 40, 56, 32)
        root.setSpacing(0)
        logo = QLabel()
        px = QPixmap(str(resource_path("assets", "brand", "arcivo-128.png")))
        if not px.isNull():
            px = px.scaled(152, 152, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            px.setDevicePixelRatio(2)
            logo.setPixmap(px)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(84)
        root.addWidget(logo)
        root.addSpacing(14)
        title = label(t("welcome.title", app=APP_NAME), "WelcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)
        root.addSpacing(6)
        text_w = 560 - 2 * 56
        sub = label(t("welcome.subtitle"), "Muted", wrap=True)
        sub.setFixedWidth(text_w)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(sub)
        root.addSpacing(26)
        for icon, color, key in FEATURES:
            row = QHBoxLayout()
            row.setSpacing(16)
            ic = QLabel()
            ic.setPixmap(icons.pixmap(icon, color, 30))
            ic.setFixedSize(40, 40)
            ic.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            row.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(label(t(f"welcome.{key}_title"), "FeatureTitle"))
            body = label(t(f"welcome.{key}_text"), "FeatureText", wrap=True)
            body.setFixedWidth(text_w - 56)
            body.setMinimumHeight(body.heightForWidth(text_w - 56))
            col.addWidget(body)
            row.addLayout(col, 1)
            root.addLayout(row)
            root.addSpacing(18)
        root.addSpacing(10)
        fine = label(t("welcome.fineprint"), "Subtle", wrap=True)
        fine.setFixedWidth(text_w)
        fine.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(fine)
        root.addSpacing(18)
        cont = button(t("common.continue"), variant="primary", on_click=self.accept)
        cont.setDefault(True)
        cont.setMinimumWidth(220)
        cont.setMinimumHeight(30)
        root.addWidget(cont, 0, Qt.AlignmentFlag.AlignHCenter)
        _ = pal
        self.adjustSize()


def show_welcome_if_needed(gui_or_ctx, pal, icons, parent=None) -> None:  # type: ignore[no-untyped-def]
    """Show the sheet once per installation; remembers the choice in settings (``onboarding_done``)."""
    cfg = gui_or_ctx.config
    if cfg.settings.onboarding_done:
        return
    WelcomeSheet(pal, icons, parent).exec()
    cfg.settings.onboarding_done = True
    try:
        cfg.save()
    except Exception:  # pragma: no cover - read-only config directory
        pass
