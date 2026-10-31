from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from visage.io.galaxy_reader import GalaxySnapshot
from visage.io.snapshot_table import SnapshotTable


def _age_lcdm(
    a: np.ndarray | float,
    h: float = 0.673,
    Om: float = 0.315,
    OL: float = 0.685,
) -> np.ndarray:
    """Cosmic age (Gyr) at scale factor a in flat ΛCDM (Planck 2018 defaults)."""
    H0_inv = 9.778 / max(h, 0.01)  # Gyr
    a = np.asarray(a, dtype=np.float64)
    return (
        (2.0 / 3.0)
        / np.sqrt(OL)
        * np.arcsinh(np.sqrt(OL / Om) * a**1.5)
        * H0_inv
    )


def _ffb_label(flag: int) -> str:
    return "FFB" if int(flag) != 0 else "Non-FFB"


def _cgm_label(flag: int) -> str:
    return "CGM (cold)" if int(flag) == 0 else "Hot atmosphere"


def _sfh_age_gyr(
    hdf5_path: str | Path,
    snap_num: int,
    raw_index: int,
    snap_table: SnapshotTable,
    h: float,
) -> float | None:
    """Mass-weighted stellar age (Gyr) computed from SFHMassDisk + SFHMassBulge.

    Returns None if the SFH arrays aren't available.  raw_index is the
    galaxy's position in the unfiltered HDF5 dataset; the caller must
    translate downsample/cut indices back to this.
    """
    from visage.io.sage_files import open_snapshot

    try:
        # raw_index is a row of the whole run (MPI rank files joined).
        with open_snapshot(hdf5_path, snap_num) as grp:
            if (
                grp is None
                or "SFHMassDisk" not in grp
                or "SFHMassBulge" not in grp
            ):
                return None
            sfh_d = np.asarray(
                grp["SFHMassDisk"][raw_index, :], dtype=np.float64
            )
            sfh_b = np.asarray(
                grp["SFHMassBulge"][raw_index, :], dtype=np.float64
            )
            sfh = sfh_d + sfh_b
    except Exception:
        return None
    total = sfh.sum()
    if total <= 0:
        return None
    # Each SFH bin maps to a snapshot; use the midpoint scale factor between
    # consecutive snapshots to compute the lookback time of formation.
    n_bins = sfh.size
    n_snaps = snap_table.count
    n = min(n_bins, n_snaps)
    a_bin = snap_table.scale_factors[:n]
    age_bin = _age_lcdm(a_bin, h=h)
    age_now = _age_lcdm(snap_table.snap_to_a(snap_num), h=h)
    lookback = age_now - age_bin
    return float(np.sum(sfh[:n] * lookback) / total)


# -- lightcones: where a galaxy is on the sky, how it looks, its dust ----

# The bands the card quotes, first available: (rest-frame colour pair,
# apparent magnitude band).
_CARD_BANDS = (
    ("sdss_g", "sdss_r"),
    ("des_g", "des_r"),
    ("lsst_g", "lsst_r"),
    ("ps1_g", "ps1_r"),
)
# Emission lines in the order the card lists them.
_LINES = (
    ("Halpha", "Hα"),
    ("Hbeta", "Hβ"),
    ("OIII5007", "[OIII] 5007"),
    ("NII6584", "[NII] 6584"),
    ("OII3727", "[OII] 3727"),
    ("SII6716_6731", "[SII] 6716+31"),
)


def _x(galaxies, name: str, i: int) -> float | None:
    col = galaxies.extra.get(name) if galaxies.extra else None
    if col is None or i >= len(col):
        return None
    v = float(col[i])
    return v if np.isfinite(v) else None


def attenuation_v(tau_v: float, cos_i: float) -> float:
    """A_V (mag) of the diffuse ISM at inclination i: dust mixed with the
    stars in a slab, as the photometry has it (visage.sed.dust,
    Charlot & Fall 2000)."""
    t = max(tau_v, 0.0) / max(cos_i, 0.05)
    if t <= 1e-6:
        return 0.0
    return float(-2.5 * np.log10(-np.expm1(-t) / t))


