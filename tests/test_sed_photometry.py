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
        path, bands=("sdss_g", "sdss_r"), frame="both", n_zbins=1
    )
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
