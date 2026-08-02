"""Addresses tab: local unused/used/trash state plus the live iCloud list."""

import os

import customtkinter as ctk

from gui import backend, theme
from gui.widgets import Card, PrimaryButton, SecondaryButton, SimpleTable

LOCAL_COLUMNS = [
    ("email", "Email", 4),
    ("label", "Label", 2),
    ("state", "State", 2),
    ("source", "Source", 2),
    ("updated_at", "Updated", 2),
    ("copy", "", 1),
]

ICLOUD_COLUMNS = [
    ("label", "Label", 2),
    ("email", "Email", 4),
    ("created_at", "Created", 2),
    ("status", "Status", 1),
    ("actions", "", 2),
]


class AddressesView(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self._icloud_cache = []
        self._search_after_id = None
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(28, 10))
        ctk.CTkLabel(
            header, text="Addresses", font=(theme.FONT_FAMILY, 22, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Manage local unused/used/trash state alongside the live iCloud inventory.",
            text_color=theme.TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        self.tabs = ctk.CTkTabview(
            self,
            fg_color=theme.BG_CARD,
            segmented_button_selected_color=theme.ACCENT,
            segmented_button_selected_hover_color=theme.ACCENT_HOVER,
            segmented_button_unselected_color=theme.BG_CARD_ALT,
            text_color=theme.TEXT_PRIMARY,
        )
        self.tabs.pack(fill="both", expand=True, padx=28, pady=(0, 28))
        self.tabs.add("Local")
        self.tabs.add("iCloud")

        self._build_local_tab(self.tabs.tab("Local"))
        self._build_icloud_tab(self.tabs.tab("iCloud"))

    # ---- Local tab ---------------------------------------------------
    def _build_local_tab(self, parent):
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.pack(fill="x", padx=4, pady=(10, 10))

        self.search_var = ctk.StringVar()
        search = ctk.CTkEntry(
            toolbar, placeholder_text="Search address or label…", textvariable=self.search_var,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER, width=260,
        )
        search.pack(side="left")
        search.bind("<KeyRelease>", lambda _e: self._schedule_refresh_local())

        self.state_filter_var = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(
            toolbar, values=["All", "unused", "used", "trash"], variable=self.state_filter_var,
            command=lambda _v: self._refresh_local(), fg_color=theme.BG_INPUT,
            button_color=theme.BG_CARD_ALT, button_hover_color=theme.SIDEBAR_HOVER,
            width=120,
        ).pack(side="left", padx=(10, 0))

        SecondaryButton(toolbar, text="Export CSV", command=self._export_csv).pack(
            side="right"
        )
        PrimaryButton(toolbar, text="Sync iCloud → Local", command=self._sync_from_icloud).pack(
            side="right", padx=(0, 10)
        )

        self.local_table = SimpleTable(parent, LOCAL_COLUMNS)
        self.local_table.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self.local_status = ctk.CTkLabel(parent, text="", text_color=theme.TEXT_SECONDARY)
        self.local_status.pack(anchor="w", padx=4, pady=(4, 0))

    def _schedule_refresh_local(self):
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(200, self._refresh_local)

    def _refresh_local(self):
        self._search_after_id = None
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            state = self.state_filter_var.get()
            rows = backend.list_addresses(conn, None if state == "All" else state, limit=500)
        finally:
            conn.close()

        query = self.search_var.get().strip().lower()
        items = [dict(row) for row in rows]
        if query:
            items = [
                r for r in items
                if query in (r["email"] or "").lower() or query in (r["label"] or "").lower()
            ]

        self.local_table.set_rows(items, cell_builder=self._local_cell, empty_text="No local addresses yet — generate or sync some.")
        self.local_status.configure(text=f"{len(items)} address(es)")

    def _local_cell(self, row_index, col_index, key, row):
        if key == "state":
            var = ctk.StringVar(value=row["state"])
            menu = ctk.CTkOptionMenu(
                self.local_table, values=list(backend.ADDRESS_STATES), variable=var,
                width=100, height=26, fg_color=theme.BG_CARD_ALT, button_color=theme.BG_CARD_ALT,
                button_hover_color=theme.SIDEBAR_HOVER,
                command=lambda choice, email=row["email"]: self._set_state(email, choice),
            )
            return menu
        if key == "copy":
            return SecondaryButton(
                self.local_table, text="Copy", width=60, height=26,
                font=(theme.FONT_FAMILY, 11),
                command=lambda email=row["email"]: self._copy(email),
            )
        return None

    def _set_state(self, email, new_state):
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            backend.mark_address(conn, email, new_state)
        finally:
            conn.close()
        self._refresh_local()

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)

    def _export_csv(self):
        try:
            outputs = backend.export_csv_files(self.app.app_state.db_file, self.app.app_state.export_dir)
        except OSError as exc:
            self.local_status.configure(text=f"Export failed: {exc}", text_color=theme.DANGER)
            return
        self.local_status.configure(
            text=f"Exported to {outputs['addresses'].parent}", text_color=theme.SUCCESS
        )
        try:
            os.startfile(outputs["addresses"].parent)  # noqa: S606 - opening our own export dir
        except OSError:
            pass

    def _sync_from_icloud(self):
        if not self.app.app_state.is_signed_in:
            self.local_status.configure(text="Sign in first.", text_color=theme.DANGER)
            return
        self.local_status.configure(text="Syncing from iCloud…", text_color=theme.TEXT_SECONDARY)

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
            self.local_status.configure(text=f"Sync failed: {error}", text_color=theme.DANGER)
            return
        active, inactive = result
        if not active["ok"] or not inactive["ok"]:
            msg = (active.get("error") or inactive.get("error") or {}).get("message", "Sync failed")
            self.local_status.configure(text=msg, text_color=theme.DANGER)
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
        self.local_status.configure(
            text=f"Synced {len(addresses)} address(es) from iCloud.", text_color=theme.SUCCESS
        )
        self._refresh_local()
        self._refresh_icloud()

    # ---- iCloud tab ----------------------------------------------------
    def _build_icloud_tab(self, parent):
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.pack(fill="x", padx=4, pady=(10, 10))
        PrimaryButton(toolbar, text="Refresh from iCloud", command=self._sync_from_icloud).pack(
            side="right"
        )

        self.icloud_table = SimpleTable(parent, ICLOUD_COLUMNS)
        self.icloud_table.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self.icloud_status = ctk.CTkLabel(parent, text="Not synced yet.", text_color=theme.TEXT_SECONDARY)
        self.icloud_status.pack(anchor="w", padx=4, pady=(4, 0))

    def _refresh_icloud(self):
        rows = []
        for addr in self._icloud_cache:
            row = dict(addr)
            row["status"] = "Active" if addr["is_active"] else "Inactive"
            rows.append(row)
        self.icloud_table.set_rows(
            rows, cell_builder=self._icloud_cell,
            empty_text="Nothing synced yet — click Refresh from iCloud.",
        )
        self.icloud_status.configure(text=f"{len(rows)} address(es) on iCloud")

    def _icloud_cell(self, row_index, col_index, key, row):
        if key == "actions":
            is_active = row["is_active"]
            label = "Deactivate" if is_active else "Reactivate"
            btn_cls = SecondaryButton if is_active else PrimaryButton
            return btn_cls(
                self.icloud_table, text=label, width=100, height=26,
                font=(theme.FONT_FAMILY, 11),
                command=lambda email=row["email"], active=is_active: self._toggle_active(email, not active),
            )
        return None

    def _toggle_active(self, email, new_active):
        self.icloud_status.configure(text=f"Updating {email}…", text_color=theme.TEXT_SECONDARY)
        self.app.worker.run_coro(
            backend.set_active(self.app.app_state.cookie_file, self.app.app_state.region, email, new_active),
            on_done=self._on_toggle_done,
        )

    def _on_toggle_done(self, result, error):
        if error is not None or not result.get("ok"):
            msg = error or (result.get("error") or {}).get("message", "Failed to update")
            self.icloud_status.configure(text=str(msg), text_color=theme.DANGER)
            return
        for addr in self._icloud_cache:
            if addr["email"] == result["email"]:
                addr["is_active"] = result["is_active"]
        self._refresh_icloud()
        self.icloud_status.configure(text=f"Updated {result['email']}.", text_color=theme.SUCCESS)

    def refresh(self):
        self._refresh_local()
        self._refresh_icloud()