def cone_summary(galaxies: GalaxySnapshot, i: int) -> list:
    """(label, value) rows for a lightcone galaxy's card: redshift and
    distance, then (with synthetic photometry) its brightness, colour and
    dust."""
    out = []
    z_obs = _x(galaxies, "redshift_observed", i)
    z_cos = (
        float(galaxies.redshifts[i])
        if galaxies.redshifts is not None
        else None
    )
    if z_obs is not None or z_cos is not None:
        out.append(
            ("Redshift", f"{z_obs if z_obs is not None else z_cos:.4f}")
        )
    d = _x(galaxies, "distance", i)
    if d is None:
        d = float(np.linalg.norm(galaxies.positions[i]))
    out.append(("Distance", f"{d:.1f} Mpc/h"))
    mags = galaxies.sed_mags or {}
    for blue, red in _CARD_BANDS:
        obs, rest = f"mag_obs_{red}", f"mag_rest_{red}"
        rest_b = f"mag_rest_{blue}"
        if obs not in mags and rest not in mags:
            continue
        from visage.sed.filters import band_label

        name = band_label(red).split()[-1]
        if obs in mags and np.isfinite(mags[obs][i]):
            out.append((f"{name} (apparent)", f"{mags[obs][i]:.2f} AB"))
        if rest in mags and np.isfinite(mags[rest][i]):
            out.append((f"M_{name}", f"{mags[rest][i]:.2f} AB"))
            if rest_b in mags and np.isfinite(mags[rest_b][i]):
                gb = band_label(blue).split()[-1]
                out.append(
                    (
                        f"{gb} − {name} (rest)",
                        f"{mags[rest_b][i] - mags[rest][i]:.2f}",
                    )
                )
        break
    av = _dust_row(galaxies, i)
    if av is not None:
        out.append(("A_V (dust)", av))
    return out


def _dust_row(galaxies, i: int) -> str | None:
    """The card's dust line, as the photometry made it (None without
    photometry, or without the values it needs)."""
    how, tau_screen = galaxies.sed_dust()
    if how == "charlot_fall":
        tau = _x(galaxies, "TauV_ISM", i)
        ci = _x(galaxies, "CosInclination", i)
        if tau is None or ci is None:
            return None
        inc = np.degrees(np.arccos(np.clip(ci, 0.0, 1.0)))
        return f"{attenuation_v(tau, ci):.2f} mag at i={inc:.0f}°"
    if how == "calzetti":
        return f"{1.086 * tau_screen:.2f} mag (one screen, all galaxies)"
    if how == "none":
        return "none (photometry made without dust)"
    return None


def dust_details(galaxies, i: int, h: float) -> dict:
    """A run's own dust (DustySAGEMode), without the rows that are zero."""
    cold = _x(galaxies, "ColdDust", i)
    if cold is None:
        return {}
    out = {}
    mass = 1e10 / max(h, 1e-6)
    for key, label in (
        ("ColdDust", "Dust (cold)"),
        ("HotDust", "Dust (hot)"),
        ("CGMDust", "Dust (CGM)"),
        ("EjectedDust", "Dust (ejected)"),
    ):
        v = _x(galaxies, key, i)
        if v:
            out[label] = f"{v * mass:.2e} Msun"
    gas = float(galaxies.cold_gas[i])  # (already Msun)
    if cold and gas > 0:
        out["Dust-to-gas"] = f"{cold * mass / gas:.2e}"
    metals = float(galaxies.metals_cold_gas[i])
    if cold and metals > 0:
        out["Dust-to-metals"] = f"{cold * mass / metals:.2f}"
    for key, label in (
        ("DustFormationRate", "Dust made"),
        ("DustGrowthRate", "Dust grown"),
        ("DustDestructionRate", "Dust destroyed"),
    ):
        v = _x(galaxies, key, i)
        if v:
            out[label] = f"{v:.3g} Msun/yr"
    return out


