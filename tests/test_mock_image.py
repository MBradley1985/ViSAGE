"""Mock survey images (visage/sed/mock_image.py) on a small synthetic
lightcone."""

from __future__ import annotations

from dataclasses import replace

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
    assert sky.std() == pytest.approx(mi.map_sigma(s, 1), rel=0.15)
    # A point source at the r limit (22.2) is 5 sigma for a PSF fit.
    area = 1 / np.sum(mi.psf_kernel(s.seeing[1] / s.pixel) ** 2)
    snr = mi.nmgy(22.2) / (mi.noise_sigma(s, 1) * np.sqrt(area))
    assert snr == pytest.approx(5.0)


def test_noise_varies_pixel_to_pixel_without_a_sky_level(
    tmp_path, monkeypatch
):
    p = tmp_path / "cone.h5"
    _cone(p)
    s = replace(mi.SURVEYS["sdss"], sky=())
    monkeypatch.setitem(mi.SURVEYS, "sdss", s)
    m = mi.make_mock_image(p, "sdss", 2, noisy=True, seed=3)
    sky = m.images["sdss_r"][:20, :20]
    assert sky.std() == pytest.approx(mi.map_sigma(s, 1), rel=0.15)


def test_every_survey_has_a_depth():
    assert all(s.depth for s in mi.SURVEYS.values())


def test_rgb_and_fits(tmp_path):
    pytest.importorskip("astropy")
    from astropy.io import fits
    from astropy.wcs import WCS

    p = tmp_path / "cone.h5"
    _cone(p)
    m = mi.make_mock_image(p, "sdss", 1, centre_row=1, noisy=False)
    assert m.rgb.shape[-1] == 3 and 0 <= m.rgb.min() and m.rgb.max() <= 1
    assert m.image_bytes()[:4] == b"\x89PNG"
    out = tmp_path / "m.fits"
    assert m.write_fits(out)
    with fits.open(out) as h:
        assert [x.name for x in h[1:]] == ["SDSS_I", "SDSS_R", "SDSS_G"]
        ny, nx = h[1].data.shape
        c = WCS(h[1].header).pixel_to_world(nx / 2 - 0.5, ny / 2 - 0.5)
    assert c.ra.deg == pytest.approx(m.ra0, abs=1e-6)
    assert c.dec.deg == pytest.approx(m.dec0, abs=1e-6)


@pytest.mark.parametrize("re_pix", [4.0, 12.0])
def test_bulge_cusp_does_not_depend_on_pixel_phase(re_pix):
    size = int(16 * re_pix) | 1
    on = mi.sersic_stamp(4.0, re_pix, 0.8, 0.3, size, sub=1)
    off = mi.sersic_stamp(4.0, re_pix, 0.8, 0.3, size, sub=1, off=(0.3, 0.2))
    c = size // 2
    assert on[c, c] == pytest.approx(off[c, c], rel=0.15)
    assert on[c, c] < 0.2


def test_light_of_a_galaxy_outside_the_field_reaches_it(tmp_path, monkeypatch):
    # Fine pixels: the galaxy is 800 pixels off a 968-pixel field, but its
    # disk (Re ~ 25") still reaches it.
    fine = replace(mi.SURVEYS["sdss"], pixel=0.031, seeing=(0.1,) * 3)
    monkeypatch.setitem(mi.SURVEYS, "sdss", fine)
    p = tmp_path / "cone.h5"
    _cone(p, n=2)
    with h5py.File(p, "a") as f:
        f["ra"][1] = 1.0
        f["dec"][1] = 1.0 + (15 + 24.8) / 3600
        f["DiskRadius"][1] = 0.02
        for b in ("sdss_g", "sdss_r", "sdss_i"):
            for k in ("mag_obs", "disk_mag_obs", "bulge_mag_obs"):
                f[f"{k}_{b}"][1] = 14.0
    m = mi.make_mock_image(p, "sdss", 0.5, centre_row=0, noisy=False)
    assert m.n_galaxies == 2


def test_bright_core_keeps_a_gradient():
    x = np.logspace(0, 5, 200)
    rgb = mi.lupton_rgb([x[None], x[None], x[None]], 1.0)
    assert rgb.max() <= 1
    assert np.all(np.diff(rgb[0, :, 0]) >= 0)
    assert np.sum(rgb[0, :, 0] >= 0.999) < 10


def test_shot_noise_grows_with_the_source():
    s = mi.SURVEYS["sdss"]
    g = mi.electrons_per_nmgy(s, 1)
    # r sky of 20.84 is 0.7245 nmgy/pixel, over the measured noise: near
    # the real camera, about 900 electrons per nanomaggy.
    assert g == pytest.approx(0.7245 / mi.map_sigma(s, 1) ** 2, rel=0.01)
    assert not mi.SURVEYS["wise"].sky


