"""The Components labels: one fixed point on each part, on the part, with
nearby markers sharing one."""

from __future__ import annotations

import types

import numpy as np


def _layer(**kw):
    """What labels.parts reads of an HD layer, from a CPU-only build."""
    from visage.hd.layer import HDGalaxyLayer, _warm_galaxy

    gal = _warm_galaxy(
        stellar_mass=4e10,
        bulge_mass=4e9,
        instability_bulge_mass=0.0,
        merger_bulge_mass=4e9,
        h2_gas=4e9,
        h1_gas=8e9,
        cold_gas=1.2e10,
        sfr_disk=4.0,
        disk_radius_kpc=4.0,
        bh_mass=3e7,
        vmax=220.0,
        **kw,
    )
    prep = HDGalaxyLayer.prepare(gal, "lite")
    return (
        types.SimpleNamespace(
            recipe=prep["rc"], gal=gal, _pts=prep["pts"], _maps=prep["maps"]
        ),
        prep,
    )


def test_parts_are_fixed_ordered_and_categorised():
    from visage.hd.labels import CATEGORIES, CATEGORY, parts

    lay, _ = _layer()
    a, b = parts(lay, False), parts(lay, False)
    assert [p["point"] for p in a] == [p["point"] for p in b]
    assert [p["cat"] for p in a] == sorted(p["cat"] for p in a)
    names = {p["name"] for p in a}
    assert {"Central black hole", "Star-forming regions"} <= names
    assert all(p["name"] in CATEGORY for p in a)
    assert all(0 <= p["cat"] < len(CATEGORIES) for p in a)
    assert all(p["text"] for p in a)


def test_arm_and_star_forming_points_sit_on_their_parts():
    from visage.hd.labels import parts

    lay, prep = _layer()
    maps = prep["maps"]
    n = maps.young.shape[0]

    def value(arr, p):
        i = int(round((p[1] + maps.half) / (2 * maps.half) * (n - 1)))
        j = int(round((p[0] + maps.half) / (2 * maps.half) * (n - 1)))
        return float(arr[i, j])

    got = {p["name"]: p["point"] for p in parts(lay, False)}
    arms = maps.young * maps.arm
    arm = next(v for k, v in got.items() if "arms" in k.lower())
    assert value(arms, arm) > 0.2 * arms.max()
    hii = next(p for p in prep["pts"] if p.name == "hii")
    d = np.linalg.norm(
        hii.pos[:, :2] - np.array(got["Star-forming regions"][:2]), axis=1
    )
    assert d.min() < 0.2  # within a complex (model units = disc scale lengths)


def test_faint_intracluster_light_is_not_labelled():
    from visage.hd.labels import parts

    lay, _ = _layer(ics=1e8)  # 0.25% of M*: too faint to see
    assert "Intracluster light" not in {p["name"] for p in parts(lay, False)}


def test_nearby_markers_share_one_and_hidden_ones_are_dropped():
    from visage.hd.labels import MERGE_PX, markers

    screen = [
        (400, 300, True),
        (400 + MERGE_PX / 2, 300, True),  # merges with 1
        (700, 500, True),
        (100, 100, False),  # out of view
    ]
    out = markers(screen, 800, 600)
    assert [m["n"] for m in out] == [[1, 2], [3]]
    assert out[0]["x"] == 0.5 and out[0]["y"] == 0.5
