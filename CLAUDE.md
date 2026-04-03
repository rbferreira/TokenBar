# CLAUDE.md — TokenBar

## What is this?

TokenBar is a Windows taskbar widget that monitors Claude Code API token usage, rate limits, and session costs in real time. It sits on the taskbar as a compact, always-on-top overlay.

## Architecture

```
Claude Code  ──stdin──▶  statusline.py  ──writes──▶  token_data.json  ◀──reads──  tokenbar.py (GUI)
```

Two independent processes connected via a shared JSON file (atomic writes via `os.replace`).

### Module structure

| Module | Responsibility |
|---|---|
| `shared.py` | Atomic file I/O, token formatting, weekly aggregation, data schema |
| `config.py` | Configuration dataclass + optional `config.json` override |
| `win32_utils.py` | Win32 API (screen geometry, z-order, singleton mutex) |
| `tokenbar.py` | Tkinter GUI — TokenBar + Tooltip classes |
| `statusline.py` | Claude Code stdin handler — accumulates data + ANSI output |

### Key design decisions

- **Atomic writes**: `save_data()` writes to a `.tmp` file then `os.replace()` to avoid read-during-write corruption.
- **Singleton via named mutex**: `CreateMutexW("Global\\TokenBar_Singleton_Mutex")` — the standard Windows single-instance pattern. Replaces the old PID-file + `TerminateProcess` approach.
- **Tooltip updates in-place**: `Tooltip.update(data)` changes label text without destroying/recreating widgets (no flicker).
- **Config is a dataclass**: `Config` + `Theme` with defaults. Override via `config.json` next to the scripts.
- **Session reset detection**: heuristic — new totals < 50% of previous totals means Claude Code restarted.

## Running

```bash
# Start the taskbar widget (windowless — recommended)
pythonw tokenbar.py

# Or with console for debugging
python tokenbar.py
```

The `statusline.py` script is **not run manually** — it's invoked by Claude Code via the `statusLine` config:

```jsonc
// ~/.claude/settings.json
{
  "statusLine": "python C:/path/to/TokenBar/statusline.py"
}
```

## Configuration

Create an optional `config.json` next to the scripts to override defaults:

```json
{
  "font_family": "JetBrains Mono",
  "font_size": 11,
  "refresh_ms": 3000,
  "initial_x": 200,
  "theme": {
    "bg": "#1E1E2E",
    "fg_green": "#A6E3A1"
  }
}
```

Only include keys you want to change — the rest keep their defaults.

## Dependencies

Python 3.10+ with standard library only (`tkinter`, `ctypes`, `json`, `dataclasses`). No pip packages required.

Optional: `pyinstaller` to package as `.exe`.

## Files

| File | Purpose |
|---|---|
| `shared.py` | Shared utilities (I/O, formatting, schema) |
| `config.py` | Configuration with defaults + config.json loader |
| `win32_utils.py` | Win32 API helpers + singleton mutex |
| `tokenbar.py` | GUI widget (Tkinter) |
| `statusline.py` | Claude Code stdin handler |
| `pyproject.toml` | Package metadata + build config |
| `config.json` | User overrides (optional, not tracked in git) |
| `token_data.json` | Persistent shared state (auto-generated) |
| `tokenbar.log` | Debug log (auto-generated) |
