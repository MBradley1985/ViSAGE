from __future__ import annotations

import asyncio
import math as _math
import pathlib

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visage.scene.scene import Scene

_FIELD = "padding:8px 0 4px;"
_BTN = "padding:8px 0 4px;"

# Full ordered lists; each entry may carry an optional "requires" key naming
# the model_fields flag that must be True for the mode to appear.
_HALO_MODES = [
    {"title": "Mvir", "value": "mvir"},
    {"title": "Rvir", "value": "rvir"},
    {"title": "Vvir", "value": "vvir"},
    {"title": "Vmax", "value": "vmax", "requires": "vmax"},
]

_GALAXY_MODES = [
    # Special / computed — always available
    {"title": "Structure", "value": "structure"},
    {"title": "Stellar Mass", "value": "stellar_mass"},
    {"title": "SFR", "value": "sfr"},
    {"title": "sSFR", "value": "ssfr"},
    {"title": "B / T", "value": "bt"},
    {"title": "Age", "value": "age", "requires": "mean_age"},
    {"title": "Type", "value": "type"},
    # Alphabetical — optional SAGE26 properties
    {"title": "BH Mass", "value": "bh_mass", "requires": "bh_mass"},
    {"title": "Bulge Mass", "value": "bulge_mass"},
    {
        "title": "Bulge Radius",
        "value": "bulge_radius",
        "requires": "bulge_radius",
    },
    {"title": "CGM Gas", "value": "cgm_gas", "requires": "cgm_gas"},
    {"title": "Cold Gas", "value": "cold_gas"},
    {"title": "Cooling", "value": "cooling", "requires": "cooling"},
    {
        "title": "Disk Radius",
        "value": "disk_radius",
        "requires": "disk_radius",
    },
    {
        "title": "Ejected Mass",
        "value": "ejected_mass",
        "requires": "ejected_mass",
    },
    {"title": "H1 Gas", "value": "h1_gas", "requires": "h1_gas"},
    {"title": "H2 Gas", "value": "h2_gas", "requires": "h2_mass"},
    {"title": "Heating", "value": "heating", "requires": "heating"},
    {"title": "Hot Gas", "value": "hot_gas", "requires": "hot_gas"},
    {"title": "ICS Mass", "value": "ics_mass", "requires": "ics_mass"},
    {
        "title": "Inst. Bulge Mass",
        "value": "instability_bulge_mass",
        "requires": "instability_bulge_mass",
    },
    {
        "title": "Inst. Bulge Rad",
        "value": "instability_bulge_radius",
        "requires": "instability_bulge_radius",
    },
    {
        "title": "Mass Loading",
        "value": "mass_loading",
        "requires": "mass_loading",
    },
    {
        "title": "Merger Bulge Mass",
        "value": "merger_bulge_mass",
        "requires": "merger_bulge_mass",
    },
    {
        "title": "Merger Bulge Rad",
        "value": "merger_bulge_radius",
        "requires": "merger_bulge_radius",
    },
    {
        "title": "Metals — Bulge",
        "value": "metals_bulge_mass",
        "requires": "metals_bulge_mass",
    },
    {
        "title": "Metals — CGM Gas",
        "value": "metals_cgm_gas",
        "requires": "metals_cgm_gas",
    },
    {
        "title": "Metals — Cold Gas",
        "value": "metals_cold_gas",
        "requires": "metals_cold_gas",
    },
    {
        "title": "Metals — Ejected",
        "value": "metals_ejected_mass",
        "requires": "metals_ejected_mass",
    },
    {
        "title": "Metals — Hot Gas",
        "value": "metals_hot_gas",
        "requires": "metals_hot_gas",
    },
    {"title": "Metals — ICS", "value": "metals_ics", "requires": "metals_ics"},
    {
        "title": "Metals — Stellar",
        "value": "metals_stellar_mass",
        "requires": "metals_stellar_mass",
    },
    {
        "title": "Outflow Rate",
        "value": "outflow_rate",
        "requires": "outflow_rate",
    },
    {"title": "SFR Bulge", "value": "sfr_bulge", "requires": "sfr_bulge"},
    {
        "title": "SFR Bulge Z",
        "value": "sfr_bulge_z",
        "requires": "sfr_bulge_z",
    },
    {"title": "SFR Disk", "value": "sfr_disk", "requires": "sfr_disk"},
    {"title": "SFR Disk Z", "value": "sfr_disk_z", "requires": "sfr_disk_z"},
]


def _filter_modes(mode_list: list[dict], fields: dict) -> list[dict]:
    """Return only modes whose required field is present (or have no requirement)."""
    return [m for m in mode_list if fields.get(m.get("requires", ""), True)]


_CMAPS = [
    # Sequential
    {"title": "Viridis", "value": "viridis"},
    {"title": "Plasma", "value": "plasma"},
    {"title": "Inferno", "value": "inferno"},
    {"title": "Magma", "value": "magma"},
    {"title": "Cividis", "value": "cividis"},
    {"title": "Turbo", "value": "turbo"},
    {"title": "Blues", "value": "Blues"},
    {"title": "Purples", "value": "Purples"},
    {"title": "Greens", "value": "Greens"},
    {"title": "Oranges", "value": "Oranges"},
    {"title": "Reds", "value": "Reds"},
    {"title": "Greys", "value": "Greys"},
    {"title": "YlOrRd", "value": "YlOrRd"},
    {"title": "YlGnBu", "value": "YlGnBu"},
    {"title": "BuPu", "value": "BuPu"},
    {"title": "Hot", "value": "hot"},
    {"title": "Cool", "value": "cool"},
    {"title": "Bone", "value": "bone"},
    {"title": "Copper", "value": "copper"},
    # Diverging
    {"title": "Coolwarm", "value": "coolwarm"},
    {"title": "RdBu", "value": "RdBu"},
    {"title": "Seismic", "value": "seismic"},
    {"title": "Spectral", "value": "Spectral"},
    {"title": "BrBG", "value": "BrBG"},
    # Cyclic / qualitative
    {"title": "Twilight", "value": "twilight"},
    {"title": "Jet", "value": "jet"},
    {"title": "Rainbow", "value": "rainbow"},
]


_HALO_CB = {
    "mvir": ("Mvir", "10^10", "10^15 Msun"),
    "rvir": ("Rvir", "0.03", "3 Mpc/h"),
    "vvir": ("Vvir", "30", "1000 km/s"),
    "vmax": ("Vmax", "30", "1000 km/s"),
}

_GAL_CB = {
    "stellar_mass": ("M*", "10^8", "10^12.5 Msun"),
    "ssfr": ("sSFR", "10^-14", "10^-6 yr^-1"),
    "sfr": ("SFR", "10^-3", "10^2 Msun/yr"),
    "cold_gas": ("Mgas", "10^7", "10^11.5 Msun"),
    "bt": ("B/T", "0", "1"),
    "bh_mass": ("Mbh", "10^4", "10^10 Msun"),
    "ics_mass": ("Mics", "10^6", "10^12 Msun"),
    "age": ("Age", "0", "14 Gyr"),
    "bulge_mass": ("Mbulge", "10^7", "10^12 Msun"),
    "type": ("Type", "Central", "Satellite"),
    # Gas / outflows
    "cgm_gas": ("Mcgm", "10^7", "10^12 Msun"),
    "h1_gas": ("MH1", "10^7", "10^12 Msun"),
    "h2_gas": ("MH2", "10^6", "10^11 Msun"),
    "hot_gas": ("Mhot", "10^7", "10^12 Msun"),
    "ejected_mass": ("Meject", "10^7", "10^12 Msun"),
    "outflow_rate": ("OutflowRate", "10^-6", "10^3 Msun/yr"),
    "mass_loading": ("Eta", "10^-2", "10^3"),
    "cooling": ("Cooling", "10^-5", "10^5"),
    "heating": ("Heating", "10^-5", "10^5"),
    # Structural
    "disk_radius": ("Rdisk", "10^-4", "1 Mpc/h"),
    "bulge_radius": ("Rbulge", "10^-4", "1 Mpc/h"),
    "merger_bulge_mass": ("Mmb", "10^6", "10^12 Msun"),
    "merger_bulge_radius": ("Rmb", "10^-4", "1 Mpc/h"),
    "instability_bulge_mass": ("Mib", "10^6", "10^12 Msun"),
    "instability_bulge_radius": ("Rib", "10^-4", "1 Mpc/h"),
    # SFR components
    "sfr_bulge": ("SFRbulge", "10^-6", "10^3 Msun/yr"),
    "sfr_disk": ("SFRdisk", "10^-6", "10^3 Msun/yr"),
    "sfr_bulge_z": ("SFRbulgeZ", "10^-6", "1"),
    "sfr_disk_z": ("SFRdiskZ", "10^-6", "1"),
    # Metals
    "metals_stellar_mass": ("Z*", "10^-2", "10^10 Msun"),
    "metals_bulge_mass": ("Zbulge", "10^-2", "10^10 Msun"),
    "metals_cold_gas": ("Zcold", "10^-2", "10^10 Msun"),
    "metals_hot_gas": ("Zhot", "10^-2", "10^10 Msun"),
    "metals_cgm_gas": ("Zcgm", "10^-2", "10^10 Msun"),
    "metals_ejected_mass": ("Zeject", "10^-2", "10^10 Msun"),
    "metals_ics": ("Zics", "10^-2", "10^10 Msun"),
}

# Default colormap applied when a colour-by property is selected.  The user
# can still pick any colormap afterwards; re-selecting a property snaps back
# to its default.  Missing entries fall back to viridis.
_HALO_CMAP_DEFAULTS = {
    "mvir": "viridis",
    "rvir": "cividis",
    "vvir": "plasma",
    "vmax": "plasma",
}

_GAL_CMAP_DEFAULTS = {
    "stellar_mass": "inferno",
    "sfr": "RdBu",
    "ssfr": "RdBu",
    "bt": "YlOrRd",
    "age": "YlOrRd",
    "type": "coolwarm",  # fixed — dropdown disabled in this mode
    "bh_mass": "cividis",
    "bulge_mass": "cividis",
    "bulge_radius": "cividis",
    "cgm_gas": "Greens",
    "cold_gas": "Blues",
    "cooling": "Blues",
    "ejected_mass": "inferno",
    "h1_gas": "turbo",
    "h2_gas": "Greens",
    "heating": "Reds",
    "hot_gas": "Reds",
    "ics_mass": "twilight",
    "mass_loading": "inferno",
    "metals_stellar_mass": "BrBG",
    "metals_bulge_mass": "BrBG",
    "metals_cold_gas": "BrBG",
    "metals_hot_gas": "BrBG",
    "metals_cgm_gas": "BrBG",
    "metals_ejected_mass": "BrBG",
    "metals_ics": "BrBG",
    "outflow_rate": "inferno",
    "sfr_bulge": "RdBu",
    "sfr_disk": "RdBu",
    "sfr_bulge_z": "RdBu",
    "sfr_disk_z": "RdBu",
}

_CBAR_BASE = "height:8px;flex:1;min-width:0;border-radius:2px;background:"


def _cbar_style(gradient: str) -> str:
    return _CBAR_BASE + gradient


def _sed_split_key(key: str) -> tuple[str, str]:
    """ "mag_rest_sdss_g" -> ("rest", "sdss_g"), "mag_obs_..." -> ("observed", ...)."""
    if key.startswith("mag_rest_"):
        return "rest", key[len("mag_rest_") :]
    if key.startswith("mag_obs_"):
        return "observed", key[len("mag_obs_") :]
    return "?", key


def _sed_short_label(filt: str) -> str:
    """ "sdss_g" -> "g", "2mass_j" -> "j", "galex_fuv" -> "fuv"."""
    for prefix in ("sdss_", "2mass_", "galex_", "wise_"):
        if filt.startswith(prefix):
            return filt[len(prefix) :]
    return filt.replace("_", " ")


def _sed_band_title(key: str) -> str:
    """ "mag_rest_sdss_g" -> "g (rest)", "mag_obs_2mass_j" -> "j (observed)"."""
    frame, filt = _sed_split_key(key)
    return f"{_sed_short_label(filt)} ({frame})"


