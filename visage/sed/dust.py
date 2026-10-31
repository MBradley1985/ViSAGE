"""Dust for SAGE26 lightcone photometry: how much dust each galaxy has,
and how it dims and reddens the galaxy's light.

Dust mass (cold ISM), from Dusty-SAGE (Triani et al. 2020, MNRAS 493,
2490), whose dust model -- production by stars, growth in molecular
clouds, destruction by supernovae -- is solved here for its steady state
from each galaxy's SAGE26 properties (SAGE26 doesn't evolve dust).

It is solved for the dust-to-metal ratio mu = M_dust / M_Z (cold gas),
not the dust-to-gas ratio: gas inflow (pristine), outflows and locking
into new stars move dust and metals together, so they cancel from mu --
in SAGE26 a metal-poor galaxy is metal-poor largely because inflow
dilutes it, and that dilutes its dust in the same way. What's left:

    0 = Y (d_c - mu) - eta m_swept(Z) N_SN Z mu
          + t_dep Z (f_H2 / tau_acc) mu (1 - 2 mu) / (1 - mu)

  stars         new metals Y per mass formed (the run's Yield), a share
                d_c = 0.2 condensed into dust (Dusty-SAGE, after Popping
                et al. 2017, MNRAS 471, 3152)
  destruction   supernova shocks: eta = 0.1 of the swept mass
                m_swept(Z) = 1535 (Z/0.02 + 0.039)^-0.289 Msun cleared
                per SN (Asano et al. 2013, EP&S 65, 213), SNe per mass
                formed N_SN from the Chabrier (2003) IMF (8-40 Msun)
  growth        accretion of gas-phase metals in molecular clouds,
                tau_acc = 20 Myr (0.02 / Z_gas) (Asano et al. 2013),
                stopping at mu = 1/2 (the dust equals the gas-phase metals)
  t_dep = M_cold / SFR, f_H2 = H2gas / ColdGas, Z = MetalsColdGas /
  ColdGas (SAGE26's metals include those in dust).
Metal-poor gas: growth (~Z^2) and destruction (~Z) fade, so mu -> d_c and
the dust-to-gas ratio falls with Z; metal-rich gas: growth takes over
(the critical metallicity of Asano et al. 2013) and mu -> 1/2.

Hot gas and the CGM (the CGM is part of the hot gas): dust there is
sputtered (Tsai & Mathews 1995, ApJ 448, 84) and its column is far below
the disk's, so it isn't included in the attenuation.

Attenuation, the two-component model of Charlot & Fall (2000, ApJ 539,
718), as Dusty SAGE's default variant has it (Triani et al. 2023, after
Lagos et al. 2019, MNRAS 489, 4196):
  dust surface  Sigma_dust = M_dust / (2 pi r l), inside the gas half-mass
  density       radius r = 1.68 R_d (as Lagos et al.; Dusty SAGE's own r is
                set to match its galaxies), l = cos i (r - r / 7.3) + r / 7.3
                the projected minor axis at the galaxy's own inclination
  diffuse ISM   a screen, tau_lambda = tau_ISM (lambda / 5500 A)^eta_ISM,
                both from Sigma_dust by the radiative-transfer results of
                Trayford et al. (2020, MNRAS 491, 3937), median relations
                as Lagos et al. digitised them
  birth clouds  stars younger than 10 Myr are also behind a cloud of
                tau_BC = (delta Sigma_cl) / (f_DTM,MW Z_sun Sigma_MW,cl),
                tau_lambda = tau_BC (lambda / 5500 A)^-0.7, with
                Sigma_cl = max(85 Msun/pc^2, the ISM's Sigma_gas), Z_sun =
                0.0189, f_DTM,MW = 0.33, at least tau_ISM and at most 5

Runs with SAGE26's DustySAGEMode carry their own dust: ColdDust replaces the
steady state. With DarkSAGEMode as well, each of the 30 annuli has its own
screen from DiscDust, and stars see the screen of the annulus they're in: new
stars placed by DiscSFR, the rest by DiscStars, the bulge near the centre.
Trayford et al. measured their relation on whole galaxies, so using it for
one annulus is an extrapolation, and a screen can't show stars mixed in with
the dust.
"""

from __future__ import annotations

import numpy as np

