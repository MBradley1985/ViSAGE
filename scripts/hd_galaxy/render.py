"""Emission + absorption ray-march of a procedural galaxy, in numpy.

The camera looks down -Z of the observer frame.  The volume is cut into
slabs perpendicular to the line of sight and integrated front to back, so
dust in front of a star dims and reddens it and dust behind it does not.
Point populations (clusters, HII regions, globulars) are dimmed by the
optical depth accumulated in front of their own slab.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter

from model import (
    BULGE_RGB,
    DUST_K,
    OLD_RGB,
    YOUNG_RGB,
    GalaxyRecipe,
    PlaneMaps,
    Points,
)


def rot(inc_deg, pa_deg):
    """Matrix taking galaxy-frame vectors to the observer frame."""
    i, p = np.deg2rad(inc_deg), np.deg2rad(pa_deg)
    rx = np.array(
        [[1, 0, 0], [0, np.cos(i), -np.sin(i)], [0, np.sin(i), np.cos(i)]]
    )
    rz = np.array(
        [[np.cos(p), -np.sin(p), 0], [np.sin(p), np.cos(p), 0], [0, 0, 1]]
    )
    return rz @ rx


def sech2(z, h):
    return 1.0 / np.cosh(np.clip(z / h, -30, 30)) ** 2 / (2 * h)


def hernquist(x, y, z, a, q=1.0, axes=(1.0, 1.0, 1.0)):
    """Unit-mass Hernquist density, optionally flattened / triaxial."""
    bx, by, bz = axes
    m = np.sqrt((x / bx) ** 2 + (y / by) ** 2 + (z / (bz * q)) ** 2)
    m = np.maximum(m, 0.004)
    return a / (2 * np.pi * bx * by * bz * q) / (m * (m + a) ** 3)


@dataclass
class Layers:
    """Separately accumulated light (linear RGB) for diagnostics."""

    disk: np.ndarray
    bulge: np.ndarray
    young: np.ndarray
    points: dict
    tau_v: np.ndarray  # total V-band optical depth through each pixel
    half_width: float = 0.0  # frame half-width, model units

    @property
    def total(self):
        img = self.disk + self.bulge + self.young
        for p in self.points.values():
            img = img + p
        return img


def render(
    rc: GalaxyRecipe,
    maps: PlaneMaps | None,
    pts: list[Points],
    inc=0.0,
    pa=0.0,
    npix=1024,
    dust_on=True,
    frame_scale=1.0,
) -> Layers:
    R = rot(inc, pa)
    Rt = R.T
    E = rc.extent * (1.3 if rc.kind == "disk" else 1.0) * frame_scale
    ax = np.linspace(-E, E, npix)
    X, Y = np.meshgrid(ax, ax[::-1])  # row 0 = top of image
    pix = ax[1] - ax[0]

    if rc.kind == "disk":
        # Depth follows the galaxy, not the frame: a wide (e.g. Rvir) frame
        # would otherwise make slabs thicker than the disk.
        zmax = min(E, rc.extent * 1.7) * abs(np.sin(np.deg2rad(inc))) + 1.2
        dz_target = 0.02
    else:
        zmax = min(E, rc.extent * 1.5)
        dz_target = 0.04
    nsl = int(np.clip(2 * zmax / dz_target, 80, 360))
    zs = np.linspace(zmax, -zmax, nsl)  # front (toward viewer) to back
    dz = zs[0] - zs[1]

    # Plane-map normalisation so each component's total light = its L.
    if maps is not None:
        dA = (2 * maps.half / (maps.old.shape[0] - 1)) ** 2
        n_old = 1.0 / (maps.old.sum() * dA)
        n_young = 1.0 / (maps.young.sum() * dA)

    disk = np.zeros((npix, npix, 3), np.float32)
    bulge = np.zeros_like(disk)
    young = np.zeros_like(disk)
    tau = np.zeros((npix, npix), np.float32)

    # Bin points into slabs once.
    pt_obs = [np.einsum("ij,nj->ni", R, p.pos) for p in pts]
    pt_slab = [
        np.clip(((zmax - po[:, 2]) / dz).astype(int), 0, nsl - 1)
        for po in pt_obs
    ]
    pt_att = [np.ones((len(po), 3)) for po in pt_obs]

    bar_ax = rc.bar_len
    old_rgb = np.array(rc.old_rgb)
    bulge_rgb = np.array(rc.bulge_rgb)
    icl = np.zeros_like(disk)
    for k, z in enumerate(zs):
        # Observer -> galaxy coordinates for this slab.
        xg = Rt[0, 0] * X + Rt[0, 1] * Y + Rt[0, 2] * z
        yg = Rt[1, 0] * X + Rt[1, 1] * Y + Rt[1, 2] * z
        zg = Rt[2, 0] * X + Rt[2, 1] * Y + Rt[2, 2] * z

        if rc.kind == "disk":
            e_disk = (
                rc.l_disk
                * n_old
                * maps.sample("old", xg, yg)
                * sech2(zg, rc.hz)
            )
            e_young = (
                rc.l_young
                * 1.2
                * n_young
                * maps.sample("young", xg, yg)
                * sech2(zg, 0.06)
            )
            e_bul = rc.l_bulge * hernquist(xg, yg, zg, rc.bulge_a, rc.bulge_q)
            if bar_ax > 0:
                ax_, ay_ = bar_ax, bar_ax * rc.bar_axis
                bar = np.exp(
                    -((np.abs(xg) / ax_) ** 2.4 + (np.abs(yg) / ay_) ** 2.4)
                )
                bar *= sech2(zg, 0.12) / (np.pi * ax_ * ay_ * 0.92)
                e_bul = e_bul + rc.l_bar * bar
            kappa = (
                maps.sample("dust", xg, yg) * sech2(zg, 0.045)
                if dust_on
                else 0.0
            )
        else:
            a, b, c = rc.axes
            core = hernquist(xg, yg, zg, 0.22, 1.0, (a, b, c))
            env = hernquist(xg, yg, zg, rc.env_a, 1.0, (a, b, c))
            e_disk = np.zeros_like(xg)
            e_young = np.zeros_like(xg)
            e_bul = None
            e_core, e_env = rc.core_frac * core, (1 - rc.core_frac) * env
            kappa = 0.0
            if rc.dust_lane > 0 and dust_on:
                rr = np.hypot(
                    xg, zg
                )  # lane in the x-z plane (minor-axis lane)
                kappa = (
                    rc.dust_lane
                    * 2.5
                    * np.exp(-rr / 0.25)
                    * (1 - np.exp(-((rr / 0.05) ** 2)))
                    * sech2(yg, 0.02)
                )

        e_icl = (
            (rc.l_icl * hernquist(xg, yg, zg, rc.icl_a, 0.85))
            if rc.l_icl > 0
            else None
        )

        dtau = (
            (kappa * dz).astype(np.float32)
            if np.ndim(kappa)
            else np.zeros_like(tau)
        )
        att = np.exp(
            -(tau + 0.5 * dtau)[..., None] * DUST_K[None, None, :]
        ).astype(np.float32)

        # Points living in this slab see the dust in front of them.
        for i, po in enumerate(pt_obs):
            sel = pt_slab[i] == k
            if sel.any():
                ix = np.clip(((po[sel, 0] + E) / pix).astype(int), 0, npix - 1)
                iy = np.clip(((E - po[sel, 1]) / pix).astype(int), 0, npix - 1)
                pt_att[i][sel] = att[iy, ix]

        if rc.kind == "disk":
            disk += (e_disk * dz)[..., None] * old_rgb * att
            young += (e_young * dz)[..., None] * YOUNG_RGB * att
            bulge += (e_bul * dz)[..., None] * bulge_rgb * att
        else:
            bulge += (e_core * dz)[..., None] * bulge_rgb * att
            disk += (e_env * dz)[..., None] * (old_rgb * 0.95 + 0.05) * att
        if e_icl is not None:
            icl += (e_icl * dz)[..., None] * (old_rgb * 0.9 + 0.08) * att
        tau += dtau

    # Splat points (bilinear deposit then a Gaussian PSF per size class).
    point_imgs = {}
    for p, po, at in zip(pts, pt_obs, pt_att, strict=True):
        name = p.name
        img = np.zeros((npix, npix, 3), np.float32)
        fx = (po[:, 0] + E) / pix
        fy = (E - po[:, 1]) / pix
        inb = (fx >= 0) & (fx < npix - 1) & (fy >= 0) & (fy < npix - 1)
        cls = np.round(p.sigma * 2) / 2
        for s in np.unique(cls[inb]):
            m = inb & (cls == s)
            x0, y0 = fx[m].astype(int), fy[m].astype(int)
            wx, wy = fx[m] - x0, fy[m] - y0
            val = (p.lum[m, None] * p.rgb[m] * at[m]) / pix**2
            layer = np.zeros_like(img)
            for dx, dy, w in (
                (0, 0, (1 - wx) * (1 - wy)),
                (1, 0, wx * (1 - wy)),
                (0, 1, (1 - wx) * wy),
                (1, 1, wx * wy),
            ):
                for c in range(3):
                    np.add.at(layer[..., c], (y0 + dy, x0 + dx), val[:, c] * w)
            img += gaussian_filter(layer, (s, s, 0))
        point_imgs[name] = img

    # Nucleus (black hole sets brightness and compactness) — a point source
    # behind the dust column at the centre.
    if rc.agn > 0:
        point_imgs["agn"] = agn_image(rc, npix, pix, tau)
    if rc.l_nucleus > 0:
        img = np.zeros((npix, npix, 3), np.float32)
        c = npix // 2
        s = max(rc.nucleus_sigma / pix, 0.8)
        img[c, c] = rc.l_nucleus / pix**2 * np.exp(-0.5 * tau[c, c] * DUST_K)
        img = gaussian_filter(img, (s, s, 0)) * np.array([1.0, 0.93, 0.85])
        point_imgs["nucleus"] = img

    if rc.l_icl > 0:
        point_imgs["icl"] = icl
    return Layers(disk, bulge, young, point_imgs, tau, E)


def agn_image(rc, npix, pix, tau):
    """Quasar-mode nucleus.  'point' is a faint unresolved source; 'glow'
    adds a bright core and a soft scattered-light halo; 'spikes' adds
    Hubble-style diffraction spikes on top."""
    c = npix // 2
    lum = rc.agn * (1 if rc.agn_style == "point" else 8)
    base = np.zeros((npix, npix, 3), np.float32)
    base[c, c] = lum / pix**2 * np.exp(-0.5 * tau[c, c] * DUST_K)
    img = gaussian_filter(base, (0.9, 0.9, 0)) + 0.15 * gaussian_filter(
        base, (4, 4, 0)
    )
    if rc.agn_style in ("glow", "spikes"):
        img += 0.05 * gaussian_filter(base, (npix / 60, npix / 60, 0))
    if rc.agn_style == "spikes":
        yy, xx = np.mgrid[0:npix, 0:npix] - c
        spike = np.zeros((npix, npix), np.float32)
        for a in (np.pi / 4, 3 * np.pi / 4):
            along = xx * np.cos(a) + yy * np.sin(a)
            perp = -xx * np.sin(a) + yy * np.cos(a)
            spike += (
                np.exp(-((perp / 0.7) ** 2))
                / (1 + np.abs(along) / 2.0) ** 1.6
                * np.exp(-np.abs(along) / (npix / 30))
            )
        img += 0.06 * spike[..., None] * base[c, c][None, None, :]
    return img * np.array([0.85, 0.92, 1.0])


def tonemap(img, q=40.0, white=None, bloom=0.25, sat=1.05):
    """Log-like asinh stretch that keeps colours, plus a soft bloom.

    `white` is the linear luminance mapped to 1; by default just under the
    brightest pixels, so the nucleus saturates but nothing else does.  A
    large `q` compresses many decades so faint outer arms stay visible next
    to a bright bulge.
    """
    lum = img.mean(axis=2)
    if white is None:
        white = np.percentile(lum, 99.97)
    x = lum / white
    f = np.arcsinh(q * x) / np.arcsinh(q) / np.maximum(x, 1e-12)
    out = img / white * f[..., None]
    l2 = out.mean(axis=2, keepdims=True)
    out = l2 + sat * (out - l2)
    n = img.shape[0]
    hi = np.clip(out - 0.7, 0, None)
    out = out + bloom * (
        gaussian_filter(hi, (n / 300, n / 300, 0))
        + 0.4 * gaussian_filter(hi, (n / 80, n / 80, 0))
    )
    return np.clip(out, 0, 1), white


# ----------------------------------------------------------------------
# Gas-halo overlay
# ----------------------------------------------------------------------


def gas_halo(
    gal,
    rc: GalaxyRecipe,
    npix: int,
    E: float,
    inc=0.0,
    pa=0.0,
    log_stretch=False,
    hot_cavity=True,
) -> np.ndarray:
    """Display-space overlay of the halo gas, in the style of an X-ray /
    optical composite.  Neither reservoir is optical light, so this is
    screen-blended over the tone-mapped galaxy rather than ray-marched.

    In SAGE26 the two are exclusive: hot-regime haloes carry HotGas (a
    smooth, quasi-hydrostatic atmosphere), cold-regime haloes carry CGMgas
    (cold-mode inflow, drawn as streams and filaments).

    `log_stretch` shows the hot atmosphere on a log scale (as X-ray images
    are usually shown) so it stays visible out to Rvir in halo-wide frames.
    """
    from model import CGM_RGB, HOT_GAS_RGB, JET_RGB, WIND_RGB, gaussian_field

    rng = np.random.default_rng(rc.seed + 7)
    ax = np.linspace(-E, E, npix) * rc.unit_kpc  # kpc
    X, Y = np.meshgrid(ax, ax[::-1])
    R = np.hypot(X, Y) + 1e-3
    th = np.arctan2(Y, X)
    rvir = max(gal.rvir_kpc, 20.0)
    out = np.zeros((npix, npix, 3))

    if gal.hot_gas > 0:
        # One look for every hot atmosphere (that of the massive hot-regime
        # ellipticals): a textured violet glow filling the halo, core
        # ~0.15 Rvir, fading at Rvir.  HotGas mass only sets its opacity.
        rcore = 0.15 * rvir
        sb = (1 + (R / rcore) ** 2) ** -0.5 * np.exp(-((R / rvir) ** 8))
        if log_stretch:
            sb = np.log1p(sb / 0.02) / np.log1p(1 / 0.02)
        if hot_cavity:
            # The intracluster / intragroup medium thins out around the
            # galaxy rather than stopping at a radius: a soft, irregular
            # depletion (its edge wobbles with a large-scale noise field)
            # that never quite reaches zero.
            r_in = 1.2 * rc.extent * rc.unit_kpc
            wob = np.exp(0.3 * gaussian_field((npix, npix), 4.0, rng))
            sb = sb * (1 - 0.85 * np.exp(-((R / (1.6 * r_in * wob)) ** 2)))
            sb = sb / max(sb.max(), 1e-9)
        tex = np.exp(0.15 * gaussian_field((npix, npix), 3.0, rng))
        opacity = hot_opacity(gal.hot_gas)
        out += opacity * (sb * tex)[..., None] * HOT_GAS_RGB
        # Cool core: gas inside the cooling radius radiates hardest, so
        # brighten and whiten the centre by the cooling luminosity.
        if gal.cooling_log > 38 and gal.rcool_to_rvir > 0 and not hot_cavity:
            rcool = min(gal.rcool_to_rvir, 1.0) * rvir
            cc = np.exp(-((R / (0.35 * rcool)) ** 2))
            camp = np.clip((gal.cooling_log - 39.0) / 3.0, 0.0, 1.0)
            out += (
                0.25
                * camp
                * opacity
                * cc[..., None]
                * (0.6 * HOT_GAS_RGB + 0.4)
            )
        # Cold streams that still penetrate the hot halo (mdot_stream > 0),
        # drawn exactly like cold-mode CGM inflow.
        if gal.mdot_stream > 0:
            samp = float(
                np.clip((np.log10(gal.mdot_stream) + 6.0) / 1.5, 0.3, 1.0)
            )
            out += (
                0.8
                * samp
                * cold_streams(R, th, rvir, rng, npix)[..., None]
                * CGM_RGB
            )

    if gal.cgm_gas > 0:
        amp = np.clip((np.log10(gal.cgm_gas) - 8.5) / 3.0, 0.05, 1.0)
        out += (
            0.8
            * amp
            * cold_streams(R, th, rvir, rng, npix)[..., None]
            * CGM_RGB
        )

    if gal.heating_log > 40.0:
        out += jets(gal, X, Y, inc, pa, rng, npix)[..., None] * JET_RGB
    if gal.outflow_rate > 0.05:
        out += (
            wind(gal, rc, R, th, X, Y, inc, pa, rng, npix)[..., None]
            * WIND_RGB
        )

    return np.clip(out, 0, 1)


# Hot-atmosphere opacity peaks here (log M_hot >= 13); fainter haloes scale
# down from it to 65% of this at log M_hot = 10.
HOT_MAX_OPACITY = 0.13


def hot_opacity(hot_gas):
    """Opacity of the hot atmosphere, rising with log HotGas to a cap of
    HOT_MAX_OPACITY, so every hot halo shows without hiding the galaxy."""
    f = np.clip((np.log10(max(hot_gas, 1.0)) - 10.0) / 3.0, 0.0, 1.0)
    return float(HOT_MAX_OPACITY * (0.65 + 0.35 * f))


def cold_streams(R, th, rvir, rng, npix):
    """Cold-mode inflow: three curling streams plus filaments, reaching out
    to Rvir.  Normalised so its brightest 0.1% sits at 1."""
    from model import gaussian_field

    env = (1 + (R / (0.12 * rvir)) ** 2) ** -0.5 * np.exp(-((R / rvir) ** 8))
    lnr = np.log(np.clip(R / rvir, 0.04, None))
    streams = np.zeros_like(R)
    t0s = (
        rng.uniform(0, 2 * np.pi)
        + np.arange(3) * 2 * np.pi / 3
        + rng.normal(0, 0.4, 3)
    )
    for t0 in t0s:
        dth = np.angle(np.exp(1j * (th - t0 - 0.25 * lnr)))
        w = 0.12 + 0.3 * np.clip(R / rvir, 0, 1)
        streams += np.exp(-((dth / w) ** 2))
    streams *= 1 - np.exp(-((R / (0.04 * rvir)) ** 2))
    # Filaments: zero-crossings of a smooth Gaussian field.
    fil = np.exp(-((gaussian_field((npix, npix), 3.4, rng) / 0.22) ** 2))
    clump = np.exp(0.5 * gaussian_field((npix, npix), 2.6, rng))
    cgm = env * (0.12 + 0.8 * streams + 0.35 * fil) * clump
    # Fade out before the frame edge so the overlay has no border.
    edge = R.max() / np.sqrt(2)
    cgm *= np.exp(-((R / (0.9 * edge)) ** 8))
    return cgm / np.percentile(cgm, 99.9)


def jets(gal, X, Y, inc, pa, rng, npix):
    """Radio-mode AGN (Heating > 1e40 erg/s): two narrow jets along the
    spin axis ending in lobes, as in radio/optical composites."""
    n_obs = rot(inc, pa) @ np.array([0.0, 0.0, 1.0])
    proj = max(np.hypot(n_obs[0], n_obs[1]), 0.25)
    ang = (
        np.arctan2(n_obs[1], n_obs[0])
        if np.hypot(n_obs[0], n_obs[1]) > 1e-3
        else 0.6
    )
    along = X * np.cos(ang) + Y * np.sin(ang)
    perp = -X * np.sin(ang) + Y * np.cos(ang)
    amp = float(np.clip((gal.heating_log - 40.0) / 1.5, 0.15, 1.0))
    length = (15 + 25 * amp) * proj  # kpc, foreshortened
    jet = np.exp(-((perp / (0.4 + 0.04 * np.abs(along))) ** 2)) * np.exp(
        -((along / length) ** 6)
    )
    lobes = sum(
        np.exp(-((along - s * length) ** 2 + perp**2) / (0.25 * length) ** 2)
        for s in (1, -1)
    )
    return 0.6 * amp * (0.6 * jet + 0.5 * lobes)


def wind(gal, rc, R, th, X, Y, inc, pa, rng, npix):
    """Biconical galactic wind along the disk's spin axis (OutflowRate,
    shaped by MassLoading): filamentary, brightest near the disk."""
    from model import gaussian_field

    n_obs = rot(inc, pa) @ np.array([0.0, 0.0, 1.0])
    proj = np.hypot(n_obs[0], n_obs[1])
    disk_r = rc.extent * rc.unit_kpc * 0.5
    length = float(np.clip(8 * gal.outflow_rate**0.35, 4, 40)) + disk_r * 0.5
    amp = float(np.clip((np.log10(gal.outflow_rate) + 1.0) / 2.5, 0.1, 1.0))
    if proj < 0.15:
        # Face-on: the cones point at us, so the wind is a diffuse halo
        # over the inner disk rather than two plumes.
        return 0.12 * amp * np.exp(-((R / (0.6 * length)) ** 2))
    ax_ang = np.arctan2(n_obs[1], n_obs[0])
    along = X * np.cos(ax_ang) + Y * np.sin(ax_ang)
    perp = -X * np.sin(ax_ang) + Y * np.cos(ax_ang)
    half_open = np.deg2rad(np.clip(25 + 5 * gal.mass_loading, 20, 45))
    width = 0.25 * disk_r + np.abs(along) * np.tan(half_open)
    cone = np.exp(-((perp / width) ** 2)) * np.exp(
        -np.abs(along) / (length * proj)
    )
    fil = np.exp(
        -(
            (gaussian_field((npix, npix), 3.0, rng, aniso=(1.0, 1.0)) / 0.35)
            ** 2
        )
    )
    return 0.35 * amp * cone * (0.3 + 0.9 * fil)


def icl_zone(gal, rc: GalaxyRecipe, npix: int, E: float) -> np.ndarray:
    """IntraClusterStars drawn into the zone around the galaxy where
    the hot medium thins out -- a soft, warm old-star glow plus a sprinkle of
    stripped stars, fading outward where the hot gas takes over.

    Display-space (like the gas overlay): physically the ICL is far too
    faint to see next to the galaxy, so this is an enhanced view of where
    those stars sit, with opacity set by the ICS mass.
    """
    from model import gaussian_field

    if gal.ics <= 0:
        return np.zeros((npix, npix, 3))
    rng = np.random.default_rng(rc.seed + 11)
    ax = np.linspace(-E, E, npix) * rc.unit_kpc  # kpc
    X, Y = np.meshgrid(ax, ax[::-1])
    # Mildly elongated envelope along a random axis.
    ang = rng.uniform(0, np.pi)
    xr = X * np.cos(ang) + Y * np.sin(ang)
    yr = (-X * np.sin(ang) + Y * np.cos(ang)) / 0.8
    R = np.hypot(xr, yr) + 1e-3
    r_in = 1.2 * rc.extent * rc.unit_kpc  # same scale as the hot-gas thinning
    prof = (1 + (R / (0.5 * r_in)) ** 2) ** -1.2
    prof *= 1 - np.exp(
        -((R / (0.35 * r_in)) ** 2)
    )  # galaxy dominates the centre
    prof *= np.exp(-((R / (2.2 * r_in)) ** 2))  # hand over to the hot medium
    prof *= np.exp(0.2 * gaussian_field((npix, npix), 3.0, rng))
    prof /= max(prof.max(), 1e-12)
    # Stripped stars scattered through the envelope.
    n = int(np.clip(gal.ics / 1e8, 200, 6000))
    p = prof.ravel() / prof.sum()
    idx = rng.choice(p.size, size=n, p=p)
    stars = np.zeros(npix * npix)
    np.add.at(stars, idx, rng.uniform(0.3, 1.0, n))
    stars = gaussian_filter(stars.reshape(npix, npix), 0.7) * 4.0
    f = np.clip((np.log10(gal.ics) - 9.0) / 3.0, 0.0, 1.0)
    opacity = 0.025 + 0.1 * f
    icl_rgb = np.array([1.0, 0.82, 0.6])
    return np.clip(opacity * (0.8 * prof + stars)[..., None] * icl_rgb, 0, 1)


def screen(a, b):
    """Screen blend: adds light without clipping to flat white."""
    return 1 - (1 - a) * (1 - b)
