from __future__ import annotations

import numpy as np

from visage.io.galaxy_reader import GalaxySnapshot


# What a FOF group is, by its host halo's mass (clusters from 1e14 Msun,
# groups 1e13-1e14 Msun: e.g. Kravtsov & Borgani 2012, ARA&A 50, 353;
# Lovisari et al. 2021, Universe 7, 139) and, in galaxy-sized haloes, by
# how many members are at least BRIGHT_MSTAR -- a fixed mass, so the label
# doesn't change with the viewer's resolution cut.
CLUSTER_MVIR = 1e14  # Msun
GROUP_MVIR = 1e13
BRIGHT_MSTAR = 1e9  # Msun
# Quenched: sSFR below 1e-11 /yr (e.g. Weinmann et al. 2006, MNRAS 366, 2).
QUENCHED_SSFR = 1e-11
# A fossil group: the brightest two members >= 2 mag apart in r (Jones
# et al. 2003, MNRAS 343, 627).
FOSSIL_GAP = 2.0


def _classify(host_mvir_msun: float, n_bright: int) -> str:
    """Cluster / Group by host halo mass; below that Small group, Pair or
    Isolated by the number of members of at least BRIGHT_MSTAR."""
    if host_mvir_msun >= CLUSTER_MVIR:
        return "Cluster"
    if host_mvir_msun >= GROUP_MVIR:
        return "Group"
    if n_bright >= 3:
        return "Small group"
    if n_bright == 2:
        return "Pair"
    return "Isolated"


def classify_members(galaxies, members, host_mvir_msun: float) -> str:
    """_classify for a group given by its member rows."""
    n = int(np.sum(galaxies.stellar_mass[members] >= BRIGHT_MSTAR))
    return _classify(host_mvir_msun, n)


def host_mass(galaxies, members, hubble_h: float) -> float:
    """The group's host halo mass (Msun): its central's Mvir, else the
    members' CentralMvir."""
    gt = galaxies.gal_type[members]
    cen = members[gt == 0]
    if len(cen):
        return float(galaxies.mvir[cen[0]]) * 1.0e10 / max(hubble_h, 1e-6)
    cm = galaxies.central_mvir[members]
    return float(cm.max()) if len(cm) else 0.0


def galaxy_label(galaxies, i: int) -> str:
    """How a galaxy is named to the user: SAGE's own GalaxyIndex (rows of
    the loaded catalogue are internal), or its row only in a catalogue
    without GalaxyIndex."""
    gid = getattr(galaxies, "galaxy_id", None)
    if gid is not None and i < len(gid) and int(gid[i]):
        return str(int(gid[i]))
    return f"row {int(i)}"


def row_for_galaxy_index(galaxies, gid: int) -> int | None:
    """The loaded row of the galaxy with GalaxyIndex `gid` (its first copy
    in a lightcone), or None; a catalogue without GalaxyIndex takes `gid`
    as the row."""
    ids = getattr(galaxies, "galaxy_id", None)
    if ids is None or not np.any(ids):
        return int(gid) if 0 <= int(gid) < galaxies.count else None
    hit = np.flatnonzero(ids == int(gid))
    return int(hit[0]) if len(hit) else None


# A lightcone's FOF group: the rows with its CentralGalaxyIndex within
# this many of the host's Rvir of its central (99% of satellites are
# inside 1.5 Rvir in microUchuu cones), or CONE_GROUP_MPC when the central
# is outside the cone.
CONE_GROUP_RVIR = 3.0
CONE_GROUP_MPC = 2.0  # Mpc/h


def member_indices(galaxies: GalaxySnapshot, idx: int) -> np.ndarray:
    """Return the array of indices belonging to the same FOF group as idx."""
    if galaxies.count == 0 or idx < 0 or idx >= galaxies.count:
        return np.array([], dtype=np.int64)
    cid = galaxies.central_id[idx]
    rows = np.where(galaxies.central_id == cid)[0]
    if getattr(galaxies, "snap_nums", None) is None or len(rows) < 2:
        return rows
    return _cone_members(galaxies, idx, rows)


