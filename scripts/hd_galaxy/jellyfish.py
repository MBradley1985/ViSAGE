"""The strongest jellyfish (ram-pressure) satellites in the Millennium
SAGE26 output, as ViSAGE draws them now: in the viewer (gas on) at +-10
kpc and a wider frame, and on their own with the tail at full exposure.

    python scripts/hd_galaxy/jellyfish.py     # -> gallery_gas/jellyfish.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parents[1])]

import gallery as G  # noqa: E402
from variants import Viewer, _ctx_shot, _spin  # noqa: E402
from viewer_grid import Shooter, load, to_galaxy  # noqa: E402

from visage.hd.group import ram_pressure  # noqa: E402

H = 0.73


def candidates(g, n=4):
    gid = g["GalaxyIndex"]
    cidx = {int(x): i for i, x in enumerate(gid)}
    pos = np.column_stack([g["Posx"], g["Posy"], g["Posz"]])
    vel = np.column_stack([g["Velx"], g["Vely"], g["Velz"]])
    rows = []
    for i in np.flatnonzero(
        (g["Type"] > 0) & (g["ColdGas"] > 3e8) & (g["StellarMass"] > 3e9)
    ):
        c = cidx.get(int(g["CentralGalaxyIndex"][i]))
        if c is None or g["Regime"][c] != 1:
            continue
        d = pos[i] - pos[c]
        d -= 62.5 * np.round(d / 62.5)
        dv = vel[i] - vel[c]
        st = ram_pressure(
            to_galaxy(g, i),
            to_galaxy(g, c),
            np.linalg.norm(d) * 1000 / H,
            float(np.linalg.norm(dv)),
        )
        rows.append((st, int(i), int(c), dv))
    rows.sort(reverse=True)
    return rows[:n]


def main():
    g = load("millennium")
    cands = candidates(g)
    v = Viewer(npix=700)
    galaxies = v.snapshot(63)
    near, wide = [], []
    for st, i, c, _ in cands:
        G.HALF_KPC = 10.0
        img, mag = G.render(v, galaxies, int(g["GalaxyIndex"][i]))
        sub = (
            f"log M* {G._lm(g)[i]:.1f} · host Mvir {g['Mvir'][c]:.1e} M☉"
            f"\nram strength {st:.2f} · drawn ×{mag:.1f}"
        )
        near.append((img, "In the viewer, ±10 kpc", sub))
        G.HALF_KPC = 40.0
        img, _ = G.render(v, galaxies, int(g["GalaxyIndex"][i]))
        wide.append((img, "In the viewer, ±40 kpc", sub))
        print(i, st, flush=True)
    sh = Shooter(700)
    alone = []
    for st, i, _, dv in cands:
        ctx = {
            "spin": _spin(g, i),
            "hubble_h": H,
            "ram": (-dv / np.linalg.norm(dv), st),
        }
        img = _ctx_shot(sh, to_galaxy(g, i), ctx, 40.0, inc=50.0)
        alone.append(
            (
                img,
                "On its own, ±40 kpc (own exposure)",
                f"ram strength {st:.2f}",
            )
        )
    G.sheet(
        near + wide + alone,
        "Jellyfish satellites in SAGE26 (Millennium) as ViSAGE draws them now",
        G.OUT / "jellyfish.png",
        len(cands),
    )
    print("wrote", G.OUT / "jellyfish.png")


if __name__ == "__main__":
    main()
