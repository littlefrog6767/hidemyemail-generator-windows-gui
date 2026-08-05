"""Generate tab: create one address or a small batch with a custom label."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QVBoxLayout, QWidget,
)

from gui import backend
from gui.widgets import Card, PrimaryButton, SecondaryButton, make_label


class GenerateView(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(10)

        heading = make_label("Generate addresses", variant="heading")
        layout.addWidget(heading)
        layout.addWidget(make_label("Create Hide My Email addresses immediately.", variant="secondary"))

        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        inner = QGridLayout()
        inner.setVerticalSpacing(8)
        card_layout.addLayout(inner)

        inner.addWidget(make_label("EMAIL DETAILS", variant="section"), 0, 0, 1, 2)

        inner.addWidget(make_label("Label", variant="secondary"), 1, 0)
        self.label_entry = QLineEdit("generated")
        self.label_entry.setFixedWidth(280)
        inner.addWidget(self.label_entry, 1, 1)

        inner.addWidget(make_label("Quantity", variant="secondary"), 2, 0)
        qty_row = QHBoxLayout()
        self.qty_entry = QLineEdit("1")
        self.qty_entry.setFixedWidth(80)
        qty_row.addWidget(self.qty_entry)
        qty_row.addWidget(make_label("email(s) — max 50 at a time", variant="secondary"))
        qty_row.addStretch()
        inner.addLayout(qty_row, 2, 1)

        layout.addWidget(card)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.generate_btn = PrimaryButton("Generate Email")
        self.generate_btn.setFixedWidth(180)
        self.generate_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self.generate_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.status_label = make_label("", variant="secondary")
        self.status_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.status_label)

        results_card = Card()
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(18, 14, 18, 18)
        row = QHBoxLayout()
        row.addWidget(make_label("JUST GENERATED", variant="section"))
        row.addStretch()
        copy_btn = SecondaryButton("Copy all")
        copy_btn.clicked.connect(self._copy_all)
        row.addWidget(copy_btn)
        results_layout.addLayout(row)

        self.results_box = QTextEdit()
        self.results_box.setReadOnly(True)
        results_layout.addWidget(self.results_box)
        layout.addWidget(results_card, stretch=1)

    def _copy_all(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.results_box.toPlainText().strip())

    def _on_generate(self):
        if not self.app.app_state.is_signed_in:
            self.status_label.setText("Sign in first — use the account button in the top-right.")
            self.status_label.setProperty("variant", "danger")
            self._repolish_status()
            return

        label = self.label_entry.text().strip() or "generated"
        try:
            count = int(self.qty_entry.text())
        except ValueError:
            count = 1
        count = max(1, min(50, count))
        self.qty_entry.setText(str(count))

        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Generating…")
        self.status_label.setText(f"Generating {count} email(s)…")
        self.status_label.setProperty("variant", "secondary")
        self._repolish_status()
        self.app.worker.run_coro(
            backend.generate_emails(self.app.app_state.cookie_file, self.app.app_state.region, label, count),
            on_done=self._on_done,
        )

    def _repolish_status(self):
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _on_done(self, result, error):
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("Generate Email")
        if error is not None:
            self.status_label.setText(f"Error: {error}")
            self.status_label.setProperty("variant", "danger")
            self._repolish_status()
            return

        emails = result["emails"]
        if emails:
            self.results_box.append("\n".join(emails))

        if result["ok"]:
            self.status_label.setText(f"Generated {len(emails)} email(s).")
            self.status_label.setProperty("variant", "success")
        else:
            msg = (result["error"] or {}).get("message", "Some addresses failed to generate.")
            self.status_label.setText(f"Generated {len(emails)} of the requested amount — {msg}")
            self.status_label.setProperty("variant", "warning")
        self._repolish_status()
        self.app.on_addresses_changed()
