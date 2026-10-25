"""Emission lines from each galaxy's AGN narrow-line region.

SAGE26 grows black holes in two ways, both recorded in the lightcone:

  quasar mode  cold gas accreted in mergers (and disk instabilities),
               ``QuasarModeBHaccretionMass`` per snapshot, spread over the
               snapshot's time step ``dT`` (in h^-1 Myr, SAGE26's internal
               time unit)
  radio mode   hot-halo accretion, ``RadioModeBHaccretionMass`` per
               snapshot (newer SAGE26) over the same step; in older
               outputs only its power, ``Heating`` (eta Mdot c^2, log10
               erg/s, eta = 0.1, averaged over the step)

The accretion rate gives the luminosity: L = eta Mdot c^2 above 1 per cent
of Eddington (a thin disc), falling as Mdot^2 below it, where the flow
becomes radiatively inefficient (Narayan & Yi 1995; Merloni & Heinz 2008,
MNRAS 388, 1011): L / L_Edd = mdot^2 / 0.01 for mdot = eta Mdot c^2 / L_Edd
< 0.01. L_Edd = 1.3e38 erg/s per Msun, as in SAGE26.

The lines come from the photoionisation models of Feltre, Charlot & Gutkin
(2016, MNRAS 456, 3354), coupled to a galaxy as Hirschmann et al. (2017,
MNRAS 472, 2468, sec. 2.3) do: an ionising spectrum S_nu ~ nu^-1.7, gas
clumps of n_H = 1e3 cm^-3, dust-to-metal ratio 0.3, the galaxy's cold-gas
metallicity, and the ionisation parameter at the Stromgren radius

    U_S = alpha_B^(2/3) / (3c) * (3 Q eps^2 n_H / 4 pi)^(1/3)

from the AGN's ionising-photon rate Q and the filling factor eps = n_gas /
n_H of the gas within 1 kpc of the black hole (capped at 1). Here that gas
is the cold gas in an exponential disk with the galaxy's DiskRadius scale
length. Brighter AGN with more central gas ionise their gas more
(Seyfert-like); faint, radiatively inefficient ones barely do (LINER-like).
The lines are dimmed by the galaxy's diffuse ISM dust, not by birth clouds.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

C_CM_S = 2.99792458e10
H_ERG_S = 6.62607015e-27
M_P_G = 1.67262192e-24
MSUN_G = 1.98847e33
KPC_CM = 3.0857e21
YR_S = 3.15576e7
ETA = 0.1  # radiative efficiency (SAGE26's AGN_RADIATIVE_EFFICIENCY)
L_EDD_PER_MSUN = 1.3e38  # erg/s (SAGE26's EDDINGTON_LUM_PER_MSUN_CGS)
MDOT_CRIT = 0.01  # Eddington ratio where the flow turns inefficient
ALPHA_B = 2.59e-13  # case-B recombination coefficient at 1e4 K, cm^3/s
N_H = 1.0e3  # cm^-3, narrow-line-region clumps (Hirschmann et al. 2017)
X_H = 0.74  # hydrogen mass fraction
R_CENTRAL_KPC = 1.0
L_GRID = 1.0e45  # erg/s, the luminosity the grid is computed for

_GRID_FILE = Path(__file__).with_name("data") / "feltre16_nlr.npz"


@lru_cache(maxsize=1)
def grid():
    """(Z nodes, log U_S nodes, table (n_Z, n_U, n_lines) erg/s per
    1e45 erg/s, line names), in nebular.LINES order."""
    g = np.load(_GRID_FILE)
    return g["Z"], g["logU"], g["lines"], [str(s) for s in g["names"]]


def ionising_photons_per_erg(alpha: float = -1.7) -> float:
    """Q / L for Feltre et al.'s broken power law (their eq. 5):
    S_nu ~ nu^alpha at 0.001-0.25 um, nu^-0.5 at 0.25-10 um, nu^2 beyond,
    continuous at the breaks."""
    nu = lambda lam_um: C_CM_S / (lam_um * 1e-4)  # noqa: E731
    n1, n2, n3 = nu(10.0), nu(0.25), nu(0.001)
    n_ion = 13.6 / 4.1356677e-15  # Hz

    # S = s1 nu^2 below n1, s2 nu^-0.5 up to n2, s3 nu^alpha up to n3.
    s3 = 1.0
    s2 = s3 * n2**alpha / n2**-0.5
    s1 = s2 * n1**-0.5 / n1**2

    def pint(s, p, a, b):
        return s * (b ** (p + 1) - a ** (p + 1)) / (p + 1)

    lum = (
        pint(s1, 2.0, 0.0, n1)
        + pint(s2, -0.5, n1, n2)
        + pint(s3, alpha, n2, n3)
    )
    q = pint(s3, alpha - 1.0, n_ion, n3) / H_ERG_S
    return q / lum


def luminosity(bh_mass, mdot_quasar, heating_log, mdot_radio=None):
    """AGN luminosity (erg/s) and Eddington ratio.

    bh_mass       Msun
    mdot_quasar   Msun/yr, quasar-mode accretion rate
    heating_log   SAGE26 ``Heating``: log10 of radio-mode eta Mdot c^2
                  (erg/s), 0 when there was none
    mdot_radio    Msun/yr, radio-mode accretion rate (from
                  ``RadioModeBHaccretionMass``); used instead of
                  ``heating_log`` when given
    """
    bh_mass = np.asarray(bh_mass, float)
    if mdot_radio is not None:
        heating = (
            ETA * np.asarray(mdot_radio, float) * MSUN_G / YR_S * C_CM_S**2
        )
    else:
        heating = np.where(
            np.asarray(heating_log, float) > 0,
            10.0 ** np.asarray(heating_log),
            0,
        )
    p_acc = ETA * np.asarray(mdot_quasar, float) * MSUN_G / YR_S * C_CM_S**2
    p_acc = p_acc + heating  # eta Mdot c^2, erg/s
    l_edd = L_EDD_PER_MSUN * bh_mass
    with np.errstate(divide="ignore", invalid="ignore"):
        mdot = np.where(l_edd > 0, p_acc / l_edd, 0.0)
    lam = np.where(mdot >= MDOT_CRIT, mdot, mdot**2 / MDOT_CRIT)
    return lam * l_edd, lam


def central_gas_density(cold_mass, disk_radius_kpc):
    """Mean hydrogen density (cm^-3) within 1 kpc of the centre, for cold
    gas in an exponential disk of scale length ``disk_radius_kpc``."""
    x = R_CENTRAL_KPC / np.maximum(np.asarray(disk_radius_kpc, float), 1e-3)
    m_in = np.asarray(cold_mass, float) * (1.0 - (1.0 + x) * np.exp(-x))
    vol = 4.0 / 3.0 * np.pi * (R_CENTRAL_KPC * KPC_CM) ** 3
    return X_H * m_in * MSUN_G / M_P_G / vol


def log_u(l_agn, n_gas, alpha: float = -1.7):
    """log10 U_S of the narrow-line region (Feltre et al. 2016, eq. 4;
    Hirschmann et al. 2017, eqs. 1-2)."""
    q = np.asarray(l_agn, float) * ionising_photons_per_erg(alpha)
    eps = np.clip(np.asarray(n_gas, float) / N_H, 1e-12, 1.0)
    u = (
        ALPHA_B ** (2.0 / 3.0)
        / (3.0 * C_CM_S)
        * np.cbrt(3.0 * q * eps**2 * N_H / (4.0 * np.pi))
    )
    with np.errstate(divide="ignore"):
        return np.log10(np.maximum(u, 1e-30))


def line_luminosities(l_agn, z_gas, logu):
    """(n, n_lines) narrow-line luminosities, erg/s, no dust; the grid
    interpolated in log Z and log U_S (clipped to its edges)."""
    from visage.sed.nebular import bilinear

    z_nodes, u_nodes, table, _ = grid()
    per = bilinear(
        np.log10(table),
        np.log10(z_nodes),
        u_nodes,
        np.log10(np.maximum(np.asarray(z_gas, float), 1e-6)),
        np.asarray(logu, float),
    )
    return 10.0**per * (np.asarray(l_agn, float) / L_GRID)[:, None]
