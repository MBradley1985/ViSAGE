"""HD galaxy mode: recipe -> particles -> scene layer -> Structure-tab button."""

from __future__ import annotations

import numpy as np
import pytest

from visage.hd.model import SageGalaxy, build_disk_maps, recipe_from_sage
from visage.hd.particles import (
    MIN_COLOUR,
    attach_dust,
    attenuation,
    build_optical,
    calibrate,
)


def _disk(**kw) -> SageGalaxy:
    base = dict(
        galaxy_index=42,
        stellar_mass=5e10,
        bulge_mass=8e9,
        merger_bulge_mass=2e9,
        instability_bulge_mass=6e9,
        cold_gas=1e10,
        h2_gas=3e9,
        h1_gas=6e9,
        metals_cold_gas=2e8,
        bh_mass=5e7,
        sfr_disk=3.0,
        sfr_bulge=0.1,
        disk_radius_kpc=4.0,
        bulge_radius_kpc=1.0,
        regime=1,
        hot_gas=3e11,
        rvir_kpc=250.0,
        metals_stellar_mass=6e8,
        outflow_rate=3.0,
        heating_log=40.8,
        ics=2e9,
    )
    base.update(kw)
    return SageGalaxy(**base)


def _elliptical() -> SageGalaxy:
    return _disk(
        bulge_mass=2e11,
        stellar_mass=2.1e11,
        merger_bulge_mass=2e11,
        instability_bulge_mass=0.0,
        cold_gas=1e8,
        h2_gas=0.0,
        h1_gas=1e8,
        sfr_disk=0.001,
        sfr_bulge=0.0,
    )


@pytest.fixture(scope="module")
def disk_particles():
    gal = _disk()
    rc = recipe_from_sage(gal)
    maps = build_disk_maps(rc, n=256)
    sets = build_optical(rc, maps, budget=0.2)
    calibrate(sets, rc.extent * 1.3)
    attach_dust(sets, maps)
    return gal, rc, sets


def test_disk_recipe_builds_every_starlight_component(disk_particles):
    _, rc, sets = disk_particles
    names = {s.name for s in sets}
    assert rc.kind == "disk"
    assert {"old_disk", "young_disk", "bulge", "clusters", "hii"} <= names
    assert "bar" in names  # instability bulge of 12% of M* makes a bar


def test_elliptical_has_no_disk_components():
    rc = recipe_from_sage(_elliptical())
    sets = build_optical(rc, None, budget=0.1)
    names = {s.name for s in sets}
    assert rc.kind == "elliptical"
    assert {"core", "envelope"} <= names
    assert not names & {"old_disk", "young_disk", "hii"}


def test_calibrated_colours_survive_the_8bit_framebuffer(disk_particles):
    """Faint regions are thinned, not filled with splats too dim to draw."""
    _, _, sets = disk_particles
    for s in sets:
        assert np.all(np.isfinite(s.colour))
        if s.meta.get("diffuse"):
            assert s.colour.max(axis=1).min() >= MIN_COLOUR * 0.999


def test_dust_dims_the_midplane_more_edge_on(disk_particles):
    _, _, sets = disk_particles
    disk = next(s for s in sets if s.name == "old_disk")
    mid = np.abs(disk.zh) < 0.5
    face = attenuation(disk, np.array([0.0, 0.0, 1.0]))
    edge = attenuation(disk, np.array([0.0, 1.0, 0.0]))
    assert face.shape == (len(disk), 3)
    # Edge-on, the line of sight runs through the whole dusty midplane.
    assert edge[mid].mean() < face[mid].mean()
    # Dust reddens: blue is extinguished more than red.
    assert edge[mid, 2].mean() < edge[mid, 0].mean()


@pytest.fixture
def plotter():
    pv = pytest.importorskip("pyvista")
    pl = pv.Plotter(off_screen=True, window_size=[64, 48])
    yield pl
    pl.close()


def test_layer_show_gas_and_clear(plotter):
    from visage.hd.layer import HDGalaxyLayer

    lay = HDGalaxyLayer(plotter)
    lay.show(
        _disk(),
        center=[10.0, 20.0, 30.0],
        spin=np.array([0, 0, 1.0]),
        hubble_h=0.73,
    )
    assert lay.active
    optical = set(lay._clouds)
    assert not any(k.startswith("gas:") for k in optical)
    # Every particle sits near the galaxy's box position.
    pts = np.vstack(
        [
            c.points
            for _, c, _ in lay._clouds.values()
            if not _.name.startswith("icl")
        ]
    )
    assert np.abs(pts.mean(axis=0) - [10.0, 20.0, 30.0]).max() < 0.05

    lay.set_gas(True)
    gas = {k for k in lay._clouds if k.startswith("gas:")}
    assert {
        "gas:hot_gas",
        "gas:wind",
        "gas:jets",
    } <= gas  # hot regime, outflow, Heating
    lay.set_gas(False)
    assert not any(k.startswith("gas:") for k in lay._clouds)

    lay.clear()
    assert not lay.active
    assert lay._observer is None


def test_layer_aligns_the_disk_with_the_spin_vector(plotter):
    from visage.hd.layer import HDGalaxyLayer

    lay = HDGalaxyLayer(plotter)
    spin = np.array([1.0, 0.0, 0.0])
    lay.show(_disk(), center=[0.0, 0.0, 0.0], spin=spin, hubble_h=0.73)
    _, cloud, _ = lay._clouds["old_disk"]
    p = np.asarray(cloud.points)
    # A thin disk perpendicular to x: small spread along x, wide in y and z.
    assert p[:, 0].std() < 0.3 * p[:, 1].std()
    assert p[:, 0].std() < 0.3 * p[:, 2].std()
    lay.clear()


