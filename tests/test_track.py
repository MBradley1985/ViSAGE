"""Following a galaxy through the snapshots of a box."""

from __future__ import annotations

import h5py
import numpy as np

from visage.utils.track import follow, forest_mulfac, merge_target

MUL = 10**9


def _snapshot(f, snap, rows):
    """rows: (GalaxyIndex, mergeType, mergeIntoID, mergeIntoSnapNum, x)."""
    g = f.create_group(f"Snap_{snap}")
    a = np.array(rows, dtype=np.int64).reshape(-1, 5)
    g["GalaxyIndex"] = a[:, 0]
    g["mergeType"] = a[:, 1].astype(np.int32)
    g["mergeIntoID"] = a[:, 2].astype(np.int32)
    g["mergeIntoSnapNum"] = a[:, 3].astype(np.int32)
    g["Posx"] = a[:, 4].astype(np.float32)
    g["Posy"] = np.zeros(len(a), np.float32)
    g["Posz"] = np.zeros(len(a), np.float32)


def _run(path, snaps, mulfac=MUL):
    with h5py.File(path, "w") as f:
        f.create_group("TreeInfo").attrs["ForestNr_Mulfac"] = mulfac
        for snap, rows in snaps.items():
            _snapshot(f, snap, rows)
    return path


# Forest 5 holds galaxies 0, 1 and 2; forest 6 holds a bystander.
A, B, C, OTHER = 5 * MUL, 5 * MUL + 1, 5 * MUL + 2, 6 * MUL


def test_mulfac_comes_from_the_file(tmp_path):
    assert forest_mulfac(_run(tmp_path / "m.hdf5", {}, 1000)) == 1000


def test_mulfac_falls_back_for_older_outputs(tmp_path):
    path = tmp_path / "m.hdf5"
    h5py.File(path, "w").close()
    assert forest_mulfac(path) == MUL


def test_target_is_a_row_of_the_forest_not_of_the_snapshot():
    ids = np.array([OTHER, A, OTHER + 1, B])
    assert merge_target(ids, C, 1, MUL) == B
    assert merge_target(ids, C, 2, MUL) is None


def test_a_merged_galaxy_carries_on_with_its_target(tmp_path):
    path = _run(
        tmp_path / "m.hdf5",
        {
            1: [(A, 0, -1, -1, 1), (B, 2, 0, 2, 2), (OTHER, 0, -1, -1, 9)],
            2: [(OTHER, 0, -1, -1, 9), (A, 0, -1, -1, 3)],
            3: [(A, 0, -1, -1, 4)],
        },
    )
    t = follow(path, B, 1, [1, 2, 3])
    assert t.snaps == [1, 2, 3]
    assert t.galaxy_id == [B, A, A]
    assert [p[0] for p in t.pos] == [2, 3, 4]
    assert t.events == [
        {"kind": "major merger", "snap": 2, "galaxy_id": B, "into": A}
    ]


def test_the_past_is_the_galaxy_itself_from_when_it_formed(tmp_path):
    path = _run(
        tmp_path / "m.hdf5",
        {
            1: [(OTHER, 0, -1, -1, 0)],
            2: [(A, 0, -1, -1, 1)],
            3: [(A, 0, -1, -1, 2)],
        },
    )
    t = follow(path, A, 3, [1, 2, 3])
    assert t.snaps == [2, 3]
    assert t.events == []


def test_a_gap_is_waited_for(tmp_path):
    path = _run(
        tmp_path / "m.hdf5",
        {
            1: [(A, 0, -1, -1, 1)],
            2: [(OTHER, 0, -1, -1, 0)],
            3: [(A, 0, -1, -1, 3)],
        },
    )
    t = follow(path, A, 1, [1, 2, 3])
    assert t.snaps == [1, 3]
    assert t.events == []


def test_a_merger_across_a_gap_waits_for_the_targets_snapshot(tmp_path):
    path = _run(
        tmp_path / "m.hdf5",
        {
            1: [(A, 0, -1, -1, 1), (B, 1, 0, 3, 2)],
            2: [(A, 0, -1, -1, 1)],
            3: [(A, 0, -1, -1, 1)],
        },
    )
    t = follow(path, B, 1, [1, 2, 3])
    assert t.snaps == [1, 3]
    assert t.galaxy_id == [B, A]
    assert t.events[0]["snap"] == 3


def test_a_chain_of_mergers_is_followed(tmp_path):
    path = _run(
        tmp_path / "m.hdf5",
        {
            1: [(A, 0, -1, -1, 1), (B, 0, -1, -1, 1), (C, 1, 1, 2, 1)],
            2: [(A, 0, -1, -1, 1), (B, 4, 0, 3, 1)],
            3: [(A, 0, -1, -1, 1)],
        },
    )
    t = follow(path, C, 1, [1, 2, 3])
    assert t.galaxy_id == [C, B, A]
    assert [e["kind"] for e in t.events] == ["minor merger", "disrupted"]


def test_a_merger_into_an_unwritten_snapshot_ends_the_track(tmp_path):
    path = _run(tmp_path / "m.hdf5", {1: [(B, 1, -1, 2, 2)]})
    t = follow(path, B, 1, [1])
    assert t.snaps == [1]
    assert t.events[0]["kind"] == "lost"


def test_a_branch_that_stops_says_so(tmp_path):
    path = _run(
        tmp_path / "m.hdf5",
        {1: [(A, 0, -1, -1, 1)], 2: [(OTHER, 0, -1, -1, 0)]},
    )
    t = follow(path, A, 1, [1, 2])
    assert t.events == [{"kind": "ended", "snap": 1, "galaxy_id": A}]


def test_a_merger_past_the_range_is_not_an_ending(tmp_path):
    path = _run(
        tmp_path / "m.hdf5",
        {1: [(B, 1, 0, 2, 2)], 2: [(A, 0, -1, -1, 1)]},
    )
    assert follow(path, B, 1, [1]).events == []


def test_progress_and_cancel(tmp_path):
    path = _run(
        tmp_path / "m.hdf5",
        {s: [(A, 0, -1, -1, s)] for s in range(1, 5)},
    )
    seen = []
    follow(path, A, 2, [1, 2, 3, 4], progress=lambda d, n: seen.append((d, n)))
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]
    t = follow(path, A, 2, [1, 2, 3, 4], cancelled=lambda: True)
    assert t.cancelled and t.snaps == []
