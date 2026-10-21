"""What the viewer's HD button renders: a type x mass grid and a component
breakdown, drawn by the real GPU renderer (`visage.hd.layer.HDGalaxyLayer`).

    python3 scripts/hd_galaxy/viewer_grid.py [grid|components|both] [--out DIR]

Every image is framed exactly as pressing HD frames it: 55 degrees from
the spin axis, the optical galaxy filling the view, or the whole halo
(+-Rvir) when the Gas box is ticked.  Exposure is per galaxy, as in the
viewer (one galaxy on screen at a time).
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from grid import MASS_BINS, columns  # noqa: E402
from run_prototype import load, to_galaxy  # noqa: E402

NPIX = 520
INC = 55.0
H = 0.73


class Shooter:
    """One off-screen plotter + HD layer, used as the viewer uses it."""

    def __init__(self, npix=NPIX):
        import pyvista as pv

        from visage.hd.layer import HDGalaxyLayer

        self.pl = pv.Plotter(off_screen=True, window_size=[npix, npix])
        self.pl.set_background("black")
        self.lay = HDGalaxyLayer(self.pl)

    def show(self, gal, gas=False, prep=None):
        self.lay.show(
            gal, [0.0, 0.0, 0.0], [0.0, 0.0, 1.0], H, gas=gas, prep=prep
        )

    def frame(self, rvir=False):
        """The HD button's framing (navigation_panel._hd_show)."""
        lay, cam = self.lay, self.pl.camera
        radius = lay.rvir_world if rvir else lay.radius_world
        dist = radius / np.tan(np.deg2rad(cam.view_angle) / 2.0) * 1.15
        e2, e3 = lay._R[:, 1], lay._R[:, 2]
        i = np.deg2rad(INC)
        view = np.cos(i) * e3 - np.sin(i) * e2
        cam.focal_point = (0.0, 0.0, 0.0)
        cam.position = tuple(view * dist)
        cam.up = tuple(e3)
        self.pl.renderer.ResetCameraClippingRange()

    def shot(self, rvir=False):
        self.frame(rvir)
        self.pl.render()
        self.pl.render()
        return self.pl.screenshot(return_img=True)[..., :3]


def _axis(ax, img, title=None, size=7):
    ax.imshow(img)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    if title:
        ax.set_title(title, color="white", fontsize=size, pad=3)


# ----------------------------------------------------------------------
# Grid
# ----------------------------------------------------------------------


