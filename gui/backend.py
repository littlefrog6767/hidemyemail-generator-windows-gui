"""Thin wrappers around the vendored hidemyemail_generator package.

We reuse the upstream CLI's classes/functions directly instead of
reimplementing the iCloud API calls, cookie parsing, or local address
database. The only thing we add here is: (1) pointing sys.path at vendor/,
(2) silencing rich.Console output (the CLI prints progress with it; a GUI
doesn't have a terminal to print to), and (3) small async helpers shaped for
what the views need.
"""

import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from hidemyemail_generator.main import (  # noqa: E402
    RichHideMyEmail,
    account_summary,
    fetch_account_info_from_cookie,
    load_cookie_context,
)
from hidemyemail_generator.inbox import (  # noqa: E402
    ADDRESS_STATES,
    InboxConfig,
    connect_db,
    export_csv_files,
    list_addresses,
    list_messages,
    load_config as load_inbox_config,
    mark_address,
    mask_account,
    save_config as save_inbox_config,
    sync_inbox,
    upsert_address,
    utc_now,
)

__all__ = [
    "ADDRESS_STATES",
    "InboxConfig",
    "connect_db",
    "export_csv_files",
    "list_addresses",
    "list_addresses_full",
    "list_messages",
    "load_inbox_config",
    "mark_address",
    "mask_account",
    "save_inbox_config",
    "sync_inbox",
    "upsert_address",
    "save_cookie_text",
    "validate_and_fetch_account",
    "generate_emails",
    "list_emails",
    "set_active",
    "update_metadata",
    "set_label",
    "delete_addresses",
    "bulk_set_label",
    "bulk_set_state",
]

# Local addresses are always grouped by state, no matter what secondary sort
# the user picks (Apple's own app does the same) — but which of the two
# fixed orders applies (Used>Unused>Trash, or its reverse) is itself
# clickable/reversible, independent of the label/created secondary sort.
STATE_SORT_ORDER_ASC = {"used": 0, "unused": 1, "trash": 2}


def _silent_client(cookie_file: str, region: str) -> RichHideMyEmail:
    hme = RichHideMyEmail(cookie_file=cookie_file, no_output_file=True, region=region)
    # Route the CLI's rich-console progress logging into a throwaway buffer -
    # there's no terminal in a GUI app for it to write to.
    hme.console = Console(file=io.StringIO(), no_color=True, force_terminal=False, width=200)
    hme.table = Table()
    return hme


def save_cookie_text(cookie_file: str, raw_text: str) -> None:
    path = Path(cookie_file)
    if path.exists() and path.stat().st_size > 0:
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    path.write_text(raw_text, encoding="utf-8")


async def validate_and_fetch_account(cookie_text: str, region: str) -> dict:
    """Parses pasted cookie text the same way the CLI parses cookies.txt
    (raw cookie header, or a 'Copy as cURL' paste), then validates it
    against iCloud's own session-check endpoint."""
    fd, tmp_path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(cookie_text)
        cookie, maildomain_host = load_cookie_context(tmp_path, region)
    finally:
        os.unlink(tmp_path)

    if not cookie:
        return {
            "ok": False,
            "error": "Could not find a cookie in the pasted text.",
            "account": None,
            "cookie": None,
            "maildomain_host": None,
        }

    account = await fetch_account_info_from_cookie(cookie, region, maildomain_host)
    if "error" in account:
        return {
            "ok": False,
            "error": account["error"],
            "account": None,
            "cookie": cookie,
            "maildomain_host": maildomain_host,
        }

    summary = account_summary(account)
    return {
        "ok": True,
        "error": None,
        "account": summary,
        "cookie": cookie,
        "maildomain_host": maildomain_host or summary["maildomain_host"],
    }


async def generate_emails(cookie_file: str, region: str, label: str, count: int) -> dict:
    hme = _silent_client(cookie_file, region)
    async with hme:
        emails = await hme.generate(label, count)
    ok = len(emails) == count
    error = None if ok else (
        hme.last_error or {"code": None, "message": "Generation failed", "retry_after": None}
    )
    return {"ok": ok, "emails": list(emails), "error": error}


async def list_emails(cookie_file: str, region: str, label_query, active: bool) -> dict:
    hme = _silent_client(cookie_file, region)
    async with hme:
        return await hme.list(label_query, active)


async def set_active(cookie_file: str, region: str, email: str, active: bool) -> dict:
    hme = _silent_client(cookie_file, region)
    async with hme:
        return await hme.set_active(email, active)


async def update_metadata(cookie_file: str, region: str, email: str, label, note) -> dict:
    hme = _silent_client(cookie_file, region)
    async with hme:
        return await hme.update_metadata(email, label, note)


def list_addresses_full(
    conn,
    state: str = None,
    sort_key: str = "created_at",
    sort_dir: str = "desc",
    state_dir: str = "asc",
    limit: int = 500,
):
    """Like the vendored list_addresses, but also returns created_at.

    Rows are always grouped by state first — sort_key/sort_dir ("label" or
    "created_at", each "asc"/"desc") only controls the order *within* each
    state group. state_dir ("asc" = Used, Unused, Trash; "desc" = reverse)
    controls the state grouping's own direction, independently. Both are
    driven by clicking column headers, not a single combined dropdown.
    Python-side, on top of a fixed query, so vendor/hidemyemail_generator
    stays unmodified.
    """
    if state:
        rows = conn.execute(
            """
            SELECT email, label, state, source, created_at, updated_at
            FROM addresses WHERE state = ?
            """,
            (state,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT email, label, state, source, created_at, updated_at FROM addresses"
        ).fetchall()

    items = [dict(row) for row in rows]

    if sort_key == "label":
        items.sort(key=lambda r: (r.get("label") or "").lower(), reverse=(sort_dir == "desc"))
    else:
        items.sort(key=lambda r: r.get("created_at") or "", reverse=(sort_dir == "desc"))
    items.sort(
        key=lambda r: STATE_SORT_ORDER_ASC.get(r["state"], 99),
        reverse=(state_dir == "desc"),
    )  # stable — state group wins over the secondary sort above

    return items[:limit]


def set_label(conn, email: str, label: str) -> None:
    now = utc_now()
    conn.execute(
        "UPDATE addresses SET label = ?, updated_at = ? WHERE email = ?", (label, now, email)
    )
    conn.commit()


def delete_addresses(conn, emails: list) -> None:
    if not emails:
        return
    placeholders = ",".join("?" for _ in emails)
    conn.execute(f"DELETE FROM addresses WHERE email IN ({placeholders})", emails)
    conn.commit()


def bulk_set_label(conn, emails: list, label: str) -> None:
    if not emails:
        return
    now = utc_now()
    placeholders = ",".join("?" for _ in emails)
    conn.execute(
        f"UPDATE addresses SET label = ?, updated_at = ? WHERE email IN ({placeholders})",
        [label, now, *emails],
    )
    conn.commit()


def bulk_set_state(conn, emails: list, state: str) -> None:
    if not emails:
        return
    if state not in ADDRESS_STATES:
        raise ValueError(f"Unsupported address state: {state}")
    now = utc_now()
    placeholders = ",".join("?" for _ in emails)
    conn.execute(
        f"UPDATE addresses SET state = ?, updated_at = ? WHERE email IN ({placeholders})",
        [state, now, *emails],
    )
    conn.commit()
