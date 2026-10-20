"""Options for clumpy (high-z) and feedback-free-starburst disks, on real
SAGE26 galaxies: rows are looks, columns are galaxies from the catalogue."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parents[1])]

import visage.hd.model as model  # noqa: E402
from variants import _median_pick, _sheet, shot  # noqa: E402
from viewer_grid import Shooter, load, to_galaxy  # noqa: E402

BASE = dict(model.CLUMPY)
OPTIONS = [
    (
        "A  original",
        dict(
            young=1.0,
            clusters=1.0,
            amp=1.7,
            base=0.5,
            width=(0.25, 0.5),
            wing=0.3,
            conc=1.0,
            spread=1.8,
            hii=0.95,
        ),
    ),
    ("B  toned down", dict(young=0.5, clusters=0.5)),
    (
        "C  subtle clumps",
        dict(
            young=0.4,
            clusters=0.35,
            amp=0.8,
            base=0.8,
            width=(0.25, 0.45),
            conc=1.3,
            spread=1.0,
            hii=1.2,
        ),
    ),
    (
        "D  faint compact knots",
        dict(
            young=0.35,
            clusters=0.3,
            amp=1.2,
            base=0.6,
            width=(0.15, 0.3),
            wing=0.15,
            conc=1.3,
            spread=1.2,
            hii=1.2,
        ),
    ),
    (
        "E  smooth, hint of clumps",
        dict(
            young=0.4,
            clusters=0.25,
            amp=0.4,
            base=1.0,
            conc=1.3,
            spread=1.0,
            hii=1.2,
        ),
    ),
    (
        "F  crisp clumps, dimmer",
        dict(
            young=0.5,
            clusters=0.5,
            amp=2.5,
            base=0.35,
            width=(0.18, 0.4),
            wing=0.0,
            conc=1.3,
            spread=1.0,
            hii=1.2,
        ),
    ),
]


E = dict(
    young=0.4, clusters=0.25, amp=0.4, base=1.0, conc=1.3, spread=1.0, hii=1.2
)
E_OPTIONS = [
    ("E  as shown", E),
    ("E1  fewer sparkles", {**E, "clusters": 0.12}),
    ("E2  dimmer young light", {**E, "young": 0.25, "clusters": 0.15}),
    (
        "E3  broad soft patches",
        {**E, "amp": 0.6, "width": (0.45, 0.9), "wing": 0.6},
    ),
    (
        "E4  even sprinkle",
        {**E, "clusters": 0.15, "conc": 0.8, "spread": 2.5, "hii": 0.9},
    ),
    (
        "E5  faintest hint",
        {**E, "young": 0.3, "clusters": 0.1, "amp": 0.2, "conc": 1.0},
    ),
]


FINAL = [("E5 (old)", E_OPTIONS[-1][1]), ("chosen: E5, more diffuse", {})]


def galaxies():
    """Clumpy star-forming disks and FFB galaxies straight from the
    Millennium SAGE26 output."""
    picks = []
    for snap in (41, 32, 27):  # z ~ 1, 2, 3
        g = load("millennium", snap)
        lms = np.log10(np.maximum(g["StellarMass"], 1))
        bt = g["BulgeMass"] / np.maximum(g["StellarMass"], 1)
        k = _median_pick(
            g, (g["Type"] == 0) & (lms > 10.2) & (lms < 10.7) & (bt < 0.3)
        )
        picks.append((g, k, f"z = {g['redshift']:.1f} disk"))
    for snap in (18, 22):
        g = load("millennium", snap)
        idx = np.flatnonzero((g["FFBRegime"] > 0) & (g["StellarMass"] > 0))
        if len(idx):
            k = int(idx[np.argmax(g["StellarMass"][idx])])
            picks.append((g, k, f"FFB, z = {g['redshift']:.1f}"))
    return picks


def main():
    out = HERE / "outputs_v6"
    sh = Shooter(700)
    picks = galaxies()
    gals = [(to_galaxy(g, k), lbl, g) for g, k, lbl in picks]
    panels = []
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    options = {"e": E_OPTIONS, "final": FINAL}.get(which, OPTIONS)
    fname = {
        "e": "clumpy_options_E.png",
        "final": "clumpy_final.png",
    }.get(which, "clumpy_options.png")
    for name, opt in options:
        model.CLUMPY.clear()
        model.CLUMPY.update(BASE, **opt)
        for gal, lbl, _g in gals:
            img, rc = shot(sh, gal, inc=25.0)
            sub = (
                f"{lbl} · log M* {np.log10(gal.stellar_mass):.1f} · "
                f"{rc.arm_class}{f', {rc.clumps} clumps' if rc.clumps else ''}"
            )
            panels.append((img, name, sub))
        print(name, flush=True)
    model.CLUMPY.clear()
    model.CLUMPY.update(BASE)
    _sheet(
        panels,
        ("Diffuse variations of E" if which == "e" else "Clumpy / FFB disks")
        + " -- options (rows), real SAGE26 Millennium galaxies (columns)",
        out / fname,
        len(gals),
    )
    print("wrote", out / fname)


if __name__ == "__main__":
    main()
