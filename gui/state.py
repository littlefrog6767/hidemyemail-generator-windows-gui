"""Local app state and config paths. Everything lives under data/, next to
this project's own folder, mirroring how the upstream CLI keeps cookies.txt
and its sqlite db next to itself."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

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

    def save(self):
        GUI_CONFIG_FILE.write_text(
            json.dumps(
                {"region": self.region, "account": self.account},
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
