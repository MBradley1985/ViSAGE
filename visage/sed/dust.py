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
718), as used in semi-analytic models (e.g. De Lucia & Blaizot 2007,
MNRAS 375, 2):
  diffuse ISM   face-on optical depth of the dust in front of the
                starlight: the mean hydrogen column inside the stellar
                half-light radius (1.68 R_d), with the molecular gas
                following the stars (Leroy et al. 2008, AJ 136, 2782)
                and the atomic gas in its own, more extended exponential
                disk, sized by the HI size-mass relation (Wang et al.
                2016, MNRAS 460, 2143: Sigma_HI = 1 Msun/pc^2 at D_HI/2);
                tau_V = (A_V / N_H)_MW / 1.086 * N_H * (M_dust / M_H) /
                (M_dust / M_H)_MW, A_V / N_H = 5.3e-22 mag cm^2 (Bohlin,
                Savage & Drake 1978, R_V = 3.1), (M_dust / M_H)_MW =
                0.010 (Draine & Li 2007, ApJ 657, 810);
                tau_lambda = tau_V (lambda / 5500 A)^-0.7, mixed with the
                stars in a slab seen at inclination i:
                T = (1 - exp(-tau sec i)) / (tau sec i)
  birth clouds  stars younger than 10 Myr are also behind their birth
                cloud, tau_V^BC = tau_V (1 - mu) / mu with mu = 0.3,
                tau_lambda^BC = tau_V^BC (lambda / 5500 A)^-1.3
