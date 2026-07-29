from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

from visage.io.galaxy_reader import GalaxySnapshot
from visage.io.halo_reader import HaloSnapshot


@dataclass
class LightconeSnapshot:
    """Everything ViSAGE needs to render a lightcone through the normal
    Model/Scene/UI stack.

    A lightcone is a *flat* HDF5 point cloud in observer-frame coordinates,
    spanning all redshifts at once — no periodic box, no per-snapshot groups.
    But every SAGE field (incl. host-halo properties: Mvir/Rvir/Vmax/Vvir/Type/
    CentralGalaxyIndex) is inlined, so we can build a full GalaxySnapshot AND a
    HaloSnapshot (host haloes from the Type==0 centrals) exactly as Explore
    mode does — no tree-file reads, no coordinate transform (positions are
    already observer-frame).
    """

    galaxies: GalaxySnapshot
    halos: HaloSnapshot
    snapnum: np.ndarray  # (N,) int — per-galaxy source snapshot (time/z shell)
    halo_snapnum: np.ndarray  # (H,) int — per-host-halo source snapshot
    redshift: np.ndarray  # (N,) float — per-galaxy cosmological redshift
    hubble_h: float
    bounds: np.ndarray  # (2, 3) float — [min_xyz, max_xyz] Mpc/h
    box_extent: float  # largest axis span (Mpc/h) — used for camera/box math
    present_fields: set  # raw HDF5 field names present (for fields_available)
    a_list_path: str | None  # SAGE scale-factor list, if resolvable on disk
    header: dict
    source_path: str

    @property
    def count(self) -> int:
        return self.galaxies.count


def _open_ro(path: Path) -> h5py.File:
    """Open read-only, disabling file locking when supported — lightcone files
    often live on temp/network filesystems where locking fails spuriously."""
    try:
        return h5py.File(path, "r", locking=False)
    except (TypeError, ValueError):
        return h5py.File(path, "r")


def _find(f: h5py.File, name: str) -> str | None:
    """Case-insensitive field lookup (pass-through fields are CamelCase,
    computed fields lowercase)."""
    if name in f:
        return name
    low = name.lower()
    for k in f.keys():
        if k.lower() == low:
            return k
    return None


def _read_hubble_h(f: h5py.File) -> float:
    for grp_name in ("SageOutputHeader", "Header"):
        if grp_name in f:
            grp = f[grp_name]
            sim = grp.get("Simulation") if hasattr(grp, "get") else None
            for holder in (sim, grp):
                if holder is None:
                    continue
                for key in holder.attrs:
                    if key.lower() in ("hubble_h", "hubble_constant", "h0"):
                        try:
                            return float(np.asarray(holder.attrs[key]))
                        except (TypeError, ValueError):
                            pass
    if "cosmology" in f:
        cg = f["cosmology"]
        for key in ("hubble_constant", "hubble_h", "h"):
            k = _find(cg, key) if hasattr(cg, "keys") else None
            if k is not None:
                try:
                    return float(np.asarray(cg[k][()]))
                except (TypeError, ValueError):
                    pass
    return 0.73


def _resolve_a_list(f: h5py.File) -> str | None:
    """Find the SAGE scale-factor list path recorded in the copied header."""
    for grp_name in ("SageOutputHeader", "Header"):
        if grp_name in f:
            grp = f[grp_name]
            for holder in (grp.get("Simulation"), grp):
                if holder is None:
                    continue
                for key in holder.attrs:
                    if key.lower() in ("filewithsnaplist", "snaplist"):
                        val = holder.attrs[key]
                        if isinstance(val, (bytes, np.bytes_)):
                            val = val.decode(errors="replace")
                        if val and Path(str(val)).is_file():
                            return str(val)
    return None


VERBOSE = True


