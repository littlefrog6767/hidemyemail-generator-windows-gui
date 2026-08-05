"""HideMyEmail Generator — unofficial Windows GUI.

A CustomTkinter front-end over the project's existing Python CLI backend
(vendored under vendor/hidemyemail_generator), mirroring the macOS app's
Generate / Addresses / Inbox / Scheduler layout.
"""

import os
from pathlib import Path

import customtkinter as ctk

from gui import theme
from gui.async_worker import AsyncWorker
from gui.state import AppState
from gui.views.addresses_view import AddressesView
from gui.views.generate_view import GenerateView
from gui.views.inbox_view import InboxView
from gui.views.scheduler_view import SchedulerView
from gui.views.signin_dialog import SignInDialog

ASSETS_DIR = Path(__file__).resolve().parent / "gui" / "assets"

NAV_ITEMS = [
    ("generate", "＋  Generate"),
    ("addresses", "✉  Addresses"),
    ("inbox", "📥  Inbox"),
    ("scheduler", "⏱  Scheduler"),
]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.app_state = AppState()
        self.worker = AsyncWorker(self)

        self.title("HideMyEmail Generator")
        self.geometry("1360x900")
        self.minsize(1000, 680)
        self.configure(fg_color=theme.BG_MAIN)
        icon_path = ASSETS_DIR / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._nav_buttons = {}
        self._active_key = None
        self._build_sidebar()
        self._build_content()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._show("generate")
        self._refresh_account_pill()

    # ---- sidebar ---------------------------------------------------
    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, fg_color=theme.BG_SIDEBAR, corner_radius=0, width=220)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        title_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        title_row.pack(fill="x", padx=18, pady=(20, 18))
        ctk.CTkLabel(
            title_row, text="HideMyEmail", font=(theme.FONT_FAMILY, 15, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_row, text="Generator", font=(theme.FONT_FAMILY, 12), text_color=theme.TEXT_SECONDARY,
        ).pack(anchor="w")

        for key, label in NAV_ITEMS:
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w", corner_radius=8, height=38,
                fg_color="transparent", hover_color=theme.SIDEBAR_HOVER,
                text_color=theme.TEXT_PRIMARY, font=(theme.FONT_FAMILY, 13),
                command=lambda k=key: self._show(k),
            )
            btn.pack(fill="x", padx=12, pady=3)
            self._nav_buttons[key] = btn

        spacer = ctk.CTkFrame(sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(fill="x", padx=18, pady=(0, 18))
        ctk.CTkLabel(
            bottom, text="●  No telemetry collected", text_color=theme.TEXT_MUTED,
            font=(theme.FONT_FAMILY, 10),
        ).pack(anchor="w")

    def _select_nav(self, active_key):
        for key, btn in self._nav_buttons.items():
            btn.configure(fg_color=theme.SIDEBAR_SELECTED if key == active_key else "transparent")

    # ---- content -----------------------------------------------------
    def _build_content(self):
        outer = ctk.CTkFrame(self, fg_color=theme.BG_MAIN, corner_radius=0)
        outer.grid(row=0, column=1, sticky="nsew")
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        topbar = ctk.CTkFrame(outer, fg_color="transparent", height=48)
        topbar.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 0))
        self.account_btn = ctk.CTkButton(
            topbar, text="Sign in", width=180, height=32, corner_radius=16,
            fg_color=theme.BG_CARD_ALT, hover_color=theme.SIDEBAR_HOVER,
            text_color=theme.TEXT_PRIMARY, font=(theme.FONT_FAMILY, 12),
            command=self._on_account_button,
        )
        self.account_btn.pack(side="right")

        container = ctk.CTkFrame(outer, fg_color="transparent")
        container.grid(row=1, column=0, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.views = {
            "generate": GenerateView(container, self),
            "addresses": AddressesView(container, self),
            "inbox": InboxView(container, self),
            "scheduler": SchedulerView(container, self),
        }
        for view in self.views.values():
            view.grid(row=0, column=0, sticky="nsew")

        # Both tabs' tables are rebuilt from scratch on refresh(), which is
        # expensive (hundreds of widgets). Only do that when their data
        # actually changed (tracked via on_addresses_changed / initial load),
        # not on every nav click.
        self._dirty = {"addresses": True, "inbox": True}

    def _show(self, key):
        self._active_key = key
        self.views[key].tkraise()
        self._select_nav(key)
        if key in self._dirty and self._dirty[key]:
            self.views[key].refresh()
            self._dirty[key] = False

    # ---- account / sign-in --------------------------------------------
    def _on_account_button(self):
        if self.app_state.is_signed_in:
            self._sign_out()
        else:
            self.open_signin_dialog()

    def open_signin_dialog(self):
        SignInDialog(self, self)

    def on_signed_in(self, account):
        self._refresh_account_pill()
        self.on_addresses_changed()

    def _sign_out(self):
        self.app_state.sign_out()
        self._refresh_account_pill()

    def _refresh_account_pill(self):
        if self.app_state.is_signed_in and self.app_state.account:
            apple_id = self.app_state.account.get("apple_id", "Signed in")
            self.account_btn.configure(text=f"☁  {apple_id}  (sign out)")
        else:
            self.account_btn.configure(text="☁  Sign in")

    # ---- cross-view refresh --------------------------------------------
    def on_addresses_changed(self):
        # Inbox syncing also upserts addresses, so both tables are affected.
        # Refresh immediately only whichever tab is currently visible; the
        # other is marked dirty and refreshed lazily next time it's shown.
        for key in ("addresses", "inbox"):
            if key == self._active_key:
                self.views[key].refresh()
                self._dirty[key] = False
            else:
                self._dirty[key] = True

    def _on_close(self):
        self.worker.shutdown()
        self.destroy()


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    os.makedirs(Path(__file__).resolve().parent / "data", exist_ok=True)
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
