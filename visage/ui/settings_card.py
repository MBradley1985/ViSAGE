"""Settings card (toolbar cog): HD quality presets, what they give, and
custom values, within HD's 4 GB."""

from __future__ import annotations

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visage.hd import settings

_PRESETS = (
    ("Low", "low"),
    ("Medium", "medium"),
    ("High", "high"),
    ("Crazy", "crazy"),
    ("Custom", "custom"),
)
_QUALITY = (("Light", "lite"), ("Medium", "group"), ("Full", "full"))
_RENDER = (("Standard", "standard"), ("Retina", "retina"))
_NAME = {v: k for k, v in _QUALITY}


def _info(s: dict) -> list[str]:
    """What the settings give, one line each."""
    from visage import system
    from visage.hd.group import TEXTURE_MB

    models, cache = settings.split(s)
    allowed = settings.QUALITIES[: settings.QUALITIES.index(s["quality"]) + 1]
    reach = [
        f"{_NAME[q].lower()} up to "
        f"{min(s['max_models'], max(1, models // TEXTURE_MB[q]))}"
        for q in allowed[::-1]
    ]
    ram = (system.total_memory_bytes() or 0) / 1024**3
    render = (
        "Rendered at every screen pixel (sharpest, slowest)."
        if s["render"] == "retina"
        else "Rendered at standard resolution on a Retina screen: a quarter "
        "of the pixels, about 2-4x the frame rate."
    )
    return [
        render,
        "Galaxies in one view: " + ", ".join(reach) + "; beyond that, glows.",
        f"Memory limit {s['memory_mb'] / 1000:g} GB of HD's "
        f"{settings.LIMIT_MB / 1000:.0f} GB maximum: setup "
        f"{settings.SETUP_MB / 1000:.1f}, recent builds {cache / 1000:.1f}, "
        f"galaxies on screen {models / 1000:.1f}.",
        f"This machine: {ram:.0f} GB of memory.",
    ]


def build_settings_card(server) -> None:
    state, ctrl = server.state, server.controller
    s = settings.load()
    state.hd_set_dialog = False
    state.hd_set_preset = s["preset"]
    state.hd_set_quality = s["quality"]
    state.hd_set_memory = round(s["memory_mb"] / 1000, 2)
    state.hd_set_models = s["max_models"]
    state.hd_set_render = s["render"]
    state.hd_set_info = _info(s)
    state.hd_set_mem_now = "0.0 GB"
    state.hd_set_models_now = 0
    busy = {"on": False}  # (setting several values at once)

    def apply(s):
        s = settings.save(s)
        state.hd_set_info = _info(s)
        if ctrl.hd_settings_applied.exists():
            ctrl.hd_settings_applied()

    @state.change("hd_set_preset")
    def _preset(hd_set_preset, **_):
        if busy["on"] or hd_set_preset == "custom":
            return
        s = settings.from_preset(hd_set_preset)
        busy["on"] = True
        state.hd_set_quality = s["quality"]
        state.hd_set_memory = round(s["memory_mb"] / 1000, 2)
        state.hd_set_models = s["max_models"]
        state.hd_set_render = s["render"]
        state.flush()
        busy["on"] = False
        apply(s)

    @state.change(
        "hd_set_quality", "hd_set_memory", "hd_set_models", "hd_set_render"
    )
    def _custom(
        hd_set_quality, hd_set_memory, hd_set_models, hd_set_render, **_
    ):
        if busy["on"]:
            return
        s = {
            "quality": hd_set_quality,
            "memory_mb": int(round(float(hd_set_memory) * 1000)),
            "max_models": int(hd_set_models),
            "render": hd_set_render,
        }
        match = next(
            (k for k, p in settings.PRESETS.items() if p == s), "custom"
        )
        busy["on"] = True
        state.hd_set_preset = match
        state.flush()
        busy["on"] = False
        apply({"preset": match, **s})

    @state.change("hd_set_dialog")
    def _opened(hd_set_dialog, **_):
        if hd_set_dialog and ctrl.hd_memory_now.exists():
            ctrl.hd_memory_now()

    pill = dict(size="small", variant="outlined", rounded="pill")
    sec = (
        "font-size:0.7rem;letter-spacing:0.08em;color:#22d3ee;"
        "font-weight:700;margin:12px 0 4px;"
    )
    head = "font-size:0.6rem;color:#9ca3af;display:block;padding:4px 0 2px;"

    def pills(model, items):
        with v3.VChipGroup(
            v_model=(model,),
            mandatory=True,
            selected_class="sage-pill-on",
            column=True,
        ):
            for title, value in items:
                v3.VChip(title, value=value, filter=False, **pill)

    with v3.VDialog(v_model=("hd_set_dialog",), max_width=400):
        with v3.VCard(
            classes="sage-popout", elevation=0, style="color:#e2e8f0;"
        ):
            with html.Div(
                classes="sage-popout-handle",
                style="display:flex;align-items:flex-start;padding:16px 12px 4px 18px;",
            ):
                with html.Div(style="flex:1;"):
                    html.Div(
                        "Settings",
                        style="font-size:1.15rem;font-weight:700;color:#fff;",
                    )
                    html.Div(
                        "HD quality and memory",
                        style="font-size:0.78rem;color:#9ca3af;margin-top:2px;",
                    )
                v3.VBtn(
                    icon="mdi-close",
                    size="x-small",
                    variant="text",
                    click="hd_set_dialog = false",
                )
            with html.Div(style="padding:4px 18px 16px;"):
                html.Div("PRESET", style=sec)
                pills("hd_set_preset", _PRESETS)

                html.Div("WHAT YOU GET", style=sec)
                html.Div(
                    "{{ line }}",
                    v_for="line in hd_set_info",
                    style="font-size:0.78rem;color:#cbd5e1;margin:2px 0;",
                )
                html.Div(
                    "HD holds now: about {{ hd_set_mem_now }} "
                    "({{ hd_set_models_now }} galaxies drawn).",
                    style="font-size:0.78rem;color:#cbd5e1;margin:2px 0;",
                )
                html.Div(
                    "Quality and memory apply from the next HD build; render "
                    "resolution at once.",
                    style="font-size:0.75rem;color:#fbbf24;margin-top:4px;",
                )

                html.Div("CUSTOM", style=sec)
                v3.VLabel("Best quality", style=head)
                pills("hd_set_quality", _QUALITY)
                v3.VLabel("Render resolution (Retina screens)", style=head)
                pills("hd_set_render", _RENDER)
                v3.VLabel(
                    "Memory limit  {{ '— ' + hd_set_memory + ' GB' }}",
                    style=head,
                )
                v3.VSlider(
                    v_model=("hd_set_memory",),
                    min=(settings.SETUP_MB + 200) / 1000,
                    max=settings.PRESETS["crazy"]["memory_mb"] / 1000,
                    step=0.05,
                    thumb_label=True,
                    color="cyan",
                    density="compact",
                    hide_details=True,
                )
                v3.VLabel(
                    "HD galaxies in one view  {{ '— ' + hd_set_models }}",
                    style=head,
                )
                v3.VSlider(
                    v_model=("hd_set_models",),
                    min=1,
                    max=100,
                    step=1,
                    thumb_label=True,
                    color="cyan",
                    density="compact",
                    hide_details=True,
                )