def _cone_members(galaxies, idx: int, rows: np.ndarray) -> np.ndarray:
    """Galaxy idx's group in a lightcone.  The cone repeats the box, so
    the same group (same CentralGalaxyIndex) turns up in several tiles,
    and a group on the boundary between two snapshot shells can have the
    same galaxy twice (once from each snapshot): the members are the
    copies around this one's central, each galaxy once."""
    pos = np.asarray(galaxies.positions, float)
    gid = galaxies.galaxy_id
    cen = rows[gid[rows] == galaxies.central_id[idx]]
    if len(cen):
        c = cen[np.argmin(np.linalg.norm(pos[cen] - pos[idx], axis=1))]
        reach = max(CONE_GROUP_RVIR * float(galaxies.rvir[c]), 0.3)
        ref = pos[c]
    else:
        reach, ref = CONE_GROUP_MPC, pos[idx]
    near = rows[np.linalg.norm(pos[rows] - ref, axis=1) <= reach]
    if idx not in near:
        near = np.append(near, idx)
    # One copy of each galaxy: this one's, else the one from its snapshot.
    sn = galaxies.snap_nums
    keep = {}
    for r in near:
        g = int(gid[r])
        if g == 0:
            keep[("row", int(r))] = int(r)
            continue
        old = keep.get(g)
        if (
            old is None
            or r == idx
            or (old != idx and sn[r] == sn[idx] and sn[old] != sn[idx])
        ):
            keep[g] = int(r)
    return np.array(sorted(keep.values()), dtype=np.int64)


def group_summary(galaxies, members, hubble_h: float) -> list:
    """(label, value) rows describing the FOF group `members` (central
    first): its halo, richness, dynamics and stellar content, as an
    observer of groups and clusters would quote them."""
    members = np.asarray(members, dtype=np.int64)
    if len(members) == 0:
        return []
    h = max(hubble_h, 1e-6)
    sm = galaxies.stellar_mass[members].astype(float)
    mvir = host_mass(galaxies, members, hubble_h)
    lead = int(members[0])
    out = [
        ("Type", classify_members(galaxies, members, mvir)),
        ("Host Mvir", f"{mvir:.2e} M☉"),
    ]
    if galaxies.gal_type[lead] == 0 and galaxies.rvir[lead] > 0:
        out.append(("Host Rvir", f"{galaxies.rvir[lead] * 1e3 / h:.0f} kpc"))
    n_b = int(np.sum(sm >= BRIGHT_MSTAR))
    out.append(("Members", f"{len(members)} ({n_b} with M* ≥ 1e9 M☉)"))
    # Velocity dispersion along one axis (3D / sqrt 3), from the members'
    # velocities where the catalogue has them.
    vel = [
        galaxies.extra.get(f"Vel{c}") if galaxies.extra else None
        for c in "xyz"
    ]
    if len(members) >= 3 and all(v is not None for v in vel):
        v = np.column_stack([np.asarray(c)[members] for c in vel]).astype(
            float
        )
        sig = float(np.sqrt(np.sum(np.var(v, axis=0)) / 3.0))
        out.append(("σ_v (1D)", f"{sig:.0f} km/s"))
    tot = float(sm.sum())
    out.append(("Total M*", f"{tot:.2e} M☉"))
    order = np.argsort(-sm)
    if len(members) >= 2 and sm[order[1]] > 0:
        out.append(
            (
                "M* gap (1st/2nd)",
                f"{np.log10(sm[order[0]] / sm[order[1]]):.2f} dex",
            )
        )
        mags = galaxies.sed_mags or {}
        r = mags.get("mag_obs_sdss_r")
        if r is not None:
            mr = np.sort(np.asarray(r)[members][np.isfinite(r[members])])
            if len(mr) >= 2:
                gap = float(mr[1] - mr[0])
                out.append(
                    (
                        "Δm12 (r)",
                        f"{gap:.2f} mag"
                        + (" · fossil" if gap >= FOSSIL_GAP else ""),
                    )
                )
    ssfr = galaxies.ssfr[members]
    if len(members) >= 2:
        out.append(
            (
                "Quenched",
                f"{np.mean(ssfr < QUENCHED_SSFR):.0%} (sSFR < 1e-11 /yr)",
            )
        )
    ics = float(galaxies.ics_mass[lead])
    if ics > 0:
        out.append(
            (
                "Intracluster light",
                f"{ics:.2e} M☉ ({ics / (ics + tot):.0%} of stars)",
            )
        )
    hot = float(galaxies.hot_gas[lead]) + float(galaxies.cgm_gas[lead])
    if hot > 0:
        out.append(("Hot gas + CGM", f"{hot:.2e} M☉"))
    return out
