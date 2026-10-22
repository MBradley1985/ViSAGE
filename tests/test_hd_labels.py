"""The Components labels: laid out in the side margins, never overlapping."""

from __future__ import annotations


def test_labels_sit_in_the_margins_without_overlapping():
    from visage.hd.labels import MIN_GAP, layout

    pts = [
        ("Bar", 0.4, 0.50),
        ("Bulge", 0.45, 0.51),
        ("Arms", 0.3, 0.52),
        ("Wind", 0.6, 0.2),
        ("Black hole", 0.55, 0.5),
    ]
    out = layout(pts)
    assert len(out) == len(pts)
    for side in ("left", "right"):
        ys = sorted(o["ly"] for o in out if o["side"] == side)
        assert all(
            b - a >= MIN_GAP - 1e-9 for a, b in zip(ys, ys[1:], strict=False)
        )
    assert all(o["lx"] < 0.1 for o in out if o["side"] == "left")
    assert all(o["lx"] > 0.9 for o in out if o["side"] == "right")
    # The wind, well above the centre, goes to the top edge.
    assert next(o for o in out if o["t"] == "WIND")["side"] == "top"


def test_each_part_points_somewhere_different_when_it_can():
    from visage.hd.labels import choose

    parts = [
        ("Black hole", [(0.5, 0.5)]),
        ("Bulge", [(0.51, 0.5), (0.5, 0.42)]),  # 1st candidate on the hole
        ("Bar", [(0.5, 0.5), (0.62, 0.5)]),
    ]
    got = {t: (x, y) for t, x, y in choose(parts)}
    assert got["Bulge"] == (0.5, 0.42)
    assert got["Bar"] == (0.62, 0.5)
