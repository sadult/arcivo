"""Reusable widgets following the Arcivo design system."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)

from ..theme.style import qcolor


def label(text: str = "", obj: str | None = None, wrap: bool = False, selectable: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    if selectable:
        lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lb


def button(text: str, icon=None, variant: str | None = None, tooltip: str | None = None,  # type: ignore[no-untyped-def]
           on_click: Callable[[], None] | None = None) -> QPushButton:
    text = text.replace("&", "&&")  # no accidental mnemonics ("Review & delete")
    b = QPushButton(f" {text}" if icon is not None and text else text)  # breathing room between glyph and label
    if icon is not None:
        b.setIcon(icon)
        b.setIconSize(QSize(16, 16))
    if variant:
        b.setProperty("variant", variant)
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if on_click:
        b.clicked.connect(lambda *_: on_click())
    return b


def tool(icon, tooltip: str, on_click: Callable[[], None] | None = None, checkable: bool = False) -> QToolButton:  # type: ignore[no-untyped-def]
    b = QToolButton()
    b.setIcon(icon)
    b.setIconSize(QSize(18, 18))
    b.setToolTip(tooltip)
    b.setAccessibleName(tooltip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if on_click:
        b.clicked.connect(lambda *_: on_click())
    return b


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    return f


def hbox(*widgets, spacing: int = 8, margins=(0, 0, 0, 0), stretch_at: int | None = None) -> QHBoxLayout:  # type: ignore[no-untyped-def]
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for i, w in enumerate(widgets):
        if stretch_at == i:
            lay.addStretch(1)
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, QLayout):
            lay.addLayout(w)
        else:
            lay.addWidget(w)
    return lay


def vbox(*widgets, spacing: int = 8, margins=(0, 0, 0, 0)) -> QVBoxLayout:  # type: ignore[no-untyped-def]
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, QLayout):
            lay.addLayout(w)
        else:
            lay.addWidget(w)
    return lay


class Card(QFrame):
    clicked = Signal()

    def __init__(self, title: str | None = None, subtitle: str | None = None, *, clickable: bool = False,
                 padding: int = 18, actions: list[QWidget] | None = None) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("clickable", clickable)
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(padding, padding - 2, padding, padding)
        self.outer.setSpacing(10)
        if title or actions:
            head = QHBoxLayout()
            head.setSpacing(8)
            col = QVBoxLayout()
            col.setSpacing(2)
            if title:
                self.title_label = label(title, "CardTitle")
                col.addWidget(self.title_label)
            if subtitle:
                self.subtitle_label = label(subtitle, "CardSubtitle", wrap=True)
                col.addWidget(self.subtitle_label)
            head.addLayout(col, 1)
            for a in actions or []:
                head.addWidget(a)
            self.outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        self.outer.addLayout(self.body, 1)

    def add(self, w: QWidget | QLayout, stretch: int = 0) -> None:
        if isinstance(w, QLayout):
            self.body.addLayout(w, stretch)
        else:
            self.body.addWidget(w, stretch)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self.property("clickable") and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class IconBadge(QLabel):
    """A tinted SF-Symbol-like glyph (no filled badge background, per macOS conventions)."""

    def __init__(self, pixmap, color: str, size: int = 34) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.setFixedSize(size, size)
        self._px = pixmap
        self._color = qcolor(color)

    def paintEvent(self, _e) -> None:  # type: ignore[no-untyped-def]
        p = QPainter(self)
        s = self._px.deviceIndependentSize()
        p.drawPixmap(int((self.width() - s.width()) / 2), int((self.height() - s.height()) / 2), self._px)
        p.end()


class StatCard(Card):
    """macOS-widget style tile: small tinted glyph + caption, large value, secondary line."""

    def __init__(self, icon_px, color: str, label_text: str, value: str, sub: str = "", tooltip: str = "",  # type: ignore[no-untyped-def]
                 clickable: bool = True) -> None:
        super().__init__(clickable=clickable, padding=16)
        self.body.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(6)
        ic = QLabel()
        ic.setPixmap(icon_px)
        ic.setFixedSize(16, 16)
        ic.setScaledContents(True)
        top.addWidget(ic)
        top.addWidget(label(label_text, "StatLabel"), 1)
        self.add(top)
        self.body.addSpacing(6)
        self.value = label(value, "StatValue")
        self.add(self.value)
        self.sub = label(sub, "Subtle")
        self.add(self.sub)
        if tooltip:
            self.setToolTip(tooltip)
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], current: str | None = None) -> None:
        super().__init__()
        self.setObjectName("Segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for key, text in options:
            b = QPushButton(text)
            b.setProperty("variant", "segment")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b
        self.set(current or options[0][0])

    def set(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)

    def value(self) -> str:
        for k, b in self.buttons.items():
            if b.isChecked():
                return k
        return ""


class SearchBox(QLineEdit):
    """Search field with leading icon, live debounce and history (↑/↓)."""

    submitted = Signal(str)
    debounced = Signal(str)

    def __init__(self, icon_px, placeholder: str, delay_ms: int = 280) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.setObjectName("SearchField")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self._icon = icon_px
        self._timer = QTimer(self, singleShot=True, interval=delay_ms)
        self._timer.timeout.connect(lambda: self.debounced.emit(self.text()))
        self.textEdited.connect(lambda _: self._timer.start())
        self.returnPressed.connect(lambda: (self._timer.stop(), self._remember(), self.submitted.emit(self.text())))
        self.history: list[str] = []
        self._hpos = -1

    def _remember(self) -> None:
        t = self.text().strip()
        if t and (not self.history or self.history[-1] != t):
            self.history.append(t)
            self.history = self.history[-50:]
        self._hpos = -1

    def keyPressEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        if e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down) and self.history:
            self._hpos = (len(self.history) - 1 if self._hpos < 0 else self._hpos) + (-1 if e.key() == Qt.Key.Key_Up and self._hpos >= 0 else 0)
            if e.key() == Qt.Key.Key_Down:
                self._hpos = min(len(self.history) - 1, self._hpos + 1)
            self._hpos = max(0, self._hpos)
            self.setText(self.history[self._hpos])
            return
        super().keyPressEvent(e)

    def paintEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(e)
        p = QPainter(self)
        s = self._icon.deviceIndependentSize()
        p.drawPixmap(10, int((self.height() - s.height()) / 2), self._icon)
        p.end()


class EmptyState(QWidget):
    def __init__(self, icon_px, title: str, text: str = "", action: QPushButton | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 40, 24, 40)
        lay.setSpacing(8)
        lay.addStretch(1)
        ic = QLabel()
        ic.setPixmap(icon_px)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic)
        t = label(title, "EmptyTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        if text:
            d = label(text, "Muted", wrap=True)
            d.setAlignment(Qt.AlignmentFlag.AlignCenter)
            d.setMaximumWidth(460)
            lay.addWidget(d, 0, Qt.AlignmentFlag.AlignHCenter)
        if action:
            lay.addSpacing(8)
            lay.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(2)


class Chip(QLabel):
    """Small coloured tag chip."""

    def __init__(self, text: str, color: str) -> None:
        super().__init__(text)
        c = qcolor(color)
        self.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},40); color: {c.name()}; border-radius: 9px;"
                           " padding: 1px 9px; font-size: 11px; font-weight: 600;")


class FlowLayout(QLayout):
    """Wrapping layout for chips."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QWidgetItem] = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # type: ignore[no-untyped-def]
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int):  # type: ignore[no-untyped-def]
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int):  # type: ignore[no-untyped-def]
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # type: ignore[no-untyped-def]
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return self._layout(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s + QSize(4, 4)

    def _layout(self, rect: QRect, test: bool) -> int:
        x, y, line_h = rect.x(), rect.y(), 0
        sp = self.spacing()
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() and line_h > 0:
                x, y, line_h = rect.x(), y + line_h + sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + sp
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


class KeyValueGrid(QWidget):
    def __init__(self, rows: list[tuple[str, str]] | None = None, selectable: bool = True) -> None:
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(1, 1)
        self.selectable = selectable
        for k, v in rows or []:
            self.add(k, v)

    def add(self, key: str, value: str) -> None:
        r = self.grid.rowCount()
        k = label(key, "Muted")
        k.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeading)
        v = label(value, None, wrap=True, selectable=self.selectable)
        self.grid.addWidget(k, r, 0)
        self.grid.addWidget(v, r, 1)

    def clear(self) -> None:
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()


