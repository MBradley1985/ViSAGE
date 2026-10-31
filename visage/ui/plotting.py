"""The Plotting tab: SAGE26's diagnostic plots for whatever is selected."""

from __future__ import annotations

import asyncio
import datetime
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visage import procs
from visage.io.sage_files import open_snapshot
from visage.plots import history, local, observed  # noqa: F401
from visage.plots.base import COLOUR_LABELS, PLOTS
from visage.plots.style import FORMATS

KINDS = (("local", "Local"), ("history", "History"), ("observed", "Observed"))
FILTER_KEYS = ("filter_", "extra_", "env_show_")
SCALES = [
    {"title": "As drawn", "value": ""},
    {"title": "Log", "value": "log"},
    {"title": "Linear", "value": "linear"},
]
HEADING = (
    "font-size:0.85rem;font-weight:700;letter-spacing:0.06em;"
    "color:#06b6d4;display:block;padding:4px 0 6px;"
)


def _present(scene) -> set:
    """The fields of the open catalogue."""
    model = scene.active_model
    lc = getattr(model, "_lc", None)
    if lc is not None:
        return {f.lower() for f in lc.present_fields}
    with open_snapshot(scene._cfg.hdf5_path, scene.current_snap) as group:
        return {str(k).lower() for k in group.keys()} if group else set()


def plot_groups(scene) -> list:
    """The plots a catalogue can make, as Local, History, Observed, each
    in sections; those missing a field are greyed out."""
    mode = "cone" if scene.is_lightcone else "box"
    fields = _present(scene)
    out = []
    for kind, title in KINDS:
        sections: dict = {}
        for key, spec in PLOTS.items():
            if spec["kind"] != kind or mode not in spec["modes"]:
                continue
            sections.setdefault(spec["section"], []).append(
                {
                    "key": key,
                    "title": spec["title"],
                    "group": spec["group"],
                    "missing": not all(
                        f.lower() in fields for f in spec["needs"]
                    ),
                }
            )
        if sections:
            out.append(
                {
                    "title": title,
                    "sections": [
                        {"title": k, "items": v} for k, v in sections.items()
                    ],
                }
            )
    return out


