"""What a galaxy survey would catalogue from a lightcone with photometry.

The magnitudes in a cone are each galaxy's total light. A survey measures
less, in apertures, so here each galaxy's disk and bulge (exponential and
de Vaucouleurs, sizes and magnitudes from the cone) are measured as SDSS
measures them (Blanton et al. 2001, AJ 121, 2358; Strauss et al. 2002, AJ
124, 1810), on circular profiles of each component's circularised radius,
blurred by the seeing:

  Petrosian   r_P where the surface brightness in 0.8-1.25 r_P is 0.2 of
              the mean inside r_P; the flux is that inside 2 r_P, about
              99% of an exponential and 80% of a de Vaucouleurs profile
  r50, mu50   radius holding half that flux, and the mean surface
              brightness inside it
  fibre       the flux inside the 3" diameter of an SDSS fibre (or a
              survey's own), so a nearby galaxy's spectrum sees its centre

Apertures are set in the detection band and used in every band. Selections
are the surveys' published cuts on those magnitudes, with survey noise,
and the survey's fibre collisions: no two fibres closer than their limit
(55" for SDSS), so one of each close pair goes without a redshift.

The catalogue is written as a FITS table.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from visage.sed.mock_image import Q0, nmgy
from visage.sed.noise import flux_error
from visage.system import native_path

PETRO_RATIO = 0.2
N_PETRO = 2.0
_R = np.logspace(-2.5, 2.5, 1501)  # radius / Re, for the profile table


def _enclosed(n: float) -> np.ndarray:
    """Fraction of a Sersic profile's light inside each of _R."""
    bn = 2 * n - 1 / 3 + 0.009876 / n
    i = np.exp(-bn * _R ** (1 / n)) * _R**2  # dL / dln r
    cum = np.cumsum(0.5 * (i[1:] + i[:-1]) * np.diff(np.log(_R)))
    return np.r_[0.0, cum] / cum[-1]


_CUM = {1.0: _enclosed(1.0), 4.0: _enclosed(4.0)}


def _light_inside(r, re, n) -> np.ndarray:
    return np.interp(
        np.log(np.maximum(r / np.maximum(re, 1e-6), 1e-9)),
        np.log(_R),
        _CUM[n],
    )


def measure(flux_d, flux_b, re_d, re_b, seeing, fibre=3.0) -> dict:
    """Petrosian flux, r50 and fibre flux in the detection band, for fluxes
    of the disk and bulge and their half-light radii (arcsec). The seeing
    (FWHM) broadens each radius in quadrature."""
    fd, fb = np.asarray(flux_d, float), np.asarray(flux_b, float)
    rd = np.hypot(re_d, 0.5 * seeing)
    rb = np.hypot(re_b, 0.5 * seeing)
    total = np.maximum(fd + fb, 1e-30)
    grid = np.logspace(-1.5, 3.0, 400)[:, None]

    def inside(r):
        return (
            fd * _light_inside(r, rd, 1.0) + fb * _light_inside(r, rb, 4.0)
        ) / total

    mean_in = inside(grid) / grid**2
    annulus = (inside(1.25 * grid) - inside(0.8 * grid)) / (
        (1.25**2 - 0.8**2) * grid**2
    )
    eta = annulus / np.maximum(mean_in, 1e-30)
    # The first radius where the ratio falls through the limit.
    below = eta < PETRO_RATIO
    first = np.where(below.any(0), below.argmax(0), len(grid) - 1)
    r_p = grid[first, 0]
    in_petro = inside(N_PETRO * r_p[None, :])[0]
    fine = np.logspace(-1.5, 3.0, 1200)[:, None]
    half = (inside(fine) >= 0.5 * in_petro).argmax(0)
    return {
        "petro_frac": in_petro,
        "r_petro": r_p,
        "r50": fine[half, 0],
        "fibre_frac": inside(np.full((1, len(fd)), 0.5 * fibre))[0],
        "rd": rd,
        "rb": rb,
    }


