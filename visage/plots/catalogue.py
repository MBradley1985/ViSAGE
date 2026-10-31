"""Galaxies for a plot: a snapshot, or part of one, in physical units.

Masses are M_sun and SFRs M_sun/yr; radii stay as the model writes them
(Mpc/h).  A Sample has a volume in Mpc^3, or None when a selection has none
that means anything (a group), and mass functions are then plain counts.
"""

from __future__ import annotations

import h5py
import numpy as np

from visage.io.sage_files import galaxy_files, open_snapshot

MASS_FIELDS = {
    "StellarMass",
    "BulgeMass",
    "MergerBulgeMass",
    "InstabilityBulgeMass",
    "BlackHoleMass",
    "ColdGas",
    "H1gas",
    "H2gas",
    "HotGas",
    "CGMgas",
    "EjectedMass",
    "IntraClusterStars",
    "Mvir",
    "CentralMvir",
    "MetalsColdGas",
    "MetalsStellarMass",
    "MetalsBulgeMass",
    "MetalsHotGas",
    "MetalsEjectedMass",
    "MetalsCGMgas",
    "ColdDust",
    "HotDust",
    "CGMDust",
    "EjectedDust",
    "DiscDust",
    "DiscGas",
    "DiscGasMetals",
    "DiscStars",
    "DiscHI",
    "DiscH2",
}


class Sample:
    """The chosen galaxies of one snapshot, or of one slice of a cone."""

    def __init__(self, read, rows, hubble_h, redshift, volume) -> None:
        self._read = read
        self.rows = rows
        self.h = hubble_h
        self.z = redshift
        self.volume = volume

    def __len__(self) -> int:
        return len(self.rows)

    def has(self, name: str) -> bool:
        try:
            self._read(name)
        except KeyError:
            return False
        return True

    def __call__(self, name: str) -> np.ndarray:
        if name == "SFR":
            return self("SfrDisk") + self("SfrBulge")
        if name == "sSFR":
            mass = self("StellarMass")
            return np.divide(
                self("SFR"),
                mass,
                out=np.zeros(len(mass)),
                where=mass > 0,
            )
        values = self._read(name)[self.rows]
        return values * 1.0e10 / self.h if name in MASS_FIELDS else values


def box_reader(path, snap: int):
    """A cached reader of one snapshot's fields."""
    cache: dict = {}

    def read(name: str) -> np.ndarray:
        if name not in cache:
            with open_snapshot(path, snap) as group:
                cache[name] = np.asarray(group[name])
        return cache[name]

    return read


def cone_reader(path):
    """A cached reader of a lightcone's columns, by any case of name."""
    cache: dict = {}
    with h5py.File(path, "r") as f:
        names = {k.lower(): k for k in f.keys()}

    def read(name: str) -> np.ndarray:
        key = names[name.lower()]
        if key not in cache:
            with h5py.File(path, "r") as f:
                cache[key] = np.asarray(f[key])
        return cache[key]

    return read


def box_volume(path, box_size: float, hubble_h: float) -> float:
    """The simulated volume in Mpc^3, for the share of it this run did."""
    share = 0.0
    for name in galaxy_files(path):
        with h5py.File(name, "r") as f:
            run = f.get("Header/Runtime")
            share += float(
                run.attrs.get("frac_volume_processed", 0.0) if run else 0.0
            )
    return (box_size / hubble_h) ** 3 * (share or 1.0)


def comoving_mpc(z, hubble_h: float, omega_m: float, omega_l: float):
    """Comoving distance to redshift `z`, in Mpc."""
    grid = np.linspace(0.0, max(float(np.max(z)), 1e-6), 4000)
    e = np.sqrt(omega_m * (1 + grid) ** 3 + omega_l)
    chi = np.concatenate(
        ([0.0], np.cumsum(0.5 * (1 / e[1:] + 1 / e[:-1]) * np.diff(grid)))
    )
    return np.interp(z, grid, chi) * 2997.92458 / hubble_h


def cone_area(ra: np.ndarray, dec: np.ndarray) -> float:
    """Solid angle of a cone's RA/Dec rectangle, in steradians."""
    d_ra = np.radians(float(ra.max() - ra.min()))
    lo, hi = np.radians(float(dec.min())), np.radians(float(dec.max()))
    return d_ra * (np.sin(hi) - np.sin(lo))


def shell_volume(area, z_lo, z_hi, h, omega_m, omega_l) -> float:
    """Volume of a cone between two redshifts, in Mpc^3."""
    lo, hi = comoving_mpc(np.array([z_lo, z_hi]), h, omega_m, omega_l)
    return float(area / 3.0 * (hi**3 - lo**3))
