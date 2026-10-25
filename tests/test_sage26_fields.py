"""ViSAGE's use of SAGE26's black-hole and star-formation-history fields."""

from __future__ import annotations

import numpy as np
import pytest

from visage.sed import agn


def test_radio_accretion_gives_the_power_heating_records():
    """RadioModeBHaccretionMass and Heating describe the same power
    (Heating = 0.1 c^2 x accretion / dT): either gives one luminosity."""
    bh = np.array([1e8])
    mdot = 1e-3  # Msun/yr
    p = agn.ETA * mdot * agn.MSUN_G / agn.YR_S * agn.C_CM_S**2
    l_heat, _ = agn.luminosity(bh, [0.0], [np.log10(p)])
    l_rad, _ = agn.luminosity(bh, [0.0], [0.0], mdot_radio=[mdot])
    assert l_rad == pytest.approx(l_heat, rel=1e-9)


def test_bulge_history_is_topped_up_only_when_short():
    from visage.hd.adapter import _bulge_history

    disk = np.array([1.0, 2.0, 3.0])
    old = np.stack([disk, np.zeros(3)])  # older SAGE26: bulge history empty
    fixed = _bulge_history(old, bulge_raw=3.0)
    assert fixed[1].sum() == pytest.approx(3.0)
    assert fixed.sum() == pytest.approx(old.sum())  # nothing lost
    # The disk's age mix: the moved stars have its shape.
    np.testing.assert_allclose(fixed[1] / fixed[1].sum(), disk / disk.sum())
    # A fixed SAGE26 history already sums to BulgeMass: left alone.
    new = np.stack([disk, np.array([0.5, 1.0, 1.5])])
    np.testing.assert_array_equal(_bulge_history(new, bulge_raw=3.0), new)


def test_a_newborn_black_hole_draws_no_quasar():
    """SAGE26's black holes start at zero: a dwarf's first event 'accretes'
    a tiny black hole whole; nothing an observer would see."""
    from test_hd_galaxy import _disk

    from visage.hd.model import recipe_from_sage
    import dataclasses

    g = _disk()
    assert (
        recipe_from_sage(dataclasses.replace(g, qso_accretion=50.0)).agn == 0
    )
    assert recipe_from_sage(dataclasses.replace(g, qso_accretion=1e7)).agn > 0


def test_card_notes_a_black_hole_born_this_step():
    from visage.io.galaxy_reader import GalaxySnapshot
    from visage.utils.galaxy_info import cone_details

    g = GalaxySnapshot.empty(0)
    n = 2
    for k, v in vars(g).items():
        if isinstance(v, np.ndarray) and v.ndim == 1:
            setattr(g, k, np.zeros(n, v.dtype))
    g.positions = np.zeros((n, 3), np.float32)
    g.sage_indices = np.arange(n)
    g.redshifts = np.zeros(n)
    g.snap_nums = np.zeros(n, int)
    g.bh_mass = np.array([0.01, 1e8], np.float32)
    h = 0.7
    g.extra = {
        "EddingtonRatio": np.array([0.2, 0.01], np.float32),
        "QuasarModeBHaccretionMass": np.array([0.01 * h / 1e10, 1e-6]),
    }
    g.photometry = {"NebularEmission": "Feltre+16", "Dust": "none"}
    assert "born this step" in cone_details(g, 0, h)["Eddington ratio"]
    assert "born" not in cone_details(g, 1, h)["Eddington ratio"]
