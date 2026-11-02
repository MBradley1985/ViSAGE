"""Following a galaxy through the snapshots of a box."""

from __future__ import annotations

import h5py
import numpy as np

from visage.utils.track import (
    Track,
    camera_centres,
    captions,
    contributors,
    follow,
    forest_mulfac,
    merge_chains,
    merge_target,
    nearest_image,
    reaches,
)

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


def test_the_panel_keeps_only_the_range_asked_for():
    from visage.ui.tracking import trim

    t = Track(
        snaps=[1, 2, 3],
        galaxy_id=[A, A, B],
        pos=[(0, 0, 0)] * 3,
        events=[{"kind": "minor merger", "snap": 3, "into": B}],
    )
    assert trim(t, 1, 2).snaps == [1, 2]
    assert trim(t, 1, 2).events == []


def test_the_history_reads_plainly():
    from visage.ui.tracking import event_text

    assert event_text({"kind": "major merger", "snap": 46, "into": 7}) == (
        "Snapshot 46: major merger into galaxy 7"
    )
    assert "no merger on record" in event_text({"kind": "ended", "snap": 3})


def test_the_camera_crosses_a_gap_in_a_line():
    t = Track(snaps=[1, 3], pos=[(2, 0, 0), (4, 0, 0)])
    assert camera_centres(t, [1, 2, 3], 10)[2] == (3, 0, 0)


def test_the_camera_crosses_a_gap_the_short_way_round_the_box():
    t = Track(snaps=[1, 3], pos=[(9, 0, 0), (1, 0, 0)])
    assert camera_centres(t, [2], 10)[2] == (0, 0, 0)


def test_the_camera_has_no_view_outside_the_track():
    t = Track(snaps=[2, 3], pos=[(1, 0, 0), (2, 0, 0)])
    assert sorted(camera_centres(t, [1, 2, 3, 4], 10)) == [2, 3]


def test_a_merger_is_captioned_for_a_few_snapshots():
    t = Track(
        snaps=[4, 5, 6, 7, 8],
        events=[{"kind": "major merger", "snap": 5, "into": 7}],
    )
    assert sorted(captions(t)) == [5, 6, 7]
    assert captions(t)[5] == "Major merger: now following galaxy 7"


def test_the_end_of_a_branch_has_no_caption():
    t = Track(snaps=[4], events=[{"kind": "ended", "snap": 4}])
    assert captions(t) == {}


def test_zoom_keeps_the_direction_of_the_view():
    from visage.ui.tracking import views

    got = views({1: (5, 5, 5)}, "galaxy", (0, 0, 20), 3)
    assert got[1][0] == (5, 5, 5)
    np.testing.assert_allclose(got[1][1], (0, 0, 3))


def test_the_keep_zoom_keeps_the_distance_too():
    from visage.ui.tracking import KEEP, views

    got = views({1: (5, 5, 5)}, "surroundings", (0, 3, 4), KEEP)
    np.testing.assert_allclose(got[1][1], (0, 3, 4))


def test_the_whole_box_leaves_the_camera_alone():
    from visage.ui.tracking import views

    assert views({1: (5, 5, 5)}, "box", (0, 0, 4), 3)[1] == ((5, 5, 5), None)


def test_every_framing_but_the_box_starts_at_a_zoom_offered():
    from visage.ui.tracking import DEFAULT_ZOOM, FRAMING_ITEMS, ZOOMS

    offered = {z["value"] for z in ZOOMS}
    named = {f["value"] for f in FRAMING_ITEMS} - {"box"}
    assert named == set(DEFAULT_ZOOM)
    assert set(DEFAULT_ZOOM.values()) <= offered


def test_a_gap_keeps_the_galaxy_before_it():
    from visage.ui.tracking import track_ids

    t = Track(snaps=[1, 3], galaxy_id=[A, B])
    assert track_ids(t) == {1: A, 2: A, 3: B}


def _tree(path):
    """B merges into A at 3; C merges into B at 2; A stays, OTHER apart."""
    return _run(
        path,
        {
            1: [(A, 0, -1, -1, 1), (B, 0, -1, -1, 2), (C, 1, 1, 2, 3)],
            2: [(A, 0, -1, -1, 1), (B, 1, 0, 3, 2), (6 * MUL, 0, -1, -1, 9)],
            3: [(A, 0, -1, -1, 1), (6 * MUL, 0, -1, -1, 9)],
        },
    )


def test_links_join_a_forest_up_to_its_mergers(tmp_path):
    rows, links = merge_chains(_tree(tmp_path / "m.hdf5"), A, [1, 2, 3])
    assert links == {C: B, B: A}
    assert list(rows[3]) == [A]


