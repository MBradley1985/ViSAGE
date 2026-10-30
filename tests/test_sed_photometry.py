"""Tests for visage.sed (synthetic photometry for LightSAGE lightcones).

FSPS/astropy are optional dependencies (pip install sage-viewer[sed]) — every
test here skips cleanly if they're not installed (or, for fsps, installed but
not configured — importing it raises RuntimeError rather than ImportError
when the SPS_HOME env var pointing at its SSP data isn't set, e.g. in CI)
rather than failing.
"""

from __future__ import annotations

import numpy as np
import pytest

try:
    import fsps
except Exception as exc:  # ImportError (missing) or RuntimeError (no SPS_HOME)
    pytest.skip(f"fsps unavailable: {exc}", allow_module_level=True)
pytest.importorskip("astropy")

from visage.sed.photometry import (  # noqa: E402
    _FilterProjector,
    _mag_from_fnu,
    _trapz_weights,
)
from visage.sed.ssp_grid import (  # noqa: E402
    SSPGrid,
    assign_metallicity_bins,
    metallicity_bin_edges,
    metallicity_weights,
)


def test_trapz_weights_matches_trapezoid():
    x = np.array([0.0, 1.0, 2.5, 4.0, 10.0])
    f = np.array([1.0, 2.0, 0.5, 3.0, 1.0])
    weighted_sum = float(np.sum(f * _trapz_weights(x)))
    assert weighted_sum == pytest.approx(float(np.trapezoid(f, x)))


def test_metallicity_bin_edges_and_assignment():
    edges = metallicity_bin_edges(n_bins=4)
    assert len(edges) == 5
    assert edges[0] == -2.0 and edges[-1] == 0.3

    # values inside range land in the expected bin; out-of-range values clamp
    logzsol = np.array([-2.0, -1.0, 0.0, 0.3, -10.0, 10.0])
    idx, centers = assign_metallicity_bins(logzsol, edges)
    assert idx.min() >= 0 and idx.max() <= 3
    assert idx[4] == idx[0]  # -10 clamps to the same bin as the lower edge
    assert idx[5] == 3  # +10 clamps into the top bin
    assert len(centers) == 4


def test_mag_from_fnu_handles_zero_flux():
    f_nu = np.array([0.0, 1e-27, 1.0])
    mag = _mag_from_fnu(f_nu)
    assert mag[0] > 100  # zero flux -> the floor sentinel, not -inf/NaN
    assert np.isfinite(mag).all()
    # AB zeropoint: f_nu = 1 (cgs erg/s/cm^2/Hz) -> m_AB = -48.6
    assert mag[2] == pytest.approx(-48.6, abs=1e-4)


def test_ssp_grid_tage_zero_is_not_the_fsps_sentinel():
    """Regression test: FSPS treats tage=0.0 as 'return the whole age grid'
    (matches get_mags' documented default), not 'age exactly zero'. A naive
    call would silently get back a (n_ages, n_wave) array instead of one
    spectrum, breaking np.stack in spectra_at_ages with a shape error."""
    grid = SSPGrid(logzsol=-0.5)
    spec = grid.spectrum_at_age(0.0)
    assert spec.shape == grid.wave.shape

    ages = np.array([0.0, 0.0, 1.0, 5.0])
    matrix = grid.spectra_at_ages(ages)
    assert matrix.shape == (4, len(grid.wave))
    assert np.isfinite(matrix).all()
    # the two age=0.0 rows must be identical (both clamped to the same floor)
    np.testing.assert_array_equal(matrix[0], matrix[1])


def test_filter_projector_flat_spectrum_recovers_constant(monkeypatch):
    """A flat (constant-in-lambda) spectrum through a top-hat filter at
    z=0 should recover exactly that constant — an exact-answer sanity check
    that doesn't depend on FSPS's real filter curves.

    The top-hat must be resolved at a density comparable to its own
    bandwidth (as every real FSPS filter curve is — e.g. sdss_g has 89
    points over ~2200 A) — a filter defined by only a couple of points
    spanning a sharp edge would make the numerator (interpolated onto the
    fine SSP wavelength grid) and denominator (integrated on the filter's
    own native grid) discretize that edge differently, which is a
    dicretization-consistency artifact of an under-resolved test filter,
    not a property of the projection math itself.
    """
    import visage.sed.photometry as photometry_mod

    wave = np.linspace(1000.0, 9000.0, 4000)

    def _fake_transmission(name):
        # top-hat filter between 4000-6000 A, resolved every 20 A (~100
        # points) so its own native grid is fine relative to its bandwidth.
        edge = np.linspace(3990.0, 4010.0, 5)
        core = np.linspace(4010.0, 5990.0, 100)
        edge2 = np.linspace(5990.0, 6010.0, 5)
        fw = np.concatenate([edge, core, edge2])
        ft = np.concatenate(
            [
                np.linspace(0.0, 1.0, 5),
                np.ones_like(core),
                np.linspace(1.0, 0.0, 5),
            ]
        )
        return fw, ft

    monkeypatch.setattr(
        photometry_mod, "filter_transmission", _fake_transmission
    )

    proj = _FilterProjector("toy_tophat", wave)
    flat_level = 3.7
    spectra = np.full((5, len(wave)), flat_level)
    f_nu_eff = proj.project(spectra, z=0.0)
    assert f_nu_eff == pytest.approx(flat_level, rel=1e-3)


