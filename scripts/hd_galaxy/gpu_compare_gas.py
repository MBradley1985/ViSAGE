"""CPU 2D gas overlay vs GPU shader gas, same view (galaxy and halo scale).

python3 scripts/hd_galaxy/gpu_compare_gas.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/hd_galaxy"))


def main():
    import pyvista as pv
    from PIL import Image

    from run_prototype import load, pick, to_galaxy
    from visage.hd.gpu import GPUGalaxy
    from visage.hd.model import build_disk_maps, build_points, recipe_from_sage
    from visage.hd.raymarch import (
        gas_halo,
        icl_zone,
        render,
        rot,
        screen,
        tonemap,
    )

    g = load("millennium")
    ch = pick(g)
    rows = []
    for which in (
        "Star-forming disk (cold regime)",
        "Massive disk (hot regime)",
    ):
        gal = to_galaxy(g, ch[which])
        rc = recipe_from_sage(gal)
        maps = build_disk_maps(rc, n=1024)
        pts = build_points(rc, maps)
        face = render(rc, maps, pts, inc=0, pa=25, npix=256, threads=8)
        white = float(
            np.percentile(
                (face.total - face.points.get("agn", 0)).mean(axis=2), 99.97
            )
        )
        row = []
        for inc, half in (
            (55, rc.extent * 1.3 * 2.5),
            (55, 1.05 * gal.rvir_kpc / rc.unit_kpc),
        ):
            npix = 384
            R = rot(inc, 25)
            log = half * rc.unit_kpc > 0.5 * gal.rvir_kpc
            lay = render(
                rc, maps, pts, R=R, npix=npix, half_width=half, threads=8
            )
            cpu, _ = tonemap(lay.total, white=white, bloom=0.0)
            cpu = screen(cpu, icl_zone(gal, rc, npix, half))
            cpu = screen(
                cpu, gas_halo(gal, rc, npix, half, R=R, log_stretch=log)
            )
            pl = pv.Plotter(off_screen=True, window_size=[npix, npix])
            pl.set_background("black")
            gg = GPUGalaxy(pl)
            gg.build(rc, maps, pts, white, np.eye(4), gal=gal, gas=True)
            gg.set_view_half(half * rc.unit_kpc)
            d = 40 * half
            toward = R.T @ np.array([0.0, 0.0, 1.0])
            up = R.T @ np.array([0.0, 1.0, 0.0])
            pl.camera_position = [tuple(toward * d), (0, 0, 0), tuple(up)]
            pl.camera.view_angle = float(np.degrees(2 * np.arctan(half / d)))
            hx = max(gg.box_half)
            pl.camera.clipping_range = (d - 2 * hx, d + 2 * hx)
            gg.set_camera(toward * d)
            pl.render()
            gpu = pl.screenshot(return_img=True)[..., :3]
            pl.close()
            row.append(
                np.concatenate([(cpu * 255).astype(np.uint8), gpu], axis=1)
            )
        rows.append(np.concatenate(row, axis=1))
    out = ROOT / "scripts/hd_galaxy/outputs_v4/viewer/gpu_vs_cpu_gas.png"
    Image.fromarray(np.concatenate(rows, axis=0)).save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
