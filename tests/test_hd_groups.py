"""Groups, clusters and drawn regions in HD; the group card."""

from __future__ import annotations

import gc

import numpy as np
import pytest

pytest.importorskip("pyvista")

import test_hd_galaxy  # noqa: E402
from test_hd_galaxy import _disk  # noqa: E402

# (The HD panel fixture, shared.)
hd_panel_fixture = test_hd_galaxy.hd_panel


def _snap(n=6, h=0.7):
    from visage.io.galaxy_reader import GalaxySnapshot

    g = GalaxySnapshot.empty(0)
    z = np.zeros(n, np.float32)
    for k, v in vars(g).items():
        if isinstance(v, np.ndarray) and v.ndim == 1:
            setattr(g, k, np.zeros(n, v.dtype))
    g.positions = np.zeros((n, 3), np.float32)
    g.sage_indices = np.arange(n)
    g.stellar_mass = np.array([1e11, 5e10, 2e9, 5e8, 3e8, 2e8], np.float32)
    g.gal_type = np.array([0, 1, 1, 1, 1, 1], np.int32)
    g.mvir = z + 1e4 * h  # 1e14 Msun
    g.rvir = z + 1.0
    g.ssfr = np.array([1e-12, 1e-12, 1e-10, 1e-10, 1e-12, 1e-10], np.float32)
    g.extra = {
        "Velx": np.array([0, 300, -300, 100, -100, 0], np.float32),
        "Vely": z,
        "Velz": z,
    }
    return g


def test_groups_are_named_by_their_halo_and_bright_members():
    from visage.utils.group_info import _classify

    assert _classify(2e14, 1) == "Cluster"
    assert _classify(5e13, 1) == "Group"
    # Galaxy-sized haloes: by members of at least 1e9 Msun, whatever the
    # resolution cut lets in below that.
    assert _classify(5e12, 4) == "Small group"
    assert _classify(5e12, 2) == "Pair"
    assert _classify(5e12, 1) == "Isolated"


def test_group_summary_describes_the_group():
    from visage.utils.group_info import group_summary

    g = _snap()
    rows = dict(group_summary(g, np.arange(6), 0.7))
    assert rows["Type"] == "Cluster"
    assert rows["Members"].startswith("6 (3 with")
    assert rows["Quenched"].startswith("50%")
    assert "σ_v (1D)" in rows
    assert rows["M* gap (1st/2nd)"] == "0.30 dex"


def test_glow_members_become_extras_when_visited(
    hd_panel_fixture, monkeypatch
):
    """Past N_HD a member is a glow; Go on it builds it on its own and
    adds it to the scene, and the card tags each member."""
    import visage.hd.group as grp_mod

    for k, v in (("N_FULL", 0), ("N_TOP", 1), ("N_GROUP", 1), ("N_HD", 1)):
        monkeypatch.setattr(grp_mod, k, v)
    server, scene = hd_panel_fixture
    state, ctrl = server.state, server.controller
    _, galaxies = scene.active_model.loader.get(scene.current_snap)
    galaxies.central_id[:] = np.arange(1, galaxies.count + 1)
    galaxies.central_id[[0, 3, 5]] = 99
    state.nav_gal_idx = 0
    state.sel_kind = "halo"
    ctrl.toggle_hd()
    state.flush()
    layer = [
        o for o in gc.get_objects() if isinstance(o, grp_mod.HDGroupLayer)
    ]
    grp = next(g for g in layer if g.active)
    # The selected galaxy and the most massive are models.
    n0 = len(grp.members)
    tags = dict(state.hd_member_tags)
    assert "glow" in tags.values()
    glow = next(k for k, t in tags.items() if t == "glow")
    state.nav_gal_idx = int(glow)
    state.flush()
    ctrl.go_to_galaxy_enter()
    assert len(grp.members) == n0 + 1
    assert state.hd_member_tags[int(glow)] == "HD extra"
    assert state.hd_active
    ctrl.toggle_hd()


def test_galaxies_are_named_by_their_galaxy_index():
    """Only SAGE's GalaxyIndex names a galaxy; a typed or Console number
    is a GalaxyIndex too (rows are internal)."""
    from visage.utils.group_info import galaxy_label, row_for_galaxy_index

    g = _snap()
    g.galaxy_id = np.array([501, 502, 503, 504, 505, 506], np.int64)
    assert galaxy_label(g, 2) == "503"
    assert row_for_galaxy_index(g, 505) == 4
    assert row_for_galaxy_index(g, 7) is None
    # Without GalaxyIndex the row is all there is, and says so.
    g.galaxy_id = np.zeros(6, np.int64)
    assert galaxy_label(g, 2) == "row 2"
    assert row_for_galaxy_index(g, 3) == 3
