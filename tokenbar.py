"""
tokenbar.py — Windows taskbar token usage widget for Claude Code.

Displays inside the taskbar (left side): session rate limit %, weekly rate
limit %, time until session reset, and session cost.

Hover: tooltip with raw token counts and reset times.
Right-click: reset session / exit.
Left-click drag: reposition the window.

Usage:
    pythonw tokenbar.py

Reads token_data.json (written by statusline.py) every 2 seconds.
"""
import tkinter as tk
import json
import os
import logging
import ctypes
import ctypes.wintypes
from datetime import datetime, timedelta

_DIR     = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(_DIR, "tokenbar.log")
PID_FILE = os.path.join(_DIR, "tokenbar.pid")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("tokenbar")

DATA_FILE = os.path.join(_DIR, "token_data.json")

# ── Win32 constants ───────────────────────────────────────────────────────────
HWND_TOPMOST    = -1
SWP_NOMOVE      = 0x0002
SWP_NOSIZE      = 0x0001
SWP_NOACTIVATE  = 0x0010
PROCESS_TERMINATE = 0x0001

BG          = "#1C1C1C"
BG_TOOLTIP  = "#252525"
FG_GREEN    = "#44BB44"
FG_ORANGE   = "#FF8C00"
FG_RED      = "#FF4444"
FG_RESET    = "#7BAFD4"
FG_COST     = "#CC4444"
FG_DIM      = "#666666"
FG_MUTED    = "#888888"
FG_NORMAL   = "#D0D0D0"
FONT        = ("Consolas", 10)
FONT_BOLD   = ("Consolas", 10, "bold")
REFRESH_MS  = 2000
TOPMOST_MS  = 500   # how often to re-assert z-order above taskbar
TOOLTIP_GAP = 4


# ── Singleton ─────────────────────────────────────────────────────────────────

def _kill_pid(pid: int):
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if h:
        ctypes.windll.kernel32.TerminateProcess(h, 0)
        ctypes.windll.kernel32.CloseHandle(h)


