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


def _map_peaks(arr, half, rlo, rhi, extent, k=6):
    """Model-frame (x, y) of up to `k` bright places of a disk-plane map in
    the annulus rlo..rhi (fractions of the extent), spread round the disk:
    the brightest in each of `k` sectors."""
    if arr is None:
        return []
    n = arr.shape[0]
    step = max(n // 256, 1)  # a coarse grid is plenty to point at
    a = arr[::step, ::step]
    ax = np.linspace(-half, half, a.shape[0])
    x, y = np.meshgrid(ax, ax)
    r = np.hypot(x, y)
    th = np.arctan2(y, x)
    ok = (r > rlo * extent) & (r < rhi * extent) & (a > 0)
    out = []
    for s in range(k):
        lo = -np.pi + 2 * np.pi * s / k
        m = ok & (th >= lo) & (th < lo + 2 * np.pi / k)
        if m.any():
            i = int(np.argmax(np.where(m, a, -np.inf)))
            out.append((float(x.flat[i]), float(y.flat[i]), 0.0))
    return out


def _points(pts, name):
    for p in pts or ():
        if getattr(p, "name", "") == name and len(p.pos):
            return p
    return None


def _spread(p, k=5):
    """Up to `k` points of a population, spread out (a few radii)."""
    r = np.linalg.norm(p.pos, axis=1)
    order = np.argsort(r)
    qs = np.linspace(0.3, 0.8, k)
    return [p.pos[order[int(q * (len(r) - 1))]] for q in qs]


def _ring(radius, k=6, z=0.0, phase=0.0):
    t = phase + np.arange(k) * 2 * np.pi / k
    return [(radius * np.cos(a), radius * np.sin(a), z) for a in t]


def anchors(layer, gas: bool) -> list[tuple[str, list]]:
    """(label, candidate model-frame points) for each part this HD galaxy
    has; one candidate of each is chosen on screen (see `choose`)."""
    rc, gal = layer.recipe, layer.gal
    pts, maps = getattr(layer, "_pts", None), getattr(layer, "_maps", None)
    if rc is None or gal is None:
        return []
    out: list[tuple[str, list]] = []
    E = rc.extent
    disk = rc.kind == "disk"

    def add(text, cands):
        cands = [np.asarray(c, float) for c in cands]
        if cands:
            out.append((text, cands))

    if gal.bh_mass > 0:
        add("Central black hole", [(0.0, 0.0, 0.0)])
    if disk:
        if rc.l_pseudo > rc.l_bulge:
            add("Pseudo-bulge", _ring(1.4 * rc.pseudo_a, 8, phase=0.4))
        elif rc.l_bulge > 0:
            add("Galactic bulge", _ring(1.3 * rc.bulge_a, 8, phase=0.4))
        if rc.bar_len > 0:
            b = 0.75 * rc.bar_len
            add("Bar", [(-b, 0.0, 0.0), (b, 0.0, 0.0)])
        if rc.ring > 0:
            add("Nuclear ring", _ring(rc.ring_r, 8, phase=0.2))
        half = maps.half if maps is not None else E
        arm_name = {
            "clumpy": "Giant star-forming clumps",
            "irregular": "Irregular disk",
            "flocculent": "Flocculent arms",
        }.get(rc.arm_class, "Spiral arms")
        add(
            arm_name,
            _map_peaks(getattr(maps, "arm", None), half, 0.55, 0.9, E),
        )
        hii = _points(pts, "hii")
        if hii is not None:
            r = np.linalg.norm(hii.pos[:, :2], axis=1)
            ok = np.flatnonzero(r > 0.35 * E)
            if len(ok):
                best = ok[np.argsort(hii.lum[ok])[::-1][:400]]
                th = np.arctan2(hii.pos[best, 1], hii.pos[best, 0])
                cands = []
                for s in range(6):  # the brightest in each sector
                    lo = -np.pi + s * np.pi / 3
                    m = best[(th >= lo) & (th < lo + np.pi / 3)]
                    if len(m):
                        cands.append(hii.pos[m[0]])
                add("Star-forming regions", cands)
        add(
            "Dust lanes",
            _map_peaks(getattr(maps, "lanes", None), half, 0.3, 0.75, E),
        )
    else:
        add("Elliptical galaxy", _ring(0.4 * E, 8, phase=0.3))
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
            add(text, _spread(p))
    if rc.l_icl > 0:
        add("Intracluster light", _ring(0.55 * max(rc.icl_a, E), 8, phase=0.6))

    gs = getattr(getattr(layer, "_gpu", None), "gas", None)
    if gas and gs is not None:
        u = rc.unit_kpc
        if gs.wind > 0:
            h = 0.45 * gs.wind_len / u
            add("Galactic wind", [(0.0, 0.0, h), (0.0, 0.0, -h)])
        if gs.jet > 0:
            h = 0.5 * gs.jet_len / u
            add("Radio jet", [(0.0, 0.0, -h), (0.0, 0.0, h)])
        if gs.hi_amp > 0:
            add("HI gas disk", _ring(1.3 * gs.hi_rs / u, 8, phase=0.1))
        if gs.stream_amp > 0:
            add(
                "Cold stream",
                [
                    gs.web[k] * 0.45 * gs.rvir / u
                    for k in range(3)
                    if np.any(gs.web[k])
                ],
            )
        if gs.hot > 0:
            add("Hot halo gas", _ring(0.55 * gs.rvir / u, 8, phase=0.9))
    return out


def choose(parts, min_sep: float = 0.07):
    """parts: [(text, [(x, y) screen fractions of its visible candidates])]
    -> [(text, x, y)]: one point each, in order, as far as possible from
    the points already chosen (so labels don't all point at one spot)."""
    chosen: list[tuple[str, float, float]] = []
    for text, cands in parts:
        if not cands:
            continue
        best, best_d = None, -1.0
        for x, y in cands:
            d = min(
                (np.hypot(x - cx, y - cy) for _, cx, cy in chosen),
                default=1.0,
            )
            # Prefer well-separated points; among those, the first given
            # (the most characteristic).
            score = min(d, min_sep)
            if score > best_d + 1e-9:
                best, best_d = (x, y), score
        chosen.append((text, *best))
    return chosen


def to_world(layer, p: np.ndarray) -> np.ndarray:
    """A model-frame point of `layer` in world coordinates."""
    return np.asarray(layer._center) + layer._R @ (
        np.asarray(p) * layer._scale
    )


# Label width per character (fraction of the view width at 1600 px).
_CHAR_W = 9.0


def _side(x, y, aspect):
    """The view edge nearest the direction from the centre to (x, y)."""
    dx, dy = (x - 0.5) * aspect, y - 0.5
    if abs(dx) >= abs(dy):
        return "left" if dx < 0 else "right"
    return "top" if dy < 0 else "bottom"


def layout(
    points: list[tuple[str, float, float]],
    width: int = 1600,
    height: int = 900,
) -> list[dict]:
    """Screen positions (fractions, y down) -> labels around all four edges
    of the view with leader lines: each to the edge nearest its part, the
    sides kept balanced, and spread so no two overlap."""
    aspect = width / max(height, 1)
    sides: dict[str, list] = {
        s: [] for s in ("left", "right", "top", "bottom")
    }
    # Parts at the very centre (nucleus, bulge, bar) have no natural edge:
    # they go to the top and bottom in turn, so their lines come in short
    # and from different directions instead of all crossing the disk.
    central = []
    for p in points:
        if np.hypot((p[1] - 0.5) * aspect, p[2] - 0.5) < 0.09:
            central.append(p)
        else:
            sides[_side(p[1], p[2], aspect)].append(p)
    for p in central:
        s = "top" if len(sides["top"]) <= len(sides["bottom"]) else "bottom"
        sides[s].append(p)
    # Balance: an edge with too many hands its farthest-out extras to the
    # next edge round.
    cap = {"left": 7, "right": 7, "top": 4, "bottom": 4}
    nxt = {"top": "right", "right": "bottom", "bottom": "left", "left": "top"}
    for _ in range(2):
        for s in ("top", "bottom", "left", "right"):
            while len(sides[s]) > cap[s]:
                sides[nxt[s]].append(sides[s].pop())
    out = []
    for side in ("left", "right"):
        mine = sorted(sides[side], key=lambda p: p[2])
        ys = [min(max(p[2], 0.12), 0.88) for p in mine]
        for i in range(1, len(ys)):
            ys[i] = max(ys[i], ys[i - 1] + MIN_GAP)
        over = (ys[-1] - 0.88) if ys else 0.0
        if over > 0:
            ys = [max(y - over, 0.12) for y in ys]
        lx = MARGIN if side == "left" else 1.0 - MARGIN
        for (text, x, y), ly in zip(mine, ys, strict=True):
            out.append(_label(text, x, y, lx, ly, side))
    for side in ("top", "bottom"):
        mine = sorted(sides[side], key=lambda p: p[1])
        ws = [(_CHAR_W * len(p[0]) + 30) / width for p in mine]
        xs = [min(max(p[1], 0.18), 0.82) for p in mine]
        for i in range(1, len(xs)):
            xs[i] = max(xs[i], xs[i - 1] + 0.5 * (ws[i - 1] + ws[i]))
        over = (xs[-1] - 0.82) if xs else 0.0
        if over > 0:
            xs = [max(x - over, 0.18) for x in xs]
        ly = 0.05 if side == "top" else 0.95
        for (text, x, y), lx in zip(mine, xs, strict=True):
            out.append(_label(text, x, y, lx, ly, side))
    return out


def _label(text, x, y, lx, ly, side) -> dict:
    return {
        "t": text.upper(),
        "x": round(x, 4),
        "y": round(y, 4),
        "lx": round(lx, 4),
        "ly": round(ly, 4),
        "side": side,
    }
