"""Per-simulation-box state profiles.

When multiple simulation boxes are loaded side-by-side, each box
remembers its own snapshot, filter settings, and layer rendering
settings independently.  Switching the active box saves the outgoing
box's profile and restores the incoming one.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# ── Keys that are per-box (saved / restored on active-box switch) ────────────
# Order matches the initialisation sequence in navigation_panel.py / toolbar.py.

SNAPSHOT_KEYS: list[str] = [
    "snap_num",
    "snap_max",
]

LAYER_KEYS: list[str] = [
    "halos_visible",
    "galaxies_visible",
    "halo_opacity",
    "halo_color_mode",
    "halo_colormap",
    "galaxy_colormap",
    "galaxy_color_mode",
    "galaxy_opacity",
]

FILTER_KEYS: list[str] = [
    # Halo range filters
    "filter_halo_mvir",
    "filter_halo_rvir",
    "filter_halo_vvir",
    "filter_halo_len",
    "filter_halo_vmax",
    "filter_halo_conc",
    "filter_halo_spin",
    # Galaxy range filters
    "filter_gal_smass",
    "filter_gal_sfr",
    "filter_gal_ssfr",
    "filter_gal_coldgas",
    "filter_gal_bulge",
    "filter_gal_bt",
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
    "filter_gal_age",
    # Categorical filters
    "filter_gal_type",
    "filter_gal_ffb",
    "filter_gal_cgm",
]

BOX_PROFILE_KEYS: list[str] = SNAPSHOT_KEYS + LAYER_KEYS + FILTER_KEYS


# ── Default values that match navigation_panel.py initialisation ─────────────

_FILTER_DEFAULTS: dict[str, Any] = {
    "filter_halo_mvir": [10.0, 15.0],
    "filter_halo_rvir": [0.0, 3.0],
    "filter_halo_vvir": [0.0, 1000.0],
    "filter_halo_len": [0, 10000],
    "filter_halo_vmax": [0.0, 1000.0],
    "filter_halo_conc": [0.0, 50.0],
    "filter_halo_spin": [0.0, 0.2],
    "filter_gal_smass": [0.0, 14.0],
    "filter_gal_sfr": [-6.0, 5.0],
    "filter_gal_ssfr": [-14.0, 0.0],
    "filter_gal_coldgas": [0.0, 14.0],
    "filter_gal_bulge": [0.0, 14.0],
    "filter_gal_bt": [0.0, 1.0],
    "filter_gal_bhmass": [0.0, 14.0],
    "filter_gal_ics": [0.0, 14.0],
    "filter_gal_h2": [0.0, 14.0],
    "filter_gal_cgmgas": [0.0, 14.0],
    "filter_gal_hotgas": [0.0, 14.0],
    "filter_gal_h1gas": [0.0, 14.0],
    "filter_gal_ejected": [0.0, 14.0],
    "filter_gal_outflow": [-6.0, 5.0],
    "filter_gal_massload": [-3.0, 5.0],
    "filter_gal_cooling": [-7.0, 7.0],
    "filter_gal_heating": [-7.0, 7.0],
    "filter_gal_diskrad": [-4.0, 1.0],
    "filter_gal_bulgerad": [-4.0, 1.0],
    "filter_gal_mb_mass": [0.0, 14.0],
    "filter_gal_mb_rad": [-4.0, 1.0],
    "filter_gal_ib_mass": [0.0, 14.0],
    "filter_gal_ib_rad": [-4.0, 1.0],
    "filter_gal_sfr_bulge": [-6.0, 5.0],
    "filter_gal_sfr_disk": [-6.0, 5.0],
    "filter_gal_sfr_blg_z": [-6.0, 1.0],
    "filter_gal_sfr_dsk_z": [-6.0, 1.0],
    "filter_gal_met_cg": [-2.0, 12.0],
    "filter_gal_met_sm": [-2.0, 12.0],
    "filter_gal_met_bm": [-2.0, 12.0],
    "filter_gal_met_hg": [-2.0, 12.0],
    "filter_gal_met_em": [-2.0, 12.0],
    "filter_gal_met_ics": [-2.0, 12.0],
    "filter_gal_met_cgm": [-2.0, 12.0],
    "filter_gal_age": [0.0, 14.0],
    "filter_gal_type": "both",
    "filter_gal_ffb": "any",
    "filter_gal_cgm": "any",
}

_LAYER_DEFAULTS: dict[str, Any] = {
    "halos_visible": True,
    "galaxies_visible": True,
    "halo_opacity": 0.12,
    "halo_color_mode": "mvir",
    "halo_colormap": "viridis",
    "galaxy_colormap": "plasma",
    "galaxy_color_mode": "structure",
    "galaxy_opacity": 1.0,
}


def default_profile(snap_count: int) -> dict[str, Any]:
    """Return a default BoxProfile for a freshly-loaded model."""
    p: dict[str, Any] = {}
    p["snap_num"] = snap_count - 1
    p["snap_max"] = snap_count - 1
    p.update(_LAYER_DEFAULTS)
    p.update(_FILTER_DEFAULTS)
    return p


def save_profile(state) -> dict[str, Any]:
    """Snapshot the per-box keys from *state* into a new profile dict."""
    return {k: deepcopy(getattr(state, k, None)) for k in BOX_PROFILE_KEYS}


def load_profile(state, profile: dict[str, Any]) -> None:
    """Write every key in *profile* back into *state*.

    Callers must call ``state.dirty(*BOX_PROFILE_KEYS); state.flush()``
    afterwards to push changes to the browser and fire change handlers.
    """
    for k, v in profile.items():
        setattr(state, k, deepcopy(v))
