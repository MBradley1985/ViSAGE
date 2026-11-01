"""The Regions tab: a sphere, box, slice or selection, one at a time.

What is on the tab is the active region: the count, Plotting and export all
read it from here. Go cuts the view to it and frames it. Saved regions come back with their model. The region
itself is visage.utils.regions; a selection is drawn in the browser
(visage.js, over `region-draw`) and picked here by where galaxies fall on
screen.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pyvista as pv
from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visage.utils import regions

_HEAD = (
    "font-size:0.72rem;font-weight:700;letter-spacing:0.05em;"
    "color:#7FDBFF;padding:10px 0 6px;"
)
_ROW = "display:flex;gap:6px;margin-bottom:6px;"
_SHAPES = ("sphere", "box", "slice", "selection")
_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
_GEOMETRY = (
    "nav_x",
    "nav_y",
    "nav_z",
    "nav_distance",
    "nav_box_xmin",
    "nav_box_xmax",
    "nav_box_ymin",
    "nav_box_ymax",
    "nav_box_zmin",
    "nav_box_zmax",
    "slice_depth",
    "slice_thickness",
)
_CLICK_REACH = 0.03  # of the view: how near a click must be to a galaxy


def _active(scene):
    """The active model's galaxies and their world positions."""
    model = scene.active_model
    _, galaxies = model.loader.get(model.current_snap)
    return galaxies, galaxies.positions + model.offset


