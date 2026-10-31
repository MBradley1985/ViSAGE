"""Light that isn't stars in galaxies: AGN and intracluster stars, as extra
magnitudes on a lightcone that has its photometry.

AGN. SAGE26 gives each black hole's accretion, so its LAGN. Above 1% of
Eddington, where the flow is a thin disk (agn.py), the continuum is the mean
quasar spectrum of Shen et al. (2020, MNRAS 495, 3252), scaled to LAGN with
their B-band correction. Fainter flows have no thin disk, so only their narrow
lines. A share of quasars is hidden: the column density is drawn from Ueda et
al. (2014, ApJ 786, 104), repeatably from the galaxy's id, as Shen et al. use
it, with A_B/N_H = 8.47e-22 cm^2 scaled by their dust-to-gas ratio of 0.78. The
wavelength dependence, (lambda / 4400 A)^-1.3, stands in for their Pei (1992)
curve, below 1 micron: beyond it the template is the torus's own emission,
which any quasar has, so absorbed light isn't re-emitted on top of it.

Intracluster stars. SAGE26 gives their mass and metals on each central, and
when they were deposited, not when they formed. They're one population of
SAGE26's metallicity, at the mass-weighted age of the central's own stars, or
the age of the deposit if that's older: they can't be younger than that. The
stars formed M / (1 - R) of mass, as in the photometry.

Written as agn_mag_obs_<band> and ics_mag_obs_<band>, with AGNObscured. The
galaxy's mag_obs_<band> stay as they are.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np

from visage.sed import agn as ag
from visage.sed import igm
from visage.sed.cosmology import MPC_TO_CM, age_at_scale_factor
from visage.sed.filters import filter_transmission
from visage.sed.photometry import L_SUN_ERG_S
from visage.system import native_path

SED_FILE = Path(__file__).parent / "data" / "quasar_sed.npz"
L_SUN_LBOL = 3.826e33  # erg/s, as Shen et al.'s fit
A_B_PER_NH = 8.47e-22 * 0.78  # mag cm^2
C_ANG = 2.99792458e18
F_CTK = 1.0  # Ueda et al. 2014
EPSILON = 1.7
AGE_NODES = np.geomspace(0.3, 13.5, 16)  # Gyr
LOGZSOL_NODES = np.array([-2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.3])
Z_SUN_FSPS = 0.0142


def b_band_share(l_bol) -> np.ndarray:
    """nu L_nu at 4400 A over L_bol (Shen et al. 2020, table 1)."""
    x = np.log10(np.asarray(l_bol, float) / L_SUN_LBOL) - 10.0
    return 1 / (
        3.75876730 * 10 ** (-0.36057087 * x)
        + 9.82954354 * 10 ** (-6.29078046e-3 * x)
    )


def hard_xray(l_bol) -> np.ndarray:
    """L(2-10 keV), erg/s (Shen et al. 2020, table 1)."""
    x = np.log10(np.asarray(l_bol, float) / L_SUN_LBOL) - 10.0
    return l_bol / (
        4.07349835 * 10 ** (-0.02553868 * x)
        + 12.5996205 * 10 ** (0.27750559 * x)
    )


def absorbed_share(l_x, z) -> np.ndarray:
    """psi, the share of Compton-thin quasars with log N_H >= 22."""
    psi0 = 0.43 * (1 + np.minimum(z, 2.0)) ** 0.48
    psi = psi0 - 0.24 * (np.log10(l_x) - 43.75)
    return np.clip(psi, 0.2, 0.84)


def column_density(l_x, z, u) -> np.ndarray:
    """log N_H from the Ueda et al. (2014) distribution, for u in [0, 1)."""
    psi = absorbed_share(l_x, z)
    ctk = F_CTK * psi / 2
    total = 1 + ctk
    thin = (1 - psi) / total  # log N_H < 22
    mid = psi / (1 + EPSILON) / total  # 22-23
    top = EPSILON * psi / (1 + EPSILON) / total  # 23-24
    out = np.full(np.shape(u), 25.0)
    out = np.where(u < thin + mid + top, 23.5, out)
    out = np.where(u < thin + mid, 22.5, out)
    return np.where(u < thin, 20.0, out)


def continuum(wave, l_bol, log_nh) -> np.ndarray:
    """L_nu (erg/s/Hz) at rest wavelengths `wave` (Angstrom), n x len(wave),
    through the absorbing column."""
    with np.load(SED_FILE) as d:
        w, shape = d["wave"].astype(float), d["nulnu_b"].astype(float)
    s = np.interp(np.log10(wave), np.log10(w), shape, left=0.0, right=0.0)
    l_bol = np.atleast_1d(l_bol)
    nu_l_nu = (l_bol * b_band_share(l_bol))[:, None] * s
    log_nh = np.atleast_1d(log_nh)[:, None]
    a_b = np.where(log_nh >= 22, A_B_PER_NH * 10.0**log_nh, 0.0)
    tau = a_b / 1.086 * (wave / 4400.0) ** -1.3
    # Beyond 1 micron the template is the dust's own emission.
    tau = np.where(wave < 1.0e4, tau, 0.0)
    return nu_l_nu * wave / C_ANG * np.exp(-tau)


def _ab_mag(wave, l_nu, z, d_l_cm, band) -> float:
    """Observed AB magnitude of L_nu (erg/s/Hz) at rest `wave`."""
    lam, t = filter_transmission(band)
    w_obs = wave * (1 + z)
    tr = np.interp(w_obs, lam, t, left=0.0, right=0.0)
    if not tr.any():
        return np.inf
    f = (1 + z) * l_nu / (4 * np.pi * d_l_cm**2) * igm.transmission(wave, z)
    top = np.trapezoid(f * tr / w_obs, w_obs)
    if top <= 0:
        return np.inf
    return -2.5 * np.log10(top / np.trapezoid(tr / w_obs, w_obs)) - 48.6


def stellar_table():
    """Rest wavelengths and L_nu (erg/s/Hz) per Msun formed, by metallicity
    and age, from FSPS."""
    import fsps

    sp = fsps.StellarPopulation(zcontinuous=1, imf_type=1, sfh=0)
    table = []
    for lz in LOGZSOL_NODES:
        sp.params["logzsol"] = float(lz)
        row = [sp.get_spectrum(tage=float(a), peraa=False) for a in AGE_NODES]
        table.append([r[1] for r in row])
        wave = row[0][0]
    return wave, np.asarray(table) * L_SUN_ERG_S


def central_age_gyr(f, rows, t_snap, offset) -> np.ndarray:
    """Mass-weighted age of the stars of galaxies `rows`, from SFHMassDisk
    and SFHMassBulge, in bins between snapshots."""
    hist = f["SFHMassDisk"][rows] + f["SFHMassBulge"][rows]
    snap = f["SnapNum"][rows]
    n = hist.shape[1]
    index = np.arange(n) + 1 - offset  # see sfh_step_offset
    lo = t_snap[np.clip(index - 1, 0, len(t_snap) - 1)]
    hi = t_snap[np.clip(index, 0, len(t_snap) - 1)]
    mid = 0.5 * (lo + hi)
    age = np.clip(t_snap[snap][:, None] - mid, 0.0, None)
    return np.sum(hist * age, 1) / np.maximum(hist.sum(1), 1e-30)


def add_components(path: str | Path, alist: str | Path | None = None) -> None:
    """Write the AGN and intracluster magnitudes of every band `path` has."""
    from visage.io.galaxy_reader import sfh_step_offset
    from visage.sed.spectrum import find_alist, run_settings

    path = Path(path)
    run_settings(path)
    al = find_alist(path, alist)
    with h5py.File(path, "r", locking=False) as f:
        bands = sorted(
            k[len("mag_obs_") :] for k in f if k.startswith("mag_obs_")
        )
        sim = f["SageOutputHeader"]["Simulation"].attrs
        run = f["SageOutputHeader"]["Runtime"].attrs
        hub = float(sim["hubble_h"])
        om, ol = float(sim["omega_matter"]), float(sim["omega_lambda"])
        recycle = float(run["RecycleFraction"])
        unit_gyr = (
            float(run["UnitLength_in_cm"])
            / float(run["UnitVelocity_in_cm_per_s"])
            / 3.15576e16
        )
        n = len(f["ra"])
        z = f["redshift_observed"][:].astype(float)
        d_l = (1 + z) * f["distance"][:] / hub * MPC_TO_CM
        l_agn = f["LAGN"][:].astype(float) if "LAGN" in f else np.zeros(n)
        edd = (
            f["EddingtonRatio"][:].astype(float)
            if "EddingtonRatio" in f
            else np.zeros(n)
        )
        gid = f["GalaxyIndex"][:]
        snap = f["SnapNum"][:]
        ics = f["IntraClusterStars"][:].astype(float) * 1e10 / hub
        mz = f["MetalsIntraClusterStars"][:].astype(float) * 1e10 / hub
        scales = np.loadtxt(al)
        t_snap = age_at_scale_factor(scales, hub, om, ol)
        ics_rows = np.flatnonzero(ics > 0)
        m_t = f["ICS_sum_mt"][:][ics_rows].astype(float)
        dep = (f["ICS_disrupt"][:] + f["ICS_accrete"][:])[ics_rows]
        # Mass-weighted lookback (SAGE26's time) of the deposits to z = 0.
        look = m_t / np.maximum(dep, 1e-30) * unit_gyr / hub
        deposited = look - (t_snap[-1] - t_snap[snap[ics_rows]])
        offset = (
            sfh_step_offset(f["SFHMassDisk"][ics_rows], snap[ics_rows])
            if ics_rows.size
            else 0
        )
        own = (
            central_age_gyr(f, ics_rows, t_snap, offset)
            if ics_rows.size
            else np.zeros(0)
        )

    agn = np.full((n, len(bands)), np.inf, dtype=np.float32)
    obscured = np.zeros(n, np.float32)
    hot = np.flatnonzero((edd >= ag.MDOT_CRIT) & (l_agn > 0))
    if hot.size:
        with np.load(SED_FILE) as d:
            wave = d["wave"].astype(float)
        u = ag.burst_phase(gid[hot], snap[hot] + 1000)
        log_nh = column_density(hard_xray(l_agn[hot]), z[hot], u)
        obscured[hot] = log_nh >= 22
        l_nu = continuum(wave, l_agn[hot], log_nh)
        for j, b in enumerate(bands):
            agn[hot, j] = [
                _ab_mag(wave, l_nu[i], z[r], d_l[r], b)
                for i, r in enumerate(hot)
            ]

    light = np.full((n, len(bands)), np.inf, dtype=np.float32)
    if ics_rows.size:
        wave, table = stellar_table()
        lz = np.log10(
            np.maximum(mz[ics_rows] / ics[ics_rows], 1e-6) / Z_SUN_FSPS
        )
        iz = np.abs(lz[:, None] - LOGZSOL_NODES).argmin(1)
        age = np.maximum(own, deposited)
        ia = np.abs(np.log(age[:, None] + 1e-3) - np.log(AGE_NODES)).argmin(1)
        formed = ics[ics_rows] / (1 - recycle)
        for j, b in enumerate(bands):
            for i, r in enumerate(ics_rows):
                light[r, j] = _ab_mag(
                    wave, formed[i] * table[iz[i], ia[i]], z[r], d_l[r], b
                )

    with h5py.File(path, "a") as f:
        for j, b in enumerate(bands):
            for name, data in (("agn", agn), ("ics", light)):
                key = f"{name}_mag_obs_{b}"
                if key in f:
                    del f[key]
                f[key] = data[:, j]
        if "AGNObscured" in f:
            del f["AGNObscured"]
        f["AGNObscured"] = obscured
        hdr = f["PhotometryHeader"].attrs
        hdr["AGNContinuum"] = "Shen+20 mean SED, Ueda+14 columns, above 1% Edd"
        hdr["IntraclusterStars"] = "SAGE26 mass, Z; age of central or deposit"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="visage-components",
        description="Add AGN and intracluster light to a lightcone.",
    )
    p.add_argument("--input", required=True, metavar="FILE")
    p.add_argument("--alist", default=None, metavar="FILE")
    a = p.parse_args(argv)
    add_components(native_path(a.input), a.alist)


if __name__ == "__main__":
    main()
