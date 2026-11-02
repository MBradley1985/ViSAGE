"""The Track tab: follow a galaxy or halo through the snapshots of a box."""

from __future__ import annotations

import asyncio

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visage.ui.plotting import _step
from visage.utils.track import Track, follow


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


def setup(server, scene) -> None:
    state, ctrl = server.state, server.controller
    state.track_busy = False
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
        state.track_busy = False
        if track.cancelled:
            state.track_status = "Stopped."
        else:
            track = trim(track, first, last)
            run["track"] = track
            state.track_events = [event_text(e) for e in track.events]
            state.track_status = (
                f"Followed through {len(track.snaps)} snapshots, "
                f"{track.snaps[0]} to {track.snaps[-1]}."
                if track.snaps
                else "The galaxy isn't in that range."
            )
        state.flush()

    @ctrl.set("track_build")
    def track_build():
        gid = ctrl.sel_track_target()
        if gid is None or bool(state.track_busy):
            return
        first, last = sorted((int(state.track_from), int(state.track_to)))
        asyncio.get_running_loop().create_task(build(gid, first, last))

    @ctrl.set("track_stop")
    def track_stop():
        run["stop"] = True

    def forget(**_):
        run["track"] = None
        state.track_events = []
        state.track_status = ""

    def whole_run():
        model = scene.active_model
        state.track_from = int(getattr(model, "snap_min", 0))
        state.track_to = int(getattr(model, "snap_max", scene.snap_count - 1))
        forget()

    whole_run()
    scene.register_model_change_callback(whole_run)
    state.change("sel_title", "track_from", "track_to")(forget)


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
