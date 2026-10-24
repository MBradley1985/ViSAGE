"""Mock survey images (visage/sed/mock_image.py) on a small synthetic
lightcone."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from visage.sed import mock_image as mi


def _cone(path, n=3, split=True):
    """Galaxies near RA 1, Dec 1 at z ~ 0.05, all observed in SDSS gri."""
    rng = np.random.default_rng(1)
    ra = 1.0 + np.r_[0.0, rng.uniform(-0.01, 0.01, n - 1)]
    dec = 1.0 + np.r_[0.0, rng.uniform(-0.01, 0.01, n - 1)]
    dist = np.full(n, 150.0)  # Mpc/h
    th, ph = np.deg2rad(90 - dec), np.deg2rad(ra)
    pos = (
        dist[:, None]
        * np.c_[np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]
    )
    with h5py.File(path, "w") as f:
        sim = f.create_group("SageOutputHeader/Simulation")
        sim.attrs["hubble_h"] = 0.7
        cols = {
            "ra": ra,
            "dec": dec,
            "distance": dist,
            "redshift_cosmological": np.full(n, 0.05),
            "DiskRadius": np.full(n, 0.002),
            "BulgeRadius": np.full(n, 0.001),
            "Spinx": np.ones(n),
            "Spiny": np.zeros(n),
            "Spinz": np.zeros(n),
            "Posx": pos[:, 0],
            "Posy": pos[:, 1],
            "Posz": pos[:, 2],
            "StellarMass": np.ones(n),
            "BulgeMass": np.full(n, 0.3),
            "CosInclination": np.full(n, 0.5),
        }
        for k, v in cols.items():
            f[k] = v
        for b in ("sdss_g", "sdss_r", "sdss_i"):
            f[f"mag_obs_{b}"] = np.r_[16.0, np.full(n - 1, 19.0)]
            if split:  # disk + bulge = the total
                f[f"disk_mag_obs_{b}"] = f[f"mag_obs_{b}"][:] + 2.5 * np.log10(
                    1 / 0.7
                )
                f[f"bulge_mag_obs_{b}"] = f[f"mag_obs_{b}"][
                    :
                ] + 2.5 * np.log10(1 / 0.3)


def test_surveys_offered_and_field_cap(tmp_path):
    p = tmp_path / "cone.h5"
    _cone(p)
    with h5py.File(p) as f:
        assert mi.available_surveys(set(f.keys())) == ["sdss"]
    # 30' at 0.396"/pixel is 4545 pixels: over the cap.
    assert 30 not in mi.field_sizes("sdss")
    assert 1 in mi.field_sizes("nircam") and 5 not in mi.field_sizes("nircam")


@pytest.mark.parametrize("split", [True, False])
def test_noiseless_image_keeps_the_flux(tmp_path, split):
    p = tmp_path / "cone.h5"
    _cone(p, split=split)
    m = mi.make_mock_image(p, "sdss", 2, noisy=False)
    assert m.n_galaxies == 3
    # Everything sits well inside the 2' field, so the image holds all
    # the light: 16 + 2 x 19 mag.
    want = float(mi.nmgy(16.0) + 2 * mi.nmgy(19.0))
    for b in ("sdss_g", "sdss_r", "sdss_i"):
        assert m.images[b].sum() == pytest.approx(want, rel=0.02)
    # The brightest galaxy is the centre, at the middle of the image.
    assert (m.ra0, m.dec0) == (1.0, 1.0)
    img = m.images["sdss_r"]
    y, x = np.unravel_index(np.argmax(img), img.shape)
    assert abs(x - img.shape[1] / 2) <= 1 and abs(y - img.shape[0] / 2) <= 1


def test_depth_noise_matches_the_survey_limit(tmp_path):
    p = tmp_path / "cone.h5"
    _cone(p)
    m = mi.make_mock_image(p, "sdss", 2, noisy=True, seed=3)
    s = mi.SURVEYS["sdss"]
    sky = m.images["sdss_r"][:20, :20]  # an empty corner
    assert sky.std() == pytest.approx(mi.noise_sigma(s, 1), rel=0.15)
    # A point source at the r limit (22.2) is 5 sigma for a PSF fit.
    sig_psf = s.seeing[1] / 2.3548 / s.pixel
    snr = mi.nmgy(22.2) / (
        mi.noise_sigma(s, 1) * np.sqrt(4 * np.pi * sig_psf**2)
    )
    assert snr == pytest.approx(5.0)


def test_rgb_and_fits(tmp_path):
    pytest.importorskip("astropy")
    from astropy.io import fits
    from astropy.wcs import WCS

    p = tmp_path / "cone.h5"
    _cone(p)
    m = mi.make_mock_image(p, "sdss", 1, centre_row=1, noisy=False)
    assert m.rgb.shape[-1] == 3 and 0 <= m.rgb.min() and m.rgb.max() <= 1
    assert m.png_bytes()[:4] == b"\x89PNG"
    out = tmp_path / "m.fits"
    assert m.write_fits(out)
    with fits.open(out) as h:
        assert [x.name for x in h[1:]] == ["SDSS_I", "SDSS_R", "SDSS_G"]
        ny, nx = h[1].data.shape
        c = WCS(h[1].header).pixel_to_world(nx / 2 - 0.5, ny / 2 - 0.5)
    assert c.ra.deg == pytest.approx(m.ra0, abs=1e-6)
    assert c.dec.deg == pytest.approx(m.dec0, abs=1e-6)
