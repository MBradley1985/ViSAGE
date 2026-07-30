from __future__ import annotations

import asyncio
import base64
import io
import os as _os

import numpy as np
from trame.widgets import html, vuetify3 as v3

from visage.scene.camera_motion import (
    orbit_around,
    orbit_start_position,
    smooth_move,
)
from visage.scene.scene import Scene

# Frames per second for each speed multiplier
_FPS: dict[float, float] = {
    0.1: 0.3,
    0.25: 0.75,
    0.5: 1.5,
    0.75: 2.25,
    1: 3,
    2: 6,
    5: 15,
}

_SPEED_ITEMS = [
    {"title": "0.1×", "value": 0.1},
    {"title": "0.25×", "value": 0.25},
    {"title": "0.5×", "value": 0.5},
    {"title": "0.75×", "value": 0.75},
    {"title": "1×", "value": 1},
    {"title": "2×", "value": 2},
    {"title": "5×", "value": 5},
]

_ROTATE_ITEMS = [
    {"title": "Off", "value": "off"},
    {"title": "CW  15°/s", "value": "cw_15"},
    {"title": "CW  30°/s", "value": "cw_30"},
    {"title": "CW  60°/s", "value": "cw_60"},
    {"title": "CCW 15°/s", "value": "ccw_15"},
    {"title": "CCW 30°/s", "value": "ccw_30"},
    {"title": "CCW 60°/s", "value": "ccw_60"},
]

_ROT_RATE_FPS = 12  # rotation render rate — lower = less load, larger steps

# All trame state variables that affect what a rendered frame looks like.
# Checked in _scene_hash() so the frame cache is invalidated when any of these
# change (filters, environment, box/sphere selection, options, etc.).
_SCENE_FILTER_VARS: tuple[str, ...] = (
    "filter_halo_mvir",
    "filter_halo_rvir",
    "filter_halo_vvir",
    "filter_halo_len",
    "filter_halo_vmax",
    "filter_halo_conc",
    "filter_halo_spin",
    "filter_gal_smass",
    "filter_gal_sfr",
    "filter_gal_ssfr",
    "filter_gal_coldgas",
    "filter_gal_bulge",
    "filter_gal_bt",
    "filter_gal_type",
    "filter_gal_bhmass",
    "filter_gal_ics",
    "filter_gal_h2",
    "filter_gal_cgmgas",
    "filter_gal_hotgas",
    "filter_gal_h1gas",
    "filter_gal_ejected",
    "filter_gal_outflow",
    "filter_gal_massload",
    "filter_gal_cooling",
    "filter_gal_heating",
    "filter_gal_diskrad",
    "filter_gal_bulgerad",
    "filter_gal_mb_mass",
    "filter_gal_mb_rad",
    "filter_gal_ib_mass",
    "filter_gal_ib_rad",
    "filter_gal_sfr_bulge",
    "filter_gal_sfr_disk",
    "filter_gal_sfr_blg_z",
    "filter_gal_sfr_dsk_z",
    "filter_gal_met_cg",
    "filter_gal_met_sm",
    "filter_gal_met_bm",
    "filter_gal_met_hg",
    "filter_gal_met_em",
    "filter_gal_met_ics",
    "filter_gal_met_cgm",
    "filter_gal_ffb",
    "filter_gal_cgm",
    "filter_gal_age",
    "env_show_field",
    "env_show_isolated",
    "env_show_pairs",
    "env_show_group",
    "env_show_cluster",
)


def _parse_rotate(mode: str) -> tuple[float, float]:
    """Return (sign, deg_per_second) for a rotate_mode string, or (0, 0) for off."""
    if mode == "off":
        return 0.0, 0.0
    parts = mode.split("_")
    sign = 1.0 if parts[0] == "cw" else -1.0
    return sign, float(parts[1])


