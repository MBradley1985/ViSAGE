"""The Regions tab: a sphere, box or slice, one at a time.

What is on the tab is the active region: the count, Plotting and export all
read it from here. Go cuts the view to it and frames it. Saved regions come
back with their model. The region itself is visage.utils.regions.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pyvista as pv
from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visage.scene.shape_drag import ShapeDrag
from visage.utils import regions

_HEAD = (
    "font-size:0.72rem;font-weight:700;letter-spacing:0.05em;"
    "color:#7FDBFF;padding:18px 0 10px;"
)
_ROW = "display:flex;gap:8px;margin-bottom:12px;"
_SHAPES = ("sphere", "box", "slice")
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
_COLOUR = "cyan"


def _active(scene):
    """The active model's galaxies and their world positions."""
    model = scene.active_model
    _, galaxies = model.loader.get(model.current_snap)
    return galaxies, galaxies.positions + model.offset


def setup(server, scene, push) -> None:
    """The tab's state and handlers; `push` redraws."""
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
    held: dict = {"normal": (0.0, 0.0, 1.0)}
    sweep: list = [None]

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
        return None

    def rows(region) -> np.ndarray:
        galaxies, pos = _active(scene)
        return scene.region_mask(region, galaxies, pos)

    def count_note(region) -> str:
        if region is None:
            return "Fill in every field."
        n = int(rows(region).sum())
        model = scene.active_model
        halos, _ = model.loader.get(model.current_snap)
        size = None if scene.is_lightcone else model.box_size
        h = regions.mask(region, halos.positions + model.offset, size)
        text = f"{n:,} galaxies · {int(h.sum()):,} haloes"
        vol = regions.volume(region, size)
        return text if vol is None else f"{text} · {vol:.3g} (Mpc/h)³"

    def apply() -> None:
        region = current()
        state.region_note = count_note(region)
        if state.region_on and region is not None:
            scene.set_focus_region(region, bool(state.region_grey))
            state.focus_active = True
            state.isolate_active = False
        show_handles()
        push()

    def on_drag(region: dict) -> None:
        """A shape dragged in the view: the tab's fields follow."""
        if region["kind"] == "sphere":
            for a, v in zip("xyz", region["centre"], strict=True):
                state[f"nav_{a}"] = round(v, 2)
            state.nav_distance = round(region["radius"], 2)
        elif region["kind"] == "box":
            for n, a in enumerate("xyz"):
                state[f"nav_box_{a}min"] = round(region["lo"][n], 2)
                state[f"nav_box_{a}max"] = round(region["hi"][n], 2)
        else:
            depth = float(np.dot(region["point"], region["normal"]))
            depth = min(max(depth, state.slice_lo), state.slice_hi)
            state.slice_depth = round(depth, 2)
        state.flush()

    drag = ShapeDrag(scene.plotter, on_drag, push)

    def show_handles() -> None:
        """The active shape in the view, once created."""
        region = current()
        if region is None or not state.region_handles:
            drag.hide()
            return
        if region["kind"] == "slice":
            region["reach"] = 0.5 * float(state.slice_hi - state.slice_lo)
        drag.show(region)

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
        state.slice_sweep = False
        if region_shape == "slice":
            slice_range()
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
            push()

    @state.change("region_handles")
    def on_handles(**_):
        show_handles()
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
        show_handles()

    @ctrl.set("region_fit_view")
    def on_fit_view():
        """Centre on the view and size to what it shows."""
        cam = scene.plotter.camera
        centre = np.array(cam.focal_point, float)
        gap = float(np.linalg.norm(np.subtract(cam.position, centre)))
        half = max(gap * np.tan(np.deg2rad(cam.view_angle) / 2.0), 0.1)
        if state.region_shape == "sphere":
            state.nav_distance = round(half, 3)
        else:
            for a, v in zip("xyz", centre, strict=True):
                state[f"nav_box_{a}min"] = round(float(v - half), 3)
                state[f"nav_box_{a}max"] = round(float(v + half), 3)
        centre_on(centre)

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
        state.slice_sweep = False
        state.region_on = False
        state.region_handles = False
        scene.clear_focus()
        scene.camera._clear_indicator()
        state.focus_active = False
        state.isolate_active = False
        apply()

    # -- Saved -----------------------------------------------------------

    def model_name() -> str:
        return str(scene.active_model.name)

    def list_saved() -> None:
        state.region_saved = [
            {"name": e["name"], "count": e["count"]}
            for e in regions.saved(model_name())
            if e["region"]["kind"] != "selection"
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
        return found.astype(np.int64), {
            f"region_{k}": str(v) for k, v in region.items()
        }

    @ctrl.set("region_show")
    def region_show() -> None:
        state.region_on = True
        state.flush()
        apply()

    def on_model() -> None:
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
    with html.Div(
        raw_attrs=['data-enter-click="btn-region-go"'],
        style="flex:1 1 0;min-width:0;",
    ):
        v3.VTextField(
            v_model=(key,),
            label=label,
            type="number",
            hide_details=True,
            variant="outlined",
            bg_color="#1a1a2e",
            density="compact",
        )


def _tick(key: str, label: str) -> None:
    with html.Div(style="height:30px;"):
        v3.VCheckbox(
            v_model=(key,),
            label=label,
            color=_COLOUR,
            hide_details=True,
            density="compact",
        )


def _toggle(key: str, items, colour: str = _COLOUR) -> None:
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
        color=kw.pop("color", _COLOUR),
        density="compact",
        style=style + kw.pop("style", ""),
        **kw,
    )


