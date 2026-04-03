"""
config.py — Configuration with sensible defaults + optional config.json override.

Place a config.json next to this file to override any default value.
Only the keys you include will be overridden; the rest keep their defaults.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_DIR, "config.json")


@dataclass
class Theme:
    bg: str = "#1C1C1C"
    bg_tooltip: str = "#252525"
    fg_green: str = "#44BB44"
    fg_orange: str = "#FF8C00"
    fg_red: str = "#FF4444"
    fg_reset: str = "#7BAFD4"
    fg_cost: str = "#CC4444"
    fg_dim: str = "#666666"
    fg_muted: str = "#888888"
    fg_normal: str = "#D0D0D0"
    fg_separator: str = "#444444"

    def pct_color(self, pct: float) -> str:
        """Green / orange / red based on usage thresholds."""
        if pct >= 80:
            return self.fg_red
        if pct >= 50:
            return self.fg_orange
        return self.fg_green


@dataclass
class Config:
    # UI
    font_family: str = "Consolas"
    font_size: int = 10
    alpha: float = 0.95
    initial_x: int = 160

    # Timing (ms)
    refresh_ms: int = 2000
    topmost_ms: int = 500
    tooltip_hide_delay_ms: int = 80
    tooltip_gap: int = 4

    # Theme
    theme: Theme = field(default_factory=Theme)

    @property
    def font(self) -> tuple[str, int]:
        return (self.font_family, self.font_size)

    @property
    def font_bold(self) -> tuple[str, int, str]:
        return (self.font_family, self.font_size, "bold")


def _deep_merge(target: dict, source: dict) -> dict:
    """Merge source into target, recursing into nested dicts."""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def _apply_overrides(obj: Any, overrides: dict) -> None:
    """Apply dict overrides onto a dataclass instance."""
    field_names = {f.name for f in fields(obj)}
    for key, value in overrides.items():
        if key not in field_names:
            continue
        current = getattr(obj, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _apply_overrides(current, value)
        else:
            setattr(obj, key, value)


def load_config() -> Config:
    """Load config with defaults, overriding from config.json if present."""
    cfg = Config()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            _apply_overrides(cfg, overrides)
        except (json.JSONDecodeError, OSError):
            pass  # bad config file — use defaults silently
    return cfg
