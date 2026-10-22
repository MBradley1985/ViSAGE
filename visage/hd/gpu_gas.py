"""Gas overlay for the GPU galaxy: the offline 2D formulas, per pixel.

The offline renderer draws the halo gas as image-plane overlays (hot
intracluster medium, CGM / cold streams, wind, radio jets; see
`raymarch.gas_halo`).  Here each pixel's image-plane position is the point
where its ray passes closest to the galaxy centre, measured in a screen
basis tied to the galaxy's own axes, so the same formulas give the same
look and turn with the galaxy as the camera orbits.  The random fields of
the 2D version become 3D value-noise sampled at that point, so the texture
changes smoothly with viewing angle instead of being painted on the screen.
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
from visage.hd.raymarch import HOT_MAX_OPACITY

# ----------------------------------------------------------------------
# numpy mirror of the shader's noise (for normalisation constants)
# ----------------------------------------------------------------------


def _hash3(p):
    p = np.modf(p * 0.3183099 + np.array([0.11, 0.17, 0.13]))[0] % 1.0
    p = p * 17.0
    return (p[..., 0] * p[..., 1] * p[..., 2] * p.sum(axis=-1)) % 1.0


def _vnoise(x):
    i = np.floor(x)
    f = x - i
    f = f * f * (3.0 - 2.0 * f)

    def h(dx, dy, dz):
        return _hash3(i + np.array([dx, dy, dz], float))

    fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]
    x00 = h(0, 0, 0) + (h(1, 0, 0) - h(0, 0, 0)) * fx
    x10 = h(0, 1, 0) + (h(1, 1, 0) - h(0, 1, 0)) * fx
    x01 = h(0, 0, 1) + (h(1, 0, 1) - h(0, 0, 1)) * fx
    x11 = h(0, 1, 1) + (h(1, 1, 1) - h(0, 1, 1)) * fx
    y0 = x00 + (x10 - x00) * fy
    y1 = x01 + (x11 - x01) * fy
    return (y0 + (y1 - y0) * fz) * 2.0 - 1.0


def fbm(p):
    a, s = 0.5, 0.0
    for _ in range(4):
        s = s + a * _vnoise(p)
        p = p * 2.03
        a *= 0.5
    return s


def fbm6(p):
    """Six-octave noise: cloudy clumping down to small scales."""
    a, s = 0.5, 0.0
    for _ in range(6):
        s = s + a * _vnoise(p)
        p = p * 2.03
        a *= 0.55
    return s


def fbm2(p):
    """Two-octave noise: smooth, for soft filament ridges."""
    return 0.5 * _vnoise(p) + 0.25 * _vnoise(p * 2.03)


def noise_std(kind="fbm"):
    """Standard deviation of each noise over 200k random points (slow: the
    values are stored in `_STDS`, which a test checks against this)."""
    pts = np.random.default_rng(0).uniform(-50, 50, (200_000, 3))
    return float(np.std({"fbm": fbm, "fbm2": fbm2, "fbm6": fbm6}[kind](pts)))


# Cool-core brightening of the hot atmosphere from SAGE's Cooling (0: off).
COOL_CORE = 0.0

# Extended HI disk (Gas on), from H1gas: its colour, brightness, size
# (times the HI size-mass relation), thickness (fraction of its scale
# length), warp, and clumpiness.
HI = dict(
    on=True,
    rgb=(0.70, 0.85, 1.00),
    gain=0.35,
    size=1.0,
    h=0.06,
    warp=0.15,
    clump=0.5,
)
# Cold streams: at "random" angles, or aimed at the massive haloes around
# the galaxy: "neighbours" (the three strongest), "weighted" (brighter
# toward the strongest), "filament" (both ways along the strongest
# direction, and toward the next).
WEB_STREAMS = "filament"
# Hot-halo colour by virial temperature: None, or stops of (log10 Mvir,
# rgb), interpolated, then tinted by metallicity.  T_vir ~ Mvir^(2/3)
# (1+z): a halo of given mass is hotter at high z, so it is looked up at
# log Mvir + 1.5 log(1+z).
HOT_TEMP = [
    (12.0, (0.90, 0.40, 0.95)),
    (13.3, (0.60, 0.45, 1.00)),
    (14.8, (0.70, 0.92, 1.00)),
]


def hot_opacity(gal) -> float:
    """Opacity of the hot atmosphere: rising with log HotGas, with the hot
    gas's share of the halo's baryons, and with redshift (denser haloes),
    capped so it never hides the galaxy."""
    if gal.hot_gas <= 0:
        return 0.0
    f_m = np.clip((np.log10(gal.hot_gas) - 9.0) / 3.5, 0.0, 1.0)
    frac = 1.0
    if gal.mvir > 0:
        frac = np.clip(gal.hot_gas / (0.17 * gal.mvir), 0.0, 1.0)
    zb = min(1.0 + gal.redshift, 3.0) ** 0.5
    op = (0.3 + 0.7 * f_m) * (0.55 + 0.45 * frac**0.5) * zb
    return float(HOT_MAX_OPACITY * min(op, 1.3))


_STDS = {"fbm": 0.212785, "fbm2": 0.206308, "fbm6": 0.220944}


def _std(kind="fbm"):
    """Standard deviation of each noise, to give it unit variance like the
    2D version's Gaussian random fields."""
    return _STDS[kind]


