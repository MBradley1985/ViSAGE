"""One snapshot, or one redshift slice of a lightcone: SAGE26's
allresults-local plots, with the observations those use."""

from __future__ import annotations

import numpy as np

from visage.plots import obs
from visage.plots.base import F_BARYON, SSFR_CUT, log_edges, plot
from visage.plots.style import GROUPS, observed, plasma

Z_FIELD = "redshift_cosmological"
M_STAR = r"$M_\star\ (M_\odot)$"
M_VIR = r"$M_{\rm vir}\ (M_\odot)$"
M_EDGES = log_edges(8.0, 12.2, 0.1)
HALO_EDGES = log_edges(10.0, 15.0, 0.1)
RESERVOIRS = (
    ("Stars", "StellarMass"),
    ("Cold gas", "ColdGas"),
    ("Hot gas", "HotGas"),
    ("CGM gas", "CGMgas"),
    ("Ejected gas", "EjectedMass"),
    ("Intracluster stars", "IntraClusterStars"),
)
BARYONS = tuple(f for _, f in RESERVOIRS) + ("BlackHoleMass",)


@plot(
    "Mass functions",
    "smf",
    "Stellar mass function, by sSFR",
    ("StellarMass", "SfrDisk", "SfrBulge"),
)
def smf(p):
    fig, ax = p.figure()
    s = p.s
    mass, ssfr = s("StellarMass"), s("sSFR")
    q = ssfr < 10.0**SSFR_CUT
    edges = log_edges(7.0, 13.0, 0.1)
    p.mass_function(ax, mass, edges, "All")
    c = plasma(2, p.o.dark)
    p.mass_function(ax, mass[q], edges, "Quiescent", c[1])
    p.mass_function(ax, mass[~q], edges, "Star forming", c[0])
    gama = obs.table("gama_smf_morph.ecsv", skiprows=15)
    baldry = np.genfromtxt(
        obs.DATA / "baldry_blue_red.csv", delimiter=",", skip_header=2
    )
    if s.volume:
        ok = np.isfinite(gama[:, 7])
        observed(
            ax,
            10 ** gama[ok, 0],
            10 ** gama[ok, 7],
            "GAMA discs",
            dark=p.o.dark,
        )
        ok = np.isfinite(gama[:, 1])
        observed(
            ax,
            10 ** gama[ok, 0],
            10 ** gama[ok, 1],
            "GAMA ellipticals",
            dark=p.o.dark,
        )
        observed(
            ax,
            10 ** baldry[:, 0],
            10 ** baldry[:, 1],
            "Baldry et al. blue",
            dark=p.o.dark,
        )
        observed(
            ax,
            10 ** baldry[:, 2],
            10 ** baldry[:, 3],
            "Baldry et al. red",
            dark=p.o.dark,
        )
    ax.set(xscale="log", xlim=(1e8, 1e12), xlabel=M_STAR)
    p.phi_label(ax)
    ax.set_ylim(1e-6, 1e-1) if s.volume else None
    p.finish()
    return fig


@plot(
    "Mass functions",
    "bmf",
    "Baryonic mass function",
    ("StellarMass", "ColdGas", "Type"),
)
def bmf(p):
    fig, ax = p.figure()
    s, h = p.s, p.s.h
    mass, kind = s("StellarMass") + s("ColdGas"), s("Type")
    edges = log_edges(7.0, 13.0, 0.1)
    c = plasma(2, p.o.dark)
    p.mass_function(ax, mass, edges, "All")
    p.mass_function(ax, mass[kind == 0], edges, "Centrals", c[0])
    p.mass_function(ax, mass[kind == 1], edges, "Satellites", c[1], "--")
    if s.volume:
        m = np.arange(8.0, 12.2, 0.2)
        star = np.log10(5.3e10 / h / h)
        observed(  # diet Salpeter to Chabrier
            ax,
            10**m / 0.7 / 1.8,
            obs.schechter(m, star, -1.21, 0.0108 * h**3),
            "Bell+03",
            dark=p.o.dark,
        )
    ax.set(xscale="log", xlim=(1e8, 10**12.2))
    ax.set_xlabel(r"$M_{\rm bar}\ (M_\odot)$")
    p.phi_label(ax)
    ax.set_ylim(1e-6, 1e-1) if s.volume else None
    p.finish()
    return fig


@plot(
    "Mass functions",
    "gmf",
    "Cold gas mass function",
    ("ColdGas", "H1gas", "H2gas", "Type"),
)
def gmf(p):
    fig, ax = p.figure()
    s, h = p.s, p.s.h
    central = s("Type") == 0
    edges = log_edges(6.0, 12.0, 0.1)
    c = plasma(2, p.o.dark)
    p.mass_function(ax, s("ColdGas")[central], edges, "Cold gas")
    p.mass_function(ax, s("H2gas")[central], edges, r"H$_2$", c[0])
    p.mass_function(ax, s("H1gas")[central], edges, "HI", c[1])
    if s.volume:
        for name, data in (
            ("Obreschkow and Rawlings 09 (cold)", obs.OBRESCHKOW09_COLD),
            ("Zwaan+05 (HI)", obs.ZWAAN05_HI),
            ("Obreschkow and Rawlings 09 (H$_2$)", obs.OBRESCHKOW09_H2),
        ):
            observed(
                ax,
                10 ** data[:, 0] / h**2,
                10 ** data[:, 1] * h**3,
                name,
                dark=p.o.dark,
            )
    ax.set(xscale="log", xlim=(1e8, 10**11.5))
    ax.set_xlabel(r"$M_{\rm X}\ (M_\odot)$")
    p.phi_label(ax)
    ax.set_ylim(1e-6, 1e-1) if s.volume else None
    p.finish()
    return fig


