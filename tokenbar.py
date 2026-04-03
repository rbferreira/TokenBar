"""
tokenbar.py — Windows taskbar token-usage widget for Claude Code.

Displays inside the taskbar (left side): session rate-limit %,
weekly rate-limit %, time until session reset, and session cost.

Hover:  tooltip with raw token counts and reset times.
Right-click: reset session / exit.
Left-click drag: reposition the window.

Usage:
    pythonw tokenbar.py        # windowless (recommended)
    python  tokenbar.py        # with console for debugging

Reads token_data.json (written by statusline.py) every refresh cycle.
"""
from __future__ import annotations

import logging
import os
import tkinter as tk
from datetime import datetime

from config import Config, load_config
from shared import (
    DATA_FILE,
    fmt_time_until,
    fmt_tokens,
    get_weekly_tokens,
    load_data,
    save_data,
)
from win32_utils import (
    cleanup_pid_file,
    ensure_singleton,
    get_screen_width,
    get_work_area,
    get_screen_height,
    set_topmost,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(_DIR, "tokenbar.log")
PID_FILE = os.path.join(_DIR, "tokenbar.pid")  # legacy — cleaned up on start

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("tokenbar")


# ── Tooltip ──────────────────────────────────────────────────────────────────

class Tooltip:
    """Hover tooltip that updates in-place without destroying/recreating widgets."""

    _ROWS = [
        "sessão desde:",
        "tokens sessão:",
        "tokens 7d:",
        "5h reset em:",
        "7d reset em:",
    ]

    def __init__(self, parent: tk.Tk, cfg: Config) -> None:
        self.cfg = cfg
        th = cfg.theme

        self.win = tk.Toplevel(parent)
        self.win.wm_overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        self.win.configure(bg=th.bg_tooltip)

        frame = tk.Frame(self.win, bg=th.bg_tooltip, padx=10, pady=7)
        frame.pack()

        self._value_labels: list[tk.Label] = []
        self._suffix_labels: list[tk.Label] = []

        for label_text in self._ROWS:
            row = tk.Frame(frame, bg=th.bg_tooltip)
            row.pack(fill=tk.X, pady=1)

            tk.Label(
                row, text=label_text, bg=th.bg_tooltip, fg=th.fg_dim,
                font=cfg.font, width=14, anchor="w",
            ).pack(side=tk.LEFT)

            val = tk.Label(
                row, text="—", bg=th.bg_tooltip, fg=th.fg_normal,
                font=cfg.font_bold, anchor="w",
            )
            val.pack(side=tk.LEFT)
            self._value_labels.append(val)

            suf = tk.Label(
                row, text="", bg=th.bg_tooltip, fg=th.fg_muted,
                font=cfg.font, anchor="w",
            )
            suf.pack(side=tk.LEFT)
            self._suffix_labels.append(suf)

    def update(self, data: dict) -> None:
        """Update tooltip values without recreating widgets."""
        rl = data.get("rate_limits", {})
        fh = rl.get("five_hour", {})
        sd = rl.get("seven_day", {})
        session = data.get("session", {})

        in_tok = session.get("input_tokens", 0) or 0
        out_tok = session.get("output_tokens", 0) or 0
        weekly = get_weekly_tokens(data)

        started_at = session.get("started_at")
        started_str = "—"
        if started_at:
            try:
                started_str = datetime.fromisoformat(started_at).strftime("%H:%M")
            except (ValueError, TypeError):
                pass

        values = [
            started_str,
            fmt_tokens(in_tok + out_tok),
            fmt_tokens(weekly),
            fmt_time_until(fh.get("resets_at")),
            fmt_time_until(sd.get("resets_at")),
        ]
        suffixes = [
            "",
            f"  ↑{fmt_tokens(in_tok)} ↓{fmt_tokens(out_tok)}",
            "",
            "",
            "",
        ]
        for lbl, val in zip(self._value_labels, values):
            lbl.config(text=val)
        for lbl, suf in zip(self._suffix_labels, suffixes):
            lbl.config(text=suf)

    def position(self, ref_x: int, ref_y: int) -> None:
        self.win.update_idletasks()
        tw = self.win.winfo_width()
        th = self.win.winfo_height()
        x = ref_x
        y = ref_y - th - self.cfg.tooltip_gap
        screen_w = get_screen_width()
        if x + tw > screen_w:
            x = screen_w - tw - 4
        self.win.geometry(f"+{x}+{y}")

    def destroy(self) -> None:
        self.win.destroy()


# ── Main widget ──────────────────────────────────────────────────────────────

class TokenBar:
    def __init__(self, cfg: Config | None = None) -> None:
        self.cfg = cfg or load_config()
        th = self.cfg.theme

        self.root = tk.Tk()
        self.root.wm_overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", self.cfg.alpha)
        self.root.configure(bg=th.bg)

        self._tooltip: Tooltip | None = None
        self._drag_start: tuple[int, int] = (0, 0)
        self._custom_pos: bool = False
        self._hwnd: int = 0

        self._build_ui()
        self.root.update()
        self._hwnd = self.root.winfo_id()
        self._position_window()
        self._loop_topmost()
        self._loop_refresh()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        th = self.cfg.theme

        self.frame = tk.Frame(self.root, bg=th.bg, padx=8, pady=4, cursor="fleur")
        self.frame.pack()

        self.lbl_5h = tk.Label(
            self.frame, text="—%", bg=th.bg, fg=th.fg_green,
            font=self.cfg.font_bold, anchor="w",
        )
        self.lbl_5h.pack(side=tk.LEFT)

        self._sep(self.frame)

        self.lbl_7d = tk.Label(
            self.frame, text="7d —%", bg=th.bg, fg=th.fg_green,
            font=self.cfg.font_bold, anchor="w",
        )
        self.lbl_7d.pack(side=tk.LEFT)

        self._sep(self.frame)

        self.lbl_reset = tk.Label(
            self.frame, text="—", bg=th.bg, fg=th.fg_reset,
            font=self.cfg.font, anchor="w",
        )
        self.lbl_reset.pack(side=tk.LEFT)

        self._sep(self.frame)

        self.lbl_cost = tk.Label(
            self.frame, text="$—", bg=th.bg, fg=th.fg_cost,
            font=self.cfg.font_bold, anchor="w",
        )
        self.lbl_cost.pack(side=tk.LEFT)

        # Bind events to all widgets
        for w in self.frame.winfo_children() + [self.frame]:
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-3>", self._show_menu)
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

    def _sep(self, parent: tk.Frame) -> None:
        tk.Label(
            parent, text=" | ", bg=self.cfg.theme.bg,
            fg=self.cfg.theme.fg_separator, font=self.cfg.font,
        ).pack(side=tk.LEFT)

    # ── Window positioning ───────────────────────────────────────────────────

    def _position_window(self) -> None:
        if self._custom_pos:
            return
        wa = get_work_area()
        screen_h = get_screen_height()
        taskbar_h = screen_h - wa.bottom
        h = self.root.winfo_height()
        x = self.cfg.initial_x
        y = wa.bottom + (taskbar_h - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _loop_topmost(self) -> None:
        """Periodically reassert z-order above the taskbar."""
        try:
            if self._hwnd:
                set_topmost(self._hwnd)
        except Exception:
            log.exception("_loop_topmost error")
        self.root.after(self.cfg.topmost_ms, self._loop_topmost)

    # ── Drag ─────────────────────────────────────────────────────────────────

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_start = (
            event.x_root - self.root.winfo_x(),
            event.y_root - self.root.winfo_y(),
        )

    def _on_drag(self, event: tk.Event) -> None:
        self._custom_pos = True
        dx, dy = self._drag_start
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    # ── Tooltip ──────────────────────────────────────────────────────────────

    def _on_enter(self, event: tk.Event | None = None) -> None:
        if self._tooltip:
            return
        data = load_data()
        self._tooltip = Tooltip(self.root, self.cfg)
        self._tooltip.update(data)
        self._tooltip.position(self.root.winfo_x(), self.root.winfo_y())

    def _on_leave(self, event: tk.Event | None = None) -> None:
        self.root.after(self.cfg.tooltip_hide_delay_ms, self._maybe_hide_tooltip)

    def _maybe_hide_tooltip(self) -> None:
        if self._tooltip is None:
            return
        try:
            px, py = self.root.winfo_pointerx(), self.root.winfo_pointery()

            # Still over main widget?
            wx, wy = self.root.winfo_rootx(), self.root.winfo_rooty()
            ww, wh = self.root.winfo_width(), self.root.winfo_height()
            if wx <= px <= wx + ww and wy <= py <= wy + wh:
                return

            # Still over tooltip?
            tw = self._tooltip.win
            tx, ty = tw.winfo_rootx(), tw.winfo_rooty()
            tww, twh = tw.winfo_width(), tw.winfo_height()
            if tx <= px <= tx + tww and ty <= py <= ty + twh + self.cfg.tooltip_gap:
                return
        except Exception:
            pass
        self._tooltip.destroy()
        self._tooltip = None

    def _hide_tooltip_now(self) -> None:
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None

    # ── Context menu ─────────────────────────────────────────────────────────

    def _show_menu(self, event: tk.Event) -> None:
        self._hide_tooltip_now()
        th = self.cfg.theme
        menu = tk.Menu(
            self.root, tearoff=0, bg="#2A2A2A", fg=th.fg_normal,
            activebackground="#3A3A3A", activeforeground="white",
            bd=0, relief=tk.FLAT,
        )
        menu.add_command(label="Zerar sessão", command=self._reset_session)
        menu.add_separator()
        menu.add_command(label="Sair", command=self._exit)
        menu.post(event.x_root, event.y_root)

    def _reset_session(self) -> None:
        try:
            data = load_data()
            data["session"] = {}
            save_data(data)
        except Exception:
            log.exception("session reset error")

    def _exit(self) -> None:
        self.root.destroy()

    # ── Refresh loop ─────────────────────────────────────────────────────────

    def _loop_refresh(self) -> None:
        try:
            data = load_data()
            rl = data.get("rate_limits", {})
            fh = rl.get("five_hour", {})
            sd = rl.get("seven_day", {})
            session = data.get("session", {})
            th = self.cfg.theme

            fh_pct = fh.get("used_pct") or 0.0
            sd_pct = sd.get("used_pct") or 0.0
            reset_ts = fh.get("resets_at")
            cost = session.get("cost_usd", 0.0) or 0.0

            self.lbl_5h.config(text=f"* {fh_pct:.0f}%", fg=th.pct_color(fh_pct))
            self.lbl_7d.config(text=f"7d {sd_pct:.0f}%", fg=th.pct_color(sd_pct))
            self.lbl_reset.config(text=fmt_time_until(reset_ts))
            self.lbl_cost.config(text=f"${cost:.4f}" if cost else "$—")

            # Update tooltip in-place if visible
            if self._tooltip:
                try:
                    self._tooltip.update(data)
                except Exception:
                    log.exception("tooltip refresh error")
                    self._hide_tooltip_now()

        except Exception:
            log.exception("_loop_refresh error")

        self.root.after(self.cfg.refresh_ms, self._loop_refresh)

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(self) -> None:
        log.info("TokenBar starting (pid=%s)", os.getpid())
        self.root.mainloop()
        log.info("TokenBar exiting")


if __name__ == "__main__":
    ensure_singleton()
    cleanup_pid_file(PID_FILE)  # remove legacy PID file if present
    TokenBar().run()
