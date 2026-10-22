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


def float_texture(
    rgb: np.ndarray, interpolate: bool = True, mipmap: bool = False
):
    """(H, W, 3 or 4) float array -> VTK float texture (row 0 = y minimum)."""
    import vtk
    from vtkmodules.util.numpy_support import numpy_to_vtk

    h, w, nc = rgb.shape
    img = vtk.vtkImageData()
    img.SetDimensions(w, h, 1)
    arr = numpy_to_vtk(
        np.ascontiguousarray(rgb.reshape(-1, nc), np.float32), deep=True
    )
    arr.SetName("rgb")
    img.GetPointData().SetScalars(arr)
    tex = vtk.vtkTexture()
    tex.SetInputData(img)
    tex.SetColorModeToDirectScalars()
    tex.SetInterpolate(bool(interpolate))
    # Mipmaps: the shader picks the level from the pixel footprint
    # (textureLod), so maps seen from afar are filtered, not aliased.
    tex.SetMipmap(bool(mipmap))
    tex.RepeatOff()
    tex.EdgeClampOn()
    return tex


def _splat_plane(pts, half, n, px_proto):
    """Deposit disk-plane point populations into an emissivity-per-area map
    (RGB, n x n over [-half, half]^2), blurred by each population's PSF."""
    cell = 2 * half / n
    layers: dict = {}
    for p in pts:
        fx = (p.pos[:, 0] + half) / cell - 0.5
        fy = (p.pos[:, 1] + half) / cell - 0.5
        ok = (fx >= 0) & (fx < n - 1) & (fy >= 0) & (fy < n - 1)
        sig = np.maximum(p.sigma * px_proto / cell, 0.6)
        # PSF classes a factor of 2 apart: one blur per class.
        cls = 2.0 ** np.round(np.log2(sig))
        for s in np.unique(cls[ok]):
            m = ok & (cls == s)
            x0, y0 = fx[m].astype(int), fy[m].astype(int)
            wx, wy = fx[m] - x0, fy[m] - y0
            val = p.lum[m, None] * p.rgb[m] / (cell * cell)
            layer = layers.setdefault(float(s), np.zeros((3, n * n)))
            for dx, dy, w in (
                (0, 0, (1 - wx) * (1 - wy)),
                (1, 0, wx * (1 - wy)),
                (0, 1, (1 - wx) * wy),
                (1, 1, wx * wy),
            ):
                flat = (y0 + dy) * n + (x0 + dx)
                for c in range(3):
                    layer[c] += np.bincount(
                        flat, weights=val[:, c] * w, minlength=n * n
                    )
    img = np.zeros((n, n, 3), np.float64)
    for s, layer in layers.items():
        img += gaussian_filter(
            layer.reshape(3, n, n).astype(np.float32), (0, s, s), truncate=3.0
        ).transpose(1, 2, 0)
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


# Point sources drawn exactly by the shader: each one's own PSF, sized to
# the screen pixel, so clusters, HII regions and field stars stay sharp at
# any zoom.  Intrinsic sizes (fraction of the offline PSF, `Points.sigma`).
_POINT_SIZE = {
    "clusters": 0.2,
    "midclusters": 0.2,
    "ring": 0.2,
    "field": 0.0,  # stars are points: always one pixel across
    "hii": 0.35,
    "ring_hii": 0.35,
}
# Beyond this pixel footprint (model units) the stars are sub-pixel and the
# splatted textures take over.
FP_MAX = 0.02
GRID_CELL = 0.1
PER_CELL = 8
Z_EXACT = 0.25
_ENT_W = 4096
_IDX_W = 2048


# Point populations drawn as diffuse light in the 3D emissivity volume.
VOLUME_POPS = (
    "shells",
    "tails",
    "stream",
    "tidal",
    "iclstream",
    "halpha",
    "jelly",
    "strip",
)