@plot(
    "Scaling relations",
    "btf",
    "Baryonic Tully-Fisher",
    ("StellarMass", "ColdGas", "BulgeMass", "Vmax", "Type"),
)
def btf(p):
    fig, ax = p.figure()
    s = p.s
    mass, bulge = s("StellarMass"), s("BulgeMass")
    with np.errstate(divide="ignore", invalid="ignore"):
        b_t = bulge / mass
    ok = (s("Type") == 0) & (b_t > 0.1) & (b_t < 0.5)
    v = s("Vmax").astype(float)
    p.relation(
        ax,
        v,
        mass + s("ColdGas"),
        log_edges(1.4, 2.9, 0.1),
        ok,
        "Sb/c galaxies",
    )
    vv = np.arange(1.5, 2.9, 0.15)
    observed(
        ax,
        10**vv,
        10 ** (3.94 * vv + 1.79),
        "Stark+09",
        yerr=None,
        dark=p.o.dark,
    )
    ax.set(
        xscale="log",
        yscale="log",
        xlim=(10**1.4, 10**2.9),
        ylim=(10**7.5, 1e12),
    )
    ax.set_xlabel(r"$V_{\rm max}\ ({\rm km\,s}^{-1})$")
    ax.set_ylabel(r"$M_{\rm bar}\ (M_\odot)$")
    p.finish("upper left", "lower right")
    return fig


@plot(
    "Star formation",
    "ssfr",
    "sSFR vs stellar mass",
    ("StellarMass", "SfrDisk", "SfrBulge"),
)
def ssfr(p):
    fig, ax = p.figure()
    s = p.s
    p.relation(ax, s("StellarMass"), s("sSFR"), M_EDGES)
    ax.axhline(10.0**SSFR_CUT, color=p.ink, ls=":", lw=1.5)
    ax.set(
        xscale="log",
        yscale="log",
        xlim=(1e8, 1e12),
        ylim=(1e-16, 1e-8),
        xlabel=M_STAR,
    )
    ax.set_ylabel(r"$s{\rm SFR}\ ({\rm yr}^{-1})$")
    p.finish("lower left")
    return fig


@plot(
    "Star formation",
    "ssfr_density",
    "sSFR vs stellar mass, density contours",
    ("StellarMass", "SfrDisk", "SfrBulge"),
)
def ssfr_density(p):
    from scipy.ndimage import gaussian_filter

    fig, ax = p.figure()
    s = p.s
    mass, rate = s("StellarMass"), s("sSFR")
    ok = (mass > 0) & (rate > 0)
    x, y = np.log10(mass[ok]), np.log10(rate[ok])
    xb, yb = np.linspace(8.0, 12.2, 100), np.linspace(-13, -8, 100)
    xc, yc = 0.5 * (xb[1:] + xb[:-1]), 0.5 * (yb[1:] + yb[:-1])
    c = plasma(2, p.o.dark)
    for label, keep, colour in (
        ("Quiescent", y <= SSFR_CUT, c[1]),
        ("Star forming", y > SSFR_CUT, c[0]),
    ):
        if keep.sum() < 10:
            continue
        hist = np.histogram2d(x[keep], y[keep], bins=[xb, yb])[0].T
        smooth = gaussian_filter(hist, sigma=1.5)
        order = np.sort(smooth.ravel())[::-1]
        order = order[order > 0]
        total = np.cumsum(order) / order.sum()
        lv = [order[np.searchsorted(total, f)] for f in (0.997, 0.95, 0.68)]
        lv = np.unique(lv)
        for lo, alpha in zip(lv, (0.3, 0.5, 0.7), strict=False):
            ax.contourf(
                10**xc,
                10**yc,
                smooth,
                levels=[lo, smooth.max()],
                colors=[colour],
                alpha=alpha,
            )
        ax.plot([], [], color=colour, label=label)
    ax.axhline(
        10.0**SSFR_CUT, color=p.ink, ls="--", lw=1.5, label=r"$s{\rm SFR}$ cut"
    )
    ax.set(
        xscale="log",
        yscale="log",
        xlim=(1e8, 10**12.2),
        ylim=(1e-13, 1e-8),
        xlabel=M_STAR,
    )
    ax.set_ylabel(r"$s{\rm SFR}\ ({\rm yr}^{-1})$")
    p.finish()
    return fig


@plot(
    "Star formation",
    "sfr",
    "SFR vs stellar mass",
    ("StellarMass", "SfrDisk", "SfrBulge"),
)
def sfr(p):
    fig, ax = p.figure()
    s = p.s
    p.relation(ax, s("StellarMass"), s("SFR"), log_edges(6.0, 12.2, 0.1))
    ax.set(
        xscale="log",
        yscale="log",
        xlim=(1e6, 10**12.2),
        ylim=(1e-5, 1e3),
        xlabel=M_STAR,
    )
    ax.set_ylabel(r"${\rm SFR}\ (M_\odot\,{\rm yr}^{-1})$")
    p.finish("upper left")
    return fig


