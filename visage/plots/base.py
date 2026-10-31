"""What every plot shares: the registry, its options and its drawing."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from visage.plots import style

SSFR_CUT = -11.0  # log10 /yr, between star-forming and quiescent
MAX_POINTS = 30000  # drawn in a scatter
MIN_IN_BIN = 5  # galaxies a median needs
F_BARYON = 0.17
PLOTS: dict = {}


def plot(section, key, title, needs=(), modes=("box", "cone"), group=True):
    """Register a plot. `needs`: fields it reads, `modes`: where it shows,
    `group`: whether it can be made for a group."""

    def add(fn):
        PLOTS[key] = dict(
            fn=fn,
            section=section,
            kind=fn.__module__.rsplit(".", 1)[-1],
            title=title,
            needs=tuple(needs),
            modes=modes,
            group=group,
        )
        return fn

    return add


@dataclass
class Options:
    """The panel's choices for a plot."""

    scatter: bool = False
    dark: bool = False
    colour_by: str = ""
    xscale: str = ""
    yscale: str = ""
    limits: dict = field(default_factory=dict)


COLOUR_LABELS = {
    "StellarMass": r"$M_\star\ (M_\odot)$",
    "Mvir": r"$M_{\rm vir}\ (M_\odot)$",
    "ColdGas": r"$M_{\rm cold}\ (M_\odot)$",
    "BlackHoleMass": r"$M_{\rm BH}\ (M_\odot)$",
    "SFR": r"${\rm SFR}\ (M_\odot\,{\rm yr}^{-1})$",
    "sSFR": r"$s{\rm SFR}\ ({\rm yr}^{-1})$",
    "redshift": r"$z$",
}


class Plot:
    """One plot being drawn: its galaxies, options and figure."""

    def __init__(self, sample, views, options) -> None:
        self.s = sample  # the galaxies, for Local plots
        self.views = views  # one Sample per snapshot, for History
        self.o = options
        self.rng = np.random.default_rng(2222)
        self.mappable = None

    def figure(self, cols: int = 1, wide: bool = False, **kw):
        self.fig, self.axes = style.new_figure(self.o.dark, cols, wide, **kw)
        return self.fig, self.axes

    @property
    def ink(self) -> str:
        return style.ink(self.o.dark)

    def dilute(self, idx: np.ndarray, n: int = MAX_POINTS) -> np.ndarray:
        if len(idx) <= n:
            return idx
        return np.sort(self.rng.choice(idx, n, replace=False))

    def relation(
        self,
        ax,
        x,
        y,
        edges,
        ok=None,
        label="Model",
        colour=None,
        log_y=True,
        s=None,
        band=True,
        ls="-",
    ):
        """A model relation: its median and 1-sigma band in bins of x, or
        each galaxy as a point, as chosen in the panel."""
        s = s or self.s
        colour = colour if colour is not None else self.ink
        good = np.isfinite(x) & np.isfinite(y) & (x > 0)
        if log_y:
            good &= y > 0
        if ok is not None:
            good &= ok
        idx = np.flatnonzero(good)
        if not len(idx):
            return
        if self.o.scatter:
            self._points(ax, x, y, idx, label, colour, s)
            return
        med, lo, hi, centres = binned(x[idx], y[idx], edges, log_y)
        keep = np.isfinite(med)
        if band:
            ax.fill_between(
                centres[keep],
                lo[keep],
                hi[keep],
                color=colour,
                alpha=0.22,
                lw=0,
            )
        ax.plot(centres[keep], med[keep], color=colour, label=label, ls=ls)

    def _points(self, ax, x, y, idx, label, colour, s) -> None:
        idx = self.dilute(idx)
        if self.o.colour_by:
            c = s(self.o.colour_by)[idx].astype(float)
            pos = c > 0
            if self.o.colour_by != "redshift":
                c = np.log10(np.where(pos, c, np.nan))
            self.mappable = ax.scatter(
                x[idx],
                y[idx],
                c=c,
                cmap="plasma",
                s=3,
                alpha=0.7,
                lw=0,
                rasterized=True,
            )
            return
        ax.scatter(
            x[idx],
            y[idx],
            color=colour,
            s=2,
            alpha=0.5,
            lw=0,
            rasterized=True,
            label=label,
        )

    def mass_function(
        self, ax, values, edges, label, colour=None, ls="-", s=None
    ):
        """Number density per dex (a count per dex without a volume)."""
        s = s or self.s
        centres, phi = density(values, edges, s.volume)
        keep = phi > 0
        ax.plot(
            centres[keep],
            phi[keep],
            color=self.ink if colour is None else colour,
            ls=ls,
            label=label,
        )

    def phi_label(self, ax, s=None) -> None:
        s = s or self.s
        ax.set_yscale("log")
        ax.set_ylabel(
            r"$\phi\ ({\rm Mpc}^{-3}\,{\rm dex}^{-1})$"
            if s.volume
            else r"$N\ ({\rm dex}^{-1})$"
        )

    def finish(self, model_loc="upper right", obs_loc="lower left") -> None:
        """The panel's axis choices, legends and any colour bar."""
        o = self.o
        axes = np.atleast_1d(self.axes)
        for ax in axes:
            if o.xscale:
                ax.set_xscale(o.xscale)
            if o.yscale:
                ax.set_yscale(o.yscale)
            xlim = (o.limits.get("xmin"), o.limits.get("xmax"))
            ylim = (o.limits.get("ymin"), o.limits.get("ymax"))
            if any(v is not None for v in xlim):
                ax.set_xlim(*xlim)
            if any(v is not None for v in ylim):
                ax.set_ylim(*ylim)
            style.legends(ax, model_loc, obs_loc)
        if self.mappable is not None:
            bar = self.fig.colorbar(self.mappable, ax=list(axes), pad=0.02)
            name = COLOUR_LABELS.get(o.colour_by, o.colour_by)
            bar.set_label(
                name if o.colour_by == "redshift" else r"$\log_{10}$ " + name
            )


def log_edges(lo: float, hi: float, dex: float) -> np.ndarray:
    """Bin edges in linear units, evenly spaced in log10."""
    return 10.0 ** np.arange(lo, hi + dex / 2, dex)


def binned(x, y, edges, log_y=True):
    """Median and 16th/84th percentiles of y in bins of x; log-mean bin
    centres.  log_y only keeps the percentiles of a log axis positive."""
    med, lo, hi = (np.full(len(edges) - 1, np.nan) for _ in range(3))
    which = np.digitize(x, edges) - 1
    for i in range(len(edges) - 1):
        v = y[which == i]
        if len(v) >= MIN_IN_BIN:
            lo[i], med[i], hi[i] = np.percentile(v, [16, 50, 84])
    if log_y:
        lo = np.where(lo > 0, lo, np.nan)
    return med, lo, hi, np.sqrt(edges[:-1] * edges[1:])


def density(values, edges, volume):
    """Bin centres and counts per dex, per Mpc^3 if there's a volume."""
    counts, _ = np.histogram(values[values > 0], bins=edges)
    dex = np.log10(edges[1:] / edges[:-1])
    return np.sqrt(edges[:-1] * edges[1:]), counts / dex / (volume or 1.0)
