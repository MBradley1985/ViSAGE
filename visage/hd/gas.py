"""3D halo gas and ICL for the HD galaxy (the "Gas" checkbox).

Same looks as the offline prototype's gas overlay, as point clouds:

* HotGas: the intracluster / intragroup medium filling Rvir (beta-model
  core 0.15 Rvir), softly and irregularly thinned around the galaxy;
  opacity 0.085 -> 0.13 with log HotGas.
* CGMgas, and mdot_stream in hot haloes: three curling inflow streams plus
  filaments, out to Rvir.
* OutflowRate / MassLoading: biconical wind along the spin axis.
* Heating > 1e40 erg/s: radio jets and lobes.
* IntraClusterStars: the warm stellar envelope in the zone the hot gas
  thins out of (always on: it is starlight, not gas).

Lengths are built in kpc and returned in the recipe's model units, galaxy
frame (spin axis = +z).
"""

from __future__ import annotations

import numpy as np

from visage.hd.model import (
    CGM_RGB,
    HOT_GAS_RGB,
    JET_RGB,
    WIND_RGB,
    GalaxyRecipe,
)
from visage.hd.particles import SPLAT_KAPPA, ParticleSet, thin

# Hot-atmosphere opacity peaks here (log M_hot >= 13); fainter haloes scale
# down from it to 65% of this at log M_hot = 10.
HOT_MAX_OPACITY = 0.13
ICL_RGB = np.array([1.0, 0.82, 0.6])


def hot_opacity(hot_gas: float) -> float:
    f = np.clip((np.log10(max(hot_gas, 1.0)) - 10.0) / 3.0, 0.0, 1.0)
    return float(HOT_MAX_OPACITY * (0.65 + 0.35 * f))


def _unit(rng, n):
    v = rng.normal(size=(n, 3))
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _radii(rng, n, density, rmax, rmin=0.0):
    """Radii drawn from a spherical density profile rho(r) (r^2 rho)."""
    r = np.linspace(rmin, rmax, 2000)
    pdf = r**2 * density(r)
    cdf = np.cumsum(pdf)
    cdf /= cdf[-1]
    return np.interp(rng.uniform(0, 1, n), cdf, r)


def _wobble(rng, dirs, amp=0.3, k=4):
    """Smooth random function on the sphere (a few random plane waves)."""
    w = np.zeros(len(dirs))
    for _ in range(k):
        kv = rng.normal(size=3) * 2.0
        w += np.cos(np.einsum("nj,j->n", dirs, kv) + rng.uniform(0, 2 * np.pi))
    return np.exp(amp * w / np.sqrt(k))


def _set(name, pos_kpc, unit_kpc, rgb, lum, radius_kpc):
    n = len(pos_kpc)
    return ParticleSet(
        name,
        (pos_kpc / unit_kpc).astype(np.float32),
        np.tile(np.asarray(rgb, np.float32), (n, 1)),
        np.asarray(lum, np.float32) * np.ones(n, np.float32),
        (np.asarray(radius_kpc) / unit_kpc * np.ones(n)).astype(np.float32),
        dusty=False,
        meta={"diffuse": False},
    )


def _scale_to(s: ParticleSet, target: float, half: float, rng, grid=160):
    """Colour the set so its projected (x-y) brightness peaks at ~target."""
    edges = np.linspace(-half, half, grid + 1)
    area = (2 * half / grid) ** 2
    img, _, _ = np.histogram2d(
        s.pos[:, 0],
        s.pos[:, 1],
        bins=[edges, edges],
        weights=s.lum * SPLAT_KAPPA * np.pi * s.radius**2,
    )
    from scipy.ndimage import gaussian_filter

    img = gaussian_filter(img / area, 2.0)
    ref = max(
        float(np.percentile(img[img > 0], 99.5)) if (img > 0).any() else 1,
        1e-12,
    )
    s.colour = (target * (s.lum / ref)[:, None] * s.rgb).astype(np.float32)
    thin(s, rng)