@plot(
    "Gas and baryons",
    "gas_fraction",
    "Gas fraction",
    ("StellarMass", "ColdGas", "BulgeMass"),
)
def gas_fraction(p):
    fig, ax = p.figure()
    s = p.s
    mass, cold, bulge = s("StellarMass"), s("ColdGas"), s("BulgeMass")
    with np.errstate(divide="ignore", invalid="ignore"):
        b_t = bulge / mass
        frac = cold / (mass + cold)
    p.relation(
        ax,
        mass,
        frac,
        M_EDGES,
        (b_t > 0.1) & (b_t < 0.5),
        "Sb/c galaxies",
        log_y=False,
    )
    ax.set(xscale="log", xlim=(1e8, 1e12), ylim=(0, 1), xlabel=M_STAR)
    ax.set_ylabel(r"$M_{\rm cold}\,/\,(M_{\rm cold}+M_\star)$")
    p.finish()
    return fig


@plot(
    "Scaling relations",
    "metallicity",
    "Gas metallicity vs stellar mass",
    ("StellarMass", "ColdGas", "MetalsColdGas", "Type"),
)
def metallicity(p):
    fig, ax = p.figure()
    s = p.s
    mass, cold = s("StellarMass"), s("ColdGas")
    with np.errstate(divide="ignore", invalid="ignore"):
        oh = np.log10(s("MetalsColdGas") / cold / 0.02) + 9.0
        ok = (s("Type") == 0) & (cold / (mass + cold) > 0.1) & (mass > 1e8)
    p.relation(ax, mass, oh, M_EDGES, ok, "Gas-rich centrals", log_y=False)
    d = p.o.dark
    t = obs.table("Tremonti04.dat")
    shift = 10.0**-obs.KROUPA
    observed(
        ax,
        10 ** t[:, 0] * shift,
        t[:, 1],
        "Tremonti+04",
        yerr=[t[:, 1] - t[:, 2], t[:, 3] - t[:, 1]],
        dark=d,
    )
    c = obs.table("Curti2020.dat")
    observed(
        ax,
        10 ** c[:, 0] * shift,
        c[:, 1],
        "Curti+20",
        yerr=[c[:, 1] - c[:, 2], c[:, 3] - c[:, 1]],
        dark=d,
    )
    a = obs.table("MMAdrews13.dat")
    observed(
        ax, 10 ** a[:, 0] * shift, a[:, 1], "Andrews and Martini 13", dark=d
    )
    k = obs.table("MMR-Kewley08.dat")[59:74]
    observed(
        ax, 10 ** k[:, 0] * shift, k[:, 1], "Kewley and Ellison 08", dark=d
    )
    g = obs.table("MSZR-Gallazzi05.dat")[7:]
    observed(
        ax, 10 ** g[:, 0], g[:, 1] + 8.69, "Gallazzi+05 (stellar)", dark=d
    )
    ax.set(xscale="log", xlim=(1e8, 1e12), ylim=(8.0, 9.5), xlabel=M_STAR)
    ax.set_ylabel(r"$12+\log_{10}({\rm O/H})$")
    p.finish("upper left", "lower right")
    return fig


@plot(
    "Scaling relations",
    "bh_bulge",
    "Black hole vs bulge mass",
    ("BulgeMass", "BlackHoleMass"),
)
def bh_bulge(p):
    fig, ax = p.figure()
    s = p.s
    bulge, bh = s("BulgeMass"), s("BlackHoleMass")
    p.relation(
        ax, bulge, bh, log_edges(8.0, 12.0, 0.2), (bulge > 1e8) & (bh > 1e6)
    )
    d = p.o.dark
    w = np.arange(8.0, 12.1, 0.4)
    observed(
        ax,
        10**w,
        10 ** (8.2 + 1.12 * (w - 11.0)),
        'H\\"aring and Rix 04',
        dark=d,
    )
    o = obs.scott13(s.h)
    for label, cut in (
        ("Scott+13 cored", o["core"]),
        ("Scott+13 S\\'ersic", ~o["core"]),
    ):
        observed(
            ax,
            o["sph"][cut],
            o["bh"][cut],
            label,
            xerr=[o["sph_lo"][cut], o["sph_hi"][cut]],
            yerr=[o["bh_lo"][cut], o["bh_hi"][cut]],
            dark=d,
        )
    ax.set(xscale="log", yscale="log", xlim=(1e8, 1e12), ylim=(1e6, 1e10))
    ax.set_xlabel(r"$M_{\rm bulge}\ (M_\odot)$")
    ax.set_ylabel(r"$M_{\rm BH}\ (M_\odot)$")
    p.finish("lower right", "upper left")
    return fig


