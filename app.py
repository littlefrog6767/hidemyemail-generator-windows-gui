"""HideMyEmail Generator — unofficial Windows GUI.

A PySide6 (Qt) front-end over the project's existing Python CLI backend
(vendored under vendor/hidemyemail_generator), mirroring the macOS app's
Generate / Addresses / Inbox / Scheduler layout.
"""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from gui import theme
from gui.async_worker import AsyncWorker
from gui.qss import STYLESHEET
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


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.app_state = AppState()
        self.worker = AsyncWorker(self)

        self.setWindowTitle("HideMyEmail Generator")
        self.setMinimumSize(1000, 680)
        self._restore_geometry()
        icon_path = ASSETS_DIR / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._nav_buttons = {}
        self._active_key = None

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_content(), stretch=1)

        self._show("generate")
        self._refresh_account_pill()

    # ---- sidebar ---------------------------------------------------
    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 20, 18, 18)
        layout.setSpacing(3)

        title = QLabel("HideMyEmail")
        title.setObjectName("SidebarTitle")
        layout.addWidget(title)
        subtitle = QLabel("Generator")
        subtitle.setObjectName("SidebarSubtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(15)

        for key, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setProperty("variant", "nav")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.clicked.connect(lambda _checked=False, k=key: self._show(k))
            layout.addWidget(btn)
            self._nav_buttons[key] = btn

        layout.addStretch()

        footer = QLabel("●  No telemetry collected")
        footer.setObjectName("FooterLabel")
        layout.addWidget(footer)
        return sidebar

    def _select_nav(self, active_key):
        for key, btn in self._nav_buttons.items():
            btn.setProperty("active", "true" if key == active_key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ---- content -----------------------------------------------------
    def _build_content(self):
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(20, 14, 20, 20)
        outer_layout.setSpacing(10)

        topbar = QHBoxLayout()
        topbar.addStretch()
        self.account_btn = QPushButton("Sign in")
        self.account_btn.setProperty("variant", "secondary")
        self.account_btn.setCursor(Qt.PointingHandCursor)
        self.account_btn.clicked.connect(self._on_account_button)
        topbar.addWidget(self.account_btn)
        outer_layout.addLayout(topbar)

        self.stack = QStackedWidget()
        outer_layout.addWidget(self.stack, stretch=1)

        self.views = {
            "generate": GenerateView(self),
            "addresses": AddressesView(self),
            "inbox": InboxView(self),
            "scheduler": SchedulerView(self),
        }
        for view in self.views.values():
            self.stack.addWidget(view)

        # Each view's table used to need manual pagination + a heavy set of
        # workarounds under CustomTkinter (destroy/rebuild real widgets per
        # row, resize freezing the whole app). Qt's model/view tables only
        # ever render the rows actually on screen, so none of that carries
        # over here. Still keep a lazy-refresh dirty flag purely to avoid
        # redundant DB round-trips when nothing changed.
        self._dirty = {"addresses": True, "inbox": True}
        return outer

    def _show(self, key):
        self._active_key = key
        self.stack.setCurrentWidget(self.views[key])
        self._select_nav(key)
        if key in self._dirty and self._dirty[key]:
            self.views[key].refresh()
            self._dirty[key] = False

    # ---- window geometry -------------------------------------------------
    def _restore_geometry(self):
        geo = self.app_state.window_geometry
        if geo and isinstance(geo, list) and len(geo) == 4:
            try:
                x, y, w, h = geo
                self.setGeometry(int(x), int(y), int(w), int(h))
                return
            except (TypeError, ValueError):
                pass
        self.resize(1360, 900)

    def closeEvent(self, event):
        rect = self.geometry()
        self.app_state.window_geometry = [rect.x(), rect.y(), rect.width(), rect.height()]
        self.app_state.save()
        self.worker.shutdown()
        super().closeEvent(event)

    # ---- account / sign-in --------------------------------------------
    def _on_account_button(self):
        if self.app_state.is_signed_in:
            self._sign_out()
        else:
            self.open_signin_dialog()

    def open_signin_dialog(self):
        dlg = SignInDialog(self, self)
        dlg.exec()

    def on_signed_in(self, account):
        self._refresh_account_pill()
        self.on_addresses_changed()

    def _sign_out(self):
        self.app_state.sign_out()
        self._refresh_account_pill()

    def _refresh_account_pill(self):
        if self.app_state.is_signed_in and self.app_state.account:
            apple_id = self.app_state.account.get("apple_id", "Signed in")
            self.account_btn.setText(f"☁  {apple_id}  (sign out)")
        else:
            self.account_btn.setText("☁  Sign in")

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


def main():
    os.makedirs(Path(__file__).resolve().parent / "data", exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
