"""Draw an HD galaxy into the scene as additive gaussian splats.

The model is built in the galaxy's own frame (spin axis = +z, model length
units) and placed in the world by a rotation that aligns +z with the
galaxy's SAGE spin vector, a scale to Mpc/h, and its box position.

Dust is view-dependent: whenever the camera moves, each dusty particle is
dimmed and reddened by the part of the disk's dust layer lying between it
and the camera (see `particles.attenuation`).  Recomputing this is a few
numpy passes over the particles, done only when the viewing direction
changes by more than ~0.5 degrees.
"""

from __future__ import annotations

import numpy as np

from visage.hd.gas import build_gas, build_icl
from visage.hd.model import SageGalaxy, build_disk_maps, recipe_from_sage
from visage.hd.particles import (
    ParticleSet,
    attach_dust,
    attenuation,
    build_optical,
    calibrate,
)

_DUST_STEP = np.cos(np.deg2rad(0.5))


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


class HDGalaxyLayer:
    """One HD galaxy in a pyvista plotter."""

    def __init__(self, plotter):
        self._pl = plotter
        self._clouds: dict[str, tuple] = {}  # name -> (actor, cloud, set)
        self._gas_sets: list[ParticleSet] | None = None
        self._gas_on = False
        self._observer = None
        self._last_dir = None
        self.gal: SageGalaxy | None = None
        self.recipe = None

    # -- lifecycle -----------------------------------------------------

    @property
    def active(self) -> bool:
        return bool(self._clouds)

    def show(
        self, gal: SageGalaxy, center, spin, hubble_h: float, gas: bool = False
    ):
        """Build and draw the HD model of `gal` at world position `center`."""
        self.clear()
        self.gal = gal
        rc = recipe_from_sage(gal)
        self.recipe = rc
        maps = build_disk_maps(rc, n=1024) if rc.kind == "disk" else None
        optical = build_optical(rc, maps)
        calibrate(optical, rc.extent * (1.3 if rc.kind == "disk" else 1.0))
        attach_dust(optical, maps)
        optical += build_icl(gal, rc)

        self._R = galaxy_basis(spin, rc.seed)
        self._scale = rc.unit_kpc * hubble_h / 1000.0  # model units -> Mpc/h
        self._center = np.asarray(center, float)
        self._hubble_h = hubble_h
        for s in optical:
            self._add(s)
        self._gas_sets = None
        self.set_gas(gas)
        cam = self._pl.renderer.GetActiveCamera()
        self._observer = (
            cam,
            cam.AddObserver("ModifiedEvent", self._on_camera),
        )
        self._last_dir = None
        self.update_dust()

    def clear(self):
        if self._observer is not None:
            cam, tag = self._observer
            try:
                cam.RemoveObserver(tag)
            except Exception:
                pass
            self._observer = None
        for actor, _, _ in self._clouds.values():
            self._pl.remove_actor(actor, render=False)
        self._clouds = {}
        self._gas_sets = None
        self._gas_on = False
        self.gal = None
        self.recipe = None

    def set_gas(self, on: bool):
        """Show or hide the halo-gas overlay (built on first use)."""
        on = bool(on)
        if not self.gal:
            return
        if on and self._gas_sets is None:
            self._gas_sets = build_gas(self.gal, self.recipe)
        for s in self._gas_sets or []:
            key = "gas:" + s.name
            if on and key not in self._clouds:
                self._add(s, key)
            elif not on and key in self._clouds:
                actor, _, _ = self._clouds.pop(key)
                self._pl.remove_actor(actor, render=False)
        self._gas_on = on

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

    def to_world(self, pos_model: np.ndarray) -> np.ndarray:
        # einsum rather than @: macOS Accelerate's matmul raises spurious
        # overflow warnings on float data like this.
        return self._center + np.einsum(
            "ij,nj->ni", self._R, pos_model * self._scale
        )

    def _add(self, s: ParticleSet, key: str | None = None):
        import pyvista as pv

        cloud = pv.PolyData(self.to_world(s.pos.astype(np.float64)))
        cloud["rgb"] = np.clip(s.colour, 0.0, 1.0).astype(np.float32)
        cloud["radius"] = (s.radius * self._scale).astype(np.float32)
        actor = self._pl.add_mesh(
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
        mp = actor.mapper
        mp.SetScaleArray("radius")
        mp.SetScaleFactor(1.0)
        self._clouds[key or s.name] = (actor, cloud, s)

    # -- dust ----------------------------------------------------------

    def _on_camera(self, *_):
        self.update_dust()

    def update_dust(self, force: bool = False):
        """Re-attenuate the dusty components for the current view."""
        if not self._clouds:
            return
        cam = np.array(
            self._pl.renderer.GetActiveCamera().GetPosition(), float
        )
        d = cam - self._center
        norm = np.linalg.norm(d)
        if norm == 0:
            return
        d_gal = self._R.T @ (d / norm)
        if (
            not force
            and self._last_dir is not None
            and float(d_gal @ self._last_dir) > _DUST_STEP
        ):
            return
        self._last_dir = d_gal
        for _, cloud, s in self._clouds.values():
            att = attenuation(s, d_gal)
            if att is None:
                continue
            cloud["rgb"] = np.clip(s.colour * att, 0.0, 1.0).astype(np.float32)
            cloud.Modified()
