"""HD and the selection card in a lightcone, with every combination of
synthetic photometry and dust a cone can have (none at all, magnitudes
only, each dust model, missing or NaN values, stale dust columns from an
earlier run), and FOF groups repeated across the cone's box tiles."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from visage.hd.adapter import prefetch_sfh, sage_galaxy_from_snapshot
from visage.hd.layer import HDGalaxyLayer
from visage.hd.model import DUST_K, SED_DUST_K, recipe_from_sage
from visage.io.lightcone_reader import load_lightcone_snapshot
from visage.scene.lightcone_model import _SyntheticSnapTable
from visage.utils.galaxy_info import build_galaxy_info, cone_summary
from visage.utils.group_info import member_indices

H = 0.7
N_SNAP = 10
SNAP_Z = np.linspace(9.0, 0.0, N_SNAP)
# A group (central 11, satellites 12, 13), its copy in the next box tile
# 100 Mpc/h on, satellite 12 again from the neighbouring snapshot shell
# (a shell-boundary duplicate), and a lone galaxy.
GID = np.array([11, 12, 13, 11, 12, 13, 12, 21])
CID = np.array([11, 11, 11, 11, 11, 11, 11, 21])
TYPE = np.array([0, 1, 1, 0, 1, 1, 1, 0])
SNAP = np.array([8, 8, 8, 6, 6, 6, 9, 8])
POS = np.array(
    [
        [50.0, 1.0, 1.0],
        [50.2, 1.0, 1.0],
        [49.9, 1.1, 1.0],
        [150.0, 1.0, 1.0],
        [150.2, 1.0, 1.0],
        [149.9, 1.1, 1.0],
        [50.21, 1.0, 1.0],
        [80.0, 5.0, 2.0],
    ]
)


def _cone(path, phot=None, mags=("sdss_g", "sdss_r", "sdss_i"), dust=True):
    """phot: the PhotometryHeader "Dust" value (None: no header);
    dust: write the Charlot & Fall columns; mags: bands written."""
    n = len(GID)
    rng = np.random.default_rng(0)
    with h5py.File(path, "w") as f:
        for k, c in enumerate("xyz"):
            f[f"Pos{c}"] = POS[:, k].astype(np.float32)
            f[f"Spin{c}"] = rng.normal(size=n).astype(np.float32)
        f["StellarMass"] = np.full(n, 3.0, np.float32)
        f["BulgeMass"] = np.full(n, 0.3, np.float32)
        f["ColdGas"] = np.full(n, 1.0, np.float32)
        f["H1gas"] = np.full(n, 0.6, np.float32)
        f["H2gas"] = np.full(n, 0.3, np.float32)
        f["MetalsColdGas"] = np.full(n, 0.01, np.float32)
        f["MetalsStellarMass"] = np.full(n, 0.05, np.float32)
        f["SfrDisk"] = np.full(n, 1.0, np.float32)
        f["DiskRadius"] = np.full(n, 0.004, np.float32)
        f["Mvir"] = np.full(n, 100.0, np.float32)
        f["Rvir"] = np.full(n, 0.2, np.float32)
        f["Type"] = TYPE.astype(np.int32)
        f["GalaxyIndex"] = GID.astype(np.int64)
        f["CentralGalaxyIndex"] = CID.astype(np.int64)
        f["SnapNum"] = SNAP.astype(np.int32)
        f["redshift_cosmological"] = SNAP_Z[SNAP]
        f["redshift_observed"] = SNAP_Z[SNAP] + 1e-4
        f["distance"] = np.linalg.norm(POS, axis=1)
        sfh = np.zeros((n, N_SNAP))
        sfh[:, 2:8] = 0.5
        f["SFHMassDisk"] = sfh
        f["SFHMassBulge"] = sfh * 0.1
        hdr = f.create_group("SageOutputHeader")
        hdr["snapshot_redshifts"] = SNAP_Z
        sim = hdr.create_group("Simulation")
        sim.attrs["hubble_h"] = H
        sim.attrs["omega_matter"] = 0.3
        for b in mags:
            for frame, base in (("obs", 18.0), ("rest", -20.0)):
                v = np.full(n, base, np.float32)
                v += {"g": 0.6, "r": 0.0, "i": -0.3}.get(b[-1], 0.0)
                f[f"mag_{frame}_{b}"] = v
        if dust:
            f["TauV_ISM"] = np.full(n, 0.8, np.float32)
            f["CosInclination"] = np.full(n, 0.5, np.float32)
            f["DustMassCold"] = np.full(n, 1e7, np.float32)
        if phot is not None:
            f.create_group("PhotometryHeader").attrs["Dust"] = phot


def _load(path):
    lc = load_lightcone_snapshot(path)
    st = _SyntheticSnapTable(lc.snapnum, lc.redshift, lc.snap_redshifts)
    return lc, st


def _gal(lc, st, i=0):
    g = lc.galaxies
    prefetch_sfh(g, [i], st, H, 0.3)
    return sage_galaxy_from_snapshot(g, i, H, st, 0.3)


CASES = {
    "no photometry": dict(phot=None, mags=(), dust=False),
    "mags, no header": dict(phot=None, dust=False),
    "dust none": dict(phot="none", dust=False),
    "stale dust columns": dict(phot="none", dust=True),
    "calzetti": dict(phot="Calzetti 2000, tau_V=0.3", dust=False),
    "charlot_fall": dict(phot="Charlot & Fall 2000 birth clouds", dust=True),
    "charlot_fall, no columns": dict(
        phot="Charlot & Fall 2000 birth clouds", dust=False
    ),
    "charlot_fall, IR bands only": dict(
        phot="Charlot & Fall 2000 birth clouds",
        mags=("2mass_j", "2mass_ks"),
        dust=True,
    ),
}


@pytest.mark.parametrize("case", list(CASES))
def test_hd_and_card_any_photometry(tmp_path, case):
    path = tmp_path / "cone.h5"
    _cone(path, **CASES[case])
    lc, st = _load(path)
    gal = _gal(lc, st)
    # Its own redshift and SFH, not snapshot 0's.
    assert gal.redshift == pytest.approx(SNAP_Z[8])
    assert gal.sfh_disk and sum(gal.sfh_disk) > 0
    assert gal.los and np.isclose(np.linalg.norm(gal.los), 1.0)

    rc = recipe_from_sage(gal)
    how = lc.galaxies.sed_dust()[0]
    has_gri = "mag_obs_sdss_r" in lc.galaxies.sed_mags
    if how == "charlot_fall" and "TauV_ISM" in lc.galaxies.extra:
        assert gal.tau_v_ism == pytest.approx(0.8)
        assert rc.dust_k == pytest.approx(tuple(SED_DUST_K))
    else:
        # HD's own dust (no photometry, a Calzetti screen, or photometry
        # made without dust).
        assert gal.tau_v_ism == -1.0
        assert rc.dust_k == pytest.approx(tuple(DUST_K))
    assert bool(gal.sed_ratio) == has_gri

    prep = HDGalaxyLayer.prepare(gal, "lite", {"spin": None})
    gain = np.asarray(prep["rc"].col_gain)
    assert np.all(np.isfinite(gain)) and np.all(gain > 0)
    if not has_gri:
        assert gain == pytest.approx(1.0)

    rows = dict(cone_summary(lc.galaxies, 0))
    assert "Redshift" in rows and "Distance" in rows
    assert ("r (apparent)" in rows) == has_gri
    if how is None:
        assert "A_V (dust)" not in rows
    info = build_galaxy_info(lc.galaxies, {"central_id": True}, 0, st, H)
    assert info["Approx Age"].endswith("Gyr")
    if how != "charlot_fall":
        # (Dust columns left by another run aren't this photometry's.)
        assert "Dust mass (cold ISM)" not in info


def test_zero_photometry_dust_draws_none(tmp_path):
    """A galaxy whose own (Charlot & Fall) dust is zero has none in HD."""
    path = tmp_path / "cone.h5"
    _cone(path, phot="Charlot & Fall 2000 birth clouds")
    with h5py.File(path, "a") as f:
        f["TauV_ISM"][0] = 0.0
    lc, st = _load(path)
    gal = _gal(lc, st)
    rc = recipe_from_sage(gal)
    assert rc.tau0 == 0.0 and rc.lane == 0.0
    prep = HDGalaxyLayer.prepare(gal, "lite")
    assert float(prep["maps"].dust.max()) == 0.0


def test_hd_with_nan_photometry(tmp_path):
    path = tmp_path / "cone.h5"
    _cone(path, phot="Charlot & Fall 2000 birth clouds")
    with h5py.File(path, "a") as f:
        f["TauV_ISM"][0] = np.nan
        f["mag_obs_sdss_g"][0] = np.nan
    lc, st = _load(path)
    gal = _gal(lc, st)
    assert gal.tau_v_ism == -1.0 and gal.sed_ratio == ()
    prep = HDGalaxyLayer.prepare(gal, "lite")
    assert prep["rc"].col_gain == (1.0, 1.0, 1.0)
    cone_summary(lc.galaxies, 0)


def test_cone_groups_one_copy_per_tile(tmp_path):
    path = tmp_path / "cone.h5"
    _cone(path, phot=None, mags=(), dust=False)
    lc, _ = _load(path)
    g = lc.galaxies
    # The group around the first copy: its central and two satellites,
    # not the copy 100 Mpc/h away, and satellite 12 once (this shell's).
    assert list(member_indices(g, 2)) == [0, 1, 2]
    assert list(member_indices(g, 4)) == [3, 4, 5]
    # Selected from the other shell: that copy of 12 is the one kept.
    assert list(member_indices(g, 6)) == [0, 2, 6]
    assert list(member_indices(g, 7)) == [7]


def test_hd_on_a_bare_cone(tmp_path):
    """Positions, masses and types only: no SFH, spins, redshifts,
    photometry or SAGE header."""
    path = tmp_path / "bare.h5"
    n = 4
    with h5py.File(path, "w") as f:
        for k, c in enumerate("xyz"):
            f[f"Pos{c}"] = POS[:n, k].astype(np.float32)
        f["StellarMass"] = np.full(n, 2.0, np.float32)
        f["Mvir"] = np.full(n, 50.0, np.float32)
        f["Type"] = np.zeros(n, np.int32)
        f["SnapNum"] = np.full(n, 3, np.int32)
    lc, st = _load(path)
    gal = _gal(lc, st)
    assert gal.sfh_disk == () and gal.tau_v_ism == -1.0
    prep = HDGalaxyLayer.prepare(gal, "lite")
    assert prep["rc"].col_gain == (1.0, 1.0, 1.0)
    assert dict(cone_summary(lc.galaxies, 0))["Distance"]
    build_galaxy_info(lc.galaxies, {}, 0, st, H)


def _spiral(**kw):
    """A star-forming lightcone galaxy with component photometry."""
    from visage.hd.model import SageGalaxy

    base = dict(
        galaxy_index=7,
        stellar_mass=3e10,
        bulge_mass=6e9,
        merger_bulge_mass=0.0,
        instability_bulge_mass=0.0,
        cold_gas=8e9,
        h2_gas=2e9,
        h1_gas=6e9,
        metals_cold_gas=1.2e8,
        bh_mass=1e7,
        sfr_disk=2.0,
        sfr_bulge=0.0,
        disk_radius_kpc=4.0,
        bulge_radius_kpc=1.2,
        regime=0,
        gtype=0,
        tau_v_ism=0.4,
        los=(0.0, 0.0, 1.0),
        sed_ratio=(1.3, 0.7),
        sed_disk=(1.2, 0.75),
        sed_bulge=(1.5, 0.45),
        bulge_share=0.3,
        agn_share=0.5,
        ha_share=0.02,
    )
    return SageGalaxy(**(base | kw))


def test_lightcone_galaxy_has_sage26_radii():
    from visage.hd.model import display_sizes

    assert display_sizes(_spiral(disk_radius_kpc=9.0))[0] == 9.0


def test_box_galaxy_keeps_the_display_sizes():
    from visage.hd.model import display_sizes

    assert display_sizes(_spiral(disk_radius_kpc=9.0, los=()))[0] != 9


def test_closure_sets_the_components_to_the_photometry():
    from visage.hd.layer import observer_rotation, photometry_closure
    from visage.hd.model import build_disk_maps, build_points, recipe_from_sage
    from visage.hd.raymarch import render

    g = _spiral()
    rc = recipe_from_sage(g)
    maps = build_disk_maps(rc, n=256)
    rc, pts = photometry_closure(rc, maps, build_points(rc, maps), g, None)
    R = observer_rotation(g.los, None, rc.seed)
    lay = render(rc, maps, pts, R=R, npix=96, threads=1)
    disk = (lay.disk + lay.young)[..., 1].sum()
    bulge = lay.bulge[..., 1].sum()
    host = disk + bulge
    assert bulge / host == pytest.approx(0.3, rel=0.2)
    assert lay.points["agn"][..., 1].sum() / host == pytest.approx(
        0.5, rel=0.2
    )
    assert lay.points["hii"][..., 1].sum() / host == pytest.approx(
        0.02, rel=0.3
    )


def test_hidden_agn_is_not_drawn():
    from visage.hd.model import recipe_from_sage

    assert recipe_from_sage(_spiral(agn_share=0.0)).agn == 0
