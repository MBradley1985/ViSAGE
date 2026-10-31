"""Build the HD recipe's input (SageGalaxy) from a loaded GalaxySnapshot."""

from __future__ import annotations

import numpy as np

from visage.hd.model import SageGalaxy


def _extra(snap, name, i, default=0.0):
    arr = snap.extra.get(name) if getattr(snap, "extra", None) else None
    if arr is None or i >= len(arr):
        return default
    return float(arr[i])


# SFH bins read on demand, kept per (file, snapshot) for the session's
# recent snapshots: {(path, snap): {raw row: bins}}.
# Centrals of the recent snapshots, for finding a galaxy's neighbours:
# {id(snapshot): (rows, KD-tree)}.
_WEB_CACHE: dict = {}
# How far to look for the haloes a galaxy's cold streams come from, Mpc/h.
WEB_RADIUS = 4.0


def web_neighbours(snap, i, k=3) -> tuple:
    """Up to `k` directions to the massive haloes around galaxy `i`, at
    least 45 degrees apart, strongest (Mvir / d^2) first:
    ((dx, dy, dz, weight), ...), weight relative to the strongest."""
    pos = getattr(snap, "positions", None)
    gt = getattr(snap, "gal_type", None)
    mv = getattr(snap, "mvir", None)
    if pos is None or gt is None or mv is None or i >= len(pos):
        return ()
    key = id(snap)
    if key not in _WEB_CACHE:
        from scipy.spatial import cKDTree

        rows = np.flatnonzero((gt == 0) & (mv > 0))
        if len(rows) == 0:
            return ()
        while len(_WEB_CACHE) >= 2:
            _WEB_CACHE.pop(next(iter(_WEB_CACHE)))
        _WEB_CACHE[key] = (rows, cKDTree(pos[rows]))
    rows, tree = _WEB_CACHE[key]
    near = rows[tree.query_ball_point(pos[i], WEB_RADIUS)]
    own = getattr(snap, "central_id", None)
    gid = getattr(snap, "galaxy_id", None)
    if own is not None and gid is not None:
        near = near[gid[near] != own[i]]
    near = near[near != i]
    if len(near) == 0:
        return ()
    d = (pos[near] - pos[i]).astype(float)
    r = np.linalg.norm(d, axis=1)
    keep = r > 0.05
    d, r, near = d[keep], r[keep], near[keep]
    if len(r) == 0:
        return ()
    w = mv[near].astype(float) / r**2
    out = []
    for j in np.argsort(w)[::-1]:
        u = d[j] / r[j]
        if all(np.dot(u, o[:3]) < np.cos(np.deg2rad(45)) for o in out):
            out.append((*u, w[j] / w.max()))
        if len(out) == k:
            break
    return tuple(tuple(float(x) for x in o) for o in out)


_SFH_CACHE: dict = {}
_SFH_CACHE_SNAPS = 4


def prefetch_sfh(snap, rows, snap_table, hubble_h, omega_m) -> None:
    """Read the SFH bins of several galaxies (snapshot rows) in one go --
    a group's members before its HD build -- so each galaxy doesn't open
    the files on its own."""
    if getattr(snap, "sfh_bins", None) is not None:
        return
    if not getattr(snap, "has_sfh", False) or snap_table is None:
        return
    key = (snap.source_path, int(snap.snap_num))
    have = _SFH_CACHE.get(key, {})
    raw = [
        int(snap.sage_indices[i] if snap.sage_indices is not None else i)
        for i in rows
    ]
    need = sorted({r for r in raw if r not in have})
    if not need:
        return
    from visage.io.galaxy_reader import lightcone_sfh_bins, sfh_bins_for

    try:
        if getattr(snap, "snap_nums", None) is not None:
            # A lightcone: one file, each galaxy from its own snapshot.
            at = {
                r: int(snap.snap_nums[i])
                for r, i in zip(raw, rows, strict=True)
            }
            out = lightcone_sfh_bins(
                snap.source_path,
                need,
                [at[r] for r in need],
                snap_table.scale_factors,
                hubble_h,
                omega_m,
            )
        else:
            out = sfh_bins_for(
                snap.source_path,
                int(snap.snap_num),
                need,
                snap_table.scale_factors,
                hubble_h,
                omega_m,
            )
    except Exception:
        return
    if out is None:
        return
    if key not in _SFH_CACHE:
        while len(_SFH_CACHE) >= _SFH_CACHE_SNAPS:
            _SFH_CACHE.pop(next(iter(_SFH_CACHE)))
        _SFH_CACHE[key] = {}
    _SFH_CACHE[key].update(zip(need, out, strict=True))


