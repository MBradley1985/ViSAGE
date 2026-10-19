"""Drive the real viewer off-screen: select galaxies, press HD (+ Gas), and
capture what the scene renders.

    python3 scripts/hd_galaxy/viewer_shots.py [--par PATH] [--out DIR]

Uses the same pattern as the nav-panel tests: an off-screen Scene, the
navigation panel built on a trame server with a stub view_update, and the
HD controller called exactly as the button does.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def capture(scene):
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

    rw = scene.plotter.ren_win
    rw.Render()
    w2if = vtkWindowToImageFilter()
    w2if.SetInput(rw)
    w2if.SetInputBufferTypeToRGB()
    w2if.ReadFrontBufferOff()
    w2if.Update()
    vimg = w2if.GetOutput()
    w, h, _ = vimg.GetDimensions()
    return vtk_to_numpy(vimg.GetPointData().GetScalars()).reshape(h, w, -1)[
        ::-1
    ]


def orbit(scene, lay, inc_deg, dist_scale=1.0, gas=False):
    """Put the camera at `inc_deg` from the galaxy's spin axis."""
    cam = scene.plotter.camera
    radius = lay.rvir_world if gas else lay.radius_world
    dist = (
        radius / np.tan(np.deg2rad(cam.view_angle) / 2.0) * 1.15 * dist_scale
    )
    e2, e3 = lay._R[:, 1], lay._R[:, 2]
    i = np.deg2rad(inc_deg)
    view = np.cos(i) * e3 - np.sin(i) * e2
    c = lay._center
    cam.focal_point = tuple(c)
    cam.position = tuple(c + view * dist)
    up = e3 if inc_deg > 5 else lay._R[:, 0]
    cam.up = tuple(up)
    scene.plotter.renderer.ResetCameraClippingRange()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--par",
        default=str(Path.home() / "Documents/PhD/SAGE26/input/millennium.par"),
    )
    ap.add_argument(
        "--out", default=str(ROOT / "scripts/hd_galaxy/outputs_v4/viewer")
    )
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from PIL import Image
    from trame.app import get_server
    from trame.ui.vuetify3 import SinglePageLayout

    from visage.scene.scene import Scene
    from visage.ui.navigation_panel import build_navigation_panel

    t0 = time.time()
    scene = Scene(args.par, off_screen=True)
    server = get_server("hd_viewer_shots", client_type="vue3")
    server.controller.view_update = lambda *a, **k: None
    with SinglePageLayout(server) as layout:
        with layout.content:
            build_navigation_panel(server, scene)
    state, ctrl = server.state, server.controller
    state.ready()
    scene.plotter.ren_win.SetSize(900, 900)
    print(f"scene ready in {time.time() - t0:.0f}s", flush=True)

    halos, galaxies = scene.active_model.loader.get(scene.current_snap)
    lms = np.log10(np.maximum(galaxies.stellar_mass, 1))
    bt = galaxies.bulge_mass / np.maximum(galaxies.stellar_mass, 1)
    sfr = galaxies.sfr_disk + galaxies.sfr_bulge
    ib = galaxies.instability_bulge_mass / np.maximum(galaxies.stellar_mass, 1)
    cen = galaxies.gal_type == 0

    def median_sfr(mask):
        idx = np.flatnonzero(mask & cen)
        return (
            int(idx[np.argsort(sfr[idx])[len(idx) // 2]]) if len(idx) else None
        )

    picks = {
        "cold_disk": median_sfr(
            (galaxies.cgm_regime == 0)
            & (lms > 10.4)
            & (lms < 10.8)
            & (bt < 0.15)
        ),
        "barred": median_sfr(
            (lms > 10.5) & (lms < 11.0) & (ib > 0.12) & (bt < 0.4)
        ),
        "hot_disk": median_sfr(
            (galaxies.cgm_regime == 1) & (lms > 10.9) & (bt < 0.3) & (sfr > 1)
        ),
        "elliptical": median_sfr(
            (galaxies.cgm_regime == 1) & (lms > 11.2) & (bt > 0.85)
        ),
    }
    print("picks", picks, flush=True)

    for name, gidx in picks.items():
        if gidx is None:
            continue
        state.hd_gas = False
        state.nav_gal_idx = gidx
        state.flush()
        t = time.time()
        ctrl.toggle_hd()
        lay = scene_hd_layer(ctrl)
        print(
            f"{name}: HD built in {time.time() - t:.1f}s, "
            f"{sum(len(c[2]) for c in lay._clouds.values())} particles; "
            + "; ".join(lay.recipe.notes[:3]),
            flush=True,
        )
        # Top row: the particle preview (what you see while orbiting).
        # Bottom row: the refined, ray-marched view once the camera rests.
        views = [
            (0, 1.0, False),
            (55, 1.0, False),
            (88, 1.0, False),
            (55, 1.0, True),
            (55, 0.25, True),
        ]
        preview, refined = [], []
        for inc, dscale, gas in views:
            if gas and not state.hd_gas:
                state.hd_gas = True
                state.flush()
            orbit(scene, lay, inc, dist_scale=dscale, gas=gas)
            lay._on_camera()  # as the camera observer would
            preview.append(capture(scene))
            t = time.time()
            ctrl.hd_refine_now(900)
            dt = time.time() - t
            refined.append(capture(scene))
            print(f"   refine i={inc} gas={gas}: {dt:.1f}s", flush=True)
        grid = np.concatenate(
            [np.concatenate(preview, axis=1), np.concatenate(refined, axis=1)],
            axis=0,
        )
        Image.fromarray(grid).save(out / f"viewer_{name}.png")
        ctrl.toggle_hd()  # off again
        state.flush()
        assert not lay.active, "HD layer should be cleared when toggled off"
    print("wrote", out, flush=True)


def scene_hd_layer(ctrl):
    """The HD layer the controller created (closure state of the panel)."""
    import gc

    from visage.hd.layer import HDGalaxyLayer

    layers = [o for o in gc.get_objects() if isinstance(o, HDGalaxyLayer)]
    return [lay for lay in layers if lay.active][0]


if __name__ == "__main__":
    main()
