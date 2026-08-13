import numpy as np
import pytest

from visage.io.halo_reader import (
    HALO_DTYPE,
    MASS_FIELDS,
    _pick_mass_field,
    load_halo_snapshot,
)


def test_loads_correct_snap(mini_tree_path):
    snap = load_halo_snapshot(
        tree_dir=mini_tree_path.parent,
        tree_name="trees_063",
        snap_num=63,
        first_file=0,
        last_file=0,
        mass_cut=0.0,
        n_jobs=1,
    )
    assert snap.snap_num == 63
    assert snap.count > 0
    assert snap.positions.shape[1] == 3


def test_mass_cut_filters(mini_tree_path):
    snap_all = load_halo_snapshot(
        tree_dir=mini_tree_path.parent,
        tree_name="trees_063",
        snap_num=63,
        first_file=0,
        last_file=0,
        mass_cut=0.0,
        n_jobs=1,
    )
    snap_cut = load_halo_snapshot(
        tree_dir=mini_tree_path.parent,
        tree_name="trees_063",
        snap_num=63,
        first_file=0,
        last_file=0,
        mass_cut=1.0e15,  # nothing passes
        n_jobs=1,
    )
    assert snap_all.count > snap_cut.count


def test_empty_snap_returns_empty(mini_tree_path):
    snap = load_halo_snapshot(
        tree_dir=mini_tree_path.parent,
        tree_name="trees_063",
        snap_num=0,  # not in fixture
        first_file=0,
        last_file=0,
        mass_cut=0.0,
        n_jobs=1,
    )
    assert snap.count == 0


def test_falls_back_when_mvir_is_empty(mini_tree_path, mini_tree_tophat_path):
    """Trees carrying the mass in M_TopHat load identically to Mvir trees."""
    kwargs = dict(
        tree_name="trees_063",
        snap_num=63,
        first_file=0,
        last_file=0,
        mass_cut=0.0,
        n_jobs=1,
    )
    mvir = load_halo_snapshot(tree_dir=mini_tree_path.parent, **kwargs)
    tophat = load_halo_snapshot(
        tree_dir=mini_tree_tophat_path.parent, **kwargs
    )

    assert tophat.count == mvir.count > 0
    assert np.allclose(tophat.masses, mvir.masses)
    assert np.allclose(tophat.rvir, mvir.rvir)


def test_pick_mass_field_prefers_mvir():
    halos = np.zeros(4, dtype=HALO_DTYPE)
    halos["M_Mean200"] = 2.0
    halos["M_TopHat"] = 3.0
    assert _pick_mass_field(halos) == "M_TopHat"  # first populated in order

    halos["Mvir"] = 1.0
    assert _pick_mass_field(halos) == "Mvir"  # canonical column wins


def test_pick_mass_field_all_empty():
    halos = np.zeros(4, dtype=HALO_DTYPE)
    assert _pick_mass_field(halos) == MASS_FIELDS[0]


def test_max_halos_downsamples(mini_tree_path):
    snap = load_halo_snapshot(
        tree_dir=mini_tree_path.parent,
        tree_name="trees_063",
        snap_num=63,
        first_file=0,
        last_file=0,
        mass_cut=0.0,
        max_halos=5,
        n_jobs=1,
    )
    assert snap.count <= 5
