"""
Cross-platform (Windows / macOS / Ubuntu) desktop tracking agent.

Flow:
  1. Employee logs in once (email/password against the backend API).
  2. Click "Start Tracking" in the system tray icon -> opens a time entry on
     the server and starts a background loop that takes a screenshot every
     SCREENSHOT_INTERVAL_SECONDS and uploads it (with the machine's public IP).
  3. Click "Stop Tracking" -> closes the time entry and stops the loop.

Notes for packaging on each OS:
  - Windows: works as-is. Package with PyInstaller (`pyinstaller --onefile --noconsole agent.py`).
  - macOS: the OS will prompt for "Screen Recording" permission the first time
    a screenshot is taken (System Settings > Privacy & Security > Screen Recording).
    Grant it to Terminal/Python (or to the packaged .app) or captures will be black.
  - Ubuntu/Linux: on Wayland, mss/screenshot tools may be restricted; X11 works
    out of the box. If needed, run the session under X11 or use `grim` as a fallback.
"""
import io
import json
import os
import socket
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from getpass import getpass
from pynput import keyboard, mouse
import ctypes

import mss
import requests
from PIL import Image
import pystray
from pystray import MenuItem as Item

from media_activity import is_foreground_media_playing

from config import (
    BACKEND_URL,
    AUTO_START_TRACKING,
    DATA_DIR,
    SCREENSHOT_INTERVAL_SECONDS,
    IDLE_TIMEOUT_SECONDS,
    MEDIA_ACTIVITY_DETECTION_ENABLED,
    MEDIA_CHECK_INTERVAL_SECONDS,
    SCREENSHOT_NOTIFICATIONS_ENABLED,
    TOKEN_FILE,
)


