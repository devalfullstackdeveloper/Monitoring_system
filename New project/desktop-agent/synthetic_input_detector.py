"""Detect Windows low-level mouse and keyboard input injection."""

import ctypes
import os
import sys
import threading
from ctypes import wintypes


WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
LLMHF_INJECTED = 0x00000001
LLKHF_INJECTED = 0x00000010
ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
HOOKPROC = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
        ("mouse_data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dw_extra_info", ULONG_PTR),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vk_code", wintypes.DWORD),
        ("scan_code", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dw_extra_info", ULONG_PTR),
    ]


class SyntheticInputDetector:
    """Report low-level injected and hardware input on Windows."""

    def __init__(self, on_real_input=None, on_synthetic_input=None):
        self._on_real = on_real_input or (lambda: None)
        self._on_synthetic = on_synthetic_input or (lambda: None)
        self._mouse_hook = None
        self._keyboard_hook = None
        self._thread = None
        self._thread_id = None
        self._running = False
        self._hook_ready = threading.Event()
        self._debug_events = os.getenv(
            "SYNTHETIC_INPUT_DEBUG", "true"
        ).lower() in ("1", "true", "yes", "on")
        self._logged_event_count = 0
        self._event_log_limit = 20

        hook_proc = HOOKPROC(
            LRESULT,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        self._mouse_proc = hook_proc(self._mouse_hook_proc)
        self._keyboard_proc = hook_proc(self._keyboard_hook_proc)

    @property
    def supported(self):
        return sys.platform == "win32"

    def _mouse_hook_proc(self, n_code, w_param, l_param):
        if n_code >= 0:
            info = ctypes.cast(
                l_param, ctypes.POINTER(MSLLHOOKSTRUCT)
            ).contents
            injected = bool(info.flags & LLMHF_INJECTED)
            self._log_event("mouse", injected)
            self._report(injected)
        return ctypes.windll.user32.CallNextHookEx(
            self._mouse_hook, n_code, w_param, l_param
        )

    def _keyboard_hook_proc(self, n_code, w_param, l_param):
        if n_code >= 0:
            info = ctypes.cast(
                l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)
            ).contents
            injected = bool(info.flags & LLKHF_INJECTED)
            self._log_event("keyboard", injected)
            self._report(injected)
        return ctypes.windll.user32.CallNextHookEx(
            self._keyboard_hook, n_code, w_param, l_param
        )

    def _report(self, synthetic):
        try:
            if synthetic:
                self._on_synthetic()
            else:
                self._on_real()
        except Exception:
            # Hook callbacks must not raise into the Windows hook chain.
            pass

    def _log_event(self, device, injected):
        if not self._debug_events or self._logged_event_count >= self._event_log_limit:
            return
        self._logged_event_count += 1
        print(
            f"synthetic input hook event: device={device}, "
            f"injected={injected}",
            flush=True,
        )

    def start(self):
        if not self.supported or self._running:
            return
        self._running = True
        self._hook_ready.clear()
        self._thread = threading.Thread(
            target=self._run_message_loop,
            name="synthetic-input-detector",
            daemon=True,
        )
        self._thread.start()
        self._hook_ready.wait(timeout=2)
        if not self._hook_ready.is_set():
            print("ERROR: synthetic input hook thread did not initialize", flush=True)

    def _run_message_loop(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.CallNextHookEx.restype = LRESULT
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        self._thread_id = kernel32.GetCurrentThreadId()
        # Ensure this thread owns a message queue before installing hooks.
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        module = kernel32.GetModuleHandleW(None)
        self._mouse_hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_proc, module, 0
        )
        if not self._mouse_hook:
            error = kernel32.GetLastError()
            print(
                f"ERROR: mouse hook failed to install, GetLastError={error}",
                flush=True,
            )
        self._keyboard_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._keyboard_proc, module, 0
        )
        if not self._keyboard_hook:
            error = kernel32.GetLastError()
            print(
                f"ERROR: keyboard hook failed to install, GetLastError={error}",
                flush=True,
            )
        self._hook_ready.set()

        if not self._mouse_hook or not self._keyboard_hook:
            self.stop()
            return

        while self._running and user32.GetMessageW(
            ctypes.byref(message), None, 0, 0
        ) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        if self._thread is not threading.current_thread():
            if self._thread:
                self._thread.join(timeout=2)
        if self._mouse_hook:
            ctypes.windll.user32.UnhookWindowsHookEx(self._mouse_hook)
        if self._keyboard_hook:
            ctypes.windll.user32.UnhookWindowsHookEx(self._keyboard_hook)
        self._mouse_hook = None
        self._keyboard_hook = None
        self._thread = None
        self._thread_id = None