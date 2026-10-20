"""The selection: card, ring, host halo, following a galaxy in time."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def panel(mini_par_path, tmp_path):
    from trame.app import get_server
    from trame.ui.vuetify3 import SinglePageLayout

    from visage.scene.scene import Scene
    from visage.ui.navigation_panel import build_navigation_panel
    from visage.ui.selection import build_selection, selection_card

    scene = Scene(str(mini_par_path), off_screen=True)
    server = get_server(f"test_sel_{tmp_path.name}", client_type="vue3")
    server.controller.view_update = lambda *a, **k: None
    with SinglePageLayout(server) as layout:
        with layout.content:
            selection_card(server)
            build_navigation_panel(server, scene)
            build_selection(server, scene)
    server.state.ready()
    return server, scene


def _group(scene, members, central):
    """Make `members` one FOF group with `central` on halo 0."""
    halos, galaxies = scene.active_model.loader.get(scene.current_snap)
    galaxies.central_id[:] = np.arange(1, galaxies.count + 1)
    galaxies.central_id[members] = 99
    galaxies.gal_type[members] = 1
    galaxies.gal_type[central] = 0
    halos.positions[0] = galaxies.positions[central]
    return halos, galaxies


def test_selecting_a_galaxy_fills_the_card_and_marks_it(panel):
    server, scene = panel
    state = server.state
    _group(scene, [2, 4, 6], central=4)
    state.nav_gal_idx = 6
    state.flush()
    assert state.sel_show
    assert state.sel_title == "Galaxy 6"
    assert "satellite" in state.sel_sub
    # Group list: central first, the selected one flagged.
    assert state.sel_members[0]["idx"] == 4
    assert [m["idx"] for m in state.sel_members if m["current"]] == [6]
    # Host halo: the one the central sits on, not the nearest visible one.
    assert state.nav_halo_idx == 0
    marker = scene.camera.marker
    assert marker.active and len(marker.members) == 2


def test_typing_a_halo_selects_its_central(panel):
    server, scene = panel
    state = server.state
    _group(scene, [1, 3], central=3)
    state.nav_gal_idx = 1
    state.flush()
    state.nav_halo_idx = 5
    state.flush()  # a halo with no galaxy on it: selection stays
    assert state.sel_title == "Galaxy 1"
    halos, galaxies = scene.active_model.loader.get(scene.current_snap)
    halos.positions[7] = galaxies.positions[3]
    state.nav_halo_idx = 7
    state.flush()
    assert state.nav_gal_idx == 3


def test_the_selection_follows_the_galaxy_through_snapshots(panel):
    server, scene = panel
    state = server.state
    model = scene.active_model
    now = model.loader.get(63)[1]
    before = model.loader.get(62)[1]
    now.galaxy_id[:] = np.arange(1000, 1000 + now.count)
    before.galaxy_id[:] = np.arange(5000, 5000 + before.count)
    before.galaxy_id[11] = now.galaxy_id[4]  # galaxy 4 is row 11 before
    state.snap_num = 63
    state.nav_gal_idx = 4
    state.flush()
    state.snap_num = 62
    state.flush()
    assert state.nav_gal_idx == 11 and not state.sel_note
    before.galaxy_id[11] = -1  # gone: not formed yet / merged
    state.snap_num = 63
    state.flush()
    state.snap_num = 62
    state.flush()
    assert "Not in this snapshot" in state.sel_note


def test_hd_offers_its_galaxies_for_picking(panel):
    server, scene = panel
    state, ctrl = server.state, server.controller
    _group(scene, [0, 3, 5], central=0)
    state.nav_gal_idx = 0
    state.flush()
    ctrl.toggle_hd()
    state.flush()
    idx, pos = ctrl.hd_pick_candidates()
    assert {0, 3, 5} <= set(idx) and len(pos) == len(idx)
    # The ring stays on the selection in HD.
    assert scene.camera.marker.active
    ctrl.toggle_hd()
    state.flush()


def test_nothing_is_selected_at_startup(panel):
    server, scene = panel
    state = server.state
    assert state.nav_gal_idx is None and not state.sel_show
    assert not scene.camera.marker.active


def test_selecting_by_typed_index_and_info(panel):
    server, _ = panel
    state, ctrl = server.state, server.controller
    state.sel_q_gal = "7"
    ctrl.sel_query("galaxy")
    assert state.nav_gal_idx == 7 and state.sel_show
    ctrl.sel_clear_marker()  # rings off, selection kept
    assert state.sel_show and not server_scene_marker(panel).active
    ctrl.sel_close()
    assert not state.sel_show
    ctrl.show_galaxy_info()  # Console "galaxy info": the card, all open
    assert state.sel_show and state.sel_info_open and state.sel_info_items


def server_scene_marker(panel):
    return panel[1].camera.marker


def test_isolate_follows_the_galaxy_or_halo_context(panel):
    """A halo selected (Console `halo N`, Go to halo, the card's switch)
    isolates the halo with its whole group; a galaxy, just the galaxy."""
    server, scene = panel
    state, ctrl = server.state, server.controller
    _group(scene, [2, 4, 6], central=4)
    gl = scene.active_model.galaxy_layer
    # Selecting the halo: its central, in halo context.
    state.nav_halo_idx = 0
    state.flush()
    assert state.nav_gal_idx == 4 and state.sel_kind == "halo"
    assert state.sel_title == "Halo 0"
    ctrl.toggle_isolate()
    state.flush()
    assert sorted(np.flatnonzero(gl._focus_mask)) == [2, 4, 6]
    ctrl.toggle_isolate()
    # A galaxy picked: galaxy context, isolate keeps just it.
    state.nav_gal_idx = 6
    state.flush()
    assert state.sel_kind == "galaxy" and state.sel_title == "Galaxy 6"
    ctrl.toggle_isolate()
    state.flush()
    assert list(np.flatnonzero(gl._focus_mask)) == [6]
    ctrl.toggle_isolate()
    # The card's switch back to the halo.
    state.sel_kind = "halo"
    state.flush()
    assert state.sel_title == "Halo 0"
