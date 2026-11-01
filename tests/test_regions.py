import numpy as np
import pytest

from visage.utils import regions


def test_sphere_wraps_around_a_periodic_box():
    pos = [[0.5, 50, 50], [99.5, 50, 50], [50, 50, 50]]
    sphere = {"kind": "sphere", "centre": [0, 50, 50], "radius": 1}
    assert regions.mask(sphere, pos, 100.0).tolist() == [True, True, False]
    assert regions.mask(sphere, pos).tolist() == [True, False, False]


def test_box_wraps_and_keeps_its_edges():
    pos = [[99, 5, 5], [1, 5, 5], [50, 5, 5]]
    box = {"kind": "box", "lo": [-2, 0, 0], "hi": [2, 10, 10]}
    assert regions.mask(box, pos, 100.0).tolist() == [True, True, False]


def test_slice_is_its_thickness_about_the_plane():
    pos = [[5, 5, 11], [5, 5, 13], [90, 2, 9.5]]
    cut = {
        "kind": "slice",
        "point": [50, 50, 10],
        "normal": [0, 0, 1],
        "thickness": 2,
    }
    assert regions.mask(cut, pos, 100.0).tolist() == [True, False, True]
    assert regions.volume(cut, 100.0) == 20000
    tilted = dict(cut, normal=[0.6, 0.8, 0])
    assert regions.volume(tilted, 100.0) is None


def test_selection_goes_by_identity():
    chosen = {"kind": "selection", "ids": [7, 9]}
    ids = np.array([1, 7, 9, 3])
    got = regions.mask(chosen, np.zeros((4, 3)), ids=ids)
    assert got.tolist() == [False, True, True, False]
    assert regions.volume(chosen) is None


def test_volumes():
    sphere = {"kind": "sphere", "centre": [0, 0, 0], "radius": 2}
    box = {"kind": "box", "lo": [0, 0, 0], "hi": [1, 2, 3]}
    assert regions.volume(sphere) == pytest.approx(33.51, abs=0.01)
    assert regions.volume(box) == 6


def test_points_are_picked_on_screen():
    # An orthographic-like matrix: x, y as they are, z as depth.
    xy, depth, ahead = regions.screen(
        [[0.1, 0.2, 0.5], [0.9, 0.9, -1]], np.eye(4)
    )
    assert xy[0].tolist() == [0.1, 0.2] and ahead.all()
    square = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]]
    assert regions.in_polygon(xy, square).tolist() == [True, False]


def test_behind_the_camera_is_flagged():
    m = np.eye(4)
    m[3] = [0, 0, 1, 0]  # w is z
    assert regions.screen([[0, 0, -1]], m)[2].tolist() == [False]


def test_front_keeps_the_nearest_in_each_cell():
    xy = np.array([[0.001, 0.001], [0.002, 0.002], [0.5, 0.5]])
    assert sorted(regions.front(xy, np.array([3.0, 1.0, 2.0]))) == [1, 2]


def test_saved_regions_are_kept_by_model(tmp_path, monkeypatch):
    monkeypatch.setattr(regions, "_SAVED", tmp_path / "regions.json")
    assert regions.saved("m") == []
    entry = {"name": "a", "region": {"kind": "selection", "ids": [1]}}
    regions.save("m", [entry])
    regions.save("n", [])
    assert regions.saved("m") == [entry]
