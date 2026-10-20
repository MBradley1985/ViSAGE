"""HD mode for a whole halo: a pair, group or cluster.

Every member of the FOF group is drawn at its own position and spin.  The
most massive ones get the full HD model (at a texture resolution that
falls with rank, as each is small on screen); any long tail of a big
cluster is drawn as soft glows.  All members share one exposure, so their
relative brightness follows stellar mass as in the offline grids
(brightness ~ M^0.35), anchored so the central looks as it does on its
own.  Only the central carries the halo (gas, ICL, Rvir box): its Rvir is
the group's.

The CPU side of the builds runs in a process pool (many small numpy
operations, which threads can't spread across cores).
"""

from __future__ import annotations

import os

import numpy as np

from visage.hd.layer import HDGalaxyLayer
from visage.hd.model import (
    CGM_RGB,
    HOT_GAS_RGB,
    OLD_LIGHT,
    SageGalaxy,
    display_sizes,
)

# Light scale for a shared exposure (as scripts/hd_galaxy/grid.py).
M_REF = 3e10
LUM_POWER = 0.35
# Members by stellar-mass rank: the first N_TOP in full quality (all of a
# group of up to N_FULL), then "group" quality up to N_GROUP, "lite" up to
# N_HD; the rest of a big cluster as glows.  Quality over build time (a few
# seconds is fine); GPU memory per full model (~150 MB) sets the limits.
N_FULL = 5
N_TOP = 4
N_GROUP = 16
N_HD = 40


def display_luminosity(gal: SageGalaxy, kind: str) -> float:
    """Relative brightness of a galaxy in a shared exposure."""
    if kind == "disk":
        ref = max(gal.stellar_mass - gal.bulge_mass, 1.0)
    else:
        ref = max(gal.stellar_mass * OLD_LIGHT, 1.0)
    return float((ref / M_REF) ** LUM_POWER)


def plan(gals: list[SageGalaxy]) -> list[str | None]:
    """Build quality for each member (None = drawn as a glow), in the
    order given (the caller sorts by stellar mass, central first)."""
    if len(gals) <= N_FULL:
        return ["full"] * len(gals)
    return [
        (
            "full"
            if i < N_TOP
            else "group" if i < N_GROUP else "lite" if i < N_HD else None
        )
        for i in range(len(gals))
    ]


def prepare_member(gal: SageGalaxy, quality: str) -> dict:
    """Pool worker: the CPU side of one member's build."""
    return HDGalaxyLayer.prepare(gal, quality)


_POOL: dict = {"pool": None}


def pool():
    """A lazily started process pool for member builds (spawned workers,
    kept for the session)."""
    if _POOL["pool"] is not None and getattr(_POOL["pool"], "_broken", False):
        _POOL["pool"] = None
    if _POOL["pool"] is None:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor

        n = max(2, min(8, (os.cpu_count() or 4) - 1))
        _POOL["pool"] = ProcessPoolExecutor(
            max_workers=n, mp_context=mp.get_context("spawn")
        )
    return _POOL["pool"]