def build_navigation_panel(server, scene: Scene) -> None:
    state, ctrl = server.state, server.controller

    # Navigation state
    state.nav_halo_idx = 0
    state.nav_gal_idx = 0
    state.nav_gal_last_radius = 10.0  # 10 Mpc/h — Target Go default
    state.nav_x = round(scene._cfg.box_size / 2, 2)
    state.nav_y = round(scene._cfg.box_size / 2, 2)
    state.nav_z = round(scene._cfg.box_size / 2, 2)
    state.nav_distance = 10.0  # 10 Mpc/h — Target/Environment standoff
    state.nav_box_xmin = 0.0
    state.nav_box_xmax = round(scene._cfg.box_size / 2, 2)
    state.nav_box_ymin = 0.0
    state.nav_box_ymax = round(scene._cfg.box_size / 2, 2)
    state.nav_box_zmin = 0.0
    state.nav_box_zmax = round(scene._cfg.box_size / 2, 2)
    state.focus_active = False
    state.nav_active_tab = "layers"
    state.draw_sphere_active = False  # interactive sphere widget in Coords tab
    state.draw_box_active = False  # interactive box widget in Box tab

    # Console — supports multiple parallel sessions. The state vars
    # below always reflect the *active* console; switching consoles
    # syncs them in/out of the per-session Python-side storage dict
    # (`_consoles_data`).
    state.console_input = ""
    state.console_history = []  # active console's history
    state.consoles_list = [{"id": 1, "title": "Console 1"}]
    state.console_active_id = 1
    state.console_popout_show = False
    state.pty_out_data = ""  # base64-encoded latest PTY output chunk
    state.pty_out_seq = 0  # monotonically increasing; JS polls this
    # PTY input relay — JS dispatches native input events to hidden <input> elements
    # bound to these state vars via v-model; that is the only reliable path from
    # external JS to @state.change handlers in Trame 3.
    state.pty_input_raw = ""  # "seq:cid:b64data" — set by JS onData
    state.pty_ensure_seq = 0  # incremented by JS after xterm.js mounts

    # Library
    state.library_files = []  # list of {"name", "path", "kind", "size_kb"}
    state.library_items = (
        []
    )  # open pop-outs: [{id, name, kind, data_url, top_px}]

    # Group info panel state (mirrors galinfo_*)
    state.groupinfo_show = False
    state.groupinfo_items = []

    # ── Filter state (log10 ranges where appropriate) ──────────
    # Halo filters
    state.filter_halo_mvir = [10.0, 15.0]  # log10 Msun
    state.filter_halo_rvir = [0.0, 3.0]  # Mpc/h (raw)
    state.filter_halo_vvir = [0.0, 1000.0]  # km/s   (raw)
    state.filter_halo_len = [0, 10000]  # particle count (raw)
    state.filter_halo_vmax = [0.0, 1000.0]  # km/s   (raw)
    state.filter_halo_conc = [0.0, 50.0]  # NFW concentration (raw)
    state.filter_halo_spin = [0.0, 0.2]  # spin parameter (raw)
    # Galaxy mass / rate filters
    state.filter_gal_smass = [0.0, 14.0]  # log10 Msun
    state.filter_gal_sfr = [-6.0, 5.0]  # log10 Msun/yr (-6 incl. quenched)
    state.filter_gal_ssfr = [-14.0, 0.0]  # log10 yr^-1
    state.filter_gal_coldgas = [0.0, 14.0]  # log10 Msun
    state.filter_gal_bulge = [0.0, 14.0]  # log10 Msun
    state.filter_gal_bt = [0.0, 1.0]  # bulge/total
    state.filter_gal_bhmass = [0.0, 14.0]  # log10 Msun
    state.filter_gal_ics = [0.0, 14.0]  # log10 Msun
    state.filter_gal_h2 = [0.0, 14.0]  # log10 Msun
    state.filter_gal_cgmgas = [0.0, 14.0]  # log10 Msun
    state.filter_gal_hotgas = [0.0, 14.0]  # log10 Msun
    state.filter_gal_h1gas = [0.0, 14.0]  # log10 Msun
    state.filter_gal_ejected = [0.0, 14.0]  # log10 Msun
    state.filter_gal_outflow = [-6.0, 5.0]  # log10 Msun/yr
    state.filter_gal_massload = [-3.0, 5.0]  # log10 dimensionless
    state.filter_gal_cooling = [-7.0, 7.0]  # log10 SAGE units
    state.filter_gal_heating = [-7.0, 7.0]  # log10 SAGE units
    # Galaxy structural
    state.filter_gal_diskrad = [-4.0, 1.0]  # log10 Mpc/h
    state.filter_gal_bulgerad = [-4.0, 1.0]  # log10 Mpc/h
    state.filter_gal_mb_mass = [0.0, 14.0]  # log10 Msun (merger bulge mass)
    state.filter_gal_mb_rad = [-4.0, 1.0]  # log10 Mpc/h (merger bulge radius)
    state.filter_gal_ib_mass = [
        0.0,
        14.0,
    ]  # log10 Msun (instability bulge mass)
    state.filter_gal_ib_rad = [
        -4.0,
        1.0,
    ]  # log10 Mpc/h (instability bulge radius)
    # SFR components
    state.filter_gal_sfr_bulge = [-6.0, 5.0]  # log10 Msun/yr
    state.filter_gal_sfr_disk = [-6.0, 5.0]  # log10 Msun/yr
    state.filter_gal_sfr_blg_z = [-6.0, 1.0]  # log10 dimensionless
    state.filter_gal_sfr_dsk_z = [-6.0, 1.0]  # log10 dimensionless
    # Metals
    state.filter_gal_met_cg = [-2.0, 12.0]  # log10 Msun (metals cold gas)
    state.filter_gal_met_sm = [-2.0, 12.0]  # log10 Msun (metals stellar)
    state.filter_gal_met_bm = [-2.0, 12.0]  # log10 Msun (metals bulge)
    state.filter_gal_met_hg = [-2.0, 12.0]  # log10 Msun (metals hot gas)
    state.filter_gal_met_em = [-2.0, 12.0]  # log10 Msun (metals ejected)
    state.filter_gal_met_ics = [-2.0, 12.0]  # log10 Msun (metals ICS)
    state.filter_gal_met_cgm = [-2.0, 12.0]  # log10 Msun (metals CGM)
    # Misc
    _snap_max = max(0, scene.primary.snap_table.count - 1)
    # Categoricals
    state.filter_gal_type = "both"  # both | central | satellite
    state.filter_gal_ffb = "any"  # any | yes | no   (FFBRegime)
    state.filter_gal_cgm = "any"  # any | cold | hot (Regime 0/1)
    # Environment categories — each checkbox toggles inclusion of that class.
    # When all four are checked the filter is a no-op (= "show all").
    state.env_show_field = True
    state.env_show_isolated = True
    state.env_show_pairs = True
    state.env_show_group = True
    state.env_show_cluster = True
    state.filter_gal_age = [0.0, 14.0]  # Gyr  (mass-weighted stellar age)

    # ── Galaxy info panel ──────────────────────────────────────
    state.galinfo_show = False
    state.galinfo_items = []  # list[{label, value}] for the panel

    # ── Record state ───────────────────────────────────────────
    state.recording_active = False
    state.recording_frames = 0
    state.recording_dir = ""
    state.last_screenshot = ""
    state.last_movie = ""
    state.movie_fps = 10
    state.movie_resolution = "native"  # native | hd | uhd
    state.movie_format = "gif"  # gif | mov | png
    state.screenshot_label = ""
    state.movie_label = ""
    state.movie_loop = True  # only used for GIF output

    # Colorbar state — full style strings to avoid Vue concatenation issues
    from visage.utils.colormap import cmap_css_gradient

    _h_label, _h_min, _h_max = _HALO_CB[scene.halo_layer.color_mode]
    _g_label, _g_min, _g_max = _GAL_CB.get(
        scene.galaxy_layer.color_mode, ("—", "—", "—")
    )
    state.halo_cbar_style = _cbar_style(
        cmap_css_gradient(scene.halo_layer.colormap)
    )
    state.halo_cbar_min = _h_min
    state.halo_cbar_max = _h_max
    state.gal_cbar_style = _cbar_style(
        cmap_css_gradient(scene.galaxy_layer.colormap)
    )
    state.gal_cbar_min = _g_min
    state.gal_cbar_max = _g_max

    # Layer state
    state.halos_visible = True
    state.galaxies_visible = True
    state.halo_opacity = scene.halo_layer.opacity
    state.galaxy_opacity = scene.galaxy_layer.opacity
    state.halo_color_mode = scene.halo_layer.color_mode
    state.galaxy_color_mode = scene.galaxy_layer.color_mode
    state.halo_colormap = scene.halo_layer.colormap
    state.galaxy_colormap = scene.galaxy_layer.colormap

    # ── Synthetic Photometry — its OWN independent layer (scene.sed_layer),
    #    shown in a dedicated Photometry tab (Lightcone Mode only). Completely
    #    separate from the galaxies: their own Visible/Opacity, so you can show
    #    photometry with the galaxies on, off, or on their own. When visible it
    #    paints a false-colour STACK of the ticked filter bands (each tinted
    #    its representative colour).
    state.photometry_visible = False
    state.photometry_opacity = 1.0
    state.sed_galaxy_bands = []  # ticked filter keys (multi-select stack)
    state.sed_legend = []  # [{title, color}] swatches for the ticked bands

    def _rebuild_color_mode_lists() -> None:
        fields = dict(scene.active_model.fields_available)
        sed_bands = getattr(scene.active_model, "sed_bands_available", [])
        # Each ticked item contributes its own representative colour to the
        # stack (multi-select). Items are raw filter bands (brightness) plus,
        # for rest-frame bands with a known solar magnitude, a mass-to-light
        # entry — all stackable together in any combination.
        from visage.sed.filters import SOLAR_ABSMAG_AB

        sed_modes = [
            {"title": _sed_band_title(k), "value": k} for k in sed_bands
        ]
        for k in sed_bands:
            frame, filt = _sed_split_key(k)
            if frame == "rest" and filt in SOLAR_ABSMAG_AB:
                sed_modes.append(
                    {
                        "title": f"M*/L ({_sed_short_label(filt)}, rest)",
                        "value": f"ml:{k}",
                    }
                )
        state.halo_color_modes = _filter_modes(_HALO_MODES, fields)
        # SED bands live only in the dedicated Synthetic Photometry section
        # below, not in the general "Colour by" dropdown.
        state.galaxy_color_modes = _filter_modes(_GALAXY_MODES, fields)
        state.sed_color_modes = sed_modes
        state.has_sed_data = bool(sed_modes)
        state.is_lightcone = scene.is_lightcone

    _rebuild_color_mode_lists()

    def _sed_legend(items: list) -> list:
        """Colour-swatch legend for the ticked stack items (name + CSS
        colour). Handles both filter bands and 'ml:'-prefixed M/L items."""
        from visage.sed.filters import band_colour

        out = []
        for item in items:
            is_ml = item.startswith("ml:")
            key = item[len("ml:") :] if is_ml else item
            filt = key
            for pre in ("mag_rest_", "mag_obs_"):
                if filt.startswith(pre):
                    filt = filt[len(pre) :]
                    break
            r, g, b = band_colour(filt)
            title = _sed_band_title(key)
            if is_ml:
                title = f"M*/L · {title}"
            out.append(
                {
                    "title": title,
                    "color": f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})",
                }
            )
        return out

    # Pre-tick the first band so the photometry layer has something to show
    # the moment it's switched on. The layer itself starts hidden (built in
    # LightconeModel with visible=False), so this doesn't change the initial
    # view — the galaxies keep their normal colouring.
    if state.has_sed_data and state.sed_color_modes:
        state.sed_galaxy_bands = [state.sed_color_modes[0]["value"]]
        state.sed_legend = _sed_legend(state.sed_galaxy_bands)

    def _push():
        if hasattr(server.controller, "view_update"):
            server.controller.view_update()

    def _focused() -> bool:
        return bool(state.focus_active)

    # ------------------------------------------------------------------
    # Filter recompute — runs whenever any filter changes OR snapshot changes
    # ------------------------------------------------------------------

    def _apply_filters() -> None:
        import numpy as np

        halos, galaxies = scene.active_model.loader.get(scene.current_snap)

        # Halo filters
        m_lo, m_hi = state.filter_halo_mvir
        r_lo, r_hi = state.filter_halo_rvir
        v_lo, v_hi = state.filter_halo_vvir

        h_mvir_log = np.log10(np.maximum(halos.masses, 1.0))
        h_mask = (
            (h_mvir_log >= float(m_lo))
            & (h_mvir_log <= float(m_hi))
            & (halos.rvir >= float(r_lo))
            & (halos.rvir <= float(r_hi))
            & (halos.vvir >= float(v_lo))
            & (halos.vvir <= float(v_hi))
        )
        full = (
            float(m_lo) <= 10.0 + 1e-6
            and float(m_hi) >= 15.0 - 1e-6
            and float(r_lo) <= 0.0 + 1e-6
            and float(r_hi) >= 3.0 - 1e-6
            and float(v_lo) <= 0.0 + 1e-6
            and float(v_hi) >= 1000.0 - 1e-6
        )
        if full:
            h_mask = None
        scene.halo_layer.set_filter_mask(h_mask)

        # Galaxy: stellar mass, sSFR, B/T, type
        if galaxies.count == 0:
            scene.galaxy_layer.set_filter_mask(None)
        else:
            g_mask = np.ones(galaxies.count, dtype=bool)

            # Each range filter is only applied when the slider has been moved off its
            # full-range default — at default every slider is a pass-through.
            def _active(lo, hi, mn, mx):
                """True when the slider has been moved away from its default extent."""
                return float(lo) > mn + 1e-6 or float(hi) < mx - 1e-6

            def _lg(x):
                return np.log10(np.maximum(x, 1.0))

            def _lgr(x):
                return np.log10(np.maximum(x, 1e-6))

            def _apply(lo, hi, arr, mn, mx):
                if _active(lo, hi, mn, mx):
                    g_mask.__iand__((arr >= float(lo)) & (arr <= float(hi)))

            def _apply_nz(lo, hi, raw, mn, mx):
                # Zero/negative raw values always pass (not "below range", just absent).
                if _active(lo, hi, mn, mx):
                    log_v = np.log10(np.maximum(raw, 1e-30))
                    g_mask.__iand__(
                        (raw <= 0)
                        | ((log_v >= float(lo)) & (log_v <= float(hi)))
                    )

            # ── Unconditional filters ──────────────────────────────────────────
            sm_lo, sm_hi = state.filter_gal_smass
            if _active(sm_lo, sm_hi, 0.0, 14.0):
                sm_log = np.log10(np.maximum(galaxies.stellar_mass, 1.0))
                g_mask &= (sm_log >= float(sm_lo)) & (sm_log <= float(sm_hi))

            sfr_lo, sfr_hi = state.filter_gal_sfr
            if _active(sfr_lo, sfr_hi, -6.0, 5.0):
                sfr_log = np.log10(np.maximum(galaxies.sfr, 1e-6))
                g_mask &= (sfr_log >= float(sfr_lo)) & (
                    sfr_log <= float(sfr_hi)
                )

            ss_lo, ss_hi = state.filter_gal_ssfr
            if _active(ss_lo, ss_hi, -14.0, 0.0):
                ssfr_log = np.log10(np.maximum(galaxies.ssfr, 1e-14))
                g_mask &= (ssfr_log >= float(ss_lo)) & (
                    ssfr_log <= float(ss_hi)
                )

            cg_lo, cg_hi = state.filter_gal_coldgas
            if _active(cg_lo, cg_hi, 0.0, 14.0):
                cg_log = np.log10(np.maximum(galaxies.cold_gas, 1.0))
                g_mask &= (cg_log >= float(cg_lo)) & (cg_log <= float(cg_hi))

            bm_lo, bm_hi = state.filter_gal_bulge
            if _active(bm_lo, bm_hi, 0.0, 14.0):
                bm_log = np.log10(np.maximum(galaxies.bulge_mass, 1.0))
                g_mask &= (bm_log >= float(bm_lo)) & (bm_log <= float(bm_hi))

            bt_lo, bt_hi = state.filter_gal_bt
            if _active(bt_lo, bt_hi, 0.0, 1.0):
                sm_safe = np.maximum(galaxies.stellar_mass, 1.0)
                # Clamp: SAGE can produce BulgeMass > StellarMass numerically.
                bt_c = np.clip(galaxies.bulge_mass / sm_safe, 0.0, 1.0)
                g_mask &= (bt_c >= float(bt_lo)) & (bt_c <= float(bt_hi))

            t = str(state.filter_gal_type)
            if t == "central":
                g_mask &= galaxies.gal_type == 0
            elif t == "satellite":
                g_mask &= galaxies.gal_type > 0

            fields = scene.active_model.fields_available

            # ── Conditional filters ────────────────────────────────────────────
            if fields.get("bh_mass", False):
                lo, hi = state.filter_gal_bhmass
                _apply(lo, hi, _lg(galaxies.bh_mass), 0.0, 14.0)

            if fields.get("ics_mass", False):
                lo, hi = state.filter_gal_ics
                _apply(lo, hi, _lg(galaxies.ics_mass), 0.0, 14.0)

            if fields.get("h2_mass", False):
                lo, hi = state.filter_gal_h2
                _apply(lo, hi, _lg(galaxies.h2_mass), 0.0, 14.0)

            if fields.get("cgm_gas", False):
                lo, hi = state.filter_gal_cgmgas
                _apply(lo, hi, _lg(galaxies.cgm_gas), 0.0, 14.0)

            if fields.get("hot_gas", False):
                lo, hi = state.filter_gal_hotgas
                _apply(lo, hi, _lg(galaxies.hot_gas), 0.0, 14.0)

            if fields.get("h1_gas", False):
                lo, hi = state.filter_gal_h1gas
                _apply(lo, hi, _lg(galaxies.h1_gas), 0.0, 14.0)

            if fields.get("ejected_mass", False):
                lo, hi = state.filter_gal_ejected
                _apply(lo, hi, _lg(galaxies.ejected_mass), 0.0, 14.0)

            if fields.get("outflow_rate", False):
                lo, hi = state.filter_gal_outflow
                _apply_nz(lo, hi, galaxies.outflow_rate, -6.0, 5.0)

            if fields.get("mass_loading", False):
                lo, hi = state.filter_gal_massload
                _apply_nz(lo, hi, galaxies.mass_loading, -3.0, 5.0)

            if fields.get("cooling", False):
                lo, hi = state.filter_gal_cooling
                _apply_nz(lo, hi, galaxies.cooling, -7.0, 7.0)

            if fields.get("heating", False):
                lo, hi = state.filter_gal_heating
                _apply_nz(lo, hi, galaxies.heating, -7.0, 7.0)

            if fields.get("disk_radius", False):
                lo, hi = state.filter_gal_diskrad
                _apply_nz(lo, hi, galaxies.disk_radius, -4.0, 1.0)

            if fields.get("bulge_radius", False):
                lo, hi = state.filter_gal_bulgerad
                _apply_nz(lo, hi, galaxies.bulge_radius, -4.0, 1.0)

            if fields.get("merger_bulge_mass", False):
                lo, hi = state.filter_gal_mb_mass
                _apply(lo, hi, _lg(galaxies.merger_bulge_mass), 0.0, 14.0)

            if fields.get("merger_bulge_radius", False):
                lo, hi = state.filter_gal_mb_rad
                _apply_nz(lo, hi, galaxies.merger_bulge_radius, -4.0, 1.0)

            if fields.get("instability_bulge_mass", False):
                lo, hi = state.filter_gal_ib_mass
                _apply(lo, hi, _lg(galaxies.instability_bulge_mass), 0.0, 14.0)

            if fields.get("instability_bulge_radius", False):
                lo, hi = state.filter_gal_ib_rad
                _apply_nz(lo, hi, galaxies.instability_bulge_radius, -4.0, 1.0)

            if fields.get("sfr_bulge", False):
                lo, hi = state.filter_gal_sfr_bulge
                _apply(lo, hi, _lgr(galaxies.sfr_bulge), -6.0, 5.0)

            if fields.get("sfr_disk", False):
                lo, hi = state.filter_gal_sfr_disk
                _apply(lo, hi, _lgr(galaxies.sfr_disk), -6.0, 5.0)

            if fields.get("sfr_bulge_z", False):
                lo, hi = state.filter_gal_sfr_blg_z
                _apply(lo, hi, _lgr(galaxies.sfr_bulge_z), -6.0, 1.0)

            if fields.get("sfr_disk_z", False):
                lo, hi = state.filter_gal_sfr_dsk_z
                _apply(lo, hi, _lgr(galaxies.sfr_disk_z), -6.0, 1.0)

            if fields.get("metals_cold_gas", False):
                lo, hi = state.filter_gal_met_cg
                _apply(lo, hi, _lg(galaxies.metals_cold_gas), -2.0, 12.0)

            if fields.get("metals_stellar_mass", False):
                lo, hi = state.filter_gal_met_sm
                _apply(lo, hi, _lg(galaxies.metals_stellar_mass), -2.0, 12.0)

            if fields.get("metals_bulge_mass", False):
                lo, hi = state.filter_gal_met_bm
                _apply(lo, hi, _lg(galaxies.metals_bulge_mass), -2.0, 12.0)

            if fields.get("metals_hot_gas", False):
                lo, hi = state.filter_gal_met_hg
                _apply(lo, hi, _lg(galaxies.metals_hot_gas), -2.0, 12.0)

            if fields.get("metals_ejected_mass", False):
                lo, hi = state.filter_gal_met_em
                _apply(lo, hi, _lg(galaxies.metals_ejected_mass), -2.0, 12.0)

            if fields.get("metals_ics", False):
                lo, hi = state.filter_gal_met_ics
                _apply(lo, hi, _lg(galaxies.metals_ics), -2.0, 12.0)

            if fields.get("metals_cgm_gas", False):
                lo, hi = state.filter_gal_met_cgm
                _apply(lo, hi, _lg(galaxies.metals_cgm_gas), -2.0, 12.0)

            if fields.get("ffb_regime", False):
                ffb = str(state.filter_gal_ffb)
                if ffb == "yes":
                    g_mask &= galaxies.ffb_regime != 0
                elif ffb == "no":
                    g_mask &= galaxies.ffb_regime == 0

            if fields.get("cgm_regime", False):
                cgm = str(state.filter_gal_cgm)
                if cgm == "cold":
                    g_mask &= galaxies.cgm_regime == 0
                elif cgm == "hot":
                    g_mask &= galaxies.cgm_regime == 1

            if fields.get("mean_age", False):
                age_lo, age_hi = state.filter_gal_age
                ages = galaxies.mean_age
                # 0-age galaxies are those with no SFH data — keep them visible
                # only when the slider includes 0 to avoid hiding everything.
                age_mask = (ages >= float(age_lo)) & (ages <= float(age_hi))
                if float(age_lo) > 0.0:
                    g_mask &= age_mask
                else:
                    g_mask &= (ages == 0) | age_mask

            # Environment categories — checkbox-driven; subset → mask
            show_f = bool(state.env_show_field)
            show_i = bool(state.env_show_isolated)
            show_p = bool(state.env_show_pairs)
            show_g = bool(state.env_show_group)
            show_c = bool(state.env_show_cluster)
            all_on = show_f and show_i and show_p and show_g and show_c
            if not all_on and fields.get("central_mvir", False):
                cm = galaxies.central_mvir
                log_cm = np.log10(np.maximum(cm, 1.0))
                cat_mask = np.zeros(galaxies.count, dtype=bool)
                if show_f:
                    cat_mask |= log_cm < 11.0
                if show_i:
                    cat_mask |= (log_cm >= 11.0) & (log_cm < 12.5)
                if show_p and fields.get("central_id", False):
                    # Use central_id (not central_mvir) for accurate FOF group count
                    _, _inv, _grp_sizes = np.unique(
                        galaxies.central_id,
                        return_inverse=True,
                        return_counts=True,
                    )
                    cat_mask |= _grp_sizes[_inv] == 2
                if show_g:
                    cat_mask |= (log_cm >= 12.5) & (log_cm < 14.0)
                if show_c:
                    cat_mask |= log_cm >= 14.0
                g_mask &= cat_mask

            scene.galaxy_layer.set_filter_mask(g_mask)

        _push()

    # Re-apply on every snapshot change (new data, masks must be rebuilt)
    scene.register_snap_change_callback(lambda _n: _apply_filters())

    @state.change(
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
        "env_show_field",
        "env_show_isolated",
        "env_show_pairs",
        "env_show_group",
        "env_show_cluster",
        "filter_gal_age",
    )
    def on_filter_change(**_):
        _apply_filters()

    @ctrl.set("reset_opacities")
    def on_reset_opacities():
        state.halo_opacity = 0.15
        state.galaxy_opacity = 1.0
        state.flush()

    @ctrl.set("reset_filters")
    def on_reset_filters():
        state.filter_halo_mvir = [10.0, 15.0]
        state.filter_halo_rvir = [0.0, 3.0]
        state.filter_halo_vvir = [0.0, 1000.0]
        state.filter_halo_len = [0, 10000]
        state.filter_halo_vmax = [0.0, 1000.0]
        state.filter_halo_conc = [0.0, 50.0]
        state.filter_halo_spin = [0.0, 0.2]
        state.filter_gal_smass = [0.0, 14.0]
        state.filter_gal_sfr = [-6.0, 5.0]
        state.filter_gal_ssfr = [-14.0, 0.0]
        state.filter_gal_coldgas = [0.0, 14.0]
        state.filter_gal_bulge = [0.0, 14.0]
        state.filter_gal_bt = [0.0, 1.0]
        state.filter_gal_type = "both"
        state.filter_gal_bhmass = [0.0, 14.0]
        state.filter_gal_ics = [0.0, 14.0]
        state.filter_gal_h2 = [0.0, 14.0]
        state.filter_gal_cgmgas = [0.0, 14.0]
        state.filter_gal_hotgas = [0.0, 14.0]
        state.filter_gal_h1gas = [0.0, 14.0]
        state.filter_gal_ejected = [0.0, 14.0]
        state.filter_gal_outflow = [-6.0, 5.0]
        state.filter_gal_massload = [-3.0, 5.0]
        state.filter_gal_cooling = [-7.0, 7.0]
        state.filter_gal_heating = [-7.0, 7.0]
        state.filter_gal_diskrad = [-4.0, 1.0]
        state.filter_gal_bulgerad = [-4.0, 1.0]
        state.filter_gal_mb_mass = [0.0, 14.0]
        state.filter_gal_mb_rad = [-4.0, 1.0]
        state.filter_gal_ib_mass = [0.0, 14.0]
        state.filter_gal_ib_rad = [-4.0, 1.0]
        state.filter_gal_sfr_bulge = [-6.0, 5.0]
        state.filter_gal_sfr_disk = [-6.0, 5.0]
        state.filter_gal_sfr_blg_z = [-6.0, 1.0]
        state.filter_gal_sfr_dsk_z = [-6.0, 1.0]
        state.filter_gal_met_cg = [-2.0, 12.0]
        state.filter_gal_met_sm = [-2.0, 12.0]
        state.filter_gal_met_bm = [-2.0, 12.0]
        state.filter_gal_met_hg = [-2.0, 12.0]
        state.filter_gal_met_em = [-2.0, 12.0]
        state.filter_gal_met_ics = [-2.0, 12.0]
        state.filter_gal_met_cgm = [-2.0, 12.0]
        state.filter_gal_ffb = "any"
        state.filter_gal_cgm = "any"
        state.env_show_field = True
        state.env_show_isolated = True
        state.env_show_pairs = True
        state.env_show_group = True
        state.env_show_cluster = True
        state.filter_gal_age = [0.0, 14.0]
        state.flush()

    # ------------------------------------------------------------------
    # Layer change handlers
    # ------------------------------------------------------------------

    @state.change("halos_visible")
    def on_halo_toggle(halos_visible, **_):
        scene.halo_layer.visible = bool(halos_visible)
        _push()

    @state.change("galaxies_visible")
    def on_galaxy_toggle(galaxies_visible, **_):
        scene.galaxy_layer.visible = bool(galaxies_visible)
        _push()

    @state.change("halo_opacity")
    def on_halo_opacity(halo_opacity, **_):
        scene.halo_layer.opacity = float(halo_opacity)
        _push()

    @state.change("galaxy_opacity")
    def on_galaxy_opacity(galaxy_opacity, **_):
        scene.galaxy_layer.opacity = float(galaxy_opacity)
        _push()

    @state.change("halo_color_mode")
    def on_halo_mode(halo_color_mode, **_):
        scene.halo_layer.color_mode = halo_color_mode
        # Snap to the property's default colormap — unless the same update
        # also set the colormap explicitly (story scenes, console commands).
        if "halo_colormap" not in state.modified_keys:
            state.halo_colormap = _HALO_CMAP_DEFAULTS.get(
                halo_color_mode, "viridis"
            )
        _, lo, hi = _HALO_CB[halo_color_mode]
        state.halo_cbar_min = lo
        state.halo_cbar_max = hi
        _push()

    def _sed_layer():
        """The photometry layer for the active model (None outside lightcones)."""
        return getattr(scene.active_model, "sed_layer", None)

    @state.change("photometry_visible")
    def on_photometry_visible(photometry_visible, **_):
        # Photometry is its own layer, but it's a distinct *view*: turning it
        # on hides the normal galaxies by default so the photometry image
        # reads cleanly (and turning it off brings them back). The user can
        # still re-enable galaxies manually to overlay both.
        layer = _sed_layer()
        if layer is not None:
            # Make sure the current stack is applied before showing it.
            bands = list(state.sed_galaxy_bands or [])
            if bands:
                layer.set_sed_bands(bands)
                layer.color_mode = "sedstack"
            layer.visible = bool(photometry_visible)
        # Swap the galaxies out for the photometry image (and back).
        state.galaxies_visible = not bool(photometry_visible)
        _push()

    @state.change("photometry_opacity")
    def on_photometry_opacity(photometry_opacity, **_):
        layer = _sed_layer()
        if layer is not None:
            layer.opacity = float(photometry_opacity)
        _push()

    @state.change("sed_galaxy_bands")
    def on_sed_bands(sed_galaxy_bands, **_):
        # Ticking/unticking filters restyles the stack legend and recomposites
        # the photometry layer (if it exists / is showing).
        bands = list(sed_galaxy_bands or [])
        state.sed_legend = _sed_legend(bands)
        layer = _sed_layer()
        if layer is not None and bands:
            layer.set_sed_bands(bands)
            layer.color_mode = "sedstack"
            _push()

    @state.change("galaxy_color_mode")
    def on_galaxy_mode(galaxy_color_mode, **_):
        scene.galaxy_layer.color_mode = galaxy_color_mode
        # Snap to the property's default colormap — unless the same update
        # also set the colormap explicitly (story scenes, console commands).
        # Structure mode has no colormap (dropdown disabled), so leave it.
        # Type is fixed at coolwarm (dropdown disabled), so always force it.
        if galaxy_color_mode == "type":
            state.galaxy_colormap = _GAL_CMAP_DEFAULTS["type"]
        elif (
            galaxy_color_mode != "structure"
            and "galaxy_colormap" not in state.modified_keys
        ):
            state.galaxy_colormap = _GAL_CMAP_DEFAULTS.get(
                galaxy_color_mode, "viridis"
            )
        if galaxy_color_mode in _GAL_CB:
            _, lo, hi = _GAL_CB[galaxy_color_mode]
        else:
            lo, hi = "—", "—"
        state.gal_cbar_min = lo
        state.gal_cbar_max = hi
        _push()

    @state.change("halo_colormap")
    def on_halo_cmap(halo_colormap, **_):
        scene.halo_layer.colormap = halo_colormap
        from visage.utils.colormap import cmap_css_gradient

        state.halo_cbar_style = _cbar_style(cmap_css_gradient(halo_colormap))
        _push()

    @state.change("galaxy_colormap")
    def on_galaxy_cmap(galaxy_colormap, **_):
        scene.galaxy_layer.colormap = galaxy_colormap
        from visage.utils.colormap import cmap_css_gradient

        state.gal_cbar_style = _cbar_style(cmap_css_gradient(galaxy_colormap))
        _push()

    # ------------------------------------------------------------------
    # Interactive draw-widget storage (one slot each; only one active at a time)
    # ------------------------------------------------------------------

    _draw_sphere_widget: list = [None]  # vtkSphereWidget or None
    _draw_sphere_actor: list = [None]  # custom 5-ring mesh actor or None
    _draw_box_widget: list = [None]  # vtkBoxWidget or None
    _box_cam_obs_tag: list = [None]  # (widget, w_tag, cam, cam_tag) or None
    _handle_world_r: list = [None]  # fixed world-space handle radius
    _box_handle_sources: list = [
        []
    ]  # vtkSphereSource objects for the 7 handle spheres

    def _remove_sphere_actor() -> None:
        if _draw_sphere_actor[0] is not None:
            try:
                scene.plotter.remove_actor(_draw_sphere_actor[0], render=False)
            except Exception:
                pass
            _draw_sphere_actor[0] = None

    # ------------------------------------------------------------------
    # Box widget handle sizing — keep handles world-space constant.
    #
    # PyVista uses vtkBoxWidget (not vtkBoxWidget2).  Internally, VTK
    # calls SizeHandles() (C++, not Python-accessible) on every Scale /
    # Translate interaction, which recomputes handle sphere radii based
    # on the CURRENT camera distance.  SetHandleSize() has no visual
    # effect in VTK 9.5 — it is not wired to the sphere geometry.
    #
    # Direct fix: capture the vtkSphereSource objects that back the 7
    # handle actors at placement time, snapshot their initial radius, and
    # restore it in an EndInteractionEvent observer (which fires AFTER
    # SizeHandles() but BEFORE the following Render()).  The camera
    # ModifiedEvent observer covers zoom changes for the same reason.
    # ------------------------------------------------------------------

    def _rescale_box_handles(*_) -> None:
        r = _handle_world_r[0]
        sources = _box_handle_sources[0]
        if r is None or not sources:
            return
        try:
            for src in sources:
                src.SetRadius(r)
                src.Modified()
        except Exception:
            pass

    def _attach_box_cam_observer(widget) -> None:
        w_tag = widget.AddObserver("EndInteractionEvent", _rescale_box_handles)
        cam = scene.plotter.renderer.GetActiveCamera()
        cam_tag = cam.AddObserver("ModifiedEvent", _rescale_box_handles)
        _box_cam_obs_tag[0] = (widget, w_tag, cam, cam_tag)

    def _detach_box_cam_observer() -> None:
        if _box_cam_obs_tag[0] is not None:
            widget, w_tag, cam, cam_tag = _box_cam_obs_tag[0]
            try:
                widget.RemoveObserver(w_tag)
            except Exception:
                pass
            try:
                cam.RemoveObserver(cam_tag)
            except Exception:
                pass
            _box_cam_obs_tag[0] = None
        _handle_world_r[0] = None
        _box_handle_sources[0] = []

    def _rebuild_sphere_rings(center, radius: float) -> None:
        """Draw 5 great-circle rings identical to _add_sphere_indicator."""
        import numpy as _np2
        import pyvista as _pv2

        _remove_sphere_actor()
        cx2 = float(center[0])
        cy2 = float(center[1])
        cz2 = float(center[2])
        r2 = max(0.01, float(radius))
        t = _np2.linspace(0.0, 2.0 * _np2.pi, 64, dtype=_np2.float64)
        c2, s2 = _np2.cos(t) * r2, _np2.sin(t) * r2
        rings = [
            _np2.column_stack([cx2 + c2, cy2 + s2, _np2.full_like(c2, cz2)])
        ]
        for deg in (0.0, 45.0, 90.0, 135.0):
            ca, sa = _np2.cos(_np2.deg2rad(deg)), _np2.sin(_np2.deg2rad(deg))
            rings.append(
                _np2.column_stack([cx2 + c2 * ca, cy2 + c2 * sa, cz2 + s2])
            )
        all_pts = _np2.vstack(rings)
        n = len(t)
        lines = []
        for i in range(len(rings)):
            lines.append(n + 1)
            lines.extend([i * n + j for j in range(n)])
            lines.append(i * n)
        poly = _pv2.PolyData(all_pts)
        poly.verts = _np2.empty(0, dtype=_np2.int64)
        poly.lines = _np2.array(lines, dtype=_np2.int64)
        _draw_sphere_actor[0] = scene.plotter.add_mesh(
            poly,
            color="cyan",
            opacity=0.9,
            line_width=2,
            style="wireframe",
            render_points_as_spheres=False,
            point_size=0,
        )
        try:
            _draw_sphere_actor[0].GetProperty().SetRenderPointsAsSpheres(False)
            _draw_sphere_actor[0].GetProperty().SetVertexVisibility(False)
            _draw_sphere_actor[0].GetProperty().SetPointSize(0)
        except Exception:
            pass

    def _clear_draw_widgets() -> None:
        """Remove any active interactive sphere/box widget and reset state."""
        if bool(state.draw_sphere_active):
            try:
                scene.plotter.clear_sphere_widgets()
            except Exception:
                pass
            _draw_sphere_widget[0] = None
            _remove_sphere_actor()
            state.draw_sphere_active = False
        if bool(state.draw_box_active):
            try:
                scene.plotter.clear_box_widgets()
            except Exception:
                pass
            _detach_box_cam_observer()
            _draw_box_widget[0] = None
            state.draw_box_active = False

    # Clear draw widgets whenever the primary model changes (world coords shift).
    scene.register_model_change_callback(_clear_draw_widgets)
    scene.register_model_change_callback(_rebuild_color_mode_lists)

    # ------------------------------------------------------------------
    # Navigation controllers
    # ------------------------------------------------------------------

    @ctrl.set("go_to_halo")
    def on_go_to_halo():
        try:
            idx = int(state.nav_halo_idx)
            d = float(state.nav_distance)
            scene.camera.go_to_halo(idx, d)
            # Always engage focus on Go (user can toggle it off afterwards)
            pos = scene.camera._halo_index.position_of(idx)
            scene.set_focus_sphere(
                (float(pos[0]), float(pos[1]), float(pos[2])), d
            )
            state.focus_active = True
        except Exception:
            pass
        _push()

    def _go_to_galaxy_at_radius(radius: float) -> None:
        try:
            state.nav_gal_last_radius = radius
            center = scene.camera.go_to_galaxy(int(state.nav_gal_idx), radius)
            if center != (0.0, 0.0, 0.0):
                scene.set_focus_sphere(center, radius)
                state.focus_active = True
        except Exception:
            pass
        _push()

    @ctrl.set("go_to_galaxy_1")
    def on_go_to_galaxy_1():
        _go_to_galaxy_at_radius(3.0)  # 3 Mpc/h

    @ctrl.set("go_to_galaxy_3")
    def on_go_to_galaxy_3():
        _go_to_galaxy_at_radius(5.0)  # 5 Mpc/h

    @ctrl.set("go_to_galaxy_5")
    def on_go_to_galaxy_5():
        _go_to_galaxy_at_radius(10.0)  # 10 Mpc/h

    @ctrl.set("go_to_galaxy_enter")
    def on_go_to_galaxy_enter():
        _go_to_galaxy_at_radius(float(state.nav_gal_last_radius))

    @ctrl.set("clear_indicator")
    def on_clear_indicator():
        scene.camera._clear_indicator()
        scene.camera._clear_member_indicators()
        state.galinfo_show = False
        state.galinfo_items = []
        state.groupinfo_show = False
        state.groupinfo_items = []
        state.flush()
        _push()

    # Keyboard fly movement (WASD / arrow keys). A held key is pressed/
    # released via the hidden cam-press-*/cam-release-* buttons; a single
    # server loop flies every currently-held direction each tick.
    #
    # Ghost-frame prevention (two layers):
    # 1. on_cam_release cancels the asyncio task immediately so the loop
    #    exits during either sleep rather than after a ghost fly() call.
    # 2. A 3 ms grace sleep before each fly() gives any in-flight keyup
    #    WebSocket message time to arrive and trigger the cancel before we
    #    commit to another movement step (localhost RTT ~1-2 ms).
    _held_dirs: set[str] = set()
    _fly_task: list = [None]

    async def _fly_loop():
        try:
            first_tick = True
            while True:
                if not first_tick:
                    # (A) Main sleep — cancel from on_cam_release fires here.
                    await asyncio.sleep(0.023)
                    # (B) Expensive sync ops run AFTER the cancel window, so a
                    # keyup that arrives during clip/push is queued and caught
                    # at the grace sleep (C) below — not after fly().
                    scene.plotter.renderer.ResetCameraClippingRange()

                # (C) Grace sleep — catches any keyup that arrived during (B)
                # or that was in-flight when (A) woke up (localhost RTT ~1-2 ms).
                await asyncio.sleep(0.010)
                if not _held_dirs:
                    break

                first_tick = False
                for d in list(_held_dirs):
                    if d in _held_dirs:
                        scene.camera.fly(d, step_frac=0.008)
                # Synchronous window is now only fly() + _push() (~1 ms total).
                _push()
        except asyncio.CancelledError:
            pass
        finally:
            _fly_task[0] = None

    @ctrl.set("cam_press")
    def on_cam_press(direction=None, **_):
        if not direction:
            return
        _held_dirs.add(str(direction))
        t = _fly_task[0]
        if t is None or t.done() or t.cancelled():
            _fly_task[0] = asyncio.ensure_future(_fly_loop())

    @ctrl.set("cam_release")
    def on_cam_release(direction=None, **_):
        _held_dirs.discard(str(direction))
        if not _held_dirs:
            # Cancel mid-sleep immediately — don't wait for the tick to finish.
            t = _fly_task[0]
            if t and not t.done():
                t.cancel()
            _push()  # confirm final stopped position to the client

    @ctrl.set("go_to_env_halo")
    def on_go_to_env_halo():
        """Fly to the chosen halo and snap nav_gal_idx to the FOF central there."""
        try:
            hidx = int(state.nav_halo_idx)
            d = float(state.nav_distance)
        except (TypeError, ValueError):
            return
        halos, galaxies = scene.active_model.loader.get(scene.current_snap)
        if hidx < 0 or hidx >= halos.count:
            return  # invalid halo index — silently bail
        try:
            halo_pos = scene.camera._halo_index.position_of(hidx)
        except Exception:
            return
        scene.camera.go_to_halo(hidx, d)
        # Resolve to nearest galaxy so Group Info / Highlight Members work
        import numpy as np

        if galaxies.count > 0:
            off = scene.active_model.offset
            d2 = np.sum(
                ((galaxies.positions + off) - np.array(halo_pos)) ** 2, axis=1
            )
            state.nav_gal_idx = int(np.argmin(d2))
        # Always engage focus on Go in the Environment tab
        scene.set_focus_sphere(
            (float(halo_pos[0]), float(halo_pos[1]), float(halo_pos[2])), d
        )
        state.focus_active = True
        state.flush()
        _push()

    @ctrl.set("show_galaxy_info")
    def on_show_galaxy_info():
        from visage.utils.galaxy_info import build_galaxy_info

        try:
            gidx = int(state.nav_gal_idx)
        except (TypeError, ValueError):
            return
        _, galaxies = scene.active_model.loader.get(scene.current_snap)
        if gidx < 0 or gidx >= galaxies.count:
            return

        # Show the info panel only — do NOT move the camera or change focus.
        info = build_galaxy_info(
            galaxies=galaxies,
            fields_available=scene.active_model.fields_available,
            idx=gidx,
            snap_table=scene._snap_table,
            hubble_h=scene._cfg.hubble_h,
        )
        state.galinfo_items = [
            {"label": k, "value": v} for k, v in info.items()
        ]
        state.galinfo_show = True
        # Close any other right-side overlay
        state.groupinfo_show = False
        state.flush()
        _push()

    @ctrl.set("hide_galaxy_info")
    def on_hide_galaxy_info():
        state.galinfo_show = False
        state.flush()

    def _find_central_pos_and_extent(galaxies, gidx) -> tuple:
        """Return (central_position, group_extent_mpch, central_idx_in_galaxies)."""
        import numpy as np
        from visage.utils.group_info import member_indices

        members = member_indices(galaxies, gidx)
        if len(members) == 0:
            return None, 0.0, -1
        pos = galaxies.positions[members]
        gt = galaxies.gal_type[members]
        # Prefer the type==0 central; fall back to the geometric centre
        central_mask = gt == 0
        if central_mask.any():
            central_idx_local = int(np.argmax(central_mask))
            central_pos = pos[central_idx_local]
            central_idx = int(members[central_idx_local])
        else:
            central_pos = pos.mean(axis=0)
            central_idx = -1
        extent = (
            float(np.linalg.norm(pos - central_pos, axis=1).max())
            if len(pos)
            else 0.0
        )
        return central_pos, extent, central_idx

    @ctrl.set("show_group_info")
    def on_show_group_info():
        from visage.utils.group_info import build_group_info
        import numpy as np

        try:
            gidx = int(state.nav_gal_idx)
        except (TypeError, ValueError):
            return
        _, galaxies = scene.active_model.loader.get(scene.current_snap)
        if gidx < 0 or gidx >= galaxies.count:
            return
        info = build_group_info(
            galaxies=galaxies,
            fields_available=scene.active_model.fields_available,
            idx=gidx,
            hubble_h=scene._cfg.hubble_h,
        )
        state.groupinfo_items = [
            {"label": k, "value": v} for k, v in info.items()
        ]
        state.groupinfo_show = True
        # Mutually exclusive with the other right-side overlays
        state.galinfo_show = False

        # Place the standard small red circle on the FOF central — same
        # indicator style used by the Galaxy info action.
        central_pos, _extent, _central_idx = _find_central_pos_and_extent(
            galaxies, gidx
        )
        if central_pos is not None:
            off = scene.active_model.offset
            scene.camera._add_circle_indicator(
                (
                    float(central_pos[0] + off[0]),
                    float(central_pos[1] + off[1]),
                    float(central_pos[2] + off[2]),
                ),
                0.0,
            )
        state.flush()
        _push()

    @ctrl.set("hide_group_info")
    def on_hide_group_info():
        state.groupinfo_show = False
        state.flush()
        _push()

    # ------------------------------------------------------------------
    # Export catalogue
    # ------------------------------------------------------------------

    state.export_dialog_show = False
    # lightcone|filters|target|group|coords|box  ("lightcone" only offered in
    # Lightcone Mode; default to it there so export works out of the box).
    state.export_scope = "lightcone" if scene.is_lightcone else "filters"
    state.export_scope_items = (
        [{"title": "Whole Lightcone", "value": "lightcone"}]
        if scene.is_lightcone
        else []
    ) + [
        {"title": "Current Filters", "value": "filters"},
        {"title": "Target Galaxy", "value": "target"},
        {"title": "Group Members", "value": "group"},
        {"title": "Coords Sphere", "value": "coords"},
        {"title": "Box Region", "value": "box"},
    ]
    state.export_format = "csv"  # csv|hdf5|fits|txt
    state.export_filename = ""  # optional custom stem
    state.export_status = ""  # last result path or error
    state.export_busy = False

    def _resolve_export_indices(scope: str) -> tuple:  # noqa: F821
        """Return (gal_indices_into_snapshot, scope_bounds_dict)."""
        import numpy as np

        _, galaxies = scene.active_model.loader.get(scene.current_snap)
        if galaxies.count == 0:
            raise ValueError("No galaxies loaded.")

        if scope == "lightcone":
            return (
                np.arange(galaxies.count, dtype=np.int64),
                {"lightcone": "all galaxies in the cone"},
            )

        if scope == "target":
            idx = int(state.nav_gal_idx)
            if idx < 0 or idx >= galaxies.count:
                raise ValueError(f"Target index {idx} out of range.")
            pos = galaxies.positions[idx]
            bounds = {
                "galaxy_index_in_snapshot": idx,
                "position_x_Mpch": np.format_float_positional(
                    float(pos[0]), unique=True, trim="-"
                ),
                "position_y_Mpch": np.format_float_positional(
                    float(pos[1]), unique=True, trim="-"
                ),
                "position_z_Mpch": np.format_float_positional(
                    float(pos[2]), unique=True, trim="-"
                ),
            }
            return np.array([idx], dtype=np.int64), bounds

        if scope == "group":
            from visage.utils.group_info import member_indices

            idx = int(state.nav_gal_idx)
            members = member_indices(galaxies, idx)
            if len(members) == 0:
                raise ValueError("No group members found for target galaxy.")
            central_pos = galaxies.positions[idx]
            bounds = {
                "central_galaxy_index_in_snapshot": idx,
                "n_members": len(members),
                "central_position_x_Mpch": np.format_float_positional(
                    float(central_pos[0]), unique=True, trim="-"
                ),
                "central_position_y_Mpch": np.format_float_positional(
                    float(central_pos[1]), unique=True, trim="-"
                ),
                "central_position_z_Mpch": np.format_float_positional(
                    float(central_pos[2]), unique=True, trim="-"
                ),
            }
            return members.astype(np.int64), bounds

        if scope == "coords":
            cx, cy, cz = (
                float(state.nav_x),
                float(state.nav_y),
                float(state.nav_z),
            )
            r = float(state.nav_distance)
            d2 = np.sum(
                (galaxies.positions - np.array([cx, cy, cz])) ** 2, axis=1
            )
            mask = d2 <= r * r
            if not mask.any():
                raise ValueError(
                    f"No galaxies within {r} Mpc/h of ({cx:.1f},{cy:.1f},{cz:.1f})."
                )
            bounds = {
                "sphere_center_x_Mpch": cx,
                "sphere_center_y_Mpch": cy,
                "sphere_center_z_Mpch": cz,
                "sphere_radius_Mpch": r,
            }
            return np.where(mask)[0].astype(np.int64), bounds

        if scope == "box":
            pos = galaxies.positions
            xmin, xmax = float(state.nav_box_xmin), float(state.nav_box_xmax)
            ymin, ymax = float(state.nav_box_ymin), float(state.nav_box_ymax)
            zmin, zmax = float(state.nav_box_zmin), float(state.nav_box_zmax)
            mask = (
                (pos[:, 0] >= xmin)
                & (pos[:, 0] <= xmax)
                & (pos[:, 1] >= ymin)
                & (pos[:, 1] <= ymax)
                & (pos[:, 2] >= zmin)
                & (pos[:, 2] <= zmax)
            )
            if not mask.any():
                raise ValueError("No galaxies within the current box bounds.")
            bounds = {
                "box_xmin_Mpch": xmin,
                "box_xmax_Mpch": xmax,
                "box_ymin_Mpch": ymin,
                "box_ymax_Mpch": ymax,
                "box_zmin_Mpch": zmin,
                "box_zmax_Mpch": zmax,
            }
            return np.where(mask)[0].astype(np.int64), bounds

        # default: "filters" — use the active filter mask on the galaxy layer
        fmask = scene.galaxy_layer._filter_mask
        if fmask is None:
            gal_indices = np.arange(galaxies.count, dtype=np.int64)
        else:
            gal_indices = np.where(fmask)[0].astype(np.int64)
        if len(gal_indices) == 0:
            raise ValueError("Filter mask excludes all galaxies.")
        bounds = {"filter_description": "Active galaxy filter tab settings"}
        return gal_indices, bounds

    _SCOPE_LABELS = {
        "lightcone": "Whole Lightcone",
        "filters": "Current Filters",
        "target": "Target Galaxy",
        "group": "Group Members",
        "coords": "Coords Sphere",
        "box": "Box Region",
    }

    @ctrl.set("do_export")
    async def on_do_export():
        import asyncio, pathlib, datetime

        scope = str(state.export_scope)
        fmt = str(state.export_format)
        stem = str(state.export_filename or "").strip()
        state.export_busy = True
        state.export_status = "Exporting…"
        state.flush()

        try:
            gal_indices, scope_bounds = _resolve_export_indices(scope)
            _, galaxies = scene.active_model.loader.get(scene.current_snap)
            sage_idx = galaxies.sage_indices[gal_indices]

            cfg = scene.primary.cfg
            snap_tbl = scene.primary.snap_table
            snap_num = scene.current_snap
            # A lightcone is a flat file (no Snap_N group); read its top-level
            # columns — which also include the synthetic-photometry mags —
            # straight from the cone source file rather than a SAGE snapshot.
            is_lc = scene.is_lightcone
            if is_lc:
                hdf5_path = getattr(scene.active_model, "path", cfg.hdf5_path)
            else:
                hdf5_path = cfg.hdf5_path
            snap_lbl = (
                str(state.snap_label)
                if hasattr(state, "snap_label")
                else f"snap{snap_num}"
            )

            out_dir = pathlib.Path.cwd() / "sage_outputs" / "catalogues"
            if not stem:
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                stem = f"catalogue_{scope}_{ts}"
            exts = {
                "csv": ".csv",
                "hdf5": ".h5",
                "fits": ".fits",
                "txt": ".txt",
            }
            out_path = out_dir / f"{stem}{exts.get(fmt, '.csv')}"

            from visage.utils.catalogue import write_catalogue

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: write_catalogue(
                    hdf5_path=hdf5_path,
                    snap_num=snap_num,
                    snap_label=snap_lbl,
                    sage_indices=sage_idx,
                    out_path=out_path,
                    fmt=fmt,
                    hubble_h=cfg.hubble_h,
                    scope_label=_SCOPE_LABELS.get(scope, scope),
                    scope_bounds=scope_bounds,
                    cfg=cfg,
                    snap_table=snap_tbl,
                    flat=is_lc,
                ),
            )
            n = len(sage_idx)
            state.export_status = f"✓ {n:,} galaxies → {result}"
        except Exception as exc:
            state.export_status = f"Error: {exc}"

        state.export_busy = False
        state.flush()

    # Auto-refresh whichever info card is open when the selection changes.
    @state.change("nav_gal_idx")
    def _refresh_info_on_selection(**_):
        if bool(state.galinfo_show):
            ctrl.show_galaxy_info()
        elif bool(state.groupinfo_show):
            ctrl.show_group_info()

    # Cache the last-highlighted set so re-toggling re-shows the SAME
    # positions even if the snapshot or nav_gal_idx have drifted in between.
    _highlight_cache: dict = {
        "positions": None,
        "regimes": None,
        "gidx": -1,
        "snap": -1,
        "central_idx": -1,
        "box_name": None,
    }

    @ctrl.set("highlight_group_members")
    def on_highlight_group_members():
        """Toggle: first click highlights members, second click clears them."""
        cam = scene.camera

        # Toggle off — but keep the cache so a third click reproduces the same
        # set of positions.
        if cam.has_member_indicators:
            cam._clear_member_indicators()
            _push()
            return

        import numpy as np
        from visage.utils.group_info import member_indices

        try:
            gidx = int(state.nav_gal_idx)
        except (TypeError, ValueError):
            return

        cur_snap = scene.current_snap
        cur_box = scene.active_box_name
        cached = (
            _highlight_cache["positions"] is not None
            and _highlight_cache["gidx"] == gidx
            and _highlight_cache["snap"] == cur_snap
            and _highlight_cache["box_name"] == cur_box
        )
        active = scene.active_model
        off = active.offset
        _, galaxies = active.loader.get(cur_snap)
        if not cached:
            if gidx < 0 or gidx >= galaxies.count:
                return
            members = member_indices(galaxies, gidx)
            if len(members) == 0:
                return
            # Find the FOF central (type 0); fall back to first member
            member_types = galaxies.gal_type[members]
            central_mask = member_types == 0
            central_idx = (
                int(members[np.argmax(central_mask)])
                if central_mask.any()
                else int(members[0])
            )
            # others excludes only the selected galaxy (central stays in for regime colouring)
            others = members[members != gidx]
            # Store world-space positions so indicators land on the correct box
            positions = (galaxies.positions[others] + off).copy()
            has_regime = scene.active_model.fields_available.get(
                "cgm_regime", False
            )
            regimes = (
                galaxies.cgm_regime[others].copy() if has_regime else None
            )
            _highlight_cache["positions"] = positions
            _highlight_cache["regimes"] = regimes
            _highlight_cache["gidx"] = gidx
            _highlight_cache["snap"] = cur_snap
            _highlight_cache["central_idx"] = central_idx
            _highlight_cache["box_name"] = cur_box

        central_idx = _highlight_cache["central_idx"]
        # Draw all members (including central) with regime colours
        cam._add_member_indicators(
            _highlight_cache["positions"],
            _highlight_cache["regimes"],
        )
        # Paint gold on top of the central's regime dot (larger point wins the depth fight)
        if 0 <= central_idx < galaxies.count and central_idx != gidx:
            cam._add_central_gold_indicator(
                galaxies.positions[central_idx] + off
            )
        # Selected galaxy: gold if it IS the central, else regime colour
        if 0 <= gidx < galaxies.count:
            if gidx == central_idx:
                cam._add_selected_indicator(
                    galaxies.positions[gidx] + off, color="gold"
                )
            else:
                has_regime = scene.active_model.fields_available.get(
                    "cgm_regime", False
                )
                regime = int(galaxies.cgm_regime[gidx]) if has_regime else None
                cam._add_selected_indicator(
                    galaxies.positions[gidx] + off, regime
                )
        _push()

    # ------------------------------------------------------------------
    # Record / screenshot controllers
    # ------------------------------------------------------------------

    _record_state: dict = {
        "active": False,
        "dir": None,
        "frames": 0,
        "cb": None,
        "fps": 10,
        "format": "gif",
        "scale": 1,
        "movie_base": "movie",
    }
    _session_state: dict = {"dir": None}

    _RES_SCALE = {"native": 1, "hd": 2, "uhd": 4}

    def _get_session_dir() -> pathlib.Path:
        """Lazily create one session folder per app launch."""
        import datetime

        if _session_state["dir"] is None:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            sess = _make_outdir("sage_outputs") / f"session_{ts}"
            sess.mkdir(parents=True, exist_ok=True)
            _session_state["dir"] = sess
        return _session_state["dir"]

    def _safe_label(label: str) -> str:
        """Sanitize a user-typed label into a safe filename fragment."""
        import re

        s = re.sub(r"[^\w\-]+", "_", str(label or "").strip())
        return s.strip("_")

    def _resolve_name(user_label: str, prefix: str) -> str:
        """Return '<prefix>_<label>' if labelled, else '<prefix>_<timestamp>'."""
        import datetime

        label = _safe_label(user_label)
        if label:
            return f"{prefix}_{label}"
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{ts}"

    def _capture_image(scale: int = 1):
        """Capture the current render window as a vtkImageData.

        Always renders at native resolution then PIL-upscales for scale > 1.
        Using vtkWindowToImageFilter.SetScale produces tiled rendering that
        leaves a visible grid seam at the tile boundaries in the output."""
        import vtk

        rw = scene.plotter.ren_win
        prev = rw.GetOffScreenRendering()
        rw.SetOffScreenRendering(1)
        try:
            rw.Render()
            w2i = vtk.vtkWindowToImageFilter()
            w2i.SetInput(rw)
            w2i.SetInputBufferTypeToRGB()
            w2i.ReadFrontBufferOff()
            w2i.Update()
            vimg = w2i.GetOutput()
            if scale <= 1:
                return vimg
            from vtkmodules.util.numpy_support import (
                vtk_to_numpy,
                numpy_to_vtk,
            )
            import numpy as _np2
            from PIL import Image as _PIL2

            w, h, _ = vimg.GetDimensions()
            arr = vtk_to_numpy(vimg.GetPointData().GetScalars()).reshape(
                h, w, 3
            )[::-1]
            try:
                _resample = _PIL2.Resampling.LANCZOS
            except AttributeError:
                _resample = _PIL2.LANCZOS
            up = _PIL2.fromarray(arr).resize((w * scale, h * scale), _resample)
            up_arr = _np2.asarray(up)[::-1].ravel().astype(_np2.uint8)
            vtk_data = numpy_to_vtk(
                up_arr, deep=True, array_type=vtk.VTK_UNSIGNED_CHAR
            )
            vtk_data.SetNumberOfComponents(3)
            out = vtk.vtkImageData()
            out.SetDimensions(w * scale, h * scale, 1)
            out.GetPointData().SetScalars(vtk_data)
            return out
        finally:
            rw.SetOffScreenRendering(prev)

    def _vtk_to_pil(scale: int = 1):
        """Return a PIL Image from the VTK render window (RGB, top-row first)."""
        from vtkmodules.util.numpy_support import vtk_to_numpy
        import numpy as _np2
        from PIL import Image as _PIL

        vimg = _capture_image(scale)
        w, h, _ = vimg.GetDimensions()
        arr = vtk_to_numpy(vimg.GetPointData().GetScalars()).reshape(h, w, 3)[
            ::-1
        ]
        return _PIL.fromarray(arr.astype(_np2.uint8), "RGB")

    def _vtk_to_pil_passive(scale: int = 1):
        """Read the last rendered framebuffer without forcing a re-render.

        Used for live recording so the capture loop doesn't inject extra
        Render() calls that would compete with interactive camera use.
        Reads the back buffer (which holds the last completed render).
        """
        import vtk
        from vtkmodules.util.numpy_support import vtk_to_numpy
        import numpy as _np2
        from PIL import Image as _PIL

        rw = scene.plotter.ren_win
        w2i = vtk.vtkWindowToImageFilter()
        w2i.SetInput(rw)
        w2i.SetInputBufferTypeToRGB()
        w2i.ReadFrontBufferOff()
        w2i.ShouldRerenderOff()
        w2i.Update()
        vimg = w2i.GetOutput()
        w, h, _ = vimg.GetDimensions()
        if w == 0 or h == 0:
            return _vtk_to_pil(scale)
        arr = vtk_to_numpy(vimg.GetPointData().GetScalars()).reshape(h, w, 3)[
            ::-1
        ]
        img = _PIL.fromarray(arr.astype(_np2.uint8), "RGB")
        if scale > 1:
            try:
                rs = _PIL.Resampling.LANCZOS
            except AttributeError:
                rs = _PIL.LANCZOS
            img = img.resize((w * scale, h * scale), rs)
        return img

    def _composite_overlays(pil_img):
        """Composite all visible HTML overlays: library cards, info panels, console pop-out."""
        lib_items = list(getattr(state, "library_items", []))
        if lib_items:
            pil_img = _draw_library_cards(pil_img, lib_items)
        # Galaxy Info — only visible when Target tab is active
        if (
            bool(getattr(state, "galinfo_show", False))
            and str(getattr(state, "nav_active_tab", "")) == "target"
        ):
            items = list(getattr(state, "galinfo_items", []))
            if items:
                pil_img = _draw_info_panel(
                    pil_img, items, "Galaxy Information"
                )
        # Group Info — only visible when Environment tab is active
        elif (
            bool(getattr(state, "groupinfo_show", False))
            and str(getattr(state, "nav_active_tab", "")) == "environment"
        ):
            items = list(getattr(state, "groupinfo_items", []))
            if items:
                pil_img = _draw_info_panel(pil_img, items, "Group Information")
        if bool(getattr(state, "console_popout_show", False)):
            pil_img = _draw_console_popout(pil_img)
        return pil_img

    # Backward-compat alias used by the screenshot path written earlier.
    _composite_console_overlay = _composite_overlays

    def _draw_library_cards(pil_img, items):
        """Paste open library image cards at top-right, matching the UI position."""
        import base64 as _b64, io as _bio2
        from PIL import Image as _PIL2, ImageDraw as _ID2, ImageFont as _IF2

        W, H = pil_img.size
        card_max_w = min(540, int(W * 0.50))
        right_pad = 24
        stagger = 44
        base = pil_img.convert("RGBA")
        try:
            _f = _IF2.truetype("/System/Library/Fonts/Helvetica.ttc", 11)
        except Exception:
            _f = _IF2.load_default()
        for i, item in enumerate(items):
            if item.get("kind") != "image":
                continue
            durl = item.get("data_url", "")
            if not durl.startswith("data:image"):
                continue
            try:
                raw = _b64.b64decode(durl.split(",", 1)[1])
                img = _PIL2.open(_bio2.BytesIO(raw)).convert("RGBA")
            except Exception:
                continue
            iw, ih = img.size
            if iw > card_max_w:
                ih = int(ih * card_max_w / iw)
                iw = card_max_w
                try:
                    rs = _PIL2.Resampling.LANCZOS
                except AttributeError:
                    rs = _PIL2.LANCZOS
                img = img.resize((iw, ih), rs)
            hdr, pad = 36, 8
            cw, ch = iw + pad * 2, ih + hdr + pad
            card = _PIL2.new("RGBA", (cw, ch), (17, 24, 39, 235))
            draw = _ID2.Draw(card)
            draw.rectangle(
                [0, 0, cw - 1, ch - 1], outline=(55, 65, 81), width=1
            )
            draw.rectangle([0, 0, cw - 1, hdr], fill=(26, 35, 53, 255))
            draw.text(
                (8, 10),
                (item.get("name") or "")[:50],
                fill=(226, 232, 240),
                font=_f,
            )
            card.paste(img, (pad, hdr + pad // 2), img)
            base.paste(
                card,
                (max(0, W - right_pad - cw), max(0, 32 + i * stagger)),
                card,
            )
        return base.convert("RGB")

    def _draw_console_popout(pil_img):
        """Draw the console pop-out onto *pil_img*.

        Matches the CSS: left:24, bottom:24, width≤560, height≤360."""
        from PIL import Image as _PIL, ImageDraw, ImageFont
        import platform

        W, H = pil_img.size
        pop_w = min(560, int(W * 0.60))
        pop_h = min(360, int(H * 0.55))
        pop_x = 24
        pop_y = max(0, H - 24 - pop_h)
        font_sz = 11
        try:
            if platform.system() == "Darwin":
                _font = ImageFont.truetype(
                    "/System/Library/Fonts/Supplemental/Courier New.ttf",
                    font_sz,
                )
            else:
                _font = ImageFont.truetype("DejaVuSansMono.ttf", font_sz)
        except Exception:
            _font = ImageFont.load_default()
        overlay = _PIL.new("RGBA", (pop_w, pop_h), (13, 13, 26, 235))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle(
            [0, 0, pop_w - 1, pop_h - 1], outline=(6, 182, 212), width=1
        )
        title_h = 26
        draw.rectangle([1, 1, pop_w - 2, title_h], fill=(20, 20, 45, 255))
        draw.line([1, title_h, pop_w - 2, title_h], fill=(31, 41, 55, 255))
        cid = getattr(state, "console_active_id", 1)
        draw.text(
            (8, 6), f"CONSOLE  (Console {cid})", fill=(6, 182, 212), font=_font
        )
        pad_x, pad_y = 8, title_h + 6
        line_h = font_sz + 3
        max_visible = max(1, (pop_h - pad_y - 4) // line_h)
        lines = []
        for entry in list(getattr(state, "console_history", [])):
            cmd = str(entry.get("cmd", "")).strip()
            out = str(entry.get("out", "")).strip()
            if cmd:
                lines.append((cmd, (6, 182, 212)))
            for ol in out.split("\n"):
                ol = ol.rstrip()
                if ol:
                    lines.append((ol, (156, 163, 175)))
        visible = lines[-max_visible:]
        for i, (text, color) in enumerate(visible):
            draw.text(
                (pad_x, pad_y + i * line_h), text, fill=color, font=_font
            )
        base = pil_img.convert("RGBA")
        base.paste(overlay, (pop_x, pop_y), overlay)
        return base.convert("RGB")

    def _draw_info_panel(pil_img, items, title):
        """Composite a Galaxy Info or Group Info card at the top-right corner.

        Matches the UI card CSS: right:24px, top:32px, width 260-320px."""
        from PIL import Image as _PIL, ImageDraw, ImageFont
        import platform

        W, H = pil_img.size
        row_h = 18
        title_h = 30
        pad = 8
        gap = 16  # minimum gap between the label and value columns
        font_sz = 11
        try:
            if platform.system() == "Darwin":
                _lf = ImageFont.truetype(
                    "/System/Library/Fonts/Helvetica.ttc", font_sz
                )
                _vf = ImageFont.truetype(
                    "/System/Library/Fonts/Supplemental/Courier New.ttf",
                    font_sz,
                )
            else:
                try:
                    _lf = ImageFont.truetype("DejaVuSans.ttf", font_sz)
                    _vf = ImageFont.truetype("DejaVuSansMono.ttf", font_sz)
                except Exception:
                    _lf = ImageFont.load_default()
                    _vf = _lf
        except Exception:
            _lf = ImageFont.load_default()
            _vf = _lf
        # Size the panel to its content so nothing collides or gets clipped
        # in recordings (the label is left-aligned, the value right-aligned,
        # so a fixed width let long rows overlap). Width = widest
        # label+gap+value row, capped to the frame; height grows with rows.
        _meas = ImageDraw.Draw(_PIL.new("RGB", (1, 1)))

        def _text_w(text, font):
            try:
                b = _meas.textbbox((0, 0), text, font=font)
                return b[2] - b[0]
            except (AttributeError, TypeError):
                return int(len(text) * font_sz * 0.6)

        content_w = _text_w("i  " + title, _lf)
        for row in items:
            lw = _text_w(str(row.get("label", "")), _lf)
            vw = _text_w(str(row.get("value", "")), _vf)
            content_w = max(content_w, lw + gap + vw)
        pan_w = int(min(W - 48, max(260, content_w + pad * 2)))
        n_rows = max(1, len(items))
        pan_h = title_h + pad // 2 + n_rows * row_h + pad
        pan_x = W - 24 - pan_w
        pan_y = 32
        overlay = _PIL.new("RGBA", (pan_w, pan_h), (17, 24, 39, 216))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle(
            [0, 0, pan_w - 1, pan_h - 1], outline=(55, 65, 81), width=1
        )
        draw.rectangle([1, 1, pan_w - 2, title_h - 1], fill=(20, 20, 45, 255))
        draw.line(
            [1, title_h - 1, pan_w - 2, title_h - 1], fill=(31, 41, 55, 255)
        )
        ty = (title_h - font_sz) // 2
        draw.text((pad, ty), "i", fill=(6, 182, 212), font=_lf)
        draw.text((pad + 14, ty), title, fill=(6, 182, 212), font=_lf)
        y = title_h + pad // 2
        for row in items:
            label = str(row.get("label", ""))
            value = str(row.get("value", ""))
            draw.text((pad, y), label, fill=(156, 163, 175), font=_lf)
            try:
                bbox = draw.textbbox((0, 0), value, font=_vf)
                val_w = bbox[2] - bbox[0]
            except AttributeError:
                val_w = int(len(value) * font_sz * 0.6)
            draw.text(
                (pan_w - pad - val_w, y), value, fill=(226, 232, 240), font=_vf
            )
            y += row_h
            if y + row_h > pan_h:
                break
        base = pil_img.convert("RGBA")
        base.paste(overlay, (pan_x, pan_y), overlay)
        return base.convert("RGB")

    def _save_image(image, path) -> None:
        """Write a vtkImageData to disk; format inferred from extension."""
        import vtk

        ext = str(path).lower().rsplit(".", 1)[-1]
        if ext in ("jpg", "jpeg"):
            writer = vtk.vtkJPEGWriter()
            writer.SetQuality(95)
        elif ext in ("tif", "tiff"):
            writer = vtk.vtkTIFFWriter()
        else:
            writer = vtk.vtkPNGWriter()
        writer.SetFileName(str(path))
        writer.SetInputData(image)
        writer.Write()

    def _make_outdir(sub: str) -> pathlib.Path:
        outdir = pathlib.Path.cwd() / sub
        outdir.mkdir(parents=True, exist_ok=True)
        return outdir

    def _take_screenshot(ext: str) -> None:
        try:
            sess = _get_session_dir()
            name = _resolve_name(state.screenshot_label, "screenshot")
            path = sess / f"{name}.{ext}"
            if path.exists():
                import datetime

                ts = datetime.datetime.now().strftime("%H%M%S")
                path = sess / f"{name}_{ts}.{ext}"
            pb_active = bool(getattr(state, "playback_active", False))
            pf = str(getattr(state, "playback_frame", "") or "")
            if pb_active and pf.startswith("data:image"):
                import base64
                import io as _io
                from PIL import Image as _PIL

                raw = base64.b64decode(pf.split(",", 1)[1])
                pil = _PIL.open(_io.BytesIO(raw)).convert("RGB")
            else:
                pil = _vtk_to_pil(scale=1)
            pil = _composite_console_overlay(pil)
            ext_out = str(path).lower().rsplit(".", 1)[-1]
            if ext_out in ("jpg", "jpeg"):
                pil.save(str(path), "JPEG", quality=95)
            elif ext_out in ("tif", "tiff"):
                pil.save(str(path), "TIFF")
            else:
                pil.save(str(path), "PNG")
            state.last_screenshot = str(path)
        except Exception as e:
            state.last_screenshot = f"ERROR: {e!s}"
        state.flush()

    @ctrl.set("take_screenshot")
    def on_take_screenshot():
        _take_screenshot("png")

    @ctrl.set("screenshot_png")
    def on_screenshot_png():
        _take_screenshot("png")

    @ctrl.set("screenshot_jpg")
    def on_screenshot_jpg():
        _take_screenshot("jpg")

    @ctrl.set("screenshot_tiff")
    def on_screenshot_tiff():
        _take_screenshot("tiff")

    # ------------------------------------------------------------------
    # Recording — PNG frames during playback, finalized to GIF/MOV at stop
    # ------------------------------------------------------------------

    _record_task: list = [None]  # asyncio.Task | None

    async def _record_loop():
        """Capture frames for recording.

        PLAYBACK MODE
        -------------
        Reads state.playback_frame — the pre-rendered JPEG the overlay is
        already showing — and writes frames_per_snap copies each time the
        snap advances.  No VTK rendering, no scene.set_snapshot(), zero
        asyncio blocking.  Speed and FPS settings produce exact frame counts:

            frames_per_snap = round(movie_fps / (3.0 * play_speed))

        The pre-rendered frames already have rotation baked in by
        _render_frames(), so rotation is consistent with the overlay.

        LIVE MODE  (no playback active)
        --------------------------------
        Unchanged: passive capture with no rotation, or force-render with
        rotation.  This path is confirmed smooth and is not modified.
        """
        import asyncio, base64 as _b64, io as _io
        import numpy as _np_rec

        movie_fps = max(1, int(_record_state["fps"]))
        record_interval = 1.0 / movie_fps

        def _step_rotation(mode: str, dt: float) -> None:
            parts = mode.split("_")
            sign = 1.0 if parts[0] == "cw" else -1.0
            dps = float(parts[1])
            delta = sign * dps * dt
            cam = scene.plotter.camera
            focal = _np_rec.array(cam.focal_point, dtype=_np_rec.float64)
            pos = _np_rec.array(cam.position, dtype=_np_rec.float64)
            r = pos - focal
            ang = _np_rec.deg2rad(delta)
            c, s = _np_rec.cos(ang), _np_rec.sin(ang)
            rm = _np_rec.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
            cam.position = tuple(focal + rm @ r)
            cam.up = (0.0, 1.0, 0.0)

        # Playback-recording state
        _last_pb_snap: list[int | None] = [None]
        _pb_end_snap: list[int | None] = [None]
        _pb_at_end: list[bool] = [False]
        _pb_done: bool = False

        # ── Live-mode frame writer (VTK capture) ──────────────────────────
        def _save_live_frame(force_render: bool = False) -> None:
            sc = _record_state["scale"]
            raw = (
                _vtk_to_pil(scale=sc)
                if force_render
                else _vtk_to_pil_passive(scale=sc)
            )
            outpath = (
                _record_state["dir"]
                / f"frame_{_record_state['frames']:05d}.jpg"
            )
            _composite_overlays(raw).save(str(outpath), "JPEG", quality=95)
            _record_state["frames"] += 1
            state.recording_frames = _record_state["frames"]
            state.flush()

        # ── Playback-mode frame writer (pre-rendered JPEG) ─────────────────
        def _save_pb_frames(data_url: str, n: int) -> None:
            """Write ONE unique snap file and record it in snap_files.

            Duplicates are generated later in _finalize_movie with crossfade
            transitions between snaps — no identical-frame runs in the output.

            Fast path (no overlays, no upscale): writes raw JPEG bytes.
            Slow path: decode once, composite overlays, upscale if needed.
            """
            from PIL import Image as _PIL

            sc = _record_state["scale"]
            has_overlays = (
                bool(getattr(state, "library_items", []))
                or (
                    bool(getattr(state, "galinfo_show", False))
                    and str(getattr(state, "nav_active_tab", "")) == "target"
                )
                or (
                    bool(getattr(state, "groupinfo_show", False))
                    and str(getattr(state, "nav_active_tab", ""))
                    == "environment"
                )
                or bool(getattr(state, "console_popout_show", False))
            )

            raw_bytes = _b64.b64decode(data_url.split(",", 1)[1])
            snap_idx = len(_record_state["snap_files"])
            snap_path = _record_state["dir"] / f"snap_{snap_idx:05d}.jpg"

            if has_overlays or sc > 1:
                img = _PIL.open(_io.BytesIO(raw_bytes)).convert("RGB")
                if sc > 1:
                    w, h = img.size
                    try:
                        _rs = _PIL.Resampling.LANCZOS
                    except AttributeError:
                        _rs = _PIL.LANCZOS
                    img = img.resize((w * sc, h * sc), _rs)
                _composite_overlays(img).save(
                    str(snap_path), "JPEG", quality=95
                )
            else:
                snap_path.write_bytes(raw_bytes)

            _record_state["snap_files"].append(
                {"file": str(snap_path), "count": n}
            )
            _record_state["frames"] += n
            state.recording_frames = _record_state["frames"]
            state.flush()

        try:
            while _record_state["active"]:
                t0 = asyncio.get_event_loop().time()
                try:
                    pb_active = bool(getattr(state, "playback_active", False))
                    prerender = bool(getattr(state, "prerender_busy", False))
                    rot_mode = str(getattr(state, "rotate_mode", "off"))

                    if pb_active and not _pb_done:
                        if prerender:
                            # Pre-render in progress — wait; don't capture yet
                            pass
                        else:
                            # ── Image-playback: read overlay frames ────────
                            current_snap = int(getattr(state, "snap_num", 0))
                            pb_frame = str(
                                getattr(state, "playback_frame", "")
                            )

                            # Lazy-init end-snap for one-pass detection
                            if _pb_end_snap[0] is None:
                                snap_max = int(getattr(state, "snap_max", 63))
                                reverse = bool(
                                    getattr(state, "is_reverse", False)
                                )
                                _pb_end_snap[0] = 0 if reverse else snap_max

                            # On every snap change write frames_per_snap
                            # copies of the overlay frame immediately.
                            if current_snap != _last_pb_snap[
                                0
                            ] and pb_frame.startswith("data:"):
                                play_speed = float(
                                    getattr(state, "play_speed", 1)
                                )
                                snap_rate = 3.0 * play_speed
                                frames_per_snap = max(
                                    1, round(movie_fps / snap_rate)
                                )
                                _save_pb_frames(pb_frame, frames_per_snap)
                                _last_pb_snap[0] = current_snap

                            # One-pass: stop when end snap rolls over (repeat)
                            if current_snap == _pb_end_snap[0]:
                                _pb_at_end[0] = True
                            elif _pb_at_end[0]:
                                _pb_done = True

                    elif not pb_active:
                        # ── Live view recording ────────────────────────────
                        _last_pb_snap[0] = None
                        _pb_end_snap[0] = None
                        _pb_at_end[0] = False
                        _pb_done = False

                        rotating = rot_mode not in ("off", "undefined")
                        if rotating:
                            _step_rotation(rot_mode, record_interval)
                            _save_live_frame(force_render=True)
                        else:
                            _save_live_frame(force_render=False)

                except Exception as e:
                    state.last_movie = f"ERROR capturing frame: {e!s}"
                    state.flush()
                    break

                elapsed = asyncio.get_event_loop().time() - t0
                await asyncio.sleep(max(0.001, record_interval - elapsed))
        except asyncio.CancelledError:
            pass

    @ctrl.set("start_recording")
    def on_start_recording():
        if _record_state["active"]:
            return
        import asyncio

        sess = _get_session_dir()
        movie_base = _resolve_name(state.movie_label, "movie")
        # Frames go to a temp subdir prefixed with "_" inside the session.
        # On finalize (gif/mov) the temp dir is deleted; for PNG seq we rename it.
        frames_dir = sess / f"_{movie_base}_frames"
        if frames_dir.exists():
            for f in frames_dir.glob("*"):
                try:
                    f.unlink()
                except OSError:
                    pass
        frames_dir.mkdir(parents=True, exist_ok=True)

        scale = _RES_SCALE.get(str(state.movie_resolution), 1)
        fps = max(1, int(state.movie_fps))
        _record_state.update(
            {
                "active": True,
                "dir": frames_dir,
                "frames": 0,
                "fps": fps,
                "format": str(state.movie_format),
                "scale": scale,
                "movie_base": movie_base,
                "session": sess,
                # Playback recording: list of {"file": path, "count": n}
                # entries — one per unique snap.  Populated by _save_pb_frames
                # and consumed by _finalize_movie to generate crossfaded output.
                "snap_files": [],
            }
        )
        state.recording_active = True
        state.recording_dir = str(frames_dir)
        state.recording_frames = 0
        state.flush()
        # Schedule the capture loop as a separate task so this handler returns
        # immediately and Trame can process the Stop click while we record.
        _record_task[0] = asyncio.ensure_future(_record_loop())

    def _remove_dir(frames_dir) -> None:
        """Recursively remove a frames temp directory."""
        import pathlib
        import shutil

        try:
            shutil.rmtree(pathlib.Path(frames_dir))
        except OSError:
            pass

    def _expand_with_crossfade(frames_dir, snap_files: list) -> None:
        """Expand snap_files into a crossfaded frame_*.jpg sequence.

        For each snap transition, frames are split into a hold section and a
        crossfade section that blends into the next snap:

            hold_n  = count - blend_n    (identical copies of this snap)
            blend_n = min(count // 2, 8) (crossfade into the next snap)

        The last snap has no following snap so all its frames are holds.
        Snap files are deleted after expansion.
        """
        from PIL import Image as _PIL
        import pathlib

        frames_dir = pathlib.Path(frames_dir)
        if not snap_files:
            return

        imgs = []
        for entry in snap_files:
            try:
                imgs.append(_PIL.open(entry["file"]).convert("RGB"))
            except Exception:
                imgs.append(None)

        frame_idx = 0
        n_snaps = len(snap_files)

        for k, (img, entry) in enumerate(zip(imgs, snap_files, strict=True)):
            if img is None:
                continue
            count = entry["count"]
            is_last = k == n_snaps - 1
            next_img = imgs[k + 1] if not is_last else None

            if is_last or next_img is None:
                blend_n = 0
            else:
                blend_n = min(max(1, count // 2), 8)
            hold_n = count - blend_n

            for _ in range(hold_n):
                img.save(
                    str(frames_dir / f"frame_{frame_idx:05d}.jpg"),
                    "JPEG",
                    quality=95,
                )
                frame_idx += 1

            for j in range(blend_n):
                alpha = (j + 1) / (blend_n + 1)
                _PIL.blend(img, next_img, alpha).save(
                    str(frames_dir / f"frame_{frame_idx:05d}.jpg"),
                    "JPEG",
                    quality=95,
                )
                frame_idx += 1

        # Close PIL images and delete the unique snap files
        for img, entry in zip(imgs, snap_files, strict=True):
            try:
                if img is not None:
                    img.close()
            except Exception:
                pass
            try:
                pathlib.Path(entry["file"]).unlink()
            except Exception:
                pass

    def _finalize_movie(
        frames_dir,
        session_dir,
        movie_base: str,
        fps: int,
        fmt: str,
        gif_loop: bool = True,
        snap_files: list | None = None,
    ) -> str:
        """Convert PNG sequence in frames_dir → <session>/<movie_base>.<fmt>.
        For PNG sequence, renames the temp frames dir to <session>/<movie_base>/.
        On successful gif/mov, the temp frames dir is removed."""
        import subprocess
        import pathlib

        frames_dir = pathlib.Path(frames_dir)
        session_dir = pathlib.Path(session_dir)

        # Playback recordings: expand unique snap files into a crossfaded
        # frame sequence before encoding.  Live recordings already have
        # frame_*.jpg files and skip this step.
        if snap_files:
            try:
                _expand_with_crossfade(frames_dir, snap_files)
            except Exception as exc:
                return f"ERROR (crossfade): {exc!s}"

        if fmt == "png":
            target = session_dir / movie_base
            if target.exists():
                import datetime

                target = (
                    session_dir
                    / f"{movie_base}_{datetime.datetime.now():%H%M%S}"
                )
            frames_dir.rename(target)
            return str(target)

        out_path = session_dir / f"{movie_base}.{fmt}"
        if out_path.exists():
            import datetime

            out_path = (
                session_dir
                / f"{movie_base}_{datetime.datetime.now():%H%M%S}.{fmt}"
            )

        if fmt == "gif":
            try:
                from PIL import Image as _PilGif

                frames = sorted(frames_dir.glob("frame_*.jpg"))
                if not frames:
                    _remove_dir(frames_dir)
                    return "ERROR: no frames captured"
                # Determine even crop from the first frame (applied uniformly).
                _f0 = _PilGif.open(str(frames[0]))
                _w0, _h0 = _f0.size
                _f0.close()
                ew = _w0 if _w0 % 2 == 0 else _w0 - 1
                eh = _h0 if _h0 % 2 == 0 else _h0 - 1
                need_crop = ew != _w0 or eh != _h0
                # Floyd-Steinberg dithering distributes quantisation error to
                # neighbouring pixels, which prevents hard contour lines on
                # smooth gaussian-splat gradients (a visible artefact with the
                # default median-cut quantiser and no dithering).
                try:
                    _dither = _PilGif.Dither.FLOYDSTEINBERG
                    _adaptive = _PilGif.Palette.ADAPTIVE
                except AttributeError:
                    _dither = 3  # FLOYDSTEINBERG numeric value
                    _adaptive = 1  # ADAPTIVE numeric value
                pil_frames = []
                for p in frames:
                    img = _PilGif.open(str(p)).convert("RGB")
                    if need_crop:
                        img = img.crop((0, 0, ew, eh))
                    # Resize to canonical size if a frame is unexpectedly
                    # different (e.g. live-VTK frames at 2× vs native
                    # playback frames before the scale fix took effect).
                    if img.size != (ew, eh):
                        try:
                            _gif_rs = _PilGif.Resampling.LANCZOS
                        except AttributeError:
                            _gif_rs = _PilGif.LANCZOS
                        img = img.resize((ew, eh), _gif_rs)
                    pil_frames.append(
                        img.convert("P", palette=_adaptive, dither=_dither)
                    )
                    img.close()
                duration_ms = max(1, int(1000 / fps))
                # loop=0 = infinite, loop=1 = play once
                pil_frames[0].save(
                    str(out_path),
                    save_all=True,
                    append_images=pil_frames[1:],
                    optimize=False,
                    loop=0 if gif_loop else 1,
                    duration=duration_ms,
                )
                _remove_dir(frames_dir)
                return str(out_path)
            except Exception as e:
                return f"ERROR (gif): {e!s}"

        if fmt == "mov":
            cmd = [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(frames_dir / "frame_%05d.jpg"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                str(out_path),
            ]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300
                )
                if proc.returncode != 0:
                    return f"ERROR (mov): ffmpeg returned {proc.returncode}: {proc.stderr[-300:]}"
                _remove_dir(frames_dir)
                return str(out_path)
            except FileNotFoundError:
                return "ERROR: ffmpeg not found in PATH"
            except Exception as e:
                return f"ERROR (mov): {e!s}"

        return f"ERROR: unknown format {fmt!r}"

    @ctrl.set("stop_recording")
    def on_stop_recording():
        if not _record_state["active"]:
            return
        _record_state["active"] = False
        state.recording_active = False
        state.last_movie = "Encoding…"
        state.flush()
        # Cancel the capture task so no new frames get written before finalize.
        if _record_task[0] is not None and not _record_task[0].done():
            _record_task[0].cancel()
        # Finalize (imageio / ffmpeg) can take seconds — run in a thread so
        # the event loop stays responsive while encoding.
        import threading

        snap = dict(_record_state)  # copy current state before thread starts

        def _do_finalize():
            try:
                result = _finalize_movie(
                    frames_dir=snap["dir"],
                    session_dir=snap["session"],
                    movie_base=snap["movie_base"],
                    fps=snap["fps"],
                    fmt=snap["format"],
                    gif_loop=bool(state.movie_loop),
                    snap_files=snap.get("snap_files") or [],
                )
            except Exception as exc:
                result = f"ERROR (finalize): {exc!s}"
            state.last_movie = result
            state.flush()

        threading.Thread(target=_do_finalize, daemon=True).start()

    @ctrl.set("go_to_coords")
    def on_go_to_coords():
        # Clear any active draw widget — its final position is already in the fields.
        if bool(state.draw_sphere_active):
            try:
                scene.plotter.clear_sphere_widgets()
            except Exception:
                pass
            _draw_sphere_widget[0] = None
            _remove_sphere_actor()
            state.draw_sphere_active = False
        x, y, z, d = (
            float(state.nav_x),
            float(state.nav_y),
            float(state.nav_z),
            float(state.nav_distance),
        )
        scene.camera.zoom_to_radius((x, y, z), d)
        # Always engage focus on Go
        scene.set_focus_sphere((x, y, z), d)
        state.focus_active = True
        _push()

    @ctrl.set("toggle_draw_sphere")
    def on_toggle_draw_sphere():
        """Toggle the interactive sphere widget in the Coords tab.

        First click places a draggable sphere in the 3D view; dragging its
        handles updates the X/Y/Z and Standoff fields in real time.
        Second click (Lock) removes the widget and runs go_to_coords so
        the locked sphere becomes the active focus region."""
        if bool(state.draw_sphere_active):
            # Lock — clear widget; fields already hold the final position.
            try:
                scene.plotter.clear_sphere_widgets()
            except Exception:
                pass
            _draw_sphere_widget[0] = None
            _remove_sphere_actor()
            state.draw_sphere_active = False
            state.flush()
            on_go_to_coords()
        else:
            # Start — place two draggable handle balls:
            #   index 0 = center ball  (translates the sphere)
            #   index 1 = edge ball    (resizes: distance from centre = radius)
            # A custom 5-ring mesh (identical to the Coords indicator sphere)
            # is drawn between them and rebuilt whenever either ball moves.
            import numpy as _np_ds

            _cam_ds = scene.plotter.camera
            _fp_ds = _cam_ds.focal_point
            cx, cy, cz = float(_fp_ds[0]), float(_fp_ds[1]), float(_fp_ds[2])
            _cam_d_ds = float(
                _np_ds.linalg.norm(
                    _np_ds.array(_cam_ds.position) - _np_ds.array(_fp_ds)
                )
            )
            r = max(
                0.5,
                _cam_d_ds
                * float(_np_ds.tan(_np_ds.deg2rad(_cam_ds.view_angle) / 2.0))
                * 0.25,
            )
            state.nav_x = round(cx, 3)
            state.nav_y = round(cy, 3)
            state.nav_z = round(cz, 3)
            state.nav_distance = round(r, 3)

            # Mutable centre/radius shared by the callback closure.
            _sc = [cx, cy, cz]
            _sr = [r]

            def _sphere_cb(point, index, widget):
                import numpy as _np2

                if index == 0:
                    # Centre ball moved — translate sphere.
                    _sc[0], _sc[1], _sc[2] = (
                        float(point[0]),
                        float(point[1]),
                        float(point[2]),
                    )
                    state.nav_x = round(_sc[0], 2)
                    state.nav_y = round(_sc[1], 2)
                    state.nav_z = round(_sc[2], 2)
                    # Slide the edge ball to stay on the sphere surface (+X).
                    ww = _draw_sphere_widget[0]
                    if isinstance(ww, list) and len(ww) > 1:
                        ww[1].SetCenter(_sc[0] + _sr[0], _sc[1], _sc[2])
                        ww[1].Modified()
                else:
                    # Edge ball moved — resize from distance to centre.
                    p = _np2.array(
                        [float(point[0]), float(point[1]), float(point[2])]
                    )
                    c = _np2.array(_sc)
                    _sr[0] = max(0.1, float(_np2.linalg.norm(p - c)))
                    state.nav_distance = round(_sr[0], 2)
                _rebuild_sphere_rings(_sc, _sr[0])
                state.flush()

            handle_r = max(0.3, r * 0.12)
            try:
                _draw_sphere_widget[0] = scene.plotter.add_sphere_widget(
                    _sphere_cb,
                    center=[(cx, cy, cz), (cx + r, cy, cz)],
                    radius=handle_r,
                    color="cyan",
                    style="surface",
                    pass_widget=True,
                    interaction_event="always",
                )
                _rebuild_sphere_rings((cx, cy, cz), r)
                state.draw_sphere_active = True
            except Exception:
                pass
            state.flush()
            _push()

    @ctrl.set("populate_coords_from_camera")
    def on_populate_coords_from_camera():
        """Fill the Coords fields with the current camera focal point + standoff."""
        import numpy as _np

        cam = scene.plotter.camera
        fp = _np.array(cam.focal_point, dtype=_np.float64)
        pos = _np.array(cam.position, dtype=_np.float64)
        d = float(_np.linalg.norm(pos - fp))
        state.nav_x = round(float(fp[0]), 3)
        state.nav_y = round(float(fp[1]), 3)
        state.nav_z = round(float(fp[2]), 3)
        # Standoff matches the current camera distance from the focal point.
        state.nav_distance = (
            round(d, 3) if d > 0 else float(state.nav_distance)
        )
        state.flush()

    @ctrl.set("populate_box_from_camera")
    def on_populate_box_from_camera():
        """Fill the Box fields with the axis-aligned bounding region currently in view."""
        import numpy as _np

        cam = scene.plotter.camera
        fp = _np.array(cam.focal_point, dtype=_np.float64)
        pos = _np.array(cam.position, dtype=_np.float64)
        d = float(_np.linalg.norm(pos - fp))
        # Half-extent at the focal plane = d * tan(FOV/2). Use that as the
        # cube half-width so the box roughly matches what's on screen.
        fov_rad = _np.deg2rad(cam.view_angle)
        half = max(d * _np.tan(fov_rad / 2.0), 0.1)
        state.nav_box_xmin = round(float(fp[0] - half), 3)
        state.nav_box_xmax = round(float(fp[0] + half), 3)
        state.nav_box_ymin = round(float(fp[1] - half), 3)
        state.nav_box_ymax = round(float(fp[1] + half), 3)
        state.nav_box_zmin = round(float(fp[2] - half), 3)
        state.nav_box_zmax = round(float(fp[2] + half), 3)
        state.flush()

    @ctrl.set("zoom_to_box")
    def on_zoom_to_box():
        # Clear any active draw widget — its final bounds are already in the fields.
        if bool(state.draw_box_active):
            try:
                scene.plotter.clear_box_widgets()
            except Exception:
                pass
            _detach_box_cam_observer()
            _draw_box_widget[0] = None
            state.draw_box_active = False
        xmin, xmax = float(state.nav_box_xmin), float(state.nav_box_xmax)
        ymin, ymax = float(state.nav_box_ymin), float(state.nav_box_ymax)
        zmin, zmax = float(state.nav_box_zmin), float(state.nav_box_zmax)
        scene.camera.zoom_to_box(xmin, xmax, ymin, ymax, zmin, zmax)
        # Always engage focus on Zoom — matches Target / Environment /
        # Coords behaviour. User can toggle it off via the focus button.
        scene.set_focus_box(xmin, xmax, ymin, ymax, zmin, zmax)
        state.focus_active = True
        _push()

    @ctrl.set("toggle_draw_box")
    def on_toggle_draw_box():
        """Toggle the interactive box widget in the Box tab.

        First click places a draggable, resizable box in the 3D view; moving
        its handles updates the six min/max bound fields in real time.
        Second click (Lock) removes the widget and runs zoom_to_box so the
        locked box becomes the active focus region."""
        if bool(state.draw_box_active):
            # Lock — clear widget; fields already hold the final bounds.
            try:
                scene.plotter.clear_box_widgets()
            except Exception:
                pass
            _detach_box_cam_observer()
            _draw_box_widget[0] = None
            state.draw_box_active = False
            state.flush()
            on_zoom_to_box()
        else:
            # Start — place an interactive box centred on the current view.
            import numpy as _np_db

            _cam_db = scene.plotter.camera
            _fp_db = _cam_db.focal_point
            _cx, _cy, _cz = (
                float(_fp_db[0]),
                float(_fp_db[1]),
                float(_fp_db[2]),
            )
            _cam_d_db = float(
                _np_db.linalg.norm(
                    _np_db.array(_cam_db.position) - _np_db.array(_fp_db)
                )
            )
            _h = max(
                1.0,
                _cam_d_db
                * float(_np_db.tan(_np_db.deg2rad(_cam_db.view_angle) / 2.0))
                * 0.5,
            )
            xmin, xmax = _cx - _h, _cx + _h
            ymin, ymax = _cy - _h, _cy + _h
            zmin, zmax = _cz - _h, _cz + _h
            state.nav_box_xmin = round(xmin, 3)
            state.nav_box_xmax = round(xmax, 3)
            state.nav_box_ymin = round(ymin, 3)
            state.nav_box_ymax = round(ymax, 3)
            state.nav_box_zmin = round(zmin, 3)
            state.nav_box_zmax = round(zmax, 3)

            def _box_cb(planes):
                pts = planes.GetPoints()
                if pts is None or pts.GetNumberOfPoints() == 0:
                    return
                n = pts.GetNumberOfPoints()
                xs = [pts.GetPoint(i)[0] for i in range(n)]
                ys = [pts.GetPoint(i)[1] for i in range(n)]
                zs = [pts.GetPoint(i)[2] for i in range(n)]
                bxmin = round(min(xs), 2)
                bxmax = round(max(xs), 2)
                bymin = round(min(ys), 2)
                bymax = round(max(ys), 2)
                bzmin = round(min(zs), 2)
                bzmax = round(max(zs), 2)
                state.nav_box_xmin = bxmin
                state.nav_box_xmax = bxmax
                state.nav_box_ymin = bymin
                state.nav_box_ymax = bymax
                state.nav_box_zmin = bzmin
                state.nav_box_zmax = bzmax
                state.flush()

            try:
                # Snapshot sphere sources that exist BEFORE the widget
                # so we can identify the 7 new handle sources afterward.
                def _sphere_src_ids():
                    _ids = set()
                    _a = scene.plotter.renderer.GetActors()
                    _a.InitTraversal()
                    for _ in range(_a.GetNumberOfItems()):
                        _ac = _a.GetNextActor()
                        _mp = _ac.GetMapper()
                        if _mp:
                            _s = _mp.GetInputAlgorithm()
                            if _s and hasattr(_s, "SetRadius"):
                                _ids.add(id(_s))
                    return _ids

                _pre_ids = _sphere_src_ids()

                _draw_box_widget[0] = scene.plotter.add_box_widget(
                    _box_cb,
                    bounds=[xmin, xmax, ymin, ymax, zmin, zmax],
                    color="cyan",
                    rotation_enabled=False,
                )
                state.draw_box_active = True

                # Capture the new sphere sources (= handle spheres)
                _new_srcs = []
                _a2 = scene.plotter.renderer.GetActors()
                _a2.InitTraversal()
                for _ in range(_a2.GetNumberOfItems()):
                    _ac2 = _a2.GetNextActor()
                    _mp2 = _ac2.GetMapper()
                    if _mp2:
                        _s2 = _mp2.GetInputAlgorithm()
                        if (
                            _s2
                            and id(_s2) not in _pre_ids
                            and hasattr(_s2, "SetRadius")
                            and hasattr(_s2, "GetRadius")
                        ):
                            _new_srcs.append(_s2)
                _box_handle_sources[0] = _new_srcs
                _handle_world_r[0] = (
                    _new_srcs[0].GetRadius() if _new_srcs else None
                )
                _attach_box_cam_observer(_draw_box_widget[0])
            except Exception:
                pass
            state.flush()
            _push()

    @ctrl.set("clear_draw_sphere")
    def on_clear_draw_sphere():
        """Cancel any active Draw Sphere widget, clear the zoom indicator, and undo focus."""
        if bool(state.draw_sphere_active):
            try:
                scene.plotter.clear_sphere_widgets()
            except Exception:
                pass
            _draw_sphere_widget[0] = None
            _remove_sphere_actor()
            state.draw_sphere_active = False
        scene.camera._clear_indicator()
        scene.clear_focus()
        state.focus_active = False
        state.flush()
        _push()

    @ctrl.set("clear_draw_box")
    def on_clear_draw_box():
        """Cancel any active Draw Box widget, clear the zoom indicator, and undo focus."""
        if bool(state.draw_box_active):
            try:
                scene.plotter.clear_box_widgets()
            except Exception:
                pass
            _detach_box_cam_observer()
            _draw_box_widget[0] = None
            state.draw_box_active = False
        scene.camera._clear_indicator()
        scene.clear_focus()
        state.focus_active = False
        state.flush()
        _push()

    @ctrl.set("reset_camera")
    def on_reset():
        _clear_draw_widgets()
        scene.camera._clear_indicator()
        if scene.is_lightcone:
            # A lightcone isn't a cube at the origin — frame its actual
            # bounds (CameraController.reset() already does this correctly).
            scene.camera.reset()
        else:
            regions = [(0.0, 0.0, 0.0, scene.primary.box_size)]
            for name in scene._adjacent_order:
                m = scene._models.get(name)
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
        scene.clear_focus()
        state.focus_active = False
        # Recompute clipping planes so all geometry is visible without
        # the user having to zoom/move to trigger an automatic update.
        scene.plotter.renderer.ResetCameraClippingRange()
        _push()

    @ctrl.set("center_camera")
    def on_center_camera():
        if scene.is_lightcone:
            # No box centre in a lightcone — stand at the observer (origin)
            # and look outward along the cone.
            scene.camera.go_to_lightcone_observer()
            _push()
            return
        active = scene.active_model
        off = tuple(float(v) for v in active.offset)
        scene.camera.go_to_box_center(offset=off, box_size=active.box_size)
        _push()

    # ------------------------------------------------------------------
    # Console — natural-language command interpreter
    # ------------------------------------------------------------------

    from visage.utils.command_parser import (
        CommandContext,
        execute_command,
    )
    import subprocess as _subprocess
    import os as _os
    import sys as _sys
    import socket as _socket
    import getpass as _getpass
    import base64 as _base64
    import pathlib as _pathlib_pty

    _cmd_ctx = CommandContext(scene=scene, state=state, ctrl=ctrl)

    def _python_shim_dir() -> str | None:
        """Create a bin dir of python/python3/pip/pip3 shims pointing at the
        interpreter running ViSAGE, so the Console's `python3` (etc.) sees all
        of ViSAGE's installed packages (h5py, numpy, scipy, matplotlib, …)
        rather than whatever the login shell's default python happens to be."""
        exe = _sys.executable
        if not exe:
            return None
        shim = _pathlib_pty.Path.home() / ".visage" / "shims"
        try:
            shim.mkdir(parents=True, exist_ok=True)
            for _name in ("python", "python3"):
                link = shim / _name
                try:
                    if link.is_symlink() or link.exists():
                        link.unlink()
                    link.symlink_to(exe)
                except OSError:
                    pass
            for _name in ("pip", "pip3"):
                f = shim / _name
                try:
                    f.write_text(f'#!/bin/sh\nexec "{exe}" -m pip "$@"\n')
                    f.chmod(0o755)
                except OSError:
                    pass
        except OSError:
            return None
        return str(shim)

    class _PTYSession:
        """PTY-backed shell session powering the xterm.js terminal."""

        def __init__(self, cwd: str, env: dict) -> None:
            import pty as _pty, fcntl as _fcntl, struct as _struct, termios as _termios

            master_fd, slave_fd = _pty.openpty()
            try:
                _fcntl.ioctl(
                    slave_fd,
                    _termios.TIOCSWINSZ,
                    _struct.pack("HHHH", 24, 80, 0, 0),
                )
            except Exception:
                pass
            shell = env.get("SHELL", _os.environ.get("SHELL", "/bin/bash"))
            self._proc = _subprocess.Popen(
                [shell, "-l"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                cwd=str(cwd),
                env=env,
                preexec_fn=_os.setsid,
            )
            _os.close(slave_fd)
            self._fd = master_fd
            self._dead = False

        @property
        def fd(self) -> int:
            return self._fd

        def write(self, data: bytes) -> None:
            if not self._dead:
                try:
                    _os.write(self._fd, data)
                except OSError:
                    self._dead = True

        def resize(self, rows: int, cols: int) -> None:
            try:
                import fcntl as _fcntl2, struct as _struct2, termios as _termios2

                _fcntl2.ioctl(
                    self._fd,
                    _termios2.TIOCSWINSZ,
                    _struct2.pack("HHHH", rows, cols, 0, 0),
                )
            except Exception:
                pass

        def is_alive(self) -> bool:
            return not self._dead and self._proc.poll() is None

        def close(self) -> None:
            self._dead = True
            try:
                _os.close(self._fd)
            except Exception:
                pass
            try:
                self._proc.kill()
            except Exception:
                pass

    def _make_console_data() -> dict:
        """Per-session state for one console: PTY terminal + SAGE command mode."""
        return {
            "history": [],
            "input": "",
            "mode": "terminal",
            "prompt": "$",
            "pty": None,  # _PTYSession, created lazily on first keystroke
            "counter": 0,
        }

    _consoles_data: dict[int, dict] = {1: _make_console_data()}
    _active_console = [1]
    _console_id_counter = [1]

    import atexit as _atexit

    def _kill_all_ptys() -> None:
        for d in _consoles_data.values():
            pty_sess = d.get("pty")
            if pty_sess:
                pty_sess.close()

    _atexit.register(_kill_all_ptys)

    def _truncate(text: str, n: int = 4000) -> str:
        if len(text) <= n:
            return text
        return text[:n] + f"\n… [{len(text) - n} chars truncated]"

    def _save_active() -> None:
        """Snapshot the state vars into the active console's storage."""
        cid = _active_console[0]
        d = _consoles_data.get(cid)
        if d is None:
            return
        d["history"] = list(state.console_history)
        d["input"] = state.console_input

    def _load_console(cid: int) -> None:
        """Push storage[cid] into the state vars and mark active."""
        d = _consoles_data.get(cid)
        if d is None:
            return
        state.console_history = list(d["history"])
        state.console_input = d["input"]
        state.console_mode = d["mode"]
        state.console_prompt = d["prompt"]
        state.console_active_id = cid
        _active_console[0] = cid
        state.flush()

    # Mode + prompt initialised from the default console.
    state.console_mode = _consoles_data[1]["mode"]
    state.console_prompt = _consoles_data[1]["prompt"]

    def _push_history(prompt: str, cmd: str, out: str) -> None:
        d = _consoles_data[_active_console[0]]
        d["counter"] += 1
        history = list(state.console_history)
        history.append(
            {
                "id": d["counter"],
                "cmd": f"{prompt} {cmd}" if cmd else prompt,
                "out": _truncate(out) if out else "",
            }
        )
        if len(history) > 200:
            history = history[-200:]
        state.console_history = history
        d["history"] = list(history)

    def _start_pty_reader(cid: int, pty_sess: _PTYSession) -> None:
        """Stream PTY output to xterm.js via state updates.

        Uses an async coroutine + run_in_executor so the blocking read happens
        in a thread pool while state updates run on the event loop (same
        pattern as other blocking I/O in this file).  select() with a 1 s
        timeout makes the thread exit promptly on shutdown so the event loop
        never hangs waiting for a blocked os.read().
        Drains all immediately-available bytes after the first read so that
        rapid bursts (echo + output) arrive as one chunk and are not dropped
        between 50 ms JS polls.
        """
        import select as _select

        def _read_chunk(fd: int) -> bytes | None:
            """Wait up to 1 s for data, then drain all available bytes.
            Returns None on timeout (caller retries), b"" on fd close."""
            try:
                r, _, _ = _select.select([fd], [], [], 1.0)
            except (OSError, ValueError):
                return b""
            if not r:
                return None  # timeout — is_alive() re-checked by caller
            try:
                chunk = _os.read(fd, 4096)
            except OSError:
                return b""
            if not chunk:
                return b""
            buf = bytearray(chunk)
            # drain any further bytes already buffered (non-blocking)
            while True:
                try:
                    r2, _, _ = _select.select([fd], [], [], 0)
                    if not r2:
                        break
                    more = _os.read(fd, 4096)
                    if not more:
                        break
                    buf.extend(more)
                except OSError:
                    break
            return bytes(buf)

        async def _pump() -> None:
            loop = asyncio.get_running_loop()
            seq = 0
            fd = pty_sess.fd
            while pty_sess.is_alive():
                try:
                    data = await loop.run_in_executor(
                        None, lambda: _read_chunk(fd)
                    )
                except asyncio.CancelledError:
                    break
                if data is None:
                    continue  # select timeout — loop back and check is_alive
                if not data:
                    break  # fd closed / process exited
                seq += 1
                if _active_console[0] == cid:
                    state.pty_out_data = _base64.b64encode(data).decode(
                        "ascii"
                    )
                    state.pty_out_seq = seq
                    state.flush()

        asyncio.ensure_future(_pump())

    @ctrl.set("console_mode_sage")
    def on_console_mode_sage():
        d = _consoles_data[_active_console[0]]
        d["mode"] = "command"
        d["prompt"] = "cmd>"
        state.console_mode = "command"
        state.console_prompt = "cmd>"
        _push_history(
            "$",
            "sage",
            "ViSAGE command mode. "
            "Examples: 'show only clusters', 'go to halo 42', "
            "'snap 30', 'screenshot'. Type 'help' for the full "
            "list, 'exit' to return to the terminal.",
        )
        state.flush()

    @ctrl.set("console_mode_terminal")
    def on_console_mode_terminal():
        d = _consoles_data[_active_console[0]]
        d["mode"] = "terminal"
        d["prompt"] = "$"
        state.console_mode = "terminal"
        state.console_prompt = "$"
        state.flush()
        # PTY is created by pty_ensure_trigger fired from JS after xterm.js mounts.

    @ctrl.set("console_close_pty")
    def on_console_close_pty():
        """Kill the active PTY session and switch to SAGE command mode."""
        cid = _active_console[0]
        d = _consoles_data.get(cid)
        if d is None:
            return
        pty_sess = d.get("pty")
        if pty_sess:
            pty_sess.close()
        d["pty"] = None
        d["mode"] = "command"
        d["prompt"] = "cmd>"
        state.console_mode = "command"
        state.console_prompt = "cmd>"
        state.flush()

    @ctrl.set("console_submit")
    async def on_console_submit():
        cid = _active_console[0]
        d = _consoles_data[cid]
        cmd_raw = str(state.console_input or "")

        if d["mode"] == "terminal":
            # Terminal uses xterm.js directly; text input is hidden.
            return

        # Empty line is a no-op in command mode.
        if not cmd_raw.strip():
            return

        cmd = cmd_raw.rstrip()
        low = cmd.strip().lower()
        if low in ("exit", "quit", "terminal"):
            d["mode"] = "terminal"
            d["prompt"] = "$"
            state.console_mode = "terminal"
            state.console_prompt = "$"
            _push_history("cmd>", cmd, "(back to terminal)")
        else:
            try:
                out_text = execute_command(cmd, _cmd_ctx) or "(ok)"
            except Exception as e:
                out_text = f"Error: {e}"
            _push_history("cmd>", cmd, out_text)

        state.console_input = ""
        d["input"] = ""
        state.flush()
        _push()

    @ctrl.set("console_clear")
    def on_console_clear():
        state.console_history = []
        _consoles_data[_active_console[0]]["history"] = []
        state.flush()

    @ctrl.set("console_new")
    def on_console_new():
        _save_active()
        _console_id_counter[0] += 1
        new_id = _console_id_counter[0]
        _consoles_data[new_id] = _make_console_data()
        state.consoles_list = state.consoles_list + [
            {"id": new_id, "title": f"Console {new_id}"}
        ]
        _load_console(new_id)

    @ctrl.set("console_switch")
    def on_console_switch(cid):
        cid = int(cid)
        if cid == _active_console[0]:
            return
        _save_active()
        _load_console(cid)

    @ctrl.set("console_close")
    def on_console_close(cid):
        cid = int(cid)
        if len(_consoles_data) <= 1:
            return
        _save_active()
        closing = _consoles_data.pop(cid, None)
        if closing:
            try:
                pty_sess = closing.get("pty")
                if pty_sess:
                    pty_sess.close()
            except Exception:
                pass
        state.consoles_list = [
            c for c in state.consoles_list if c["id"] != cid
        ]
        if _active_console[0] == cid:
            new_active = state.consoles_list[0]["id"]
            _load_console(new_active)
        else:
            state.flush()

    @ctrl.set("console_toggle_popout")
    def on_console_toggle_popout():
        state.console_popout_show = not bool(state.console_popout_show)
        state.flush()

    # ------------------------------------------------------------------
    # Library — browse and replay stored screenshots / movies
    # ------------------------------------------------------------------

    import pathlib as _pathlib

    _cwd = _pathlib.Path.cwd()
    _LIBRARY_DIR = _cwd / "sage_library"
    _LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

    _MEDIA_EXTS = {
        ".png": ("image", "image/png"),
        ".jpg": ("image", "image/jpeg"),
        ".jpeg": ("image", "image/jpeg"),
        ".tif": ("image", "image/tiff"),
        ".tiff": ("image", "image/tiff"),
        ".gif": ("image", "image/gif"),
        ".mov": ("video", "video/mp4"),  # MOV with H.264 ≈ MP4
        ".mp4": ("video", "video/mp4"),
    }

    def _scan_library() -> list[dict]:
        out: list[dict] = []
        roots = [_LIBRARY_DIR, _cwd / "sage_outputs"]
        for root in roots:
            if not root.exists():
                continue
            for p in sorted(root.rglob("*")):
                if not p.is_file():
                    continue
                ext = p.suffix.lower()
                if ext not in _MEDIA_EXTS:
                    continue
                kind, _mime = _MEDIA_EXTS[ext]
                try:
                    size_kb = max(1, p.stat().st_size // 1024)
                except OSError:
                    continue
                try:
                    rel = p.relative_to(_cwd)
                except ValueError:
                    rel = p
                out.append(
                    {
                        "name": p.name,
                        "rel": str(rel),
                        "path": str(p),
                        "kind": kind,
                        "ext": ext.lstrip("."),
                        "size_kb": int(size_kb),
                        "folder": str(rel.parent),
                    }
                )
        # Group by source folder first, then by file type, then
        # alphabetically within each type. Flag the first entry of each
        # folder and each type so the UI can draw section headers / dividers.
        out.sort(key=lambda e: (e["folder"], e["ext"], e["name"].lower()))
        prev_folder = None
        prev_ext = None
        for e in out:
            e["first_in_folder"] = e["folder"] != prev_folder
            # A new folder always restarts the type grouping.
            e["first_in_group"] = e["first_in_folder"] or e["ext"] != prev_ext
            prev_folder = e["folder"]
            prev_ext = e["ext"]
        return out

    @ctrl.set("library_refresh")
    def on_library_refresh():
        state.library_files = _scan_library()
        state.flush()

    _lib_id = [0]
    _lib_items: list[dict] = (
        []
    )  # authoritative list; never read back from state proxy

    @ctrl.set("library_open")
    def on_library_open(path: str):
        import base64

        p = _pathlib.Path(path)
        if not p.is_file():
            return
        ext = p.suffix.lower()
        if ext not in _MEDIA_EXTS:
            return
        kind, mime = _MEDIA_EXTS[ext]
        try:
            data = p.read_bytes()
        except OSError:
            return
        b64 = base64.b64encode(data).decode("ascii")
        _lib_id[0] += 1
        idx = len(_lib_items)
        new_item = {
            "id": _lib_id[0],
            "name": p.name,
            "kind": kind,
            "data_url": f"data:{mime};base64,{b64}{'#' + str(_lib_id[0]) if mime == 'image/gif' else ''}",
            "top_px": 32 + (idx % 6) * 50,
            "right_px": 24 + (idx % 6) * 44,
        }
        _lib_items.append(new_item)
        state.library_items = list(_lib_items)
        state.flush()
        _push()

    @ctrl.set("library_close")
    def on_library_close():
        _lib_items.clear()
        state.library_items = []
        state.flush()

    @ctrl.set("library_close_item")
    def on_library_close_item(item_id: int):
        target = int(item_id)
        _lib_items[:] = [x for x in _lib_items if x["id"] != target]
        state.library_items = list(_lib_items)
        state.flush()

    @ctrl.set("library_delete")
    def on_library_delete(path: str):
        p = _pathlib.Path(path)
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
        state.library_files = _scan_library()
        state.flush()

    @ctrl.set("library_rename")
    def on_library_rename(path: str, new_name: str):
        new_name = str(new_name).strip()
        if not new_name:
            return
        p = _pathlib.Path(path)
        if not p.is_file():
            return
        # Keep the original extension if the user didn't type one.
        if "." not in new_name:
            new_name += p.suffix
        dest = p.parent / new_name
        if dest.exists():
            return
        try:
            p.rename(dest)
        except OSError:
            return
        state.library_files = _scan_library()
        state.flush()

    # Populate the file list at startup
    state.library_files = _scan_library()

    # PTY state-change handlers — JS writes to hidden <input v-model="...">
    # elements and dispatches native 'input' events so Vue's reactivity carries
    # the update to the server.  This is more reliable than window.trame.set()
    # (local only) or window.trame.trigger() (broken in external JS on Trame 3).

    def _ensure_pty(cid: int) -> None:
        d = _consoles_data.get(cid)
        if d is None:
            return
        if d.get("pty") is None or not d["pty"].is_alive():
            # Put ViSAGE's own interpreter (and pip) first on PATH so the
            # Console's python/python3/pip carry all of ViSAGE's packages.
            env = dict(_os.environ)
            _prepend = _os.pathsep.join(
                p
                for p in (
                    _python_shim_dir(),
                    _os.path.dirname(_sys.executable),
                )
                if p
            )
            if _prepend:
                env["PATH"] = _prepend + _os.pathsep + env.get("PATH", "")
            d["pty"] = _PTYSession(cwd=_os.getcwd(), env=env)
            _start_pty_reader(cid, d["pty"])
            # A login shell re-sources the user's profile, which can push our
            # dirs back down PATH; re-assert them as the shell's first input
            # (queued before any typing, runs after profile init).
            if _prepend:
                try:
                    d["pty"].write(
                        (
                            'export PATH="'
                            + _prepend
                            + ':$PATH"; hash -r 2>/dev/null; clear\n'
                        ).encode()
                    )
                except Exception:
                    pass

    @state.change("pty_ensure_seq")
    def on_pty_ensure(pty_ensure_seq, **_):
        if not pty_ensure_seq:
            return
        try:
            cid = int(state.console_active_id or 1)
        except (ValueError, TypeError):
            cid = 1
        _ensure_pty(cid)

    @state.change("pty_input_raw")
    def on_pty_input(pty_input_raw, **_):
        # Format: "seq:cid:b64data"
        if not pty_input_raw or ":" not in str(pty_input_raw):
            return
        try:
            raw = str(pty_input_raw)
            first = raw.index(":")
            second = raw.index(":", first + 1)
            cid = int(raw[first + 1 : second])
            b64 = raw[second + 1 :]
        except (ValueError, IndexError):
            return
        d = _consoles_data.get(cid)
        if d is None:
            return
        _ensure_pty(cid)
        try:
            d["pty"].write(_base64.b64decode(b64))
        except Exception:
            pass

    # Triggers — Enter / per-row buttons fire these from Vue templates.
    server.trigger("console_submit_trigger")(on_console_submit)
    server.trigger("console_switch_trigger")(on_console_switch)
    server.trigger("console_close_trigger")(on_console_close)
    server.trigger("library_rename_trigger")(on_library_rename)
    server.trigger("library_delete_trigger")(on_library_delete)

    @ctrl.set("highlight_galaxy")
    def on_highlight_galaxy():
        """Toggle white-border + regime-coloured splat on the selected galaxy."""
        cam = scene.camera
        if cam.has_member_indicators:
            cam._clear_member_indicators()
            _push()
            return
        try:
            gidx = int(state.nav_gal_idx)
        except (TypeError, ValueError):
            return
        _, galaxies = scene.active_model.loader.get(scene.current_snap)
        if gidx < 0 or gidx >= galaxies.count:
            return
        off = scene.active_model.offset
        cam._add_selected_indicator(
            galaxies.positions[gidx] + off, color="limegreen"
        )
        _push()

    @ctrl.set("toggle_focus")
    def on_toggle_focus():
        currently_on = bool(state.focus_active)
        if currently_on:
            # Turning OFF — always just clears focus, regardless of tab.
            _clear_draw_widgets()
            state.focus_active = False
            scene.clear_focus()
            _push()
            return

        # Turning ON — engage focus appropriate to the active tab so the
        # button behaves naturally wherever the user is in the UI.
        tab = state.nav_active_tab
        halos, galaxies = scene.active_model.loader.get(scene.current_snap)

        if tab == "target":
            try:
                idx = int(state.nav_gal_idx)
                radius = float(state.nav_gal_last_radius)
                if 0 <= idx < galaxies.count:
                    g = galaxies.positions[idx]
                    scene.set_focus_sphere(
                        (float(g[0]), float(g[1]), float(g[2])), radius
                    )
                    state.focus_active = True
            except Exception:
                pass
        elif tab == "environment":
            try:
                hidx = int(state.nav_halo_idx)
                d = float(state.nav_distance)
                if 0 <= hidx < halos.count:
                    pos = scene.camera._halo_index.position_of(hidx)
                    scene.set_focus_sphere(
                        (float(pos[0]), float(pos[1]), float(pos[2])), d
                    )
                    state.focus_active = True
            except Exception:
                pass
        elif tab == "box":
            try:
                xmin, xmax = (
                    float(state.nav_box_xmin),
                    float(state.nav_box_xmax),
                )
                ymin, ymax = (
                    float(state.nav_box_ymin),
                    float(state.nav_box_ymax),
                )
                zmin, zmax = (
                    float(state.nav_box_zmin),
                    float(state.nav_box_zmax),
                )
                scene.set_focus_box(xmin, xmax, ymin, ymax, zmin, zmax)
                state.focus_active = True
            except Exception:
                pass
        elif tab == "coords":
            try:
                x = float(state.nav_x)
                y = float(state.nav_y)
                z = float(state.nav_z)
                d = float(state.nav_distance)
                scene.set_focus_sphere((x, y, z), d)
                state.focus_active = True
            except Exception:
                pass
        else:
            # Other tabs (Structure, Filters, Record, Console, Library) —
            # re-apply whatever focus region was last set, if any.
            if scene._focus_region is not None:
                scene._apply_focus_masks(halos.positions, galaxies.positions)
                state.focus_active = True

        _push()

    # ------------------------------------------------------------------
    # UI helper
    # ------------------------------------------------------------------

    def _tf(v_model, label, on_enter=None, target_id=None):
        """Number-input helper. Enter binds via `target_id` (the id of
        an action button to simulate-click via the global JS handler);
        legacy callers can still pass `on_enter` and we'll keep that
        wired as a defensive backup."""
        kwargs = dict(
            v_model=(v_model,),
            label=label,
            type="number",
            hide_details=True,
            variant="outlined",
            bg_color="#1a1a2e",
            density="compact",
        )
        if on_enter is not None:
            kwargs["keydown_enter"] = on_enter
        if target_id is not None:
            with html.Div(
                raw_attrs=[f'data-enter-click="{target_id}"'],
                style="display:contents;",
            ):
                v3.VTextField(**kwargs)
        else:
            v3.VTextField(**kwargs)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    with v3.VSheet(
        color="#000000",
        style=(
            "height:100%;display:flex;flex-direction:column;"
            "color:#e2e8f0;overflow:hidden;"
        ),
    ):
        # Hidden fly-movement triggers — clicked by the keyboard handler in
        # visage.js (WASD / arrow keys). Kept in the DOM at all times so
        # getElementById always resolves regardless of the active tab.
        with html.Div(style="display:none;"):
            for _dir in ("forward", "back", "left", "right", "up", "down"):
                v3.VBtn(
                    "",
                    id=f"cam-press-{_dir}",
                    click=(server.controller.cam_press, f"['{_dir}']"),
                )
                v3.VBtn(
                    "",
                    id=f"cam-release-{_dir}",
                    click=(server.controller.cam_release, f"['{_dir}']"),
                )

        # ── Reset + Focus + Centre ─────────────────────────────────
        with v3.VSheet(
            color="transparent", style="padding:8px;flex-shrink:0;"
        ):
            with v3.VRow(no_gutters=True, style="gap:6px;"):
                with v3.VCol(style="padding:0;"):
                    v3.VBtn(
                        "Reset Camera",
                        block=True,
                        variant="outlined",
                        color="cyan",
                        density="compact",
                        click=ctrl.reset_camera,
                    )
                with v3.VCol(cols="auto", style="padding:0;"):
                    v3.VBtn(
                        icon="mdi-target",
                        variant="outlined",
                        density="compact",
                        click=ctrl.toggle_focus,
                        color=("focus_active ? 'cyan' : 'white'",),
                        title="Focus",
                    )
                with v3.VCol(cols="auto", style="padding:0;"):
                    v3.VBtn(
                        icon="mdi-image-filter-center-focus",
                        variant="outlined",
                        density="compact",
                        click=ctrl.center_camera,
                        color="white",
                        title="Place camera at box centre",
                    )

        v3.VDivider(style="flex-shrink:0;")

        # ── Tab rows: 3-up grid wrapping to multiple rows ───────────
        # NOTE: VBtnToggle's `density="compact"` clamps the wrapper to a
        # single row of buttons via a fixed --v-btn-height.  We force
        # height:auto so wrapped rows are actually visible.
        with v3.VBtnToggle(
            v_model=("nav_active_tab",),
            mandatory=True,
            style=(
                "width:100%;flex-shrink:0;background:#111827;"
                "border-radius:0;display:flex;flex-wrap:wrap;"
                "height:auto;min-height:118px;padding-bottom:6px;"
            ),
        ):
            # A lightcone has no periodic box to zoom to, but it does have
            # synthetic photometry — so swap the Box tab for a Photometry tab.
            _box_or_phot = (
                ("Photometry", "photometry")
                if scene.is_lightcone
                else ("Box", "box")
            )
            for label, value in [
                ("Structure", "layers"),
                ("Filters", "filters"),
                ("Record", "record"),
                ("Target", "target"),
                ("Environment", "environment"),
                ("Coords", "coords"),
                _box_or_phot,
                ("Console", "console"),
                ("Library", "library"),
            ]:
                v3.VBtn(
                    label,
                    value=value,
                    style=(
                        "flex:0 0 33.333%;font-size:0.72rem;letter-spacing:0;"
                        "min-width:0;height:34px;text-transform:none;"
                        "font-weight:700;"
                    ),
                    color=(
                        f"nav_active_tab === '{value}' ? 'cyan' : '#6b7280'",
                    ),
                    variant="text",
                    density="compact",
                )

        v3.VDivider(style="flex-shrink:0;")

        # ── Tab content — fills remaining panel height; scrolls vertically
        # if a tab's content is taller than the available space so that
        # nothing is ever cut off on small screens.
        with v3.VSheet(
            color="transparent",
            style=(
                "flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;"
                "padding:10px 12px;"
                "display:flex;flex-direction:column;"
            ),
        ):
            # Layers
            with v3.VSheet(
                color="transparent",
                v_show=("nav_active_tab === 'layers'",),
            ):
                html.Div(
                    "DARK MATTER HALOES",
                    style=(
                        "font-size:0.95rem;font-weight:700;letter-spacing:0.08em;"
                        "color:#c084fc;padding:6px 0 8px;display:block;"
                    ),
                )
                with v3.VSheet(color="transparent", style=_FIELD):
                    v3.VCheckbox(
                        v_model=("halos_visible",),
                        label="Visible",
                        color="#c084fc",
                        hide_details=True,
                        density="compact",
                    )
                with v3.VSheet(color="transparent", style=_FIELD):
                    v3.VSlider(
                        v_model=("halo_opacity",),
                        label="Opacity",
                        min=0.0,
                        max=1.0,
                        step=0.01,
                        thumb_label=True,
                        color="#c084fc",
                        hide_details=True,
                    )
                with v3.VSheet(color="transparent", style=_FIELD):
                    v3.VSelect(
                        v_model=("halo_color_mode",),
                        items=("halo_color_modes",),
                        label="Colour by",
                        hide_details=True,
                        variant="outlined",
                        color="#c084fc",
                        density="compact",
                    )
                with v3.VSheet(color="transparent", style=_FIELD):
                    v3.VSelect(
                        v_model=("halo_colormap",),
                        items=(_CMAPS,),
                        label="Colormap",
                        hide_details=True,
                        variant="outlined",
                        color="#c084fc",
                        density="compact",
                        disabled=("halo_color_mode === 'mvir'",),
                    )
                with v3.VSheet(
                    color="transparent", style="padding:4px 0 8px;"
                ):
                    with v3.VSheet(
                        color="transparent",
                        style="display:flex;align-items:center;gap:4px;",
                    ):
                        v3.VLabel(
                            "{{ halo_cbar_min }}",
                            style="font-size:0.6rem;color:#a3adbb;white-space:nowrap;flex-shrink:0;",
                        )
                        v3.VSheet(
                            style=("halo_cbar_style",), color="transparent"
                        )
                        v3.VLabel(
                            "{{ halo_cbar_max }}",
                            style="font-size:0.6rem;color:#a3adbb;white-space:nowrap;flex-shrink:0;",
                        )

                v3.VDivider(style="margin:14px 0;")

                v3.VLabel(
                    "GALAXIES",
                    style=(
                        "font-size:0.95rem;font-weight:700;letter-spacing:0.08em;"
                        "color:#FFD700;padding:6px 0 8px;display:block;"
                    ),
                )
                with v3.VSheet(color="transparent", style=_FIELD):
                    v3.VCheckbox(
                        v_model=("galaxies_visible",),
                        label="Visible",
                        color="#FFD700",
                        hide_details=True,
                        density="compact",
                    )
                with v3.VSheet(color="transparent", style=_FIELD):
                    v3.VSlider(
                        v_model=("galaxy_opacity",),
                        label="Opacity",
                        min=0.0,
                        max=1.0,
                        step=0.01,
                        thumb_label=True,
                        color="#FFD700",
                        hide_details=True,
                    )
                with v3.VSheet(color="transparent", style=_FIELD):
                    v3.VSelect(
                        v_model=("galaxy_color_mode",),
                        items=("galaxy_color_modes",),
                        label="Colour by",
                        hide_details=True,
                        variant="outlined",
                        color="#FFD700",
                        density="compact",
                    )
                with v3.VSheet(color="transparent", style=_FIELD):
                    v3.VSelect(
                        v_model=("galaxy_colormap",),
                        items=(_CMAPS,),
                        label="Colormap",
                        hide_details=True,
                        variant="outlined",
                        color="#FFD700",
                        density="compact",
                        # Structure mode is the bare composition (no outer
                        # property halo) — the colormap doesn't apply.
                        # Type is fixed at coolwarm. For every other mode
                        # the colormap drives the outermost layer that sits
                        # around the envelope.
                        disabled=(
                            "galaxy_color_mode === 'structure' || "
                            "galaxy_color_mode === 'type'",
                        ),
                    )
                with v3.VSheet(
                    color="transparent", style="padding:4px 0 8px;"
                ):
                    with v3.VSheet(
                        color="transparent",
                        style="display:flex;align-items:center;gap:4px;",
                    ):
                        v3.VLabel(
                            "{{ gal_cbar_min }}",
                            style="font-size:0.6rem;color:#a3adbb;white-space:nowrap;flex-shrink:0;",
                        )
                        v3.VSheet(
                            style=("gal_cbar_style",), color="transparent"
                        )
                        v3.VLabel(
                            "{{ gal_cbar_max }}",
                            style="font-size:0.6rem;color:#a3adbb;white-space:nowrap;flex-shrink:0;",
                        )

                v3.VDivider(style="margin:14px 0 10px;")

                v3.VBtn(
                    "Reset Opacities",
                    block=True,
                    variant="outlined",
                    color="red",
                    density="compact",
                    prepend_icon="mdi-restore",
                    click=ctrl.reset_opacities,
                )

            # Target (halo + galaxy combined)
            with v3.VSheet(
                color="transparent",
                v_show=("nav_active_tab === 'target'",),
            ):
                v3.VLabel(
                    "HALO",
                    style=(
                        "font-size:0.85rem;font-weight:700;letter-spacing:0.06em;"
                        "color:#c084fc;display:block;padding:4px 0 6px;"
                    ),
                )
                with v3.VSheet(color="transparent", style=_FIELD):
                    _tf(
                        "nav_halo_idx",
                        "Halo index",
                        on_enter=ctrl.go_to_halo,
                        target_id="btn-target-halo-go",
                    )
                with v3.VSheet(color="transparent", style=_FIELD):
                    _tf(
                        "nav_distance",
                        "Standoff (Mpc/h)",
                        on_enter=ctrl.go_to_halo,
                        target_id="btn-target-halo-go",
                    )
                with v3.VSheet(color="transparent", style=_BTN):
                    v3.VBtn(
                        "Go",
                        block=True,
                        color="#c084fc",
                        density="compact",
                        click=ctrl.go_to_halo,
                        id="btn-target-halo-go",
                    )

                v3.VDivider(style="margin:12px 0;")

                v3.VLabel(
                    "GALAXY",
                    style=(
                        "font-size:0.85rem;font-weight:700;letter-spacing:0.06em;"
                        "color:#FFD700;display:block;padding:4px 0 6px;"
                    ),
                )
                with v3.VSheet(color="transparent", style=_FIELD):
                    _tf(
                        "nav_gal_idx",
                        "Galaxy index",
                        on_enter=ctrl.go_to_galaxy_enter,
                        target_id="btn-target-galaxy-go",
                    )
                with v3.VSheet(color="transparent", style=_BTN):
                    v3.VBtn(
                        "Go",
                        block=True,
                        color="#FFD700",
                        density="compact",
                        click=ctrl.go_to_galaxy_enter,
                        id="btn-target-galaxy-go",
                    )
                v3.VLabel(
                    "Zoom radius (Mpc/h)",
                    style=(
                        "font-size:0.6rem;color:#9ca3af;"
                        "display:block;padding:10px 0 4px;"
                    ),
                )
                with v3.VBtnGroup(
                    variant="outlined",
                    density="compact",
                    style="width:100%;",
                ):
                    v3.VBtn(
                        "3",
                        style="flex:1;",
                        color="#FFD700",
                        click=ctrl.go_to_galaxy_1,
                    )
                    v3.VBtn(
                        "5",
                        style="flex:1;",
                        color="#FFD700",
                        click=ctrl.go_to_galaxy_3,
                    )
                    v3.VBtn(
                        "10",
                        style="flex:1;",
                        color="#FFD700",
                        click=ctrl.go_to_galaxy_5,
                    )

                v3.VDivider(style="margin:14px 0 10px;")

                v3.VBtn(
                    "Galaxy Info",
                    block=True,
                    color="#FFD700",
                    density="compact",
                    prepend_icon="mdi-information-outline",
                    click=ctrl.show_galaxy_info,
                    style="margin-bottom:6px;",
                )

                v3.VBtn(
                    "Highlight Galaxy",
                    block=True,
                    color="#FFD700",
                    variant="outlined",
                    density="compact",
                    prepend_icon="mdi-bullseye-arrow",
                    click=ctrl.highlight_galaxy,
                    style="margin-bottom:6px;",
                )

                v3.VBtn(
                    "Clear Indicator",
                    block=True,
                    variant="outlined",
                    color="red",
                    density="compact",
                    prepend_icon="mdi-close-circle-outline",
                    click=ctrl.clear_indicator,
                )

            # Environment tab — group/cluster-level selection & inspection
            with v3.VSheet(
                color="transparent",
                v_show=("nav_active_tab === 'environment'",),
            ):
                v3.VLabel(
                    "HALO  (pick a FOF group)",
                    style=(
                        "font-size:0.85rem;font-weight:700;letter-spacing:0.06em;"
                        "color:#c084fc;display:block;padding:4px 0 6px;"
                    ),
                )
                with v3.VSheet(color="transparent", style=_FIELD):
                    _tf(
                        "nav_halo_idx",
                        "Halo index",
                        on_enter=ctrl.go_to_env_halo,
                        target_id="btn-env-go",
                    )
                with v3.VSheet(color="transparent", style=_FIELD):
                    _tf(
                        "nav_distance",
                        "Standoff (Mpc/h)",
                        on_enter=ctrl.go_to_env_halo,
                        target_id="btn-env-go",
                    )
                with v3.VSheet(color="transparent", style=_BTN):
                    v3.VBtn(
                        "Go",
                        block=True,
                        color="#c084fc",
                        density="compact",
                        click=ctrl.go_to_env_halo,
                        id="btn-env-go",
                    )

                v3.VDivider(style="margin:12px 0;")

                v3.VLabel(
                    "ENVIRONMENT FILTER",
                    style=(
                        "font-size:0.85rem;font-weight:700;letter-spacing:0.06em;"
                        "color:#06b6d4;display:block;padding:4px 0 6px;"
                    ),
                )
                v3.VLabel(
                    "Show galaxies in these environments",
                    style="font-size:0.6rem;color:#9ca3af;padding:0 0 4px;display:block;",
                )
                _ENV_CB_STYLE = (
                    "margin-top:-6px;margin-bottom:-8px;"
                    "--v-input-control-height:24px;"
                )
                v3.VCheckbox(
                    v_model=("env_show_field",),
                    label="Field",
                    hide_details=True,
                    density="compact",
                    color="cyan",
                    disabled=("!model_fields.central_mvir",),
                    style=_ENV_CB_STYLE,
                )
                v3.VCheckbox(
                    v_model=("env_show_isolated",),
                    label="Isolated",
                    hide_details=True,
                    density="compact",
                    color="cyan",
                    disabled=("!model_fields.central_mvir",),
                    style=_ENV_CB_STYLE,
                )
                v3.VCheckbox(
                    v_model=("env_show_pairs",),
                    label="Pairs",
                    hide_details=True,
                    density="compact",
                    color="cyan",
                    disabled=("!model_fields.central_mvir",),
                    style=_ENV_CB_STYLE,
                )
                v3.VCheckbox(
                    v_model=("env_show_group",),
                    label="Groups",
                    hide_details=True,
                    density="compact",
                    color="cyan",
                    disabled=("!model_fields.central_mvir",),
                    style=_ENV_CB_STYLE,
                )
                v3.VCheckbox(
                    v_model=("env_show_cluster",),
                    label="Clusters",
                    hide_details=True,
                    density="compact",
                    color="cyan",
                    disabled=("!model_fields.central_mvir",),
                    style=_ENV_CB_STYLE,
                )

                v3.VDivider(style="margin:14px 0 10px;")

                v3.VBtn(
                    "Group Info",
                    block=True,
                    color="#c084fc",
                    density="compact",
                    prepend_icon="mdi-account-group-outline",
                    click=ctrl.show_group_info,
                    style="margin-bottom:6px;",
                )
                v3.VBtn(
                    "Highlight Members",
                    block=True,
                    color="#c084fc",
                    variant="outlined",
                    density="compact",
                    prepend_icon="mdi-bullseye-arrow",
                    click=ctrl.highlight_group_members,
                    style="margin-bottom:6px;",
                )
                v3.VBtn(
                    "Clear",
                    block=True,
                    variant="outlined",
                    color="red",
                    density="compact",
                    prepend_icon="mdi-close-circle-outline",
                    click=ctrl.clear_indicator,
                )

            # Coords
            with v3.VSheet(
                color="transparent",
                v_show=("nav_active_tab === 'coords'",),
            ):
                for label, key in [
                    ("X (Mpc/h)", "nav_x"),
                    ("Y (Mpc/h)", "nav_y"),
                    ("Z (Mpc/h)", "nav_z"),
                    ("Standoff", "nav_distance"),
                ]:
                    with v3.VSheet(color="transparent", style=_FIELD):
                        _tf(
                            key,
                            label,
                            on_enter=ctrl.go_to_coords,
                            target_id="btn-coords-go",
                        )
                with v3.VSheet(color="transparent", style=_BTN):
                    v3.VBtn(
                        "{{ draw_sphere_active ? 'Lock Sphere' : 'Draw Sphere' }}",
                        block=True,
                        variant="outlined",
                        color=("draw_sphere_active ? 'orange' : 'cyan'",),
                        density="compact",
                        prepend_icon=(
                            "draw_sphere_active ? 'mdi-lock-outline' : 'mdi-sphere'",
                        ),
                        click=ctrl.toggle_draw_sphere,
                        title=(
                            "draw_sphere_active "
                            "? 'Lock this sphere and apply as focus region' "
                            ": 'Place an interactive sphere you can drag to size'"
                        ),
                        style="margin-bottom:6px;",
                    )
                    v3.VBtn(
                        "Use Current Position",
                        block=True,
                        variant="outlined",
                        color="cyan",
                        density="compact",
                        prepend_icon="mdi-crosshairs-gps",
                        click=ctrl.populate_coords_from_camera,
                        style="margin-bottom:6px;",
                    )
                    v3.VBtn(
                        "Zoom",
                        block=True,
                        color="cyan",
                        density="compact",
                        click=ctrl.go_to_coords,
                        id="btn-coords-go",
                        style="margin-bottom:6px;",
                    )
                    v3.VBtn(
                        "Clear",
                        block=True,
                        variant="outlined",
                        color="#ef4444",
                        density="compact",
                        prepend_icon="mdi-close-circle-outline",
                        click=ctrl.clear_draw_sphere,
                        title="Clear sphere widget, zoom indicator and focus region",
                        v_show=("draw_sphere_active || focus_active",),
                    )

            # Box
            with v3.VSheet(
                color="transparent",
                v_show=("nav_active_tab === 'box'",),
            ):
                for label, key in [
                    ("X min", "nav_box_xmin"),
                    ("X max", "nav_box_xmax"),
                    ("Y min", "nav_box_ymin"),
                    ("Y max", "nav_box_ymax"),
                    ("Z min", "nav_box_zmin"),
                    ("Z max", "nav_box_zmax"),
                ]:
                    with v3.VSheet(color="transparent", style=_FIELD):
                        _tf(
                            key,
                            label,
                            on_enter=ctrl.zoom_to_box,
                            target_id="btn-box-zoom",
                        )
                with v3.VSheet(color="transparent", style=_BTN):
                    v3.VBtn(
                        "{{ draw_box_active ? 'Lock Box' : 'Draw Box' }}",
                        block=True,
                        variant="outlined",
                        color=("draw_box_active ? 'orange' : 'cyan'",),
                        density="compact",
                        prepend_icon=(
                            "draw_box_active ? 'mdi-lock-outline' : 'mdi-cube-outline'",
                        ),
                        click=ctrl.toggle_draw_box,
                        title=(
                            "draw_box_active "
                            "? 'Lock this box and apply as focus region' "
                            ": 'Place an interactive box you can drag to resize'"
                        ),
                        style="margin-bottom:6px;",
                    )
                    v3.VBtn(
                        "Use Current View",
                        block=True,
                        variant="outlined",
                        color="cyan",
                        density="compact",
                        prepend_icon="mdi-crosshairs-gps",
                        click=ctrl.populate_box_from_camera,
                        style="margin-bottom:6px;",
                    )
                    v3.VBtn(
                        "Zoom",
                        block=True,
                        color="cyan",
                        density="compact",
                        click=ctrl.zoom_to_box,
                        id="btn-box-zoom",
                        style="margin-bottom:6px;",
                    )
                    v3.VBtn(
                        "Clear",
                        block=True,
                        variant="outlined",
                        color="#ef4444",
                        density="compact",
                        prepend_icon="mdi-close-circle-outline",
                        click=ctrl.clear_draw_box,
                        title="Clear box widget, zoom indicator and focus region",
                        v_show=("draw_box_active || focus_active",),
                    )

            # Photometry (Lightcone Mode only — replaces the Box tab). Its own
            # independent splat layer: a false-colour image built from the
            # ticked filter/M-L stack, shown on top of (or instead of) the
            # normal galaxies.
            with v3.VSheet(
                color="transparent",
                v_show=("nav_active_tab === 'photometry'",),
            ):
                v3.VLabel(
                    "SYNTHETIC PHOTOMETRY (SED)",
                    style=(
                        "font-size:0.95rem;font-weight:700;letter-spacing:0.08em;"
                        "color:#7FDBFF;padding:2px 0 8px;display:block;"
                    ),
                )
                # No SED data → just say so (the LightSAGE run had SED off).
                html.Div(
                    "This lightcone was built without synthetic photometry. "
                    "Re-run the LightSAGE flow with SED enabled to use this.",
                    v_show=("!has_sed_data",),
                    style="font-size:0.72rem;color:#9ca3af;line-height:1.4;",
                )
                with html.Div(v_show=("has_sed_data",)):
                    html.Div(
                        "A false-colour image built from the filters you tick "
                        "— each tinted its own colour, stacked. A completely "
                        "separate layer from the galaxies: show it with the "
                        "galaxies on, off, or on its own.",
                        style="font-size:0.66rem;color:#8b98a5;padding:0 0 8px;line-height:1.35;",
                    )
                    with v3.VSheet(color="transparent", style=_FIELD):
                        v3.VCheckbox(
                            v_model=("photometry_visible",),
                            label="Visible",
                            color="#7FDBFF",
                            hide_details=True,
                            density="compact",
                        )
                    with v3.VSheet(color="transparent", style=_FIELD):
                        v3.VSlider(
                            v_model=("photometry_opacity",),
                            label="Opacity",
                            min=0.0,
                            max=1.0,
                            step=0.01,
                            thumb_label=True,
                            color="#7FDBFF",
                            hide_details=True,
                        )
                    with v3.VSheet(color="transparent", style=_FIELD):
                        # Multi-select: ticking several filters stacks them
                        # into the composite. Ticks show the current stack.
                        v3.VSelect(
                            v_model=("sed_galaxy_bands",),
                            items=("sed_color_modes",),
                            label="Filters (tick to stack)",
                            multiple=True,
                            chips=True,
                            closable_chips=True,
                            hide_details=True,
                            variant="outlined",
                            color="#7FDBFF",
                            density="compact",
                        )
                    # Legend: one swatch per ticked filter, in its own colour.
                    with v3.VSheet(
                        color="transparent",
                        style="padding:8px 0 0;display:flex;flex-wrap:wrap;gap:6px 12px;",
                        v_show=("sed_legend.length > 0",),
                    ):
                        with html.Div(
                            v_for=("s in sed_legend",),
                            key=("s.title",),
                            style="display:flex;align-items:center;gap:5px;",
                        ):
                            html.Div(
                                style=(
                                    "'width:11px;height:11px;border-radius:2px;"
                                    "flex-shrink:0;background:' + s.color",
                                )
                            )
                            html.Span(
                                "{{ s.title }}",
                                style="font-size:0.62rem;color:#a3adbb;white-space:nowrap;",
                            )

            # ── CONSOLE tab — multi-session REPL ────────────────────
            # Layout: heading + tab strip pinned to the top, history
            # absorbs all remaining vertical space, and a bottom-anchored
            # block carries the two text fields plus the 4 action
            # buttons. `margin-top:auto` on the bottom block guarantees
            # it sits flush against the panel's bottom edge.
            with html.Div(
                v_show=("nav_active_tab === 'console'",),
                style=(
                    "display:flex;flex-direction:column;"
                    "height:100%;min-height:0;width:100%;"
                ),
            ):
                # Heading + session tab strip on one line — saves a row
                # of vertical space and keeps the buttons clearly visible.
                # `min-height` and `padding` are generous so the small
                # buttons don't visually clip inside the flex column.
                with html.Div(
                    style=(
                        "display:flex;align-items:center;gap:6px;"
                        "padding:2px 0 6px;flex-shrink:0;flex-wrap:wrap;"
                    ),
                ):
                    html.Span(
                        "CONSOLE",
                        style=(
                            "font-size:0.85rem;font-weight:700;"
                            "letter-spacing:0.08em;color:#06b6d4;"
                            "margin-right:4px;"
                        ),
                    )
                    # Per-session buttons — render the title + close X
                    # as a single contiguous span so flex-wrap keeps
                    # them together instead of breaking mid-session.
                    with html.Span(
                        v_for=("c in consoles_list",),
                        key=("c.id",),
                        style=(
                            "display:inline-flex;align-items:center;gap:2px;"
                        ),
                    ):
                        v3.VBtn(
                            "{{ c.title }}",
                            size="x-small",
                            density="compact",
                            variant=(
                                "console_active_id === c.id ? 'flat' "
                                ": 'outlined'",
                            ),
                            color=(
                                "console_active_id === c.id ? 'cyan' "
                                ": '#6b7280'",
                            ),
                            click=(
                                "trigger('console_switch_trigger', [c.id])"
                            ),
                            style=(
                                "text-transform:none;font-size:0.62rem;"
                                "min-width:0;padding:0 8px;height:22px;"
                            ),
                        )
                        v3.VBtn(
                            icon="mdi-close",
                            size="x-small",
                            density="compact",
                            variant="text",
                            color="#6b7280",
                            v_show=("consoles_list.length > 1",),
                            click=("trigger('console_close_trigger', [c.id])"),
                            style="min-width:18px;padding:0;height:22px;",
                        )
                    v3.VBtn(
                        icon="mdi-plus",
                        size="x-small",
                        density="compact",
                        variant="outlined",
                        color="cyan",
                        click=ctrl.console_new,
                        title="New console",
                        style="min-width:24px;padding:0;height:22px;",
                    )
                    # Mode selector — terminal (>_) and SAGE command mode (cmd).
                    v3.VBtn(
                        ">_",
                        size="x-small",
                        density="compact",
                        variant=(
                            "console_mode === 'terminal' ? 'flat' : 'outlined'",
                        ),
                        color=(
                            "console_mode === 'terminal' ? 'cyan' : '#6b7280'",
                        ),
                        click=ctrl.console_mode_terminal,
                        title="Terminal",
                        style=(
                            "text-transform:none;font-size:0.62rem;"
                            "min-width:0;padding:0 6px;height:22px;"
                            "font-family:monospace;margin-left:4px;"
                        ),
                    )
                    v3.VBtn(
                        "cmd",
                        size="x-small",
                        density="compact",
                        variant=(
                            "console_mode === 'command' ? 'flat' : 'outlined'",
                        ),
                        color=(
                            "console_mode === 'command' ? 'cyan' : '#6b7280'",
                        ),
                        click=ctrl.console_mode_sage,
                        title="SAGE command mode",
                        style=(
                            "text-transform:none;font-size:0.62rem;"
                            "min-width:0;padding:0 6px;height:22px;"
                            "font-family:monospace;"
                        ),
                    )

                # Hidden relay inputs — JS dispatches native input events to these
                # to push PTY state to the server.  window.trame.set() only
                # updates the local client store; the v-model binding here goes
                # through Vue's reactivity which is the only path that actually
                # reaches @state.change handlers on the server.
                html.Input(
                    id="sage-pty-input-relay",
                    v_model=("pty_input_raw",),
                    type="text",
                    style=(
                        "position:fixed;left:-9999px;"
                        "width:1px;height:1px;opacity:0;pointer-events:none;"
                    ),
                )
                html.Input(
                    id="sage-pty-ensure-relay",
                    v_model=("pty_ensure_seq",),
                    type="text",
                    style=(
                        "position:fixed;left:-9999px;"
                        "width:1px;height:1px;opacity:0;pointer-events:none;"
                    ),
                )

                # xterm.js terminal — shown in terminal mode.
                html.Div(
                    id=("'sage-pty-' + console_active_id",),
                    v_show=("console_mode === 'terminal'",),
                    style=(
                        "flex:1 1 0;min-height:0;"
                        "border:1px solid #1f2937;border-radius:4px;"
                        "overflow:hidden;"
                    ),
                )

                # Terminal action row — pop-out + close, only in terminal mode.
                with html.Div(
                    v_show=("console_mode === 'terminal'",),
                    style=(
                        "margin-top:6px;flex-shrink:0;"
                        "display:flex;gap:6px;align-items:center;"
                    ),
                ):
                    v3.VBtn(
                        "Pop-out",
                        variant="outlined",
                        color=("console_popout_show ? 'cyan' : '#6b7280'",),
                        density="compact",
                        prepend_icon="mdi-dock-window",
                        click=ctrl.console_toggle_popout,
                        style="flex:1 1 auto;",
                    )
                    v3.VBtn(
                        icon="mdi-close-circle-outline",
                        variant="outlined",
                        color="red",
                        density="compact",
                        click=ctrl.console_close_pty,
                        title="Close terminal",
                        style="flex-shrink:0;min-width:36px;",
                    )

                # History — shown in SAGE command mode.
                with v3.VSheet(
                    color="#0a0a0f",
                    classes="sage-console-scroll",
                    v_show=("console_mode === 'command'",),
                    style=(
                        "flex:1 1 0;min-height:0;overflow-y:auto;"
                        "padding:6px 8px;border:1px solid #1f2937;"
                        "border-radius:4px;font-family:monospace;"
                        "font-size:0.7rem;line-height:1.4;"
                    ),
                ):
                    with html.Div(
                        v_for=("entry in console_history",),
                        key=("entry.id",),
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
                            style="color:#9ca3af;white-space:pre-wrap;",
                        )

                # Bottom block — input field and action buttons (command mode only).
                with html.Div(
                    v_show=("console_mode === 'command'",),
                    style=(
                        "margin-top:6px;flex-shrink:0;"
                        "display:flex;flex-direction:column;gap:6px;"
                    ),
                ):
                    with html.Div(
                        raw_attrs=['data-enter-click="btn-console-run"'],
                    ):
                        v3.VTextField(
                            v_model=("console_input",),
                            label="SAGE Commands  (type exit to return to terminal)",
                            hide_details=True,
                            variant="outlined",
                            bg_color="#1a1a2e",
                            density="compact",
                            keydown_enter=ctrl.console_submit,
                        )
                    with v3.VRow(no_gutters=True, style="gap:6px;"):
                        with v3.VCol(style="padding:0;"):
                            v3.VBtn(
                                "Run",
                                block=True,
                                color="cyan",
                                density="compact",
                                prepend_icon="mdi-play",
                                click=ctrl.console_submit,
                                id="btn-console-run",
                            )
                        with v3.VCol(style="padding:0;"):
                            v3.VBtn(
                                "Clear",
                                block=True,
                                variant="outlined",
                                color="red",
                                density="compact",
                                prepend_icon="mdi-delete-sweep-outline",
                                click=ctrl.console_clear,
                            )
                    v3.VBtn(
                        "Pop-out",
                        block=True,
                        variant="outlined",
                        color=("console_popout_show ? 'cyan' : '#6b7280'",),
                        density="compact",
                        prepend_icon="mdi-dock-window",
                        click=ctrl.console_toggle_popout,
                    )

            # ── LIBRARY tab — browse stored media ──────────────
            with v3.VSheet(
                color="transparent",
                v_show=("nav_active_tab === 'library'",),
                style=(
                    "display:flex;flex-direction:column;"
                    "height:100%;min-height:0;width:100%;"
                ),
            ):
                v3.VLabel(
                    "MEDIA LIBRARY",
                    style=(
                        "font-size:0.95rem;font-weight:700;letter-spacing:0.08em;"
                        "color:#06b6d4;padding:4px 0 4px;display:block;"
                        "flex-shrink:0;"
                    ),
                )
                v3.VLabel(
                    "Screenshots and movies from sage_library/ and "
                    "sage_outputs/ in your working directory.  Double-click a row to open as a floating viewer.",
                    style=(
                        "font-size:0.6rem;color:#9ca3af;line-height:1.35;"
                        "display:block;padding:0 0 4px;flex-shrink:0;"
                    ),
                )
                # File list — flex-fills the available vertical space so the
                # black box runs the full height of the panel.
                with v3.VSheet(
                    color="#0a0a0f",
                    style=(
                        "flex:1 1 0;min-height:0;overflow-y:auto;"
                        "border:1px solid #1f2937;border-radius:4px;"
                        "margin-top:6px;"
                    ),
                ):
                    with html.Div():
                        with html.Template(
                            v_for=("entry in library_files",),
                            key=("entry.path",),
                        ):
                            # Folder header — primary grouping. Shown above
                            # the first file of each source folder.
                            with html.Div(
                                v_if=("entry.first_in_folder",),
                                style=(
                                    "display:flex;align-items:center;gap:4px;"
                                    "padding:8px 6px 4px;"
                                    "border-top:2px solid #475569;"
                                    "background:#111827;"
                                ),
                            ):
                                v3.VIcon(
                                    "mdi-folder-outline",
                                    color="#94a3b8",
                                    size="x-small",
                                    style="flex-shrink:0;",
                                )
                                html.Div(
                                    "{{ entry.folder }}",
                                    style=(
                                        "font-size:0.65rem;color:#cbd5e1;"
                                        "font-weight:700;letter-spacing:0.04em;"
                                        "white-space:nowrap;overflow:hidden;"
                                        "text-overflow:ellipsis;"
                                    ),
                                )
                            # Type sub-divider within a folder (types sorted,
                            # files alphabetical within each type).
                            html.Div(
                                "{{ entry.ext.toUpperCase() }}",
                                v_if=("entry.first_in_group",),
                                style=(
                                    "font-size:0.6rem;color:#22d3ee;"
                                    "letter-spacing:0.08em;font-weight:600;"
                                    "padding:4px 6px 2px 14px;"
                                    "background:#0d1117;"
                                ),
                            )
                            with html.Div(
                                style=(
                                    "display:flex;align-items:center;gap:6px;"
                                    "padding:4px 6px;"
                                    "border-bottom:1px solid #1f2937;"
                                    "cursor:pointer;"
                                ),
                            ):
                                v3.VIcon(
                                    icon=(
                                        "entry.kind === 'video' "
                                        "? 'mdi-movie-open-outline' "
                                        ": 'mdi-image-outline'",
                                    ),
                                    color="cyan",
                                    size="small",
                                    style="flex-shrink:0;",
                                )
                                with html.Div(
                                    style="flex:1;min-width:0;",
                                    dblclick=(
                                        server.controller.library_open,
                                        "[entry.path]",
                                    ),
                                ):
                                    html.Div(
                                        "{{ entry.name }}",
                                        style=(
                                            "font-size:0.72rem;color:#e5e7eb;"
                                            "white-space:nowrap;overflow:hidden;"
                                            "text-overflow:ellipsis;"
                                        ),
                                    )
                                    html.Div(
                                        "{{ entry.ext.toUpperCase() }}"
                                        " · {{ entry.size_kb }} KB",
                                        style="font-size:0.6rem;color:#6b7280;",
                                    )
                                v3.VBtn(
                                    icon="mdi-delete-outline",
                                    density="compact",
                                    size="x-small",
                                    color="red",
                                    variant="text",
                                    style="flex-shrink:0;",
                                    click=(
                                        server.controller.library_delete,
                                        "[entry.path]",
                                    ),
                                )
                # Bottom block — count + action buttons anchored to the
                # panel's bottom edge, mirroring the Console tab layout.
                with html.Div(
                    style=(
                        "margin-top:6px;flex-shrink:0;"
                        "display:flex;flex-direction:column;gap:6px;"
                    ),
                ):
                    v3.VLabel(
                        "{{ library_files.length }} file"
                        "{{ library_files.length === 1 ? '' : 's' }}",
                        style=(
                            "font-size:0.6rem;color:#6b7280;display:block;"
                        ),
                    )
                    with v3.VRow(no_gutters=True, style="gap:6px;"):
                        with v3.VCol(style="padding:0;"):
                            v3.VBtn(
                                "Refresh",
                                block=True,
                                color="cyan",
                                density="compact",
                                size="small",
                                prepend_icon="mdi-refresh",
                                click=ctrl.library_refresh,
                            )
                        with v3.VCol(style="padding:0;"):
                            v3.VBtn(
                                "Close all",
                                block=True,
                                variant="outlined",
                                color="red",
                                density="compact",
                                size="small",
                                prepend_icon="mdi-close-circle-outline",
                                click=ctrl.library_close,
                            )

            # ── FILTERS tab ────────────────────────────────────
            with v3.VSheet(
                color="transparent",
                v_show=("nav_active_tab === 'filters'",),
            ):
                _FSEC_HALO = (
                    "font-size:0.85rem;font-weight:700;letter-spacing:0.06em;"
                    "color:#c084fc;padding:2px 0 2px;display:block;"
                    "text-align:center;"
                )
                _FSEC_GAL = (
                    "font-size:0.85rem;font-weight:700;letter-spacing:0.06em;"
                    "color:#FFD700;padding:2px 0 2px;display:block;"
                    "text-align:center;"
                )
                _FLBL = (
                    "font-size:0.8rem;color:#9ca3af;display:block;"
                    "padding:2px 0 0;text-align:center;"
                )
                _FSLD = (
                    "padding:0;margin-top:-14px;margin-bottom:-14px;"
                    "margin-left:-12.5%;"
                    "transform:scale(0.65);transform-origin:center center;"
                    "width:125%;"
                )
                _FSEL = (
                    "--v-input-control-height:30px;"
                    "--v-field-font-size:0.8rem;"
                    "margin-top:1px;"
                )
                # Explicit heights so each section scrolls independently
                # while the panel itself never needs an outer scrollbar.
                _SH = "overflow-y:auto;overflow-x:hidden;padding-right:2px;padding-top:18px;"

                # ── Halo section ──────────────────────────────
                v3.VLabel("DARK MATTER HALOES", style=_FSEC_HALO)
                with html.Div(style=_SH + "height:120px;"):
                    html.Div("Mvir  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_halo_mvir",),
                        min=10.0,
                        max=15.0,
                        step=0.1,
                        thumb_label=True,
                        color="#c084fc",
                        density="compact",
                        hide_details=True,
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Rvir  (Mpc/h)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_halo_rvir",),
                        min=0.0,
                        max=3.0,
                        step=0.05,
                        thumb_label=True,
                        color="#c084fc",
                        density="compact",
                        hide_details=True,
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Vvir  (km/s)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_halo_vvir",),
                        min=0.0,
                        max=1000.0,
                        step=10.0,
                        thumb_label=True,
                        color="#c084fc",
                        density="compact",
                        hide_details=True,
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Vmax  (km/s)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_halo_vmax",),
                        min=0.0,
                        max=1000.0,
                        step=10.0,
                        thumb_label=True,
                        color="#c084fc",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.vmax",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Len  (DM particles)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_halo_len",),
                        min=0,
                        max=10000,
                        step=100,
                        thumb_label=True,
                        color="#c084fc",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.len_particles",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Concentration  (NFW)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_halo_conc",),
                        min=0.0,
                        max=50.0,
                        step=0.5,
                        thumb_label=True,
                        color="#c084fc",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.concentration",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Spin  (dimensionless)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_halo_spin",),
                        min=0.0,
                        max=0.2,
                        step=0.002,
                        thumb_label=True,
                        color="#c084fc",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.spin",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )

                v3.VDivider(style="margin:4px 0 2px;")

                # ── Galaxy section ────────────────────────────
                html.Div("GALAXIES", style=_FSEC_GAL)
                with html.Div(style=_SH + "height:185px;"):
                    # ── Top 5 ──────────────────────────────────────
                    html.Div("Stellar mass  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_smass",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div(
                        "SFR  (log10 Msun/yr,  -6 = quenched)", style=_FLBL
                    )
                    v3.VRangeSlider(
                        v_model=("filter_gal_sfr",),
                        min=-6.0,
                        max=5.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("sSFR  (log10 yr^-1)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_ssfr",),
                        min=-14.0,
                        max=0.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("B / T  (BulgeMass / StellarMass)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_bt",),
                        min=0.0,
                        max=1.0,
                        step=0.02,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Stellar age  (Gyr, mass-weighted)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_age",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.mean_age",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    # ── Alphabetical ──────────────────────────────
                    html.Div("BH mass  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_bhmass",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.bh_mass",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Bulge mass  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_bulge",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Bulge radius  (log10 Mpc/h)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_bulgerad",),
                        min=-4.0,
                        max=1.0,
                        step=0.05,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.bulge_radius",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("CGM gas  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_cgmgas",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.cgm_gas",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Cold gas  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_coldgas",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Cooling  (log10 SAGE units)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_cooling",),
                        min=-7.0,
                        max=7.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.cooling",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Disk radius  (log10 Mpc/h)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_diskrad",),
                        min=-4.0,
                        max=1.0,
                        step=0.05,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.disk_radius",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Ejected mass  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_ejected",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.ejected_mass",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("H1 gas  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_h1gas",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.h1_gas",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("H2 gas  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_h2",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.h2_mass",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Heating  (log10 SAGE units)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_heating",),
                        min=-7.0,
                        max=7.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.heating",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Hot gas  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_hotgas",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.hot_gas",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div(
                        "Instability bulge mass  (log10 Msun)", style=_FLBL
                    )
                    v3.VRangeSlider(
                        v_model=("filter_gal_ib_mass",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.instability_bulge_mass",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div(
                        "Instability bulge radius  (log10 Mpc/h)", style=_FLBL
                    )
                    v3.VRangeSlider(
                        v_model=("filter_gal_ib_rad",),
                        min=-4.0,
                        max=1.0,
                        step=0.05,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.instability_bulge_radius",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("ICS mass  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_ics",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.ics_mass",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div(
                        "Mass loading  (log10 OutflowRate/SFR)", style=_FLBL
                    )
                    v3.VRangeSlider(
                        v_model=("filter_gal_massload",),
                        min=-3.0,
                        max=5.0,
                        step=0.05,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.mass_loading",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Merger bulge mass  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_mb_mass",),
                        min=0.0,
                        max=14.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.merger_bulge_mass",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Merger bulge radius  (log10 Mpc/h)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_mb_rad",),
                        min=-4.0,
                        max=1.0,
                        step=0.05,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.merger_bulge_radius",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Metals — bulge mass  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_met_bm",),
                        min=-2.0,
                        max=12.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.metals_bulge_mass",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Metals — CGM gas  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_met_cgm",),
                        min=-2.0,
                        max=12.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.metals_cgm_gas",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Metals — cold gas  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_met_cg",),
                        min=-2.0,
                        max=12.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.metals_cold_gas",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div(
                        "Metals — ejected mass  (log10 Msun)", style=_FLBL
                    )
                    v3.VRangeSlider(
                        v_model=("filter_gal_met_em",),
                        min=-2.0,
                        max=12.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.metals_ejected_mass",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Metals — hot gas  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_met_hg",),
                        min=-2.0,
                        max=12.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.metals_hot_gas",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Metals — ICS  (log10 Msun)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_met_ics",),
                        min=-2.0,
                        max=12.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.metals_ics",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div(
                        "Metals — stellar mass  (log10 Msun)", style=_FLBL
                    )
                    v3.VRangeSlider(
                        v_model=("filter_gal_met_sm",),
                        min=-2.0,
                        max=12.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.metals_stellar_mass",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("Outflow rate  (log10 Msun/yr)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_outflow",),
                        min=-6.0,
                        max=5.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.outflow_rate",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("SFR bulge  (log10 Msun/yr)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_sfr_bulge",),
                        min=-6.0,
                        max=5.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.sfr_bulge",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("SFR bulge Z  (log10 dimensionless)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_sfr_blg_z",),
                        min=-6.0,
                        max=1.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.sfr_bulge_z",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("SFR disk  (log10 Msun/yr)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_sfr_disk",),
                        min=-6.0,
                        max=5.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.sfr_disk",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )
                    html.Div("SFR disk Z  (log10 dimensionless)", style=_FLBL)
                    v3.VRangeSlider(
                        v_model=("filter_gal_sfr_dsk_z",),
                        min=-6.0,
                        max=1.0,
                        step=0.1,
                        thumb_label=True,
                        color="#FFD700",
                        density="compact",
                        hide_details=True,
                        disabled=("!model_fields.sfr_disk_z",),
                        thumb_size=10,
                        track_size=2,
                        classes="sage-fslider",
                        style=_FSLD,
                    )

                v3.VDivider(style="margin:4px 0 2px;")

                # ── Categorical section ───────────────────────
                html.Div("CATEGORICAL", style=_FSEC_GAL)
                with html.Div(style="padding-top:18px;"):
                    html.Div("Type", style=_FLBL)
                    v3.VSelect(
                        v_model=("filter_gal_type",),
                        items=(
                            [
                                {"title": "All", "value": "both"},
                                {"title": "Centrals", "value": "central"},
                                {"title": "Satellites", "value": "satellite"},
                            ],
                        ),
                        hide_details=True,
                        variant="outlined",
                        color="#FFD700",
                        density="compact",
                        style=_FSEL,
                    )
                    html.Div("FFB regime", style=_FLBL)
                    v3.VSelect(
                        v_model=("filter_gal_ffb",),
                        items=(
                            [
                                {"title": "Any", "value": "any"},
                                {"title": "FFB only", "value": "yes"},
                                {"title": "Non-FFB only", "value": "no"},
                            ],
                        ),
                        hide_details=True,
                        variant="outlined",
                        color="#FFD700",
                        density="compact",
                        disabled=("!model_fields.ffb_regime",),
                        style=_FSEL,
                    )
                    html.Div("CGM / Hot regime", style=_FLBL)
                    v3.VSelect(
                        v_model=("filter_gal_cgm",),
                        items=(
                            [
                                {"title": "Any", "value": "any"},
                                {"title": "CGM galaxies", "value": "cold"},
                                {
                                    "title": "Hot atmosphere galaxies",
                                    "value": "hot",
                                },
                            ],
                        ),
                        hide_details=True,
                        variant="outlined",
                        color="#FFD700",
                        density="compact",
                        disabled=("!model_fields.cgm_regime",),
                        style=_FSEL,
                    )

                v3.VDivider(style="margin:6px 0 4px;")

                v3.VBtn(
                    "Reset Filters",
                    block=True,
                    variant="outlined",
                    color="red",
                    density="compact",
                    size="small",
                    prepend_icon="mdi-restore",
                    click=ctrl.reset_filters,
                )

            # ── RECORD tab ─────────────────────────────────────
            with v3.VSheet(
                color="transparent",
                v_show=("nav_active_tab === 'record'",),
            ):
                v3.VLabel(
                    "SCREENSHOT",
                    style=(
                        "font-size:0.95rem;font-weight:700;letter-spacing:0.08em;"
                        "color:#06b6d4;padding:6px 0 8px;display:block;"
                    ),
                )
                with html.Div(
                    raw_attrs=['data-enter-click="btn-take-screenshot"'],
                ):
                    v3.VTextField(
                        v_model=("screenshot_label",),
                        label="Label (optional)",
                        hide_details=True,
                        variant="outlined",
                        bg_color="#1a1a2e",
                        density="compact",
                        style="padding-bottom:8px;",
                        keydown_enter=ctrl.take_screenshot,
                    )
                v3.VBtn(
                    "Take Screenshot",
                    block=True,
                    color="cyan",
                    density="compact",
                    prepend_icon="mdi-camera",
                    click=ctrl.take_screenshot,
                    id="btn-take-screenshot",
                )
                with v3.VRow(
                    no_gutters=True, style="gap:6px;padding-top:6px;"
                ):
                    with v3.VCol(style="padding:0;"):
                        v3.VBtn(
                            "PNG",
                            block=True,
                            variant="outlined",
                            color="cyan",
                            density="compact",
                            click=ctrl.screenshot_png,
                        )
                    with v3.VCol(style="padding:0;"):
                        v3.VBtn(
                            "JPG",
                            block=True,
                            variant="outlined",
                            color="cyan",
                            density="compact",
                            click=ctrl.screenshot_jpg,
                        )
                    with v3.VCol(style="padding:0;"):
                        v3.VBtn(
                            "TIFF",
                            block=True,
                            variant="outlined",
                            color="cyan",
                            density="compact",
                            click=ctrl.screenshot_tiff,
                        )
                v3.VLabel(
                    "Saved to sage_outputs/session_*/ in your working directory",
                    style="font-size:0.62rem;color:#6b7280;display:block;padding:6px 0 2px;",
                )
                v3.VLabel(
                    "{{ last_screenshot ? 'Last: ' + last_screenshot : '' }}",
                    style="font-size:0.6rem;color:#6b7280;display:block;word-break:break-all;",
                )

                v3.VDivider(style="margin:14px 0;")

                v3.VLabel(
                    "RECORD MOVIE",
                    style=(
                        "font-size:0.95rem;font-weight:700;letter-spacing:0.08em;"
                        "color:#06b6d4;padding:6px 0 8px;display:block;"
                    ),
                )
                with html.Div(
                    raw_attrs=['data-enter-click="btn-start-recording"'],
                ):
                    v3.VTextField(
                        v_model=("movie_label",),
                        label="Label (optional)",
                        hide_details=True,
                        variant="outlined",
                        bg_color="#1a1a2e",
                        density="compact",
                        style="padding-bottom:8px;",
                        keydown_enter=ctrl.start_recording,
                    )
                v3.VLabel(
                    "FPS (output)  {{ '— ' + movie_fps }}",
                    style="font-size:0.6rem;color:#9ca3af;display:block;padding:4px 0 2px;",
                )
                v3.VSlider(
                    v_model=("movie_fps",),
                    min=1,
                    max=60,
                    step=1,
                    thumb_label=True,
                    color="cyan",
                    density="compact",
                    hide_details=True,
                )

                v3.VLabel(
                    "Resolution",
                    style="font-size:0.6rem;color:#9ca3af;display:block;padding:10px 0 2px;",
                )
                v3.VSelect(
                    v_model=("movie_resolution",),
                    items=(
                        [
                            {"title": "Native  (1×)", "value": "native"},
                            {"title": "High   (2× window)", "value": "hd"},
                            {"title": "Ultra  (4× window)", "value": "uhd"},
                        ],
                    ),
                    hide_details=True,
                    variant="outlined",
                    color="cyan",
                    density="compact",
                )

                v3.VLabel(
                    "Output format",
                    style="font-size:0.6rem;color:#9ca3af;display:block;padding:10px 0 2px;",
                )
                v3.VSelect(
                    v_model=("movie_format",),
                    items=(
                        [
                            {"title": "GIF", "value": "gif"},
                            {"title": "MOV  (H.264)", "value": "mov"},
                            {"title": "PNG sequence", "value": "png"},
                        ],
                    ),
                    hide_details=True,
                    variant="outlined",
                    color="cyan",
                    density="compact",
                )

                # GIF-only: repeat (loop) checkbox
                v3.VCheckbox(
                    v_model=("movie_loop",),
                    label="Loop GIF forever",
                    v_show=("movie_format === 'gif'",),
                    color="cyan",
                    density="compact",
                    hide_details=True,
                    style="padding-top:4px;",
                )

                with v3.VRow(
                    no_gutters=True, style="gap:6px;padding-top:10px;"
                ):
                    with v3.VCol(style="padding:0;"):
                        v3.VBtn(
                            "Start",
                            block=True,
                            color="red",
                            density="compact",
                            prepend_icon="mdi-record-circle-outline",
                            click=ctrl.start_recording,
                            disabled=("recording_active",),
                            id="btn-start-recording",
                        )
                    with v3.VCol(style="padding:0;"):
                        v3.VBtn(
                            "Stop",
                            block=True,
                            color="#6b7280",
                            density="compact",
                            prepend_icon="mdi-stop",
                            click=ctrl.stop_recording,
                            disabled=("!recording_active",),
                        )

                v3.VLabel(
                    "{{ recording_active ? '● Recording — ' + recording_frames + ' frames' : 'Idle' }}",
                    style="font-size:0.6rem;color:#9ca3af;display:block;padding:10px 0 2px;",
                )
                v3.VLabel(
                    "{{ last_movie ? 'Last: ' + last_movie : '' }}",
                    style="font-size:0.6rem;color:#6b7280;display:block;word-break:break-all;padding:4px 0;",
                )
