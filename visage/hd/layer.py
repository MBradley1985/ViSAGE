"""Draw an HD galaxy into the scene with the GPU ray-marcher.

The model is built in the galaxy's own frame (spin axis = +z, model length
units) and placed in the world by a 4x4 transform: rotation aligning +z
with the galaxy's SAGE spin vector, scale to Mpc/h, and its box position.
`gpu.GPUGalaxy` ray-marches it per pixel with the same physics and tone map
as the offline renders, every frame; this layer keeps its camera uniforms
in step with the scene camera and toggles the gas overlay.
"""

from __future__ import annotations

import numpy as np

from visage.hd.gpu import GPUGalaxy
from visage.hd.model import (
    SageGalaxy,
    build_disk_maps,
    build_points,
    recipe_from_sage,
)


def galaxy_basis(spin: np.ndarray | None, seed: int) -> np.ndarray:
    """Columns e1, e2, e3: galaxy frame -> world directions (e3 = spin)."""
    rng = np.random.default_rng(seed)
    if (
        spin is None
        or not np.all(np.isfinite(spin))
        or np.linalg.norm(spin) == 0
    ):
        spin = rng.normal(size=3)
    e3 = np.asarray(spin, float) / np.linalg.norm(spin)
    trial = (
        np.array([1.0, 0.0, 0.0])
        if abs(e3[0]) < 0.9
        else np.array([0.0, 1.0, 0.0])
    )
    e1 = np.cross(e3, trial)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(e3, e1)
    # Random position angle about the spin axis, so bars/arms don't all line up.
    t = rng.uniform(0, 2 * np.pi)
    e1, e2 = np.cos(t) * e1 + np.sin(t) * e2, -np.sin(t) * e1 + np.cos(t) * e2
    return np.column_stack([e1, e2, e3])


def exposure(rc, maps, pts) -> float:
    """White level of the tone map, fixed per galaxy: as the offline renders,
    the 99.97th percentile of a face-on view (AGN excluded)."""
    from visage.hd.raymarch import render

    face = render(rc, maps, pts, inc=0, pa=25, npix=256, threads=8)
    lum = (face.total - face.points.get("agn", 0)).mean(axis=2)
    return float(np.percentile(lum, 99.97)) or 1.0


class HDGalaxyLayer:
    """One HD galaxy in a pyvista plotter."""

    def __init__(self, plotter):
        self._pl = plotter
        self._gpu = GPUGalaxy(plotter)
        self._observer = None
        self._gas_on = False
        self.gal: SageGalaxy | None = None
        self.recipe = None

    @property
    def active(self) -> bool:
        return self._gpu.actor is not None

    def show(
        self, gal: SageGalaxy, center, spin, hubble_h: float, gas: bool = False
    ):
        """Build and draw the HD model of `gal` at world position `center`."""
        self.clear()
        self.gal = gal
        rc = recipe_from_sage(gal)
        self.recipe = rc
        maps = build_disk_maps(rc, n=1024) if rc.kind == "disk" else None
        pts = build_points(rc, maps)

        self._R = galaxy_basis(spin, rc.seed)
        self._scale = rc.unit_kpc * hubble_h / 1000.0  # model units -> Mpc/h
        self._center = np.asarray(center, float)
        self._hubble_h = hubble_h
        m = np.eye(4)
        m[:3, :3] = self._R * self._scale
        m[:3, 3] = self._center
        self._gpu.build(
            rc, maps, pts, exposure(rc, maps, pts), m, gal=gal, gas=gas
        )
        self._gas_on = bool(gas)
        self._gpu.set_gas(self._gas_on)
        cam = self._pl.renderer.GetActiveCamera()
        self._observer = (
            cam,
            cam.AddObserver("ModifiedEvent", self._on_camera),
        )
        self._on_camera()

    def clear(self):
        if self._observer is not None:
            cam, tag = self._observer
            try:
                cam.RemoveObserver(tag)
            except Exception:
                pass
            self._observer = None
        self._gpu.clear()
        self.gal = None
        self.recipe = None

    def set_gas(self, on: bool):
        """Show or hide the halo-gas overlay (no rebuild: a shader switch)."""
        self._gas_on = bool(on)
        self._gpu.set_gas(self._gas_on)

    # -- geometry ------------------------------------------------------

    @property
    def radius_world(self) -> float:
        """Half-width that frames the optical galaxy, Mpc/h."""
        if self.recipe is None:
            return 0.0
        k = 1.3 if self.recipe.kind == "disk" else 1.0
        return float(self.recipe.extent * k * self._scale)

    @property
    def rvir_world(self) -> float:
        return (
            float(self.gal.rvir_kpc * self._hubble_h / 1000.0)
            if self.gal
            else 0.0
        )

    def to_model(self, world: np.ndarray) -> np.ndarray:
        return self._R.T @ (
            (np.asarray(world, float) - self._center) / self._scale
        )

    def _on_camera(self, *_):
        """Keep the shader's camera (galaxy frame) and view size current."""
        if not self.active:
            return
        cam = self._pl.renderer.GetActiveCamera()
        pos = np.array(cam.GetPosition(), float)
        self._gpu.set_camera(self.to_model(pos))
        dist = np.linalg.norm(pos - self._center)
        half_world = dist * np.tan(np.deg2rad(cam.GetViewAngle()) / 2.0)
        self._gpu.set_view_half(
            half_world / self._scale * self.recipe.unit_kpc
        )