def load_lightcone_snapshot(
    path: str | Path,
    min_stellar_mass: float = 0.0,
    min_halo_mass: float = 1.0e10,
    max_galaxies: int | None = None,
) -> LightconeSnapshot:
    """Read a flat ``cli_lightcone`` HDF5 file into galaxies + haloes."""
    path = Path(path)
    if VERBOSE:
        print(f"  Lightcone: reading {path.name} ...")
    with _open_ro(path) as f:
        present = set(f.keys())

        def raw(name, dtype=np.float64):
            actual = _find(f, name)
            return None if actual is None else np.asarray(f[actual][:], dtype)

        posx, posy, posz = raw("Posx"), raw("Posy"), raw("Posz")
        if posx is None or posy is None or posz is None:
            raise KeyError(
                f"{path} is not a lightcone file (missing Posx/Posy/Posz)"
            )
        n_all = len(posx)
        hubble_h = _read_hubble_h(f)
        a_list_path = _resolve_a_list(f)
        mfac = 1.0e10 / max(hubble_h, 1e-6)

        # Read every field we need at full length (None if absent).
        cols = {name: raw(name) for name in _RAW_FIELDS}
        cols["Posx"], cols["Posy"], cols["Posz"] = posx, posy, posz

        # Synthetic photometry (visage.sed), if this cone has been run
        # through it — dataset names are data-dependent (whichever bands/
        # frames the user picked), so discover them rather than hardcode.
        sed_names = sorted(
            n for n in present if n.startswith(("mag_rest_", "mag_obs_"))
        )
        sed_cols = {name: raw(name, np.float32) for name in sed_names}
        stellar_raw = cols.get("StellarMass")
        stellar_mass_all = (
            stellar_raw * mfac if stellar_raw is not None else np.zeros(n_all)
        )

        header = {
            k: (
                v.decode(errors="replace")
                if isinstance(v, (bytes, np.bytes_))
                else (v.item() if hasattr(v, "item") else v)
            )
            for k, v in (
                f["LightconeOutputHeader"].attrs.items()
                if "LightconeOutputHeader" in f
                else []
            )
        }

    # ── Select galaxies: stellar-mass floor, then downsample for speed ──
    keep = stellar_mass_all >= float(min_stellar_mass)
    idx = np.where(keep)[0]
    # max_galaxies=None → keep every galaxy (no downsample).
    if max_galaxies is not None and len(idx) > max_galaxies:
        rng = np.random.default_rng(42)
        idx = np.sort(rng.choice(idx, max_galaxies, replace=False))
    n = len(idx)

    def col(name, dtype=np.float64, mass=False):
        v = cols.get(name)
        if v is None:
            return np.zeros(n, dtype=dtype)
        out = v[idx].astype(dtype)
        return out * mfac if mass else out

    positions = np.column_stack(
        [cols["Posx"][idx], cols["Posy"][idx], cols["Posz"][idx]]
    ).astype(np.float32)

    z32 = lambda: np.zeros(n, dtype=np.float32)  # noqa: E731
    sfr_disk = col("SfrDisk", np.float32)
    sfr_bulge = col("SfrBulge", np.float32)
    sfr = (sfr_disk + sfr_bulge).astype(np.float32)
    stellar_mass = col("StellarMass", np.float32, mass=True)
    ssfr = (sfr / np.where(stellar_mass > 0, stellar_mass, np.inf)).astype(
        np.float32
    )

    galaxies = GalaxySnapshot(
        positions=positions,
        stellar_mass=stellar_mass,
        mvir=col("Mvir", np.float32),  # raw 10^10 Msun/h (as galaxy_reader)
        rvir=col("Rvir", np.float32),  # Mpc/h
        sfr=sfr,
        ssfr=ssfr,
        cold_gas=col("ColdGas", np.float32, mass=True),
        bulge_mass=col("BulgeMass", np.float32, mass=True),
        gal_type=col("Type", np.int32),
        bh_mass=col("BlackHoleMass", np.float32, mass=True),
        ics_mass=col("IntraClusterStars", np.float32, mass=True),
        ffb_regime=col("FFBRegime", np.int32),
        cgm_regime=col("Regime", np.int32),
        central_mvir=col("CentralMvir", np.float32, mass=True),
        h2_mass=col("H2gas", np.float32, mass=True),
        cgm_gas=col("CGMgas", np.float32, mass=True),
        hot_gas=col("HotGas", np.float32, mass=True),
        galaxy_id=col("GalaxyIndex", np.int64),
        central_id=col("CentralGalaxyIndex", np.int64),
        time_of_infall=col("TimeOfInfall", np.int32),
        mean_age=z32(),  # per-galaxy age across the cone is not computed
        len_particles=col("Len", np.int32),
        vmax=col("Vmax", np.float32),
        concentration=col("Concentration", np.float32),
        spin=z32(),  # lightcone stores Spinx/y/z, not a scalar Spin
        disk_radius=col("DiskRadius", np.float32),
        bulge_radius=col("BulgeRadius", np.float32),
        merger_bulge_mass=col("MergerBulgeMass", np.float32, mass=True),
        merger_bulge_radius=col("MergerBulgeRadius", np.float32),
        instability_bulge_mass=col(
            "InstabilityBulgeMass", np.float32, mass=True
        ),
        instability_bulge_radius=col("InstabilityBulgeRadius", np.float32),
        h1_gas=col("H1gas", np.float32, mass=True),
        ejected_mass=col("EjectedMass", np.float32, mass=True),
        outflow_rate=col("OutflowRate", np.float32),
        mass_loading=col("MassLoading", np.float32),
        cooling=col("Cooling", np.float32),
        heating=col("Heating", np.float32),
        sfr_bulge=sfr_bulge,
        sfr_disk=sfr_disk,
        sfr_bulge_z=col("SfrBulgeZ", np.float32),
        sfr_disk_z=col("SfrDiskZ", np.float32),
        metals_cold_gas=col("MetalsColdGas", np.float32, mass=True),
        metals_stellar_mass=col("MetalsStellarMass", np.float32, mass=True),
        metals_bulge_mass=col("MetalsBulgeMass", np.float32, mass=True),
        metals_hot_gas=col("MetalsHotGas", np.float32, mass=True),
        metals_ejected_mass=col("MetalsEjectedMass", np.float32, mass=True),
        metals_ics=col("MetalsIntraClusterStars", np.float32, mass=True),
        metals_cgm_gas=col("MetalsCGMgas", np.float32, mass=True),
        sage_indices=idx.astype(np.int64),
        snap_num=0,
        sed_mags={
            name: values[idx].astype(np.float32)
            for name, values in sed_cols.items()
            if values is not None
        },
    )

    # Per-galaxy time/redshift (drives the "highlight shell" navigation).
    snapnum = col("SnapNum", np.int32)
    redshift = cols.get("redshift_cosmological")
    if redshift is None:
        redshift = cols.get("redshift_observed")
    redshift = (
        redshift[idx].astype(np.float64)
        if redshift is not None
        else np.zeros(n)
    )

    # ── Host haloes from the Type==0 centrals ──────────────────────────
    halos, central_idx = _build_halos(galaxies, min_halo_mass)
    halo_snapnum = snapnum[central_idx].astype(np.int32)

    if n:
        bounds = np.vstack([positions.min(0), positions.max(0)]).astype(
            np.float64
        )
        box_extent = float(np.max(bounds[1] - bounds[0])) or 1.0
    else:
        bounds = np.zeros((2, 3), dtype=np.float64)
        box_extent = 1.0

    if VERBOSE:
        print(
            f"  Lightcone: {n:,} galaxies, {halos.count:,} host haloes "
            f"(of {n_all:,}; h={hubble_h})"
        )

    return LightconeSnapshot(
        galaxies=galaxies,
        halos=halos,
        snapnum=snapnum.astype(np.int32),
        halo_snapnum=halo_snapnum,
        redshift=redshift,
        hubble_h=hubble_h,
        bounds=bounds,
        box_extent=box_extent,
        present_fields=present,
        a_list_path=a_list_path,
        header=header,
        source_path=str(path),
    )


