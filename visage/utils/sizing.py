from __future__ import annotations

import numpy as np

from visage.utils.colormap import HALO_MASS_RANGE, STELLAR_MASS_RANGE

# Point size bounds in screen pixels
HALO_SIZE_BINS = [25.0, 30.0, 35.0, 40.0, 60.0]
GALAXY_SIZE_SCALE = 0.17


def halo_point_sizes(
    masses: np.ndarray,
    size_min: float = HALO_SIZE_BINS[0],
    size_max: float = HALO_SIZE_BINS[-1],
    mass_range: tuple[float, float] = HALO_MASS_RANGE,
) -> np.ndarray:
    """Scale halo point sizes by Mvir (Msun) using a fixed log10 range.

    Fixed range prevents flickering when the mass distribution changes
    between snapshots.
    """
    if len(masses) == 0:
        return np.array([], dtype=np.float32)
    log_m = np.log10(np.maximum(masses, 1.0))
    vmin, vmax = mass_range
    norm = np.clip((log_m - vmin) / (vmax - vmin + 1e-10), 0.0, 1.0)
    return (size_min + norm * (size_max - size_min)).astype(np.float32)


def galaxy_point_sizes(
    stellar_mass: np.ndarray,
    size_min: float = HALO_SIZE_BINS[0] * GALAXY_SIZE_SCALE,
    size_max: float = HALO_SIZE_BINS[-1] * GALAXY_SIZE_SCALE,
    mass_range: tuple[float, float] = STELLAR_MASS_RANGE,
) -> np.ndarray:
    """Scale galaxy point sizes by stellar mass (Msun) using a fixed log10 range."""
    if len(stellar_mass) == 0:
        return np.array([], dtype=np.float32)
    log_m = np.log10(np.maximum(stellar_mass, 1.0))
    vmin, vmax = mass_range
    norm = np.clip((log_m - vmin) / (vmax - vmin + 1e-10), 0.0, 1.0)
    return (size_min + norm * (size_max - size_min)).astype(np.float32)


def galaxy_world_radii(
    stellar_mass: np.ndarray,
    r_min: float = 0.025,  # Mpc/h  (low-mass end)
    r_max: float = 0.35,  # Mpc/h  (high-mass end)
    mass_range: tuple[float, float] = STELLAR_MASS_RANGE,
) -> np.ndarray:
    """Per-galaxy world-space gaussian radius (Mpc/h), scaling with stellar mass."""
    if len(stellar_mass) == 0:
        return np.array([], dtype=np.float32)
    log_m = np.log10(np.maximum(stellar_mass, 1.0))
    vmin, vmax = mass_range
    norm = np.clip((log_m - vmin) / (vmax - vmin + 1e-10), 0.0, 1.0)
    return (r_min + norm * (r_max - r_min)).astype(np.float32)


def galaxy_world_radii_rvir(
    rvir: np.ndarray,
    mvir_raw: np.ndarray | None = None,
    scale: float = 1.0,
    r_min: float = 0.02,  # Mpc/h visibility floor
) -> np.ndarray:
    """Per-galaxy world-space gaussian radius (Mpc/h): the subhalo Rvir.

    The whole layered galaxy composition (outer CGM/Hot envelope, cold-gas
    envelope, focus-only disk/bulge) is keyed off this radius, so a galaxy's
    rendered extent is its subhalo's virial radius rather than a fixed
    stellar-mass mapping.

    Where Rvir is missing (<= 0), falls back to the analytic virial radius
    of ``mvir_raw`` (raw SAGE units, 10^10 Msun/h; Δ=200 × ρ_crit), then to
    the ``r_min`` visibility floor.
    """
    if len(rvir) == 0:
        return np.array([], dtype=np.float32)
    r = np.asarray(rvir, dtype=np.float64).copy()
    bad = ~(r > 0)
    if mvir_raw is not None and np.any(bad):
        m = np.maximum(  # Msun/h
            np.asarray(mvir_raw, dtype=np.float64)[bad] * 1.0e10, 1.0
        )
        rho_crit = 2.775e11  # h^2 Msun / Mpc^3
        r[bad] = (3.0 * m / (4.0 * np.pi * 200.0 * rho_crit)) ** (1.0 / 3.0)
    return np.maximum(r * scale, r_min).astype(np.float32)


# Neighbours further away than this many of their own splat radii are
# ignored by `glow_crowding` (their share of the pile-up is under 1%).
_CROWD_REACH = 8.0


def glow_crowding(positions: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """How many galaxy glows overlap at each galaxy, on average over
    viewing directions (1 = only its own).

    A splat is a gaussian of width ``sigma``.  Seen from a random direction,
    a neighbour at 3D distance d adds, on average, D(x) / x of its peak
    brightness at this galaxy's position on screen, where x = d / (sigma *
    sqrt(2)) and D is Dawson's integral (the isotropic average of the
    projected gaussian).  Averaging over directions keeps the estimate the
    same however the camera turns, so it is computed once per snapshot.
    """
    from scipy.spatial import cKDTree
    from scipy.special import dawsn

    pos = np.asarray(positions, dtype=np.float64)
    sig = np.maximum(np.asarray(sigma, dtype=np.float64), 1e-6)
    n = len(pos)
    out = np.ones(n)
    if n < 2:
        return out
    tree = cKDTree(pos)
    # Neighbours are found per band of splat size, each band searched out
    # to the reach of its largest splat: one search at the reach of the
    # largest splat overall (a cluster's) would test every pair in the box.
    lo, hi = np.log(sig.min()), np.log(sig.max())
    edges = np.exp(np.linspace(lo, hi, max(2, int((hi - lo) / 0.4) + 2)))
    edges[-1] = np.inf
    band = np.searchsorted(edges, sig, side="right") - 1
    for b in np.unique(band):
        src = np.flatnonzero(band == b)
        reach = _CROWD_REACH * sig[src].max()
        pairs = cKDTree(pos[src]).sparse_distance_matrix(
            tree, reach, output_type="ndarray"
        )
        j, i, d = src[pairs["i"]], pairs["j"], pairs["v"]
        keep = (i != j) & (d < _CROWD_REACH * sig[j])
        j, i, d = j[keep], i[keep], d[keep]
        x = np.maximum(d / (np.sqrt(2.0) * sig[j]), 1e-6)
        out += np.bincount(i, dawsn(x) / x, minlength=n)
    return out


def halo_world_radii(
    masses: np.ndarray,
    r_min: float = 0.15,  # Mpc/h  (low-mass end)
    r_max: float = 1.5,  # Mpc/h  (high-mass end)
    mass_range: tuple[float, float] = HALO_MASS_RANGE,
) -> np.ndarray:
    """Per-halo world-space gaussian radius (Mpc/h), scaling with Mvir."""
    if len(masses) == 0:
        return np.array([], dtype=np.float32)
    log_m = np.log10(np.maximum(masses, 1.0))
    vmin, vmax = mass_range
    norm = np.clip((log_m - vmin) / (vmax - vmin + 1e-10), 0.0, 1.0)
    return (r_min + norm * (r_max - r_min)).astype(np.float32)


def size_bin_mask(
    sizes: np.ndarray, bin_edges: list[float]
) -> list[np.ndarray]:
    """Return a boolean mask per size bin for split-bin rendering."""
    masks = []
    for i, edge in enumerate(bin_edges):
        lo = bin_edges[i - 1] if i > 0 else 0.0
        if i < len(bin_edges) - 1:
            masks.append((sizes >= lo) & (sizes < edge))
        else:
            masks.append(sizes >= lo)
    return masks