COND_EFFICIENCY = 0.2  # Popping et al. 2017; Dusty-SAGE delta_SN, delta_AGB
ETA_SN = 0.1  # Asano et al. 2013; Dusty-SAGE
TAU_ACC_MYR = 20.0  # Asano et al. 2013; Dusty-SAGE
BC_AGE_GYR = 0.01  # birth clouds disperse after 10 Myr (Charlot & Fall)
N_BC = 0.7  # Charlot & Fall 2000, Dusty SAGE's default
EDGE_ON_RATIO = 7.3  # disk length / height (Kregel et al. 2002)
SIGMA_CL_MW = 85.0  # Msun/pc^2 (Lagos et al. 2019)
Z_SUN_LAGOS = 0.0189
F_DTM_MW = 0.33
TAU_BC_MAX = 5.0
# Trayford et al. (2020), medians digitised by Lagos et al. (2019).
LOG_SIGMA_TAU = np.array(
    (
        4.10304,
        4.35135,
        4.58446,
        4.82264,
        5.06081,
        5.28885,
        5.52703,
        5.76520,
        6.00338,
        6.23649,
        6.46959,
        6.70270,
        6.94595,
        7.17905,
        7.41723,
    )
)  # log Msun/kpc^2
TAU_ISM = np.array(
    (
        0.03606,
        0.05048,
        0.06490,
        0.10096,
        0.15144,
        0.21635,
        0.33894,
        0.46875,
        0.66346,
        0.85096,
        1.03125,
        1.18269,
        1.34856,
        1.51442,
        1.58654,
    )
)
LOG_SIGMA_ETA = np.array(
    (
        4.58953,
        4.82264,
        5.05574,
        5.29392,
        5.53209,
        5.76520,
        6.00338,
        6.23649,
        6.46959,
        6.70270,
        6.94088,
        7.17905,
        7.42230,
        7.64527,
    )
)
ETA_ISM = np.array(
    (
        -1.35463,
        -1.34361,
        -1.27753,
        -1.18392,
        -1.04075,
        -0.87555,
        -0.74339,
        -0.61674,
        -0.52313,
        -0.44053,
        -0.39648,
        -0.33590,
        -0.26982,
        -0.30837,
    )
)
P0_LSUN_MSUN = 125.0  # L_dust / M_dust at U = 1 (Magdis et al. 2012)
U_MIN_NODES = np.array([0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0])  # DL07
# <U> / U_min for the Draine & Li (2007) U_min..1e6 power law, gamma = 0.01
# (nearly constant across their range).
MEAN_U_PER_UMIN = 1.13
DISK_A = 1.68  # gas disk half-mass radius / scale length (De Lucia & Blaizot)


def sn_per_mass_formed(m_lo=8.0, m_hi=40.0) -> float:
    """Core-collapse supernovae per Msun formed, Chabrier (2003) IMF over
    0.1-100 Msun, progenitors m_lo..m_hi (as Dusty-SAGE)."""
    m = np.logspace(-1, 2, 20000)
    lm = np.log10(m)
    # Chabrier 2003 (system IMF, eq. 18 / Table 1): dN/dlog m.
    xi = np.where(
        m < 1.0,
        0.158 * np.exp(-((lm - np.log10(0.079)) ** 2) / (2 * 0.69**2)),
        0.0443 * m**-1.3,
    )
    dn_dm = xi / (m * np.log(10))
    mass = np.trapezoid(m * dn_dm, m)
    sel = (m >= m_lo) & (m <= m_hi)
    return float(np.trapezoid(dn_dm[sel], m[sel]) / mass)


def cold_dust_ratio(
    cold, metals_cold, h2, sfr, recycle=0.43, yield_=0.025
) -> np.ndarray:
    """Dust-to-gas ratio of each galaxy's cold ISM, delta = mu Z (see the
    module docstring). Arrays in Msun and Msun/yr; 0 without cold gas.
    (``recycle`` cancels from the dust-to-metal balance; kept for the
    call signature.)"""
    cold = np.asarray(cold, float)
    z = np.where(
        cold > 0, np.asarray(metals_cold, float) / np.maximum(cold, 1e-30), 0.0
    )
    f_h2 = np.clip(
        np.where(
            cold > 0, np.asarray(h2, float) / np.maximum(cold, 1e-30), 0.0
        ),
        0,
        1,
    )
    sfr = np.asarray(sfr, float)
    t_dep = np.where(sfr > 0, cold / np.maximum(sfr, 1e-30), np.inf)  # yr
    n_sn = sn_per_mass_formed()

    def f(mu):
        zg = np.maximum(z * (1 - mu), 1e-8)  # gas-phase metals
        tau_acc = TAU_ACC_MYR * 1e6 * 0.02 / zg
        grow = np.where(
            mu < 0.5,
            (f_h2 / tau_acc) * mu * (1 - 2 * mu) / np.maximum(1 - mu, 1e-12),
            0.0,
        )
        m_sw = 1535.0 * (zg / 0.02 + 0.039) ** -0.289
        stars = yield_ * (COND_EFFICIENCY - mu) - ETA_SN * m_sw * n_sn * z * mu
        with np.errstate(invalid="ignore", over="ignore"):
            # Not forming stars: only growth acts (toward mu = 1/2).
            return np.where(np.isfinite(t_dep), stars + t_dep * z * grow, grow)

    # Bisection on mu in (0, 1): f(0) > 0 where stars form.
    lo = np.zeros_like(z)
    hi = np.ones_like(z)
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        pos = f(mid) > 0
        lo = np.where(pos, mid, lo)
        hi = np.where(pos, hi, mid)
    mu = 0.5 * (lo + hi)
    # No star formation and no H2: nothing processes the dust; it keeps
    # the share stars condense.
    quiet = ~np.isfinite(t_dep) & (f_h2 <= 0)
    mu = np.where(quiet, COND_EFFICIENCY, mu)
    return np.where(cold > 0, mu * z, 0.0)


