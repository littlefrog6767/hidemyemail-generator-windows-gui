"""Inbox tab: connect a receiving mailbox via IMAP and pull verification
codes from forwarded Hide My Email messages. Everything here — the mailbox
credentials and the synced messages — stays in the local sqlite db and a
local inbox_config.json, same as the upstream CLI."""

import os

import customtkinter as ctk

from gui import backend, theme
from gui.widgets import Card, PrimaryButton, SecondaryButton, SimpleTable

MESSAGE_COLUMNS = [
    ("received_at", "Received", 2),
    ("hme_address", "Hide My Email", 3),
    ("sender", "From", 2),
    ("subject", "Subject", 3),
    ("code", "Code", 1),
    ("copy", "", 1),
]


class InboxView(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self._build()
        self._load_config_into_form()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(28, 10))
        ctk.CTkLabel(
            header, text="Inbox", font=(theme.FONT_FAMILY, 22, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Connect a receiving mailbox and extract verification codes locally.",
            text_color=theme.TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        config_card = Card(self)
        config_card.pack(fill="x", padx=28, pady=10)
        inner = ctk.CTkFrame(config_card, fg_color="transparent")
        inner.pack(fill="x", padx=22, pady=20)
        inner.grid_columnconfigure(1, weight=1)
        inner.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            inner, text="CONNECT A RECEIVING MAILBOX", text_color=theme.TEXT_SECONDARY,
            font=(theme.FONT_FAMILY, 11, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        def entry(row, col, label_text, show=None, default=""):
            ctk.CTkLabel(inner, text=label_text, text_color=theme.TEXT_SECONDARY).grid(
                row=row, column=col, sticky="w", pady=6, padx=(0 if col == 0 else 18, 0)
            )
            var = ctk.StringVar(value=default)
            e = ctk.CTkEntry(
                inner, textvariable=var, fg_color=theme.BG_INPUT, border_color=theme.BORDER,
                show=show,
            )
            e.grid(row=row + 1, column=col, sticky="ew", padx=(0 if col == 0 else 18, 0))
            return var

        self.host_var = entry(1, 0, "IMAP host")
        self.port_var = entry(1, 1, "Port")
        self.port_var.set("993")
        self.user_var = entry(3, 0, "Username")
        self.pass_var = entry(3, 1, "Password (app password recommended)", show="•")
        self.folder_var = entry(5, 0, "Folder")
        self.folder_var.set("INBOX")

        self.ssl_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            inner, text="Use SSL", variable=self.ssl_var, text_color=theme.TEXT_SECONDARY,
        ).grid(row=6, column=1, sticky="w", pady=(10, 0), padx=(18, 0))

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.grid(row=7, column=0, columnspan=4, sticky="w", pady=(16, 0))
        PrimaryButton(btn_row, text="Save Settings", command=self._save_config).pack(side="left")
        SecondaryButton(btn_row, text="Sync Now", command=self._sync).pack(side="left", padx=(10, 0))

        self.config_status = ctk.CTkLabel(inner, text="", text_color=theme.TEXT_SECONDARY)
        self.config_status.grid(row=8, column=0, columnspan=4, sticky="w", pady=(10, 0))

        # Messages
        messages_card = Card(self)
        messages_card.pack(fill="both", expand=True, padx=28, pady=(0, 28))
        toolbar = ctk.CTkFrame(messages_card, fg_color="transparent")
        toolbar.pack(fill="x", padx=18, pady=(14, 8))
        ctk.CTkLabel(
            toolbar, text="MESSAGES", text_color=theme.TEXT_SECONDARY,
            font=(theme.FONT_FAMILY, 11, "bold"),
        ).pack(side="left")
        self.only_codes_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            toolbar, text="Only show codes", variable=self.only_codes_var,
            text_color=theme.TEXT_SECONDARY, command=self._refresh_messages,
        ).pack(side="left", padx=(16, 0))
        SecondaryButton(toolbar, text="Export CSV", command=self._export_csv).pack(side="right")

        self.messages_table = SimpleTable(messages_card, MESSAGE_COLUMNS)
        self.messages_table.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def _load_config_into_form(self):
        try:
            config = backend.load_inbox_config(self.app.app_state.inbox_config_file)
        except FileNotFoundError:
            return
        self.host_var.set(config.host)
        self.port_var.set(str(config.port))
        self.user_var.set(config.username)
        self.pass_var.set(config.password)
        self.folder_var.set(config.folder)
        self.ssl_var.set(config.use_ssl)

    def _build_config(self):
        try:
            port = int(self.port_var.get())
        except ValueError:
            port = 993
        return backend.InboxConfig(
            host=self.host_var.get().strip(),
            port=port,
            username=self.user_var.get().strip(),
            password=self.pass_var.get(),
            folder=self.folder_var.get().strip() or "INBOX",
            use_ssl=self.ssl_var.get(),
        )

    def _save_config(self):
        config = self._build_config()
        if not config.host or not config.username:
            self.config_status.configure(text="Host and username are required.", text_color=theme.DANGER)
            return
        backend.save_inbox_config(config, self.app.app_state.inbox_config_file)
        self.config_status.configure(
            text=f"Saved. Mailbox: {backend.mask_account(config.username)}", text_color=theme.SUCCESS
        )

    def _sync(self):
        config = self._build_config()
        if not config.host or not config.username:
            self.config_status.configure(text="Host and username are required.", text_color=theme.DANGER)
            return
        backend.save_inbox_config(config, self.app.app_state.inbox_config_file)
        self.config_status.configure(text="Syncing…", text_color=theme.TEXT_SECONDARY)
        self.app.worker.run_sync(
            backend.sync_inbox, config, self.app.app_state.db_file, 50, on_done=self._on_sync_done
        )

    def _on_sync_done(self, inserted, error):
        if error is not None:
            self.config_status.configure(text=f"Sync failed: {error}", text_color=theme.DANGER)
            return
        self.config_status.configure(
            text=f"Synced — {len(inserted)} new message(s).", text_color=theme.SUCCESS
        )
        self._refresh_messages()
        self.app.on_addresses_changed()

    def _refresh_messages(self):
        conn = backend.connect_db(self.app.app_state.db_file)
        try:
            rows = backend.list_messages(conn, only_codes=self.only_codes_var.get(), limit=200)
        finally:
            conn.close()
        items = [dict(row) for row in rows]
        self.messages_table.set_rows(
            items, cell_builder=self._message_cell,
            empty_text="No messages synced yet.",
        )

    def _message_cell(self, row_index, col_index, key, row):
        if key == "copy":
            code = row.get("code") or ""
            if not code:
                return None
            return SecondaryButton(
                self.messages_table, text="Copy code", width=80, height=26,
                font=(theme.FONT_FAMILY, 11), command=lambda c=code: self._copy(c),
            )
        return None

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)

    def _export_csv(self):
        try:
            outputs = backend.export_csv_files(self.app.app_state.db_file, self.app.app_state.export_dir)
        except OSError as exc:
            self.config_status.configure(text=f"Export failed: {exc}", text_color=theme.DANGER)
            return
        self.config_status.configure(
            text=f"Exported to {outputs['messages'].parent}", text_color=theme.SUCCESS
        )
        try:
            os.startfile(outputs["messages"].parent)  # noqa: S606 - opening our own export dir
        except OSError:
            pass

    def refresh(self):
        self._refresh_messages()
