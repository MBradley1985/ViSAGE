"""Mock fibre spectroscopy of a survey catalogue.

The spectra the photometry is built from, as a spectrograph records them:
the disk and bulge light inside the fibre, at the instrument's resolution
and wavelengths, with noise measured from real faint SDSS spectra, sky lines
included. SAGE26 gives one star formation history per component, so the
fibre mixes those two and cannot show gradients within either. Noise is the
sky's and the detector's: bright galaxies' own shot noise isn't added.

Indices are measured from the noisy spectra as a survey would: D_n4000
(Balogh et al. 1999) and lines from a band and side bands. As in a raw
measurement, the stellar absorption under a Balmer line isn't corrected.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np
from scipy.ndimage import gaussian_filter1d

from visage.system import native_path
from visage.sed import igm, spectrum
from visage.sed.photometry import compute_photometry
from visage.sed.spectrum import L_SUN_ERG_S, MPC_TO_CM
from visage.sed.survey import SELECTIONS, _light_inside, catalogue

NOISE_FILE = Path(__file__).parent / "data" / "sdss_sky_noise.npz"
RESOLUTION = 2000.0  # Smee et al. 2013
DLOGLAM = 1e-4
OVERSAMPLE = 4
C_ANG = 2.99792458e18  # Angstrom / s
UNIT = 1e-17  # erg/s/cm^2/Angstrom, as SDSS spectra
# Rest band, and the side bands either side, Angstrom.
LINES = {
    "Hbeta": ((4855, 4869), (4800, 4840), (4880, 4920)),
    "OIII5007": ((5000, 5014), (4970, 4990), (5025, 5060)),
    "Halpha": ((6555, 6571), (6480, 6530), (6600, 6640)),
    "NII6584": ((6577, 6591), (6480, 6530), (6600, 6640)),
}


def fibre_weights(rd, rb, fibre: float = 3.0) -> tuple:
    """Share of the disk's and the bulge's light inside a fibre of diameter
    `fibre` (arcsec), for half-light radii already blurred by the seeing."""
    r = np.full_like(np.asarray(rd, float), 0.5 * fibre)
    return _light_inside(r, rd, 1.0), _light_inside(r, rb, 4.0)


def observe(wave_rest, lnu, z, d_l_cm, igm_on=False):
    """L_sun/Hz at rest wavelengths to the instrument's noiseless spectrum:
    (log10 observed wavelength, f_lambda in UNIT), as if at resolution
    RESOLUTION on its pixels."""
    with np.load(NOISE_FILE) as d:
        loglam = d["loglam"].astype(float)
    fnu = (1 + z) * lnu * L_SUN_ERG_S / (4 * np.pi * d_l_cm**2)
    if igm_on:
        fnu = fnu * igm.transmission(wave_rest, z)
    lam = wave_rest * (1 + z)
    flam = fnu * C_ANG / lam**2 / UNIT
    fine = np.arange(loglam[0], loglam[-1] + DLOGLAM, DLOGLAM / OVERSAMPLE)
    f = np.interp(10**fine, lam, flam)
    sigma = 1 / (2.3548 * RESOLUTION * np.log(10) * DLOGLAM / OVERSAMPLE)
    f = gaussian_filter1d(f, sigma)
    return loglam, f[: OVERSAMPLE * len(loglam)][::OVERSAMPLE]


def noise_sigma() -> np.ndarray:
    """1 sigma per pixel, in UNIT."""
    with np.load(NOISE_FILE) as d:
        return d["sigma"].astype(float)


def _band(loglam, z, lo, hi):
    rest = 10**loglam / (1 + z)
    return (rest >= lo) & (rest < hi)


def dn4000(loglam, flam, z) -> float:
    """D_n4000: mean f_nu in 4000-4100 over 3850-3950 Angstrom (rest)."""
    fnu = flam * 10 ** (2 * loglam)
    red, blue = _band(loglam, z, 4000, 4100), _band(loglam, z, 3850, 3950)
    if not red.any() or not blue.any():
        return np.nan
    return float(fnu[red].mean() / fnu[blue].mean())


def measure_line(loglam, flam, sigma, z, name) -> tuple:
    """Flux (UNIT Angstrom, observed), its error and rest equivalent width
    (Angstrom, emission positive) of line `name`."""
    centre, left, right = LINES[name]
    m = _band(loglam, z, *centre)
    side = _band(loglam, z, *left) | _band(loglam, z, *right)
    if not m.any() or not side.any():
        return np.nan, np.nan, np.nan
    cont = float(np.median(flam[side]))
    dlam = 10 ** loglam[m] * np.log(10) * DLOGLAM
    flux = float(np.sum((flam[m] - cont) * dlam))
    err = float(np.sqrt(np.sum((sigma[m] * dlam) ** 2)))
    ew = flux / (1 + z) / cont if cont > 0 else np.nan
    return flux, err, ew


def spectroscopy(
    path: str | Path, key: str = "sdss_main", seed: int = 0, progress_cb=None
) -> tuple:
    """Fibre spectra of the galaxies survey `key` selects from lightcone
    `path` and can put a fibre on: (catalogue, log10 wavelength, flux,
    sigma per pixel), with the catalogue gaining what's measured."""
    path = Path(path)
    sel = SELECTIONS[key]
    cat = catalogue(path, key, seed)
    keep = ~cat["fibre_collided"]
    cat = {k: v[keep] for k, v in cat.items()}
    rows = cat["row"]
    order = np.argsort(rows)
    cat = {k: v[order] for k, v in cat.items()}
    rows = cat["row"]
    kw, hdr = spectrum.run_settings(path)
    spec: dict = {}
    compute_photometry(
        path,
        bands=(sel.band,),
        alist=spectrum.find_alist(path),
        rows=rows,
        spectra_out=spec,
        frame="obs",
        progress_cb=progress_cb,
        **kw,
    )
    with h5py.File(path, "r", locking=False) as f:
        hub = float(f["SageOutputHeader"]["Simulation"].attrs["hubble_h"])
        dist = f["distance"][:][rows]
    d_l = (1 + cat["z_obs"]) * dist / hub * MPC_TO_CM
    w_d, w_b = fibre_weights(cat["rd"], cat["rb"], sel.fibre)
    wave = spec["wave"]
    sigma = noise_sigma()
    rng = np.random.default_rng(seed)
    out, names = [], ("dn4000", "dn4000_total")
    measured = {k: np.full(len(rows), np.nan) for k in names}
    for name in LINES:
        for part in ("flux", "err", "ew"):
            measured[f"{name}_{part}"] = np.full(len(rows), np.nan)
    use_igm = "IGM" in hdr
    for i in range(len(rows)):
        z = float(cat["z_obs"][i])
        lnu = w_d[i] * spec["disk"][i] + w_b[i] * spec["bulge"][i]
        if "agn" in spec:  # the narrow-line region is nuclear
            lnu = lnu + spec["agn"][i]
        loglam, clean = observe(wave, lnu, z, d_l[i], use_igm)
        noisy = clean + rng.normal(0, sigma)
        out.append(noisy.astype(np.float32))
        measured["dn4000"][i] = dn4000(loglam, noisy, z)
        total = observe(wave, spec["observed"][i], z, d_l[i], use_igm)[1]
        measured["dn4000_total"][i] = dn4000(loglam, total, z)
        for name in LINES:
            flux, err, ew = measure_line(loglam, noisy, sigma, z, name)
            measured[f"{name}_flux"][i] = flux
            measured[f"{name}_err"][i] = err
            measured[f"{name}_ew"][i] = ew
    cat |= measured
    cat["sn_median"] = np.median(np.asarray(out) / sigma, axis=1)
    return cat, loglam, np.asarray(out), sigma


