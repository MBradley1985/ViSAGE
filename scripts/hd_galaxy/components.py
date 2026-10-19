"""Component breakdown for cold-regime (CGM) and hot-regime galaxies.

    python3 scripts/hd_galaxy/components.py [--out outputs_v4]

Each row is one real SAGE26 central split into the layers the HD render is
built from, with the SAGE property that drives each one.  Stars at i = 60°
in a ±35 kpc frame; the last panel is the whole halo out to Rvir.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from grid import columns  # noqa: E402
from model import build_disk_maps, build_points, recipe_from_sage  # noqa: E402
from render import gas_halo, render, screen, tonemap  # noqa: E402
from run_prototype import OUT, load, to_galaxy  # noqa: E402

NPIX = 512
INC, PA = 60, 25
FRAME_KPC = 35.0


def pick(g, cname, lo, hi):
    lms = np.log10(np.maximum(g["StellarMass"], 1))
    sfr = g["SfrDisk"] + g["SfrBulge"]
    idx = np.flatnonzero(
        columns(g)[cname] & (g["Type"] == 0) & (lms >= lo) & (lms < hi)
    )
    return int(idx[np.argsort(sfr[idx])[len(idx) // 2]])


def pick_streams(g):
    """A hot-regime central that still has cold streams, near the median."""
    lms = np.log10(np.maximum(g["StellarMass"], 1))
    idx = np.flatnonzero(
        (g["Type"] == 0) & (g["mdot_stream"] > 0) & (lms > 10.0)
    )
    return int(idx[np.argsort(g["mdot_stream"][idx])[len(idx) // 2]])


def layer(lay, *names):
    out = np.zeros_like(lay.disk)
    for n in names:
        if n == "disk":
            out += lay.disk
        elif n == "bulge":
            out += lay.bulge
        elif n == "young":
            out += lay.young
        elif n in lay.points:
            out += lay.points[n]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument(
        "--no-cavity",
        action="store_true",
        help="hot gas right up to the galaxy (no cavity around it)",
    )
    args = ap.parse_args()
    out_dir = Path(args.out) if args.out else OUT
    out_dir.mkdir(parents=True, exist_ok=True)

    g = load("millennium")
    rows = [
        (
            "Cold regime (CGM): star-forming disk",
            pick(g, "Star-forming disk\ncold regime", 10.5, 11.0),
        ),
        (
            "Hot regime: star-forming disk",
            pick(g, "Star-forming disk\nhot regime", 11.0, 11.5),
        ),
        ("Hot regime: elliptical", pick(g, "Elliptical", 11.5, 12.5)),
        ("Hot regime with cold streams\n(mdot_stream > 0)", pick_streams(g)),
    ]
    cols = [
        "Old stars\nStellarMass, MetalsStellarMass",
        "Bulge / bar / nucleus / AGN\nBulge masses, BlackHoleMass,\nQuasarModeBHaccretionMass",
        "Young stars + clusters\nSfrDisk (+ SfrBulge ring)",
        "HII regions\nH2gas",
        "Dust optical depth\nH2gas, H1gas, MetalsColdGas",
        "Merger debris + ICL\nTimeOfLastMajor/MinorMerger,\nIntraClusterStars",
        "Optical composite",
        "Halo gas\nCGMgas  or  HotGas (opacity), Cooling,\nRcoolToRvir, mdot_stream",
        "Wind + radio jets\nOutflowRate, MassLoading,\nHeating",
        "Optical + all gas",
        "Whole halo (±Rvir)\noptical + all gas",
    ]
    fig, axes = plt.subplots(
        len(rows),
        len(cols),
        figsize=(2.6 * len(cols), 3.0 * len(rows) + 1.2),
        facecolor="black",
        gridspec_kw={"wspace": 0.03, "hspace": 0.08},
    )
    for r, (label, i) in enumerate(rows):
        gal = to_galaxy(g, i)
        rc = recipe_from_sage(gal)
        maps = build_disk_maps(rc) if rc.kind == "disk" else None
        pts = build_points(rc, maps)
        e0 = rc.extent * (1.3 if rc.kind == "disk" else 1.0)
        lay = render(
            rc,
            maps,
            pts,
            inc=INC,
            pa=PA,
            npix=NPIX,
            frame_scale=FRAME_KPC / (e0 * rc.unit_kpc),
        )
        no_agn = lay.total - lay.points.get("agn", 0)
        white = np.percentile(no_agn.mean(2), 99.9)

        def tm(x, white=white):
            return tonemap(x, white=white)[0]

        optical = tm(lay.total)
        halo_only = gas_halo(
            dataclasses.replace(gal, outflow_rate=0.0, heating_log=0.0),
            rc,
            NPIX,
            lay.half_width,
            inc=INC,
            pa=PA,
            hot_cavity=not args.no_cavity,
        )
        outflows = gas_halo(
            dataclasses.replace(gal, hot_gas=0.0, cgm_gas=0.0),
            rc,
            NPIX,
            lay.half_width,
            inc=INC,
            pa=PA,
            hot_cavity=not args.no_cavity,
        )
        all_gas = gas_halo(
            gal,
            rc,
            NPIX,
            lay.half_width,
            inc=INC,
            pa=PA,
            hot_cavity=not args.no_cavity,
        )

        # Whole halo at ±1.05 Rvir, hot gas on a log stretch.
        lay_r = render(
            rc,
            maps,
            pts,
            inc=INC,
            pa=PA,
            npix=NPIX,
            frame_scale=1.05 * gal.rvir_kpc / (e0 * rc.unit_kpc),
        )
        whole = screen(
            tonemap(lay_r.total, white=white)[0],
            gas_halo(
                gal,
                rc,
                NPIX,
                lay_r.half_width,
                inc=INC,
                pa=PA,
                log_stretch=True,
                hot_cavity=not args.no_cavity,
            ),
        )

        panels = [
            tm(layer(lay, "disk", "field", "globulars")),
            tm(layer(lay, "bulge", "nucleus", "agn")),
            tm(layer(lay, "young", "clusters", "ring")),
            tm(layer(lay, "hii", "ring_hii")),
            None,  # dust: drawn with its own colour map
            tm(layer(lay, "shells", "tails", "stream", "icl")),
            optical,
            halo_only,
            outflows,
            screen(optical, all_gas),
            whole,
        ]
        for c, im in enumerate(panels):
            ax = axes[r, c]
            ax.set_xticks([]), ax.set_yticks([])
            ax.set_facecolor("black")
            if im is None:
                ax.imshow(
                    lay.tau_v,
                    cmap="magma",
                    vmin=0,
                    vmax=max(np.percentile(lay.tau_v, 99.5), 0.1),
                )
                ax.text(
                    0.03,
                    0.03,
                    f"max τ_V {lay.tau_v.max():.1f}",
                    color="w",
                    fontsize=7,
                    transform=ax.transAxes,
                )
            else:
                ax.imshow(im)
            if r == 0:
                ax.set_title(cols[c], color="w", fontsize=7.5)
        axes[r, 0].set_ylabel(
            f"{label}\nlog M* {np.log10(gal.stellar_mass):.2f}  B/T {gal.bt:.2f}  "
            f"SFR {gal.sfr_disk + gal.sfr_bulge:.2g}\n"
            f"log HotGas {np.log10(max(gal.hot_gas, 1)):.1f}  log CGM {np.log10(max(gal.cgm_gas, 1)):.1f}\n"
            f"Rvir {gal.rvir_kpc:.0f} kpc",
            color="w",
            fontsize=7.5,
        )
        print(label, "->", "; ".join(rc.notes), flush=True)
    fig.suptitle(
        "HD isolate components — cold (CGM) vs hot regime "
        f"(i = {INC}°, ±{FRAME_KPC:.0f} kpc; last column ±Rvir)"
        + ("  —  no hot-gas cavity" if args.no_cavity else ""),
        color="w",
        fontsize=13,
    )
    fig.subplots_adjust(left=0.05, right=0.995, top=0.86, bottom=0.01)
    out = out_dir / (
        "components_cgm_vs_hot"
        + ("_nocavity" if args.no_cavity else "")
        + ".png"
    )
    fig.savefig(out, dpi=115, facecolor="black")
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
