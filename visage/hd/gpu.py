"""GPU ray-marcher for the HD galaxy: the offline renderer's look, every frame.

The galaxy is drawn as the inside faces of a box placed in the galaxy's own
frame (spin axis = +z, model length units).  Each fragment casts the ray
from the camera through that point and integrates, front to back and in
floating point, exactly what `raymarch.render` integrates on the CPU:

* the disk-plane maps (old disk, young disk, dust) as float textures, with
  the analytic sech^2 vertical profiles, bulge (Hernquist) and bar;
* the elliptical body (two triaxial Hernquist components) and its dust lane;
* clusters, HII regions and field stars, baked into thin emissive disk-plane
  textures; merger debris, globulars and other 3D point light baked into a
  3D emissivity volume (stored as a 2D atlas of slices);
* the nucleus and the AGN glow as analytic point-spread functions;
* per-channel dust absorption (reddening), then the asinh tone map;
* the ICL envelope and the halo gas as screen-blended overlays.

Nothing is accumulated in the 8-bit framebuffer: the shader writes the
finished, tone-mapped colour of each pixel once.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter

from visage.hd.model import (
    BULGE_RGB,
    DUST_K,
    YOUNG_RGB,
    GalaxyRecipe,
    PlaneMaps,
)

# ----------------------------------------------------------------------
# Textures
# ----------------------------------------------------------------------


def float_texture(rgb: np.ndarray):
    """(H, W, 3) float array -> VTK float texture (row 0 = y minimum)."""
    import vtk
    from vtkmodules.util.numpy_support import numpy_to_vtk

    h, w, _ = rgb.shape
    img = vtk.vtkImageData()
    img.SetDimensions(w, h, 1)
    arr = numpy_to_vtk(
        np.ascontiguousarray(rgb.reshape(-1, 3), np.float32), deep=True
    )
    arr.SetName("rgb")
    img.GetPointData().SetScalars(arr)
    tex = vtk.vtkTexture()
    tex.SetInputData(img)
    tex.SetColorModeToDirectScalars()
    tex.InterpolateOn()
    tex.RepeatOff()
    tex.EdgeClampOn()
    return tex


def _splat_plane(pts, half, n, px_proto):
    """Deposit disk-plane point populations into an emissivity-per-area map
    (RGB, n x n over [-half, half]^2), blurred by each population's PSF."""
    img = np.zeros((n, n, 3), np.float64)
    cell = 2 * half / n
    for p in pts:
        fx = (p.pos[:, 0] + half) / cell - 0.5
        fy = (p.pos[:, 1] + half) / cell - 0.5
        ok = (fx >= 0) & (fx < n - 1) & (fy >= 0) & (fy < n - 1)
        sig = np.maximum(p.sigma * px_proto / cell, 0.6)
        cls = np.round(sig * 2) / 2
        for s in np.unique(cls[ok]):
            m = ok & (cls == s)
            x0, y0 = fx[m].astype(int), fy[m].astype(int)
            wx, wy = fx[m] - x0, fy[m] - y0
            val = p.lum[m, None] * p.rgb[m] / (cell * cell)
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
    return img.astype(np.float32)