def write_fits(cat, loglam, flux, sigma, path, key) -> None:
    """Table of measurements, then the spectra as image extensions."""
    from astropy.io import fits
    from astropy.table import Table

    table = fits.BinTableHDU(
        Table({k: np.asarray(v) for k, v in cat.items()}), name="CATALOGUE"
    )
    table.header["SURVEY"] = SELECTIONS[key].label
    table.header["ORIGIN"] = "ViSAGE (visage.sed.spectroscopy)"
    fits.HDUList(
        [
            fits.PrimaryHDU(),
            table,
            fits.ImageHDU(flux, name="FLUX"),
            fits.ImageHDU(loglam.astype(np.float32), name="LOGLAM"),
            fits.ImageHDU(sigma.astype(np.float32), name="SIGMA"),
        ]
    ).writeto(path, overwrite=True)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="visage-spectroscopy",
        description="Mock fibre spectra of a survey's galaxies.",
    )
    p.add_argument("--input", required=True, metavar="FILE")
    p.add_argument("--survey", choices=["sdss_main"], default="sdss_main")
    p.add_argument("--output", required=True, metavar="FILE")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)
    res = spectroscopy(native_path(a.input), a.survey, a.seed, print)
    write_fits(*res, a.output, a.survey)


if __name__ == "__main__":
    main()
