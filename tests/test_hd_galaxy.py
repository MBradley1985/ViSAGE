"""HD galaxy mode: recipe -> GPU ray-marcher -> scene layer -> Target-tab button."""

from __future__ import annotations

import numpy as np
import pytest

from visage.hd.model import (
    SageGalaxy,
    build_disk_maps,
    build_points,
    recipe_from_sage,
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


def test_disk_recipe_has_every_starlight_component():
    rc = recipe_from_sage(_disk())
    maps = build_disk_maps(rc, n=256)
    names = {p.name for p in build_points(rc, maps)}
    assert rc.kind == "disk"
    assert {"clusters", "hii", "field"} <= names
    assert rc.bar_len > 0  # instability bulge of 12% of M* makes a bar
    assert maps.dust.max() > 0


def test_elliptical_recipe():
    rc = recipe_from_sage(_elliptical())
    names = {p.name for p in build_points(rc, None)}
    assert rc.kind == "elliptical"
    assert "globulars" in names and "hii" not in names


@pytest.fixture
def plotter():
    pv = pytest.importorskip("pyvista")
    pl = pv.Plotter(off_screen=True, window_size=[64, 48])
    yield pl
    pl.close()


def _look(pl, gpu_or_layer, pos, focal=(0.0, 0.0, 0.0), up=(0.0, 0.0, 1.0)):
    pl.set_background("black")  # as the viewer's sky
    pl.camera_position = [tuple(pos), tuple(focal), tuple(up)]
    pl.renderer.ResetCameraClippingRange()
    pl.render()
    return pl.screenshot(return_img=True)


def test_gpu_galaxy_draws_the_galaxy(plotter):
    """The shader runs and puts a bright, coloured galaxy in the frame."""
    from visage.hd.gpu import GPUGalaxy

    plotter.window_size = [96, 96]
    rc = recipe_from_sage(_disk())
    maps = build_disk_maps(rc, n=256)
    g = GPUGalaxy(plotter)
    g.build(rc, maps, build_points(rc, maps), 1.0, np.eye(4), gal=_disk())
    cam = np.array([0.0, -12.0, 12.0])
    g.set_camera(cam)
    img = _look(plotter, g, cam)[..., :3].astype(float)
    centre = img[40:56, 40:56].mean()
    corner = img[:10, :10].mean()
    assert centre > 40 and centre > 4 * corner + 1
    g.clear()
    assert g.actor is None


def test_gas_switch_changes_the_picture(plotter):
    from visage.hd.gpu import GPUGalaxy

    plotter.window_size = [96, 96]
    gal = _disk()
    rc = recipe_from_sage(gal)
    maps = build_disk_maps(rc, n=256)
    g = GPUGalaxy(plotter)
    g.build(rc, maps, build_points(rc, maps), 1.0, np.eye(4), gal=gal)
    far = np.array([0.0, -1.5, 1.5]) * gal.rvir_kpc / rc.unit_kpc
    g.set_camera(far)
    g.set_view_half(gal.rvir_kpc)
    off = _look(plotter, g, far).astype(float)
    g.set_gas(True)
    on = _look(plotter, g, far).astype(float)
    # The hot halo, wind and jets add light around the galaxy.
    assert on[..., :3].sum() > off[..., :3].sum() * 1.05
    g.clear()


def test_layer_places_and_orients_the_model(plotter):
    from visage.hd.layer import HDGalaxyLayer

    lay = HDGalaxyLayer(plotter)
    spin = np.array([1.0, 0.0, 0.0])
    lay.show(_disk(), center=[10.0, 20.0, 30.0], spin=spin, hubble_h=0.73)
    assert lay.active
    m = lay._gpu.actor.GetUserMatrix()
    z_axis = np.array([m.GetElement(i, 2) for i in range(3)])
    assert np.allclose(z_axis / np.linalg.norm(z_axis), spin)
    assert np.allclose(
        [m.GetElement(i, 3) for i in range(3)], [10.0, 20.0, 30.0]
    )
    lay.set_gas(True)
    lay.set_gas(False)
    lay.clear()
    assert not lay.active
    assert lay._observer is None


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
    # Off again backs out to the standard 10 Mpc/h view of the galaxy.
    cam = scene.plotter.camera
    dist = np.linalg.norm(np.subtract(cam.position, cam.focal_point))
    assert dist == pytest.approx(10.0)


def test_target_go_defaults_to_10_mpc(hd_panel):
    """The 3 / 5 buttons are one-off zooms, and the Coords sphere no longer
    shares the halo standoff: Go keeps its 10 Mpc/h default."""
    server, scene = hd_panel
    state, ctrl = server.state, server.controller
    state.nav_gal_idx = 0
    ctrl.go_to_galaxy_1()  # 3 Mpc/h
    ctrl.go_to_galaxy_enter()
    cam = scene.plotter.camera
    dist = np.linalg.norm(np.subtract(cam.position, cam.focal_point))
    assert dist == pytest.approx(10.0)
    state.nav_distance = 0.5  # e.g. a drawn Coords sphere
    assert state.nav_halo_distance == 10.0


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


def test_threaded_raymarch_matches_single_thread():
    from visage.hd.model import build_points
    from visage.hd.raymarch import render

    rc = recipe_from_sage(_disk())
    maps = build_disk_maps(rc, n=256)
    pts = build_points(rc, maps)
    one = render(rc, maps, pts, inc=60, pa=20, npix=96, threads=1).total
    four = render(rc, maps, pts, inc=60, pa=20, npix=96, threads=4).total
    assert np.abs(four - one).sum() / np.abs(one).sum() < 1e-5


def test_point_grid_lists_each_star_in_its_own_cell():
    """Every exactly drawn star is listed in the cell that holds it (so the
    shader's walk finds it wherever the ray's closest approach falls)."""
    from visage.hd.gpu import point_grid, split_exact

    rc = recipe_from_sage(_disk())
    maps = build_disk_maps(rc, n=256)
    pts = build_points(rc, maps)
    exact, rest = split_exact(pts, per_cell=4)
    n_in = sum(
        len(p.lum) for p in pts if p.name in ("clusters", "hii", "field")
    )
    assert sum(len(p.lum) for p in exact + rest) == n_in
    g = point_grid(exact, 0.01)
    n = g["n"]
    idx = g["idx"].reshape(-1, 3)[: int(np.prod(n))]
    pos = g["pos"].reshape(-1, 4)
    p = exact[0].pos[0]
    c = np.floor((p - g["lo"]) / g["cell"]).astype(int)
    off, cnt = idx[c[0] + n[0] * (c[1] + n[1] * c[2])][:2].astype(int)
    assert np.any(np.all(np.isclose(pos[off : off + cnt, :3], p), axis=1))


def test_exposure_only_darkens_when_zooming_in():
    from visage.hd.layer import Exposure

    rc = recipe_from_sage(_disk())
    maps = build_disk_maps(rc, n=256)
    ex = Exposure(rc, maps, build_points(rc, maps), npix=96)
    assert ex.white(0, 0, 50.0) == ex.base
    assert ex.white(0, 0, 0.3) > ex.base


def test_noise_constants_match_the_noise():
    from visage.hd.gpu_gas import _STDS, noise_std

    assert noise_std("fbm2") == pytest.approx(_STDS["fbm2"], rel=1e-4)


def test_hd_builds_in_the_background_with_a_message(hd_panel):
    """In the app (a running event loop) the button returns at once with
    the "Building" message up, and the model appears when the worker is
    done."""
    import asyncio

    server, _ = hd_panel
    state, ctrl = server.state, server.controller
    state.nav_gal_idx = 0

    async def run():
        ctrl.toggle_hd()
        assert state.hd_building and not state.hd_active
        for _ in range(400):
            if not state.hd_building:
                break
            await asyncio.sleep(0.05)
        assert state.hd_active and not state.hd_building

    asyncio.run(run())


def test_hd_draws_the_whole_group(hd_panel):
    """A galaxy with company: HD draws every member of its FOF group, the
    halo's gas on the central only, and backs out to 10 Mpc/h when off."""
    server, scene = hd_panel
    state, ctrl = server.state, server.controller
    _, galaxies = scene.active_model.loader.get(scene.current_snap)
    galaxies.central_id[:] = np.arange(1, galaxies.count + 1)
    galaxies.central_id[[0, 3, 5]] = 99  # a group of three
    state.nav_gal_idx = 3
    ctrl.toggle_hd()
    state.flush()
    assert state.hd_active and state.isolate_active
    import gc

    from visage.hd.group import HDGroupLayer

    grp = [o for o in gc.get_objects() if isinstance(o, HDGroupLayer)][0]
    assert len(grp.members) == 3 and grp.active
    # Only the central carries the halo.
    assert grp.members[0]._gpu.gas is not None
    assert all(m._gpu.gas is None for m in grp.members[1:])
    # Go to a member while in HD: the camera flies to it, HD stays on.
    state.nav_gal_idx = 5
    state.flush()
    ctrl.go_to_galaxy_enter()
    assert state.hd_active and grp.active
    # (at its periodic image nearest the central, as the group is drawn)
    box = float(scene.active_model.box_size)
    central = grp.members[0]._center - scene.active_model.offset
    d = galaxies.positions[5] - central
    target = central + d - box * np.round(d / box) + scene.active_model.offset
    assert np.allclose(scene.plotter.camera.focal_point, target, atol=1e-4)
    state.hd_gas = True
    state.flush()
    ctrl.toggle_hd()
    state.flush()
    assert not state.hd_active and not grp.active
    cam = scene.plotter.camera
    dist = np.linalg.norm(np.subtract(cam.position, cam.focal_point))
    assert dist == pytest.approx(10.0)


def test_group_plan_tiers():
    from visage.hd.group import N_FULL, N_GROUP, N_HD, N_TOP, plan

    gals = [_disk()] * 60
    q = plan(gals)
    assert q[:N_TOP] == ["full"] * N_TOP
    assert set(q[N_TOP:N_GROUP]) == {"group"}
    assert set(q[N_GROUP:N_HD]) == {"lite"}
    assert q[N_HD:] == [None] * (60 - N_HD)
    assert plan(gals[:N_FULL]) == ["full"] * N_FULL


def test_group_members_build_in_the_process_pool():
    """Member builds run in spawned workers: the galaxy goes over and the
    prepared textures come back."""
    from visage.hd import group

    try:
        res = group.pool().submit(group.prepare_member, _disk(), "lite")
        prep = res.result(timeout=300)
    finally:
        if group._POOL["pool"] is not None:
            group._POOL["pool"].shutdown()
            group._POOL["pool"] = None
    assert prep["rc"].kind == "disk"
    assert prep["gpu"]["tex"]["mapTex"][0].shape == (384, 384, 3)


def test_hd_is_dropped_when_the_snapshot_changes(hd_panel):
    server, _ = hd_panel
    state, ctrl = server.state, server.controller
    state.snap_num = 63
    state.nav_gal_idx = 0
    state.flush()
    ctrl.toggle_hd()
    state.flush()
    assert state.hd_active
    state.snap_num = 62
    state.flush()
    assert not state.hd_active and not state.isolate_active


def test_group_across_the_box_edge_stays_together(hd_panel):
    """Members on the far side of the periodic box are drawn at their image
    next to the central; everyone else exactly on the catalogue position."""
    server, scene = hd_panel
    state, ctrl = server.state, server.controller
    _, galaxies = scene.active_model.loader.get(scene.current_snap)
    box = float(scene.active_model.box_size)
    galaxies.central_id[:] = np.arange(1, galaxies.count + 1)
    galaxies.central_id[[0, 1]] = 77
    galaxies.gal_type[0], galaxies.gal_type[1] = 0, 1
    galaxies.positions[0] = [0.5, 30.0, 30.0]
    galaxies.positions[1] = [box - 0.3, 30.2, 30.0]  # just across the edge
    state.nav_gal_idx = 0
    ctrl.toggle_hd()
    state.flush()
    import gc

    from visage.hd.group import HDGroupLayer

    grp = [o for o in gc.get_objects() if isinstance(o, HDGroupLayer)][0]
    off = scene.active_model.offset
    centers = sorted(m._center[0] - off[0] for m in grp.members)
    assert centers == pytest.approx([-0.3, 0.5], abs=1e-4)
    assert grp.radius_world < 2.0  # framed on the pair, not the whole box
    ctrl.toggle_hd()
    state.flush()
