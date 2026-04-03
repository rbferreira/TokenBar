"""
statusline.py — Claude Code statusLine handler.

Receives JSON on stdin from Claude Code after each turn,
accumulates token/cost data into token_data.json for TokenBar to display,
and outputs a formatted ANSI-colored status line for Claude Code's terminal.

Claude Code config (~/.claude/settings.json):
    { "statusLine": "python /path/to/TokenBar/statusline.py" }
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta

from shared import DATA_FILE, fmt_tokens, load_data, save_data

# ANSI escape codes
_CY = "\033[36m"         # cyan   — directory
_YL = "\033[33m"         # yellow — model
_GR = "\033[32m"         # green  — rate-limit used %
_BL = "\033[94m"         # blue   — reset time
_MG = "\033[38;5;208m"   # orange — token counts
_RD = "\033[31m"         # red    — cost
_RST = "\033[0m"


def _detect_new_session(
    total_input: int,
    total_output: int,
    prev_session: dict,
) -> bool:
    """Detect whether Claude Code started a fresh session.

    Heuristic: the new totals are significantly lower than previous totals.
    This happens because Claude Code resets its counters on a new session.
    We also treat it as new if there's no previous session data.
    """
    prev_input = prev_session.get("input_tokens", 0)
    prev_output = prev_session.get("output_tokens", 0)
    prev_total = prev_input + prev_output
    if prev_total == 0:
        return False
    return (total_input + total_output) < prev_total * 0.5


def _accumulate_daily(
    daily: dict,
    today_key: str,
    total_input: int,
    total_output: int,
    prev_input: int,
    prev_output: int,
    is_new_session: bool,
) -> None:
    """Add token deltas to today's daily entry (avoids double-counting)."""
    entry = daily.setdefault(today_key, {"input_tokens": 0, "output_tokens": 0})
    if is_new_session:
        entry["input_tokens"] += total_input
        entry["output_tokens"] += total_output
    else:
        entry["input_tokens"] += max(0, total_input - prev_input)
        entry["output_tokens"] += max(0, total_output - prev_output)


def _prune_old_entries(daily: dict, max_age_days: int = 30) -> dict:
    """Remove daily entries older than max_age_days."""
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    return {k: v for k, v in daily.items() if k >= cutoff}


def _build_status_line(
    cwd: str,
    model: str,
    used_pct: float | None,
    resets_at: int | None,
    total_input: int,
    total_output: int,
    total_cost: float,
) -> str:
    """Build ANSI-colored terminal status line."""
    parts: list[str] = []
    if cwd:
        parts.append(f"{_CY}{cwd}{_RST}")
    if model:
        parts.append(f"{_YL}{model}{_RST}")
    if used_pct is not None:
        parts.append(f"{_GR}{used_pct:.0f}% usado{_RST}")
    if resets_at is not None:
        secs = int(resets_at) - int(time.time())
        if secs > 0:
            h, rem = divmod(secs, 3600)
            m = rem // 60
            t = f"reset em {h}h{m:02d}m" if h > 0 else f"reset em {m}m"
            parts.append(f"{_BL}{t}{_RST}")
    if total_input or total_output:
        parts.append(f"{_MG}↑{fmt_tokens(total_input)} ↓{fmt_tokens(total_output)}{_RST}")
    if total_cost:
        parts.append(f"{_RD}${total_cost:.4f}{_RST}")
    return "  ".join(parts)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    raw = sys.stdin.read().strip()
    if not raw:
        return

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    # ── Extract fields from Claude Code payload ──────────────────────────────
    cwd = payload.get("workspace", {}).get("current_dir") or payload.get("cwd", "")
    model = payload.get("model", {}).get("display_name", "")

    ctx = payload.get("context_window", {})
    total_input: int = ctx.get("total_input_tokens") or 0
    total_output: int = ctx.get("total_output_tokens") or 0

    cost_data = payload.get("cost", {})
    total_cost: float = cost_data.get("total_cost_usd") or 0.0

    rate_limits_raw: dict = payload.get("rate_limits", {})

    # ── Accumulate into token_data.json ──────────────────────────────────────
    data = load_data()
    prev_session = data.get("session", {})

    is_new_session = _detect_new_session(total_input, total_output, prev_session)

    data["session"] = {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cost_usd": total_cost,
        "started_at": (
            datetime.now().isoformat()
            if is_new_session
            else prev_session.get("started_at", datetime.now().isoformat())
        ),
    }

    daily = data.setdefault("daily", {})
    _accumulate_daily(
        daily,
        today_key=date.today().isoformat(),
        total_input=total_input,
        total_output=total_output,
        prev_input=prev_session.get("input_tokens", 0),
        prev_output=prev_session.get("output_tokens", 0),
        is_new_session=is_new_session,
    )

    # Update rate limits
    if rate_limits_raw:
        fh = rate_limits_raw.get("five_hour", {})
        sd = rate_limits_raw.get("seven_day", {})
        data["rate_limits"] = {
            "five_hour": {
                "used_pct": fh.get("used_percentage", 0),
                "resets_at": fh.get("resets_at"),
            },
            "seven_day": {
                "used_pct": sd.get("used_percentage", 0),
                "resets_at": sd.get("resets_at"),
            },
        }

    data["daily"] = _prune_old_entries(daily)

    save_data(data)  # atomic write

    # ── Terminal output ──────────────────────────────────────────────────────
    rl = rate_limits_raw.get("five_hour", {})
    print(
        _build_status_line(
            cwd=cwd,
            model=model,
            used_pct=rl.get("used_percentage"),
            resets_at=rl.get("resets_at"),
            total_input=total_input,
            total_output=total_output,
            total_cost=total_cost,
        ),
        end="",
    )


if __name__ == "__main__":
    main()
