"""Base class for all pages: large-title header with actions, lazy refresh, events."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ..widgets.common import label


class Page(QWidget):
    key = ""
    scrollable = True
    margins = (32, 26, 32, 28)

    def __init__(self, gui) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.gui = gui
        self.t = gui.t
        self._dirty = True
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        holder = QWidget()
        self.root = QVBoxLayout(holder)
        self.root.setContentsMargins(*self.margins)
        self.root.setSpacing(18)
        head = QHBoxLayout()
        head.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title_label = label(self.title(), "PageTitle")
        col.addWidget(self.title_label)
        sub = self.subtitle()
        self.title_label.setToolTip(sub)
        self.subtitle_label = label(sub, "PageSubtitle", wrap=True)
        self.subtitle_label.setVisible(False)  # macOS large titles stand alone; the description lives in the tooltip
        col.addWidget(self.subtitle_label)
        head.addLayout(col, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        head.addLayout(self.actions)
        head.setAlignment(self.actions, Qt.AlignmentFlag.AlignVCenter)
        self.root.addLayout(head)
        if self.scrollable:
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.Shape.NoFrame)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            sa.setWidget(holder)
            outer.addWidget(sa)
            self.scroll = sa
        else:
            outer.addWidget(holder)
        self.build()

    # ---- to override
    def title(self) -> str:
        return self.t(f"nav.{self.key}")

    def subtitle(self) -> str:
        return self.t(f"{self.key}.subtitle")

    def build(self) -> None:
        pass

    def refresh(self) -> None:
        pass

    def open(self, **kw: Any) -> None:
        """Called when navigated to with arguments."""

    def on_event(self, topic: str, payload: dict) -> None:
        pass

    # ---- lifecycle
    def mark_dirty(self) -> None:
        self._dirty = True
        if self.isVisible():
            self.ensure_fresh()

    def ensure_fresh(self) -> None:
        if self._dirty:
            self._dirty = False
            try:
                self.refresh()
            except Exception as exc:
                self.gui.show_error(exc)

    def showEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(e)
        self.ensure_fresh()

    def no_account(self) -> bool:
        return self.gui.account_id is None
