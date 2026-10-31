"""Redshift-space group finding (visage/sed/groups.py)."""

from __future__ import annotations

import numpy as np
import pytest

from visage.sed import groups as gr


def _sky(seed=1):
    """A sparse field plus one tight group of 10."""
    rng = np.random.default_rng(seed)
    ra = rng.uniform(0, 10, 300)
    dec = rng.uniform(0, 5, 300)
    z = rng.uniform(0.02, 0.1, 300)
    ra[:10] = 5 + rng.normal(0, 0.005, 10)
    dec[:10] = 2.5 + rng.normal(0, 0.005, 10)
    z[:10] = 0.05 + rng.normal(0, 0.001, 10)
    return ra, dec, z


def test_tight_group_is_found_whole():
    ra, dec, z = _sky()
    lab = gr.find_groups(ra, dec, z, 17.77, 0.7)
    assert len(set(lab[:10])) == 1 and lab[10] != lab[0]


def test_big_group_comes_from_the_first_pass_and_labels_are_unique():
    ra, dec, z = _sky()
    ra[10:40] = 8 + 0.01 * np.arange(30) / 30
    dec[10:40] = 1.0
    z[10:40] = 0.07
    lab = gr.find_groups(ra, dec, z, 17.77, 0.7)
    assert len(set(lab[10:40])) == 1 and set(lab[10:40]) != set(lab[:10])


def test_linking_grows_with_distance_in_a_flux_limited_sample():
    near, far = gr._scale(np.array([3000.0, 30000.0]), 17.77, 0.7)
    assert 1 <= near < far


def test_perfect_groups_score_one():
    h = np.array([0, 0, 0, 1, 1, 2, 3])
    res = gr.bijective(h + 5, h)
    assert res["purity"] == 1 and res["completeness"] == 1


def test_merged_haloes_lose_both():
    h = np.array([0, 0, 1, 1])
    res = gr.bijective(np.zeros(4), h)
    assert res["purity"] == 0 and res["completeness"] == 0


def test_virial_mass_reduces_to_the_theorem_above_the_limits():
    m = gr.virial_mass(np.array([800.0]), np.array([2.0]), 0.7)[0]
    assert m == pytest.approx(5 / 3 * 800**2 * 2 / gr.G_MPC)


def test_small_groups_get_the_calibrated_boost():
    low = gr.virial_mass(np.array([100.0]), np.array([0.1]), 0.7)[0]
    assert low > 5 / 3 * 100**2 * 0.1 / gr.G_MPC


def test_table_recovers_the_dispersion():
    rng = np.random.default_rng(0)
    n = 200
    z = 0.05 + rng.normal(0, 500 / gr.C_KMS * 1.05, n)
    ra, dec = rng.normal(5, 0.05, n), rng.normal(2, 0.05, n)
    t = gr.group_table(ra, dec, z, np.zeros(n, int), 0.7)
    assert t["sigma"][0] == pytest.approx(500, rel=0.15)


def test_collided_galaxies_get_no_group():
    ra, dec, z = _sky()
    cat = {
        "ra": ra,
        "dec": dec,
        "z_obs": z,
        "fibre_collided": np.arange(300) == 299,
    }
    out = gr.add_groups(cat, 17.77, 0.7)
    assert out["group"][299] == -1 and out["group_n"][0] >= 10
