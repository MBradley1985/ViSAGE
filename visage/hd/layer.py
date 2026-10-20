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


# Texture resolutions per build quality.
QUALITY = {
    "full": {"map_n": 1024, "npts": 2048, "exp_npix": 256, "atlas_n": 112},
    "group": {"map_n": 768, "npts": 1024, "exp_npix": 160, "atlas_n": 80},
    "lite": {"map_n": 384, "npts": 512, "exp_npix": 96, "atlas_n": 48},
}


class Exposure:
    """White level of the tone map.

    The base level is fixed per galaxy as in the offline renders: the
    99.97th percentile of a face-on view (AGN excluded).  Zoomed into a
    region brighter than the galaxy as a whole, the level rises with that
    region's mean surface brightness, as a camera's auto-exposure would, so
    the inner disk and bulge don't wash out; it never drops below the base,
    so the whole-galaxy view is unchanged.
    """

    _PA = 25.0

    def __init__(self, rc, maps, pts, npix: int = 256, threads: int = 8):
        from visage.hd.raymarch import render, rot

        face = render(
            rc, maps, pts, inc=0, pa=self._PA, npix=npix, threads=threads
        )
        lum = (face.total - face.points.get("agn", 0)).mean(axis=2)
        self.base = float(np.percentile(lum, 99.97)) or 1.0
        self._R = rot(0, self._PA)
        self._E = float(face.half_width)
        self._n = lum.shape[0]
        self._pix = 2 * self._E / (self._n - 1)
        # Summed-area table: O(1) box means.
        self._sat = np.pad(lum.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        self._k = self.base / max(self._box_mean(0.0, 0.0, self._E), 1e-30)

    def _box_mean(self, x: float, y: float, half: float) -> float:
        """Mean face-on surface brightness over a square of half-width
        `half` centred on galaxy-frame (x, y); outside the image counts as
        dark."""
        ox, oy, _ = self._R @ np.array([x, y, 0.0])
        n = self._n
        c0 = int(np.clip(np.floor((ox - half + self._E) / self._pix), 0, n))
        c1 = int(np.clip(np.ceil((ox + half + self._E) / self._pix), 0, n))
        r0 = int(np.clip(np.floor((self._E - oy - half) / self._pix), 0, n))
        r1 = int(np.clip(np.ceil((self._E - oy + half) / self._pix), 0, n))
        side = max(2 * half / self._pix, 1.0)
        S = self._sat
        tot = S[r1, c1] - S[r0, c1] - S[r1, c0] + S[r0, c0]
        return float(tot) / (side * side)

    def white(self, x: float, y: float, half: float) -> float:
        """White level for a view of half-width `half` (model units)
        centred on galaxy-frame (x, y)."""
        return max(self.base, self._k * self._box_mean(x, y, half))


class HDGalaxyLayer:
    """One HD galaxy in a pyvista plotter."""

    def __init__(self, plotter):
        self._pl = plotter
        self._gpu = GPUGalaxy(plotter)
        self._observer = None
        self._fxaa = None
        self._white0 = 1.0
        self._gas_on = False
        self.gal: SageGalaxy | None = None
        self.recipe = None

    @property
    def active(self) -> bool:
        return self._gpu.actor is not None

    @staticmethod
    def prepare(gal: SageGalaxy, quality: str = "full") -> dict:
        """Everything CPU-heavy in a build (numpy only, so it can run on a
        worker thread while the UI says what is happening).  `quality`
        (QUALITY key) sets texture resolutions: lower for the many members
        of a group, each of which is small on screen."""
        from visage.hd.gpu import prepare

        q = QUALITY[quality]
        rc = recipe_from_sage(gal)
        maps = build_disk_maps(rc, n=q["map_n"]) if rc.kind == "disk" else None
        pts = build_points(rc, maps)
        return {
            "gal": gal,
            "rc": rc,
            "maps": maps,
            "pts": pts,
            # Group members build in parallel processes: one thread each.
            "exposure": Exposure(
                rc,
                maps,
                pts,
                npix=q["exp_npix"],
                threads=8 if quality == "full" else 1,
            ),
            "gpu": prepare(
                rc, maps, pts, npts=q["npts"], atlas_n=q["atlas_n"]
            ),
        }

    def show(
        self,
        gal: SageGalaxy,
        center,
        spin,
        hubble_h: float,
        gas: bool = False,
        prep: dict | None = None,
        white: float | None = None,
        halo: bool = True,
        manage_fxaa: bool = True,
    ):
        """Build and draw the HD model of `gal` at world position `center`.

        `prep`: `prepare(gal)`, if already made.  For a member of a group:
        `white` is its share of the group's common exposure (default: its
        own), `halo=False` leaves out the halo (gas, ICL, Rvir box) for a
        satellite, and `manage_fxaa=False` leaves FXAA to the group."""
        self.clear()
        # (By value: a prep built in a worker process holds a copy of gal.)
        if prep is None or prep["gal"] != gal:
            prep = self.prepare(gal)
        self.gal = gal
        rc, maps, pts = prep["rc"], prep["maps"], prep["pts"]
        self.recipe = rc

        self._R = galaxy_basis(spin, rc.seed)
        self._scale = rc.unit_kpc * hubble_h / 1000.0  # model units -> Mpc/h
        self._center = np.asarray(center, float)
        self._hubble_h = hubble_h
        m = np.eye(4)
        m[:3, :3] = self._R * self._scale
        m[:3, 3] = self._center
        self._exposure = prep["exposure"]
        self._white0 = float(white) if white else self._exposure.base
        self._gpu.build(
            rc,
            maps,
            pts,
            self._white0,
            m,
            gal=gal if halo else None,
            gas=gas,
            prep=prep["gpu"],
        )
        self._gas_on = bool(gas)
        self._gpu.set_gas(self._gas_on)
        ren = self._pl.renderer
        if manage_fxaa:
            # The shader resolves single stars; FXAA would smear them.
            self._fxaa = bool(ren.GetUseFXAA())
            ren.SetUseFXAA(False)
        # Camera uniforms are refreshed as each frame starts, so they follow
        # camera moves and window resizes alike.
        self._observer = (ren, ren.AddObserver("StartEvent", self._on_camera))
        self._on_camera()

    def clear(self):
        if self._observer is not None:
            ren, tag = self._observer
            try:
                ren.RemoveObserver(tag)
            except Exception:
                pass
            self._observer = None
        if self._fxaa is not None:
            self._pl.renderer.SetUseFXAA(self._fxaa)
            self._fxaa = None
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
        """Keep the shader's camera (galaxy frame), pixel size and view size
        current."""
        if not self.active:
            return
        ren = self._pl.renderer
        cam = ren.GetActiveCamera()
        pos = np.array(cam.GetPosition(), float)
        tan_half = np.tan(np.deg2rad(cam.GetViewAngle()) / 2.0)
        height = max(int(ren.GetSize()[1]), 1)
        cam_model = self.to_model(pos)
        pix_ang = 2.0 * tan_half / height
        self._gpu.set_camera(cam_model, pix_ang)
        self._gpu.set_pixel(float(np.linalg.norm(cam_model)) * pix_ang)
        dist = np.linalg.norm(pos - self._center)
        half_world = dist * tan_half
        focal = np.array(cam.GetFocalPoint(), float)
        fx, fy, _ = self.to_model(focal)
        half_focal = np.linalg.norm(pos - focal) * tan_half / self._scale
        # Auto-exposure relative to this galaxy's own base level.
        auto = self._exposure.white(fx, fy, half_focal) / self._exposure.base
        self._gpu.set_white(self._white0 * auto)
        self._gpu.set_view_half(
            half_world / self._scale * self.recipe.unit_kpc
        )
