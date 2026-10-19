"""CPU ray-march (raymarch.render) vs GPU shader (gpu.GPUGalaxy), same view.

python3 scripts/hd_galaxy/gpu_compare.py ["Barred spiral"] [--npix 512]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/hd_galaxy"))


def gpu_view(rc, maps, pts, white, gal, inc, pa, npix):
    import pyvista as pv

    from visage.hd.gpu import GPUGalaxy
    from visage.hd.raymarch import rot

    pl = pv.Plotter(off_screen=True, window_size=[npix, npix])
    pl.set_background("black")
    g = GPUGalaxy(pl)
    g.build(rc, maps, pts, white, np.eye(4), gal=gal)
    R = rot(inc, pa)
    E = rc.extent * (1.3 if rc.kind == "disk" else 1.0)
    d = 400.0
    toward = R.T @ np.array([0.0, 0.0, 1.0])
    up = R.T @ np.array([0.0, 1.0, 0.0])
    pl.camera_position = [tuple(toward * d), (0, 0, 0), tuple(up)]
    pl.camera.view_angle = float(np.degrees(2 * np.arctan(E / d)))
    hx = max(g.box_half)
    pl.camera.clipping_range = (d - 2 * hx, d + 2 * hx)
    g.set_camera(toward * d)
    pl.render()
    t = time.time()
    for _ in range(3):
        pl.render()
    dt = (time.time() - t) / 3
    img = pl.screenshot(return_img=True)
    pl.close()
    return img, dt


def main():
    from PIL import Image

    from run_prototype import load, pick, to_galaxy
    from visage.hd.model import build_disk_maps, build_points, recipe_from_sage
    from visage.hd.raymarch import icl_zone, render, screen, tonemap

    which = (
        sys.argv[1]
        if len(sys.argv) > 1 and not sys.argv[1].startswith("--")
        else "Barred spiral"
    )
    npix = 512
    g = load("millennium")
    gal = to_galaxy(g, pick(g)[which])
    rc = recipe_from_sage(gal)
    maps = build_disk_maps(rc, n=1024) if rc.kind == "disk" else None
    pts = build_points(rc, maps)
    face = render(rc, maps, pts, inc=0, pa=25, npix=256, threads=8)
    no_agn = face.total - face.points.get("agn", 0)
    white = float(np.percentile(no_agn.mean(axis=2), 99.97))
    rows = []
    for inc in (0, 60, 88):
        lay = render(rc, maps, pts, inc=inc, pa=25, npix=npix, threads=8)
        cpu, _ = tonemap(lay.total, white=white, bloom=0.0)
        cpu = screen(cpu, icl_zone(gal, rc, npix, lay.half_width))
        gpu, dt = gpu_view(rc, maps, pts, white, gal, inc, 25, npix)
        print(f"{which} i={inc}: GPU frame {dt * 1000:.0f} ms", flush=True)
        rows.append(
            np.concatenate(
                [(cpu * 255).astype(np.uint8), gpu[..., :3]], axis=1
            )
        )
    out = (
        ROOT
        / "scripts/hd_galaxy/outputs_v4/viewer"
        / f"gpu_vs_cpu_{which.split()[0].lower()}.png"
    )
    Image.fromarray(np.concatenate(rows, axis=0)).save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