@dataclass(frozen=True)
class Selection:
    label: str
    band: str  # detection band
    limit: float  # AB, on the Petrosian magnitude
    bright: float  # AB
    mu50: float | None  # mag / arcsec^2
    collision: float  # arcsec, 0 = none
    fibre: float  # diameter, arcsec
    seeing: float  # FWHM, arcsec
    ref: str


SELECTIONS = {
    "sdss_main": Selection(
        "SDSS Main Galaxy Sample",
        "sdss_r",
        17.77,
        14.5,
        24.5,
        55.0,
        3.0,
        1.32,
        "Strauss et al. 2002",
    ),
    "gama": Selection(
        "GAMA II",
        "sdss_r",
        19.8,
        14.5,
        None,
        0.0,
        2.0,
        1.32,
        "Baldry et al. 2018",
    ),
}


def _collided(ra, dec, limit, rng) -> np.ndarray:
    """True for one galaxy of each pair closer than `limit` arcsec."""
    from scipy.spatial import cKDTree

    ra, dec = np.deg2rad(ra), np.deg2rad(dec)
    xyz = np.c_[
        np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)
    ]
    pairs = cKDTree(xyz).query_pairs(
        np.deg2rad(limit / 3600), output_type="ndarray"
    )
    lost = np.zeros(len(ra), bool)
    for i, j in pairs[rng.permutation(len(pairs))]:
        if not lost[i] and not lost[j]:
            lost[i if rng.random() < 0.5 else j] = True
    return lost


def catalogue(path: str | Path, key: str, seed: int = 0) -> dict:
    """The galaxies survey `key` would select from lightcone `path`, as a
    dict of arrays, with every band's Petrosian and fibre magnitudes."""
    from visage.io.lightcone_reader import _read_hubble_h

    sel = SELECTIONS[key]
    rng = np.random.default_rng(seed)
    with h5py.File(path, "r", locking=False) as f:
        hub = _read_hubble_h(f)
        z = f["redshift_cosmological"][:]
        d_a = np.maximum(f["distance"][:] / hub / (1 + z), 1e-6)
        scale = 206265.0 / d_a / hub  # arcsec per (Mpc/h)
        cosi = f["CosInclination"][:]
        q = np.sqrt(cosi**2 + Q0**2 * (1 - cosi**2))
        re_d = 1.678 * f["DiskRadius"][:] * scale * np.sqrt(q)
        re_b = f["BulgeRadius"][:] * scale
        bands = sorted(
            k[len("disk_mag_obs_") :]
            for k in f
            if k.startswith("disk_mag_obs_")
            and f"bulge_mag_obs_{k[len('disk_mag_obs_') :]}" in f
        )
        comp = {
            b: (
                nmgy(f[f"disk_mag_obs_{b}"][:]),
                nmgy(f[f"bulge_mag_obs_{b}"][:]),
            )
            for b in bands
        }
        out = {
            "ra": f["ra"][:],
            "dec": f["dec"][:],
            "z_obs": f["redshift_observed"][:],
            "z_cos": z,
            "GalaxyIndex": f["GalaxyIndex"][:],
            "StellarMass": f["StellarMass"][:] * 1e10 / hub,
            "halo": f["CentralGalaxyIndex"][:],
            "halo_mass": f["CentralMvir"][:] * 1e10,  # M_sun/h
            "Sfr": f["SfrDisk"][:] + f["SfrBulge"][:],
        }
    fd, fb = comp[sel.band]
    m = measure(fd, fb, re_d, re_b, sel.seeing, sel.fibre)
    ap = m["r_petro"] * N_PETRO
    fib = np.full_like(ap, 0.5 * sel.fibre)
    for b, (d, b_) in comp.items():
        total = np.maximum(d + b_, 1e-30)
        for name, r in (("petro", ap), ("fibre", fib)):
            flux = d * _light_inside(r, m["rd"], 1.0)
            flux = flux + b_ * _light_inside(r, m["rb"], 4.0)
            with np.errstate(divide="ignore"):
                out[f"{name}_mag_{b}"] = 22.5 - 2.5 * np.log10(
                    np.maximum(flux, 1e-30)
                )
        out[f"total_mag_{b}"] = 22.5 - 2.5 * np.log10(total)
    flux = 10 ** (0.4 * (23.9 - out[f"petro_mag_{sel.band}"]))
    err = flux_error(sel.band, flux, m["r50"])
    seen = 23.9 - 2.5 * np.log10(np.maximum(flux + rng.normal(0, err), 1e-30))
    out["r50"] = m["r50"]
    out["r_petro"] = m["r_petro"]
    out[f"petro_mag_err_{sel.band}"] = 1.0857 * err / flux
    out["mu50"] = seen + 2.5 * np.log10(2 * np.pi * m["r50"] ** 2)
    keep = (seen <= sel.limit) & (seen >= sel.bright)
    if sel.mu50 is not None:
        keep &= out["mu50"] <= sel.mu50
    out["detected_mag"] = seen
    out["row"] = np.arange(len(seen))
    out["rd"], out["rb"] = m["rd"], m["rb"]
    idx = np.flatnonzero(keep)
    collided = np.zeros(len(keep), bool)
    if sel.collision > 0:
        collided[idx] = _collided(
            out["ra"][idx], out["dec"][idx], sel.collision, rng
        )
    out["fibre_collided"] = collided
    return {k: v[keep] for k, v in out.items()}


