"""Which galaxies and haloes a simulation resolves, from its particle mass.

A halo is resolved with at least N dark-matter particles (20, the halo
finder's own minimum, by default; settable on the SAGE26 and LightSAGE
setup screens).  Haloes are cut at N particle masses.  Galaxies are cut in
stellar mass where their haloes become resolved: per snapshot, the lowest
stellar mass from which RESOLVED_SHARE of central galaxies (in 0.1 dex bins)
live in haloes of at least N particles -- so the cut follows the
simulation's resolution and redshift rather than one number for every
run.

The setting is kept in ~/.visage/settings.json, per kind of model ("box",
"cone"), so it holds for every model opened afterwards.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DEFAULT_PARTICLES = 20
CHOICES = (20, 50, 100)
# Share of a bin's centrals whose haloes must be resolved.
RESOLVED_SHARE = 0.9
BIN_DEX = 0.1
MIN_PER_BIN = 20  # centrals a bin needs to count

_SETTINGS = Path.home() / ".visage" / "settings.json"


def _load() -> dict:
    try:
        data = json.loads(_SETTINGS.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def particles(kind: str) -> int:
    """Particles a resolved halo needs, for a "box" or "cone" model."""
    v = _load().get("resolved_particles", {}).get(kind, DEFAULT_PARTICLES)
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return DEFAULT_PARTICLES


def set_particles(kind: str, n: int) -> None:
    data = _load()
    data.setdefault("resolved_particles", {})[kind] = int(n)
    try:
        _SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def resolved_stellar_mass(
    stellar_mass: np.ndarray,
    halo_particles: np.ndarray,
    central: np.ndarray,
    n: int,
) -> float | None:
    """Lowest stellar mass (the units given) from which RESOLVED_SHARE of
    centrals have haloes of at least `n` particles; None if no bin has
    enough centrals to tell."""
    sm = np.asarray(stellar_mass, float)
    ok = np.asarray(central, bool) & (sm > 0)
    if not ok.any():
        return None
    lm = np.log10(sm[ok])
    res = np.asarray(halo_particles, float)[ok] >= n
    lo = np.floor(lm.min() / BIN_DEX) * BIN_DEX
    edges = np.arange(lo, lm.max() + BIN_DEX, BIN_DEX)
    which = np.digitize(lm, edges) - 1
    count = np.bincount(which, minlength=len(edges))
    good = np.bincount(which, weights=res, minlength=len(edges))
    for b in range(len(edges)):
        if count[b] >= MIN_PER_BIN and good[b] / count[b] >= RESOLVED_SHARE:
            return float(10 ** edges[b])
    return None