def _has_display():
    """Whether a login dialog can actually be shown. On Windows/macOS a
    display is always assumed present; on Linux, tray apps require an X11/
    Wayland session (there's no DISPLAY on a headless server, for example)."""
    if sys.platform in ("win32", "darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def prompt_login_gui(error_message=None):
    """Shows a small login window and returns (email, password), or None if
    the user closed it. Used instead of a console prompt because a packaged,
    auto-starting tray app has no terminal to type into."""
    import tkinter as tk

    result = {}

    root = tk.Tk()
    root.title("Org Tracker — Log in")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    frame = tk.Frame(root, padx=24, pady=20)
    frame.pack()

    tk.Label(frame, text="Org Tracker", font=("Segoe UI", 14, "bold")).grid(
        row=0, column=0, columnspan=2, pady=(0, 12)
    )

    if error_message:
        tk.Label(frame, text=error_message, fg="#c0392b", wraplength=260).grid(
            row=1, column=0, columnspan=2, pady=(0, 8)
        )

    tk.Label(frame, text="Email").grid(row=2, column=0, sticky="w")
    email_var = tk.StringVar()
    email_entry = tk.Entry(frame, textvariable=email_var, width=30)
    email_entry.grid(row=3, column=0, columnspan=2, pady=(0, 8))
    email_entry.focus_set()

    tk.Label(frame, text="Password").grid(row=4, column=0, sticky="w")
    password_var = tk.StringVar()
    password_entry = tk.Entry(frame, textvariable=password_var, width=30, show="*")
    password_entry.grid(row=5, column=0, columnspan=2, pady=(0, 14))

    def submit(event=None):
        result["email"] = email_var.get().strip()
        result["password"] = password_var.get()
        root.destroy()

    password_entry.bind("<Return>", submit)
    tk.Button(frame, text="Log in", command=submit, width=12).grid(row=6, column=0, columnspan=2)

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.eval("tk::PlaceWindow . center")
    root.mainloop()

    if not result.get("email"):
        return None
    return result["email"], result["password"]


class ActivityMonitor:
    """Track mouse, keyboard, and Windows system input activity."""

    def __init__(self, on_idle_change, timeout_seconds=IDLE_TIMEOUT_SECONDS):
        self._on_idle_change = on_idle_change
        self._timeout_seconds = timeout_seconds
        self._last_activity = time.monotonic()
        self._last_media_check = 0.0
        self._idle = False
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._thread = None
        self._mouse_listener = None
        self._keyboard_listener = None

        # Windows system-input tracking
        self._last_system_input = self._get_system_input_time()
        
    @staticmethod
    def _get_system_input_time():
        """
        Get the time of the last user input reported by Windows.

        This acts as an additional activity source for things such as
        Precision Touchpad gestures that may not reach pynput's
        on_scroll callback.
        """
        if sys.platform != "win32":
            return None
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("dwTime", ctypes.c_uint),
            ]
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)

        try:
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return info.dwTime
        except Exception:
            pass
        return None
    def set_timeout(self, timeout_seconds):
        with self._state_lock:
            self._timeout_seconds = timeout_seconds

    def start(self):
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return
            self._last_activity = time.monotonic()
            self._last_media_check = 0.0
            self._idle = False
            self._stop_event.clear()
            # Reset Windows input timestamp when monitoring starts.
            self._last_system_input = self._get_system_input_time()
            self._mouse_listener = mouse.Listener(
                on_move=self._activity,
                on_click=self._activity,
                on_scroll=self._activity,
            )
            self._keyboard_listener = keyboard.Listener(
                on_press=self._activity
            )
            self._mouse_listener.start()
            self._keyboard_listener.start()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True
            )
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        for listener in (
            self._mouse_listener,
            self._keyboard_listener
        ):
            if listener:
                listener.stop()
        if (
            self._thread
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=2)
        self._mouse_listener = None
        self._keyboard_listener = None
        self._thread = None

    def _activity(self, *args):
        became_active = False
        with self._state_lock:
            self._last_activity = time.monotonic()
            if self._idle:
                self._idle = False
                became_active = True

        if became_active:
            self._on_idle_change(False)

    def _check_windows_input(self):
        """
        Check whether Windows has registered new user input.
        This is especially useful for Precision Touchpad gestures.
        """
        current_input = self._get_system_input_time()

        if current_input is None:
            return

        with self._state_lock:
            previous_input = self._last_system_input
            if (
                previous_input is not None
                and current_input != previous_input
            ):
                self._last_activity = time.monotonic()
                if self._idle:
                    self._idle = False
                    became_active = True
                else:
                    became_active = False
            else:
                became_active = False
            self._last_system_input = current_input
        if became_active:
            self._on_idle_change(False)

    def _run(self):
        while not self._stop_event.wait(1):
            now = time.monotonic()

            if (
                MEDIA_ACTIVITY_DETECTION_ENABLED
                and now - self._last_media_check >= MEDIA_CHECK_INTERVAL_SECONDS
            ):
                self._last_media_check = now
                if is_foreground_media_playing():
                    self._activity()
                    continue
            became_idle = False
            with self._state_lock:
                timeout = self._timeout_seconds
                if (
                    not self._idle
                    and time.monotonic() - self._last_activity >= timeout
                ):
                    self._idle = True
                    became_idle = True
            if became_idle:
                self._on_idle_change(True)


