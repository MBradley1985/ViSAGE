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


# ── Tree-file resolution ──────────────────────────────────────────────────
# A run configured for consistent-trees ASCII points TreeName at the ASCII
# file itself ("tree_0_0_0.dat"), which matches none of the "TreeName.n"
# patterns — the haloes silently came back empty.  These runs keep the
# converted lhalo_binary trees nearby, so that set is found instead.


def test_resolves_configured_numbered_files_first(mini_tree_path, tmp_path):
    import shutil

    from visage.io.halo_reader import _resolve_tree_files

    tree_dir = tmp_path / "trees"
    (tree_dir / "converted").mkdir(parents=True)
    shutil.copy(mini_tree_path, tree_dir / "trees_063.0")
    shutil.copy(mini_tree_path, tree_dir / "converted" / "other_063.0")

    files = _resolve_tree_files(tree_dir, "trees_063", 0, 0, "lhalo_binary")
    assert [f.name for f in files] == ["trees_063.0"]


def test_ascii_tree_name_falls_back_to_converted_binary(
    mini_tree_path, tmp_path
):
    import shutil

    from visage.io.halo_reader import _resolve_tree_files

    tree_dir = tmp_path / "trees"
    converted = tree_dir / "lhalo-binary-mergertree"
    converted.mkdir(parents=True)
    (tree_dir / "tree_0_0_0.dat").write_text("#scale(0) id(1)\n")
    (tree_dir / "locations.dat").write_text("junk\n")
    for i in range(3):
        shutil.copy(mini_tree_path, converted / f"tree_49.{i}")

    files = _resolve_tree_files(
        tree_dir, "tree_0_0_0.dat", 0, 0, "consistent_trees_ascii"
    )
    assert [f.name for f in files] == ["tree_49.0", "tree_49.1", "tree_49.2"]


def test_numbered_non_tree_files_are_not_mistaken_for_trees(tmp_path):
    from visage.io.halo_reader import _resolve_tree_files

    tree_dir = tmp_path / "trees"
    tree_dir.mkdir()
    (tree_dir / "tree_0_0_0.dat").write_text("#scale(0) id(1)\n")
    (tree_dir / "notes.1").write_text("not a tree file at all\n")

    assert (
        _resolve_tree_files(
            tree_dir, "tree_0_0_0.dat", 0, 0, "consistent_trees_ascii"
        )
        == []
    )


def test_loads_haloes_through_the_fallback(mini_tree_path, tmp_path):
    import shutil

    tree_dir = tmp_path / "trees"
    converted = tree_dir / "lhalo-binary-mergertree"
    converted.mkdir(parents=True)
    (tree_dir / "tree_0_0_0.dat").write_text("#scale(0) id(1)\n")
    shutil.copy(mini_tree_path, converted / "tree_49.0")

    snap = load_halo_snapshot(
        tree_dir=tree_dir,
        tree_name="tree_0_0_0.dat",
        snap_num=63,
        first_file=0,
        last_file=0,
        mass_cut=0.0,
        n_jobs=1,
        tree_type="consistent_trees_ascii",
    )
    assert snap.count > 0