def write_fits(cat: dict, path: str | Path, key: str) -> None:
    """The catalogue as a FITS binary table."""
    from astropy.table import Table

    t = Table({k: np.asarray(v) for k, v in cat.items()})
    t.meta["SURVEY"] = SELECTIONS[key].label
    t.meta["REF"] = SELECTIONS[key].ref
    t.meta["ORIGIN"] = "ViSAGE (visage.sed.survey)"
    t.write(path, overwrite=True)


def hubble_h(path: str | Path) -> float:
    """Hubble parameter of lightcone `path`."""
    with h5py.File(path, "r", locking=False) as f:
        return float(f["SageOutputHeader"]["Simulation"].attrs["hubble_h"])


def available(present: set[str]) -> list[str]:
    """Selections a lightcone with the columns `present` has the bands for."""
    return [
        k
        for k, sel in SELECTIONS.items()
        if f"disk_mag_obs_{sel.band}" in present
        and f"bulge_mag_obs_{sel.band}" in present
    ]


def write_csv(cat: dict, path: str | Path) -> None:
    """The catalogue as a table of plain text."""
    names = list(cat)
    data = np.column_stack([np.asarray(cat[k], float) for k in names])
    np.savetxt(path, data, delimiter=",", header=",".join(names), comments="")


def summary(cat: dict, path: str | Path, key: str) -> dict:
    """Numbers to quote for a catalogue: count, density, median redshift
    and half-light radius, median fibre minus Petrosian magnitude."""
    band = SELECTIONS[key].band
    with h5py.File(path, "r", locking=False) as f:
        ra, dec = f["ra"][:], f["dec"][:]
    area = np.ptp(ra) * np.ptp(np.sin(np.deg2rad(dec))) * 180 / np.pi
    fibre = cat[f"fibre_mag_{band}"] - cat[f"petro_mag_{band}"]
    n = len(cat["ra"])
    return {
        "n": n,
        "zmax": float(np.max(cat["z_cos"], initial=0.0)),
        "density": n / area,
        "z": float(np.median(cat["z_cos"])),
        "r50": float(np.median(cat["r50"])),
        "fibre": float(np.median(fibre)),
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="visage-survey",
        description="Select a survey's catalogue from a lightcone.",
    )
    p.add_argument("--input", required=True, metavar="FILE")
    p.add_argument("--survey", choices=sorted(SELECTIONS), default="sdss_main")
    p.add_argument("--output", required=True, metavar="FILE")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)
    cat = catalogue(native_path(args.input), args.survey, args.seed)
    write_fits(cat, args.output, args.survey)
    print(f"{len(cat['ra'])} galaxies written to {args.output}")


if __name__ == "__main__":
    main(sys.argv[1:])
