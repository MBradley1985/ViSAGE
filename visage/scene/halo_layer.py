from __future__ import annotations

from typing import Literal

import numpy as np
import pyvista as pv

from visage.io.halo_reader import HaloSnapshot
from visage.utils.colormap import normalize_log
from visage.utils.sizing import halo_world_radii

ColorMode = Literal["mvir", "rvir", "vvir", "vmax"]

_RANGES = {
    "mvir": (10.0, 15.0),  # log10(Msun)
    "rvir": (-1.5, 0.5),  # log10(Mpc/h)
    "vvir": (1.5, 3.0),  # log10(km/s)
    "vmax": (1.5, 3.0),  # log10(km/s)
}


class HaloLayer:
    """Manages the halo point-cloud actor(s) inside a PyVista Plotter."""

    def __init__(
        self,
        plotter: pv.Plotter,
        color_mode: ColorMode = "mvir",
        colormap: str = "viridis",
        opacity: float = 0.12,
        visible: bool = True,
    ) -> None:
        self._pl = plotter
        self._color_mode: ColorMode = color_mode
        self._colormap = colormap
        self._opacity = opacity
        self._visible = visible
        self._actors: list = []
        self._snapshot: HaloSnapshot | None = None
        self._focus_mask: np.ndarray | None = None
        self._filter_mask: np.ndarray | None = None
        self._slice_mask: np.ndarray | None = None  # lightcone redshift cut
        self._offset: np.ndarray = np.zeros(3, dtype=np.float32)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._visible = value
        for actor in self._actors:
            actor.SetVisibility(value)
        self._pl.render()

    @property
    def opacity(self) -> float:
        return self._opacity

    @opacity.setter
    def opacity(self, value: float) -> None:
        self._opacity = float(value)
        if self._snapshot is not None:
            self._redraw()

    @property
    def color_mode(self) -> ColorMode:
        return self._color_mode

    @color_mode.setter
    def color_mode(self, value: ColorMode) -> None:
        self._color_mode = value
        if self._snapshot is not None:
            self._redraw()

    @property
    def colormap(self) -> str:
        return self._colormap

    @colormap.setter
    def colormap(self, value: str) -> None:
        self._colormap = value
        if self._snapshot is not None:
            self._redraw()

    def set_offset(self, offset: np.ndarray) -> None:
        self._offset = np.asarray(offset, dtype=np.float32)
        if self._snapshot is not None:
            self._redraw()

    def update(self, snapshot: HaloSnapshot) -> None:
        self._snapshot = snapshot
        self._redraw()

    def set_mask(self, mask: np.ndarray | None) -> None:
        self.set_focus_mask(mask)

    def set_focus_mask(self, mask: np.ndarray | None) -> None:
        self._focus_mask = mask
        if self._snapshot is not None:
            self._redraw()

    def set_filter_mask(self, mask: np.ndarray | None) -> None:
        self._filter_mask = mask
        if self._snapshot is not None:
            self._redraw()

    def set_slice_mask(self, mask: np.ndarray | None) -> None:
        """Lightcone redshift/time cut keep-mask (True = shown)."""
        self._slice_mask = mask
        if self._snapshot is not None:
            self._redraw()

    def _combined_mask(self) -> np.ndarray | None:
        masks = [
            m
            for m in (self._focus_mask, self._filter_mask, self._slice_mask)
            if m is not None
        ]
        if not masks:
            return None
        n = len(masks[0])
        if any(len(m) != n for m in masks):
            return None
        out = masks[0].copy()
        for m in masks[1:]:
            out = out & m
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _clear_actors(self) -> None:
        for actor in self._actors:
            self._pl.remove_actor(actor, render=False)
        self._actors.clear()

    def _redraw(self) -> None:
        snap = self._snapshot
        if snap is None or snap.count == 0:
            self._clear_actors()
            return

        # Combined focus + filter mask
        mask = self._combined_mask()
        if mask is not None and len(mask) == snap.count:
            from visage.io.halo_reader import HaloSnapshot as _HS

            snap = _HS(
                positions=snap.positions[mask],
                masses=snap.masses[mask],
                vmax=snap.vmax[mask],
                rvir=snap.rvir[mask],
                vvir=snap.vvir[mask],
                snap_num=snap.snap_num,
            )
            if snap.count == 0:
                self._clear_actors()
                return

        colors = self._compute_colors(snap)
        radii = halo_world_radii(snap.masses)

        # Full rebuild every redraw — the layered NFW-style stack has
        # three actors per halo population so the in-place fast-path
        # doesn't apply (the same trade-off galaxies make for Structure).
        self._clear_actors()
        self._render_layered(snap.positions + self._offset, colors, radii)

    # ------------------------------------------------------------------
    # Layered NFW-style halo rendering — 3 stacked gaussian splats per
    # halo at decreasing radius and increasing opacity, giving a soft
    # density-profile look (bright core → faint Rvir boundary).
    # ------------------------------------------------------------------

    _LAYERS = (
        # (radius_scale, opacity_floor, opacity_multiplier)
        (1.00, 0.03, 0.35),  # outer envelope ~ Rvir boundary
        (0.45, 0.05, 0.60),  # inner halo
        (0.18, 0.08, 0.95),  # dense core
    )

    def _render_layered(
        self,
        positions: np.ndarray,
        colors: np.ndarray,
        radii: np.ndarray,
    ) -> None:
        if len(positions) == 0:
            return
        for r_scale, opa_floor, opa_mul in self._LAYERS:
            cloud = pv.PolyData(positions)
            cloud["scalar"] = colors
            cloud["radius"] = (radii * float(r_scale)).astype(np.float32)
            actor = self._pl.add_mesh(
                cloud,
                scalars="scalar",
                cmap=self._colormap,
                clim=[0.0, 1.0],
                style="points_gaussian",
                emissive=False,
                opacity=max(opa_floor, self._opacity * opa_mul),
                show_scalar_bar=False,
                render=False,
                reset_camera=False,
            )
            mapper = actor.mapper
            mapper.SetScaleArray("radius")
            mapper.SetScaleFactor(1.0)
            if not self._visible:
                actor.SetVisibility(False)
            self._actors.append(actor)

    def _compute_colors(self, snap: HaloSnapshot) -> np.ndarray:
        vmin, vmax_r = _RANGES[self._color_mode]
        if self._color_mode == "mvir":
            return normalize_log(snap.masses, vmin, vmax_r)
        if self._color_mode == "rvir":
            return normalize_log(snap.rvir, vmin, vmax_r)
        if self._color_mode == "vvir":
            return normalize_log(snap.vvir, vmin, vmax_r)
        if self._color_mode == "vmax":
            return normalize_log(np.maximum(snap.vmax, 1e-3), vmin, vmax_r)
        return normalize_log(snap.masses, *_RANGES["mvir"])