def _splat_volume(pts, half, n, px_proto):
    """3D point light -> emissivity-per-volume grid (n^3 over [-half, half]^3),
    returned as a 2D atlas of z slices plus its tile layout."""
    vol = np.zeros((n, n, n, 3), np.float64)
    cell = 2 * half / n
    for p in pts:
        f = (p.pos + half) / cell - 0.5
        ok = np.all((f >= 0) & (f < n - 1), axis=1)
        i = np.floor(f[ok]).astype(int)
        w = f[ok] - i
        val = p.lum[ok, None] * p.rgb[ok] / cell**3
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    ww = (
                        (w[:, 0] if dx else 1 - w[:, 0])
                        * (w[:, 1] if dy else 1 - w[:, 1])
                        * (w[:, 2] if dz else 1 - w[:, 2])
                    )
                    for c in range(3):
                        np.add.at(
                            vol[..., c],
                            (i[:, 2] + dz, i[:, 1] + dy, i[:, 0] + dx),
                            val[:, c] * ww,
                        )
    vol = gaussian_filter(vol, (0.8, 0.8, 0.8, 0))
    nx = int(math.ceil(math.sqrt(n)))
    ny = int(math.ceil(n / nx))
    atlas = np.zeros((ny * n, nx * n, 3), np.float32)
    for k in range(n):
        tx, ty = k % nx, k // nx
        atlas[ty * n : (ty + 1) * n, tx * n : (tx + 1) * n] = vol[k]
    return atlas, nx, ny


# ----------------------------------------------------------------------
# Shader
# ----------------------------------------------------------------------

_DEC = """//VTK::PositionVC::Dec
in vec3 posMC;
// Uniforms (u*) and samplers (*Tex) are declared by VTK from the
// shader property's custom uniforms and the actor's named textures.

float sech2(float z, float h) {
  float c = cosh(clamp(z / h, -30.0, 30.0));
  return 1.0 / (c * c) / (2.0 * h);
}
float hernq(vec3 p, float a, float q, vec3 ax) {
  float m = length(vec3(p.x / ax.x, p.y / ax.y, p.z / (ax.z * q)));
  m = max(m, 0.004);
  return a / (6.2831853 * ax.x * ax.y * ax.z * q) / (m * pow(m + a, 3.0));
}
vec2 mapUV(vec2 xy, float half_, float n) {
  return (((xy + half_) / (2.0 * half_)) * (n - 1.0) + 0.5) / n;
}
float hash3(vec3 p) {
  p = fract(p * 0.3183099 + vec3(0.11, 0.17, 0.13));
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float vnoise(vec3 x) {
  vec3 i = floor(x);
  vec3 f = fract(x);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash3(i), hash3(i + vec3(1, 0, 0)), f.x),
                 mix(hash3(i + vec3(0, 1, 0)), hash3(i + vec3(1, 1, 0)), f.x), f.y),
             mix(mix(hash3(i + vec3(0, 0, 1)), hash3(i + vec3(1, 0, 1)), f.x),
                 mix(hash3(i + vec3(0, 1, 1)), hash3(i + vec3(1, 1, 1)), f.x), f.y), f.z) * 2.0 - 1.0;
}
float fbm(vec3 p) {
  float a = 0.5, s = 0.0;
  for (int i = 0; i < 4; i++) { s += a * vnoise(p); p *= 2.03; a *= 0.5; }
  return s;
}
float fbm6(vec3 p) {
  float a = 0.5, s = 0.0;
  for (int i = 0; i < 6; i++) { s += a * vnoise(p); p *= 2.03; a *= 0.55; }
  return s;
}
float fbm2(vec3 p) {
  return 0.5 * vnoise(p) + 0.25 * vnoise(p * 2.03);
}
float gauss2(float b, float s) { return exp(-0.5 * b * b / (s * s)) / (6.2831853 * s * s); }
vec3 screenB(vec3 a, vec3 b) { return 1.0 - (1.0 - a) * (1.0 - b); }
//GAS::Dec
"""