@pytest.mark.slow
def test_compute_photometry_end_to_end(tmp_path):
    """Full pipeline on a tiny synthetic lightcone: no crashes, correct
    output shape/keys, zero-mass galaxies are NaN, everyone else finite and
    in a physically plausible magnitude range, and (the real payoff) more
    massive galaxies come out redder — the expected mass-color relation."""
    import h5py

    from visage.sed.photometry import compute_photometry

    h, om, ol = 0.7, 0.3, 0.7
    n_bins = 8
    a_list = np.linspace(0.1, 1.0, n_bins)
    alist_path = tmp_path / "toy.a_list"
    np.savetxt(alist_path, a_list)

    rng = np.random.default_rng(0)
    n = 40
    stellar_mass = rng.uniform(0.01, 5.0, n)  # 1e10 Msun/h
    stellar_mass[0] = 0.0  # exercise the zero-mass exclusion path
    sfh_disk = rng.uniform(0, 1, (n, n_bins)) * stellar_mass[:, None] * 0.5
    sfh_bulge = rng.uniform(0, 1, (n, n_bins)) * stellar_mass[:, None] * 0.5
    # normalize so each row sums to ~stellar_mass (not exact, fine for a test)
    row_sum = sfh_disk.sum(1) + sfh_bulge.sum(1)
    scale = np.where(
        row_sum > 0, stellar_mass / np.maximum(row_sum, 1e-30), 0.0
    )
    sfh_disk *= scale[:, None]
    sfh_bulge *= scale[:, None]
    metals = stellar_mass * rng.uniform(
        0.001, 0.02, n
    )  # metal mass fraction range
    snapnum = np.full(n, n_bins - 1, dtype=np.int32)
    redshift = np.full(n, 0.05)

    path = tmp_path / "toy_lightcone.h5"
    with h5py.File(path, "w") as f:
        f["StellarMass"] = stellar_mass.astype(np.float32)
        f["SFHMassDisk"] = sfh_disk.astype(np.float32)
        f["SFHMassBulge"] = sfh_bulge.astype(np.float32)
        f["MetalsStellarMass"] = metals.astype(np.float32)
        f["SnapNum"] = snapnum
        f["redshift_cosmological"] = redshift
        sim = f.create_group("SageOutputHeader").create_group("Simulation")
        sim.attrs["hubble_h"] = h
        sim.attrs["omega_matter"] = om
        sim.attrs["omega_lambda"] = ol
        sim.attrs["FileWithSnapList"] = str(alist_path)

    results = compute_photometry(
        path, bands=("sdss_g", "sdss_r"), frame="both", use_metallicity=False
    )
    settings = results.pop("_settings")
    assert settings["IMF"] == "Chabrier 2003"
    assert settings["RecycleFraction"] == 0.43
    assert set(results) == {
        "mag_rest_sdss_g",
        "mag_obs_sdss_g",
        "mag_rest_sdss_r",
        "mag_obs_sdss_r",
    }
    for arr in results.values():
        assert arr.shape == (n,)
        assert np.isnan(arr[0])  # the zero-mass galaxy
        assert np.isfinite(arr[1:]).all()
        # broadly plausible AB magnitude range for both frames at low z
        assert (arr[1:] > -30).all() and (arr[1:] < 60).all()

    gr_rest = results["mag_rest_sdss_g"][1:] - results["mag_rest_sdss_r"][1:]
    sm = stellar_mass[1:]
    order = np.argsort(sm)
    lo = order[: len(order) // 3]
    hi = order[-len(order) // 3 :]
    assert gr_rest[hi].mean() > gr_rest[lo].mean()  # more massive -> redder


def test_mean_spectrum_spans_the_bin():
    """A history bin's stars, spread over its time span, are brighter and
    bluer than all of them placed at the bin's oldest edge."""
    grid = SSPGrid(logzsol=0.0)
    blue = grid.wave < 4000
    spread = grid.mean_spectrum(0.0, 0.5)
    oldest = grid.spectrum_at_age(0.5)
    assert spread[blue].sum() > 2 * oldest[blue].sum()
    # A very narrow span is the single-age spectrum.
    narrow = grid.mean_spectrum(1.0, 1.0 + 1e-7)
    np.testing.assert_allclose(narrow, grid.spectrum_at_age(1.0), rtol=1e-6)


def test_metallicity_weights_interpolate_between_nodes():
    nodes = np.array([-1.0, 0.0, 0.5])
    lo, hi, w = metallicity_weights(np.array([-1.0, -0.5, 0.25, 9.0]), nodes)
    assert list(lo) == [0, 0, 1, 1] and list(hi) == [1, 1, 2, 2]
    np.testing.assert_allclose(w, [0.0, 0.5, 0.5, 1.0])


def test_dust_equilibrium_and_attenuation():
    from visage.sed import dust

    # ~0.01 core-collapse SNe per Msun formed (Chabrier IMF, 8-40 Msun).
    assert 0.008 < dust.sn_per_mass_formed() < 0.014
    # Solar-metallicity, H2-rich, star-forming gas: about Milky Way dust
    # (dust/gas ~ 1/100); never more dust than metals.
    cold = np.array([1e10, 1e10, 1e10])
    z = np.array([0.0142, 0.0142, 0.0014])
    delta = dust.cold_dust_ratio(
        cold, z * cold, 0.3 * cold, np.array([1.0, 1.0, 1.0])
    )
    assert 0.003 < delta[0] < 0.0072
    assert delta[2] < delta[0]  # metal-poor: less dust
    assert (delta <= 0.5 * z + 1e-9).all()  # growth stops at half
    # Metal-poor: dust-to-metals ~ the stellar condensation share (0.2),
    # so dust-to-gas falls with metallicity.
    assert 0.15 < delta[2] / z[2] < 0.3
    # No gas: no dust.
    assert (
        dust.cold_dust_ratio(
            np.array([0.0]), np.array([0.0]), np.array([0.0]), np.array([1.0])
        )[0]
        == 0
    )
    # Screen transmission: 1 at zero depth, falls with depth, and is lower
    # in the blue than the red.
    wave = np.array([3500.0, 5500.0, 8000.0])
    t = dust.ism_transmission(
        wave, np.array([0.0, 1.0, 2.0]), np.array([-0.7, -0.7, -0.7])
    )
    np.testing.assert_allclose(t[0], 1.0, atol=1e-6)
    assert (t[1] < 1).all() and (t[2] < t[1]).all()
    assert t[1, 0] < t[1, 2]


def test_zero_spin_orientation_does_not_depend_on_rows():
    from visage.sed import dust as dm

    pos = np.array([[10.0, 2.0, 3.0], [4.0, 50.0, 6.0], [7.0, 8.0, 90.0]])
    spin = np.zeros_like(pos)
    full = dm.cos_inclination(spin, pos)
    assert dm.cos_inclination(spin[2:], pos[2:])[0] == full[2]
    assert np.all((full >= 0) & (full <= 1))


@pytest.mark.parametrize("z", [3.0, 6.0])
def test_igm_matches_fsps(z):
    fsps = pytest.importorskip("fsps")
    from visage.sed import igm

    kw = dict(zcontinuous=1, sfh=1, tau=1.0, imf_type=1, dust_type=0)
    on = fsps.StellarPopulation(add_igm_absorption=True, zred=z, **kw)
    off = fsps.StellarPopulation(add_igm_absorption=False, zred=z, **kw)
    w, a = on.get_spectrum(tage=0.5)
    _, b = off.get_spectrum(tage=0.5)
    m = (w > 600) & (w < 1300)
    assert igm.transmission(w, z)[m] == pytest.approx((a / b)[m], abs=1e-3)
    assert igm.transmission(np.array([1300.0]), z)[0] == 1.0


def test_sfh_step_offset_reads_either_layout():
    from visage.io.galaxy_reader import sfh_step_offset

    old, new = np.zeros((2, 6)), np.zeros((2, 6))
    old[:, 2], new[:, 3] = 1.0, 1.0  # the last step of galaxies at snap 3
    assert sfh_step_offset(old, [3, 3]) == 0
    assert sfh_step_offset(new, [3, 3]) == 1


def test_umin_follows_the_light_per_dust_mass():
    from visage.sed import dust as dm

    u = dm.umin_from_luminosity(
        np.array([1.0, 141.25, 1e6]), np.array([1.0, 1.0, 1.0])
    )
    assert u[0] == dm.U_MIN_NODES[0] and u[2] == dm.U_MIN_NODES[-1]
    assert u[1] == pytest.approx(1.0, rel=1e-3)


def test_warmer_dust_peaks_at_shorter_wavelengths():
    pytest.importorskip("fsps")
    from visage.sed import dust as dm

    wave = np.logspace(3, 7.5, 3000)
    cold, warm = dm.emission_spectra(wave, np.array([0.2, 20.0]))
    w = dm.frequency_weights(wave)
    assert cold @ w == pytest.approx(1.0, rel=1e-3)
    assert warm @ w == pytest.approx(1.0, rel=1e-3)
    fir = wave > 3e5
    assert wave[fir][np.argmax(warm[fir])] < wave[fir][np.argmax(cold[fir])]


def _metal_cone(path, alist, enriched):
    """Two galaxies at snapshot 7 whose stars total Z = 0.01; `enriched`
    gives their older bins Z = 0.002 and their later ones 0.018."""
    import h5py

    n_bins = 8
    sfh = np.full((2, n_bins), 0.1)
    z_bin = np.full(n_bins, 0.01)
    if enriched:
        z_bin = np.r_[np.full(4, 0.002), np.full(4, 0.018)]
    with h5py.File(path, "w") as f:
        f["StellarMass"] = sfh.sum(1).astype(np.float32)
        f["MetalsStellarMass"] = (0.01 * sfh.sum(1)).astype(np.float32)
        f["SFHMassDisk"] = sfh.astype(np.float32)
        f["SFHMassBulge"] = np.zeros_like(sfh, dtype=np.float32)
        f["MHMetalsDisk"] = (sfh * z_bin).astype(np.float32)
        f["MHMetalsBulge"] = np.zeros_like(sfh, dtype=np.float32)
        f["SnapNum"] = np.full(2, 7, dtype=np.int32)
        f["redshift_cosmological"] = np.full(2, 0.05)
        sim = f.create_group("SageOutputHeader/Simulation")
        sim.attrs["hubble_h"] = 0.7
        sim.attrs["omega_matter"] = 0.3
        sim.attrs["omega_lambda"] = 0.7
        sim.attrs["FileWithSnapList"] = str(alist)


@pytest.mark.slow
def test_metal_history_gives_each_bin_its_metallicity(tmp_path):
    from visage.sed.photometry import compute_photometry

    alist = tmp_path / "a.list"
    np.savetxt(alist, np.linspace(0.1, 1.0, 8))
    flat, rising = tmp_path / "flat.h5", tmp_path / "rising.h5"
    _metal_cone(flat, alist, False)
    _metal_cone(rising, alist, True)
    bands = ("sdss_g", "sdss_r")

    def run(path, **kw):
        return compute_photometry(path, bands=bands, frame="rest", **kw)

    # A flat history is the one metallicity it's the same as...
    a, b = run(flat), run(flat, metal_history=False)
    assert "per SFH bin" in a["_settings"]["Metallicity"]
    assert "present-day" in b["_settings"]["Metallicity"]
    np.testing.assert_allclose(
        a["mag_rest_sdss_r"], b["mag_rest_sdss_r"], atol=1e-4
    )
    # ...and the same total metals spread over time isn't.
    c = run(rising)
    assert abs(c["mag_rest_sdss_g"][0] - a["mag_rest_sdss_g"][0]) > 0.005


def test_ism_screen_follows_trayford():
    from visage.sed import dust as dm

    tau, eta = dm.tau_eta_ism(np.array([10**5.0576, 10**6.47, 10**4.0]))
    assert tau[0] == pytest.approx(0.149, abs=0.01)
    assert tau[1] == pytest.approx(1.03, abs=0.01)
    assert 0 < tau[2] < 0.03  # thinner than the table: scales down
    assert np.all(eta < 0)


def test_birth_clouds_of_a_milky_way_like_disk():
    from visage.sed import dust as dm

    t = dm.tau_bc(0.33 * 0.0189, 1e9, 4.0, 0.1)
    assert t == pytest.approx(1.0)  # Sigma_cl = 85: tau_BC,0
    assert dm.tau_bc(0.33 * 0.0189, 1e9, 4.0, 2.0) == 2.0
    assert dm.tau_bc(0.33 * 0.0189, 1e11, 2.0, 0.1) > 1.0  # dense ISM
    assert dm.tau_bc(0.2, 1e11, 1.0, 0.1) == dm.TAU_BC_MAX


def test_edge_on_disks_show_more_dust():
    from visage.sed import dust as dm

    face, edge = dm.sigma_dust(1e7, 4.0, np.array([1.0, 0.0]))
    assert edge == pytest.approx(7.3 * face)
