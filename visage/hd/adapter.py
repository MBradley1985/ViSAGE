"""Build the HD recipe's input (SageGalaxy) from a loaded GalaxySnapshot."""

from __future__ import annotations

import numpy as np

from visage.hd.model import SageGalaxy


def _extra(snap, name, i, default=0.0):
    arr = snap.extra.get(name) if getattr(snap, "extra", None) else None
    if arr is None or i >= len(arr):
        return default
    return float(arr[i])


def _field(snap, name, i, default=0.0):
    arr = getattr(snap, name, None)
    if arr is None or i >= len(arr):
        return default
    return float(arr[i])


def sage_galaxy_from_snapshot(snap, i: int, hubble_h: float) -> SageGalaxy:
    """One galaxy of a GalaxySnapshot, in the physical units the recipe uses.

    Snapshot masses are already in Msun; radii are Mpc/h (-> kpc).  Fields
    the loader doesn't name land raw in `snap.extra` (masses there are still
    1e10 Msun/h).  Missing optional fields read as zero, which simply turns
    the matching feature off.
    """
    kpc = 1e3 / hubble_h
    mass = 1e10 / hubble_h
    return SageGalaxy(
        galaxy_index=int(_field(snap, "galaxy_id", i, i)),
        stellar_mass=_field(snap, "stellar_mass", i),
        bulge_mass=_field(snap, "bulge_mass", i),
        merger_bulge_mass=_field(snap, "merger_bulge_mass", i),
        instability_bulge_mass=_field(snap, "instability_bulge_mass", i),
        cold_gas=_field(snap, "cold_gas", i),
        h2_gas=_field(snap, "h2_mass", i),
        h1_gas=_field(snap, "h1_gas", i),
        metals_cold_gas=_field(snap, "metals_cold_gas", i),
        bh_mass=_field(snap, "bh_mass", i),
        sfr_disk=_field(snap, "sfr_disk", i),
        sfr_bulge=_field(snap, "sfr_bulge", i),
        disk_radius_kpc=_field(snap, "disk_radius", i) * kpc,
        bulge_radius_kpc=_field(snap, "bulge_radius", i) * kpc,
        regime=int(_field(snap, "cgm_regime", i)),
        gtype=int(_field(snap, "gal_type", i)),
        hot_gas=_field(snap, "hot_gas", i),
        cgm_gas=_field(snap, "cgm_gas", i),
        rvir_kpc=_field(snap, "rvir", i) * kpc,
        metals_stellar_mass=_field(snap, "metals_stellar_mass", i),
        t_major_myr=_extra(snap, "TimeOfLastMajorMerger", i, -1.0),
        t_minor_myr=_extra(snap, "TimeOfLastMinorMerger", i, -1.0),
        qso_accretion=_extra(snap, "QuasarModeBHaccretionMass", i) * mass,
        ics=_field(snap, "ics_mass", i),
        outflow_rate=_field(snap, "outflow_rate", i),
        mass_loading=_field(snap, "mass_loading", i, 1.5),
        mdot_stream=_extra(snap, "mdot_stream", i),
        cooling_log=_field(snap, "cooling", i),
        rcool_to_rvir=_extra(snap, "RcoolToRvir", i, -1.0),
        concentration=_field(snap, "concentration", i, 8.0),
        heating_log=_field(snap, "heating", i),
    )


def spin_vector(snap, i: int) -> np.ndarray | None:
    """Unit spin axis from Spinx/y/z, or None if the output has none."""
    v = np.array([_extra(snap, f"Spin{c}", i) for c in "xyz"])
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else None
