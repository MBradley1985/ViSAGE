"""A small persisted registry of recently-loaded models (boxes + lightcones).

Lets the Launch-mode dropdown list every model loaded this session so the user
can jump back to any of them (each re-opens by relaunching ViSAGE on it).
Stored in ~/.visage/session_models.json, most-recent first, capped.
"""

from __future__ import annotations

import json
from pathlib import Path

_REGISTRY = Path.home() / ".visage" / "session_models.json"
_CAP = 12


def _load_raw() -> list[dict]:
    try:
        data = json.loads(_REGISTRY.read_text())
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(entries: list[dict]) -> None:
    try:
        _REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        _REGISTRY.write_text(json.dumps(entries, indent=2))
    except OSError:
        pass


def _prune(entries: list[dict]) -> list[dict]:
    """Drop entries whose file no longer exists — a path can go stale (moved,
    deleted, or a throwaway test file from outside a normal session) and
    there's otherwise nothing that ever removes it."""
    return [e for e in entries if Path(e.get("path", "")).is_file()]


def record(name: str, kind: str, path: str) -> list[dict]:
    """Promote (name, kind, path) to most-recent and return the updated list.

    kind is 'box' or 'lightcone'.  Entries are de-duplicated by (kind, path).
    """
    p = str(Path(path).expanduser())
    entries = [
        e
        for e in _prune(_load_raw())
        if not (e.get("kind") == kind and e.get("path") == p)
    ]
    entries.insert(0, {"name": str(name), "kind": str(kind), "path": p})
    entries = entries[:_CAP]
    _save(entries)
    return entries


def load() -> list[dict]:
    """Return the stored entries (most-recent first), pruning any that no
    longer exist on disk (and persisting that cleanup)."""
    entries = _load_raw()
    pruned = _prune(entries)
    if len(pruned) != len(entries):
        _save(pruned)
    return pruned