# ----------------------------------------------------------------------
# GLSL
# ----------------------------------------------------------------------

GLSL_IMPL = """
  if (uGasOn > 0.5) {
    // Image-plane position of this pixel relative to the centre (kpc), in
    // a screen basis tied to the galaxy's x axis.
    vec3 cpk = cp * uUnitKpc;
    float R = length(cpk) + 1e-3;
    vec3 ex = vec3(1.0, 0.0, 0.0) - rd.x * rd;
    if (length(ex) < 1e-3) ex = vec3(0.0, 1.0, 0.0) - rd.y * rd;
    ex = normalize(ex);
    vec3 ey = cross(rd, ex);
    float X = dot(cpk, ex);
    float Y = dot(cpk, ey);
    float th = atan(Y, X);
    float rvir = uRvirKpc;
    vec3 gas = vec3(0.0);

    // Spin axis (galaxy +z) projected on the image plane.
    vec3 ax = vec3(0.0, 0.0, 1.0) - rd.z * rd;
    float proj = length(ax);
    vec3 axd = proj > 1e-3 ? ax / proj : ex;
    float along = dot(cpk, axd);
    float perp = length(cpk - along * axd);

    if (uHotOpacity > 0.0) {
      float sb = pow(1.0 + pow(R / (uHotCore * rvir), 2.0), -0.5) * exp(-pow(R / rvir, 8.0));
      if (uHotLog > 0.5) sb = log(1.0 + sb / 0.02) / log(1.0 + 1.0 / 0.02);
      float wob = exp(0.3 * fbm(cpk / (0.25 * rvir) + vec3(11.0)) / uFbmStd);
      sb *= 1.0 - 0.85 * exp(-pow(R / (1.6 * uRinKpc * wob), 2.0));
      sb /= (uHotLog > 0.5 ? uHotNormLog : uHotNormLin);
      if (uCoolCore > 0.0) {
        // Cool core: the radiative cooling (SAGE's Cooling) brightens the
        // centre of the hot atmosphere, as in cool-core clusters' X-rays.
        sb += uCoolCore * exp(-pow(R / (0.07 * rvir), 2.0))
            * (1.0 - 0.85 * exp(-pow(R / (1.6 * uRinKpc * wob), 2.0)));
      }
      if (uCavAmp > 0.0) {
        // X-ray cavities: bubbles the radio jets inflate at the AGN heating
        // radius, along the jet axis, with slightly brighter rims.
        for (int k = 0; k < 2; k++) {
          float sgn = k == 0 ? 1.0 : -1.0;
          vec3 c = sgn * uCavR * max(proj, 0.3) * axd;
          float d = length(cpk - c) / (0.55 * uCavR);
          sb *= 1.0 - 0.8 * uCavAmp * exp(-pow(d, 4.0));
          sb *= 1.0 + 0.35 * uCavAmp * exp(-pow((d - 1.0) / 0.18, 2.0));
        }
      }
      float tex = exp(0.15 * fbm(cpk / (0.06 * rvir) + vec3(23.0)) / uFbmStd);
      gas += uHotOpacity * sb * tex * uHotRGB;
    }

    if (uStreamAmp > 0.0) {
      float env = pow(1.0 + pow(R / (0.12 * rvir), 2.0), -0.5) * exp(-pow(R / rvir, 8.0));
      float lnr = log(max(R / rvir, 0.04));
      float w = uStreamW * (0.12 + 0.3 * clamp(R / rvir, 0.0, 1.0));
      float st = 0.0;
      for (int k = 0; k < 3; k++) {
        float t0 = k == 0 ? uStreamT0.x : (k == 1 ? uStreamT0.y : uStreamT0.z);
        // Aimed at a neighbouring halo, where there is one: its direction
        // on screen; fading as it points toward or away from the camera.
        vec3 D = k == 0 ? uWeb0 : (k == 1 ? uWeb1 : uWeb2);
        float wk = 1.0;
        if (dot(D, D) > 0.0) {
          vec2 q = vec2(dot(D, ex), dot(D, ey));
          t0 = atan(q.y, q.x);
          wk = (k == 0 ? uWebW.x : (k == 1 ? uWebW.y : uWebW.z))
             * smoothstep(0.05, 0.4, length(q));
        }
        float d = th - t0 - 0.25 * lnr;
        d = atan(sin(d), cos(d));
        st += wk * exp(-pow(d / w, 2.0));
      }
      st *= 1.0 - exp(-pow(R / (0.04 * uStreamW * rvir), 2.0));
      float fil = exp(-pow(fbm2(cpk / (0.5 * rvir) + vec3(37.0)) / uFbm2Std / 0.35, 2.0));
      // Lognormal clumping, with the bright tail soft-capped so one rare
      // clump on a stream near the core can't outshine the whole halo.
      float zc = fbm6(cpk / (0.08 * rvir) + vec3(51.0)) / uFbm6Std;
      if (zc > 0.0) zc = 1.2 * (1.0 - 2.0 / (exp(2.0 * zc / 1.2) + 1.0));
      float clump = exp(0.55 * zc);
      float cgm = env * (0.12 + 0.8 * st + 0.35 * fil) * clump;
      cgm *= exp(-pow(R / (0.95 * rvir), 8.0));
      gas += uStreamAmp * (cgm / uStreamNorm) * uCgmRGB;
    }

    if (uJetAmp > 0.0) {
      float pj = max(proj, 0.25);
      float len = uJetLen * pj;
      float jet = exp(-pow(perp / (0.4 + 0.04 * abs(along)), 2.0)) * exp(-pow(along / len, 6.0));
      float lobes = exp(-(pow(along - len, 2.0) + perp * perp) / pow(0.25 * len, 2.0))
                  + exp(-(pow(along + len, 2.0) + perp * perp) / pow(0.25 * len, 2.0));
      gas += 0.4 * uJetAmp * (0.6 * jet + 0.5 * lobes) * uJetRGB;
    }

    if (uWindAmp > 0.0) {
      // Galactic wind: a hollow bipolar cone along the spin axis,
      // integrated through 3D along the ray (so it looks right from every
      // angle), faded to nothing by 3 wind lengths.  A few thin streamers
      // run outward through it (noise stretched radially), with clumps.
      float L = uWindLen;
      float reach = min(3.0 * L, 0.9 * rvir);
      float b = length(cpk);
      if (b < reach) {
        float hs = sqrt(reach * reach - b * b);
        const int NW = 18;
        float ds = 2.0 * hs / float(NW);
        float tw = tan(uWindOpen);
        float w0 = 0.25 * uDiskRKpc;
        float acc = 0.0;
        // Per-pixel offset of the samples: grain, not banding.
        float jit = hash3(floor(gl_FragCoord.xyy) + vec3(0.0, 0.0, 17.0));
        for (int k = 0; k < NW; k++) {
          vec3 p = cpk + (-hs + (float(k) + jit) * ds) * rd;
          float z = abs(p.z);
          float r = length(p) + 1e-3;
          float q = length(p.xy) / (w0 + z * tw);
          float dens = exp(-z / L)
                     * (1.0 - exp(-pow(z / (0.3 * w0 + 0.3), 2.0)))
                     * exp(-pow(r / reach, 6.0))
                     * (exp(-pow((q - 0.7) / 0.35, 2.0)) + 0.25 * exp(-q * q));
          if (dens > 1e-4) {
            float s = fbm2((p / r) * 3.0 + vec3(0.0, 0.0, 0.12 * r / L)
                           + vec3(73.0)) / uFbm2Std;
            float zc = fbm2(p / (0.45 * L) + vec3(51.0)) / uFbm2Std;
            dens *= (0.5 + 0.7 * exp(-pow(s / 0.3, 2.0))) * exp(0.35 * zc);
          }
          acc += dens * ds;
        }
        gas += 0.22 * uWindAmp * acc / (1.77 * (w0 + 0.5 * L * tw)) * uWindRGB;
      }
    }
    if (uHiAmp > 0.0) {
      // Extended HI disk: an exponential gas disk past the stars, with a
      // shallow centre (the gas there is molecular), its thickness
      // integrated exactly along the ray; warped beyond 1.5 scale lengths.
      float reach = 4.0 * uHiRs;
      float b = length(cpk);
      if (b < reach) {
        float hs = sqrt(reach * reach - b * b);
        const int NH = 16;
        float ds = 2.0 * hs / float(NH);
        float acc = 0.0;
        for (int k = 0; k < NH; k++) {
          vec3 p0 = cpk + (-hs + float(k) * ds) * rd;
          vec3 p1 = p0 + ds * rd;
          vec3 pm = 0.5 * (p0 + p1);
          float R = length(pm.xy);
          float zw = uHiWarp * uHiRs * pow(max(R / uHiRs - 1.5, 0.0), 2.0)
                   * pm.y / max(R, 1e-3);
          float sig = exp(-R / uHiRs)
                    * (1.0 - 0.9 * exp(-pow(R / uHiRs, 2.0)))
                    * exp(-pow(R / reach, 6.0));
          if (uHiClump > 0.0)
            sig *= exp(uHiClump * fbm2(pm / (0.4 * uHiRs) + vec3(91.0)) / uFbm2Std);
          acc += sig * pint(p0.z - zw, p1.z - zw, uHiH, ds);
        }
        gas += uHiAmp * (1.0 - exp(-0.5 * acc)) * uHiRGB;
      }
    }
    outc = screenB(outc, clamp(gas, 0.0, 1.0));
  }
"""