def test_bright_galaxy_has_more_noise_than_sky(tmp_path):
    p = tmp_path / "cone.h5"
    _cone(p)
    with h5py.File(p, "a") as f:
        f["mag_obs_sdss_r"][0] = 10.0
        f["disk_mag_obs_sdss_r"][0] = 10.4
        f["bulge_mag_obs_sdss_r"][0] = 11.3
    clean = mi.make_mock_image(p, "sdss", 2, centre_row=0, noisy=False)
    noisy = mi.make_mock_image(p, "sdss", 2, centre_row=0, seed=1)
    a, b = clean.images["sdss_r"], noisy.images["sdss_r"]
    core = a > 0.5 * a.max()
    assert core.sum() > 5
    assert (b - a)[core].std() > 2 * mi.noise_sigma(mi.SURVEYS["sdss"], 1)


def test_black_point_keeps_a_galaxys_colour():
    r = np.full((1, 1), 4.0)
    b = np.full((1, 1), 2.0)
    plain = mi.lupton_rgb([r, 0.5 * (r + b), b], 1.0)
    cut = mi.lupton_rgb([r, 0.5 * (r + b), b], 1.0, black=1.0)
    assert cut[0, 0, 1] < plain[0, 0, 1]
    assert cut[0, 0, 0] / cut[0, 0, 2] == pytest.approx(2.0)


def test_background_adds_only_galaxies_beyond_the_cone(tmp_path):
    p, deep = tmp_path / "cone.h5", tmp_path / "deep.h5"
    _cone(p)
    _cone(deep, n=400)
    with h5py.File(deep, "a") as f:
        z = np.r_[np.full(200, 0.04), np.full(200, 0.2)]
        f["redshift_cosmological"][...] = z
        f["ra"][...] = 1.0 + np.linspace(-0.1, 0.1, 400)
        f["dec"][...] = 1.0 + np.linspace(-0.1, 0.1, 400)[::-1]
    plain = mi.make_mock_image(p, "sdss", 2, noisy=False)
    both = mi.make_mock_image(p, "sdss", 2, noisy=False, background=deep)
    assert both.n_galaxies > plain.n_galaxies
    assert both.images["sdss_r"].sum() > plain.images["sdss_r"].sum()


def test_moffat_psf_has_the_fwhm_and_wings():
    k = mi.psf_kernel(4.0)
    c = k.shape[0] // 2
    assert k.sum() == pytest.approx(1.0)
    assert k[c, c + 2] / k[c, c] == pytest.approx(0.5, abs=0.01)
    gauss = np.exp(-4 * np.log(2) * (12.0 / 4.0) ** 2)
    assert k[c, c + 12] / k[c, c] > 50 * gauss


def test_background_cones_are_deeper_and_have_the_bands(tmp_path):
    for name, z in (("cone", 0.05), ("deep", 0.5), ("shallow", 0.01)):
        (tmp_path / name).mkdir()
        _cone(tmp_path / name / f"{name}.h5")
        with h5py.File(tmp_path / name / f"{name}.h5", "a") as f:
            f["redshift_cosmological"][...] = z
    got = mi.background_cones(tmp_path / "cone" / "cone.h5", "sdss")
    assert [c["title"] for c in got] == ["deep"]


@pytest.mark.parametrize(
    "fmt, magic",
    [("png", b"\x89PNG"), ("jpeg", b"\xff\xd8"), ("pdf", b"%PDF")],
)
def test_image_formats(tmp_path, fmt, magic):
    p = tmp_path / "cone.h5"
    _cone(p)
    m = mi.make_mock_image(p, "sdss", 1, noisy=False)
    assert m.image_bytes(fmt).startswith(magic)


def test_random_patch_moves_with_the_seed_and_has_no_redshift(tmp_path):
    p = tmp_path / "cone.h5"
    _cone(p, n=20)
    a = mi.make_mock_image(p, "sdss", 0.5, noisy=False, patch=True, seed=1)
    b = mi.make_mock_image(p, "sdss", 0.5, noisy=False, patch=True, seed=2)
    assert a.ra0 != b.ra0 and np.isnan(a.z0)
    assert a.write_fits(tmp_path / "patch.fits")


def test_leaving_the_sky_in_lifts_the_colours_not_the_images(tmp_path):
    p = tmp_path / "cone.h5"
    _cone(p)
    a = mi.make_mock_image(p, "sdss", 2, seed=1)
    b = mi.make_mock_image(p, "sdss", 2, seed=1, subtract_sky=False)
    assert np.array_equal(a.images["sdss_r"], b.images["sdss_r"])
    assert 0.05 < np.median(b.rgb) < 0.2 and np.median(a.rgb) < 0.02


