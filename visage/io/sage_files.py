"""The galaxy files of one SAGE run, read as a single catalogue.

A serial SAGE run writes ``model_0.hdf5``.  An MPI run with N ranks writes
one file per rank, ``model_0.hdf5`` … ``model_<N-1>.hdf5``, each holding the
forests that rank processed (spread across the whole box), plus a master
``model.hdf5`` of external links.  Reading only ``model_0`` would show 1/N
of the galaxies.

``open_snapshot`` hides the difference: it yields one group for a
snapshot.  For a single file that is the real HDF5 group; for an MPI run
it is a MergedGroup that joins every rank's rows in rank order, so
``grp[name]``, ``np.asarray(grp[name])`` and row indexing behave as if
SAGE had written one file.  A galaxy's row index (``sage_indices``) is
therefore its position in that concatenation.
"""

from __future__ import annotations

import re
from contextlib import ExitStack, contextmanager
from pathlib import Path

import h5py
import numpy as np


def galaxy_files(first: str | Path) -> list[Path]:
    """Every rank file of the run whose first file is ``first``.

    The rank count comes from ``Header/Misc/num_cores`` in the first file,
    so files left behind by an earlier run with more ranks are ignored.
    Older outputs without that attribute fall back to the unbroken run of
    ``<name>_0``, ``<name>_1``, … files on disk.
    """
    first = Path(first)
    m = re.match(r"^(.*)_(\d+)$", first.stem)
    if not m or int(m.group(2)) != 0:
        return [first]
    base = first.with_name(m.group(1))

    def _rank(i: int) -> Path:
        return base.with_name(f"{base.name}_{i}{first.suffix}")

    n = None
    try:
        with h5py.File(first, "r") as f:
            misc = f.get("Header/Misc")
            if misc is not None and "num_cores" in misc.attrs:
                n = int(misc.attrs["num_cores"])
    except OSError:
        return [first]
    if n is not None and n >= 1:
        files = [_rank(i) for i in range(n)]
        missing = [p.name for p in files if not p.is_file()]
        if missing:
            raise FileNotFoundError(
                f"{first.name} says the run used {n} MPI ranks, but "
                f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} "
                f"missing from {first.parent}"
            )
        return files
    files = [first]
    while _rank(len(files)).is_file():
        files.append(_rank(len(files)))
    return files


class MergedDataset:
    """One column of a snapshot, joined across rank files (read on use)."""

    def __init__(self, parts: list[h5py.Dataset]) -> None:
        self._parts = parts
        self._offsets = np.cumsum([0] + [p.shape[0] for p in parts])
        self.attrs = parts[0].attrs
        self.dtype = parts[0].dtype
        self.shape = (int(self._offsets[-1]), *parts[0].shape[1:])
        self.ndim = len(self.shape)

    def __len__(self) -> int:
        return self.shape[0]

    def __array__(self, dtype=None, copy=None):
        out = np.concatenate([np.asarray(p) for p in self._parts])
        return out if dtype is None else out.astype(dtype)

    def _rows(self, rows) -> np.ndarray:
        """Global row indices -> values, in the order asked for."""
        rows = np.asarray(rows, dtype=np.int64)
        rows = np.where(rows < 0, rows + len(self), rows)
        rank = np.searchsorted(self._offsets, rows, side="right") - 1
        out = np.empty((len(rows), *self.shape[1:]), dtype=self.dtype)
        for r in np.unique(rank):
            sel = np.nonzero(rank == r)[0]
            local = rows[sel] - self._offsets[r]
            # h5py wants increasing, unique indices.
            uniq, inverse = np.unique(local, return_inverse=True)
            out[sel] = self._parts[r][uniq][inverse]
        return out

    def __getitem__(self, key):
        rest = ()
        if isinstance(key, tuple):
            key, rest = key[0], key[1:]
        if isinstance(key, (int, np.integer)):
            vals = self._rows([key])[0]
        elif isinstance(key, slice):
            vals = self._rows(np.arange(len(self))[key])
        elif key is Ellipsis:
            vals = np.asarray(self)
        else:
            vals = self._rows(key)
        if not rest:
            return vals
        if isinstance(key, (int, np.integer)):
            return vals[rest]
        return vals[(slice(None), *rest)]


class MergedGroup:
    """A snapshot group joined across rank files.  Only columns every rank
    wrote with the same shape and type are offered."""

    def __init__(self, groups: list[h5py.Group]) -> None:
        self._cols: dict[str, MergedDataset] = {}
        for name, ds in groups[0].items():
            if not isinstance(ds, h5py.Dataset) or ds.ndim < 1:
                continue
            parts = [g.get(name) for g in groups]
            if all(
                isinstance(p, h5py.Dataset)
                and p.shape[1:] == ds.shape[1:]
                and p.dtype == ds.dtype
                for p in parts
            ):
                self._cols[name] = MergedDataset(parts)

    def __contains__(self, name) -> bool:
        return name in self._cols

    def __getitem__(self, name) -> MergedDataset:
        return self._cols[name]

    def get(self, name, default=None):
        return self._cols.get(name, default)

    def keys(self):
        return self._cols.keys()

    def items(self):
        return self._cols.items()

    def __iter__(self):
        return iter(self._cols)

    def __len__(self) -> int:
        return len(self._cols)


def is_dataset(obj) -> bool:
    """True for an HDF5 dataset or a MergedDataset."""
    return isinstance(obj, (h5py.Dataset, MergedDataset))


@contextmanager
def open_snapshot(first: str | Path, snap_num: int):
    """Yield snapshot ``snap_num`` of the run as one group (the real HDF5
    group for a single file, a MergedGroup for an MPI run), or None if no
    rank file has it."""
    files = galaxy_files(first)
    key = f"Snap_{snap_num}"
    with ExitStack() as stack:
        handles = [stack.enter_context(h5py.File(p, "r")) for p in files]
        groups = [h[key] for h in handles if key in h]
        if not groups:
            yield None
        elif len(groups) == 1:
            yield groups[0]
        else:
            yield MergedGroup(groups)


def probe_snapshot(first: str | Path, preferred: int) -> int | None:
    """``preferred`` if the run has that snapshot, else the first one it
    has (for detecting which fields a model offers)."""
    try:
        with h5py.File(first, "r") as f:
            if f"Snap_{preferred}" in f:
                return preferred
            for k in f.keys():
                if k.startswith("Snap_") and k[5:].isdigit():
                    return int(k[5:])
    except OSError:
        pass
    return None