def cone_details(
    galaxies: GalaxySnapshot, i: int, hubble_h: float = 0.7
) -> dict:
    """Every lightcone-only property of galaxy i, for "All properties":
    sky position, dust, AGN, emission lines and every magnitude."""
    info: dict = {}
    ra, dec = _x(galaxies, "ra", i), _x(galaxies, "dec", i)
    if ra is not None and dec is not None:
        info["RA, Dec"] = f"{ra:.4f}°, {dec:+.4f}°"
    z_obs = _x(galaxies, "redshift_observed", i)
    if z_obs is not None:
        info["Redshift (observed)"] = f"{z_obs:.5f}"
    if galaxies.redshifts is not None:
        info["Redshift (cosmological)"] = f"{galaxies.redshifts[i]:.5f}"
    if galaxies.snap_nums is not None:
        info["Snapshot"] = str(int(galaxies.snap_nums[i]))
    d = _x(galaxies, "distance", i)
    if d is not None:
        info["Comoving distance"] = f"{d:.2f} Mpc/h"
    how = galaxies.sed_dust()[0]
    if how == "charlot_fall":
        # (Columns of an older run with another dust setting are left
        # in the file: only this one's are shown.)
        own = dust_details(galaxies, i, hubble_h)
        info.update(own)
        for key, label, fmt in (
            ("DustMassCold", "Dust mass (cold ISM)", "{:.2e} Msun"),
            ("DustToGas", "Dust-to-gas", "{:.2e}"),
            ("TauV_ISM", "τ_V face-on (ISM)", "{:.3f}"),
        ):
            if own and key != "TauV_ISM":
                continue
            v = _x(galaxies, key, i)
            if v is not None:
                info[label] = fmt.format(v)
        tau = _x(galaxies, "TauV_ISM", i)
        ci = _x(galaxies, "CosInclination", i)
        if ci is not None:
            info["Inclination"] = (
                f"{np.degrees(np.arccos(np.clip(ci, 0.0, 1.0))):.1f}°"
            )
            if tau is not None:
                info["A_V (ISM, at i)"] = f"{attenuation_v(tau, ci):.3f} mag"
    elif how is not None:
        info["Dust"] = _dust_row(galaxies, i)
    phot = galaxies.photometry or {}
    dust_ir = "re-emitted" in str(phot.get("Dust", ""))
    lines = str(phot.get("NebularEmission", "none")).lower() != "none"
    for key, label, fmt, on in (
        ("LDust", "Dust luminosity (IR)", "{:.2e} Lsun", dust_ir),
        ("LAGN", "AGN luminosity", "{:.2e} erg/s", lines),
        ("EddingtonRatio", "Eddington ratio", "{:.2e}", lines),
    ):
        v = _x(galaxies, key, i) if on else None
        if v is not None and v > 0:
            info[label] = fmt.format(v)
    if "Eddington ratio" in info:
        # SAGE26's black holes start at zero: one born this step "accreted"
        # all of its mass at once, and its Eddington ratio only reflects the
        # step's length.
        q = _x(galaxies, "QuasarModeBHaccretionMass", i)
        bh = float(galaxies.bh_mass[i])
        if q is not None and bh > 0 and q * 1e10 / hubble_h >= 0.99 * bh:
            info["Eddington ratio"] += " (black hole born this step)"
    path = getattr(galaxies, "source_path", "") if lines else ""
    raw = (
        int(galaxies.sage_indices[i])
        if galaxies.sage_indices is not None
        else i
    )
    if path:
        try:
            from visage.io.lightcone_reader import _open_ro

            with _open_ro(Path(path)) as f:
                for key, label in _LINES:
                    if f"LineFlux_{key}" in f:
                        v = float(f[f"LineFlux_{key}"][raw])
                        if np.isfinite(v) and v > 0:
                            info[f"{label} flux"] = f"{v:.2e} erg/s/cm²"
        except Exception:
            pass
    mags = galaxies.sed_mags or {}
    if mags:
        from visage.sed.filters import band_label, wavelength_order

        for frame, word in (("obs", "apparent"), ("rest", "absolute")):
            keys = sorted(
                (k for k in mags if k.startswith(f"mag_{frame}_")),
                key=lambda k: wavelength_order(k.split("_", 2)[2]),
            )
            for k in keys:
                v = float(mags[k][i])
                if np.isfinite(v):
                    band = band_label(k.split("_", 2)[2])
                    info[f"{band} ({word})"] = f"{v:.2f} AB"
    return info


