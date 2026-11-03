"""Following one galaxy through the snapshots of a box.

A galaxy keeps its GalaxyIndex for life, so its past and future are the
rows with that index.  Two things break the simple lookup:

- A merger.  The galaxy's last row gives mergeIntoSnapNum and mergeIntoID,
  the target's row among the rows of the same forest in that snapshot.
  The track carries on with the target.
- A gap.  A subhalo the halo finder loses for a snapshot takes its galaxy
  with it (mergeType 0, no row), and the galaxy returns later.  The track
  waits for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable

import h5py
import numpy as np

from visage.io.sage_files import galaxy_files, open_snapshot

# GalaxyIndex is filenr * FileNr_Mulfac + forestnr * ForestNr_Mulfac +
# GalaxyNr.  SAGE records its multiplier in /TreeInfo; this is its value for
# the tree formats that older outputs came from.
DEFAULT_FOREST_MULFAC = 10**9

MERGE_KINDS = {1: "minor merger", 2: "major merger", 4: "disrupted"}


@dataclass
class Track:
    """One track, oldest snapshot first.  ``galaxy_id[i]`` is the galaxy
    followed at ``snaps[i]``; it changes where a merger hands over."""

    snaps: list[int] = field(default_factory=list)
    galaxy_id: list[int] = field(default_factory=list)
    pos: list[tuple[float, float, float]] = field(default_factory=list)
    # The central of its group at each snapshot, for following a halo.
    central_id: list[int] = field(default_factory=list)
    central_pos: list[tuple[float, float, float]] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    cancelled: bool = False


def forest_mulfac(first: str | Path) -> int:
    """How many GalaxyIndex values one forest spans in this run."""
    with h5py.File(galaxy_files(first)[0], "r") as f:
        info = f.get("TreeInfo")
        value = None if info is None else info.attrs.get("ForestNr_Mulfac")
    return int(value) if value else DEFAULT_FOREST_MULFAC


def merge_target(ids: np.ndarray, gid: int, row: int, mulfac: int):
    """The GalaxyIndex at row ``row`` of ``gid``'s forest, in a snapshot
    whose GalaxyIndex column is ``ids``; None if there is no such row."""
    rows = np.flatnonzero(ids // mulfac == gid // mulfac)
    return int(ids[rows[row]]) if 0 <= row < len(rows) else None


def _column(group, name: str, row: int, default: float = -1):
    return group[name][row] if name in group else default


def _row(group, gid: int) -> tuple:
    """(the snapshot's GalaxyIndex column, ``gid``'s row or None)."""
    ids = np.asarray(group["GalaxyIndex"]).astype(np.int64)
    hit = np.flatnonzero(ids == gid)
    return ids, int(hit[0]) if len(hit) else None


def _position(group, row: int) -> tuple[float, float, float]:
    return tuple(float(group[c][row]) for c in ("Posx", "Posy", "Posz"))


def _entry(group, ids: np.ndarray, row: int, snap: int) -> tuple:
    """(snapshot, galaxy, its position, its central, the central's position)."""
    gid = int(ids[row])
    central = int(_column(group, "CentralGalaxyIndex", row, gid))
    hit = np.flatnonzero(ids == central)
    return (
        snap,
        gid,
        _position(group, row),
        central,
        _position(group, int(hit[0]) if len(hit) else row),
    )


def follow(
    first: str | Path,
    galaxy_id: int,
    start: int,
    snaps: list[int],
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Track:
    """The track of ``galaxy_id`` over ``snaps``, starting from ``start``.

    Earlier snapshots hold the galaxy itself, from when it formed.  Later
    ones carry on through its mergers.  A snapshot it is missing from is
    left out, so the caller decides how to cross the gap.  ``progress`` is
    called with (done, total); ``cancelled`` stops the walk early.
    """
    snaps = sorted(int(s) for s in snaps)
    mulfac = forest_mulfac(first)
    total, done = len(snaps), 0
    before, after = [], []
    events: list[dict] = []
    track = Track()

    def stop() -> bool:
        track.cancelled = bool(cancelled and cancelled())
        return track.cancelled

    def tick() -> None:
        nonlocal done
        done += 1
        if progress:
            progress(done, total)

    for snap in reversed([s for s in snaps if s < start]):
        if stop():
            return track
        with open_snapshot(first, snap) as group:
            if group is not None:
                ids, row = _row(group, galaxy_id)
                if row is not None:
                    before.append(_entry(group, ids, row, snap))
        tick()

    gid = galaxy_id
    pending = None  # the merger waiting for its target's snapshot
    for snap in [s for s in snaps if s >= start]:
        if stop():
            return track
        with open_snapshot(first, snap) as group:
            if group is None:
                tick()
                continue
            ids, row = _row(group, gid)
            if pending and snap >= pending["snap"]:
                target = merge_target(ids, gid, pending["row"], mulfac)
                if snap > pending["snap"] or target is None:
                    events.append(
                        {
                            "kind": "lost",
                            "snap": snap,
                            "galaxy_id": gid,
                        }
                    )
                    tick()
                    break
                events.append(
                    {
                        "kind": pending["kind"],
                        "snap": snap,
                        "galaxy_id": gid,
                        "into": target,
                    }
                )
                gid, pending = target, None
                _, row = _row(group, gid)
            if row is not None:
                after.append(_entry(group, ids, row, snap))
                into = int(_column(group, "mergeIntoID", row))
                kind = int(_column(group, "mergeType", row, 0))
                if kind > 0 and into < 0:
                    # Merged, but its target's snapshot wasn't written.
                    events.append(
                        {
                            "kind": "lost",
                            "snap": snap,
                            "galaxy_id": gid,
                        }
                    )
                    tick()
                    break
                if kind > 0:
                    pending = {
                        "snap": int(_column(group, "mergeIntoSnapNum", row)),
                        "row": into,
                        "kind": MERGE_KINDS.get(kind, "merger"),
                    }
        tick()

    # The branch stopped with no merger on record, so there is nothing to
    # carry on with.
    final = (snaps or [start])[-1]
    closed = events and events[-1]["kind"] == "lost"
    if after and after[-1][0] != final and not pending and not closed:
        events.append(
            {"kind": "ended", "snap": after[-1][0], "galaxy_id": after[-1][1]}
        )

    for snap, gid, pos, central, central_pos in [*reversed(before), *after]:
        track.snaps.append(snap)
        track.galaxy_id.append(gid)
        track.pos.append(pos)
        track.central_id.append(central)
        track.central_pos.append(central_pos)
    track.events = events
    return track


def camera_centres(
    track: Track, snaps: list[int], box: float, halo: bool = False
) -> dict:
    """Where to look at each of ``snaps`` the track covers: the galaxy, or
    with ``halo`` the central of its group.

    A snapshot in a gap gets a point on the line between its neighbours,
    the short way round the periodic box."""
    if not track.snaps:
        return {}
    known = np.asarray(track.snaps, dtype=float)
    points = track.central_pos if halo else track.pos
    pos = np.unwrap(np.asarray(points, float), axis=0, period=box)
    out = {}
    for snap in snaps:
        if known[0] <= snap <= known[-1]:
            out[int(snap)] = tuple(
                float(np.interp(snap, known, pos[:, c]) % box)
                for c in range(3)
            )
    return out


def captions(track: Track, hold: int = 3, halo: bool = False) -> dict:
    """What the view says at each snapshot: an event, for ``hold``
    snapshots from when it happened."""
    out: dict[int, str] = {}
    if halo:
        steps = zip(track.snaps, track.central_id, strict=False)
        last = None
        for i, (snap, central) in enumerate(steps):
            joined = last is not None and central != last
            if joined and central != track.galaxy_id[i]:
                for held in range(snap, snap + hold):
                    out[held] = f"Now in the halo of galaxy {central}"
            last = central
    for event in track.events:
        if event["kind"] in ("ended", "lost"):
            continue
        name = event["kind"].capitalize()
        text = f"{name}: now following galaxy {event['into']}"
        for snap in range(event["snap"], event["snap"] + hold):
            out[snap] = text
    return {s: out[s] for s in track.snaps if s in out}


def nearest_image(points, centre, box: float) -> np.ndarray:
    """``points`` at their images nearest ``centre`` in the periodic box."""
    centre = np.asarray(centre, float)
    return (
        centre + (np.asarray(points, float) - centre + box / 2) % box - box / 2
    )


def merge_chains(first: str | Path, galaxy_id: int, snaps: list[int]):
    """The merger links of ``galaxy_id``'s forest.  Mergers stay inside a
    forest, so nothing else is read.  Returns ({snapshot: GalaxyIndex of the
    forest's rows, in file order}, {galaxy: the galaxy it merged into})."""
    mulfac = forest_mulfac(first)
    forest = galaxy_id // mulfac
    rows, merged = {}, []
    for snap in sorted(snaps):
        with open_snapshot(first, snap) as group:
            if group is None:
                continue
            ids = np.asarray(group["GalaxyIndex"]).astype(np.int64)
            here = np.flatnonzero(ids // mulfac == forest)
            rows[snap] = ids[here]
            if "mergeIntoID" not in group or "mergeIntoSnapNum" not in group:
                continue
            into = np.asarray(group["mergeIntoID"])[here]
            at = np.asarray(group["mergeIntoSnapNum"])[here]
            for i in np.flatnonzero(into >= 0):
                merged.append((int(ids[here[i]]), int(at[i]), int(into[i])))
    links = {}
    for gid, snap, row in merged:
        if snap in rows and row < len(rows[snap]):
            links[gid] = int(rows[snap][row])
    return rows, links


def reaches(gid: int, targets: set, links: dict) -> bool:
    """Does ``gid`` end up in one of ``targets``, or is it one?"""
    seen = set()
    while gid not in seen:
        if gid in targets:
            return True
        seen.add(gid)
        if gid not in links:
            return False
        gid = links[gid]
    return False


def group_members(first: str | Path, galaxy_id: int, snap: int) -> set:
    """The GalaxyIndex of every galaxy in ``galaxy_id``'s group at ``snap``."""
    with open_snapshot(first, snap) as group:
        if group is None:
            return {galaxy_id}
        ids, row = _row(group, galaxy_id)
        if row is None or "CentralGalaxyIndex" not in group:
            return {galaxy_id}
        centrals = np.asarray(group["CentralGalaxyIndex"])
        return {int(g) for g in ids[centrals == centrals[row]]}


def contributors(
    first: str | Path, path: dict, snaps: list[int], halo: bool = False
) -> dict:
    """{snapshot: the galaxies there that end up in what is followed}.

    ``path`` is {snapshot: GalaxyIndex followed}.  Counted at the end of the
    track: the last galaxy followed, or with ``halo`` every member of its
    group, satellites as well as mergers."""
    if not path:
        return {}
    end = max(path)
    rows, links = merge_chains(first, path[end], snaps)
    targets = group_members(first, path[end], end) if halo else {path[end]}
    out = {}
    for snap in sorted(path):
        out[snap] = [
            int(g)
            for g in rows.get(snap, ())
            if reaches(int(g), targets, links)
        ]
    return out


# A halo merger is major when the smaller halo had at least a third of the
# larger's mass just before it fell in (e.g. Fakhouri, Ma & Boylan-Kolchin
# 2010, MNRAS 406, 2267).
MAJOR_RATIO = 1.0 / 3.0


@dataclass
class HaloHistory:
    """The host halo of one galaxy, oldest snapshot first: its mass
    (``mvir``, 1e10 Msun/h, as SAGE writes it) at each of ``snaps``, and
    the haloes that fell into it as (snapshot, mass ratio, smaller over
    larger) in ``mergers``."""

    snaps: list[int] = field(default_factory=list)
    mvir: list[float] = field(default_factory=list)
    mergers: list[tuple[int, float]] = field(default_factory=list)

    def formed(self) -> int | None:
        """The first snapshot its halo had half its last mass."""
        if not self.mvir:
            return None
        half = 0.5 * self.mvir[-1]
        return next(
            s for s, m in zip(self.snaps, self.mvir, strict=True) if m >= half
        )

    def last_major(self) -> tuple[int, float] | None:
        major = [m for m in self.mergers if m[1] >= MAJOR_RATIO]
        return major[-1] if major else None


def halo_history(first: str | Path, galaxy_id: int, snap: int) -> HaloHistory:
    """The history of the halo ``galaxy_id`` lives in, up to ``snap``.

    A halo is its group, and its mass its central's Mvir.  Going back a
    snapshot, its progenitors are the groups its members were in then:
    the most massive carries the history on (its main branch), and the
    others are haloes that fell in.  Haloes only merge inside a forest,
    so only the forest's rows are read."""
    mulfac = forest_mulfac(first)
    forest = galaxy_id // mulfac
    rows = {}  # snapshot: (GalaxyIndex, its central, Mvir) of the forest
    for s in range(int(snap) + 1):
        with open_snapshot(first, s) as group:
            if group is None or "CentralGalaxyIndex" not in group:
                continue
            ids = np.asarray(group["GalaxyIndex"]).astype(np.int64)
            here = np.flatnonzero(ids // mulfac == forest)
            rows[s] = (
                ids[here],
                np.asarray(group["CentralGalaxyIndex"])[here].astype(np.int64),
                np.asarray(group["Mvir"])[here].astype(float),
            )

    def mass(s: int, central: int) -> float:
        ids, _, mvir = rows[s]
        at = np.flatnonzero(ids == central)
        return float(mvir[at[0]]) if len(at) else 0.0

    out = HaloHistory()
    if snap not in rows:
        return out
    ids, cen, _ = rows[snap]
    at = np.flatnonzero(ids == galaxy_id)
    if not len(at):
        return out
    host = int(cen[at[0]])
    back = [(int(snap), mass(snap, host))]
    for s in sorted((k for k in rows if k < snap), reverse=True):
        later = back[-1][0]
        ids, cen, _ = rows[later]
        members = ids[cen == host]
        p_ids, p_cen, _ = rows[s]
        hosts = np.unique(p_cen[np.isin(p_ids, members)])
        if not len(hosts):
            break  # it formed after this
        m = np.array([mass(s, int(c)) for c in hosts])
        main = int(np.argmax(m))
        for k in np.flatnonzero(np.arange(len(hosts)) != main):
            if m[main] > 0:
                out.mergers.append((later, float(m[k] / m[main])))
        host = int(hosts[main])
        back.append((s, float(m[main])))
    for s, m in reversed(back):
        out.snaps.append(s)
        out.mvir.append(m)
    out.mergers.sort()
    return out
