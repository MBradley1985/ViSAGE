"""What a lightcone's photometry adds: plots of galaxies as observed."""

from __future__ import annotations

import numpy as np

from visage.plots import obs
from visage.plots.base import density, log_edges, plot
from visage.plots.local import M_STAR
from visage.plots.style import observed, plasma

Z = "redshift_cosmological"
COUNT_BANDS = ("sdss_u", "sdss_g", "sdss_r", "sdss_i")
DRIVER12 = (
    ("sdss_u", "lfu_z0_driver12.data", "u"),
    ("sdss_g", "lfg_z0_driver12.data", "g"),
    ("sdss_r", "lfr_z0_driver12.data", "r"),
    ("2mass_ks", "lfk_z0_driver12.data", "K"),
)


def _area_deg2(s) -> float:
    return s.area * (180.0 / np.pi) ** 2


@plot("Observed", "nz", "Redshift distribution", (Z,), modes=("cone",))
def nz(p):
    fig, ax = p.figure()
    z = p.s(Z)
    ax.hist(z, bins=40, histtype="step", color=p.ink, lw=2, label="Model")
    ax.set_xlabel(r"Redshift $z$")
    ax.set_ylabel(r"$N$")
    p.finish()
    return fig


@plot(
    "Observed",
    "counts",
    "Number counts",
    tuple(f"mag_obs_{b}" for b in COUNT_BANDS),
    modes=("cone",),
)
def counts(p):
    fig, ax = p.figure()
    s = p.s
    edges = np.arange(10.0, 32.0, 0.5)
    centres = 0.5 * (edges[1:] + edges[:-1])
    area = _area_deg2(s)
    driver = np.genfromtxt(
        obs.DATA / "driver16_sdss_counts.data",
        dtype=None,
        encoding=None,
        usecols=(1, 2, 3, 4),
    )
    for band, colour in zip(
        COUNT_BANDS, plasma(len(COUNT_BANDS), p.o.dark), strict=True
    ):
        d = driver[driver["f0"] == band.split("_")[1]]
        # Per 0.5 mag in the table.
        observed(
            ax,
            d["f1"],
            d["f2"] / 0.5,
            f"Driver+16 {band.split('_')[1]}",
            yerr=d["f3"] / 0.5,
            colour=colour,
            dark=p.o.dark,
        )
        m = s(f"mag_obs_{band}")
        n = np.histogram(m[np.isfinite(m)], edges)[0] / 0.5 / area
        keep = n > 0
        ax.plot(centres[keep], n[keep], color=colour, label=band.split("_")[1])
    ax.set(yscale="log", xlabel="Apparent magnitude (AB)")
    ax.set_ylabel(r"$N\ ({\rm mag}^{-1}\,{\rm deg}^{-2})$")
    p.finish("upper left", "lower right")
    return fig


def _density_panel(p, ax, x, y) -> None:
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    if not len(x):
        return
    ax.hexbin(x, y, gridsize=70, bins="log", cmap="plasma", mincnt=1, lw=0)


@plot(
    "Observed",
    "colour_magnitude",
    "Colour-magnitude diagram",
    ("mag_rest_sdss_g", "mag_rest_sdss_r"),
    modes=("cone",),
)
def colour_magnitude(p):
    fig, ax = p.figure()
    g, r = p.s("mag_rest_sdss_g"), p.s("mag_rest_sdss_r")
    _density_panel(p, ax, r, g - r)
    ax.invert_xaxis()
    ax.set_xlabel(r"$M_r$ (AB)")
    ax.set_ylabel(r"$g-r$")
    p.finish()
    return fig


@plot(
    "Observed",
    "colour_colour",
    "Colour-colour diagram",
    ("mag_rest_sdss_u", "mag_rest_sdss_r", "mag_rest_2mass_j"),
    modes=("cone",),
)
def colour_colour(p):
    fig, ax = p.figure()
    s = p.s
    u, r, j = (
        s("mag_rest_sdss_u"),
        s("mag_rest_sdss_r"),
        s("mag_rest_2mass_j"),
    )
    _density_panel(p, ax, r - j, u - r)
    ax.set_xlabel(r"$r-J$")
    ax.set_ylabel(r"$u-r$")
    p.finish()
    return fig


