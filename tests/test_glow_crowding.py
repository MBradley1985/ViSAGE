"""Crowded galaxies dim their glow instead of clipping to white
(visage.utils.sizing.glow_crowding and its use in the galaxy layer)."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from visage.io.galaxy_reader import GalaxySnapshot
from visage.utils.sizing import glow_crowding


def test_isolated_galaxies_carry_only_their_own_glow():
    pos = np.array([[0.0, 0, 0], [50.0, 0, 0], [0, 50.0, 0]])
    np.testing.assert_allclose(glow_crowding(pos, np.full(3, 0.1)), 1.0)


def test_coincident_galaxies_stack():
    pos = np.zeros((5, 3))
    np.testing.assert_allclose(glow_crowding(pos, np.full(5, 0.1)), 5.0)


def test_neighbour_share_is_the_average_over_view_directions():
    """A neighbour's share at distance d matches a brute-force average of
    its projected gaussian over random viewing directions."""
    sigma, d = 0.1, 0.25
    n = glow_crowding(np.array([[0.0, 0, 0], [d, 0, 0]]), np.full(2, sigma))
    rng = np.random.default_rng(0)
    u = rng.uniform(-1.0, 1.0, 200_000)  # cos(angle to the line of sight)
    expected = np.exp(-0.5 * (d / sigma) ** 2 * (1.0 - u**2)).mean()
    np.testing.assert_allclose(n - 1.0, expected, rtol=0.01)


def test_a_large_glow_reaches_small_neighbours():
    """A cluster's wide glow covers its satellites even though they are
    searched for in a band of much smaller splats."""
    pos = np.array([[0.0, 0, 0], [0.3, 0, 0], [40.0, 0, 0]])
    sigma = np.array([1.0, 0.01, 0.01])
    n = glow_crowding(pos, sigma)
    assert n[1] > 1.8  # sits well inside the cluster's glow
    assert n[0] == pytest.approx(1.0, abs=1e-3)  # a tiny satellite: ~nothing
    assert n[2] == pytest.approx(1.0)


def test_handles_tiny_inputs():
    assert glow_crowding(np.zeros((0, 3)), np.zeros(0)).shape == (0,)
    np.testing.assert_allclose(glow_crowding(np.zeros((1, 3)), [0.1]), 1.0)


# ── galaxy layer ──────────────────────────────────────────────────────────


def _snapshot(positions: np.ndarray) -> GalaxySnapshot:
    n = len(positions)
    empty = GalaxySnapshot.empty(0)
    kwargs = {}
    for fld in dataclasses.fields(empty):
        v = getattr(empty, fld.name)
        if isinstance(v, np.ndarray):
            shape = (n, 3) if v.ndim == 2 else (n,)
            v = np.ones(shape, dtype=v.dtype)
        kwargs[fld.name] = v
    snap = GalaxySnapshot(**kwargs)
    snap.positions = np.asarray(positions, dtype=np.float32)
    snap.rvir = np.full(n, 0.1, dtype=np.float32)
    snap.cold_gas = np.full(n, 1e10, dtype=np.float32)
    snap.hot_gas = np.full(n, 1e11, dtype=np.float32)
    return snap


@pytest.fixture
def layer():
    pv = pytest.importorskip("pyvista")
    from visage.scene.galaxy_layer import GalaxyLayer

    pl = pv.Plotter(off_screen=True, window_size=[64, 48])
    yield GalaxyLayer(pl)
    pl.close()


def _cluster_and_loner():
    rng = np.random.default_rng(1)
    cluster = rng.normal(0.0, 0.05, (40, 3))
    return np.vstack([cluster, [[30.0, 0, 0]]])


def test_crowded_galaxies_are_dimmed_and_loners_are_not(layer):
    colours = []
    hue_rgba = layer._hue_rgba

    def spy(*args, **kwargs):
        colours.append(hue_rgba(*args, **kwargs))
        return colours[-1]

    layer._hue_rgba = spy
    layer.update(_snapshot(_cluster_and_loner()))
    dim = layer._dim
    assert dim[-1] == 1.0  # the isolated galaxy keeps its brightness
    assert dim[:-1].max() < 0.5  # every cluster member is dimmed
    # Every layer drawn for all 41 galaxies: members come out darker.
    full = [c for c in colours if len(c) == len(dim)]
    assert full
    for rgba in full:
        bright = rgba[:, :3].max(axis=1).astype(int)
        assert bright[:-1].max() < 0.6 * bright[-1]


def test_crowding_follows_the_emissive_switch(layer):
    layer.update(_snapshot(_cluster_and_loner()))
    layer.emissive = False
    assert layer._dim is None  # alpha-blended splats never clip


def test_loader_crowding_is_used_and_restyling_reuses_it(layer, monkeypatch):
    from visage.scene import galaxy_layer as gl

    snap = _snapshot(_cluster_and_loner())
    snap.crowding = np.full(snap.count, 6.0)  # as the loader fills it in
    calls = []
    monkeypatch.setattr(
        gl, "glow_crowding", lambda *a: calls.append(a) or np.ones(41)
    )
    layer.update(snap)
    expected = (6.0 / gl._CROWD_FREE) ** -gl._CROWD_POWER
    np.testing.assert_allclose(layer._dim, expected, rtol=1e-6)
    layer.glow_strength = 3.0
    layer.color_mode = "stellar_mass"
    assert calls == []


def test_a_thinning_filter_recomputes_for_what_is_left(layer):
    snap = _snapshot(_cluster_and_loner())
    layer.update(snap)
    crowded = layer._dim[0]
    keep = np.zeros(snap.count, dtype=bool)
    keep[[0, -1]] = True  # one cluster member and the loner
    layer.set_filter_mask(keep)
    assert layer._dim.shape == (2,)
    assert layer._dim[0] > crowded  # its neighbours are gone


def test_a_focus_region_reuses_the_snapshot_crowding(layer, monkeypatch):
    from visage.scene import galaxy_layer as gl

    snap = _snapshot(_cluster_and_loner())
    layer.update(snap)
    full = layer._dim.copy()
    monkeypatch.setattr(gl, "glow_crowding", None)  # must not be called
    keep = np.zeros(snap.count, dtype=bool)
    keep[:10] = True
    layer.set_focus_mask(keep)
    np.testing.assert_array_equal(layer._dim, full[:10])


def test_glowing_splats_get_a_narrow_core(layer):
    from visage.scene import galaxy_layer as gl

    layer.update(_snapshot(_cluster_and_loner()))
    codes = {a.mapper.GetSplatShaderCode() for a in layer._actors}
    assert codes == {gl._SPLAT_SHADER}
    layer.emissive = False  # alpha-blended splats keep VTK's gaussian
    assert {a.mapper.GetSplatShaderCode() for a in layer._actors} == {None}
