"""Splats that show a run's discs and dust, and that other runs ignore them."""

from __future__ import annotations

from types import SimpleNamespace

import h5py
import numpy as np

from visage.scene import disc_sprites as ds


def test_scaled_runs_zero_to_one():
    v = ds.scaled(np.array([1e7, 10**9.75, 1e13]), 8.0, 11.5)
    np.testing.assert_allclose(v, [0.0, 0.5, 1.0])


def test_spins_are_read_for_the_galaxies_drawn(tmp_path):
    p = tmp_path / "m.hdf5"
    spins = np.arange(12.0).reshape(4, 3)
    with h5py.File(p, "w") as f:
        f.create_group("Snap_5")["SpinStars"] = spins
    snap = SimpleNamespace(
        source_path=str(p), snap_num=5, sage_indices=np.array([3, 1])
    )
    np.testing.assert_array_equal(ds.read_spins(snap, {}), spins[[3, 1]])


def test_a_run_without_spins_gives_none(tmp_path):
    p = tmp_path / "m.hdf5"
    with h5py.File(p, "w") as f:
        f.create_group("Snap_5")["StellarMass"] = np.ones(2)
    snap = SimpleNamespace(
        source_path=str(p), snap_num=5, sage_indices=np.array([0])
    )
    assert ds.read_spins(snap, {}) is None


def test_spins_read_from_a_flat_lightcone(tmp_path):
    p = tmp_path / "cone.h5"
    with h5py.File(p, "w") as f:
        f["StellarMass"] = np.ones(2)
        f["SpinStars"] = np.eye(2, 3)
    snap = SimpleNamespace(
        source_path=str(p), snap_num=0, sage_indices=np.array([1])
    )
    np.testing.assert_array_equal(ds.read_spins(snap, {}), [[0.0, 1.0, 0.0]])
