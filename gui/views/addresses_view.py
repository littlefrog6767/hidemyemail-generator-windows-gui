"""Addresses tab: local unused/used/trash state plus the live iCloud list."""

import os
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from gui import backend, theme
from gui.widgets import DangerButton, PrimaryButton, PromptDialog, SecondaryButton, SimpleTable


def _format_ts(value):
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
    ("select", "", 0),
    ("email", "Email", 4),
    ("label", "Label", 2),
    ("state", "State", 2),
    ("source", "Source", 1),
    ("created_at", "Created", 2),
    ("copy", "", 1),
]

ICLOUD_COLUMNS = [
    ("label", "Label", 2),
    ("email", "Email", 4),
    ("created_at", "Created", 2),
    ("status", "Status", 1),
    ("actions", "", 2),
]

STATE_FILTERS = ("All", "unused", "used", "trash")

# Order matters here — this is also the display order of the sort dropdown.
SORT_OPTIONS = [
    (backend.SORT_CREATED_DESC, "Newest created"),
    (backend.SORT_CREATED_ASC, "Oldest created"),
    (backend.SORT_LABEL_ASC, "Label A–Z"),
]
SORT_LABEL_TO_KEY = {label: key for key, label in SORT_OPTIONS}
SORT_KEY_TO_LABEL = {key: label for key, label in SORT_OPTIONS}