def build_toolbar(server, scene: Scene) -> None:
    state, ctrl = server.state, server.controller
    snap_count = scene._snap_table.count
    # Slider bounds — normally the full snap table, but a lightcone only spans
    # the snapshots actually present in the cone (snap_min..snap_max).
    snap_lo = int(getattr(scene.primary, "snap_min", 0))
    snap_hi = int(getattr(scene.primary, "snap_max", snap_count - 1))

    state.snap_num = scene.current_snap
    state.snap_label = scene.snap_label
    state.snap_min = snap_lo
    state.snap_max = snap_hi
    state.play_speed = 1
    _snap_count = [
        snap_count
    ]  # mutable so closures stay current after model switch
    _snap_lo = [snap_lo]  # slider lower bound (0 for a box)
    _snap_hi = [snap_hi]  # slider upper bound (snap_count-1 for a box)
    state.is_playing = False
    state.is_reverse = False
    state.is_repeat = False
    state.rotate_mode = "off"
    state.flythrough_active = False
    state.preload_status = ""  # non-empty while the snapshot cache warms
    # Pre-rendered playback: frames are rendered once on play, then flipped
    # through as images for stutter-free playback.
    state.playback_active = False  # showing pre-rendered frames
    state.playback_frame = ""  # current frame data URL
    state.prerender_busy = False  # rendering frames (full-viewport overlay)

    # Plain dict — direction/repeat flags read from the play coroutine
    _ctl = {"reverse": False, "repeat": False, "rotate_mode": "off"}

    # asyncio.Event drives pause/stop without relying on state-proxy reactivity.
    # Created lazily on first use so we bind to the running loop.
    _stop_evt: list[asyncio.Event | None] = [None]
    _play_task: list[asyncio.Task | None] = [None]
    _rotate_task: list[asyncio.Task | None] = [None]
    _flythrough_task: list[asyncio.Task | None] = [None]
    # While True, internal snapshot changes (the pre-render sweep) don't push
    # snap_num / snap_label to the client, so the slider and the redshift/scale
    # readout stay still during loading.
    _suppress_snap = [False]

    def _get_stop_evt() -> asyncio.Event:
        if _stop_evt[0] is None:
            _stop_evt[0] = asyncio.Event()
        return _stop_evt[0]

    def _on_snap_change(n):
        if _suppress_snap[0]:
            return
        state.update({"snap_num": n, "snap_label": scene.snap_label})

    scene.register_snap_change_callback(lambda n: _on_snap_change(n))

    def _on_model_change():
        new_count = scene._snap_table.count
        _snap_count[0] = new_count
        _snap_lo[0] = int(getattr(scene.active_model, "snap_min", 0))
        _snap_hi[0] = int(
            getattr(scene.active_model, "snap_max", new_count - 1)
        )
        _suppress_snap[0] = False  # cancel any in-flight prerender
        _frames["key"] = None
        _frames["data"] = {}
        _preload_started[0] = False
        _preload_done[0] = False
        state.snap_min = _snap_lo[0]
        state.snap_max = _snap_hi[0]
        state.snap_num = scene.current_snap
        state.snap_label = scene.snap_label
        state.flush()

    scene.register_model_change_callback(_on_model_change)

    def _push():
        if hasattr(ctrl, "view_update"):
            ctrl.view_update()

    # ------------------------------------------------------------------
    # Slider
    # ------------------------------------------------------------------

    @state.change("snap_num")
    def on_snap_slider(snap_num, **_):
        if _play_task[0] is None or _play_task[0].done():
            scene.set_snapshot(int(snap_num))
            state.snap_label = scene.snap_label
            state.flush()
            _push()

    # ------------------------------------------------------------------
    # Playback — driven by a single task + asyncio.Event for instant stop
    # ------------------------------------------------------------------

    # Per-snapshot frame cache + the camera/rotation/scene-state signature it's valid for.
    _frames: dict = {"key": None, "data": {}}

    def _scene_hash() -> int:
        """Integer fingerprint of all visual-affecting scene state.

        Covers every filter, environment, focus, visibility, opacity, and
        colour-mode setting so the frame cache is invalidated whenever any of
        those change — even when the camera hasn't moved."""
        gl = scene.galaxy_layer
        hl = scene.halo_layer
        parts: list = []
        for v in _SCENE_FILTER_VARS:
            val = getattr(state, v, None)
            parts.append(tuple(val) if isinstance(val, list) else val)
        parts += [
            gl.visible,
            round(gl.opacity, 3),
            gl.color_mode,
            gl.colormap,
            hl.visible,
            round(hl.opacity, 3),
            hl.color_mode,
            hl.colormap,
            str(scene._focus_region),
            scene.camera.has_member_indicators,
        ]
        return hash(tuple(parts))

    def _cam_key():
        cam = scene.plotter.camera
        return (
            tuple(np.round(cam.position, 2)),
            tuple(np.round(cam.focal_point, 2)),
            tuple(np.round(cam.up, 3)),
            _ctl["rotate_mode"],
            _scene_hash(),
        )

    def _cancel_rotate():
        if _rotate_task[0] is not None and not _rotate_task[0].done():
            _rotate_task[0].cancel()

    def _ensure_rotate_loop():
        if _ctl["rotate_mode"] != "off" and (
            _rotate_task[0] is None or _rotate_task[0].done()
        ):
            _rotate_task[0] = asyncio.ensure_future(_rotate_loop())

    def _capture_frame() -> np.ndarray:
        """Grab the current render-window image as an (H, W, 3) uint8 array.
        Uses vtkWindowToImageFilter directly because the remote-view plotter
        is never .show()n, so pyvista's screenshot() refuses to run."""
        from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
        from vtkmodules.util.numpy_support import vtk_to_numpy

        rw = scene.plotter.ren_win
        rw.Render()
        w2if = vtkWindowToImageFilter()
        w2if.SetInput(rw)
        w2if.SetInputBufferTypeToRGB()
        w2if.ReadFrontBufferOff()
        w2if.Update()
        vimg = w2if.GetOutput()
        w, h, _ = vimg.GetDimensions()
        arr = vtk_to_numpy(vimg.GetPointData().GetScalars()).reshape(h, w, -1)
        return arr[::-1]  # VTK image origin is bottom-left

    async def _render_frames(order: list[int]) -> None:
        """Render the snapshots in `order` (skipping any already cached) into
        _frames['data']. Rotation, when active, is baked by play-order
        position so the spin starts from the current view.

        As soon as the starting frame exists, the playback overlay is raised
        showing it, so the rest of the render is never visible underneath
        (the live view would otherwise flicker through every snapshot)."""
        from PIL import Image

        pl = scene.plotter
        cam = pl.camera
        pos0 = np.array(cam.position, dtype=np.float64)
        focal0 = np.array(cam.focal_point, dtype=np.float64)
        sign, dps = _parse_rotate(_ctl["rotate_mode"])
        per_snap = np.deg2rad(sign * dps / 3.0)
        stop_evt = _get_stop_evt()
        first = order[0]

        # Starting frame already cached → raise the overlay before rendering.
        if first in _frames["data"]:
            state.playback_frame = _frames["data"][first]
            state.playback_active = True

        todo = [
            (pos, s) for pos, s in enumerate(order) if s not in _frames["data"]
        ]
        total = len(todo)
        if total == 0:
            state.flush()
            return

        state.prerender_busy = True
        state.flush()
        # Off-screen rendering writes to an FBO we can actually read back —
        # the on-screen/back buffer comes out black on this setup.
        rw = pl.ren_win
        prev_offscreen = rw.GetOffScreenRendering()
        rw.SetOffScreenRendering(1)
        try:
            done = 0
            for pos, s in todo:
                if stop_evt.is_set():
                    break
                scene.set_snapshot(s)
                if per_snap:
                    ang = per_snap * pos
                    c, sn = np.cos(ang), np.sin(ang)
                    rm = np.array([[c, 0, sn], [0, 1, 0], [-sn, 0, c]])
                    cam.position = tuple(focal0 + rm @ (pos0 - focal0))
                    cam.focal_point = tuple(focal0)
                    cam.up = (0.0, 1.0, 0.0)
                img = _capture_frame()
                buf = io.BytesIO()
                Image.fromarray(img[..., :3]).save(
                    buf, format="JPEG", quality=95
                )
                url = "data:image/jpeg;base64," + base64.b64encode(
                    buf.getvalue()
                ).decode("ascii")
                _frames["data"][s] = url
                if s == first:
                    # Cover the rest of the render with the starting frame.
                    state.playback_frame = url
                    state.playback_active = True
                done += 1
                state.preload_status = f"Loading snapshots...  {done}/{total}"
                state.flush()
                await asyncio.sleep(0)
        finally:
            rw.SetOffScreenRendering(prev_offscreen)
            cam.position = tuple(pos0)
            cam.focal_point = tuple(focal0)
            cam.up = (0.0, 1.0, 0.0)
            state.prerender_busy = False
            state.preload_status = ""
            state.flush()

    async def _image_playback(order: list[int]) -> None:
        stop_evt = _get_stop_evt()
        n = len(order)
        if n == 0:
            return
        state.playback_active = True
        state.is_playing = True
        state.flush()
        idx = 0
        try:
            while not stop_evt.is_set():
                interval = 1.0 / _FPS.get(float(state.play_speed), 3)
                s = order[idx]
                frame = _frames["data"].get(s)
                if frame is not None:
                    state.playback_frame = frame
                state.snap_num = s
                state.snap_label = scene._snap_table.label(s)
                state.flush()

                # Hold every frame — including the last — for the full
                # interval, otherwise the final snapshot just flashes past.
                try:
                    await asyncio.wait_for(stop_evt.wait(), timeout=interval)
                    break
                except asyncio.TimeoutError:
                    pass

                if idx == n - 1:
                    if not _ctl["repeat"]:
                        break
                    idx = 0
                else:
                    idx += 1
        finally:
            state.is_playing = False
            state.flush()

    async def _play_sequence():
        stop_evt = _get_stop_evt()
        _cancel_rotate()
        await _await_preload()
        if stop_evt.is_set():
            return
        # Play from the current slider position toward z=0 (forward) or toward
        # high-z (reverse). Only that range is rendered.
        start = int(state.snap_num)
        if _ctl["reverse"]:
            order = list(range(start, _snap_lo[0] - 1, -1))
        else:
            order = list(range(start, _snap_hi[0] + 1))
        # Invalidate the frame cache if the camera, rotation, or start position
        # changed. Start is included because rotation bakes the angle by frame
        # position — the same snapshot lands at a different angle when playback
        # begins from a different snapshot, so cached frames from a prior run
        # would be wrong.
        rot_start = start if _ctl["rotate_mode"] != "off" else 0
        key = _cam_key() + (rot_start,)
        if _frames["key"] != key:
            _frames["key"] = key
            _frames["data"] = {}
        # Freeze the slider + redshift readout while rendering — the snapshot
        # sweep below shouldn't drag them around.
        _suppress_snap[0] = True
        await _render_frames(order)  # raises the overlay itself
        if stop_evt.is_set():
            _suppress_snap[0] = False
            state.playback_active = False
            state.flush()
            return
        # _render_frames restores the camera to pos0/focal0 when it exits.
        # If rotation was baked into the pre-rendered frames, advance the live
        # camera to the final frame's rotation angle now, while the overlay is
        # still covering the VTK canvas.  The reveal will then be seamless —
        # the live scene matches the last overlay frame, and _ensure_rotate_loop
        # continues rotating from exactly where the animation left off.
        _rots, _rotd = _parse_rotate(_ctl["rotate_mode"])
        _per_snap = np.deg2rad(_rots * _rotd / 3.0)
        if _per_snap:
            _cam = scene.plotter.camera
            _pos0 = np.array(_cam.position, dtype=np.float64)
            _focal0 = np.array(_cam.focal_point, dtype=np.float64)
            _ang = _per_snap * (len(order) - 1)
            _c, _sn = np.cos(_ang), np.sin(_ang)
            _rm = np.array([[_c, 0, _sn], [0, 1, 0], [-_sn, 0, _c]])
            _cam.position = tuple(_focal0 + _rm @ (_pos0 - _focal0))
            _cam.focal_point = tuple(_focal0)
            _cam.up = (0.0, 1.0, 0.0)
        # Park the live scene on the final snapshot now, while the overlay is
        # still covering it, so revealing it at the end is a seamless match —
        # no flash of the selected snapshot, no jump.
        scene.set_snapshot(order[-1])
        _push()
        _suppress_snap[0] = False  # playback drives the slider from here
        await _image_playback(order)
        # Ended naturally.  Push a fresh live render so the VTK canvas is
        # up-to-date when the overlay drops — the earlier _push() may have
        # been many seconds ago.
        last = int(state.snap_num)
        if scene.current_snap != last:
            scene.set_snapshot(last)
        _push()
        state.snap_label = scene.snap_label
        state.flush()
        await asyncio.sleep(0.2)  # let the render stream before revealing
        state.playback_active = False
        state.flush()
        _ensure_rotate_loop()

    @ctrl.set("play")
    async def on_play():
        if _play_task[0] is not None and not _play_task[0].done():
            return
        _get_stop_evt().clear()
        _start_preload()
        _play_task[0] = asyncio.ensure_future(_play_sequence())

    def _end_playback_to(snap: int) -> None:
        """Stop any playback / prerender and hand back to the live view at
        `snap`. The overlay is kept up — showing the matching frame — until
        the live render of `snap` has streamed, so there's no black flash as
        it hands off."""
        if _stop_evt[0] is not None:
            _stop_evt[0].set()
        if _play_task[0] is not None and not _play_task[0].done():
            _play_task[0].cancel()
        _suppress_snap[0] = False
        state.is_playing = False
        state.prerender_busy = False
        state.preload_status = ""
        # Keep the overlay up, showing the target frame if we have it, so it
        # matches the live view we're about to reveal.
        if snap in _frames["data"]:
            state.playback_frame = _frames["data"][snap]
        state.playback_active = True
        # Render the live view at `snap` behind the overlay.
        scene.set_snapshot(snap)
        state.snap_num = snap
        state.snap_label = scene.snap_label
        state.flush()
        _push()
        _ensure_rotate_loop()

        async def _reveal():
            # The live re-render (rebuild + encode + stream) isn't instant and
            # the off-screen toggle can leave a black intermediate, so hold the
            # overlay, re-push once the rebuild has settled, then reveal — only
            # if no new playback started meanwhile.
            await asyncio.sleep(0.4)
            if _play_task[0] is not None and not _play_task[0].done():
                return
            _push()
            await asyncio.sleep(0.55)
            if _play_task[0] is None or _play_task[0].done():
                state.playback_active = False
                state.flush()

        asyncio.ensure_future(_reveal())

    @ctrl.set("pause")
    def on_pause():
        _end_playback_to(int(state.snap_num))

    @ctrl.set("stop")
    def on_stop():
        _end_playback_to(_snap_hi[0])

    @ctrl.set("snap_prev")
    def on_snap_prev():
        if _play_task[0] is not None and not _play_task[0].done():
            return
        n = max(_snap_lo[0], int(state.snap_num) - 1)
        scene.set_snapshot(n)
        state.snap_num = n
        state.snap_label = scene.snap_label
        state.flush()
        _push()

    @ctrl.set("snap_next")
    def on_snap_next():
        if _play_task[0] is not None and not _play_task[0].done():
            return
        n = min(_snap_hi[0], int(state.snap_num) + 1)
        scene.set_snapshot(n)
        state.snap_num = n
        state.snap_label = scene.snap_label
        state.flush()
        _push()

    @ctrl.set("sync_active_snap_count")
    def on_sync_active_snap_count():
        """Update the toolbar's snap-count cache to the active box.

        Called after an active-box switch so step/play use the correct range
        for whichever model is currently selected.
        """
        _snap_count[0] = scene.active_model.snap_count
        _snap_lo[0] = int(getattr(scene.active_model, "snap_min", 0))
        _snap_hi[0] = int(
            getattr(scene.active_model, "snap_max", _snap_count[0] - 1)
        )
        state.snap_min = _snap_lo[0]
        state.snap_max = _snap_hi[0]
        _frames["key"] = None
        _frames["data"] = {}

    @ctrl.set("refresh_snap_range")
    def on_refresh_snap_range():
        """Update slider bounds + current snap after a model switch."""
        new_count = scene._snap_table.count
        _snap_count[0] = new_count
        _snap_lo[0] = int(getattr(scene.active_model, "snap_min", 0))
        _snap_hi[0] = int(
            getattr(scene.active_model, "snap_max", new_count - 1)
        )
        state.snap_min = _snap_lo[0]
        state.snap_max = _snap_hi[0]
        state.snap_num = scene.current_snap
        state.snap_label = scene.snap_label
        # Invalidate pre-rendered frame cache; reset preload so it reruns
        _frames["key"] = None
        _frames["data"] = {}
        _preload_started[0] = False
        _preload_done[0] = False
        state.flush()

    @ctrl.set("toggle_reverse")
    def on_toggle_reverse():
        _ctl["reverse"] = not _ctl["reverse"]
        state.is_reverse = _ctl["reverse"]

    @ctrl.set("toggle_repeat")
    def on_toggle_repeat():
        _ctl["repeat"] = not _ctl["repeat"]
        state.is_repeat = _ctl["repeat"]

    # ------------------------------------------------------------------
    # Rotation — smaller per-frame angle for smoothness
    # ------------------------------------------------------------------

    async def _rotate_loop():
        interval = 1.0 / _ROT_RATE_FPS
        while _ctl["rotate_mode"] != "off":
            mode = _ctl["rotate_mode"]
            sign, deg_per_sec = _parse_rotate(mode)
            if sign == 0:
                break
            # While recording, _record_loop steps rotation at the recording
            # FPS — skip stepping here to avoid double-rotating the camera.
            if not bool(getattr(state, "recording_active", False)):
                delta = sign * deg_per_sec * interval
                cam = scene.plotter.camera
                focal = np.array(cam.focal_point, dtype=np.float64)
                pos = np.array(cam.position, dtype=np.float64)
                r = pos - focal
                angle = np.deg2rad(delta)
                c, s = np.cos(angle), np.sin(angle)
                rm = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
                cam.position = tuple(focal + rm @ r)
                cam.up = (0.0, 1.0, 0.0)
            _push()
            await asyncio.sleep(interval)

    @state.change("rotate_mode")
    def on_rotate_mode(rotate_mode, **_):
        _ctl["rotate_mode"] = rotate_mode
        if rotate_mode == "off":
            if _rotate_task[0] is not None and not _rotate_task[0].done():
                _rotate_task[0].cancel()
            return
        # Stop fly-through if rotation is engaged
        if bool(getattr(state, "flythrough_active", False)):
            state.flythrough_active = False
        if _rotate_task[0] is None or _rotate_task[0].done():
            _rotate_task[0] = asyncio.ensure_future(_rotate_loop())

    # ------------------------------------------------------------------
    # Fly-through mode — a continuous tour of every group and cluster:
    #   1. Approach : Explore Mode only — fly in from the reset view to the
    #                 box centre as an establishing shot. Lightcone Mode
    #                 skips this (see below) and goes straight to step 2.
    #   2. Tour     : fly to each group/cluster in turn, spin around it,
    #                 then move to the next — looping forever once every
    #                 target has been visited. Never zooms out to orbit
    #                 the box/cone as a whole.
    # In Lightcone Mode, targets are ordered near → far (a genuine flight
    # outward through the cone) and the tour's first move zooms straight
    # from the reset framing into the nearest group/cluster — no separate
    # approach to the observer's point (that looked wrong: the cone's
    # narrow sky angle inside a much wider FOV read as a thin sliver/bar,
    # and the transition into the first target didn't flow).
    # In Explore Mode, targets are ordered most massive → least.
    # ------------------------------------------------------------------

    _FT_FPS = 15  # render rate during fly-through
    _FT_APPROACH_SECS = 8.0  # fly-in duration (reset → starting viewpoint)
    _FT_GROUP_RADIUS = 15.0  # standoff radius for group spin
    _FT_CLUSTER_RADIUS = 30.0  # standoff radius for cluster spin
    _FT_GROUP_DPS = 10.0  # group spin speed deg/s
    _FT_CLUSTER_DPS = 8.0  # cluster spin speed deg/s

    async def _flythrough_loop():
        import numpy as _np

        try:
            interval = 1.0 / _FT_FPS
            cam = scene.plotter.camera
            is_lc = scene.is_lightcone

            def _active():
                return bool(getattr(state, "flythrough_active", False))

            # ── Shared camera-motion helpers (see scene/camera_motion.py) ──
            async def _smooth_move(p0, f0, p1, f1, secs):
                return await smooth_move(
                    cam,
                    p0,
                    f0,
                    p1,
                    f1,
                    secs,
                    _FT_FPS,
                    is_active=_active,
                    push=_push,
                )

            async def _orbit_around(target, radius, spin_degs, dps):
                return await orbit_around(
                    cam,
                    target,
                    radius,
                    spin_degs,
                    dps,
                    _FT_FPS,
                    is_active=_active,
                    push=_push,
                )

            # Fly to the orbit-start position around a target, keeping the
            # camera on its current bearing so there is no direction flip.
            async def _fly_to_orbit(target, radius, secs):
                t3 = _np.array(target, dtype=float)
                dest_pos = orbit_start_position(cam, t3, radius)
                return await _smooth_move(
                    _np.array(cam.position, dtype=float),
                    _np.array(cam.focal_point, dtype=float),
                    dest_pos,
                    t3,
                    secs,
                )

            # ── Load simulation data + build the continuous tour list ─────
            halos, galaxies = scene.active_model.loader.get(scene.current_snap)
            off = _np.array(scene.active_model.offset, dtype=float)

            targets = []  # [(position, standoff_radius, spin_deg_per_sec)]
            h_pos = _np.empty((0, 3))
            if halos.count > 0:
                log_m = _np.log10(
                    _np.maximum(_np.array(halos.masses, dtype=float), 1.0)
                )
                h_pos = _np.array(halos.positions, dtype=float) + off
                mask = log_m >= 12.5  # groups (12.5-14) and clusters (>=14)
                if mask.any():
                    idxs = _np.where(mask)[0]
                    if is_lc:
                        # Observer sits at the coordinate origin in a
                        # lightcone — tour near-to-far, like actually
                        # flying outward through the cone.
                        dist = _np.linalg.norm(h_pos[idxs], axis=1)
                        order = idxs[_np.argsort(dist)]
                    else:
                        order = idxs[_np.argsort(-halos.masses[idxs])]
                    for i in order:
                        if log_m[i] >= 14.0:
                            targets.append(
                                (h_pos[i], _FT_CLUSTER_RADIUS, _FT_CLUSTER_DPS)
                            )
                        else:
                            targets.append(
                                (h_pos[i], _FT_GROUP_RADIUS, _FT_GROUP_DPS)
                            )

            # ── Snap to the normal reset framing ───────────────────────────
            scene.camera.reset()
            start_pos = _np.array(cam.position, dtype=float)
            start_focal = _np.array(cam.focal_point, dtype=float)
            _push()
            await asyncio.sleep(interval)

            # ── Phase 1: Approach ──────────────────────────────────────────
            # Explore Mode: fly in from the reset view to the box centre —
            # an establishing shot before the tour begins.
            # Lightcone Mode: no separate approach — parking the camera at
            # the observer's point (the coordinate origin) looked wrong (the
            # cone's narrow sky angle inside a much wider FOV read as a thin
            # sliver/bar, and the transition into the first target didn't
            # flow). Instead, the tour's own first move (below) zooms
            # straight from the reset framing into the first group/cluster.
            if not is_lc:
                bs = scene._cfg.box_size
                half = bs / 2.0
                dest_pos = _np.array([half, half, half])
                dest_focal = dest_pos + _np.array([0.0, 0.0, -0.5])
                if not await _smooth_move(
                    start_pos,
                    start_focal,
                    dest_pos,
                    dest_focal,
                    _FT_APPROACH_SECS,
                ):
                    return

            # ── Phase 2: Continuous group/cluster tour — loops forever ────
            i = 0
            while _active():
                if not targets:
                    await asyncio.sleep(interval)
                    continue
                pos, radius, dps = targets[i % len(targets)]
                approach_secs = 8.0 if radius == _FT_CLUSTER_RADIUS else 6.5
                # Lightcone Mode skips the establishing approach, so its FIRST
                # move flies all the way from the whole-cone reset framing into
                # the nearest group — a far larger distance than any box-mode
                # move. At the fixed 6.5-8 s that reads as a fast swoop. Scale
                # the first move's duration by distance so its linear speed
                # matches box mode's gentle approach (≈ span / approach_secs).
                if is_lc and i == 0:
                    dest = orbit_start_position(
                        cam, _np.array(pos, dtype=float), radius
                    )
                    dist = float(
                        _np.linalg.norm(
                            dest - _np.array(cam.position, dtype=float)
                        )
                    )
                    span = float(getattr(scene._cfg, "box_size", 0.0)) or 1.0
                    ref_speed = span / _FT_APPROACH_SECS
                    approach_secs = float(
                        _np.clip(dist / ref_speed, _FT_APPROACH_SECS, 18.0)
                    )
                if not await _fly_to_orbit(pos, radius, approach_secs):
                    return
                # Focus ON — render one stationary frame so focus is visible
                # before any rotation starts.
                scene.set_focus_sphere(tuple(pos), radius)
                state.focus_active = True
                _push()
                await asyncio.sleep(interval)
                if not _active():
                    scene.clear_focus()
                    state.focus_active = False
                    return
                if not await _orbit_around(pos, radius, 360.0, dps):
                    scene.clear_focus()
                    state.focus_active = False
                    return
                # Focus OFF — render one stationary frame after rotation stops,
                # before clearing focus and moving on.
                _push()
                await asyncio.sleep(interval)
                if not _active():
                    scene.clear_focus()
                    state.focus_active = False
                    return
                scene.clear_focus()
                state.focus_active = False
                i += 1

        except asyncio.CancelledError:
            pass
        finally:
            if bool(getattr(state, "flythrough_active", False)):
                state.flythrough_active = False
                state.flush()

    @state.change("flythrough_active")
    def on_flythrough_active(flythrough_active, **_):
        if not flythrough_active:
            t = _flythrough_task[0]
            if t is not None and not t.done():
                t.cancel()
            return
        # Stop rotation if active
        if _ctl["rotate_mode"] != "off":
            state.rotate_mode = "off"
        if _flythrough_task[0] is None or _flythrough_task[0].done():
            _flythrough_task[0] = asyncio.ensure_future(_flythrough_loop())

    @ctrl.set("toggle_flythrough")
    def on_toggle_flythrough():
        state.flythrough_active = not bool(
            getattr(state, "flythrough_active", False)
        )

    # ------------------------------------------------------------------
    # Snapshot preloading — warm the whole cache in the background so
    # playback steps frame-to-frame without disk stalls. A status chip in
    # the toolbar reports progress while it runs.
    # ------------------------------------------------------------------

    _preload_started = [False]
    _preload_done = [False]

    async def _preload_loop():
        loader = scene._loader
        futures = loader.preload_all()
        total = len(futures)
        if total == 0:
            _preload_done[0] = True
            return
        while True:
            done = sum(1 for f in futures if f.done())
            if done >= total:
                break
            state.preload_status = f"Loading snapshots...  {done}/{total}"
            state.flush()
            await asyncio.sleep(0.25)
        _preload_done[0] = True
        state.preload_status = ""
        state.flush()

    def _start_preload(**_):
        if _preload_started[0]:
            return
        _preload_started[0] = True
        try:
            asyncio.ensure_future(_preload_loop())
        except RuntimeError:
            # No running loop yet — fall back to first play press.
            _preload_started[0] = False

    async def _await_preload():
        """Block until every snapshot is cached so playback runs at an even
        cadence — without this, playback overtakes the background preload and
        stalls on uncached snapshots mid-run, then bursts through the rest."""
        _start_preload()
        if not _preload_started[0]:  # no loop earlier — start inline now
            _preload_started[0] = True
            asyncio.ensure_future(_preload_loop())
        while not _preload_done[0]:
            await asyncio.sleep(0.1)

    ctrl.add("on_server_ready")(_start_preload)

    # ------------------------------------------------------------------
    # Widgets
    # ------------------------------------------------------------------

    # Single big spacer pushes the entire playback cluster to the right
    # of the toolbar, immediately adjacent to the title / hamburger on
    # the left.
    v3.VSpacer()

    # Status chip — shows "Loading galaxies..." during model switch/load/overlay,
    # or "Loading snapshots... X/Y" while the snapshot cache warms up.
    v3.VChip(
        "{{ model_loading ? 'Loading galaxies...' : preload_status }}",
        v_show=("model_loading || preload_status",),
        size="small",
        color="#FFD700",
        prepend_icon="mdi-database-clock-outline",
        style="font-family:monospace;margin-right:10px;",
    )

    # Transport controls — leftmost of the right-hand cluster.
    with v3.VBtnGroup(variant="outlined", density="compact"):
        v3.VBtn(
            icon="mdi-swap-horizontal",
            click=ctrl.toggle_reverse,
            color=("is_reverse ? 'cyan' : 'white'",),
            title="Reverse direction",
        )
        v3.VBtn(icon="mdi-play", click=ctrl.play, color="white")
        v3.VBtn(icon="mdi-pause", click=ctrl.pause, color="white")
        v3.VBtn(
            icon="mdi-stop",
            click=ctrl.stop,
            color="white",
            title="Stop and return to z=0",
        )
        v3.VBtn(
            icon="mdi-repeat",
            click=ctrl.toggle_repeat,
            color=("is_repeat ? 'cyan' : 'white'",),
            title="Loop",
        )

    _FLASH_JS = (
        "var b=this,i=b.querySelector('i');"
        "b.style.color='cyan';"
        "if(i)i.style.color='cyan';"
        "clearTimeout(b._ft);"
        "b._ft=setTimeout(function(){b.style.color='white';if(i)i.style.color='';},300);"
    )

    # Snapshot step-back button + slider + step-forward button
    with html.Button(
        click=ctrl.snap_prev,
        title="Previous snapshot",
        classes="sage-step-btn",
        raw_attrs=[f'onmousedown="{_FLASH_JS}"'],
        style=(
            "background:none;border:none;outline:none;box-shadow:none;"
            "cursor:pointer;padding:2px;margin-left:10px;"
            "color:white;font-size:20px;line-height:1;display:flex;align-items:center;"
        ),
    ):
        html.I(classes="mdi mdi-skip-previous")
    with v3.VCol(style="max-width:240px;padding:0 4px;"):
        v3.VSlider(
            v_model=("snap_num",),
            min=("snap_min",),
            max=("snap_max",),
            step=1,
            thumb_label=False,
            hide_details=True,
            color="cyan",
            density="compact",
        )
    with html.Button(
        click=ctrl.snap_next,
        title="Next snapshot",
        classes="sage-step-btn",
        raw_attrs=[f'onmousedown="{_FLASH_JS}"'],
        style=(
            "background:none;border:none;outline:none;box-shadow:none;"
            "cursor:pointer;padding:2px;margin-left:6px;margin-right:10px;"
            "color:white;font-size:20px;line-height:1;display:flex;align-items:center;"
        ),
    ):
        html.I(classes="mdi mdi-skip-next")

    # Snapshot label chip — Mustache interpolation for reactive content
    v3.VChip(
        "{{ snap_label }}",
        size="small",
        color="cyan",
        style="font-family:monospace;min-width:220px;margin-right:8px;",
    )

    # Speed selector
    v3.VSelect(
        v_model=("play_speed",),
        items=(_SPEED_ITEMS,),
        density="compact",
        hide_details=True,
        style="max-width:90px;",
    )

    # Rotation selector — disabled in multi-box mode (shared camera)
    v3.VSelect(
        v_model=("rotate_mode",),
        items=(_ROTATE_ITEMS,),
        density="compact",
        hide_details=True,
        style="max-width:120px;",
        disabled=("box_strip_items && box_strip_items.length > 1",),
        title="Rotation disabled in multi-box mode",
    )

    # Close application button
    v3.VBtn(
        icon="mdi-close-thick",
        variant="text",
        density="compact",
        color="#ef4444",
        title="Close ViSAGE",
        click=ctrl.close_app,
        style="margin-left:8px;margin-right:4px;",
    )

    @ctrl.set("close_app")
    def on_close_app():
        asyncio.ensure_future(server.stop())

    # (theme selector removed — DOS Blue is the only palette)