@plot(
    "Observed",
    "lf",
    "Rest-frame luminosity functions",
    tuple(f"mag_rest_{b}" for b, _, _ in DRIVER12),
    modes=("cone",),
)
def lf(p):
    fig, ax = p.figure()
    s = p.s
    edges = np.arange(-28.0, -10.0, 0.5)
    centres = 0.5 * (edges[1:] + edges[:-1])
    h = s.h
    colours = plasma(len(DRIVER12), p.o.dark)
    for (band, name, label), colour in zip(DRIVER12, colours, strict=True):
        m = s(f"mag_rest_{band}")
        n = np.histogram(m[np.isfinite(m)], edges)[0] / 0.5
        n = n / (s.volume or 1.0)
        keep = n > 0
        ax.plot(centres[keep], n[keep], color=colour, label=label)
        if s.volume:
            d = obs.table(name)
            d = d[d[:, 1] > 0]
            # M - 5 log h and (Mpc/h)^-3 per 0.5 mag, to h-free per mag.
            observed(
                ax,
                d[:, 0] + 5 * np.log10(h),
                d[:, 1] * h**3 / 0.5,
                f"Driver+12 {label}",
                yerr=d[:, 2] * h**3 / 0.5,
                colour=colour,
                dark=p.o.dark,
            )
    ax.set(yscale="log", xlim=(-14, -27), xlabel="Absolute magnitude (AB)")
    ax.set_ylabel(
        r"$\phi\ ({\rm Mpc}^{-3}\,{\rm mag}^{-1})$"
        if s.volume
        else r"$N\ ({\rm mag}^{-1})$"
    )
    if s.volume:
        ax.set_ylim(1e-7, 1e-1)
    p.finish("upper left", "lower right")
    return fig


@plot(
    "Observed",
    "halpha_lf",
    "H-alpha luminosity function",
    ("LineLum_Halpha",),
    modes=("cone",),
)
def halpha_lf(p):
    fig, ax = p.figure()
    s = p.s
    p.mass_function(
        ax, s("LineLum_Halpha"), log_edges(38.0, 44.0, 0.2), "Through dust"
    )
    ax.set_xscale("log")
    ax.set_xlabel(r"$L_{{\rm H}\alpha}\ ({\rm erg\,s}^{-1})$")
    p.phi_label(ax)
    p.finish()
    return fig


@plot(
    "Observed",
    "bpt",
    "BPT diagram",
    (
        "LineLum_Halpha",
        "LineLum_Hbeta",
        "LineLum_NII6584",
        "LineLum_OIII5007",
    ),
    modes=("cone",),
)
def bpt(p):
    fig, ax = p.figure()
    s = p.s
    ha, hb = s("LineLum_Halpha"), s("LineLum_Hbeta")
    n2, o3 = s("LineLum_NII6584"), s("LineLum_OIII5007")
    keep = (ha > 0) & (hb > 0) & (n2 > 0) & (o3 > 0)
    _density_panel(
        p, ax, np.log10(n2[keep] / ha[keep]), np.log10(o3[keep] / hb[keep])
    )
    x = np.linspace(-2.0, 0.0, 200)
    ax.plot(
        x, 0.61 / (x - 0.05) + 1.3, color=p.ink, ls="--", label="Kauffmann+03"
    )
    x = np.linspace(-2.0, 0.4, 200)
    ax.plot(
        x, 0.61 / (x - 0.47) + 1.19, color=p.ink, ls="-", label="Kewley+01"
    )
    ax.set(xlim=(-2, 0.6), ylim=(-1.5, 1.5))
    ax.set_xlabel(r"$\log_{10}$ [NII]/H$\alpha$")
    ax.set_ylabel(r"$\log_{10}$ [OIII]/H$\beta$")
    p.finish("lower left")
    return fig


@plot(
    "Observed",
    "tully_fisher",
    "HI Tully-Fisher",
    ("W50_HI", "CosInclination", "StellarMass"),
    modes=("cone",),
)
def tully_fisher(p):
    fig, ax = p.figure()
    s = p.s
    sin_i = np.sqrt(np.maximum(1 - s("CosInclination") ** 2, 1e-4))
    ok = (s("W50_HI") > 0) & (sin_i > 0.5) & (s("StellarMass") > 1e8)
    p.relation(
        ax, s("W50_HI") / sin_i, s("StellarMass"), log_edges(1.5, 3.0, 0.1), ok
    )
    ax.set(xscale="log", yscale="log", ylabel=r"$M_\star\ (M_\odot)$")
    ax.set_xlabel(r"$W_{50} / \sin i\ ({\rm km\,s^{-1}})$")
    p.finish("upper left")
    return fig


@plot(
    "Observed",
    "attenuation",
    "Dust attenuation vs stellar mass",
    ("TauV_ISM", "StellarMass"),
    modes=("cone",),
)
def attenuation(p):
    fig, ax = p.figure()
    s = p.s
    a_v = 1.086 * s("TauV_ISM")
    p.relation(ax, s("StellarMass"), a_v, log_edges(8.0, 12.2, 0.2))
    ax.set(xscale="log", yscale="log", xlabel=M_STAR)
    ax.set_ylabel(r"$A_V$ (face-on, mag)")
    p.finish("upper left")
    return fig
