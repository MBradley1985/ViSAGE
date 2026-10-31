from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

from visage.io.sage_files import galaxy_files, is_dataset, open_snapshot


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
    # ── Synthetic photometry (LightSAGE lightcones only) ────────────────
    # key -> (N,) float32 AB magnitude, e.g. "mag_rest_sdss_g",
    # "mag_obs_sdss_r". Empty for every non-SED-enabled snapshot/model.
    sed_mags: dict = field(default_factory=dict)
    # ── Auto-discovered properties ──────────────────────────────────────
    # Every other per-galaxy dataset found in the snapshot group, keyed by
    # its HDF5 name.  This is what keeps the UI honest when SAGE grows a
    # new output field: it shows up as a filter and a Colour-by mode with
    # no code change here.  Values are raw (no unit conversion is possible
    # without knowing what the field means).
    extra: dict = field(default_factory=dict)
    # ── Rendering ───────────────────────────────────────────────────────
    # How many galaxy glows overlap at each galaxy (utils.sizing.
    # glow_crowding), filled in by the loader's background thread.
    crowding: np.ndarray | None = None
    # ── Star-formation history, summarised ─────────────────────────────
    # Stellar mass formed (raw, 10^10 Msun/h) in each lookback-time bin of
    # SFH_AGE_EDGES, for the disk ([:, 0]) and the bulge ([:, 1]): shape
    # (N, 2, len(SFH_AGE_EDGES) - 1).  None without SFHMassDisk/Bulge
    # (SAGE's SaveFullSFH off), and None by default with them too: HD reads
    # the few rows it needs on demand (sfh_bins_for) rather than every
    # snapshot load binning every galaxy.
    sfh_bins: np.ndarray | None = None
    # Where the snapshot came from, and whether it has SFH arrays.
    source_path: str = ""
    has_sfh: bool = False
    # ── Lightcones: each galaxy is from its own snapshot ────────────────
    # (N,) source snapshot and cosmological redshift per galaxy; None in a
    # box, where every galaxy is at `snap_num`.
    snap_nums: np.ndarray | None = None
    redshifts: np.ndarray | None = None
    # The cone's PhotometryHeader (how its synthetic photometry was made;
    # empty without photometry).
    photometry: dict = field(default_factory=dict)

    def sed_dust(self) -> tuple[str | None, float]:
        """The dust in this catalogue's synthetic photometry: ("charlot_fall",
        0) for each galaxy's own (TauV_ISM, CosInclination), ("calzetti",
        tau_V) for one screen for all, ("none", 0), or (None, 0) without
        photometry."""
        desc = str(self.photometry.get("Dust", "")) if self.photometry else ""
        if not self.photometry:
            return None, 0.0
        low = desc.lower()
        if low.startswith("charlot"):
            return "charlot_fall", 0.0
        if low.startswith("calzetti"):
            import re

            m = re.search(r"tau_v\s*=\s*([0-9.eE+-]+)", desc, re.I)
            return "calzetti", float(m.group(1)) if m else 0.0
        if low == "none":
            return "none", 0.0
        return None, 0.0

    @property
    def is_cone(self) -> bool:
        return self.snap_nums is not None

    def snap_of(self, i: int) -> int:
        """The snapshot galaxy `i` is from."""
        if self.snap_nums is not None:
            return int(self.snap_nums[i])
        return int(self.snap_num)

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


# Every dataset this reader handles by name.  Anything else found in a
# snapshot group is picked up automatically into `GalaxySnapshot.extra`.
KNOWN_HDF5_FIELDS: frozenset[str] = frozenset(
    {
        # Core (required)
        "Posx",
        "Posy",
        "Posz",
        "StellarMass",
        "BulgeMass",
        "ColdGas",
        "Mvir",
        "SfrDisk",
        "SfrBulge",
        "Type",
        # Optional, read explicitly above
        "BlackHoleMass",
        "IntraClusterStars",
        "FFBRegime",
        "Regime",
        "CentralMvir",
        "Rvir",
        "H2gas",
        "CGMgas",
        "HotGas",
        "GalaxyIndex",
        "CentralGalaxyIndex",
        "TimeOfInfall",
        "Len",
        "Vmax",
        "Concentration",
        "Spin",
        "DiskRadius",
        "BulgeRadius",
        "MergerBulgeMass",
        "MergerBulgeRadius",
        "InstabilityBulgeMass",
        "InstabilityBulgeRadius",
        "H1gas",
        "EjectedMass",
        "OutflowRate",
        "MassLoading",
        "Cooling",
        "Heating",
        "SfrBulgeZ",
        "SfrDiskZ",
        "MetalsColdGas",
        "MetalsStellarMass",
        "MetalsBulgeMass",
        "MetalsHotGas",
        "MetalsEjectedMass",
        "MetalsIntraClusterStars",
        "MetalsCGMgas",
        # Multi-column / derived inputs
        "SFHMassDisk",
        "SFHMassBulge",
    }
)


