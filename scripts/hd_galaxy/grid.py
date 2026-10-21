"""Grid of SAGE26 galaxy types x stellar mass, rendered as HD previews.

    python3 scripts/hd_galaxy/grid.py [--inc 55] [--npix 640] [--frame 35]

Each cell is a real z=0 central from the Millennium SAGE26 run, the galaxy
closest to the median SFR of everything that matches the cell's cuts.  Cells
Millennium can't fill fall back to the (larger) microUchuu run.

Every cell shares one physical frame (+-`--frame` kpc) and one white point,
so size and brightness both follow mass.  Writes grid_i<inc>.png (optical)
and grid_i<inc>_gas.png (with the CGM / hot-gas overlay).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from model import (
    OLD_LIGHT,
    build_disk_maps,
    build_points,
    recipe_from_sage,
)  # noqa: E402
from render import gas_halo, icl_zone, render, screen, tonemap  # noqa: E402
from run_prototype import OUT, load, to_galaxy  # noqa: E402

MASS_BINS = [
    (9.5, 10.0),
    (10.0, 10.5),
    (10.5, 11.0),
    (11.0, 11.5),
    (11.5, 12.5),
]
# Rendered light scales as (M / M_REF)^LUM_POWER: brighter with mass, but
# compressed so the dwarfs stay visible and the giants don't blow out into
# a haze.
M_REF = 3e10
LUM_POWER = 0.35


def columns(g):
    ms = np.maximum(g["StellarMass"], 1)
    bt = g["BulgeMass"] / ms
    ib = g["InstabilityBulgeMass"] / ms
    ssfr = (g["SfrDisk"] + g["SfrBulge"]) / ms
    reg = g["Regime"]
    sf = ssfr > 10**-10.6
    q = ssfr < 10**-11.5
    return {
        "Star-forming disk\ncold regime": (reg == 0)
        & sf
        & (bt < 0.3)
        & (ib < 0.06),
        "Star-forming disk\nhot regime": (reg == 1)
        & sf
        & (bt < 0.3)
        & (ib < 0.06),
        "Barred spiral\n(instability bulge)": sf & (ib > 0.1) & (bt < 0.5),
        "Bulgy spiral\n(merger bulge)": (ssfr > 10**-11)
        & (bt > 0.3)
        & (bt < 0.7)
        & (g["MergerBulgeMass"] > g["InstabilityBulgeMass"]),
        "Green valley /\nfading disk": (ssfr > 10**-11.5)
        & (ssfr < 10**-10.8)
        & (bt < 0.5),
        "Quenched disk /\nlenticular": q & (bt < 0.6),
        "Elliptical": (bt > 0.8),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inc", type=float, default=0.0)
    ap.add_argument("--npix", type=int, default=640)
    ap.add_argument(
        "--frame", type=float, default=35.0, help="frame half-width, kpc"
    )
    ap.add_argument(
        "--rvir",
        action="store_true",
        help="frame each cell at +-1.05 Rvir of its own halo",
    )
    ap.add_argument(
        "--paired",
        action="store_true",
        help="one figure, optical | +gas columns per type",
    )
    ap.add_argument(
        "--out", default=None, help="output directory (default: output/)"
    )
    args = ap.parse_args()

    sims = []
    for name in ("millennium", "microuchuu"):
        g = load(name)
        sims.append(
            (
                g,
                columns(g),
                np.log10(np.maximum(g["StellarMass"], 1)),
                g["SfrDisk"] + g["SfrBulge"],
                g["Type"] == 0,
            )
        )
    cnames = list(sims[0][1])

    # Pass 1: render every cell in linear light at a common physical scale.
    cells = {}
    highlights = []
    t0 = time.time()
    for j, cname in enumerate(cnames):
        for i, (lo, hi) in enumerate(MASS_BINS):
            # First simulation that has a galaxy for this cell wins.
            for sim in sims:
                g, cmasks, lms, sfr, cen = sim
                idx = np.flatnonzero(
                    cmasks[cname] & cen & (lms >= lo) & (lms < hi)
                )
                if len(idx):
                    break
            if len(idx) == 0:
                continue
            k = int(idx[np.argsort(sfr[idx])[len(idx) // 2]])
            gal = to_galaxy(g, k)
            rc = recipe_from_sage(gal)
            maps = build_disk_maps(rc, n=1536) if rc.kind == "disk" else None
            pts = build_points(rc, maps)
            e0 = rc.extent * (1.3 if rc.kind == "disk" else 1.0)
            half_kpc = 1.05 * gal.rvir_kpc if args.rvir else args.frame
            scale = half_kpc / (e0 * rc.unit_kpc)
            lay = render(
                rc,
                maps,
                pts,
                inc=args.inc,
                pa=25,
                npix=args.npix,
                frame_scale=scale,
            )
            # Absolute light: disk recipes are in units of the disk mass;
            # elliptical recipes put unit light in M* of old stars.
            if rc.kind == "disk":
                ref_mass = gal.stellar_mass - gal.bulge_mass
            else:
                ref_mass = gal.stellar_mass * OLD_LIGHT
            lum_scale = (ref_mass / M_REF) ** LUM_POWER
            lin = lay.total * lum_scale
            # Highlight level for the shared white point, without the AGN
            # glow (a point source shouldn't set the exposure).
            hl = np.percentile(
                (lay.total - lay.points.get("agn", 0)).mean(2) * lum_scale,
                99.97,
            )
            halo = gas_halo(
                gal,
                rc,
                args.npix,
                lay.half_width,
                inc=args.inc,
                pa=25,
                log_stretch=args.rvir,
            )
            # ICL is starlight, so it goes in both the optical and gas views.
            halo_icl = icl_zone(gal, rc, args.npix, lay.half_width)
            src = "Millennium" if g["sim"] == "millennium" else "microUchuu"
            cells[(i, j)] = (
                gal,
                rc,
                lin,
                (halo, halo_icl),
                len(idx),
                src,
                half_kpc,
            )
            highlights.append(hl)
            print(
                f"{cname.splitlines()[0]:22s} {lo}-{hi}: {src:10s} N={len(idx):5d} "
                f"-> {rc.kind:10s} ({time.time() - t0:.0f}s)",
                flush=True,
            )

    # One white point for the whole grid: the median cell's highlight level.
    # Shared white point from the brighter cells (75th percentile), so the
    # most massive galaxies aren't overexposed.
    white = float(np.percentile(highlights, 75))

    if args.paired:
        draw_paired(cells, cnames, args, white)
    else:
        for with_gas in (False, True):
            draw(cells, cnames, args, white, with_gas)


def _cell(ax, cell, args, white, with_gas):
    """Draw one rendered galaxy (optical, or with the gas overlay)."""
    gal, rc, lin, halo, n, src, half_kpc = cell
    gas, icl = halo
    img = screen(tonemap(lin, white=white)[0], icl)
    if with_gas:
        img = screen(img, gas)
    ax.imshow(img)
    ax.text(
        0.03,
        0.97,
        f"N={n}  {src}",
        fontsize=6.5,
        va="top",
        color="#aaa" if src == "Millennium" else "#ffd27a",
        transform=ax.transAxes,
    )
    if with_gas:
        txt = (
            f"HotGas {np.log10(max(gal.hot_gas, 1)):.1f}  CGM {np.log10(max(gal.cgm_gas, 1)):.1f}\n"
            f"wind {gal.outflow_rate:.2g}  Heating {gal.heating_log:.1f}"
        )
    else:
        txt = (
            f"log M* {np.log10(gal.stellar_mass):.2f}  B/T {gal.bt:.2f}  "
            f"SFR {gal.sfr_disk + gal.sfr_bulge:.2g}\n"
            f"H2 {np.log10(max(gal.h2_gas, 1)):.1f}  BH {np.log10(max(gal.bh_mass, 1)):.1f}"
            f"  {'hot' if gal.regime else 'cold'}"
        )
    ax.text(0.03, 0.03, txt, color="w", fontsize=6, transform=ax.transAxes)
    # Scale bar, bottom right (10 kpc, or 100 kpc in Rvir frames).
    bar_kpc = 100.0 if args.rvir else 10.0
    bar_px = bar_kpc / (2 * half_kpc) * args.npix
    x1, y = args.npix * 0.95, args.npix * 0.93
    ax.plot([x1 - bar_px, x1], [y, y], color="w", lw=1.2)
    ax.text(
        x1 - bar_px / 2,
        y - args.npix * 0.02,
        f"{bar_kpc:.0f} kpc",
        color="w",
        fontsize=6,
        ha="center",
    )
    if args.rvir:
        c = args.npix / 2
        rad = gal.rvir_kpc / (2 * half_kpc) * args.npix
        t = np.linspace(0, 2 * np.pi, 200)
        ax.plot(
            c + rad * np.cos(t),
            c + rad * np.sin(t),
            ls="--",
            lw=0.6,
            color="#888",
        )
        ax.text(
            c + rad * 0.72,
            c - rad * 0.72,
            f"Rvir {gal.rvir_kpc:.0f} kpc",
            color="#aaa",
            fontsize=5.5,
        )
        ax.set_xlim(0, args.npix), ax.set_ylim(args.npix, 0)


def _empty(ax):
    ax.text(
        0.5,
        0.5,
        "none in Millennium\nor microUchuu",
        color="#777",
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=8,
    )


def _style(ax):
    ax.set_xticks([]), ax.set_yticks([])
    ax.set_facecolor("black")
    for s in ax.spines.values():
        s.set_color("#333")


def _title(args, kind):
    framing = (
        "each cell framed at ±1.05 Rvir of its halo, hot gas on a log stretch"
        if args.rvir
        else f"common ±{args.frame:.0f} kpc frame"
    )
    return (
        f"SAGE26 z=0 centrals — HD isolate previews, {kind} "
        f"(i = {args.inc:.0f}°, {framing}, common white point; gold = microUchuu fill-in)"
    )


def _outfile(args, suffix=""):
    out = Path(args.out) if args.out else OUT
    out.mkdir(parents=True, exist_ok=True)
    frame = "rvir" if args.rvir else f"{int(args.frame)}kpc"
    return out / f"grid_{frame}_i{int(args.inc)}{suffix}.png"


def draw(cells, cnames, args, white, with_gas):
    nr, nc = len(MASS_BINS), len(cnames)
    fig, axes = plt.subplots(
        nr, nc, figsize=(2.9 * nc, 3.2 * nr + 0.6), facecolor="black"
    )
    for i, (lo, hi) in enumerate(MASS_BINS):
        for j, cname in enumerate(cnames):
            ax = axes[i, j]
            _style(ax)
            if i == 0:
                ax.set_title(cname, color="w", fontsize=10, pad=8)
            if j == 0:
                ax.set_ylabel(f"log M* {lo}–{hi}", color="w", fontsize=10)
            if (i, j) in cells:
                _cell(ax, cells[(i, j)], args, white, with_gas)
            else:
                _empty(ax)
    kind = "with CGM / hot-gas overlay" if with_gas else "optical"
    fig.suptitle(_title(args, kind), color="w", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    out = _outfile(args, "_gas" if with_gas else "_optical")
    fig.savefig(out, dpi=120, facecolor="black")
    plt.close(fig)
    print("wrote", out, flush=True)


def draw_paired(cells, cnames, args, white):
    """Each type gets two adjacent columns: optical, then with gas."""
    nr, nc = len(MASS_BINS), 2 * len(cnames)
    fig, axes = plt.subplots(
        nr,
        nc,
        figsize=(2.45 * nc, 2.75 * nr + 0.9),
        facecolor="black",
        gridspec_kw={"wspace": 0.03, "hspace": 0.06},
    )
    for i, (lo, hi) in enumerate(MASS_BINS):
        for j, cname in enumerate(cnames):
            for k, with_gas in enumerate((False, True)):
                ax = axes[i, 2 * j + k]
                _style(ax)
                if i == 0:
                    ax.set_title(
                        ("" if k else cname.replace("\n", " ") + "\n")
                        + ("+ gas" if k else "optical"),
                        color="w",
                        fontsize=8.5,
                        loc="left" if not k else "center",
                    )
                if j == 0 and k == 0:
                    ax.set_ylabel(f"log M* {lo}–{hi}", color="w", fontsize=10)
                if (i, j) in cells:
                    _cell(ax, cells[(i, j)], args, white, with_gas)
                else:
                    _empty(ax)
    fig.suptitle(
        _title(args, "optical | + gas pairs"), color="w", fontsize=13, y=0.995
    )
    fig.subplots_adjust(left=0.02, right=0.995, top=0.93, bottom=0.01)
    out = _outfile(args)
    fig.savefig(out, dpi=110, facecolor="black")
    plt.close(fig)
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
