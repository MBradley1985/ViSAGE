from __future__ import annotations

import os
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import fields as dataclass_fields
from threading import Lock
from collections.abc import Callable
from typing import Optional

import numpy as np
from scipy.spatial import KDTree

from visage.config import SimConfig
from visage.io.galaxy_reader import GalaxySnapshot, load_galaxy_snapshot
from visage.io.halo_reader import HaloSnapshot, load_halo_snapshot
from visage.io.snapshot_table import SnapshotTable


def _array_bytes(value) -> int:
    """Bytes held by an ndarray, or by a dict of them."""
    if isinstance(value, np.ndarray):
        return int(value.nbytes)
    if isinstance(value, dict):
        return sum(_array_bytes(v) for v in value.values())
    return 0


def snapshot_bytes(entry: tuple) -> int:
    """Rough resident size of one cached (haloes, galaxies) pair."""
    total = 0
    for snap in entry:
        for fld in dataclass_fields(snap):
            total += _array_bytes(getattr(snap, fld.name))
    return total


def default_cache_bytes() -> int:
    """How much memory snapshot caching may use by default.

    Half of physical RAM, floored at 2 GiB — a full run of a large box is
    tens of gigabytes, and pinning all of it is what makes ViSAGE run a
    machine out of memory.  `VISAGE_CACHE_GB` overrides it.
    """
    env = os.environ.get("VISAGE_CACHE_GB")
    if env:
        try:
            return max(int(float(env) * 1024**3), 256 * 1024**2)
        except ValueError:
            pass
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        total = 8 * 1024**3
    return max(int(total * 0.5), 2 * 1024**3)


class _SnapshotCache:
    """LRU snapshot cache bounded by memory, not by entry count.

    A count-based cache sized to the whole run keeps every snapshot of
    every loaded box resident; at ~200 bytes per galaxy plus haloes that
    reaches tens of gigabytes on a big box.  This evicts the
    least-recently-used snapshot once the byte budget is exceeded, and
    always keeps at least the snapshot just asked for.
    """

    def __init__(
        self,
        budget_bytes: int,
        load_fn: Callable[[int], tuple],
        on_evict: Callable[[int], None] | None = None,
    ) -> None:
        self._budget = max(int(budget_bytes), 1)
        self._load = load_fn
        self._on_evict = on_evict
        self._items: OrderedDict[int, tuple] = OrderedDict()
        self._sizes: dict[int, int] = {}
        self._bytes = 0
        self._lock = Lock()
        self._key_locks: dict[int, Lock] = {}
        self.evictions = 0

    @property
    def nbytes(self) -> int:
        return self._bytes

    def __call__(self, snap_num: int) -> tuple:
        return self.get(snap_num)

    def peek(self, snap_num: int) -> tuple | None:
        with self._lock:
            return self._items.get(snap_num)

    def get(self, snap_num: int) -> tuple:
        with self._lock:
            hit = self._items.get(snap_num)
            if hit is not None:
                self._items.move_to_end(snap_num)
                return hit
            key_lock = self._key_locks.setdefault(snap_num, Lock())

        # One loader per snapshot: prefetch threads asking for the same
        # snapshot wait for it rather than reading the files twice.
        with key_lock:
            with self._lock:
                hit = self._items.get(snap_num)
                if hit is not None:
                    self._items.move_to_end(snap_num)
                    return hit
            value = self._load(snap_num)
            size = snapshot_bytes(value)
            with self._lock:
                self._items[snap_num] = value
                self._items.move_to_end(snap_num)
                self._sizes[snap_num] = size
                self._bytes += size
                evicted = self._evict_locked(keep=snap_num)
            for snap in evicted:
                if self._on_evict is not None:
                    self._on_evict(snap)
            return value

    def _evict_locked(self, keep: int) -> list[int]:
        evicted: list[int] = []
        while self._bytes > self._budget and len(self._items) > 1:
            victim = next(iter(self._items))
            if victim == keep:
                # Never drop what was just asked for — take the next oldest.
                keys = list(self._items.keys())
                if len(keys) < 2:
                    break
                victim = keys[1]
            self._items.pop(victim, None)
            self._bytes -= self._sizes.pop(victim, 0)
            self.evictions += 1
            evicted.append(victim)
        return evicted

    def cache_clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._sizes.clear()
            self._bytes = 0


