"""Non-blocking toast notifications (stacked, auto-dismiss, optional action)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n.translator import T

KIND_ICON = {"info": ("info", "info"), "success": ("circle-check", "success"), "warning": ("triangle-alert", "warning"),
             "error": ("circle-alert", "danger")}


class Toast(QFrame):
    def __init__(self, parent: QWidget, icons, pal, kind: str, title: str, text: str,  # type: ignore[no-untyped-def]
                 action: tuple[str, Callable[[], None]] | None, on_close: Callable[[Toast], None]) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.on_close = on_close
        self.setFixedWidth(360)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 10, 12)
        lay.setSpacing(10)
        icon_name, color_attr = KIND_ICON.get(kind, KIND_ICON["info"])
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, getattr(pal, color_attr), 20))
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("ToastTitle")
        t.setWordWrap(True)
        col.addWidget(t)
        if text:
            d = QLabel(text)
            d.setObjectName("Muted")
            d.setWordWrap(True)
            col.addWidget(d)
        lay.addLayout(col, 1)
        if action:
            b = QPushButton(action[0])
            b.setProperty("variant", "ghost")
            b.clicked.connect(lambda: (action[1](), self.close_toast()))
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        x = QPushButton()
        x.setIcon(icons.icon("x", size=14))
        x.setProperty("variant", "ghost")
        x.setFixedSize(26, 26)
        x.setToolTip(T()("common.close"))
        x.clicked.connect(self.close_toast)
        lay.addWidget(x, 0, Qt.AlignmentFlag.AlignTop)
        self.adjustSize()
        self.eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.eff)
        self.anim = QPropertyAnimation(self.eff, b"opacity", self)
        self.anim.setDuration(200)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()
        timeout = 9000 if kind == "error" else 5000
        QTimer.singleShot(timeout, self.close_toast)
        self._closing = False

    def close_toast(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.anim.stop()
        self.anim.setStartValue(self.eff.opacity())
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(lambda: (self.on_close(self), self.deleteLater()))
        self.anim.start()


class ToastManager:
    def __init__(self, host: QWidget, icons, pal) -> None:  # type: ignore[no-untyped-def]
        self.host = host
        self.icons = icons
        self.pal = pal
        self.toasts: list[Toast] = []
        self.enabled = True

    def show(self, title: str, text: str = "", kind: str = "info", action: tuple[str, Callable[[], None]] | None = None) -> None:
        if not self.enabled and kind != "error":
            return
        t = Toast(self.host, self.icons, self.pal, kind, title, text, action, self._remove)
        self.toasts.append(t)
        if len(self.toasts) > 4:
            self.toasts[0].close_toast()
        t.show()
        t.raise_()
        self.reposition()

    def _remove(self, t: Toast) -> None:
        if t in self.toasts:
            self.toasts.remove(t)
        self.reposition()

    def reposition(self) -> None:
        margin = 20
        y = self.host.height() - margin - 28
        for t in reversed(self.toasts):
            t.adjustSize()
            y -= t.height()
            x = self.host.width() - t.width() - margin
            t.move(QPoint(x, y))
            y -= 10