def ensure_singleton():
    """Kill any previous tokenbar instance, then register this PID."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid():
                _kill_pid(old_pid)
                log.info("Killed previous instance pid=%s", old_pid)
        except Exception:
            log.exception("Could not kill previous instance")
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


# ── Win32 helpers ─────────────────────────────────────────────────────────────

def get_work_area() -> ctypes.wintypes.RECT:
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    return rect


def get_screen_height() -> int:
    return ctypes.windll.user32.GetSystemMetrics(1)


def win32_set_topmost(hwnd: int):
    """Force window above taskbar using Win32 SetWindowPos (stronger than tkinter -topmost)."""
    ctypes.windll.user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
    )


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_data() -> dict:
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"session": {}, "daily": {}, "rate_limits": {}}


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n) if n else "—"


def fmt_time_until(timestamp) -> str:
    if not timestamp:
        return "—"
    try:
        delta = datetime.fromtimestamp(timestamp) - datetime.now()
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
    except Exception:
        return "—"


def pct_color(pct: float) -> str:
    if pct >= 80:
        return FG_RED
    if pct >= 50:
        return FG_ORANGE
    return FG_GREEN


def get_weekly_tokens(data: dict) -> int:
    daily = data.get("daily", {})
    today = datetime.now().date()
    total = 0
    for i in range(7):
        day   = (today - timedelta(days=i)).isoformat()
        entry = daily.get(day, {})
        total += entry.get("input_tokens", 0) + entry.get("output_tokens", 0)
    return total


# ── Tooltip ───────────────────────────────────────────────────────────────────

class Tooltip:
    def __init__(self, parent: tk.Tk, data: dict):
        self.win = tk.Toplevel(parent)
        self.win.wm_overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        self.win.configure(bg=BG_TOOLTIP)

        rl      = data.get("rate_limits", {})
        fh      = rl.get("five_hour", {})
        sd      = rl.get("seven_day", {})
        session = data.get("session", {})
        cost    = session.get("cost_usd", 0.0) or 0.0
        in_tok  = session.get("input_tokens", 0) or 0
        out_tok = session.get("output_tokens", 0) or 0
        weekly  = get_weekly_tokens(data)

        started_at  = session.get("started_at")
        started_str = "—"
        if started_at:
            try:
                started_str = datetime.fromisoformat(started_at).strftime("%H:%M")
            except Exception:
                pass

        rows = [
            ("sessão desde:", started_str,                    ""),
            ("tokens sessão:", fmt_tokens(in_tok + out_tok),  f"↑{fmt_tokens(in_tok)} ↓{fmt_tokens(out_tok)}"),
            ("tokens 7d:",    fmt_tokens(weekly),             ""),
            ("5h reset em:",  fmt_time_until(fh.get("resets_at")), ""),
            ("7d reset em:",  fmt_time_until(sd.get("resets_at")), ""),
        ]

        frame = tk.Frame(self.win, bg=BG_TOOLTIP, padx=10, pady=7)
        frame.pack()

        for label, value, suffix in rows:
            row = tk.Frame(frame, bg=BG_TOOLTIP)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label, bg=BG_TOOLTIP, fg=FG_DIM,    font=FONT,      width=14, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=value, bg=BG_TOOLTIP, fg=FG_NORMAL, font=FONT_BOLD,           anchor="w").pack(side=tk.LEFT)
            if suffix:
                tk.Label(row, text=f"  {suffix}", bg=BG_TOOLTIP, fg=FG_MUTED, font=FONT, anchor="w").pack(side=tk.LEFT)

    def position(self, ref_x: int, ref_y: int, ref_w: int):
        self.win.update_idletasks()
        tw = self.win.winfo_width()
        th = self.win.winfo_height()
        x  = ref_x
        y  = ref_y - th - TOOLTIP_GAP
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        if x + tw > screen_w:
            x = screen_w - tw - 4
        self.win.geometry(f"+{x}+{y}")

    def destroy(self):
        self.win.destroy()


# ── Main widget ───────────────────────────────────────────────────────────────

class TokenBar:
    def __init__(self):
        self.root = tk.Tk()
        self.root.wm_overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.95)
        self.root.configure(bg=BG)

        self._tooltip: Tooltip | None = None
        self._drag_start = (0, 0)
        self._custom_pos = False
        self._hwnd: int  = 0

        self._build_ui()
        self.root.update()
        self._hwnd = self.root.winfo_id()
        self._position_window()
        self._assert_topmost()  # start the topmost loop
        self._refresh()

    def _build_ui(self):
        self.frame = tk.Frame(self.root, bg=BG, padx=8, pady=4, cursor="fleur")
        self.frame.pack()

        self.lbl_5h = tk.Label(self.frame, text="—%", bg=BG, fg=FG_GREEN, font=FONT_BOLD, anchor="w")
        self.lbl_5h.pack(side=tk.LEFT)

        tk.Label(self.frame, text=" | ", bg=BG, fg="#444", font=FONT).pack(side=tk.LEFT)

        self.lbl_7d = tk.Label(self.frame, text="7d —%", bg=BG, fg=FG_GREEN, font=FONT_BOLD, anchor="w")
        self.lbl_7d.pack(side=tk.LEFT)

        tk.Label(self.frame, text=" | ", bg=BG, fg="#444", font=FONT).pack(side=tk.LEFT)

        self.lbl_reset = tk.Label(self.frame, text="—", bg=BG, fg=FG_RESET, font=FONT, anchor="w")
        self.lbl_reset.pack(side=tk.LEFT)

        tk.Label(self.frame, text=" | ", bg=BG, fg="#444", font=FONT).pack(side=tk.LEFT)

        self.lbl_cost = tk.Label(self.frame, text="$—", bg=BG, fg=FG_COST, font=FONT_BOLD, anchor="w")
        self.lbl_cost.pack(side=tk.LEFT)

        for w in self.frame.winfo_children() + [self.frame]:
            w.bind("<Enter>",     self._on_enter)
            w.bind("<Leave>",     self._on_leave)
            w.bind("<Button-3>",  self._show_menu)
            w.bind("<Button-1>",  self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

    def _assert_topmost(self):
        """Periodically call Win32 SetWindowPos to stay above the taskbar."""
        try:
            if self._hwnd:
                win32_set_topmost(self._hwnd)
        except Exception:
            log.exception("_assert_topmost error")
        self.root.after(TOPMOST_MS, self._assert_topmost)

    def _position_window(self):
        if self._custom_pos:
            return
        wa        = get_work_area()
        screen_h  = get_screen_height()
        taskbar_h = screen_h - wa.bottom
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = 160
        y = wa.bottom + (taskbar_h - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _start_drag(self, event):
        self._drag_start = (event.x_root - self.root.winfo_x(),
                            event.y_root - self.root.winfo_y())

    def _on_drag(self, event):
        self._custom_pos = True
        dx, dy = self._drag_start
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _on_enter(self, event=None):
        if self._tooltip:
            return
        data = load_data()
        self._tooltip = Tooltip(self.root, data)
        self._tooltip.position(
            self.root.winfo_x(),
            self.root.winfo_y(),
            self.root.winfo_width(),
        )

    def _on_leave(self, event=None):
        self.root.after(80, self._maybe_hide_tooltip)

    def _maybe_hide_tooltip(self):
        if self._tooltip is None:
            return
        try:
            px = self.root.winfo_pointerx()
            py = self.root.winfo_pointery()

            wx, wy = self.root.winfo_rootx(), self.root.winfo_rooty()
            ww, wh = self.root.winfo_width(), self.root.winfo_height()
            if wx <= px <= wx + ww and wy <= py <= wy + wh:
                return

            tw = self._tooltip.win
            tx, ty   = tw.winfo_rootx(), tw.winfo_rooty()
            tww, twh = tw.winfo_width(), tw.winfo_height()
            if tx <= px <= tx + tww and ty <= py <= ty + twh + TOOLTIP_GAP:
                return
        except Exception:
            pass
        self._tooltip.destroy()
        self._tooltip = None

    def _show_menu(self, event):
        self._hide_tooltip_now()
        menu = tk.Menu(self.root, tearoff=0, bg="#2A2A2A", fg=FG_NORMAL,
                       activebackground="#3A3A3A", activeforeground="white",
                       bd=0, relief=tk.FLAT)
        menu.add_command(label="Zerar sessão", command=self._reset_session)
        menu.add_separator()
        menu.add_command(label="Sair", command=self._exit)
        menu.post(event.x_root, event.y_root)

    def _hide_tooltip_now(self):
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None

    def _reset_session(self):
        try:
            data = load_data()
            data["session"] = {}
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _exit(self):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
        self.root.destroy()

    def _refresh(self):
        try:
            data    = load_data()
            rl      = data.get("rate_limits", {})
            fh      = rl.get("five_hour", {})
            sd      = rl.get("seven_day", {})
            session = data.get("session", {})

            fh_pct   = fh.get("used_pct") or 0.0
            sd_pct   = sd.get("used_pct") or 0.0
            reset_ts = fh.get("resets_at")
            cost     = session.get("cost_usd", 0.0) or 0.0

            self.lbl_5h.config(   text=f"* {fh_pct:.0f}%",          fg=pct_color(fh_pct))
            self.lbl_7d.config(   text=f"7d {sd_pct:.0f}%",         fg=pct_color(sd_pct))
            self.lbl_reset.config(text=fmt_time_until(reset_ts),     fg=FG_RESET)
            self.lbl_cost.config( text=f"${cost:.4f}" if cost else "$—", fg=FG_COST)

            if self._tooltip:
                try:
                    self._tooltip.destroy()
                    self._tooltip = Tooltip(self.root, data)
                    self._tooltip.position(
                        self.root.winfo_x(),
                        self.root.winfo_y(),
                        self.root.winfo_width(),
                    )
                except Exception:
                    log.exception("tooltip refresh error")
                    self._tooltip = None

        except Exception:
            log.exception("_refresh error")

        self.root.after(REFRESH_MS, self._refresh)

    def run(self):
        log.info("TokenBar starting (pid=%s)", os.getpid())
        self.root.mainloop()
        log.info("TokenBar exiting")


if __name__ == "__main__":
    ensure_singleton()
    TokenBar().run()
