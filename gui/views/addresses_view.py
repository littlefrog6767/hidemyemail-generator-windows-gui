"""Addresses tab: local unused/used/trash state plus the live iCloud list."""

import os
from datetime import datetime

from PySide6.QtCore import Qt, QItemSelectionModel, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLineEdit, QMenu, QMessageBox, QTabWidget,
    QTableView, QVBoxLayout, QWidget,
)

from gui import backend
from gui.widgets import (
    DangerButton, DictTableModel, PillButton, PrimaryButton, PromptDialog,
    SecondaryButton, make_label,
)


def _format_ts(value, _row=None):
    """ISO timestamps (with microseconds/UTC offset) into the local,
    human-readable form used throughout the UI, e.g. '2026-08-05 14:32'."""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


LOCAL_COLUMNS = [
    ("email", "Email"),
    ("label", "Label"),
    ("state", "State"),
    ("source", "Source"),
    ("created_at", "Created"),
]
LOCAL_COLUMN_INDEX = {key: i for i, (key, _) in enumerate(LOCAL_COLUMNS)}

ICLOUD_COLUMNS = [
    ("label", "Label"),
    ("email", "Email"),
    ("created_at", "Created"),
    ("status", "Status"),
]

STATE_FILTERS = ("All", "unused", "used", "trash")

# Clicking the Label/State/Created headers sorts — Qt's native sortable-header
# affordance (arrow indicator, click-to-toggle) instead of a dropdown or our
# own hand-rolled click handling. State's own direction controls which of the
# two fixed group orders applies (Used>Unused>Trash or reverse); Label/
# Created control the secondary order within each state group.
SORTABLE_COLUMNS = {"label", "state", "created_at"}