def cone_age_gyr(galaxies: GalaxySnapshot, i: int, snap_table, h: float):
    """Mass-weighted stellar age (Gyr) of a lightcone galaxy from its SFH
    (as _sfh_age_gyr, at its own snapshot); None without one."""
    if not getattr(galaxies, "has_sfh", False) or snap_table is None:
        return None
    from visage.io.galaxy_reader import find_sfh_datasets
    from visage.io.lightcone_reader import _open_ro

    raw = (
        int(galaxies.sage_indices[i])
        if galaxies.sage_indices is not None
        else i
    )
    try:
        with _open_ro(Path(galaxies.source_path)) as f:
            disk, bulge = find_sfh_datasets(f)
            if disk is None or bulge is None:
                return None
            sfh = np.asarray(f[disk][raw, :], float) + np.asarray(
                f[bulge][raw, :], float
            )
    except Exception:
        return None
    total = sfh.sum()
    if total <= 0:
        return None
    n = min(sfh.size, snap_table.count)
    age_bin = _age_lcdm(snap_table.scale_factors[:n], h=h)
    age_now = _age_lcdm(snap_table.snap_to_a(galaxies.snap_of(i)), h=h)
    lookback = np.maximum(age_now - age_bin, 0.0)
    return float(np.sum(sfh[:n] * lookback) / total)


