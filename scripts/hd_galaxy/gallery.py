"""Gallery: every kind of galaxy SAGE26 produces, as ViSAGE's HD mode draws
it, gas on, each framed +-10 kpc.

Each panel is a real galaxy from the Millennium SAGE26 output, picked from
the catalogue by its properties (and, for arm class / bar / ring / clumps,
by the same recipe the viewer builds from them), then rendered through the
viewer itself (scripts/hd_galaxy/variants.py: Viewer), so its group,
neighbours and tidal context are drawn as in the app.

    python scripts/hd_galaxy/gallery.py          # -> gallery_gas/
"""

from __future__ import annotations

import gc
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parents[1])]

from grid import columns  # noqa: E402
from variants import Viewer, _median_pick  # noqa: E402
from viewer_grid import load, to_galaxy  # noqa: E402

from visage.hd.model import recipe_from_sage  # noqa: E402

H = 0.73
HALF_KPC = 10.0
OUT = HERE / "gallery_gas"


def _lm(g):
    return np.log10(np.maximum(g["StellarMass"], 1))


def _sf_disks(g):
    ms = np.maximum(g["StellarMass"], 1)
    ssfr = (g["SfrDisk"] + g["SfrBulge"]) / ms
    return (
        (g["Type"] == 0)
        & (ssfr > 10**-10.6)
        & (g["BulgeMass"] / ms < 0.3)
        & (_lm(g) > 10.2)
        & (_lm(g) < 10.9)
    )


def _recipes(g, mask, n=1200, seed=0):
    idx = np.flatnonzero(mask)
    if len(idx) > n:
        idx = np.random.default_rng(seed).choice(idx, n, replace=False)
    return [(int(k), recipe_from_sage(to_galaxy(g, int(k)))) for k in idx]


