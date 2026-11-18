"""HD quality settings: a preset (or custom values) for how much HD may
build and hold, within a hard 4 GB.

Stored in ~/.visage/hd_settings.json.  The memory limit covers all of HD:
its one-off setup, the cache of recent builds and the models on screen.
"""

from __future__ import annotations

import json
from pathlib import Path

_FILE = Path.home() / ".visage" / "hd_settings.json"

# Nothing HD holds may reach this (MB); Crazy comes closest.
LIMIT_MB = 4000
# HD's one-off cost on first use (shaders, buffers), measured in the
# viewer 2026-11-09.
SETUP_MB = 150
# The cache of recent builds takes this share of what is left.
CACHE_SHARE = 0.2

QUALITIES = ("lite", "group", "full")
# HD's render resolution on a high-DPI (Retina) screen: every screen pixel
# ("retina"), or one per point of the page ("standard": a quarter of the
# pixels at 2x, the same on an ordinary screen).
RENDERS = ("standard", "retina")
PRESETS = {
    "low": {
        "quality": "lite",
        "memory_mb": 1000,
        "max_models": 30,
        "render": "standard",
    },
    "medium": {
        "quality": "group",
        "memory_mb": 1750,
        "max_models": 60,
        "render": "standard",
    },
    "high": {
        "quality": "full",
        "memory_mb": 2500,
        "max_models": 100,
        "render": "retina",
    },
    "crazy": {
        "quality": "full",
        "memory_mb": 2900,
        "max_models": 100,
        "render": "retina",
    },
}
DEFAULT = "medium"


def _clean(s: dict) -> dict:
    """Valid values only, the memory under LIMIT_MB."""
    base = PRESETS[DEFAULT]
    q = s.get("quality") if s.get("quality") in QUALITIES else base["quality"]
    r = s.get("render") if s.get("render") in RENDERS else base["render"]
    try:
        mem = int(s.get("memory_mb", base["memory_mb"]))
        n = int(s.get("max_models", base["max_models"]))
    except (TypeError, ValueError):
        mem, n = base["memory_mb"], base["max_models"]
    preset = s.get("preset")
    if preset not in PRESETS and preset != "custom":
        preset = DEFAULT
    return {
        "preset": preset,
        "quality": q,
        "memory_mb": max(
            SETUP_MB + 200, min(mem, PRESETS["crazy"]["memory_mb"])
        ),
        "max_models": max(1, min(n, 100)),
        "render": r,
    }


def load() -> dict:
    try:
        return _clean(json.loads(_FILE.read_text()))
    except (OSError, ValueError, AttributeError):
        return _clean({"preset": DEFAULT, **PRESETS[DEFAULT]})


def save(s: dict) -> dict:
    s = _clean(s)
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(s, indent=2))
    except OSError:
        pass
    return s


def from_preset(name: str) -> dict:
    return _clean({"preset": name, **PRESETS[name]})


def split(s: dict) -> tuple[int, int]:
    """(MB for the models on screen, MB for the build cache)."""
    rest = s["memory_mb"] - SETUP_MB
    cache = int(rest * CACHE_SHARE)
    return rest - cache, cache