def build_gas(gal, rc: GalaxyRecipe) -> list[ParticleSet]:
    rng = np.random.default_rng(rc.seed + 77)
    u = rc.unit_kpc
    rvir = max(gal.rvir_kpc, 20.0)
    half = 1.05 * rvir / u
    sets = []

    if gal.hot_gas > 0:
        rcore = 0.15 * rvir
        n_c = 5000
        r = _radii(
            rng,
            n_c,
            lambda r: (1 + (r / rcore) ** 2) ** -1.0
            * np.exp(-((r / rvir) ** 8)),
            1.05 * rvir,
        )
        d = _unit(rng, n_c)
        # Soft, irregular thinning around the galaxy (never a hard edge).
        r_in = 1.2 * rc.extent * u
        keep = 1 - 0.85 * np.exp(-((r / (1.6 * r_in * _wobble(rng, d))) ** 2))
        ok = rng.uniform(0, 1, n_c) < keep
        centres = (d * r[:, None])[ok]
        k = 8  # clumps give the mottled texture
        pos = np.repeat(centres, k, axis=0) + rng.normal(
            0, 0.025 * rvir, (len(centres) * k, 3)
        )
        s = _set("hot_gas", pos, u, HOT_GAS_RGB, 1.0, 0.045 * rvir)
        _scale_to(s, hot_opacity(gal.hot_gas), half, rng)
        sets.append(s)

    stream_amp = 0.0
    if gal.cgm_gas > 0:
        stream_amp = 0.8 * float(
            np.clip((np.log10(gal.cgm_gas) - 8.5) / 3.0, 0.05, 1.0)
        )
    elif gal.hot_gas > 0 and gal.mdot_stream > 0:
        stream_amp = 0.8 * float(
            np.clip((np.log10(gal.mdot_stream) + 6.0) / 1.5, 0.3, 1.0)
        )
    if stream_amp > 0:
        sets.append(_streams(rng, rvir, u, stream_amp, half))

    if gal.outflow_rate > 0.05:
        sets.append(_wind(rng, gal, rc, half))
    if gal.heating_log > 40.0:
        sets.append(_jets(rng, gal, u, half))
    return [s for s in sets if len(s)]


def _streams(rng, rvir, u, amp, half):
    """Three curling inflow streams and a web of filaments."""
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    e1, e2, nrm = q[:, 0], q[:, 1], q[:, 2]
    pos = []
    for t0 in (
        rng.uniform(0, 2 * np.pi)
        + np.arange(3) * 2 * np.pi / 3
        + rng.normal(0, 0.4, 3)
    ):
        m = 9000
        rr = _radii(
            rng,
            m,
            # r^2 rho ~ r: the stream's light spreads out along it rather
            # than piling up where it meets the galaxy.
            lambda r: (1 + (r / (0.12 * rvir)) ** 2) ** -0.5
            / np.maximum(r, 1e-3),
            rvir,
            0.04 * rvir,
        )
        ang = t0 + 0.25 * np.log(rr / rvir)
        tilt = 0.25 * np.sin(3 * ang)
        base = (np.cos(ang)[:, None] * e1 + np.sin(ang)[:, None] * e2) + tilt[
            :, None
        ] * nrm
        base /= np.linalg.norm(base, axis=1, keepdims=True)
        w = (0.12 + 0.3 * rr / rvir) * rr * 0.28
        pos.append(base * rr[:, None] + rng.normal(0, 1, (m, 3)) * w[:, None])
    # Filaments: persistent random walks through the halo.
    for _ in range(40):
        p = _unit(rng, 1)[0] * rng.uniform(0.15, 0.85) * rvir
        step = _unit(rng, 1)[0]
        walk = []
        for _ in range(250):
            step = step + rng.normal(0, 0.25, 3)
            step /= np.linalg.norm(step)
            p = p + step * 0.006 * rvir
            walk.append(p.copy())
        pos.append(np.array(walk) + rng.normal(0, 0.006 * rvir, (250, 3)))
    pos = np.vstack(pos)
    # Strongly clumped, so the streams read as filamentary knots, not tubes.
    lum = rng.lognormal(0, 1.1, len(pos))
    s = _set("cold_streams", pos, u, CGM_RGB, lum, 0.012 * rvir)
    _scale_to(s, 0.5 * amp, half, rng)
    return s