class TrackerAgent:
    def __init__(self):
        self.token = None
        self.active_entry_id = None
        self.tracking = False
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._command_thread = None
        self._start_lock = threading.Lock()
        self._activity_monitor = None
        self._idle = False
        self._resume_after_idle = False
        self._settings_thread = None
        self.icon = None
        self.screenshot_interval_seconds = SCREENSHOT_INTERVAL_SECONDS
        self.idle_timeout_seconds = IDLE_TIMEOUT_SECONDS

    # ---------- Notifications ----------

    def notify(self, message, title="Org Tracker"):
        """Shows a small OS-native popup (Windows toast / macOS notification
        center / Linux libnotify, depending on platform support). This is the
        ONLY thing an employee sees once the agent is packaged with
        --noconsole for real deployment — print() statements go nowhere
        visible at that point, so every important status change needs to
        also call this."""
        print(f"[{title}] {message}")
        if not self.icon:
            return
        try:
            if getattr(self.icon, "HAS_NOTIFICATION", True):
                self.icon.notify(message, title)
        except Exception as e:
            print(f"Notification failed (non-fatal): {e}")

    # ---------- Auth ----------

    def load_token(self):
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r") as f:
                self.token = json.load(f).get("token")

    def save_token(self, token):
        self.token = token
        with open(TOKEN_FILE, "w") as f:
            json.dump({"token": token}, f)

    def delete_token(self):
        self.token = None
        if os.path.exists(TOKEN_FILE):
            try:
                os.remove(TOKEN_FILE)
            except OSError:
                pass

    def _prompt_credentials(self, error_message=None):
        if _has_display():
            try:
                creds = prompt_login_gui(error_message)
            except Exception as e:
                print(f"Login window failed ({e}), falling back to console login.")
                creds = None
            if creds is not None:
                return creds
            if _has_display():
                # user closed the window deliberately — don't fall through to console
                raise SystemExit("Login cancelled.")

        print("=== Org Tracker Agent: Login ===")
        if error_message:
            print(error_message)
        email = input("Email: ").strip()
        password = getpass("Password: ")
        return email, password

    def login(self):
        error_message = None
        while True:
            email, password = self._prompt_credentials(error_message)
            resp = requests.post(
                f"{BACKEND_URL}/auth/login",
                data={"username": email, "password": password},
                timeout=10,
            )
            if resp.status_code == 401:
                error_message = "Incorrect email or password. Please try again."
                continue
            resp.raise_for_status()
            token = resp.json()["access_token"]
            self.save_token(token)
            print("Logged in successfully.")
            return

    def validate_token(self):
        if not self.token:
            return False
        try:
            resp = requests.get(
                f"{BACKEND_URL}/users/me",
                headers=self.auth_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (401, 403):
                print("Stored token is invalid or expired. Please log in again.")
                self.delete_token()
                return False
            raise
        except Exception as exc:
            print(f"Token validation failed: {exc}")
            return False

    def auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def fetch_settings(self):
        if not self.token:
            return
        try:
            resp = requests.get(
                f"{BACKEND_URL}/settings",
                headers=self.auth_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            new_interval = data.get("screenshot_interval_seconds")
            if isinstance(new_interval, int) and new_interval > 0:
                if new_interval != self.screenshot_interval_seconds:
                    print(f"Screenshot interval updated: {self.screenshot_interval_seconds}s -> {new_interval}s")
                self.screenshot_interval_seconds = new_interval

            new_idle_timeout = data.get("idle_timeout_seconds")
            if isinstance(new_idle_timeout, int) and new_idle_timeout > 0:
                if new_idle_timeout != self.idle_timeout_seconds:
                    print(f"Idle timeout updated: {self.idle_timeout_seconds}s -> {new_idle_timeout}s")
                self.idle_timeout_seconds = new_idle_timeout
                if self._activity_monitor:
                    self._activity_monitor.set_timeout(new_idle_timeout)
        except requests.exceptions.RequestException as e:
            print(f"Could not refresh settings ({e.__class__.__name__}); keeping current interval.")
        except Exception as e:
            print(f"Unexpected error refreshing settings: {e}")

    def _settings_loop(self):
        while True:
            self.fetch_settings()
            time.sleep(300)

    def _get_error_detail(self, response):
        try:
            return response.json().get("detail")
        except Exception:
            return response.text

    def _handle_unauthorized(self):
        was_tracking = self.tracking
        self.delete_token()
        self.tracking = False
        self.active_entry_id = None
        self._stop_event.set()
        if self.icon:
            self._update_menu()
        if was_tracking:
            self.notify("Session expired — tracking stopped. Please log in again.")
        else:
            self.notify("Session expired. Please log in again.")

    def sync_active_entry(self):
        try:
            resp = requests.get(
                f"{BACKEND_URL}/time-entries/active",
                headers=self.auth_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            entry = resp.json()
            if entry:
                self.active_entry_id = entry["id"]
                self.tracking = True
                self._start_worker()
            else:
                self.active_entry_id = None
                self.tracking = False
            if self.icon:
                self._update_menu()
        except Exception as e:
            print(f"Could not refresh active tracking state: {e}")
            self.active_entry_id = None
            self.tracking = False

    # ---------- Helpers ----------

    @staticmethod
    def get_system_ip():
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "unknown"

    @staticmethod
    def capture_screenshot_bytes():
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # full virtual screen, all monitors combined
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            return buf.getvalue()

    # ---------- Tracking control ----------

    def _start_worker(self):
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self._worker_thread.start()

    def _start_activity_monitor(self):
        if not self._activity_monitor:
            self._activity_monitor = ActivityMonitor(self._handle_idle_change, self.idle_timeout_seconds)
        else:
            self._activity_monitor.set_timeout(self.idle_timeout_seconds)
        self._activity_monitor.start()

    def _handle_idle_change(self, is_idle):
        self._idle = is_idle
        if is_idle:
            if self.tracking:
                entry_id = self.active_entry_id
                self.notify(
                    f"Tracking stopped after {self.idle_timeout_seconds} seconds of inactivity "
                    f"(session #{entry_id})."
                )
                self._stop_tracking(notify_user=False, preserve_for_idle=True)
        elif self._resume_after_idle:
            self._resume_after_idle = False
            self.start_tracking()
            self.notify("Activity detected. Tracking resumed.")

    def start_tracking(self, icon=None, item=None):
        if not self._start_lock.acquire(blocking=False):
            return
        try:
            self._start_tracking()
        finally:
            self._start_lock.release()

    def _start_tracking(self):
        if self.tracking:
            return

        try:
            if not self.token or not self.validate_token():
                self.login()

            ip_address = self.get_system_ip()
            resp = requests.post(
                f"{BACKEND_URL}/time-entries/start",
                json={"ip_address": ip_address},
                
                headers=self.auth_headers(),
                timeout=10,
            )
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError:
                detail = self._get_error_detail(resp)
                if resp.status_code == 400 and "already active" in str(detail).lower():
                    print("Tracking session already active on the backend. Syncing local state.")
                    self.sync_active_entry()
                    return
                if resp.status_code == 401:
                    print("Start Tracking auth failed. Please log in again.")
                    self.delete_token()
                    self.login()
                    resp = requests.post(
                        f"{BACKEND_URL}/time-entries/start",
                        json={"ip_address": ip_address},
                        headers=self.auth_headers(),
                        timeout=10,
                    )
                    resp.raise_for_status()
                else:
                    raise
        except requests.exceptions.RequestException as e:
            self.notify(f"Could not reach the server — tracking not started. ({e.__class__.__name__})")
            return
        except SystemExit:
            return
        except Exception as e:
            self.notify(f"Could not start tracking: {e}")
            return

        self.active_entry_id = resp.json()["id"]
        self.tracking = True
        self._idle = False
        self._start_worker()
        self._update_menu()
        self.notify(f"Tracking started (IP {ip_address})")

    def stop_tracking(self, icon=None, item=None):
        self._stop_tracking()

    def _stop_tracking(self, notify_user=True, preserve_for_idle=False):
        if not self.tracking:
            if not preserve_for_idle:
                self._resume_after_idle = False
            return
        self._resume_after_idle = preserve_for_idle
        self.tracking = False
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

        entry_id = self.active_entry_id
        try:
            resp = requests.post(
                f"{BACKEND_URL}/time-entries/{entry_id}/stop",
                headers=self.auth_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            if notify_user:
                if preserve_for_idle:
                    self.notify(f"Tracking paused (session #{entry_id})")
                else:
                    self.notify(f"Tracking stopped (session #{entry_id})")
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                self._handle_unauthorized()
            else:
                if notify_user:
                    self.notify(f"Tracking stopped locally, but the server didn't confirm it "
                                f"(HTTP {exc.response.status_code if exc.response else '?'}).")
        except requests.exceptions.RequestException as e:
            if notify_user:
                self.notify(f"Tracking stopped locally, but couldn't reach the server to confirm it "
                            f"({e.__class__.__name__}). It may still show as active on the dashboard.")

        self.active_entry_id = None
        self._update_menu()

    def _tracking_loop(self):
        elapsed = 0
        while not self._stop_event.is_set():
            # sleep in 1s ticks so Stop reacts quickly instead of waiting a full interval
            if self._stop_event.wait(timeout=1):
                break
            elapsed += 1
            if elapsed >= self.screenshot_interval_seconds:
                elapsed = 0
                try:
                    self._capture_and_upload()
                except Exception as e:
                    self.notify(f"Screenshot failed: {e}")

    def _command_loop(self):
        request_file = os.path.join(DATA_DIR, "start_tracking.request")
        while True:
            if os.path.exists(request_file):
                try:
                    os.remove(request_file)
                except OSError:
                    pass
                if not self.tracking:
                    self.start_tracking()
            time.sleep(1)

    def _capture_and_upload(self):
        image_bytes = self.capture_screenshot_bytes()
        ip_address = self.get_system_ip()
        files = {"file": (f"shot_{int(time.time())}.jpg", image_bytes, "image/jpeg")}
        data = {"time_entry_id": self.active_entry_id, "ip_address": ip_address}
        resp = requests.post(
            f"{BACKEND_URL}/screenshots",
            data=data,
            files=files,
            headers=self.auth_headers(),
            timeout=30,
        )
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError:
            if resp.status_code == 401:
                self._handle_unauthorized()
            raise
        captured_at = datetime.now(timezone.utc).astimezone().strftime("%I:%M %p")
        if SCREENSHOT_NOTIFICATIONS_ENABLED:
            self.notify(f"Screenshot captured at {captured_at} (IP {ip_address})")

    # ---------- Tray icon ----------

    def _make_icon_image(self, color):
        img = Image.new("RGB", (64, 64), color)
        return img

    def _update_menu(self):
        if self.icon:
            self.icon.icon = self._make_icon_image("green" if self.tracking else "gray")
            self.icon.menu = self._build_menu()

    def _build_menu(self):
        return pystray.Menu(
            Item("Start Tracking", self.start_tracking, enabled=not self.tracking),
            Item("Stop Tracking", self.stop_tracking, enabled=self.tracking),
            Item("Quit", self.quit),
        )

    def quit(self, icon=None, item=None):
        if self.tracking:
            self.stop_tracking()
        if self.icon:
            self.icon.stop()

    def run(self):
        self.load_token()
        if not self.validate_token():
            self.login()

        self.icon = pystray.Icon(
            "org-tracker",
            self._make_icon_image("gray"),
            "Org Tracker (stopped)",
            menu=self._build_menu(),
        )
        self._start_activity_monitor()
        self.fetch_settings()
        self.sync_active_entry()
        if AUTO_START_TRACKING and not self.tracking:
            self.start_tracking()
        self._command_thread = threading.Thread(target=self._command_loop, daemon=True)
        self._command_thread.start()
        self._settings_thread = threading.Thread(target=self._settings_loop, daemon=True)
        self._settings_thread.start()
        print("Agent started. Look for the tray icon in the notification area.")
        self.icon.run()


if __name__ == "__main__":
    try:
        TrackerAgent().run()
    except Exception:
        # Running via pythonw.exe means there's no console for a crash to
        # print to — without this, a startup failure looks like "nothing
        # happened" with zero clues why. Always leave a trail on disk.
        log_path = os.path.join(DATA_DIR, "agent_error.log")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- crash at {datetime.now(timezone.utc).isoformat()} ---\n")
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise
 