def _sfh_bins(snap, i, snap_table, hubble_h, omega_m):
    """Galaxy i's SFH lookback bins, (2, n) raw, or None: from the
    snapshot if it carries them, else read from the file on demand."""
    bins = getattr(snap, "sfh_bins", None)
    if bins is not None:
        return bins[i] if i < len(bins) else None
    if not getattr(snap, "has_sfh", False) or snap_table is None:
        return None
    raw = int(snap.sage_indices[i] if snap.sage_indices is not None else i)
    prefetch_sfh(snap, [i], snap_table, hubble_h, omega_m)
    return _SFH_CACHE.get((snap.source_path, int(snap.snap_num)), {}).get(raw)


def _bulge_history(sfh, bulge_raw: float):
    """SFH bins (2, n: disk, bulge; raw units) with the bulge's history
    made up to its mass.  Older SAGE26 outputs kept the stars mergers and
    disk instabilities moved into the bulge in the disk's history (fixed in
    SAGE26 since): the share of the disk's history that brings the bulge's
    total to BulgeMass moves over, those stars taken to have the disk's age
    mix -- as the lightcone photometry does.  A history already summing to
    BulgeMass is unchanged."""
    sfh = np.asarray(sfh, float)
    disk, bulge = sfh[0], sfh[1]
    sd = float(disk.sum())
    if sd <= 0 or bulge_raw <= 0:
        return sfh
    f = float(np.clip((bulge_raw - bulge.sum()) / sd, 0.0, 1.0))
    if f <= 0:
        return sfh
    return np.stack([disk * (1 - f), bulge + f * disk])


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
        # (A lightcone's galaxies are each from their own snapshot.)
        sn = (
            snap.snap_of(i)
            if hasattr(snap, "snap_of")
            else int(getattr(snap, "snap_num", -1))
        )
        if 0 <= sn < snap_table.count:
            z = float(snap_table.snap_to_z(sn))
            s_in = int(_field(snap, "time_of_infall", i))
            if 0 < s_in <= sn and int(_field(snap, "gal_type", i)) > 0:
                t_inf = cosmic_time_gyr(
                    snap_table.snap_to_a(sn), hubble_h, omega_m
                ) - cosmic_time_gyr(
                    snap_table.snap_to_a(s_in), hubble_h, omega_m
                )
    zs = getattr(snap, "redshifts", None)
    if zs is not None and i < len(zs):
        z = float(zs[i])  # its own redshift on the cone
    sfh = _sfh_bins(snap, i, snap_table, hubble_h, omega_m)
    if sfh is not None:
        sfh = _bulge_history(sfh, _field(snap, "bulge_mass", i) / mass)
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
        web=web_neighbours(snap, i),
        tau_v_ism=_sed_tau(snap, i),
        sed_ratio=_sed_ratio(snap, i),
        los=_los(snap, i),
        **_sed_parts(snap, i),
        sfh_disk=() if sfh is None else tuple(float(v) * mass for v in sfh[0]),
        sfh_bulge=(
            () if sfh is None else tuple(float(v) * mass for v in sfh[1])
        ),
    )


# Observed-frame bands standing in for HD's B, V and I channels, first
# set the lightcone has.
SED_BANDS = (
    ("sdss_g", "sdss_r", "sdss_i"),
    ("des_g", "des_r", "des_i"),
    ("lsst_g", "lsst_r", "lsst_i"),
    ("ps1_g", "ps1_r", "ps1_i"),
)


