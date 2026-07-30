"""End-to-end tests for the Photometry tab (Lightcone Mode), built via a real
trame Server + Scene so the actual @state.change wiring is exercised. Covers
that photometry is its OWN layer (independent of the galaxies, off by
default), that the filter/M-L stack composites, and that band colours are
representative — all "looks right on read, wrong at runtime" wiring that only
shows up when the reactive cascade runs against a real scene.
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
    """A real (scene, state) pair with the nav panel built against a
    lightcone that has SED data, ready for reactive state changes. Returns
    a small holder so tests can assert on both the trame state and the
    galaxy/photometry layers it drives."""
    from trame.app import get_server
    from trame.ui.vuetify3 import SinglePageLayout

    from visage.scene.scene import Scene
    from visage.ui.navigation_panel import build_navigation_panel

    path = tmp_path / "sed_lightcone.h5"
    _make_sed_lightcone(path)

    # Scene builds its own (off-screen) plotter; primary_par_path is unused
    # in lightcone mode.
    scene = Scene(
        "unused-in-lightcone", lightcone_path=str(path), off_screen=True
    )

    server = get_server(f"test_sed_panel_{tmp_path.name}", client_type="vue3")
    server.controller.view_update = lambda *a, **k: None
    with SinglePageLayout(server) as layout:
        with layout.content:
            build_navigation_panel(server, scene)

    state = server.state
    state.ready()

    class _Holder:
        def __init__(self, state, scene):
            self.state = state
            self.scene = scene

        @property
        def gal(self):
            return self.scene.active_model.galaxy_layer

        @property
        def sed(self):
            return self.scene.active_model.sed_layer

    return _Holder(state, scene)


def test_sed_dropdown_lists_filters_and_mass_to_light(sed_panel):
    modes = [m["value"] for m in sed_panel.state.sed_color_modes]
    # Raw filter bands (rest + observed) are stackable...
    assert "mag_rest_sdss_g" in modes
    assert "mag_obs_sdss_r" in modes
    # ...and mass-to-light per rest-frame band with a solar magnitude.
    assert "ml:mag_rest_sdss_g" in modes


def test_photometry_is_its_own_hidden_layer(sed_panel):
    # Photometry is a SEPARATE layer, hidden by default — the galaxy layer is
    # untouched (normal structure colouring) on load.
    st = sed_panel.state
    assert st.photometry_visible is False
    assert sed_panel.sed is not sed_panel.gal
    assert sed_panel.sed.visible is False
    assert sed_panel.gal.color_mode == "structure"
    assert st.sed_galaxy_bands  # a band is pre-ticked, ready for when shown


def test_enabling_photometry_shows_the_stack_layer(sed_panel):
    st = sed_panel.state
    with st:
        st.sed_galaxy_bands = ["mag_rest_sdss_g"]
        st.photometry_visible = True
    assert sed_panel.sed.visible is True
    assert sed_panel.sed.color_mode == "sedstack"
    assert sed_panel.sed._sed_bands == ["mag_rest_sdss_g"]
    # The galaxy layer is completely untouched.
    assert sed_panel.gal.color_mode == "structure"
    # Legend reflects the ticked band with its representative colour.
    assert len(st.sed_legend) == 1
    assert st.sed_legend[0]["color"].startswith("rgb(")


def test_photometry_independent_of_galaxies(sed_panel):
    # The key requirement: photometry works with the galaxies off entirely.
    st = sed_panel.state
    with st:
        st.sed_galaxy_bands = ["mag_rest_sdss_g"]
        st.photometry_visible = True
        st.galaxies_visible = False
    assert sed_panel.gal.visible is False  # galaxies off
    assert sed_panel.sed.visible is True  # photometry still on
    # ...and opacity is its own control.
    with st:
        st.photometry_opacity = 0.5
    assert abs(sed_panel.sed.opacity - 0.5) < 1e-6


def test_stack_renders_nested_shells_for_definition(sed_panel):
    st = sed_panel.state
    with st:
        st.sed_galaxy_bands = ["mag_rest_sdss_g", "mag_rest_sdss_r"]
        st.photometry_visible = True
    # Several nested gaussian shells give the splats a defined profile.
    assert len(sed_panel.sed._actors) >= 3


def test_stacking_multiple_filters_composite(sed_panel):
    st = sed_panel.state
    stack = ["mag_rest_sdss_g", "mag_rest_sdss_r", "mag_rest_sdss_i"]
    with st:
        st.sed_galaxy_bands = stack
        st.photometry_visible = True
    assert sed_panel.sed._sed_bands == stack
    assert len(st.sed_legend) == 3

    import numpy as np

    snap = sed_panel.scene.active_model.loader.get(0)[1]
    rgb = sed_panel.sed._compute_sed_stack_rgb(snap)
    assert rgb.shape == (snap.count, 3)
    assert rgb.max() > 0.2
    spread = np.abs(rgb[:, 0] - rgb[:, 2]).mean()
    assert spread > 0.01  # false-colour, not greyscale


def test_mass_to_light_is_stackable(sed_panel):
    st = sed_panel.state
    with st:
        st.sed_galaxy_bands = ["ml:mag_rest_sdss_g", "ml:mag_rest_sdss_r"]
        st.photometry_visible = True
    assert sed_panel.sed.color_mode == "sedstack"
    import numpy as np

    snap = sed_panel.scene.active_model.loader.get(0)[1]
    rgb = sed_panel.sed._compute_sed_stack_rgb(snap)
    assert rgb.shape == (snap.count, 3)
    assert np.isfinite(rgb).all()


def test_band_colours_are_representative():
    # Each filter's representative colour should read as its own light:
    # g green-dominant, r/i red-dominant, u/FUV blue-dominant.
    from visage.sed.filters import band_colour

    g = band_colour("sdss_g")
    assert g[1] > g[0] and g[1] > g[2]  # green channel dominates
    for red_band in ("sdss_r", "sdss_i", "2mass_j"):
        c = band_colour(red_band)
        assert c[0] > c[1] and c[0] > c[2]  # red channel dominates
    for blue_band in ("sdss_u", "galex_fuv"):
        c = band_colour(blue_band)
        assert c[2] > c[1]  # blue channel over green