def build_galaxy_info(
    galaxies: GalaxySnapshot,
    fields_available: dict[str, bool],
    idx: int,
    snap_table: SnapshotTable,
    hubble_h: float,
    hdf5_path: str | Path | None = None,
    sage_indices: np.ndarray | None = None,
) -> dict:
    """Return a display-friendly dict of properties for galaxy at `idx`.

    Parameters
    ----------
    galaxies          : current snapshot (post-filter; idx is into THIS array)
    fields_available  : dict[ui_key, bool] from Model.fields_available
    idx               : index into galaxies (the masked subset rendered in the scene)
    snap_table        : the model's SnapshotTable (for redshift/scale-factor lookups)
    hubble_h          : H/100 used by SAGE for unit conversions / cosmology
    hdf5_path         : SAGE HDF5 path, for on-demand SFH read (Age)
    sage_indices      : np.ndarray mapping galaxies.<arr> index → HDF5 raw row
                        (None if downsample preserved order; used to fetch SFH)
    """
    if galaxies.count == 0 or idx < 0 or idx >= galaxies.count:
        return {}

    is_central = bool(galaxies.gal_type[idx] == 0)
    gal_type_str = "Central" if is_central else "Satellite"
    # `mvir` in the snapshot is raw 10¹⁰ Msun/h; everything else is already Msun.
    mvir = float(galaxies.mvir[idx]) * 1.0e10 / max(hubble_h, 1e-6)
    sm = float(galaxies.stellar_mass[idx])
    ssfr = float(galaxies.ssfr[idx])
    bm = float(galaxies.bulge_mass[idx])
    cg = float(galaxies.cold_gas[idx])
    bt = bm / sm if sm > 0 else 0.0

    bt_label = f"{bt:.2f}"
    if bt <= 0.0:
        bt_label += "  (pure disk)"
    elif bt >= 0.7:
        bt_label += "  (bulge-dom.)"

    info: dict = {
        "GalaxyIndex": "—",
        "Type": gal_type_str,
        "Halo Mvir": f"{mvir:.2e} Msun",
        "Stellar Mass": f"{sm:.2e} Msun",
        "sSFR": f"{ssfr:.2e} yr^-1",
        "Cold Gas": f"{cg:.2e} Msun",
        "Bulge / Total": bt_label,
    }

    if fields_available.get("galaxy_id", False):
        info["GalaxyIndex"] = str(int(galaxies.galaxy_id[idx]))

    if fields_available.get("bh_mass", False):
        bh = float(galaxies.bh_mass[idx])
        info["BH Mass"] = f"{bh:.2e} Msun" if bh > 0 else "0  (no central BH)"

    if fields_available.get("h2_mass", False):
        # `h2_mass` in the snapshot is already Msun (converted by the reader).
        h2 = float(galaxies.h2_mass[idx])
        info["H2 Mass"] = f"{h2:.2e} Msun" if h2 > 0 else "0  (no H2)"

    if fields_available.get("cgm_regime", False):
        regime = int(galaxies.cgm_regime[idx])
        info["Gas Regime"] = _cgm_label(regime)
        # Show whichever gas-mass fields are non-zero for this galaxy;
        # if both are present (shouldn't happen often) show both.
        has_cgm = fields_available.get("cgm_gas", False)
        has_hot = fields_available.get("hot_gas", False)
        if has_cgm:
            cgm_m = float(galaxies.cgm_gas[idx])
            if cgm_m > 0:
                info["CGM Gas"] = f"{cgm_m:.2e} Msun"
        if has_hot:
            hot_m = float(galaxies.hot_gas[idx])
            if hot_m > 0:
                info["Hot Gas"] = f"{hot_m:.2e} Msun"
        # If the regime flag says CGM/Hot but neither mass is non-zero, say so.
        if has_cgm and has_hot:
            if regime == 0 and float(galaxies.cgm_gas[idx]) <= 0:
                info["CGM Gas"] = "0"
            elif regime == 1 and float(galaxies.hot_gas[idx]) <= 0:
                info["Hot Gas"] = "0"

    if fields_available.get("ffb_regime", False):
        info["FFB Regime"] = _ffb_label(int(galaxies.ffb_regime[idx]))

    # Group / environment classification
    if fields_available.get("central_id", False):
        from visage.utils.group_info import (
            classify_members,
            host_mass,
            member_indices,
        )

        members = member_indices(galaxies, idx)
        n_members = len(members)
        env = classify_members(
            galaxies, members, host_mass(galaxies, members, hubble_h)
        )
        if n_members == 1:
            members_str = f"{env}"
        else:
            others = n_members - 1
            members_str = (
                f"{env}, {others} other "
                + ("member" if others == 1 else "members")
                + (
                    ", target IS central"
                    if is_central
                    else ", target is satellite"
                )
            )
        info["Environment"] = members_str

    # Mass-weighted stellar age (Gyr), precomputed at load time from SFH bins
    age = (
        float(galaxies.mean_age[idx]) if galaxies.mean_age.size > idx else 0.0
    )
    if getattr(galaxies, "is_cone", False) and galaxies.has_sfh:
        # (A lightcone's ages aren't precomputed: from its SFH, now.)
        a = cone_age_gyr(galaxies, idx, snap_table, hubble_h)
        info["Approx Age"] = f"{a:.2f} Gyr" if a else "—"
    elif not fields_available.get("mean_age", False):
        # The catalogue has no star-formation histories (SAGE's
        # SaveFullSFH off), which the age is computed from.
        info["Approx Age"] = "Needs full SFH"
    else:
        info["Approx Age"] = f"{age:.2f} Gyr" if age > 0 else "—"

    if getattr(galaxies, "is_cone", False):
        info.update(cone_details(galaxies, idx, hubble_h))
    else:
        info.update(dust_details(galaxies, idx, hubble_h))

    return info
