"""Nebular emission lines for the lightcone photometry.

Young stars' ionising light lights up their HII regions. The lines come
from FSPS's nebular model (Byler et al. 2017, ApJ 840, 44: Cloudy
photoionisation grids over gas metallicity and ionisation parameter),
from each galaxy's stars younger than the young window (formed at its
current SFR), at:

  gas metallicity       the galaxy's cold-gas metallicity
                        (MetalsColdGas / ColdGas)
  ionisation parameter  from the galaxy's specific star-formation rate,
                        gas metallicity and HII-region density, as measured
                        in SDSS by Kashino & Inoue (2019, MNRAS 486, 1053,
                        eq. 5): log U = -2.316 - 0.360 (log O/H + 4)
                        - 0.292 log n_e + 0.428 (log sSFR + 9), with the
                        density from their eq. 3, log sSFR = -12.661
                        - 0.627 (log M* - 10) + 1.753 log n_e. More young
                        stars per unit mass ionise their gas more; metal-
                        rich stars are softer and denser gas less ionised.
                        O/H from Z with the solar 12 + log O/H = 8.69
                        (Asplund et al. 2009)

Lines arise in the birth clouds, so they are dimmed by the birth cloud
and the diffuse ISM at their wavelength and the galaxy's inclination
(Charlot & Fall 2000). Ionising photons absorbed by dust inside the HII
regions, and any that escape, are neglected (all are taken to ionise).
FSPS line wavelengths are vacuum.
"""

from __future__ import annotations

import numpy as np

C_CM_S = 2.99792458e10
Z_SUN = 0.0142  # Asplund et al. 2009
LOG_OH_SUN = 8.69 - 12.0
L_SUN_ERG_S = 3.828e33

# name: (vacuum wavelengths [A] summed into it, label)
LINES = {
    "OII3727": ((3727.1, 3729.9), "[OII] 3726+3729"),
    "Hbeta": ((4862.7,), "H-beta"),
    "OIII5007": ((5008.2,), "[OIII] 5007"),
    "Halpha": ((6564.6,), "H-alpha"),
    "NII6584": ((6585.3,), "[NII] 6584"),
    "SII6716_6731": ((6718.3, 6732.7), "[SII] 6716+6731"),
}

# Gas-metallicity and ionisation-parameter nodes of the line table
# (within FSPS's nebular grid: log Z/Zsun -2..0.5, log U -4..-1).
GAS_LOGZ_NODES = np.array([-2.0, -1.5, -1.0, -0.6, -0.3, 0.0, 0.25, 0.5])
GAS_LOGU_NODES = np.array([-4.0, -3.5, -3.0, -2.5, -2.0, -1.5, -1.0])


def kashino_inoue_logu(z_gas, ssfr, stellar_mass) -> np.ndarray:
    """log10 U of a galaxy's HII regions (Kashino & Inoue 2019, eqs. 3, 5)
    from its gas metallicity (mass fraction), sSFR (1/yr) and stellar
    mass (Msun); clipped to the line table's range."""
    z = np.maximum(np.asarray(z_gas, float), 1e-6)
    lssfr = np.log10(np.maximum(np.asarray(ssfr, float), 1e-14))
    lm = np.log10(np.maximum(np.asarray(stellar_mass, float), 1.0))
    log_ne = np.clip((lssfr + 12.661 + 0.627 * (lm - 10.0)) / 1.753, 0, 4)
    log_oh_4 = np.log10(z / Z_SUN) + LOG_OH_SUN + 4.0
    logu = -2.316 - 0.360 * log_oh_4 - 0.292 * log_ne + 0.428 * (lssfr + 9)
    return np.clip(logu, GAS_LOGU_NODES[0], GAS_LOGU_NODES[-1])


def line_indices(emline_wavelengths) -> dict[str, list[int]]:
    """For each LINES entry, the FSPS emission-line indices it sums."""
    w = np.asarray(emline_wavelengths, float)
    return {
        name: [int(np.argmin(np.abs(w - lw))) for lw in waves]
        for name, (waves, _) in LINES.items()
    }


def bilinear(table, x_nodes, y_nodes, x, y) -> np.ndarray:
    """Interpolate table[(nx, ny, ...)] at points (x, y) -> (n, ...)."""
    x = np.clip(x, x_nodes[0], x_nodes[-1])
    y = np.clip(y, y_nodes[0], y_nodes[-1])
    i = np.clip(np.searchsorted(x_nodes, x) - 1, 0, len(x_nodes) - 2)
    j = np.clip(np.searchsorted(y_nodes, y) - 1, 0, len(y_nodes) - 2)
    tx = ((x - x_nodes[i]) / (x_nodes[i + 1] - x_nodes[i]))[:, None]
    ty = ((y - y_nodes[j]) / (y_nodes[j + 1] - y_nodes[j]))[:, None]
    return (
        (1 - tx) * (1 - ty) * table[i, j]
        + tx * (1 - ty) * table[i + 1, j]
        + (1 - tx) * ty * table[i, j + 1]
        + tx * ty * table[i + 1, j + 1]
    )