(Charlot & Fall used lambda^-0.7 for both; the steeper birth-cloud curve
and mu = 0.3 are those of da Cunha, Charlot & Elbaz 2008, MNRAS 388, 1595,
fitted to nearby galaxies' UV-to-IR SEDs.)
"""

from __future__ import annotations

import numpy as np

COND_EFFICIENCY = 0.2  # Popping et al. 2017; Dusty-SAGE delta_SN, delta_AGB
ETA_SN = 0.1  # Asano et al. 2013; Dusty-SAGE
TAU_ACC_MYR = 20.0  # Asano et al. 2013; Dusty-SAGE
AV_PER_NH = 5.3e-22  # mag cm^2 (Bohlin et al. 1978, R_V = 3.1)
DTG_MW = 0.010  # Draine & Li 2007: dust per hydrogen mass
MU_ISM = 0.3  # da Cunha et al. 2008 (Charlot & Fall 2000 model)
BC_AGE_GYR = 0.01  # birth clouds disperse after 10 Myr (Charlot & Fall)
N_ISM, N_BC = 0.7, 1.3  # Charlot & Fall 2000; da Cunha et al. 2008
DISK_A = 1.68  # gas disk half-mass radius / scale length (De Lucia & Blaizot)
M_P = 1.6726e-24  # g
MSUN = 1.989e33  # g
KPC = 3.0857e21  # cm


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


def _exp_scale_hi(m_hi, r1_pc):
    """Scale length (pc) of an exponential HI disk of mass m_hi (Msun)
    whose surface density falls to 1 Msun/pc^2 at radius r1_pc."""
    lo = np.full_like(m_hi, 1.0)
    hi = np.maximum(r1_pc, 2.0)
    for _ in range(60):
        h = 0.5 * (lo + hi)
        sig = m_hi / (2 * np.pi * h * h) * np.exp(-r1_pc / h)
        # Sigma(r1) rises with h up to h = r1/2; take the extended root.
        grow = sig < 1.0
        lo = np.where(grow, h, lo)
        hi = np.where(grow, hi, h)
    return 0.5 * (lo + hi)


def tau_v_ism(m_hi, m_h2, m_cold, disk_radius_kpc, delta) -> np.ndarray:
    """Face-on V-band optical depth of the diffuse ISM in front of the
    starlight (see the module docstring). Masses in Msun (HI and H2 as
    hydrogen, cold gas total), radius in kpc."""
    m_hi = np.maximum(np.asarray(m_hi, float), 0.0)
    m_h2 = np.maximum(np.asarray(m_h2, float), 0.0)
    rd = np.maximum(np.asarray(disk_radius_kpc, float), 0.05) * 1e3  # pc
    r_half = DISK_A * rd
    x = r_half / rd
    f_star = 1.0 - (1.0 + x) * np.exp(-x)  # H2: the stars' profile
    d_hi = 10 ** (0.506 * np.log10(np.maximum(m_hi, 1.0)) - 3.293) * 1e3
    h_hi = np.where(m_hi > 1e6, _exp_scale_hi(m_hi, 0.5 * d_hi), rd)
    xh = r_half / h_hi
    f_hi = 1.0 - (1.0 + xh) * np.exp(-xh)
    sigma_h = (f_star * m_h2 + f_hi * m_hi) / (np.pi * r_half**2)  # Msun/pc^2
    n_h = sigma_h * MSUN / (M_P * (3.0857e18) ** 2)  # cm^-2
    m_h = m_hi + m_h2
    d_per_h = np.where(
        m_h > 0,
        np.asarray(delta, float)
        * np.asarray(m_cold, float)
        / np.maximum(m_h, 1.0),
        0.0,
    )
    return AV_PER_NH / 1.086 * n_h * d_per_h / DTG_MW


def cos_inclination(spin, los) -> np.ndarray:
    """|cos i| between each galaxy's spin axis and the line of sight
    (random orientation where the spin is zero)."""
    s = np.asarray(spin, float)
    los = np.asarray(los, float)
    ns = np.linalg.norm(s, axis=1)
    nl = np.linalg.norm(los, axis=1)
    c = np.abs(np.sum(s * los, axis=1)) / np.maximum(ns * nl, 1e-30)
    rnd = np.random.default_rng(0).random(len(c))
    return np.where(ns > 0, c, rnd)


def ism_transmission(wave, tau_v, cos_i) -> np.ndarray:
    """(n, n_wave) diffuse-ISM transmission: dust mixed with the stars in
    a slab (Charlot & Fall 2000 curve)."""
    t = np.outer(tau_v / np.maximum(cos_i, 0.05), (wave / 5500.0) ** -N_ISM)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        tr = np.where(
            t > 1e-6, -np.expm1(-t) / np.maximum(t, 1e-30), 1.0 - 0.5 * t
        )
    return tr


def bc_transmission(wave, tau_v) -> np.ndarray:
    """(n, n_wave) birth-cloud transmission (a screen)."""
    tau_bc = tau_v * (1 - MU_ISM) / MU_ISM
    return np.exp(-np.outer(tau_bc, (wave / 5500.0) ** -N_BC))


_EMISSION: dict = {}


def emission_template(wave: np.ndarray) -> np.ndarray:
    """Dust emission per unit absorbed luminosity (L_nu per L_sun, on
    `wave`): the Draine & Li (2007) model as FSPS has it (U_min = 1,
    q_PAH = 3.5%, gamma = 0.01), normalised to integrate to 1 over
    frequency. Energy balance (da Cunha, Charlot & Elbaz 2008, MNRAS 388,
    1595): each galaxy re-emits exactly what its dust absorbed."""
    key = len(wave)
    if key not in _EMISSION:
        import fsps

        kw = dict(zcontinuous=1, sfh=0, imf_type=1, dust_type=2, dust2=1.0)
        w, with_em = fsps.StellarPopulation(
            add_dust_emission=True, **kw
        ).get_spectrum(tage=0.1)
        _, without = fsps.StellarPopulation(
            add_dust_emission=False, **kw
        ).get_spectrum(tage=0.1)
        em = np.clip(np.asarray(with_em) - np.asarray(without), 0.0, None)
        em = np.interp(wave, np.asarray(w), em)
        _EMISSION[key] = em / np.dot(em, frequency_weights(wave))
    return _EMISSION[key]


def frequency_weights(wave: np.ndarray) -> np.ndarray:
    """Weights w with L = sum(L_nu * w) = integral L_nu d(nu), on a
    wavelength grid in Angstrom."""
    nu = 2.99792458e18 / np.asarray(wave, float)
    w = np.zeros_like(nu)
    d = np.abs(np.diff(nu))
    w[:-1] += 0.5 * d
    w[1:] += 0.5 * d
    return w