def _build_halos(
    gal: GalaxySnapshot, min_halo_mass: float
) -> tuple[HaloSnapshot, np.ndarray]:
    """Build a HaloSnapshot from the central (Type==0) galaxies — mirroring
    Explore's halo layer, sourced from the lightcone's inlined halo properties.
    Returns (halos, central_indices) so callers can align per-halo metadata
    (e.g. SnapNum) to the halo set."""
    if gal.count == 0:
        return HaloSnapshot.empty(0), np.empty(0, dtype=np.int64)

    h = 0.73  # only used for the mass floor comparison scale; masses already Msun
    central = gal.gal_type == 0
    cen_mass = gal.mvir.astype(np.float64) * 1.0e10 / h  # raw→Msun for the cut
    keep = central & (cen_mass >= float(min_halo_mass))
    ci = np.where(keep)[0]

    positions = gal.positions[ci]
    masses = cen_mass[ci].astype(np.float32)
    vmax = gal.vmax[ci].astype(np.float32)
    rvir = gal.rvir[ci].astype(np.float32)
    # Vvir isn't a GalaxySnapshot field; approximate from Mvir/Rvir if needed.
    with np.errstate(divide="ignore", invalid="ignore"):
        # Vvir = sqrt(G Mvir / Rvir); G in (Mpc/h)(km/s)^2 / (Msun/h) = 4.301e-9
        mvir_h = gal.mvir[ci].astype(np.float64) * 1.0e10  # Msun/h
        rvir_h = np.maximum(gal.rvir[ci].astype(np.float64), 1e-6)  # Mpc/h
        vvir = np.sqrt(4.301e-9 * mvir_h / rvir_h).astype(np.float32)
    vvir = np.nan_to_num(vvir, nan=0.0, posinf=0.0, neginf=0.0)

    halos = HaloSnapshot(
        positions=positions.astype(np.float32),
        masses=masses,
        vmax=vmax,
        rvir=rvir,
        vvir=vvir,
        snap_num=0,
    )
    return halos, ci


# Raw HDF5 field names we read (used for presence detection + bulk read).
_RAW_FIELDS = (
    "StellarMass",
    "Mvir",
    "Rvir",
    "SfrDisk",
    "SfrBulge",
    "ColdGas",
    "BulgeMass",
    "Type",
    "BlackHoleMass",
    "IntraClusterStars",
    "FFBRegime",
    "Regime",
    "CentralMvir",
    "H2gas",
    "CGMgas",
    "HotGas",
    "GalaxyIndex",
    "CentralGalaxyIndex",
    "TimeOfInfall",
    "Len",
    "Vmax",
    "Concentration",
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
    "SnapNum",
    "redshift_cosmological",
    "redshift_observed",
)
