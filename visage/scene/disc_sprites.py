"""Galaxy splats that show a run's discs and dust, for SAGE26's DarkSAGEMode
and DustySAGEMode: each galaxy's stars and gas as an ellipse tilted to its
own stellar spin, with a bulge core at its centre, and a glow of its dust.

A splat has no direction of its own, so these carry it in their colour: rgb
holds the spin, which the shader turns by the camera each frame (`uView`), and
each sprite layer has one colour of its own."""

from __future__ import annotations

import numpy as np
import pyvista as pv

from visage.io.family_binary import _disc_group

BLUE = (0.45, 0.65, 1.0)  # stars of star-forming discs, and gas
AMBER = (1.0, 0.7, 0.42)  # stars of passive discs
CORE = (1.0, 0.8, 0.5)
DUST = (1.0, 0.45, 0.12)
STAR_FORMING = 2e-11  # sSFR, /yr
BULGE_ONLY = 0.7  # B/T above which a galaxy has no disc to draw
Q0 = 0.15  # edge-on axis ratio
DISC_SIZE = 0.6  # of the splat's radius
_MASS_RANGE = (8.0, 11.5)  # log10 Msun, faint to full
_DUST_RANGE = (5.5, 9.0)  # log10 Msun

_DISC = f"""//VTK::Color::Impl
  vec3 n = uView * (vertexColorVSOutput.rgb * 2.0 - 1.0);
  vec2 major = vec2(-n.y, n.x) / (length(n.xy) + 1e-5);
  float q = sqrt(n.z * n.z + {Q0 * Q0} * (1.0 - n.z * n.z));
  vec2 p = offsetVCVSOutput.xy;
  float ux = dot(p, major);
  float uy = dot(p, vec2(major.y, -major.x)) / max(q, 0.1);
  ambientColor = vec3(%s); diffuseColor = vec3(0.0);
  opacity = min(1.0, opacity * 1.6) * exp(-(ux * ux + uy * uy) * 1.8);
"""
_ROUND = """//VTK::Color::Impl
  ambientColor = vec3(%s); diffuseColor = vec3(0.0);
  opacity = opacity * exp(-dot(offsetVCVSOutput.xy, offsetVCVSOutput.xy) * %s);
"""


def scaled(values, lo: float, hi: float) -> np.ndarray:
    """log10 `values` from `lo` to `hi` as 0 to 1."""
    log = np.log10(np.maximum(values, 1.0))
    return np.clip((log - lo) / (hi - lo), 0.0, 1.0)


def read_spins(snap, cache: dict) -> np.ndarray | None:
    """(N, 3) stellar disc spins of `snap`'s galaxies; None if the run has
    none. The file's column is kept per snapshot in `cache`."""
    key = (snap.source_path, int(snap.snap_num))
    if key not in cache:
        try:
            with _disc_group(snap.source_path, key[1]) as group:
                has = "SpinStars" in group
                cache[key] = np.asarray(group["SpinStars"]) if has else None
        except (OSError, KeyError):
            cache[key] = None
    spins = cache[key]
    return None if spins is None else spins[snap.sage_indices]


def _splats(plotter, pos, radius, rgba, code, emissive=True):
    cloud = pv.PolyData(pos)
    cloud["rgba"] = np.clip(rgba * 255, 0, 255).astype(np.uint8)
    cloud["radius"] = radius.astype(np.float32)
    actor = plotter.add_mesh(
        cloud,
        scalars="rgba",
        rgb=True,
        style="points_gaussian",
        emissive=emissive,
        show_scalar_bar=False,
        render=False,
        reset_camera=False,
    )
    actor.mapper.SetScaleArray("radius")
    actor.mapper.SetScaleFactor(1.0)
    actor.mapper.SetSplatShaderCode(code)
    return actor


def discs(plotter, pos, spin, radius, alpha, colour):
    """Tilted ellipses; the actor, whose `uView` needs `set_view`."""
    norm = np.maximum(np.linalg.norm(spin, axis=1, keepdims=True), 1e-9)
    n = np.where(norm > 1e-8, spin / norm, np.array([0.0, 0.0, 1.0]))
    rgba = np.c_[(n + 1) / 2, alpha]
    code = _DISC % ", ".join(f"{v}" for v in colour)
    return _splats(plotter, pos, radius, rgba, code)


def glow(plotter, pos, radius, alpha, colour, falloff: float):
    """Round sprites of one colour."""
    rgba = np.c_[np.ones((len(pos), 3)), alpha]
    code = _ROUND % (", ".join(f"{v}" for v in colour), falloff)
    return _splats(plotter, pos, radius, rgba, code)


def set_view(actors, camera) -> None:
    """Point `actors`' discs by the camera."""
    m = camera.GetViewTransformMatrix()
    view = [m.GetElement(i, j) for j in range(3) for i in range(3)]
    for actor in actors:
        actor.GetShaderProperty().GetFragmentCustomUniforms().SetUniformMatrix3x3(
            "uView", view
        )
