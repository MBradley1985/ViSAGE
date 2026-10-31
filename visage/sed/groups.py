"""Galaxy groups found in redshift space, and how they compare with SAGE26's
true haloes.

The recipe of Van Kempen et al. (2024; 2025), made with Lambert et al.'s
(2020) probabilistic friends-of-friends: over many trials of random linking
lengths, only links that recur are kept. Two passes find the large groups with
looser lengths, then the small ones among the galaxies left. Projected lengths
grow with distance as the luminosity function's integral falls, so a
flux-limited sample's groups stay comparable (Huchra & Geller 1982).

Masses are the calibrated virial estimator of Van Kempen et al. (2025).
Groups are scored with bijective matching (Robotham et al. 2011): a group and
a halo match if each holds more than half of the other's galaxies.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

G_MPC = 4.301e-9  # Mpc (km/s)^2 / M_sun
C_KMS = 299792.458
V_FID = 1000.0  # km/s, the fiducial velocity (Huchra & Geller 1982)
MIN_PASS1 = 10  # groups this big are kept from the first pass
# r band luminosity function, h = 1 (Blanton et al. 2003).
LF_MSTAR, LF_ALPHA = -20.44, -1.05
# Modified virial theorem, h = 0.7 (Van Kempen et al. 2025, table 1).
MVT = {"a": 1.030, "s": 244.634, "n1": -1.989}
MVT |= {"b": 0.213, "r": 0.369, "n2": -1.591, "h": 0.7}


@dataclass(frozen=True)
class Pass:
    d: tuple[float, float]  # linking length range, Mpc
    v: tuple[float, float]  # km/s
    d_max: float  # hard limits
    v_max: float
    cutoff: float  # a link must recur in this share of trials
    trials: int = 200


# Van Kempen et al. 2024, table 2.
PASSES = (
    Pass((0.075, 0.275), (75.0, 800.0), 0.95, 3400.0, 0.4),
    Pass((0.05, 0.25), (50.0, 550.0), 0.75, 1700.0, 0.35),
)


def _scale(cz, mag_limit: float, hubble_h: float) -> np.ndarray:
    """Factor on the projected linking length at velocity `cz`: the cube
    root of the luminosity function's integral at the fiducial velocity over
    its integral at `cz`, for a survey limit (Lambert et al. 2020, eq. 2)."""
    mags = np.linspace(-26.0, -8.0, 1801)
    x = 10 ** (0.4 * (LF_MSTAR - mags))
    phi = x ** (LF_ALPHA + 1) * np.exp(-x)
    cum = np.cumsum(phi)

    def integral(v):
        # (magnitudes are for H0 = 100, as the luminosity function)
        limit = mag_limit - 25 - 5 * np.log10(np.maximum(v, V_FID) / 100.0)
        return np.interp(limit, mags, cum)

    return (integral(cz) / integral(np.array(V_FID))) ** (-1 / 3)


def _one_pass(cz, unit, scale, step: Pass, hubble_h: float, rng):
    """Galaxy labels from `step`: links that recur over its trials."""
    h0 = 100.0 * hubble_h
    reach = step.d_max * 2 * h0 / max(float(cz.min()), 100.0)
    tree = cKDTree(unit)
    pairs = tree.query_pairs(min(reach, 2.0), output_type="ndarray")
    i, j = pairs[:, 0], pairs[:, 1]
    dv = np.abs(cz[i] - cz[j])
    chord = 0.5 * np.linalg.norm(unit[i] - unit[j], axis=1)
    sep = chord * (cz[i] + cz[j]) / h0
    near = (dv <= step.v_max) & (sep <= step.d_max)
    i, j, dv, sep = i[near], j[near], dv[near], sep[near]
    grow = 0.5 * (scale[i] + scale[j])
    n = len(cz)
    weight = np.zeros(len(i))
    for _ in range(step.trials):
        link = (sep <= rng.uniform(*step.d) * grow) & (
            dv <= rng.uniform(*step.v)
        )
        graph = coo_matrix(
            (np.ones(link.sum()), (i[link], j[link])), shape=(n, n)
        )
        lab = connected_components(graph, directed=False)[1]
        weight += lab[i] == lab[j]
    keep = weight / step.trials >= step.cutoff
    graph = coo_matrix((np.ones(keep.sum()), (i[keep], j[keep])), shape=(n, n))
    return connected_components(graph, directed=False)[1]


def find_groups(
    ra, dec, z_obs, mag_limit, hubble_h, seed: int = 0, passes=PASSES
) -> np.ndarray:
    """Group label of each galaxy; every galaxy has one, singles included."""
    ra_r, dec_r = np.deg2rad(ra), np.deg2rad(dec)
    unit = np.c_[
        np.cos(dec_r) * np.cos(ra_r),
        np.cos(dec_r) * np.sin(ra_r),
        np.sin(dec_r),
    ]
    cz = C_KMS * np.asarray(z_obs, float)
    scale = _scale(cz, mag_limit, hubble_h)
    rng = np.random.default_rng(seed)
    labels = np.full(len(cz), -1)
    left = np.arange(len(cz))
    next_label = 0
    for k, step in enumerate(passes):
        lab = _one_pass(cz[left], unit[left], scale[left], step, hubble_h, rng)
        size = np.bincount(lab)[lab]
        last = k == len(passes) - 1
        take = np.ones(len(lab), bool) if last else size >= MIN_PASS1
        _, new = np.unique(lab[take], return_inverse=True)
        labels[left[take]] = new + next_label
        next_label += new.max(initial=-1) + 1
        left = left[~take]
    return labels


def bijective(groups, haloes, n_min: int = 2) -> dict:
    """Bijective purity and completeness of groups of at least `n_min`
    galaxies against haloes with as many (Robotham et al. 2011)."""
    _, g = np.unique(groups, return_inverse=True)
    _, h = np.unique(haloes, return_inverse=True)
    n_g, n_h = np.bincount(g), np.bincount(h)
    pair, count = np.unique(np.c_[g, h], axis=0, return_counts=True)
    match = (count / n_g[pair[:, 0]] > 0.5) & (count / n_h[pair[:, 1]] > 0.5)
    big = (n_g[pair[:, 0]] >= n_min) & (n_h[pair[:, 1]] >= n_min)
    good = pair[match & big]
    total_g, total_h = (n_g >= n_min).sum(), (n_h >= n_min).sum()
    return {
        "n_groups": int(total_g),
        "n_haloes": int(total_h),
        "purity": len(good) / max(total_g, 1),
        "completeness": len(good) / max(total_h, 1),
    }


def add_groups(cat: dict, mag_limit: float, hubble_h: float) -> dict:
    """`cat` with each galaxy's group and how many galaxies are in it, for
    the galaxies with a fibre: collided ones have no redshift (group -1)."""
    n = len(cat["ra"])
    label = np.full(n, -1)
    size = np.zeros(n, int)
    ok = ~cat["fibre_collided"]
    found = find_groups(
        cat["ra"][ok], cat["dec"][ok], cat["z_obs"][ok], mag_limit, hubble_h
    )
    label[ok] = found
    size[ok] = np.bincount(found)[found]
    return cat | {"group": label, "group_n": size}


def virial_mass(sigma, radius, hubble_h: float):
    """Halo mass (M_sun/h) from the velocity dispersion (km/s) and maximum
    projected radius (Mpc), by the modified virial theorem."""
    r_lim = MVT["r"] * MVT["h"] / hubble_h
    a_s = MVT["a"] * ((sigma / MVT["s"]) ** MVT["n1"] - 1)
    a_r = MVT["b"] * ((radius / r_lim) ** MVT["n2"] - 1)
    a = (
        5 / 3
        + np.where(sigma <= MVT["s"], a_s, 0.0)
        + np.where(radius <= r_lim, a_r, 0.0)
    )
    return a * sigma**2 * radius / G_MPC


def group_table(ra, dec, z_obs, groups, hubble_h, n_min=3) -> dict:
    """Per group of at least `n_min`: members, redshift, gapper velocity
    dispersion (km/s; Beers et al. 1990), maximum projected radius from the
    median centre (Mpc) and modified virial mass (M_sun/h)."""
    out = {k: [] for k in ("label", "n", "z", "sigma", "radius", "mass")}
    order = np.argsort(groups)
    labels, first, counts = np.unique(
        groups[order], return_index=True, return_counts=True
    )
    for lab, s, n in zip(labels, first, counts, strict=True):
        if n < n_min:
            continue
        m = order[s : s + n]
        z0 = float(np.median(z_obs[m]))
        v = np.sort(C_KMS * (z_obs[m] - z0) / (1 + z0))
        w = np.arange(1, n) * np.arange(n - 1, 0, -1)
        gap = np.sqrt(np.pi) / (n * (n - 1)) * np.sum(w * np.diff(v))
        sigma = gap * np.sqrt(n / (n - 1.0))
        dx = np.deg2rad(ra[m] - np.median(ra[m])) * np.cos(np.deg2rad(dec[m]))
        dy = np.deg2rad(dec[m] - np.median(dec[m]))
        d_a = C_KMS * z0 / (100.0 * hubble_h) / (1 + z0)
        radius = d_a * float(np.max(np.hypot(dx, dy)))
        out["label"].append(lab)
        out["n"].append(n)
        out["z"].append(z0)
        out["sigma"].append(sigma)
        out["radius"].append(radius)
    res = {k: np.asarray(v) for k, v in out.items() if k != "mass"}
    res["mass"] = virial_mass(res["sigma"], res["radius"], hubble_h)
    return res
