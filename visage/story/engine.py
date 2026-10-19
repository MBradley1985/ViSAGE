"""Story playback engine.

``StoryPlayer`` owns the active story, the current scene index, and the async
playback task.  It applies scenes (camera + state + focus + target + theme),
runs per-scene motion, and steps with Next / Previous / Play / Pause.  It is a
non-destructive overlay: entering stashes the user's state, exiting restores it,
and pausing simply stops auto-advance without locking anything.
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import numpy as np

from visage.scene.camera_motion import (
    MOTION_FPS,
    FramePacer,
    orbit_around,
    orbit_start_position,
    smooth_move,
)
from visage.story.keys import STORY_STATE_KEYS
from visage.story.model import Story

_FPS = MOTION_FPS  # render rate for transitions / motion (matches fly-through)
_UP = (0.0, 1.0, 0.0)

# Per-kind text-overlay defaults (size in rem, weight, italic, default colour).
_OVERLAY_DEFAULTS = {
    "title": {"size": 2.2, "weight": 800, "italic": False, "color": "#ffffff"},
    "heading": {
        "size": 1.6,
        "weight": 700,
        "italic": False,
        "color": "#ffffff",
    },
    "text": {"size": 1.15, "weight": 400, "italic": False, "color": "#e2e8f0"},
    "citation": {
        "size": 0.85,
        "weight": 400,
        "italic": True,
        "color": "#94a3b8",
    },
    "equation": {
        "size": 1.6,
        "weight": 400,
        "italic": False,
        "color": "#ffffff",
    },
}


async def _maybe_await(result):
    """Await *result* if it is awaitable; otherwise return it."""
    if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
        return await result
    return result


def _overlay_position_style(anchor: str, x, y) -> str:
    """CSS positioning for a 9-grid anchor plus an offset.

    ``x``/``y`` are percentages when numeric, or pass-through CSS lengths when
    given as strings (e.g. ``"150px"``) — handy for pinning logos to a fixed
    pixel offset regardless of window width.
    """

    def _len(v):
        return v if isinstance(v, str) else f"{float(v)}%"

    parts: list[str] = ["position:absolute;"]
    transforms: list[str] = []
    # Vertical.
    if anchor.startswith("top"):
        parts.append(f"top:{_len(y)};")
    elif anchor.startswith("bottom"):
        parts.append(f"bottom:{_len(y)};")
    else:  # vertical centre
        parts.append("top:50%;")
        transforms.append("translateY(-50%)")
    # Horizontal.
    if anchor.endswith("left"):
        parts.append(f"left:{_len(x)};")
    elif anchor.endswith("right"):
        parts.append(f"right:{_len(x)};")
    else:  # horizontal centre
        parts.append("left:50%;")
        transforms.append("translateX(-50%)")
    if transforms:
        parts.append(f"transform:{' '.join(transforms)};")
    return "".join(parts)


def _normalize_overlay(item: dict) -> dict:
    """Turn an authored overlay into a render-ready dict for the JS renderer.

    Equation items carry ``latex`` + ``display`` so the client calls
    ``katex.render`` directly (more reliable than delimiter auto-render).
    Other items carry plain ``text``.
    """
    kind = item.get("kind", "text")
    anchor = item.get("anchor", "top-left")
    # Numeric → percentage; string → pass-through CSS length (e.g. "150px").
    x = item.get("x", 6.0)
    y = item.get("y", 6.0)

    # Image overlays (e.g. logos) carry a src + sizing, not text/font props.
    if kind == "image":
        w = item.get("width", 140)
        width_css = w if isinstance(w, str) else f"{float(w):g}px"
        style = (
            _overlay_position_style(anchor, x, y)
            + f"width:{width_css};height:auto;"
            + f"opacity:{float(item.get('opacity', 1.0))};"
            + "pointer-events:none;"
            + "filter:drop-shadow(0 2px 8px rgba(0,0,0,0.8));"
        )
        return {
            "id": str(item.get("id", "")),
            "style": style,
            "src": item.get("src", ""),
        }

    # Video overlays (e.g. the TNG movie) carry a src + sizing like an image,
    # plus playback flags. Served from visage/static/ at /sage_static/,
    # so the file must live there (NOT the data Library). Use MP4/WebM.
    if kind == "video":
        w = item.get("width", 480)
        width_css = w if isinstance(w, str) else f"{float(w):g}px"
        # With controls on, the element must accept clicks so the user can use
        # the native transport / fullscreen button; otherwise stay click-through.
        controls = bool(item.get("controls", False))
        style = (
            _overlay_position_style(anchor, x, y)
            + f"width:{width_css};height:auto;"
            + f"opacity:{float(item.get('opacity', 1.0))};"
            + ("pointer-events:auto;" if controls else "pointer-events:none;")
            + "filter:drop-shadow(0 2px 8px rgba(0,0,0,0.8));"
        )
        return {
            "id": str(item.get("id", "")),
            "style": style,
            "src": item.get("src", ""),
            "video": True,
            "loop": bool(item.get("loop", True)),
            "autoplay": bool(item.get("autoplay", True)),
            "muted": bool(item.get("muted", True)),
            "controls": controls,
        }

    # Audio overlays (e.g. a short intro sting) carry only a src + playback
    # flags and render NO visible element. Served from /sage_static/ like
    # image/video. Unlike video they default unmuted and play once (loop off);
    # the client pauses/resumes them with the show's play/pause state.
    if kind == "audio":
        return {
            "id": str(item.get("id", "")),
            "src": item.get("src", ""),
            "audio": True,
            "loop": bool(item.get("loop", False)),
            "autoplay": bool(item.get("autoplay", True)),
            "muted": bool(item.get("muted", False)),
            "volume": float(item.get("volume", 1.0)),
        }

    base = _OVERLAY_DEFAULTS.get(kind, _OVERLAY_DEFAULTS["text"])

    size = float(item.get("size", base["size"]))
    color = item.get("color", base["color"])
    weight = int(item.get("weight", base["weight"]))
    italic = bool(item.get("italic", base["italic"]))
    align = item.get("align", "left")

    style = (
        _overlay_position_style(anchor, x, y)
        + f"font-size:{size}rem;color:{color};font-weight:{weight};"
        + f"text-align:{align};"
        + ("font-style:italic;" if italic else "")
        + "white-space:pre-wrap;pointer-events:none;"
        + "text-shadow:0 2px 8px rgba(0,0,0,0.8);line-height:1.25;"
        # % of the fixed overlay stage (not vw) so it scales together with the
        # rest of the slide when the stage is fitted to the window (visage.js).
        + f"max-width:{float(item.get('max_width', 60))}%;"
    )
    out: dict = {"id": str(item.get("id", "")), "style": style}
    if kind == "equation":
        out["latex"] = item.get("latex", "")
        out["display"] = not bool(item.get("inline"))
    else:
        out["text"] = item.get("text", "")
    return out


def _parse_redshift_spec(value):
    """Return the redshift float for a ``"z=1.5"`` / ``"z1.5"`` spec, else None."""
    if not isinstance(value, str):
        return None
    s = value.strip().lower().replace(" ", "")
    if s.startswith("z="):
        s = s[2:]
    elif s.startswith("z"):
        s = s[1:]
    else:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def resolve_snap(value, count: int, table=None) -> int:
    """Resolve a (possibly symbolic) snapshot reference for a model.

    Accepts an int (absolute), ``"first"`` / ``"last"``, a percentage string
    like ``"40%"``, or a redshift spec like ``"z=1.5"`` / ``"z1.5"`` — so a
    story is portable across models with different snapshot counts/redshifts.
    A redshift is resolved to the **closest** snapshot via the model's redshift
    *table* (so it carries over to whatever box is loaded); without a table it
    falls back to the last snapshot.  Always clamped to ``[0, count-1]``.
    """
    last = max(0, int(count) - 1)
    if isinstance(value, str):
        z = _parse_redshift_spec(value)
        if z is not None:
            if table is not None and getattr(table, "count", 0) > 0:
                return max(0, min(last, int(table.z_to_snap(z))))
            return last
        v = value.strip().lower()
        if v == "last":
            return last
        if v == "first":
            return 0
        if v.endswith("%"):
            try:
                frac = float(v[:-1]) / 100.0
            except ValueError:
                return last
            return max(0, min(last, round(frac * last)))
        try:
            value = int(float(v))
        except ValueError:
            return last
    return max(0, min(last, int(value)))


class StoryPlayer:
    def __init__(self, server, scene) -> None:
        self._server = server
        self._scene = scene
        self._story: Story | None = None
        self._index = 0
        self._playing = False
        self._paused = (
            False  # True after pause() → next play() resumes in place
        )
        self._task: asyncio.Task | None = None
        self._saved: dict | None = None  # user state stashed on enter
        # Per-scene fly-through state. ``_ft_done`` holds scene indices whose
        # centre-approach intro has already played, and ``_ft_idx`` the current
        # target index per scene. Both are cleared when a scene is freshly
        # staged (apply_scene), so entering a fly-through scene always replays
        # the full sequence (reset → centre → clusters → groups), but are kept
        # across a pause/resume so Play simply continues the tour in place.
        self._ft_done: set[int] = set()
        self._ft_idx: dict[int, int] = {}
        # Per-scene snapshot_sweep frame index, so a pause/resume continues the
        # evolution in place instead of restarting from the first snapshot.
        self._sweep_k: dict[int, int] = {}
        # Cache of pre-rendered snapshot frame sequences (JPEG data-URLs), keyed
        # by (scene id, model, snapshot order), so a fly-through rewind or a
        # snapshot_sweep plays back smoothly off cached images and re-visits are
        # instant. Cleared on exit.
        self._frame_cache: dict = {}

    # ---- small helpers --------------------------------------------------

    @property
    def state(self):
        return self._server.state

    @property
    def ctrl(self):
        return self._server.controller

    def _push(self) -> None:
        if hasattr(self.ctrl, "view_update"):
            self.ctrl.view_update()

    def _render_push(self) -> None:
        """Render the plotter, THEN push — needed after data changes that don't
        themselves render (e.g. ``set_snapshot``), so ``view_update`` doesn't
        ship a stale frame (camera moves render via the motion helpers)."""
        try:
            self._scene.plotter.render()
        except Exception:
            pass
        self._push()

    def _start(self, coro) -> None:
        """Cancel any running task and start *coro*."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = asyncio.ensure_future(coro)

    # ---- HUD state ------------------------------------------------------

    def _push_hud(self) -> None:
        st = self.state
        if self._story is None:
            st.story_active = False
            st.flush()
            return
        sc = self._story.scenes[self._index]
        st.story_active = True
        st.story_playing = self._playing
        st.story_title = self._story.title
        st.story_scene_title = sc.title
        st.story_scene_caption = sc.caption
        st.story_scene_index = self._index + 1
        st.story_scene_count = len(self._story.scenes)
        st.flush()

    # ---- lifecycle ------------------------------------------------------

    def enter(self, story: Story) -> None:
        """Enter Story Mode: stash user state, preload sandbox, play scene 0."""
        if not story.scenes:
            return
        self._story = story
        self._index = 0
        self._playing = False
        self._save_user_state()
        # Suppress the per-box name/redshift labels for a clean presentation
        # view; restored on exit.
        if hasattr(self._scene, "set_labels_enabled"):
            self._scene.set_labels_enabled(False)
        self._start(self._enter_async(story))

    async def _enter_async(self, story: Story) -> None:
        try:
            # Hide the panel for the whole show up front, so the rewind
            # pre-render captures at the same window size the show uses (the
            # seamless hand-off depends on matching size).
            self.state.panels_hidden = True
            self.state.flush()
            await self._preload_sandbox(story)
            # Pre-render every pre-renderable motion (fly-through rewinds + any
            # snapshot_sweep flagged prerender) DURING loading — before the title
            # opens — so reaching those scenes plays back instantly and
            # seamlessly, and nothing churns on the title.
            await self._prerender_motions(story)
            self.state.playback_active = (
                False  # no overlay when the title opens
            )
            # A story opens at its first scene (typically a title slide).
            await self.apply_scene(0, transition=False)
            # Story-level autoplay: begin playback immediately so a title
            # scene's motion (e.g. a fly-through) runs without a Play click.
            if getattr(story, "autoplay", False):
                self._playing = True
                self._push_hud()
                await self._autoplay_from(0)
        except asyncio.CancelledError:
            pass

    def exit(self) -> None:
        """Leave Story Mode and restore the user's prior state."""
        self._playing = False
        self._story = None
        self.state.story_active = False
        self.state.story_playing = False
        self.state.story_overlays_json = "[]"
        # Drop any pre-rendered playback overlay + free the cached frames.
        self.state.playback_active = False
        self._frame_cache.clear()
        self.state.flush()
        # Restore the per-box labels that were suppressed on enter.
        if hasattr(self._scene, "set_labels_enabled"):
            self._scene.set_labels_enabled(True)
        # Restore (incl. async model switch-back) on a fresh task.
        self._start(self._exit_async())

    async def _exit_async(self) -> None:
        try:
            await self._restore_models()
            self._restore_user_state()
        except asyncio.CancelledError:
            pass

    # ---- transport ------------------------------------------------------

    def next(self) -> None:
        if self._story is None:
            return
        i = min(self._index + 1, len(self._story.scenes) - 1)
        # Advancing the show plays the target scene's motion, even if playback
        # was paused or had stopped at the end — otherwise a sweep/flythrough
        # sits frozen on its first frame. (Pause to stop; Play to resume here.)
        self._paused = False
        self._playing = True
        self._start(self._go(i, play=True))

    def prev(self) -> None:
        if self._story is None:
            return
        i = max(self._index - 1, 0)
        self._paused = False
        self._playing = True
        self._start(self._go(i, play=True))

    def play(self) -> None:
        if self._story is None:
            return
        if self._paused:
            # Resume in place: continue the current scene's motion WITHOUT
            # re-staging it (so a fly-through doesn't restart from the top),
            # and re-hide the panel per the scene's chrome.
            self._paused = False
            self._playing = True
            self._apply_chrome(self._story.scenes[self._index])
            # Mirror any visibility the user toggled while paused (e.g. galaxies
            # on the active box) onto every loaded box, so a multi-box scene
            # resumes with both boxes matching.
            self._propagate_layer_visibility(self._story.scenes[self._index])
            self.state.flush()
            self._push_hud()
            self._start(self._resume())
        else:
            self._playing = True
            self._push_hud()
            self._start(self._go(self._index, play=True))

    async def _resume(self) -> None:
        try:
            await self._autoplay_from(self._index)
        except asyncio.CancelledError:
            pass

    def pause(self) -> None:
        # Stop auto-advance, freeze motion, and hand full control back: show
        # the right panel again (even if the scene hid it for presentation).
        self._playing = False
        self._paused = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self.state.panels_hidden = False
        # Drop the rewind playback overlay if a pause lands mid-rewind.
        self.state.playback_active = False
        self.state.flush()
        self._push_hud()

    def goto(self, i: int) -> None:
        if self._story is None:
            return
        i = max(0, min(int(i), len(self._story.scenes) - 1))
        self._paused = False
        self._playing = True
        self._start(self._go(i, play=True))

    def goto_menu(self) -> None:
        """Jump to the scene that holds the scene-selector grid (if any)."""
        if self._story is None:
            return
        for idx, s in enumerate(self._story.scenes):
            if self._scene_has_menu(s):
                self.goto(idx)
                return

    # ---- async drivers --------------------------------------------------

    async def _go(self, i: int, *, play: bool) -> None:
        try:
            await self.apply_scene(i, transition=True)
            if play:
                await self._autoplay_from(i)
        except asyncio.CancelledError:
            pass

    async def _autoplay_from(self, i: int) -> None:
        n = len(self._story.scenes)
        while self._playing:
            sc = self._story.scenes[i]
            await self._run_motion(sc)
            if not self._playing:
                break
            # hold=True parks here (motion done, but _playing stays True) until
            # Next cancels this task — so nothing auto-advances off the scene,
            # yet Next still resumes playback on the following scene.
            while self._playing and sc.hold:
                await asyncio.sleep(0.1)
            if not self._playing:
                break
            if i + 1 >= n:
                self._playing = False
                self._push_hud()
                break
            i += 1
            await self.apply_scene(i, transition=True)

    # ---- scene application ----------------------------------------------

    async def apply_scene(self, i: int, *, transition: bool = True) -> None:
        scene = self._scene
        sc = self._story.scenes[i]
        self._index = i
        self._paused = False
        secs = (
            float(sc.transition.get("duration_secs", 0.0))
            if transition
            else 0.0
        )
        # Do NOT drop playback_active here — keep any pre-rendered overlay
        # visible while we stage the new scene (model switch, snapshot, camera).
        # Dropping it at the TOP leaves the stale live VTK view exposed until
        # _render_push() fires, causing a visible flash. We drop it at the
        # BOTTOM, after the new scene is fully rendered (see end of this method).
        #
        # For an instant cut with NO overlay already up, raise one now with a
        # freeze-frame of the current view: staging churns the live view (a
        # model switch pushes its own frames; snapshot and camera land at
        # different moments), and the cover turns all of that into a single
        # crossfade to the fully-staged scene. Animated transitions skip this —
        # the camera flight itself must stay visible.
        if (
            transition
            and secs <= 0.05
            and not getattr(self.state, "playback_active", False)
        ):
            frame = self._capture_live_frame()
            if frame:
                self.state.playback_frame = frame
                self.state.playback_active = True
                self.state.flush()
        self._sweep_k.pop(i, None)  # fresh staging → sweep starts from the top
        # Fresh staging restarts the fly-through from the top (reset → centre →
        # clusters → groups); pause/resume keeps these so Play continues in
        # place. So switching scenes/models always replays the full sequence,
        # while take-control/pause/play never interferes with it.
        self._ft_done.discard(i)
        self._ft_idx.pop(i, None)
        self._push_hud()

        # Model / multi-box layout first — it changes the active data.
        await self._apply_models(sc)
        # Data: snapshot (triggers filter re-apply via callbacks).
        self._apply_snapshot(sc)

        # Resolve the camera now (needs the model/box). For an INSTANT cut set
        # it BEFORE the flush, so the client never renders the new scene's data
        # under the previous camera — that mismatch is the next/back flicker.
        cam = scene.plotter.camera
        pos1, foc1, up1 = self._resolve_camera(sc)
        if secs <= 0.05:
            cam.position = tuple(pos1)
            cam.focal_point = tuple(foc1)
            cam.up = tuple(up1)

        # Apply all reactive state + focus/target, then flush ONCE so the client
        # re-renders a single time per scene (multiple flushes caused stutter).
        self._apply_flat_state(sc)
        self._propagate_layer_visibility(sc)
        self._apply_theme(sc)
        self._apply_chrome(sc)
        self._apply_overlays(sc)
        self._apply_focus(sc)
        self._apply_target(sc)
        self.state.flush()

        # An animated transition flies into the (already-applied) new scene.
        if secs > 0.05:
            await smooth_move(
                cam,
                np.asarray(cam.position, dtype=float),
                np.asarray(cam.focal_point, dtype=float),
                pos1,
                foc1,
                secs,
                _FPS,
                is_active=lambda: True,
                push=self._push,
            )

        # Render the fully-staged scene ONCE before pushing, so the client gets
        # the new frame in one shot instead of flickering through the old view.
        self._render_push()
        # Now drop any pre-rendered playback overlay from the previous scene.
        # Doing it HERE (after _render_push) rather than at the top of this
        # method means the overlay stays visible while we staged — no flash of a
        # stale live view. A one-iteration yield lets the view_update image
        # arrive at the client before the state flush drops the overlay, avoiding
        # a race where the overlay drops before the new frame is painted.
        if getattr(self.state, "playback_active", False):
            await asyncio.sleep(0)
        self.state.playback_active = False
        self.state.flush()
        # Lazily capture a thumbnail for the scene selector the first time a
        # scene is shown, so the menu grid fills in as the talk is navigated
        # (best-effort; the menu scene itself is skipped).
        self._maybe_capture_thumb(sc)

    # ---- symbolic resolution (portability across models) ----------------

    def _box(self) -> tuple[float, np.ndarray]:
        """Return (box_size, box_centre) of the active model."""
        bs = float(self._scene.active_model.box_size)
        c = bs / 2.0
        return bs, np.array([c, c, c], dtype=float)

    def _resolve_point(self, value) -> np.ndarray | None:
        """Resolve a point: ``"box"`` → box centre, list → array."""
        if value is None:
            return None
        if isinstance(value, str):
            if value.strip().lower() == "box":
                return self._box()[1]
            return None
        return np.asarray(value, dtype=float)

    def _frame_boxes(self, zoom: float = 1.0):
        """Frame all currently-loaded boxes (primary + adjacent).

        Box-size aware and multi-box aware, so the same ``"box"`` camera works
        whether one or several simulations are side-by-side. ``zoom`` > 1 pulls
        the camera further back (smaller box on screen, e.g. to clear a heading).
        """
        scene = self._scene
        boxes = [
            (
                np.asarray(scene.primary.offset, dtype=float),
                float(scene.primary.box_size),
            )
        ]
        for name in getattr(scene, "_adjacent_order", []) or []:
            m = scene._models.get(name)
            if m is not None:
                boxes.append(
                    (np.asarray(m.offset, dtype=float), float(m.box_size))
                )
        mins = np.array([min(o[i] for o, _ in boxes) for i in range(3)], float)
        maxs = np.array(
            [max(o[i] + bs for o, bs in boxes) for i in range(3)], float
        )
        center = (mins + maxs) / 2.0
        extent = float(np.max(maxs - mins))
        pos = np.array(
            [center[0], center[1], maxs[2] + extent * 1.2 * zoom], dtype=float
        )
        return pos, center, np.array(_UP, dtype=float)

    def _resolve_camera(self, sc):
        """Resolve a scene camera to (position, focal_point, up) arrays.

        ``sc.camera`` may be an explicit dict, or the string ``"box"`` /
        ``"reset"`` to frame all loaded boxes (size- and multi-box-aware).
        """
        cam = self._scene.plotter.camera
        spec = sc.camera
        if isinstance(spec, str):
            return self._frame_boxes()
        # Box framing with a pull-back factor: {"frame": "box", "zoom": 1.4}.
        if "frame" in spec:
            return self._frame_boxes(zoom=float(spec.get("zoom", 1.0)))
        pos = np.asarray(spec.get("position", cam.position), dtype=float)
        foc = np.asarray(spec.get("focal_point", cam.focal_point), dtype=float)
        up = np.asarray(spec.get("up", _UP), dtype=float)
        return pos, foc, up

    def _apply_snapshot(self, sc) -> None:
        scene = self._scene
        active = scene.active_model
        # Pass each model's own redshift table so a redshift spec ("z=1.5")
        # resolves to that box's closest snapshot — it carries over on a switch.
        snap = resolve_snap(sc.snap_num, active.snap_count, active.snap_table)
        if snap != scene.current_snap:
            scene.set_snapshot(snap)
        # Pre-position every other on-screen box at its own equivalent snapshot
        # so a multi-box scene doesn't flash the adjacent box at its default
        # frame before the sweep starts.
        for mdl in self._displayed_models():
            if mdl is active:
                continue
            mdl.set_snapshot(
                resolve_snap(sc.snap_num, mdl.snap_count, mdl.snap_table)
            )
            scene.refresh_label(mdl.name)

    def _apply_flat_state(self, sc) -> None:
        st = self.state
        if not sc.state:
            return
        for k, v in sc.state.items():
            setattr(st, k, deepcopy(v))
        st.dirty(*sc.state.keys())

    def _displayed_models(self) -> list:
        """Boxes actually on screen: the primary + any adjacent side-by-side
        boxes. Excludes models that are only PRELOADED into the scene (loaded
        hidden at the origin to warm their caches) — turning those visible
        would stack a second box directly on top of the primary.
        """
        scene = self._scene
        names = [
            scene.primary_name,
            *(getattr(scene, "_adjacent_order", []) or []),
        ]
        out: list = []
        for n in names:
            m = scene._models.get(n)
            if m is not None and m not in out:
                out.append(m)
        return out

    def _propagate_layer_visibility(self, sc) -> None:
        """Mirror halo/galaxy visibility across the on-screen boxes.

        The ``halos_visible`` / ``galaxies_visible`` state.change handlers route
        to the ACTIVE box only (``scene.halo_layer`` → ``active_model``), and a
        freshly added adjacent box turns *both* its layers on. So in a multi-box
        scene a halo-only state would still show galaxies in the second box —
        here we apply the scene's visibility to every DISPLAYED box for a
        uniform view (preloaded-but-hidden models are left alone).
        """
        models = self._displayed_models()
        if len(models) < 2:
            return
        st = self.state
        halos = bool(getattr(st, "halos_visible", True))
        gals = bool(getattr(st, "galaxies_visible", True))
        for m in models:
            m.halo_layer.visible = halos
            m.galaxy_layer.visible = gals

    def _apply_theme(self, sc) -> None:
        theme = sc.theme or (self._story.theme if self._story else None)
        if theme and getattr(self.state, "ui_theme", None) != theme:
            self.state.ui_theme = theme

    def _available_models(self) -> list[str]:
        """Names of all models the app can load (discovered + loaded)."""
        ml = getattr(self.state, "models_list", None) or []
        names = [
            m.get("name") for m in ml if isinstance(m, dict) and m.get("name")
        ]
        if names:
            return names
        return [m.name for m in self._scene.list_models()]

    def _resolve_model_ref(self, value, avail, initial, exclude):
        """Resolve a (possibly symbolic) model reference to a real name.

        ``"current"``/``"same"`` → the model loaded when the story started;
        ``"other"``/``"auto"``/``"any"`` → the first available model that isn't
        the current primary (or already chosen); anything else is a literal
        name.  Keeps stories portable — no hardcoded model names needed.
        """
        if value is None:
            return None
        v = str(value).strip().lower()
        if v in ("current", "same", "launched"):
            return initial
        if v in ("other", "auto", "any", "next"):
            for nm in avail:
                if nm != self._scene.primary_name and nm not in exclude:
                    return nm
            return None
        return value  # explicit name (as discovered, case-sensitive)

    async def _apply_models(self, sc) -> None:
        """Switch the primary model and adjacent boxes to match the scene.

        Supports adaptive refs (``current``/``other``/``auto``) so a portable
        story works without knowing the output's model names.  Reuses the
        existing async ``switch_model`` / ``toggle_adjacent`` controllers.
        """
        spec = sc.models
        if not spec:
            return
        scene = self._scene
        ctrl = self.ctrl
        avail = self._available_models()
        initial = (self._saved or {}).get("primary", scene.primary_name)

        if "primary" in spec and hasattr(ctrl, "switch_model"):
            primary = self._resolve_model_ref(
                spec.get("primary"), avail, initial, exclude=set()
            )
            if primary and primary != scene.primary_name:
                try:
                    await _maybe_await(ctrl.switch_model(primary))
                except Exception:
                    pass

        # Only touch adjacents when the scene explicitly mentions them.
        if "adjacent" in spec and hasattr(ctrl, "toggle_adjacent"):
            used = {scene.primary_name}
            wanted: list[str] = []
            for a in spec.get("adjacent") or []:
                r = self._resolve_model_ref(a, avail, initial, exclude=used)
                if r and r not in used:
                    wanted.append(r)
                    used.add(r)
            wanted_set = set(wanted)
            current = set(getattr(scene, "_adjacent_order", []) or [])
            for name in wanted_set - current:
                try:
                    await _maybe_await(ctrl.toggle_adjacent(name))
                except Exception:
                    pass
            for name in current - wanted_set:
                try:
                    await _maybe_await(ctrl.toggle_adjacent(name))
                except Exception:
                    pass

        # Background-warm every loaded box's snapshots. Only the primary does
        # this at scene-init; adjacent boxes would otherwise load on demand and
        # stutter the first sweep. preload_all() is idempotent (skips in-flight
        # snaps), so this is cheap to call on every scene.
        for mdl in scene.list_models():
            loader = getattr(mdl, "loader", None)
            if loader is not None and hasattr(loader, "preload_all"):
                try:
                    loader.preload_all()
                except Exception:
                    pass

    def _apply_chrome(self, sc) -> None:
        self.state.panels_hidden = bool(
            (sc.chrome or {}).get("hide_panel", False)
        )

    def _apply_overlays(self, sc) -> None:
        # Ship overlays as JSON for the client to render OUTSIDE Vue's control
        # (visage.js builds the DOM + runs KaTeX). Rendering them via Vue
        # would let KaTeX's DOM mutations corrupt Vue's virtual DOM.
        items = []
        for o in sc.overlays or []:
            if o.get("kind") == "scene_menu":
                # Auto-expanded into a clickable grid of the story's scenes;
                # the client renders the cells and each one jumps via goto.
                items.append(self._build_scene_menu(o, sc.id))
            else:
                items.append(_normalize_overlay(o))
        self.state.story_overlays_json = json.dumps(items)

    # ---- scene-selector grid + thumbnails -------------------------------

    def _thumbs_dir(self) -> Path:
        """Folder holding captured scene thumbnails (served at /sage_static/)."""
        return (
            Path(__file__).resolve().parent.parent / "static" / "story_thumbs"
        )

    def _story_slug(self) -> str:
        """Stable per-story prefix for thumbnail filenames."""
        sp = getattr(self._story, "source_path", None) if self._story else None
        if sp:
            return Path(sp).stem
        title = (self._story.title if self._story else "") or "story"
        return title.lower().replace(" ", "_")

    def _thumb_file(self, scene) -> Path:
        return self._thumbs_dir() / f"{self._story_slug()}__{scene.id}.png"

    def _thumb_src(self, scene) -> str:
        """Served URL for a scene's thumbnail, or '' if not captured yet."""
        f = self._thumb_file(scene)
        return f"/sage_static/story_thumbs/{f.name}" if f.exists() else ""

    def _build_scene_menu(self, item: dict, current_id: str) -> dict:
        """Expand a ``{"kind":"scene_menu"}`` overlay into a grid spec.

        Lists every scene except the menu scene itself (and, unless
        ``include_cards`` is true, the ``card-*`` divider scenes). Each cell
        carries its scene index (for goto), a 1-based number, a label, and a
        thumbnail URL when one has been captured.
        """
        scenes = self._story.scenes if self._story else []
        include_cards = bool(item.get("include_cards", False))
        cells = []
        for i, s in enumerate(scenes):
            if s.id == current_id:
                continue
            if not include_cards and str(s.id).startswith("card-"):
                continue
            cells.append(
                {
                    "index": i,
                    "n": i + 1,
                    "label": s.title or s.id or f"Scene {i + 1}",
                    "thumb": self._thumb_src(s),
                }
            )
        anchor = item.get("anchor", "center")
        style = (
            _overlay_position_style(anchor, item.get("x", 0), item.get("y", 0))
            + "pointer-events:none;"
        )
        return {
            "menu": True,
            "cols": int(item.get("cols", 4)),
            "title": item.get("title", ""),
            "max_width": float(item.get("max_width", 90)),
            "cells": cells,
            "style": style,
        }

    def _capture_image(self):
        """Grab the current render-window image as an (H, W, 3) uint8 array.

        Uses ``vtkWindowToImageFilter`` directly because the remote-view plotter
        is never ``.show()``n, so pyvista's ``screenshot()`` refuses to run.
        Returns ``None`` if capture fails.
        """
        try:
            from vtkmodules.util.numpy_support import vtk_to_numpy
            from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

            rw = self._scene.plotter.ren_win
            rw.Render()
            w2if = vtkWindowToImageFilter()
            w2if.SetInput(rw)
            w2if.SetInputBufferTypeToRGB()
            w2if.ReadFrontBufferOff()
            w2if.Update()
            vimg = w2if.GetOutput()
            w, h, _ = vimg.GetDimensions()
            arr = vtk_to_numpy(vimg.GetPointData().GetScalars()).reshape(
                h, w, -1
            )
            return arr[::-1].copy()  # VTK image origin is bottom-left
        except Exception:
            return None

    @staticmethod
    def _encode_frame(arr) -> str:
        """JPEG data-URL for a captured (H, W, 3) frame.

        Full quality so an overlay↔live hand-off (both at quality 100) is
        imperceptible.
        """
        import base64
        import io as _io

        from PIL import Image

        buf = _io.BytesIO()
        Image.fromarray(arr[:, :, :3], "RGB").save(buf, "JPEG", quality=100)
        return "data:image/jpeg;base64," + base64.b64encode(
            buf.getvalue()
        ).decode("ascii")

    def _capture_live_frame(self) -> str | None:
        """Freeze-frame the current render window as a JPEG data-URL.

        Used to cover instant scene cuts: the frame matches what the client is
        showing, so raising the playback overlay with it is invisible.
        Captured off-screen for the same reason as ``_save_thumb`` (the
        on-screen buffer reads back black on the remote-view setup).
        Best-effort — returns ``None`` on failure so the caller falls back to
        the plain cut.
        """
        try:
            rw = self._scene.plotter.ren_win
            prev_off = rw.GetOffScreenRendering()
            rw.SetOffScreenRendering(1)
            try:
                arr = self._capture_image()
            finally:
                rw.SetOffScreenRendering(prev_off)
            if arr is None:
                return None
            return self._encode_frame(arr)
        except Exception:
            return None

    @staticmethod
    def _scene_has_menu(scene) -> bool:
        return any(
            (o or {}).get("kind") == "scene_menu"
            for o in (scene.overlays or [])
        )

    def _save_thumb(self, scene, *, width: int = 360) -> bool:
        """Screenshot the current render window into the scene's thumbnail PNG.

        Returns True on success. Best-effort: never raises (capture/encode
        failures just return False so playback is never interrupted).
        """
        try:
            from PIL import Image

            # Capture off-screen — the on-screen/back buffer reads back black on
            # the remote-view setup (same reason the rewind pre-render does this).
            rw = self._scene.plotter.ren_win
            prev_off = rw.GetOffScreenRendering()
            rw.SetOffScreenRendering(1)
            try:
                arr = self._capture_image()
            finally:
                rw.SetOffScreenRendering(prev_off)
            if arr is None:
                return False
            img = Image.fromarray(arr[:, :, :3], "RGB")
            w, h = img.size
            if w > width:
                img = img.resize((width, max(1, round(h * width / w))))
            self._thumbs_dir().mkdir(parents=True, exist_ok=True)
            img.save(str(self._thumb_file(scene)), "PNG")
            return True
        except Exception:
            return False

    def _maybe_capture_thumb(self, scene) -> None:
        """Capture a thumbnail the first time a scene is shown (lazy fill).

        Skips the scene-selector scene itself and anything already captured, so
        the menu grid populates automatically as the talk is navigated.
        """
        if self._story is None or self._scene_has_menu(scene):
            return
        if self._thumb_file(scene).exists():
            return
        self._save_thumb(scene)

    async def capture_thumbnails(self, *, width: int = 360) -> None:
        """Walk every scene, stage it, and (re)save its thumbnail.

        Run from the Story Mode menu → "Capture thumbnails" to refresh the whole
        set at once; normal navigation also fills thumbnails in lazily via
        ``_maybe_capture_thumb``.
        """
        if self._story is None:
            return
        self.pause()  # stop any auto-advance/motion before stepping scenes
        start = self._index
        for i, s in enumerate(self._story.scenes):
            if self._scene_has_menu(s):
                continue
            await self.apply_scene(i, transition=False)
            await asyncio.sleep(0.4)  # let the staged scene render server-side
            self._save_thumb(s, width=width)
        # Return to where the author was, refreshing the menu so new thumbs show.
        await self.apply_scene(start, transition=False)
        self.state.flush()

    def _apply_focus(self, sc) -> None:
        scene = self._scene
        st = self.state
        f = sc.focus or {"kind": "none"}
        kind = f.get("kind", "none")
        if kind == "sphere":
            center = self._resolve_point(f.get("center"))
            if center is None:
                center = self._box()[1]  # default to box centre
            if f.get("radius") is not None:
                radius = float(f["radius"])
            else:  # radius_frac → fraction of the box size (portable)
                radius = float(f.get("radius_frac", 0.4)) * self._box()[0]
            scene.set_focus_sphere(tuple(center), radius)
            st.focus_active = True
        elif kind == "box":
            scene.set_focus_box(*[float(x) for x in f["bounds"]])
            st.focus_active = True
        else:
            scene.clear_focus()
            st.focus_active = False

    def _apply_target(self, sc) -> None:
        if not sc.target:
            return
        idx = self._resolve_target(sc.target)
        if idx is None:
            return
        self.state.nav_gal_idx = int(idx)
        if sc.target.get("highlight_group") and hasattr(
            self.ctrl, "highlight_group_members"
        ):
            self.ctrl.highlight_group_members()

    def _resolve_target(self, target: dict) -> int | None:
        """Resolve a target to a galaxy index in the current snapshot.

        Order: exact GalaxyIndex match → nearest position within radius →
        None (caller falls back to focus geometry only).
        """
        scene = self._scene
        model = scene.active_model
        _, galaxies = model.loader.get(scene.current_snap)
        if galaxies.count == 0:
            return None

        gi = target.get("galaxy_index")
        if gi is not None:
            hits = np.where(galaxies.galaxy_id == int(gi))[0]
            if len(hits):
                return int(hits[0])

        pos = target.get("position")
        if pos is None:
            return None
        off = np.asarray(model.offset, dtype=float)
        world = np.asarray(galaxies.positions, dtype=float) + off
        d = np.linalg.norm(world - np.asarray(pos, dtype=float), axis=1)
        j = int(np.argmin(d))
        radius = float(target.get("radius", np.inf))
        return j if d[j] <= radius else None

    # ---- motion ---------------------------------------------------------

    async def _run_motion(self, sc) -> None:
        m = sc.motion or {"kind": "still"}
        kind = m.get("kind", "still")
        if kind == "orbit":
            await self._motion_orbit(sc, m)
        elif kind == "snapshot_sweep":
            await self._motion_snapshot_sweep(sc, m)
        elif kind == "flythrough":
            await self._motion_flythrough(sc, m)
        else:
            await self._dwell(sc.dwell_secs)

    async def _dwell(self, secs: float) -> None:
        end = asyncio.get_event_loop().time() + max(0.0, float(secs))
        while self._playing and asyncio.get_event_loop().time() < end:
            await asyncio.sleep(0.1)

    async def _motion_orbit(self, sc, m) -> None:
        center = self._motion_center(sc)
        if center is None:
            await self._dwell(sc.dwell_secs)
            return
        cam = self._scene.plotter.camera
        radius = float(
            m.get(
                "radius",
                np.linalg.norm(np.asarray(cam.position, dtype=float) - center),
            )
        )
        await orbit_around(
            cam,
            center,
            radius,
            float(m.get("degrees", 360.0)),
            float(m.get("dps", 10.0)),
            _FPS,
            is_active=lambda: self._playing,
            push=self._push,
        )

    def _motion_center(self, sc) -> np.ndarray | None:
        if sc.target and sc.target.get("position"):
            return self._resolve_point(sc.target["position"])
        f = sc.focus or {}
        if f.get("kind") == "sphere":
            center = self._resolve_point(f.get("center"))
            return center if center is not None else self._box()[1]
        return None

    def _flythrough_targets(self):
        """(groups, clusters) world positions for the current snapshot.

        Groups (10^12.5 ≤ Mvir < 10^14) and clusters (Mvir ≥ 10^14), each
        sorted most-massive first — the same thresholds the toolbar
        fly-through uses.
        """
        scene = self._scene
        halos, _gal = scene.active_model.loader.get(scene.current_snap)
        if getattr(halos, "count", 0) <= 0:
            return [], []
        masses = np.asarray(halos.masses, dtype=float)
        log_m = np.log10(np.maximum(masses, 1.0))
        h_pos = np.asarray(halos.positions, dtype=float) + np.asarray(
            scene.active_model.offset, dtype=float
        )
        g_idx = np.where((log_m >= 12.5) & (log_m < 14.0))[0]
        g_idx = g_idx[np.argsort(masses[g_idx])[::-1]]
        c_idx = np.where(log_m >= 14.0)[0]
        c_idx = c_idx[np.argsort(masses[c_idx])[::-1]]
        return [h_pos[i] for i in g_idx], [h_pos[i] for i in c_idx]

    def _ffb_galaxy_targets(self):
        """World positions of FFB-regime galaxies (``ffb_regime != 0``) for the
        current snapshot, most-massive (stellar mass) first."""
        scene = self._scene
        _halos, gals = scene.active_model.loader.get(scene.current_snap)
        flag = getattr(gals, "ffb_regime", None)
        pos = getattr(gals, "positions", None)
        if flag is None or pos is None:
            return []
        ffb = np.asarray(flag) != 0
        if not np.any(ffb):
            return []
        idx = np.where(ffb)[0]
        sm = np.asarray(gals.stellar_mass, dtype=float)[idx]
        idx = idx[np.argsort(sm)[::-1]]
        world = np.asarray(pos, dtype=float) + np.asarray(
            scene.active_model.offset, dtype=float
        )
        return [world[i] for i in idx]

    async def _capture_snapshot_sequence(
        self, sc, lead, order, *, show_overlay
    ):
        """Render an ordered list of snapshots to a cached JPEG sequence.

        One frame per entry in ``order`` (snapshot indices), rendered ONCE
        off-screen at the live render-window size (so cached frames match the
        in-show view — seamless). Cached per (scene, model, order); a cache hit
        returns at once. Returns the frame list, or ``None`` if cancelled
        mid-render. Requires the scene's model + camera staged by the caller and
        ``self._playing`` True (so ``_warm_sweep`` runs). ``show_overlay`` raises
        the playback overlay over the live view while rendering.
        """
        scene = self._scene
        st = self.state
        key = (sc.id, lead.name, tuple(order))
        if key in self._frame_cache:
            return self._frame_cache[key]
        if not order:
            self._frame_cache[key] = []
            return []

        await self._warm_sweep([(lead, min(order), max(order))])
        frames: list[str] = []
        rw = scene.plotter.ren_win
        prev_off = rw.GetOffScreenRendering()
        rw.SetOffScreenRendering(1)  # read-back needs the off-screen FBO
        # One warm-up render after switching context so points_gaussian shaders
        # compile in the off-screen FBO before we start capturing frames.
        rw.Render()
        try:
            for k, s in enumerate(order):
                if not self._playing:
                    return None  # cancelled mid-render
                scene.set_snapshot(int(s))
                arr = self._capture_image()
                if arr is None:
                    continue
                frames.append(self._encode_frame(arr))
                if show_overlay and k == 0:  # cover the live view ASAP
                    st.playback_frame = frames[0]
                    st.playback_active = True
                st.preload_status = (
                    f"Pre-rendering z-evolution…  {k + 1}/{len(order)}"
                )
                st.flush()
                await asyncio.sleep(0)
        finally:
            rw.SetOffScreenRendering(prev_off)
            st.preload_status = ""
        if not frames:
            # All captures returned None — don't cache so a retry is possible
            # (e.g. if the render window wasn't settled during load).
            return None
        self._frame_cache[key] = frames
        return frames

    async def _ensure_rewind_frames(self, sc, rewind_to, *, show_overlay):
        """Render the rewind range to a cached JPEG sequence (one per snapshot).

        Returns ``(frames, start, end)`` — ``frames`` is ``None`` if cancelled.
        Delegates the capture/cache to ``_capture_snapshot_sequence``.
        """
        scene = self._scene
        if scene.active_box_name != scene.primary_name:
            scene.set_active_box(scene.primary_name)
        lead = scene.primary
        start = scene.current_snap
        end = resolve_snap(rewind_to, lead.snap_count, lead.snap_table)
        if end == start:
            return [], start, end
        step = -1 if end < start else 1
        order = list(range(start, end + step, step))
        frames = await self._capture_snapshot_sequence(
            sc, lead, order, show_overlay=show_overlay
        )
        return frames, start, end

    async def _flythrough_rewind(self, sc, rewind_to, fps: float) -> None:
        """Play the (pre-rendered, cached) snapshot rewind back at ``fps``.

        A fly-through pre-step: the scene is staged at ``snap_num`` (e.g. z=0);
        this plays the cached image sequence up to ``rewind_to`` (e.g. z=1.5)
        through the playback overlay — smooth and high-res, decoupled from live
        remote-render throughput. Frames are normally pre-rendered up front (see
        ``_prerender_motions``); a cache miss renders them here behind the
        overlay. The hand-off back to live is seamless: the live view is set to
        the final snapshot (same box camera) and rendered BEFORE the overlay is
        dropped, so it matches the last shown frame exactly.
        """
        st = self.state
        scene = self._scene
        frames, start, end = await self._ensure_rewind_frames(
            sc, rewind_to, show_overlay=True
        )
        if frames is None:  # cancelled during render
            st.playback_active = False
            st.flush()
            return
        if start == end or not frames:
            st.playback_active = False
            st.flush()
            return

        # Ensure the overlay is up (cache-hit path skips the render above).
        st.playback_frame = frames[0]
        st.playback_active = True
        st.flush()

        # Playback pass — flip the cached frames. The per-frame state stream
        # can only push so fast; above ~30 fps the client coalesces updates and
        # you see a "flash" from the first frame to the last. So cap the DISPLAY
        # rate at 30 fps and honour any higher rewind_fps as a frame-skip
        # "speed" (e.g. 60 → 30 fps × step 2 = 2× speed, still smooth).
        display_fps = min(float(fps), 30.0)
        speed = max(1, int(round(float(fps) / display_fps)))
        interval = 1.0 / display_fps
        i = 0
        n = len(frames)
        while i < n:
            if not self._playing:
                break
            st.playback_frame = frames[i]
            st.flush()
            await asyncio.sleep(interval)
            i += speed

        # Seamless hand-off: render the LIVE view at the final snapshot (same box
        # camera as the recording) BEFORE dropping the overlay. A one-iteration
        # yield lets the view_update image reach the client before the state
        # flush clears the overlay, preventing a race-condition flash.
        scene.set_snapshot(int(end))
        self._render_push()
        await asyncio.sleep(0)
        st.playback_active = False
        st.flush()

    async def _prerender_motions(self, story) -> None:
        """Pre-render every pre-renderable motion up front (during load), so
        reaching those scenes plays back instantly and seamlessly.

        Covers fly-through **rewinds** (``rewind_to``) and **snapshot_sweep**
        scenes flagged ``"prerender": true``. Stages each scene's
        model/snapshot/state/camera and fills the frame cache off-screen at the
        in-show render-window size. Called during the load (after the panel is
        hidden, before the opening scene is applied); the caller applies the
        opening scene afterwards.
        """
        jobs = []
        for sc in story.scenes:
            m = sc.motion or {}
            kind = m.get("kind")
            if kind == "flythrough" and m.get("rewind_to") is not None:
                jobs.append(("rewind", sc))
            elif kind == "snapshot_sweep" and m.get("prerender"):
                jobs.append(("sweep", sc))
        if not jobs:
            return
        # Let the render window settle to the (already-set) panel-hidden size.
        await asyncio.sleep(0.3)
        was_playing = self._playing
        self._playing = True  # so _warm_sweep + capture run during the load
        try:
            for kind, sc in jobs:
                await self._apply_models(sc)
                self._apply_snapshot(sc)
                self._apply_flat_state(sc)
                self._propagate_layer_visibility(sc)
                cam = self._scene.plotter.camera
                pos1, foc1, up1 = self._resolve_camera(sc)
                cam.position = tuple(pos1)
                cam.focal_point = tuple(foc1)
                cam.up = tuple(up1)
                if kind == "rewind":
                    await self._ensure_rewind_frames(
                        sc, sc.motion.get("rewind_to"), show_overlay=False
                    )
                else:  # sweep
                    lead = self._scene.primary
                    await self._capture_snapshot_sequence(
                        sc,
                        lead,
                        self._sweep_order(sc, lead),
                        show_overlay=False,
                    )
        finally:
            self._playing = was_playing

    async def _motion_flythrough_normal(self, sc, m) -> None:
        """Normal-mode (toolbar) fly-through, for use as a calm background.

        Mirrors ``toolbar._flythrough_loop``: reset → approach the box centre →
        most-massive group (spin) → every cluster (focus + spin) → return to a
        box-orbit standoff → **continuous gentle box orbit forever** (until
        Next). The intro plays only on a fresh staging; a pause/resume continues
        the box orbit from the current camera. Uses the shared ``camera_motion``
        helpers (so ``toolbar.py`` is untouched). Honours ``self._playing``.
        """
        scene = self._scene
        st = self.state
        cam = scene.plotter.camera
        active = lambda: self._playing  # noqa: E731
        fps = _FPS
        interval = 1.0 / fps
        bs, centre = self._box()
        cx, cy, cz = float(centre[0]), float(centre[1]), float(centre[2])
        orbit_r = bs * 1.7
        approach_secs = float(m.get("approach_secs", 10.0))
        box_dps = float(m.get("box_dps", 8.0))
        g_radius = float(m.get("group_radius", 15.0))
        c_radius = float(m.get("cluster_radius", 30.0))
        g_dps = float(m.get("group_dps", 10.0))
        c_dps = float(m.get("cluster_dps", 8.0))

        async def fly_to(target, radius, secs):
            t3 = np.asarray(target, dtype=float)
            dest = orbit_start_position(cam, t3, radius)
            return await smooth_move(
                cam,
                np.asarray(cam.position, dtype=float),
                np.asarray(cam.focal_point, dtype=float),
                dest,
                t3,
                secs,
                fps,
                is_active=active,
                push=self._push,
            )

        async def spin(target, radius, dps):
            return await orbit_around(
                cam,
                np.asarray(target, dtype=float),
                radius,
                360.0,
                dps,
                fps,
                is_active=active,
                push=self._push,
            )

        idx = self._index
        fresh = idx not in self._ft_done
        self._ft_done.add(idx)
        groups, clusters = self._flythrough_targets()
        try:
            if fresh:
                # Reset → approach the box centre (focal just past centre so the
                # final frame isn't a degenerate camera).
                cam.position = (cx, cy, bs * 2.2)
                cam.focal_point = (cx, cy, cz)
                cam.up = _UP
                self._render_push()
                await asyncio.sleep(interval)
                if not await smooth_move(
                    cam,
                    np.array([cx, cy, bs * 2.2]),
                    np.array([cx, cy, cz]),
                    np.array([cx, cy, cz]),
                    np.array([cx, cy, cz - 0.5]),
                    approach_secs,
                    fps,
                    is_active=active,
                    push=self._push,
                ):
                    return
                # Most-massive group.
                if groups:
                    if not await fly_to(groups[0], g_radius, 8.0):
                        return
                    if not await spin(groups[0], g_radius, g_dps):
                        return
                # Every cluster, most → least massive, with focus.
                for cpos in clusters:
                    if not await fly_to(cpos, c_radius, 10.0):
                        return
                    scene.set_focus_sphere(
                        tuple(float(v) for v in cpos), c_radius
                    )
                    st.focus_active = True
                    st.flush()
                    self._render_push()
                    await asyncio.sleep(interval)
                    ok = active() and await spin(cpos, c_radius, c_dps)
                    scene.clear_focus()
                    st.focus_active = False
                    st.flush()
                    self._render_push()
                    if not ok:
                        return
                # Return to a box-orbit standoff (shortest fly-back).
                diff = np.asarray(cam.position, dtype=float) - np.array(
                    [cx, cy, cz]
                )
                diff[1] = 0.0
                theta = (
                    float(np.arctan2(diff[0], diff[2]))
                    if np.linalg.norm(diff) > 1e-6
                    else 0.0
                )
                rtn = np.array(
                    [
                        cx + orbit_r * np.sin(theta),
                        cy,
                        cz + orbit_r * np.cos(theta),
                    ]
                )
                if not await smooth_move(
                    cam,
                    np.asarray(cam.position, dtype=float),
                    np.asarray(cam.focal_point, dtype=float),
                    rtn,
                    np.array([cx, cy, cz]),
                    10.0,
                    fps,
                    is_active=active,
                    push=self._push,
                ):
                    return

            # Continuous gentle box orbit forever (resume continues from here).
            diff = np.asarray(cam.position, dtype=float) - np.array(
                [cx, cy, cz]
            )
            diff[1] = 0.0
            theta = (
                float(np.arctan2(diff[0], diff[2]))
                if np.linalg.norm(diff) > 1e-6
                else 0.0
            )
            pacer = FramePacer(fps)
            theta0 = theta
            while active():
                theta = theta0 + np.deg2rad(box_dps * pacer.elapsed())
                cam.position = (
                    cx + orbit_r * np.sin(theta),
                    cy,
                    cz + orbit_r * np.cos(theta),
                )
                cam.focal_point = (cx, cy, cz)
                cam.up = _UP
                self._push()
                await pacer.wait()
        finally:
            if getattr(st, "focus_active", False):
                scene.clear_focus()
                st.focus_active = False
                st.flush()

    async def _motion_flythrough(self, sc, m) -> None:
        """Cinematic fly-through — the full sequence every time it is staged.

        On a **fresh** start (every time a fly-through scene is staged via
        next/prev/goto/enter, including a model switch): reset the camera, fly
        into the box centre, then — repeated until Next — one uniform cycle per
        target (clusters first, then groups, most-massive first): fly **in**
        (search) → raise a **focus** ring → **orbit** it (rotate) → drop the
        ring and go to the **next**. There is no settling box orbit at the end.

        Only a **pause/resume** is exempt: Play after Pause re-enters here for
        the same scene WITHOUT re-staging, so ``_ft_done`` / ``_ft_idx`` are
        intact and the tour simply continues in place (the intro is skipped) —
        so taking control then resuming never interferes with the fly-through.
        Driven by the shared ``camera_motion`` helpers (the same ones the
        toolbar uses). Honours ``self._playing``.
        """
        # The normal-mode (toolbar) fly-through settles into a gentle box orbit
        # — used e.g. as the scene-selector background. Dispatch to it.
        if str(m.get("style", "")).lower() == "normal":
            await self._motion_flythrough_normal(sc, m)
            return

        scene = self._scene
        st = self.state
        cam = scene.plotter.camera
        active = lambda: self._playing  # noqa: E731

        fps = _FPS
        approach_secs = float(m.get("approach_secs", 8.0))
        fly_secs = float(m.get("fly_secs", 7.0))
        g_radius = float(m.get("group_radius", 15.0))
        c_radius = float(m.get("cluster_radius", 30.0))
        g_dps = float(m.get("group_dps", 10.0))
        c_dps = float(m.get("cluster_dps", 8.0))
        gal_radius = float(m.get("galaxy_radius", 6.0))
        gal_dps = float(m.get("galaxy_dps", 14.0))
        spin_degrees = float(m.get("spin_degrees", 180.0))  # orbit per target
        target_kind = str(m.get("targets", "halos")).lower()

        async def fly_to(target, radius, secs):
            t3 = np.asarray(target, dtype=float)
            dest = orbit_start_position(cam, t3, radius)
            return await smooth_move(
                cam,
                np.asarray(cam.position, dtype=float),
                np.asarray(cam.focal_point, dtype=float),
                dest,
                t3,
                secs,
                fps,
                is_active=active,
                push=self._push,
            )

        async def spin(target, radius, dps):
            return await orbit_around(
                cam,
                np.asarray(target, dtype=float),
                radius,
                spin_degrees,
                dps,
                fps,
                is_active=active,
                push=self._push,
            )

        # Fresh staging (not a pause/resume) → play the centre-approach intro
        # and restart the cursor. apply_scene clears _ft_done/_ft_idx for the
        # scene on every fresh staging, so this replays the full sequence each
        # time; only a pause/resume keeps them, continuing the tour in place.
        idx = self._index
        fresh = idx not in self._ft_done
        self._ft_done.add(idx)

        try:
            if fresh:
                self._ft_idx[idx] = 0
                # Optional snapshot rewind first: the scene is staged at snap_num
                # (e.g. z=0), then stepped to rewind_to (e.g. z=1.5) before the
                # tour, so the box "rewinds" into the tour epoch.
                rewind_to = m.get("rewind_to")
                if rewind_to is not None:
                    await self._flythrough_rewind(
                        sc, rewind_to, float(m.get("rewind_fps", 4.0))
                    )
                    if not active():
                        return
                # Into the box: reset to a pulled-back view, then approach centre.
                bs, centre = self._box()
                cx, cy, cz = (
                    float(centre[0]),
                    float(centre[1]),
                    float(centre[2]),
                )
                cam.position = (cx, cy, bs * 2.2)
                cam.focal_point = (cx, cy, cz)
                cam.up = _UP
                self._render_push()
                await asyncio.sleep(1.0 / fps)
                if not await smooth_move(
                    cam,
                    np.array([cx, cy, bs * 2.2]),
                    np.array([cx, cy, cz]),
                    np.array([cx, cy, cz]),
                    np.array([cx, cy, cz - 0.5]),
                    approach_secs,
                    fps,
                    is_active=active,
                    push=self._push,
                ):
                    return

            # Build the target list AFTER any rewind, so it reflects the current
            # snapshot. Default = halo clusters first (most massive), then groups;
            # targets:"ffb" tours FFB-regime galaxies (most massive first). Each
            # target is visited with the identical search → focus → rotate → next.
            if target_kind in ("ffb", "ffb_galaxies", "galaxies"):
                targets = [
                    (p, gal_radius, gal_dps)
                    for p in self._ffb_galaxy_targets()
                ]
            else:
                groups, clusters = self._flythrough_targets()
                targets = [(c, c_radius, c_dps) for c in clusters] + [
                    (g, g_radius, g_dps) for g in groups
                ]

            if not targets:
                # Empty box: hold the staged view until Next (no box orbit).
                while active():
                    await asyncio.sleep(0.1)
                return
            # Continue from this scene's cursor (resume in place after a pause).
            i = self._ft_idx.get(idx, 0) % len(targets)
            while active():
                self._ft_idx[idx] = i  # checkpoint before the awaits
                pos, radius, dps = targets[i]
                # search: fly toward the structure.
                if not await fly_to(pos, radius, fly_secs):
                    return
                # focus: raise the ring on it.
                scene.set_focus_sphere(tuple(float(v) for v in pos), radius)
                st.focus_active = True
                st.flush()
                self._render_push()
                await asyncio.sleep(1.0 / fps)
                # rotate: orbit the structure.
                ok = active() and await spin(pos, radius, dps)
                # next: drop the focus ring and advance to the next structure.
                scene.clear_focus()
                st.focus_active = False
                st.flush()
                self._render_push()
                if not ok:
                    return
                i = (i + 1) % len(targets)
        finally:
            # Never leave a focus mask behind when the scene changes/pauses.
            if getattr(st, "focus_active", False):
                scene.clear_focus()
                st.focus_active = False
                st.flush()

    def _sweep_order(self, sc, lead) -> list[int]:
        """Ordered snapshot indices for a sweep scene's [from, to] range."""
        m = sc.motion or {}
        lo = resolve_snap(
            m.get("from", sc.snap_num), lead.snap_count, lead.snap_table
        )
        hi = resolve_snap(
            m.get("to", sc.snap_num), lead.snap_count, lead.snap_table
        )
        step = 1 if hi >= lo else -1
        return list(range(lo, hi + step, step))

    async def _sweep_playback(self, sc, lead, fps: float, loop: bool) -> None:
        """Play a pre-rendered snapshot_sweep back through the playback overlay.

        Frames (one per snapshot in [from, to]) are normally pre-rendered up
        front; a cache miss renders them here behind the overlay. Plays at a
        display rate capped to 30 fps, honouring higher ``fps`` as a frame-skip
        speed (same as the rewind). Loops until Next/Pause when ``loop`` (those
        cancel the task; `pause`/`apply_scene` drop the overlay). A pause/resume
        continues in place via ``_sweep_k``.
        """
        st = self.state
        scene = self._scene
        order = self._sweep_order(sc, lead)
        frames = await self._capture_snapshot_sequence(
            sc, lead, order, show_overlay=True
        )
        if not frames:  # None (cancelled) or empty
            st.playback_active = False
            st.flush()
            return
        n = len(frames)
        display_fps = min(float(fps), 30.0)
        speed = max(1, int(round(float(fps) / display_fps)))
        interval = 1.0 / display_fps
        i = self._sweep_k.get(self._index, 0)
        if i >= n:
            i = 0
        st.playback_frame = frames[i]
        st.playback_active = True
        st.flush()
        while self._playing:
            while i < n:
                if not self._playing:
                    break
                self._sweep_k[self._index] = i
                st.playback_frame = frames[i]
                st.flush()
                await asyncio.sleep(interval)
                i += speed
            i = 0
            self._sweep_k[self._index] = 0
            if not loop:
                break
        # loop=False ends naturally → land the live view on the final snapshot
        # and drop the overlay (loop=True is ended by Next/Pause, which drop it).
        if not loop and self._playing:
            scene.set_snapshot(int(order[-1]))
            self._render_push()
            await asyncio.sleep(0)
            st.playback_active = False
            st.flush()

    async def _motion_snapshot_sweep(self, sc, m) -> None:
        scene = self._scene
        # Lead the sweep with the PRIMARY box so it always steps one snapshot
        # per frame at the intended rate — independent of which box happens to
        # be UI-active (clicking an adjacent box must not change the cadence).
        if scene.active_box_name != scene.primary_name:
            scene.set_active_box(scene.primary_name)
        lead = scene.primary
        # Pre-rendered path: play cached frames back smoothly. Single box only —
        # a pre-rendered image can't independently step adjacent boxes, so fall
        # back to the live sweep when side-by-side boxes are shown.
        if m.get("prerender") and len(self._displayed_models()) <= 1:
            await self._sweep_playback(
                sc, lead, float(m.get("fps", 4.0)), bool(m.get("loop", False))
            )
            return
        from_spec = m.get("from", sc.snap_num)
        to_spec = m.get("to", sc.snap_num)
        lo = resolve_snap(from_spec, lead.snap_count, lead.snap_table)
        hi = resolve_snap(to_spec, lead.snap_count, lead.snap_table)
        fps = float(m.get("fps", 4.0))
        loop = bool(m.get("loop", False))
        # Frames = the lead box's span (it moves one snapshot per frame).
        n = abs(hi - lo) + 1
        # Resolve each OTHER loaded box's own [lo, hi] so boxes with different
        # snapshot counts stay in sync: every box starts and finishes together,
        # advancing by the same fraction of its own range each frame (rather
        # than a shared index, which desyncs when counts differ).
        others = [
            (
                mdl,
                resolve_snap(from_spec, mdl.snap_count, mdl.snap_table),
                resolve_snap(to_spec, mdl.snap_count, mdl.snap_table),
            )
            for mdl in self._displayed_models()
            if mdl is not lead
        ]
        # Make sure every box's frames are cached before evolving so the first
        # pass is stutter-free (the initial sandbox preload only covers the
        # primary; adjacent boxes are warmed here off the event loop).
        await self._warm_sweep([(lead, lo, hi), *others])
        if not self._playing:
            return

        # loop=True replays the sweep until Next/Pause cancels the task; the
        # auto-advance never fires, so the scene holds until the user steps on.
        i = self._index
        while True:
            for k in range(self._sweep_k.get(i, 0), n):
                if not self._playing:
                    return
                self._sweep_k[i] = k  # checkpoint BEFORE the await so a pause
                #                       (which cancels the task) resumes here.
                frac = k / (n - 1) if n > 1 else 0.0
                scene.set_snapshot(int(round(lo + frac * (hi - lo))))
                for mdl, mlo, mhi in others:
                    mdl.set_snapshot(int(round(mlo + frac * (mhi - mlo))))
                    scene.refresh_label(mdl.name)  # keep its z-label live
                # set_snapshot updates the geometry but does NOT render, so
                # render before pushing or view_update ships the previous frame
                # (the box would appear frozen / "not evolving").
                self._render_push()
                await asyncio.sleep(1.0 / max(0.5, fps))
            self._sweep_k[i] = 0  # full pass done → next loop restarts at top
            if not loop:
                return

    async def _warm_sweep(self, ranges) -> None:
        """Block (off the event loop) until each (model, lo, hi) range is cached.

        Already-warm snapshots are skipped via the loader's tree cache, so a
        resume — where everything is already loaded — returns immediately.
        """
        st = self.state
        warmed = False
        for mdl, mlo, mhi in ranges:
            loader = getattr(mdl, "loader", None)
            if loader is None:
                continue
            a, b = (mlo, mhi) if mlo <= mhi else (mhi, mlo)
            for s in range(a, b + 1):
                if not self._playing:
                    break
                if loader.get_tree(int(s)) is not None:
                    continue  # already loaded
                st.preload_status = (
                    f"Warming {getattr(mdl, 'name', 'model')}..."
                )
                st.flush()
                warmed = True
                try:
                    await asyncio.to_thread(loader.get, int(s))
                except Exception:
                    pass
        if warmed:
            st.preload_status = ""
            st.flush()

    # ---- sandbox preload ------------------------------------------------

    def _story_model_names(self, story: Story) -> list[str]:
        """Every model the story uses: the launched primary, explicit
        ``requirements.models``, and each scene's ``models`` primary/adjacent
        refs (symbolic refs resolved against the discovered models)."""
        scene = self._scene
        avail = self._available_models()
        launched = scene.primary_name
        names: list[str] = []

        def add(ref):
            nm = self._resolve_model_ref(ref, avail, launched, set())
            if nm and nm not in names:
                names.append(nm)

        add(launched)
        for ref in story.requirements.get("models") or []:
            add(ref)
        for sc in story.scenes:
            spec = sc.models or {}
            if spec.get("primary"):
                add(spec.get("primary"))
            for a in spec.get("adjacent") or []:
                add(a)
        return names

    def _model_paths(self) -> dict[str, str]:
        """Map discovered model name → parameter-file path (for loading)."""
        out: dict[str, str] = {}
        for m in getattr(self.state, "models_list", None) or []:
            if isinstance(m, dict) and m.get("name") and m.get("path"):
                out[m["name"]] = m["path"]
        return out

    async def _preload_sandbox(self, story: Story) -> None:
        """Load EVERY model the story uses (hidden) and warm all its snapshots,
        so playback, camera moves, and model switches are stall-free. The
        original build only warmed the active model, which left adjacent boxes
        to load on demand and stutter the first sweep."""
        scene = self._scene
        st = self.state
        names = self._story_model_names(story)
        paths = self._model_paths()

        # Resolve each model to a (loaded) loader + the snapshots to warm.
        plan: list[tuple] = []  # (loader, [snaps])
        for name in names:
            mdl = scene._models.get(name) if scene.has_model(name) else None
            if mdl is None and name in paths:
                try:
                    mdl = scene.add_model(paths[name])  # loads hidden
                except Exception:
                    mdl = None
            loader = getattr(mdl, "loader", None)
            if loader is None:
                continue
            if hasattr(loader, "preload_all"):
                try:
                    loader.preload_all()  # kick background loads of the rest
                except Exception:
                    pass
            plan.append((loader, list(range(mdl.snap_count))))

        total = sum(len(s) for _, s in plan) or 1
        done = 0
        for loader, snaps in plan:
            for s in snaps:
                if self._story is None:  # exited while loading
                    return
                done += 1
                st.preload_status = f"Loading story... {done}/{total}"
                st.flush()
                try:
                    await asyncio.to_thread(loader.get, int(s))
                except Exception:
                    pass
        st.preload_status = ""
        st.flush()

    # ---- user-state stash / restore -------------------------------------

    def _save_user_state(self) -> None:
        st = self.state
        cam = self._scene.plotter.camera
        self._saved = {
            "state": {
                k: deepcopy(getattr(st, k, None)) for k in STORY_STATE_KEYS
            },
            "snap_num": int(getattr(st, "snap_num", self._scene.current_snap)),
            "ui_theme": getattr(st, "ui_theme", "dos_blue"),
            "focus_active": bool(getattr(st, "focus_active", False)),
            "panels_hidden": bool(getattr(st, "panels_hidden", False)),
            "primary": self._scene.primary_name,
            "adjacent": list(
                getattr(self._scene, "_adjacent_order", []) or []
            ),
            "camera": {
                "position": tuple(cam.position),
                "focal_point": tuple(cam.focal_point),
                "up": tuple(cam.up),
            },
        }

    async def _restore_models(self) -> None:
        """Switch the primary model + adjacent boxes back to the saved layout."""
        if not self._saved:
            return
        scene = self._scene
        ctrl = self.ctrl
        saved = self._saved

        primary = saved.get("primary")
        if (
            primary
            and primary != scene.primary_name
            and hasattr(ctrl, "switch_model")
        ):
            try:
                await _maybe_await(ctrl.switch_model(primary))
            except Exception:
                pass

        if hasattr(ctrl, "toggle_adjacent"):
            wanted = set(saved.get("adjacent", []) or [])
            current = set(getattr(scene, "_adjacent_order", []) or [])
            for name in (wanted - current) | (current - wanted):
                try:
                    await _maybe_await(ctrl.toggle_adjacent(name))
                except Exception:
                    pass

    def _restore_user_state(self) -> None:
        if not self._saved:
            return
        scene = self._scene
        st = self.state
        saved = self._saved

        if int(saved["snap_num"]) != scene.current_snap:
            scene.set_snapshot(int(saved["snap_num"]))

        for k, v in saved["state"].items():
            setattr(st, k, deepcopy(v))
        st.dirty(*saved["state"].keys())

        scene.clear_focus()
        st.focus_active = False

        st.ui_theme = saved["ui_theme"]
        st.panels_hidden = saved.get("panels_hidden", False)
        st.story_overlays_json = "[]"

        cam = scene.plotter.camera
        cam.position = saved["camera"]["position"]
        cam.focal_point = saved["camera"]["focal_point"]
        cam.up = saved["camera"]["up"]

        st.flush()
        self._push()
        self._saved = None