@plot(
    "Star formation",
    "quiescent",
    "Quiescent fraction",
    ("StellarMass", "SfrDisk", "SfrBulge", "Type", "CentralMvir"),
)
def quiescent(p):
    fig, ax = p.figure()
    s = p.s
    mass, kind = s("StellarMass"), s("Type")
    q = s("sSFR") < 10.0**SSFR_CUT
    halo = s("CentralMvir")
    edges = log_edges(9.5, 12.5, 0.1)
    centres = np.sqrt(edges[1:] * edges[:-1])
    all_n = np.histogram(mass, edges)[0].astype(float)
    sat = kind == 1
    sat_n = np.histogram(mass[sat], edges)[0].astype(float)
    cen_n = np.histogram(mass[kind == 0], edges)[0].astype(float)
    c = plasma(4, p.o.dark)

    def line(pick, total, label, colour, ls="-"):
        n = np.histogram(mass[pick & q], edges)[0]
        with np.errstate(divide="ignore", invalid="ignore"):
            f = n / total
        ok = np.isfinite(f) & (f > 0)
        ax.plot(centres[ok], f[ok], color=colour, ls=ls, label=label)

    line(np.ones(len(mass), bool), all_n, "All", p.ink)
    line(kind == 0, cen_n, "Centrals", c[0])
    line(sat, sat_n, "Satellites", c[2])
    group = 10.0**12.5
    line(sat & (halo < group), sat_n, "Satellites, low-mass halo", c[2], "--")
    line(
        sat & (halo > group), sat_n, "Satellites, group or cluster", c[2], "-."
    )
    ax.set(
        xscale="log",
        xlim=(10**9.5, 10**12.5),
        ylim=(0, 1.05),
        xlabel=M_STAR,
        ylabel="Quiescent fraction",
    )
    p.finish("lower right")
    return fig


@plot(
    "Structure",
    "bulge_fraction",
    "Bulge and disc mass fractions",
    ("StellarMass", "BulgeMass"),
)
def bulge_fraction(p):
    fig, ax = p.figure()
    s = p.s
    mass, bulge = s("StellarMass"), s("BulgeMass")
    with np.errstate(divide="ignore", invalid="ignore"):
        b_t = bulge / mass
    edges = log_edges(8.25, 12.75, 0.5)
    c = plasma(1, p.o.dark)[0]
    p.relation(ax, mass, b_t, edges, label="Bulge", colour=c, log_y=False)
    p.relation(ax, mass, 1 - b_t, edges, label="Disc", log_y=False)
    ax.set(
        xscale="log",
        xlim=(edges[0], edges[-1]),
        ylim=(0, 1.05),
        xlabel=M_STAR,
        ylabel="Stellar mass fraction",
    )
    p.finish()
    return fig


