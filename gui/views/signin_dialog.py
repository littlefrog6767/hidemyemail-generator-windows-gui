"""Paste-cookie sign-in flow: the user copies their authenticated iCloud
request (raw Cookie header, or a browser 'Copy as cURL'), pastes it here, and
we validate it against iCloud before saving it locally."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QHBoxLayout, QTextEdit, QVBoxLayout,
)

from gui import backend
from gui.widgets import PillButton, PrimaryButton, SecondaryButton, make_label


class SignInDialog(QDialog):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle("Sign in to iCloud")
        self.setFixedSize(580, 600)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        heading = make_label("Connect your iCloud account")
        heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(heading)

        instructions = make_label(
            "1. Sign in at icloud.com/settings (icloud.com.cn for China) in your browser.\n"
            "2. Open DevTools (F12) → Network tab, then refresh the page.\n"
            "3. Filter requests for \"hme\" or \"maildomainws\".\n"
            "4. Right-click a matching request → Copy → Copy as cURL.\n"
            "5. Paste the whole copied text below. A raw Cookie header also works.\n\n"
            "Avoid feedbackws/reportStats requests — they're usually missing the\n"
            "X-APPLE-WEBAUTH-USER cookie this needs.",
            variant="secondary",
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        region_row = QHBoxLayout()
        region_row.addWidget(make_label("Region", variant="secondary"))
        self._region = self.app.app_state.region
        self._region_group = QButtonGroup(self)
        self._region_group.setExclusive(True)
        for value in ("global", "china"):
            btn = PillButton(value)
            btn.setCheckable(True)
            btn.setChecked(value == self._region)
            btn.set_active(value == self._region)
            btn.clicked.connect(lambda _c=False, v=value: self._on_region_selected(v))
            self._region_group.addButton(btn)
            region_row.addWidget(btn)
        region_row.addStretch()
        layout.addLayout(region_row)

        self.text_box = QTextEdit()
        self.text_box.setFixedHeight(200)
        layout.addWidget(self.text_box)

        self.status_label = make_label("", variant="secondary")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()

        btn_row = QHBoxLayout()
        self.validate_btn = PrimaryButton("Validate & Sign In")
        self.validate_btn.clicked.connect(self._validate)
        cancel_btn = SecondaryButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.validate_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_region_selected(self, value):
        self._region = value
        for btn in self._region_group.buttons():
            btn.set_active(btn.text() == value)

    def _set_status(self, text, variant):
        self.status_label.setText(text)
        self.status_label.setProperty("variant", variant)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _validate(self):
        text = self.text_box.toPlainText().strip()
        if not text:
            self._set_status("Paste your cookie / cURL text first.", "danger")
            return
        region = self._region
        self.validate_btn.setEnabled(False)
        self.validate_btn.setText("Validating…")
        self._set_status("Contacting iCloud…", "secondary")
        self.app.worker.run_coro(
            backend.validate_and_fetch_account(text, region),
            on_done=lambda v, e: self._on_result(v, e, text, region),
        )

    def _on_result(self, result, error, raw_text, region):
        if not self.isVisible():
            return
        self.validate_btn.setEnabled(True)
        self.validate_btn.setText("Validate & Sign In")
        if error is not None:
            self._set_status(f"Error: {error}", "danger")
            return
        if not result["ok"]:
            self._set_status(result["error"], "danger")
            return

        backend.save_cookie_text(self.app.app_state.cookie_file, raw_text)
        self.app.app_state.region = region
        self.app.app_state.account = result["account"]
        self.app.app_state.save()
        self._set_status(f"Signed in as {result['account']['apple_id']}.", "success")
        self.app.on_signed_in(result["account"])
        QTimer.singleShot(700, self.accept)
