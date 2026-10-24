"""Tests for the emission-line pieces of visage.sed that don't need FSPS:
the HII-region ionisation parameter and the AGN narrow-line region."""

from __future__ import annotations

import numpy as np

from visage.sed import agn
from visage.sed import nebular as nb


def test_kashino_inoue_logu():
    # Their eq. 5 at their eq. 3's density, by hand.
    z, ssfr, m = 0.0142, 1e-10, 1e10
    log_ne = (-10 + 12.661) / 1.753
    want = -2.316 - 0.360 * (8.69 - 12 + 4) - 0.292 * log_ne - 0.428
    got = nb.kashino_inoue_logu(np.array([z]), np.array([ssfr]), np.array([m]))
    np.testing.assert_allclose(got[0], want, atol=1e-9)
    # More star formation per unit mass: more highly ionised; metal-rich
    # gas: less.
    u = nb.kashino_inoue_logu(
        np.array([z, z, 2 * z]), np.array([1e-10, 1e-9, 1e-10]), np.full(3, m)
    )
    assert u[1] > u[0] > u[2]
    # Clipped to the line table.
    u = nb.kashino_inoue_logu(
        np.array([1e-6]), np.array([1e-6]), np.array([1e6])
    )
    assert nb.GAS_LOGU_NODES[0] <= u[0] <= nb.GAS_LOGU_NODES[-1]


def test_agn_grid_and_photons():
    z_nodes, u_nodes, table, names = agn.grid()
    assert names == list(nb.LINES)
    assert table.shape == (len(z_nodes), len(u_nodes), len(nb.LINES))
    assert (table > 0).all()
    # Ionising photons per erg for the alpha = -1.7 spectrum, checked
    # against the grid itself: H-beta at low U (little dust inside the
    # cloud) is close to case B, 4.76e-13 erg per ionising photon.
    q = agn.ionising_photons_per_erg() * agn.L_GRID
    i = list(z_nodes).index(0.014)
    hb = table[i, 0, names.index("Hbeta")]
    assert 0.7 < hb / (4.76e-13 * q) < 1.05


def test_agn_luminosity():
    bh = np.array([1e8, 1e8, 1e8, 0.0])
    l_edd = 1.3e38 * 1e8
    # Thin disc above 1% Eddington: L = 0.1 Mdot c^2.
    mdot_10pc = 0.1 * l_edd / (0.1 * 2.99792458e10**2) * 3.15576e7 / 1.98847e33
    lum, lam = agn.luminosity(
        bh,
        np.array([mdot_10pc, 0.0, 0.0, 1.0]),
        np.array([0.0, 0.0, 0.0, 0.0]),
    )
    np.testing.assert_allclose(lam[0], 0.1, rtol=1e-6)
    np.testing.assert_allclose(lum[0], 0.1 * l_edd, rtol=1e-6)
    assert lum[1] == 0 and lum[3] == 0  # nothing accreting / no black hole
    # Radio mode at 1e-3 Eddington: inefficient, L/L_Edd = 1e-6 / 0.01.
    heat = np.log10(1e-3 * l_edd)
    lum, lam = agn.luminosity(bh[:1], np.zeros(1), np.array([heat]))
    np.testing.assert_allclose(lam[0], 1e-4, rtol=1e-6)


def test_agn_lines_scale():
    n_c = agn.central_gas_density(np.array([1e10]), np.array([3.0]))
    assert 0.1 < n_c[0] < 100  # cm^-3, averaged over 1 kpc
    # U_S grows as L^(1/3).
    u = agn.log_u(np.array([1e42, 1e45]), np.array([n_c[0], n_c[0]]))
    np.testing.assert_allclose(u[1] - u[0], 1.0, atol=1e-9)
    # Line luminosities are linear in L at fixed Z and U.
    lines = agn.line_luminosities(
        np.array([1e43, 1e44]), np.array([0.014, 0.014]), np.array([-3, -3])
    )
    np.testing.assert_allclose(lines[1] / lines[0], 10.0, rtol=1e-9)
    # A Seyfert-like ratio: [OIII]/H-beta high at high U.
    names = list(nb.LINES)
    seyfert = agn.line_luminosities(
        np.array([1e45]), np.array([0.02]), np.array([-2.0])
    )[0]
    assert seyfert[names.index("OIII5007")] / seyfert[names.index("Hbeta")] > 5