def _sed_ratio(snap, i: int) -> tuple:
    """(f_I / f_V, f_B / f_V) from a lightcone galaxy's observed
    magnitudes; () without them."""
    mags = getattr(snap, "sed_mags", None) or {}
    for b, v, ir in SED_BANDS:
        keys = [f"mag_obs_{x}" for x in (b, v, ir)]
        if all(k in mags for k in keys):
            mb, mv, mi = (float(mags[k][i]) for k in keys)
            if not np.all(np.isfinite([mb, mv, mi])):
                return ()
            return (10 ** (-0.4 * (mi - mv)), 10 ** (-0.4 * (mb - mv)))
    return ()


def _flux(snap, key, i) -> float:
    """Flux from a lightcone magnitude, 0 if it has none."""
    mag = _extra(snap, key, i, np.inf)
    return float(10 ** (-0.4 * mag)) if np.isfinite(mag) else 0.0


def _sed_parts(snap, i: int) -> dict:
    """What a lightcone's photometry says of a galaxy's components, on HD's
    (B, V, I) bands: their colours, and shares of its light in V. Empty
    without disk and bulge magnitudes, or in a box."""
    if getattr(snap, "snap_nums", None) is None:
        return {}
    extra = getattr(snap, "extra", None)
    if extra is None:
        return {}
    for b, v, ir in SED_BANDS:
        if f"disk_mag_obs_{v}" not in extra:
            continue
        band = (b, v, ir)
        disk = [_flux(snap, f"disk_mag_obs_{x}", i) for x in band]
        bulge = [_flux(snap, f"bulge_mag_obs_{x}", i) for x in band]
        agn = [_flux(snap, f"agn_mag_obs_{x}", i) for x in band]
        ics = [_flux(snap, f"ics_mag_obs_{x}", i) for x in band]
        host = disk[1] + bulge[1]
        if host <= 0:
            return {}

        def ratio(f):
            return (f[2] / f[1], f[0] / f[1]) if min(f) > 0 else ()

        # Halpha as a share of the V band's light, across the r band's
        # width (R = 1387 A; Fukugita et al. 1996).
        ha = _extra(snap, "LineFlux_Halpha", i, 0.0)
        f_nu = host * 3631e-23
        band_flux = f_nu * 2.998e18 / 6165.0**2 * 1387.0
        return {
            "sed_disk": ratio(disk),
            "sed_bulge": ratio(bulge),
            "sed_ics": ratio(ics),
            "bulge_share": bulge[1] / host,
            "agn_share": agn[1] / host,
            "ics_share": ics[1] / host,
            "ha_share": float(ha / band_flux) if ha > 0 else 0.0,
            "lum_v": host * float(np.sum(snap.positions[i] ** 2)),
        }
    return {}


def _sed_tau(snap, i: int) -> float:
    """Face-on optical depth HD draws a lightcone galaxy's dust with: its
    photometry's own (Charlot & Fall), else -1 (HD's own estimate: no
    photometry, one screen for every galaxy, or photometry made without
    dust)."""
    how = snap.sed_dust()[0] if hasattr(snap, "sed_dust") else None
    if how == "charlot_fall":
        tau = _extra(snap, "TauV_ISM", i, -1.0)
        return tau if np.isfinite(tau) else -1.0
    return -1.0


def _los(snap, i: int) -> tuple:
    """Unit vector from a lightcone galaxy to the observer at the cone's
    apex (the origin); () in a box."""
    if getattr(snap, "snap_nums", None) is None:
        return ()
    p = np.asarray(snap.positions[i], float)
    n = float(np.linalg.norm(p))
    return tuple(float(v) for v in -p / n) if n > 0 else ()


def spin_vector(snap, i: int) -> np.ndarray | None:
    """Unit spin axis from Spinx/y/z, or None if the output has none."""
    v = np.array([_extra(snap, f"Spin{c}", i) for c in "xyz"])
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else None
