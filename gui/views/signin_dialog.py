"""Paste-cookie sign-in flow: the user copies their authenticated iCloud
request (raw Cookie header, or a browser 'Copy as cURL'), pastes it here, and
we validate it against iCloud before saving it locally."""

import customtkinter as ctk

from gui import backend, theme
from gui.widgets import PrimaryButton, SecondaryButton


class SignInDialog(ctk.CTkToplevel):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("Sign in to iCloud")
        self.geometry("580x600")
        self.configure(fg_color=theme.BG_MAIN)
        self.resizable(False, False)
        self.transient(master)
        self._build()
        self.after(50, self.grab_set)

    def _build(self):
        pad = {"padx": 24}
        ctk.CTkLabel(
            self,
            text="Connect your iCloud account",
            font=(theme.FONT_FAMILY, 18, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(22, 6), **pad)

        ctk.CTkLabel(
            self,
            text=(
                "1. Sign in at icloud.com/settings (icloud.com.cn for China) in your browser.\n"
                "2. Open DevTools (F12) → Network tab, then refresh the page.\n"
                "3. Filter requests for \"hme\" or \"maildomainws\".\n"
                "4. Right-click a matching request → Copy → Copy as cURL.\n"
                "5. Paste the whole copied text below. A raw Cookie header also works.\n\n"
                "Avoid feedbackws/reportStats requests — they're usually missing the\n"
                "X-APPLE-WEBAUTH-USER cookie this needs."
            ),
            justify="left",
            anchor="w",
            text_color=theme.TEXT_SECONDARY,
            font=(theme.FONT_FAMILY, 12),
        ).pack(anchor="w", pady=(0, 14), **pad)

        region_row = ctk.CTkFrame(self, fg_color="transparent")
        region_row.pack(anchor="w", fill="x", pady=(0, 12), **pad)
        ctk.CTkLabel(region_row, text="Region", text_color=theme.TEXT_SECONDARY).pack(
            side="left", padx=(0, 10)
        )
        self.region_var = ctk.StringVar(value=self.app.app_state.region)
        ctk.CTkSegmentedButton(
            region_row,
            values=["global", "china"],
            variable=self.region_var,
            fg_color=theme.BG_INPUT,
            selected_color=theme.ACCENT,
            selected_hover_color=theme.ACCENT_HOVER,
            unselected_color=theme.BG_INPUT,
        ).pack(side="left")

        self.text_box = ctk.CTkTextbox(
            self,
            height=200,
            fg_color=theme.BG_INPUT,
            border_width=1,
            border_color=theme.BORDER,
            corner_radius=8,
        )
        self.text_box.pack(fill="both", expand=True, pady=(0, 12), **pad)

        self.status_label = ctk.CTkLabel(
            self,
            text="",
            text_color=theme.TEXT_SECONDARY,
            wraplength=520,
            justify="left",
            anchor="w",
        )
        self.status_label.pack(anchor="w", fill="x", pady=(0, 10), **pad)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 22), **pad)
        self.validate_btn = PrimaryButton(
            btn_row, text="Validate & Sign In", command=self._validate
        )
        self.validate_btn.pack(side="left")
        SecondaryButton(btn_row, text="Cancel", command=self.destroy).pack(
            side="left", padx=(10, 0)
        )

    def _validate(self):
        text = self.text_box.get("1.0", "end").strip()
        if not text:
            self.status_label.configure(
                text="Paste your cookie / cURL text first.", text_color=theme.DANGER
            )
            return
        region = self.region_var.get()
        self.validate_btn.configure(state="disabled", text="Validating…")
        self.status_label.configure(text="Contacting iCloud…", text_color=theme.TEXT_SECONDARY)
        self.app.worker.run_coro(
            backend.validate_and_fetch_account(text, region),
            on_done=lambda v, e: self._on_result(v, e, text, region),
        )

    def _on_result(self, result, error, raw_text, region):
        if not self.winfo_exists():
            return
        self.validate_btn.configure(state="normal", text="Validate & Sign In")
        if error is not None:
            self.status_label.configure(text=f"Error: {error}", text_color=theme.DANGER)
            return
        if not result["ok"]:
            self.status_label.configure(text=result["error"], text_color=theme.DANGER)
            return

        backend.save_cookie_text(self.app.app_state.cookie_file, raw_text)
        self.app.app_state.region = region
        self.app.app_state.account = result["account"]
        self.app.app_state.save()
        self.status_label.configure(
            text=f"Signed in as {result['account']['apple_id']}.", text_color=theme.SUCCESS
        )
        self.app.on_signed_in(result["account"])
        self.after(700, self.destroy)