# Datasets to leave out of discovery: bookkeeping, tree indices and internal
# SAGE state rather than physical properties worth filtering or colouring by.
# Matched case- and underscore-insensitively, so a spelling change in SAGE's
# output doesn't put them back in the UI.
IGNORED_HDF5_FIELDS: frozenset[str] = frozenset(
    {
        "DT",
        "MergeIntoID",
        "MergeIntoSnapNum",
        "SAGEHaloIndex",
        "SAGETreeIndex",
        "SimulationHaloIndex",
        "SnapNum",
    }
)

_IGNORED_NORMALISED = frozenset(
    n.lower().replace("_", "") for n in IGNORED_HDF5_FIELDS
)


def is_ignored_field(name: str) -> bool:
    """True for bookkeeping datasets that should never reach the UI."""
    return name.lower().replace("_", "") in _IGNORED_NORMALISED


def find_sfh_datasets(grp) -> tuple[str | None, str | None]:
    """(disk, bulge) star-formation-history dataset names in `grp`.

    Matched by shape rather than an exact spelling — the SFH arrays are the
    two-dimensional "SFH…Disk"/"SFH…Bulge" pair — so a rename or a change of
    case in SAGE's output doesn't silently switch stellar age off.
    """
    disk = bulge = None
    for name, ds in grp.items():
        if not is_dataset(ds) or ds.ndim != 2:
            continue
        low = name.lower()
        if not low.startswith("sfh"):
            continue
        if "disk" in low and disk is None:
            disk = name
        elif "bulge" in low and bulge is None:
            bulge = name
    return disk, bulge


