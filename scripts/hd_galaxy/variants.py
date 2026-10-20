"""The SAGE26-driven HD variants, rendered as the viewer renders them.

    python3 scripts/hd_galaxy/variants.py [--out DIR]

Three sheets in DIR (default outputs_v6):

* variants_redshift.png -- a star-forming disk of similar mass from z=0 to
  z=3 (same physical frame: they shrink, thicken and turn clumpy), and a
  feedback-free starburst at z~6;
* variants_structure.png -- classical vs pseudo-bulge, a buckled (peanut)
  bar edge-on, thin vs thick disks (halo sigma/Vmax), metal-poor vs
  metal-rich HII regions;
* variants_environment.png -- through the viewer's own HD path (group,
  neighbours, tidal context): the strongest jellyfish, the most stripped
  satellite, a major merger the snapshot before it, a cooling cluster core
  (H-alpha filaments, X-ray cavities), a central with ICL streams.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from run_prototype import load, to_galaxy  # noqa: E402
from viewer_grid import Shooter  # noqa: E402

NPIX = 480
H = 0.73


def _axis(ax, img, title, sub=""):
    ax.imshow(img)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title(title, color="white", fontsize=9, pad=3)
    if sub:
        ax.text(
            0.03,
            0.03,
            sub,
            color="#9ca3af",
            fontsize=6.5,
            transform=ax.transAxes,
        )


def _sheet(panels, title, path, ncol):
    nrow = int(np.ceil(len(panels) / ncol))
    fig, axes = plt.subplots(
        nrow,
        ncol,
        figsize=(3.1 * ncol, 3.25 * nrow + 0.6),
        facecolor="black",
        squeeze=False,
        gridspec_kw={"wspace": 0.03, "hspace": 0.16},
    )
    for ax in axes.flat:
        ax.axis("off")
    for ax, (img, t, sub) in zip(axes.flat, panels, strict=False):
        ax.axis("on")
        _axis(ax, img, t, sub)
    fig.suptitle(title, color="white", fontsize=12, y=0.995)
    fig.savefig(path, dpi=110, facecolor="black", bbox_inches="tight")
    plt.close(fig)
    print("wrote", path, flush=True)


def shot(sh, gal, inc=55.0, half_kpc=None, gas=False):
    """One galaxy, HD-framed (or a fixed +-half_kpc frame), `inc` degrees
    from its spin axis."""
    import viewer_grid

    viewer_grid.INC = inc
    prep = sh.lay.prepare(gal)
    sh.show(gal, gas=gas, prep=prep)
    if half_kpc is not None:
        lay, cam = sh.lay, sh.pl.camera
        r = half_kpc * H / 1000.0
        dist = r / np.tan(np.deg2rad(cam.view_angle) / 2.0)
        e2, e3 = lay._R[:, 1], lay._R[:, 2]
        i = np.deg2rad(inc)
        view = np.cos(i) * e3 - np.sin(i) * e2
        cam.focal_point = (0.0, 0.0, 0.0)
        cam.position = tuple(view * dist)
        cam.up = tuple(e3)
        sh.pl.renderer.ResetCameraClippingRange()
        sh.pl.render()
        sh.pl.render()
        img = sh.pl.screenshot(return_img=True)[..., :3]
    else:
        img = sh.shot()
    sh.lay.clear()
    viewer_grid.INC = 55.0
    return img, prep["rc"]


def _median_pick(g, mask):
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return None
    sfr = g["SfrDisk"] + g["SfrBulge"]
    return int(idx[np.argsort(sfr[idx])[len(idx) // 2]])


# ----------------------------------------------------------------------


def redshift_sheet(out: Path):
    sh = Shooter(NPIX)
    panels, close = [], []
    for snap in (63, 48, 41, 32, 27):
        g = load("millennium", snap)
        lms = np.log10(np.maximum(g["StellarMass"], 1))
        bt = g["BulgeMass"] / np.maximum(g["StellarMass"], 1)
        k = _median_pick(
            g, (g["Type"] == 0) & (lms > 10.2) & (lms < 10.7) & (bt < 0.3)
        )
        if k is None:
            continue
        gal = to_galaxy(g, k)
        img, rc = shot(sh, gal, inc=40.0, half_kpc=25.0)
        sub = f"log M* {np.log10(gal.stellar_mass):.1f} · {rc.arm_class}"
        panels.append((img, f"z = {g['redshift']:.1f}", sub))
        img, _ = shot(sh, gal, inc=40.0)
        close.append((img, f"z = {g['redshift']:.1f}, framed on it", sub))
    g = load("millennium", 18)
    idx = np.flatnonzero((g["FFBRegime"] > 0) & (g["StellarMass"] > 0))
    if len(idx):
        k = int(idx[np.argmax(g["StellarMass"][idx])])
        gal = to_galaxy(g, k)
        img, rc = shot(sh, gal, inc=40.0, half_kpc=25.0)
        sub = f"log M* {np.log10(gal.stellar_mass):.1f} · {rc.clumps} clumps"
        panels.append(
            (img, f"Feedback-free starburst, z = {g['redshift']:.1f}", sub)
        )
        img, _ = shot(sh, gal, inc=40.0)
        close.append((img, "FFB, framed on it", sub))
    _sheet(
        panels + close,
        "Redshift: a star-forming disk of similar mass -- top, same ±25 kpc "
        "frame (smaller at high z); bottom, framed on each (thicker, clumpy)",
        out / "variants_redshift.png",
        3,
    )


def structure_sheet(out: Path):
    sh = Shooter(NPIX)
    g = load("millennium")
    lms = np.log10(np.maximum(g["StellarMass"], 1))
    ms = np.maximum(g["StellarMass"], 1)
    cen = g["Type"] == 0
    disk = (g["BulgeMass"] / ms) < 0.6
    panels = []
    # Classical vs pseudo-bulge (face-on-ish, zoomed).
    mb, ib = g["MergerBulgeMass"] / ms, g["InstabilityBulgeMass"] / ms
    for label, mask in (
        (
            "Classical bulge (merger-built)",
            cen & disk & (mb > 0.2) & (ib < 0.03) & (lms > 10.5),
        ),
        (
            "Pseudo-bulge (instability-built)",
            cen
            & disk
            & (ib > 0.05)
            & (ib < 0.06)
            & (mb < 0.02)
            & (lms > 10.3),
        ),
    ):
        k = _median_pick(g, mask)
        if k is not None:
            img, rc = shot(sh, to_galaxy(g, k), inc=60.0)
            panels.append((img, label, f"B/T {g['BulgeMass'][k] / ms[k]:.2f}"))
    # Peanut bar, edge-on.
    k = _median_pick(g, cen & disk & (ib > 0.12) & (lms > 10.5))
    if k is not None:
        img, rc = shot(sh, to_galaxy(g, k), inc=89.0)
        panels.append(
            (img, "Buckled (peanut) bar, edge-on", "instability bulge")
        )
    # Thin vs thick (halo sigma / Vmax), edge-on.
    sv = g["VelDisp"] / np.maximum(g["Vmax"], 1)
    base = (
        cen
        & disk
        & (lms > 10.2)
        & (lms < 10.6)
        & ((g["BulgeMass"] / ms) < 0.15)
    )
    for label, sel in (
        ("Thin disk (low σ/Vmax)", sv < np.percentile(sv[base], 10)),
        ("Thick disk (high σ/Vmax)", sv > np.percentile(sv[base], 90)),
    ):
        k = _median_pick(g, base & sel)
        if k is not None:
            img, rc = shot(sh, to_galaxy(g, k), inc=88.0)
            panels.append((img, label, f"σ/Vmax {sv[k]:.2f}"))
    # HII colour by star-forming gas metallicity.
    z = g["SfrDiskZ"] / 0.02
    sf = cen & disk & ((g["SfrDisk"]) > 0.5) & (g["H2gas"] > 1e9)
    for label, sel in (
        ("Metal-poor HII regions", z < np.percentile(z[sf], 10)),
        ("Metal-rich HII regions", z > np.percentile(z[sf], 90)),
    ):
        k = _median_pick(g, sf & sel)
        if k is not None:
            img, rc = shot(sh, to_galaxy(g, k), inc=20.0)
            panels.append((img, label, f"Z(SF gas) {z[k]:.2f} Z☉"))
    _sheet(
        panels,
        "Structure and colour from SAGE26",
        out / "variants_structure.png",
        4,
    )


# -- the viewer's own HD path (group, neighbours, tidal context) --------


class Viewer:
    def __init__(self, npix=NPIX):
        from trame.app import get_server
        from trame.ui.vuetify3 import SinglePageLayout

        from visage.scene.scene import Scene
        from visage.ui.navigation_panel import build_navigation_panel
        from visage.ui.selection import build_selection, selection_card

        self.scene = Scene(
            str(Path.home() / "Documents/PhD/SAGE26/input/millennium.par"),
            off_screen=True,
        )
        server = get_server("variants", client_type="vue3")
        server.controller.view_update = lambda *a, **k: None
        with SinglePageLayout(server) as layout:
            with layout.content:
                selection_card(server)
                build_navigation_panel(server, self.scene)
                build_selection(server, self.scene)
        self.state, self.ctrl = server.state, server.controller
        self.state.ready()
        self.scene.plotter.ren_win.SetSize(npix, npix)

    def snapshot(self, snap):
        self.scene.set_snapshot(snap)
        self.state.snap_num = snap
        self.state.flush()
        return self.scene.active_model.loader.get(snap)[1]

    def hd(self, gid, galaxies, zoom=1.0, halo=False, gas=True, pair=None):
        from viewer_shots import capture

        i = int(np.flatnonzero(galaxies.galaxy_id == gid)[0])
        st, ctrl = self.state, self.ctrl
        st.hd_gas = gas
        st.nav_gal_idx = i
        st.flush()
        st.sel_kind = "halo" if halo else "galaxy"
        st.flush()
        ctrl.toggle_hd()
        st.flush()
        cam = self.scene.plotter.camera
        fp, ps = np.array(cam.focal_point), np.array(cam.position)
        if pair is not None:
            # Frame both galaxies of a pair: their midpoint, their
            # separation filling the view.
            off = self.scene.active_model.offset
            j = int(np.flatnonzero(galaxies.galaxy_id == pair)[0])
            a = galaxies.positions[i] + off
            d = galaxies.positions[j] - galaxies.positions[i]
            d -= self.scene.active_model.box_size * np.round(
                d / self.scene.active_model.box_size
            )
            mid = a + 0.5 * d
            view = (ps - fp) / np.linalg.norm(ps - fp)
            dist = (
                0.8
                * np.linalg.norm(d)
                / np.tan(np.deg2rad(cam.view_angle) / 2)
            )
            cam.focal_point = tuple(mid)
            ps, fp = mid + view * dist, mid
        cam.position = tuple(fp + (ps - fp) * zoom)
        self.scene.plotter.renderer.ResetCameraClippingRange()
        self.scene.camera.marker.clear()
        img = capture(self.scene)
        ctrl.toggle_hd()
        st.flush()
        return img


def _ctx_shot(sh, gal, ctx, half_kpc, inc=55.0, gas=False):
    """One galaxy at full quality with its group context (`ctx`, as
    HDGalaxyLayer.prepare takes it), framed +-half_kpc."""
    import viewer_grid
    from visage.hd.layer import HDGalaxyLayer

    viewer_grid.INC = inc
    prep = HDGalaxyLayer.prepare(gal, "full", ctx)
    sh.lay.show(gal, [0.0, 0.0, 0.0], ctx.get("spin"), H, gas=gas, prep=prep)
    lay, cam = sh.lay, sh.pl.camera
    r = half_kpc * H / 1000.0
    dist = r / np.tan(np.deg2rad(cam.view_angle) / 2.0)
    e2, e3 = lay._R[:, 1], lay._R[:, 2]
    i = np.deg2rad(inc)
    view = np.cos(i) * e3 - np.sin(i) * e2
    cam.focal_point = (0.0, 0.0, 0.0)
    cam.position = tuple(view * dist)
    cam.up = tuple(e3)
    sh.pl.renderer.ResetCameraClippingRange()
    sh.pl.render()
    sh.pl.render()
    img = sh.pl.screenshot(return_img=True)[..., :3]
    sh.lay.clear()
    viewer_grid.INC = 55.0
    return img


def _spin(g, i):
    v = np.array([g["Spinx"][i], g["Spiny"][i], g["Spinz"][i]], float)
    n = np.linalg.norm(v)
    return v / n if n > 0 else None


def environment_sheet(out: Path):
    from visage.hd.group import ram_pressure

    sh = Shooter(NPIX)
    iso, situ = [], []
    g = load("millennium")
    gid = g["GalaxyIndex"]
    cidx = {int(x): i for i, x in enumerate(gid)}
    pos = np.column_stack([g["Posx"], g["Posy"], g["Posz"]])
    vel = np.column_stack([g["Velx"], g["Vely"], g["Velz"]])

    def rel(i, c):
        d = pos[i] - pos[c]
        d -= 62.5 * np.round(d / 62.5)
        return d, vel[i] - vel[c]

    # Jellyfish: the strongest ram pressure on a gas-rich satellite.
    best, best_s, best_c = None, 0.0, None
    for i in np.flatnonzero(
        (g["Type"] > 0) & (g["ColdGas"] > 3e8) & (g["StellarMass"] > 3e9)
    ):
        c = cidx.get(int(g["CentralGalaxyIndex"][i]))
        if c is None or g["Regime"][c] != 1:
            continue
        d, dv = rel(i, c)
        st = ram_pressure(
            to_galaxy(g, i),
            to_galaxy(g, c),
            np.linalg.norm(d) * 1000 / H,
            float(np.linalg.norm(dv)),
        )
        if st > best_s:
            best, best_s, best_c = i, st, c
    if best is not None:
        d, dv = rel(best, best_c)
        ctx = {
            "spin": _spin(g, best),
            "hubble_h": H,
            "ram": (-dv / np.linalg.norm(dv), best_s),
        }
        gal = to_galaxy(g, best)
        iso.append(
            (
                _ctx_shot(sh, gal, ctx, 70.0, inc=50.0),
                "Jellyfish (ram pressure)",
                f"satellite in a hot halo · {np.linalg.norm(dv):.0f} km/s · strength {best_s:.2f}",
            )
        )
    # Most stripped satellite.
    sat = (g["Type"] > 0) & (g["StellarMass"] > 3e9) & (g["infallMvir"] > 0)
    f_dm = np.where(sat, g["Mvir"] / np.maximum(g["infallMvir"], 1), 9)
    k = int(np.argmin(f_dm))
    c = cidx.get(int(g["CentralGalaxyIndex"][k]), k)
    d, dv = rel(k, c)
    vd = dv / max(np.linalg.norm(dv), 1e-9)
    ctx = {
        "spin": _spin(g, k),
        "hubble_h": H,
        "strip": (vd, float(np.clip((0.35 - f_dm[k]) / 0.3, 0.2, 1.0))),
    }
    iso.append(
        (
            _ctx_shot(sh, to_galaxy(g, k), ctx, 60.0, inc=50.0),
            "Tidally stripped satellite",
            f"subhalo {f_dm[k]:.2f} of infall · {g['t_since_infall'][k]:.1f} Gyr since infall",
        )
    )
    # Cooling core: H-alpha filaments, then the X-ray cavities.
    rcool = g["RcoolToRvir"] * g["Rvir"]
    net = np.where(
        rcool > 0, (rcool - g["r_heat"]) / np.maximum(rcool, 1e-9), -9
    )
    # (SAGE heats every cluster-mass core past its cooling radius, so the
    # still-cooling hot haloes are ~1e12 Msun ones.)
    core = (
        (g["Type"] == 0)
        & (g["Regime"] == 1)
        & (g["mdot_cool"] > 0)
        & (g["r_heat"] > 0)
        & (net > 0.5)
        & (g["Mvir"] > 1e12)
    )
    if core.any():
        k = int(np.flatnonzero(core)[np.argmax(g["mdot_cool"][core])])
        gal = to_galaxy(g, k)
        ctx = {"spin": _spin(g, k), "hubble_h": H}
        iso.append(
            (
                _ctx_shot(sh, gal, ctx, 60.0),
                "Still-cooling hot halo: H-alpha filaments",
                f"cooling radius beyond r_heat ({net[k]:.2f})",
            )
        )
        iso.append(
            (
                _ctx_shot(sh, gal, ctx, 2.5 * gal.r_heat_kpc, gas=True),
                "Radio jets and X-ray cavities",
                f"cavities at r_heat = {gal.r_heat_kpc:.0f} kpc",
            )
        )
    # ICL streams.
    k = int(np.argmax(np.where(g["Type"] == 0, g["ICS_disrupt"], 0)))
    gal = to_galaxy(g, k)
    iso.append(
        (
            _ctx_shot(sh, gal, {"spin": _spin(g, k), "hubble_h": H}, 160.0),
            "Streams feeding the ICL",
            f"in-situ ICS {g['ICS_disrupt'][k]:.1e} M☉",
        )
    )
    # Ejected gas reach: the biggest ejected fraction among star-forming disks.
    halo = g["HotGas"] + g["CGMgas"] + g["EjectedMass"]
    fe = np.where(halo > 0, g["EjectedMass"] / np.maximum(halo, 1), 0)
    sfd = (
        (g["Type"] == 0)
        & (g["OutflowRate"] > 1)
        & ((g["BulgeMass"] / np.maximum(g["StellarMass"], 1)) < 0.3)
    )
    if sfd.any():
        k = int(np.flatnonzero(sfd)[np.argmax(fe[sfd])])
        gal = to_galaxy(g, k)
        iso.append(
            (
                _ctx_shot(
                    sh,
                    gal,
                    {"spin": _spin(g, k), "hubble_h": H},
                    120.0,
                    inc=85.0,
                    gas=True,
                ),
                "Winds reaching out (ejected gas)",
                f"ejected {fe[k]:.2f} of halo gas",
            )
        )
    _sheet(
        iso,
        "Environment from SAGE26 -- each galaxy on its own (full quality, its own SAGE values)",
        out / "variants_environment.png",
        3,
    )

    # The same, in place: the viewer's HD path (group, neighbours, tides).
    v = Viewer()
    galaxies = v.snapshot(63)
    if best is not None:
        situ.append(
            (
                v.hd(int(gid[best]), galaxies, zoom=1.5, gas=False),
                "Jellyfish, in its cluster",
                "",
            )
        )
    g62 = load("millennium", 62)
    mm = np.flatnonzero((g62["mergeType"] == 2) & (g62["StellarMass"] > 1e9))
    if len(mm):
        k = int(mm[np.argmax(g62["StellarMass"][mm])])
        p62 = np.column_stack([g62["Posx"], g62["Posy"], g62["Posz"]])
        dd = p62 - p62[k]
        dd -= 62.5 * np.round(dd / 62.5)
        dist = np.linalg.norm(dd, axis=1)
        heavier = np.flatnonzero(
            (g62["StellarMass"] >= g62["StellarMass"][k])
            & (np.arange(len(dist)) != k)
        )
        j = int(heavier[np.argmin(dist[heavier])])
        galaxies = v.snapshot(62)
        situ.append(
            (
                v.hd(
                    int(g62["GalaxyIndex"][k]),
                    galaxies,
                    zoom=1.0,
                    gas=False,
                    pair=int(g62["GalaxyIndex"][j]),
                ),
                "Major merger, a snapshot before it",
                f"z = {g62['redshift']:.2f} · {dist[j] * 1000 / H:.0f} kpc apart",
            )
        )
    _sheet(
        situ,
        "The same, in the viewer's HD (group, neighbours, tidal context)",
        out / "variants_environment_in_viewer.png",
        2,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "which",
        nargs="?",
        default="all",
        choices=["all", "redshift", "structure", "environment"],
    )
    ap.add_argument("--out", default=str(HERE / "outputs_v6"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.which in ("all", "redshift"):
        redshift_sheet(out)
    if a.which in ("all", "structure"):
        structure_sheet(out)
    if a.which in ("all", "environment"):
        environment_sheet(out)


if __name__ == "__main__":
    main()
