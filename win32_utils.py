"""
win32_utils.py — Windows API helpers for TaskBar positioning and singleton management.

Uses ctypes exclusively (no pywin32 dependency).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import os
import sys

log = logging.getLogger("tokenbar")

# ── Win32 constants ──────────────────────────────────────────────────────────
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
ERROR_ALREADY_EXISTS = 183


# ── Screen / taskbar geometry ────────────────────────────────────────────────

def get_work_area() -> ctypes.wintypes.RECT:
    """Return the desktop work area (excludes taskbar)."""
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    return rect


def get_screen_height() -> int:
    return ctypes.windll.user32.GetSystemMetrics(1)


def get_screen_width() -> int:
    return ctypes.windll.user32.GetSystemMetrics(0)


def set_topmost(hwnd: int) -> None:
    """Force window above taskbar using Win32 SetWindowPos."""
    ctypes.windll.user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
    )


# ── Singleton via named mutex ────────────────────────────────────────────────

_mutex_handle: int | None = None

MUTEX_NAME = "Global\\TokenBar_Singleton_Mutex"


def ensure_singleton() -> None:
    """Acquire a named mutex. Exit immediately if another instance holds it.

    This replaces the old PID-file + TerminateProcess approach.
    A named mutex is the standard Windows pattern for single-instance apps:
    - No risk of killing an unrelated process that reused the PID
    - Automatically released if the process crashes
    - No stale files to clean up
    """
    global _mutex_handle

    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
    last_error = ctypes.GetLastError()

    if last_error == ERROR_ALREADY_EXISTS:
        log.info("Another TokenBar instance is already running — exiting.")
        # Close the duplicate handle before exiting
        if _mutex_handle:
            ctypes.windll.kernel32.CloseHandle(_mutex_handle)
            _mutex_handle = None
        sys.exit(0)

    log.info("Singleton mutex acquired (pid=%s)", os.getpid())


def cleanup_pid_file(pid_file: str) -> None:
    """Remove legacy PID file if it exists (migration from old singleton method)."""
    try:
        os.unlink(pid_file)
    except OSError:
        pass
