"""Addresses tab: local unused/used/trash state plus the live iCloud list."""

import os
import tkinter as tk
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

# CustomTkinter's per-row widgets (CTkOptionMenu/CTkCheckBox) and
# CTkScrollableFrame get dramatically slower to build/destroy as row count
# grows — a real 247-row rebuild measured ~63s. Pagination keeps the
# rendered widget count bounded regardless of how many addresses exist.
PAGE_SIZE = 25


class AddressesView(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self._icloud_cache = []
        self._search_after_id = None
        self._state_filter = (
            app.app_state.addresses_filter if app.app_state.addresses_filter in STATE_FILTERS else "All"
        )
        self._page = 0
        self._selected = set()  # emails selected, independent of pagination
        self._last_filtered_emails = []  # all emails matching the current filter/search (not just this page)
        self._select_labels = {}  # email -> the rendered "select" cell label, current page only
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

        pagination_row = ctk.CTkFrame(parent, fg_color="transparent")
        pagination_row.pack(fill="x", padx=4, pady=(4, 0))
        self.prev_page_btn = SecondaryButton(
            pagination_row, text="◀ Prev", width=80, height=26, command=self._prev_page,
        )
        self.prev_page_btn.pack(side="left")
        self.page_label = ctk.CTkLabel(pagination_row, text="", text_color=theme.TEXT_SECONDARY)
        self.page_label.pack(side="left", padx=12)
        self.next_page_btn = SecondaryButton(
            pagination_row, text="Next ▶", width=80, height=26, command=self._next_page,
        )
        self.next_page_btn.pack(side="left")

        self.local_status = ctk.CTkLabel(parent, text="", text_color=theme.TEXT_SECONDARY)
        self.local_status.pack(anchor="w", padx=4, pady=(4, 0))

    def _schedule_refresh_local(self):
        self._page = 0
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(200, self._refresh_local)

    def _set_state_filter(self, key):
        self._state_filter = key
        self._page = 0
        self.app.app_state.addresses_filter = key
        self.app.app_state.save()
        self._refresh_local()

    def _on_sort_changed(self):
        sort_key = SORT_LABEL_TO_KEY.get(self.sort_var.get(), backend.SORT_CREATED_DESC)
        self._page = 0
        self.app.app_state.addresses_sort = sort_key
        self.app.app_state.save()
        self._refresh_local()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._refresh_local()

    def _next_page(self):
        self._page += 1
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
            items = backend.list_addresses_full(conn, state=state, sort=sort_key, limit=5000)
        finally:
            conn.close()

        query = self.search_var.get().strip().lower()
        if query:
            items = [
                r for r in items
                if query in (r["email"] or "").lower() or query in (r["label"] or "").lower()
            ]

        total = len(items)
        page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._page = max(0, min(self._page, page_count - 1))
        start = self._page * PAGE_SIZE
        page_items = items[start:start + PAGE_SIZE]

        self._last_filtered_emails = [i["email"] for i in items]
        full_emails = set(self._last_filtered_emails)
        self._selected &= full_emails  # drop selections no longer matching the filter

        page_emails = {i["email"] for i in page_items}
        self._select_labels = {e: v for e, v in self._select_labels.items() if e in page_emails}

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
            page_items, cell_builder=self._local_cell,
            empty_text="No local addresses yet — generate or sync some.",
        )
        self.select_all_var.set(bool(full_emails) and full_emails.issubset(self._selected))
        self.prev_page_btn.configure(state="normal" if self._page > 0 else "disabled")
        self.next_page_btn.configure(state="normal" if self._page < page_count - 1 else "disabled")
        if total:
            self.page_label.configure(
                text=f"Page {self._page + 1} of {page_count}  ·  "
                     f"{start + 1}–{min(start + PAGE_SIZE, total)} of {total}"
            )
        else:
            self.page_label.configure(text="")
        self.local_status.configure(text=f"{total} address(es)")
        self._update_bulk_bar()

    def _local_cell(self, row_index, col_index, key, row):
        if key == "select":
            # A plain clickable label instead of CTkCheckBox — measured 3-5x
            # cheaper to build/destroy per row, which matters a lot once
            # you're rendering dozens of these per page (see PAGE_SIZE note).
            email = row["email"]
            checked = email in self._selected
            lbl = ctk.CTkLabel(
                self.local_table, text="✓" if checked else "", width=20, height=20,
                cursor="hand2", corner_radius=4, text_color="#ffffff",
                fg_color=theme.ACCENT if checked else theme.BG_INPUT,
            )
            lbl.bind("<Button-1>", lambda _e, email=email, lbl=lbl: self._toggle_row_selection(email, lbl))
            self._select_labels[email] = lbl
            return lbl
        if key == "label":
            return SecondaryButton(
                self.local_table, text=row["label"] or "(no label)", anchor="w",
                fg_color="transparent", border_width=0, hover_color=theme.SIDEBAR_HOVER,
                font=(theme.FONT_FAMILY, 12), height=26,
                command=lambda email=row["email"], label=row["label"]: self._edit_label(email, label),
            )
        if key == "state":
            # Same reasoning as "select" above — a clickable label with a
            # native tk.Menu popup instead of a persistent CTkOptionMenu.
            email = row["email"]
            lbl = ctk.CTkLabel(
                self.local_table, text=row["state"], cursor="hand2", width=90, height=26,
                corner_radius=6, fg_color=theme.BG_CARD_ALT, text_color=theme.TEXT_PRIMARY,
            )
            lbl.bind("<Button-1>", lambda e, email=email: self._open_state_menu(e, email))
            return lbl
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
    # Selection (self._selected) is decoupled from which checkboxes are
    # currently rendered, since only one page of rows exists as widgets at
    # a time — bulk actions can span the whole filtered set, not just the
    # visible page.
    def _selected_emails(self):
        return list(self._selected)

    def _update_bulk_bar(self):
        selected = self._selected_emails()
        if selected:
            self.bulk_count_label.configure(text=f"{len(selected)} selected")
            if not self.bulk_bar.winfo_ismapped():
                self.bulk_bar.pack(in_=self.bulk_bar_slot, fill="x", pady=(0, 10))
        else:
            self.bulk_bar.pack_forget()

    def _set_select_label(self, lbl, checked):
        lbl.configure(
            text="✓" if checked else "",
            fg_color=theme.ACCENT if checked else theme.BG_INPUT,
        )

    def _toggle_row_selection(self, email, lbl):
        if email in self._selected:
            self._selected.discard(email)
        else:
            self._selected.add(email)
        self._set_select_label(lbl, email in self._selected)
        self._update_bulk_bar()

    def _on_select_all_toggle(self):
        if self.select_all_var.get():
            self._selected = set(self._last_filtered_emails)
        else:
            self._selected = set()
        for email, lbl in self._select_labels.items():
            self._set_select_label(lbl, email in self._selected)
        self._update_bulk_bar()

    def _clear_selection(self):
        self._selected = set()
        for lbl in self._select_labels.values():
            self._set_select_label(lbl, False)
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
        self._selected.clear()
        self._refresh_local()

    def _open_state_menu(self, event, email):
        menu = tk.Menu(self, tearoff=0)
        for state in backend.ADDRESS_STATES:
            menu.add_command(label=state, command=lambda s=state, email=email: self._set_state(email, s))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

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
