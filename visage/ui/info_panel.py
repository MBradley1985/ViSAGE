from __future__ import annotations

import time

import numpy as np
from scipy.spatial import KDTree
from trame.widgets import vuetify3 as v3

from visage.scene.scene import Scene

# Galaxies this close to the cursor (pixels) all count as under it.
_PICK_NEAR_PX = 12.0
_DOUBLE_CLICK_THRESHOLD = (
    0.45  # seconds between two clicks to count as double-click
)


def build_info_panel(server, scene: Scene) -> None:
    """Footer pick-info bar + double-click galaxy selection."""
    state = server.state
    ctrl = server.controller
    state.pick_info = "Double-click any point to select the nearest galaxy"

    _last_click: list[float] = [0.0]

    # Cache the point-picking KD-trees so repeated double-clicks don't rebuild
    # them every time. The tree only depends on the visible point set, so we key
    # on (model, snapshot, offset, visible-set fingerprint): any change — a new
    # snapshot, a different box, or a filter / environment toggle that alters
    # which points are visible — changes the key and forces a rebuild. Building a
    # KD-tree over millions of points is O(N log N); reusing it turns each extra
    # pick into a cheap query. hash(visible.tobytes()) is O(N) but ~an order of
    # magnitude cheaper than the rebuild it avoids.
    _gal_tree_cache: dict = {}
    _halo_tree_cache: dict = {}

    def _cached_tree(cache, positions, visible, off, model_name, snap):
        key = (
            model_name,
            snap,
            off.tobytes(),
            int(visible.size),
            hash(visible.tobytes()),
        )
        if cache.get("key") != key:
            cache["key"] = key
            cache["tree"] = KDTree(positions[visible] + off)
        return cache["tree"]

    def _push():
        if hasattr(ctrl, "view_update"):
            ctrl.view_update()

    def _on_pick(point):
        """Fires on every left-click; only selects on a fast second click."""
        # In HD the catalogue is hidden: picking there is done among the
        # galaxies HD draws (visage.ui.selection), and a click must not
        # switch box (which would drop HD).
        if bool(state.hd_active) if state.has("hd_active") else False:
            return
        now = time.monotonic()
        dt, _last_click[0] = now - _last_click[0], now

        # Box activation: every click checks which box was clicked by world-X coord.
        if point is not None:
            pt = np.asarray(point, dtype=np.float64)
            if not np.all(np.abs(pt) < 1e-10):
                clicked_box = scene.box_name_at(float(pt[0]))
                if clicked_box != scene.active_box_name:
                    if hasattr(ctrl, "set_active_box"):
                        ctrl.set_active_box(clicked_box)

        if dt > _DOUBLE_CLICK_THRESHOLD:
            # First click — wait for the matching second click.
            return

        # Second click fired in time — reset timer so triple-click won't cascade.
        _last_click[0] = 0.0

        if point is None:
            return
        point = np.asarray(point, dtype=np.float64)
        if np.all(np.abs(point) < 1e-10):
            return

        active = scene.active_model
        halos, galaxies = active.loader.get(active.current_snap)
        off = active.offset.astype(np.float64)
        lines = [f"({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f}) Mpc/h"]

        # ── Galaxy selection ──────────────────────────────────────────────
        # Respect environment checkboxes and all other filters via _combined_mask.
        # If combined_mask returns None (size mismatch during a snapshot transition),
        # fall back to _filter_mask so environment checkboxes are always honoured.
        gidx = None
        gpos = None
        if galaxies.count > 0:
            mask = scene.galaxy_layer._combined_mask()
            if mask is None:
                mask = scene.galaxy_layer._filter_mask
            visible = (
                np.where(mask)[0]
                if mask is not None
                else np.arange(galaxies.count)
            )

            if len(visible) > 0:
                # Two-stage selection for screen-space accuracy:
                # 1. Find the 50 nearest in 3D world space (fast pre-filter).
                # 2. Project those candidates to screen pixels and take the one
                #    visually closest to the cursor — avoids picking a galaxy
                #    that is 3D-near but hidden behind a visually closer one.
                k = min(50, len(visible))
                gtree = _cached_tree(
                    _gal_tree_cache,
                    galaxies.positions,
                    visible,
                    off,
                    active.name,
                    active.current_snap,
                )
                _, near_local = gtree.query(point, k=k)
                if np.isscalar(near_local):
                    near_local = [near_local]

                renderer = scene.plotter.renderer
                sx, sy = scene.plotter.iren.get_event_position()
                best_dist2 = float("inf")
                close = []  # within a few pixels of the cursor
                for local_i in near_local:
                    abs_idx = int(visible[local_i])
                    pos = galaxies.positions[abs_idx] + off
                    renderer.SetWorldPoint(
                        float(pos[0]), float(pos[1]), float(pos[2]), 1.0
                    )
                    renderer.WorldToDisplay()
                    dp = renderer.GetDisplayPoint()
                    d2 = (dp[0] - sx) ** 2 + (dp[1] - sy) ** 2
                    if d2 < _PICK_NEAR_PX**2:
                        close.append(abs_idx)
                    if d2 < best_dist2:
                        best_dist2 = d2
                        gidx = abs_idx
                # Under the cursor, the galaxy you can see wins: the most
                # massive there, not a dwarf a pixel closer.
                if close:
                    gidx = max(close, key=lambda k: galaxies.stellar_mass[k])

                if gidx is not None:
                    gpos = galaxies.positions[gidx] + off

        if gidx is not None:
            sm = galaxies.stellar_mass[gidx]
            ss = galaxies.ssfr[gidx]
            gt = "central" if galaxies.gal_type[gidx] == 0 else "satellite"
            lines.append(
                f"Galaxy M* = {sm:.2e} Msun  sSFR = {ss:.2e} yr^-1  "
                f"({gt})  →  idx {gidx} selected"
            )
            state.nav_gal_idx = gidx
            scene.camera._add_circle_indicator(
                (float(gpos[0]), float(gpos[1]), float(gpos[2])), 0.0
            )
            # Re-selecting the same galaxy (no index change to react to)
            # still brings its card back.
            if hasattr(ctrl, "sel_refresh"):
                ctrl.sel_refresh()

        # The host halo follows from the galaxy (visage.ui.selection), so it
        # is the halo the galaxy's group lives in, not just the nearest one.
        state.pick_info = "   |   ".join(lines)
        state.flush()
        _push()

    # Picker is on globally: a double-click anywhere selects the nearest
    # galaxy and halo, placing a circle indicator but NOT moving the
    # camera or switching tabs. The user flies/navigates independently
    # and can press Go in the Target tab when ready.
    scene.plotter.enable_point_picking(
        callback=_on_pick,
        show_message=False,
        show_point=False,
        left_clicking=True,
        tolerance=0.025,
    )

    v3.VLabel(
        ("pick_info",),
        style=(
            "font-size:0.75rem; font-family:monospace;"
            " color:#9ca3af; padding:0 12px; line-height:36px;"
        ),
    )
