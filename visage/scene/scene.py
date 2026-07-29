from __future__ import annotations

from pathlib import Path
from collections.abc import Callable

import numpy as np
import pyvista as pv

from visage.scene.camera import CameraController
from visage.scene.galaxy_layer import GalaxyLayer
from visage.scene.halo_layer import HaloLayer
from visage.scene.model import Model

# Gap between adjacent boxes as a fraction of the primary box size.
_BOX_GAP_FRACTION = 0.30


class Scene:
    """Owner of the PyVista plotter and a dict of Models.

    One model is the *primary* (its layers are exposed via `scene.halo_layer` /
    `scene.galaxy_layer` so all existing UI code keeps working). Additional
    models can be loaded and made visible as overlays if they share the same
    box size and snapshot count, or placed side-by-side as independent
    adjacent boxes with their own snapshot, filters and render settings.

    Playback animation is driven externally by the Trame async event loop
    (see toolbar.py) so that all VTK calls stay on the main thread.
    """

    def __init__(
        self,
        primary_par_path: str | Path,
        off_screen: bool = False,
        initial_snap: int | None = None,
        n_jobs: int = -1,
        min_halo_mass: float = 1.0e10,
        min_stellar_mass: float = 1.0e8,
        max_halos: int = 100_000,
        max_galaxies: int | None = None,
        lightcone_path: str | Path | None = None,
    ) -> None:
        self._plotter = pv.Plotter(
            off_screen=off_screen, window_size=[1600, 900]
        )
        self._plotter.set_background("black")
        self._plotter.renderer.SetNearClippingPlaneTolerance(0.00001)

        # Loader kwargs reused when adding additional models later
        self._loader_kwargs = dict(
            n_jobs=n_jobs,
            min_halo_mass=min_halo_mass,
            min_stellar_mass=min_stellar_mass,
            max_halos=max_halos,
            max_galaxies=max_galaxies,
        )

        self._models: dict[str, Model] = {}
        self._primary_name: str = ""
        self._is_lightcone: bool = lightcone_path is not None

        # Build the primary model — a lightcone (flat cone) or a SAGE box.
        if self._is_lightcone:
            from visage.scene.lightcone_model import LightconeModel

            primary = LightconeModel(
                lightcone_path, self._plotter, self._loader_kwargs
            )
        else:
            primary = Model(
                primary_par_path, self._plotter, self._loader_kwargs
            )
        self._models[primary.name] = primary
        self._primary_name = primary.name

        # Adjacent-box state
        self._adjacent_order: list[str] = []  # names in placement order
        self._active_box_name: str = primary.name

        # Label actors keyed by model name (only shown when multiple boxes are loaded)
        self._label_actors: dict[str, list] = {}
        # When False, the per-box name/redshift labels are suppressed entirely
        # (e.g. Story Mode prefers a clean view). Restored on exit.
        self._labels_enabled: bool = True

        self._camera = CameraController(self._plotter, primary.box_size)
        if self._is_lightcone:
            # Frame the actual cone bounds, not a cube.
            self._camera.set_lightcone_bounds(getattr(primary, "bounds", None))

        if initial_snap is not None:
            self._current_snap: int = initial_snap
        elif self._is_lightcone:
            # Full cone by default: the near-side cut is "off" at snap_max.
            self._current_snap = getattr(
                primary, "snap_max", primary.snap_count - 1
            )
        else:
            self._current_snap = primary.snap_count - 1

        self._on_snap_change: list[Callable[[int], None]] = []
        self._on_model_change: list[Callable[[], None]] = []
        self._focus_region: dict | None = None

        self.set_snapshot(self._current_snap)
        self._camera.reset()

        # Start background preloading of all snapshots immediately so
        # navigation is stall-free by the time the browser opens.
        # Suppress per-snapshot log lines so they don't bury the server URL.
        from visage.io import halo_reader, galaxy_reader

        halo_reader.VERBOSE = False
        galaxy_reader.VERBOSE = False
        # A lightcone is a single static cloud — nothing to preload.
        if not self._is_lightcone:
            self.primary.loader.preload_all()

    # ------------------------------------------------------------------
    # Primary model & layer access
    # ------------------------------------------------------------------

    @property
    def primary(self) -> Model:
        return self._models[self._primary_name]

    @property
    def primary_name(self) -> str:
        return self._primary_name

    @property
    def active_model(self) -> Model:
        """The model whose settings the UI panel currently controls."""
        return self._models.get(self._active_box_name, self.primary)

    # halo_layer / galaxy_layer route to the ACTIVE model so all existing
    # filter and rendering handlers automatically target the right box.
    @property
    def halo_layer(self) -> HaloLayer:
        return self.active_model.halo_layer

    @property
    def galaxy_layer(self) -> GalaxyLayer:
        return self.active_model.galaxy_layer

    @property
    def camera(self) -> CameraController:
        return self._camera

    @property
    def plotter(self) -> pv.Plotter:
        return self._plotter

    @property
    def current_snap(self) -> int:
        return self.active_model.current_snap

    @property
    def snap_label(self) -> str:
        m = self.active_model
        return m.snap_table.label(m.current_snap)

    # Backward-compat shims used by various callers
    @property
    def _cfg(self):
        return self.primary.cfg

    @property
    def _snap_table(self):
        return self.primary.snap_table

    @property
    def _loader(self):
        return self.primary.loader

    @property
    def snap_count(self) -> int:
        return self.primary.snap_count

    # ------------------------------------------------------------------
    # Active-box management
    # ------------------------------------------------------------------

    @property
    def active_box_name(self) -> str:
        return self._active_box_name

    def set_active_box(self, name: str) -> None:
        """Switch which box the UI controls.
        Profile save/restore is handled by the app layer."""
        if name not in self._models:
            return
        self._active_box_name = name
        self._update_labels()
        self._plotter.render()

    # ------------------------------------------------------------------
    # Adjacent-box management
    # ------------------------------------------------------------------

    def is_adjacent(self, name: str) -> bool:
        return name in self._adjacent_order

    def toggle_adjacent(self, par_path: str | Path) -> tuple[bool, str | None]:
        """Add or remove a model as an adjacent side-by-side box.

        Returns (is_now_adjacent, error_message_or_None).
        """
        # Load the model if not already known
        if not self.has_model_by_path(par_path):
            model = Model(par_path, self._plotter, self._loader_kwargs)
            self._models[model.name] = model
        else:
            model = self._model_by_path(par_path)

        name = model.name
        if name == self._primary_name:
            return False, "Cannot place the primary model as adjacent."

        if name in self._adjacent_order:
            # Remove it
            self._adjacent_order.remove(name)
            if self._active_box_name == name:
                self._active_box_name = self._primary_name
            model.offset = np.zeros(3)
            model.visible = False
            self._remove_label(name)
            self._recompute_offsets()
            self._update_labels()
            self._plotter.render()
            for cb in self._on_model_change:
                cb()
            return False, None
        else:
            # Add it
            self._adjacent_order.append(name)
            self._recompute_offsets()
            # Always start adjacent boxes with default color/colormap so they
            # don't inherit whatever the primary box had been set to.
            model.halo_layer.color_mode = "mvir"
            model.halo_layer.colormap = "viridis"
            model.galaxy_layer.color_mode = "structure"
            model.galaxy_layer.colormap = "plasma"
            model.set_snapshot(model.snap_count - 1)
            model.visible = True
            self._update_labels()
            self._plotter.render()
            for cb in self._on_model_change:
                cb()
            return True, None

    def _recompute_offsets(self) -> None:
        """Lay adjacent boxes out along +X with a small gap."""
        gap = self.primary.box_size * _BOX_GAP_FRACTION
        x = self.primary.box_size + gap
        for name in self._adjacent_order:
            m = self._models.get(name)
            if m is None:
                continue
            m.offset = np.array([x, 0.0, 0.0])
            x += m.box_size + gap

    def has_model_by_path(self, par_path: str | Path) -> bool:
        p = Path(par_path)
        return any(m.path == p for m in self._models.values())

    def _model_by_path(self, par_path: str | Path) -> Model:
        p = Path(par_path)
        for m in self._models.values():
            if m.path == p:
                return m
        raise KeyError(par_path)

    # ------------------------------------------------------------------
    # 3-D text labels (model name + redshift, below each box)
    # Shown only when multiple boxes are loaded.
    # ------------------------------------------------------------------

    def _box_center_xz(self, name: str) -> tuple[float, float, float]:
        """Return (cx, 0, cz) — the XZ centre of the named box."""
        m = self._models[name]
        off = m.offset
        bs = m.box_size
        return float(off[0] + bs / 2), 0.0, float(off[2] + bs / 2)

    def _label_position(self, name: str) -> tuple[float, float, float]:
        cx, _, cz = self._box_center_xz(name)
        m = self._models[name]
        return cx, -m.box_size * 0.22, cz

    def _label_text(self, name: str) -> str:
        m = self._models[name]
        snap = max(0, m.current_snap)
        z = m.snap_table.snap_to_z(snap)
        return f"{m.name}  z={z:.2f}"

    def _remove_label(self, name: str) -> None:
        for actor in self._label_actors.pop(name, []):
            self._plotter.renderer.RemoveActor(actor)

    def _add_label(self, name: str) -> None:
        from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D

        cx, y, cz = self._label_position(name)
        text = self._label_text(name)

        actor = vtkBillboardTextActor3D()
        actor.SetInput(text)
        actor.SetPosition(cx, y, cz)

        tp = actor.GetTextProperty()
        if name == self._active_box_name:
            tp.SetColor(0.2, 1.0, 0.4)  # green for active
        else:
            tp.SetColor(1.0, 1.0, 1.0)  # white for idle
        tp.SetFontSize(14)
        tp.SetJustificationToCentered()
        tp.SetVerticalJustificationToCentered()
        tp.SetBackgroundOpacity(0.0)
        tp.SetBold(False)
        tp.SetShadow(False)

        self._plotter.renderer.AddActor(actor)
        self._label_actors[name] = [actor]

    def _update_labels(self) -> None:
        """Rebuild labels for all boxes — only when more than one box is loaded."""
        if not self._labels_enabled:
            for name in list(self._label_actors):
                self._remove_label(name)
            self._plotter.render()
            return
        if len(self._adjacent_order) == 0:
            # Back to a single box: remove any lingering labels
            for name in list(self._label_actors):
                self._remove_label(name)
            self._plotter.render()
            return
        label_names = [self._primary_name] + list(self._adjacent_order)
        for name in list(self._label_actors):
            if name not in label_names:
                self._remove_label(name)
        for name in label_names:
            self._remove_label(name)
            self._add_label(name)
        self._plotter.render()

    def set_labels_enabled(self, enabled: bool) -> None:
        """Enable/disable the per-box name+redshift labels and rebuild/clear."""
        enabled = bool(enabled)
        if enabled == self._labels_enabled:
            return
        self._labels_enabled = enabled
        self._update_labels()

    def refresh_label(self, name: str) -> None:
        """Refresh just one label (e.g. after a snapshot change)."""
        if not self._labels_enabled:
            return
        if len(self._adjacent_order) == 0:
            return
        if name in self._label_actors or name in (
            [self._primary_name] + self._adjacent_order
        ):
            self._remove_label(name)
            self._add_label(name)
            self._plotter.render()

    # ------------------------------------------------------------------
    # Overlay model management (unchanged from before)
    # ------------------------------------------------------------------

    def list_models(self) -> list[Model]:
        return list(self._models.values())

    def has_model(self, name: str) -> bool:
        return name in self._models

    def add_model(self, par_path: str | Path) -> Model:
        """Load a new model alongside the primary. Starts hidden by default."""
        model = Model(par_path, self._plotter, self._loader_kwargs)
        if model.name in self._models:
            return self._models[model.name]
        model.set_snapshot(self._current_snap)
        model.visible = False
        self._models[model.name] = model
        for cb in self._on_model_change:
            cb()
        return model

    def remove_model(self, name: str) -> None:
        if name == self._primary_name or name not in self._models:
            return
        model = self._models.pop(name)
        model.visible = False
        model.halo_layer._clear_actors()
        model.galaxy_layer._clear_actors()
        model.shutdown()
        if name in self._adjacent_order:
            self._adjacent_order.remove(name)
        self._remove_label(name)
        for cb in self._on_model_change:
            cb()

    def switch_primary(self, name: str) -> None:
        """Switch the active primary model.

        Adjacent boxes stay in place; their offsets are recomputed relative
        to the new primary.  If the active box was the old primary, the
        active box switches to the new primary.
        """
        if name == self._primary_name or name not in self._models:
            return
        old_primary_box = self.primary.box_size
        self._models[self._primary_name].visible = False

        # If old primary was active, transfer focus to new primary
        if self._active_box_name == self._primary_name:
            self._active_box_name = name

        self._primary_name = name

        # Hide overlays that are incompatible with the new primary
        for other_name, m in self._models.items():
            if other_name == self._primary_name:
                continue
            if other_name in self._adjacent_order:
                continue  # adjacent boxes are not overlay-checked
            if m.visible and not self.is_compatible_for_overlay(other_name):
                m.visible = False

        self.primary.visible = True
        snap = self.primary.snap_count - 1
        self._current_snap = snap
        self.primary.set_snapshot(snap)

        new_box = self.primary.box_size
        self._camera._box_size = new_box
        if abs(new_box - old_primary_box) > 1e-3:
            self._camera.reset()

        # Recompute adjacent offsets relative to new primary
        self._recompute_offsets()
        self._update_labels()

        if self._focus_region is not None:
            halos, galaxies = self.primary.loader.get(self._current_snap)
            self._apply_focus_masks_for_layer(
                self.primary.halo_layer,
                self.primary.galaxy_layer,
                halos.positions,
                galaxies.positions,
            )
        for cb in self._on_snap_change:
            cb(self._current_snap)
        for cb in self._on_model_change:
            cb()

    def set_overlay_visible(self, name: str, vis: bool) -> str | None:
        if name == self._primary_name or name not in self._models:
            return None
        if name in self._adjacent_order:
            return "Use the Side-by-Side toggle to manage adjacent boxes."
        m = self._models[name]
        if vis:
            if not self.is_compatible_for_overlay(name):
                primary = self.primary
                cand = self._models[name]
                if abs(primary.box_size - cand.box_size) > 1e-3:
                    detail = (
                        f"box size {cand.box_size:.1f} ≠ "
                        f"{primary.box_size:.1f} Mpc/h"
                    )
                elif primary.snap_count != cand.snap_count:
                    detail = (
                        f"snapshot count {cand.snap_count} ≠ "
                        f"{primary.snap_count}"
                    )
                else:
                    detail = "incompatible simulation parameters"
                return (
                    f"Can't overlay '{name}' on '{primary.name}': {detail}. "
                    f"Use Side-by-Side instead."
                )
            m.set_snapshot(self._current_snap)
        m.visible = vis
        for cb in self._on_model_change:
            cb()
        return None

    def is_compatible_for_overlay(self, name: str) -> bool:
        if name == self._primary_name or name not in self._models:
            return False
        primary = self.primary
        candidate = self._models[name]
        return (
            abs(primary.box_size - candidate.box_size) < 1e-3
            and primary.snap_count == candidate.snap_count
        )

    # ------------------------------------------------------------------
    # Snapshot control
    # ------------------------------------------------------------------

    def set_snapshot(self, snap_num: int) -> None:
        """Update snapshot.

        When the active box is an adjacent model, only that model's snapshot
        changes.  When the primary is active, the original behaviour applies
        (primary + compatible overlays all update together).
        """
        if (
            self._active_box_name != self._primary_name
            and self._active_box_name in self._adjacent_order
        ):
            active = self.active_model
            snap_num = max(0, min(int(snap_num), active.snap_count - 1))
            active.set_snapshot(snap_num)
            halos, galaxies = active.loader.get(snap_num)
            off = active.offset.astype(np.float32)
            self._camera.update_halo_index(
                halos.positions + off, tree=active.loader.get_tree(snap_num)
            )
            self._camera.update_galaxy_positions(galaxies.positions + off)
            self.refresh_label(self._active_box_name)
            for cb in self._on_snap_change:
                cb(snap_num)
            return

        # Primary is active: original behaviour
        snap_num = max(0, min(int(snap_num), self.primary.snap_count - 1))
        self._current_snap = snap_num
        self.primary.set_snapshot(snap_num)

        # Update compatible overlays (not adjacent boxes — they're independent)
        for name, m in self._models.items():
            if name == self._primary_name:
                continue
            if name in self._adjacent_order:
                continue
            if m.visible:
                m.set_snapshot(min(snap_num, m.snap_count - 1))

        halos, galaxies = self.primary.loader.get(snap_num)
        self._camera.update_halo_index(
            halos.positions, tree=self.primary.loader.get_tree(snap_num)
        )
        self._camera.update_galaxy_positions(galaxies.positions)

        if self._focus_region is not None:
            self._apply_focus_masks_for_layer(
                self.primary.halo_layer,
                self.primary.galaxy_layer,
                halos.positions,
                galaxies.positions,
            )

        self.refresh_label(self._primary_name)
        for cb in self._on_snap_change:
            cb(snap_num)

    # ------------------------------------------------------------------
    # Click-to-activate: determine which box a 3-D click point belongs to
    # ------------------------------------------------------------------

    def box_name_at(self, world_x: float) -> str:
        """Return the model name whose X range contains *world_x*.

        Falls back to the primary if no adjacent box matches.
        """
        for name in reversed(self._adjacent_order):
            m = self._models[name]
            x0 = float(m.offset[0])
            x1 = x0 + m.box_size
            if x0 <= world_x <= x1:
                return name
        return self._primary_name

    # ------------------------------------------------------------------
    # Focus / spatial masking (applies to active model only)
    # ------------------------------------------------------------------

    def set_focus_box(
        self,
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        zmin: float,
        zmax: float,
    ) -> None:
        self._focus_region = dict(
            type="box",
            xmin=xmin,
            xmax=xmax,
            ymin=ymin,
            ymax=ymax,
            zmin=zmin,
            zmax=zmax,
        )
        active = self.active_model
        halos, galaxies = active.loader.get(active.current_snap)
        self._apply_focus_masks_for_layer(
            active.halo_layer,
            active.galaxy_layer,
            halos.positions,
            galaxies.positions,
        )

    def set_focus_sphere(
        self,
        center: tuple[float, float, float],
        radius: float,
    ) -> None:
        self._focus_region = dict(type="sphere", center=center, radius=radius)
        active = self.active_model
        halos, galaxies = active.loader.get(active.current_snap)
        off = active.offset.astype(np.float32)
        self._apply_focus_masks_for_layer(
            active.halo_layer,
            active.galaxy_layer,
            halos.positions + off,
            galaxies.positions + off,
        )

    def clear_focus(self) -> None:
        self._focus_region = None
        for m in self._models.values():
            m.halo_layer.set_mask(None)
            m.galaxy_layer.set_mask(None)

    def _apply_focus_masks_for_layer(
        self,
        halo_layer: HaloLayer,
        gal_layer: GalaxyLayer,
        halo_pos: np.ndarray,
        gal_pos: np.ndarray,
    ) -> None:
        r = self._focus_region
        if r is None:
            return
        if r["type"] == "box":

            def _box_mask(pos):
                if len(pos) == 0:
                    return np.array([], dtype=bool)
                return (
                    (pos[:, 0] >= r["xmin"])
                    & (pos[:, 0] <= r["xmax"])
                    & (pos[:, 1] >= r["ymin"])
                    & (pos[:, 1] <= r["ymax"])
                    & (pos[:, 2] >= r["zmin"])
                    & (pos[:, 2] <= r["zmax"])
                )

            halo_layer.set_mask(_box_mask(halo_pos))
            gal_layer.set_mask(_box_mask(gal_pos))
        elif r["type"] == "sphere":
            cx, cy, cz = r["center"]
            rad = r["radius"]

            def _sphere_mask(pos):
                if len(pos) == 0:
                    return np.array([], dtype=bool)
                return (
                    np.linalg.norm(pos - np.array([cx, cy, cz]), axis=1) <= rad
                )

            halo_layer.set_mask(_sphere_mask(halo_pos))
            gal_layer.set_mask(_sphere_mask(gal_pos))

    def _apply_focus_masks(self, halo_pos, gal_pos) -> None:
        self._apply_focus_masks_for_layer(
            self.primary.halo_layer,
            self.primary.galaxy_layer,
            halo_pos,
            gal_pos,
        )

    def next_snap_num(self) -> int:
        return (
            self.active_model.current_snap + 1
        ) % self.active_model.snap_count

    def prev_snap_num(self) -> int:
        return (
            self.active_model.current_snap - 1
        ) % self.active_model.snap_count

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def register_snap_change_callback(self, cb: Callable[[int], None]) -> None:
        self._on_snap_change.append(cb)

    def register_model_change_callback(self, cb: Callable[[], None]) -> None:
        self._on_model_change.append(cb)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        for m in self._models.values():
            m.shutdown()
        self._plotter.close()
