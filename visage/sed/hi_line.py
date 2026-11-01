"""HI line widths from a galaxy's annuli: the gas of each annulus turning at
its circular speed, seen at the galaxy's inclination, with the gas's own
11 km/s dispersion (Stevens et al. 2024). W50 is the full width at half the
peak, the usual measure of a line (Springob et al. 2005, ApJS 160, 149)."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d

STEP = 4.0  # km/s
TOP = 800.0  # km/s, the widest a line is followed
PHASES = 24  # points round each annulus
SIGMA = 11.0  # km/s
CHUNK = 4000


def _profiles(hi, speed, sin_i) -> np.ndarray:
    """(n, n_bins) line profiles."""
    n, annuli = hi.shape
    n_bins = int(2 * TOP / STEP)
    phase = np.cos(2 * np.pi * (np.arange(PHASES) + 0.5) / PHASES)
    los = (speed * sin_i[:, None])[:, :, None] * phase
    bins = np.clip(((los + TOP) / STEP).astype(int), 0, n_bins - 1)
    gal = np.arange(n)[:, None, None] * n_bins
    weight = np.broadcast_to(hi[:, :, None], (n, annuli, PHASES)) / PHASES
    prof = np.bincount(
        (gal + bins).ravel(), weight.ravel(), minlength=n * n_bins
    ).reshape(n, n_bins)
    return gaussian_filter1d(prof, SIGMA / STEP, axis=1)


def widths(hi, vcirc, sin_i) -> np.ndarray:
    """W50 (km/s) of galaxies with HI masses `hi` (n, 30), circular speeds
    at the annulus edges `vcirc` (n, 31) and inclinations `sin_i`; 0 with
    no HI."""
    hi = np.asarray(hi, float)
    speed = 0.5 * (np.asarray(vcirc)[:, 1:] + np.asarray(vcirc)[:, :-1])
    sin_i = np.asarray(sin_i, float)
    out = np.zeros(len(hi))
    for lo in range(0, len(hi), CHUNK):
        k = slice(lo, lo + CHUNK)
        prof = _profiles(hi[k], speed[k], sin_i[k])
        peak = prof.max(axis=1, keepdims=True)
        over = (prof >= 0.5 * peak) & (peak > 0)
        first = over.argmax(axis=1)
        last = over.shape[1] - 1 - over[:, ::-1].argmax(axis=1)
        out[k] = np.where(over.any(axis=1), (last - first) * STEP, 0.0)
    return out
