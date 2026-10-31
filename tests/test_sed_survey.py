"""Survey apertures and selection (visage/sed/survey.py)."""

from __future__ import annotations

import numpy as np
import pytest

from visage.sed import survey as sv


@pytest.mark.parametrize("disk, want", [(1.0, 0.99), (0.0, 0.81)])
def test_petrosian_recovers_the_published_fractions(disk, want):
    m = sv.measure(np.array([disk]), np.array([1 - disk]), [8.0], [8.0], 0.0)
    assert m["petro_frac"][0] == pytest.approx(want, abs=0.02)


def test_fibre_sees_less_of_a_nearby_galaxy():
    m = sv.measure(np.ones(2), np.zeros(2), [20.0, 1.0], [1.0, 1.0], 0.0)
    assert m["fibre_frac"][0] < 0.1 < 0.5 < m["fibre_frac"][1]


def test_half_light_radius_of_an_exponential():
    m = sv.measure(np.array([1.0]), np.array([0.0]), [5.0], [1.0], 0.0)
    assert m["r50"][0] == pytest.approx(5.0, rel=0.05)


def test_fibre_collisions_lose_one_of_each_close_pair():
    ra = np.array([10.0, 10.0 + 30 / 3600, 11.0])
    dec = np.zeros(3)
    lost = sv._collided(ra, dec, 55.0, np.random.default_rng(0))
    assert lost[:2].sum() == 1 and not lost[2]