def test_adapter_converts_snapshot_units():
    from visage.hd.adapter import sage_galaxy_from_snapshot, spin_vector
    from visage.io.galaxy_reader import GalaxySnapshot

    snap = GalaxySnapshot.empty(63)
    n = 2
    for name, value in vars(snap).items():
        if isinstance(value, np.ndarray) and value.ndim == 1:
            setattr(snap, name, np.zeros(n, dtype=value.dtype))
    snap.stellar_mass = np.array([1e10, 5e10], np.float32)
    snap.disk_radius = np.array([0.0, 0.00292], np.float32)  # Mpc/h
    snap.rvir = np.array([0.1, 0.146], np.float32)
    snap.extra = {
        "Spinx": np.array([0.0, 0.0]),
        "Spiny": np.array([0.0, 3.0]),
        "Spinz": np.array([0.0, 4.0]),
        "TimeOfLastMajorMerger": np.array([-1.0, 1500.0]),
        "QuasarModeBHaccretionMass": np.array([0.0, 1e-4]),  # 1e10 Msun/h
    }
    gal = sage_galaxy_from_snapshot(snap, 1, hubble_h=0.73)
    assert gal.stellar_mass == pytest.approx(5e10)
    assert gal.disk_radius_kpc == pytest.approx(4.0, rel=1e-3)
    assert gal.rvir_kpc == pytest.approx(200.0, rel=1e-3)
    assert gal.t_major_myr == pytest.approx(1500.0)
    assert gal.qso_accretion == pytest.approx(1e6 / 0.73, rel=1e-3)
    np.testing.assert_allclose(spin_vector(snap, 1), [0.0, 0.6, 0.8])
    assert spin_vector(snap, 0) is None


@pytest.fixture
def hd_panel(mini_par_path, tmp_path):
    from trame.app import get_server
    from trame.ui.vuetify3 import SinglePageLayout

    from visage.scene.scene import Scene
    from visage.ui.navigation_panel import build_navigation_panel

    scene = Scene(str(mini_par_path), off_screen=True)
    server = get_server(f"test_hd_panel_{tmp_path.name}", client_type="vue3")
    server.controller.view_update = lambda *a, **k: None
    with SinglePageLayout(server) as layout:
        with layout.content:
            build_navigation_panel(server, scene)
    server.state.ready()
    return server, scene


def test_hd_button_isolates_and_toggles_off(hd_panel):
    """The minimal catalogue has only the required fields: HD must still
    build (every optional feature simply switches off)."""
    server, scene = hd_panel
    state, ctrl = server.state, server.controller
    state.nav_gal_idx = 0
    ctrl.toggle_hd()
    assert state.hd_active
    assert state.isolate_active
    gl = scene.active_model.galaxy_layer
    assert gl._focus_mask is not None and not gl._focus_mask.any()

    ctrl.toggle_hd()
    state.flush()
    assert not state.hd_active
    assert not state.isolate_active


def test_dropping_isolate_removes_the_hd_model(hd_panel):
    server, _ = hd_panel
    state, ctrl = server.state, server.controller
    state.nav_gal_idx = 0
    ctrl.toggle_hd()
    state.flush()
    assert state.hd_active
    state.isolate_active = False  # e.g. Reset Camera / Go To / Focus
    state.flush()
    assert not state.hd_active


def test_refined_view_swaps_in_and_out_with_the_camera(plotter):
    """Progressive refinement: a ray-marched view replaces the particles
    while the camera rests, and the next camera move brings them back."""
    from visage.hd.layer import HDGalaxyLayer

    lay = HDGalaxyLayer(plotter)
    lay.show(
        _disk(),
        center=[0.0, 0.0, 0.0],
        spin=np.array([0, 0, 1.0]),
        hubble_h=0.73,
    )
    r = lay.radius_world
    plotter.camera_position = [(0, -2 * r, 2 * r), (0, 0, 0), (0, 0, 1)]
    cam = lay.camera_state()
    assert lay.needs_refine(cam)

    view = lay.refine_view(cam, max_npix=160, threads=2)
    img = view["image"]
    assert img.ndim == 3 and img.shape[2] == 3 and np.isfinite(img).all()
    assert img.max() > 0.2  # the galaxy is there, tone-mapped into [0, 1]

    lay.show_impostor(view)
    assert lay.impostor_matches(cam) and not lay.needs_refine(cam)
    assert all(not a.GetVisibility() for a, _, _ in lay._clouds.values())

    plotter.camera_position = [(0, -2.5 * r, 1.5 * r), (0, 0, 0), (0, 0, 1)]
    lay._on_camera()
    assert lay._impostor is None
    assert all(a.GetVisibility() for a, _, _ in lay._clouds.values())
    lay.clear()


def test_threaded_raymarch_matches_single_thread():
    from visage.hd.model import build_points
    from visage.hd.raymarch import render

    rc = recipe_from_sage(_disk())
    maps = build_disk_maps(rc, n=256)
    pts = build_points(rc, maps)
    one = render(rc, maps, pts, inc=60, pa=20, npix=96, threads=1).total
    four = render(rc, maps, pts, inc=60, pa=20, npix=96, threads=4).total
    assert np.abs(four - one).sum() / np.abs(one).sum() < 1e-5
