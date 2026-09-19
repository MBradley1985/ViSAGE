from __future__ import annotations

from functools import lru_cache

import numpy as np


@lru_cache(maxsize=64)
def colormap_lut(name: str, n: int = 256) -> np.ndarray:
    """(n, 4) uint8 RGBA lookup table for a matplotlib colormap.

    Bin centres, matching how VTK samples its own lookup table, so the
    colours come out identical to the ones VTK would have produced.
    """
    import matplotlib

    cmap = matplotlib.colormaps[name]
    return (cmap((np.arange(n) + 0.5) / n) * 255.0).astype(np.uint8)


def scalars_to_rgba(values: np.ndarray, cmap: str, n: int = 256) -> np.ndarray:
    """Map already-normalised (0-1) scalars to RGBA, vectorised.

    Handing VTK a scalar array plus a colormap makes PyVista convert the
    values to colours one at a time in Python — hundreds of milliseconds
    for a large point cloud, and it happens on every redraw.  A table
    lookup here is the same 256-entry quantisation VTK's own lookup table
    uses, done in numpy.

    Alpha is left at full: layer opacity stays an actor property, so the
    opacity slider can still move it without rebuilding anything.
    """
    v = np.asarray(values, dtype=np.float32)
    idx = np.clip((v * n).astype(np.int32), 0, n - 1)
    return colormap_lut(cmap, n)[idx]


def cmap_css_gradient(name: str, n: int = 12) -> str:
    """CSS linear-gradient string for a matplotlib colormap."""
    import matplotlib.pyplot as plt

    cmap = plt.get_cmap(name)
    stops = []
    for i in range(n):
        t = i / (n - 1)
        r, g, b, a = cmap(float(t))
        stops.append(
            f"rgba({int(r*255)},{int(g*255)},{int(b*255)},{a:.2f}) {int(t*100)}%"
        )
    return "linear-gradient(to right, " + ", ".join(stops) + ")"


# Default scalar ranges (log10 units)
HALO_MASS_RANGE = (10.0, 15.0)  # log10(Msun)
STELLAR_MASS_RANGE = (8.0, 12.5)  # log10(Msun)
SSFR_RANGE = (-14.0, -8.0)  # log10(yr^-1)


def normalize_log(
    values: np.ndarray,
    vmin: float,
    vmax: float,
) -> np.ndarray:
    """Generic log10 normalisation to [0, 1]."""
    log_v = np.log10(np.maximum(values, 1e-30))
    return np.clip((log_v - vmin) / (vmax - vmin + 1e-10), 0.0, 1.0).astype(
        np.float32
    )


def normalize_log_mass(
    mass: np.ndarray,
    vmin: float = STELLAR_MASS_RANGE[0],
    vmax: float = STELLAR_MASS_RANGE[1],
) -> np.ndarray:
    """Map stellar or halo masses (Msun) to [0, 1] via log10."""
    log_m = np.log10(np.maximum(mass, 1.0))
    return np.clip((log_m - vmin) / (vmax - vmin + 1e-10), 0.0, 1.0)


def normalize_log_halo_mass(
    mass: np.ndarray,
    vmin: float = HALO_MASS_RANGE[0],
    vmax: float = HALO_MASS_RANGE[1],
) -> np.ndarray:
    """Map halo masses (Msun) to [0, 1] via log10."""
    log_m = np.log10(np.maximum(mass, 1.0))
    return np.clip((log_m - vmin) / (vmax - vmin + 1e-10), 0.0, 1.0)


def normalize_log_ssfr(
    ssfr: np.ndarray,
    vmin: float = SSFR_RANGE[0],
    vmax: float = SSFR_RANGE[1],
) -> np.ndarray:
    """Map specific SFR (yr^-1) to [0, 1] via log10."""
    ssfr_safe = np.maximum(ssfr, 1e-14)
    log_ssfr = np.log10(ssfr_safe)
    return np.clip((log_ssfr - vmin) / (vmax - vmin + 1e-10), 0.0, 1.0)
