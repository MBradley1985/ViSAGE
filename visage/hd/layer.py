"""Draw an HD galaxy into the scene as additive gaussian splats.

The model is built in the galaxy's own frame (spin axis = +z, model length
units) and placed in the world by a rotation that aligns +z with the
galaxy's SAGE spin vector, a scale to Mpc/h, and its box position.

Dust is view-dependent: whenever the camera moves, each dusty particle is
dimmed and reddened by the part of the disk's dust layer lying between it
and the camera (see `particles.attenuation`).  Recomputing this is a few
numpy passes over the particles, done only when the viewing direction
changes by more than ~0.5 degrees.

Progressive refinement: the particles are the fast preview while the
camera moves.  Once it rests, `refine_view` ray-marches the galaxy from
exactly that viewpoint with the same renderer as the offline grids
(emission + dust absorption, asinh tone map, bloom, gas overlay), and
`show_impostor` draws the result on a camera-facing quad in place of the
particles.  The next camera move swaps the particles back.
"""

from __future__ import annotations

import os

import numpy as np

from visage.hd.gas import build_gas, build_icl
from visage.hd.model import (
    SageGalaxy,
    build_disk_maps,
    build_points,
    recipe_from_sage,
)
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
        self._impostor = None  # (actor, camera_state) of the refined view
        self._white = None  # exposure of the refined views, fixed per galaxy

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
        # Inputs of the ray-marched (refined) views.
        self._maps = maps
        self._pts2d = build_points(rc, maps)
        self._white = None
        self._gas_cache = {}

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
        self.hide_impostor(remove=True)
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
        self.hide_impostor(remove=True)  # its baked-in gas is now stale
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
        if self._impostor is not None and not self.impostor_matches(
            self.camera_state()
        ):
            self.hide_impostor()

    # -- progressive refinement -----------------------------------------

    def camera_state(self) -> tuple:
        cam = self._pl.renderer.GetActiveCamera()
        w, h = self._pl.ren_win.GetSize()
        return (
            tuple(round(v, 12) for v in cam.GetPosition()),
            tuple(round(v, 12) for v in cam.GetFocalPoint()),
            tuple(round(v, 9) for v in cam.GetViewUp()),
            round(cam.GetViewAngle(), 6),
            (int(w), int(h)),
        )

    def impostor_matches(self, cam_state) -> bool:
        return self._impostor is not None and self._impostor[1] == cam_state

    def needs_refine(self, cam_state) -> bool:
        return self.active and not self.impostor_matches(cam_state)

    def refine_view(
        self, cam_state, max_npix: int = 768, threads=None
    ) -> dict:
        """Ray-march the galaxy as seen from `cam_state`.  Pure numpy (no
        VTK), so it can run off the UI thread."""
        from visage.hd import raymarch as rm

        pos, focal, up, view_angle, (w, h) = cam_state
        pos, focal, up = (np.asarray(v, float) for v in (pos, focal, up))
        zo = pos - focal
        zo /= np.linalg.norm(zo)  # toward the viewer
        yo = up - (up @ zo) * zo
        yo /= np.linalg.norm(yo)
        xo = np.cross(yo, zo)
        R = np.vstack([xo, yo, zo]) @ self._R  # galaxy frame -> observer frame

        rc, gal = self.recipe, self.gal
        k = 1.3 if rc.kind == "disk" else 1.0
        frame = rc.extent * k
        if self._gas_on:
            frame = max(frame, 1.05 * gal.rvir_kpc / rc.unit_kpc)
        # Only as much as the camera can see around the galaxy, so zooming
        # in buys resolution.
        dist = abs(float((self._center - pos) @ -zo)) / self._scale
        h_vis = dist * np.tan(np.deg2rad(view_angle) / 2.0)
        half = float(min(frame, 1.15 * h_vis * max(1.0, w / max(h, 1))))
        npix = int(np.clip(2 * half / (2 * h_vis) * h, 160, max_npix))

        lay = rm.render(
            rc,
            self._maps,
            self._pts2d,
            R=R,
            npix=npix,
            half_width=half,
            threads=threads or min(8, os.cpu_count() or 1),
        )
        if self._white is None:
            no_agn = lay.total - lay.points.get("agn", 0)
            self._white = (
                float(np.percentile(no_agn.mean(axis=2), 99.97)) or 1.0
            )
        img, _ = rm.tonemap(lay.total, white=self._white)
        img = rm.screen(img, rm.icl_zone(gal, rc, npix, half))
        if self._gas_on:
            img = rm.screen(img, self._gas_image(npix, half, R))
        return {
            "image": img.astype(np.float32),
            "half_world": half * self._scale,
            "axes": (xo, yo, zo),
            "camera": cam_state,
        }

    def _gas_image(self, npix: int, half: float, R: np.ndarray) -> np.ndarray:
        """Gas overlay for a refined view.  The halo gas (hot medium, CGM,
        cold streams) doesn't depend on the viewing angle, so it is cached
        per frame; only the wind and jets, which follow the spin axis, are
        redone for each view."""
        import dataclasses

        from visage.hd import raymarch as rm

        gal, rc = self.gal, self.recipe
        log = half * rc.unit_kpc > 0.5 * gal.rvir_kpc
        key = (npix, round(half, 6), log)
        cache = self.__dict__.setdefault("_gas_cache", {})
        if key not in cache:
            static = dataclasses.replace(
                gal, outflow_rate=0.0, heating_log=0.0
            )
            cache.clear()
            cache[key] = rm.gas_halo(
                static, rc, npix, half, R=R, log_stretch=log
            )
        moving = dataclasses.replace(gal, hot_gas=0.0, cgm_gas=0.0)
        if moving.outflow_rate > 0.05 or moving.heating_log > 40.0:
            return rm.screen(
                cache[key],
                rm.gas_halo(moving, rc, npix, half, R=R, log_stretch=log),
            )
        return cache[key]

    def show_impostor(self, view: dict) -> None:
        """Show a refined view in place of the particles (if the camera
        hasn't moved since it was requested)."""
        import pyvista as pv

        if not self.active or view["camera"] != self.camera_state():
            return
        self.hide_impostor(remove=True)
        xo, yo, _ = view["axes"]
        hw = view["half_world"]
        c = self._center
        corners = np.array(
            [
                c - xo * hw - yo * hw,
                c + xo * hw - yo * hw,
                c + xo * hw + yo * hw,
                c - xo * hw + yo * hw,
            ]
        )
        quad = pv.PolyData(corners, faces=np.array([4, 0, 1, 2, 3]))
        quad.active_texture_coordinates = np.array(
            [[0, 0], [1, 0], [1, 1], [0, 1]], np.float32
        )
        # Premultiplied encoding over the (black) scene: alpha = brightest
        # channel, colour = hue at full value, so blending reproduces the
        # image exactly and the sky behind it shows through dark regions.
        img = np.clip(view["image"], 0.0, 1.0)
        alpha = img.max(axis=2, keepdims=True)
        rgb = img / np.maximum(alpha, 1e-6)
        rgba = (np.concatenate([rgb, alpha], axis=2) * 255).astype(np.uint8)
        tex = pv.Texture(
            np.ascontiguousarray(rgba)
        )  # row 0 = top, as pyvista expects
        tex.SetInterpolate(True)
        actor = self._pl.add_mesh(
            quad,
            texture=tex,
            lighting=False,
            show_scalar_bar=False,
            render=False,
            reset_camera=False,
            pickable=False,
        )
        for a, _, _ in self._clouds.values():
            a.SetVisibility(False)
        self._impostor = (actor, view["camera"])

    def hide_impostor(self, remove: bool = False) -> None:
        if self._impostor is None:
            return
        actor, _ = self._impostor
        self._pl.remove_actor(actor, render=False)
        self._impostor = None
        for a, _, _ in self._clouds.values():
            a.SetVisibility(True)

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
