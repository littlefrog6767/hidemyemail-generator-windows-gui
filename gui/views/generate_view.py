"""Generate tab: create one address or a small batch with a custom label."""

import tkinter as tk

import customtkinter as ctk

from gui import backend, theme
from gui.widgets import Card, PrimaryButton


class GenerateView(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(28, 10))
        ctk.CTkLabel(
            header,
            text="Generate addresses",
            font=(theme.FONT_FAMILY, 22, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Create Hide My Email addresses immediately.",
            text_color=theme.TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        card = Card(self)
        card.pack(fill="x", padx=28, pady=10)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=22, pady=22)

        ctk.CTkLabel(
            inner,
            text="EMAIL DETAILS",
            text_color=theme.TEXT_SECONDARY,
            font=(theme.FONT_FAMILY, 11, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ctk.CTkLabel(inner, text="Label", text_color=theme.TEXT_SECONDARY).grid(
            row=1, column=0, sticky="w", pady=6
        )
        self.label_entry = ctk.CTkEntry(
            inner, fg_color=theme.BG_INPUT, border_color=theme.BORDER, width=280
        )
        self.label_entry.insert(0, "generated")
        self.label_entry.grid(row=1, column=1, sticky="w", pady=6, padx=(14, 0))

        ctk.CTkLabel(inner, text="Quantity", text_color=theme.TEXT_SECONDARY).grid(
            row=2, column=0, sticky="w", pady=6
        )
        qty_row = ctk.CTkFrame(inner, fg_color="transparent")
        qty_row.grid(row=2, column=1, sticky="w", pady=6, padx=(14, 0))
        self.qty_var = tk.StringVar(value="1")
        ctk.CTkEntry(
            qty_row, fg_color=theme.BG_INPUT, border_color=theme.BORDER, width=80,
            textvariable=self.qty_var,
        ).pack(side="left")
        ctk.CTkLabel(qty_row, text="email(s) — max 50 at a time", text_color=theme.TEXT_SECONDARY).pack(
            side="left", padx=(8, 0)
        )

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(8, 16))
        self.generate_btn = PrimaryButton(
            btn_row, text="Generate Email", width=180, command=self._on_generate
        )
        self.generate_btn.pack()

        self.status_label = ctk.CTkLabel(self, text="", text_color=theme.TEXT_SECONDARY)
        self.status_label.pack(pady=(0, 8))

        results_card = Card(self)
        results_card.pack(fill="both", expand=True, padx=28, pady=(0, 28))
        row = ctk.CTkFrame(results_card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkLabel(
            row, text="JUST GENERATED", text_color=theme.TEXT_SECONDARY,
            font=(theme.FONT_FAMILY, 11, "bold"),
        ).pack(side="left")
        ctk.CTkButton(
            row, text="Copy all", width=80, height=24, fg_color=theme.BG_CARD_ALT,
            hover_color=theme.SIDEBAR_HOVER, text_color=theme.TEXT_PRIMARY,
            font=(theme.FONT_FAMILY, 11), command=self._copy_all,
        ).pack(side="right")

        self.results_box = ctk.CTkTextbox(
            results_card, fg_color=theme.BG_INPUT, border_width=1, border_color=theme.BORDER,
            corner_radius=8,
        )
        self.results_box.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.results_box.configure(state="disabled")

    def _copy_all(self):
        self.clipboard_clear()
        self.clipboard_append(self.results_box.get("1.0", "end").strip())

    def _on_generate(self):
        if not self.app.app_state.is_signed_in:
            self.status_label.configure(
                text="Sign in first — use the account button in the top-right.",
                text_color=theme.DANGER,
            )
            return

        label = self.label_entry.get().strip() or "generated"
        try:
            count = int(self.qty_var.get())
        except ValueError:
            count = 1
        count = max(1, min(50, count))
        self.qty_var.set(str(count))

        self.generate_btn.configure(state="disabled", text="Generating…")
        self.status_label.configure(
            text=f"Generating {count} email(s)…", text_color=theme.TEXT_SECONDARY
        )
        self.app.worker.run_coro(
            backend.generate_emails(self.app.app_state.cookie_file, self.app.app_state.region, label, count),
            on_done=self._on_done,
        )

    def _on_done(self, result, error):
        self.generate_btn.configure(state="normal", text="Generate Email")
        if error is not None:
            self.status_label.configure(text=f"Error: {error}", text_color=theme.DANGER)
            return

        emails = result["emails"]
        if emails:
            self.results_box.configure(state="normal")
            self.results_box.insert("end", "\n".join(emails) + "\n")
            self.results_box.see("end")
            self.results_box.configure(state="disabled")

        if result["ok"]:
            self.status_label.configure(
                text=f"Generated {len(emails)} email(s).", text_color=theme.SUCCESS
            )
        else:
            msg = (result["error"] or {}).get("message", "Some addresses failed to generate.")
            self.status_label.configure(
                text=f"Generated {len(emails)} of the requested amount — {msg}",
                text_color=theme.WARNING,
            )
        self.app.on_addresses_changed()