def fade_in(w: QWidget, ms: int = 180) -> None:
    eff = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", w)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: w.setGraphicsEffect(None))
    anim.start()
    w._fade_anim = anim  # type: ignore[attr-defined]


class StorageBar(QWidget):
    """macOS "Storage"-style stacked capacity bar: rounded track split into coloured segments."""

    def __init__(self, track: str, height: int = 22) -> None:
        super().__init__()
        self.setFixedHeight(height)
        self._track = qcolor(track)
        self.segments: list[tuple[str, float, str]] = []  # (key, value, color)
        self.setMouseTracking(True)
        self.tooltips: dict[str, str] = {}

    def set_segments(self, segments: list[tuple[str, float, str]], tooltips: dict[str, str] | None = None) -> None:
        self.segments = [s for s in segments if s[1] > 0]
        self.tooltips = tooltips or {}
        self.update()

    def _rects(self) -> list[tuple[str, QRect]]:
        total = sum(v for _, v, _ in self.segments) or 1
        x, out, w = 0.0, [], self.width()
        for key, v, _c in self.segments:
            seg = max(2.0, w * v / total)
            out.append((key, QRect(int(x), 0, round(seg), self.height())))
            x += seg
        return out

    def paintEvent(self, _e) -> None:  # type: ignore[no-untyped-def]
        from PySide6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        path = QPainterPath()
        path.addRoundedRect(r.toRectF(), 6, 6)
        p.setClipPath(path)
        p.fillRect(r, self._track)
        for (_key, rect), (_k, _v, color) in zip(self._rects(), self.segments, strict=False):
            p.fillRect(rect, qcolor(color))
            p.fillRect(QRect(rect.right(), 0, 1, rect.height()), self._track)  # hairline gap between segments
        p.end()

    def mouseMoveEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QToolTip
        for key, rect in self._rects():
            if rect.contains(e.position().toPoint()):
                QToolTip.showText(QCursor.pos(), self.tooltips.get(key, key), self)
                return
        QToolTip.hideText()