def setup(server, scene, toggle_sphere, toggle_box, push) -> None:
    """The tab's state and handlers. `toggle_sphere` and `toggle_box` show
    or hide the drag handles; `push` redraws."""
    state, ctrl = server.state, server.controller
    state.region_shape = "sphere"
    state.region_on = False
    state.region_grey = False
    state.region_handles = False
    state.region_note = ""
    state.region_name = ""
    state.region_saved = []
    state.box_minmax = False
    state.slice_axis = "z"
    state.slice_depth = 0.0
    state.slice_thickness = 5.0
    state.slice_lo, state.slice_hi = 0.0, 1.0
    state.slice_sweep = False
    state.region_tool = None
    state.region_op = "add"
    state.region_front = False
    picked: set = set()
    held: dict = {"normal": (0.0, 0.0, 1.0), "geometry": "sphere"}
    sweep: list = [None]
    outline: list = [None]

    def number(key) -> float:
        return float(state[key])

    def middle() -> np.ndarray:
        _, pos = _active(scene)
        if scene.is_lightcone:
            return pos.mean(axis=0) if len(pos) else np.zeros(3)
        size = scene.active_model.box_size
        return np.asarray(scene.active_model.offset) + 0.5 * size

    def normal() -> np.ndarray:
        axis = state.slice_axis
        return np.array(_AXES.get(axis, held["normal"]))

    def current(shape=None) -> dict | None:
        """The region on the tab, or None while a field is empty."""
        shape = shape or state.region_shape
        try:
            if shape == "sphere":
                return {
                    "kind": "sphere",
                    "centre": [number(f"nav_{a}") for a in "xyz"],
                    "radius": number("nav_distance"),
                }
            if shape == "box":
                return {
                    "kind": "box",
                    "lo": [number(f"nav_box_{a}min") for a in "xyz"],
                    "hi": [number(f"nav_box_{a}max") for a in "xyz"],
                }
            if shape == "slice":
                n, mid = normal(), middle()
                depth = number("slice_depth")
                point = mid + n * (depth - float(mid @ n))
                return {
                    "kind": "slice",
                    "point": point.tolist(),
                    "normal": n.tolist(),
                    "thickness": number("slice_thickness"),
                    "axis": state.slice_axis,
                    "depth": depth,
                }
        except (TypeError, ValueError):
            return None
        return {"kind": "selection", "ids": sorted(int(i) for i in picked)}

    def rows(region) -> np.ndarray:
        galaxies, pos = _active(scene)
        return scene.region_mask(region, galaxies, pos)

    def count_note(region) -> str:
        if region is None:
            return "Fill in every field."
        n = int(rows(region).sum())
        if region["kind"] == "selection":
            follow = "" if scene.is_lightcone else ", followed through time"
            return f"{n:,} of {len(picked):,} chosen galaxies here{follow}"
        model = scene.active_model
        halos, _ = model.loader.get(model.current_snap)
        size = None if scene.is_lightcone else model.box_size
        h = regions.mask(region, halos.positions + model.offset, size)
        text = f"{n:,} galaxies · {int(h.sum()):,} haloes"
        vol = regions.volume(region, size)
        return text if vol is None else f"{text} · {vol:.3g} (Mpc/h)³"

    def show_chosen() -> None:
        """While choosing, dim everything but the chosen galaxies."""
        focus = scene._focus_region
        marking = focus is not None and focus.get("marking", False)
        if state.region_on:
            return
        if picked and state.region_shape == "selection":
            scene.set_focus_region(current("selection"), True, True)
        elif marking:
            scene.clear_focus()

    def apply() -> None:
        region = current()
        state.region_note = count_note(region)
        if state.region_on and region is not None:
            scene.set_focus_region(region, bool(state.region_grey))
            state.focus_active = True
            state.isolate_active = False
        show_chosen()
        show_slice()
        push()

    def show_slice() -> None:
        """Outline the slice in the view, once created."""
        if outline[0] is not None:
            scene.plotter.remove_actor(outline[0], render=False)
            outline[0] = None
        region = current("slice")
        if not state.region_handles or state.region_shape != "slice":
            return
        if region is None:
            return
        n, point = np.array(region["normal"]), np.array(region["point"])
        u = np.cross(
            n, (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (1.0, 0.0, 0.0)
        )
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        reach = 0.5 * float(state.slice_hi - state.slice_lo)
        corners = [(a, b) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        ring = [point + reach * (a * u + b * v) for a, b in corners]
        line = pv.lines_from_points(np.array(ring + ring[:1]))
        outline[0] = scene.plotter.add_mesh(
            line,
            color="white",
            opacity=0.55,
            line_width=1,
            pickable=False,
            reset_camera=False,
            render=False,
        )

    def stop_handles() -> None:
        if state.draw_sphere_active:
            toggle_sphere()
        if state.draw_box_active:
            toggle_box()

    def sync_handles() -> None:
        stop_handles()
        if state.region_handles and state.region_shape == "sphere":
            toggle_sphere()
        if state.region_handles and state.region_shape == "box":
            toggle_box()

    def slice_range() -> None:
        """The slider's reach along the slice's direction."""
        _, pos = _active(scene)
        if not len(pos):
            return
        along = np.sum(np.asarray(pos, float) * normal(), axis=1)
        lo, hi = float(along.min()), float(along.max())
        state.slice_lo, state.slice_hi = round(lo, 2), round(hi, 2)
        state.slice_depth = round(0.5 * (lo + hi), 2)

    @state.change("region_shape")
    def on_shape(region_shape, **_):
        state.region_tool = None
        state.slice_sweep = False
        if region_shape != "selection":
            held["geometry"] = region_shape
        if region_shape == "slice":
            slice_range()
        sync_handles()
        apply()

    @state.change(*_GEOMETRY)
    def on_geometry(**_):
        apply()

    @state.change("region_on", "region_grey")
    def on_show(region_on, **_):
        region = scene._focus_region
        mine = region is not None and region["type"] == "region"
        mine = mine and not region["marking"]
        if region_on:
            apply()
        elif mine:
            scene.clear_focus()
            state.focus_active = False
            show_chosen()
            push()

    @state.change("region_handles")
    def on_handles(**_):
        sync_handles()
        show_slice()
        push()

    @state.change("slice_axis")
    def on_axis(slice_axis, **_):
        if slice_axis == "camera":
            cam = scene.plotter.camera
            forward = np.subtract(cam.focal_point, cam.position)
            held["normal"] = tuple(forward / np.linalg.norm(forward))
        slice_range()
        apply()

    @state.change("slice_sweep")
    def on_sweep(slice_sweep, **_):
        if sweep[0] is not None:
            sweep[0].cancel()
            sweep[0] = None
        if slice_sweep:
            state.region_on = True
            sweep[0] = asyncio.ensure_future(run_sweep())

    async def run_sweep() -> None:
        while True:
            lo, hi = float(state.slice_lo), float(state.slice_hi)
            step = max(0.5 * float(state.slice_thickness), 0.01)
            depth = float(state.slice_depth) + step
            with state:
                state.slice_depth = round(lo if depth > hi else depth, 2)
            await asyncio.sleep(0.2)

    def centre_on(point) -> None:
        """Move the sphere or box to `point`, keeping its size."""
        if state.region_shape == "sphere":
            for a, v in zip("xyz", point, strict=True):
                state[f"nav_{a}"] = round(float(v), 3)
        else:
            for a, v in zip("xyz", point, strict=True):
                half = 0.5 * (
                    number(f"nav_box_{a}max") - number(f"nav_box_{a}min")
                )
                state[f"nav_box_{a}min"] = round(float(v) - half, 3)
                state[f"nav_box_{a}max"] = round(float(v) + half, 3)
        sync_handles()

    @ctrl.set("region_view_centre")
    def on_view_centre():
        centre_on(scene.plotter.camera.focal_point)

    @ctrl.set("region_galaxy_centre")
    def on_galaxy_centre():
        if state.nav_gal_idx is not None:
            _, pos = _active(scene)
            centre_on(pos[int(state.nav_gal_idx)])

    @ctrl.set("region_go")
    def on_go():
        """Isolate the region and frame it."""
        region = current()
        if region is None:
            return
        if region["kind"] == "sphere":
            centre, radius = region["centre"], region["radius"]
        else:
            _, pos = _active(scene)
            pos = np.asarray(pos[rows(region)], float)
            if not len(pos):
                return
            centre = 0.5 * (pos.min(axis=0) + pos.max(axis=0))
            radius = float(np.linalg.norm(pos - centre, axis=1).max())
        scene.camera.zoom_to_radius(tuple(centre), max(radius, 0.1))
        scene.camera._clear_indicator()
        state.region_tool = None
        region_show()

    @ctrl.set("region_face_slice")
    def on_face_slice():
        region = current("slice")
        if region is None:
            return
        cam = scene.plotter.camera
        n, point = np.array(region["normal"]), np.array(region["point"])
        gap = float(np.linalg.norm(np.subtract(cam.position, cam.focal_point)))
        cam.focal_point = tuple(point)
        cam.position = tuple(point - n * gap)
        cam.up = (0.0, 1.0, 0.0) if abs(n[1]) < 0.9 else (0.0, 0.0, 1.0)
        scene._refit_clipping()
        push()

    @ctrl.set("region_clear")
    def on_clear():
        picked.clear()
        state.slice_sweep = False
        state.region_tool = None
        state.region_on = False
        state.region_handles = False
        scene.clear_focus()
        scene.camera._clear_indicator()
        state.focus_active = False
        state.isolate_active = False
        apply()

    # -- Selection -------------------------------------------------------

    def choose(ids) -> None:
        """Change the selection by `ids`, as the tab's Add/Remove/Replace."""
        if state.region_op == "replace":
            picked.clear()
        if state.region_op == "remove":
            picked.difference_update(int(i) for i in ids)
        else:
            picked.update(int(i) for i in ids)
        apply()

    def on_screen() -> tuple:
        """Rows of the galaxies on show, their screen positions and depth."""
        galaxies, pos = _active(scene)
        layer = scene.active_model.galaxy_layer
        shown = layer._combined_mask()
        idx = (
            np.arange(galaxies.count)
            if shown is None
            else np.flatnonzero(shown)
        )
        ren = scene.plotter.renderer
        m = ren.GetActiveCamera().GetCompositeProjectionTransformMatrix(
            ren.GetTiledAspectRatio(), -1, 1
        )
        matrix = [[m.GetElement(i, j) for j in range(4)] for i in range(4)]
        xy, depth, ahead = regions.screen(pos[idx], matrix)
        return idx[ahead], xy[ahead], depth[ahead]

    @ctrl.trigger("region_pick")
    def on_pick(tool, points):
        """A stroke over the view: `points` run 0 to 1 from the top left."""
        idx, xy, depth = on_screen()
        ids = regions.identity(_active(scene)[0])
        stroke = np.array(points, float) * [2, -2] + [-1, 1]
        if tool == "click":
            near = np.linalg.norm(xy - stroke[0], axis=1)
            hit = near.argmin() if len(near) else None
            if hit is not None and near[hit] < 2 * _CLICK_REACH:
                choose(ids[idx[[hit]]])
            return
        if tool == "rectangle":
            (x0, y0), (x1, y1) = stroke[0], stroke[-1]
            stroke = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        inside = np.flatnonzero(regions.in_polygon(xy, stroke))
        if state.region_front and len(inside):
            inside = inside[regions.front(xy[inside], depth[inside])]
        choose(ids[idx[inside]])

    @ctrl.set("region_take_filtered")
    def on_take_filtered():
        galaxies, _ = _active(scene)
        keep = scene.active_model.galaxy_layer._filter_mask
        ids = regions.identity(galaxies)
        choose(ids if keep is None else ids[keep])

    @ctrl.set("region_take_group")
    def on_take_group():
        from visage.utils.group_info import member_indices

        if state.nav_gal_idx is not None:
            galaxies, _ = _active(scene)
            members = member_indices(galaxies, int(state.nav_gal_idx))
            choose(regions.identity(galaxies)[members])

    @ctrl.set("region_take_region")
    def on_take_region():
        region = current(held["geometry"])
        if region is not None:
            choose(regions.identity(_active(scene)[0])[rows(region)])

    # -- Saved -----------------------------------------------------------

    def model_name() -> str:
        return str(scene.active_model.name)

    def list_saved() -> None:
        state.region_saved = [
            {"name": e["name"], "count": e["count"]}
            for e in regions.saved(model_name())
        ]

    @ctrl.set("region_save")
    def on_save():
        region = current()
        if region is None:
            return
        entries = regions.saved(model_name())
        name = str(state.region_name or "").strip() or (
            f"{state.region_shape.title()} {len(entries) + 1}"
        )
        entries = [e for e in entries if e["name"] != name]
        count = int(rows(region).sum())
        entries.append({"name": name, "region": region, "count": count})
        regions.save(model_name(), entries)
        state.region_name = ""
        list_saved()

    @ctrl.set("region_load")
    def on_load(name):
        entry = next(
            (e for e in regions.saved(model_name()) if e["name"] == name),
            None,
        )
        if entry is None:
            return
        region = entry["region"]
        kind = region["kind"]
        if kind == "sphere":
            for a, v in zip("xyz", region["centre"], strict=True):
                state[f"nav_{a}"] = v
            state.nav_distance = region["radius"]
        elif kind == "box":
            for k, a in enumerate("xyz"):
                state[f"nav_box_{a}min"] = region["lo"][k]
                state[f"nav_box_{a}max"] = region["hi"][k]
        elif kind == "slice":
            held["normal"] = tuple(region["normal"])
            state.slice_axis = region["axis"]
            state.slice_thickness = region["thickness"]
        else:
            picked.clear()
            picked.update(region["ids"])
        state.region_shape = kind
        state.flush()
        if kind == "slice":
            state.slice_depth = region["depth"]
            state.flush()
        state.region_on = True
        apply()

    @ctrl.set("region_delete")
    def on_delete(name):
        regions.save(
            model_name(),
            [e for e in regions.saved(model_name()) if e["name"] != name],
        )
        list_saved()

    # -- For everything else ---------------------------------------------

    @ctrl.set("region_now")
    def region_now() -> dict | None:
        return current()

    @ctrl.set("region_rows")
    def region_rows() -> tuple:
        """Rows of the active region, and what it is, for an export."""
        region = current()
        if region is None:
            raise ValueError("Fill in every field on the Regions tab.")
        found = np.flatnonzero(rows(region))
        if not len(found):
            raise ValueError("No galaxies in the active region.")
        if region["kind"] == "selection":
            return found.astype(np.int64), {"selection_galaxies": len(found)}
        return found.astype(np.int64), {
            f"region_{k}": str(v) for k, v in region.items()
        }

    @ctrl.set("region_show")
    def region_show() -> None:
        state.region_on = True
        state.flush()
        apply()

    def on_model() -> None:
        picked.clear()
        state.region_on = False
        state.slice_sweep = False
        list_saved()
        if state.region_shape == "slice":
            slice_range()
        apply()

    list_saved()
    scene.register_model_change_callback(on_model)

    def on_snap(_snap) -> None:
        state.region_note = count_note(current())

    scene.register_snap_change_callback(on_snap)
    state.region_note = count_note(current())


def _field(key: str, label: str) -> None:
    v3.VTextField(
        v_model=(key,),
        label=label,
        type="number",
        hide_details=True,
        variant="outlined",
        bg_color="#1a1a2e",
        density="compact",
        style="flex:1 1 0;min-width:0;",
    )


def _tick(key: str, label: str) -> None:
    with html.Div(style="height:30px;"):
        v3.VCheckbox(
            v_model=(key,),
            label=label,
            color="cyan",
            hide_details=True,
            density="compact",
        )


def _toggle(key: str, items, colour: str = "cyan") -> None:
    """A row of mutually exclusive buttons, (label, value) each."""
    with v3.VBtnToggle(
        v_model=(key,),
        mandatory=True,
        density="compact",
        color=colour,
        style="width:100%;height:30px;margin-bottom:8px;",
    ):
        for label, value in items:
            v3.VBtn(
                label,
                value=value,
                size="small",
                variant="tonal",
                style=(
                    "flex:1 1 0;min-width:0;height:30px;letter-spacing:0;"
                    "text-transform:none;font-size:0.7rem;"
                ),
            )


def _button(label: str, click, **kw) -> None:
    style = "flex:1 1 0;min-width:0;letter-spacing:0;text-transform:none;"
    v3.VBtn(
        label,
        click=click,
        variant=kw.pop("variant", "outlined"),
        color=kw.pop("color", "cyan"),
        density="compact",
        style=style + kw.pop("style", ""),
        **kw,
    )


def _centre_buttons(ctrl) -> None:
    with html.Div(style=_ROW):
        _button("Centre on view", ctrl.region_view_centre)
        _button(
            "Centre on galaxy",
            ctrl.region_galaxy_centre,
            disabled=("nav_gal_idx == null",),
        )


def _box_axis_field(a: str, centre: bool) -> None:
    """A box's centre or size on axis `a`; it holds min and max."""
    lo, hi = f"nav_box_{a}min", f"nav_box_{a}max"
    mid = f"(+{lo} + +{hi}) / 2"
    half = f"(+{hi} - +{lo}) / 2"
    tidy = "(v) => +v.toFixed(3)"
    if centre:
        value = f"+({mid}).toFixed(3)"
        new = ("+$event - h", "+$event + h")
        keep = f"const h = {half}"
    else:
        value = f"+(+{hi} - +{lo}).toFixed(3)"
        new = ("m - $event / 2", "m + $event / 2")
        keep = f"const m = {mid}"
    write = f"const r = {tidy}; {keep}; {lo} = r({new[0]}); {hi} = r({new[1]})"
    v3.VTextField(
        model_value=(value,),
        update_modelValue=f"if ($event !== '') {{ {write} }}",
        label=a.upper(),
        type="number",
        hide_details=True,
        variant="outlined",
        bg_color="#1a1a2e",
        density="compact",
        style="flex:1 1 0;min-width:0;",
    )


def tab(ctrl) -> None:
    """The tab's content."""
    _toggle(
        "region_shape",
        [(s.title(), s) for s in _SHAPES],
    )
    with html.Div(v_show=("region_shape === 'sphere'",)):
        html.Div("CENTRE", style=_HEAD)
        with html.Div(style=_ROW):
            for a in "xyz":
                _field(f"nav_{a}", a.upper())
        _centre_buttons(ctrl)
        html.Div("SIZE", style=_HEAD)
        with html.Div(style=_ROW):
            _field("nav_distance", "Radius (Mpc/h)")
    with html.Div(v_show=("region_shape === 'box'",)):
        with html.Div(v_show=("!box_minmax",)):
            html.Div("CENTRE", style=_HEAD)
            with html.Div(style=_ROW):
                for a in "xyz":
                    _box_axis_field(a, True)
            _centre_buttons(ctrl)
            html.Div("SIZE (Mpc/h)", style=_HEAD)
            with html.Div(style=_ROW):
                for a in "xyz":
                    _box_axis_field(a, False)
        with html.Div(v_show=("box_minmax",)):
            html.Div("BOUNDS (Mpc/h)", style=_HEAD)
            for a in "xyz":
                with html.Div(style=_ROW):
                    _field(f"nav_box_{a}min", f"{a.upper()} min")
                    _field(f"nav_box_{a}max", f"{a.upper()} max")
        _tick("box_minmax", "Enter min and max")
    with html.Div(v_show=("region_shape === 'slice'",)):
        html.Div("AXIS", style=_HEAD)
        _toggle(
            "slice_axis",
            [("X", "x"), ("Y", "y"), ("Z", "z"), ("View", "camera")],
        )
        html.Div("POSITION", style=_HEAD)
        v3.VSlider(
            v_model=("slice_depth",),
            min=("slice_lo",),
            max=("slice_hi",),
            step=0.1,
            color="cyan",
            hide_details=True,
            density="compact",
        )
        with html.Div(style=_ROW + "margin-top:10px;"):
            _field("slice_depth", "Position (Mpc/h)")
            _field("slice_thickness", "Thickness")
        _tick("slice_sweep", "Sweep")
        with html.Div(style=_ROW + "margin-top:6px;"):
            _button("Face slice", ctrl.region_face_slice)
    with html.Div(v_show=("region_shape === 'selection'",)):
        html.Div("DRAW", style=_HEAD)
        with html.Div(style=_ROW):
            for label, tool in (
                ("Lasso", "lasso"),
                ("Rectangle", "rectangle"),
                ("Click", "click"),
            ):
                _button(
                    label,
                    f"region_tool = region_tool === '{tool}' ? null : '{tool}'",
                    variant=(
                        f"region_tool === '{tool}' ? 'flat' : 'outlined'",
                    ),
                )
        html.Div("MODE", style=_HEAD)
        _toggle(
            "region_op",
            [("Add", "add"), ("Remove", "remove"), ("Replace", "replace")],
        )
        html.Div("ADD FROM", style=_HEAD)
        with html.Div(style=_ROW):
            _button("Filters", ctrl.region_take_filtered)
            _button(
                "Group",
                ctrl.region_take_group,
                disabled=("nav_gal_idx == null",),
            )
            _button("Last region", ctrl.region_take_region)
        _tick("region_front", "Front galaxies only")
    with html.Div(
        v_show=("region_shape !== 'selection'",),
        style=_ROW + "margin-top:10px;",
    ):
        v3.VBtn(
            "{{ region_handles ? 'Remove' : 'Create' }} {{ region_shape }}",
            click="region_handles = !region_handles",
            variant="outlined",
            color="cyan",
            density="compact",
            style=(
                "flex:1 1 0;letter-spacing:0;text-transform:none;min-width:0;"
            ),
        )
    _tick("region_grey", "Dim the rest instead of hiding")
    with html.Div(style=_ROW + "margin-top:6px;"):
        _button("Go", ctrl.region_go, variant="flat")
        _button("Clear", ctrl.region_clear, color="#ef4444")
    html.Div(
        "{{ region_note }}",
        style=(
            "background:#0e1a24;border-radius:4px;padding:7px 8px;"
            "font-size:0.78rem;color:#bfeaf5;margin-top:6px;"
        ),
    )
    html.Div("SAVED", style=_HEAD + "margin-top:8px;")
    with html.Div(style=_ROW):
        v3.VTextField(
            v_model=("region_name",),
            label="Name",
            hide_details=True,
            variant="outlined",
            bg_color="#1a1a2e",
            density="compact",
            style="flex:2 1 0;min-width:0;",
        )
        _button("Save", ctrl.region_save)
    with html.Div(
        v_for="s in region_saved",
        key="s.name",
        style=(
            "display:flex;align-items:center;gap:6px;font-size:0.8rem;"
            "border-top:1px solid #1e2533;padding:3px 0;"
        ),
    ):
        html.Span(
            "{{ s.name }}",
            click=(ctrl.region_load, "[s.name]"),
            style="flex:1;cursor:pointer;color:#7FDBFF;",
            title="Show this region",
        )
        html.Span("{{ s.count.toLocaleString() }}", style="color:#8b95a5;")
        v3.VBtn(
            icon="mdi-close",
            size="x-small",
            variant="text",
            density="compact",
            click=(ctrl.region_delete, "[s.name]"),
            title="Delete",
        )
