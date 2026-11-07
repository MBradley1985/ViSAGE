"""Labels for the parts of an HD galaxy (the selection card's Components
button): which parts this galaxy has, from its SAGE26 properties, one fixed
point on each, its category and a line on what it is.

Each part's point is chosen once, from the model itself (the arm ridge where
the young light peaks, the brightest star-forming complex, the darkest lane,
the densest shell, ...), and spread round the disc away from the other
parts'. It never changes as the view turns or zooms: the screen shows a
numbered marker on it, and the key (drawn by visage.js) never moves. A part
out of view greys out in the key; markers closer than MERGE_PX share one."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

# The key's categories, in its order, and the colour of each (validated for
# colour-blind and normal vision, all pairs).
CATEGORIES = (
    ("Stars and structure", "#edad5d"),
    ("Star formation", "#ff72ab"),
    ("Dust", "#cb6803"),
    ("Black hole and AGN", "#60cdff"),
    ("Mergers and environment", "#9284e5"),
    ("Halo gas", "#35f0ae"),
)
CATEGORY = {
    "Classical bulge": 0,
    "Pseudo-bulge": 0,
    "Bar": 0,
    "Spiral arms": 0,
    "Flocculent arms": 0,
    "Irregular disc": 0,
    "Elliptical galaxy": 0,
    "Star-forming regions": 1,
    "Nuclear ring": 1,
    "Giant clumps": 1,
    "Dust lanes": 2,
    "Dust lane": 2,
    "Central black hole": 3,
    "Radio jet": 3,
    "Merger shells": 4,
    "Tidal tails": 4,
    "Stellar stream": 4,
    "Tidal debris": 4,
    "Stripped stars": 4,
    "Ram-pressure tail": 4,
    "Intracluster light": 4,
    "Galactic wind": 5,
    "HI gas disc": 5,
    "Cold stream": 5,
    "Hot halo gas": 5,
}
# Markers closer than this (pixels) share one.
MERGE_PX = 24
# Intracluster light is labelled only when SAGE26's ICS is this share of the
# galaxy's stars: below it the envelope is too faint to see.
ICL_SHARE = 0.05


def _mass(m: float) -> str:
    """A mass as "2.1 × 10^7 M☉" (visage.js raises the exponent)."""
    if m <= 0:
        return "0 M☉"
    e = int(np.floor(np.log10(m)))
    return f"{m / 10**e:.1f} × 10^{e} M☉"


def _ago(myr: float) -> str:
    return f"{myr:.0f} Myr" if myr < 1000 else f"{myr / 1e3:.1f} Gyr"


def _map_cands(arr, half, rlo, rhi, extent, weight=None, k=8):
    """Model-frame points of a disc-plane map's brightest place in each of
    `k` sectors of the annulus rlo..rhi (fractions of the extent), with
    their value relative to the best: [((x, y, 0), v)]."""
    if arr is None:
        return []
    step = max(arr.shape[0] // 256, 1)  # a coarse grid is plenty
    a = np.asarray(arr[::step, ::step], float)
    if weight is not None:
        a = a * np.asarray(weight[::step, ::step], float)
    a = gaussian_filter(a, 3)
    ax = np.linspace(-half, half, a.shape[0])
    x, y = np.meshgrid(ax, ax)
    r = np.hypot(x, y)
    th = np.arctan2(y, x)
    ok = (r > rlo * extent) & (r < rhi * extent)
    out = []
    for s in range(k):
        lo = -np.pi + 2 * np.pi * s / k
        m = ok & (th >= lo) & (th < lo + 2 * np.pi / k)
        if m.any():
            i = int(np.argmax(np.where(m, a, -np.inf)))
            out.append(((float(x.flat[i]), float(y.flat[i]), 0.0), a.flat[i]))
    top = max((v for _, v in out), default=0.0)
    return [(p, float(v / top)) for p, v in out] if top > 0 else []


def _spread_pick(cands, taken):
    """The candidate strong on its part and furthest round the disc (by
    angle about the centre) from the points already taken."""

    def ang(p):
        return np.arctan2(p[1], p[0])

    best, best_s = None, -1.0
    for p, v in cands:
        if v < 0.3:
            continue
        sep = (
            min(
                (abs(np.angle(np.exp(1j * (ang(p) - ang(q))))) for q in taken),
                default=np.pi,
            )
            / np.pi
        )
        score = v**0.5 * sep
        if score > best_s:
            best, best_s = p, score
    return best


def _points(pts, name):
    for p in pts or ():
        if getattr(p, "name", "") == name and len(p.pos):
            return p
    return None


def _densest(p, cell):
    """Centre of the brightest cell of a point population."""
    q = np.floor(p.pos / cell).astype(int)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    inv = inv.ravel()
    k = int(np.argmax(np.bincount(inv, weights=p.lum)))
    return tuple(float(v) for v in p.pos[inv == k].mean(axis=0))


def parts(layer, gas: bool) -> list[dict]:
    """The labelled parts of an HD galaxy, in the key's order: name,
    category (index into CATEGORIES), its fixed model-frame point and a line
    on what it is, from this galaxy's own values."""
    rc, g = layer.recipe, layer.gal
    pts, maps = getattr(layer, "_pts", None), getattr(layer, "_maps", None)
    if rc is None or g is None:
        return []
    E, u = rc.extent, rc.unit_kpc
    out: list[dict] = []

    def add(name, point, text):
        if point is not None:
            out.append(
                {
                    "name": name,
                    "cat": CATEGORY.get(name, 0),
                    "point": tuple(float(v) for v in point),
                    "text": text,
                }
            )

    if g.bh_mass > 0:
        add(
            "Central black hole",
            (0.0, 0.0, 0.0),
            f"{_mass(g.bh_mass)}"
            + ("; quasar-mode AGN" if rc.agn > 0 else "; sets the nucleus"),
        )
    if rc.kind == "disk":
        if rc.l_pseudo > rc.l_bulge:
            add(
                "Pseudo-bulge",
                (0.0, 2.5 * rc.pseudo_a, 0.0),
                f"{_mass(g.instability_bulge_mass)} built by disc instabilities",
            )
        elif rc.l_bulge > 0:
            add(
                "Classical bulge",
                (0.0, 2.0 * rc.bulge_a, 0.0),
                f"{_mass(g.merger_bulge_mass)} built by mergers",
            )
        if rc.bar_len > 0:
            add(
                "Bar",
                (0.7 * rc.bar_len, 0.0, 0.0),
                f"{rc.bar_len * u:.1f} kpc half-length; the disc is unstable to a bar",
            )
        ring = _points(pts, "ring")
        if rc.ring > 0 and ring is not None:
            add(
                "Nuclear ring",
                _densest(ring, 0.1),
                f"at {rc.ring_r * u:.1f} kpc, fed by the bar",
            )
        taken: list = []
        if maps is not None:
            name = {
                "flocculent": "Flocculent arms",
                "irregular": "Irregular disc",
                "clumpy": "Giant clumps",
            }.get(rc.arm_class, "Spiral arms")
            kind = {
                "grand": "grand design",
                "multi": "multi-arm",
                "partial": "partial arms",
                "flocculent": "flocculent",
            }.get(rc.arm_class)
            p = _spread_pick(
                _map_cands(
                    maps.young, maps.half, 0.3, 0.75, E, weight=maps.arm
                ),
                taken,
            )
            if p is not None:
                taken.append(p)
                if kind:
                    text = f"{kind}, pitch {rc.pitch_deg:.0f}°"
                elif name == "Giant clumps":
                    text = f"{rc.clumps} clumps in a gas-rich, turbulent disc"
                else:
                    text = "no spiral: patchy star formation, lopsided"
                add(name, p, text)
        hii = _points(pts, "hii")
        if hii is not None:
            r = np.linalg.norm(hii.pos[:, :2], axis=1)
            ok = np.flatnonzero((r > 0.3 * E) & (r < 0.8 * E))
            if len(ok):
                q = np.floor(hii.pos[ok] / 0.12).astype(int)
                _, inv = np.unique(q, axis=0, return_inverse=True)
                inv = inv.ravel()
                w = np.bincount(inv, weights=hii.lum[ok])
                cands = [
                    (
                        tuple(hii.pos[ok][inv == k].mean(axis=0)),
                        float(w[k] / w.max()),
                    )
                    for k in np.argsort(w)[::-1][:40]
                ]
                p = _spread_pick(cands, taken)
                if p is not None:
                    taken.append(p)
                    add(
                        "Star-forming regions",
                        p,
                        f"{rc.n_hii:,} complexes from {_mass(g.h2_gas)} of H₂; "
                        f"SFR {g.sfr_disk + g.sfr_bulge:.1f} M☉/yr",
                    )
        lanes = getattr(maps, "lanes", None)
        if lanes is not None and rc.lane > 0:
            p = _spread_pick(_map_cands(lanes, maps.half, 0.2, 0.6, E), taken)
            if p is not None:
                taken.append(p)
                add(
                    "Dust lanes",
                    p,
                    f"face-on τ_V {rc.tau0:.1f}, from "
                    f"{_mass(g.h1_gas + g.h2_gas)} of gas",
                )
    else:
        a, b, c = rc.axes
        slow = any(n.startswith("slow rotator") for n in rc.notes)
        add(
            "Elliptical galaxy",
            (0.9, 0.0, 0.0),
            f"{'slow' if slow else 'fast'} rotator, c/a {c:.2f}; "
            f"{_mass(g.stellar_mass)} of stars",
        )
        if rc.dust_lane > 0:
            add(
                "Dust lane",
                (0.12, 0.0, 0.0),
                "nuclear lane from its molecular gas or dust",
            )
    for pop, name in (
        ("shells", "Merger shells"),
        ("tails", "Tidal tails"),
        ("stream", "Stellar stream"),
    ):
        p = _points(pts, pop)
        if p is not None:
            major = pop == "tails" or 0 <= g.t_major_myr < 1500
            t = g.t_major_myr if major else g.t_minor_myr
            add(
                name,
                _densest(p, 0.25),
                f"{'major' if major else 'minor'} merger {_ago(max(t, 0))} ago",
            )
    for pop, name, text in (
        ("tidal", "Tidal debris", "raised by a close neighbour"),
        (
            "strip",
            "Stripped stars",
            "tidal streams: most of its subhalo is gone",
        ),
        ("jelly", "Ram-pressure tail", "gas stripped by the host's hot halo"),
    ):
        p = _points(pts, pop)
        if p is not None:
            add(name, _densest(p, 0.3), text)
    if rc.l_icl > 0 and g.ics >= ICL_SHARE * g.stellar_mass:
        # On the visible envelope, just inside the frame HD opens with.
        k = 1.05 if rc.kind == "disk" else 0.8
        add(
            "Intracluster light",
            (0.0, -k * E, 0.0),
            f"{_mass(g.ics)} of stars between the galaxies",
        )

    gs = getattr(getattr(layer, "_gpu", None), "gas", None)
    if gas and gs is not None:
        if gs.jet > 0:
            add(
                "Radio jet",
                (0.0, 0.0, 0.6 * gs.jet_len / u),
                f"radio-mode accretion; reaches {gs.jet_len:.0f} kpc",
            )
        if gs.wind > 0.05:
            add(
                "Galactic wind",
                (0.0, 0.0, -0.4 * gs.wind_len / u),
                f"outflow {g.outflow_rate:.1f} M☉/yr, "
                f"mass loading {g.mass_loading:.1f}",
            )
        if gs.hi_amp > 0:
            add(
                "HI gas disc",
                (1.6 * gs.hi_rs / u, 0.0, 0.0),
                f"{_mass(g.h1_gas)} of HI",
            )
        if gs.stream_amp > 0 and np.any(gs.web[0]):
            add(
                "Cold stream",
                tuple(np.asarray(gs.web[0]) * 0.3 * gs.rvir / u),
                f"CGM {_mass(g.cgm_gas)}, fed along the cosmic web",
            )
        if gs.hot > 0:
            from visage.hd.gpu_gas import hot_luminosity

            add(
                "Hot halo gas",
                (0.3 * gs.rvir / u, 0.18 * gs.rvir / u, 0.0),
                f"{_mass(g.hot_gas)}, L_X 10^{hot_luminosity(g):.1f} erg/s",
            )
    out.sort(key=lambda p: p["cat"])
    return out


def to_world(layer, p) -> np.ndarray:
    """A model-frame point of `layer` in world coordinates."""
    return np.asarray(layer._center) + layer._R @ (
        np.asarray(p) * layer._scale
    )


def markers(screen, width: int, height: int) -> list[dict]:
    """Screen points of the parts -> markers.  `screen`: [(x, y, visible)]
    in pixels (y down), one per part in key order.  Markers closer than
    MERGE_PX share one: {"x", "y" (fractions), "n": key numbers, "cats"}."""
    out: list[dict] = []
    for k, (x, y, vis) in enumerate(screen):
        if not vis:
            continue
        for m in out:
            if np.hypot(m["px"] - x, m["py"] - y) < MERGE_PX:
                m["n"].append(k + 1)
                break
        else:
            out.append({"px": x, "py": y, "n": [k + 1]})
    return [
        {
            "x": round(m["px"] / width, 4),
            "y": round(m["py"] / height, 4),
            "n": m["n"],
        }
        for m in out
    ]