def test_a_galaxy_reaches_what_it_merges_into_through_a_chain():
    links = {C: B, B: A}
    assert reaches(C, {A}, links)
    assert not reaches(A, {C}, links)
    assert not reaches(OTHER, {A}, links)
    assert not reaches(C, {OTHER}, {C: B, B: C})  # never hangs on a loop


def test_contributors_are_those_that_end_up_in_it(tmp_path):
    path = _tree(tmp_path / "m.hdf5")
    got = contributors(path, {1: A, 2: A, 3: A}, [1, 2, 3])
    assert sorted(got[1]) == [A, B, C]
    assert sorted(got[2]) == [A, B]
    assert got[3] == [A]


def test_contributors_count_towards_the_end_of_the_track(tmp_path):
    path = _tree(tmp_path / "m.hdf5")
    got = contributors(path, {1: C, 2: B, 3: A}, [1, 2, 3])
    assert sorted(got[1]) == [A, B, C]  # A too, though C is followed here
    assert sorted(got[2]) == [A, B]


def test_a_halo_counts_its_whole_group_at_the_end(tmp_path):
    path = tmp_path / "m.hdf5"
    _run(
        path,
        {
            1: [(A, 0, -1, -1, 1), (B, 0, -1, -1, 2), (C, 0, -1, -1, 3)],
            2: [(A, 0, -1, -1, 1), (B, 0, -1, -1, 2), (C, 0, -1, -1, 3)],
        },
    )
    with h5py.File(path, "a") as f:
        f["Snap_2/CentralGalaxyIndex"] = np.array([A, A, C])
    got = contributors(path, {1: A, 2: A}, [1, 2], halo=True)
    assert sorted(got[1]) == [A, B]


def test_a_halo_is_centred_on_its_central():
    t = Track(
        snaps=[1], pos=[(5, 0, 0)], central_pos=[(2, 0, 0)], central_id=[A]
    )
    assert camera_centres(t, [1], 10, halo=True)[1] == (2, 0, 0)


def test_joining_a_larger_halo_is_captioned():
    t = Track(snaps=[1, 2], galaxy_id=[A, A], central_id=[A, B], events=[])
    assert captions(t, halo=True)[2] == f"Now in the halo of galaxy {B}"
    assert captions(t) == {}


def test_a_group_across_the_box_edge_is_drawn_together():
    np.testing.assert_allclose(
        nearest_image([[9.5, 0, 0]], (0.5, 0, 0), 10), [[-0.5, 0, 0]]
    )


def _halo_run(path):
    """Galaxy A's halo (forest 5) grows 1 -> 2 -> 4 -> 8; B's halo (1)
    falls in at 3, a 1:2 merger; C's (0.5) at 4, 1:8.  Columns:
    (GalaxyIndex, CentralGalaxyIndex, Type, Mvir)."""
    snaps = {
        1: [(A, A, 0, 1.0), (B, B, 0, 1.5), (C, C, 0, 0.2)],
        2: [(A, A, 0, 2.0), (B, B, 0, 1.0), (C, C, 0, 0.5)],
        3: [(A, A, 0, 4.0), (B, A, 1, 1.0), (C, C, 0, 0.5)],
        4: [(A, A, 0, 8.0), (B, A, 1, 2.0), (C, A, 1, 0.5)],
    }
    with h5py.File(path, "w") as f:
        f.create_group("TreeInfo").attrs["ForestNr_Mulfac"] = MUL
        for snap, rows in snaps.items():
            g = f.create_group(f"Snap_{snap}")
            g["GalaxyIndex"] = np.array([r[0] for r in rows], np.int64)
            g["CentralGalaxyIndex"] = np.array([r[1] for r in rows], np.int64)
            g["Type"] = np.array([r[2] for r in rows], np.int32)
            g["Mvir"] = np.array([r[3] for r in rows], np.float32)
    return path


def test_a_halos_history_is_its_growth_formation_and_mergers(tmp_path):
    from visage.utils.track import halo_history

    past = halo_history(_halo_run(tmp_path / "h.hdf5"), A, 4)
    assert past.snaps == [1, 2, 3, 4]
    assert past.mvir == [1.0, 2.0, 4.0, 8.0]
    assert past.formed() == 3  # first at half of 8
    assert past.mergers == [(3, 0.5), (4, 0.125)]
    assert past.last_major() == (3, 0.5)  # 1:8 is minor
    # Up to an earlier snapshot, its mass then is what counts.
    assert halo_history(tmp_path / "h.hdf5", A, 2).formed() == 1