_IMPL = """//VTK::Light::Impl
  vec3 ro = uCam;
  vec3 rd = normalize(posMC - uCam);
  vec3 inv = 1.0 / rd;
  vec3 ta = (uBoxLo - ro) * inv;
  vec3 tb = (uBoxHi - ro) * inv;
  vec3 tmn = min(ta, tb);
  vec3 tmx = max(ta, tb);
  float t0 = max(max(max(tmn.x, tmn.y), tmn.z), 0.0);
  float t1 = min(min(tmx.x, tmx.y), tmx.z);

  // Closest approach to the centre (nucleus, AGN, ICL, gas overlays).
  float tc = max(-dot(ro, rd), 0.0);
  vec3 cp = ro + tc * rd;
  float bimp = length(cp);

  // Step sizes: fine inside the disk's own slab (|x|,|y| < map half,
  // |z| < zcut) and the core sphere (the body sphere for ellipticals), the
  // debris volume's cell size inside its cube, coarse elsewhere -- and
  // never step over the start of a finer region.
  vec3 dLo = vec3(-uMapHalf, -uMapHalf, -uZCut);
  vec3 dHi = vec3(uMapHalf, uMapHalf, uZCut);
  vec3 da = (dLo - ro) * inv;
  vec3 db = (dHi - ro) * inv;
  float slabA = max(max(min(da.x, db.x), min(da.y, db.y)), min(da.z, db.z));
  float slabB = min(min(max(da.x, db.x), max(da.y, db.y)), max(da.z, db.z));
  if (uIsDisk < 0.5 || slabB < slabA) { slabA = 1e30; slabB = -1e30; }
  float bco = dot(ro, rd);
  float disc = bco * bco - (dot(ro, ro) - uRCore * uRCore);
  float cA = 1e30, cB = -1e30;
  if (disc > 0.0) { cA = -bco - sqrt(disc); cB = -bco + sqrt(disc); }
  vec3 aa = (vec3(-uAtlasHalf) - ro) * inv;
  vec3 ab = (vec3(uAtlasHalf) - ro) * inv;
  float atA = max(max(min(aa.x, ab.x), min(aa.y, ab.y)), min(aa.z, ab.z));
  float atB = min(min(max(aa.x, ab.x), max(aa.y, ab.y)), max(aa.z, ab.z));
  if (uHasAtlas < 0.5 || atB < atA) { atA = 1e30; atB = -1e30; }
  float dtFine = clamp(0.3 * 0.045 / max(abs(rd.z), 1e-3), 0.004, 0.03);
  if (uIsDisk < 0.5) dtFine = 0.04;
  float dtAtlas = 2.0 * uAtlasHalf / uAtlasN;
  float dtCoarse = max((t1 - t0) / 64.0, dtFine);

  vec3 col = vec3(0.0);
  vec3 tau = vec3(0.0);
  float tauC = 0.0;
  bool passedC = false;
  float t = t0;
  for (int it = 0; it < 4096; it++) {
    if (t >= t1 || float(it) >= uMaxSteps) break;
    bool fine = (t >= slabA && t <= slabB) || (t >= cA && t <= cB);
    bool inAtlas = t >= atA && t <= atB;
    float dt = fine ? dtFine : (inAtlas ? dtAtlas : dtCoarse);
    if (!fine) {
      if (t < slabA) dt = min(dt, max(slabA - t, 1e-4));
      if (t < cA) dt = min(dt, max(cA - t, 1e-4));
      if (!inAtlas && t < atA) dt = min(dt, max(atA - t, 1e-4));
    }
    dt = min(dt, t1 - t);
    vec3 p = ro + (t + 0.5 * dt) * rd;
    vec3 e = vec3(0.0);
    float kappa = 0.0;
    if (uIsDisk > 0.5) {
      if (abs(p.x) < uMapHalf && abs(p.y) < uMapHalf) {
        vec3 m = texture(mapTex, mapUV(p.xy, uMapHalf, uMapN)).rgb;
        e += m.r * sech2(p.z, uHz) * uOldRGB + m.g * sech2(p.z, 0.06) * uYoungRGB;
        kappa = m.b * sech2(p.z, 0.045);
        vec2 puv = mapUV(p.xy, uMapHalf, uPtsN);
        e += texture(ptsThinTex, puv).rgb * sech2(p.z, 0.045)
           + texture(ptsFieldTex, puv).rgb * sech2(p.z, 0.03);
      }
      float bul = uLBulge * hernq(p, uBulgeA, uBulgeQ, vec3(1.0));
      if (uBarLen > 0.0) {
        float bx = uBarLen, by = uBarLen * uBarAxis;
        float bar = exp(-(pow(abs(p.x) / bx, 2.4) + pow(abs(p.y) / by, 2.4)));
        bul += uLBar * bar * sech2(p.z, 0.12) / (3.14159265 * bx * by * 0.92);
      }
      e += bul * uBulgeRGB;
    } else {
      e += uCoreFrac * hernq(p, 0.22, 1.0, uEllAxes) * uBulgeRGB
         + (1.0 - uCoreFrac) * hernq(p, uEnvA, 1.0, uEllAxes) * (uOldRGB * 0.95 + 0.05);
      if (uDustLane > 0.0) {
        float rr = length(p.xz);
        kappa = uDustLane * 2.5 * exp(-rr / 0.25) * (1.0 - exp(-pow(rr / 0.05, 2.0)))
              * sech2(p.y, 0.02);
      }
    }
    if (uLIcl > 0.0) e += uLIcl * hernq(p, uIclA, 0.85, vec3(1.0)) * (uOldRGB * 0.9 + 0.08);
    if (uHasAtlas > 0.5) {
      // 3D emissivity volume stored as a 2D atlas of z slices (inlined:
      // samplers are declared after the PositionVC::Dec block).
      vec3 q = (p + uAtlasHalf) / (2.0 * uAtlasHalf);
      if (all(greaterThanEqual(q, vec3(0.0))) && all(lessThanEqual(q, vec3(1.0)))) {
        float zf = q.z * uAtlasN - 0.5;
        float z0 = clamp(floor(zf), 0.0, uAtlasN - 1.0);
        float z1 = min(z0 + 1.0, uAtlasN - 1.0);
        float fz = clamp(zf - z0, 0.0, 1.0);
        vec2 inT = clamp(q.xy * uAtlasN, 0.5, uAtlasN - 0.5);
        vec2 a0 = vec2(mod(z0, uAtlasNx), floor(z0 / uAtlasNx)) * uAtlasN + inT;
        vec2 a1 = vec2(mod(z1, uAtlasNx), floor(z1 / uAtlasNx)) * uAtlasN + inT;
        e += mix(texture(atlasTex, a0 / uAtlasSize).rgb,
                 texture(atlasTex, a1 / uAtlasSize).rgb, fz);
      }
    }
    vec3 att = exp(-(tau + 0.5 * kappa * dt * uDustK) );
    col += e * dt * att;
    tau += kappa * dt * uDustK;
    if (!passedC && t + dt >= tc) { tauC = tau.g; passedC = true; }
    t += dt;
  }
  if (!passedC) tauC = tau.g;

  // Nucleus and AGN glow (analytic PSFs, dimmed by the dust at the centre).
  vec3 tC = exp(-0.5 * tauC * uDustK);
  if (uLNuc > 0.0)
    col += uLNuc * gauss2(bimp, max(uNucSig, 0.8 * uPixProto)) * vec3(1.0, 0.93, 0.85) * tC;
  if (uAgn > 0.0) {
    float L = 8.0 * uAgn;
    col += L * (gauss2(bimp, 0.9 * uPixProto) + 0.15 * gauss2(bimp, 4.0 * uPixProto)
              + 0.05 * gauss2(bimp, uFrameProto / 60.0)) * vec3(0.85, 0.92, 1.0) * tC;
  }

  // asinh tone map (as raymarch.tonemap).
  float lum = (col.r + col.g + col.b) / 3.0;
  float x = max(lum / uWhite, 1e-12);
  float f = asinh(uQ * x) / asinh(uQ) / x;
  vec3 outc = col / uWhite * f;
  float l2 = (outc.r + outc.g + outc.b) / 3.0;
  outc = clamp(vec3(l2) + uSat * (outc - vec3(l2)), 0.0, 1.0);

  // ICL envelope (display overlay, around the closest-approach point).
  if (uIclOpacity > 0.0) {
    vec2 rot = vec2(cos(uIclAng) * cp.x + sin(uIclAng) * cp.y,
                    (-sin(uIclAng) * cp.x + cos(uIclAng) * cp.y) / 0.8);
    float R = length(vec3(rot, cp.z / 0.8)) + 1e-3;
    float prof = pow(1.0 + pow(R / (0.5 * uIclRin), 2.0), -1.2)
               * (1.0 - exp(-pow(R / (0.35 * uIclRin), 2.0)))
               * exp(-pow(R / (2.2 * uIclRin), 2.0))
               * exp(0.2 * fbm(cp * 3.0 / uIclRin));
    vec3 icl = clamp(uIclOpacity * 0.8 * prof * vec3(1.0, 0.82, 0.6), 0.0, 1.0);
    outc = screenB(outc, icl);
  }
  //GAS::Impl
  float a = max(max(outc.r, outc.g), outc.b);
  gl_FragData[0] = vec4(outc / max(a, 1e-6), a);
"""


