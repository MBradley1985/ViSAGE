"""Tests for visage.sed.spectrum: a galaxy's spectrum is made with the
settings the cone's photometry recorded (no FSPS needed for these)."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from visage.sed.photometry import compute_photometry, write_photometry
from visage.sed.spectrum import GalaxySpectrum, find_alist, run_settings


def _cone(tmp_path, dust: str, lines: str = "none", disk=False):
    path = tmp_path / "cone.h5"
    with h5py.File(path, "w") as f:
        f["StellarMass"] = np.ones(3, dtype=np.float32)
        if disk:
            f["disk_mag_obs_sdss_r"] = np.zeros(3, dtype=np.float32)
        sim = f.create_group("SageOutputHeader/Simulation")
        sim.attrs["FileWithSnapList"] = "input/run/trees/run.a_list"
    write_photometry(
        path,
        {
            "_settings": {
                "IMF": "Kroupa 2001",
                "RecycleFraction": 0.4,
                "Metallicity": "solar",
                "Dust": dust,
                "NebularEmission": lines,
            }
        },
    )
    return path


def test_run_settings_charlot_fall(tmp_path):
    path = _cone(
        tmp_path,
        "Charlot & Fall 2000 birth clouds + ISM slab; re-emitted in the IR",
        lines="HII regions: Gutkin+16",
        disk=True,
    )
    kw, hdr = run_settings(path)
    assert kw["dust_model"] == "charlot_fall"
    assert kw["dust_emission"] is True
    assert kw["lines"] is True
    assert kw["disk_bulge"] is True
    assert kw["use_metallicity"] is False
    assert kw["imf_type"] == 2
    assert kw["recycle_fraction"] == pytest.approx(0.4)
    assert hdr["IMF"] == "Kroupa 2001"
    # every key is one compute_photometry takes
    import inspect

    assert set(kw) <= set(inspect.signature(compute_photometry).parameters)


def test_run_settings_calzetti_and_none(tmp_path):
    kw, _ = run_settings(_cone(tmp_path, "Calzetti 2000, tau_V=0.7"))
    assert kw["dust_model"] == "calzetti" and kw["dust"] is True
    assert kw["dust2"] == pytest.approx(0.7)
    assert kw["dust_emission"] is False and kw["lines"] is False
    kw, _ = run_settings(_cone(tmp_path, "none"))
    assert kw["dust_model"] == "none"


def test_find_alist_in_a_sibling_folder(tmp_path):
    # LightSAGE records the a_list relative to the SAGE run directory,
    # usually a sibling of the viewer's folder (../SAGE26/input/...).
    viewer = tmp_path / "viewer" / "sage_outputs"
    viewer.mkdir(parents=True)
    al = tmp_path / "SAGE26" / "input" / "run" / "trees" / "run.a_list"
    al.parent.mkdir(parents=True)
    al.write_text("0.5\n1.0\n")
    path = _cone(viewer, "none")
    assert find_alist(path) == al


def test_observed_flux_scaling():
    # 1 L_sun/Hz at 10 pc, z = 0: f_nu = L / (4 pi d^2)
    d = 10 * 3.0856775814913673e18
    s = GalaxySpectrum(
        row=0,
        label="x",
        z_obs=0.0,
        d_l_cm=d,
        wave=np.array([5000.0]),
        lnu={"observed": np.array([1.0])},
        mags={},
    )
    expect = 3.828e33 / (4 * np.pi * d**2) * 1e29
    assert s.fnu_ujy()[0] == pytest.approx(expect)
    s.z_obs = 1.0
    assert s.wave_obs[0] == pytest.approx(10000.0)
    assert s.fnu_ujy()[0] == pytest.approx(2 * expect)
