"""Turn an HD galaxy recipe into 3D point clouds for additive splatting.

Every component of the recipe (old disk, young disk, bulge, bar, elliptical
body, clusters, HII regions, merger debris, nucleus, AGN) becomes a set of
points in the galaxy's own frame, in model length units (the disk scale
length, or a fraction of the half-light radius for ellipticals).

Brightness is calibrated so that, seen face-on, the summed splats reproduce
the offline prototype's tone-mapped image: each particle carries its share
of an asinh-compressed surface brightness.  Because the scene is drawn into
an 8-bit framebuffer, a splat dimmer than ~1/255 simply vanishes, so faint
regions are thinned (fewer, proportionally brighter particles) rather than
filled with sub-threshold ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter

from visage.hd.model import (
    CLUSTER_RGB,
    YOUNG_RGB,
    GalaxyRecipe,
    PlaneMaps,
    Points,
    _sample_map,
    build_points,
)

# Integral of one splat over the plane, in units of pi r^2 (VTK's gaussian
# point kernel has sigma ~ the scale-array radius).
SPLAT_KAPPA = 1.82
# Dimmest per-particle colour that survives the 8-bit framebuffer.
MIN_COLOUR = 0.02
# asinh stretch of the prototype's tone map.
STRETCH_Q = 40.0
# Overall exposure of the 3D model relative to the face-on calibration
# (splats overlap less evenly than a ray-marched image, so it reads dimmer).
GAIN = 2.2
# Dust layer scale height (model units), as in the offline renderer.
DUST_HZ = 0.045


@dataclass
class ParticleSet:
    """One component's points, in the galaxy frame (model units)."""

    name: str
    pos: np.ndarray  # (N, 3)
    rgb: np.ndarray  # (N, 3) unit colour
    lum: np.ndarray  # (N,) luminosity (recipe units)
    radius: np.ndarray  # (N,) splat radius, model units
    dusty: bool = True  # attenuated by the disk's dust
    colour: np.ndarray | None = None  # (N, 3) calibrated display colour
    tau_face: np.ndarray | None = None  # (N,) face-on dust column at (x, y)
    zh: np.ndarray | None = None  # (N,) height over the dust scale height
    meta: dict = field(default_factory=dict)

    def __len__(self):
        return len(self.lum)

    def take(self, keep: np.ndarray) -> None:
        for name in (
            "pos",
            "rgb",
            "lum",
            "radius",
            "colour",
            "tau_face",
            "zh",
        ):
            arr = getattr(self, name)
            if arr is not None:
                setattr(self, name, arr[keep])


# ----------------------------------------------------------------------
# Samplers
# ----------------------------------------------------------------------


def _sech2_z(rng, n, h):
    """Heights drawn from a sech^2(z/h) profile."""
    u = rng.uniform(1e-6, 1 - 1e-6, n)
    return h * np.arctanh(2 * u - 1)