class LegendItem(QWidget):
    """Colour dot + name + secondary value (used under StorageBar)."""

    clicked = Signal()

    def __init__(self, color: str, name: str, value: str) -> None:
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        c = qcolor(color)
        dot.setStyleSheet(f"background: {c.name()}; border-radius: 4px;")
        lay.addWidget(dot)
        lay.addWidget(label(name, None))
        lay.addWidget(label(value, "Subtle"))

    def mouseReleaseEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class InsetRow(QFrame):
    """One row of an inset grouped list: glyph · title/subtitle · trailing value · chevron."""

    clicked = Signal()

    def __init__(self, icon_px, title: str, subtitle: str = "", trailing: str = "", chevron_px=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.setObjectName("InsetRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(10)
        if icon_px is not None:
            ic = QLabel()
            ic.setPixmap(icon_px)
            ic.setFixedWidth(18)
            lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(1)
        t = label(title, None)
        t.setMinimumWidth(40)
        t.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        col.addWidget(t)
        if subtitle:
            col.addWidget(label(subtitle, "Subtle"))
        lay.addLayout(col, 1)
        if trailing:
            lay.addWidget(label(trailing, "Muted"))
        if chevron_px is not None:
            ch = QLabel()
            ch.setPixmap(chevron_px)
            lay.addWidget(ch)

    def mouseReleaseEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class InsetList(QWidget):
    """Rows separated by hairlines, meant to sit inside a Card (macOS inset grouped style)."""

    def __init__(self) -> None:
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(0)
        self.rows: list[InsetRow] = []

    def clear(self) -> None:
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        self.rows = []

    def add(self, row: InsetRow) -> InsetRow:
        if self.rows:
            self.lay.addWidget(hline())
        self.lay.addWidget(row)
        self.rows.append(row)
        return row
