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


def _classify_environment(host_mvir_msun: float, n_members: int) -> str:
    """Loose categorical label for the FOF environment of this galaxy."""
    if n_members <= 1:
        return "Isolated"
    if n_members == 2:
        return "Pair"
    if host_mvir_msun >= 1e14:
        return "Cluster"
    if host_mvir_msun >= 1e13:
        return "Group"
    return "Small group"


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
        "GalaxyID": "—",
        "Type": gal_type_str,
        "Halo Mvir": f"{mvir:.2e} Msun",
        "Stellar Mass": f"{sm:.2e} Msun",
        "sSFR": f"{ssfr:.2e} yr^-1",
        "Cold Gas": f"{cg:.2e} Msun",
        "Bulge / Total": bt_label,
    }

    if fields_available.get("galaxy_id", False):
        info["GalaxyID"] = str(int(galaxies.galaxy_id[idx]))

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
        cid = int(galaxies.central_id[idx])
        n_members = int(np.sum(galaxies.central_id == cid))
        # central_mvir is already in Msun (converted by the reader)
        host_mvir = (
            float(galaxies.central_mvir[idx])
            if fields_available.get("central_mvir", False)
            else mvir
        )
        env = _classify_environment(host_mvir, n_members)
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
    info["Approx Age"] = f"{age:.2f} Gyr" if age > 0 else "—"

    return info
