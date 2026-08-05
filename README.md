# HideMyEmail Generator — Windows GUI (unofficial)

A PySide6 (Qt) desktop GUI for Windows that mirrors the upstream project's
native macOS app (Generate / Addresses / Inbox / Scheduler). It's a thin UI
layer over the same Python CLI backend (`hidemyemail_generator`), vendored
unmodified under `vendor/`. This isn't from the original project's author —
it's a Windows front-end built on top of their MIT-licensed code.

## Running it

```bat
run.bat
```

First run creates a `.venv`, installs dependencies, and launches the app.
Subsequent runs just launch it.

## Signing in

Apple doesn't offer a Hide My Email API you can sign into directly, so
(same as the CLI) this app authenticates by reusing an active iCloud web
session's cookie:

1. Sign in at `icloud.com/settings` (or `icloud.com.cn` for iCloud China) in
   your normal browser.
2. Open DevTools (F12) → Network tab, refresh the page.
3. Filter for `hme` or `maildomainws`, right-click a matching request →
   Copy → **Copy as cURL**.
4. Paste the whole copied text into the sign-in dialog (the account button
   in the top-right of the app). A raw `Cookie:` header value also works.

The app validates the cookie against iCloud before saving it, and shows the
Apple ID it resolves to. Avoid `feedbackws`/`reportStats` requests — they're
usually missing the `X-APPLE-WEBAUTH-USER` cookie this needs.

## What's local vs. what's not

Every network call goes straight to Apple's own `icloud.com` / `icloud.com.cn`
Hide My Email endpoints — nothing is sent anywhere else, and the app collects
no telemetry.

Everything else lives in `data/`, next to this app:

- `data/cookies.txt` — your pasted iCloud session cookie. Treat this like a
  password; anyone with it can act as you against Hide My Email while it's
  valid.
- `data/hidemyemail.db` — local sqlite database of addresses
  (unused/used/trash state) and synced inbox messages.
- `data/inbox_config.json` — your IMAP mailbox host/username/password, saved
  in plain text (same as the upstream CLI). Use an app-specific password
  where your mail provider supports one.
- `data/exports/` — CSV exports.

## Tabs

- **Generate** — create one address or a small batch with a custom label.
- **Addresses** — local unused/used/trash management, plus a live view of
  your iCloud inventory (deactivate/reactivate, sync either direction, CSV
  export).
- **Inbox** — connect a mailbox over IMAP, sync forwarded messages, and pull
  out verification codes automatically.
- **Scheduler** — generate a larger batch over time; pauses and resumes
  automatically if Apple rate-limits address creation.

## Requirements

- Windows with Python 3.10+ on PATH.
- An active iCloud+ subscription (required for Hide My Email).
