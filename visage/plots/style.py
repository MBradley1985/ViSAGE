"""One look for every plot: the SAGE26 stylesheet, plasma, and the rules
for observations (always markers, in a legend of their own)."""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.figure import Figure

STYLESHEET = Path(__file__).with_name("kieren_cohare_palatino_sty.mplstyle")
MARKERS = ("o", "s", "D", "^", "v", "P", "X", "*", "<", ">", "p", "h")
# Unordered groups (reservoirs, centrals and satellites), the stylesheet's.
GROUPS = ("#0C5DA5", "#FF2C00", "#00B945", "#FF9500", "#845B97", "#9e9e9e")
FORMATS = ("png", "pdf", "jpeg", "svg")


def _colours(dark: bool) -> dict:
    """Matplotlib's colours for a light or dark background."""
    back = "black" if dark else "white"
    rc = {"figure.facecolor": back, "savefig.facecolor": back}
    if dark:
        for key in (
            "text.color",
            "axes.edgecolor",
            "axes.labelcolor",
            "xtick.color",
            "ytick.color",
            "legend.labelcolor",
        ):
            rc[key] = "white"
        rc["axes.facecolor"] = "black"
    return rc


def _rc(dark: bool) -> dict:
    rc = dict(
        matplotlib.rc_params_from_file(STYLESHEET, use_default_template=False)
    )
    rc["savefig.dpi"] = 200
    rc["axes.prop_cycle"] = rc["axes.prop_cycle"]
    latex = all(shutil.which(t) for t in ("latex", "dvipng", "gs"))
    if not latex:
        # Same look without LaTeX: a Palatino face and matching maths.
        rc["text.usetex"] = False
        rc["font.serif"] = ["Palatino", "TeX Gyre Pagella", "DejaVu Serif"]
        rc["mathtext.fontset"] = "stix"
    rc.update(_colours(dark))
    return rc


def context(dark: bool):
    """Matplotlib settings for a plot, for use in a `with`."""
    return matplotlib.rc_context(_rc(dark))


def theme(dark: bool):
    """The colours alone, for a figure with its own layout, in a `with`."""
    return matplotlib.rc_context(_colours(dark))


def plasma(n: int, dark: bool) -> np.ndarray:
    """`n` plasma colours, leaving out the end lost on the background."""
    lo, hi = (0.3, 0.98) if dark else (0.02, 0.85)
    return matplotlib.colormaps["plasma"](np.linspace(lo, hi, max(n, 1)))


def ink(dark: bool) -> str:
    """The neutral colour of lines and observations."""
    return "white" if dark else "black"


def new_figure(dark: bool, cols: int = 1, wide: bool = False, **kw):
    """A figure and its axes, sized by the stylesheet."""
    w, h = matplotlib.rcParams["figure.figsize"]
    fig = Figure(figsize=(w * cols if cols > 1 else w, h))
    if wide:
        fig.set_size_inches(w * 1.25, h)
    axes = fig.subplots(1, cols, **kw)
    for ax in np.atleast_1d(axes):
        ax._obs = []
    return fig, axes


def observed(
    ax,
    x,
    y,
    label: str,
    xerr=None,
    yerr=None,
    colour=None,
    dark: bool = False,
) -> None:
    """Observations, as markers, entered in the observations legend."""
    grey = "#c8c8c8" if dark else "#4a4a4a"
    ax.errorbar(
        x,
        y,
        xerr=xerr,
        yerr=yerr,
        fmt=MARKERS[len(ax._obs) % len(MARKERS)],
        ms=6,
        mfc="none" if colour is not None else grey,
        mec=grey if colour is None else colour,
        ecolor=grey if colour is None else colour,
        elinewidth=0.9,
        capsize=0,
        zorder=6,
    )
    ax._obs.append(
        matplotlib.lines.Line2D(
            [],
            [],
            ls="none",
            marker=MARKERS[len(ax._obs) % len(MARKERS)],
            ms=6,
            mfc="none" if colour is not None else grey,
            mec=grey if colour is None else colour,
            label=label,
        )
    )


def legends(ax, model_loc: str = "upper right", obs_loc: str = "lower left"):
    """A model legend and, apart from it, an observations legend."""
    handles, labels = ax.get_legend_handles_labels()
    size = 12 if len(labels) <= 6 else 9
    if handles:
        first = ax.legend(
            handles,
            labels,
            loc=model_loc,
            fontsize=size,
            ncol=2 if len(labels) > 8 else 1,
        )
        ax.add_artist(first)
    if ax._obs:
        ax.legend(
            handles=ax._obs,
            loc=obs_loc,
            fontsize=11 if len(ax._obs) <= 5 else 8,
            ncol=2 if len(ax._obs) > 6 else 1,
        )


def save(fig, stem: Path, formats) -> list[Path]:
    """Write the figure in each format; the PNG is always kept to show."""
    out = []
    for fmt in dict.fromkeys(["png", *formats]):
        path = stem.with_suffix(f".{'jpg' if fmt == 'jpeg' else fmt}")
        fig.savefig(path, format=fmt, bbox_inches="tight")
        out.append(path)
    return out