class AddressesView(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._icloud_cache = []
        self._state_filter = (
            app.app_state.addresses_filter if app.app_state.addresses_filter in STATE_FILTERS else "All"
        )
        self._sort_key = (
            app.app_state.addresses_sort_key
            if app.app_state.addresses_sort_key in ("label", "created_at") else "created_at"
        )
        self._sort_dir = (
            app.app_state.addresses_sort_dir if app.app_state.addresses_sort_dir in ("asc", "desc") else "desc"
        )
        self._state_dir = (
            app.app_state.addresses_state_dir if app.app_state.addresses_state_dir in ("asc", "desc") else "asc"
        )
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._refresh_local)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(10)

        layout.addWidget(make_label("Addresses", variant="heading"))
        layout.addWidget(make_label(
            "Manage local unused/used/trash state alongside the live iCloud inventory.",
            variant="secondary",
        ))

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, stretch=1)
        self.tabs.addTab(self._build_local_tab(), "Local")
        self.tabs.addTab(self._build_icloud_tab(), "iCloud")

    # ---- Local tab ---------------------------------------------------
    def _build_local_tab(self):
        parent = QWidget()
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search address or label…")
        self.search_entry.setFixedWidth(230)
        self.search_entry.textChanged.connect(lambda _t: self._search_timer.start(200))
        toolbar.addWidget(self.search_entry)

        hint = make_label("Click Label / State / Created to sort", variant="muted")
        toolbar.addWidget(hint)

        select_all_btn = SecondaryButton("Select all")
        select_all_btn.clicked.connect(lambda: self.local_table.selectAll())
        toolbar.addWidget(select_all_btn)
        toolbar.addStretch()

        export_btn = SecondaryButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        sync_btn = PrimaryButton("Sync iCloud → Local")
        sync_btn.clicked.connect(self._sync_from_icloud)
        toolbar.addWidget(sync_btn)
        toolbar.addWidget(export_btn)
        layout.addLayout(toolbar)

        badges_row = QHBoxLayout()
        self._badge_buttons = {}
        for key in STATE_FILTERS:
            btn = PillButton(key)
            btn.clicked.connect(lambda _c=False, k=key: self._set_state_filter(k))
            badges_row.addWidget(btn)
            self._badge_buttons[key] = btn
        badges_row.addStretch()
        self._updated_label = make_label("", variant="muted")
        badges_row.addWidget(self._updated_label)
        layout.addLayout(badges_row)

        self.bulk_bar = QWidget()
        self.bulk_bar.setObjectName("BulkBar")
        bulk_layout = QHBoxLayout(self.bulk_bar)
        bulk_layout.setContentsMargins(12, 8, 12, 8)
        self.bulk_count_label = make_label("")
        bulk_layout.addWidget(self.bulk_count_label)
        edit_label_btn = SecondaryButton("Edit label…")
        edit_label_btn.clicked.connect(self._bulk_edit_label)
        bulk_layout.addWidget(edit_label_btn)
        for state in backend.ADDRESS_STATES:
            btn = SecondaryButton(f"Mark {state}")
            btn.clicked.connect(lambda _c=False, s=state: self._bulk_set_state(s))
            bulk_layout.addWidget(btn)
        copy_btn = SecondaryButton("Copy emails")
        copy_btn.clicked.connect(self._bulk_copy)
        bulk_layout.addWidget(copy_btn)
        delete_btn = DangerButton("Delete")
        delete_btn.clicked.connect(self._bulk_delete)
        bulk_layout.addWidget(delete_btn)
        clear_btn = SecondaryButton("Clear selection")
        clear_btn.clicked.connect(lambda: self.local_table.clearSelection())
        bulk_layout.addWidget(clear_btn)
        bulk_layout.addStretch()
        self.bulk_bar.setVisible(False)
        layout.addWidget(self.bulk_bar)

        self.local_model = DictTableModel(
            LOCAL_COLUMNS, row_id_key="email",
            formatters={"created_at": _format_ts},
        )
        self.local_table = QTableView()
        self.local_table.setModel(self.local_model)
        self.local_table.setAlternatingRowColors(True)
        self.local_table.setSelectionBehavior(QTableView.SelectRows)
        self.local_table.setSelectionMode(QTableView.ExtendedSelection)
        self.local_table.verticalHeader().setVisible(False)
        self.local_table.horizontalHeader().setStretchLastSection(True)
        self.local_table.setSortingEnabled(True)
        self.local_table.horizontalHeader().sortIndicatorChanged.connect(self._on_header_sort_changed)
        self.local_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.local_table.customContextMenuRequested.connect(self._show_local_context_menu)
        self.local_table.doubleClicked.connect(self._on_local_double_clicked)
        self.local_table.selectionModel().selectionChanged.connect(self._update_bulk_bar)
        layout.addWidget(self.local_table, stretch=1)

        self.local_status = make_label("", variant="secondary")
        layout.addWidget(self.local_status)
        return parent

    def _set_state_filter(self, key):
        self._state_filter = key
        self.app.app_state.addresses_filter = key
        self.app.app_state.save()
        self._refresh_local()

    def _on_header_sort_changed(self, column, order):
        try:
            key = LOCAL_COLUMNS[column][0]
        except IndexError:
            return
        if key not in SORTABLE_COLUMNS:
            return
        direction = "asc" if order == Qt.AscendingOrder else "desc"
        if key == "state":
            self._state_dir = direction
            self.app.app_state.addresses_state_dir = direction
        else:
            self._sort_key = key
            self._sort_dir = direction
            self.app.app_state.addresses_sort_key = key
            self.app.app_state.addresses_sort_dir = direction
        self.app.app_state.save()
        self._refresh_local()

    def _refresh_local(self):
        selected_before = self._selected_emails()
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            counts = {
                "All": conn.execute("SELECT COUNT(*) FROM addresses").fetchone()[0],
                "unused": conn.execute("SELECT COUNT(*) FROM addresses WHERE state='unused'").fetchone()[0],
                "used": conn.execute("SELECT COUNT(*) FROM addresses WHERE state='used'").fetchone()[0],
                "trash": conn.execute("SELECT COUNT(*) FROM addresses WHERE state='trash'").fetchone()[0],
            }
            latest_updated = conn.execute("SELECT MAX(updated_at) FROM addresses").fetchone()[0]
            state = None if self._state_filter == "All" else self._state_filter
            items = backend.list_addresses_full(
                conn, state=state, sort_key=self._sort_key, sort_dir=self._sort_dir,
                state_dir=self._state_dir, limit=5000,
            )
        finally:
            conn.close()

        query = self.search_entry.text().strip().lower()
        if query:
            items = [
                r for r in items
                if query in (r["email"] or "").lower() or query in (r["label"] or "").lower()
            ]

        for key, btn in self._badge_buttons.items():
            btn.setText(f"{key}  {counts[key]}")
            btn.set_active(self._state_filter == key)
        self._updated_label.setText(f"Updated {_format_ts(latest_updated)}" if latest_updated else "")

        header = self.local_table.horizontalHeader()
        header.blockSignals(True)
        sort_col = LOCAL_COLUMN_INDEX.get(self._sort_key, LOCAL_COLUMN_INDEX["created_at"])
        header.setSortIndicator(sort_col, Qt.AscendingOrder if self._sort_dir == "asc" else Qt.DescendingOrder)
        header.blockSignals(False)

        self.local_model.set_rows(items)
        self._reapply_selection(selected_before)
        self.local_status.setText(f"{len(items)} address(es)")
        self._update_bulk_bar()

    def _reapply_selection(self, emails):
        if not emails:
            return
        selection_model = self.local_table.selectionModel()
        for row_index, row in enumerate(self.local_model.all_rows()):
            if row.get("email") in emails:
                idx = self.local_model.index(row_index, 0)
                selection_model.select(
                    idx, QItemSelectionModel.Select | QItemSelectionModel.Rows
                )

    # ---- selection / bulk actions --------------------------------------
    def _selected_emails(self):
        rows = {idx.row() for idx in self.local_table.selectionModel().selectedRows()}
        return [self.local_model.row_at(r)["email"] for r in rows]

    def _update_bulk_bar(self, *_args):
        selected = self._selected_emails()
        self.bulk_bar.setVisible(bool(selected))
        if selected:
            self.bulk_count_label.setText(f"{len(selected)} selected")

    def _edit_label(self, email, current_label):
        def on_submit(value):
            conn = backend.connect_db(self.app.app_state.db_file)
            try:
                backend.set_label(conn, email, value)
            finally:
                conn.close()
            self._refresh_local()
            self._push_labels_to_icloud([email], value)

        PromptDialog(self, "Edit label", f"Label for {email}:", initial=current_label or "", on_submit=on_submit).exec()

    def _bulk_edit_label(self):
        selected = self._selected_emails()
        if not selected:
            return

        def on_submit(value):
            conn = backend.connect_db(self.app.app_state.db_file)
            try:
                backend.bulk_set_label(conn, selected, value)
            finally:
                conn.close()
            self._refresh_local()
            self._push_labels_to_icloud(selected, value)

        PromptDialog(
            self, "Edit label", f"Set label for {len(selected)} address(es):", on_submit=on_submit,
        ).exec()

    def _push_labels_to_icloud(self, emails, label):
        """Best-effort: also update the label on iCloud itself, not just the
        local copy, so it doesn't drift out of sync. Only meaningful for
        addresses that actually exist on iCloud — purely local/manual
        entries just fail this call and the local edit still stands."""
        if not self.app.app_state.is_signed_in:
            return
        self.local_status.setText(f"Saved locally. Syncing {len(emails)} label(s) to iCloud…")

        async def _push_all():
            ok, failed = 0, 0
            for email in emails:
                result = await backend.update_metadata(
                    self.app.app_state.cookie_file, self.app.app_state.region, email, label, None,
                )
                if result.get("ok"):
                    ok += 1
                else:
                    failed += 1
            return ok, failed

        self.app.worker.run_coro(_push_all(), on_done=self._on_labels_pushed)

    def _on_labels_pushed(self, result, error):
        if error is not None:
            self.local_status.setText(f"Saved locally, but iCloud sync errored: {error}")
            return
        ok, failed = result
        if failed and ok:
            self.local_status.setText(
                f"Synced {ok} label(s) to iCloud, {failed} failed (not on iCloud, or offline)."
            )
        elif failed:
            self.local_status.setText(
                f"Saved locally, but iCloud sync failed for {failed} address(es) (not on iCloud, or offline)."
            )
        else:
            self.local_status.setText(f"Label updated locally and on iCloud ({ok}).")

    def _bulk_set_state(self, state):
        selected = self._selected_emails()
        if not selected:
            return
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            backend.bulk_set_state(conn, selected, state)
        finally:
            conn.close()
        self._refresh_local()

    def _bulk_copy(self):
        selected = self._selected_emails()
        if not selected:
            return
        QApplication.clipboard().setText("\n".join(selected))
        self.local_status.setText(f"Copied {len(selected)} address(es) to clipboard.")

    def _bulk_delete(self):
        selected = self._selected_emails()
        if not selected:
            return
        reply = QMessageBox.question(
            self, "Delete addresses",
            f"Permanently delete {len(selected)} address(es) from the local database?\n\n"
            "This only removes them from this app's local list — it does not deactivate "
            "them on iCloud.",
        )
        if reply != QMessageBox.Yes:
            return
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            backend.delete_addresses(conn, selected)
        finally:
            conn.close()
        self._refresh_local()

    def _set_state(self, email, new_state):
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            backend.mark_address(conn, email, new_state)
        finally:
            conn.close()
        self._refresh_local()

    def _on_local_double_clicked(self, index):
        row = self.local_model.row_at(index.row())
        key = LOCAL_COLUMNS[index.column()][0]
        if key == "label":
            self._edit_label(row["email"], row.get("label"))
        elif key == "email":
            self._copy(row["email"])
            self.local_status.setText(f"Copied {row['email']}.")

    def _show_local_context_menu(self, point):
        index = self.local_table.indexAt(point)
        if index.isValid() and index.row() not in {i.row() for i in self.local_table.selectionModel().selectedRows()}:
            self.local_table.selectRow(index.row())
        selected = self._selected_emails()
        if not selected:
            return
        menu = QMenu(self)
        label_text = "Edit label…" if len(selected) == 1 else f"Edit label for {len(selected)}…"
        edit_action = QAction(label_text, self)
        if len(selected) == 1:
            row = self.local_model.row_at(index.row())
            edit_action.triggered.connect(lambda: self._edit_label(row["email"], row.get("label")))
        else:
            edit_action.triggered.connect(self._bulk_edit_label)
        menu.addAction(edit_action)
        menu.addSeparator()
        for state in backend.ADDRESS_STATES:
            action = QAction(f"Mark {state}", self)
            action.triggered.connect(lambda _c=False, s=state: self._bulk_set_state(s))
            menu.addAction(action)
        menu.addSeparator()
        copy_action = QAction("Copy email(s)", self)
        copy_action.triggered.connect(self._bulk_copy)
        menu.addAction(copy_action)
        menu.addSeparator()
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(self._bulk_delete)
        menu.addAction(delete_action)
        menu.exec(self.local_table.viewport().mapToGlobal(point))

    def _copy(self, text):
        QApplication.clipboard().setText(text)

    def _export_csv(self):
        try:
            outputs = backend.export_csv_files(self.app.app_state.db_file, self.app.app_state.export_dir)
        except OSError as exc:
            self.local_status.setText(f"Export failed: {exc}")
            return
        self.local_status.setText(f"Exported to {outputs['addresses'].parent}")
        try:
            os.startfile(outputs["addresses"].parent)  # noqa: S606 - opening our own export dir
        except OSError:
            pass

    def _sync_from_icloud(self):
        if not self.app.app_state.is_signed_in:
            self.local_status.setText("Sign in first.")
            return
        self.local_status.setText("Syncing from iCloud…")

        async def _fetch_both():
            active = await backend.list_emails(
                self.app.app_state.cookie_file, self.app.app_state.region, None, True
            )
            inactive = await backend.list_emails(
                self.app.app_state.cookie_file, self.app.app_state.region, None, False
            )
            return active, inactive

        self.app.worker.run_coro(_fetch_both(), on_done=self._on_sync_done)

    def _on_sync_done(self, result, error):
        if error is not None:
            self.local_status.setText(f"Sync failed: {error}")
            return
        active, inactive = result
        if not active["ok"] or not inactive["ok"]:
            msg = (active.get("error") or inactive.get("error") or {}).get("message", "Sync failed")
            self.local_status.setText(msg)
            return

        addresses = active["addresses"] + inactive["addresses"]
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            for addr in addresses:
                backend.upsert_address(
                    conn, addr["email"], label=addr["label"], state="unused",
                    source="icloud", note="Synced from iCloud",
                )
        finally:
            conn.close()

        self._icloud_cache = addresses
        self.local_status.setText(f"Synced {len(addresses)} address(es) from iCloud.")
        self._refresh_local()
        self._refresh_icloud()

    # ---- iCloud tab ----------------------------------------------------
    def _build_icloud_tab(self):
        parent = QWidget()
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        refresh_btn = PrimaryButton("Refresh from iCloud")
        refresh_btn.clicked.connect(self._sync_from_icloud)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        self.icloud_model = DictTableModel(
            ICLOUD_COLUMNS, row_id_key="email", formatters={"created_at": _format_ts},
        )
        self.icloud_table = QTableView()
        self.icloud_table.setModel(self.icloud_model)
        self.icloud_table.setAlternatingRowColors(True)
        self.icloud_table.setSelectionBehavior(QTableView.SelectRows)
        self.icloud_table.verticalHeader().setVisible(False)
        self.icloud_table.horizontalHeader().setStretchLastSection(True)
        self.icloud_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.icloud_table.customContextMenuRequested.connect(self._show_icloud_context_menu)
        self.icloud_table.doubleClicked.connect(self._on_icloud_double_clicked)
        layout.addWidget(self.icloud_table, stretch=1)

        self.icloud_status = make_label("Not synced yet.", variant="secondary")
        layout.addWidget(self.icloud_status)
        return parent

    def _refresh_icloud(self):
        rows = []
        for addr in self._icloud_cache:
            row = dict(addr)
            row["status"] = "Active" if addr["is_active"] else "Inactive"
            rows.append(row)
        self.icloud_model.set_rows(rows)
        self.icloud_status.setText(f"{len(rows)} address(es) on iCloud")

    def _on_icloud_double_clicked(self, index):
        row = self.icloud_model.row_at(index.row())
        self._toggle_active(row["email"], not row["is_active"])

    def _show_icloud_context_menu(self, point):
        index = self.icloud_table.indexAt(point)
        if not index.isValid():
            return
        row = self.icloud_model.row_at(index.row())
        menu = QMenu(self)
        label = "Deactivate" if row["is_active"] else "Reactivate"
        action = QAction(label, self)
        action.triggered.connect(lambda: self._toggle_active(row["email"], not row["is_active"]))
        menu.addAction(action)
        copy_action = QAction("Copy email", self)
        copy_action.triggered.connect(lambda: self._copy(row["email"]))
        menu.addAction(copy_action)
        menu.exec(self.icloud_table.viewport().mapToGlobal(point))

    def _toggle_active(self, email, new_active):
        self.icloud_status.setText(f"Updating {email}…")
        self.app.worker.run_coro(
            backend.set_active(self.app.app_state.cookie_file, self.app.app_state.region, email, new_active),
            on_done=self._on_toggle_done,
        )

    def _on_toggle_done(self, result, error):
        if error is not None or not result.get("ok"):
            msg = error or (result.get("error") or {}).get("message", "Failed to update")
            self.icloud_status.setText(str(msg))
            return
        for addr in self._icloud_cache:
            if addr["email"] == result["email"]:
                addr["is_active"] = result["is_active"]
        self._refresh_icloud()
        self.icloud_status.setText(f"Updated {result['email']}.")

    def refresh(self):
        self._refresh_local()
        self._refresh_icloud()
