from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np


@dataclass
class GalaxySnapshot:
    positions: np.ndarray  # (N, 3) float32, Mpc/h
    stellar_mass: np.ndarray  # (N,)   float32, Msun
    mvir: np.ndarray  # (N,)   float32, 10^10 Msun/h (raw)
    rvir: np.ndarray  # (N,)   float32, Mpc/h (subhalo virial radius)
    sfr: np.ndarray  # (N,)   float32, Msun/yr
    ssfr: np.ndarray  # (N,)   float32, yr^-1
    cold_gas: np.ndarray  # (N,)   float32, Msun
    bulge_mass: np.ndarray  # (N,)   float32, Msun
    gal_type: np.ndarray  # (N,)   int32, 0=central 1+=satellite
    bh_mass: np.ndarray  # (N,)   float32, Msun
    ics_mass: np.ndarray  # (N,)   float32, Msun (intra-cluster stars)
    ffb_regime: np.ndarray  # (N,)   int32, FFB regime flag
    cgm_regime: np.ndarray  # (N,)   int32, 0=cold 1=hot (Regime field)
    central_mvir: np.ndarray  # (N,)   float32, Msun (host FOF Mvir)
    h2_mass: np.ndarray  # (N,)   float32, Msun
    cgm_gas: np.ndarray  # (N,)   float32, Msun
    hot_gas: np.ndarray  # (N,)   float32, Msun
    galaxy_id: np.ndarray  # (N,)   int64
    central_id: np.ndarray  # (N,)   int64
    time_of_infall: np.ndarray  # (N,)   int32
    mean_age: np.ndarray  # (N,)   float32, Gyr
    # ── Halo structural (per-galaxy from merger trees) ────────────────
    len_particles: np.ndarray  # (N,)   int32,   DM particle count
    vmax: np.ndarray  # (N,)   float32, km/s
    concentration: np.ndarray  # (N,)   float32, NFW concentration
    spin: np.ndarray  # (N,)   float32, dimensionless
    # ── Galaxy structural ─────────────────────────────────────────────
    disk_radius: np.ndarray  # (N,) float32, Mpc/h
    bulge_radius: np.ndarray  # (N,) float32, Mpc/h
    merger_bulge_mass: np.ndarray  # (N,) float32, Msun
    merger_bulge_radius: np.ndarray  # (N,) float32, Mpc/h
    instability_bulge_mass: np.ndarray  # (N,) float32, Msun
    instability_bulge_radius: np.ndarray  # (N,) float32, Mpc/h
    # ── Gas / outflows ────────────────────────────────────────────────
    h1_gas: np.ndarray  # (N,) float32, Msun  (HI gas)
    ejected_mass: np.ndarray  # (N,) float32, Msun
    outflow_rate: np.ndarray  # (N,) float32, Msun/yr
    mass_loading: np.ndarray  # (N,) float32, dimensionless
    cooling: np.ndarray  # (N,) float32, internal SAGE units
    heating: np.ndarray  # (N,) float32, internal SAGE units
    # ── SFR components ───────────────────────────────────────────────
    sfr_bulge: np.ndarray  # (N,) float32, Msun/yr (bulge SFR)
    sfr_disk: np.ndarray  # (N,) float32, Msun/yr (disk SFR)
    sfr_bulge_z: (
        np.ndarray
    )  # (N,) float32, dimensionless (bulge SFR metallicity)
    sfr_disk_z: (
        np.ndarray
    )  # (N,) float32, dimensionless (disk SFR metallicity)
    # ── Metals ───────────────────────────────────────────────────────
    metals_cold_gas: np.ndarray  # (N,) float32, Msun
    metals_stellar_mass: np.ndarray  # (N,) float32, Msun
    metals_bulge_mass: np.ndarray  # (N,) float32, Msun
    metals_hot_gas: np.ndarray  # (N,) float32, Msun
    metals_ejected_mass: np.ndarray  # (N,) float32, Msun
    metals_ics: np.ndarray  # (N,) float32, Msun
    metals_cgm_gas: np.ndarray  # (N,) float32, Msun
    # ─────────────────────────────────────────────────────────────────
    sage_indices: np.ndarray  # (N,) int64 — row indices in raw HDF5 snap group
    snap_num: int

    @property
    def count(self) -> int:
        return len(self.positions)

    @classmethod
    def empty(cls, snap_num: int) -> GalaxySnapshot:
        z = np.empty(0, dtype=np.float32)
        zi = np.empty(0, dtype=np.int32)
        zi64 = np.empty(0, dtype=np.int64)
        return cls(
            positions=np.empty((0, 3), dtype=np.float32),
            stellar_mass=z,
            mvir=z,
            rvir=z,
            sfr=z,
            ssfr=z,
            cold_gas=z,
            bulge_mass=z,
            gal_type=zi,
            bh_mass=z,
            ics_mass=z,
            central_mvir=z,
            ffb_regime=zi,
            cgm_regime=zi,
            h2_mass=z,
            cgm_gas=z,
            hot_gas=z,
            galaxy_id=zi64,
            central_id=zi64,
            time_of_infall=zi,
            mean_age=z,
            len_particles=zi,
            vmax=z,
            concentration=z,
            spin=z,
            disk_radius=z,
            bulge_radius=z,
            merger_bulge_mass=z,
            merger_bulge_radius=z,
            instability_bulge_mass=z,
            instability_bulge_radius=z,
            h1_gas=z,
            ejected_mass=z,
            outflow_rate=z,
            mass_loading=z,
            cooling=z,
            heating=z,
            sfr_bulge=z,
            sfr_disk=z,
            sfr_bulge_z=z,
            sfr_disk_z=z,
            metals_cold_gas=z,
            metals_stellar_mass=z,
            metals_bulge_mass=z,
            metals_hot_gas=z,
            metals_ejected_mass=z,
            metals_ics=z,
            metals_cgm_gas=z,
            sage_indices=np.empty(0, dtype=np.int64),
            snap_num=snap_num,
        )