def _centre_buttons(ctrl, shape: str) -> None:
    with html.Div(style=_ROW):
        _button(f"Fit {shape} to view", ctrl.region_fit_view)
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
        _centre_buttons(ctrl, "sphere")
        html.Div("SIZE", style=_HEAD)
        with html.Div(style=_ROW):
            _field("nav_distance", "Radius (Mpc/h)")
    with html.Div(v_show=("region_shape === 'box'",)):
        with html.Div(v_show=("!box_minmax",)):
            html.Div("CENTRE", style=_HEAD)
            with html.Div(style=_ROW):
                for a in "xyz":
                    _box_axis_field(a, True)
            _centre_buttons(ctrl, "box")
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
            [("X", "x"), ("Y", "y"), ("Z", "z"), ("Camera", "camera")],
        )
        html.Div("POSITION", style=_HEAD)
        v3.VSlider(
            v_model=("slice_depth",),
            min=("slice_lo",),
            max=("slice_hi",),
            step=0.1,
            color=_COLOUR,
            hide_details=True,
            density="compact",
        )
        with html.Div(style=_ROW + "margin-top:10px;"):
            _field("slice_depth", "Position (Mpc/h)")
            _field("slice_thickness", "Thickness")
        _tick("slice_sweep", "Animate through the volume")
        with html.Div(style=_ROW + "margin-top:6px;"):
            _button("Look along slice", ctrl.region_face_slice)
    with html.Div(style=_ROW + "margin-top:10px;"):
        v3.VBtn(
            "{{ region_handles ? 'Remove' : 'Create' }} {{ region_shape }}",
            click="region_handles = !region_handles",
            variant="outlined",
            color=_COLOUR,
            density="compact",
            style=(
                "flex:1 1 0;letter-spacing:0;text-transform:none;min-width:0;"
            ),
        )
    _tick("region_grey", "Dim outside the region")
    with html.Div(style=_ROW + "margin-top:6px;"):
        _button(
            "Go",
            ctrl.region_go,
            variant="flat",
            id="btn-region-go",
        )
        _button("Clear", ctrl.region_clear, color="#ef4444")
    html.Div(
        "{{ region_note }}",
        style=(
            "background:#0e1a24;border-radius:12px;"
            "padding:10px 12px;font-size:0.78rem;color:#bfeaf5;margin-top:10px;"
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
