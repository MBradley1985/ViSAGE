"""Find: galaxies worth a look in a snapshot, by preset.

Each preset picks and orders galaxies straight from the catalogue; the
selection card's Find list shows the top few, and a click selects one.
"""

from __future__ import annotations

import numpy as np

from visage.utils.group_info import galaxy_label

# key -> label, in the order the menu lists them.
PRESETS = {
    "massive": "Most massive galaxies",
    "richest": "Richest groups and clusters",
    "mw": "Milky Way analogues",
    "pairs": "Close pairs",
    "merging": "Merging before the next snapshot",
    "starburst": "Starbursts (highest sSFR)",
    "quenched": "Quenched centrals",
    "bh": "Biggest black holes",
    "ffb": "Feedback-free starbursts",
}


def _lm(x) -> np.ndarray:
    return np.log10(np.maximum(np.asarray(x, float), 1.0))


def _group_sizes(galaxies, ok) -> tuple[np.ndarray, np.ndarray]:
    """For every galaxy, the number of members (with M* > 0) in its FOF
    group; zeros if the catalogue has no CentralGalaxyIndex."""
    cid = np.asarray(galaxies.central_id)
    if not np.any(cid):
        return np.zeros(galaxies.count, int), cid
    ids, inv, counts = np.unique(
        cid[ok], return_inverse=True, return_counts=True
    )
    n = np.zeros(galaxies.count, int)
    n[np.flatnonzero(ok)] = counts[inv.ravel()]
    return n, cid


def find(galaxies, preset: str, box: float | None = None, n: int = 15):
    """The top `n` galaxies for `preset`: a list of {"idx", "text"}."""
    if galaxies.count == 0 or preset not in PRESETS:
        return []
    ms = np.asarray(galaxies.stellar_mass, float)
    ok = ms > 0
    lm = _lm(ms)
    cen = np.asarray(galaxies.gal_type) == 0
    ssfr = np.asarray(galaxies.ssfr, float)
    pick: np.ndarray
    detail = {}

    if preset == "massive":
        pick = np.flatnonzero(ok)[np.argsort(-ms[ok])]
    elif preset == "richest":
        size, _ = _group_sizes(galaxies, ok)
        c = np.flatnonzero(ok & cen & (size > 1))
        pick = c[np.lexsort((-ms[c], -size[c]))]
        detail = {int(k): f"{size[k]} members" for k in pick[:n]}
    elif preset == "mw":
        bt = np.asarray(galaxies.bulge_mass, float) / np.maximum(ms, 1.0)
        c = np.flatnonzero(
            ok & cen & (lm > 10.6) & (lm < 10.9) & (bt < 0.35) & (ssfr > 1e-11)
        )
        pick = c[np.argsort(np.abs(lm[c] - 10.75))]
        detail = {int(k): f"B/T {bt[k]:.2f}" for k in pick[:n]}
    elif preset == "pairs":
        size, cid = _group_sizes(galaxies, ok)
        two = np.flatnonzero(ok & (size == 2))
        pos = np.asarray(galaxies.positions, float)
        by_group: dict = {}
        for k in two:
            by_group.setdefault(int(cid[k]), []).append(int(k))
        rows = []
        for a, b in (v for v in by_group.values() if len(v) == 2):
            d = pos[a] - pos[b]
            if box:
                d -= box * np.round(d / box)
            big = a if ms[a] >= ms[b] else b
            rows.append((float(np.linalg.norm(d)), big))
        rows.sort()
        pick = np.array([k for _, k in rows], int)
        detail = {k: f"{1000 * d:.0f} kpc/h apart" for d, k in rows[:n]}
    elif preset == "merging":
        mt = (getattr(galaxies, "extra", None) or {}).get("mergeType")
        if mt is None:
            return []
        mt = np.asarray(mt)
        c = np.flatnonzero(ok & (mt > 0))
        pick = c[np.argsort(-ms[c])]
        kind = {
            1: "minor merger",
            2: "major merger",
            3: "disk instability",
            4: "disrupted to ICS",
        }
        detail = {int(k): kind.get(int(mt[k]), "merging") for k in pick[:n]}
    elif preset == "starburst":
        c = np.flatnonzero(ok & (ms > 1e9))
        pick = c[np.argsort(-ssfr[c])]
        detail = {int(k): f"sSFR {ssfr[k]:.1e}/yr" for k in pick[:n]}
    elif preset == "quenched":
        c = np.flatnonzero(ok & cen & (ssfr < 1e-11))
        pick = c[np.argsort(-ms[c])]
    elif preset == "bh":
        bh = np.asarray(galaxies.bh_mass, float)
        c = np.flatnonzero(ok & (bh > 0))
        pick = c[np.argsort(-bh[c])]
        detail = {int(k): f"log M_BH {_lm(bh[k]):.1f}" for k in pick[:n]}
    else:  # ffb
        c = np.flatnonzero(ok & (np.asarray(galaxies.ffb_regime) == 1))
        pick = c[np.argsort(-ms[c])]

    out = []
    for k in pick[:n]:
        k = int(k)
        role = "central" if cen[k] else "sat."
        extra = detail.get(k)
        out.append(
            {
                "idx": k,
                "text": f"{galaxy_label(galaxies, k)} · {role} · "
                f"log M* {lm[k]:.1f}" + (f" · {extra}" if extra else ""),
            }
        )
    return out
