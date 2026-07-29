from __future__ import annotations

from pathlib import Path

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from textwrap import dedent

from trame.widgets import html, vuetify3 as v3
from trame_vtk.modules.vtk import has_capabilities
from trame_vtk.widgets.vtk import VtkRemoteView

from visage.scene.box_profile import (
    BOX_PROFILE_KEYS,
    default_profile,
    save_profile,
    load_profile,
)
from visage.scene.scene import Scene
from visage.utils.discover import find_models

# ──────────────────────────────────────────────────────────────────────────
# UI palettes
# ──────────────────────────────────────────────────────────────────────────
_THEME_CSS = dedent(
    """
/* Force the page root to black so no theme colour bleeds through
   above the toolbar or in any uncovered gap. */
html, body, .v-application { background: #000000 !important; }
.v-app-bar, .v-toolbar { background: #000000 !important; box-shadow: none !important; }

/* ============================================================
   MODERN (default) — colours come from the Vuetify theme.  No
   structural overrides; Vuetify defaults apply.
   ============================================================ */

/* ============================================================
   DOS BLUE — Norton-Commander-style high-contrast IBM blue.
   Vuetify adds `.v-theme--dos_blue` to the application root when
   the theme is active; everything below is scoped to that class.
   ============================================================ */
/* Border-radius zero on everything (including icons — no harm) */
.v-theme--dos_blue,
.v-theme--dos_blue *,
.v-theme--dos_blue *::before,
.v-theme--dos_blue *::after { border-radius: 0 !important; }

/* VT323 font on text-bearing elements, but explicitly NOT on any icon
   wrapper / glyph so MDI keeps its own font and continues to render. */
.v-theme--dos_blue,
.v-theme--dos_blue *:not(.v-icon):not(.v-icon *):not(i.mdi):not(.mdi):not([class*="mdi-"]):not(.material-icons):not(.material-icons *) {
    font-family: 'VT323','Perfect DOS VGA 437','Courier New',monospace !important;
    letter-spacing: 0.03em;
}
/* VT323 renders smaller than equivalent-pt sans-serif fonts; bump every
   text-bearing element in DOS Blue mode so it reads at a comfortable size. */
.v-theme--dos_blue .v-label,
.v-theme--dos_blue .v-list-item-title,
.v-theme--dos_blue .v-list-subheader { font-size: 1.1rem !important; }
.v-theme--dos_blue .v-list-item-subtitle { font-size: 0.92rem !important; }
.v-theme--dos_blue .v-btn { font-size: 1.0rem !important; }
.v-theme--dos_blue .v-card-title { font-size: 1.2rem !important; }
.v-theme--dos_blue .v-card-text { font-size: 0.95rem !important; }
.v-theme--dos_blue .v-field__input,
.v-theme--dos_blue .v-field input,
.v-theme--dos_blue input { font-size: 1.05rem !important; }
.v-theme--dos_blue .v-chip { font-size: 1.0rem !important; }
/* Slider value bubbles (thumb labels) — default is tiny and unreadable;
   enlarge the bubble and its text on every slider / range slider. */
.v-theme--dos_blue .v-slider-thumb__label {
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    min-width: 2.4em !important;
    height: 1.9em !important;
    padding: 0 6px !important;
}
/* Filter range sliders are rendered at transform:scale(0.7) to save space,
   which shrinks their value bubble. Bump the font so the on-screen size
   matches the (unscaled) opacity sliders: 1.5rem * 0.7 ~= 1.05rem.
   Also widen the bubble so values like "-14.0" or "10000" never get clipped.
   white-space:nowrap prevents the text wrapping inside the bubble. */
.v-theme--dos_blue .sage-fslider .v-slider-thumb__label {
    font-size: 1.5rem !important;
    min-width: 4em !important;
    white-space: nowrap !important;
    overflow: visible !important;
}
.v-theme--dos_blue .v-select__selection-text { font-size: 1.0rem !important; }
.v-theme--dos_blue .v-select__selection { font-size: 1.0rem !important; }
.v-theme--dos_blue span { font-size: 1em; }       /* keep inheritance */
.v-theme--dos_blue .v-toolbar-title { font-size: 1.25rem !important; }
.v-theme--dos_blue .v-card {
    border: 2px solid #ffffff !important;
    box-shadow: 4px 4px 0 #000 !important;
    backdrop-filter: none !important;
}
.v-theme--dos_blue .v-card-title {
    background: #aaaaaa !important;
    color: #000 !important;
    letter-spacing: 0.12em;
}
.v-theme--dos_blue .v-btn {
    border: 1px solid #ffffff !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    box-shadow: 2px 2px 0 #000 !important;
    font-weight: 700;
}
/* Text-variant and icon-only buttons should look borderless — the DOS
   border treatment is for solid action buttons, not inline controls. */
.v-theme--dos_blue .v-btn--variant-text,
.v-theme--dos_blue .v-btn--icon {
    border: none !important;
    box-shadow: none !important;
}
.v-theme--dos_blue .v-text-field .v-field,
.v-theme--dos_blue .v-select .v-field { border-radius: 0 !important; }
.v-theme--dos_blue .v-chip { border-radius: 0 !important; }
"""
)
from visage.ui.info_panel import build_info_panel
from visage.ui.navigation_panel import build_navigation_panel
from visage.ui.toolbar import build_toolbar
from visage.ui.story_mode import (
    build_story_button,
    build_story_hud,
    build_story_overlays,
    init_story_mode,
)