VERBOSE = True


def load_galaxy_snapshot(
    hdf5_path: str | Path,
    snap_num: int,
    min_stellar_mass: float = 1.0e8,
    max_galaxies: int | None = None,
    hubble_h: float | None = None,
    scale_factors: np.ndarray | None = None,
    omega_m: float | None = None,
    omega_l: float | None = None,
) -> GalaxySnapshot:
    # Prefer the cosmology + scale factors that are written into the HDF5
    # header.  Arguments are now overrides / fallbacks only.
    from visage.io.sage_header import read_sage_header

    hdr = read_sage_header(hdf5_path)
    if hubble_h is None:
        hubble_h = hdr.get("hubble_h", 0.73)
    if omega_m is None:
        omega_m = hdr.get("omega_m", 0.315)
    if omega_l is None:
        omega_l = hdr.get("omega_l", 0.685)
    if scale_factors is None:
        scale_factors = hdr.get("scale_factors", None)
    """Load galaxy positions and properties for one snapshot from SAGE HDF5 output.

    Parameters
    ----------
    hdf5_path:        path to SAGE HDF5 output (e.g. model_0.hdf5)
    snap_num:         snapshot index
    min_stellar_mass: minimum stellar mass in Msun (after h correction)
    max_galaxies:     random downsample if more galaxies than this are found
    hubble_h:         Hubble parameter h (from par file)
    """
    hdf5_path = Path(hdf5_path)
    group_key = f"Snap_{snap_num}"

    if VERBOSE:
        print(f"  Galaxies: reading {hdf5_path.name} / {group_key}...")
    with h5py.File(hdf5_path, "r") as f:
        if group_key not in f:
            if VERBOSE:
                print(
                    f"  Galaxies: group {group_key} not found — empty snapshot"
                )
            return GalaxySnapshot.empty(snap_num)

        grp = f[group_key]

        def _get(field: str) -> np.ndarray:
            return np.array(grp[field])

        try:
            posx = _get("Posx")
            posy = _get("Posy")
            posz = _get("Posz")
            stellar_raw = _get("StellarMass")
            bulge_raw = _get("BulgeMass")
            cold_gas_raw = _get("ColdGas")
            mvir_raw = _get("Mvir")
            sfr_disk_arr = _get("SfrDisk")
            sfr_bulge_arr = _get("SfrBulge")
            gal_type = _get("Type").astype(np.int32)
        except KeyError as e:
            raise KeyError(
                f"Missing field {e} in {hdf5_path}:{group_key}"
            ) from e

        # Optional fields — present in current SAGE outputs but tolerate absence
        def _opt(field: str, default_dtype) -> np.ndarray:
            if field in grp:
                return np.array(grp[field])
            return np.zeros(len(posx), dtype=default_dtype)

        bh_raw = _opt("BlackHoleMass", np.float32)
        ics_raw = _opt("IntraClusterStars", np.float32)
        ffb_regime_raw = _opt("FFBRegime", np.int32).astype(np.int32)
        cgm_regime_raw = _opt("Regime", np.int32).astype(np.int32)
        cmvir_raw = _opt("CentralMvir", np.float32)
        rvir_raw = _opt("Rvir", np.float32)  # Mpc/h, no unit conversion
        h2_raw = _opt("H2gas", np.float32)
        cgm_gas_raw = _opt("CGMgas", np.float32)
        hot_gas_raw = _opt("HotGas", np.float32)
        galid_raw = _opt("GalaxyIndex", np.int64).astype(np.int64)
        cid_raw = _opt("CentralGalaxyIndex", np.int64).astype(np.int64)
        tinfall_raw = _opt("TimeOfInfall", np.int32).astype(np.int32)
        # Halo structural
        len_raw = _opt("Len", np.int32).astype(np.int32)
        vmax_raw = _opt("Vmax", np.float32)
        conc_raw = _opt("Concentration", np.float32)
        spin_raw = _opt("Spin", np.float32)
        # Galaxy structural
        disk_rad_raw = _opt("DiskRadius", np.float32)
        bulge_rad_raw = _opt("BulgeRadius", np.float32)
        mbm_raw = _opt("MergerBulgeMass", np.float32)
        mbr_raw = _opt("MergerBulgeRadius", np.float32)
        ibm_raw = _opt("InstabilityBulgeMass", np.float32)
        ibr_raw = _opt("InstabilityBulgeRadius", np.float32)
        # Gas / outflows
        h1_raw = _opt("H1gas", np.float32)
        ejected_raw = _opt("EjectedMass", np.float32)
        outflow_raw = _opt("OutflowRate", np.float32)
        massload_raw = _opt("MassLoading", np.float32)
        cooling_raw = _opt("Cooling", np.float32)
        heating_raw = _opt("Heating", np.float32)
        # SFR components (metallicity fields are dimensionless fractions)
        sfr_bulge_z_raw = _opt("SfrBulgeZ", np.float32)
        sfr_disk_z_raw = _opt("SfrDiskZ", np.float32)
        # Metals
        mcg_raw = _opt("MetalsColdGas", np.float32)
        msm_raw = _opt("MetalsStellarMass", np.float32)
        mbm_met_raw = _opt("MetalsBulgeMass", np.float32)
        mhg_raw = _opt("MetalsHotGas", np.float32)
        mem_raw = _opt("MetalsEjectedMass", np.float32)
        misc_raw = _opt("MetalsIntraClusterStars", np.float32)
        mcgm_raw = _opt("MetalsCGMgas", np.float32)

        # SFH arrays (one row per galaxy × ~64 time bins).  Only read if
        # present; the age computation tolerates absent SFH gracefully.
        has_sfh = ("SFHMassDisk" in grp) and ("SFHMassBulge" in grp)
        sfh_disk_raw = np.asarray(grp["SFHMassDisk"]) if has_sfh else None
        sfh_bulge_raw = np.asarray(grp["SFHMassBulge"]) if has_sfh else None

    # All mass fields stored as 10^10 Msun/h → convert to Msun
    f = 1.0e10 / hubble_h
    stellar_mass = stellar_raw.astype(np.float32) * f
    bulge_mass = bulge_raw.astype(np.float32) * f
    cold_gas = cold_gas_raw.astype(np.float32) * f
    bh_mass = bh_raw.astype(np.float32) * f
    ics_mass = ics_raw.astype(np.float32) * f
    central_mvir = cmvir_raw.astype(np.float32) * f
    h2_mass = h2_raw.astype(np.float32) * f
    cgm_gas = cgm_gas_raw.astype(np.float32) * f
    hot_gas = hot_gas_raw.astype(np.float32) * f
    sfr = (sfr_disk_arr + sfr_bulge_arr).astype(np.float32)
    sfr_bulge = sfr_bulge_arr.astype(np.float32)
    sfr_disk = sfr_disk_arr.astype(np.float32)
    ssfr = sfr / np.where(stellar_mass > 0, stellar_mass, np.inf)
    # New mass fields (10^10 Msun/h → Msun)
    h1_gas = h1_raw.astype(np.float32) * f
    ejected_mass = ejected_raw.astype(np.float32) * f
    merger_bulge_mass = mbm_raw.astype(np.float32) * f
    instability_bulge_mass = ibm_raw.astype(np.float32) * f
    metals_cold_gas = mcg_raw.astype(np.float32) * f
    metals_stellar_mass = msm_raw.astype(np.float32) * f
    metals_bulge_mass = mbm_met_raw.astype(np.float32) * f
    metals_hot_gas = mhg_raw.astype(np.float32) * f
    metals_ejected_mass = mem_raw.astype(np.float32) * f
    metals_ics = misc_raw.astype(np.float32) * f
    metals_cgm_gas = mcgm_raw.astype(np.float32) * f
    # Fields already in correct units (no conversion)
    disk_radius = disk_rad_raw.astype(np.float32)  # Mpc/h
    bulge_radius = bulge_rad_raw.astype(np.float32)  # Mpc/h
    merger_bulge_radius = mbr_raw.astype(np.float32)  # Mpc/h
    instability_bulge_radius = ibr_raw.astype(np.float32)  # Mpc/h
    vmax = vmax_raw.astype(np.float32)  # km/s
    concentration = conc_raw.astype(np.float32)  # dimensionless
    spin = spin_raw.astype(np.float32)  # dimensionless
    outflow_rate = outflow_raw.astype(np.float32)  # Msun/yr
    mass_loading = massload_raw.astype(np.float32)  # dimensionless
    cooling = cooling_raw.astype(np.float32)  # SAGE units
    heating = heating_raw.astype(np.float32)  # SAGE units
    sfr_bulge_z = sfr_bulge_z_raw.astype(np.float32)  # dimensionless
    sfr_disk_z = sfr_disk_z_raw.astype(np.float32)  # dimensionless

    mask = (stellar_mass > min_stellar_mass) & (mvir_raw > 0)
    indices = np.where(mask)[0]

    # max_galaxies=None → load every galaxy (no downsample). All snapshots are
    # preloaded, so there's no display cap.
    if max_galaxies is not None and len(indices) > max_galaxies:
        rng = np.random.default_rng(42)
        indices = rng.choice(indices, max_galaxies, replace=False)

    if VERBOSE:
        print(f"  Galaxies: {len(indices):,} loaded")
    positions = np.column_stack(
        [posx[indices], posy[indices], posz[indices]]
    ).astype(np.float32)

    # Mass-weighted stellar age, Gyr (one value per galaxy).  Needs SFH arrays
    # and scale factors; otherwise filled with zeros.
    mean_age = _compute_mean_ages(
        sfh_disk=sfh_disk_raw,
        sfh_bulge=sfh_bulge_raw,
        indices=indices,
        snap_num=snap_num,
        scale_factors=scale_factors,
        hubble_h=hubble_h,
        omega_m=omega_m,
        omega_l=omega_l,
    )

    return GalaxySnapshot(
        positions=positions,
        stellar_mass=stellar_mass[indices],
        mvir=mvir_raw[indices].astype(np.float32),
        rvir=rvir_raw[indices].astype(np.float32),
        sfr=sfr[indices],
        ssfr=ssfr[indices],
        cold_gas=cold_gas[indices],
        bulge_mass=bulge_mass[indices],
        gal_type=gal_type[indices],
        bh_mass=bh_mass[indices],
        ics_mass=ics_mass[indices],
        ffb_regime=ffb_regime_raw[indices],
        cgm_regime=cgm_regime_raw[indices],
        central_mvir=central_mvir[indices],
        h2_mass=h2_mass[indices],
        cgm_gas=cgm_gas[indices],
        hot_gas=hot_gas[indices],
        galaxy_id=galid_raw[indices],
        central_id=cid_raw[indices],
        time_of_infall=tinfall_raw[indices],
        mean_age=mean_age,
        len_particles=len_raw[indices],
        vmax=vmax[indices],
        concentration=concentration[indices],
        spin=spin[indices],
        disk_radius=disk_radius[indices],
        bulge_radius=bulge_radius[indices],
        merger_bulge_mass=merger_bulge_mass[indices],
        merger_bulge_radius=merger_bulge_radius[indices],
        instability_bulge_mass=instability_bulge_mass[indices],
        instability_bulge_radius=instability_bulge_radius[indices],
        h1_gas=h1_gas[indices],
        ejected_mass=ejected_mass[indices],
        outflow_rate=outflow_rate[indices],
        mass_loading=mass_loading[indices],
        cooling=cooling[indices],
        heating=heating[indices],
        sfr_bulge=sfr_bulge[indices],
        sfr_disk=sfr_disk[indices],
        sfr_bulge_z=sfr_bulge_z[indices],
        sfr_disk_z=sfr_disk_z[indices],
        metals_cold_gas=metals_cold_gas[indices],
        metals_stellar_mass=metals_stellar_mass[indices],
        metals_bulge_mass=metals_bulge_mass[indices],
        metals_hot_gas=metals_hot_gas[indices],
        metals_ejected_mass=metals_ejected_mass[indices],
        metals_ics=metals_ics[indices],
        metals_cgm_gas=metals_cgm_gas[indices],
        sage_indices=indices.astype(np.int64),
        snap_num=snap_num,
    )