def _wind(rng, gal, rc, half):
    u = rc.unit_kpc
    disk_r = rc.extent * u * 0.5
    length = float(np.clip(8 * gal.outflow_rate**0.35, 4, 40)) + disk_r * 0.5
    amp = float(np.clip((np.log10(gal.outflow_rate) + 1.0) / 2.5, 0.1, 1.0))
    half_open = np.deg2rad(np.clip(25 + 5 * gal.mass_loading, 20, 45))
    m = 12000
    z = rng.exponential(length, m) * rng.choice([-1, 1], m)
    rmax = 0.25 * disk_r + np.abs(z) * np.tan(half_open)
    rr = rmax * np.sqrt(rng.uniform(0, 1, m))
    phi = rng.uniform(0, 2 * np.pi, m)
    pos = np.c_[rr * np.cos(phi), rr * np.sin(phi), z]
    s = _set("wind", pos, u, WIND_RGB, rng.lognormal(0, 0.6, m), 0.6)
    _scale_to(s, 0.35 * amp, half, rng)
    return s


def _jets(rng, gal, u, half):
    amp = float(np.clip((gal.heating_log - 40.0) / 1.5, 0.15, 1.0))
    length = 15 + 25 * amp
    m = 5000
    z = rng.uniform(0, length, m) * rng.choice([-1, 1], m)
    w = 0.4 + 0.04 * np.abs(z)
    jet = np.c_[rng.normal(0, 1, m) * w, rng.normal(0, 1, m) * w, z]
    lobes = []
    for sgn in (1, -1):
        lobes.append(
            rng.normal(0, 0.25 * length, (3000, 3)) * [1, 1, 0.7]
            + [0, 0, sgn * length]
        )
    pos = np.vstack([jet] + lobes)
    lum = np.r_[np.full(m, 1.5), np.full(6000, 0.6)]
    s = _set(
        "jets",
        pos,
        u,
        JET_RGB,
        lum,
        np.r_[np.full(m, 0.5), np.full(6000, 2.5)],
    )
    _scale_to(s, 0.6 * amp, half, rng)
    return s


def build_icl(gal, rc: GalaxyRecipe) -> list[ParticleSet]:
    """IntraClusterStars in the zone around the galaxy where the hot medium
    thins: a soft warm glow plus a sprinkle of stripped stars."""
    if gal.ics <= 0:
        return []
    rng = np.random.default_rng(rc.seed + 11)
    u = rc.unit_kpc
    r_in = 1.2 * rc.extent * u

    def prof(r):
        p = (1 + (r / (0.5 * r_in)) ** 2) ** -1.2
        p *= 1 - np.exp(-((r / (0.35 * r_in)) ** 2))
        return p * np.exp(-((r / (2.2 * r_in)) ** 2))

    f = float(np.clip((np.log10(gal.ics) - 9.0) / 3.0, 0.0, 1.0))
    opacity = 0.025 + 0.1 * f
    half = 3 * r_in / u
    sets = []
    m = 40000
    pos = (
        _unit(rng, m) * _radii(rng, m, prof, 4 * r_in)[:, None] * [1, 0.8, 0.8]
    )
    glow = _set("icl_glow", pos, u, ICL_RGB, 1.0, 0.008 * r_in)
    _scale_to(glow, 0.8 * opacity, half, rng)
    sets.append(glow)
    n = int(np.clip(gal.ics / 1e8, 200, 6000))
    pos = (
        _unit(rng, n) * _radii(rng, n, prof, 4 * r_in)[:, None] * [1, 0.8, 0.8]
    )
    stars = _set(
        "icl_stars", pos, u, ICL_RGB, rng.uniform(0.3, 1.0, n), 0.004 * r_in
    )
    stars.colour = (
        np.clip(1.5 * opacity, 0.03, 0.3) * stars.lum[:, None] * stars.rgb
    ).astype(np.float32)
    sets.append(stars)
    return [s for s in sets if len(s)]
