"""HD's dust on discs in annuli (DarkSAGEMode, with or without DustySAGEMode),
box and lightcone: each annulus a screen of its own dust, weighted by its
share of the old stars, as the photometry finds it; and the fallbacks
without annuli."""

from __future__ import annotations

import types

import numpy as np

EDGES = np.geomspace(0.05, 40.0, 31)  # kpc
R = 0.5 * (EDGES[1:] + EDGES[:-1])


def _prof(dust=True, scale=3.0):
    p = {
        "edges": [EDGES],
        "r": [R],
        "stars": [500.0 * np.exp(-R / scale)],  # Msun / pc^2
        "gas": [20.0 * np.exp(-R / (1.5 * scale))],
    }
    if dust:
        p["dust"] = [0.2 * np.exp(-R / (1.5 * scale))]
    return p


def _gal(**kw):
    base = dict(
        cold_gas=1e10,
        metals_cold_gas=1.5e8,
        h2_gas=3e9,
        sfr_disk=2.0,
        sfr_bulge=0.0,
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_disc_screen_is_the_photometrys_star_weighted_screen():
    from visage.hd.adapter import disc_screen
    from visage.sed import dust as dm

    p = _prof()
    got = disc_screen(p, 1e10, 1.0, _gal())
    area = np.pi * np.diff(EDGES**2) * 1e6
    share = dm.annulus_shares(
        (p["stars"][0] * area)[None],
        np.array([1e10]),
        np.array([1.0]),
        EDGES[None],
    )[0]
    tau = dm.annulus_tau((p["dust"][0] * area)[None], EDGES[None], np.ones(1))
    want = -np.log(np.sum(share * np.exp(-tau[0][0])))
    assert np.isclose(got, want)
    assert got > 0


def test_without_dust_the_annuli_gas_carries_the_dust_to_gas_ratio():
    from visage.hd.adapter import disc_screen

    with_dust = disc_screen(_prof(dust=True), 1e10, 1.0, _gal())
    from_gas = disc_screen(_prof(dust=False), 1e10, 1.0, _gal())
    assert from_gas > 0 and np.isfinite(from_gas)
    # Metal-free gas holds no dust.
    assert (
        disc_screen(_prof(dust=False), 1e10, 1.0, _gal(metals_cold_gas=0.0))
        <= 0
    )
    assert with_dust != from_gas


def _disc_galaxy(tau_disc):
    from visage.hd.layer import _warm_galaxy

    p = _prof()
    radial = (
        tuple(R),
        tuple(p["stars"][0]),
        tuple(10.0 * np.exp(-R / 4.5)),
        tuple(10.0 * np.exp(-R / 3.0)),
        tuple(0.01 * np.exp(-R / 3.0)),
        tuple(p["dust"][0]),
        (),
    )
    return _warm_galaxy(
        stellar_mass=4e10,
        bulge_mass=4e9,
        merger_bulge_mass=4e9,
        instability_bulge_mass=0.0,
        disk_radius_kpc=3.0,
        bulge_radius_kpc=1.0,
        vmax=220.0,
        radial=radial,
        tau_disc=tau_disc,
    )


def _map_screen(rc, maps):
    n = maps.old.shape[0]
    ax = np.linspace(-maps.half, maps.half, n)
    x, y = np.meshgrid(ax, ax)
    r = np.hypot(x, y) + 1e-3
    w = (1 - rc.dust_wb) * maps.old / maps.old.sum()
    b = np.exp(-r / rc.dust_rb)
    w = w + rc.dust_wb * b / b.sum()
    lanes = maps.lanes if maps.lanes is not None else 0.0
    return float(-np.log(np.sum(w * np.exp(-(maps.dust + lanes)))))


def test_hd_dust_map_is_scaled_to_the_annuli_screen():
    from visage.hd.model import TAU_MAX, build_disk_maps, recipe_from_sage

    for target in (0.05, 0.4):
        rc = recipe_from_sage(_disc_galaxy(target))
        assert rc.tau_star == target
        maps = build_disk_maps(rc, n=256)
        assert np.isclose(_map_screen(rc, maps), target, rtol=1e-3)
    # Deeper than the map can hold under TAU_MAX: short of it, not piled up.
    rc = recipe_from_sage(_disc_galaxy(1.5))
    maps = build_disk_maps(rc, n=256)
    d = maps.dust[maps.dust > 0]
    assert np.percentile(d, 99) <= TAU_MAX * 1.001
    assert 1.0 < _map_screen(rc, maps) <= 1.5


def test_no_dust_draws_none_and_no_annuli_falls_back():
    from visage.hd.model import build_disk_maps, recipe_from_sage

    rc = recipe_from_sage(_disc_galaxy(0.0))
    assert build_disk_maps(rc, n=128).dust.max() == 0.0
    # Without annuli the screen is ignored: tau0 sets the map as before.
    import dataclasses

    g = dataclasses.replace(_disc_galaxy(0.7), radial=())
    rc = recipe_from_sage(g)
    assert rc.tau_star < 0


def test_cone_prefers_its_photometrys_dust_to_dustysage_mass():
    from visage.hd.adapter import _sed_tau

    class Cone:
        snap_nums = np.array([5])
        extra = {"TauV_ISM": np.array([0.42]), "ColdDust": np.array([1e-3])}
        disk_radius = np.array([0.004])

        def sed_dust(self):
            return ("charlot_fall", 0.0)

    assert _sed_tau(Cone(), 0, 0.7) == 0.42
    # No photometry dust column: DustySAGE's dust by the photometry recipe.
    cone = Cone()
    cone.extra = {"ColdDust": np.array([1e-3])}
    cone.sed_dust = lambda: ("none", 0.0)
    assert _sed_tau(cone, 0, 0.7) > 0
