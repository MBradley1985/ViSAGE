"""AGN and intracluster light (visage/sed/components.py)."""

from __future__ import annotations

import numpy as np
import pytest

from visage.sed import components as cp
from visage.sed import mock_image as mi


def test_continuum_matches_the_b_band_correction():
    wave = np.array([4400.0])
    l_bol = np.array([1e45])
    l_nu = cp.continuum(wave, l_bol, np.array([20.0]))[0, 0]
    want = 1e45 * cp.b_band_share(1e45)
    assert l_nu * cp.C_ANG / 4400.0 == pytest.approx(want, rel=0.01)


def test_absorbed_quasars_lose_the_optical_not_the_mid_infrared():
    wave = np.array([3000.0, 1.0e5])
    a = cp.continuum(wave, np.array([1e45]), np.array([20.0]))[0]
    b = cp.continuum(wave, np.array([1e45]), np.array([23.5]))[0]
    assert b[0] / a[0] < 1e-6 and b[1] / a[1] > 0.5


def test_fainter_quasars_are_absorbed_more_often():
    psi = cp.absorbed_share(np.array([1e43, 1e45]), 0.1)
    assert psi[0] > psi[1] and 0.2 <= psi[1] and psi[0] <= 0.84


def test_columns_follow_the_absorbed_share():
    u = np.linspace(0, 1, 100001)[:-1]
    nh = cp.column_density(np.full(u.shape, 1e44), 0.1, u)
    psi = cp.absorbed_share(1e44, 0.1)
    total = 1 + psi / 2
    assert np.mean(nh >= 22) == pytest.approx(
        (psi + psi / 2) / total, abs=1e-3
    )


def test_nfw_integrates_to_one_inside_the_virial_radius():
    x = np.linspace(1e-4, 1, 20000)
    s = mi.nfw_projected(x, 6.0)
    assert np.trapezoid(2 * np.pi * x * s, x) == pytest.approx(1, abs=0.01)
    assert mi.nfw_projected(np.array([1.2]), 6.0)[0] == 0


def test_missing_concentration_uses_the_mass_relation():
    c = mi._concentration(np.array([0.0, 7.0]), np.array([2e12, 2e12]))
    assert c[0] == pytest.approx(5.71) and c[1] == 7