class HDGroupLayer:
    """All members of a group, as HD models plus glows for the tail."""

    def __init__(self, plotter):
        self._pl = plotter
        self.members: list[HDGalaxyLayer] = []
        self._glow = None
        self._glow_data = None
        self._halo = None
        self._halo_rgb = None
        self._observer = None
        self._fxaa = None
        self.center = np.zeros(3)

    @property
    def active(self) -> bool:
        return any(m.active for m in self.members)

    def show(self, entries, hubble_h: float, gas: bool = False):
        """Draw the group.  `entries`: dicts with gal, center, spin and
        prep (None for a glow), central first."""
        self.clear()
        ren = self._pl.renderer
        self._fxaa = bool(ren.GetUseFXAA())
        ren.SetUseFXAA(False)
        lead = entries[0]
        k_lead = lead["prep"]["rc"].kind
        # Shared exposure, anchored on the central.
        w_common = lead["prep"]["exposure"].base * display_luminosity(
            lead["gal"], k_lead
        )
        for i, e in enumerate(entries):
            if e["prep"] is None:
                continue
            lay = HDGalaxyLayer(self._pl)
            lum = display_luminosity(e["gal"], e["prep"]["rc"].kind)
            lay.show(
                e["gal"],
                e["center"],
                e["spin"],
                hubble_h,
                gas=gas and i == 0,
                prep=e["prep"],
                white=w_common / lum,
                halo=i == 0,
                manage_fxaa=False,
            )
            self.members.append(lay)
            e["layer"] = lay
        self.center = np.asarray(lead["center"], float)
        self._add_glows(
            entries, hubble_h, display_luminosity(lead["gal"], k_lead)
        )
        self._add_halos(entries, hubble_h, gas)
        self._observer = ren.AddObserver("StartEvent", self._update_glows)
        self._update_glows()

    def _add_glows(self, entries, hubble_h, lum_lead):
        """Every member as a soft glow (size from the size-mass relation,
        colour from sSFR, brightness from mass).  A galaxy smaller than a
        pixel or two would otherwise vanish (its box covers no pixel); the
        glow keeps it in view and fades out as its HD model resolves.  The
        tail of a big cluster is only ever glows."""
        import pyvista as pv

        pos, rad, col, hd = [], [], [], []
        for e in entries:
            g = e["gal"]
            rd, r50e, _ = display_sizes(g)
            disky = g.bt < 0.6
            r_kpc = 1.5 * rd if disky else r50e
            pos.append(np.asarray(e["center"], float))
            rad.append(r_kpc * hubble_h / 1000.0)
            kind = "disk" if disky else "elliptical"
            b = float(
                np.clip(1.2 * display_luminosity(g, kind) / lum_lead, 0.3, 1.0)
            )
            rgb = (
                np.array([0.75, 0.85, 1.0])
                if g.ssfr > 1e-11
                else np.array([1.0, 0.82, 0.6])
            )
            col.append(b * rgb)
            hd.append(e.get("layer"))
        self._glow_data = {
            "pos": np.array(pos),
            "rad": np.array(rad),
            "rgb": np.array(col, np.float32),
            "hd": hd,
        }
        cloud = pv.PolyData(np.array(pos))
        cloud["rgb"] = np.array(col, np.float32)
        cloud["radius"] = np.array(rad, np.float32)
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
        self._glow = a
        self._cloud = cloud

    def _add_halos(self, entries, hubble_h, gas):
        """Every member's halo as a soft glow the size of its normal-mode
        splat (Rvir, scaled by its gas mass as there), tinted by whichever
        of CGM or hot gas dominates: the galaxy keeps its true size and
        sits inside the same footprint it has in the normal view.  The
        central's glow gives way to its full gas render when Gas is on."""
        import pyvista as pv

        from visage.utils.sizing import galaxy_world_radii_rvir

        pos, rad, col = [], [], []
        for e in entries:
            g = e["gal"]
            r = float(
                galaxy_world_radii_rvir(
                    np.array([g.rvir_kpc * hubble_h / 1000.0])
                )[0]
            )
            cgm = g.cgm_gas >= g.hot_gas
            m = max(g.cgm_gas if cgm else g.hot_gas, 1.0)
            lo, hi = (7.0, 11.5) if cgm else (7.0, 14.0)
            f = float(np.clip((np.log10(m) - lo) / (hi - lo), 0.0, 1.0))
            pos.append(np.asarray(e["center"], float))
            rad.append(r * (0.5 + 0.5 * f))
            rgb = np.asarray(CGM_RGB if cgm else HOT_GAS_RGB, float)
            col.append((0.06 + 0.16 * f) * rgb / max(rgb.max(), 1e-6))
        self._halo_rgb = np.array(col, np.float32)
        cloud = pv.PolyData(np.array(pos))
        cloud["rgb"] = self._halo_rgb.copy()
        cloud["radius"] = np.array(rad, np.float32)
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
        self._halo = a
        self._halo_cloud = cloud
        self._halo_gas(gas)

    def _halo_gas(self, on: bool):
        if self._halo_rgb is None:
            return
        rgb = self._halo_rgb.copy()
        if on:
            rgb[0] = 0.0  # the central's full gas render takes over
        self._halo_cloud["rgb"] = rgb

    def _update_glows(self, *_):
        """Per frame: each glow at least ~2.5 px across, faded out once the
        member's HD model is ~8 px across."""
        d = self._glow_data
        if d is None or self._glow is None:
            return
        ren = self._pl.renderer
        cam = ren.GetActiveCamera()
        pos = np.array(cam.GetPosition(), float)
        tan_half = np.tan(np.deg2rad(cam.GetViewAngle()) / 2.0)
        pix = 2.0 * tan_half / max(int(ren.GetSize()[1]), 1)
        dist = np.maximum(np.linalg.norm(d["pos"] - pos, axis=1), 1e-6)
        px_world = dist * pix
        rad = np.maximum(d["rad"], 2.5 * px_world)
        w = np.ones(len(rad))
        for k, lay in enumerate(d["hd"]):
            if lay is not None:
                size_px = lay.radius_world / px_world[k]
                w[k] = float(np.clip(1.0 - (size_px - 3.0) / 5.0, 0.0, 1.0))
        self._cloud["radius"] = rad.astype(np.float32)
        self._cloud["rgb"] = (d["rgb"] * w[:, None]).astype(np.float32)

    def clear(self):
        for m in self.members:
            m.clear()
        self.members = []
        if self._observer is not None:
            try:
                self._pl.renderer.RemoveObserver(self._observer)
            except Exception:
                pass
            self._observer = None
        if self._glow is not None:
            self._pl.remove_actor(self._glow, render=False)
            self._glow = None
            self._glow_data = None
        if self._halo is not None:
            self._pl.remove_actor(self._halo, render=False)
            self._halo = None
            self._halo_rgb = None
        if self._fxaa is not None:
            self._pl.renderer.SetUseFXAA(self._fxaa)
            self._fxaa = None

    def set_gas(self, on: bool):
        """The group's gas is the central's halo."""
        if self.members:
            self.members[0].set_gas(on)
        self._halo_gas(on)

    # -- geometry ------------------------------------------------------

    @property
    def radius_world(self) -> float:
        """Half-width that frames the group, Mpc/h: every member of a pair
        or small group; the central and the inner three quarters of a big
        one's members (outliers, often beyond Rvir, would shrink everything
        else to a few pixels)."""
        if not self.members:
            return 0.0
        r = [
            np.linalg.norm(m._center - self.center) + m.radius_world
            for m in self.members
        ]
        if len(r) <= 10:
            return float(max(r))
        return float(max(r[0], np.percentile(r, 75)))

    @property
    def rvir_world(self) -> float:
        return self.members[0].rvir_world if self.members else 0.0

    @property
    def basis(self) -> np.ndarray:
        """The central's frame (for the 55-degree framing)."""
        return self.members[0]._R