class AddressesView(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self._icloud_cache = []
        self._search_after_id = None
        self._state_filter = (
            app.app_state.addresses_filter if app.app_state.addresses_filter in STATE_FILTERS else "All"
        )
        self._checkbox_vars = {}  # email -> BooleanVar, persists across refreshes
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
        toolbar.pack(fill="x", padx=4, pady=(10, 8))

        self.search_var = ctk.StringVar()
        search = ctk.CTkEntry(
            toolbar, placeholder_text="Search address or label…", textvariable=self.search_var,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER, width=230,
        )
        search.pack(side="left")
        search.bind("<KeyRelease>", lambda _e: self._schedule_refresh_local())

        ctk.CTkLabel(toolbar, text="Sort", text_color=theme.TEXT_SECONDARY).pack(
            side="left", padx=(14, 6)
        )
        initial_sort_label = SORT_KEY_TO_LABEL.get(self.app.app_state.addresses_sort, SORT_OPTIONS[0][1])
        self.sort_var = ctk.StringVar(value=initial_sort_label)
        ctk.CTkOptionMenu(
            toolbar, values=[label for _, label in SORT_OPTIONS], variable=self.sort_var,
            command=lambda _v: self._on_sort_changed(), fg_color=theme.BG_INPUT,
            button_color=theme.BG_CARD_ALT, button_hover_color=theme.SIDEBAR_HOVER,
            width=150,
        ).pack(side="left")

        self.select_all_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            toolbar, text="Select all", variable=self.select_all_var,
            text_color=theme.TEXT_SECONDARY, command=self._on_select_all_toggle,
        ).pack(side="left", padx=(16, 0))

        SecondaryButton(toolbar, text="Export CSV", command=self._export_csv).pack(
            side="right"
        )
        PrimaryButton(toolbar, text="Sync iCloud → Local", command=self._sync_from_icloud).pack(
            side="right", padx=(0, 10)
        )

        badges_row = ctk.CTkFrame(parent, fg_color="transparent")
        badges_row.pack(fill="x", padx=4, pady=(0, 10))
        self._badge_buttons = {}
        for key in STATE_FILTERS:
            btn = ctk.CTkButton(
                badges_row, text=key, width=92, height=28, corner_radius=14,
                font=(theme.FONT_FAMILY, 12, "bold"),
                command=lambda k=key: self._set_state_filter(k),
            )
            btn.pack(side="left", padx=(0, 8))
            self._badge_buttons[key] = btn
        self._updated_label = ctk.CTkLabel(
            badges_row, text="", text_color=theme.TEXT_MUTED, font=(theme.FONT_FAMILY, 11)
        )
        self._updated_label.pack(side="right")

        # Bulk action bar — only shown while 1+ rows are selected. Packed into
        # a slot that's always in place (right before the table) so toggling
        # the bar's own pack/pack_forget doesn't need positioning relative to
        # a CTkScrollableFrame sibling (which pack(before=...) can't target).
        self.bulk_bar_slot = ctk.CTkFrame(parent, fg_color="transparent")
        self.bulk_bar_slot.pack(fill="x", padx=4)
        self.bulk_bar = ctk.CTkFrame(self.bulk_bar_slot, fg_color=theme.BG_CARD_ALT, corner_radius=8)
        self.bulk_count_label = ctk.CTkLabel(
            self.bulk_bar, text="", text_color=theme.TEXT_PRIMARY, font=(theme.FONT_FAMILY, 12, "bold"),
        )
        self.bulk_count_label.pack(side="left", padx=(12, 14), pady=8)
        SecondaryButton(
            self.bulk_bar, text="Edit label…", width=100, height=26, command=self._bulk_edit_label,
        ).pack(side="left", padx=(0, 8), pady=8)
        for state in backend.ADDRESS_STATES:
            SecondaryButton(
                self.bulk_bar, text=f"Mark {state}", width=100, height=26,
                command=lambda s=state: self._bulk_set_state(s),
            ).pack(side="left", padx=(0, 8), pady=8)
        SecondaryButton(
            self.bulk_bar, text="Copy emails", width=100, height=26, command=self._bulk_copy,
        ).pack(side="left", padx=(0, 8), pady=8)
        DangerButton(
            self.bulk_bar, text="Delete", width=90, height=26, command=self._bulk_delete,
        ).pack(side="left", padx=(0, 8), pady=8)
        SecondaryButton(
            self.bulk_bar, text="Clear selection", width=112, height=26, command=self._clear_selection,
        ).pack(side="left", pady=8)
        # Not packed yet — _update_bulk_bar() shows/hides it based on selection.

        self.local_table = SimpleTable(parent, LOCAL_COLUMNS)
        self.local_table.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self.local_status = ctk.CTkLabel(parent, text="", text_color=theme.TEXT_SECONDARY)
        self.local_status.pack(anchor="w", padx=4, pady=(4, 0))

    def _schedule_refresh_local(self):
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(200, self._refresh_local)

    def _set_state_filter(self, key):
        self._state_filter = key
        self.app.app_state.addresses_filter = key
        self.app.app_state.save()
        self._refresh_local()

    def _on_sort_changed(self):
        sort_key = SORT_LABEL_TO_KEY.get(self.sort_var.get(), backend.SORT_CREATED_DESC)
        self.app.app_state.addresses_sort = sort_key
        self.app.app_state.save()
        self._refresh_local()

    def _refresh_local(self):
        self._search_after_id = None
        sort_key = SORT_LABEL_TO_KEY.get(self.sort_var.get(), backend.SORT_CREATED_DESC)
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            counts = {
                "All": conn.execute("SELECT COUNT(*) FROM addresses").fetchone()[0],
                "unused": conn.execute(
                    "SELECT COUNT(*) FROM addresses WHERE state='unused'"
                ).fetchone()[0],
                "used": conn.execute(
                    "SELECT COUNT(*) FROM addresses WHERE state='used'"
                ).fetchone()[0],
                "trash": conn.execute(
                    "SELECT COUNT(*) FROM addresses WHERE state='trash'"
                ).fetchone()[0],
            }
            latest_updated = conn.execute("SELECT MAX(updated_at) FROM addresses").fetchone()[0]
            state = None if self._state_filter == "All" else self._state_filter
            items = backend.list_addresses_full(conn, state=state, sort=sort_key, limit=500)
        finally:
            conn.close()

        query = self.search_var.get().strip().lower()
        if query:
            items = [
                r for r in items
                if query in (r["email"] or "").lower() or query in (r["label"] or "").lower()
            ]

        visible_emails = {i["email"] for i in items}
        self._checkbox_vars = {e: v for e, v in self._checkbox_vars.items() if e in visible_emails}

        for key, btn in self._badge_buttons.items():
            active = self._state_filter == key
            btn.configure(
                text=f"{key}  {counts[key]}",
                fg_color=theme.ACCENT if active else theme.BG_CARD_ALT,
                text_color="#ffffff" if active else theme.TEXT_SECONDARY,
            )
        self._updated_label.configure(
            text=f"Updated {_format_ts(latest_updated)}" if latest_updated else ""
        )

        self.local_table.set_rows(
            items, cell_builder=self._local_cell,
            empty_text="No local addresses yet — generate or sync some.",
        )
        self.local_status.configure(text=f"{len(items)} address(es)")
        self._update_bulk_bar()

    def _local_cell(self, row_index, col_index, key, row):
        if key == "select":
            email = row["email"]
            var = self._checkbox_vars.get(email)
            if var is None:
                var = ctk.BooleanVar(value=False)
                self._checkbox_vars[email] = var
            return ctk.CTkCheckBox(
                self.local_table, text="", variable=var, width=20,
                checkbox_width=18, checkbox_height=18, command=self._update_bulk_bar,
            )
        if key == "label":
            return SecondaryButton(
                self.local_table, text=row["label"] or "(no label)", anchor="w",
                fg_color="transparent", border_width=0, hover_color=theme.SIDEBAR_HOVER,
                font=(theme.FONT_FAMILY, 12), height=26,
                command=lambda email=row["email"], label=row["label"]: self._edit_label(email, label),
            )
        if key == "state":
            var = ctk.StringVar(value=row["state"])
            menu = ctk.CTkOptionMenu(
                self.local_table, values=list(backend.ADDRESS_STATES), variable=var,
                width=100, height=26, fg_color=theme.BG_CARD_ALT, button_color=theme.BG_CARD_ALT,
                button_hover_color=theme.SIDEBAR_HOVER,
                command=lambda choice, email=row["email"]: self._set_state(email, choice),
            )
            return menu
        if key == "created_at":
            return ctk.CTkLabel(
                self.local_table, text=_format_ts(row["created_at"]), anchor="w",
                text_color=theme.TEXT_PRIMARY, font=(theme.FONT_FAMILY, 12),
            )
        if key == "copy":
            return SecondaryButton(
                self.local_table, text="Copy", width=60, height=26,
                font=(theme.FONT_FAMILY, 11),
                command=lambda email=row["email"]: self._copy(email),
            )
        return None

    # ---- selection / bulk actions --------------------------------------
    def _selected_emails(self):
        return [email for email, var in self._checkbox_vars.items() if var.get()]

    def _update_bulk_bar(self):
        selected = self._selected_emails()
        if selected:
            self.bulk_count_label.configure(text=f"{len(selected)} selected")
            if not self.bulk_bar.winfo_ismapped():
                self.bulk_bar.pack(in_=self.bulk_bar_slot, fill="x", pady=(0, 10))
        else:
            self.bulk_bar.pack_forget()

    def _on_select_all_toggle(self):
        value = self.select_all_var.get()
        for var in self._checkbox_vars.values():
            var.set(value)
        self._update_bulk_bar()

    def _clear_selection(self):
        for var in self._checkbox_vars.values():
            var.set(False)
        self.select_all_var.set(False)
        self._update_bulk_bar()

    def _edit_label(self, email, current_label):
        def on_submit(value):
            conn = backend.connect_db(self.app.app_state.db_file)
            try:
                backend.set_label(conn, email, value)
            finally:
                conn.close()
            self._refresh_local()

        PromptDialog(
            self, title="Edit label", message=f"Label for {email}:",
            initial=current_label or "", on_submit=on_submit,
        )

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

        PromptDialog(
            self, title="Edit label", message=f"Set label for {len(selected)} address(es):",
            initial="", on_submit=on_submit,
        )

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
        self.clipboard_clear()
        self.clipboard_append("\n".join(selected))
        self.local_status.configure(
            text=f"Copied {len(selected)} address(es) to clipboard.", text_color=theme.SUCCESS
        )

    def _bulk_delete(self):
        selected = self._selected_emails()
        if not selected:
            return
        if not messagebox.askyesno(
            "Delete addresses",
            f"Permanently delete {len(selected)} address(es) from the local database?\n\n"
            "This only removes them from this app's local list — it does not deactivate "
            "them on iCloud.",
            parent=self,
        ):
            return
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            backend.delete_addresses(conn, selected)
        finally:
            conn.close()
        for email in selected:
            self._checkbox_vars.pop(email, None)
        self._refresh_local()

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
        if key == "created_at":
            return ctk.CTkLabel(
                self.icloud_table, text=_format_ts(row.get("created_at")), anchor="w",
                text_color=theme.TEXT_PRIMARY, font=(theme.FONT_FAMILY, 12),
            )
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
