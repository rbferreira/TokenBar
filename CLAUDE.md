# CLAUDE.md — TokenBar

## What is this?

TokenBar is a Windows taskbar widget that monitors Claude Code API token usage, rate limits, and session costs in real time. It sits on the taskbar as a compact, always-on-top overlay.

## Architecture

```
Claude Code  ──stdin──▶  statusline.py  ──writes──▶  token_data.json  ◀──reads──  tokenbar.py (GUI)
```

Two independent processes connected via a shared JSON file:

- **`statusline.py`** — Claude Code `statusLine` handler. Receives JSON on stdin after each turn, accumulates token/cost data into `token_data.json`, and outputs an ANSI-colored status line back to the terminal.
- **`tokenbar.py`** — Tkinter GUI widget. Polls `token_data.json` every 2s and renders metrics on the Windows taskbar. Uses Win32 API (`ctypes`) for taskbar positioning and z-order management.
- **`token_data.json`** — Shared state file with three sections: `session`, `daily` (rolling 30d), and `rate_limits`.

## Running

```bash
# Start the taskbar widget (windowless — recommended)
pythonw tokenbar.py

# Or with console for debugging
python tokenbar.py
```

The `statusline.py` script is **not run manually** — it's invoked by Claude Code via the `statusLine` config. Configure it in Claude Code settings:

```jsonc
// ~/.claude/settings.json
{
  "statusLine": "python C:/path/to/TokenBar/statusline.py"
}
```

## Dependencies

Python 3.10+ with standard library only (`tkinter`, `ctypes`, `json`). No pip packages required.

Optional: `pyinstaller` to package as `.exe`.

## Key details

- **Singleton**: `tokenbar.py` writes a PID file and kills previous instances on startup.
- **Topmost loop**: Win32 `SetWindowPos(HWND_TOPMOST)` every 500ms to stay above the taskbar.
- **Session reset detection**: `statusline.py` detects when token counters drop below 50% of previous values (new Claude Code session).
- **Daily accumulation**: Only deltas are added to daily counts to prevent double-counting. Entries older than 30 days are pruned.
- **Color coding**: Green (<50%), Orange (50-80%), Red (>=80%) for rate limit percentages.
- **UI language**: Portuguese (menu items, tooltip labels).

## Files

| File | Purpose |
|---|---|
| `tokenbar.py` | GUI widget (Tkinter + Win32) |
| `statusline.py` | Claude Code stdin handler + JSON writer |
| `token_data.json` | Persistent shared state (auto-generated) |
| `tokenbar.pid` | Singleton PID lock (auto-generated) |
| `tokenbar.log` | Debug log (auto-generated) |
| `requirements.txt` | Dependencies (stdlib only) |