def grid(out: Path):
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
    sh = Shooter()
    nr, nc = len(MASS_BINS), len(cnames)
    fig, axes = plt.subplots(
        nr,
        2 * nc,
        figsize=(2.0 * 2 * nc, 2.1 * nr + 1.0),
        facecolor="black",
        gridspec_kw={"wspace": 0.02, "hspace": 0.12},
    )
    t0 = time.time()
    for j, cname in enumerate(cnames):
        for i, (lo, hi) in enumerate(MASS_BINS):
            a_opt, a_gas = axes[i, 2 * j], axes[i, 2 * j + 1]
            for sim in sims:
                g, cm, lms, sfr, cen = sim
                idx = np.flatnonzero(
                    cm[cname] & cen & (lms >= lo) & (lms < hi)
                )
                if len(idx):
                    break
            if len(idx) == 0:
                for a in (a_opt, a_gas):
                    _axis(a, np.zeros((NPIX, NPIX, 3), np.uint8))
                continue
            k = int(idx[np.argsort(sfr[idx])[len(idx) // 2]])
            gal = to_galaxy(g, k)
            prep = sh.lay.prepare(gal)
            sh.show(gal, prep=prep)
            opt = sh.shot()
            sh.lay.set_gas(True)
            gas = sh.shot(rvir=True)
            sh.lay.clear()
            src = "Mill." if g["sim"] == "millennium" else "μUchuu"
            r_kpc = sh_radius_kpc(prep)
            _axis(a_opt, opt, f"{prep['rc'].kind}  ±{r_kpc:.0f} kpc", 6)
            _axis(
                a_gas, gas, f"+gas  ±{1.05 * gal.rvir_kpc * 1.15:.0f} kpc", 6
            )
            a_opt.text(
                0.03,
                0.03,
                f"{src} N={len(idx)}",
                color="#9ca3af",
                fontsize=5,
                transform=a_opt.transAxes,
            )
            print(
                f"{cname.splitlines()[0]:22s} {lo}-{hi}: {prep['rc'].kind} "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )
    for j, cname in enumerate(cnames):
        axes[0, 2 * j].annotate(
            cname.replace("\n", " "),
            xy=(1.0, 1.32),
            xycoords="axes fraction",
            ha="center",
            color="white",
            fontsize=9,
            fontweight="bold",
        )
    for i, (lo, hi) in enumerate(MASS_BINS):
        axes[i, 0].set_ylabel(f"log M* {lo}–{hi}", color="white", fontsize=9)
    fig.suptitle(
        "What the HD button renders (GPU, as in the viewer): optical | with "
        "Gas box ticked.  55° from the spin axis; per-galaxy exposure.",
        color="white",
        fontsize=12,
        y=0.995,
    )
    fig.savefig(
        out / "grid_viewer.png",
        dpi=110,
        facecolor="black",
        bbox_inches="tight",
    )
    plt.close(fig)
    print("wrote", out / "grid_viewer.png", flush=True)


def sh_radius_kpc(prep):
    rc = prep["rc"]
    k = 1.3 if rc.kind == "disk" else 1.0
    return rc.extent * k * rc.unit_kpc * 1.15


# ----------------------------------------------------------------------
# Components
# ----------------------------------------------------------------------

# Uniform settings that isolate each component in the shader.
_STARS_OFF = {"uPtsGain": 0.0, "uHasAtlas": 0.0}
_CORE_OFF = {"uBulgeRGB": (0.0, 0.0, 0.0), "uLNuc": 0.0, "uAgn": 0.0}
_ICL_OFF = {"uLIcl": 0.0, "uIclOpacity": 0.0}
_DISK_OFF = {"uOldRGB": (0.0, 0.0, 0.0), "uYoungRGB": (0.0, 0.0, 0.0)}
COMPONENTS = [
    (
        "Old stars\nStellarMass, MetalsStellarMass",
        {"uYoungRGB": (0.0, 0.0, 0.0), **_CORE_OFF, **_ICL_OFF, **_STARS_OFF},
        True,
    ),
    (
        "Bulge / bar / nucleus / AGN\nBulge masses, BlackHoleMass,\n"
        "QuasarModeBHaccretionMass",
        {**_DISK_OFF, **_ICL_OFF, **_STARS_OFF},
        False,
    ),
    (
        "Young stars, clusters, HII\nSfrDisk (+ SfrBulge ring), H2gas",
        {
            "uOldRGB": (0.0, 0.0, 0.0),
            **_CORE_OFF,
            **_ICL_OFF,
            "uHasAtlas": 0.0,
        },
        False,
    ),
    (
        "Optical, dust removed\n(dust: H2gas, H1gas, MetalsColdGas)",
        {"uDustK": (0.0, 0.0, 0.0)},
        True,
    ),
    (
        "Debris, ICL, cooling filaments\nTime of last mergers, ICS_disrupt,\nmdot_cool vs r_heat",
        {**_DISK_OFF, **_CORE_OFF, "uPtsGain": 0.0},
        True,
    ),
    ("Optical composite", {}, True),
]


def _apply(u, settings):
    for k, v in settings.items():
        if isinstance(v, tuple):
            u.SetUniform3f(k, list(v))
        else:
            u.SetUniformf(k, float(v))


def _pick(g, cname, lo, hi):
    lms = np.log10(np.maximum(g["StellarMass"], 1))
    sfr = g["SfrDisk"] + g["SfrBulge"]
    idx = np.flatnonzero(
        columns(g)[cname] & (g["Type"] == 0) & (lms >= lo) & (lms < hi)
    )
    return int(idx[np.argsort(sfr[idx])[len(idx) // 2]])


def _pick_streams(g):
    lms = np.log10(np.maximum(g["StellarMass"], 1))
    idx = np.flatnonzero(
        (g["Type"] == 0) & (g["mdot_stream"] > 0) & (lms > 10.0)
    )
    return int(idx[np.argsort(g["mdot_stream"][idx])[len(idx) // 2]])


def components(out: Path):
    g = load("millennium")
    rows = [
        (
            "Cold regime (CGM):\nstar-forming disk",
            _pick(g, "Star-forming disk\ncold regime", 10.5, 11.0),
        ),
        (
            "Hot regime:\nstar-forming disk",
            _pick(g, "Star-forming disk\nhot regime", 11.0, 11.5),
        ),
        ("Hot regime:\nelliptical", _pick(g, "Elliptical", 11.5, 12.5)),
        ("Hot regime with\ncold streams", _pick_streams(g)),
    ]
    gas_cols = [
        "Halo gas\nCGMgas or HotGas, Cooling,\nRcoolToRvir, mdot_stream",
        "Wind + radio jets\nOutflowRate, MassLoading, Heating",
        "Optical + all gas",
        "Whole halo (±Rvir)\noptical + all gas (Gas box)",
    ]
    titles = [c[0] for c in COMPONENTS] + gas_cols
    sh = Shooter()
    fig, axes = plt.subplots(
        len(rows),
        len(titles),
        figsize=(2.3 * len(titles), 2.55 * len(rows) + 1.3),
        facecolor="black",
        gridspec_kw={"wspace": 0.03, "hspace": 0.1},
    )
    for r, (label, i) in enumerate(rows):
        gal = to_galaxy(g, i)
        prep = sh.lay.prepare(gal)
        imgs = []
        sh.show(gal, prep=prep)
        u = sh.lay._gpu._uni
        spr = getattr(sh.lay._gpu, "sprinkle_actor", None)
        for _, settings, sprinkle in COMPONENTS:
            sh.show(gal, prep=prep)  # fresh uniforms
            u = sh.lay._gpu._uni
            _apply(u, settings)
            spr = getattr(sh.lay._gpu, "sprinkle_actor", None)
            if spr is not None:
                spr.SetVisibility(bool(sprinkle))
            imgs.append(sh.shot())
        dark = {**_DISK_OFF, **_CORE_OFF, **_ICL_OFF, **_STARS_OFF}
        for variant in (
            dataclasses.replace(gal, outflow_rate=0.0, heating_log=0.0),
            dataclasses.replace(gal, hot_gas=0.0, cgm_gas=0.0),
        ):
            p2 = dict(prep, gal=variant)
            sh.show(variant, gas=True, prep=p2)
            _apply(sh.lay._gpu._uni, dark)
            spr = getattr(sh.lay._gpu, "sprinkle_actor", None)
            if spr is not None:
                spr.SetVisibility(False)
            imgs.append(sh.shot())
        sh.show(gal, gas=True, prep=prep)
        imgs.append(sh.shot())
        imgs.append(sh.shot(rvir=True))
        sh.lay.clear()
        for c, img in enumerate(imgs):
            _axis(axes[r, c], img, titles[c] if r == 0 else None, 7)
        axes[r, 0].set_ylabel(
            f"{label}\nlog M*={np.log10(gal.stellar_mass):.2f}",
            color="white",
            fontsize=8,
        )
        print("row", r, flush=True)
    fig.suptitle(
        "HD components as the viewer renders them (GPU).  55° from the spin "
        "axis, HD framing; last column = Gas box framing (±Rvir).",
        color="white",
        fontsize=12,
        y=0.995,
    )
    fig.savefig(
        out / "components_viewer.png",
        dpi=110,
        facecolor="black",
        bbox_inches="tight",
    )
    plt.close(fig)
    print("wrote", out / "components_viewer.png", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "what",
        nargs="?",
        default="both",
        choices=["grid", "components", "both"],
    )
    ap.add_argument("--out", default=str(HERE / "outputs_v5"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.what in ("components", "both"):
        components(out)
    if args.what in ("grid", "both"):
        grid(out)


if __name__ == "__main__":
    main()