@plot(
    "Structure",
    "bulge_to_total",
    "Bulge-to-total ratio",
    ("StellarMass", "BulgeMass", "MergerBulgeMass", "InstabilityBulgeMass"),
)
def bulge_to_total(p):
    fig, ax = p.figure()
    s = p.s
    mass, bulge = s("StellarMass"), s("BulgeMass")
    edges = log_edges(8.5, 12.5, 0.25)
    ok = (mass > 0) & (bulge > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        b_t = bulge / mass
    p.relation(ax, mass, b_t, edges, ok, "Model median", log_y=False)
    c = plasma(2, p.o.dark)
    centres = np.sqrt(edges[1:] * edges[:-1])
    which = np.digitize(mass, edges) - 1
    for field, label, colour, ls in (
        ("MergerBulgeMass", "Mean merger-driven", c[1], "--"),
        ("InstabilityBulgeMass", "Mean instability-driven", c[0], "-."),
    ):
        part = s(field)
        y = np.full(len(centres), np.nan)
        for i in range(len(centres)):
            pick = ok & (which == i)
            if pick.sum() >= 5:
                y[i] = np.mean(part[pick] / mass[pick])
        ax.plot(centres, y, color=colour, ls=ls, label=label)
    m = obs.table("Moffet16.dat")
    observed(
        ax,
        10 ** m[:, 0],
        m[:, 1],
        "Moffett+16",
        yerr=[m[:, 1] - m[:, 2], m[:, 3] - m[:, 1]],
        dark=p.o.dark,
    )
    ax.set(
        xscale="log", xlim=(10**8.5, 10**12.5), ylim=(0, 1.05), xlabel=M_STAR
    )
    ax.set_ylabel(r"$M_{\rm bulge}\,/\,M_\star$")
    p.finish("upper left", "lower right")
    return fig


@plot(
    "Gas and baryons",
    "baryon_fraction",
    "Baryon fraction vs halo mass",
    ("Mvir", "Type", "CentralGalaxyIndex", "BlackHoleMass") + BARYONS,
)
def baryon_fraction(p):
    fig, ax = p.figure()
    s = p.s
    mvir, kind = s("Mvir"), s("Type")
    ids, which = np.unique(s("CentralGalaxyIndex"), return_inverse=True)
    central = np.flatnonzero(kind == 0)
    halo = which[central]
    log_m = np.log10(np.maximum(mvir[central], 1.0))
    edges = np.arange(11.0, 16.0 + 0.05, 0.1)
    bins = np.digitize(log_m, edges) - 1
    c = plasma(len(RESERVOIRS), p.o.dark)

    def line(total, label, colour, ls="-"):
        frac = total[halo] / mvir[central]
        x, y, e = [], [], []
        for i in range(len(edges) - 1):
            pick = bins == i
            if pick.sum() > 10:
                x.append(np.mean(log_m[pick]))
                y.append(np.mean(frac[pick]))
                e.append(np.std(frac[pick]) / np.sqrt(pick.sum()))
        x, y, e = 10 ** np.array(x), np.array(y), np.array(e)
        if len(x):
            ax.fill_between(x, y - e, y + e, color=colour, alpha=0.2, lw=0)
            ax.plot(x, y, color=colour, ls=ls, label=label)

    sums = {f: np.bincount(which, s(f), minlength=len(ids)) for f in BARYONS}
    line(sum(sums.values()), "Total", p.ink)
    for (label, field), colour in zip(RESERVOIRS, c, strict=False):
        line(sums[field], label, colour)
    ax.axhline(F_BARYON, color=p.ink, ls="--", lw=1)
    ax.set(
        xscale="log",
        xlim=(10**11.1, 1e15),
        ylim=(0, 0.2),
        xlabel=M_VIR,
        ylabel="Baryon fraction",
    )
    p.finish("center right")
    return fig


@plot(
    "Gas and baryons",
    "reservoirs",
    "Mass reservoirs vs halo mass",
    ("Mvir", "Type") + BARYONS[:-1],
)
def reservoirs(p):
    fig, ax = p.figure()
    s = p.s
    mvir = s("Mvir")
    ok = (s("Type") == 0) & (mvir > 1e10) & (s("StellarMass") > 0)
    for (label, field), colour in zip(RESERVOIRS, GROUPS, strict=False):
        p.relation(ax, mvir, s(field), HALO_EDGES, ok, label, colour)
    ax.set(
        xscale="log",
        yscale="log",
        xlim=(1e10, 1e15),
        ylim=(10**7.5, 1e14),
        xlabel=M_VIR,
        ylabel=r"Mass $(M_\odot)$",
    )
    p.finish("upper left")
    return fig


DUST_EDGES = log_edges(5.0, 9.5, 0.25)
DUST = (
    ("Cold", "ColdDust"),
    ("Hot", "HotDust"),
    ("CGM", "CGMDust"),
    ("Ejected", "EjectedDust"),
)


@plot(
    "Dust",
    "dust_mf",
    "Dust mass function",
    ("ColdDust",),
)
def dust_mf(p):
    fig, ax = p.figure()
    s = p.s
    dust = s("ColdDust")
    p.mass_function(ax, dust[dust > 0], DUST_EDGES, "Model")
    grid = np.geomspace(1e5, 3e9, 18)
    observed(ax, grid, obs.dust_mf(grid, s.h), "Beeston+18 fit", dark=p.o.dark)
    ax.set(
        xscale="log",
        ylim=(1e-5, 0.1),
        xlabel=r"$M_{\rm dust}\ (M_\odot)$",
    )
    p.phi_label(ax)
    p.finish()
    return fig


@plot(
    "Dust",
    "dust_gas",
    "Dust-to-gas vs metallicity",
    ("ColdDust", "ColdGas", "MetalsColdGas"),
)
def dust_gas(p):
    fig, ax = p.figure()
    s = p.s
    cold, metals = s("ColdGas"), s("MetalsColdGas")
    ok = (cold > 0) & (metals > 0)
    oh = np.full(len(cold), np.nan)
    oh[ok] = obs.oh_from_z(metals[ok] / cold[ok])
    ratio = np.divide(
        s("ColdDust"), cold, out=np.zeros(len(cold)), where=cold > 0
    )
    p.relation(ax, oh, ratio, np.arange(7.0, 9.7, 0.1), ok)
    grid = np.arange(7.1, 9.6, 0.2)
    observed(
        ax,
        grid,
        obs.dust_to_gas(grid),
        "Rémy-Ruyer+14 fit",
        dark=p.o.dark,
    )
    ax.set(
        yscale="log",
        xlim=(7.0, 9.6),
        ylim=(1e-6, 0.1),
        xlabel=r"$12 + \log_{10}({\rm O/H})$",
        ylabel=r"$M_{\rm dust} / M_{\rm cold}$",
    )
    p.finish("upper left", "lower right")
    return fig


@plot(
    "Dust",
    "dust_metals",
    "Dust-to-metal ratio",
    ("ColdDust", "MetalsColdGas", "StellarMass"),
)
def dust_metals(p):
    fig, ax = p.figure()
    s = p.s
    metals = s("MetalsColdGas")
    ratio = np.divide(
        s("ColdDust"),
        metals,
        out=np.zeros(len(metals)),
        where=metals > 0,
    )
    p.relation(ax, s("StellarMass"), ratio, M_EDGES, metals > 0, log_y=False)
    ax.set(
        xscale="log",
        xlim=(1e8, 1e12),
        ylim=(0, 1),
        xlabel=M_STAR,
        ylabel=r"$M_{\rm dust} / M_{Z,\rm cold}$",
    )
    p.finish("lower right")
    return fig


@plot(
    "Dust",
    "dust_reservoirs",
    "Dust reservoirs",
    ("Mvir", "Type") + tuple(f for _, f in DUST),
)
def dust_reservoirs(p):
    fig, ax = p.figure()
    s = p.s
    mvir = s("Mvir")
    ok = (s("Type") == 0) & (mvir > 1e10)
    for (label, field), colour in zip(DUST, GROUPS, strict=False):
        p.relation(ax, mvir, s(field), HALO_EDGES, ok, label, colour)
    ax.set(
        xscale="log",
        yscale="log",
        xlim=(1e10, 1e15),
        ylim=(1e2, 1e10),
        xlabel=M_VIR,
        ylabel=r"Dust $(M_\odot)$",
    )
    p.finish("upper left")
    return fig


@plot(
    "Discs",
    "disc_sizes",
    "Disc half-mass radii",
    ("StellarDiscHalfMassRadius", "GasDiscHalfMassRadius", "StellarMass"),
)
def disc_sizes(p):
    fig, ax = p.figure()
    s = p.s
    mass = s("StellarMass")
    for label, field, colour in (
        ("Stellar disc", "StellarDiscHalfMassRadius", GROUPS[0]),
        ("Gas disc", "GasDiscHalfMassRadius", GROUPS[1]),
    ):
        p.relation(
            ax, mass, s(field) * 1e3 / s.h, M_EDGES, mass > 0, label, colour
        )
    grid = np.geomspace(1e9, 4e11, 9)
    observed(
        ax,
        grid,
        obs.late_size(grid),
        "Lange+15 late types (half-light)",
        dark=p.o.dark,
    )
    ax.set(
        xscale="log",
        yscale="log",
        xlim=(1e8, 1e12),
        ylim=(0.3, 100),
        xlabel=M_STAR,
        ylabel=r"$r_{50}\ ({\rm kpc})$",
    )
    p.finish("upper left", "lower right")
    return fig


def _stack(p, values):
    """(radii in kpc, median and 16th, 84th percentile of `values` by
    radius) over massive disc galaxies, from their (n, 30) annuli."""
    s = p.s
    mass = s("StellarMass")
    ok = (mass > 1e10) & (s("BulgeMass") < 0.3 * mass)
    edges = s("DiscRadii")[ok] * 1e3 / s.h
    mid = np.log(np.maximum(0.5 * (edges[:, 1:] + edges[:, :-1]), 1e-4))
    grid = np.geomspace(0.1, 50, 30)
    logv = np.log(np.maximum(values(ok, edges), 1e-12))
    rows = [
        np.interp(np.log(grid), m, v) for m, v in zip(mid, logv, strict=True)
    ]
    if not rows:
        return grid, np.full((3, len(grid)), np.nan)
    return grid, np.exp(np.percentile(rows, [50, 16, 84], axis=0))


@plot(
    "Discs",
    "disc_profiles",
    "Stacked disc profiles",
    ("DiscRadii", "DiscStars", "DiscHI", "DiscH2", "StellarMass", "BulgeMass"),
)
def disc_profiles(p):
    fig, ax = p.figure()
    s = p.s
    fields = [
        ("Stars", "DiscStars", 1),
        ("HI", "DiscHI", 1),
        ("H2", "DiscH2", 1),
    ]
    if s.has("DiscDust"):
        fields.append(("Dust x 100", "DiscDust", 100))

    def surface(field, scale):
        def values(ok, edges):
            area = np.pi * np.diff(edges**2, axis=1) * 1e6  # pc^2
            return s(field)[ok] * scale / np.maximum(area, 1e-6)

        return values

    for (label, field, scale), colour in zip(fields, GROUPS, strict=False):
        r, (med, lo, hi) = _stack(p, surface(field, scale))
        ax.fill_between(r, lo, hi, color=colour, alpha=0.22, lw=0)
        ax.plot(r, med, color=colour, label=label)
    ax.set(
        xscale="log",
        yscale="log",
        ylim=(1e-3, 1e4),
        xlabel=r"$R\ ({\rm kpc})$",
        ylabel=r"$\Sigma\ (M_\odot\,{\rm pc}^{-2})$",
    )
    p.finish()
    return fig


@plot(
    "Discs",
    "disc_metals",
    "Gas metallicity gradient",
    ("DiscRadii", "DiscGas", "DiscGasMetals", "StellarMass", "BulgeMass"),
)
def disc_metals(p):
    fig, ax = p.figure()
    s = p.s

    def ratio(ok, edges):
        gas = s("DiscGas")[ok]
        return s("DiscGasMetals")[ok] / np.maximum(gas, 1e-3)

    r, (med, lo, hi) = _stack(p, ratio)
    ax.fill_between(
        r, obs.oh_from_z(lo), obs.oh_from_z(hi), color=p.ink, alpha=0.22, lw=0
    )
    ax.plot(r, obs.oh_from_z(med), color=p.ink, label="Model")
    ax.set(
        xscale="log",
        xlabel=r"$R\ ({\rm kpc})$",
        ylabel=r"$12 + \log_{10}({\rm O/H})$",
    )
    p.finish()
    return fig


def _density_colour(a, b, n: int = 128) -> np.ndarray:
    """Each point's local density, from a 2D histogram."""
    hist, xe, ye = np.histogram2d(a, b, bins=n)
    i = np.clip(np.digitize(a, xe) - 1, 0, n - 1)
    j = np.clip(np.digitize(b, ye) - 1, 0, n - 1)
    return hist[i, j]


@plot(
    "Structure",
    "spatial",
    "Spatial distribution",
    ("Mvir", "StellarMass", "Posx", "Posy", "Posz"),
    modes=("box",),
)
def spatial(p):
    fig, axes = p.figure(cols=3)
    fig.set_size_inches(16, 5.4)
    s = p.s
    idx = np.flatnonzero((s("Mvir") > 0) & (s("StellarMass") > 1e9))
    idx = p.dilute(idx, 40000)
    x, y, z = s("Posx")[idx], s("Posy")[idx], s("Posz")[idx]
    for ax, (a, b, la, lb) in zip(
        axes,
        ((x, y, "x", "y"), (x, z, "x", "z"), (y, z, "y", "z")),
        strict=False,
    ):
        ax.scatter(
            a,
            b,
            c=_density_colour(a, b),
            cmap="plasma",
            s=0.8,
            lw=0,
            rasterized=True,
        )
        ax.set_aspect("equal")
        ax.set_xlabel(rf"${la}\ ({{\rm Mpc}}\,h^{{-1}})$")
        ax.set_ylabel(rf"${lb}\ ({{\rm Mpc}}\,h^{{-1}})$")
    p.finish()
    return fig


@plot(
    "Structure",
    "spatial_3d",
    "Spatial distribution in 3D",
    ("Mvir", "StellarMass", "Posx", "Posy", "Posz"),
    modes=("box",),
)
def spatial_3d(p):
    from matplotlib.figure import Figure

    s = p.s
    idx = np.flatnonzero((s("Mvir") > 0) & (s("StellarMass") > 1e9))
    idx = p.dilute(idx, 40000)
    x, y, z = s("Posx")[idx], s("Posy")[idx], s("Posz")[idx]
    fig = Figure()
    ax = fig.add_subplot(projection="3d")
    ax.scatter(x, y, z, c=_density_colour(x, y), cmap="plasma", s=0.8, lw=0)
    ax.set_box_aspect((1, 1, 1))
    ax.grid(False)
    ax.set_xlabel(r"$x\ ({\rm Mpc}\,h^{-1})$")
    ax.set_ylabel(r"$y\ ({\rm Mpc}\,h^{-1})$")
    ax.set_zlabel(r"$z\ ({\rm Mpc}\,h^{-1})$")
    return fig


@plot(
    "Structure",
    "wedge",
    "Cone wedge",
    ("ra", "redshift_cosmological", "StellarMass"),
    modes=("cone",),
)
def wedge(p):
    fig, ax = p.figure()
    s = p.s
    ra, z = np.radians(s("ra")), s("redshift_cosmological")
    idx = p.dilute(np.flatnonzero(s("StellarMass") > 0))
    x, y = z[idx] * np.cos(ra[idx]), z[idx] * np.sin(ra[idx])
    ax.scatter(
        x,
        y,
        c=_density_colour(x, y),
        cmap="plasma",
        s=1.2,
        lw=0,
        rasterized=True,
    )
    ax.set_aspect("equal")
    ax.set_xlabel(r"$z\,\cos\alpha$")
    ax.set_ylabel(r"$z\,\sin\alpha$")
    p.finish()
    return fig


@plot(
    "Feedback",
    "mass_loading",
    "Mass loading vs Vvir",
    ("StellarMass", "MassLoading", "Vvir"),
)
def mass_loading(p):
    fig, ax = p.figure()
    s = p.s
    v = s("Vvir").astype(float)
    p.relation(
        ax, v, s("MassLoading"), log_edges(1.0, 3.0, 0.1), s("StellarMass") > 0
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(r"$V_{\rm vir}\ ({\rm km\,s}^{-1})$")
    ax.set_ylabel(r"$\eta_{\rm reheat}$")
    p.finish()
    return fig


@plot(
    "Scaling relations",
    "smhm_regime",
    "Stellar-halo mass by regime",
    ("Mvir", "StellarMass", "Regime"),
)
def smhm_regime(p):
    fig, ax = p.figure()
    s = p.s
    mvir, mass, regime = s("Mvir"), s("StellarMass"), s("Regime")
    c = plasma(2, p.o.dark)
    p.relation(ax, mvir, mass, HALO_EDGES, regime == 0, "CGM regime", c[0])
    p.relation(ax, mvir, mass, HALO_EDGES, regime == 1, "Hot regime", c[1])
    ax.set(
        xscale="log",
        yscale="log",
        xlim=(1e10, 1e15),
        ylim=(1e8, 1e12),
        xlabel=M_VIR,
        ylabel=M_STAR,
    )
    p.finish("upper left")
    return fig


@plot(
    "Scaling relations",
    "concentration",
    "Concentration vs Mvir",
    ("Concentration", "Mvir", "StellarMass", "Type"),
)
def concentration(p):
    fig, axes = p.figure(cols=2, sharey=True)
    fig.set_size_inches(13, 6.2)
    s = p.s
    conc, mvir, kind = s("Concentration"), s("Mvir"), s("Type")
    ok = (conc > 0) & (mvir > 0) & (s("StellarMass") > 1e8)
    c = plasma(2, p.o.dark)
    edges = log_edges(9.5, 15.0, 0.25)
    for ax, pick, title, colour in (
        (axes[0], kind == 0, "Centrals", c[0]),
        (axes[1], kind > 0, "Satellites", c[1]),
    ):
        p.relation(ax, mvir, conc, edges, ok & pick, title, colour)
        ax.set(xscale="log", xlim=(10**9.5, 1e15), ylim=(1, 40), xlabel=M_VIR)
    axes[0].set_ylabel(r"Concentration $c$")
    p.finish()
    return fig


@plot(
    "Star formation",
    "sfr_accretion",
    "SFR vs halo accretion rate",
    ("SfrDisk", "SfrBulge", "mdot_cool", "mdot_stream"),
)
def sfr_accretion(p):
    fig, ax = p.figure()
    s = p.s
    rate, acc = s("SFR"), s("mdot_cool") + s("mdot_stream")
    p.relation(ax, acc, rate, log_edges(0.0, 4.0, 0.2), rate > 0)
    r = np.array([1.0, 1e4])
    ax.plot(r, r, color=p.ink, ls="--", lw=1.2, label="SFR = accretion")
    ax.set(xscale="log", yscale="log", xlim=(1, 1e4), ylim=(1e-6, 1e4))
    ax.set_xlabel(r"$\dot{M}_{\rm acc}\ (M_\odot\,{\rm yr}^{-1})$")
    ax.set_ylabel(r"${\rm SFR}\ (M_\odot\,{\rm yr}^{-1})$")
    p.finish("upper left")
    return fig


@plot(
    "Gas and baryons",
    "tcool",
    "Cooling rate vs Mvir",
    ("CoolingRate", "Mvir", "Regime", "Rvir"),
)
def tcool(p):
    fig, ax = p.figure()
    s = p.s
    mvir, rate, regime = s("Mvir"), s("CoolingRate"), s("Regime")
    c = plasma(2, p.o.dark)
    ok = (rate > 0) & (s("Rvir") > 0)
    edges = HALO_EDGES
    p.relation(ax, mvir, rate, edges, ok & (regime == 0), "CGM regime", c[0])
    p.relation(ax, mvir, rate, edges, ok & (regime == 1), "Hot regime", c[1])
    ax.set(xscale="log", yscale="log", xlabel=M_VIR)
    ax.set_ylabel(r"Cooling rate $(M_\odot\,{\rm Gyr}^{-1})$")
    p.finish("upper left")
    return fig


@plot(
    "Gas and baryons",
    "cgm_fraction",
    "CGM fraction vs Mvir",
    ("CGMgas", "Mvir"),
)
def cgm_fraction(p):
    fig, ax = p.figure()
    s = p.s
    mvir = s("Mvir")
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = s("CGMgas") / (F_BARYON * mvir)
    p.relation(ax, mvir, frac, log_edges(10.0, 12.0, 0.1))
    ax.set(xscale="log", yscale="log", xlim=(1e10, 1e12), xlabel=M_VIR)
    ax.set_ylabel(r"$M_{\rm CGM}\,/\,(f_b\,M_{\rm vir})$")
    p.finish()
    return fig


@plot(
    "Feedback",
    "ejection",
    "Ejection efficiency vs Vvir",
    ("SfrDisk", "SfrBulge", "MassLoading", "Vvir", "Mvir"),
)
def ejection(p):
    fig, ax = p.figure()
    s = p.s
    rate, load, v = s("SFR"), s("MassLoading"), s("Vvir").astype(float)
    # SAGE26's FIRE feedback, Eqs 4-6: epsilon_disk 2.9, epsilon_halo 0.3,
    # V_sn 501 km/s.
    with np.errstate(divide="ignore", invalid="ignore"):
        energy = 0.5 * 0.3 * (load / 2.9) * rate * 501.0**2
        lift = 0.5 * load * rate * v**2
        eject = np.maximum(0.0, (energy - lift) / (0.5 * v**2))
        efficiency = eject / rate
    ok = (rate > 0) & (load > 0) & (v > 0) & (s("Mvir") > 0)
    p.relation(ax, v, efficiency, log_edges(1.0, 3.0, 0.1), ok)
    ax.set(xscale="log", yscale="log")
    ax.set_xlabel(r"$V_{\rm vir}\ ({\rm km\,s}^{-1})$")
    ax.set_ylabel("Ejection efficiency")
    p.finish()
    return fig


@plot(
    "Structure",
    "disk_radius",
    "Disc radius vs Rvir",
    ("DiskRadius", "StellarMass", "Rvir"),
)
def disk_radius(p):
    fig, ax = p.figure()
    s = p.s
    # r_e = 1.68 r_d for an exponential disc, physical kpc.
    disk = s("DiskRadius") * 1.0e3 * 1.68 / s.h
    rvir = s("Rvir") * 1.0e3 / s.h
    mass = s("StellarMass")
    ok = (rvir > 0) & (disk > 0) & (mass > 10**9.3) & (mass < 10**11.3)
    if ok.any():
        p.relation(
            ax,
            rvir,
            disk,
            log_edges(np.log10(rvir[ok].min()), np.log10(rvir[ok].max()), 0.1),
            ok,
        )
        ratio = np.median(obs.table("RSRHSomerville.dat")[:, 1])
        grid = np.geomspace(rvir[ok].min(), rvir[ok].max(), 8)
        observed(ax, grid, ratio * grid, "Somerville+18", dark=p.o.dark)
    ax.set(xscale="log", yscale="log", ylim=(1e-2, 1e2))
    ax.set_xlabel(r"$R_{\rm vir}\ ({\rm kpc})$")
    ax.set_ylabel(r"$R_{\rm e,disc}\ ({\rm kpc})$")
    p.finish("upper left", "lower right")
    return fig


@plot(
    "Structure",
    "half_mass",
    "Half-mass radius vs stellar mass",
    ("DiskRadius", "BulgeRadius", "StellarMass", "BulgeMass"),
)
def half_mass(p):
    fig, ax = p.figure()
    s = p.s
    mass, bulge = s("StellarMass"), s("BulgeMass")
    disk_r = s("DiskRadius") * 1.0e3 * 1.68 / s.h
    bulge_r = s("BulgeRadius") * 1.0e3 / s.h
    # Mass-weighted disc and bulge (Lagos+18), physical kpc.
    with np.errstate(divide="ignore", invalid="ignore"):
        r50 = ((mass - bulge) * disk_r + bulge * bulge_r) / mass
    ok = (mass > 1e8) & ((disk_r > 0) | (bulge_r > 0))
    p.relation(ax, mass, r50, log_edges(8.0, 12.2, 0.2), ok)
    ax.set(xscale="log", yscale="log", xlabel=M_STAR)
    ax.set_ylabel(r"$R_{50}\ ({\rm kpc})$")
    p.finish("upper left")
    return fig
