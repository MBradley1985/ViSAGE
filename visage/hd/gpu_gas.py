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
from visage.hd.raymarch import hot_opacity

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
      float sb = pow(1.0 + pow(R / (0.15 * rvir), 2.0), -0.5) * exp(-pow(R / rvir, 8.0));
      if (uHotLog > 0.5) sb = log(1.0 + sb / 0.02) / log(1.0 + 1.0 / 0.02);
      float wob = exp(0.3 * fbm(cpk / (0.25 * rvir) + vec3(11.0)) / uFbmStd);
      sb *= 1.0 - 0.85 * exp(-pow(R / (1.6 * uRinKpc * wob), 2.0));
      sb /= (uHotLog > 0.5 ? uHotNormLog : uHotNormLin);
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
      float w = 0.12 + 0.3 * clamp(R / rvir, 0.0, 1.0);
      float st = 0.0;
      for (int k = 0; k < 3; k++) {
        float t0 = k == 0 ? uStreamT0.x : (k == 1 ? uStreamT0.y : uStreamT0.z);
        float d = th - t0 - 0.25 * lnr;
        d = atan(sin(d), cos(d));
        st += exp(-pow(d / w, 2.0));
      }
      st *= 1.0 - exp(-pow(R / (0.04 * rvir), 2.0));
      float fil = exp(-pow(fbm2(cpk / (0.5 * rvir) + vec3(37.0)) / uFbm2Std / 0.35, 2.0));
      float clump = exp(0.55 * fbm6(cpk / (0.08 * rvir) + vec3(51.0)) / uFbm6Std);
      float cgm = env * (0.12 + 0.8 * st + 0.35 * fil) * clump;
      cgm *= exp(-pow(R / (0.95 * rvir), 8.0));
      gas += uStreamAmp * (cgm / uStreamNorm) * uCgmRGB;
    }

    if (uJetAmp > 0.0) {
      float pj = max(proj, 0.25);
      float len = (15.0 + 25.0 * uJetAmp) * pj;
      float jet = exp(-pow(perp / (0.4 + 0.04 * abs(along)), 2.0)) * exp(-pow(along / len, 6.0));
      float lobes = exp(-(pow(along - len, 2.0) + perp * perp) / pow(0.25 * len, 2.0))
                  + exp(-(pow(along + len, 2.0) + perp * perp) / pow(0.25 * len, 2.0));
      gas += 0.6 * uJetAmp * (0.6 * jet + 0.5 * lobes) * uJetRGB;
    }

    if (uWindAmp > 0.0) {
      float wnd;
      if (proj < 0.15) {
        wnd = 0.12 * uWindAmp * exp(-pow(R / (0.6 * uWindLen), 2.0));
      } else {
        float width = 0.25 * uDiskRKpc + abs(along) * tan(uWindOpen);
        float cone = exp(-pow(perp / width, 2.0)) * exp(-abs(along) / (uWindLen * proj));
        float fil = exp(-pow(fbm(cpk / 3.0 + vec3(61.0)) / uFbmStd / 0.35, 2.0));
        wnd = 0.35 * uWindAmp * cone * (0.3 + 0.9 * fil);
      }
      gas += wnd * uWindRGB;
    }
    outc = screenB(outc, clamp(gas, 0.0, 1.0));
  }
"""


class GasSpec:
    """Uniform values for the gas overlay of one galaxy."""

    glsl_impl = GLSL_IMPL

    def __init__(self, gal, rc: GalaxyRecipe):
        self.gal, self.rc = gal, rc
        self.rvir = max(gal.rvir_kpc, 20.0)
        self.half = 1.05 * self.rvir / rc.unit_kpc  # model units
        self.r_in = 1.2 * rc.extent * rc.unit_kpc
        self.hot = hot_opacity(gal.hot_gas) if gal.hot_gas > 0 else 0.0

        self.stream_amp = 0.0
        if gal.cgm_gas > 0:
            self.stream_amp = 0.8 * float(
                np.clip((np.log10(gal.cgm_gas) - 8.5) / 3.0, 0.05, 1.0)
            )
        elif gal.hot_gas > 0 and gal.mdot_stream > 0:
            self.stream_amp = 0.8 * float(
                np.clip((np.log10(gal.mdot_stream) + 6.0) / 1.5, 0.3, 1.0)
            )
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
        self.disk_r = rc.extent * rc.unit_kpc * 0.5
        self.wind = 0.0
        if gal.outflow_rate > 0.05:
            self.wind = float(
                np.clip((np.log10(gal.outflow_rate) + 1.0) / 2.5, 0.1, 1.0)
            )
        self.wind_len = (
            float(np.clip(8 * gal.outflow_rate**0.35, 4, 40))
            + self.disk_r * 0.5
        )
        # Winds reach further the more gas has been blown right out of the
        # halo (SAGE's ejected reservoir).
        halo_gas = gal.hot_gas + gal.cgm_gas + gal.ejected
        if gal.ejected > 0 and halo_gas > 0:
            self.wind_len *= 1.0 + 1.5 * float(gal.ejected / halo_gas)

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
        self.wind_open = float(
            np.deg2rad(np.clip(25 + 5 * gal.mass_loading, 20, 45))
        )

        self.norm_lin, self.norm_log = self._hot_norms()
        self._stream_norms: dict = {}

    def _hot_norms(self):
        """Peak of the (cavity-thinned) hot profile, linear and log-stretched,
        so its brightest point sits at the chosen opacity (as in 2D)."""
        R = np.linspace(0.0, 1.05 * self.rvir, 4000) + 1e-3
        sb = (1 + (R / (0.15 * self.rvir)) ** 2) ** -0.5 * np.exp(
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
        w = 0.12 + 0.3 * np.clip(R / rv, 0, 1)
        st = sum(
            np.exp(-((np.angle(np.exp(1j * (th - t0 - 0.25 * lnr))) / w) ** 2))
            for t0 in self.t0
        )
        st *= 1 - np.exp(-((R / (0.04 * rv)) ** 2))
        fil = np.exp(
            -((fbm2(P / (0.5 * rv) + 37.0) / _std("fbm2") / 0.35) ** 2)
        )
        clump = np.exp(0.55 * fbm6(P / (0.08 * rv) + 51.0) / _std("fbm6"))
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
        f("uWindAmp", float(self.wind))
        f("uWindLen", float(self.wind_len))
        f("uWindOpen", float(self.wind_open))
        f("uDiskRKpc", float(self.disk_r))
        u.SetUniform3f("uHotRGB", [float(v) for v in self.hot_rgb])
        u.SetUniform3f("uCgmRGB", [float(v) for v in self.cgm_rgb])
        f("uCavR", float(self.cav_r))
        f("uCavAmp", float(self.cav))
        u.SetUniform3f("uJetRGB", [float(v) for v in JET_RGB])
        u.SetUniform3f("uWindRGB", [float(v) for v in WIND_RGB])