def picks_z0(g):
    """(label, row, note) for each type at z = 0."""
    out = []
    cols = columns(g)
    pos = np.column_stack([g["Posx"], g["Posy"], g["Posz"]])
    cidx = {int(x): i for i, x in enumerate(g["GalaxyIndex"])}

    disks = _recipes(g, _sf_disks(g))

    def by_recipe(test, key=None):
        hits = [(k, rc) for k, rc in disks if test(rc)]
        if not hits:
            return None
        if key is None:
            sfr = np.array([g["SfrDisk"][k] for k, _ in hits])
            return hits[int(np.argsort(sfr)[len(sfr) // 2])][0]
        return max(hits, key=lambda h: key(h[1]))[0]

    plain = lambda rc: rc.bar_len < 0.3 and rc.ring == 0  # noqa: E731
    for cls, label in (
        ("grand", "Grand-design spiral"),
        ("multi", "Multi-arm spiral"),
        ("partial", "Partial-arm spiral"),
        ("flocculent", "Flocculent spiral"),
    ):
        k = by_recipe(lambda rc, c=cls: rc.arm_class == c and plain(rc))
        out.append((label, k, f"arm class: {cls}"))
    out.append(
        (
            "Barred spiral",
            by_recipe(lambda rc: rc.bar_len > 0.5, key=lambda rc: rc.l_bar),
            "instability bulge -> bar",
        )
    )
    out.append(
        (
            "Nuclear ring",
            by_recipe(lambda rc: rc.ring > 0, key=lambda rc: rc.ring),
            "bar-driven ring",
        )
    )
    out.append(
        (
            "Pseudo-bulge disk",
            by_recipe(lambda rc: rc.l_pseudo > 0, key=lambda rc: rc.l_pseudo),
            "instability (pseudo) bulge",
        )
    )
    for key, label in (
        ("Bulgy spiral\n(merger bulge)", "Bulgy spiral (classical bulge)"),
        ("Star-forming disk\nhot regime", "Star-forming disk, hot halo"),
        ("Green valley /\nfading disk", "Green valley / fading disk"),
        ("Quenched disk /\nlenticular", "Lenticular / quenched disk"),
    ):
        m = cols[key] & (g["Type"] == 0) & (_lm(g) > 10.2) & (_lm(g) < 11.0)
        out.append((label, _median_pick(g, m), ""))

    # Ellipticals: the one with the most merger debris.
    ell = _recipes(g, cols["Elliptical"] & (g["Type"] == 0) & (_lm(g) > 10.8))
    k, _ = max(ell, key=lambda h: h[1].shells + h[1].tails + h[1].stream)
    out.append(("Elliptical with merger debris", k, "shells and tails"))

    # The cluster's brightest galaxy.
    cen = g["Type"] == 0
    k = int(np.flatnonzero(cen)[np.argmax(g["Mvir"][cen])])
    out.append(
        (
            "Brightest cluster galaxy",
            k,
            "ICL, intracluster gas",
        )
    )
    # Cooling core with H-alpha filaments.
    rcool = g["RcoolToRvir"] * g["Rvir"]
    net = np.where(
        rcool > 0, (rcool - g["r_heat"]) / np.maximum(rcool, 1e-9), -9
    )
    core = (
        cen
        & (g["Regime"] == 1)
        & (g["mdot_cool"] > 0)
        & (g["r_heat"] > 0)
        & (net > 0.5)
        & (g["Mvir"] > 1e12)
    )
    if core.any():
        k = int(np.flatnonzero(core)[np.argmax(g["mdot_cool"][core])])
        out.append(("Cooling core: Hα filaments", k, "cooling beyond r_heat"))
    # Radio AGN in a group (not the cluster's BCG).
    grp = cen & (g["Mvir"] > 1e13) & (g["Mvir"] < 1e14)
    k = int(np.flatnonzero(grp)[np.argmax(g["Heating"][grp])])
    out.append(("Radio AGN: jets, cavities", k, "strongest radio heating"))
    # Starburst winds.
    sfd = cen & (g["BulgeMass"] / np.maximum(g["StellarMass"], 1) < 0.3)
    k = int(np.flatnonzero(sfd)[np.argmax(g["OutflowRate"][sfd])])
    out.append(
        ("Starburst winds", k, f"outflow {g['OutflowRate'][k]:.0f} M☉/yr")
    )
    # Cold streams into a hot halo.
    m = cen & (g["Regime"] == 1) & (g["mdot_stream"] > 0) & (_lm(g) > 10.0)
    idx = np.flatnonzero(m)
    k = int(idx[np.argsort(g["mdot_stream"][idx])[len(idx) // 2]])
    out.append(("Cold streams in a hot halo", k, "mdot_stream"))

    # Satellites: jellyfish (ram pressure) and tidally stripped.
    from visage.hd.group import ram_pressure

    vel = np.column_stack([g["Velx"], g["Vely"], g["Velz"]])
    best, best_s = None, 0.0
    for i in np.flatnonzero(
        (g["Type"] > 0) & (g["ColdGas"] > 3e8) & (g["StellarMass"] > 3e9)
    ):
        c = cidx.get(int(g["CentralGalaxyIndex"][i]))
        if c is None or g["Regime"][c] != 1:
            continue
        # Bright enough beside its central to be seen (one exposure for
        # the whole group: brightness ~ M*^0.35).
        if g["StellarMass"][i] < 0.2 * g["StellarMass"][c]:
            continue
        d = pos[i] - pos[c]
        d -= 62.5 * np.round(d / 62.5)
        st = ram_pressure(
            to_galaxy(g, i),
            to_galaxy(g, c),
            np.linalg.norm(d) * 1000 / H,
            float(np.linalg.norm(vel[i] - vel[c])),
        )
        if st > best_s:
            best, best_s = int(i), st
    out.append(("Jellyfish satellite", best, "ram-pressure tail"))
    host_ms = np.array(
        [
            g["StellarMass"][cidx.get(int(c), 0)]
            for c in g["CentralGalaxyIndex"]
        ]
    )
    sat = (
        (g["Type"] > 0)
        & (g["StellarMass"] > 3e9)
        & (g["infallMvir"] > 0)
        & (g["StellarMass"] > 0.2 * host_ms)
    )
    f_dm = np.where(sat, g["Mvir"] / np.maximum(g["infallMvir"], 1), 9)
    k = int(np.argmin(f_dm))
    out.append(
        (
            "Stripped satellite",
            k,
            f"subhalo {f_dm[k]:.2f} of infall mass",
        )
    )
    # A close pair (tidal bridge and tails).
    big = np.flatnonzero(g["StellarMass"] > 3e9)
    from scipy.spatial import cKDTree

    t = cKDTree(np.mod(pos[big], 62.5), boxsize=62.5)
    d, j = t.query(np.mod(pos[big], 62.5), k=2)
    a = int(np.argmin(d[:, 1]))
    k1, k2 = int(big[a]), int(big[j[a, 1]])
    k = k1 if g["StellarMass"][k1] >= g["StellarMass"][k2] else k2
    out.append(
        (
            "Close interacting pair",
            k,
            f"{d[a, 1] * 1000 / H:.0f} kpc apart",
        )
    )
    # Dwarf irregular.
    ms = np.maximum(g["StellarMass"], 1)
    dw = cen & (_lm(g) > 8.6) & (_lm(g) < 9.2) & ((g["SfrDisk"] / ms) > 1e-10)
    out.append(("Star-forming dwarf", _median_pick(g, dw), ""))
    return [(lbl, k, note) for lbl, k, note in out if k is not None]


def picks_highz():
    out = []
    g = load("millennium", 62)
    mm = np.flatnonzero((g["mergeType"] == 2) & (g["StellarMass"] > 1e9))
    if len(mm):
        k = int(mm[np.argmax(g["StellarMass"][mm])])
        out.append((62, g, "Major merger (next snapshot)", k, "mergeType 2"))
    g = load("millennium", 32)
    disks = _recipes(g, _sf_disks(g), n=400)
    hits = [k for k, rc in disks if rc.arm_class == "clumpy"]
    if hits:
        k = _median_pick(g, np.isin(np.arange(len(g["Type"])), hits))
        out.append((32, g, "Clumpy high-z disk", k, ""))
    g = load("millennium", 18)
    idx = np.flatnonzero((g["FFBRegime"] > 0) & (g["StellarMass"] > 0))
    if len(idx):
        k = int(idx[np.argmax(g["StellarMass"][idx])])
        out.append((18, g, "Feedback-free starburst", k, "FFB regime"))
    return out


def render(v, galaxies, gid, inc=55.0):
    """The galaxy as the viewer's HD draws it (gas on), seen `inc` degrees
    from its spin axis, the view +-HALF_KPC across."""
    from viewer_shots import capture

    from visage.hd.group import HDGroupLayer

    st, ctrl = v.state, v.ctrl
    i = int(np.flatnonzero(galaxies.galaxy_id == gid)[0])
    st.hd_gas = True
    st.nav_gal_idx = i
    st.flush()
    st.sel_kind = "galaxy"
    st.flush()
    ctrl.toggle_hd()
    st.flush()
    cam = v.scene.plotter.camera
    fp = np.array(cam.focal_point)
    grp = next(
        o for o in gc.get_objects() if isinstance(o, HDGroupLayer) and o.active
    )
    m = grp.member_at(fp)
    if m is not None:
        e2, e3 = m._R[:, 1], m._R[:, 2]
        t = np.deg2rad(inc)
        view = np.cos(t) * e3 - np.sin(t) * e2
        cam.up = tuple(e3)
    else:
        view = np.subtract(cam.position, fp)
        view /= np.linalg.norm(view)
    # Group members are drawn magnified to their normal-view size: frame
    # +-HALF_KPC at the scale the galaxy is drawn (its true 10 kpc).
    mag = 1.0
    if m is not None and m.gal is not None:
        mag = m.recipe.unit_kpc / recipe_from_sage(m.gal).unit_kpc
    dist = HALF_KPC * mag * H / 1000.0 / np.tan(np.deg2rad(cam.view_angle) / 2)
    cam.position = tuple(fp + view * dist)
    v.scene.plotter.renderer.ResetCameraClippingRange()
    v.scene.camera.marker.clear()
    img = capture(v.scene)
    ctrl.toggle_hd()
    st.flush()
    return img, mag


def sheet(panels, title, path, ncol):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    nrow = int(np.ceil(len(panels) / ncol))
    fig, axes = plt.subplots(
        nrow,
        ncol,
        figsize=(3.0 * ncol, 3.35 * nrow + 0.5),
        facecolor="black",
        squeeze=False,
    )
    fig.subplots_adjust(
        left=0.005,
        right=0.995,
        bottom=0.035,
        top=1 - 0.5 / (3.35 * nrow + 0.5),
        wspace=0.03,
        hspace=0.22,
    )
    for ax in axes.flat:
        ax.axis("off")
    for ax, (img, t, sub) in zip(axes.flat, panels, strict=False):
        ax.imshow(img)
        ax.set_title(t, color="white", fontsize=10.5, pad=3)
        ax.text(
            0.5,
            -0.02,
            sub,
            transform=ax.transAxes,
            ha="center",
            va="top",
            color="#b0b0b0",
            fontsize=7.5,
            linespacing=1.3,
        )
    fig.suptitle(title, color="white", fontsize=13, y=0.998)
    fig.savefig(path, dpi=150, facecolor="black")
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    v = Viewer(npix=700)
    panels = []
    g = load("millennium")
    galaxies = v.snapshot(63)
    for label, k, note in picks_z0(g):
        img, mag = render(v, galaxies, int(g["GalaxyIndex"][k]))
        sub = f"z = 0 · log M* {_lm(g)[k]:.1f}"
        sub += f" · drawn ×{mag:.1f}" if mag > 1.05 else ""
        sub += f"\n{note}" if note else ""
        panels.append((img, label, sub))
        print(label, flush=True)
    for snap, gs, label, k, note in picks_highz():
        galaxies = v.snapshot(snap)
        img, mag = render(v, galaxies, int(gs["GalaxyIndex"][k]))
        sub = f"z = {gs['redshift']:.1f} · log M* {_lm(gs)[k]:.1f}"
        sub += f" · drawn ×{mag:.1f}" if mag > 1.05 else ""
        sub += f"\n{note}" if note else ""
        panels.append((img, label, sub))
        print(label, flush=True)
    sheet(
        panels,
        "Galaxies SAGE26 produces, as ViSAGE HD draws them (gas on) -- "
        "Millennium, each ±10 kpc of the galaxy",
        OUT / "gallery_gas.png",
        6,
    )
    print("wrote", OUT / "gallery_gas.png")


if __name__ == "__main__":
    main()
