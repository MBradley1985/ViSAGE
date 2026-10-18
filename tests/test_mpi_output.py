"""SAGE runs under MPI write one galaxy file per rank (model_0 … model_N-1);
ViSAGE must read them as one catalogue (visage.io.sage_files)."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from visage.io.galaxy_reader import load_galaxy_snapshot
from visage.io.sage_files import galaxy_files, open_snapshot

ROWS = (5, 0, 7)  # galaxies per rank at Snap_63 — rank 1 found none
N_SFH = 4


def _write_rank(path: Path, rank: int, n: int, num_cores: int | None):
    with h5py.File(path, "w") as f:
        if num_cores is not None:
            f.create_group("Header/Misc").attrs["num_cores"] = num_cores
        g = f.create_group("Snap_63")
        i = np.arange(n)
        # GalaxyIndex encodes (rank, row) so tests can tell galaxies apart.
        g["GalaxyIndex"] = (rank * 1000 + i).astype(np.int64)
        g["Posx"] = (rank + i / 10).astype(np.float32)
        g["Posy"] = np.zeros(n, np.float32)
        g["Posz"] = np.zeros(n, np.float32)
        g["StellarMass"] = np.full(n, 0.5, np.float32)
        g["Mvir"] = np.ones(n, np.float32)
        for name in ("BulgeMass", "ColdGas", "SfrDisk", "SfrBulge"):
            g[name] = np.zeros(n, np.float32)
        g["Type"] = np.zeros(n, np.int32)
        g["NewField"] = (rank * 1000 + i).astype(np.float32)
        g["SFHMassDisk"] = np.full((n, N_SFH), rank, np.float32)
        g["SFHMassBulge"] = np.zeros((n, N_SFH), np.float32)


@pytest.fixture
def mpi_run(tmp_path) -> Path:
    for rank, n in enumerate(ROWS):
        _write_rank(tmp_path / f"model_{rank}.hdf5", rank, n, len(ROWS))
    return tmp_path / "model_0.hdf5"


def _expected_ids():
    return np.concatenate(
        [r * 1000 + np.arange(n) for r, n in enumerate(ROWS)]
    )


def test_galaxy_files_uses_num_cores(mpi_run):
    assert [p.name for p in galaxy_files(mpi_run)] == [
        "model_0.hdf5",
        "model_1.hdf5",
        "model_2.hdf5",
    ]


def test_stale_rank_files_from_an_older_run_are_ignored(tmp_path):
    """A serial rerun into a folder that held a 4-rank run."""
    _write_rank(tmp_path / "model_0.hdf5", 0, 3, num_cores=1)
    _write_rank(tmp_path / "model_1.hdf5", 1, 3, num_cores=4)
    assert galaxy_files(tmp_path / "model_0.hdf5") == [
        tmp_path / "model_0.hdf5"
    ]


def test_missing_rank_file_is_an_error(mpi_run):
    (mpi_run.parent / "model_2.hdf5").unlink()
    with pytest.raises(FileNotFoundError, match="model_2.hdf5"):
        galaxy_files(mpi_run)


def test_old_outputs_without_num_cores_glob_contiguous_files(tmp_path):
    for rank in (0, 1, 3):  # gap at 2: model_3 is not part of the run
        _write_rank(tmp_path / f"model_{rank}.hdf5", rank, 2, None)
    assert [p.name for p in galaxy_files(tmp_path / "model_0.hdf5")] == [
        "model_0.hdf5",
        "model_1.hdf5",
    ]


def test_merged_snapshot_reads_like_one_file(mpi_run):
    with open_snapshot(mpi_run, 63) as g:
        assert "Posx" in g and "Nope" not in g
        assert len(g["GalaxyIndex"]) == sum(ROWS)
        np.testing.assert_array_equal(
            np.asarray(g["GalaxyIndex"]), _expected_ids()
        )
        # rows in any order, with repeats, across rank boundaries
        rows = np.array([11, 0, 5, 5, 4])
        np.testing.assert_array_equal(
            g["GalaxyIndex"][rows], _expected_ids()[rows]
        )
        assert g["GalaxyIndex"][-1] == 2006
        assert g["SFHMassDisk"].shape == (sum(ROWS), N_SFH)
        assert g["SFHMassDisk"][6, :].tolist() == [2.0] * N_SFH
        assert g["SFHMassDisk"][3:7].shape == (4, N_SFH)


def test_missing_snapshot(mpi_run):
    with open_snapshot(mpi_run, 10) as g:
        assert g is None


def test_load_galaxy_snapshot_reads_every_rank(mpi_run):
    snap = load_galaxy_snapshot(mpi_run, 63, min_stellar_mass=0.0)
    assert snap.count == sum(ROWS)
    np.testing.assert_array_equal(np.sort(snap.galaxy_id), _expected_ids())
    # sage_indices address the joined rows, so they map back correctly.
    with open_snapshot(mpi_run, 63) as g:
        ids = g["GalaxyIndex"][snap.sage_indices]
    np.testing.assert_array_equal(ids, snap.galaxy_id)


def test_catalogue_export_reads_rows_from_the_right_rank(mpi_run, tmp_path):
    from visage.utils.catalogue import _read_snap_fields

    rows = np.array([0, 5, 11])  # rank 0, rank 2 first, rank 2 last
    data, _ = _read_snap_fields(mpi_run, 63, rows)
    assert data["GalaxyIndex"].tolist() == [0, 2000, 2006]
    assert data["NewField"].tolist() == [0.0, 2000.0, 2006.0]


def test_serial_run_is_untouched(mini_hdf5_path):
    assert galaxy_files(mini_hdf5_path) == [mini_hdf5_path]
    with open_snapshot(mini_hdf5_path, 63) as g:
        assert isinstance(g, h5py.Group)
