"""
shared.py — Shared utilities for TokenBar.

Provides atomic file I/O, token formatting, and the canonical
data schema used by both statusline.py and tokenbar.py.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(_DIR, "token_data.json")

EMPTY_DATA: dict[str, Any] = {
    "session": {},
    "daily": {},
    "rate_limits": {},
}


# ── Atomic file I/O ─────────────────────────────────────────────────────────

def load_data(path: str = DATA_FILE) -> dict[str, Any]:
    """Load token_data.json, returning EMPTY_DATA on any failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {k: dict(v) if isinstance(v, dict) else v for k, v in EMPTY_DATA.items()}


def save_data(data: dict[str, Any], path: str = DATA_FILE) -> None:
    """Write data atomically: tmp file + os.replace (safe on NTFS)."""
    data["last_updated"] = datetime.now().isoformat()
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except BaseException:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── Formatting ───────────────────────────────────────────────────────────────

def fmt_tokens(n: int | None) -> str:
    """Human-readable token count: 1.5k, 2.3M, or raw number."""
    if n is None or n == 0:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_time_until(timestamp: int | float | None) -> str:
    """Countdown string from a unix timestamp: '3h22m', '45m', 'resetou'."""
    if not timestamp:
        return "—"
    try:
        delta = datetime.fromtimestamp(float(timestamp)) - datetime.now()
        if delta.total_seconds() <= 0:
            return "resetou"
        secs = int(delta.total_seconds())
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        if days > 0:
            return f"{days}d{hours}h"
        if hours > 0:
            return f"{hours}h{minutes:02d}m"
        return f"{minutes}m"
    except (TypeError, ValueError, OSError):
        return "—"


def get_weekly_tokens(data: dict[str, Any]) -> int:
    """Sum input+output tokens from the last 7 days of daily data."""
    daily = data.get("daily", {})
    today = datetime.now().date()
    total = 0
    for i in range(7):
        day = (today - timedelta(days=i)).isoformat()
        entry = daily.get(day, {})
        total += entry.get("input_tokens", 0) + entry.get("output_tokens", 0)
    return total
