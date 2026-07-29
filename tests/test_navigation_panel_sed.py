"""End-to-end test for the Structure panel's Synthetic Photometry (SED)
section, built via a real trame Server + Scene (not a hand-rolled fake) so
the actual @state.change wiring is exercised — the bugs this guards against
(colour-index/mass-to-light modes silently missing from the dropdown, the
SED picker showing a foreign mode like "structure" as raw text, wrong
default colormaps) were all "looks right on read, wrong at runtime" wiring
mistakes that only show up when the real reactive cascade runs.
"""

from __future__ import annotations

import h5py
import numpy as np
import pytest

pytest.importorskip("pyvista")


def _make_sed_lightcone(path, n=30, seed=2):
    rng = np.random.default_rng(seed)
    with h5py.File(path, "w") as f:
        f["Posx"] = rng.uniform(0, 100, n).astype(np.float32)
        f["Posy"] = rng.uniform(0, 100, n).astype(np.float32)
        f["Posz"] = rng.uniform(0, 100, n).astype(np.float32)
        f["StellarMass"] = rng.uniform(0.1, 10, n).astype(np.float32)
        f["Mvir"] = rng.uniform(10, 200, n).astype(np.float32)
        f["Type"] = np.zeros(n, dtype=np.int32)
        f["SnapNum"] = np.full(n, 5, dtype=np.int32)
        f["mag_rest_sdss_u"] = rng.uniform(-20, -14, n).astype(np.float32)
        f["mag_rest_sdss_g"] = rng.uniform(-22, -16, n).astype(np.float32)
        f["mag_rest_sdss_r"] = rng.uniform(-23, -17, n).astype(np.float32)
        f["mag_obs_sdss_r"] = rng.uniform(15, 25, n).astype(np.float32)
        sim = f.create_group("SageOutputHeader").create_group("Simulation")
        sim.attrs["hubble_h"] = 0.73


@pytest.fixture
def sed_panel(tmp_path):
    """A real (server, state) pair with the nav panel built against a
    lightcone that has SED data, ready for reactive state changes."""
    import pyvista as pv
    from trame.app import get_server
    from trame.ui.vuetify3 import SinglePageLayout

    from visage.scene.scene import Scene
    from visage.ui.navigation_panel import build_navigation_panel

    path = tmp_path / "sed_lightcone.h5"
    _make_sed_lightcone(path)

    plotter = pv.Plotter(off_screen=True)
    scene = Scene(plotter, lightcone_path=str(path))

    server = get_server(f"test_sed_panel_{tmp_path.name}", client_type="vue3")
    server.controller.view_update = lambda *a, **k: None
    with SinglePageLayout(server) as layout:
        with layout.content:
            build_navigation_panel(server, scene)

    state = server.state
    state.ready()
    return state


def test_sed_modes_include_colour_index_and_mass_to_light(sed_panel):
    modes = [m["value"] for m in sed_panel.sed_color_modes]
    assert any(m.startswith("sed:") for m in modes)
    assert any(m.startswith("sedcolor:") for m in modes)
    assert any(m.startswith("sedml:") for m in modes)


def test_sed_picker_starts_blank_not_showing_structure(sed_panel):
    assert sed_panel.galaxy_color_mode == "structure"
    assert sed_panel.sed_galaxy_color_mode == ""


def test_selecting_raw_band_sets_frame_appropriate_colormap(sed_panel):
    with sed_panel:
        sed_panel.sed_galaxy_color_mode = "sed:mag_rest_sdss_g"
    assert sed_panel.galaxy_color_mode == "sed:mag_rest_sdss_g"
    assert sed_panel.galaxy_colormap == "viridis"
    assert sed_panel.gal_cbar_min != "—"

    with sed_panel:
        sed_panel.sed_galaxy_color_mode = "sed:mag_obs_sdss_r"
    assert sed_panel.galaxy_colormap == "magma"


def test_selecting_colour_index_sets_diverging_colormap(sed_panel):
    modes = [m["value"] for m in sed_panel.sed_color_modes]
    color_mode = next(m for m in modes if m.startswith("sedcolor:"))
    with sed_panel:
        sed_panel.sed_galaxy_color_mode = color_mode
    assert sed_panel.galaxy_color_mode == color_mode
    assert sed_panel.galaxy_colormap == "coolwarm"
    assert sed_panel.gal_cbar_min != "—" and sed_panel.gal_cbar_max != "—"


def test_selecting_mass_to_light_sets_mass_colormap(sed_panel):
    modes = [m["value"] for m in sed_panel.sed_color_modes]
    ml_mode = next(m for m in modes if m.startswith("sedml:"))
    with sed_panel:
        sed_panel.sed_galaxy_color_mode = ml_mode
    assert sed_panel.galaxy_color_mode == ml_mode
    assert sed_panel.galaxy_colormap == "cividis"
    assert sed_panel.gal_cbar_min != "—" and sed_panel.gal_cbar_max != "—"


def test_switching_main_dropdown_clears_sed_picker(sed_panel):
    with sed_panel:
        sed_panel.sed_galaxy_color_mode = "sed:mag_rest_sdss_g"
    assert sed_panel.sed_galaxy_color_mode != ""

    with sed_panel:
        sed_panel.galaxy_color_mode = "stellar_mass"
    assert sed_panel.sed_galaxy_color_mode == ""


# ── Derived (colour-index / mass-to-light) modes scale to a partial band
# selection — a user unchecking most of the 14 run-script checkboxes must
# still get whatever colour indices/M-L ratios remain derivable, not an
# all-or-nothing dropdown. Pure unit tests on the list-building helper, no
# trame/pyvista needed.


def test_derived_modes_from_two_unrelated_bands():
    from visage.ui.navigation_panel import _sed_extra_modes

    # Only 2 (non-SDSS) bands computed: a colour index between them is still
    # derivable; mass-to-light isn't (no known solar magnitude for GALEX).
    modes = _sed_extra_modes(["mag_rest_galex_fuv", "mag_rest_galex_nuv"])
    values = [m["value"] for m in modes]
    assert any(v.startswith("sedcolor:") for v in values)
    assert not any(v.startswith("sedml:") for v in values)


def test_mass_to_light_needs_only_its_own_band():
    from visage.ui.navigation_panel import _sed_extra_modes

    # A single SDSS rest-frame band is enough for M*/L on its own — it must
    # not require every other band to also be selected.
    modes = _sed_extra_modes(["mag_rest_sdss_g"])
    assert modes == [
        {"title": "M*/L (g, rest)", "value": "sedml:mag_rest_sdss_g"}
    ]


def test_single_band_with_no_solar_magnitude_yields_no_derived_modes():
    from visage.ui.navigation_panel import _sed_extra_modes

    # No crash, just nothing to derive: 1 band -> no colour index (needs 2),
    # and galex has no sourced solar magnitude -> no M*/L either.
    assert _sed_extra_modes(["mag_rest_galex_fuv"]) == []