def _gas_radius_kpc(disk_radius_kpc):
    return DISK_A * np.maximum(np.asarray(disk_radius_kpc, float), 0.05)


def sigma_dust(m_dust, disk_radius_kpc, cos_i) -> np.ndarray:
    """Dust surface density (Msun/kpc^2) seen at inclination `cos_i` (1 is
    face-on; see the module docstring)."""
    r = _gas_radius_kpc(disk_radius_kpc)
    edge = r / EDGE_ON_RATIO
    return np.asarray(m_dust, float) / (
        2 * np.pi * r * (np.asarray(cos_i, float) * (r - edge) + edge)
    )


def tau_eta_ism(sig_dust) -> tuple[np.ndarray, np.ndarray]:
    """V-band optical depth and slope of the ISM screen for dust surface
    density `sig_dust` (Msun/kpc^2), proportional to it below the table."""
    lg = np.log10(np.maximum(np.asarray(sig_dust, float), 1e-30))
    tau = np.interp(lg, LOG_SIGMA_TAU, TAU_ISM)
    tau = tau * 10.0 ** np.minimum(lg - LOG_SIGMA_TAU[0], 0.0)
    return tau, np.interp(lg, LOG_SIGMA_ETA, ETA_ISM)


def tau_bc(delta, m_cold, disk_radius_kpc, tau_ism) -> np.ndarray:
    """V-band optical depth of the birth clouds (see the module docstring)
    for dust-to-gas ratio `delta` and cold gas `m_cold` (Msun)."""
    r_pc = _gas_radius_kpc(disk_radius_kpc) * 1e3
    sig_gas = np.asarray(m_cold, float) / (2 * np.pi * r_pc**2)
    sig_cl = np.maximum(sig_gas, SIGMA_CL_MW)
    tau = (
        np.asarray(delta, float)
        * sig_cl
        / (F_DTM_MW * Z_SUN_LAGOS * SIGMA_CL_MW)
    )
    return np.clip(np.maximum(tau, tau_ism), 0.0, TAU_BC_MAX)


def cos_inclination(spin, los) -> np.ndarray:
    """|cos i| between each galaxy's spin axis and the line of sight (for
    a zero spin, a random orientation taken from the galaxy's position,
    so that it doesn't depend on which rows are being computed)."""
    s = np.asarray(spin, float)
    los = np.asarray(los, float)
    ns = np.linalg.norm(s, axis=1)
    nl = np.linalg.norm(los, axis=1)
    c = np.abs(np.sum(s * los, axis=1)) / np.maximum(ns * nl, 1e-30)
    rnd = np.modf(np.abs(los).sum(axis=1) * 1e3)[0]
    return np.where(ns > 0, c, rnd)


def ism_transmission(wave, tau_ism, eta_ism) -> np.ndarray:
    """(n, n_wave) transmission of the diffuse ISM screen."""
    x = np.asarray(wave, float)[None, :] / 5500.0
    return np.exp(-np.asarray(tau_ism)[:, None] * x ** eta_ism[:, None])


def annulus_tau(disc_dust, edges_kpc, cos_i) -> tuple:
    """(n, 30) V-band depths and slopes of each annulus's screen, for its
    dust (Msun) and (n, 31) edges, seen at `cos_i`."""
    area = np.maximum(
        np.pi * np.diff(np.asarray(edges_kpc) ** 2, axis=1), 1e-12
    )
    edge = 1.0 / EDGE_ON_RATIO
    tilt = np.asarray(cos_i, float)[:, None] * (1 - edge) + edge
    return tau_eta_ism(np.asarray(disc_dust, float) / area / tilt)


