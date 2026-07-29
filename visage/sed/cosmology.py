from __future__ import annotations

import numpy as np

# Reuse the exact same flat-LCDM age formula already validated for the
# "mean stellar age" colour-by mode, so SED ages are consistent with it.
from visage.io.galaxy_reader import _age_lcdm

MPC_TO_CM = 3.0856775814913673e24


def age_at_scale_factor(
    a: np.ndarray | float, h: float, om: float, ol: float
) -> np.ndarray:
    """Cosmic age (Gyr) at scale factor a, flat LCDM."""
    return _age_lcdm(a, h, om, ol)


def luminosity_distance_mpc(
    z: np.ndarray, h: float, om: float, ol: float
) -> np.ndarray:
    """Luminosity distance (Mpc) at redshift z, using the simulation's own
    cosmology (NOT an assumed/hardcoded one, unlike FSPS's built-in
    redshift-to-magnitude helper)."""
    from astropy.cosmology import FlatLambdaCDM

    cosmo = FlatLambdaCDM(H0=100.0 * h, Om0=om)
    return cosmo.luminosity_distance(np.asarray(z, dtype=np.float64)).value
