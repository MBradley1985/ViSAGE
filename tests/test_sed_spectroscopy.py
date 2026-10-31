"""Mock fibre spectroscopy (visage/sed/spectroscopy.py)."""

from __future__ import annotations

import numpy as np
import pytest

from visage.sed import spectroscopy as sp

Z = 0.05
D_L = 7e26  # cm


def _spectrum(line=0.0, step=1.0):
    """Flat f_nu with a break at 4000 A and a line at Halpha."""
    wave = np.arange(3000.0, 8000.0, 0.9)
    lnu = np.where(wave < 4000, 1e24 / step, 1e24)
    lnu = lnu + line * np.exp(-0.5 * ((wave - 6563) / 1.0) ** 2)
    return wave, lnu


def test_fibre_sees_more_of_the_bulge_than_the_disk():
    d, b = sp.fibre_weights(np.array([6.0]), np.array([2.0]))
    assert 0 < d[0] < b[0] < 1


def test_flat_fnu_has_no_break_and_a_step_is_recovered():
    wave, lnu = _spectrum()
    loglam, f = sp.observe(wave, lnu, Z, D_L)
    assert sp.dn4000(loglam, f, Z) == pytest.approx(1.0, abs=0.01)
    wave, lnu = _spectrum(step=2.0)
    loglam, f = sp.observe(wave, lnu, Z, D_L)
    assert sp.dn4000(loglam, f, Z) == pytest.approx(2.0, abs=0.05)


def test_line_flux_survives_the_resolution():
    wave, lnu = _spectrum()
    bare = sp.observe(wave, lnu, Z, D_L)[1]
    wave, lnu = _spectrum(line=5e25)
    loglam, f = sp.observe(wave, lnu, Z, D_L)
    sigma = np.ones_like(f)
    flux, err, ew = sp.measure_line(loglam, f, sigma, Z, "Halpha")
    m = sp._band(loglam, Z, 6500, 6620)
    dlam = 10 ** loglam[m] * np.log(10) * sp.DLOGLAM
    want = np.sum((f - bare)[m] * dlam)
    assert flux == pytest.approx(want, rel=0.03) and ew > 0 and err > 0


def test_resolution_width_is_right():
    wave = np.arange(3000.0, 8000.0, 0.1)
    lnu = np.exp(-0.5 * ((wave - 6000) / 0.1) ** 2)
    loglam, f = sp.observe(wave, lnu, 0.0, D_L)
    lam = 10**loglam
    mean = np.sum(lam * f) / np.sum(f)
    width = np.sqrt(np.sum(f * (lam - mean) ** 2) / np.sum(f))
    assert width * 2.3548 == pytest.approx(mean / sp.RESOLUTION, rel=0.25)


def test_noise_has_sky_lines():
    with np.load(sp.NOISE_FILE) as d:
        lam, s = 10 ** d["loglam"], d["sigma"]
    near = np.abs(lam - 5577) < 3
    clear = (lam > 5300) & (lam < 5500)
    assert s[near].max() > 1.5 * np.median(s[clear])