def _rows(a: np.ndarray, width: int) -> np.ndarray:
    """(N, C) -> (ceil(N / width), width, C), zero padded."""
    n, c = a.shape
    h = max(1, -(-n // width))
    out = np.zeros((h * width, c), np.float32)
    out[:n] = a
    return out.reshape(h, width, c)


# Levels of detail for the exact stars: level L has cells 2^L times larger
# and is drawn exactly while a pixel is up to 2^L * FP_MAX across, each
# keeping the brightest PER_CELL stars per cell of the level below, so the
# stars on screen stay pinpoints at any distance.
N_LEVELS = 4


def _subset(sel, mask):
    from visage.hd.model import Points

    out, i = [], 0
    for p in sel:
        m = mask[i : i + len(p.lum)]
        i += len(p.lum)
        if m.any():
            out.append(
                Points(p.pos[m], p.lum[m], p.rgb[m], p.sigma[m], p.name)
            )
    return out


def _brightest_per_cell(pos, lum, cand, cell, per_cell):
    """Mask: among `cand`, the `per_cell` brightest in each cell."""
    keep = np.zeros(len(lum), bool)
    idx = np.flatnonzero(cand)
    if len(idx) == 0:
        return keep
    _, home = np.unique(
        np.floor(pos[idx] / cell).astype(np.int64), axis=0, return_inverse=True
    )
    home = home.ravel()
    order = np.lexsort((-lum[idx], home))
    first = np.r_[0, np.flatnonzero(np.diff(home[order])) + 1]
    start = np.repeat(first, np.diff(np.r_[first, len(order)]))
    sel = np.empty(len(idx), bool)
    sel[order] = (np.arange(len(order)) - start) < per_cell
    keep[idx[sel]] = True
    return keep


def split_levels(pts, n_levels: int = N_LEVELS, per_cell: int = PER_CELL):
    """(exact, rest): exact[L] are the stars level L draws exactly (nested:
    each level a subset of the one below); rest[L] are all the others, drawn
    from splats while level L is in use (rest[n_levels] = every star)."""
    sel = [p for p in pts if p.name in _POINT_SIZE and len(p.lum)]
    if not sel:
        return [[] for _ in range(n_levels)], [[] for _ in range(n_levels + 1)]
    pos = np.vstack([p.pos for p in sel])
    lum = np.concatenate([p.lum for p in sel])
    # The few stars far off the plane stay splatted: a thin grid is a short
    # walk for every ray.
    cand = np.abs(pos[:, 2]) < Z_EXACT
    exact, rest = [], []
    for L in range(n_levels):
        cand = _brightest_per_cell(pos, lum, cand, GRID_CELL * 2**L, per_cell)
        exact.append(_subset(sel, cand))
        rest.append(_subset(sel, ~cand))
    rest.append(sel)
    return exact, rest


def split_exact(pts, cell: float = GRID_CELL, per_cell: int = PER_CELL):
    """Level 0 of `split_levels`: (exact stars, the rest)."""
    exact, rest = split_levels(pts, 1, per_cell)
    return exact[0], rest[0]


def point_grid(
    pts, px_proto: float, cell: float = GRID_CELL, fp_max: float = FP_MAX
):
    """Bin point sources into a uniform 3D grid for the shader's walk.

    Each point is listed in every cell its 3-sigma sphere (at the largest
    footprint drawn exactly) touches; the shader counts a point only in the
    cell holding the ray's closest approach to it, so nothing is counted
    twice.  Returns None if there are no points.
    """
    pos, sig, col = [], [], []
    for p in pts:
        k = _POINT_SIZE.get(p.name)
        if k is None or len(p.lum) == 0:
            continue
        pos.append(p.pos)
        sig.append(k * p.sigma * px_proto)
        # Light, plus the offline PSF width (sets each one's brightness).
        col.append(
            np.column_stack([p.lum[:, None] * p.rgb, p.sigma * px_proto])
        )
    if not pos:
        return None
    pos = np.vstack(pos).astype(np.float64)
    sig = np.concatenate(sig)
    col = np.vstack(col)
    r = 3.0 * np.sqrt(sig**2 + (0.6 * fp_max) ** 2)
    rmax = float(r.max())
    lo = pos.min(axis=0) - rmax - 1e-3
    hi = pos.max(axis=0) + rmax + 1e-3
    n = np.maximum(np.ceil((hi - lo) / cell).astype(int), 1)
    hi = lo + n * cell
    i0 = np.floor((pos - r[:, None] - lo) / cell).astype(int)
    i1 = np.floor((pos + r[:, None] - lo) / cell).astype(int)
    span = int((i1 - i0).max()) + 1
    vox, src = [], []
    for dx in range(span):
        for dy in range(span):
            for dz in range(span):
                c = i0 + (dx, dy, dz)
                ok = np.all(c <= i1, axis=1)
                c = np.clip(c[ok], 0, n - 1)
                vox.append(c[:, 0] + n[0] * (c[:, 1] + n[1] * c[:, 2]))
                src.append(np.flatnonzero(ok))
    vox = np.concatenate(vox)
    src = np.concatenate(src)
    order = np.argsort(vox, kind="stable")
    vox, src = vox[order], src[order]
    nvox = int(np.prod(n))
    count = np.bincount(vox, minlength=nvox)
    offset = np.concatenate([[0], np.cumsum(count)[:-1]])
    idx = np.zeros((nvox, 3), np.float32)
    idx[:, 0] = offset
    idx[:, 1] = count
    a = np.column_stack([pos[src], sig[src]]).astype(np.float32)
    return {
        "lo": lo,
        "n": n,
        "cell": cell,
        "idx": idx,
        "pos": a,
        "col": col[src].astype(np.float32),
    }


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
// Exact integral over one step of a sech^2 layer (z0 -> z1 along the ray),
// times dt / dz: no banding however coarse the step through a thin layer.
float pint(float z0, float z1, float h, float dt) {
  float dz = z1 - z0;
  if (abs(dz) < 0.05 * h) return sech2(0.5 * (z0 + z1), h) * dt;
  return 0.5 * (tanh(clamp(z1 / h, -15.0, 15.0)) - tanh(clamp(z0 / h, -15.0, 15.0)))
         * dt / dz;
}
vec2 rayBox(vec3 ro, vec3 inv, vec3 lo, vec3 hi) {
  vec3 a = (lo - ro) * inv;
  vec3 b = (hi - ro) * inv;
  return vec2(max(max(min(a.x, b.x), min(a.y, b.y)), min(a.z, b.z)),
              min(min(max(a.x, b.x), max(a.y, b.y)), max(a.z, b.z)));
}
vec2 raySphere(vec3 ro, vec3 rd, float r) {
  float b = dot(ro, rd);
  float d = b * b - (dot(ro, ro) - r * r);
  if (d <= 0.0) return vec2(1e30, -1e30);
  return vec2(-b - sqrt(d), -b + sqrt(d));
}
float gauss2(float b, float s) { return exp(-0.5 * b * b / (s * s)) / (6.2831853 * s * s); }
vec3 screenB(vec3 a, vec3 b) { return 1.0 - (1.0 - a) * (1.0 - b); }
//GAS::Dec
"""

_IMPL = """//VTK::Light::Impl
  vec3 ro = uCam;
  vec3 rd = normalize(posMC - uCam);
  vec3 inv = 1.0 / rd;
  vec2 tb = rayBox(ro, inv, uBoxLo, uBoxHi);
  float t0 = max(tb.x, 0.0);
  float t1 = tb.y;

  // Closest approach to the centre (nucleus, AGN, ICL, gas overlays).
  float tc = max(-dot(ro, rd), 0.0);
  vec3 cp = ro + tc * rd;
  float bimp = length(cp);

  // Level of detail for the stars, from the pixel size at the galaxy:
  // level LV is drawn exactly up to 2^LV * FP_MAX, crossfading into the
  // next level (LV = uNLevels: splats only, beyond the coarsest level).
  float fpC = max(length(ro) , 1e-3) * uPixAng;
  float lf = clamp(log2(max(2.0 * fpC / uFpMax, 1e-6)), 0.0, uNLevels);
  int LV = int(floor(lf));
  float wLV = smoothstep(0.55, 1.0, lf - float(LV));
  if (float(LV) >= uNLevels) { LV = int(uNLevels + 0.5); wLV = 0.0; }
  #define REST(K, UA, UB, LA, LB) ((K) == 0 ? textureLod(rest0Tex, UA, LA).rgb \
    : (K) == 1 ? textureLod(rest1Tex, UA, LA).rgb \
    : (K) == 2 ? textureLod(rest2Tex, UB, LB).rgb \
    : (K) == 3 ? textureLod(rest3Tex, UB, LB).rgb : textureLod(rest4Tex, UB, LB).rgb)

  // Only the regions that hold light are marched; the empty rest of the
  // box is jumped.  Disk slab, core sphere (the body for an elliptical),
  // debris cube, ICL sphere.
  vec2 rS = vec2(1e30, -1e30);
  if (uIsDisk > 0.5)
    rS = rayBox(ro, inv, vec3(-uMapHalf, -uMapHalf, -uZCut), vec3(uMapHalf, uMapHalf, uZCut));
  vec2 rC = raySphere(ro, rd, uRCore);
  vec2 rA = vec2(1e30, -1e30);
  if (uHasAtlas > 0.5) rA = rayBox(ro, inv, vec3(-uAtlasHalf), vec3(uAtlasHalf));
  vec2 rI = vec2(1e30, -1e30);
  if (uLIcl > 0.0) rI = raySphere(ro, rd, uIclR);
  rS = vec2(max(rS.x, t0), min(rS.y, t1));
  rC = vec2(max(rC.x, t0), min(rC.y, t1));
  rA = vec2(max(rA.x, t0), min(rA.y, t1));
  rI = vec2(max(rI.x, t0), min(rI.y, t1));
  float rz = abs(rd.z);
  float dtAtlas = 2.0 * uAtlasHalf / uAtlasN;
  float dtIcl = max((rI.y - rI.x) / 40.0, 1e-3);
  float tEnd = max(max(rS.y, rC.y), max(rA.y, rI.y));

  vec3 col = vec3(0.0);
  vec3 tau = vec3(0.0);
  float tauC = 0.0;
  bool passedC = false;
  float t = min(min(rS.x, rC.x), min(rA.x, rI.x));
  for (int it = 0; it < 4096; it++) {
    if (t >= tEnd || float(it) >= uMaxSteps) break;
    bool inS = t >= rS.x && t < rS.y;
    bool inC = t >= rC.x && t < rC.y;
    bool inA = t >= rA.x && t < rA.y;
    bool inI = t >= rI.x && t < rI.y;
    if (!(inS || inC || inA || inI)) {
      float nx = 1e30;
      if (rS.x > t && rS.x < rS.y) nx = min(nx, rS.x);
      if (rC.x > t && rC.x < rC.y) nx = min(nx, rC.x);
      if (rA.x > t && rA.x < rA.y) nx = min(nx, rA.x);
      if (rI.x > t && rI.x < rI.y) nx = min(nx, rI.x);
      if (nx >= 1e29) break;
      if (!passedC && nx >= tc) { tauC = tau.g; passedC = true; }
      t = nx;
      continue;
    }
    float dt = 1e30;
    if (inS) {
      // Every layer is integrated exactly in z, so steps can grow away from
      // the midplane; near it they stay short enough to follow the maps.
      float zs = abs(ro.z + t * rd.z);
      dt = clamp((0.03 + 0.5 * zs) / max(rz, 1e-3), 0.004, zs < 0.15 ? 0.03 : 0.08);
    }
    if (inC) dt = min(dt, clamp(0.2 * length(ro + t * rd), uDtCore, 1.0));
    // Inside the body the step stays the body's own (finer steps there
    // would integrate the smooth light differently and outline the debris
    // cube); the debris volume is sub-sampled within the step instead.
    if (inA && !inC) dt = min(dt, dtAtlas);
    if (inI) dt = min(dt, dtIcl);
    // Never step over the start of a finer region.
    if (t < rS.x) dt = min(dt, rS.x - t);
    if (t < rC.x) dt = min(dt, rC.x - t);
    if (t < rA.x) dt = min(dt, rA.x - t);
    dt = max(min(dt, tEnd - t), 1e-4);
    vec3 p = ro + (t + 0.5 * dt) * rd;
    float z0 = ro.z + t * rd.z;
    float z1 = z0 + dt * rd.z;
    vec3 e = vec3(0.0);  // emission integrated over the step
    float kap = 0.0;     // dust optical depth over the step
    if (uIsDisk > 0.5) {
      // The layers' light sits at the midplane: sample the maps where the
      // ray is nearest it within this step, not at the step's midpoint.
      vec2 pm = (ro + clamp(-ro.z * inv.z, t, t + dt) * rd).xy;
      if (inS && abs(pm.x) < uMapHalf && abs(pm.y) < uMapHalf) {
        // Mip level from this point's pixel footprint.
        float fpS = (t + 0.5 * dt) * uPixAng;
        float lodM = max(log2(fpS * uMapN / (2.0 * uMapHalf)), 0.0);
        vec3 m = textureLod(mapTex, mapUV(pm, uMapHalf, uMapN), lodM).rgb;
        // Inside-out growth: older (redder) inside, younger outside.
        vec3 oldC = mix(uOldRGB, uOldOutRGB, smoothstep(0.0, uGradR, length(pm)));
        e += m.r * pint(z0, z1, uHz, dt) * oldC + m.g * pint(z0, z1, 0.06, dt) * uYoungRGB;
        kap = m.b * pint(z0, z1, 0.045, dt);
        {
          // Splatted stars: those the current level(s) don't draw exactly.
          vec2 uA = mapUV(pm, uMapHalf, uPtsN);
          vec2 uB = mapUV(pm, uMapHalf, 0.5 * uPtsN);
          float lA = max(log2(fpS * uPtsN / (2.0 * uMapHalf)), 0.0);
          float lB = max(lA - 1.0, 0.0);
          vec3 rs = (1.0 - wLV) * REST(LV, uA, uB, lA, lB);
          if (wLV > 0.0) rs += wLV * REST(LV + 1, uA, uB, lA, lB);
          e += uPtsGain * rs * pint(z0, z1, 0.04, dt);
        }
      }
      if (inC) {
        float bul = uLBulge * hernq(p, uBulgeA, uBulgeQ, vec3(1.0)) * dt;
        // Pseudo-bulge: compact and flattened (instability-built).
        if (uLPseudo > 0.0) bul += uLPseudo * hernq(p, uPseudoA, uPseudoQ, vec3(1.0)) * dt;
        if (uBarLen > 0.0) {
          float bx = uBarLen, by = uBarLen * uBarAxis;
          float bar = exp(-(pow(abs(p.x) / bx, 2.4) + pow(abs(p.y) / by, 2.4)));
          // A buckled bar is thickest half way out: boxy / peanut-shaped
          // seen edge-on.
          float hb = 0.12;
          if (uPeanut > 0.0)
            hb = 0.07 + 0.4 * uPeanut * exp(-pow((abs(p.x) / bx - 0.5) / 0.25, 2.0));
          bul += uLBar * bar * pint(z0, z1, hb, dt) / (3.14159265 * bx * by * 0.92);
        }
        e += bul * uBulgeRGB;
      }
    } else if (inC) {
      e += (uCoreFrac * hernq(p, 0.22, 1.0, uEllAxes) * uBulgeRGB
         + (1.0 - uCoreFrac) * hernq(p, uEnvA, 1.0, uEllAxes) * (uOldRGB * 0.95 + 0.05)) * dt;
      if (uDustLane > 0.0) {
        float rr = length(p.xz);
        float y0 = ro.y + t * rd.y;
        kap = uDustLane * 2.5 * exp(-rr / 0.25) * (1.0 - exp(-pow(rr / 0.05, 2.0)))
            * pint(y0, y0 + dt * rd.y, 0.02, dt);
      }
    }
    if (inI) e += uLIcl * hernq(p, uIclA, 0.85, vec3(1.0)) * (uOldRGB * 0.9 + 0.08) * dt;
    if (inA) {
      // 3D emissivity volume stored as a 2D atlas of z slices (inlined:
      // samplers are declared after the PositionVC::Dec block).
      int ns = int(clamp(ceil(dt / dtAtlas), 1.0, 8.0));
      vec3 acc = vec3(0.0);
      for (int k = 0; k < 8; k++) {
        if (k >= ns) break;
        vec3 pa = ro + (t + (float(k) + 0.5) / float(ns) * dt) * rd;
        vec3 q = (pa + uAtlasHalf) / (2.0 * uAtlasHalf);
        if (all(greaterThanEqual(q, vec3(0.0))) && all(lessThanEqual(q, vec3(1.0)))) {
          float zf = q.z * uAtlasN - 0.5;
          float za = clamp(floor(zf), 0.0, uAtlasN - 1.0);
          float zb = min(za + 1.0, uAtlasN - 1.0);
          float fz = clamp(zf - za, 0.0, 1.0);
          vec2 inT = clamp(q.xy * uAtlasN, 0.5, uAtlasN - 0.5);
          vec2 a0 = vec2(mod(za, uAtlasNx), floor(za / uAtlasNx)) * uAtlasN + inT;
          vec2 a1 = vec2(mod(zb, uAtlasNx), floor(zb / uAtlasNx)) * uAtlasN + inT;
          acc += mix(texture(atlasTex, a0 / uAtlasSize).rgb,
                     texture(atlasTex, a1 / uAtlasSize).rgb, fz);
        }
      }
      e += acc * dt / float(ns);
    }
    vec3 att = exp(-(tau + 0.5 * kap * uDustK));
    col += e * att;
    tau += kap * uDustK;
    if (!passedC && t + dt >= tc) { tauC = tau.g; passedC = true; }
    t += dt;
  }
  if (!passedC) tauC = tau.g;

  // Point sources, exactly: walk the grid cells the ray crosses (3D DDA);
  // each star counts in the cell holding the ray's closest approach to it.
  // Stars are drawn in display space: each gets the tone-mapped brightness
  // of its own peak at the offline renders' scale (dimmed and reddened by
  // the dust in front of it) and a profile about a pixel across, so a
  // bright star is a brighter point, not a bigger, saturated disc.
  vec3 starD = vec3(0.0);
  for (int pass = 0; pass < 2; pass++) {
    int lv = LV + pass;
    float wp = pass == 0 ? 1.0 - wLV : wLV;
    if (wp <= 0.0 || float(lv) >= uNLevels) continue;
    vec3 gLo = uGridLo0; vec3 gNf = uGridN0; float gCell = uGridCell0; float gBase = uIdxBase0;
    if (lv == 1) { gLo = uGridLo1; gNf = uGridN1; gCell = uGridCell1; gBase = uIdxBase1; }
    else if (lv == 2) { gLo = uGridLo2; gNf = uGridN2; gCell = uGridCell2; gBase = uIdxBase2; }
    else if (lv == 3) { gLo = uGridLo3; gNf = uGridN3; gCell = uGridCell3; gBase = uIdxBase3; }
    float fpMaxL = uFpMax * exp2(float(lv));
    vec2 g = rayBox(ro, inv, gLo, gLo + gNf * gCell);
    float g0 = max(g.x, 0.0);
    if (g.y > g0) {
      ivec3 N = ivec3(gNf + 0.5);
      int base = int(gBase + 0.5);
      vec3 q = ro + g0 * rd;
      ivec3 c = clamp(ivec3(floor((q - gLo) / gCell)), ivec3(0), N - ivec3(1));
      ivec3 st = ivec3(rd.x > 0.0 ? 1 : -1, rd.y > 0.0 ? 1 : -1, rd.z > 0.0 ? 1 : -1);
      vec3 tDel = abs(gCell * inv);
      vec3 tMx = (gLo + (vec3(c) + step(vec3(0.0), rd)) * gCell - ro) * inv;
      float tIn = g0;
      for (int k = 0; k < 1024; k++) {
        float tOut = min(min(tMx.x, tMx.y), tMx.z);
        int id = base + c.x + N.x * (c.y + N.y * c.z);
        vec3 oc = texelFetch(gIdxTex, ivec2(id % uIdxW, id / uIdxW), 0).rgb;
        int off = int(oc.r + 0.5);
        int cnt = int(oc.g + 0.5);
        for (int j = 0; j < cnt; j++) {
          int en = off + j;
          ivec2 ec = ivec2(en % uEntW, en / uEntW);
          vec4 A = texelFetch(gPosTex, ec, 0);
          float ts = dot(A.xyz - ro, rd);
          if (ts < tIn || ts >= tOut || ts <= 0.0) continue;
          vec3 dv = A.xyz - ro - ts * rd;
          float d2 = dot(dv, dv);
          float fp = min(ts * uPixAng, fpMaxL);
          float s2 = A.w * A.w + 0.25 * fp * fp;
          if (d2 > 9.0 * s2) continue;
          float tauP = 0.0;
          if (uIsDisk > 0.5 && abs(A.x) < uMapHalf && abs(A.y) < uMapHalf) {
            float k0 = texture(mapTex, mapUV(A.xy, uMapHalf, uMapN)).b;
            tauP = k0 * 0.5 * (1.0 + sign(rd.z) * tanh(A.z / 0.045)) / max(rz, 0.08);
          }
          vec4 C = texelFetch(gColTex, ec, 0);
          vec3 L = C.rgb * exp(-tauP * uDustK);
          float Lm = max((L.r + L.g + L.b) / 3.0, 1e-30);
          // Peak at the offline PSF width (a little sharper), against the
          // galaxy's base exposure: the same brightness at any zoom.
          float sd2 = 0.5 * C.a * C.a;
          float pk = Lm / (6.2831853 * sd2) / uWhite0;
          float cpk = min(asinh(uQ * pk) / asinh(uQ), 1.0);
          starD += wp * cpk * (L / Lm) * exp(-0.5 * d2 / s2);
        }
        if (tOut >= g.y) break;
        if (tMx.x <= tMx.y && tMx.x <= tMx.z) { c.x += st.x; tMx.x += tDel.x; }
        else if (tMx.y <= tMx.z) { c.y += st.y; tMx.y += tDel.y; }
        else { c.z += st.z; tMx.z += tDel.z; }
        if (any(lessThan(c, ivec3(0))) || any(greaterThanEqual(c, N))) break;
        tIn = tOut;
      }
    }
  }

  // Nucleus and AGN glow (analytic PSFs, dimmed by the dust at the centre).
  vec3 tC = exp(-0.5 * tauC * uDustK);
  // Point-like cores are a pixel across at any zoom, not a fixed size.
  float fpN = min(fpC, uPixProto);
  if (uLNuc > 0.0)
    col += uLNuc * gauss2(bimp, max(uNucSig, 0.8 * fpN)) * vec3(1.0, 0.93, 0.85) * tC;
  if (uAgn > 0.0) {
    float L = 8.0 * uAgn;
    col += L * (gauss2(bimp, 0.9 * fpN) + 0.15 * gauss2(bimp, 4.0 * fpN)
              + 0.05 * gauss2(bimp, uFrameProto / 60.0)) * vec3(0.85, 0.92, 1.0) * tC;
  }

  // asinh tone map (as raymarch.tonemap).
  float lum = (col.r + col.g + col.b) / 3.0;
  float x = max(lum / uWhite, 1e-12);
  float f = asinh(uQ * x) / asinh(uQ) / x;
  vec3 outc = col / uWhite * f;
  float l2 = (outc.r + outc.g + outc.b) / 3.0;
  outc = clamp(vec3(l2) + uSat * (outc - vec3(l2)), 0.0, 1.0);
  outc = screenB(outc, clamp(uPtsGain * starD, 0.0, 1.0));

  // ICL envelope (display overlay, around the closest-approach point).
  if (uIclOpacity > 0.0) {
    vec2 rot = vec2(cos(uIclAng) * cp.x + sin(uIclAng) * cp.y,
                    (-sin(uIclAng) * cp.x + cos(uIclAng) * cp.y) / 0.8);
    float R = length(vec3(rot, cp.z / 0.8)) + 1e-3;
    float prof = pow(1.0 + pow(R / (0.5 * uIclRin), 2.0), -1.2)
               * (1.0 - exp(-pow(R / (0.35 * uIclRin), 2.0)))
               * exp(-pow(R / (2.2 * uIclRin), 2.0))
               * exp(0.2 * fbm(cp * 3.0 / uIclRin));
    vec3 icl = clamp(uIclOpacity * 0.8 * prof * uIclRGB, 0.0, 1.0);
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
    colour = c[:, None] * np.asarray(rc.icl_rgb)
    return pos, np.full(n, 0.7 * px_proto * 1.5), colour


def prepare(
    rc: GalaxyRecipe,
    maps: PlaneMaps | None,
    pts,
    npts: int = 2048,
    atlas_n: int = 112,
) -> dict:
    """The CPU side of a build (numpy only, safe off the main thread): the
    texture arrays, the exact-star grid and the layout numbers the shader
    needs.  `npts` / `atlas_n`: splat and debris-volume resolution."""
    disk = rc.kind == "disk"
    E = rc.extent * (1.3 if disk else 1.0)
    px_proto = 2 * E / 1024.0
    # Stars: per level of detail, the brightest in each cell drawn exactly,
    # the rest splatted.
    stars = [p for p in pts if disk and p.name in _POINT_SIZE]
    exact, rest = split_levels(stars)
    # Point-like 3D sources (an elliptical's field stars and globular
    # clusters) are tiny splats; only diffuse 3D light (merger shells,
    # tails, streams) goes into the emissivity volume.
    sprinkle = [
        p
        for p in pts
        if (not disk and p.name in ("field", "globulars"))
        or p.name == "jellyknots"  # star-forming knots in a jellyfish tail
    ]
    # Diffuse 3D light: merger debris, tidal features, ICL streams, cooling
    # filaments, ram-pressure tails.
    vol = [p for p in pts if p.name in VOLUME_POPS]

    tex = {}
    dummy3 = np.zeros((2, 2, 3), np.float32)
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
        tex["mapTex"] = (m, "mip")
        from concurrent.futures import ThreadPoolExecutor

        # Splats of what each level leaves out (the finest two at full
        # resolution; coarser levels are only used from further away).
        sizes = [npts, npts] + [npts // 2] * (len(rest) - 2)
        with ThreadPoolExecutor(len(rest)) as ex:
            splats = list(
                ex.map(
                    lambda a: _splat_plane(a[0], maps.half, a[1], px_proto),
                    zip(rest, sizes, strict=True),
                )
            )
        for L, img in enumerate(splats):
            tex[f"rest{L}Tex"] = (img, "mip")
        map_info = (maps.half, maps.old.shape[0], npts)
    else:
        tex["mapTex"] = (dummy3, "mip")
        for L in range(N_LEVELS + 1):
            tex[f"rest{L}Tex"] = (dummy3, "mip")
        map_info = (1.0, 2, 2)

    atlas_info = None
    tex["atlasTex"] = (dummy3, "linear")
    if vol:
        allpos = np.vstack([p.pos for p in vol])
        atlas_half = float(max(np.percentile(np.abs(allpos), 99.5), E))
        atlas, nx, ny = _splat_volume(vol, atlas_half, atlas_n, px_proto)
        tex["atlasTex"] = (atlas, "linear")
        atlas_info = (atlas_half, atlas_n, nx, (nx * atlas_n, ny * atlas_n))

    # One grid per level, packed into one set of textures.
    levels, idx, posl, coll = [], [], [], []
    n_vox = n_ent = 0
    for L, ex_L in enumerate(exact if disk else []):
        g = (
            point_grid(ex_L, px_proto, GRID_CELL * 2**L, FP_MAX * 2**L)
            if ex_L
            else None
        )
        if g is None:
            break
        i = g["idx"].copy()
        i[:, 0] += n_ent
        idx.append(i)
        posl.append(g["pos"])
        coll.append(g["col"])
        levels.append(
            {"lo": g["lo"], "n": g["n"], "cell": g["cell"], "base": n_vox}
        )
        n_vox += len(i)
        n_ent += len(g["pos"])
    grid = levels or None
    if grid is not None:
        tex["gIdxTex"] = (_rows(np.vstack(idx), _IDX_W), "nearest")
        tex["gPosTex"] = (_rows(np.vstack(posl), _ENT_W), "nearest")
        tex["gColTex"] = (_rows(np.vstack(coll), _ENT_W), "nearest")
    else:
        tex["gIdxTex"] = (dummy3, "nearest")
        tex["gPosTex"] = (np.zeros((2, 2, 4), np.float32), "nearest")
        tex["gColTex"] = (np.zeros((2, 2, 4), np.float32), "nearest")
    # The light maps are smooth values of order 1: half precision holds
    # them to ~0.1% and halves a build's memory (the cache of recent
    # builds, and the copy back from a worker).  Uploads are float32 as
    # before.  The exact-star tables (indices up to ~1e6, positions) stay
    # single precision.
    for k, (arr, mode) in list(tex.items()):
        if mode != "nearest":
            tex[k] = (np.asarray(arr, np.float16), mode)
    return {
        "tex": tex,
        "sprinkle": sprinkle,
        "map": map_info,
        "atlas": atlas_info,
        "grid": grid,
    }


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
        prep=None,
        icl: bool = True,
        magnify: float = 1.0,
    ):
        """Create the actor.  `user_matrix` (4x4) maps galaxy-frame model
        units to world coordinates; `gas` is an optional GasSpec.  `prep` is
        `prepare(rc, maps, pts)`, if already made (e.g. on a worker
        thread)."""
        import pyvista as pv
        import vtk

        self.clear()
        self.rc = rc
        disk = rc.kind == "disk"
        E = rc.extent * (1.3 if disk else 1.0)
        self.frame_proto = 2 * E
        px_proto = 2 * E / 1024.0

        if prep is None:
            prep = prepare(rc, maps, pts)
        tex = {
            k: float_texture(arr, mode != "nearest", mode == "mip")
            for k, (arr, mode) in prep["tex"].items()
        }
        sprinkle = prep["sprinkle"]
        map_half, map_n, npts = prep["map"]
        has_atlas = prep["atlas"] is not None
        atlas_half, atlas_n, atlas_nx, atlas_size = prep["atlas"] or (
            1.0,
            2,
            1,
            (2, 2),
        )
        grid = prep["grid"]

        # Bounding box of everything optical (gas extends it if on).
        if disk:
            hx = max(map_half, atlas_half if has_atlas else 0.0)
            hz = max(1.5, atlas_half if has_atlas else 0.0, 8 * rc.bulge_a)
        else:
            hx = hz = max(E * 1.5, atlas_half if has_atlas else 0.0)
        if gal is not None:
            # Room for the halo gas whether or not it is shown, so Gas can
            # be toggled without rebuilding: out to 1.35 Rvir, where its
            # fade at Rvir has reached zero (no box edge in view).
            hx = hz = max(hx, 1.35 * max(gal.rvir_kpc, 20.0) / rc.unit_kpc)
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

        # No halo (a group's satellites): no gas code, whose uniforms would
        # otherwise go undeclared.
        dec = _DEC
        impl = _IMPL.replace(
            "  //GAS::Impl", gas_glsl if gal is not None else ""
        )
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
        f("uLPseudo", float(rc.l_pseudo if disk else 0.0))
        f("uPseudoA", float(rc.pseudo_a))
        f("uPseudoQ", float(rc.pseudo_q))
        f("uPeanut", float(rc.peanut if disk else 0.0))
        u.SetUniform3f("uIclRGB", [float(v) for v in rc.icl_rgb])
        u.SetUniform3f(
            "uOldRGB", [float(v) for v in rc.old_in_rgb or rc.old_rgb]
        )
        u.SetUniform3f(
            "uOldOutRGB", [float(v) for v in rc.old_out_rgb or rc.old_rgb]
        )
        f("uGradR", float(rc.grad_r))
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
                max(8 * rc.bulge_a, 1.3 * rc.bar_len, 0.5) if disk else 3.0 * E
            ),
        )
        f("uDtCore", 0.004 if disk else 0.01)
        f("uIclR", float(min(4.0 * rc.icl_a, 1.75 * max(hx, hz))))
        f("uNLevels", float(len(grid) if grid else 0))
        f("uFpMax", FP_MAX)
        f("uPixAng", 1e-3)
        for L in range(N_LEVELS):
            g = (grid or [])[L] if L < len(grid or []) else None
            g = g or {
                "lo": np.zeros(3),
                "n": np.ones(3),
                "cell": 1.0,
                "base": 0,
            }
            u.SetUniform3f(f"uGridLo{L}", [float(v) for v in g["lo"]])
            u.SetUniform3f(f"uGridN{L}", [float(v) for v in g["n"]])
            f(f"uGridCell{L}", float(g["cell"]))
            f(f"uIdxBase{L}", float(g["base"]))
        u.SetUniformi("uIdxW", _IDX_W)
        u.SetUniformi("uEntW", _ENT_W)
        f("uHasAtlas", 1.0 if has_atlas else 0.0)
        f("uAtlasHalf", float(atlas_half))
        f("uAtlasN", float(atlas_n))
        f("uAtlasNx", float(atlas_nx))
        u.SetUniform2f(
            "uAtlasSize", [float(atlas_size[0]), float(atlas_size[1])]
        )
        u.SetUniform3f("uDustK", [float(v) for v in DUST_K])
        f("uWhite", float(white))
        f("uWhite0", float(white))
        f("uPtsGain", 1.0)  # star sources on (component views switch it)
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
        self._icl_uniforms(u, rc, gal if icl else None)
        from visage.hd.gpu_gas import GasSpec

        self.gas = GasSpec(gal, rc, magnify) if gal is not None else None
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

    def set_pixel(self, fp_model: float) -> None:
        """Keep the star splats about a pixel across (`fp_model`: one
        screen pixel at the galaxy, model units) rather than a fixed size
        that balloons as the camera closes in."""
        a = getattr(self, "sprinkle_actor", None)
        if a is not None:
            proto = self.frame_proto / 1024.0
            a.mapper.SetScaleFactor(float(min(1.0, 1.5 * fp_model / proto)))

    def set_white(self, white: float) -> None:
        """Tone-map white level (see `layer.Exposure`)."""
        if self._uni is not None:
            self._uni.SetUniformf("uWhite", float(white))

    def set_camera(
        self, cam_model: np.ndarray, pix_ang: float | None = None
    ) -> None:
        """Camera position in the galaxy frame (model units) and the angle
        one screen pixel subtends (radians)."""
        if self._uni is not None:
            self._uni.SetUniform3f("uCam", [float(v) for v in cam_model])
            if pix_ang is not None:
                self._uni.SetUniformf("uPixAng", float(pix_ang))

    def clear(self) -> None:
        for a in (self.actor, getattr(self, "sprinkle_actor", None)):
            if a is not None:
                self._pl.remove_actor(a, render=False)
        self.actor = None
        self.sprinkle_actor = None
        self._uni = None


__all__ = ["BULGE_RGB", "GPUGalaxy", "float_texture"]