def icl_stars(gal, rc, px_proto):
    """The ICL's stripped stars (as raymarch.icl_zone's sprinkle), in 3D:
    drawn from the same envelope profile, display brightness as there."""
    rng = np.random.default_rng(rc.seed + 13)
    r_in = 1.2 * rc.extent

    def prof(r):
        p = (1 + (r / (0.5 * r_in)) ** 2) ** -1.2
        p *= 1 - np.exp(-((r / (0.35 * r_in)) ** 2))
        return p * np.exp(-((r / (2.2 * r_in)) ** 2))

    rr = np.linspace(0, 4 * r_in, 2000)
    cdf = np.cumsum(rr**2 * prof(rr))
    cdf /= cdf[-1]
    n = int(np.clip(gal.ics / 1e8, 200, 6000))
    r = np.interp(rng.uniform(0, 1, n), cdf, rr)
    v = rng.normal(size=(n, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    pos = v * r[:, None] * np.array([1.0, 0.8, 0.8])
    f = float(np.clip((np.log10(gal.ics) - 9.0) / 3.0, 0.0, 1.0))
    opacity = 0.025 + 0.1 * f
    c = np.clip(opacity * 1.3 * rng.uniform(0.3, 1.0, n), 0.0, 1.0)
    colour = c[:, None] * np.array([1.0, 0.82, 0.6])
    return pos, np.full(n, 0.7 * px_proto * 1.5), colour


class GPUGalaxy:
    """The GPU ray-marched galaxy as one VTK actor."""

    def __init__(self, plotter):
        self._pl = plotter
        self.actor = None
        self._uni = None

    def build(
        self,
        rc: GalaxyRecipe,
        maps: PlaneMaps | None,
        pts,
        white: float,
        user_matrix: np.ndarray,
        gal=None,
        gas=None,
    ):
        """Create the actor.  `user_matrix` (4x4) maps galaxy-frame model
        units to world coordinates; `gas` is an optional GasSpec."""
        import pyvista as pv
        import vtk

        self.clear()
        self.rc = rc
        disk = rc.kind == "disk"
        E = rc.extent * (1.3 if disk else 1.0)
        self.frame_proto = 2 * E
        px_proto = 2 * E / 1024.0

        # Split point populations: thin disk-plane ones -> textures, the
        # rest (3D) -> the emissivity volume.
        thin_names = {"clusters", "hii", "ring", "ring_hii"}
        thin = [p for p in pts if disk and p.name in thin_names]
        field = [p for p in pts if disk and p.name == "field"]
        # Point-like 3D sources (an elliptical's field stars and globular
        # clusters) are tiny splats; only diffuse 3D light (merger shells,
        # tails, streams) goes into the emissivity volume.
        sprinkle = [
            p for p in pts if not disk and p.name in ("field", "globulars")
        ]
        vol = [p for p in pts if p.name in ("shells", "tails", "stream")]

        tex = {}
        if disk:
            dA = (2 * maps.half / (maps.old.shape[0] - 1)) ** 2
            n_old = 1.0 / (maps.old.sum() * dA)
            n_young = 1.0 / (maps.young.sum() * dA)
            m = np.dstack(
                [
                    rc.l_disk * n_old * maps.old,
                    rc.l_young * 1.2 * n_young * maps.young,
                    maps.dust,
                ]
            ).astype(np.float32)
            tex["mapTex"] = float_texture(m)
            npts = 2048
            tex["ptsThinTex"] = float_texture(
                _splat_plane(thin, maps.half, npts, px_proto)
            )
            tex["ptsFieldTex"] = float_texture(
                _splat_plane(field, maps.half, npts, px_proto)
            )
            map_half, map_n = maps.half, maps.old.shape[0]
        else:
            dummy = np.zeros((2, 2, 3), np.float32)
            for k in ("mapTex", "ptsThinTex", "ptsFieldTex"):
                tex[k] = float_texture(dummy)
            map_half, map_n, npts = 1.0, 2, 2

        has_atlas = bool(vol)
        atlas_half, atlas_n, atlas_nx, atlas_size = 1.0, 2, 1, (2, 2)
        if has_atlas:
            allpos = np.vstack([p.pos for p in vol])
            atlas_half = float(max(np.percentile(np.abs(allpos), 99.5), E))
            atlas_n = 112
            atlas, nx, ny = _splat_volume(vol, atlas_half, atlas_n, px_proto)
            tex["atlasTex"] = float_texture(atlas)
            atlas_nx, atlas_size = nx, (nx * atlas_n, ny * atlas_n)
        else:
            tex["atlasTex"] = float_texture(np.zeros((2, 2, 3), np.float32))

        # Bounding box of everything optical (gas extends it if on).
        if disk:
            hx = max(map_half, atlas_half if has_atlas else 0.0)
            hz = max(1.5, atlas_half if has_atlas else 0.0, 8 * rc.bulge_a)
        else:
            hx = hz = max(E * 1.5, atlas_half if has_atlas else 0.0)
        if gal is not None:
            # Room for the halo gas (Rvir) whether or not it is shown, so the
            # Gas box can be toggled without rebuilding.
            hx = hz = max(hx, 1.05 * max(gal.rvir_kpc, 20.0) / rc.unit_kpc)
        lo, hi = np.array([-hx, -hx, -hz]), np.array([hx, hx, hz])
        box = pv.Box(
            bounds=(lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
        ).triangulate()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(box)
        mapper.ScalarVisibilityOff()
        # The shader needs vertexMC to be the true galaxy-frame coordinate;
        # VTK otherwise shifts/scales vertex data for precision on its own.
        mapper.SetVBOShiftScaleMethod(0)  # DISABLE_SHIFT_SCALE
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.PickableOff()
        self._pl.add_actor(actor, reset_camera=False, render=False)
        prop = actor.GetProperty()
        prop.LightingOff()
        prop.FrontfaceCullingOn()  # draw the far faces: works from inside too
        prop.SetOpacity(0.999)  # translucent pass: blend over the sky
        for name, t in tex.items():
            prop.SetTexture(name, t)
        m4 = vtk.vtkMatrix4x4()
        for i in range(4):
            for j in range(4):
                m4.SetElement(i, j, float(user_matrix[i, j]))
        actor.SetUserMatrix(m4)

        sp = actor.GetShaderProperty()
        sp.AddVertexShaderReplacement(
            "//VTK::PositionVC::Dec",
            True,
            "//VTK::PositionVC::Dec\nout vec3 posMC;\n",
            False,
        )
        sp.AddVertexShaderReplacement(
            "//VTK::PositionVC::Impl",
            True,
            "//VTK::PositionVC::Impl\nposMC = vertexMC.xyz;\n",
            False,
        )
        from visage.hd.gpu_gas import GLSL_IMPL as gas_glsl

        dec, impl = _DEC, _IMPL.replace("  //GAS::Impl", gas_glsl)
        sp.AddFragmentShaderReplacement(
            "//VTK::PositionVC::Dec", True, dec, False
        )
        sp.AddFragmentShaderReplacement(
            "//VTK::Light::Impl", True, impl, False
        )

        u = sp.GetFragmentCustomUniforms()
        f = u.SetUniformf
        f("uIsDisk", 1.0 if disk else 0.0)
        f("uMapHalf", float(map_half))
        f("uMapN", float(map_n))
        f("uPtsN", float(npts))
        f("uHz", float(rc.hz))
        f("uBulgeA", float(rc.bulge_a))
        f("uBulgeQ", float(rc.bulge_q))
        f("uLBulge", float(rc.l_bulge if disk else 0.0))
        f("uBarLen", float(rc.bar_len if disk else 0.0))
        f("uBarAxis", float(rc.bar_axis))
        f("uLBar", float(rc.l_bar))
        u.SetUniform3f("uOldRGB", [float(v) for v in rc.old_rgb])
        u.SetUniform3f("uBulgeRGB", [float(v) for v in rc.bulge_rgb])
        u.SetUniform3f("uYoungRGB", [float(v) for v in YOUNG_RGB])
        u.SetUniform3f("uEllAxes", [float(v) for v in rc.axes])
        f("uEnvA", float(rc.env_a))
        f("uCoreFrac", float(rc.core_frac))
        f("uDustLane", float(0.0 if disk else rc.dust_lane))
        f("uLIcl", float(rc.l_icl))
        f("uIclA", float(rc.icl_a))
        f("uZCut", float(7 * max(rc.hz, 0.06)))
        f(
            "uRCore",
            float(
                max(8 * rc.bulge_a, 1.3 * rc.bar_len, 0.5) if disk else 1.5 * E
            ),
        )
        f("uHasAtlas", 1.0 if has_atlas else 0.0)
        f("uAtlasHalf", float(atlas_half))
        f("uAtlasN", float(atlas_n))
        f("uAtlasNx", float(atlas_nx))
        u.SetUniform2f(
            "uAtlasSize", [float(atlas_size[0]), float(atlas_size[1])]
        )
        u.SetUniform3f("uDustK", [float(v) for v in DUST_K])
        f("uWhite", float(white))
        f("uQ", 40.0)
        f("uSat", 1.05)
        f("uLNuc", float(rc.l_nucleus))
        f("uNucSig", float(rc.nucleus_sigma))
        f("uAgn", float(rc.agn))
        f("uPixProto", float(px_proto))
        f("uFrameProto", float(self.frame_proto))
        f("uMaxSteps", 1500.0)
        u.SetUniform3f("uBoxLo", [float(v) for v in lo])
        u.SetUniform3f("uBoxHi", [float(v) for v in hi])
        u.SetUniform3f("uCam", [0.0, 0.0, 10.0])
        self._icl_uniforms(u, rc, gal)
        from visage.hd.gpu_gas import GasSpec

        self.gas = GasSpec(gal, rc) if gal is not None else None
        if self.gas is not None:
            self.gas.set_uniforms(u, on=gas is not None and gas is not False)
        else:
            u.SetUniformf("uGasOn", 0.0)
        self.actor, self._uni = actor, u
        self.box_half = (hx, hz)
        # Point-like stars: the elliptical's field stars and globulars, and
        # the ICL's stripped stars.
        parts = []
        if sprinkle:
            pos = np.vstack([p.pos for p in sprinkle])
            sig = (
                np.concatenate([np.maximum(p.sigma, 0.6) for p in sprinkle])
                * px_proto
            )
            lum = np.concatenate([p.lum for p in sprinkle])
            rgb = np.vstack([p.rgb for p in sprinkle])
            # Each is a pixel-sized dot in the offline renders: give it the
            # tone-mapped brightness of its own peak.
            x = np.maximum(lum / (2 * np.pi * sig**2) / white, 1e-12)
            c = np.clip(np.arcsinh(40.0 * x) / np.arcsinh(40.0), 0.0, 1.0)
            parts.append((pos, 1.5 * sig, c[:, None] * rgb))
        if gal is not None and gal.ics > 0:
            parts.append(icl_stars(gal, rc, px_proto))
        if parts:
            self._add_sprinkle(
                np.vstack([p[0] for p in parts]),
                np.concatenate([p[1] for p in parts]),
                np.vstack([p[2] for p in parts]),
                user_matrix,
            )
        return actor

    def _add_sprinkle(self, pos, radius, colour, user_matrix):
        """Point-like stars as additive gaussian splats (display colours)."""
        import pyvista as pv
        import vtk

        cloud = pv.PolyData(pos.astype(np.float64))
        cloud["rgb"] = np.clip(colour, 0.0, 1.0).astype(np.float32)
        cloud["radius"] = radius.astype(np.float32)
        a = self._pl.add_mesh(
            cloud,
            scalars="rgb",
            rgb=True,
            style="points_gaussian",
            emissive=True,
            show_scalar_bar=False,
            render=False,
            reset_camera=False,
            pickable=False,
        )
        a.mapper.SetScaleArray("radius")
        a.mapper.SetScaleFactor(1.0)
        m4 = vtk.vtkMatrix4x4()
        for i in range(4):
            for j in range(4):
                m4.SetElement(i, j, float(user_matrix[i, j]))
        a.SetUserMatrix(m4)
        self.sprinkle_actor = a

    def _icl_uniforms(self, u, rc, gal):
        ics = getattr(gal, "ics", 0.0) if gal is not None else 0.0
        if ics > 0:
            f = float(np.clip((np.log10(ics) - 9.0) / 3.0, 0.0, 1.0))
            opacity = 0.025 + 0.1 * f
        else:
            opacity = 0.0
        r_in = 1.2 * rc.extent  # model units (as unit_kpc cancels)
        rng = np.random.default_rng(rc.seed + 11)
        u.SetUniformf("uIclOpacity", float(opacity))
        u.SetUniformf("uIclRin", float(r_in))
        u.SetUniformf("uIclAng", float(rng.uniform(0, np.pi)))

    def set_gas(self, on: bool) -> None:
        if self._uni is not None and self.gas is not None:
            self._uni.SetUniformf("uGasOn", 1.0 if on else 0.0)

    def set_view_half(self, half_kpc: float) -> None:
        """How much of the halo is in view (kpc half-width): the hot gas
        switches to its log stretch on halo-wide views and the streams are
        normalised to the visible frame, as in the 2D overlay."""
        if self._uni is None or self.gas is None:
            return
        self._uni.SetUniformf(
            "uHotLog", 1.0 if half_kpc > 0.5 * self.gas.rvir else 0.0
        )
        self._uni.SetUniformf(
            "uStreamNorm", float(self.gas.stream_norm(half_kpc))
        )

    def set_camera(self, cam_model: np.ndarray) -> None:
        """Camera position in the galaxy frame (model units)."""
        if self._uni is not None:
            self._uni.SetUniform3f("uCam", [float(v) for v in cam_model])

    def clear(self) -> None:
        for a in (self.actor, getattr(self, "sprinkle_actor", None)):
            if a is not None:
                self._pl.remove_actor(a, render=False)
        self.actor = None
        self.sprinkle_actor = None
        self._uni = None


__all__ = ["BULGE_RGB", "GPUGalaxy", "float_texture"]