def setup(server, scene, region_indices, open_image, refresh, out_dir) -> None:
    """The tab's state and handlers.  `region_indices(scope)`: galaxies of
    a region ("coords", "box", "group"), `open_image(path)` shows a plot,
    `refresh()` updates the Library."""
    state, ctrl = server.state, server.controller
    state.plot_groups = plot_groups(scene)
    state.plot_selected = []
    state.plot_region = "whole"
    state.plot_regions = [
        {
            "title": "Whole lightcone" if scene.is_lightcone else "Whole box",
            "value": "whole",
        },
        {"title": "Coords sphere", "value": "coords"},
        {"title": "Box region", "value": "box"},
        {"title": "Selected group", "value": "group"},
    ]
    state.plot_filters = True
    state.plot_scatter = False
    state.plot_dark = False
    state.plot_colour = ""
    state.plot_colours = [{"title": "None", "value": ""}] + [
        {"title": k, "value": k}
        for k in COLOUR_LABELS
        if k != "redshift" or scene.is_lightcone
    ]
    state.plot_xscale = state.plot_yscale = ""
    state.plot_scales = SCALES
    state.plot_xmin = state.plot_xmax = None
    state.plot_ymin = state.plot_ymax = None
    state.plot_formats = ["png"]
    state.plot_format_items = list(FORMATS)
    state.plot_busy = False
    state.plot_percent = 0
    state.plot_status = ""
    state.plot_is_cone = bool(scene.is_lightcone)
    state.plot_zmin, state.plot_zmax = 0.0, 0.2
    run: dict = {"proc": None, "cancelled": False}

    def number(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def chosen_rows(gal) -> np.ndarray:
        region = state.plot_region
        keep = np.ones(gal.count, bool)
        if region != "whole":
            keep[:] = False
            keep[region_indices(region)[0]] = True
        mask = scene.galaxy_layer._filter_mask
        if state.plot_filters and mask is not None:
            keep &= mask
        return np.asarray(gal.sage_indices)[keep]

    def region_spec(h: float) -> tuple:
        """The region for other snapshots, and its volume in Mpc^3."""
        if state.plot_region == "coords":
            r = float(state.nav_distance)
            centre = [
                float(state.nav_x),
                float(state.nav_y),
                float(state.nav_z),
            ]
            spec = {"kind": "sphere", "centre": centre, "radius": r}
            return spec, 4.0 / 3.0 * math.pi * (r / h) ** 3
        if state.plot_region == "box":
            lo = [float(state[f"nav_box_{a}min"]) for a in "xyz"]
            hi = [float(state[f"nav_box_{a}max"]) for a in "xyz"]
            size = np.subtract(hi, lo) / h
            return {"kind": "box", "lo": lo, "hi": hi}, float(np.prod(size))
        return {}, None

    def request(rows_path: Path) -> dict:
        from visage.plots import catalogue as cat

        model = scene.active_model
        cfg = scene._cfg
        h = float(cfg.hubble_h)
        _, gal = model.loader.get(scene.current_snap)
        rows = chosen_rows(gal)
        np.savez(rows_path, rows=rows)
        req = dict(
            plots=list(state.plot_selected),
            formats=list(state.plot_formats) or ["png"],
            options=dict(
                scatter=bool(state.plot_scatter),
                dark=bool(state.plot_dark),
                colour_by=state.plot_colour or "",
                xscale=state.plot_xscale or "",
                yscale=state.plot_yscale or "",
                limits={
                    k: number(state[f"plot_{k}"])
                    for k in ("xmin", "xmax", "ymin", "ymax")
                },
            ),
            h=h,
            omega_m=float(cfg.omega),
            omega_l=float(cfg.omega_lambda),
            out_dir=str(out_dir),
            stamp=f"{datetime.datetime.now():%H%M%S}",
        )
        if scene.is_lightcone:
            req.update(
                mode="cone",
                path=str(model.path),
                has_volume=state.plot_region == "whole",
                zmin=float(state.plot_zmin),
                zmax=float(state.plot_zmax),
            )
            return req
        region, volume = region_spec(h)
        full = cat.box_volume(cfg.hdf5_path, cfg.box_size, h)
        if state.plot_region == "whole":
            volume = full
        filters = None
        if state.plot_filters:
            filters = {
                k: v
                for k, v in state.to_dict().items()
                if str(k).startswith(FILTER_KEYS)
            }
        table = scene.primary.snap_table
        req.update(
            mode="box",
            path=str(cfg.hdf5_path),
            snap=int(scene.current_snap),
            z=float(1.0 / table.scale_factors[scene.current_snap] - 1.0),
            scale_factors=[float(a) for a in table.scale_factors],
            snapshots=list(range(len(table.scale_factors))),
            volume=volume,
            local_volume=volume,
            region=region,
            filters=filters,
            fields=dict(model.fields_available),
            min_stellar_mass=float(model.loader._min_stellar_mass),
            min_particles=model.loader._min_particles,
            particle_mass=cfg.part_mass,
        )
        return req

    @ctrl.set("plot_make")
    async def make_plots():
        if state.plot_busy or not state.plot_selected:
            return
        work = Path(tempfile.mkdtemp(prefix="visage_plots_"))
        try:
            req = request(work / "req.npz")
        except ValueError as exc:
            state.plot_status = str(exc)
            return
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (work / "req.json").write_text(json.dumps(req))
        log = work / "log"
        with open(log, "w") as handle:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-W",
                    "ignore",
                    "-m",
                    "visage.plots",
                    str(work / "req.json"),
                ],
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        procs.track(proc)
        run.update(proc=proc, cancelled=False)
        state.plot_busy = True
        state.plot_percent = 0
        state.plot_status = "Starting…"
        state.flush()
        while proc.poll() is None:
            await asyncio.sleep(0.5)
            for line in reversed(log.read_text().splitlines()):
                if line.startswith("progress "):
                    _, share, what = line.split(" ", 2)
                    state.plot_percent = round(100 * float(share))
                    state.plot_status = what
                    break
            state.flush()
        procs.untrack(proc)
        lines = log.read_text().splitlines()
        made = [ln[5:] for ln in lines if ln.startswith("made ")]
        bad = [ln for ln in lines if ln.startswith(("failed ", "skipped "))]
        for path in made[-6:]:
            open_image(path)
        refresh()
        state.plot_busy = False
        if run["cancelled"]:
            state.plot_status = "Cancelled."
        elif proc.returncode != 0:
            state.plot_status = (lines or ["Couldn't make the plots."])[-1]
        else:
            state.plot_status = f"Made {len(made)} in the Library."
            if bad:
                state.plot_status += " " + "; ".join(bad)
        state.flush()

    @ctrl.set("plot_cancel")
    def cancel_plots():
        if run["proc"] is not None:
            run["cancelled"] = True
            procs.stop_group(run["proc"])


