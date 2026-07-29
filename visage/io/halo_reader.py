from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from joblib import Parallel, delayed

# Matches the C struct written by lhalo_binary tree code
HALO_DTYPE = np.dtype(
    [
        ("Descendant", np.int32),
        ("FirstProgenitor", np.int32),
        ("NextProgenitor", np.int32),
        ("FirstHaloInFOFgroup", np.int32),
        ("NextHaloInFOFgroup", np.int32),
        ("Len", np.int32),
        ("M_Mean200", np.float32),
        ("Mvir", np.float32),
        ("M_TopHat", np.float32),
        ("Pos", np.float32, (3,)),
        ("Vel", np.float32, (3,)),
        ("VelDisp", np.float32),
        ("Vmax", np.float32),
        ("Spin", np.float32, (3,)),
        ("MostBoundID", np.int64),
        ("SnapNum", np.int32),
        ("FileNr", np.int32),
        ("SubhaloIndex", np.int32),
        ("SubHalfMass", np.float32),
    ]
)


_RHOCRIT0 = 27.75  # critical density at z=0, units: 10^10 Msun/h per (Mpc/h)^3
_DELTA = 200.0  # virial overdensity

# Per-snapshot load chatter is silenced (e.g. during background preload) by
# flipping this off, so the startup browser URL isn't buried in the terminal.
VERBOSE = True


def _compute_rvir(mvir_tree: np.ndarray) -> np.ndarray:
    """Rvir in Mpc/h from Mvir in 10^10 Msun/h (z=0 approximation)."""
    return (mvir_tree / (4.0 / 3.0 * np.pi * _DELTA * _RHOCRIT0)) ** (
        1.0 / 3.0
    )


def _compute_vvir(rvir: np.ndarray) -> np.ndarray:
    """Vvir in km/s from Rvir in Mpc/h (z=0, H0=100h km/s/(Mpc/h))."""
    # Vvir^2 = 50 * H0^2 * Rvir^2  with H0=100 km/s/(Mpc/h)
    return np.sqrt(50.0) * 100.0 * rvir


@dataclass
class HaloSnapshot:
    positions: np.ndarray  # (N, 3) float32, Mpc/h
    masses: np.ndarray  # (N,)   float32, Msun
    vmax: np.ndarray  # (N,)   float32, km/s
    rvir: np.ndarray  # (N,)   float32, Mpc/h  (computed from Mvir)
    vvir: np.ndarray  # (N,)   float32, km/s   (computed from Rvir)
    snap_num: int

    @property
    def count(self) -> int:
        return len(self.positions)

    @classmethod
    def empty(cls, snap_num: int) -> HaloSnapshot:
        z = np.empty(0, dtype=np.float32)
        return cls(
            positions=np.empty((0, 3), dtype=np.float32),
            masses=z,
            vmax=z,
            rvir=z,
            vvir=z,
            snap_num=snap_num,
        )


def _read_tree_file(
    tree_file: Path,
    snap_num: int,
    mass_cut_msun: float,
    hubble_h: float,
    box_size: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Read one lhalo_binary tree file and return (positions, masses) for snap_num."""
    if not tree_file.exists():
        return np.empty((0, 3), dtype=np.float32), np.empty(
            0, dtype=np.float32
        )

    _empty = np.empty((0, 3), dtype=np.float32)
    _empty_ret = (_empty, _empty, _empty, _empty, _empty)
    with open(tree_file, "rb") as f:
        nforests = np.fromfile(f, dtype=np.int32, count=1)[0]
        nhalos_total = np.fromfile(f, dtype=np.int32, count=1)[0]

        if nhalos_total == 0:
            return _empty_ret

        # Skip past the per-forest halo counts to reach the halo records
        # (this fromfile advances the file cursor; the values are unused).
        np.fromfile(f, dtype=np.int32, count=nforests)
        halos = np.fromfile(f, dtype=HALO_DTYPE, count=nhalos_total)

    snap_glob = np.flatnonzero(halos["SnapNum"] == snap_num)
    if len(snap_glob) == 0:
        return _empty_ret
    snap_halos = halos[snap_glob]

    # Mvir in tree files is in units of 1e10 Msun/h. Satellites carry Mvir=0,
    # so the mass cut keeps only FOF centrals (what we render as splats).
    mvir_tree = snap_halos["Mvir"].astype(np.float32)  # 10^10 Msun/h
    masses = mvir_tree * 1.0e10 / hubble_h  # Msun
    mass_mask = masses > mass_cut_msun

    return (
        snap_halos["Pos"][mass_mask],
        masses[mass_mask],
        snap_halos["Vmax"].astype(np.float32)[mass_mask],
        _compute_rvir(mvir_tree[mass_mask]),
        _compute_vvir(_compute_rvir(mvir_tree[mass_mask])),
    )


def load_halo_snapshot(
    tree_dir: str | Path,
    tree_name: str,
    snap_num: int,
    first_file: int = 0,
    last_file: int = 7,
    mass_cut: float = 1.0e10,
    max_halos: int = 100_000,
    hubble_h: float = 0.73,
    n_jobs: int = -1,
    box_size: float = 0.0,
) -> HaloSnapshot:
    """Load halo positions and masses for one snapshot from lhalo_binary tree files.

    Parameters
    ----------
    tree_dir:  directory containing the tree files
    tree_name: base name (e.g. 'trees_063'); files are tree_name.{first_file..last_file}
    snap_num:  snapshot index to extract
    mass_cut:  minimum halo mass in Msun (after h correction)
    max_halos: random downsample if more haloes than this are found
    n_jobs:    joblib parallel workers (-1 = all CPUs)
    """
    tree_dir = Path(tree_dir)
    tree_files = [
        tree_dir / f"{tree_name}.{i}" for i in range(first_file, last_file + 1)
    ]
    n_files = len(tree_files)
    if VERBOSE:
        print(
            f"  Haloes: reading {n_files} tree file(s) in parallel (snap {snap_num})..."
        )

    # prefer="threads": file I/O releases the GIL so threads are fully parallel
    # and avoid the semaphore / mmap leak that loky process pools produce
    results = Parallel(n_jobs=n_jobs, prefer="threads")(
        delayed(_read_tree_file)(tf, snap_num, mass_cut, hubble_h, box_size)
        for tf in tree_files
    )

    results = [r for r in results if len(r[0]) > 0]
    if not results:
        if VERBOSE:
            print(f"  Haloes: none found above mass cut ({mass_cut:.1e} Msun)")
        return HaloSnapshot.empty(snap_num)

    positions = np.vstack([r[0] for r in results])
    masses = np.concatenate([r[1] for r in results])
    vmax = np.concatenate([r[2] for r in results])
    rvir = np.concatenate([r[3] for r in results])
    vvir = np.concatenate([r[4] for r in results])

    if len(positions) > max_halos:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(positions), max_halos, replace=False)
        positions, masses, vmax, rvir, vvir = (
            positions[idx],
            masses[idx],
            vmax[idx],
            rvir[idx],
            vvir[idx],
        )

    if VERBOSE:
        print(f"  Haloes: {len(positions):,} loaded")
    return HaloSnapshot(
        positions=positions,
        masses=masses,
        vmax=vmax,
        rvir=rvir,
        vvir=vvir,
        snap_num=snap_num,
    )
