"""Style options for the quasar-mode AGN, radio jets and nuclear rings.

    python3 scripts/hd_galaxy/features.py

Real SAGE26 centrals that trigger each feature, rendered with every style
side by side.  Writes output/options_agn.png and output/options_ring.png.
"""

from __future__ import annotations

import dataclasses
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
from run_prototype import OUT, load, to_galaxy  # noqa: E402

NPIX = 512


def examples(g, mask, n, key):
    idx = np.flatnonzero(mask)
    return [int(i) for i in idx[np.argsort(-key[idx])][:n]]


def frame(rc, half_kpc):
    e0 = rc.extent * (1.3 if rc.kind == "disk" else 1.0)
    return half_kpc / (e0 * rc.unit_kpc)


def panel(ax, img, title):
    ax.imshow(img)
    ax.set_xticks([]), ax.set_yticks([])
    ax.set_title(title, color="w", fontsize=9)


def agn_figure(g):
    lms = np.log10(np.maximum(g["StellarMass"], 1))
    cen = g["Type"] == 0
    qso = g["QuasarModeBHaccretionMass"]
    rows = []
    for lo, hi in [(10.0, 10.6), (10.6, 11.2), (11.2, 12.5)]:
        m = cen & (lms >= lo) & (lms < hi) & (qso > 0) & (g["Heating"] > 40)
        if not m.any():
            m = cen & (lms >= lo) & (lms < hi) & (qso > 0)
        rows += examples(g, m, 1, qso)
    cols = [
        "No AGN",
        "Point (current)",
        "Glow",
        "Glow + diffraction spikes",
        "Glow + radio jets (gas overlay)",
    ]
    fig, axes = plt.subplots(
        len(rows),
        len(cols),
        figsize=(3.4 * len(cols), 3.7 * len(rows)),
        facecolor="black",
    )
    for r, i in enumerate(rows):
        gal = to_galaxy(g, i)
        rc0 = recipe_from_sage(gal)
        maps = build_disk_maps(rc0, n=1536) if rc0.kind == "disk" else None
        pts = build_points(rc0, maps)
        fs = frame(rc0, 20.0)
        white = None
        for c, col in enumerate(cols):
            if c == 0:
                rc = dataclasses.replace(rc0, agn=0.0)
            else:
                style = {1: "point", 2: "glow", 3: "spikes", 4: "glow"}[c]
                rc = dataclasses.replace(rc0, agn_style=style)
            lay = render(
                rc, maps, pts, inc=35, pa=25, npix=NPIX, frame_scale=fs
            )
            img, w = tonemap(lay.total, white=white)
            white = white or w
            if c == 4:
                gg = dataclasses.replace(
                    gal, heating_log=max(gal.heating_log, 40.5)
                )
                img = screen(
                    img, gas_halo(gg, rc, NPIX, lay.half_width, inc=35, pa=25)
                )
            title = col if r == 0 else ""
            panel(axes[r, c], img, title)
        jet_note = (
            f"Heating 10^{gal.heating_log:.1f} erg/s"
            if gal.heating_log > 40
            else f"Heating 10^{gal.heating_log:.1f} (jets forced for demo)"
        )
        axes[r, 0].set_ylabel(
            f"log M* {np.log10(gal.stellar_mass):.2f}  {rc0.kind}\n"
            f"QSO accretion {gal.qso_accretion:.1e} Msun\nlog M_BH {np.log10(max(gal.bh_mass, 1)):.2f}\n{jet_note}",
            color="w",
            fontsize=8,
        )
        print(
            "agn row",
            r,
            i,
            rc0.kind,
            f"agn={rc0.agn:.3f}",
            jet_note,
            flush=True,
        )
    fig.suptitle(
        "Quasar-mode AGN style options (QuasarModeBHaccretionMass > 0; ±20 kpc, i = 35°)",
        color="w",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "options_agn.png", dpi=110, facecolor="black")
    plt.close(fig)
    print("wrote", OUT / "options_agn.png", flush=True)


def ring_figure(g):
    lms = np.log10(np.maximum(g["StellarMass"], 1))
    cen = g["Type"] == 0
    sb, sfr = g["SfrBulge"], g["SfrDisk"] + g["SfrBulge"]
    ring = (
        cen
        & (sb > 0.05)
        & (sb > 0.08 * sfr)
        & (lms > 10.0)
        & (g["BulgeMass"] / np.maximum(g["StellarMass"], 1) < 0.75)
    )
    ib = g["InstabilityBulgeMass"] / np.maximum(g["StellarMass"], 1)
    rows = examples(g, ring & (ib > 0.06), 2, sb) + examples(
        g, ring & (ib <= 0.06), 1, sb
    )
    cols = [
        "No ring",
        "Clusters (current)",
        "Starburst ring",
        "Starburst ring + dust lanes",
    ]
    styles = [None, "clusters", "starburst", "starburst_dust"]
    fig, axes = plt.subplots(
        len(rows),
        len(cols) + 1,
        figsize=(3.4 * (len(cols) + 1), 3.7 * len(rows)),
        facecolor="black",
    )
    for r, i in enumerate(rows):
        gal = to_galaxy(g, i)
        rc0 = recipe_from_sage(gal)
        white = None
        for c, st in enumerate(styles):
            rc = (
                dataclasses.replace(rc0, ring=0.0)
                if st is None
                else dataclasses.replace(rc0, ring_style=st)
            )
            maps = build_disk_maps(rc, n=2048)
            pts = build_points(rc, maps)
            half_kpc = max(3.0 * rc0.ring_r * rc0.unit_kpc, 4.0)
            lay = render(
                rc,
                maps,
                pts,
                inc=30,
                pa=25,
                npix=NPIX,
                frame_scale=frame(rc0, half_kpc),
            )
            img, w = tonemap(lay.total, white=white)
            white = white or w
            panel(axes[r, c + 1], img, cols[c] if r == 0 else "")
            if c == 3:
                # Context: the whole galaxy with the chosen style.
                lay = render(
                    rc,
                    maps,
                    pts,
                    inc=30,
                    pa=25,
                    npix=NPIX,
                    frame_scale=frame(rc0, 25.0),
                )
                ctx, _ = tonemap(lay.total)
                panel(
                    axes[r, 0], ctx, "Whole galaxy (±25 kpc)" if r == 0 else ""
                )
        axes[r, 0].set_ylabel(
            f"log M* {np.log10(gal.stellar_mass):.2f}  B/T {gal.bt:.2f}\n"
            f"SfrBulge {gal.sfr_bulge:.2f} of SFR {gal.sfr_bulge + gal.sfr_disk:.2f}\n"
            f"bar {'yes' if rc0.bar_len > 0 else 'no'}, ring r = {rc0.ring_r * rc0.unit_kpc:.1f} kpc",
            color="w",
            fontsize=8,
        )
        print(
            "ring row",
            r,
            i,
            f"ring={rc0.ring:.2f}",
            f"bar={rc0.bar_len:.1f}",
            flush=True,
        )
    fig.suptitle(
        "Nuclear-ring style options (SfrBulge > 0.05 and > 8% of SFR; zoomed on the centre, i = 30°)",
        color="w",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "options_ring.png", dpi=110, facecolor="black")
    plt.close(fig)
    print("wrote", OUT / "options_ring.png", flush=True)


if __name__ == "__main__":
    g = load("millennium")
    agn_figure(g)
    ring_figure(g)
