"""Intergalactic absorption of a galaxy's light on its way to us.

The mean transmission of Madau (1995, ApJ 441, 18): the Lyman series of the
Lyman-alpha forest (his eq. 15, Ly-alpha to Ly-delta) and the photoelectric
absorption of its clouds below the Lyman limit (his footnote 3). It matters
for the bands that see the rest-frame UV below 1216 A, so mostly above z ~ 2.
"""

from __future__ import annotations

import numpy as np

# (rest wavelength [A], A_j of Madau 1995).
LYMAN_SERIES = (
    (1215.67, 0.0036),
    (1025.72, 1.7e-3),
    (972.537, 1.2e-3),
    (949.743, 9.3e-4),
)
LYMAN_LIMIT_A = 911.75
LY_ALPHA_A = LYMAN_SERIES[0][0]


def transmission(wave_rest: np.ndarray, z: float) -> np.ndarray:
    """Mean IGM transmission at rest wavelengths `wave_rest` (Angstrom) of
    a source at redshift `z`."""
    wave = np.asarray(wave_rest, float)
    if z <= 0:
        return np.ones_like(wave)
    obs = wave * (1 + z)
    tau = np.zeros_like(wave)
    for lam, a in LYMAN_SERIES:
        m = wave < lam
        tau[m] += a * (obs[m] / lam) ** 3.46
    m = wave < LYMAN_LIMIT_A
    xc = np.maximum(obs[m] / LYMAN_LIMIT_A, 1.0)
    xe = 1 + z
    tau[m] += (
        0.25 * xc**3 * (xe**0.46 - xc**0.46)
        + 9.4 * xc**1.5 * (xe**0.18 - xc**0.18)
        - 0.7 * xc**3 * (xc**-1.32 - xe**-1.32)
        - 0.023 * (xe**1.68 - xc**1.68)
    )
    return np.exp(-tau)
