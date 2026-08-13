"""Reader for SAGE's HDF5 merger trees (``TreeType lhalo_hdf5``).

Same halo content as the lhalo_binary trees that :mod:`visage.io.halo_reader`
reads, but the datasets are named differently and stored per tree:

    <file>.hdf5
      Header/TreeNHalos
      Tree0/  SnapNum, Group_M_Crit200, SubhaloPos, SubhaloVMax,
              FirstHaloInFOFGroup, ...
      Tree1/  ...

There is no ``Mvir`` dataset at all — the halo mass lives in one of the
``Group_M_*`` columns, and which of them is populated varies between tree
sets. SAGE's own reader maps ``Group_M_Crit200`` onto its ``Mvir`` field
("sage uses Mvir but assumes that contains M200c", ``read_tree_lhalo_hdf5.c``),
so we resolve the mass by trying a list of aliases and taking the first one
that actually carries values.

Two things differ from the binary path and are handled here:

* **Positions are kpc/h** in these files (SAGE multiplies by 1e-3). We detect
  the scale from the box size rather than assuming it.
* **The mass columns are populated for satellites too**, so the mass cut alone
  no longer isolates FOF centrals the way it does for lhalo_binary trees
  (where satellites carry Mvir=0). We select centrals explicitly via
  ``FirstHaloInFOFGroup``.

Reading is per-tree and h5py serialises it, so a full file costs ~1 minute and
parallelising doesn't help. Each file is therefore scanned **once** into an
in-memory index of every snapshot, and per-snapshot requests are served from
that — otherwise preloading N snapshots would re-read the whole file N times.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import h5py
import numpy as np

from visage.io import halo_reader
from visage.io.halo_reader import _compute_rvir, _compute_vvir

# Candidate dataset names per column, in order of preference. Halo mass is
# the one that genuinely varies between tree sets; the rest are listed so a
# file using either the binary struct's spelling or the Illustris/LHaloTree
# HDF5 spelling reads without special-casing.
MASS_ALIASES = (
    "Mvir",
    "Group_M_Crit200",
    "M_Crit200",
    "Mass_200crit",
    "M200c",
    "Group_M_TopHat200",
    "M_TopHat200",
    "M_TopHat",
    "Group_M_Mean200",
    "M_Mean200",
    "Mass_200mean",
)
POS_ALIASES = ("Pos", "SubhaloPos", "Position", "Positions")
VMAX_ALIASES = ("Vmax", "SubhaloVMax", "SubhaloVmax", "Vmax_Rmax")
SNAP_ALIASES = ("SnapNum", "SnapshotNumber", "Snapshot", "Snap_num")
FOF_ALIASES = ("FirstHaloInFOFgroup", "FirstHaloInFOFGroup")

# Groups that hold file metadata rather than haloes.
_META_GROUPS = ("header", "cosmology", "units", "parameters")


def _resolve(keys: dict, aliases: tuple[str, ...]) -> str | None:
    """First alias present among ``keys`` (case-insensitively), else None."""
    lower = {k.lower(): k for k in keys}
    for alias in aliases:
        hit = lower.get(alias.lower())
        if hit is not None:
            return hit
    return None


def _halo_groups(f: h5py.File) -> list[str]:
    """Names of the per-tree groups holding halo records."""
    out = []
    for key in f.keys():
        if key.lower() in _META_GROUPS:
            continue
        obj = f[key]
        if isinstance(obj, h5py.Group) and _resolve(obj, SNAP_ALIASES):
            out.append(key)
    return out


def _pick_mass_dataset(
    f: h5py.File, groups: list[str], probe: int = 32
) -> str | None:
    """Choose the mass dataset: first alias present *and* populated.

    Presence isn't enough — these files carry all three ``Group_M_*`` columns
    but populate only one, so an alias whose values are all zero must fall
    through to the next. A handful of trees is a large enough sample to tell
    (each holds thousands of haloes), and probing beats reading every column
    of every tree.
    """
    if not groups:
        return None
    candidates = []
    first = f[groups[0]]
    lower = {k.lower(): k for k in first}
    for alias in MASS_ALIASES:
        hit = lower.get(alias.lower())
        if hit is not None and hit not in candidates:
            candidates.append(hit)
    if not candidates:
        return None

    for name in candidates:
        for gname in groups[:probe]:
            col = f[gname][name][:]
            if np.any(np.isfinite(col) & (col > 0.0)):
                return name
    # Every candidate looked empty in the probe — keep the preferred one so
    # the caller reports a sane field name rather than failing outright.
    return candidates[0]


def _position_scale(pos_max: float, box_size: float) -> float:
    """kpc/h → Mpc/h factor, or 1.0 if the positions are already Mpc/h.

    LHaloTree HDF5 files store positions in kpc/h and SAGE scales them by
    1e-3. Rather than hardcode that, infer it: positions spanning far more
    than the box can't be in the box's own units.
    """
    if box_size > 0.0:
        return 1.0e-3 if pos_max > 10.0 * box_size else 1.0
    # No box size to compare against: no SAGE box is larger than 10^4 Mpc/h,
    # so a span beyond that means kpc/h.
    return 1.0e-3 if pos_max > 1.0e4 else 1.0


@dataclass
class _TreeIndex:
    """Every FOF-central halo in one tree file, all snapshots, concatenated."""

    positions: np.ndarray  # (H, 3) float32, Mpc/h
    mass_raw: np.ndarray  # (H,)   float32, 10^10 Msun/h
    vmax: np.ndarray  # (H,)   float32, km/s
    snapnum: np.ndarray  # (H,)   int32
    mass_field: str  # dataset the mass came from


_cache: dict[tuple, _TreeIndex] = {}
_cache_locks: dict[tuple, Lock] = {}
_locks_guard = Lock()


def _build_index(path: Path, box_size: float) -> _TreeIndex:
    """Scan one HDF5 tree file into a per-snapshot-searchable index."""
    with h5py.File(path, "r") as f:
        groups = _halo_groups(f)
        mass_field = _pick_mass_dataset(f, groups)
        if mass_field is None:
            raise KeyError(
                f"{path}: no halo-mass dataset found (tried "
                f"{', '.join(MASS_ALIASES)})"
            )
        first = f[groups[0]]
        pos_field = _resolve(first, POS_ALIASES)
        snap_field = _resolve(first, SNAP_ALIASES)
        vmax_field = _resolve(first, VMAX_ALIASES)
        fof_field = _resolve(first, FOF_ALIASES)
        if pos_field is None or snap_field is None:
            raise KeyError(
                f"{path}: tree groups have no recognisable position/snapshot "
                f"datasets (found {sorted(first.keys())})"
            )

        if halo_reader.VERBOSE:
            print(
                f"  Haloes: indexing {len(groups):,} trees in {path.name} "
                f"(mass from {mass_field}; first load only)..."
            )

        pos_parts, mass_parts, vmax_parts, snap_parts = [], [], [], []
        for gname in groups:
            grp = f[gname]
            snap = grp[snap_field][:]
            n = len(snap)
            if n == 0:
                continue
            # FOF centrals point at themselves; indices are tree-local. Without
            # a FOF column keep everything and let the mass cut decide.
            if fof_field is not None:
                keep = grp[fof_field][:] == np.arange(n, dtype=np.int32)
            else:
                keep = np.ones(n, dtype=bool)
            if not keep.any():
                continue
            pos_parts.append(grp[pos_field][:][keep])
            mass_parts.append(grp[mass_field][:][keep])
            snap_parts.append(snap[keep])
            vmax_parts.append(
                grp[vmax_field][:][keep]
                if vmax_field is not None
                else np.zeros(int(keep.sum()), dtype=np.float32)
            )

    if not pos_parts:
        empty = np.empty(0, dtype=np.float32)
        return _TreeIndex(
            positions=np.empty((0, 3), dtype=np.float32),
            mass_raw=empty,
            vmax=empty,
            snapnum=np.empty(0, dtype=np.int32),
            mass_field=mass_field,
        )

    positions = np.concatenate(pos_parts).astype(np.float32, copy=False)
    scale = _position_scale(float(positions.max()), box_size)
    if scale != 1.0:
        positions = positions * np.float32(scale)

    index = _TreeIndex(
        positions=positions,
        mass_raw=np.concatenate(mass_parts).astype(np.float32, copy=False),
        vmax=np.concatenate(vmax_parts).astype(np.float32, copy=False),
        snapnum=np.concatenate(snap_parts).astype(np.int32, copy=False),
        mass_field=mass_field,
    )
    if halo_reader.VERBOSE:
        snaps = np.unique(index.snapnum)
        units = " (positions kpc/h → Mpc/h)" if scale != 1.0 else ""
        print(
            f"  Haloes: indexed {len(index.mass_raw):,} host haloes across "
            f"{len(snaps)} snapshots{units}"
        )
    return index


def _get_index(path: Path, box_size: float) -> _TreeIndex:
    """Return the cached index for ``path``, building it once if needed.

    Snapshots load on several threads, so the build is locked per file: the
    first caller scans and the rest wait for it instead of duplicating a
    minute of I/O.
    """
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    with _locks_guard:
        lock = _cache_locks.setdefault(key, Lock())
    with lock:
        hit = _cache.get(key)
        if hit is None:
            hit = _build_index(path, box_size)
            _cache[key] = hit
    return hit


def read_snapshot(
    tree_file: Path,
    snap_num: int,
    mass_cut_msun: float,
    hubble_h: float,
    box_size: float = 0.0,
) -> tuple:
    """Halo columns for one snapshot, matching ``halo_reader._read_tree_file``.

    Returns (positions, masses, vmax, rvir, vvir, mass_field).
    """
    index = _get_index(Path(tree_file), box_size)
    sel = index.snapnum == snap_num
    if not sel.any():
        return halo_reader._empty_result()

    mass_raw = index.mass_raw[sel]
    masses = mass_raw * 1.0e10 / hubble_h  # Msun
    keep = masses > mass_cut_msun
    rvir = _compute_rvir(mass_raw[keep])
    return (
        index.positions[sel][keep],
        masses[keep],
        index.vmax[sel][keep],
        rvir,
        _compute_vvir(rvir),
        index.mass_field,
    )


def clear_cache() -> None:
    """Drop every cached file index (used by the tests)."""
    _cache.clear()
