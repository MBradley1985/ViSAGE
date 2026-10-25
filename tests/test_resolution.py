"""Mass cuts from the simulation's resolution (visage.utils.resolution)."""

from __future__ import annotations

import argparse

import h5py
import numpy as np

from visage.utils import resolution


def _population(rng, n=20000, mp=1.0):
    """Centrals with M* ~ M_halo^1.5 and scatter: haloes of `mp` units."""
    lmh = rng.uniform(0.0, 4.0, n)  # log10 halo mass in particle masses
    lms = 6.0 + 1.5 * lmh + rng.normal(0, 0.2, n)
    return 10**lms, 10**lmh / mp


def test_resolved_stellar_mass_follows_particles():
    rng = np.random.default_rng(0)
    sm, npart = _population(rng)
    cen = np.ones(len(sm), bool)
    cuts = [
        resolution.resolved_stellar_mass(sm, npart, cen, n)
        for n in (20, 50, 100)
    ]
    assert all(c is not None for c in cuts)
    assert cuts[0] < cuts[1] < cuts[2]
    # 90% of centrals from the cut up are resolved.
    for n, c in zip((20, 50, 100), cuts, strict=True):
        assert np.mean(npart[sm >= c] >= n) > 0.9


def test_resolved_stellar_mass_too_few():
    assert (
        resolution.resolved_stellar_mass(
            np.array([1e9, 2e9]), np.array([100, 100]), np.ones(2, bool), 20
        )
        is None
    )
    assert (
        resolution.resolved_stellar_mass(
            np.array([]), np.array([]), np.zeros(0, bool), 20
        )
        is None
    )


def test_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(resolution, "_SETTINGS", tmp_path / "s.json")
    assert resolution.particles("box") == resolution.DEFAULT_PARTICLES
    resolution.set_particles("cone", 100)
    assert resolution.particles("cone") == 100
    assert resolution.particles("box") == resolution.DEFAULT_PARTICLES


def test_cli_cuts(tmp_path, monkeypatch):
    from visage.cli import _mass_cuts

    monkeypatch.setattr(resolution, "_SETTINGS", tmp_path / "s.json")
    ns = argparse.Namespace
    by_res = _mass_cuts(
        ns(min_particles=None, min_stellar_mass=None, min_halo_mass=None),
        "box",
    )
    assert by_res["min_particles"] == 20 and by_res["min_stellar_mass"] == 0
    fixed = _mass_cuts(
        ns(min_particles=None, min_stellar_mass=1e9, min_halo_mass=None),
        "box",
    )
    assert fixed["min_particles"] is None
    assert fixed["min_stellar_mass"] == 1e9


def test_lightcone_cut_per_shell(tmp_path):
    """Each snapshot shell is cut where its own haloes are resolved."""
    from visage.io.lightcone_reader import load_lightcone_snapshot

    rng = np.random.default_rng(1)
    n = 8000
    snap = np.repeat([5, 9], n // 2)
    lmh = rng.uniform(0.0, 4.0, n)
    # The earlier shell: less stellar mass per halo.
    lms = np.where(snap == 5, 5.5, 6.0) + 1.5 * lmh + rng.normal(0, 0.2, n)
    mp = 0.01  # 10^10 Msun/h
    h = 0.7
    path = tmp_path / "cone.h5"
    with h5py.File(path, "w") as f:
        for c in "xyz":
            f[f"Pos{c}"] = rng.uniform(0, 50, n).astype(np.float32)
        f["StellarMass"] = (10**lms * h / 1e10).astype(np.float32)
        f["Mvir"] = (10**lmh * mp).astype(np.float32)
        f["Type"] = np.zeros(n, np.int32)
        f["SnapNum"] = snap.astype(np.int32)
        sim = f.create_group("SageOutputHeader").create_group("Simulation")
        sim.attrs["hubble_h"] = h
        sim.attrs["particle_mass"] = mp
    full = load_lightcone_snapshot(path)
    cut = load_lightcone_snapshot(path, min_particles=20)
    assert cut.count < full.count
    g = cut.galaxies
    lo = {s: g.stellar_mass[cut.snapnum == s].min() for s in (5, 9)}
    assert lo[5] < lo[9]  # its own, lower, cut
    # Haloes cut at 20 particle masses.
    assert cut.halos.masses.min() >= 20 * mp * 1e10 / h * 0.999
