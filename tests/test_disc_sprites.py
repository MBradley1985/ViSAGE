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


def test_rotation_is_speed_over_size_and_dispersion():
    j = np.array([[3.0, 4.0, 0.0]])
    assert ds.rotation(j, np.array([0.5]), np.array([2.0]))[0] == 5.0


def test_bulge_sizes_follow_their_radii():
    r = np.array([1.0, 4.0, 0.0])
    keep = np.array([True, True, False])
    out = ds.bulge_sizes(r, keep, np.array([0.1, 0.1, 0.1]))
    assert out[1] > out[0]
    # A run with no such radii keeps its sizes.
    size = np.ones(3)
    np.testing.assert_array_equal(ds.bulge_sizes(r * 0, keep, size), size)


def test_elliptical_flattens_with_rotation_only_when_known():
    from dataclasses import replace

    from test_hd_galaxy import _disk
    from visage.hd.model import recipe_from_sage

    g = replace(
        _disk(),
        bulge_mass=_disk().stellar_mass,
        instability_bulge_mass=0.0,
        merger_bulge_mass=_disk().stellar_mass,
    )
    slow = recipe_from_sage(replace(g, bulge_rotation=1.0))
    fast = recipe_from_sage(replace(g, bulge_rotation=15.0))
    assert slow.kind == "elliptical"
    assert fast.axes[2] < slow.axes[2]