def test_stars_come_from_the_measured_counts_only_on_request(tmp_path):
    p = tmp_path / "cone.h5"
    _cone(p)
    assert mi.make_mock_image(p, "sdss", 10, noisy=False).n_stars == 0
    m = mi.make_mock_image(p, "sdss", 10, noisy=False, stars=True)
    n = len(np.load(mi.STAR_FILE)["r"])
    assert m.n_stars == pytest.approx(n / 36, rel=0.5)


def test_star_temperature_follows_colour():
    assert mi._star_temperature(np.array(1.5)) < 4000
    assert mi._star_temperature(np.array(0.2)) > 6000


def test_beam_noise_is_correlated_at_the_map_noise(tmp_path, monkeypatch):
    p = tmp_path / "cone.h5"
    _cone(p)
    s = replace(
        mi.SURVEYS["sdss"],
        seeing=(6.0, 6.0, 6.0),
        ground=False,
        beam_noise=True,
        sky=(),
    )
    monkeypatch.setitem(mi.SURVEYS, "sdss", s)
    im = mi.make_mock_image(p, "sdss", 5, seed=1).images["sdss_r"][:60, :60]
    assert im.std() == pytest.approx(mi.map_sigma(s, 1), rel=0.3)
    assert np.corrcoef(im[:-1].ravel(), im[1:].ravel())[0, 1] > 0.5


def test_confusion_noise_is_shared_between_bands(tmp_path, monkeypatch):
    p = tmp_path / "cone.h5"
    _cone(p)
    s = mi.SURVEYS["sdss"]
    conf = 3.631e-3 * float(mi.nmgy(22.2)) / 5
    s = replace(s, sky=(), confusion=(0.0, conf, conf))
    monkeypatch.setitem(mi.SURVEYS, "sdss", s)
    m = mi.make_mock_image(p, "sdss", 2, seed=1)
    r, g = m.images["sdss_r"][:60, :60], m.images["sdss_g"][:60, :60]
    assert np.corrcoef(r.ravel(), g.ravel())[0, 1] > 0.9


@pytest.mark.parametrize("survey", ["sdss", "lsst", "hst", "nircam"])
def test_mirror_psf_is_centred_and_even_across_bands(survey):
    s = mi.SURVEYS[survey]
    for i in range(len(s.bands)):
        k = mi._kernel(s, i)
        assert k.sum() == pytest.approx(1, abs=1e-3)
        assert np.unravel_index(k.argmax(), k.shape) == (
            k.shape[0] // 2,
            k.shape[1] // 2,
        )


def test_equal_seeing_gives_equal_peaks():
    s = mi.SURVEYS["lsst"]
    peaks = [mi._kernel(s, i).max() for i in range(3)]
    assert max(peaks) / min(peaks) < 1.2


def test_shot_noise_reaches_surveys_with_a_sky_level():
    for name in ("des", "euclid_vis", "roman", "hst", "nircam"):
        assert len(mi.SURVEYS[name].sky) == len(mi.SURVEYS[name].bands)


def test_real_and_mock_share_the_composite():
    im = [np.full((4, 4), 1.0)] * 3
    a = mi.composite(im, (1, 1, 1), (0.1, 0.1, 0.1))
    b = mi.composite(im, (1, 1, 1), (0.1, 0.1, 0.1), sky_level=True)
    assert a.shape == (4, 4, 3) and b.mean() >= a.mean()


def test_saturated_charge_bleeds_along_the_column():
    im = np.zeros((41, 41))
    im[20, 20] = 50.0
    out = mi._bleed(im, 5.0)
    assert out[:, 20].max() == 5.0 and (out[:, 20] == 5.0).sum() > 5
    assert out[20, 19] == 0


def test_old_population_is_white_in_a_neutral_survey():
    s = mi.SURVEYS["spitzer"]
    with np.load(mi.REFERENCE_FILE) as d:
        mags = dict(zip(d["bands"].tolist(), d["mag"].tolist(), strict=True))
    w = mi._balance(s)
    f = [mi.nmgy(mags[b]) * x for b, x in zip(s.bands, w, strict=True)]
    assert max(f) / min(f) == pytest.approx(1.0)


def test_every_band_has_a_reference():
    with np.load(mi.REFERENCE_FILE) as d:
        have = set(d["bands"].tolist())
    assert {b for s in mi.SURVEYS.values() for b in s.bands} <= have
