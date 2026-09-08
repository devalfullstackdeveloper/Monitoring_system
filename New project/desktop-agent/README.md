# Desktop Tracker Agent

Runs on the employee's machine (Windows, macOS, or Ubuntu). Lives in the
system tray with **Start Tracking** / **Stop Tracking** / **Quit**.

## Setup (development — running from source)

```bash
cd desktop-agent
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # point BACKEND_URL at your backend
python agent.py
```

First run opens a small login window (email/password, created by an admin
via the API or dashboard). The token is cached at
`%APPDATA%\OrgTracker\auth_token.json` (Windows) / `~/.config/OrgTracker/`
(Linux) / `~/Library/Application Support/OrgTracker/` (macOS), so it
survives restarts and isn't asked for again until it expires.

For distributing this to real employee machines as a packaged `.exe` with
auto-start, see the root `README.md`'s "Deploying across your organization"
section, and `build-agent.bat` / `install-autostart.bat` in this folder.

## Per-OS notes

- **Windows**: works out of the box. Package with
  `pyinstaller --onefile --noconsole --name OrgTrackerAgent agent.py`
  (or just run `build-agent.bat`), and use `install-autostart.bat` so it
  launches automatically on login.
- **macOS**: the first screenshot triggers a "Screen Recording" permission
  prompt — grant it to Terminal/Python (or your packaged `.app`) in
  System Settings > Privacy & Security > Screen Recording, otherwise captures
  come back black. Package with PyInstaller + `py2app` for a proper `.app`.
- **Ubuntu/Linux**: works on X11 sessions out of the box. On Wayland, screen
  capture is sandboxed by design — either run the session under X11, or swap
  the `mss` capture call for a Wayland-aware tool (e.g. `grim`) if you need
  Wayland support. Desktop notifications also depend on a notification
  daemon (e.g. GNOME/KDE's built-in one) being present — most desktop
  Ubuntu installs already have one.

## What it does

1. Logs in once (via a small popup window), stores a token.
2. On **Start Tracking**: opens a time entry on the backend (recording the
   machine's public IP) and starts a background loop. Shows a confirmation
   popup.
3. Every `SCREENSHOT_INTERVAL_SECONDS` (default 300s = 5 min), captures a
   screenshot and uploads it to the backend along with the current IP and the
   active time entry ID — showing a small popup notification each time
   ("Screenshot captured at ...").
4. On **Stop Tracking**: closes the time entry, stops the loop, and shows a
   confirmation popup.
5. If anything goes wrong — the server is unreachable, a screenshot upload
   fails, the login session expires mid-tracking — a popup explains what
   happened instead of failing silently. This matters especially once the
   agent is packaged with `--noconsole`: at that point popups are the
   *only* way an employee (or you, testing it) can tell what the agent is
   doing, since there's no visible console window for `print()` output to
   go to.

Notifications use the OS's native notification system via `pystray`
(Windows toast / macOS Notification Center / Linux libnotify). Support is
platform-dependent — if a given system doesn't support it, the agent logs
the same message to the console instead of failing.

## Ideas for later (not implemented yet)

- Idle detection (skip screenshots / pause timer after N minutes of no
  mouse/keyboard input) — e.g. via `pynput`.
- Retry/queue screenshots that fail to upload instead of dropping them.
- Blurring/redacting screenshots before upload for extra privacy.
