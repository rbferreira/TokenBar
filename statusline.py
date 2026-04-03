"""
statusline.py — Claude Code statusLine handler.

Receives JSON on stdin from Claude Code after each turn,
accumulates token/cost data into token_data.json for TokenBar to display,
and outputs a formatted ANSI-colored status line for Claude Code's terminal.
"""
import sys
import json
import os
import time
from datetime import datetime, timedelta, date

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token_data.json")

# ANSI colors
_CY  = "\033[36m"        # cyan  — directory
_YL  = "\033[33m"        # yellow — model
_GR  = "\033[32m"        # green — rate limit used%
_BL  = "\033[94m"        # blue — reset time
_MG  = "\033[38;5;208m"  # orange — token counts
_RD  = "\033[31m"        # red — cost
_RST = "\033[0m"


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"session": {}, "daily": {}, "rate_limits": {}}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fmt(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_k(n):
    if n is None:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    raw = sys.stdin.read().strip()
    if not raw:
        return

    try:
        payload = json.loads(raw)
    except Exception:
        return

    # Extract fields from Claude Code payload
    cwd   = payload.get("workspace", {}).get("current_dir") or payload.get("cwd", "")
    model = payload.get("model", {}).get("display_name", "")

    ctx          = payload.get("context_window", {})
    total_input  = ctx.get("total_input_tokens") or 0
    total_output = ctx.get("total_output_tokens") or 0

    cost_data  = payload.get("cost", {})
    total_cost = cost_data.get("total_cost_usd") or 0.0

    rate_limits_raw = payload.get("rate_limits", {})

    # ── Accumulate into token_data.json ──────────────────────────────────────
    data         = load_data()
    prev_session = data.get("session", {})
    prev_input   = prev_session.get("input_tokens", 0)
    prev_output  = prev_session.get("output_tokens", 0)

    # Detect session reset: counters dropped to less than half the previous value
    new_session = (total_input + total_output) < (prev_input + prev_output) * 0.5

    started_at = (
        datetime.now().isoformat()
        if new_session
        else prev_session.get("started_at", datetime.now().isoformat())
    )

    data["session"] = {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cost_usd": total_cost,
        "started_at": started_at,
    }

    # Accumulate daily delta (avoid double-counting — only add increases)
    today       = date.today().isoformat()
    daily       = data.setdefault("daily", {})
    today_entry = daily.setdefault(today, {"input_tokens": 0, "output_tokens": 0})

    if not new_session:
        today_entry["input_tokens"]  += max(0, total_input  - prev_input)
        today_entry["output_tokens"] += max(0, total_output - prev_output)
    else:
        today_entry["input_tokens"]  += total_input
        today_entry["output_tokens"] += total_output

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

    # Prune daily entries older than 30 days
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    data["daily"]        = {k: v for k, v in daily.items() if k >= cutoff}
    data["last_updated"] = datetime.now().isoformat()

    save_data(data)

    # ── Build ANSI-colored terminal status line ───────────────────────────────
    rl        = rate_limits_raw.get("five_hour", {})
    used_pct  = rl.get("used_percentage")
    resets_at = rl.get("resets_at")

    parts = []
    if cwd:
        parts.append(f"{_CY}{cwd}{_RST}")
    if model:
        parts.append(f"{_YL}{model}{_RST}")
    if used_pct is not None:
        parts.append(f"{_GR}{used_pct:.0f}% usado{_RST}")
    if resets_at is not None:
        secs = int(resets_at) - int(time.time())
        if secs > 0:
            h = secs // 3600
            m = (secs % 3600) // 60
            t = f"reset em {h}h{m:02d}m" if h > 0 else f"reset em {m}m"
            parts.append(f"{_BL}{t}{_RST}")
    if total_input or total_output:
        parts.append(f"{_MG}\u2191{fmt_k(total_input)} \u2193{fmt_k(total_output)}{_RST}")
    if total_cost:
        parts.append(f"{_RD}${total_cost:.4f}{_RST}")

    print("  ".join(parts), end="")


if __name__ == "__main__":
    main()
