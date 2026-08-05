"""Inbox tab: connect a receiving mailbox via IMAP and pull verification
codes from forwarded Hide My Email messages. Everything here — the mailbox
credentials and the synced messages — stays in the local sqlite db and a
local inbox_config.json, same as the upstream CLI."""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QGridLayout, QHBoxLayout, QLineEdit, QMenu,
    QTableView, QVBoxLayout, QWidget,
)

from gui import backend
from gui.widgets import Card, DictTableModel, PrimaryButton, SecondaryButton, make_label

MESSAGE_COLUMNS = [
    ("received_at", "Received"),
    ("hme_address", "Hide My Email"),
    ("sender", "From"),
    ("subject", "Subject"),
    ("code", "Code"),
]


class InboxView(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._build()
        self._load_config_into_form()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(10)

        layout.addWidget(make_label("Inbox", variant="heading"))
        layout.addWidget(make_label(
            "Connect a receiving mailbox and extract verification codes locally.",
            variant="secondary",
        ))

        config_card = Card()
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(22, 20, 22, 20)
        inner = QGridLayout()
        inner.setVerticalSpacing(6)
        inner.setColumnStretch(1, 1)
        inner.setColumnStretch(3, 1)
        config_layout.addLayout(inner)

        inner.addWidget(make_label("CONNECT A RECEIVING MAILBOX", variant="section"), 0, 0, 1, 4)

        inner.addWidget(make_label("IMAP host", variant="secondary"), 1, 0)
        self.host_entry = QLineEdit()
        inner.addWidget(self.host_entry, 2, 0)

        inner.addWidget(make_label("Port", variant="secondary"), 1, 1)
        self.port_entry = QLineEdit("993")
        inner.addWidget(self.port_entry, 2, 1)

        inner.addWidget(make_label("Username", variant="secondary"), 3, 0)
        self.user_entry = QLineEdit()
        inner.addWidget(self.user_entry, 4, 0)

        inner.addWidget(make_label("Password (app password recommended)", variant="secondary"), 3, 1)
        self.pass_entry = QLineEdit()
        self.pass_entry.setEchoMode(QLineEdit.Password)
        inner.addWidget(self.pass_entry, 4, 1)

        inner.addWidget(make_label("Folder", variant="secondary"), 5, 0)
        self.folder_entry = QLineEdit("INBOX")
        inner.addWidget(self.folder_entry, 6, 0)

        self.ssl_checkbox = QCheckBox("Use SSL")
        self.ssl_checkbox.setChecked(True)
        inner.addWidget(self.ssl_checkbox, 6, 1)

        btn_row = QHBoxLayout()
        save_btn = PrimaryButton("Save Settings")
        save_btn.clicked.connect(self._save_config)
        sync_btn = SecondaryButton("Sync Now")
        sync_btn.clicked.connect(self._sync)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(sync_btn)
        btn_row.addStretch()
        inner.addLayout(btn_row, 7, 0, 1, 4)

        self.config_status = make_label("", variant="secondary")
        inner.addWidget(self.config_status, 8, 0, 1, 4)

        layout.addWidget(config_card)

        messages_card = Card()
        messages_layout = QVBoxLayout(messages_card)
        messages_layout.setContentsMargins(18, 14, 18, 18)
        toolbar = QHBoxLayout()
        toolbar.addWidget(make_label("MESSAGES", variant="section"))
        self.only_codes_checkbox = QCheckBox("Only show codes")
        self.only_codes_checkbox.stateChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.only_codes_checkbox)
        toolbar.addStretch()
        export_btn = SecondaryButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        toolbar.addWidget(export_btn)
        messages_layout.addLayout(toolbar)

        self.model = DictTableModel(MESSAGE_COLUMNS, row_id_key=None)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        messages_layout.addWidget(self.table)

        layout.addWidget(messages_card, stretch=1)

    def _load_config_into_form(self):
        try:
            config = backend.load_inbox_config(self.app.app_state.inbox_config_file)
        except FileNotFoundError:
            return
        self.host_entry.setText(config.host)
        self.port_entry.setText(str(config.port))
        self.user_entry.setText(config.username)
        self.pass_entry.setText(config.password)
        self.folder_entry.setText(config.folder)
        self.ssl_checkbox.setChecked(config.use_ssl)

    def _build_config(self):
        try:
            port = int(self.port_entry.text())
        except ValueError:
            port = 993
        return backend.InboxConfig(
            host=self.host_entry.text().strip(),
            port=port,
            username=self.user_entry.text().strip(),
            password=self.pass_entry.text(),
            folder=self.folder_entry.text().strip() or "INBOX",
            use_ssl=self.ssl_checkbox.isChecked(),
        )

    def _set_status(self, text, variant):
        self.config_status.setText(text)
        self.config_status.setProperty("variant", variant)
        self.config_status.style().unpolish(self.config_status)
        self.config_status.style().polish(self.config_status)

    def _save_config(self):
        config = self._build_config()
        if not config.host or not config.username:
            self._set_status("Host and username are required.", "danger")
            return
        backend.save_inbox_config(config, self.app.app_state.inbox_config_file)
        self._set_status(f"Saved. Mailbox: {backend.mask_account(config.username)}", "success")

    def _sync(self):
        config = self._build_config()
        if not config.host or not config.username:
            self._set_status("Host and username are required.", "danger")
            return
        backend.save_inbox_config(config, self.app.app_state.inbox_config_file)
        self._set_status("Syncing…", "secondary")
        self.app.worker.run_sync(
            backend.sync_inbox, config, self.app.app_state.db_file, 50, on_done=self._on_sync_done
        )

    def _on_sync_done(self, inserted, error):
        if error is not None:
            self._set_status(f"Sync failed: {error}", "danger")
            return
        self._set_status(f"Synced — {len(inserted)} new message(s).", "success")
        self._refresh_messages()
        self.app.on_addresses_changed()

    def _on_filter_changed(self):
        self._refresh_messages()

    def _refresh_messages(self):
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            rows = backend.list_messages(
                conn, only_codes=self.only_codes_checkbox.isChecked(), limit=5000
            )
        finally:
            conn.close()
        items = [dict(row) for row in rows]
        self.model.set_rows(items)

    def _row_at_point(self, point):
        index = self.table.indexAt(point)
        if not index.isValid():
            return None
        return self.model.row_at(index.row())

    def _on_row_double_clicked(self, index):
        row = self.model.row_at(index.row())
        code = row.get("code") or ""
        if code:
            self._copy(code)
            self._set_status(f"Copied code {code}.", "success")

    def _show_context_menu(self, point):
        row = self._row_at_point(point)
        if row is None:
            return
        menu = QMenu(self)
        code = row.get("code") or ""
        if code:
            copy_action = QAction(f"Copy code ({code})", self)
            copy_action.triggered.connect(lambda: self._copy(code))
            menu.addAction(copy_action)
        if row.get("hme_address"):
            copy_addr = QAction("Copy Hide My Email address", self)
            copy_addr.triggered.connect(lambda: self._copy(row["hme_address"]))
            menu.addAction(copy_addr)
        if not menu.isEmpty():
            menu.exec(self.table.viewport().mapToGlobal(point))

    def _copy(self, text):
        QApplication.clipboard().setText(text)

    def _export_csv(self):
        try:
            outputs = backend.export_csv_files(self.app.app_state.db_file, self.app.app_state.export_dir)
        except OSError as exc:
            self._set_status(f"Export failed: {exc}", "danger")
            return
        self._set_status(f"Exported to {outputs['messages'].parent}", "success")
        try:
            os.startfile(outputs["messages"].parent)  # noqa: S606 - opening our own export dir
        except OSError:
            pass

    def refresh(self):
        self._refresh_messages()
