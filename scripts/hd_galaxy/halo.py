"""Gas-halo overlay demo: galaxy alone, with the halo gas, and gas alone.

    python3 scripts/hd_galaxy/halo.py

Frames are zoomed out to ~0.35 Rvir so the halo has room to show.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from model import build_disk_maps, build_points, recipe_from_sage  # noqa: E402
from render import gas_halo, render, screen, tonemap  # noqa: E402
from run_prototype import OUT, load, pick, to_galaxy  # noqa: E402

NPIX = 768


def main():
    g = load()
    chosen = pick(g)
    rows = [
        "Star-forming disk (cold regime)",
        "Massive disk (hot regime)",
        "Elliptical (hot regime)",
    ]
    fig, axes = plt.subplots(
        len(rows), 3, figsize=(15, 5.2 * len(rows)), facecolor="black"
    )
    for r, name in enumerate(rows):
        gal = to_galaxy(g, chosen[name])
        rc = recipe_from_sage(gal)
        maps = build_disk_maps(rc) if rc.kind == "disk" else None
        pts = build_points(rc, maps)
        e0 = rc.extent * (1.3 if rc.kind == "disk" else 1.0)
        scale = max(0.35 * gal.rvir_kpc / (e0 * rc.unit_kpc), 1.0)
        lay = render(
            rc, maps, pts, inc=50, pa=30, npix=NPIX, frame_scale=scale
        )
        img, _ = tonemap(lay.total)
        halo = gas_halo(gal, rc, NPIX, lay.half_width, inc=50, pa=30)
        comp = screen(img, halo)
        gas = "HotGas" if gal.hot_gas > 0 else "CGMgas"
        mgas = gal.hot_gas if gal.hot_gas > 0 else gal.cgm_gas
        hw = lay.half_width * rc.unit_kpc
        for c, (im, t) in enumerate(
            [
                (img, "Optical only (button default)"),
                (comp, f"With gas halo ({gas})"),
                (halo, f"{gas} alone: log M = {np.log10(max(mgas, 1)):.2f}"),
            ]
        ):
            ax = axes[r, c]
            ax.imshow(im)
            ax.set_xticks([]), ax.set_yticks([])
            ax.set_title(
                f"{name}\n{t}" if c == 0 else t, color="w", fontsize=10
            )
        axes[r, 0].text(
            0.02,
            0.02,
            f"frame ±{hw:.0f} kpc   Rvir = {gal.rvir_kpc:.0f} kpc",
            color="#bbb",
            fontsize=8,
            transform=axes[r, 0].transAxes,
        )
        print(
            name,
            gas,
            f"{np.log10(max(mgas, 1)):.2f}",
            f"Rvir={gal.rvir_kpc:.0f}kpc",
            f"frame +-{hw:.0f}kpc",
            flush=True,
        )
    fig.tight_layout()
    fig.savefig(OUT / "halo_overlay.png", dpi=100, facecolor="black")
    print("wrote", OUT / "halo_overlay.png")


if __name__ == "__main__":
    main()
