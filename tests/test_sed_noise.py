"""Survey noise on a lightcone's photometry (visage/sed/noise.py)."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from visage.sed import noise


def _cone(path, n=20000):
    with h5py.File(path, "w") as f:
        f.create_group("SageOutputHeader/Simulation").attrs["hubble_h"] = 0.7
        f.create_group("PhotometryHeader")
        f["StellarMass"] = np.ones(n)
        f["BulgeMass"] = np.zeros(n)
        f["DiskRadius"] = np.full(n, 0.002)
        f["BulgeRadius"] = np.zeros(n)
        f["distance"] = np.full(n, 150.0)
        f["redshift_cosmological"] = np.full(n, 0.05)
        f["mag_obs_sdss_r"] = np.full(n, 20.0, dtype=np.float32)
        f["mag_obs_jwst_f200w"] = np.full(n, 20.0, dtype=np.float32)


def test_point_source_at_the_limit_has_the_quoted_snr():
    f5 = noise.ujy(22.2)
    err = noise.flux_error("sdss_r", np.array([f5]), np.array([0.0]))
    assert f5 / err[0] == pytest.approx(5.0, rel=0.01)


def test_a_larger_galaxy_has_a_larger_error():
    f = np.array([1.0, 1.0])
    err = noise.flux_error("sdss_r", f, np.array([0.0, 5.0]))
    assert err[1] > 3 * err[0]


def test_bright_galaxies_reach_the_calibration_floor():
    err = noise.flux_error("sdss_r", np.array([1e6]), np.array([1.0]))
    assert err[0] == pytest.approx(1e4, rel=0.01)


def test_add_noise_writes_only_bands_with_depths(tmp_path):
    p = tmp_path / "cone.h5"
    _cone(p)
    assert noise.add_noise(p, seed=2) == ["sdss_r"]
    with h5py.File(p) as f:
        assert "flux_obs_jwst_f200w" not in f
        flux, err = f["flux_obs_sdss_r"][:], f["fluxerr_obs_sdss_r"][:]
        assert "Noise" in f["PhotometryHeader"].attrs
    z = (flux - noise.ujy(20.0)) / err
    assert abs(z.mean()) < 0.05 and z.std() == pytest.approx(1.0, abs=0.05)