def annulus_shares(disc, bulge, bulge_r_kpc, edges_kpc) -> np.ndarray:
    """(n, 30) share of some light in each annulus: `disc` there, `bulge`
    falling off exponentially from the centre over `bulge_r_kpc`. Anything
    without either is shared evenly."""
    edges = np.asarray(edges_kpc, float)
    area = np.diff(edges**2, axis=1)
    mid = 0.5 * (edges[:, 1:] + edges[:, :-1])
    rb = np.maximum(np.asarray(bulge_r_kpc, float), 0.05)[:, None]
    shape = area * np.exp(-mid / rb)
    shape = shape / np.maximum(shape.sum(axis=1, keepdims=True), 1e-30)
    light = np.asarray(disc, float) + np.asarray(bulge, float)[:, None] * shape
    total = light.sum(axis=1, keepdims=True)
    return np.where(
        total > 0, light / np.maximum(total, 1e-30), 1.0 / light.shape[1]
    )


def annuli_transmission(wave, tau, eta, shares) -> np.ndarray:
    """(n, n_wave) light through the annuli's screens."""
    x = np.asarray(wave, float) / 5500.0
    out = np.zeros((len(tau), len(x)))
    for k in range(tau.shape[1]):
        out += shares[:, k, None] * np.exp(
            -tau[:, k, None] * x ** eta[:, k, None]
        )
    return out


def bc_transmission(wave, tau_birth) -> np.ndarray:
    """(n, n_wave) birth-cloud transmission (a screen)."""
    return np.exp(
        -np.outer(tau_birth, (np.asarray(wave, float) / 5500.0) ** -N_BC)
    )


_EMISSION: dict = {}


def umin_from_luminosity(l_dust, m_dust) -> np.ndarray:
    """Draine & Li (2007) U_min of dust of mass `m_dust` (Msun) re-emitting
    `l_dust` (Lsun): L_dust = P0 <U> M_dust (Magdis et al. 2012, ApJ 760, 6),
    within the models' range."""
    m_dust = np.maximum(np.asarray(m_dust, float), 1e-30)
    u = np.asarray(l_dust, float) / (P0_LSUN_MSUN * m_dust * MEAN_U_PER_UMIN)
    return np.clip(u, U_MIN_NODES[0], U_MIN_NODES[-1])


def emission_templates(wave: np.ndarray) -> np.ndarray:
    """(n_U, n_wave) dust emission per unit absorbed luminosity (L_nu per
    L_sun, on `wave`) at each of U_MIN_NODES: the Draine & Li (2007) model
    as FSPS has it (q_PAH = 3.5%, gamma = 0.01), each normalised to
    integrate to 1 over frequency. Energy balance (da Cunha, Charlot &
    Elbaz 2008, MNRAS 388, 1595): each galaxy re-emits exactly what its
    dust absorbed."""
    key = len(wave)
    if key not in _EMISSION:
        import fsps

        kw = dict(zcontinuous=1, sfh=0, imf_type=1, dust_type=2, dust2=1.0)
        sp = fsps.StellarPopulation(add_dust_emission=True, **kw)
        _, without = fsps.StellarPopulation(
            add_dust_emission=False, **kw
        ).get_spectrum(tage=0.1)
        out = []
        for u in U_MIN_NODES:
            sp.params["duste_umin"] = float(u)
            w, with_em = sp.get_spectrum(tage=0.1)
            em = np.clip(np.asarray(with_em) - np.asarray(without), 0.0, None)
            em = np.interp(wave, np.asarray(w), em)
            out.append(em / np.dot(em, frequency_weights(wave)))
        _EMISSION[key] = np.stack(out)
    return _EMISSION[key]


def emission_spectra(wave: np.ndarray, u_min) -> np.ndarray:
    """(n, n_wave) emission_templates at each galaxy's `u_min`, linear in
    log U."""
    t = emission_templates(wave)
    lx = np.log(U_MIN_NODES)
    lu = np.log(np.asarray(u_min, float))
    j = np.clip(np.searchsorted(lx, lu) - 1, 0, len(lx) - 2)
    f = ((lu - lx[j]) / (lx[j + 1] - lx[j]))[:, None]
    return (1 - f) * t[j] + f * t[j + 1]


def frequency_weights(wave: np.ndarray) -> np.ndarray:
    """Weights w with L = sum(L_nu * w) = integral L_nu d(nu), on a
    wavelength grid in Angstrom."""
    nu = 2.99792458e18 / np.asarray(wave, float)
    w = np.zeros_like(nu)
    d = np.abs(np.diff(nu))
    w[:-1] += 0.5 * d
    w[1:] += 0.5 * d
    return w
