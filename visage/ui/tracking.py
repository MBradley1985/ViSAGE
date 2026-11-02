"""The Track tab: follow a galaxy or halo through the snapshots of a box."""

from __future__ import annotations

import asyncio

import numpy as np
from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visage.ui.plotting import _step
from visage.utils.track import Track, camera_centres, captions, follow

GROUP_DISTANCE = 10.0  # Mpc/h from the galaxy, for the Group framing
FRAMING_ITEMS = [
    {"title": "As Go: the galaxy", "value": "go"},
    {"title": "Group: its surroundings", "value": "group"},
    {"title": "Whole box: camera stays put", "value": "box"},
]


def trim(track: Track, first: int, last: int) -> Track:
    """The part of ``track`` from snapshot ``first`` to ``last``."""
    keep = [i for i, s in enumerate(track.snaps) if first <= s <= last]
    return Track(
        snaps=[track.snaps[i] for i in keep],
        galaxy_id=[track.galaxy_id[i] for i in keep],
        pos=[track.pos[i] for i in keep],
        events=[e for e in track.events if first <= e["snap"] <= last],
    )


def event_text(event: dict) -> str:
    """One line of the panel's history."""
    snap = f"Snapshot {event['snap']}"
    kind = event["kind"]
    if kind == "ended":
        return f"{snap}: the branch ends, with no merger on record"
    if kind == "lost":
        return f"{snap}: merged, but its target wasn't written out"
    return f"{snap}: {kind} into galaxy {event['into']}"


def track_ids(track: Track) -> dict:
    """{snapshot: the GalaxyIndex followed there}, gaps filled by the galaxy
    that came before."""
    ids = dict(zip(track.snaps, track.galaxy_id, strict=True))
    for snap in range(track.snaps[0] + 1, track.snaps[-1]):
        if snap not in ids:
            ids[snap] = ids[snap - 1]
    return ids


def views(centres: dict, framing: str, camera) -> dict:
    """snapshot: (centre, camera offset).  The camera has just been put on
    the galaxy by Go, so As Go keeps its offset as it stands."""
    if framing == "box":
        return {s: (c, None) for s, c in centres.items()}
    away = np.subtract(camera.position, camera.focal_point)
    if framing == "group":
        away = away / (float(np.linalg.norm(away)) or 1.0) * GROUP_DISTANCE
    return {s: (c, tuple(away)) for s, c in centres.items()}


def setup(server, scene) -> None:
    state, ctrl = server.state, server.controller
    state.track_busy = False
    state.track_ready = False
    state.track_saving = False
    state.track_saved = ""
    state.track_framing = "go"
    state.track_framings = FRAMING_ITEMS
    state.track_percent = 0
    state.track_status = ""
    state.track_events = []
    run: dict = {"stop": False, "done": 0, "total": 1, "track": None}

    async def build(gid: int, first: int, last: int) -> None:
        # The galaxy is known to exist at the current snapshot, so the walk
        # starts there even if that is outside the range asked for.
        now = int(scene.current_snap)
        snaps = list(range(min(first, now), max(last, now) + 1))
        run.update(stop=False, done=0, total=len(snaps), track=None)
        state.track_busy = True
        state.track_percent = 0
        state.track_events = []
        state.track_ready = False
        state.track_status = "Following the galaxy…"
        state.flush()
        work = asyncio.create_task(
            asyncio.to_thread(
                follow,
                scene._cfg.hdf5_path,
                gid,
                now,
                snaps,
                lambda done, _: run.update(done=done),
                lambda: run["stop"],
            )
        )
        while not work.done():
            await asyncio.sleep(0.1)
            state.track_percent = round(100 * run["done"] / run["total"])
            state.flush()
        track = await work
        if not track.cancelled:
            track = trim(track, first, last)
            run["track"] = track
            state.track_events = [event_text(e) for e in track.events]
            centres = camera_centres(
                track, list(range(first, last + 1)), scene.primary.box_size
            )
            if centres:
                state.track_status = "Rendering frames…"
                state.flush()
                if state.track_framing != "box":
                    ctrl.go_frame()
                state.track_ready = await ctrl.track_render(
                    sorted(centres),
                    views(
                        centres,
                        state.track_framing,
                        scene.plotter.camera,
                    ),
                    captions(track),
                    lambda: run["stop"],
                )
                if not state.track_ready and state.track_framing != "box":
                    ctrl.go_frame()  # stay on it, focus and all
        state.track_busy = False
        if run["stop"]:
            state.track_status = "Stopped."
            state.track_events = []
        elif state.track_ready:
            ctrl.sel_follow_track(track_ids(track))
            state.track_status = (
                f"Ready: {len(track.snaps)} snapshots, {track.snaps[0]} to "
                f"{track.snaps[-1]}. Play from the bar above."
            )
        else:
            state.track_status = "The galaxy isn't in that range."
        state.flush()

    @ctrl.set("track_build")
    def track_build():
        gid = ctrl.sel_track_target()
        if bool(state.track_busy):
            return
        if gid is None:
            state.track_status = (
                "It isn't in this snapshot: move to one it is in."
            )
            return
        first, last = sorted((int(state.track_from), int(state.track_to)))
        asyncio.get_running_loop().create_task(build(gid, first, last))

    @ctrl.set("track_stop")
    def track_stop():
        run["stop"] = True

    @ctrl.set("track_leave")
    def forget(**_):
        if state.track_ready:
            ctrl.track_clear()
            ctrl.sel_follow_track(None)
        run["track"] = None
        state.track_ready = False
        state.track_events = []
        state.track_status = ""
        state.track_saved = ""

    def whole_run():
        model = scene.active_model
        state.track_from = int(getattr(model, "snap_min", 0))
        state.track_to = int(getattr(model, "snap_max", scene.snap_count - 1))
        forget()

    whole_run()
    scene.register_model_change_callback(whole_run)
    state.change("track_from", "track_to", "track_framing")(forget)


