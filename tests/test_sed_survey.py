"""Survey apertures and selection (visage/sed/survey.py)."""

from __future__ import annotations

import h5py
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


def test_available_needs_the_detection_band():
    assert sv.available({"disk_mag_obs_sdss_g", "bulge_mag_obs_sdss_g"}) == []
    assert sv.available(set()) == []
    both = {"disk_mag_obs_sdss_r", "bulge_mag_obs_sdss_r"}
    assert "sdss_main" in sv.available(both)


def test_csv_has_a_row_per_galaxy(tmp_path):
    p = tmp_path / "cat.csv"
    sv.write_csv({"ra": np.arange(3.0), "z_cos": np.ones(3)}, p)
    assert p.read_text().splitlines()[0] == "ra,z_cos"
    assert len(p.read_text().splitlines()) == 4


def test_summary_density_uses_the_cone_area(tmp_path):
    p = tmp_path / "cone.h5"
    with h5py.File(p, "w") as f:
        f["ra"] = np.array([0.0, 10.0])
        f["dec"] = np.array([0.0, 5.0])
    cat = {
        "ra": np.zeros(50),
        "z_cos": np.full(50, 0.1),
        "r50": np.full(50, 2.0),
        "fibre_mag_sdss_r": np.full(50, 19.0),
        "petro_mag_sdss_r": np.full(50, 17.5),
    }
    n = sv.summary(cat, p, "sdss_main")
    assert n["density"] == pytest.approx(1.0, rel=0.01)
    assert n["fibre"] == pytest.approx(1.5)
