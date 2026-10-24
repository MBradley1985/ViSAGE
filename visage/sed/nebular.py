"""Nebular emission lines from each galaxy's HII regions.

Young stars' ionising light lights up their HII regions. The lines come
from the star-forming nebular models of Gutkin, Charlot & Bruzual (2016,
MNRAS 462, 1757: Bruzual & Charlot stellar populations through Cloudy,
for a Chabrier IMF to 100 Msun and constant star formation for 100 Myr),
the companions of the AGN models in visage/sed/agn.py and coupled to
galaxies the same way (Hirschmann et al. 2017, MNRAS 472, 2468). They
give line luminosity per unit SFR, so each galaxy's lines are its
current SFR (that of its stars younger than the young window) times the
grid at:

  gas metallicity       the galaxy's cold-gas metallicity
                        (MetalsColdGas / ColdGas), as the grid's total
                        (gas + dust) interstellar metallicity
  ionisation parameter  from the galaxy's specific star-formation rate,
                        gas metallicity and HII-region density, as measured
                        in SDSS by Kashino & Inoue (2019, MNRAS 486, 1053,
                        eq. 5): log U = -2.316 - 0.360 (log O/H + 4)
                        - 0.292 log n_e + 0.428 (log sSFR + 9). More young
                        stars per unit mass ionise their gas more; metal-
                        rich stars are softer and denser gas less ionised.
                        O/H from Z with the solar 12 + log O/H = 8.69
                        (Asplund et al. 2009). Their U is Cloudy's in
                        plane-parallel geometry, which is close to the
                        grid's U at the Stromgren radius (Feltre et al.
                        2016, sec. 2.1)
  density               n_H = n_e from their eq. 3, log sSFR = -12.661
                        - 0.627 (log M* - 10) + 1.753 log n_e, within the
                        grid's 100-1000 cm^-3
  dust-to-metal ratio   0.3, carbon-to-oxygen ratio solar (the models'
                        fiducial values; Hirschmann et al. 2017)

Lines arise in the birth clouds, so they are dimmed by the birth cloud
and the diffuse ISM at their wavelength and the galaxy's inclination
(visage/sed/dust.py). Wavelengths below are vacuum.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

Z_SUN = 0.0142  # Asplund et al. 2009
LOG_OH_SUN = 8.69 - 12.0
L_SUN_GRID = 3.826e33  # erg/s, the solar luminosity the grid is given in

# name: (vacuum wavelengths [A] summed into it, label)
LINES = {
    "OII3727": ((3727.1, 3729.9), "[OII] 3726+3729"),
    "Hbeta": ((4862.7,), "H-beta"),
    "OIII5007": ((5008.2,), "[OIII] 5007"),
    "Halpha": ((6564.6,), "H-alpha"),
    "NII6584": ((6585.3,), "[NII] 6584"),
    "SII6716_6731": ((6718.3, 6732.7), "[SII] 6716+6731"),
}

# The grid's ionisation-parameter range.
LOGU_MIN, LOGU_MAX = -4.0, -1.0

_GRID_FILE = Path(__file__).with_name("data") / "gutkin16_hii.npz"


@lru_cache(maxsize=1)
def grid():
    """(Z nodes, log U_S nodes, n_H nodes, table (n_Z, n_U, n_nH,
    n_lines) erg/s per Msun/yr, line names), in LINES order."""
    g = np.load(_GRID_FILE)
    return (
        g["Z"],
        g["logU"],
        g["nH"],
        g["lines"] * L_SUN_GRID,
        [str(s) for s in g["names"]],
    )


def kashino_inoue_log_ne(ssfr, stellar_mass) -> np.ndarray:
    """log10 electron density (cm^-3) of a galaxy's HII regions from its
    sSFR (1/yr) and stellar mass (Msun), Kashino & Inoue 2019 eq. 3."""
    lssfr = np.log10(np.maximum(np.asarray(ssfr, float), 1e-14))
    lm = np.log10(np.maximum(np.asarray(stellar_mass, float), 1.0))
    return np.clip((lssfr + 12.661 + 0.627 * (lm - 10.0)) / 1.753, 0, 4)


def kashino_inoue_logu(z_gas, ssfr, stellar_mass) -> np.ndarray:
    """log10 U of a galaxy's HII regions (Kashino & Inoue 2019, eqs. 3, 5)
    from its gas metallicity (mass fraction), sSFR (1/yr) and stellar
    mass (Msun); clipped to the grid's range."""
    z = np.maximum(np.asarray(z_gas, float), 1e-6)
    lssfr = np.log10(np.maximum(np.asarray(ssfr, float), 1e-14))
    log_ne = kashino_inoue_log_ne(ssfr, stellar_mass)
    log_oh_4 = np.log10(z / Z_SUN) + LOG_OH_SUN + 4.0
    logu = -2.316 - 0.360 * log_oh_4 - 0.292 * log_ne + 0.428 * (lssfr + 9)
    return np.clip(logu, LOGU_MIN, LOGU_MAX)


def hii_lines_per_sfr(z_gas, logu, log_nh) -> np.ndarray:
    """(n, n_lines) HII-region line luminosities, erg/s per Msun/yr, no
    dust outside the HII regions: the grid interpolated in log Z, log U
    and log n_H (clipped to its edges)."""
    z_nodes, u_nodes, n_nodes, table, _ = grid()
    logt = np.log10(table)
    lz = np.log10(np.maximum(np.asarray(z_gas, float), 1e-6))
    u = np.asarray(logu, float)
    ln = np.clip(
        np.asarray(log_nh, float),
        np.log10(n_nodes[0]),
        np.log10(n_nodes[-1]),
    )
    lnn = np.log10(n_nodes)
    j = np.clip(np.searchsorted(lnn, ln) - 1, 0, len(lnn) - 2)
    t = ((ln - lnn[j]) / (lnn[j + 1] - lnn[j]))[:, None]
    zn = np.log10(z_nodes)
    lo = np.empty((len(lz), logt.shape[-1]))
    hi = np.empty_like(lo)
    for k in range(len(lnn) - 1):
        m = j == k
        if m.any():
            lo[m] = bilinear(logt[:, :, k], zn, u_nodes, lz[m], u[m])
            hi[m] = bilinear(logt[:, :, k + 1], zn, u_nodes, lz[m], u[m])
    return 10.0 ** ((1 - t) * lo + t * hi)


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
