"""Build the HD recipe's input (SageGalaxy) from a loaded GalaxySnapshot."""

from __future__ import annotations

import numpy as np

from visage.hd.model import SageGalaxy


def _extra(snap, name, i, default=0.0):
    arr = snap.extra.get(name) if getattr(snap, "extra", None) else None
    if arr is None or i >= len(arr):
        return default
    return float(arr[i])


def _sfh(snap, i, part, mass) -> tuple:
    """Mass formed (Msun) per lookback bin, disk (0) or bulge (1); () if
    the run saved no star-formation history."""
    bins = getattr(snap, "sfh_bins", None)
    if bins is None or i >= len(bins):
        return ()
    return tuple(float(v) * mass for v in bins[i, part])


def _field(snap, name, i, default=0.0):
    arr = getattr(snap, name, None)
    if arr is None or i >= len(arr):
        return default
    return float(arr[i])


def cosmic_time_gyr(a: float, hubble_h: float, omega_m: float) -> float:
    """Age of a flat LCDM universe at scale factor `a`, Gyr."""
    ol = 1.0 - omega_m
    t_h = 9.7779 / hubble_h  # 1/H0 in Gyr
    return float(
        2.0
        / (3.0 * np.sqrt(ol))
        * t_h
        * np.arcsinh(np.sqrt(ol / omega_m) * max(a, 1e-4) ** 1.5)
    )


def sage_galaxy_from_snapshot(
    snap,
    i: int,
    hubble_h: float,
    snap_table=None,
    omega_m: float = 0.25,
) -> SageGalaxy:
    """One galaxy of a GalaxySnapshot, in the physical units the recipe uses.

    Snapshot masses are already in Msun; radii are Mpc/h (-> kpc).  Fields
    the loader doesn't name land raw in `snap.extra` (masses there are still
    1e10 Msun/h).  Missing optional fields read as zero, which simply turns
    the matching feature off.
    """
    kpc = 1e3 / hubble_h
    mass = 1e10 / hubble_h
    # The snapshot's redshift, and (satellites) the time since infall: SAGE
    # writes TimeOfInfall as the snapshot it became a satellite.
    z, t_inf = 0.0, -1.0
    if snap_table is not None:
        sn = int(getattr(snap, "snap_num", -1))
        if 0 <= sn < snap_table.count:
            z = float(snap_table.snap_to_z(sn))
            s_in = int(_field(snap, "time_of_infall", i))
            if 0 < s_in <= sn and int(_field(snap, "gal_type", i)) > 0:
                t_inf = cosmic_time_gyr(
                    snap_table.snap_to_a(sn), hubble_h, omega_m
                ) - cosmic_time_gyr(
                    snap_table.snap_to_a(s_in), hubble_h, omega_m
                )
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
        redshift=z,
        ffb=int(_field(snap, "ffb_regime", i)),
        vel=tuple(_extra(snap, f"Vel{c}", i) for c in "xyz"),
        vmax=_field(snap, "vmax", i),
        vel_disp=_extra(snap, "VelDisp", i),
        mvir=_field(snap, "mvir", i) * mass,
        infall_mvir=_extra(snap, "infallMvir", i) * mass,
        infall_stellar_mass=_extra(snap, "infallStellarMass", i) * mass,
        t_since_infall_gyr=t_inf,
        merge_type=int(_extra(snap, "mergeType", i)),
        merger_bulge_radius_kpc=_field(snap, "merger_bulge_radius", i) * kpc,
        instability_bulge_radius_kpc=(
            _field(snap, "instability_bulge_radius", i) * kpc
        ),
        metals_bulge=_field(snap, "metals_bulge_mass", i),
        metals_hot=_field(snap, "metals_hot_gas", i),
        metals_cgm=_field(snap, "metals_cgm_gas", i),
        metals_ics=_field(snap, "metals_ics", i),
        sfr_disk_z=_field(snap, "sfr_disk_z", i),
        ejected=_field(snap, "ejected_mass", i),
        ics_disrupt=_extra(snap, "ICS_disrupt", i) * mass,
        ics_accrete=_extra(snap, "ICS_accrete", i) * mass,
        r_heat_kpc=_extra(snap, "r_heat", i) * kpc,
        tcool_gyr=_extra(snap, "tcool", i),
        tff_gyr=_extra(snap, "tff", i),
        mdot_cool=_extra(snap, "mdot_cool", i),
        sfh_disk=_sfh(snap, i, 0, mass),
        sfh_bulge=_sfh(snap, i, 1, mass),
    )


def spin_vector(snap, i: int) -> np.ndarray | None:
    """Unit spin axis from Spinx/y/z, or None if the output has none."""
    v = np.array([_extra(snap, f"Spin{c}", i) for c in "xyz"])
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else None
