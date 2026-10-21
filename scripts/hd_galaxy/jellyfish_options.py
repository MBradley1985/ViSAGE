"""Options for jellyfish (ram-pressure) tails, on the strongest jellyfish
satellites in the Millennium SAGE26 output, each as the viewer draws it.

    python scripts/hd_galaxy/jellyfish_options.py   # -> gallery_gas/
"""

from __future__ import annotations

import gc
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parents[1])]

import gallery as G  # noqa: E402
import visage.hd.group as group  # noqa: E402
import visage.hd.model as model  # noqa: E402
from jellyfish import candidates  # noqa: E402
from variants import Viewer  # noqa: E402
from viewer_grid import load, to_galaxy  # noqa: E402

CAL = dict(lo=-7.8, span=2.0)  # recalibrated: ~1% of satellites saturate
MATCH = [
    (
        "Chosen: CGM half-stripped, matched, recalibrated",
        dict(gain=1.0),
        None,
        True,
        10.0,
    ),
]
OPTIONS = [
    ("A  current", dict(gain=1.0), None, True),
    ("B  tail ×3 brighter", dict(gain=3.0), None, True),
    ("C  ×3 brighter, recalibrated", dict(gain=3.0), CAL, True),
    ("D  ×6 bold, recalibrated", dict(gain=6.0), CAL, True),
    (
        "E  ×3, more Hα, recalibrated",
        dict(gain=3.0, halpha=0.75, knots=0.25),
        CAL,
        True,
    ),
    ("F  C with gas off", dict(gain=3.0), CAL, False),
]


def _clear_hd_cache():
    for o in gc.get_objects():
        if isinstance(o, group.BuildCache):
            o.clear()


def main():
    g = load("millennium")
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    options = MATCH if which == "match" else [o + (1.0,) for o in OPTIONS]
    cands = candidates(g, n=6 if which == "match" else 4)
    v = Viewer(npix=700)
    galaxies = v.snapshot(63)
    base_j = dict(model.JELLY)
    base_r = (group.RAM_LO, group.RAM_SPAN)
    G.HALF_KPC = 40.0
    panels = []
    import visage.hd.layer as layer

    for name, jelly, cal, gas, cap in options:
        group.TAIL_GAIN_MAX = cap
        layer.STRIP_CGM = True
        model.JELLY.clear()
        model.JELLY.update(base_j, **jelly)
        group.RAM_LO, group.RAM_SPAN = (
            (cal["lo"], cal["span"]) if cal else base_r
        )
        _clear_hd_cache()
        for _st, i, c, dv in cands:
            sat, host = to_galaxy(g, i), to_galaxy(g, c)
            d = np.column_stack([g["Posx"], g["Posy"], g["Posz"]])
            r = d[i] - d[c]
            r -= 62.5 * np.round(r / 62.5)
            st = group.ram_pressure(
                sat,
                host,
                np.linalg.norm(r) * 1000 / G.H,
                float(np.linalg.norm(dv)),
            )
            img, mag = render(v, galaxies, int(g["GalaxyIndex"][i]), gas)
            sub = (
                f"log M* {G._lm(g)[i]:.1f} · ram strength {st:.2f}"
                f"\nhost Mvir {g['Mvir'][c]:.1e} M☉ · ±40 kpc ×{mag:.1f}"
            )
            panels.append((img, name, sub))
        print(name, flush=True)
    model.JELLY.clear()
    model.JELLY.update(base_j)
    group.RAM_LO, group.RAM_SPAN = base_r
    G.sheet(
        panels,
        "Jellyfish tails -- options (rows) on the strongest SAGE26 "
        "jellyfish (columns), as the viewer draws them",
        G.OUT
        / (
            "jellyfish_matched.png"
            if which == "match"
            else "jellyfish_options.png"
        ),
        len(cands),
    )
    group.TAIL_GAIN_MAX = 10.0
    print("wrote")


def render(v, galaxies, gid, gas):
    v.state.hd_gas = gas
    v.state.flush()
    orig = v.state.hd_gas
    img, mag = _render_keep_gas(v, galaxies, gid, gas)
    v.state.hd_gas = orig
    return img, mag


def _render_keep_gas(v, galaxies, gid, gas):
    # gallery.render switches gas on; switch it back off for option F.
    img, mag = G.render(v, galaxies, gid)
    if not gas:
        # Re-render with gas off (same build, a shader switch).
        st, ctrl = v.state, v.ctrl
        i = int(np.flatnonzero(galaxies.galaxy_id == gid)[0])
        st.nav_gal_idx = i
        st.flush()
        ctrl.toggle_hd()
        st.flush()
        st.hd_gas = False
        st.flush()
        img = _frame_and_capture(v, mag)
        ctrl.toggle_hd()
        st.flush()
    return img, mag


def _frame_and_capture(v, mag, inc=55.0):
    from viewer_shots import capture

    cam = v.scene.plotter.camera
    fp = np.array(cam.focal_point)
    grp = next(
        o
        for o in gc.get_objects()
        if isinstance(o, group.HDGroupLayer) and o.active
    )
    m = grp.member_at(fp)
    e2, e3 = m._R[:, 1], m._R[:, 2]
    t = np.deg2rad(inc)
    view = np.cos(t) * e3 - np.sin(t) * e2
    cam.up = tuple(e3)
    dist = (
        G.HALF_KPC
        * mag
        * G.H
        / 1000.0
        / np.tan(np.deg2rad(cam.view_angle) / 2)
    )
    cam.position = tuple(fp + view * dist)
    v.scene.plotter.renderer.ResetCameraClippingRange()
    v.scene.camera.marker.clear()
    return capture(v.scene)


if __name__ == "__main__":
    main()
