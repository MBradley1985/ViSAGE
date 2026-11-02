"""The Track tab: follow a galaxy or halo through the snapshots of a box."""

from __future__ import annotations

import asyncio

import numpy as np
from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visage.ui.plotting import _step
from visage.utils.group_info import member_indices
from visage.utils.track import (
    Track,
    camera_centres,
    captions,
    contributors,
    follow,
    nearest_image,
)

FRAMING_ITEMS = [
    {"title": "Galaxy", "value": "galaxy"},
    {"title": "Surroundings", "value": "surroundings"},
    {"title": "FoF links", "value": "fof"},
    {"title": "Contributors", "value": "contributors"},
    {"title": "Whole box", "value": "box"},
]
# Mpc/h from the galaxy each framing starts at; the zoom buttons change it.
DEFAULT_ZOOM = {"galaxy": 3, "surroundings": 10, "fof": 5, "contributors": 10}
KEEP = 0  # the Keep zoom: as far away as the view is now
ZOOMS = [
    {"title": "Keep", "value": KEEP},
    {"title": "3", "value": 3},
    {"title": "5", "value": 5},
    {"title": "10", "value": 10},
    {"title": "20", "value": 20},
]


def trim(track: Track, first: int, last: int) -> Track:
    """The part of ``track`` from snapshot ``first`` to ``last``."""
    keep = [i for i, s in enumerate(track.snaps) if first <= s <= last]
    return Track(
        snaps=[track.snaps[i] for i in keep],
        galaxy_id=[track.galaxy_id[i] for i in keep],
        pos=[track.pos[i] for i in keep],
        central_id=[track.central_id[i] for i in keep if track.central_id],
        central_pos=[track.central_pos[i] for i in keep if track.central_pos],
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


def views(centres: dict, framing: str, away, zoom: float) -> dict:
    """snapshot: (centre, camera offset).  ``away`` is the view's offset
    from what it looks at now: its direction is kept, and with the Keep zoom
    its length too."""
    if framing == "box":
        return {s: (c, None) for s, c in centres.items()}
    away = np.asarray(away, float)
    length = float(np.linalg.norm(away)) or 1.0
    offset = tuple(away / length * (zoom or length))
    return {s: (c, offset) for s, c in centres.items()}


def setup(server, scene) -> None:
    state, ctrl = server.state, server.controller
    state.track_busy = False
    state.track_ready = False
    state.track_saving = False
    state.track_saved = ""
    state.track_framing = "galaxy"
    state.track_framings = FRAMING_ITEMS
    state.track_zoom = DEFAULT_ZOOM["galaxy"]
    state.track_zooms = ZOOMS
    state.track_percent = 0
    state.track_status = ""
    state.track_events = []
    run: dict = {"stop": False, "done": 0, "total": 1, "track": None}

    def shower(
        path: dict,
        sets: dict,
        centres: dict,
        framing: str,
        halo: bool,
        iso: bool,
    ):
        """What draws the view at a snapshot: which galaxies are shown, and
        the indicators on them.  Rows differ from one snapshot to the next,
        so this runs for each."""
        grouped = halo or framing == "fof"
        masked = iso or framing in ("fof", "contributors")

        def show(snap: int) -> None:
            model = scene.active_model
            _, galaxies = model.loader.get(snap)
            marker = scene.camera.marker
            if snap in centres:
                marker.set_target(centres[snap])
            hit = np.flatnonzero(galaxies.galaxy_id == path.get(snap))
            row = int(hit[0]) if len(hit) else None
            members = np.zeros(0, dtype=np.int64)
            if row is not None:
                members = (
                    member_indices(galaxies, row)
                    if grouped
                    else np.array([row], dtype=np.int64)
                )
            if framing == "contributors":
                members = np.flatnonzero(
                    np.isin(galaxies.galaxy_id, sets.get(snap, ()))
                )
            if masked:
                halo_rows = []
                if grouped and row is not None:
                    central = galaxies.positions[members[0]] + model.offset
                    host = ctrl.sel_host_halo(snap, central)
                    halo_rows = [] if host is None else [host]
                scene.set_focus_indices(halo_rows, members)
            box = scene.primary.box_size
            points = nearest_image(
                galaxies.positions[members] + model.offset,
                marker.target,
                box,
            )
            away = np.linalg.norm(points - marker.target, axis=1) > 1e-6
            marker.set_details(
                "", points[away], style="full" if grouped else "small"
            )
            marker.set_links(points[away] if framing == "fof" else None)

        return show

    def settle() -> None:
        """Stay on what was followed, focus and all, with a view that holds
        at any snapshot: a track's rows only hold at its own."""
        framing, iso = run.get("framing"), run.get("iso")
        scene.camera.marker.set_links(None)
        if iso:
            state.isolate_active = False
            ctrl.toggle_isolate()
        elif framing not in (None, "box"):
            ctrl.go_frame()
        away = run.get("away")
        if away is not None and framing != "box":
            cam = scene.plotter.camera
            cam.position = tuple(np.add(cam.focal_point, away))
            scene.plotter.renderer.ResetCameraClippingRange()
            ctrl.view_update()

    async def build(gid: int, own: int, first: int, last: int) -> None:
        # The galaxy is known to exist at the current snapshot, so the walk
        # starts there even if that is outside the range asked for.
        now = int(scene.current_snap)
        snaps = list(range(min(first, now), max(last, now) + 1))
        framing = str(state.track_framing)
        halo = str(state.sel_kind) == "halo"
        iso = bool(state.isolate_active)
        path_file = scene._cfg.hdf5_path
        run.update(stop=False, done=0, total=len(snaps), track=None)
        state.track_busy = True
        state.track_percent = 0
        state.track_events = []
        state.track_ready = False
        state.track_status = "Following it…"
        state.flush()
        work = asyncio.create_task(
            asyncio.to_thread(
                follow,
                path_file,
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
        path, own_path = {}, {}
        if not track.cancelled:
            track = trim(track, first, last)
            # A halo's camera follows its central; the selection stays on
            # the galaxy chosen.
            own_path = track_ids(track) if track.snaps else {}
            if own != gid:
                own_track = await asyncio.to_thread(
                    follow, path_file, own, now, snaps
                )
                own_track = trim(own_track, first, last)
                own_path = track_ids(own_track) if own_track.snaps else {}
            run["track"] = track
            state.track_events = [event_text(e) for e in track.events]
            centres = camera_centres(
                track,
                list(range(first, last + 1)),
                scene.primary.box_size,
                halo=halo or framing == "fof",
            )
            if centres:
                path = track_ids(track)
                sets = {}
                if framing == "contributors":
                    state.track_status = "Finding its contributors…"
                    state.flush()
                    sets = await asyncio.to_thread(
                        contributors, path_file, path, snaps, halo
                    )
                state.track_status = "Rendering frames…"
                state.flush()
                cam = scene.plotter.camera
                away = np.subtract(cam.position, cam.focal_point)
                planned = views(
                    centres, framing, away, float(state.track_zoom)
                )
                offset = next(iter(planned.values()))[1]
                run.update(framing=framing, iso=iso, away=offset)
                if framing in ("galaxy", "surroundings") and not iso:
                    ctrl.go_frame()
                if framing != "box":
                    state.focus_active = True
                show = shower(path, sets, centres, framing, halo, iso)
                state.track_ready = await ctrl.track_render(
                    sorted(centres),
                    planned,
                    captions(track, halo=halo),
                    show,
                    lambda: run["stop"],
                )
                if not state.track_ready:
                    settle()
        state.track_busy = False
        if run["stop"]:
            state.track_status = "Stopped."
            state.track_events = []
        elif state.track_ready:
            ctrl.sel_follow_track(own_path, show)
            state.track_status = (
                f"Ready: {len(track.snaps)} snapshots, {track.snaps[0]} to "
                f"{track.snaps[-1]}. Play from the bar above."
            )
        else:
            state.track_status = "It isn't in that range."
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
        own = ctrl.sel_galaxy()
        asyncio.get_running_loop().create_task(
            build(gid, gid if own is None else own, first, last)
        )

    @ctrl.set("track_stop")
    def track_stop():
        run["stop"] = True

    @ctrl.set("track_leave")
    def forget(**_):
        if state.track_ready:
            ctrl.track_clear()
            ctrl.sel_follow_track(None)
            state.track_ready = False
            settle()
        run["track"] = None
        state.track_events = []
        state.track_status = ""
        state.track_saved = ""

    def whole_run():
        model = scene.active_model
        state.track_from = int(getattr(model, "snap_min", 0))
        state.track_to = int(getattr(model, "snap_max", scene.snap_count - 1))
        forget()

    @state.change("track_framing")
    def framing_zoom(track_framing, **_):
        if track_framing in DEFAULT_ZOOM:
            state.track_zoom = DEFAULT_ZOOM[track_framing]

    whole_run()
    scene.register_model_change_callback(whole_run)
    # Frames hold what they were built with: changing any of these needs
    # another Build.
    state.change(
        "track_from",
        "track_to",
        "track_framing",
        "track_zoom",
        "sel_kind",
        "sel_rings",
    )(forget)


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
            with v3.VBtnToggle(
                v_model=("sel_kind",),
                mandatory=True,
                density="compact",
                color="cyan",
                variant="outlined",
                divided=True,
                disabled=("track_busy",),
                style="width:100%;margin-bottom:8px;",
            ):
                v3.VBtn("Galaxy", value="galaxy", style="flex:1;")
                v3.VBtn("Whole halo", value="halo", style="flex:1;")
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
            with html.Div(
                v_show=("track_framing !== 'box'",),
                style=(
                    "display:flex;align-items:center;gap:4px;padding:4px 0;"
                    "font-size:0.72rem;color:#9ca3af;"
                ),
            ):
                html.Span(
                    "Zoom (h^-1 Mpc)",
                    style="margin-right:auto;white-space:nowrap;",
                )
                with html.Div(style="display:flex;gap:3px;"):
                    v3.VBtn(
                        "{{ z.title }}",
                        v_for=("z in track_zooms",),
                        key=("z.value",),
                        size="x-small",
                        variant="outlined",
                        color=("track_zoom === z.value ? 'cyan' : '#cbd5e1'",),
                        disabled=("track_busy",),
                        click="track_zoom = z.value",
                        style="min-width:0;flex:none;",
                    )
            with html.Div(style="padding:2px 0 4px;text-align:left;"):
                v3.VBtn(
                    "{{ sel_rings ? 'Hide indicators' : 'Show indicators' }}",
                    size="x-small",
                    variant="text",
                    color="#9ca3af",
                    disabled=("track_busy",),
                    click=ctrl.sel_clear_marker,
                    style="flex:none;",
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
