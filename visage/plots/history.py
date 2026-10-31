"""Across redshift: SAGE26's allresults-history plots.  In a box each view
is a snapshot; in a lightcone each is the shell drawn from one snapshot."""

from __future__ import annotations

import numpy as np

from visage.plots import obs
from visage.plots.base import F_BARYON, SSFR_CUT, density, log_edges, plot
from visage.plots.style import GROUPS, observed, plasma

Z_BINS = (
    (0.2, 0.5),
    (0.5, 0.8),
    (0.8, 1.1),
    (1.1, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
    (2.5, 3.0),
    (3.0, 3.5),
    (3.5, 4.5),
    (4.5, 5.5),
    (5.5, 6.5),
    (6.5, 7.5),
    (7.5, 8.5),
    (8.5, 10.0),
    (10.0, 12.0),
)
M_STAR = r"$M_\star\ (M_\odot)$"
M_VIR = r"$M_{\rm vir}\ (M_\odot)$"
PHI = r"$\phi\ ({\rm Mpc}^{-3}\,{\rm dex}^{-1})$"
Z_LABEL = r"Redshift $z$"


def z_bins(p) -> list:
    """SAGE26's redshift bins; a cone's own range, split evenly, for a cone
    that would miss most of those."""
    zs = [s.z for s in p.views if len(s)]
    if not zs or not hasattr(p.views[0], "area") or max(zs) > 2.0:
        return list(Z_BINS)
    n = min(len(set(zs)), 5)
    edges = np.linspace(min(zs), max(zs) + 1e-6, n + 1)
    return list(zip(edges[:-1], edges[1:], strict=True))


def z_groups(p):
    """(label, colour, samples) for each redshift bin that has galaxies."""
    bins = z_bins(p)
    fmt = ".1f" if bins[0] == Z_BINS[0] else ".3f"
    for (lo, hi), colour in zip(
        bins, plasma(len(bins), p.o.dark), strict=True
    ):
        views = [s for s in p.views if lo <= s.z <= hi and len(s)]
        if views:
            yield f"{lo:{fmt}} $<$ z $<$ {hi:{fmt}}", colour, views


def nearest(p, z: float):
    """The view closest to redshift `z`, unless none is near it."""
    views = [s for s in p.views if len(s)]
    if not views:
        return None
    best = min(views, key=lambda s: abs(s.z - z))
    return best if abs(best.z - z) < 0.25 * (1 + z) else None


def z_axis(p, ax, top: float) -> None:
    """Redshift from 0 to `top`, or to the end of a shallower cone."""
    zs = [s.z for s in p.views if len(s)]
    ax.set_xlim(0, min(top, 1.05 * max(zs)) if zs else top)
    ax.set_xlabel(Z_LABEL)


def evolve(p, ax, measure, log_y=True) -> None:
    """A line for each redshift bin: the mean over its views of
    `measure(sample)` -> (x, y), with its standard error."""
    for label, colour, views in z_groups(p):
        got = [measure(s) for s in views]
        x = got[0][0]
        stack = np.array([g[1] for g in got], float)
        if not np.isfinite(stack).any():
            continue
        mean = np.nanmean(stack, axis=0)
        err = np.nanstd(stack, axis=0) / np.sqrt(len(stack))
        ok = np.isfinite(mean) & (mean > 0 if log_y else True)
        ax.plot(x[ok], mean[ok], color=colour, label=label, lw=1.8)
        low = np.maximum(mean - err, mean * 0.01) if log_y else mean - err
        ax.fill_between(
            x[ok], low[ok], (mean + err)[ok], color=colour, alpha=0.25, lw=0
        )


def means_in_bins(x, y, edges):
    """Bin centres and the mean of y in bins of x."""
    which = np.digitize(x, edges) - 1
    n = len(edges) - 1
    keep = (which >= 0) & (which < n)
    count = np.bincount(which[keep], minlength=n).astype(float)
    total = np.bincount(which[keep], y[keep], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.sqrt(edges[1:] * edges[:-1]), total / count


def phi_axis(p, ax) -> None:
    ax.set_yscale("log")
    has_volume = any(s.volume for s in p.views)
    ax.set_ylabel(PHI if has_volume else r"$N\ ({\rm dex}^{-1})$")
    if has_volume:
        ax.set_ylim(1e-6, 1e-1)


@plot(
    "Cooling",
    "rcool",
    "Rcool/Rvir above Mshock",
    ("Mvir", "RcoolToRvir"),
    group=False,
)
def rcool(p):
    fig, ax = p.figure()
    edges = np.arange(0.0, 2.2, 0.05)
    colours = plasma(3, p.o.dark)
    for target, colour in zip((0.0, 2.0, 6.0), colours, strict=True):
        s = nearest(p, target)
        if s is None:
            continue
        ratio = s("RcoolToRvir")
        pick = (s("Mvir") > 6.0e11) & (ratio >= 0)
        if not pick.any():
            continue
        share = np.mean(ratio[pick] > 1)
        ax.hist(
            np.clip(ratio[pick], edges[0], edges[-1]),
            bins=edges,
            histtype="step",
            density=True,
            color=colour,
            lw=2,
            label=f"z = {s.z:.1f}, N = {pick.sum()}, "
            rf"$f_{{>1}}$ = {share:.2f}",
        )
    ax.axvline(1.0, color=p.ink, ls="--", lw=1)
    ax.set_xlabel(r"$r_{\rm cool}\,/\,R_{\rm vir}$")
    ax.set_ylabel("PDF")
    p.finish("upper left")
    return fig


@plot(
    "Mass functions",
    "smf_z",
    "Stellar mass function at four redshifts",
    ("StellarMass",),
    group=False,
)
def smf_z(p):
    fig, ax = p.figure()
    edges = log_edges(7.0, 12.5, 0.1)
    colours = plasma(4, p.o.dark)
    for target, colour, fit in zip(
        (0.1, 1.65, 2.5, 3.5), colours, obs.MARCHESINI09, strict=True
    ):
        s = nearest(p, target)
        if s is not None:
            p.mass_function(
                ax, s("StellarMass"), edges, f"z = {s.z:.1f}", colour, s=s
            )
        label, lo, star, alpha, phi = fit
        m = np.arange(lo, 11.8, 0.25)
        observed(  # to Salpeter, then Chabrier
            ax,
            10**m * 1.6 / 1.8,
            obs.schechter(m, star, alpha, phi),
            f"Marchesini+09 {label}",
            colour=colour,
            dark=p.o.dark,
        )
    ax.set(xscale="log", xlim=(1e7, 10**12.2), xlabel=M_STAR)
    phi_axis(p, ax)
    p.finish()
    return fig


@plot(
    "Cosmic density",
    "sfrd",
    "SFR density",
    ("SfrDisk", "SfrBulge"),
    group=False,
)
def sfrd(p):
    fig, ax = p.figure()
    d = obs.SFRD
    views = [s for s in p.views if s.volume]
    z = np.array([s.z for s in views])
    rho = np.array([np.sum(s("SFR")) / s.volume for s in views])
    keep = rho > 0
    ax.plot(z[keep], rho[keep], color=p.ink, lw=2.5, label="Model")
    observed(
        ax,
        d[:, 0],
        d[:, 1],
        "Observations",
        xerr=[np.abs(d[:, 0] - d[:, 2]), np.abs(d[:, 3] - d[:, 0])],
        yerr=[np.abs(d[:, 1] - d[:, 4]), np.abs(d[:, 5] - d[:, 1])],
        dark=p.o.dark,
    )
    ax.set(yscale="log", ylim=(1e-3, 10**-0.4))
    z_axis(p, ax, 8.0)
    ax.set_ylabel(
        r"$\rho_{\rm SFR}\ (M_\odot\,{\rm yr}^{-1}\,{\rm Mpc}^{-3})$"
    )
    p.finish()
    return fig


@plot(
    "Cosmic density",
    "smd",
    "Stellar mass density",
    ("StellarMass",),
    group=False,
)
def smd(p):
    fig, ax = p.figure()
    views = [s for s in p.views if s.volume]
    z, rho = [], []
    for s in views:
        mass = s("StellarMass")
        z.append(s.z)
        rho.append(np.sum(mass[(mass > 1e8) & (mass < 1e13)]) / s.volume)
    z, rho = np.array(z), np.array(rho)
    keep = rho > 0
    ax.plot(z[keep], rho[keep], color=p.ink, lw=2.5, label="Model")
    for name, rows in obs.SMD.items():
        o = np.array(rows)
        mid = 0.5 * (o[:, 0] + o[:, 1])
        val = 10 ** o[:, 2] * 1.6 / 1.8  # to Salpeter, then Chabrier
        observed(
            ax,
            mid,
            val,
            name,
            xerr=[mid - o[:, 0], o[:, 1] - mid],
            yerr=[val * (1 - 10 ** -o[:, 3]), val * (10 ** o[:, 4] - 1)],
            dark=p.o.dark,
        )
    ax.set(yscale="log", ylim=(10**6.5, 1e9))
    z_axis(p, ax, 4.2)
    ax.set_ylabel(r"$\rho_\star\ (M_\odot\,{\rm Mpc}^{-3})$")
    p.finish("upper right", "lower left")
    return fig


@plot(
    "Relations by redshift",
    "sfr_z",
    "SFR vs stellar mass by redshift",
    ("StellarMass", "SfrDisk", "SfrBulge"),
    group=False,
)
def sfr_z(p):
    fig, ax = p.figure()
    edges = log_edges(7.2, 12.5, 0.1)

    def measure(s):
        mass, rate = s("StellarMass"), s("SFR")
        pick = (mass > 0) & (rate > 0)
        x, y = means_in_bins(mass[pick], np.log10(rate[pick]), edges)
        return x, 10**y

    evolve(p, ax, measure)
    ax.set(
        xscale="log",
        yscale="log",
        xlim=(1e8, 10**12.2),
        ylim=(1e-4, 1e3),
        xlabel=M_STAR,
    )
    ax.set_ylabel(r"${\rm SFR}\ (M_\odot\,{\rm yr}^{-1})$")
    p.finish("lower right")
    return fig


@plot(
    "Relations by redshift",
    "smhm_z",
    "Stellar-halo mass by redshift",
    ("StellarMass", "Mvir"),
    group=False,
)
def smhm_z(p):
    fig, ax = p.figure()
    edges = log_edges(10.0, 15.0, 0.1)

    def measure(s):
        mass, mvir = s("StellarMass"), s("Mvir")
        pick = (mass > 0) & (mvir > 0)
        return means_in_bins(mvir[pick], mass[pick], edges)

    evolve(p, ax, measure)
    ax.set(
        xscale="log",
        yscale="log",
        xlim=(1e10, 1e15),
        ylim=(1e7, 1e12),
        xlabel=M_VIR,
        ylabel=M_STAR,
    )
    p.finish("lower right")
    return fig


def _functions(p, field, edges, xlabel, xlim, cut=None):
    fig, ax = p.figure()

    def measure(s):
        values = s(field) if cut is None else s(field)[cut(s)]
        return density(values, edges, s.volume)

    evolve(p, ax, measure)
    ax.set(xscale="log", xlim=xlim, xlabel=xlabel)
    phi_axis(p, ax)
    p.finish()
    return fig


@plot(
    "Mass functions",
    "smf_evolution",
    "Stellar mass function by redshift",
    ("StellarMass", "Mvir"),
    group=False,
)
def smf_evolution(p):
    return _functions(
        p,
        "StellarMass",
        log_edges(7.2, 12.5, 0.1),
        M_STAR,
        (10**7.2, 1e12),
        lambda s: s("Mvir") >= 1e10,
    )


@plot(
    "Mass functions",
    "sfrf",
    "SFR function by redshift",
    ("SfrDisk", "SfrBulge"),
    group=False,
)
def sfrf(p):
    return _functions(
        p,
        "SFR",
        log_edges(-3.0, 3.4, 0.2),
        r"${\rm SFR}\ (M_\odot\,{\rm yr}^{-1})$",
        (1e-3, 10**3.2),
    )


@plot(
    "Mass functions",
    "hmf",
    "Halo mass function by redshift",
    ("Mvir", "Type"),
    group=False,
)
def hmf(p):
    return _functions(
        p,
        "Mvir",
        log_edges(10.0, 15.0, 0.1),
        M_VIR,
        (1e10, 1e15),
        lambda s: s("Type") == 0,
    )


@plot(
    "Mass functions",
    "bhmf",
    "Black hole mass function by redshift",
    ("BlackHoleMass",),
    group=False,
)
def bhmf(p):
    fig, ax = p.figure()
    edges = log_edges(6.0, 11.4, 0.1)
    targets = (0.1, 1.0, 2.0, 4.0, 6.0, 8.0)
    for target, colour in zip(targets, plasma(6, p.o.dark), strict=True):
        s = nearest(p, target)
        if s is not None:
            p.mass_function(
                ax, s("BlackHoleMass"), edges, f"z = {s.z:.1f}", colour, s=s
            )
        o = obs.table(f"fig4_bhmf_z{target:.1f}.txt")[::3]
        keep = o[:, 1] > 0
        o = o[keep]
        observed(
            ax,
            10 ** o[:, 0],
            o[:, 1],
            f"TRINITY, z = {target:.1f}",
            yerr=[np.abs(o[:, 1] - o[:, 2]), np.abs(o[:, 3] - o[:, 1])],
            colour=colour,
            dark=p.o.dark,
        )
    ax.set(xscale="log", xlim=(1e6, 1e11))
    ax.set_xlabel(r"$M_{\rm BH}\ (M_\odot)$")
    phi_axis(p, ax)
    ax.set_ylim(1e-5, 1e-1) if any(s.volume for s in p.views) else None
    p.finish()
    return fig


@plot(
    "Relations by redshift",
    "quenched_z",
    "Quenched fraction by redshift",
    ("StellarMass", "SfrDisk", "SfrBulge", "Type"),
    group=False,
)
def quenched_z(p):
    fig, ax = p.figure()
    edges = log_edges(7.2, 13.4, 0.1)

    def fraction(s, want):
        mass = s("StellarMass")
        pick = (mass > 0) & want(s("Type"))
        q = (s("sSFR") < 10.0**SSFR_CUT).astype(float)
        return means_in_bins(mass[pick], q[pick], edges)

    evolve(p, ax, lambda s: fraction(s, lambda t: t == 0), log_y=False)
    for _label, colour, views in z_groups(p):
        got = [fraction(s, lambda t: t == 1) for s in views]
        y = _nanmean([g[1] for g in got])
        ax.plot(got[0][0], y, color=colour, ls=":", lw=1.5)
    ax.plot([], [], color=p.ink, ls="-", label="Centrals")
    ax.plot([], [], color=p.ink, ls=":", label="Satellites")
    ax.set(
        xscale="log",
        xlim=(1e8, 10**12.5),
        ylim=(0, 0.8),
        xlabel=M_STAR,
        ylabel="Quenched fraction",
    )
    p.finish("upper left")
    return fig


def _nanmean(stack) -> np.ndarray:
    stack = np.array(stack, float)
    count = np.isfinite(stack).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.nansum(stack, axis=0) / count


def _percentiles(values, need: int = 5):
    if len(values) < need:
        return np.nan, np.nan, np.nan
    return tuple(np.percentile(values, [16, 50, 84]))


@plot(
    "Relations by redshift",
    "concentration_z",
    "Concentration by redshift",
    ("Concentration", "Mvir"),
    group=False,
)
def concentration_z(p):
    fig, ax = p.figure()
    bins = (
        (1e10, 1e11, r"$10^{10}-10^{11}\,M_\odot$"),
        (1e11, 1e12, r"$10^{11}-10^{12}\,M_\odot$"),
        (1e12, 1e13, r"$10^{12}-10^{13}\,M_\odot$"),
        (1e13, 1e15, r"$10^{13}-10^{15}\,M_\odot$"),
    )
    views = sorted((s for s in p.views if len(s)), key=lambda s: s.z)
    z = np.array([s.z for s in views])
    for (lo, hi, label), colour in zip(bins, plasma(4, p.o.dark), strict=True):
        rows = []
        for s in views:
            c, m = s("Concentration"), s("Mvir")
            rows.append(_percentiles(c[(c > 0) & (m >= lo) & (m < hi)]))
        low, med, high = np.array(rows).T
        keep = np.isfinite(med)
        ax.fill_between(
            z[keep], low[keep], high[keep], color=colour, alpha=0.18, lw=0
        )
        ax.plot(z[keep], med[keep], color=colour, label=label)
    ax.set(ylim=(0, 30), ylabel=r"Concentration $c$")
    z_axis(p, ax, 15.0)
    p.finish()
    return fig


@plot(
    "Relations by redshift",
    "metallicity_z",
    "Stellar metallicity by redshift",
    ("StellarMass", "MetalsStellarMass"),
    group=False,
)
def metallicity_z(p):
    fig, ax = p.figure()
    edges = log_edges(7.2, 12.5, 0.1)

    def measure(s):
        mass, metals = s("StellarMass"), s("MetalsStellarMass")
        pick = (mass > 0) & (metals > 0)
        x, y = means_in_bins(
            mass[pick], np.log10(metals[pick] / mass[pick]), edges
        )
        return x, 10**y

    evolve(p, ax, measure)
    ax.set(xscale="log", yscale="log", xlim=(10**7.2, 1e12), xlabel=M_STAR)
    ax.set_ylabel(r"$Z_\star$")
    p.finish("lower right")
    return fig


@plot(
    "Relations by redshift",
    "h2_z",
    "H2 fraction by redshift",
    ("StellarMass", "ColdGas", "H2gas"),
    group=False,
)
def h2_z(p):
    fig, ax = p.figure()
    edges = log_edges(7.2, 12.5, 0.1)

    def measure(s):
        mass, cold = s("StellarMass"), s("ColdGas")
        pick = (mass > 0) & (cold > 0)
        frac = np.clip(s("H2gas")[pick] / (cold[pick] * 0.74), 0.0, 1.0)
        return means_in_bins(mass[pick], frac, edges)

    evolve(p, ax, measure, log_y=False)
    ax.axhline(1.0, color=p.ink, ls="--", lw=1, alpha=0.5)
    ax.set(xscale="log", xlim=(10**7.2, 1e12), ylim=(0, 1.05), xlabel=M_STAR)
    ax.set_ylabel(r"$M_{\rm H_2}\,/\,(0.74\,M_{\rm cold})$")
    p.finish("upper left")
    return fig


@plot(
    "Relations by redshift",
    "sfe",
    "Star formation efficiency",
    ("StellarMass", "Mvir", "Type"),
    group=False,
)
def sfe(p):
    fig, ax = p.figure()
    z, rows = [], []
    for s in p.views:
        if not len(s):
            continue
        mass, mvir = s("StellarMass"), s("Mvir")
        pick = (s("Type") == 0) & (mass > 0) & (mvir > 0)
        z.append(s.z)
        rows.append(_percentiles(mass[pick] / (F_BARYON * mvir[pick])))
    z = np.array(z)
    low, med, high = np.array(rows).T
    order = np.argsort(z)
    keep = order[np.isfinite(med[order])]
    ax.fill_between(
        z[keep], low[keep], high[keep], color=p.ink, alpha=0.2, lw=0
    )
    ax.plot(z[keep], med[keep], color=p.ink, label="Centrals")
    ax.set(yscale="log", ylim=(1e-6, 1))
    z_axis(p, ax, 15.0)
    ax.set_ylabel(r"$M_\star\,/\,(f_b\,M_{\rm vir})$")
    p.finish()
    return fig


def _bars(p, ax, count, centrals: str, satellites: str) -> None:
    labels, cen, sat = [], [], []
    for lo, hi in z_bins(p):
        views = [s for s in p.views if lo <= s.z <= hi and len(s)]
        if views:
            got = np.array([count(s) for s in views], float)
            labels.append(f"{lo:.1f}-{hi:.1f}")
            cen.append(got[:, 0].mean())
            sat.append(got[:, 1].mean())
    x = np.arange(len(labels))
    c = plasma(2, p.o.dark)
    ax.bar(x - 0.2, cen, 0.38, color=c[0], label=centrals)
    ax.bar(x + 0.2, sat, 0.38, color=c[1], label=satellites)
    ax.set_xticks(x, labels, rotation=45, ha="right", fontsize=11)
    ax.set_xlabel(Z_LABEL)
    ax.set_ylabel("Average count")


@plot(
    "Centrals and satellites",
    "cs_counts",
    "Central and satellite counts",
    ("Type",),
    group=False,
)
def cs_counts(p):
    fig, ax = p.figure()

    def count(s):
        t = s("Type")
        return np.sum(t == 0), np.sum(t >= 1)

    _bars(p, ax, count, "Centrals", "Satellites")
    p.finish()
    return fig


@plot(
    "Centrals and satellites",
    "cs_fraction",
    "Central and satellite fractions",
    ("Type",),
    group=False,
)
def cs_fraction(p):
    fig, ax = p.figure()
    views = sorted((s for s in p.views if len(s)), key=lambda s: s.z)
    z = np.array([s.z for s in views])
    cen = np.array([np.mean(s("Type") == 0) for s in views])
    ax.plot(z, cen, color=GROUPS[0], lw=2.5, label="Centrals")
    ax.plot(z, 1 - cen, color=GROUPS[1], lw=2.5, label="Satellites")
    ax.set(ylim=(0, 1.05), xlabel=Z_LABEL, ylabel="Fraction")
    p.finish("center right")
    return fig


@plot(
    "Centrals and satellites",
    "cs_massive",
    "Massive quiescent: centrals and satellites",
    ("StellarMass", "SfrDisk", "SfrBulge", "Type"),
    group=False,
)
def cs_massive(p):
    fig, ax = p.figure()
    z, cen, sat = [], [], []
    for s in sorted(p.views, key=lambda v: v.z):
        mass = s("StellarMass")
        idx = np.flatnonzero(mass > 0)
        if len(idx) < 10:
            continue
        idx = idx[mass[idx] >= np.percentile(mass[idx], 90)]
        # Quiescent below 0.2 / t_H(z).
        hubble_rate = s.e_z * s.h / 9.778e9
        rate = s("SFR")[idx] / mass[idx]
        quiet = idx[rate < 0.2 * hubble_rate]
        if len(quiet):
            kind = s("Type")[quiet]
            z.append(s.z)
            cen.append(np.mean(kind == 0))
            sat.append(np.mean(kind >= 1))
    ax.plot(z, cen, color=GROUPS[0], lw=2.5, label="Centrals")
    ax.plot(z, sat, color=GROUPS[1], lw=2.5, label="Satellites")
    ax.set(ylim=(0, 1.05), xlabel=Z_LABEL)
    ax.set_ylabel(r"Fraction (top 10\% $M_\star$, $s{\rm SFR}<0.2/t_{\rm H}$)")
    p.finish("center right")
    return fig


@plot(
    "Centrals and satellites",
    "quenched_counts",
    "Quenched central and satellite counts",
    ("StellarMass", "SfrDisk", "SfrBulge", "Type"),
    group=False,
)
def quenched_counts(p):
    fig, ax = p.figure()

    def count(s):
        t = s("Type")
        q = s("sSFR") < 10.0**SSFR_CUT
        return np.sum((t == 0) & q), np.sum((t >= 1) & q)

    _bars(p, ax, count, "Quenched centrals", "Quenched satellites")
    p.finish()
    return fig
