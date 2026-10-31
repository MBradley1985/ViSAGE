"""The Plotting tab's catalogue, sums and plots, on made-up galaxies."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from visage.plots import catalogue as cat
from visage.plots import history, local, observed, style  # noqa: F401
from visage.plots.base import PLOTS, Options, Plot, density, log_edges
from visage.utils.filters import galaxy_mask

N = 4000


def fake_sample(volume=1.0e6):
    rng = np.random.default_rng(1)
    mass = 10 ** rng.uniform(-2.5, 1.5, N)
    data = {
        "StellarMass": mass,
        "BulgeMass": mass * rng.uniform(0, 1, N),
        "Type": rng.integers(0, 2, N),
        "SfrDisk": rng.uniform(0, 5, N),
        "SfrBulge": rng.uniform(0, 1, N),
        "Mvir": mass * 30,
        "CentralMvir": mass * 40,
        "Vmax": 10 ** rng.uniform(1.5, 2.8, N),
        "Vvir": 10 ** rng.uniform(1.5, 2.8, N),
        "Rvir": rng.uniform(0.05, 1, N),
        "DiskRadius": rng.uniform(1e-3, 0.02, N),
        "BulgeRadius": rng.uniform(1e-3, 0.02, N),
        "Concentration": rng.uniform(2, 20, N),
        "Regime": rng.integers(0, 2, N),
        "CentralGalaxyIndex": rng.integers(0, 500, N),
        "MassLoading": rng.uniform(0.1, 20, N),
        "CoolingRate": rng.uniform(0.1, 20, N),
        "mdot_cool": rng.uniform(1, 500, N),
        "mdot_stream": rng.uniform(1, 500, N),
        "Posx": rng.uniform(0, 60, N),
        "Posy": rng.uniform(0, 60, N),
        "Posz": rng.uniform(0, 60, N),
        "RcoolToRvir": rng.uniform(0, 2, N),
    }
    edges = np.cumsum(rng.uniform(1e-5, 1e-3, (N, 31)), axis=1)
    data["DiscRadii"] = edges
    data["StellarDiscHalfMassRadius"] = rng.uniform(1e-3, 0.01, N)
    data["GasDiscHalfMassRadius"] = rng.uniform(1e-3, 0.04, N)
    for name in ("DiscStars", "DiscHI", "DiscH2", "DiscDust", "DiscGas"):
        data[name] = rng.uniform(1e-4, 1e-2, (N, 30))
    data["DiscGasMetals"] = data["DiscGas"] * 0.02
    for name in ("ColdDust", "HotDust", "CGMDust", "EjectedDust"):
        data[name] = mass * rng.uniform(1e-4, 1e-2, N)
    for name in (
        "ColdGas", "H1gas", "H2gas", "HotGas", "CGMgas", "EjectedMass",
        "IntraClusterStars", "BlackHoleMass", "MergerBulgeMass",
        "InstabilityBulgeMass", "MetalsColdGas", "MetalsStellarMass",
    ):  # fmt: skip
        data[name] = mass * rng.uniform(0.01, 0.2, N)
    return cat.Sample(lambda k: data[k], np.arange(N), 0.7, 0.0, volume)


def test_masses_become_solar_and_ssfr_is_per_year():
    s = fake_sample()
    raw = s._read("StellarMass")
    assert s("StellarMass")[0] == pytest.approx(raw[0] * 1e10 / 0.7)
    assert s("sSFR")[0] == pytest.approx(s("SFR")[0] / s("StellarMass")[0])


def test_density_is_per_dex_and_volume_or_a_count_without_one():
    values = np.array([10.0**9.05] * 8)
    edges = log_edges(9.0, 9.2, 0.1)
    assert density(values, edges, 2.0)[1][0] == pytest.approx(40.0)
    assert density(values, edges, None)[1][0] == pytest.approx(80.0)


def test_a_full_sky_shell_is_a_sphere():
    chi = cat.comoving_mpc(np.array([0.5]), 0.7, 0.3, 0.7)[0]
    got = cat.shell_volume(4 * np.pi, 0.0, 0.5, 0.7, 0.3, 0.7)
    assert got == pytest.approx(4 / 3 * np.pi * chi**3)


def test_cone_area_of_the_whole_sky():
    area = cat.cone_area(np.array([0.0, 360.0]), np.array([-90.0, 90.0]))
    assert area == pytest.approx(4 * np.pi)


def test_scott13_has_every_galaxy():
    from visage.plots.obs import scott13

    assert all(len(v) == 75 for v in scott13(0.7).values())


LOCAL = [
    k for k, v in PLOTS.items() if v["kind"] == "local" and "box" in v["modes"]
]


@pytest.mark.parametrize("key", LOCAL)
def test_each_local_plot_draws(key, monkeypatch):
    monkeypatch.setattr(style.shutil, "which", lambda _: None)
    with style.context(False):
        fig = PLOTS[key]["fn"](Plot(fake_sample(), [], Options()))
    assert fig.axes


@pytest.mark.parametrize("key", ("smf", "bmf", "gmf"))
def test_mass_functions_are_counts_without_a_volume(key, monkeypatch):
    monkeypatch.setattr(style.shutil, "which", lambda _: None)
    with style.context(False):
        fig = PLOTS[key]["fn"](Plot(fake_sample(None), [], Options()))
    assert "N" in fig.axes[0].get_ylabel()


def test_only_clusters_when_only_clusters_are_ticked():
    mass = np.array([1e10, 1e12, 1e13, 1e15])
    gal = SimpleNamespace(
        count=4,
        stellar_mass=np.full(4, 1e10),
        central_mvir=mass,
        central_id=np.arange(4),
    )
    env = dict.fromkeys(
        (f"env_show_{k}" for k in ("field", "isolated", "pairs", "group")),
        False,
    )
    state = _Open(env_show_cluster=True, **env)
    mask = galaxy_mask(gal, {"central_mvir": True}, state)
    assert mask.tolist() == [False, False, False, True]


class _Open(SimpleNamespace):
    """Filter settings left at their full range."""

    def __getattr__(self, name):
        wide = (-1e9, 1e9)
        return wide if name.startswith("filter_") else []


def test_dust_observations():
    from visage.plots import obs

    # The break of Remy-Ruyer+14 joins up, and solar metals give G/D = 162.
    assert 1 / obs.dust_to_gas(8.69) == pytest.approx(162, rel=0.01)
    assert obs.dust_to_gas(8.09) == pytest.approx(
        obs.dust_to_gas(8.11), rel=0.1
    )
    # Beeston+18's knee: phi* ln10 / e at M*, h = 0.7.
    assert obs.dust_mf(np.array([4.65e7]), 0.7)[0] == pytest.approx(
        6.26e-3 * np.log(10) / np.e, rel=1e-6
    )


def test_a_run_without_dust_still_stacks_its_discs(monkeypatch):
    monkeypatch.setattr(style.shutil, "which", lambda _: None)
    s = fake_sample()
    read = s._read

    def no_dust(name):
        if name == "DiscDust":
            raise KeyError(name)
        return read(name)

    s._read = no_dust
    assert not s.has("DiscDust")
    with style.context(False):
        assert local.disc_profiles(Plot(s, [], Options())).axes
