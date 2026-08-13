"""Tests for reading SAGE's HDF5 merger trees (TreeType lhalo_hdf5)."""

import h5py
import numpy as np
import pytest

from visage.io import hdf5_tree_reader
from visage.io.halo_reader import _resolve_tree_files, load_halo_snapshot


@pytest.fixture(autouse=True)
def _clear_index_cache():
    hdf5_tree_reader.clear_cache()
    yield
    hdf5_tree_reader.clear_cache()


def _load(path, **overrides):
    kwargs = dict(
        tree_dir=path.parent,
        tree_name="trees_300",
        snap_num=63,
        first_file=0,
        last_file=0,
        mass_cut=0.0,
        hubble_h=0.678,
        box_size=62.5,
        n_jobs=1,
    )
    kwargs.update(overrides)
    return load_halo_snapshot(**kwargs)


def test_reads_hdf5_trees(mini_hdf5_tree_path):
    """The .hdf5 file is found and read even though TreeName has no suffix."""
    snap = _load(mini_hdf5_tree_path)
    # 2 trees x 2 FOF centrals, but only those at snap 63: centrals are the
    # halos at tree-local index 0 (snap 61) and 6 (snap 61) — so snap 63 has
    # none, while snap 61 has both.
    snap61 = _load(mini_hdf5_tree_path, snap_num=61)
    assert snap61.count == 4
    assert snap.count == 0


def test_only_fof_centrals_are_kept(mini_hdf5_tree_path):
    """Satellites carry mass in these files, so the mass cut can't filter them."""
    snap = _load(mini_hdf5_tree_path, snap_num=61)
    with h5py.File(mini_hdf5_tree_path, "r") as f:
        all_at_61 = sum(
            int(np.count_nonzero(f[f"Tree{t}"]["SnapNum"][:] == 61))
            for t in (0, 1)
        )
    assert all_at_61 == 8  # 4 centrals + 4 satellites
    assert snap.count == 4


def test_positions_converted_from_kpc(mini_hdf5_tree_path):
    """SubhaloPos is kpc/h; the box is 62.5 Mpc/h."""
    snap = _load(mini_hdf5_tree_path, snap_num=61)
    assert snap.positions.max() <= 62.5
    assert snap.positions.max() > 1.0  # not scaled twice


def test_mass_from_crit200_and_units(mini_hdf5_tree_path):
    """Mass comes from the one populated Group_M_* column, in 10^10 Msun/h."""
    snap = _load(mini_hdf5_tree_path, snap_num=61)
    with h5py.File(mini_hdf5_tree_path, "r") as f:
        # The FOF centrals are tree-local indices 0 and 6, both at snap 61.
        expected = np.concatenate(
            [f[f"Tree{t}"]["Group_M_Crit200"][[0, 6]] for t in (0, 1)]
        ) * (1.0e10 / 0.678)
    assert np.allclose(np.sort(snap.masses), np.sort(expected))
    assert np.all(snap.rvir > 0)
    assert np.all(snap.vvir > 0)


def test_mass_cut_applies(mini_hdf5_tree_path):
    assert _load(mini_hdf5_tree_path, snap_num=61, mass_cut=1.0e30).count == 0


def test_index_is_built_once_per_file(mini_hdf5_tree_path, monkeypatch):
    """Every snapshot after the first is served from the cached index."""
    calls = []
    real = hdf5_tree_reader._build_index

    def counted(path, box_size):
        calls.append(str(path))
        return real(path, box_size)

    monkeypatch.setattr(hdf5_tree_reader, "_build_index", counted)
    for snap in (61, 62, 63, 61):
        _load(mini_hdf5_tree_path, snap_num=snap)
    assert len(calls) == 1


def test_missing_trees_report_cleanly(tmp_path):
    """A misnamed/absent tree path returns empty rather than raising."""
    snap = load_halo_snapshot(
        tree_dir=tmp_path,
        tree_name="not_there",
        snap_num=63,
        first_file=0,
        last_file=0,
        mass_cut=0.0,
        n_jobs=1,
    )
    assert snap.count == 0


def test_resolve_tree_files_prefers_bare_then_hdf5(tmp_path):
    (tmp_path / "trees_063.0.hdf5").write_bytes(b"")
    (tmp_path / "trees_063.1").write_bytes(b"")
    found = _resolve_tree_files(tmp_path, "trees_063", 0, 2)
    assert [p.name for p in found] == ["trees_063.0.hdf5", "trees_063.1"]
