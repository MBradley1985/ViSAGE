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
                _, row = _row(group, galaxy_id)
                if row is not None:
                    before.append((snap, galaxy_id, _position(group, row)))
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
                after.append((snap, gid, _position(group, row)))
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

    for snap, gid, pos in [*reversed(before), *after]:
        track.snaps.append(snap)
        track.galaxy_id.append(gid)
        track.pos.append(pos)
    track.events = events
    return track
