"""Pick representative SAGE galaxies and render HD previews + diagnostics.

    python3 scripts/hd_galaxy/run_prototype.py [--quick]

Figures land in scripts/hd_galaxy/output/.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import h5py
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from model import (
    SageGalaxy,
    build_disk_maps,
    build_points,  # noqa: E402
    recipe_from_sage,
)
from render import render, tonemap  # noqa: E402

SAGE26_OUT = Path.home() / "Documents/PhD/SAGE26/output"
SIMS = {"millennium": 63, "microuchuu": 49}  # sim -> z=0 snapshot
OUT = HERE / "output"
OUT.mkdir(exist_ok=True)
QUICK = "--quick" in sys.argv
NPIX = 512 if QUICK else 1024

FIELDS = [
    "StellarMass",
    "BulgeMass",
    "MergerBulgeMass",
    "InstabilityBulgeMass",
    "ColdGas",
    "H2gas",
    "H1gas",
    "MetalsColdGas",
    "BlackHoleMass",
    "SfrDisk",
    "SfrBulge",
    "DiskRadius",
    "BulgeRadius",
    "Regime",
    "Type",
    "GalaxyIndex",
    "HotGas",
    "CGMgas",
    "Rvir",
    "MetalsStellarMass",
    "TimeOfLastMajorMerger",
    "TimeOfLastMinorMerger",
    "QuasarModeBHaccretionMass",
    "IntraClusterStars",
    "OutflowRate",
    "MassLoading",
    "mdot_stream",
    "Cooling",
    "RcoolToRvir",
    "Concentration",
    "Heating",
]
# Optional (newer SAGE26 outputs); missing ones read as zero.
OPTIONAL = [
    "Posx",
    "Posy",
    "Posz",
    "Velx",
    "Vely",
    "Velz",
    "Vmax",
    "VelDisp",
    "Mvir",
    "infallMvir",
    "infallStellarMass",
    "TimeOfInfall",
    "mergeType",
    "MergerBulgeRadius",
    "InstabilityBulgeRadius",
    "MetalsBulgeMass",
    "MetalsHotGas",
    "MetalsCGMgas",
    "MetalsIntraClusterStars",
    "SfrDiskZ",
    "EjectedMass",
    "ICS_disrupt",
    "ICS_accrete",
    "r_heat",
    "tcool",
    "tff",
    "mdot_cool",
    "FFBRegime",
    "CentralGalaxyIndex",
    "Spinx",
    "Spiny",
    "Spinz",
]


def load(sim="millennium", snap=None):
    """One snapshot (default z=0) of a SAGE26 run, every model_N.hdf5 file
    stacked."""
    snap = SIMS[sim] if snap is None else int(snap)
    files = sorted((SAGE26_OUT / sim).glob("model_[0-9]*.hdf5"))
    parts = {k: [] for k in FIELDS + OPTIONAL}
    for p in files:
        with h5py.File(p, "r") as f:
            h = float(f["Header/Simulation"].attrs["hubble_h"])
            om = float(f["Header/Simulation"].attrs["omega_matter"])
            zs = np.asarray(f["Header/snapshot_redshifts"][:], float)
            grp = f[f"Snap_{snap}"]
            z = float(grp.attrs.get("redshift", zs[snap]))
            n = len(grp["StellarMass"])
            for k in FIELDS + OPTIONAL:
                parts[k].append(grp[k][:] if k in grp else np.zeros(n))
    g = {k: np.concatenate(v) for k, v in parts.items()}
    g["redshift"], g["snap"], g["hubble_h"] = z, snap, h
    # Time since infall (TimeOfInfall is the snapshot it became a satellite).
    from visage.hd.adapter import cosmic_time_gyr

    t_now = cosmic_time_gyr(1 / (1 + z), h, om)
    s_in = g["TimeOfInfall"].astype(int)
    a_in = 1 / (1 + zs[np.clip(s_in, 0, len(zs) - 1)])
    g["t_since_infall"] = np.where(
        (g["Type"] > 0) & (s_in > 0) & (s_in <= snap),
        t_now - np.array([cosmic_time_gyr(a, h, om) for a in a_in]),
        -1.0,
    )
    for k in [
        "StellarMass",
        "BulgeMass",
        "MergerBulgeMass",
        "InstabilityBulgeMass",
        "ColdGas",
        "H2gas",
        "H1gas",
        "MetalsColdGas",
        "BlackHoleMass",
        "HotGas",
        "CGMgas",
        "MetalsStellarMass",
        "QuasarModeBHaccretionMass",
        "IntraClusterStars",
        "Mvir",
        "infallMvir",
        "infallStellarMass",
        "MetalsBulgeMass",
        "MetalsHotGas",
        "MetalsCGMgas",
        "MetalsIntraClusterStars",
        "EjectedMass",
        "ICS_disrupt",
        "ICS_accrete",
    ]:
        g[k] = g[k].astype(np.float64) * 1e10 / h
    for k in [
        "DiskRadius",
        "BulgeRadius",
        "Rvir",
        "MergerBulgeRadius",
        "InstabilityBulgeRadius",
        "r_heat",
    ]:
        g[k] = g[k].astype(np.float64) * 1e3 / h  # kpc
    g["sim"] = sim
    return g


def to_galaxy(g, i) -> SageGalaxy:
    return SageGalaxy(
        galaxy_index=int(g["GalaxyIndex"][i]),
        stellar_mass=g["StellarMass"][i],
        bulge_mass=g["BulgeMass"][i],
        merger_bulge_mass=g["MergerBulgeMass"][i],
        instability_bulge_mass=g["InstabilityBulgeMass"][i],
        cold_gas=g["ColdGas"][i],
        h2_gas=g["H2gas"][i],
        h1_gas=g["H1gas"][i],
        metals_cold_gas=g["MetalsColdGas"][i],
        bh_mass=g["BlackHoleMass"][i],
        sfr_disk=float(g["SfrDisk"][i]),
        sfr_bulge=float(g["SfrBulge"][i]),
        disk_radius_kpc=g["DiskRadius"][i],
        bulge_radius_kpc=g["BulgeRadius"][i],
        regime=int(g["Regime"][i]),
        gtype=int(g["Type"][i]),
        hot_gas=g["HotGas"][i],
        cgm_gas=g["CGMgas"][i],
        rvir_kpc=g["Rvir"][i],
        metals_stellar_mass=g["MetalsStellarMass"][i],
        t_major_myr=float(g["TimeOfLastMajorMerger"][i]),
        t_minor_myr=float(g["TimeOfLastMinorMerger"][i]),
        qso_accretion=g["QuasarModeBHaccretionMass"][i],
        ics=g["IntraClusterStars"][i],
        outflow_rate=float(g["OutflowRate"][i]),
        mass_loading=float(g["MassLoading"][i]),
        mdot_stream=float(g["mdot_stream"][i]),
        cooling_log=float(g["Cooling"][i]),
        rcool_to_rvir=float(g["RcoolToRvir"][i]),
        concentration=float(g["Concentration"][i]),
        heating_log=float(g["Heating"][i]),
        redshift=float(g["redshift"]),
        ffb=int(g["FFBRegime"][i]),
        vel=(float(g["Velx"][i]), float(g["Vely"][i]), float(g["Velz"][i])),
        vmax=float(g["Vmax"][i]),
        vel_disp=float(g["VelDisp"][i]),
        mvir=float(g["Mvir"][i]),
        infall_mvir=float(g["infallMvir"][i]),
        infall_stellar_mass=float(g["infallStellarMass"][i]),
        t_since_infall_gyr=float(g["t_since_infall"][i]),
        merge_type=int(g["mergeType"][i]),
        merger_bulge_radius_kpc=float(g["MergerBulgeRadius"][i]),
        instability_bulge_radius_kpc=float(g["InstabilityBulgeRadius"][i]),
        metals_bulge=float(g["MetalsBulgeMass"][i]),
        metals_hot=float(g["MetalsHotGas"][i]),
        metals_cgm=float(g["MetalsCGMgas"][i]),
        metals_ics=float(g["MetalsIntraClusterStars"][i]),
        sfr_disk_z=float(g["SfrDiskZ"][i]),
        ejected=float(g["EjectedMass"][i]),
        ics_disrupt=float(g["ICS_disrupt"][i]),
        ics_accrete=float(g["ICS_accrete"][i]),
        r_heat_kpc=float(g["r_heat"][i]),
        tcool_gyr=float(g["tcool"][i]),
        tff_gyr=float(g["tff"][i]),
        mdot_cool=float(g["mdot_cool"][i]),
    )


def pick(g):
    """A handful of centrals spanning the population."""
    ms, bt = g["StellarMass"], g["BulgeMass"] / np.maximum(g["StellarMass"], 1)
    sfr = g["SfrDisk"] + g["SfrBulge"]
    ib = g["InstabilityBulgeMass"] / np.maximum(g["StellarMass"], 1)
    cen = g["Type"] == 0
    rng = np.random.default_rng(3)

    def one(mask, key=None):
        idx = np.flatnonzero(mask & cen)
        if key is not None:
            return int(idx[np.argsort(key[idx])[len(idx) // 2]])
        return int(rng.choice(idx))

    lms = np.log10(np.maximum(ms, 1))
    lh2 = np.log10(np.maximum(g["H2gas"], 1))
    return {
        "Star-forming disk (cold regime)": one(
            (g["Regime"] == 0)
            & (lms > 10.4)
            & (lms < 10.8)
            & (bt < 0.15)
            & (ib < 0.04)
            & (lh2 > 9.3),
            sfr,
        ),
        "Barred spiral": one(
            (lms > 10.5)
            & (lms < 11.0)
            & (ib > 0.12)
            & (bt < 0.4)
            & (lh2 > 9.0),
            sfr,
        ),
        "Massive disk (hot regime)": one(
            (g["Regime"] == 1) & (lms > 10.9) & (bt < 0.3) & (lh2 > 9.3), sfr
        ),
        "Gas-rich low-mass disk": one(
            (lms > 9.6) & (lms < 10.0) & (bt < 0.05) & (lh2 > 8.8), sfr
        ),
        "Elliptical (hot regime)": one(
            (g["Regime"] == 1) & (lms > 11.2) & (bt > 0.85), ms
        ),
    }


def build(gal):
    rc = recipe_from_sage(gal)
    maps = (
        build_disk_maps(rc, n=1024 if QUICK else 2048)
        if rc.kind == "disk"
        else None
    )
    pts = build_points(rc, maps)
    return rc, maps, pts


def label(gal: SageGalaxy):
    return (
        f"log M*={np.log10(gal.stellar_mass):.2f}  B/T={gal.bt:.2f}  "
        f"SFR={gal.sfr_disk + gal.sfr_bulge:.2f}\n"
        f"log H2={np.log10(max(gal.h2_gas, 1)):.2f}  log HI={np.log10(max(gal.h1_gas, 1)):.2f}  "
        f"log M_BH={np.log10(max(gal.bh_mass, 1)):.2f}  "
        f"{'hot' if gal.regime else 'cold'}"
    )


def save_rgb(img, path):
    plt.imsave(path, np.clip(img, 0, 1))


def main():
    g = load()
    chosen = pick(g)
    for name, i in chosen.items():
        print(f"{name:34s} idx={i}")

    views = (
        [(0, 20, True), (0, 20, False), (58, 30, True)]
        if not QUICK
        else [(0, 20, True), (0, 20, False)]
    )
    results = {}
    for name, i in chosen.items():
        gal = to_galaxy(g, i)
        rc, maps, pts = build(gal)
        print(f"\n== {name}  ({rc.kind})")
        for n in rc.notes:
            print("   ", n)
        imgs = []
        white = None
        for inc, pa, dust in views:
            t = time.time()
            lay = render(
                rc, maps, pts, inc=inc, pa=pa, npix=NPIX, dust_on=dust
            )
            # Share the white point between dust on/off so they compare.
            img, w = tonemap(lay.total, white=white if inc == 0 else None)
            if inc == 0 and white is None:
                white = w
            tag = f"i{inc}" + ("" if dust else "_nodust")
            print(f"    {tag}: {time.time() - t:.1f}s")
            slug = (
                name.split(" (")[0].lower().replace(" ", "_").replace("-", "")
            )
            save_rgb(img, OUT / f"{slug}_{tag}.png")
            imgs.append(
                (f"i = {inc}°" + ("" if dust else ", no dust"), img, lay)
            )
        results[name] = (gal, rc, maps, pts, imgs)

    np.save(OUT / "_chosen.npy", np.array(list(chosen.values())))
    gallery(results)
    anatomy(*results["Barred spiral"][:4], "barred_spiral")
    anatomy(*results["Elliptical (hot regime)"][:4], "elliptical")


def gallery(results):
    names = list(results)
    nv = len(next(iter(results.values()))[4])
    fig, axes = plt.subplots(
        nv,
        len(names),
        figsize=(4.2 * len(names), 4.6 * nv),
        facecolor="black",
        squeeze=False,
    )
    for j, name in enumerate(names):
        gal, rc, *_, imgs = results[name]
        for r, (inc, img, _) in enumerate(imgs):
            ax = axes[r, j]
            ax.imshow(img)
            ax.set_xticks([]), ax.set_yticks([])
            if r == 0:
                ax.set_title(f"{name}\n{label(gal)}", color="w", fontsize=8.5)
            ax.text(
                0.02, 0.02, inc, color="w", fontsize=8, transform=ax.transAxes
            )
    fig.tight_layout()
    fig.savefig(OUT / "gallery.png", dpi=130, facecolor="black")
    plt.close(fig)


def anatomy(gal, rc, maps, pts, slug):
    """One galaxy decomposed: what each SAGE quantity contributes."""
    lay = render(rc, maps, pts, inc=0, pa=20, npix=NPIX)
    final, white = tonemap(lay.total)
    off = render(rc, maps, pts, inc=0, pa=20, npix=NPIX, dust_on=False)
    nodust, _ = tonemap(off.total, white=white)

    def tm(x):
        return tonemap(x, white=white, bloom=0)[0]

    panels = [
        (
            "Old disk stars\n(StellarMass - BulgeMass, DiskRadius)",
            tm(lay.disk),
        ),
        (
            "Bulge + bar + nucleus\n(Merger/InstabilityBulge, BlackHoleMass)",
            tm(lay.bulge + lay.points.get("nucleus", 0 * lay.bulge)),
        ),
        (
            "Young stars + clusters\n(SfrDisk)",
            tm(lay.young + lay.points.get("clusters", 0 * lay.young)),
        ),
        (
            "HII regions\n(H2gas x SFR)",
            tm(lay.points.get("hii", 0 * lay.young)),
        ),
    ]
    if rc.kind == "elliptical":
        panels = [
            (
                "Inner core (BulgeMass)",
                tm(lay.bulge + lay.points.get("nucleus", 0)),
            ),
            ("Envelope", tm(lay.disk)),
            ("Globular clusters", tm(lay.points["globulars"])),
            ("Field giants", tm(lay.points["field"])),
        ]
    fig, axes = plt.subplots(2, 4, figsize=(17, 9), facecolor="black")
    for ax, (t, im) in zip(axes[0], panels, strict=True):
        ax.imshow(im)
        ax.set_title(t, color="w", fontsize=9)
    ax = axes[1, 0]
    ax.imshow(
        lay.tau_v,
        cmap="magma",
        vmin=0,
        vmax=np.percentile(lay.tau_v, 99.5) + 1e-6,
    )
    ax.set_title(
        "Dust optical depth τ_V\n(H2gas + 0.35 H1gas) x Z_cold",
        color="w",
        fontsize=9,
    )
    if maps is not None:
        e = maps.half
        axes[1, 1].imshow(
            np.log10(maps.h2 + 1e-4),
            cmap="viridis",
            extent=[-e, e, -e, e],
            vmin=-2.5,
        )
        axes[1, 1].set_title(
            "H2 surface density (galaxy plane, log)", color="w", fontsize=9
        )
        axes[1, 1].set_xlim(-rc.extent, rc.extent), axes[1, 1].set_ylim(
            -rc.extent, rc.extent
        )
    else:
        axes[1, 1].axis("off")
    axes[1, 2].imshow(nodust)
    axes[1, 2].set_title("Composite without dust", color="w", fontsize=9)
    axes[1, 3].imshow(final)
    axes[1, 3].set_title("Final composite", color="w", fontsize=9)
    for ax in axes.ravel():
        ax.set_xticks([]), ax.set_yticks([])
    fig.suptitle(
        f"{slug.replace('_', ' ').title()} — {label(gal).replace(chr(10), '   ')}",
        color="w",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(OUT / f"anatomy_{slug}.png", dpi=110, facecolor="black")
    plt.close(fig)


if __name__ == "__main__":
    main()
