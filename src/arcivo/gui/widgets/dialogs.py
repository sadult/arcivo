"""Dialogs: two-step delete confirmation, tag picker, collection editor, command palette."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...i18n.translator import T
from ...services.delete import DeletePlan
from .common import button, label


class Dialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, width: int = 520) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.setModal(True)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(22, 20, 22, 18)
        self.root.setSpacing(12)
        head = label(title, "SectionTitle")
        self.root.addWidget(head)


class DeleteConfirmDialog(Dialog):
    """Step 1: review counts/types/size + acknowledge. Step 2: type the number of messages."""

    def __init__(self, parent: QWidget | None, gui, plan: DeletePlan, two_step: bool = True, context: str = "") -> None:  # type: ignore[no-untyped-def]
        t = T()
        super().__init__(parent, t("delete.title"), 600)
        self.plan = plan
        self.confirmed_token: str | None = None
        self.stack = QStackedWidget()
        self.root.addWidget(self.stack)

        # ---- step 1
        s1 = QWidget()
        l1 = QVBoxLayout(s1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setSpacing(10)
        banner = QWidget()
        banner.setObjectName("DangerBanner")
        bl = QHBoxLayout(banner)
        bl.setContentsMargins(12, 10, 12, 10)
        ic = QLabel()
        ic.setPixmap(gui.icons.pixmap("triangle-alert", gui.pal.danger, 22))
        bl.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        bl.addWidget(label(t("delete.warning", n=plan.count), wrap=True), 1)
        l1.addWidget(banner)
        if context:
            l1.addWidget(label(context, "Muted", wrap=True))
        summary = [(t("delete.messages"), t.num(plan.count)), (t("delete.size"), t.size(plan.total_bytes))]
        if plan.first_ts:
            summary.append((t("delete.dates"), f"{t.date(plan.first_ts)} → {t.date(plan.last_ts)}"))
        if plan.tagged:
            summary.append((t("delete.tagged"), t.num(plan.tagged)))
        grid = QFormLayout()
        for k, v in summary:
            grid.addRow(label(k, "Muted"), label(v))
        l1.addLayout(grid)
        types = QTableWidget(len(plan.by_type), 2)
        types.setHorizontalHeaderLabels([t("delete.type"), t("delete.count")])
        types.verticalHeader().setVisible(False)
        types.horizontalHeader().setStretchLastSection(True)
        types.setMaximumHeight(150)
        types.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, (k, v) in enumerate(sorted(plan.by_type.items(), key=lambda kv: -kv[1])):
            types.setItem(i, 0, QTableWidgetItem(gui.icons.icon("file", size=14), t(f"types.{k}")))
            types.setItem(i, 1, QTableWidgetItem(t.num(v)))
        l1.addWidget(types)
        samples = QListWidget()
        samples.setMaximumHeight(120)
        for s in plan.samples[:12]:
            samples.addItem(f"#{s['id']} · {t('types.' + s['type'])} · {s['name'] or ''} {('· ' + t.size(s['size'])) if s['size'] else ''}")
        l1.addWidget(label(t("delete.samples"), "Subtle"))
        l1.addWidget(samples)
        self.ack = QCheckBox(t("delete.ack"))
        l1.addWidget(self.ack)
        l1.addWidget(label(t("delete.no_undo"), "Subtle", wrap=True))
        self.stack.addWidget(s1)

        # ---- step 2
        s2 = QWidget()
        l2 = QVBoxLayout(s2)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.addWidget(label(t("delete.type_to_confirm", n=plan.count), wrap=True))
        self.typed = QLineEdit()
        self.typed.setPlaceholderText(str(plan.count))
        l2.addWidget(self.typed)
        l2.addStretch(1)
        self.stack.addWidget(s2)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.cancel_btn = button(t("common.cancel"), on_click=self.reject)
        self.next_btn = button(t("common.continue") if two_step else t("delete.delete_n", n=plan.count),
                               gui.icons.icon("trash-2", "#FFFFFF", 16) if not two_step else None, "danger")
        self.next_btn.setEnabled(False)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.next_btn)
        self.root.addLayout(btns)
        self.two_step = two_step
        self.ack.toggled.connect(self._update)
        self.typed.textChanged.connect(self._update)
        self.next_btn.clicked.connect(self._next)
        self.cancel_btn.setDefault(True)

    def _update(self) -> None:
        if self.stack.currentIndex() == 0:
            self.next_btn.setEnabled(self.ack.isChecked() and self.plan.count > 0)
        else:
            from ...domain.formatting import TO_ASCII_DIGITS
            self.next_btn.setEnabled(self.typed.text().strip().translate(TO_ASCII_DIGITS) == str(self.plan.count))

    def _next(self) -> None:
        if self.stack.currentIndex() == 0 and self.two_step:
            self.stack.setCurrentIndex(1)
            self.next_btn.setText(T()("delete.delete_n", n=self.plan.count))
            self.next_btn.setEnabled(False)
            self.typed.setFocus()
            return
        self.confirmed_token = self.plan.token
        self.accept()


class TagPickerDialog(Dialog):
    def __init__(self, parent: QWidget | None, gui, count: int) -> None:  # type: ignore[no-untyped-def]
        t = T()
        super().__init__(parent, t("tags.apply_title", n=count), 420)
        self.gui = gui
        self.list = QListWidget()
        for tag in gui.ctx.org.list_tags():
            it = QListWidgetItem(gui.icons.icon("tag", tag.color, 16), f"{tag.name}  ({t.num(tag.count)})")
            it.setData(Qt.ItemDataRole.UserRole, tag.id)
            self.list.addItem(it)
        self.root.addWidget(self.list)
        row = QHBoxLayout()
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText(t("tags.new_placeholder"))
        row.addWidget(self.new_name, 1)
        row.addWidget(button(t("tags.create"), gui.icons.icon("plus", size=14), on_click=self._create))
        self.root.addLayout(row)
        self.remove = QCheckBox(t("tags.remove_instead"))
        self.root.addWidget(self.remove)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(t("common.apply"))
        bb.button(QDialogButtonBox.StandardButton.Ok).setProperty("variant", "primary")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(t("common.cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self.root.addWidget(bb)

    def _create(self) -> None:
        name = self.new_name.text().strip()
        if not name:
            return
        try:
            tag = self.gui.ctx.org.create_tag(name)
        except Exception as exc:  # duplicate name etc.
            self.gui.notify(T()("tags.create_failed"), str(exc), "error")
            return
        it = QListWidgetItem(self.gui.icons.icon("tag", tag.color, 16), tag.name)
        it.setData(Qt.ItemDataRole.UserRole, tag.id)
        self.list.addItem(it)
        self.list.setCurrentItem(it)
        self.new_name.clear()

    def selected_tag(self) -> int | None:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None


class CollectionDialog(Dialog):
    ICONS = ["sparkles", "music", "file-text", "video", "image", "link", "flag", "star", "archive", "bookmark", "mic", "files"]

    def __init__(self, parent: QWidget | None, gui, name: str = "", query: str = "", icon: str = "sparkles",  # type: ignore[no-untyped-def]
                 color: str = "#7C83FD", pinned: bool = True) -> None:
        t = T()
        super().__init__(parent, t("collections.edit_title"), 520)
        self.gui = gui
        form = QFormLayout()
        form.setSpacing(10)
        self.name = QLineEdit(name)
        self.query = QLineEdit(query)
        self.query.setPlaceholderText("type:audio size:>20MB")
        self.status = label("", "Subtle")
        self.icon = QComboBox()
        for ic in self.ICONS:
            self.icon.addItem(gui.icons.icon(ic, size=16), ic, ic)
        self.icon.setCurrentIndex(max(0, self.ICONS.index(icon) if icon in self.ICONS else 0))
        self.color = color
        self.color_btn = button(color, on_click=self._pick)
        self.pinned = QCheckBox(t("collections.pin"))
        self.pinned.setChecked(pinned)
        form.addRow(t("collections.name"), self.name)
        form.addRow(t("collections.query"), self.query)
        form.addRow("", self.status)
        form.addRow(t("collections.icon"), self.icon)
        form.addRow(t("collections.color"), self.color_btn)
        form.addRow("", self.pinned)
        self.root.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.save_btn = bb.button(QDialogButtonBox.StandardButton.Save)
        self.save_btn.setText(t("common.save"))
        self.save_btn.setProperty("variant", "primary")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(t("common.cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.root.addWidget(bb)
        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self._validate)
        self.query.textChanged.connect(lambda _: self._timer.start())
        self.name.textChanged.connect(lambda _: self._validate())
        self._validate()

    def _pick(self) -> None:
        from PySide6.QtGui import QColor
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.color = c.name()
            self.color_btn.setText(self.color)

    def _validate(self) -> None:
        t = T()
        err = self.gui.ctx.search.validate(self.query.text())
        ok = err is None and bool(self.name.text().strip()) and bool(self.query.text().strip())
        self.query.setProperty("invalid", err is not None)
        self.query.style().unpolish(self.query)
        self.query.style().polish(self.query)
        if err:
            self.status.setText(t("search.invalid", error=err))
        elif self.gui.account_id and self.query.text().strip():
            self.status.setText(t("collections.matches", n=self.gui.ctx.search.count(self.gui.account_id, self.query.text())))
        self.save_btn.setEnabled(ok)

    def values(self) -> dict:
        return {"name": self.name.text().strip(), "query": self.query.text().strip(), "icon": self.icon.currentData(),
                "color": self.color, "pinned": self.pinned.isChecked()}


class CommandPalette(QDialog):
    """Ctrl+K quick navigation and actions with incremental filtering."""

    def __init__(self, parent: QWidget, gui, commands: list[tuple[str, str, str, Callable[[], None]]]) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.commands = commands
        box = QWidget(self)
        box.setObjectName("Palette")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(box)
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 12, 12, 12)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(T()("palette.placeholder"))
        inner.addWidget(self.edit)
        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget { border: none; background: transparent; }")
        inner.addWidget(self.list)
        self.resize(560, 420)
        self.edit.textChanged.connect(self._filter)
        self.edit.returnPressed.connect(self._run)
        self.list.itemActivated.connect(lambda _: self._run())
        self.gui = gui
        self._filter("")

    def _filter(self, text: str) -> None:
        self.list.clear()
        needle = text.lower().strip()
        for icon, title, hint, fn in self.commands:
            if needle and needle not in title.lower() and needle not in hint.lower():
                continue
            it = QListWidgetItem(self.gui.icons.icon(icon, size=16), f"{title}    {hint}")
            it.setData(Qt.ItemDataRole.UserRole, fn)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def keyPressEvent(self, e) -> None:  # type: ignore[no-untyped-def]
        if e.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            r = self.list.currentRow() + (1 if e.key() == Qt.Key.Key_Down else -1)
            self.list.setCurrentRow(max(0, min(self.list.count() - 1, r)))
            return
        super().keyPressEvent(e)

    def _run(self) -> None:
        it = self.list.currentItem()
        if it:
            fn = it.data(Qt.ItemDataRole.UserRole)
            self.accept()
            fn()