def discover_extra_fields(grp, n_rows: int | None = None) -> list[str]:
    """Names of per-galaxy datasets in `grp` this reader has no field for.

    One row per galaxy, numeric, not already handled.  Used both to read
    the values and (by Model) to list what a model actually offers.
    """
    out: list[str] = []
    for name, ds in grp.items():
        if name in KNOWN_HDF5_FIELDS or is_ignored_field(name):
            continue
        if not is_dataset(ds):
            continue
        if ds.ndim != 1 or ds.dtype.kind not in "fiu":
            continue
        if n_rows is not None and ds.shape[0] != n_rows:
            continue
        out.append(name)
    return sorted(out)


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
    min_particles: int | None = None,
    particle_mass: float | None = None,
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
    hdf5_path:        path to SAGE HDF5 output (model_0.hdf5; an MPI run's
                      other rank files model_1.hdf5 … are read with it)
    snap_num:         snapshot index
    min_stellar_mass: minimum stellar mass in Msun (after h correction)
    min_particles:    with `particle_mass` (10^10 Msun/h), cut instead at
                      the stellar mass where this snapshot's haloes are
                      resolved with that many particles
                      (visage.utils.resolution)
    max_galaxies:     random downsample if more galaxies than this are found
    hubble_h:         Hubble parameter h (from par file)
    """
    hdf5_path = Path(hdf5_path)
    group_key = f"Snap_{snap_num}"

    if VERBOSE:
        n_files = len(galaxy_files(hdf5_path))
        which = (
            hdf5_path.name
            if n_files == 1
            else f"{hdf5_path.name} + {n_files - 1} more MPI rank files"
        )
        print(f"  Galaxies: reading {which} / {group_key}...")
    with open_snapshot(hdf5_path, snap_num) as grp:
        if grp is None:
            if VERBOSE:
                print(
                    f"  Galaxies: group {group_key} not found — empty snapshot"
                )
            return GalaxySnapshot.empty(snap_num)

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
        sfh_disk_name, sfh_bulge_name = find_sfh_datasets(grp)
        has_sfh = sfh_disk_name is not None and sfh_bulge_name is not None
        sfh_disk_raw = np.asarray(grp[sfh_disk_name]) if has_sfh else None
        sfh_bulge_raw = np.asarray(grp[sfh_bulge_name]) if has_sfh else None

        # Anything else SAGE wrote — read as-is, so a new output field is
        # available to the UI without a code change here.
        extra_raw = {
            name: np.asarray(grp[name])
            for name in discover_extra_fields(grp, len(posx))
        }

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

    if min_particles and particle_mass:
        from visage.utils.resolution import resolved_stellar_mass

        cut = resolved_stellar_mass(
            stellar_mass,
            mvir_raw / particle_mass,
            gal_type == 0,
            min_particles,
        )
        min_stellar_mass = cut if cut is not None else 0.0
        if VERBOSE:
            print(
                f"  Galaxies: resolved (haloes >= {min_particles} particles)"
                f" from M* = {min_stellar_mass:.2e} Msun"
            )
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
        extra={k: v[indices] for k, v in extra_raw.items()},
        sage_indices=indices.astype(np.int64),
        snap_num=snap_num,
        source_path=str(hdf5_path),
        has_sfh=sfh_disk_raw is not None and sfh_bulge_raw is not None,
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


# Lookback-time bin edges (Gyr) for the summarised star-formation history.
SFH_AGE_EDGES = (0.0, 0.1, 0.5, 1.0, 3.0, 6.0, 10.0, 99.0)


def sfh_step_offset(sfh: np.ndarray, snap_nums) -> int:
    """How SAGE dated these (N, n_bins) histories: 1 if bin k holds the
    stars formed from snapshot k-1 to k (SAGE26 since its snapshot-lag
    fix), 0 if from k to k+1 (before it, and SAGE), told apart by whether
    any galaxy has stars in the bin of its own snapshot."""
    last = np.minimum(np.asarray(snap_nums), sfh.shape[1] - 1)
    return int(np.any(sfh[np.arange(len(sfh)), last] > 0))


def _sfh_age_bins(
    sfh_disk: np.ndarray | None,
    sfh_bulge: np.ndarray | None,
    indices: np.ndarray,
    snap_num: int,
    scale_factors: np.ndarray | None,
    hubble_h: float,
    omega_m: float,
    omega_l: float,
) -> np.ndarray | None:
    """Mass formed in each SFH_AGE_EDGES lookback bin, disk and bulge:
    (N, 2, n_bins), raw units; None without SFH arrays."""
    if (
        sfh_disk is None
        or sfh_bulge is None
        or scale_factors is None
        or len(scale_factors) == 0
        or sfh_disk.ndim != 2
    ):
        return None
    # Each bin is dated by the middle of its step (sfh_step_offset), and
    # the last step (ending now) is the current star formation, the first
    # bin.
    n = min(sfh_disk.shape[1], len(scale_factors))
    snap = min(snap_num, n - 1)
    age = _age_lcdm(scale_factors[:n], hubble_h, omega_m, omega_l)
    shift = sfh_step_offset(
        np.nan_to_num(np.asarray(sfh_disk[indices], np.float64))
        + np.nan_to_num(np.asarray(sfh_bulge[indices], np.float64)),
        np.full(len(indices), snap),
    )
    start = np.maximum(np.arange(n) - shift, 0)
    end = np.minimum(start + 1, snap)
    lookback = np.maximum(age[snap] - 0.5 * (age[start] + age[end]), 0.0)
    which = np.digitize(lookback, SFH_AGE_EDGES[1:-1])  # (n,)
    if snap - 1 + shift >= 0:
        which[snap - 1 + shift] = 0
    k = len(SFH_AGE_EDGES) - 1
    out = np.zeros((len(indices), 2, k), np.float32)
    for part, sfh in enumerate((sfh_disk, sfh_bulge)):
        rows = np.nan_to_num(np.asarray(sfh[indices][:, :n], np.float64))
        for b in range(k):
            sel = which == b
            if sel.any():
                out[:, part, b] = rows[:, sel].sum(axis=1)
    return out


def sfh_bins_for(
    path: str | Path,
    snap_num: int,
    raw_rows,
    scale_factors: np.ndarray,
    hubble_h: float,
    omega_m: float,
) -> np.ndarray | None:
    """SFH_AGE_EDGES bins (as _sfh_age_bins) for a few raw rows of a
    snapshot, read from the file on demand; None without SFH arrays."""
    rows = np.atleast_1d(np.asarray(raw_rows, np.int64))
    with open_snapshot(path, snap_num) as grp:
        if grp is None:
            return None
        disk, bulge = find_sfh_datasets(grp)
        if disk is None or bulge is None:
            return None
        order = np.argsort(rows)
        srt = rows[order]
        d = np.stack([np.asarray(grp[disk][int(r), :]) for r in srt])
        b = np.stack([np.asarray(grp[bulge][int(r), :]) for r in srt])
    out = _sfh_age_bins(
        d,
        b,
        np.arange(len(srt)),
        snap_num,
        np.asarray(scale_factors, float),
        hubble_h,
        omega_m,
        1.0 - omega_m,
    )
    res = np.empty_like(out)
    res[order] = out
    return res


def lightcone_sfh_bins(
    path: str | Path,
    raw_rows,
    snap_nums,
    scale_factors: np.ndarray,
    hubble_h: float,
    omega_m: float,
) -> np.ndarray | None:
    """SFH_AGE_EDGES bins for a few rows of a lightcone file, each dated
    from its own snapshot; None without SFH arrays."""
    from visage.io.lightcone_reader import _open_ro

    rows = np.atleast_1d(np.asarray(raw_rows, np.int64))
    snaps = np.atleast_1d(np.asarray(snap_nums, np.int64))
    with _open_ro(Path(path)) as f:
        disk, bulge = find_sfh_datasets(f)
        if disk is None or bulge is None:
            return None
        d = np.stack([np.asarray(f[disk][int(r), :]) for r in rows])
        b = np.stack([np.asarray(f[bulge][int(r), :]) for r in rows])
    a = np.asarray(scale_factors, float)
    out = None
    for k, sn in enumerate(snaps):
        one = _sfh_age_bins(
            d[k : k + 1],
            b[k : k + 1],
            np.arange(1),
            int(sn),
            a,
            hubble_h,
            omega_m,
            1.0 - omega_m,
        )
        if one is None:
            return None
        if out is None:
            out = np.zeros((len(rows),) + one.shape[1:], np.float32)
        out[k] = one[0]
    return out


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
