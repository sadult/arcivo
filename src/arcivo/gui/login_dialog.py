"""First-run / sign-in wizard: API credentials → phone → code → 2FA password.

All Telegram calls run on the core loop through :class:`CoreRuntime`; the UI
stays responsive and shows translated, actionable errors inline.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..auth.base import AuthState, AuthStep
from ..core.paths import resource_path
from .widgets.common import button, label

STEPS = ["welcome", "api", "phone", "code", "password", "done"]


class LoginDialog(QDialog):
    def __init__(self, gui, parent: QWidget | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.gui = gui
        t = gui.t
        self.setWindowTitle(t("login.title", app=APP_NAME))
        self.setMinimumSize(620, 520)
        self.setModal(True)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(12)
        logo = QLabel()
        px = QPixmap(str(resource_path("assets", "brand", "arcivo-128.png")))
        if px.isNull():
            px = gui.icons.pixmap("lock", gui.pal.accent, 26)
        else:
            px = px.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            px.setDevicePixelRatio(2)
        logo.setPixmap(px)
        head.addWidget(logo)
        head.addWidget(label(t("login.title", app=APP_NAME), "PageTitle"), 1)
        root.addLayout(head)
        steps = QHBoxLayout()
        self.step_labels: list[QLabel] = []
        for i, s in enumerate(STEPS[1:5], 1):
            lb = label(t("login.step", n=i, name=t(f"login.step_{s}")), "WizardStep")
            steps.addWidget(lb)
            self.step_labels.append(lb)
        steps.addStretch(1)
        root.addLayout(steps)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.error = label("", None, wrap=True)
        self.error.setObjectName("DangerBanner")
        self.error.setVisible(False)
        root.addWidget(self.error)
        self.busy = label("", "Muted")
        root.addWidget(self.busy)
        btns = QHBoxLayout()
        self.cancel_btn = button(t("common.cancel"), on_click=self.reject)
        self.next_btn = button(t("common.continue"), variant="primary", on_click=self._next)
        self.next_btn.setDefault(True)
        btns.addWidget(self.cancel_btn)
        btns.addStretch(1)
        btns.addWidget(self.next_btn)
        root.addLayout(btns)

        # welcome
        w = self._page()
        w.addWidget(label(t("login.welcome_title"), "SectionTitle"))
        w.addWidget(label(t("login.welcome_text"), "Muted", wrap=True))
        notice = label(t("login.tos_notice"), None, wrap=True)
        notice.setObjectName("Banner")
        notice.setContentsMargins(12, 10, 12, 10)
        w.addWidget(notice)
        w.addStretch(1)
        # api
        a = self._page()
        a.addWidget(label(t("login.api_title"), "SectionTitle"))
        guide = label(t("login.api_text"), "Muted", wrap=True)
        guide.setOpenExternalLinks(True)
        guide.setTextFormat(Qt.TextFormat.RichText)
        a.addWidget(guide)
        f = QFormLayout()
        creds = gui.ctx.auth.api_credentials()
        self.api_id = QLineEdit(str(creds.api_id) if creds else "")
        self.api_id.setPlaceholderText("1234567")
        self.api_hash = QLineEdit(creds.api_hash if creds else "")
        self.api_hash.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_hash.setPlaceholderText("0123456789abcdef0123456789abcdef")
        f.addRow(t("login.api_id"), self.api_id)
        f.addRow(t("login.api_hash"), self.api_hash)
        a.addLayout(f)
        a.addWidget(label(t("login.api_storage", store=gui.ctx.store.name), "Subtle", wrap=True))
        a.addStretch(1)
        # phone
        p = self._page()
        p.addWidget(label(t("login.phone_title"), "SectionTitle"))
        p.addWidget(label(t("login.phone_text"), "Muted", wrap=True))
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("+98 912 345 6789")
        self.phone.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        p.addWidget(self.phone)
        p.addStretch(1)
        # code
        c = self._page()
        c.addWidget(label(t("login.code_title"), "SectionTitle"))
        self.code_info = label(t("login.code_text"), "Muted", wrap=True)
        c.addWidget(self.code_info)
        self.code = QLineEdit()
        self.code.setPlaceholderText("12345")
        self.code.setMaxLength(12)
        self.code.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        c.addWidget(self.code)
        c.addWidget(label(t("login.code_warning"), "Subtle", wrap=True))
        c.addStretch(1)
        # password
        pw = self._page()
        pw.addWidget(label(t("login.password_title"), "SectionTitle"))
        self.hint = label("", "Muted", wrap=True)
        pw.addWidget(self.hint)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        pw.addWidget(self.password)
        pw.addStretch(1)
        # done
        d = self._page()
        d.addWidget(label(t("login.done_title"), "SectionTitle"))
        d.addWidget(label(t("login.done_text"), "Muted", wrap=True))
        d.addStretch(1)
        start = "api" if gui.ctx.auth.api_credentials() is None else "phone"
        self._show("welcome" if start == "api" else "api")

    def _page(self) -> QVBoxLayout:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(10)
        self.stack.addWidget(w)
        return lay

    def _show(self, step: str) -> None:
        t = self.gui.t
        self.step = step
        self.stack.setCurrentIndex(STEPS.index(step))
        for i, lb in enumerate(self.step_labels, 1):
            lb.setProperty("active", STEPS[i] == step)
            lb.style().unpolish(lb)
            lb.style().polish(lb)
        self.next_btn.setText({"welcome": t("login.agree"), "api": t("common.continue"), "phone": t("login.send_code"),
                               "code": t("login.sign_in"), "password": t("login.sign_in"), "done": t("login.finish")}[step])
        self.cancel_btn.setVisible(step != "done")
        focus = {"api": self.api_id, "phone": self.phone, "code": self.code, "password": self.password}.get(step)
        if focus:
            focus.setFocus()

    def _set_busy(self, text: str | None) -> None:
        self.busy.setText(text or "")
        self.next_btn.setEnabled(text is None)
        if text:
            self.error.setVisible(False)

    def _fail(self, exc: BaseException) -> None:
        self._set_busy(None)
        self.error.setText("  " + self.gui.error_text(exc))
        self.error.setVisible(True)

    def _state(self, st: AuthState) -> None:
        self._set_busy(None)
        t = self.gui.t
        if st.step == AuthStep.PHONE:
            self._show("phone")
        elif st.step == AuthStep.CODE:
            phone = (st.info or {}).get("phone")
            self.code_info.setText(t("login.code_text") + (f"\n{t('login.code_sent_to', phone=phone)}" if phone else ""))
            self._show("code")
        elif st.step == AuthStep.PASSWORD:
            self.hint.setText(t("login.password_text") + (f"\n{t('login.hint', hint=st.hint)}" if st.hint else ""))
            self._show("password")
        elif st.step == AuthStep.DONE:
            self.password.clear()
            self.gui.ctx.bus.publish("auth.changed")
            self._show("done")
        else:
            self._show("api")

    def _next(self) -> None:
        g, t = self.gui, self.gui.t
        auth = g.ctx.auth
        if self.step == "welcome":
            self._show("api")
        elif self.step == "api":
            try:
                auth.save_api_credentials(self.api_id.text().strip(), self.api_hash.text().strip())
            except Exception as exc:
                self._fail(exc)
                return
            self._set_busy(t("login.connecting"))
            g.runtime.submit(auth.begin("phone"), self._state, self._fail)
        elif self.step in ("phone", "code", "password"):
            value = {"phone": self.phone, "code": self.code, "password": self.password}[self.step].text().strip()
            if not value:
                return
            self._set_busy(t("login.working"))
            g.runtime.submit(auth.submit(value), self._state, self._fail)
        elif self.step == "done":
            self.accept()