def tab(ctrl) -> None:
    """The tab's panel."""
    with v3.VSheet(
        color="transparent",
        v_show=("nav_active_tab === 'track'",),
        style="display:flex;flex-direction:column;flex:1;min-height:0;",
    ):
        with html.Div(style="flex:1;min-height:0;overflow-y:auto;"):
            _step(1, "Choose what to follow")
            html.Div(
                "{{ sel_active ? sel_title : 'Select a galaxy or halo first.' }}",
                style=(
                    "font-size:0.78rem;color:#e2e8f0;padding:2px 0 8px;"
                    "text-align:left;"
                ),
            )
            _step(2, "Choose snapshots")
            with html.Div(style="display:flex;gap:8px;padding:6px 0;"):
                for key, label in (("from", "From"), ("to", "To")):
                    v3.VTextField(
                        v_model_number=(f"track_{key}",),
                        label=label,
                        type="number",
                        min=("snap_min",),
                        max=("snap_max",),
                        density="compact",
                        hide_details=True,
                        variant="outlined",
                        disabled=("track_busy",),
                    )
            _step(3, "Choose framing")
            v3.VSelect(
                v_model=("track_framing",),
                items=("track_framings",),
                classes="sage-sel-cyan",
                color="cyan",
                density="compact",
                hide_details=True,
                variant="outlined",
                disabled=("track_busy",),
                style="margin:6px 0;",
            )
            v3.VBtn(
                "Build",
                block=True,
                variant="outlined",
                color="cyan",
                density="compact",
                prepend_icon="mdi-map-marker-path",
                disabled=("!sel_active || track_busy",),
                click=ctrl.track_build,
                style="margin-top:8px;",
            )
            with html.Div(v_show=("track_busy",), style="padding-top:8px;"):
                v3.VProgressLinear(
                    model_value=("track_percent",), color="cyan", height=4
                )
                v3.VBtn(
                    "Stop",
                    block=True,
                    variant="text",
                    color="#ef4444",
                    density="compact",
                    click=ctrl.track_stop,
                )
            html.Div(
                "{{ track_status }}",
                v_show=("track_status",),
                style=(
                    "font-size:0.72rem;color:#9ca3af;padding-top:8px;"
                    "text-align:left;"
                ),
            )
            html.Div(
                "{{ line }}",
                v_for=("line in track_events",),
                key=("line",),
                style=(
                    "font-size:0.7rem;color:#cbd5e1;padding-top:4px;"
                    "text-align:left;"
                ),
            )
            with html.Div(v_show=("track_ready",), style="padding-top:10px;"):
                v3.VSelect(
                    v_model=("movie_format",),
                    items=("['gif', 'mov', 'png']",),
                    label="Save as",
                    classes="sage-sel-cyan",
                    color="cyan",
                    density="compact",
                    hide_details=True,
                    variant="outlined",
                )
                html.Div(style="height:8px;")
                v3.VBtn(
                    "Save movie",
                    block=True,
                    variant="outlined",
                    color="cyan",
                    density="compact",
                    disabled=("track_saving",),
                    click=ctrl.track_save,
                )
                v3.VBtn(
                    "Leave track",
                    block=True,
                    variant="text",
                    color="#9ca3af",
                    density="compact",
                    click=ctrl.track_leave,
                )
                html.Div(
                    "{{ track_saved }}",
                    v_show=("track_saved",),
                    style=(
                        "font-size:0.7rem;color:#9ca3af;padding-top:6px;"
                        "text-align:left;word-break:break-all;"
                    ),
                )