def _age_lcdm(
    a: np.ndarray | float, h: float, om: float, ol: float
) -> np.ndarray:
    """Cosmic age (Gyr) at scale factor a, flat ΛCDM."""
    a = np.asarray(a, dtype=np.float64)
    H0_inv = 9.778 / max(h, 0.01)  # Gyr
    return (
        (2.0 / 3.0)
        / np.sqrt(ol)
        * np.arcsinh(np.sqrt(ol / om) * a**1.5)
        * H0_inv
    )


def _compute_mean_ages(
    sfh_disk: np.ndarray | None,
    sfh_bulge: np.ndarray | None,
    indices: np.ndarray,
    snap_num: int,
    scale_factors: np.ndarray | None,
    hubble_h: float,
    omega_m: float,
    omega_l: float,
) -> np.ndarray:
    """Mass-weighted stellar age (Gyr) per galaxy from SFH arrays + cosmology.

    Returns zeros if SFH arrays or scale factors aren't available.
    """
    if (
        sfh_disk is None
        or sfh_bulge is None
        or scale_factors is None
        or len(scale_factors) == 0
    ):
        return np.zeros(len(indices), dtype=np.float32)

    # Per-galaxy SFH = disk + bulge.  Shape (N, n_bins)
    sfh = sfh_disk[indices].astype(np.float64) + sfh_bulge[indices].astype(
        np.float64
    )

    # SFH bin i ↔ snapshot i in SAGE's standard layout.  Use the snapshot's
    # scale factor as the formation time of that bin.
    n_bins = sfh.shape[1] if sfh.ndim == 2 else 0
    if n_bins == 0:
        return np.zeros(len(indices), dtype=np.float32)
    n = min(n_bins, len(scale_factors))
    a_bin = scale_factors[:n]
    age_bin = _age_lcdm(a_bin, hubble_h, omega_m, omega_l)
    age_now = _age_lcdm(
        scale_factors[min(snap_num, len(scale_factors) - 1)],
        hubble_h,
        omega_m,
        omega_l,
    )
    lookback = age_now - age_bin  # (n,)
    # Mass-weighted lookback ≈ mean stellar age
    sfh_clipped = sfh[:, :n]
    total = sfh_clipped.sum(axis=1)
    weighted = (sfh_clipped * lookback).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ages = np.where(total > 0, weighted / total, 0.0)
    return ages.astype(np.float32)
