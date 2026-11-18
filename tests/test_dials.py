"""The Filters dials' property table (visage/utils/dials.py)."""

from types import SimpleNamespace

import numpy as np

from visage.utils import dials


def _data(n=500, seed=0):
    rng = np.random.default_rng(seed)
    halos = SimpleNamespace(
        count=n,
        masses=10 ** rng.normal(12.0, 0.5, n),
        rvir=rng.uniform(0.05, 0.5, n),
        vvir=rng.uniform(80, 400, n),
        vmax=rng.uniform(80, 500, n),
    )
    sm = 10 ** rng.normal(10.0, 0.6, n)
    gals = SimpleNamespace(
        count=n,
        stellar_mass=sm,
        sfr=10 ** rng.normal(0.0, 0.5, n),
        ssfr=10 ** rng.normal(-10.0, 0.5, n),
        cold_gas=10 ** rng.normal(9.5, 0.5, n),
        bulge_mass=sm * rng.uniform(0, 1, n),
        sfr_bulge_z=rng.uniform(0.005, 0.03, n),
        extra={"Foo": 10 ** rng.normal(-1.0, 0.3, n)},
    )
    return halos, gals


def test_items_only_what_the_model_has():
    halos, gals = _data()
    out = dials.items(halos, gals, {"vmax": True})
    keys = {d["key"] for side in out.values() for d in side}
    assert "filter_gal_smass" in keys and "filter_halo_vmax" in keys
    # (No BH masses in this model: no BH dial.)
    assert "filter_gal_bhmass" not in keys


def test_ring_spans_the_data_inside_the_filter_range():
    halos, gals = _data()
    sm = next(
        d
        for d in dials.items(halos, gals, {})["gal"]
        if d["key"] == "filter_gal_smass"
    )
    assert len(sm["hist"]) == dials.NBINS
    assert sm["min"] <= sm["lo"] < sm["hi"] <= sm["max"]
    # Log-normal about 10^10: the ring is roughly 8 to 12, not 0 to 14.
    assert 7.5 < sm["lo"] < 9.0 and 11.0 < sm["hi"] < 12.5
    assert sm["log"] and sm["unit"] == "Msun"


def test_metallicity_in_solar_units():
    halos, gals = _data()
    z = next(
        d
        for d in dials.items(halos, gals, {"sfr_bulge_z": True})["gal"]
        if d["key"] == "filter_gal_sfr_blg_z"
    )
    assert z["unit"] == "Zsun"
    assert np.isclose(z["shift"], -np.log10(dials.Z_SUN))


def test_found_property_raw_mass_unit_folds_into_exponent():
    halos, gals = _data()
    spec = {
        "key": "Foo",
        "label": "Foo mass (log10 10^10 Msun h^-1)",
        "log": True,
        "min": -3.0,
        "max": 1.0,
        "step": 0.04,
    }
    foo = dials.items(halos, gals, {}, extra_gal=[spec])["gal"]
    foo = next(d for d in foo if d["key"] == "extra_gal_filter_0")
    assert foo["title"] == "Foo mass" and foo["unit"] == "Msun h^-1"
    assert foo["shift"] == 10.0
