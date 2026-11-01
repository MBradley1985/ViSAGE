"""Regions of a run: spheres, boxes, slices and selections.

A region is a plain dict, so it can be saved and handed to a plot job:

    {"kind": "sphere", "centre": [x, y, z], "radius": r}
    {"kind": "box", "lo": [x, y, z], "hi": [x, y, z]}
    {"kind": "slice", "point": [x, y, z], "normal": [x, y, z],
     "thickness": t}
    {"kind": "selection", "ids": [...]}

Coordinates are Mpc/h. A periodic run gives `box_size`, and a region then
wraps around the edges. A selection holds galaxies by `identity`, so a box's
follow their GalaxyIndex through snapshots.

Saved regions live in ~/.visage/regions.json, by model.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

_SAVED = Path.home() / ".visage" / "regions.json"


def identity(galaxies) -> np.ndarray:
    """What a selection holds a snapshot's galaxies by: GalaxyIndex, or a
    lightcone's rows, where the same GalaxyIndex can appear in several
    tiles."""
    if galaxies.is_cone:
        return np.asarray(galaxies.sage_indices)
    return np.asarray(galaxies.galaxy_id)


def _nearest(d: np.ndarray, box_size: float | None) -> np.ndarray:
    """Separations `d` by their nearest periodic image."""
    return d if not box_size else d - box_size * np.round(d / box_size)


def mask(region, pos, box_size=None, ids=None) -> np.ndarray:
    """Which of positions `pos` (N, 3) are in `region`; a selection goes by
    `ids`, the galaxies' `identity`."""
    pos = np.asarray(pos, float)
    kind = region["kind"]
    if kind == "selection":
        if ids is None:
            return np.zeros(len(pos), bool)
        return np.isin(ids, region["ids"])
    if len(pos) == 0:
        return np.zeros(0, bool)
    if kind == "sphere":
        d = _nearest(pos - np.array(region["centre"]), box_size)
        return np.sum(d**2, axis=1) <= region["radius"] ** 2
    if kind == "box":
        lo, hi = np.array(region["lo"]), np.array(region["hi"])
        d = _nearest(pos - 0.5 * (lo + hi), box_size)
        return np.all(np.abs(d) <= 0.5 * (hi - lo), axis=1)
    d = _nearest(pos - np.array(region["point"]), box_size)
    along = np.sum(d * np.array(region["normal"]), axis=1)
    return np.abs(along) <= 0.5 * region["thickness"]


def volume(region, box_size=None) -> float | None:
    """(Mpc/h)^3, or None where it has no volume of its own: a selection,
    and a slice not cut straight through a periodic box."""
    kind = region["kind"]
    if kind == "sphere":
        return 4.0 / 3.0 * math.pi * region["radius"] ** 3
    if kind == "box":
        return float(np.prod(np.subtract(region["hi"], region["lo"])))
    if kind == "slice" and box_size and max(np.abs(region["normal"])) > 0.999:
        return region["thickness"] * box_size**2
    return None


def screen(pos, matrix) -> tuple:
    """Positions by a camera's composite matrix (4, 4): (N, 2) in -1 to 1,
    depth, and whether each is in front of the camera."""
    pos = np.asarray(pos, float)
    m = np.asarray(matrix, float)
    p = pos[:, 0, None] * m[:, 0] + pos[:, 1, None] * m[:, 1]
    p = p + pos[:, 2, None] * m[:, 2] + m[:, 3]
    w = p[:, 3]
    safe = np.where(w > 0, w, 1.0)
    return p[:, :2] / safe[:, None], p[:, 2] / safe, w > 0


def in_polygon(xy, polygon) -> np.ndarray:
    """Which of `xy` (N, 2) are inside `polygon` (M, 2)."""
    from matplotlib.path import Path as Polygon

    return Polygon(np.asarray(polygon, float)).contains_points(xy)


def front(xy, depth, cell: float = 0.02) -> np.ndarray:
    """Indices of the nearest point in each `cell` of the screen."""
    cells = np.floor(np.asarray(xy) / cell).astype(np.int64)
    order = np.argsort(depth)
    _, first = np.unique(cells[order], axis=0, return_index=True)
    return order[first]


def _read() -> dict:
    try:
        return json.loads(_SAVED.read_text())
    except (OSError, ValueError):
        return {}


def saved(model: str) -> list:
    """A model's saved regions: dicts of "name", "region" and "count"."""
    return _read().get(model, [])


def save(model: str, entries: list) -> None:
    """Replace a model's saved regions."""
    data = _read()
    data[model] = entries
    _SAVED.parent.mkdir(parents=True, exist_ok=True)
    _SAVED.write_text(json.dumps(data))
