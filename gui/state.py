"""Local app state and config paths. Everything lives under data/.

When running from source, that's next to this project's own folder,
mirroring how the upstream CLI keeps cookies.txt and its sqlite db next to
itself. When frozen by PyInstaller, __file__ resolves inside the temporary
extraction directory (onefile) or the install directory (onedir) — neither
of which is a safe place for persistent per-user data — so we use the
per-user AppData folder instead.
"""

import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    DATA_DIR = Path.home() / "AppData" / "Local" / "HideMyEmailGenerator" / "data"
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

COOKIE_FILE = DATA_DIR / "cookies.txt"
DB_FILE = DATA_DIR / "hidemyemail.db"
INBOX_CONFIG_FILE = DATA_DIR / "inbox_config.json"
GUI_CONFIG_FILE = DATA_DIR / "gui_config.json"
EXPORT_DIR = DATA_DIR / "exports"

REGIONS = ("global", "china")


class AppState:
    def __init__(self):
        self.region = "global"
        self.account = None  # dict from account_summary(), or None if signed out
        self.addresses_sort = "created_desc"
        self.addresses_filter = "All"
        self.window_geometry = None  # e.g. "1360x900+120+80"; None = use the default
        self._load()

    def _load(self):
        if not GUI_CONFIG_FILE.exists():
            return
        try:
            data = json.loads(GUI_CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.region = data.get("region", "global")
        self.account = data.get("account")
        self.addresses_sort = data.get("addresses_sort", "created_desc")
        self.addresses_filter = data.get("addresses_filter", "All")
        self.window_geometry = data.get("window_geometry")

    def save(self):
        GUI_CONFIG_FILE.write_text(
            json.dumps(
                {
                    "region": self.region,
                    "account": self.account,
                    "addresses_sort": self.addresses_sort,
                    "addresses_filter": self.addresses_filter,
                    "window_geometry": self.window_geometry,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def sign_out(self):
        self.account = None
        self.save()
        if COOKIE_FILE.exists():
            COOKIE_FILE.unlink()

    @property
    def is_signed_in(self) -> bool:
        return COOKIE_FILE.exists() and self.account is not None

    @property
    def cookie_file(self) -> str:
        return str(COOKIE_FILE)

    @property
    def db_file(self) -> str:
        return str(DB_FILE)

    @property
    def inbox_config_file(self) -> str:
        return str(INBOX_CONFIG_FILE)

    @property
    def export_dir(self) -> str:
        return str(EXPORT_DIR)