def _hernquist(rng, n, a, axes=(1.0, 1.0, 1.0), rmax=60.0):
    u = rng.uniform(0, 1, n)
    s = np.sqrt(u)
    r = np.minimum(a * s / (1 - s + 1e-9), rmax * a)
    v = rng.normal(size=(n, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return v * r[:, None] * np.asarray(axes)


def _diffuse(name, pos, lum_total, rgb, dusty=True):
    n = len(pos)
    return ParticleSet(
        name,
        pos.astype(np.float32),
        np.tile(np.asarray(rgb, np.float32), (n, 1)),
        np.full(n, lum_total / max(n, 1), np.float32),
        np.zeros(n, np.float32),
        dusty=dusty,
        meta={"diffuse": True},
    )


def _from_points(p: Points, px_size: float, dusty=True) -> ParticleSet:
    """Point populations from the recipe; their PSF width (pixels at the
    prototype's 1024 px over the frame) becomes a world radius."""
    return ParticleSet(
        p.name,
        p.pos.astype(np.float32),
        p.rgb.astype(np.float32),
        p.lum.astype(np.float32),
        (p.sigma * px_size).astype(np.float32),
        dusty=dusty,
        meta={"diffuse": False},
    )


# ----------------------------------------------------------------------
# Components
# ----------------------------------------------------------------------


def build_optical(
    rc: GalaxyRecipe, maps: PlaneMaps | None, rng=None, budget=1.0
) -> list[ParticleSet]:
    """All starlight components of the recipe as particle sets."""
    rng = rng or np.random.default_rng(rc.seed + 1234)
    sets: list[ParticleSet] = []
    old_rgb = np.array(rc.old_rgb)
    bulge_rgb = np.array(rc.bulge_rgb)

    def n(k):
        return max(int(k * budget), 200)

    if rc.kind == "disk":
        m = n(140_000)
        x, y = _sample_map(maps.old, maps.half, m, rng)
        sets.append(
            _diffuse(
                "old_disk",
                np.c_[x, y, _sech2_z(rng, m, rc.hz)],
                rc.l_disk,
                old_rgb,
            )
        )
        if rc.l_young > 0:
            m = n(70_000)
            x, y = _sample_map(maps.young, maps.half, m, rng)
            sets.append(
                _diffuse(
                    "young_disk",
                    np.c_[x, y, _sech2_z(rng, m, 0.06)],
                    1.2 * rc.l_young,
                    YOUNG_RGB,
                )
            )
        if rc.l_bulge > 0:
            m = n(50_000)
            pos = _hernquist(rng, m, rc.bulge_a, (1.0, 1.0, rc.bulge_q))
            sets.append(_diffuse("bulge", pos, rc.l_bulge, bulge_rgb))
        if rc.bar_len > 0 and rc.l_bar > 0:
            m = n(30_000)
            ax_, ay_ = rc.bar_len, rc.bar_len * rc.bar_axis
            # Rejection-sample the boxy exp(-(|x/a|^2.4 + |y/b|^2.4)) profile.
            k = 4 * m
            bx = rng.uniform(-2.5 * ax_, 2.5 * ax_, k)
            by = rng.uniform(-2.5 * ay_, 2.5 * ay_, k)
            w = np.exp(
                -((np.abs(bx) / ax_) ** 2.4 + (np.abs(by) / ay_) ** 2.4)
            )
            keep = rng.uniform(0, 1, k) < w
            bx, by = bx[keep][:m], by[keep][:m]
            pos = np.c_[bx, by, _sech2_z(rng, len(bx), 0.12)]
            sets.append(_diffuse("bar", pos, rc.l_bar, bulge_rgb))
    else:
        a, b, c = rc.axes
        sets.append(
            _diffuse(
                "core",
                _hernquist(rng, n(70_000), 0.22, (a, b, c)),
                rc.core_frac,
                bulge_rgb,
                dusty=False,
            )
        )
        sets.append(
            _diffuse(
                "envelope",
                _hernquist(rng, n(130_000), rc.env_a, (a, b, c)),
                1 - rc.core_frac,
                old_rgb * 0.95 + 0.05,
                dusty=False,
            )
        )

    # Point populations (clusters, HII, field stars, globulars, debris,
    # nuclear ring).  Prototype PSF pixels -> model units.
    px = 2 * rc.extent * (1.3 if rc.kind == "disk" else 1.0) / 1024
    for p in build_points(rc, maps):
        sets.append(_from_points(p, 1.6 * px, dusty=rc.kind == "disk"))

    # Nucleus and AGN glow at the centre.
    if rc.l_nucleus > 0:
        sets.append(
            ParticleSet(
                "nucleus",
                np.zeros((1, 3), np.float32),
                np.array([[1.0, 0.93, 0.85]], np.float32),
                np.array([rc.l_nucleus], np.float32),
                np.array([max(rc.nucleus_sigma, 0.6 * px)], np.float32),
                meta={"diffuse": False},
            )
        )
    if rc.agn > 0:
        # Bright core plus a soft scattered-light halo ("glow" style).
        core_l = 8 * rc.agn
        sets.append(
            ParticleSet(
                "agn",
                np.zeros((2, 3), np.float32),
                np.array([[0.85, 0.92, 1.0]] * 2, np.float32),
                np.array([core_l, 0.6 * core_l], np.float32),
                np.array([1.2 * px, 18 * px], np.float32),
                meta={"diffuse": False, "exclude_white": True},
            )
        )
    return [s for s in sets if len(s)]


# ----------------------------------------------------------------------
# Calibration
# ----------------------------------------------------------------------


def calibrate(
    sets: list[ParticleSet],
    half: float,
    grid: int = 256,
    white: float | None = None,
    rng=None,
) -> float:
    """Give every particle a display colour and (for diffuse sets) a splat
    radius, so the face-on sum reproduces the asinh-stretched image.

    Returns the white level used (surface brightness mapped to ~1).
    """
    rng = rng or np.random.default_rng(7)
    cell = 2 * half / grid
    area = cell * cell
    edges = np.linspace(-half, half, grid + 1)

    def lookup(img, x, y):
        ix = np.clip(((x + half) / cell).astype(int), 0, grid - 1)
        iy = np.clip(((y + half) / cell).astype(int), 0, grid - 1)
        return img[ix, iy]

    xs = np.concatenate([s.pos[:, 0] for s in sets])
    ys = np.concatenate([s.pos[:, 1] for s in sets])
    ls = np.concatenate([s.lum for s in sets])
    surf, _, _ = np.histogram2d(xs, ys, bins=[edges, edges], weights=ls)
    surf = gaussian_filter(surf, 1.2) / area

    if white is None:
        excl = np.concatenate(
            [np.full(len(s), bool(s.meta.get("exclude_white"))) for s in sets]
        )
        s_at = lookup(surf, xs, ys)[~excl]
        white = float(np.percentile(s_at, 99.9)) if len(s_at) else 1.0
        white = max(white, 1e-12)

    for s in sets:
        x, y = s.pos[:, 0], s.pos[:, 1]
        if s.meta.get("diffuse"):
            cnt, _, _ = np.histogram2d(x, y, bins=[edges, edges])
            cnt = gaussian_filter(cnt, 1.0)
            spacing = np.sqrt(area / np.maximum(lookup(cnt, x, y), 0.05))
            s.radius = np.clip(1.6 * spacing, 0.02 * cell, 40 * cell).astype(
                np.float32
            )
        S = np.maximum(lookup(surf, x, y), 1e-12)
        D = np.arcsinh(STRETCH_Q * S / white) / np.arcsinh(STRETCH_Q)
        c = GAIN * s.lum * (D / S) / (SPLAT_KAPPA * np.pi * s.radius**2)
        if not s.meta.get("diffuse") and not s.meta.get("exclude_white"):
            # Compact sources: cap each one so dense groups of clusters and
            # HII knots don't pile up into a flat white blob.
            c = np.minimum(
                c, 0.3 if s.name.startswith(("hii", "ring_hii")) else 0.6
            )
        s.colour = (c[:, None] * s.rgb).astype(np.float32)
        thin(s, rng)
    return white


def thin(s: ParticleSet, rng) -> None:
    """Drop sub-threshold particles, brightening the survivors to keep the
    expected light: keep with p = c / MIN_COLOUR, colour /= p."""
    peak = s.colour.max(axis=1)
    p = np.clip(peak / MIN_COLOUR, 0.0, 1.0)
    keep = rng.uniform(0, 1, len(p)) < p
    s.take(keep)
    s.colour = s.colour / np.maximum(p[keep], 1e-6)[:, None]
    s.colour = np.minimum(s.colour, 4.0).astype(np.float32)


def attach_dust(sets: list[ParticleSet], maps: PlaneMaps | None) -> None:
    """Record each dusty particle's face-on dust column and its height over
    the dust layer, for the view-dependent attenuation."""
    for s in sets:
        if maps is None or not s.dusty:
            s.tau_face = None
            s.zh = None
            continue
        x = s.pos[:, 0].astype(np.float64)
        y = s.pos[:, 1].astype(np.float64)
        s.tau_face = maps.sample("dust", x, y).astype(np.float32)
        s.zh = (s.pos[:, 2] / DUST_HZ).astype(np.float32)
        # Typical path through the dusty disk to its edge, in dust heights.
        s.meta["path_h"] = float(0.5 * maps.half / DUST_HZ)


def attenuation(s: ParticleSet, view_dir_gal: np.ndarray) -> np.ndarray | None:
    """Per-channel transmission for a set seen from `view_dir_gal` (unit
    vector from the galaxy toward the camera, galaxy frame).

    Exact column through a sech^2 dust layer of finite extent: along the
    line of sight the height goes z -> z + s cos(i) for a path s up to the
    disk's edge (S), so

        tau = tau_face / (2 |cos i|) * |tanh((z + S cos i) / h) - tanh(z / h)|

    which is the usual slab result face-on and, edge-on, tends to
    tau_face * S / (2h) * sech^2(z / h): a dark lane along the midplane.
    """
    if s.tau_face is None:
        return None
    from visage.hd.model import DUST_K

    c = float(view_dir_gal[2])
    S_h = float(s.meta.get("path_h", 100.0))  # disk path length / dust h
    zh = s.zh.astype(np.float64)
    if abs(c) > 1e-4:
        tau = (
            s.tau_face
            / (2 * abs(c))
            * np.abs(np.tanh(zh + S_h * c) - np.tanh(zh))
        )
    else:
        tau = s.tau_face * S_h / 2 / np.cosh(np.clip(zh, -30, 30)) ** 2
    return np.exp(-tau[:, None] * DUST_K[None, :]).astype(np.float32)
