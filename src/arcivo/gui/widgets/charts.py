"""Interactive, theme-aware charts (QtCharts) and a custom heatmap.

All charts support hover tooltips; bar/donut charts emit ``clicked(key)`` so
pages can drill down (e.g. open Explorer filtered by the clicked type/month).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCharts import (
    QAreaSeries,
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QHorizontalBarSeries,
    QLineSeries,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import QMargins, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ...i18n.translator import T
from ..theme.style import qcolor
from ..theme.tokens import CHART, Palette

# Honours Settings → Appearance → animations (set by the controller on build).
ANIMATIONS = True


class ChartView(QChartView):
    clicked = Signal(str)

    def __init__(self, pal: Palette, height: int = 260) -> None:
        super().__init__(self._new_chart())
        self.pal = pal
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: transparent; border: none;")
        self.keys: list[str] = []
        self._keep: list = []
        self._old: list = []

    @staticmethod
    def _new_chart() -> QChart:
        chart = QChart()
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.setMargins(QMargins(0, 0, 0, 0))
        chart.layout().setContentsMargins(0, 0, 0, 0)
        chart.legend().setVisible(False)
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations if ANIMATIONS else QChart.AnimationOption.NoAnimation)
        chart.setAnimationDuration(450)
        return chart

    def _font(self, size: int = 11) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(size)
        return f

    def _style_axis(self, axis, grid: bool = True) -> None:  # type: ignore[no-untyped-def]
        axis.setLabelsColor(qcolor(self.pal.text_subtle))
        axis.setLabelsFont(self._font(10))
        axis.setLinePen(QPen(qcolor(self.pal.border)))
        axis.setLineVisible(False)
        axis.setGridLinePen(QPen(qcolor(self.pal.chart_grid), 1))
        axis.setGridLineVisible(grid)
        axis.setMinorGridLineVisible(False)
        if hasattr(axis, "setTruncateLabels"):  # Qt ≥ 6.4: don't elide short labels to "…" in narrow layouts
            axis.setTruncateLabels(False)
        if hasattr(axis, "setShadesVisible"):
            axis.setShadesVisible(False)

    def reset(self) -> QChart:
        # Mutating a live chart (removeAllSeries while a series animation or hover is pending) can crash
        # QtCharts. Swap in a fresh chart instead and dispose of the old one once the event loop is idle.
        old = self.chart()
        old.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        c = self._new_chart()
        self.setChart(c)
        for prev, _refs in self._old:
            prev.deleteLater()
        self._old = [(old, self._keep)]
        self.keys = []
        self._is_pie = False
        # boundary series of QAreaSeries are not owned by the chart: keep Python refs alive with their chart
        self._keep = []
        return c

    @staticmethod
    def _thin(labels: list[str], max_labels: int = 10) -> list[str]:
        if len(labels) <= max_labels:
            return labels
        step = max(1, len(labels) // max_labels)
        # QBarCategoryAxis requires unique labels → use zero-width spaces for hidden ones
        return [lb if i % step == 0 else "\u200b" * (i + 1) for i, lb in enumerate(labels)]

    # ------------------------------------------------------------------ bars
    def bars(self, labels: list[str], values: list[float], keys: list[str] | None = None, color: str | None = None,
             fmt: Callable[[float], str] | None = None, horizontal: bool = False, max_labels: int = 12,
             axis_format: str = "%.0f") -> None:
        if horizontal:  # Qt draws the first category at the bottom; show the largest first (top)
            labels, values = labels[::-1], values[::-1]
            keys = keys[::-1] if keys else None
        c = self.reset()
        self.keys = keys or labels
        fmt = fmt or (lambda v: T().num(int(v)))
        s = QBarSet("")
        s.append([float(v) for v in values])
        col = qcolor(color or self.pal.accent)
        s.setColor(col)
        s.setBorderColor(col)
        hover = QColor(col).lighter(125)
        series = QHorizontalBarSeries() if horizontal else QBarSeries()
        series.append(s)
        series.setBarWidth(0.56)
        c.addSeries(series)
        cat = QBarCategoryAxis()
        cat.append(labels if horizontal else self._thin(labels, max_labels))
        val = QValueAxis()
        val.setLabelFormat(axis_format)
        val.setTickCount(5)
        val.setRange(0, max(values or [1]) * 1.1 or 1)
        self._style_axis(cat, grid=False)
        self._style_axis(val)
        if horizontal:
            c.addAxis(cat, Qt.AlignmentFlag.AlignLeft)
            c.addAxis(val, Qt.AlignmentFlag.AlignBottom)
        else:
            c.addAxis(cat, Qt.AlignmentFlag.AlignBottom)
            c.addAxis(val, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(cat)
        series.attachAxis(val)

        def on_hover(state: bool, idx: int) -> None:
            if state and 0 <= idx < len(labels):
                s.setColor(hover)
                QToolTip.showText(QCursor.pos(), f"<b>{labels[idx]}</b><br>{fmt(values[idx])}", self)
            else:
                s.setColor(col)
                QToolTip.hideText()

        s.hovered.connect(on_hover)
        s.clicked.connect(lambda idx: self.clicked.emit(self.keys[idx]) if 0 <= idx < len(self.keys) else None)

    # ------------------------------------------------------------------ area / line
    def area(self, labels: list[str], series_values: list[tuple[str, list[float], str]], fmt: Callable[[float], str] | None = None,
             filled: bool = True, keys: list[str] | None = None) -> None:
        c = self.reset()
        self.keys = keys or labels
        fmt = fmt or (lambda v: T().num(int(v)))
        n = len(labels)
        xa = QValueAxis()
        xa.setRange(0, max(1, n - 1))
        xa.setLabelFormat("%d")
        xa.setLabelsVisible(False)
        xa.setTickCount(2)
        ya = QValueAxis()
        ya.setTickCount(5)
        top = max((max(v) for _, v, _ in series_values if v), default=1) or 1
        ya.setRange(0, top * 1.12)
        ya.setLabelFormat("%.0f")
        self._style_axis(xa, grid=False)
        self._style_axis(ya)
        c.addAxis(xa, Qt.AlignmentFlag.AlignBottom)
        c.addAxis(ya, Qt.AlignmentFlag.AlignLeft)
        # human-readable x labels via a category axis overlay
        if n:
            from PySide6.QtCharts import QCategoryAxis
            ca = QCategoryAxis()
            ca.setLabelsPosition(QCategoryAxis.AxisLabelsPosition.AxisLabelsPositionOnValue)
            step = max(1, n // 8)
            for i in range(0, n, step):
                ca.append(labels[i] + "\u200b" * i, i)
            ca.setRange(0, max(1, n - 1))
            self._style_axis(ca, grid=False)
            c.addAxis(ca, Qt.AlignmentFlag.AlignBottom)
        for name, values, color in series_values:
            col = qcolor(color)
            upper = QLineSeries()
            upper.setName(name)
            for i, v in enumerate(values):
                upper.append(QPointF(i, float(v)))
            pen = QPen(col, 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            upper.setPen(pen)
            if filled:
                lower = QLineSeries()
                for i in range(len(values)):
                    lower.append(QPointF(i, 0))
                area = QAreaSeries(upper, lower)
                # parent the boundary series to the area so they live exactly as long as it does
                upper.setParent(area)
                lower.setParent(area)
                grad = QLinearGradient(0, 0, 0, 1)
                grad.setCoordinateMode(QLinearGradient.CoordinateMode.ObjectBoundingMode)
                top_c, bot_c = QColor(col), QColor(col)
                top_c.setAlpha(72)
                bot_c.setAlpha(0)
                grad.setColorAt(0, top_c)
                grad.setColorAt(1, bot_c)
                area.setBrush(QBrush(grad))
                area.setPen(QPen(Qt.PenStyle.NoPen))  # no outline along the baseline/edges – stroke only the top line
                c.addSeries(area)
                area.attachAxis(xa)
                area.attachAxis(ya)
                stroke = QLineSeries()
                for i, v in enumerate(values):
                    stroke.append(QPointF(i, float(v)))
                stroke.setPen(pen)
                c.addSeries(stroke)
                stroke.attachAxis(xa)
                stroke.attachAxis(ya)
                hover_src = area
            else:
                c.addSeries(upper)
                upper.attachAxis(xa)
                upper.attachAxis(ya)
                hover_src = upper

            def on_hover(point: QPointF, state: bool, vals=values, nm=name) -> None:  # type: ignore[no-untyped-def]
                if state:
                    i = max(0, min(len(vals) - 1, round(point.x())))
                    QToolTip.showText(QCursor.pos(), f"<b>{labels[i]}</b><br>{nm}: {fmt(vals[i])}", self)
                else:
                    QToolTip.hideText()

            hover_src.hovered.connect(on_hover)
            if hasattr(hover_src, "clicked"):
                hover_src.clicked.connect(lambda pt: self.clicked.emit(self.keys[max(0, min(len(self.keys) - 1, round(pt.x())))]))
        if len(series_values) > 1:
            lg = c.legend()
            lg.setVisible(True)
            lg.setAlignment(Qt.AlignmentFlag.AlignTop)
            lg.setLabelColor(qcolor(self.pal.text_muted))
            lg.setFont(self._font(11))

    # ------------------------------------------------------------------ donut
    def donut(self, items: list[tuple[str, float, str, str]], fmt: Callable[[float], str] | None = None,
              center_text: str = "") -> None:
        """items: (label, value, color, key)."""
        c = self.reset()
        fmt = fmt or (lambda v: T().num(int(v)))
        series = QPieSeries()
        series.setHoleSize(0.66)
        series.setPieSize(0.9)
        total = sum(v for _, v, _, _ in items) or 1
        for lbl, v, color, key in items:
            sl = series.append(lbl, float(v))
            col = qcolor(color)
            sl.setColor(col)
            sl.setBorderColor(qcolor(self.pal.surface))
            sl.setBorderWidth(2)
            sl.setLabelVisible(False)

            def hov(state: bool, sl=sl, lbl=lbl, v=v) -> None:  # type: ignore[no-untyped-def]
                sl.setExploded(state)
                sl.setExplodeDistanceFactor(0.05)
                if state:
                    QToolTip.showText(QCursor.pos(), f"<b>{lbl}</b><br>{fmt(v)} · {T().num(round(100 * v / total, 1))}%", self)
                else:
                    QToolTip.hideText()

            sl.hovered.connect(hov)
            sl.clicked.connect(lambda key=key: self.clicked.emit(key))
        # Pie animations crash QtCharts when the series is replaced while animating; donuts render statically.
        c.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        c.addSeries(series)
        self._center = center_text
        self._is_pie = True
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # type: ignore[override]
        super().drawForeground(painter, rect)
        text = getattr(self, "_center", "")
        if text and getattr(self, "_is_pie", False):
            painter.save()
            painter.setPen(qcolor(self.pal.text))
            f = self._font(18)
            f.setBold(True)
            painter.setFont(f)
            pa = self.chart().plotArea()
            painter.drawText(pa, Qt.AlignmentFlag.AlignCenter, text)
            painter.restore()


class Heatmap(QWidget):
    """Weekday × hour activity heatmap with hover tooltips; click emits (weekday, hour)."""

    clicked = Signal(int, int)

    def __init__(self, pal: Palette) -> None:
        super().__init__()
        self.pal = pal
        self.grid: list[list[int]] = [[0] * 24 for _ in range(7)]
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.days = [T()(f"common.weekday_{i}") for i in range(7)]

    def set_data(self, grid: list[list[int]]) -> None:
        self.grid = grid
        self.update()

    def _geom(self) -> tuple[float, float, float, float]:
        left = 44.0
        top = 6.0
        cw = (self.width() - left - 6) / 24
        ch = (self.height() - top - 22) / 7
        return left, top, cw, ch

    def paintEvent(self, _e) -> None:  # type: ignore[no-untyped-def]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, top, cw, ch = self._geom()
        peak = max((max(r) for r in self.grid), default=0) or 1
        base = qcolor(self.pal.accent)
        f = QFont(self.font())
        f.setPixelSize(10)
        p.setFont(f)
        for d in range(7):
            p.setPen(qcolor(self.pal.text_subtle))
            p.drawText(QRectF(0, top + d * ch, left - 8, ch), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, self.days[d])
            for h in range(24):
                v = self.grid[d][h]
                c = QColor(base)
                c.setAlpha(18 + int(237 * (v / peak) ** 0.75) if v else 14)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(left + h * cw + 1.5, top + d * ch + 1.5, cw - 3, ch - 3), 4, 4)
        p.setPen(qcolor(self.pal.text_subtle))
        for h in range(0, 24, 3):
            p.drawText(QRectF(left + h * cw, top + 7 * ch + 2, cw * 2, 18), Qt.AlignmentFlag.AlignLeft, f"{h:02d}")
        p.end()

    def _cell(self, pos) -> tuple[int, int] | None:  # type: ignore[no-untyped-def]
        left, top, cw, ch = self._geom()
        h = int((pos.x() - left) // cw)
        d = int((pos.y() - top) // ch)
        if 0 <= h < 24 and 0 <= d < 7:
            return d, h
        return None

    def mouseMoveEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        cell = self._cell(e.position())
        if cell:
            d, h = cell
            QToolTip.showText(QCursor.pos(), f"<b>{self.days[d]} {f'{h:02d}:00'}</b><br>"
                              f"{T()('stats.messages_n', n=self.grid[d][h])}", self)

    def mouseReleaseEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        cell = self._cell(e.position())
        if cell:
            self.clicked.emit(*cell)


def palette_color(i: int) -> str:
    return CHART[i % len(CHART)]
