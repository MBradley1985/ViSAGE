"""Intergalactic absorption of a galaxy's light on its way to us.

The mean transmission of Madau (1995, ApJ 441, 18), as FSPS implements it
(its libfsps/src/igm_absorb.f90): the Lyman series of the Lyman-alpha forest
to n = 18, a small metal-line term, and the photoelectric absorption of the
clouds below the Lyman limit (his footnote 3). It matters for the bands that
see the rest-frame UV below 1216 A, so mostly above z ~ 2.
"""

from __future__ import annotations

import numpy as np

# (rest wavelength [A], A_j).
LYMAN_SERIES = (
    (1215.67, 0.0036),
    (1025.72, 0.0017),
    (972.537, 0.0011846),
    (949.743, 0.0009410),
    (937.803, 0.0007960),
    (930.748, 0.0006967),
    (926.226, 0.0006236),
    (923.150, 0.0005665),
    (920.963, 0.0005200),
    (919.352, 0.0004817),
    (918.129, 0.0004487),
    (917.181, 0.0004200),
    (916.429, 0.0003947),
    (915.824, 0.000372),
    (915.329, 0.000352),
    (914.919, 0.0003334),
    (914.576, 0.00031644),
)
METAL_COEFF = 0.0017
LYMAN_LIMIT_A = 911.75
LY_ALPHA_A = LYMAN_SERIES[0][0]


def transmission(wave_rest: np.ndarray, z: float) -> np.ndarray:
    """Mean IGM transmission at rest wavelengths `wave_rest` (Angstrom,
    ascending) of a source at redshift `z`."""
    wave = np.asarray(wave_rest, float)
    if z <= 0:
        return np.ones_like(wave)
    obs = wave * (1 + z)
    tau = np.zeros_like(wave)
    for lam, a in LYMAN_SERIES:
        m = wave < lam
        tau[m] += a * (obs[m] / lam) ** 3.46
    m = wave < LY_ALPHA_A
    tau[m] += METAL_COEFF * (obs[m] / LY_ALPHA_A) ** 1.68
    m = wave < LYMAN_LIMIT_A
    xc = obs[m] / LYMAN_LIMIT_A
    xe = 1 + z
    tau[m] += (
        0.25 * xc**3 * (xe**0.46 - xc**0.46)
        + 9.4 * xc**1.5 * (xe**0.18 - xc**0.18)
        - 0.7 * xc**3 * (xc**-1.32 - xe**-1.32)
        - 0.023 * (xe**1.68 - xc**1.68)
    )
    # The continuum fit fails at very short wavelengths: hold its maximum.
    top = int(np.argmax(tau))
    tau[:top] = tau[top]
    return np.exp(-tau)