def tab(ctrl) -> None:
    """The tab's panel."""
    with v3.VSheet(
        color="transparent",
        v_show=("nav_active_tab === 'plotting'",),
        style="padding:8px 12px;",
    ):
        html.Span("PLOTTING", style=HEADING)
        v3.VSelect(
            v_model=("plot_region",),
            items=("plot_regions",),
            label="Galaxies",
            density="compact",
            hide_details=True,
            variant="outlined",
            style="margin-bottom:6px;",
        )
        v3.VCheckbox(
            v_model=("plot_filters",),
            label="Use Filters and Environments",
            density="compact",
            hide_details=True,
            color="cyan",
        )
        with html.Div(v_show=("plot_is_cone",), style="display:flex;gap:6px;"):
            for key, label in (("zmin", "Local z from"), ("zmax", "to")):
                v3.VTextField(
                    v_model=(f"plot_{key}",),
                    label=label,
                    type="number",
                    step=0.05,
                    density="compact",
                    hide_details=True,
                    variant="outlined",
                )
        with v3.VExpansionPanels(
            multiple=True, variant="accordion", style="margin:8px 0;"
        ):
            with v3.VExpansionPanel(
                v_for=("kind in plot_groups",),
                key=("kind.title",),
                bg_color="transparent",
            ):
                v3.VExpansionPanelTitle(
                    "{{ kind.title }}",
                    style="font-size:0.8rem;min-height:34px;padding:4px 8px;",
                )
                with v3.VExpansionPanelText():
                    with html.Div(
                        v_for=("sec in kind.sections",), key=("sec.title",)
                    ):
                        html.Div(
                            "{{ sec.title }}",
                            style=(
                                "font-size:0.68rem;color:#9ca3af;"
                                "padding:6px 0 0;"
                            ),
                        )
                        v3.VCheckbox(
                            v_for=("item in sec.items",),
                            key=("item.key",),
                            v_model=("plot_selected",),
                            value=("item.key",),
                            label=("item.title",),
                            disabled=(
                                "item.missing || (plot_region === 'group'"
                                " && !item.group)",
                            ),
                            density="compact",
                            hide_details=True,
                            color="cyan",
                            style="margin-bottom:-10px;",
                        )
        v3.VSwitch(
            v_model=("plot_scatter",),
            label="Each galaxy, not the median and 1σ",
            density="compact",
            hide_details=True,
            color="cyan",
        )
        v3.VSwitch(
            v_model=("plot_dark",),
            label="Dark background",
            density="compact",
            hide_details=True,
            color="cyan",
        )
        v3.VSelect(
            v_show=("plot_scatter",),
            v_model=("plot_colour",),
            items=("plot_colours",),
            label="Colour by",
            density="compact",
            hide_details=True,
            variant="outlined",
            style="margin:6px 0;",
        )
        with html.Div(style="display:flex;gap:6px;margin:6px 0;"):
            for axis in "xy":
                v3.VSelect(
                    v_model=(f"plot_{axis}scale",),
                    items=("plot_scales",),
                    label=f"{axis} axis",
                    density="compact",
                    hide_details=True,
                    variant="outlined",
                )
        for axis in "xy":
            with html.Div(style="display:flex;gap:6px;margin-bottom:6px;"):
                for end in ("min", "max"):
                    v3.VTextField(
                        v_model=(f"plot_{axis}{end}",),
                        label=f"{axis} {end}",
                        type="number",
                        density="compact",
                        hide_details=True,
                        variant="outlined",
                    )
        v3.VSelect(
            v_model=("plot_formats",),
            items=("plot_format_items",),
            label="Save as",
            multiple=True,
            chips=True,
            density="compact",
            hide_details=True,
            variant="outlined",
        )
        v3.VBtn(
            "{{ plot_selected.length > 1 ? 'Make ' + plot_selected.length"
            " + ' plots' : 'Make plot' }}",
            v_show=("!plot_busy",),
            block=True,
            color="cyan",
            variant="outlined",
            disabled=("!plot_selected.length",),
            click=ctrl.plot_make,
            style="margin-top:8px;",
        )
        with html.Div(v_show=("plot_busy",), style="margin-top:8px;"):
            v3.VProgressLinear(
                model_value=("plot_percent",), color="cyan", height=4
            )
            v3.VBtn(
                "Cancel",
                block=True,
                variant="text",
                color="#ef4444",
                density="compact",
                click=ctrl.plot_cancel,
            )
        html.Div(
            "{{ plot_status }}",
            style="font-size:0.7rem;color:#9ca3af;padding-top:6px;",
        )
