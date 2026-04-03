# TokenBar

A Windows taskbar widget that displays real-time Claude Code token usage, rate limits, and session costs.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

## What it does

TokenBar embeds a compact overlay on your Windows taskbar showing:

| Metric | Example | Description |
|---|---|---|
| **5h rate limit** | `* 42%` | Current 5-hour window usage |
| **7d rate limit** | `7d 17%` | Rolling 7-day window usage |
| **Reset timer** | `3h22m` | Time until 5-hour limit resets |
| **Session cost** | `$0.2381` | Cumulative cost of current session |

**Hover** for a detailed tooltip with token breakdowns, session start time, and reset times.
**Right-click** to reset session counters or exit.
**Drag** to reposition the widget on the taskbar.

### Color coding

- **Green** — under 50% usage
- **Orange** — 50-80% usage
- **Red** — 80%+ usage

## How it works

```
Claude Code  ──stdin──▶  statusline.py  ──writes──▶  token_data.json  ◀──reads──  tokenbar.py
```

1. **`statusline.py`** is configured as Claude Code's `statusLine` handler. After each turn, Claude Code pipes turn metadata (tokens, cost, rate limits) to it via stdin. It accumulates the data into `token_data.json` (atomic writes) and prints an ANSI status line back to the terminal.

2. **`tokenbar.py`** is a standalone Tkinter GUI that polls `token_data.json` every 2 seconds and renders the metrics as a frameless, always-on-top window positioned on the Windows taskbar.

## Project structure

```
TokenBar/
├── shared.py          # Atomic I/O, formatting, data schema
├── config.py          # Configuration dataclass + config.json loader
├── win32_utils.py     # Win32 API helpers + singleton mutex
├── tokenbar.py        # GUI widget (Tkinter)
├── statusline.py      # Claude Code stdin handler
├── pyproject.toml     # Package metadata
├── config.json        # User overrides (optional)
└── LICENSE
```

## Requirements

- **Windows 10/11**
- **Python 3.10+** (standard library only — no pip packages needed)
- **Claude Code** CLI

## Setup

### 1. Configure Claude Code status line

Add to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "statusLine": "python C:/full/path/to/TokenBar/statusline.py"
}
```

This tells Claude Code to pipe turn data to `statusline.py` after each interaction.

### 2. Start the taskbar widget

```bash
# Windowless mode (recommended — no console window)
pythonw tokenbar.py

# With console for debugging
python tokenbar.py
```

The widget will appear on the left side of your taskbar. It auto-updates every 2 seconds.

## Configuration

Create a `config.json` next to the scripts to customize appearance and behavior:

```json
{
  "font_family": "JetBrains Mono",
  "font_size": 11,
  "alpha": 0.90,
  "refresh_ms": 3000,
  "initial_x": 200,
  "theme": {
    "bg": "#1E1E2E",
    "fg_green": "#A6E3A1",
    "fg_orange": "#FAB387",
    "fg_red": "#F38BA8"
  }
}
```

Only include keys you want to override. See `config.py` for all available options.

### Optional: auto-start on login

Create a shortcut to `pythonw.exe tokenbar.py` in your Startup folder:

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

### Optional: package as .exe

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole tokenbar.py
```

## Data format

`token_data.json` (auto-generated, shared between both scripts):

```json
{
  "session": {
    "input_tokens": 15420,
    "output_tokens": 8230,
    "cost_usd": 1.2345,
    "started_at": "2026-04-02T14:30:00.000000"
  },
  "daily": {
    "2026-04-02": { "input_tokens": 50000, "output_tokens": 25000 }
  },
  "rate_limits": {
    "five_hour": { "used_pct": 42, "resets_at": 1775196000 },
    "seven_day": { "used_pct": 17, "resets_at": 1775484000 }
  },
  "last_updated": "2026-04-02T22:37:36.552490"
}
```

## License

[MIT](LICENSE)
