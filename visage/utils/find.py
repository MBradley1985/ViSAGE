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
    "radio": "Radio-loud AGN (strongest jets)",
    "quasar": "Brightest quasars",
    "gasrich": "Most gas-rich galaxies",
    "elliptical": "Biggest ellipticals",
    "icl": "Most intracluster light",
    "winds": "Strongest galactic winds",
    "hot": "Biggest hot atmospheres",
}

# Radio-loud from this jet power (log10 erg/s; as visage.hd.model).
RADIO_LOUD = 42.0


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
        detail = {k: f"{1000 * d:.0f} h^-1 kpc apart" for d, k in rows[:n]}
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
        detail = {int(k): f"sSFR {ssfr[k]:.1e} yr^-1" for k in pick[:n]}
    elif preset == "quenched":
        c = np.flatnonzero(ok & cen & (ssfr < 1e-11))
        pick = c[np.argsort(-ms[c])]
    elif preset == "bh":
        bh = np.asarray(galaxies.bh_mass, float)
        c = np.flatnonzero(ok & (bh > 0))
        pick = c[np.argsort(-bh[c])]
        detail = {int(k): f"log M_BH {_lm(bh[k]):.1f}" for k in pick[:n]}
    elif preset == "ffb":
        c = np.flatnonzero(ok & (np.asarray(galaxies.ffb_regime) == 1))
        pick = c[np.argsort(-ms[c])]
    elif preset == "radio":
        # SAGE26's Heating is the jet power, 0.1 Mdot c^2 (log10 erg/s).
        p = np.asarray(galaxies.heating, float)
        c = np.flatnonzero(ok & (p >= RADIO_LOUD))
        pick = c[np.argsort(-p[c])]
        detail = {int(k): f"log P_jet {p[k]:.1f} erg/s" for k in pick[:n]}
    elif preset == "quasar":
        q = (getattr(galaxies, "extra", None) or {}).get(
            "QuasarModeBHaccretionMass"
        )
        if q is None:
            return []
        q = np.asarray(q, float)
        c = np.flatnonzero(ok & (q > 0))
        pick = c[np.argsort(-q[c])]
    elif preset == "gasrich":
        f = np.asarray(galaxies.cold_gas, float) / np.maximum(ms, 1.0)
        c = np.flatnonzero(ok & (ms > 1e9) & (f > 0))
        pick = c[np.argsort(-f[c])]
        detail = {int(k): f"cold gas {f[k]:.1f} x M*" for k in pick[:n]}
    elif preset == "elliptical":
        bt = np.asarray(galaxies.bulge_mass, float) / np.maximum(ms, 1.0)
        c = np.flatnonzero(ok & (bt > 0.8))
        pick = c[np.argsort(-ms[c])]
        detail = {int(k): f"B/T {bt[k]:.2f}" for k in pick[:n]}
    elif preset == "icl":
        ics = np.asarray(galaxies.ics_mass, float)
        c = np.flatnonzero(ok & cen & (ics > 0))
        pick = c[np.argsort(-ics[c])]
        detail = {int(k): f"log M_ICS {_lm(ics[k]):.1f}" for k in pick[:n]}
    elif preset == "winds":
        w = np.asarray(galaxies.outflow_rate, float)
        c = np.flatnonzero(ok & (w > 0))
        pick = c[np.argsort(-w[c])]
        detail = {int(k): f"outflow {w[k]:.0f} Msun/yr" for k in pick[:n]}
    else:  # hot
        hot = np.asarray(galaxies.hot_gas, float)
        c = np.flatnonzero(ok & cen & (hot > 0))
        pick = c[np.argsort(-hot[c])]
        detail = {int(k): f"log M_hot {_lm(hot[k]):.1f}" for k in pick[:n]}

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


def available(galaxies, box: float | None = None) -> list[str]:
    """The presets this catalogue can answer (its model writes the fields,
    and some galaxy qualifies), in menu order."""
    if galaxies.count == 0:
        return []
    out = []
    for k in PRESETS:
        if k == "pairs":  # (cheaply: some group of exactly two)
            size, _ = _group_sizes(
                galaxies, np.asarray(galaxies.stellar_mass) > 0
            )
            if np.any(size == 2):
                out.append(k)
        elif find(galaxies, k, box=box, n=1):
            out.append(k)
    return out
