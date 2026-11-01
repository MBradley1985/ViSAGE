"""DarkSAGE and DustySAGE output as a run ViSAGE reads."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from visage.io import family_binary as fb
from visage.io import sage_files

HEADER = """
#define N_BINS 3
struct GALAXY_OUTPUT
{
#ifdef MINIMIZE_IO
  short Type;
#else
  int   Type;
#endif
  long long GalaxyIndex;
  float Pos[3];
  float StellarMass;
  float DiskScaleRadius;
  float DiscGas[N_BINS];
  float DiscStars[N_BINS][N_BINS];
};
"""


def _run(tmp_path):
    (tmp_path / "h.h").write_text(HEADER)
    (tmp_path / "a.list").write_text("0.5\n1.0\n")
    out = tmp_path / "out"
    out.mkdir()
    (tmp_path / "x.par").write_text(
        f"OutputDir {out}/\nFileNameGalaxies model\nHubble_h 0.7\n"
        f"Omega 0.3\nOmegaLambda 0.7\nBoxLen 10\n"
        f"FileWithSnapList {tmp_path}/a.list ; comment\n-> 1\n"
    )
    dtype = fb.struct_dtype(tmp_path / "h.h")
    gals = np.zeros(2, dtype)
    gals["Pos"][:, 1] = (3, 4)
    gals["StellarMass"] = (1, 2)
    gals["DiskScaleRadius"] = 0.1
    with open(out / "model_z0.000_0", "wb") as f:
        np.array([1, 2, 2], np.int32).tofile(f)
        gals.tofile(f)
    return tmp_path


def test_struct_takes_the_compiled_branch_and_c_padding(tmp_path):
    (tmp_path / "h.h").write_text(HEADER)
    d = fb.struct_dtype(tmp_path / "h.h")
    assert d["Type"].itemsize == 4
    assert d.fields["GalaxyIndex"][1] == 8
    assert d["DiscStars"].shape == (3, 3)


def test_convert_writes_the_layout_viewer_reads(tmp_path):
    t = _run(tmp_path)
    path = fb.convert(t / "x.par", t / "h.h", "Test")
    with h5py.File(path) as f:
        g = f["Snap_1"]
        assert path.name == "model_0.hdf5"
        assert list(g["Posy"][:]) == [3, 4] and "DiskRadius" in g
        assert g.attrs["num_gals"] == 2
        assert f["Header/Simulation"].attrs["box_size"] == 10


def test_a_struct_that_does_not_fit_is_refused(tmp_path):
    t = _run(tmp_path)
    (t / "h.h").write_text(HEADER.replace("N_BINS 3", "N_BINS 4"))
    try:
        fb.convert(t / "x.par", t / "h.h", "Test")
    except ValueError as exc:
        assert "No output struct" in str(exc)
    else:
        raise AssertionError("should refuse")


def test_tested_parameter_files_ship_with_paths_to_fill():
    from visage.wizard.family import FAMILY, PARS

    for spec in FAMILY.values():
        text = (PARS / spec["par"]).read_text()
        assert (
            "@OUTPUT@" in text and "@TREES@" in text and "/Users" not in text
        )


def test_derived_fields_close_on_darksage_arrays():
    dtype = np.dtype(
        [
            (n, "f4", (2,))
            for n in (
                "DiscGas",
                "ClassicalBulgeMass",
                "SecularBulgeMass",
                "ClassicalMetalsBulgeMass",
                "SecularMetalsBulgeMass",
                "DiscSFR",
                "DiscH2",
                "DiscHI",
            )
        ]
        + [
            (n, "f4")
            for n in (
                "SfrMerge",
                "SfrInstab",
                "LastMajorMerger",
                "LastMinorMerger",
                "HalfMassRadiusMergerBulge",
                "HalfMassRadiusInstabilityBulge",
            )
        ]
    )
    g = np.zeros(1, dtype)
    g["ClassicalBulgeMass"], g["SecularBulgeMass"] = (1, 2), (3, 4)
    assert fb._derived(g)["BulgeMass"][0] == 10


def test_dusty_ratios_and_masses():
    dtype = np.dtype(
        [
            (n, "f4")
            for n in (
                "ColdGas",
                "ColdDust",
                "f_H2",
                "f_HI",
                "BulgeMass",
                "BulgeInstability",
            )
        ]
    )
    g = np.zeros(1, dtype)
    g["ColdGas"], g["ColdDust"] = 2.0, 0.02
    g["f_H2"], g["f_HI"] = 0.25, 0.25
    out = fb._derived(g)
    assert out["H2gas"][0] == 0.5
    assert np.isclose(out["DustToGas"][0], 0.01)
    assert out["H2Fraction"][0] == 0.5


def test_profile_conserves_the_annulus_mass(tmp_path):
    p = tmp_path / "m.hdf5"
    with h5py.File(p, "w") as f:
        g = f.create_group("Snap_1")
        g["DiscRadii"] = np.array([[0.0, 1e-3, 2e-3]])
        for k in ("DiscGas", "DiscHI", "DiscH2", "DiscStars", "DiscSFR"):
            g[k] = np.array([[1.0, 1.0]])
    out = fb.radial_profiles(p, 1, 0, 1.0)
    area = np.pi * np.array([1.0, 3.0]) * 1e6  # pc^2
    assert np.allclose(out["gas"][0] * area, 1e10)
    assert np.allclose(out["r"][0], [0.5, 1.5])


def test_profile_plots_with_or_without_the_newer_fields(tmp_path):
    p = tmp_path / "m.hdf5"
    with h5py.File(p, "w") as f:
        g = f.create_group("Snap_1")
        g["DiscRadii"] = np.array([[0.0, 1e-3, 2e-3]])
        for k in ("DiscGas", "DiscHI", "DiscH2", "DiscStars", "DiscSFR"):
            g[k] = np.array([[1.0, 1.0]])
    plain = fb.radial_profiles(p, 1, 0, 1.0)
    assert fb.plot_profile(plain, "1")[:4] == b"\x89PNG"
    assert "dust" not in plain
    with h5py.File(p, "a") as f:
        g = f["Snap_1"]
        g["DiscDust"] = np.array([[0.01, 0.01]])
        g["DiscGasMetals"] = np.array([[0.02, 0.01]])
        g["DiscStarsMetals"] = np.array([[0.02, 0.02]])
        g["DiscVcirc"] = np.array([[0.0, 200.0, 180.0]])
        g["VelDispStars"] = np.array([[30.0, 20.0]])
    full = fb.radial_profiles(p, 1, 0, 1.0)
    assert full["dust"][0] == pytest.approx(plain["gas"][0] * 0.01)
    assert full["z_gas"][0] == pytest.approx([0.02, 0.01])
    assert fb.plot_profile(full, "1")[:4] == b"\x89PNG"


def test_the_card_shows_a_runs_own_dust_and_hides_zeros():
    from types import SimpleNamespace

    from visage.utils.galaxy_info import dust_details

    extra = {
        "ColdDust": np.array([1e-3]),
        "HotDust": np.array([0.0]),
        "DustGrowthRate": np.array([1.2]),
    }
    gal = SimpleNamespace(
        extra=extra,
        cold_gas=np.array([1e9]),
        metals_cold_gas=np.array([2e7]),
    )
    d = dust_details(gal, 0, 1.0)
    assert d["Dust (cold)"] == "1.00e+07 Msun"
    assert "Dust (hot)" not in d
    assert d["Dust-to-gas"] == "1.00e-02"
    assert d["Dust-to-metals"] == "0.50"
    assert d["Dust grown"] == "1.2 Msun/yr"
    assert dust_details(SimpleNamespace(extra={}), 0, 1.0) == {}


def test_toomre_q_and_height_of_a_known_disc():
    from visage.hd.adapter import disc_height_kpc, toomre_q

    # A flat rotation curve: kappa = sqrt(2) v / r.
    prof = {
        "r": np.array([[4.0, 8.0]]),
        "vcirc": np.full((1, 3), 200.0),
        "sigma": np.array([[20.0, 20.0]]),
        "stars": np.array([[50.0, 50.0]]),
        "gas": np.array([[0.0, 0.0]]),
    }
    q = toomre_q(prof, 0.0)
    kappa = np.sqrt(2) * 200 / 4
    want = 20 * kappa / (3.36 * 4.30e-6 * 50e6)
    assert q[0] == pytest.approx(want, rel=1e-3)
    assert disc_height_kpc(prof, 4.0) == pytest.approx(
        400 / (np.pi * 4.30e-6 * 50e6)
    )


def test_stable_annuli_lose_their_arms():
    from types import SimpleNamespace

    from visage.hd.model import arm_reach

    rc = SimpleNamespace(
        radial=(
            (1.0, 2.0, 4.0),
            (), (), (), (), (),
            (0.8, 1.2, 4.0),
        )
    )  # fmt: skip
    assert arm_reach(rc, np.array([1.0]))[0] == pytest.approx(1.0)
    assert arm_reach(rc, np.array([4.0]))[0] == pytest.approx(0.0)
    assert 0 < arm_reach(rc, np.array([2.0]))[0] < 1
    assert arm_reach(SimpleNamespace(radial=()), np.ones(2)) == 1.0


def test_profiles_read_a_flat_lightcone(tmp_path):
    p = tmp_path / "cone.h5"
    with h5py.File(p, "w") as f:
        f["StellarMass"] = np.array([1.0, 1.0])
        f["DiscRadii"] = np.array([[0.0, 1e-3, 2e-3]] * 2)
        for k in ("DiscGas", "DiscHI", "DiscH2", "DiscStars", "DiscSFR"):
            f[k] = np.array([[1.0, 1.0]] * 2)
    out = fb.radial_profiles(p, 0, 1, 1.0)
    assert np.allclose(out["r"][0], [0.5, 1.5])


def test_hi_glow_follows_the_annuli():
    from visage.hd.layer import hi_texture

    radial = ((1.0, 2.0, 4.0, 8.0), (), (0.0, 0.0, 5.0, 0.0))
    img, half = hi_texture(radial, n=64)
    assert half == pytest.approx(1.15 * 4.0)
    a = img[..., 3].astype(float)
    assert a[32, 32] == 0  # a hole where the gas is molecular
    assert a[32, 32 + 28] > 0
    assert a[0, 0] == 0  # nothing beyond the disc
    assert hi_texture(((1.0, 2.0, 3.0), (), (0.0, 0.0, 0.0)))[0] is None


def test_hi_glow_is_round_even_where_annuli_end_above_its_threshold():
    from visage.hd.layer import hi_texture

    r = (0.1, 1.0, 5.0, 9.0)
    img, half = hi_texture((r, (), (50.0, 20.0, 5.0, 2.0)), n=64)
    assert img[0, 0, 3] == 0 and img[0, 32, 3] == 0
    assert img[32, 32, 3] > 0


def test_rotation_map_flips_counter_rotating_gas(tmp_path):
    prof = {
        "r": np.array([[1.0, 3.0, 6.0]]),
        "edges": np.array([[0.0, 2.0, 4.0, 8.0]]),
        "vcirc": np.array([[0.0, 150.0, 200.0, 200.0]]),
        "stars": np.array([[100.0, 10.0, 1.0]]),
        "gas": np.array([[1.0, 5.0, 5.0]]),
        "spin_dot": np.array([-0.99]),
    }
    assert fb.plot_rotation(prof, "1")[:4] == b"\x89PNG"
    assert fb.plot_rotation(prof, "1", dark=True)[:4] == b"\x89PNG"
    prof["gas"] = np.zeros((1, 3))
    assert fb.plot_rotation(prof, "1")[:4] == b"\x89PNG"


def test_a_spike_in_the_innermost_annulus_is_not_drawn():
    from types import SimpleNamespace

    from visage.hd.model import radial_scale

    edge = (0.01, 0.2, 0.5, 1.0, 2.0)
    flat = (1.0, 1.0, 1.0, 1.0, 1.0)
    spike = (1e5, 1.0, 1.0, 1.0, 1.0)
    r = np.linspace(0.02, 3, 300)
    base = np.ones_like(r)

    def drawn(v):
        return radial_scale(SimpleNamespace(radial=(edge, v)), 1, r, base)

    np.testing.assert_allclose(drawn(spike), drawn(flat))


def test_other_models_have_no_radial_scale():
    from types import SimpleNamespace

    from visage.hd.model import radial_scale

    rc = SimpleNamespace(radial=())
    assert radial_scale(rc, 1, np.ones(3), np.ones(3)) == 1.0


@pytest.mark.parametrize("model", ["DarkSAGE", "DustySAGE"])
def test_lightsage_refuses_family_output(tmp_path, model):
    with h5py.File(tmp_path / "model_0.hdf5", "w") as f:
        f.create_group("Header/Misc").attrs["sage_version"] = model
    with pytest.raises(SystemExit, match=model):
        sage_files.main([str(tmp_path)])


def test_lightsage_takes_sage26_output(tmp_path):
    with h5py.File(tmp_path / "model_0.hdf5", "w") as f:
        f.create_group("Header/Misc").attrs["sage_version"] = "SAGE26"
    sage_files.main([str(tmp_path)])