class SnapshotLoader:
    """Prefetch and cache haloes + galaxies around the current snapshot.

    Uses a thread pool so the main render thread never blocks on disk I/O.
    Keeps an LRU in-memory cache of recently loaded snapshots.

    Parameters
    ----------
    config:          parsed SimConfig
    snap_table:      SnapshotTable for the simulation
    n_jobs:          worker threads for parallel halo file reads (default: CPUs-1)
    prefetch_radius: number of snapshots ahead/behind to prefetch
    cache_size:      max snapshots kept in memory
    min_halo_mass:   Msun halo mass floor
    min_stellar_mass: Msun stellar mass floor
    cache_bytes:     memory budget for cached snapshots (None = half of
                     physical RAM, or $VISAGE_CACHE_GB)
    max_halos:       optional downsample ceiling (None = every halo)
    max_galaxies:    optional downsample ceiling (None = every galaxy)
    """

    def __init__(
        self,
        config: SimConfig,
        snap_table: SnapshotTable,
        n_jobs: int = max(1, os.cpu_count() - 1),
        prefetch_radius: int = 2,
        cache_size: int = 8,
        min_halo_mass: float = 1.0e10,
        min_stellar_mass: float = 1.0e8,
        max_halos: int | None = None,
        max_galaxies: int | None = None,
        cache_bytes: int | None = None,
    ) -> None:
        self._cfg = config
        self._snap_table = snap_table
        self._n_jobs = n_jobs
        self._prefetch_radius = prefetch_radius
        self._min_halo_mass = min_halo_mass
        self._min_stellar_mass = min_stellar_mass
        self._max_halos = max_halos
        self._max_galaxies = max_galaxies

        self._executor = ThreadPoolExecutor(
            max_workers=max(2, prefetch_radius * 2)
        )
        self._futures: dict[int, Future] = {}
        self._lock = Lock()
        self._tree_cache: dict[int, KDTree] = {}

        # Repeated requests for a snapshot skip disk entirely.  The cache
        # is bounded by memory rather than by a snapshot count, so a big
        # box fills it and then rolls, instead of holding every snapshot
        # of the run resident until the machine runs out of RAM.
        self._cache_bytes = (
            int(cache_bytes)
            if cache_bytes is not None
            else default_cache_bytes()
        )
        self._cached_load = _SnapshotCache(
            self._cache_bytes, self._load, on_evict=self._on_evict
        )

    def _load(self, snap_num: int) -> tuple[HaloSnapshot, GalaxySnapshot]:
        halos = load_halo_snapshot(
            tree_dir=self._cfg.tree_dir,
            tree_name=self._cfg.tree_name,
            tree_type=getattr(self._cfg, "tree_type", ""),
            snap_num=snap_num,
            first_file=self._cfg.first_file,
            last_file=self._cfg.last_file,
            mass_cut=self._min_halo_mass,
            max_halos=self._max_halos,
            hubble_h=self._cfg.hubble_h,
            n_jobs=self._n_jobs,
            box_size=self._cfg.box_size,
        )
        galaxies = load_galaxy_snapshot(
            hdf5_path=self._cfg.hdf5_path,
            snap_num=snap_num,
            min_stellar_mass=self._min_stellar_mass,
            max_galaxies=self._max_galaxies,
            hubble_h=self._cfg.hubble_h,
            scale_factors=self._snap_table.scale_factors,
            omega_m=self._cfg.omega,
            omega_l=self._cfg.omega_lambda,
        )
        # Build the spatial index while still on the background thread so
        # snap navigation never blocks on KDTree construction (~50 ms / snap).
        if len(halos.positions) > 0:
            self._tree_cache[snap_num] = KDTree(halos.positions)
        return halos, galaxies

    def _on_evict(self, snap_num: int) -> None:
        """Drop everything else tied to an evicted snapshot."""
        self._tree_cache.pop(snap_num, None)

    @property
    def cache_nbytes(self) -> int:
        """Bytes currently held by cached snapshots."""
        return self._cached_load.nbytes

    def get_tree(self, snap_num: int) -> KDTree | None:
        """Return the pre-built KDTree for snap_num, or None if not ready."""
        return self._tree_cache.get(snap_num)

    def get(self, snap_num: int) -> tuple[HaloSnapshot, GalaxySnapshot]:
        """Return (HaloSnapshot, GalaxySnapshot) for snap_num.

        Blocks only on a cold-cache miss; otherwise returns from memory.
        Triggers background prefetch of neighbouring snapshots as a side-effect.
        """
        result = self._cached_load(snap_num)
        self._prefetch_neighbours(snap_num)
        return result

    def preload_all(self) -> list[Future]:
        """Kick off background loads of every snapshot. Returns the futures
        so a caller can track progress. Already-loaded / in-flight snapshots
        are not resubmitted."""
        # Silence per-snapshot load chatter so it doesn't bury the startup
        # browser URL in the terminal.
        from visage.io import halo_reader, galaxy_reader

        halo_reader.VERBOSE = False
        galaxy_reader.VERBOSE = False
        n = self._snap_table.count
        futures: list[Future] = []
        with self._lock:
            for snap in range(n):
                if snap not in self._futures:
                    self._futures[snap] = self._submit(snap)
                futures.append(self._futures[snap])
        return futures

    def _submit(self, snap_num: int) -> Future:
        """Background load whose Future is released once it completes.

        A Future keeps its result alive, so holding finished ones would pin
        every snapshot in memory and make the cache budget meaningless.
        """
        future = self._executor.submit(self._cached_load, snap_num)
        future.add_done_callback(
            lambda _f, s=snap_num: self._futures.pop(s, None)
        )
        return future

    def _prefetch_neighbours(self, current: int) -> None:
        n = self._snap_table.count
        with self._lock:
            for offset in range(1, self._prefetch_radius + 1):
                for snap in (current - offset, current + offset):
                    if 0 <= snap < n and snap not in self._futures:
                        self._futures[snap] = self._submit(snap)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