def create_app(
    par_path: str | Path,
    par_dir: str | Path | None = None,
    initial_snap: int | None = None,
    n_jobs: int = -1,
    min_halo_mass: float = 1.0e10,
    min_stellar_mass: float = 1.0e8,
    max_halos: int = 100_000,
    max_galaxies: int | None = None,
    port: int = 8080,
    lightcone_path: str | Path | None = None,
):
    scene = Scene(
        primary_par_path=par_path,
        off_screen=False,
        initial_snap=initial_snap,
        n_jobs=n_jobs,
        min_halo_mass=min_halo_mass,
        min_stellar_mass=min_stellar_mass,
        max_halos=max_halos,
        max_galaxies=max_galaxies,
        lightcone_path=lightcone_path,
    )

    server = get_server(client_type="vue3")
    server.enable_module(has_capabilities)

    # Serve ViSAGE's client-side helpers (pop-out drag, Enter-to-
    # click). Vue 3 silently drops <script> tags from templates so we
    # have to inject these via the module/static-asset system.
    import os as _os_static

    _sage_static_dir = _os_static.path.join(
        _os_static.path.dirname(__file__), "static"
    )

    # Cache-bust the served JS/CSS with each file's mtime so browsers
    # pick up edits on restart instead of replaying a stale cached copy
    # (which silently breaks client-side features like the pop-out
    # fullscreen toggle until a manual hard refresh).
    def _bust(rel):
        # Map "sage_static/<subpath>" to the file under the static dir so
        # nested assets (e.g. katex/katex.min.js) are cache-busted too.
        sub = rel.split("?", 1)[0]
        if sub.startswith("sage_static/"):
            sub = sub[len("sage_static/") :]
        try:
            mtime = int(
                _os_static.path.getmtime(
                    _os_static.path.join(_sage_static_dir, sub)
                )
            )
        except OSError:
            return rel
        return f"{rel}?v={mtime}"

    server.enable_module(
        {
            "serve": {"sage_static": _sage_static_dir},
            # KaTeX (vendored, woff2-only) must load before visage.js,
            # which calls katex.render() for Story Mode equation overlays.
            "scripts": [
                _bust("sage_static/katex/katex.min.js"),
                _bust("sage_static/visage.js"),
            ],
            "styles": [
                _bust("sage_static/katex/katex.min.css"),
                _bust("sage_static/sage_theme.css"),
            ],
        }
    )

    # xterm.js — browser-side terminal emulator for the console PTY.
    server.enable_module(
        {
            "styles": [
                "https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css",
            ],
            "scripts": [
                "https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js",
                "https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.js",
            ],
        }
    )

    # Single-theme config — DOS Blue is now the only palette.
    _vuetify_config = {
        "theme": {
            "defaultTheme": "dos_blue",
            "themes": {
                "dos_blue": {
                    "dark": True,
                    "colors": {
                        "primary": "#ffff55",  # DOS yellow
                        "secondary": "#ffffff",
                        "background": "#000000",
                        "surface": "#000000",
                        "on-surface": "#ffffff",
                        "on-background": "#ffffff",
                    },
                },
            },
        }
    }
    # Story Mode player + reactive state / controllers.
    init_story_mode(server, scene)

    _NAV_TABS = [
        ("Structure", "layers"),
        ("Filters", "filters"),
        ("Record", "record"),
        ("Target", "target"),
        ("Environment", "environment"),
        ("Coords", "coords"),
        ("Box", "box"),
        ("Console", "console"),
        ("Library", "library"),
    ]

    # ---- Model discovery ------------------------------------------------
    # We list models by scanning the SAGE OUTPUT directory (each subfolder
    # with a model_0.hdf5 is one model, named after the folder).  The .par
    # files are still used internally for tree paths but they are no longer
    # surfaced in the UI.
    # A lightcone is a single standalone cloud — there are no sibling SAGE
    # model folders to discover, so skip the scan (and the par-based paths,
    # which don't apply).
    if lightcone_path is not None:
        discovered = []
    else:
        primary_hdf5 = Path(scene.primary.cfg.hdf5_path)
        output_dir = primary_hdf5.parent.parent
        par_d = Path(par_dir) if par_dir else Path(par_path).parent
        discovered = find_models(output_dir, par_dir=par_d)
    # Index by model name for fast lookup
    discovered_by_name: dict[str, dict] = {m["name"]: m for m in discovered}

    # Per-box profile storage (Python side only; keys = model names).
    _profiles: dict = {}

    def _build_box_strip_items() -> list[dict]:
        """Build the reactive list for the viewport box strip."""
        strip = []
        pm = scene.primary
        s_lbl = pm.snap_table.label(max(0, pm.current_snap))
        strip.append(
            {
                "name": pm.name,
                "label": f"{pm.name}  {s_lbl}",
                "active": scene.active_box_name == pm.name,
                "primary": True,
            }
        )
        for adj_name in scene._adjacent_order:
            m = scene._models.get(adj_name)
            if m is None:
                continue
            al = m.snap_table.label(max(0, m.current_snap))
            strip.append(
                {
                    "name": adj_name,
                    "label": f"{adj_name}  {al}",
                    "active": scene.active_box_name == adj_name,
                    "primary": False,
                }
            )
        return strip

    def _build_models_list() -> list[dict]:
        """Build the reactive list of model entries for the menu."""
        loaded = {m.name: m for m in scene.list_models()}
        out = []
        for entry in discovered:
            name = entry["name"]
            is_loaded = name in loaded
            is_primary = name == scene.primary_name
            is_adjacent = is_loaded and scene.is_adjacent(name)
            compatible = is_loaded and scene.is_compatible_for_overlay(name)
            overlay_on = (
                is_loaded
                and not is_primary
                and not is_adjacent
                and loaded[name].visible
            )
            out.append(
                {
                    "name": name,
                    "path": str(entry["par"]),
                    "loaded": is_loaded,
                    "primary": is_primary,
                    "compatible": compatible,
                    "overlay": overlay_on,
                    "adjacent": is_adjacent,
                }
            )
        # Loaded-but-not-on-disk (e.g. primary model whose output dir wasn't scanned)
        for name, m in loaded.items():
            if not any(e["name"] == name for e in out):
                is_adjacent = scene.is_adjacent(name)
                out.append(
                    {
                        "name": name,
                        "path": str(m.path),
                        "loaded": True,
                        "primary": name == scene.primary_name,
                        "compatible": scene.is_compatible_for_overlay(name),
                        "overlay": m.visible
                        and name != scene.primary_name
                        and not is_adjacent,
                        "adjacent": is_adjacent,
                    }
                )
        return out

    server.state.models_list = _build_models_list()

    # ── Session models registry ─────────────────────────────────────────
    # Remember every model (box or lightcone) opened this session so the user
    # can jump back to any of them from the Launch dropdown.  Re-opening one
    # relaunches ViSAGE on it (like the wizard's own Explore/Visualize launch).
    from visage.utils import recent_models as _recent

    if lightcone_path is not None:
        _cur_kind = "lightcone"
        _cur_path = str(Path(lightcone_path).expanduser().resolve())
        _cur_name = Path(lightcone_path).stem
    else:
        _cur_kind = "box"
        _cur_path = (
            str(Path(par_path).expanduser().resolve()) if par_path else ""
        )
        _cur_name = scene.primary_name
    _sess_entries = (
        _recent.record(_cur_name, _cur_kind, _cur_path)
        if _cur_path
        else _recent.load()
    )
    server.state.session_models = [
        {
            "name": e.get("name", ""),
            "kind": e.get("kind", "box"),
            "path": e.get("path", ""),
            # Shown as the visible subtitle (full path is the hover tooltip)
            # so two entries with the same name/kind — e.g. two lightcones —
            # are actually distinguishable in the dropdown.
            "parent": str(Path(e.get("path", "")).parent),
            "active": e.get("kind") == _cur_kind
            and e.get("path") == _cur_path,
        }
        for e in _sess_entries
    ]

    @server.controller.set("open_recent_model")
    def _open_recent_model(path, kind):
        import os as _os, sys as _sys, shutil as _shutil

        argv = (
            ["--lightcone", str(path)]
            if kind == "lightcone"
            else ["--par", str(path)]
        ) + ["--port", str(port)]
        exe = _shutil.which("visage")
        if exe:
            _os.execv(exe, [exe, *argv])
        else:
            _os.execv(
                _sys.executable, [_sys.executable, "-m", "visage.cli", *argv]
            )

    server.state.active_box_name = scene.primary_name
    server.state.box_strip_items = []
    server.state.model_loading = False
    # Rotating quip shown on the "switching models" overlay. Updated by
    # an asyncio task that runs while model_loading is True.
    server.state.model_quip = "Switching models, please hold..."
    _MODEL_QUIPS: list[str] = [
        "Reticulating splines...",
        "Herding electrons into formation...",
        "Asking the universe nicely for the haloes...",
        "Spinning up galaxies — please don't shake the box.",
        "Negotiating with dark matter (it drives a hard bargain).",
        "Counting black holes... lost count.",
        "Convincing photons to travel faster. No luck.",
        "Reading SAGE bedtime stories to the trees...",
        "Stirring the cold gas. Gently.",
        "Polishing the CGM. Won't be long.",
        "Aligning angular momenta — close your eyes.",
        "Subhalo abundance matching the vibes...",
        "Hubble tension intensifies...",
        "Letting the H2 form on dust grains. Patience.",
        "Renormalizing the friend-of-friend friendships.",
        "Tracing merger trees — they're surprisingly deep.",
        "Reminding satellites who's central.",
        "Quenching star formation (sorry).",
        "Calibrating feedback — too much, less, more, less...",
        "Recomputing 1/H(z). Again.",
        "Reading the par file out loud, slowly.",
    ]

    async def _quip_loop():
        import asyncio as _asyncio
        import random as _random

        try:
            while bool(server.state.model_loading):
                server.state.model_quip = _random.choice(_MODEL_QUIPS)
                server.state.flush()
                await _asyncio.sleep(2.5)
        finally:
            server.state.model_quip = "Switching models, please hold..."
            server.state.flush()

    _quip_task: list = [None]

    @server.state.change("model_loading")
    def on_model_loading_change(model_loading, **_):
        import asyncio as _asyncio

        if model_loading:
            if _quip_task[0] is None or _quip_task[0].done():
                _quip_task[0] = _asyncio.ensure_future(_quip_loop())
        else:
            if _quip_task[0] is not None and not _quip_task[0].done():
                _quip_task[0].cancel()

    server.state.model_fields = scene.primary.fields_available
    server.state.primary_model = scene.primary.name
    # Snackbar for overlay-compatibility errors etc.
    server.state.notice_show = False
    server.state.notice_text = ""
    server.state.notice_color = "warning"
    server.state.notice_timeout = 4500

    # Update checker
    server.state.update_checking = False

    # Per-model flags used by static menu items (dict keyed by name)
    def _model_flags() -> dict:
        loaded = {m.name: m for m in scene.list_models()}
        out = {}
        for entry in discovered:
            n = entry["name"]
            is_adjacent = scene.is_adjacent(n) if n in loaded else False
            out[n] = {
                "primary": n == scene.primary.name,
                "loaded": n in loaded,
                "overlay": n in loaded
                and loaded[n].visible
                and n != scene.primary.name
                and not is_adjacent,
                "compatible": (
                    scene.is_compatible_for_overlay(n) if n in loaded else True
                ),
                "adjacent": is_adjacent,
            }
        return out

    server.state.model_flags = _model_flags()

    def _refresh_models_state() -> None:
        server.state.models_list = _build_models_list()
        server.state.model_fields = scene.primary.fields_available
        server.state.primary_model = scene.primary.name
        server.state.model_flags = _model_flags()
        server.state.box_strip_items = _build_box_strip_items()
        server.state.flush()

    scene.register_model_change_callback(_refresh_models_state)

    @server.controller.set("switch_model")
    async def on_switch_model(name: str):
        import asyncio

        # Capture the outgoing model's full UI state (filters, structure,
        # colormaps, opacity, visibility, snapshot) so it carries over to
        # the model we switch to.  Redshift — not the raw snap index — is
        # what we preserve, so models with different snapshot lists land on
        # the matching cosmic time rather than the matching slider position.
        carried = save_profile(server.state)
        old_table = scene.primary.snap_table
        cur_snap = int(carried.get("snap_num") or 0)
        cur_snap = max(0, min(cur_snap, old_table.count - 1))
        carried_z = old_table.snap_to_z(cur_snap)

        server.state.model_loading = True
        server.state.flush()
        await asyncio.sleep(
            0
        )  # yield so the browser receives model_loading=True
        try:
            if not scene.has_model(name):
                entry = discovered_by_name.get(name)
                if entry is None:
                    return
                scene.add_model(entry["par"])
            scene.switch_primary(name)
            # Preload all snapshots of the new primary in the background.
            scene.primary.loader.preload_all()
        finally:
            server.state.model_loading = False
            # Map the carried-over redshift onto the new model's snapshot
            # list (closest match), clamped to its valid range.
            new_max = scene.primary.snap_count - 1
            target_snap = scene.primary.snap_table.z_to_snap(carried_z)
            target_snap = max(0, min(target_snap, new_max))
            # Re-apply the carried settings to the new primary, with the
            # snapshot keys adjusted to the new model's range / matched z.
            carried["snap_num"] = target_snap
            carried["snap_max"] = new_max
            load_profile(server.state, carried)
            # dirty() forces the @state.change handlers to fire even when a
            # value is numerically unchanged, so every setting is re-applied
            # to the now-active (new primary) model's layers and filters.
            server.state.dirty(*BOX_PROFILE_KEYS)
            # Keep this model's stored profile in sync so a later
            # side-by-side activation restores the same carried-over state.
            _profiles[name] = save_profile(server.state)
            server.state.snap_label = scene.snap_label
            _refresh_models_state()
            server.state.flush()

    @server.controller.set("toggle_overlay")
    async def on_toggle_overlay(name: str):
        import asyncio

        server.state.model_loading = True
        server.state.flush()
        await asyncio.sleep(
            0
        )  # yield so the browser receives model_loading=True
        try:
            if not scene.has_model(name):
                entry = discovered_by_name.get(name)
                if entry is None:
                    return
                scene.add_model(entry["par"])
            model = scene._models[name]
            # Try the toggle; capture any compatibility error
            err = scene.set_overlay_visible(name, not model.visible)
            if err is not None:
                server.state.notice_text = err
                server.state.notice_color = "warning"
                server.state.notice_show = True
            elif model.visible:
                model.loader.preload_all()
        finally:
            server.state.model_loading = False
            _refresh_models_state()

    @server.controller.set("toggle_adjacent")
    async def on_toggle_adjacent(name: str):
        import asyncio

        entry = discovered_by_name.get(name)
        if entry is not None:
            par_path = entry["par"]
        elif scene.has_model(name):
            par_path = scene._models[name].path
        else:
            return
        server.state.model_loading = True
        server.state.flush()
        await asyncio.sleep(
            0
        )  # yield so the browser receives model_loading=True
        try:
            is_now_adj, err = scene.toggle_adjacent(par_path)
            if err:
                server.state.notice_text = err
                server.state.notice_color = "warning"
                server.state.notice_show = True
                return
            if is_now_adj:
                adj_m = scene._models.get(name)
                if adj_m and name not in _profiles:
                    _profiles[name] = default_profile(adj_m.snap_count)
                if adj_m:
                    adj_m.loader.preload_all()
                # Stop any active rotation — it can't be per-box with a shared camera
                if getattr(server.state, "rotate_mode", "off") != "off":
                    server.state.rotate_mode = "off"
                # Reframe to show all loaded boxes
                regions = [(0.0, 0.0, 0.0, scene.primary.box_size)]
                for adj_name in scene._adjacent_order:
                    m = scene._models.get(adj_name)
                    if m is not None:
                        off = m.offset
                        regions.append(
                            (
                                float(off[0]),
                                float(off[1]),
                                float(off[2]),
                                m.box_size,
                            )
                        )
                scene.camera.focus_on_boxes(regions)
            else:
                _profiles.pop(name, None)
                server.state.active_box_name = scene.active_box_name
        finally:
            server.state.model_loading = False
            server.state.box_strip_items = _build_box_strip_items()
            _refresh_models_state()
            if hasattr(server.controller, "view_update"):
                server.controller.view_update()

    @server.controller.set("set_active_box")
    def on_set_active_box(name: str):
        if not scene.has_model(name):
            return
        old_name = scene.active_box_name
        if old_name == name:
            return
        _profiles[old_name] = save_profile(server.state)
        scene.set_active_box(name)
        server.state.active_box_name = name
        incoming = _profiles.get(name)
        if incoming is None:
            m = scene._models.get(name)
            incoming = default_profile(m.snap_count) if m else {}
            _profiles[name] = incoming
        load_profile(server.state, incoming)
        server.state.dirty(*BOX_PROFILE_KEYS)
        server.state.box_strip_items = _build_box_strip_items()
        server.state.flush()
        if hasattr(server.controller, "sync_active_snap_count"):
            server.controller.sync_active_snap_count()
        if hasattr(server.controller, "view_update"):
            server.controller.view_update()

    @server.controller.set("clear_box")
    def on_clear_box(name: str):
        m = scene._models.get(name)
        if m is None:
            return
        fresh = default_profile(m.snap_count)
        _profiles[name] = fresh
        m.set_snapshot(m.snap_count - 1)
        m.halo_layer.set_filter_mask(None)
        m.galaxy_layer.set_filter_mask(None)
        if name == scene.active_box_name:
            load_profile(server.state, fresh)
            server.state.dirty(*BOX_PROFILE_KEYS)
            server.state.box_strip_items = _build_box_strip_items()
            server.state.flush()
        else:
            server.state.box_strip_items = _build_box_strip_items()
            server.state.flush()

    # ── Launch Mode wizard (embedded overlay) ────────────────────────────────
    from visage.wizard.controller import WizardController
    from visage.wizard.ui import build_wizard_ui
    from visage.wizard.pso_gallery import build_pso_gallery

    server.state.wiz_active = False

    _wiz_ctrl = WizardController(
        server,
        port=port,
        scene=scene,
        auto_start=False,
    )

    @server.controller.set("open_wizard")
    def _open_wizard():
        _wiz_ctrl.reset_and_start()
        server.state.wiz_active = True
        server.state.flush()

    @server.controller.set("open_sageswarm_wizard")
    def _open_sageswarm_wizard():
        _wiz_ctrl.reset_and_start(flow="sageswarm")
        server.state.wiz_active = True
        server.state.flush()

    @server.controller.set("open_sagelightcone_wizard")
    def _open_sagelightcone_wizard():
        _wiz_ctrl.reset_and_start(flow="sagelightcone")
        server.state.wiz_active = True
        server.state.flush()

    @server.controller.set("check_for_updates")
    async def _on_check_for_updates():
        import asyncio
        import json
        import sys
        import urllib.request

        from visage._version import __version__ as _current

        server.state.update_checking = True
        server.state.flush()
        await asyncio.sleep(0)

        loop = asyncio.get_event_loop()

        def _fetch_latest() -> str:
            import ssl

            try:
                import certifi

                ctx = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                ctx = ssl.create_default_context()
            try:
                with urllib.request.urlopen(
                    "https://pypi.org/pypi/sage-viewer/json",
                    timeout=8,
                    context=ctx,
                ) as r:
                    return json.loads(r.read())["info"]["version"]
            except ssl.SSLError:
                # macOS Python may lack system CA certs; retry unverified
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(
                    "https://pypi.org/pypi/sage-viewer/json",
                    timeout=8,
                    context=ctx,
                ) as r:
                    return json.loads(r.read())["info"]["version"]

        try:
            latest = await loop.run_in_executor(None, _fetch_latest)
        except Exception as exc:
            server.state.notice_text = f"Update check failed: {exc}"
            server.state.notice_color = "error"
            server.state.notice_timeout = 5000
            server.state.notice_show = True
            server.state.update_checking = False
            server.state.flush()
            return

        if latest == _current:
            server.state.notice_text = f"ViSAGE {_current} is up to date."
            server.state.notice_color = "success"
            server.state.notice_timeout = 4500
            server.state.notice_show = True
            server.state.update_checking = False
            server.state.flush()
            return

        server.state.notice_text = f"Updating {_current} → {latest}…"
        server.state.notice_color = "info"
        server.state.notice_timeout = -1
        server.state.notice_show = True
        server.state.flush()

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "sage-viewer",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                server.state.notice_text = (
                    f"Updated to {latest}. Restart ViSAGE to apply."
                )
                server.state.notice_color = "success"
                server.state.notice_timeout = -1
            else:
                server.state.notice_text = (
                    f"pip failed: {stderr.decode(errors='replace')[:140]}"
                )
                server.state.notice_color = "error"
                server.state.notice_timeout = 7000
        except Exception as exc:
            server.state.notice_text = f"Install failed: {exc}"
            server.state.notice_color = "error"
            server.state.notice_timeout = 7000

        server.state.notice_show = True
        server.state.update_checking = False
        server.state.flush()

    # `theme=("ui_theme",)` reactively binds the active Vuetify theme to
    # our state variable — Vuetify swaps the entire palette plus the root
    # `v-theme--<name>` class instantly when ui_theme changes.
    server.state.ui_theme = "dos_blue"
    with SinglePageLayout(
        server,
        full_height=True,
        vuetify_config=_vuetify_config,
        theme=("ui_theme",),
        style="background:#000000;",
    ) as layout:
        # Hide the SinglePageLayout's auto-built title — we render our own
        # later inside the toolbar so we can control its position relative
        # to the hamburger menu.
        layout.title.style = "display:none;"
        # Hide the default VAppBarNavIcon — replaced by our custom menu button below
        layout.icon.style = "display:none;"

        with layout.toolbar as tb:
            tb.density = "compact"
            tb.color = "#000000"
            tb.elevation = 0

            # ── Launch Mode button — wizard + models ───────────────────────
            with v3.VMenu(close_on_content_click=True):
                with v3.Template(v_slot_activator="{ props }"):
                    with v3.VBtn(
                        variant="text",
                        density="compact",
                        v_bind="props",
                        title="Launch Mode",
                        style="padding:2px 4px;min-width:36px;",
                    ):
                        html.Img(
                            src="/sage_static/SAGElogo.jpg",
                            style=(
                                "height:30px;width:30px;"
                                "object-fit:cover;border-radius:50%;"
                            ),
                        )
                with v3.VList(density="compact", bg_color="transparent"):
                    # ── Launch Mode ────────────────────────────────────────
                    v3.VListSubheader(
                        "LAUNCH MODE",
                        style="color:#06b6d4;font-size:0.65rem;",
                    )
                    v3.VListItem(
                        title="Setup Wizard",
                        prepend_icon="mdi-console",
                        click=server.controller.open_wizard,
                        color="cyan",
                        density="compact",
                    )
                    v3.VListItem(
                        title="SAGEswarm",
                        prepend_icon="mdi-chart-scatter-plot",
                        click=server.controller.open_sageswarm_wizard,
                        color="cyan",
                        density="compact",
                    )
                    v3.VListItem(
                        title="LightSAGE",
                        prepend_icon="mdi-telescope",
                        click=server.controller.open_sagelightcone_wizard,
                        color="cyan",
                        density="compact",
                    )
                    # ── Session models (boxes + lightcones loaded this
                    #    session; click to re-open one) ──────────────────────
                    v3.VDivider(
                        v_show=(
                            "session_models && session_models.length > 0",
                        ),
                        style="margin:4px 0;",
                    )
                    v3.VListSubheader(
                        "SESSION MODELS",
                        style="color:#06b6d4;font-size:0.65rem;",
                        v_show=(
                            "session_models && session_models.length > 0",
                        ),
                    )
                    with html.Div(
                        v_for=("m in session_models",),
                        key=("'sess-' + m.path",),
                        title=("m.path",),  # full path on hover
                    ):
                        v3.VListItem(
                            title=("m.name",),
                            subtitle=("m.parent",),
                            prepend_icon=(
                                "m.kind === 'lightcone' "
                                "? 'mdi-telescope' : 'mdi-cube-outline'",
                            ),
                            click=(
                                server.controller.open_recent_model,
                                "[m.path, m.kind]",
                            ),
                            active=("m.active",),
                            color="cyan",
                            density="compact",
                        )
                    v3.VDivider(style="margin:4px 0;")
                    # ── Models (switch rows) ───────────────────────────────
                    v3.VListSubheader(
                        "MODELS",
                        style="color:#06b6d4;font-size:0.65rem;",
                        v_show=("models_list && models_list.length > 0",),
                    )
                    with html.Div(
                        v_for=(
                            "m in [...models_list].sort("
                            "(a,b) => (b.primary ? 1 : 0) - (a.primary ? 1 : 0))",
                        ),
                        key=("'sw-' + m.name",),
                    ):
                        v3.VListItem(
                            title=("m.name",),
                            prepend_icon=(
                                "m.primary ? 'mdi-check-circle' : 'mdi-circle-outline'",
                            ),
                            click=(server.controller.switch_model, "[m.name]"),
                            active=("m.primary",),
                            color="cyan",
                            density="compact",
                        )
                    # ── Divider + overlay rows ─────────────────────────────
                    v3.VDivider(
                        v_show=("models_list && models_list.length > 1",),
                        style="margin:4px 0;",
                    )
                    v3.VListSubheader(
                        "OVERLAYS",
                        style="color:#9ca3af;font-size:0.65rem;",
                        v_show=("models_list && models_list.length > 1",),
                    )
                    with html.Div(
                        v_for=("m in models_list",),
                        key=("'ov-' + m.name",),
                        v_show=("!m.primary",),
                    ):
                        v3.VListItem(
                            title=(
                                "m.overlay ? '✓ ' + m.name : '+ ' + m.name",
                            ),
                            prepend_icon=(
                                "m.overlay ? 'mdi-layers' : 'mdi-layers-plus'",
                            ),
                            click=(
                                server.controller.toggle_overlay,
                                "[m.name]",
                            ),
                            active=("m.overlay",),
                            color="cyan",
                            density="compact",
                        )
                    # ── Side by side rows ─────────────────────────────────
                    v3.VDivider(
                        v_show=("models_list && models_list.length > 1",),
                        style="margin:4px 0;",
                    )
                    v3.VListSubheader(
                        "SIDE BY SIDE",
                        style="color:#06b6d4;font-size:0.65rem;",
                        v_show=("models_list && models_list.length > 1",),
                    )
                    with html.Div(
                        v_for=("m in models_list",),
                        key=("'sb-' + m.name",),
                        v_show=("!m.primary",),
                    ):
                        v3.VListItem(
                            title=(
                                "m.adjacent ? '✓ ' + m.name : '⊞ ' + m.name",
                            ),
                            prepend_icon=(
                                "m.adjacent "
                                "? 'mdi-check-circle-outline' "
                                ": 'mdi-view-split-vertical'",
                            ),
                            click=(
                                server.controller.toggle_adjacent,
                                "[m.name]",
                            ),
                            active=("m.adjacent",),
                            color="cyan",
                            density="compact",
                        )
                    # ── Close application ──────────────────────────────────
                    v3.VDivider(style="margin:4px 0;")
                    v3.VListItem(
                        title="Close Everything",
                        prepend_icon="mdi-close-box-outline",
                        click=server.controller.close_app,
                        color="#ef4444",
                        density="compact",
                    )

            # ── Explore Mode menu (hamburger) — tabs.  Sits right next to the
            #    Launch Mode button. ─────────────────────────────────────────
            with v3.VMenu(close_on_content_click=True):
                with v3.Template(v_slot_activator="{ props }"):
                    v3.VBtn(
                        icon="mdi-menu",
                        variant="text",
                        density="compact",
                        v_bind="props",
                        title="Tabs",
                        style="margin-left:2px;",
                    )
                with v3.VList(density="compact", bg_color="transparent"):
                    for label, value in _NAV_TABS:
                        v3.VListItem(
                            title=label,
                            value=value,
                            click=f"nav_active_tab = '{value}'",
                            active=(f"nav_active_tab === '{value}'",),
                            color="cyan",
                        )

            # ── SAGE26 setup button — the box (opens the SAGE26 setup
            #    wizard). ─────────────────────────────────────────────────
            v3.VBtn(
                icon="mdi-cube-outline",
                variant="text",
                density="compact",
                color="white",
                title="SAGE26 Setup",
                click=server.controller.open_wizard,
                style="margin-left:2px;",
            )

            # ── SAGEswarm button — opens the wizard straight into the PSO
            #    calibration flow. ───────────────────────────────────────────
            v3.VBtn(
                icon="mdi-chart-scatter-plot",
                variant="text",
                density="compact",
                color="white",
                title="SAGEswarm — PSO Calibration",
                click=server.controller.open_sageswarm_wizard,
                style="margin-left:2px;",
            )

            # ── LightSAGE button — opens the wizard straight into the
            #    lightcone-extraction flow. ────────────────────────────────
            v3.VBtn(
                icon="mdi-telescope",
                variant="text",
                density="compact",
                color="white",
                title="LightSAGE — Lightcone Extraction",
                click=server.controller.open_sagelightcone_wizard,
                style="margin-left:2px;",
            )

            # ── Export catalogue button ────────────────────────────────────
            v3.VBtn(
                icon="mdi-database-export-outline",
                variant="text",
                density="compact",
                color="white",
                title="Export galaxy catalogue",
                click="export_dialog_show = true",
                style="margin-left:4px;",
            )

            # ── Fly-through button ─────────────────────────────────────────
            v3.VBtn(
                icon="mdi-rotate-orbit",
                variant="text",
                density="compact",
                color=("flythrough_active ? 'cyan' : 'white'",),
                title="Fly-through: approach box then orbit (click to stop)",
                click=server.controller.toggle_flythrough,
                style="margin-left:2px;",
            )

            # ── Story Mode button + dropdown ───────────────────────────────
            build_story_button(server)

            # ── Check / install updates ────────────────────────────────────
            v3.VBtn(
                icon="mdi-update",
                variant="text",
                density="compact",
                color="white",
                title="Check for updates",
                loading=("update_checking",),
                click=server.controller.check_for_updates,
                style="margin-left:2px;",
            )

            # Title
            v3.VToolbarTitle(
                "ViSAGE",
                style="padding-left:4px;",
            )

            build_toolbar(server, scene)

        with layout.content:
            # Pixel-style monospace for the retro palettes — loaded via a
            # real <link> tag so the browser treats it as a normal external
            # stylesheet (works even when injected inside a Vue template).
            html.Link(
                rel="stylesheet",
                href=(
                    "https://fonts.googleapis.com/css2?"
                    "family=VT323&display=swap"
                ),
            )
            # Vuetify DOS-blue theme overrides are loaded via enable_module
            # (sage_static/sage_theme.css) — that's the only path that reliably
            # reaches html/body from inside a Trame/Vue template.
            html.Style(_THEME_CSS)

            # ── Story Mode playback overlay (hidden unless a story is active)
            build_story_hud(server)

            # ── Export catalogue dialog ────────────────────────────────────
            _SCOPE_ITEMS = [
                {"title": "Current Filters", "value": "filters"},
                {"title": "Target Galaxy", "value": "target"},
                {"title": "Group Members", "value": "group"},
                {"title": "Coords Sphere", "value": "coords"},
                {"title": "Box Region", "value": "box"},
            ]
            _FMT_ITEMS = [
                {"title": "CSV", "value": "csv"},
                {"title": "HDF5", "value": "hdf5"},
                {"title": "FITS", "value": "fits"},
                {"title": "TXT", "value": "txt"},
            ]
            with v3.VDialog(
                v_model=("export_dialog_show",),
                max_width=500,
                persistent=False,
            ):
                with v3.VCard(
                    style="background:transparent !important;border:1px solid #06b6d4;color:#e2e8f0;",
                    color="transparent",
                    elevation=0,
                    rounded=False,
                ):
                    with html.Div(
                        style=(
                            "display:flex;align-items:center;gap:8px;"
                            "padding:14px 16px 10px;"
                            "border-bottom:1px solid #374151;"
                        ),
                    ):
                        v3.VIcon(
                            "mdi-database-export-outline",
                            color="cyan",
                            size="small",
                        )
                        html.Span(
                            "Export Galaxy Catalogue",
                            style=(
                                "color:#06b6d4;font-weight:700;"
                                "letter-spacing:0.06em;font-size:0.95rem;"
                            ),
                        )
                        v3.VSpacer()
                        v3.VBtn(
                            icon="mdi-close",
                            size="x-small",
                            variant="text",
                            color="#9ca3af",
                            click="export_dialog_show = false",
                        )
                    with v3.VCardText(
                        style="padding:16px;display:flex;flex-direction:column;gap:14px;"
                    ):
                        # Scope
                        v3.VSelect(
                            v_model=("export_scope",),
                            items=(_SCOPE_ITEMS,),
                            label="Selection scope",
                            variant="outlined",
                            density="compact",
                            color="cyan",
                            bg_color="#0d0d1a",
                            hide_details=True,
                        )
                        # Format toggle
                        with html.Div(
                            style="display:flex;flex-direction:column;gap:4px;"
                        ):
                            html.Span(
                                "Format",
                                style="font-size:0.75rem;color:#9ca3af;",
                            )
                            with v3.VBtnToggle(
                                v_model=("export_format",),
                                mandatory=True,
                                variant="outlined",
                                density="compact",
                                color="cyan",
                                style="width:100%;",
                            ):
                                for _fi in _FMT_ITEMS:
                                    v3.VBtn(
                                        _fi["title"],
                                        value=_fi["value"],
                                        style="flex:1;font-family:monospace;background:#000000;",
                                    )
                        # Optional filename
                        v3.VTextField(
                            v_model=("export_filename",),
                            label="Filename (optional, no extension)",
                            variant="outlined",
                            density="compact",
                            color="cyan",
                            bg_color="#0d0d1a",
                            hide_details=True,
                            placeholder="auto-generated if blank",
                            style="font-family:monospace;",
                        )
                        # Status
                        with html.Div(
                            v_show=("export_status",),
                            style=(
                                "font-size:0.72rem;font-family:monospace;"
                                "background:#0d0d1a;padding:8px 10px;"
                                "border:1px solid #374151;word-break:break-all;"
                                "color:#9ca3af;"
                            ),
                        ):
                            html.Span("{{ export_status }}")
                    with v3.VCardActions(
                        style="padding:8px 16px 14px;gap:8px;justify-content:flex-end;"
                    ):
                        v3.VBtn(
                            "Close",
                            variant="text",
                            color="#9ca3af",
                            click="export_dialog_show = false",
                        )
                        v3.VBtn(
                            "Export",
                            variant="outlined",
                            color="cyan",
                            prepend_icon="mdi-export",
                            loading=("export_busy",),
                            disabled=("export_busy",),
                            click=server.controller.do_export,
                            style="font-family:monospace;",
                        )

            with v3.VSheet(
                classes="sage-content",
                style=(
                    "position:fixed;"
                    "top:var(--v-layout-top,48px);"
                    "left:var(--v-layout-left,0px);"
                    "right:var(--v-layout-right,0px);"
                    "bottom:var(--v-layout-bottom,36px);"
                    "display:flex;flex-direction:row;"
                    "overflow:hidden;"
                ),
                rounded=False,
                elevation=0,
                color="#0a0a0f",
            ):
                # ── Launch Mode wizard overlay ─────────────────────────────
                with html.Div(
                    v_show=("wiz_active",),
                    style=(
                        "position:absolute;inset:0;z-index:50;"
                        "background:#0a0a1a;overflow:hidden;"
                    ),
                ):
                    build_wizard_ui(server, _wiz_ctrl)

                # Live PSO plot gallery (right-docked; shown during a run)
                build_pso_gallery(server)

                # Render window + loading overlay
                with v3.VSheet(
                    style="position:relative;flex:1;height:100%;display:flex;min-width:0;",
                    color="transparent",
                    rounded=False,
                    elevation=0,
                ):
                    view = VtkRemoteView(
                        scene.plotter.ren_win,
                        style="flex:1;height:100%;display:block;min-width:0;",
                        # Closer to original quality settings — less dramatic
                        # interactive→still cycling on each click reduces
                        # visible "flash" re-renders.
                        # Full quality at all times — no resolution drop
                        # during camera drag.
                        interactive_ratio=1.0,
                        interactive_quality=100,
                        still_quality=100,
                    )
                    server.controller.view_update = view.update

                    # Story Mode text / equation overlays (over the render).
                    build_story_overlays(server)

                    # Pre-rendered playback overlay — shown only during
                    # playback, where it flips through the cached frames. While
                    # frames are being rendered the live view stays put (the
                    # progress shows in the toolbar chip instead).
                    # Opacity-driven (not v_show) so dropping it CROSSFADES to
                    # the live view underneath — the server always renders the
                    # staged scene before clearing playback_active, so the fade
                    # lands on matching content instead of a hard cut.
                    with html.Div(
                        style=(
                            "'position:absolute;inset:0;z-index:6;"
                            "background:#000;display:flex;"
                            "align-items:center;justify-content:center;"
                            "transition:opacity 0.35s ease;' + "
                            "(playback_active ? 'opacity:1;'"
                            " : 'opacity:0;pointer-events:none;')",
                        ),
                    ):
                        html.Img(
                            src=("playback_frame",),
                            style=(
                                "width:100%;height:100%;object-fit:contain;"
                                "display:block;"
                            ),
                        )

                    # Pop-out console — floats over the viewport, mirrors
                    # the active session's history. Toggle from the
                    # Console tab's "Pop-out" button. Drag-free for now;
                    # pinned to the bottom-left corner of the viewport.
                    with v3.VCard(
                        v_show=("console_popout_show",),
                        classes="sage-popout",
                        style=(
                            "position:absolute;left:24px;bottom:24px;"
                            "width:560px;min-width:240px;"
                            "height:360px;min-height:160px;"
                            "background:rgba(13,13,26,0.92);"
                            "border:1px solid #06b6d4;"
                            "box-shadow:0 0 18px rgba(6,182,212,0.30);"
                            "display:flex;flex-direction:column;"
                            "z-index:10;color:#e2e8f0;"
                            "resize:both;overflow:hidden;"
                        ),
                        elevation=0,
                        rounded=False,
                    ):
                        # Title bar — also the drag handle (cursor:move +
                        # ".sage-popout-handle" picked up by the global
                        # drag script).
                        with html.Div(
                            classes="sage-popout-handle",
                            style=(
                                "display:flex;align-items:center;"
                                "padding:4px 8px;gap:8px;"
                                "border-bottom:1px solid #1f2937;"
                                "flex-shrink:0;cursor:move;"
                                "user-select:none;"
                            ),
                        ):
                            html.Span(
                                "CONSOLE  (Console {{ console_active_id }})",
                                style=(
                                    "font-size:0.75rem;font-weight:700;"
                                    "letter-spacing:0.08em;color:#06b6d4;"
                                ),
                            )
                            v3.VSpacer()
                            v3.VBtn(
                                icon="mdi-fullscreen",
                                size="x-small",
                                variant="text",
                                color="#9ca3af",
                                classes="sage-popout-max-btn",
                            )
                            v3.VBtn(
                                icon="mdi-close",
                                size="x-small",
                                variant="text",
                                color="#9ca3af",
                                click=server.controller.console_toggle_popout,
                            )
                        # Terminal mode: xterm.js instance in the pop-out.
                        html.Div(
                            id=("'sage-pty-popout-' + console_active_id",),
                            v_show=("console_mode === 'terminal'",),
                            style=("flex:1 1 0;min-height:0;overflow:hidden;"),
                        )
                        # Command mode: mirrored history + input.
                        with v3.VSheet(
                            color="#0a0a0f",
                            classes="sage-console-scroll",
                            v_show=("console_mode === 'command'",),
                            style=(
                                "flex:1 1 0;min-height:0;overflow-y:auto;"
                                "padding:6px 10px;font-family:monospace;"
                                "font-size:0.72rem;line-height:1.4;"
                            ),
                        ):
                            with html.Div(
                                v_for=("entry in console_history",),
                                key=("'po-' + entry.id",),
                                style=(
                                    "padding:2px 0 4px;"
                                    "border-bottom:1px solid #1f2937;"
                                ),
                            ):
                                html.Div(
                                    "{{ entry.cmd }}",
                                    style=(
                                        "color:cyan;white-space:pre-wrap;"
                                        "font-family:monospace;"
                                    ),
                                )
                                html.Div(
                                    "{{ entry.out }}",
                                    style=(
                                        "color:#9ca3af;white-space:pre-wrap;"
                                    ),
                                )
                        with html.Div(
                            v_show=("console_mode === 'command'",),
                            style="padding:6px 8px;flex-shrink:0;",
                        ):
                            with html.Div(
                                raw_attrs=[
                                    'data-enter-click="btn-console-run"'
                                ],
                            ):
                                v3.VTextField(
                                    v_model=("console_input",),
                                    label="SAGE Commands",
                                    hide_details=True,
                                    variant="outlined",
                                    bg_color="#1a1a2e",
                                    density="compact",
                                    style="font-family:monospace;",
                                    keydown_enter=server.controller.console_submit,
                                )

                    # Snackbar for compatibility / status messages
                    v3.VSnackbar(
                        "{{ notice_text }}",
                        v_model=("notice_show",),
                        timeout=("notice_timeout",),
                        color=("notice_color",),
                        location="top",
                        contained=True,
                        style="margin-top:16px;",
                    )

                    # Galaxy info panel — draggable card; drag handle is
                    # the title bar (sage-popout-handle picked up by JS).
                    with v3.VCard(
                        v_show=(
                            "galinfo_show && nav_active_tab === 'target'",
                        ),
                        classes="sage-popout",
                        style=(
                            "position:absolute;top:32px;right:24px;"
                            "min-width:260px;max-width:320px;"
                            "background:rgba(17,24,39,0.85);"
                            "backdrop-filter:blur(6px);"
                            "border:1px solid #374151;"
                            "color:#e2e8f0;"
                            "z-index:5;"
                        ),
                        elevation=8,
                    ):
                        with html.Div(
                            classes="sage-popout-handle",
                            style=(
                                "display:flex;align-items:center;"
                                "font-size:0.85rem;letter-spacing:0.06em;"
                                "padding:10px 12px 6px;"
                                "cursor:move;user-select:none;"
                                "border-bottom:1px solid #1f2937;"
                            ),
                        ):
                            v3.VIcon(
                                "mdi-information-outline",
                                size="small",
                                color="cyan",
                                style="margin-right:6px;",
                            )
                            html.Span(
                                "Galaxy Information", style="color:#06b6d4;"
                            )
                            v3.VSpacer()
                            v3.VBtn(
                                icon="mdi-close",
                                size="x-small",
                                variant="text",
                                click=server.controller.hide_galaxy_info,
                            )
                        with v3.VCardText(
                            style="padding:8px 12px;font-size:0.72rem;",
                        ):
                            with html.Div(
                                v_for=("row in galinfo_items",),
                                key=("row.label",),
                                style=(
                                    "display:flex;justify-content:space-between;"
                                    "padding:3px 0;border-bottom:1px solid #1f2937;"
                                ),
                            ):
                                html.Span(
                                    "{{ row.label }}",
                                    style="color:#9ca3af;",
                                )
                                html.Span(
                                    "{{ row.value }}",
                                    style="font-family:monospace;text-align:right;color:#e2e8f0;",
                                )

                    # Group / cluster info panel — draggable, same initial
                    # position as the Galaxy info card (mutually exclusive).
                    with v3.VCard(
                        v_show=(
                            "groupinfo_show && nav_active_tab === 'environment'",
                        ),
                        classes="sage-popout",
                        style=(
                            "position:absolute;top:32px;right:24px;"
                            "min-width:260px;max-width:320px;"
                            "background:rgba(17,24,39,0.85);"
                            "backdrop-filter:blur(6px);"
                            "border:1px solid #374151;"
                            "color:#e2e8f0;"
                            "z-index:5;"
                        ),
                        elevation=8,
                    ):
                        with html.Div(
                            classes="sage-popout-handle",
                            style=(
                                "display:flex;align-items:center;"
                                "font-size:0.85rem;letter-spacing:0.06em;"
                                "padding:10px 12px 6px;"
                                "cursor:move;user-select:none;"
                                "border-bottom:1px solid #1f2937;"
                            ),
                        ):
                            v3.VIcon(
                                "mdi-account-group-outline",
                                size="small",
                                color="cyan",
                                style="margin-right:6px;",
                            )
                            html.Span(
                                "Group Information", style="color:#06b6d4;"
                            )
                            v3.VSpacer()
                            v3.VBtn(
                                icon="mdi-close",
                                size="x-small",
                                variant="text",
                                click=server.controller.hide_group_info,
                            )
                        with v3.VCardText(
                            style="padding:8px 12px;font-size:0.72rem;",
                        ):
                            with html.Div(
                                v_for=("row in groupinfo_items",),
                                key=("row.label",),
                                style=(
                                    "display:flex;justify-content:space-between;"
                                    "padding:3px 0;border-bottom:1px solid #1f2937;"
                                ),
                            ):
                                html.Span(
                                    "{{ row.label }}",
                                    style="color:#9ca3af;",
                                )
                                html.Span(
                                    "{{ row.value }}",
                                    style="font-family:monospace;text-align:right;color:#e2e8f0;",
                                )

                    # Library media pop-outs — one draggable card per open item,
                    # floating over the viewport just like the other sage-popout cards.
                    with v3.VCard(
                        v_for=("item in library_items",),
                        key=("item.id",),
                        classes="sage-popout",
                        style=(
                            "`position:absolute;"
                            "top:${item.top_px}px;"
                            "right:${item.right_px}px;"
                            "width:480px;min-width:240px;"
                            "height:380px;min-height:200px;"
                            "display:flex;flex-direction:column;"
                            "resize:both;overflow:hidden;"
                            "background:rgba(17,24,39,0.92);"
                            "backdrop-filter:blur(6px);"
                            "border:1px solid #374151;"
                            "color:#e2e8f0;"
                            # In Story Mode, lift library cards above the story
                            # overlay layer (z40) + HUD (z50) so opened items sit
                            # on top of the scene; normal-use layering unchanged.
                            "z-index:${story_active ? 60 : 5};`",
                        ),
                        elevation=8,
                    ):
                        with v3.VCardTitle(
                            classes="sage-popout-handle",
                            style=(
                                "display:flex;align-items:center;"
                                "font-size:0.85rem;letter-spacing:0.06em;"
                                "padding:10px 12px 6px;cursor:move;"
                                "flex-shrink:0;"
                            ),
                        ):
                            v3.VIcon(
                                "mdi-folder-multimedia-outline",
                                size="small",
                                color="cyan",
                                style="margin-right:6px;",
                            )
                            html.Span("{{ item.name }}")
                            v3.VSpacer()
                            v3.VBtn(
                                icon="mdi-fullscreen",
                                size="x-small",
                                variant="text",
                                classes="sage-popout-max-btn",
                            )
                            v3.VBtn(
                                icon="mdi-close",
                                size="x-small",
                                variant="text",
                                click=(
                                    server.controller.library_close_item,
                                    "[item.id]",
                                ),
                            )
                        v3.VDivider()
                        with v3.VCardText(
                            style=(
                                "padding:8px 12px;flex:1 1 0;min-height:0;"
                                "overflow:auto;display:flex;"
                                "align-items:center;justify-content:center;"
                            ),
                        ):
                            html.Img(
                                src=("item.data_url",),
                                v_if=("item.kind === 'image'",),
                                style=(
                                    "max-width:100%;max-height:100%;"
                                    "width:auto;height:auto;"
                                    "object-fit:contain;display:block;"
                                ),
                            )
                            html.Video(
                                src=("item.data_url",),
                                v_if=("item.kind === 'video'",),
                                controls=True,
                                autoplay=True,
                                muted=True,
                                loop=True,
                                style=(
                                    "max-width:100%;max-height:100%;"
                                    "width:auto;height:auto;"
                                    "object-fit:contain;display:block;"
                                ),
                            )

                    # Loading overlay shown while a model loads
                    with v3.VOverlay(
                        v_model=("model_loading",),
                        contained=True,
                        persistent=True,
                        classes="d-flex align-center justify-center",
                        scrim="rgba(0,0,0,0.78)",
                    ):
                        with v3.VSheet(
                            color="#1a1a2e",
                            style=(
                                "padding:40px 56px;border-radius:6px;"
                                "border:1px solid #06b6d4;"
                                "display:flex;flex-direction:column;align-items:center;"
                                "gap:18px;min-width:480px;max-width:640px;"
                                "box-shadow:0 0 24px rgba(6,182,212,0.35);"
                            ),
                        ):
                            v3.VLabel(
                                "SWITCHING MODELS, PLEASE HOLD…",
                                style=(
                                    "font-size:1.35rem;font-weight:700;"
                                    "letter-spacing:0.12em;color:#06b6d4;"
                                    "text-align:center;"
                                ),
                            )
                            v3.VProgressLinear(
                                indeterminate=True,
                                color="cyan",
                                height=4,
                                style="width:100%;",
                            )
                            v3.VLabel(
                                "{{ model_quip }}",
                                style=(
                                    "font-size:0.95rem;color:#e2e8f0;"
                                    "text-align:center;font-style:italic;"
                                    "min-height:1.4em;"
                                ),
                            )

                    # Box strip — shown when at least one adjacent box is loaded
                    with html.Div(
                        v_show=(
                            "box_strip_items && box_strip_items.length > 1",
                        ),
                        style=(
                            "position:absolute;bottom:0;left:0;right:0;"
                            "z-index:10;height:44px;"
                            "background:rgba(0,0,0,0.85);"
                            "display:flex;align-items:center;gap:6px;padding:0 10px;"
                            "border-top:1px solid rgba(255,255,255,0.08);"
                        ),
                    ):
                        with html.Div(
                            v_for=("b in box_strip_items",),
                            key=("'bs-' + b.name",),
                            click=(
                                server.controller.set_active_box,
                                "[b.name]",
                            ),
                            style=(
                                "b.active "
                                "? 'display:flex;align-items:center;gap:6px;"
                                "padding:4px 10px;border-radius:4px;cursor:pointer;"
                                "border:1px solid #00ffff;"
                                "background:rgba(0,255,255,0.08)' "
                                ": 'display:flex;align-items:center;gap:6px;"
                                "padding:4px 10px;border-radius:4px;cursor:pointer;"
                                "border:1px solid #374151'",
                            ),
                        ):
                            html.Span(
                                "{{ b.label }}",
                                style=(
                                    "b.active "
                                    "? 'color:#00ffff;font-weight:700;"
                                    "font-size:0.7rem;font-family:monospace' "
                                    ": 'color:#9ca3af;"
                                    "font-size:0.7rem;font-family:monospace'",
                                ),
                            )
                            v3.VBtn(
                                "CLR",
                                v_if=("!b.primary",),
                                size="x-small",
                                variant="text",
                                style="font-size:0.6rem;min-width:28px;color:#6b7280;",
                                click=(
                                    server.controller.clear_box,
                                    "[b.name]",
                                ),
                            )

                # Right panel — layers + navigation tabs. Fixed 300px flex
                # child. v_show lets a Story Mode scene hide it
                # (chrome.hide_panel); there is no general-use toggle.
                with v3.VSheet(
                    v_show=("!panels_hidden",),
                    style=(
                        "width:300px;min-width:300px;max-width:300px;"
                        "flex:0 0 300px;"
                        "height:100%;box-sizing:border-box;overflow:hidden;"
                    ),
                    color="#000000",
                    rounded=False,
                    elevation=0,
                ):
                    build_navigation_panel(server, scene)

        with layout.footer as footer:
            footer.height = 0
            footer.style = "display:none;"
            build_info_panel(server, scene)

    return server, scene
