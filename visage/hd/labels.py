"""Labels for the parts of an HD galaxy (the selection card's Components
button): which parts this galaxy has, from its SAGE26 properties, and a
3D point on each to label, projected to the screen as the view turns.

Each label points at a real place in the model: the nucleus, a point on
the bulge, the bar, an arm, the brightest star-forming complex, the dust
lane, merger debris, and (with Gas on) the wind, jets, HI disk, cold
stream and hot halo."""

from __future__ import annotations

import numpy as np

# Margins the labels sit in (fractions of the view width), and the least
# vertical gap between two labels on one side (fraction of its height).
MARGIN = 0.035
MIN_GAP = 0.06


def _on_map(arr, half, rlo, rhi, extent):
    """Model-frame (x, y) of the largest value of a disk-plane map within
    the annulus rlo..rhi (fractions of the extent), or None."""
    if arr is None:
        return None
    n = arr.shape[0]
    ax = np.linspace(-half, half, n)
    x, y = np.meshgrid(ax, ax)
    r = np.hypot(x, y)
    m = np.where((r > rlo * extent) & (r < rhi * extent), arr, -np.inf)
    k = int(np.argmax(m))
    if not np.isfinite(m.flat[k]) or m.flat[k] <= 0:
        return None
    return float(x.flat[k]), float(y.flat[k])


def _points(pts, name):
    for p in pts or ():
        if getattr(p, "name", "") == name and len(p.pos):
            return p
    return None


def _median_point(p):
    r = np.linalg.norm(p.pos, axis=1)
    return p.pos[int(np.argsort(r)[len(r) // 2])]


def anchors(layer, gas: bool) -> list[tuple[str, np.ndarray]]:
    """(label, model-frame point) for each part this HD galaxy has."""
    rc, gal = layer.recipe, layer.gal
    pts, maps = getattr(layer, "_pts", None), getattr(layer, "_maps", None)
    if rc is None or gal is None:
        return []
    out: list[tuple[str, np.ndarray]] = []
    E = rc.extent
    disk = rc.kind == "disk"

    def add(text, xyz):
        out.append((text, np.asarray(xyz, float)))

    if gal.bh_mass > 0:
        add("Central black hole", (0.0, 0.0, 0.0))
    if disk:
        if rc.l_pseudo > rc.l_bulge:
            add("Pseudo-bulge", (1.2 * rc.pseudo_a, 0.8 * rc.pseudo_a, 0.0))
        elif rc.l_bulge > 0:
            add("Galactic bulge", (1.0 * rc.bulge_a, 1.0 * rc.bulge_a, 0.0))
        if rc.bar_len > 0:
            add("Bar", (-0.75 * rc.bar_len, 0.0, 0.0))
        if rc.ring > 0:
            c = np.cos(np.deg2rad(135))
            add("Nuclear ring", (rc.ring_r * c, -rc.ring_r * c, 0.0))
        half = maps.half if maps is not None else E
        arm_name = {
            "clumpy": "Giant star-forming clumps",
            "irregular": "Irregular disk",
            "flocculent": "Flocculent arms",
        }.get(rc.arm_class, "Spiral arms")
        xy = _on_map(getattr(maps, "arm", None), half, 0.55, 0.85, E)
        if xy is not None:
            add(arm_name, (*xy, 0.0))
        hii = _points(pts, "hii")
        if hii is not None:
            r = np.linalg.norm(hii.pos[:, :2], axis=1)
            ok = np.flatnonzero(r > 0.35 * E)
            if len(ok):
                k = ok[int(np.argmax(hii.lum[ok]))]
                add("Star-forming regions", hii.pos[k])
        xy = _on_map(getattr(maps, "lanes", None), half, 0.3, 0.7, E)
        if xy is not None:
            add("Dust lanes", (*xy, 0.0))
    else:
        add("Elliptical galaxy", (0.35 * E, 0.25 * E, 0.0))
    for name, text in (
        ("shells", "Merger shells"),
        ("tails", "Tidal tails"),
        ("stream", "Stellar stream"),
        ("tidal", "Tidal debris"),
        ("strip", "Stripped stars"),
        ("jelly", "Ram-pressure tail"),
    ):
        p = _points(pts, name)
        if p is not None:
            add(text, _median_point(p))
    if rc.l_icl > 0:
        r = 0.55 * max(rc.icl_a, E)
        add("Intracluster light", (-0.7 * r, -0.7 * r, 0.0))

    gs = getattr(getattr(layer, "_gpu", None), "gas", None)
    if gas and gs is not None:
        u = rc.unit_kpc
        if gs.wind > 0:
            add("Galactic wind", (0.0, 0.0, 0.45 * gs.wind_len / u))
        if gs.jet > 0:
            add("Radio jet", (0.0, 0.0, -0.5 * gs.jet_len / u))
        if gs.hi_amp > 0:
            r = 1.3 * gs.hi_rs / u
            add("HI gas disk", (-0.6 * r, 0.8 * r, 0.0))
        if gs.stream_amp > 0 and np.any(gs.web[0]):
            add("Cold stream", gs.web[0] * 0.45 * gs.rvir / u)
        if gs.hot > 0:
            add("Hot halo gas", (0.55 * gs.rvir / u, -0.3 * gs.rvir / u, 0.0))
    return out


def to_world(layer, p: np.ndarray) -> np.ndarray:
    """A model-frame point of `layer` in world coordinates."""
    return np.asarray(layer._center) + layer._R @ (
        np.asarray(p) * layer._scale
    )


def layout(points: list[tuple[str, float, float]]) -> list[dict]:
    """Screen positions (fractions, y down) -> labels in the side margins
    with leader lines: each side sorted by height and spread so no two
    overlap."""
    out = []
    for side in ("left", "right"):
        mine = sorted(
            (p for p in points if (p[1] < 0.5) == (side == "left")),
            key=lambda p: p[2],
        )
        ys = [min(max(p[2], 0.06), 0.94) for p in mine]
        for i in range(1, len(ys)):
            ys[i] = max(ys[i], ys[i - 1] + MIN_GAP)
        over = (ys[-1] - 0.94) if ys else 0.0
        if over > 0:
            ys = [max(y - over, 0.06) for y in ys]
        lx = MARGIN if side == "left" else 1.0 - MARGIN
        for (text, x, y), ly in zip(mine, ys, strict=True):
            out.append(
                {
                    "t": text.upper(),
                    "x": round(x, 4),
                    "y": round(y, 4),
                    "lx": lx,
                    "ly": round(ly, 4),
                    "side": side,
                }
            )
    return out
