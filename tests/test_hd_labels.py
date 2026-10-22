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
    left = [o for o in out if o["side"] == "left"]
    assert {o["t"] for o in left} == {"BAR", "BULGE", "ARMS"}
    assert all(o["lx"] < 0.1 for o in left)
    assert all(o["lx"] > 0.9 for o in out if o["side"] == "right")