class GasSpec:
    """Uniform values for the gas overlay of one galaxy."""

    glsl_impl = GLSL_IMPL

    def __init__(self, gal, rc: GalaxyRecipe, magnify: float = 1.0):
        """`magnify`: how many times its true size the galaxy is drawn (a
        group member); the halo keeps its true size, and so does the gas's
        clearing around the galaxy and its wind (true galaxy size)."""
        self.gal, self.rc = gal, rc
        true_unit = rc.unit_kpc / magnify  # kpc per model unit, unmagnified
        self.rvir = max(gal.rvir_kpc, 20.0)
        self.half = 1.05 * self.rvir / rc.unit_kpc  # model units
        self.r_in = 1.2 * rc.extent * true_unit
        self.hot = hot_opacity(gal)
        # Hot gas follows the dark matter: its core is ~1.5 NFW scale radii
        # (Rvir / c), so concentrated haloes are peakier.
        conc = gal.concentration if gal.concentration > 0 else 8.0
        self.hot_core = float(np.clip(1.5 / conc, 0.08, 0.3))

        self.stream_amp = 0.0
        if gal.cgm_gas > 0:
            self.stream_amp = 0.8 * float(
                np.clip((np.log10(gal.cgm_gas) - 8.5) / 3.0, 0.05, 1.0)
            )
        if gal.mdot_stream > 0 and (gal.cgm_gas > 0 or gal.hot_gas > 0):
            self.stream_amp = max(
                self.stream_amp,
                0.8
                * float(
                    np.clip((np.log10(gal.mdot_stream) + 6.0) / 1.5, 0.3, 1.0)
                ),
            )
        # Cold streams are narrower and reach deeper at high z (Dekel &
        # Birnboim): thinner and brighter, and right in to the galaxy.
        z = max(gal.redshift, 0.0)
        self.stream_w = float(np.clip(1.0 / (1.0 + 0.35 * z), 0.5, 1.0))
        self.stream_amp *= float(1.0 + 0.15 * min(z, 3.0))
        rng = np.random.default_rng(rc.seed + 7)
        self.t0 = (
            rng.uniform(0, 2 * np.pi)
            + np.arange(3) * 2 * np.pi / 3
            + rng.normal(0, 0.4, 3)
        )

        self.jet = (
            float(np.clip((gal.heating_log - 40.0) / 1.5, 0.15, 1.0))
            if gal.heating_log > 40.0
            else 0.0
        )
        # Bigger black holes drive brighter jets; jets reach about the
        # radius the AGN heats (r_heat), in proportion to the halo.
        if self.jet > 0 and gal.bh_mass > 0:
            self.jet *= float(
                np.clip(0.7 + 0.15 * (np.log10(gal.bh_mass) - 8.0), 0.5, 1.3)
            )
        reach = max(gal.r_heat_kpc, 0.08 * self.rvir)
        self.jet_len = float(
            np.clip(0.6 * reach, 12.0, 150.0)
            * (0.6 + 0.4 * min(self.jet, 1.0))
        )
        self.disk_r = rc.extent * true_unit * 0.5
        self.wind = 0.0
        if gal.outflow_rate > 0.05:
            self.wind = float(
                np.clip((np.log10(gal.outflow_rate) + 1.0) / 2.5, 0.1, 1.0)
            )
            # Winds need concentrated star formation: brighter with the
            # SFR surface density (high-z disks are compact, so stronger).
            rd = max(gal.disk_radius_kpc, 0.3)
            sig = (gal.sfr_disk + gal.sfr_bulge) / (np.pi * rd**2)
            self.wind *= float(
                np.clip(1.0 + 0.4 * np.log10(max(sig, 1e-6) / 0.1), 0.4, 1.5)
            )
            self.wind = min(self.wind, 1.2)
        # Faster in deeper potentials (v ~ 2 Vmax), so further out.
        self.wind_len = (
            float(
                np.clip(
                    4 * gal.outflow_rate**0.35 + 0.08 * max(gal.vmax, 0.0),
                    4,
                    60,
                )
            )
            + self.disk_r * 0.5
        )
        # Winds reach further the more gas has been blown right out of the
        # halo (SAGE's ejected reservoir).
        halo_gas = gal.hot_gas + gal.cgm_gas + gal.ejected
        if gal.ejected > 0 and halo_gas > 0:
            self.wind_len *= 1.0 + 1.5 * float(gal.ejected / halo_gas)

        # Cool core: brighter with SAGE's cooling luminosity (log erg/s,
        # ~10^39.5-10^41 among hot centrals), scaled by COOL_CORE.
        self.cool_core = 0.0
        if COOL_CORE > 0 and gal.regime == 1 and gal.hot_gas > 0:
            self.cool_core = COOL_CORE * float(
                np.clip((gal.cooling_log - 39.5) / 1.5, 0.0, 1.0)
            )

        # Cavities where radio-mode heating reaches (hot haloes).
        self.cav_r = 0.0
        self.cav = 0.0
        if (
            gal.regime == 1
            and gal.hot_gas > 0
            and self.jet > 0
            and 0 < gal.r_heat_kpc < 0.5 * self.rvir
        ):
            self.cav_r = float(max(gal.r_heat_kpc, 10.0))
            self.cav = float(np.clip(0.4 + 0.6 * self.jet, 0.0, 1.0))

        # Gas colours tinted by their metallicity.
        self.hot_rgb = np.asarray(HOT_GAS_RGB, float)
        if HOT_TEMP and gal.mvir > 0:
            lm = np.log10(gal.mvir) + 1.5 * np.log10(1 + max(gal.redshift, 0))
            xs = [x for x, _ in HOT_TEMP]
            cs = np.array([c for _, c in HOT_TEMP], float)
            self.hot_rgb = np.array(
                [np.interp(lm, xs, cs[:, j]) for j in range(3)]
            )
        if gal.hot_gas > 0 and gal.metals_hot > 0:
            zh = np.clip(
                np.log10(gal.metals_hot / gal.hot_gas / 0.02), -1.0, 0.3
            )
            self.hot_rgb = self.hot_rgb * np.array(
                [1 + 0.12 * zh, 1.0, 1 - 0.08 * zh]
            )
        self.cgm_rgb = np.asarray(CGM_RGB, float)
        if gal.cgm_gas > 0 and gal.metals_cgm > 0:
            zc = np.clip(
                np.log10(gal.metals_cgm / gal.cgm_gas / 0.02), -1.5, 0.3
            )
            self.cgm_rgb = self.cgm_rgb * np.array(
                [1.0, 1 + 0.1 * zc, 1 - 0.1 * zc]
            )
        # Heavier mass loading opens the cone wider (log, so the high
        # loadings of dwarfs don't all hit the same angle).
        self.wind_open = float(
            np.deg2rad(
                np.clip(
                    25 + 12 * np.log10(1 + max(gal.mass_loading, 0.0)), 20, 60
                )
            )
        )

        # Extended HI disk: the HI size-mass relation (Wang et al. 2016)
        # gives the diameter where it falls to 1 Msun/pc^2, about three
        # exponential scale lengths out.
        self.hi_amp, self.hi_rs, self.hi_warp, self.hi_clump = (
            0.0,
            1.0,
            0.0,
            0.0,
        )
        if HI["on"] and gal.h1_gas > 1e7:
            d_hi = 10 ** (0.506 * np.log10(gal.h1_gas) - 3.293)
            self.hi_rs = float(HI["size"] * 0.5 * d_hi / 3.0)
            self.hi_amp = float(
                HI["gain"]
                * np.clip((np.log10(gal.h1_gas) - 8.5) / 2.0, 0.1, 1)
            )
            # Satellites warp more the longer they have felt the host's
            # tides; centrals a little.
            tide = 0.3
            if gal.gtype > 0 and gal.t_since_infall_gyr >= 0:
                tide = 0.3 + 0.7 * min(gal.t_since_infall_gyr / 3.0, 1.0)
            self.hi_warp = float(HI["warp"] * tide)
            # Clumpier where more of the cold gas is molecular.
            mol = gal.h2_gas / max(gal.h1_gas + gal.h2_gas, 1.0)
            self.hi_clump = float(HI["clump"] * (0.5 + 1.5 * mol))

        # Directions the cold streams come from (set by set_web).
        self.web = np.zeros((3, 3))
        self.web_w = np.ones(3)

        self.norm_lin, self.norm_log = self._hot_norms()
        self._stream_norms: dict = {}

    def _hot_norms(self):
        """Peak of the (cavity-thinned) hot profile, linear and log-stretched,
        so its brightest point sits at the chosen opacity (as in 2D)."""
        R = np.linspace(0.0, 1.05 * self.rvir, 4000) + 1e-3
        sb = (1 + (R / (self.hot_core * self.rvir)) ** 2) ** -0.5 * np.exp(
            -((R / self.rvir) ** 8)
        )
        cav = 1 - 0.85 * np.exp(-((R / (1.6 * self.r_in)) ** 2))
        lin = float((sb * cav).max())
        lg = np.log1p(sb / 0.02) / np.log1p(1 / 0.02)
        return max(lin, 1e-9), max(float((lg * cav).max()), 1e-9)

    def stream_norm(self, half_kpc: float) -> float:
        """Normalisation of the stream image for a view `half_kpc` wide.

        The 2D overlay normalises the streams to the 99.9th percentile of
        the frame being drawn, so it depends on how much of the halo is in
        view; cached in log-spaced bins of the frame size."""
        if self.stream_amp <= 0:
            return 1.0
        key = int(np.round(8 * np.log10(max(half_kpc, 1.0))))
        if key not in self._stream_norms:
            self._stream_norms[key] = self._stream_norm(10 ** (key / 8))
        return self._stream_norms[key]

    def _stream_norm(self, half_kpc, n=160):
        """99.9th percentile of the stream image (as `cold_streams`), from
        the numpy mirror of the shader's formula, face-on."""
        rv = self.rvir
        h = min(half_kpc, 1.05 * rv)
        ax = np.linspace(-h, h, n)
        X, Y = np.meshgrid(ax, ax)
        P = np.stack([X, Y, np.zeros_like(X)], axis=-1)
        R = np.hypot(X, Y) + 1e-3
        th = np.arctan2(Y, X)
        env = (1 + (R / (0.12 * rv)) ** 2) ** -0.5 * np.exp(-((R / rv) ** 8))
        lnr = np.log(np.clip(R / rv, 0.04, None))
        w = self.stream_w * (0.12 + 0.3 * np.clip(R / rv, 0, 1))
        st = sum(
            np.exp(-((np.angle(np.exp(1j * (th - t0 - 0.25 * lnr))) / w) ** 2))
            for t0 in self.t0
        )
        st *= 1 - np.exp(-((R / (0.04 * self.stream_w * rv)) ** 2))
        fil = np.exp(
            -((fbm2(P / (0.5 * rv) + 37.0) / _std("fbm2") / 0.35) ** 2)
        )
        zc = fbm6(P / (0.08 * rv) + 51.0) / _std("fbm6")
        zc = np.where(zc > 0, 1.2 * np.tanh(zc / 1.2), zc)
        clump = np.exp(0.55 * zc)
        cgm = (
            env
            * (0.12 + 0.8 * st + 0.35 * fil)
            * clump
            * np.exp(-((R / (0.95 * rv)) ** 8))
        )
        return max(float(np.percentile(cgm, 99.9)), 1e-9)

    def set_uniforms(self, u, on: bool = True) -> None:
        f = u.SetUniformf
        f("uGasOn", 1.0 if on else 0.0)
        f("uUnitKpc", float(self.rc.unit_kpc))
        f("uRvirKpc", float(self.rvir))
        f("uRinKpc", float(self.r_in))
        f("uFbmStd", float(_std()))
        f("uFbm2Std", float(_std("fbm2")))
        f("uFbm6Std", float(_std("fbm6")))
        f("uHotOpacity", float(self.hot))
        f("uHotLog", 0.0)
        f("uHotNormLin", float(self.norm_lin))
        f("uHotNormLog", float(self.norm_log))
        f("uStreamAmp", float(self.stream_amp))
        f("uStreamNorm", float(self.stream_norm(1.05 * self.rvir)))
        u.SetUniform3f("uStreamT0", [float(v) for v in self.t0])
        f("uJetAmp", float(self.jet))
        f("uJetLen", float(self.jet_len))
        f("uHotCore", float(self.hot_core))
        f("uStreamW", float(self.stream_w))
        f("uWindAmp", float(self.wind))
        f("uWindLen", float(self.wind_len))
        f("uWindOpen", float(self.wind_open))
        f("uDiskRKpc", float(self.disk_r))
        u.SetUniform3f("uHotRGB", [float(v) for v in self.hot_rgb])
        u.SetUniform3f("uCgmRGB", [float(v) for v in self.cgm_rgb])
        f("uCavR", float(self.cav_r))
        f("uCoolCore", float(self.cool_core))
        f("uCavAmp", float(self.cav))
        u.SetUniform3f("uJetRGB", [float(v) for v in JET_RGB])
        u.SetUniform3f("uWindRGB", [float(v) for v in WIND_RGB])
        f("uHiAmp", float(self.hi_amp))
        f("uHiRs", float(self.hi_rs))
        f("uHiH", float(HI["h"] * self.hi_rs))
        f("uHiWarp", float(self.hi_warp))
        f("uHiClump", float(self.hi_clump))
        u.SetUniform3f("uHiRGB", [float(v) for v in HI["rgb"]])
        self._web_uniforms(u)

    def set_web(self, basis, u) -> None:
        """Aim the cold streams at the haloes around the galaxy (its
        `web`, in the simulation frame; `basis` columns: galaxy frame ->
        simulation frame)."""
        web = getattr(self.gal, "web", ())
        self.web = np.zeros((3, 3))
        self.web_w = np.ones(3)
        if WEB_STREAMS != "random" and web:
            dirs = [np.asarray(basis).T @ np.array(o[:3]) for o in web]
            ws = [o[3] for o in web]
            if WEB_STREAMS == "filament":
                dirs = [dirs[0], -dirs[0]] + dirs[1:2]
                ws = [ws[0], ws[0]] + ws[1:2]
            for k, (d, w) in enumerate(zip(dirs[:3], ws[:3], strict=False)):
                self.web[k] = d
                if WEB_STREAMS != "neighbours":
                    self.web_w[k] = max(0.35, float(w) ** 0.5)
        self._web_uniforms(u)

    def _web_uniforms(self, u) -> None:
        for k in range(3):
            u.SetUniform3f(f"uWeb{k}", [float(v) for v in self.web[k]])
        u.SetUniform3f("uWebW", [float(v) for v in self.web_w])
