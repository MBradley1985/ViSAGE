"""Survey noise on a lightcone's synthetic photometry: the fluxes a survey
would catalogue, with their errors, next to the noiseless magnitudes.

Each band's sky noise comes from the survey's quoted depth (a point source
at that magnitude has that signal-to-noise). A galaxy spreads over more sky
than a point source, so its error is that noise over its matched-filter
area, 4 pi (sigma_PSF^2 + sigma_gal^2), for a Gaussian of the galaxy's
half-light radius. A 1% calibration floor (as SDSS; Padmanabhan et al. 2008,
ApJ 674, 1217) is added in quadrature. Source shot noise is smaller than
that floor for any band's bright galaxies and isn't included.

Fluxes, not magnitudes, because noise is Gaussian in flux and a faint
galaxy's measured flux can be negative. Nothing is removed: a catalogue cut
is flux / error > some limit, the survey's choice.

Depths beyond those of visage/sed/mock_image.py: SDSS u, z (Abazajian et
al. 2009), DES i, Y (Abbott et al. 2021), PS1 z, y (Chambers et al. 2016),
LSST u, z, y (Ivezic et al. 2019), WISE W4 (Wright et al. 2010). Bands of
surveys without a single quoted depth are skipped.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import h5py
import numpy as np

from visage.sed.mock_image import SURVEYS, _ab_from_mjy
from visage.system import native_path

CALIBRATION_FLOOR = 0.01
DISK_RE = 1.678  # half-light radius / scale length of an exponential disk

# band: ((AB mag, signal-to-noise, aperture diameter ["] or None), FWHM ["]).
DEPTHS = {
    b: (s.depth[i], s.seeing[i])
    for s in SURVEYS.values()
    if s.depth
    for i, b in enumerate(s.bands)
}
DEPTHS |= {
    "sdss_u": ((22.0, 5, None), 1.4),
    "sdss_z": ((20.5, 5, None), 1.4),
    "des_i": ((23.8, 10, 1.95), 0.88),
    "des_y": ((21.7, 10, 1.95), 0.90),
    "ps1_z": ((22.3, 5, None), 1.07),
    "ps1_y": ((21.4, 5, None), 1.02),
    "lsst_u": ((26.1, 5, None), 0.7),
    "lsst_z": ((26.1, 5, None), 0.7),
    "lsst_y": ((24.9, 5, None), 0.7),
    "wise_w4": ((_ab_from_mjy(6.0), 5, None), 12.0),
}


def ujy(mag: np.ndarray) -> np.ndarray:
    """AB magnitude to µJy (0 for missing)."""
    mag = np.asarray(mag, dtype=np.float64)
    return np.where(np.isfinite(mag), 10 ** ((23.9 - mag) / 2.5), 0.0)


def flux_error(band: str, flux: np.ndarray, size: np.ndarray) -> np.ndarray:
    """1-sigma error (µJy) on galaxies of total `flux` (µJy) and half-light
    radius `size` (arcsec) in `band`."""
    (mag, snr, ap), fwhm = DEPTHS[band]
    sig_psf = fwhm / 2.3548
    area = np.pi * (ap / 2) ** 2 if ap else 4 * np.pi * sig_psf**2
    sky = float(ujy(mag)) / snr / np.sqrt(area)  # µJy per sqrt(arcsec^2)
    sig_gal = np.asarray(size, float) / 1.1774
    sky_err2 = sky**2 * 4 * np.pi * (sig_psf**2 + sig_gal**2)
    return np.sqrt(sky_err2 + (CALIBRATION_FLOOR * flux) ** 2)


def add_noise(path: str | Path, seed: int = 0) -> list[str]:
    """Write ``flux_obs_<band>`` and ``fluxerr_obs_<band>`` (µJy) into the
    lightcone for each of its ``mag_obs_<band>`` with a known depth;
    returns those bands."""
    from visage.io.lightcone_reader import _read_hubble_h

    rng = np.random.default_rng(seed)
    with h5py.File(path, "a") as f:
        hub = _read_hubble_h(f)
        bands = [
            k[len("mag_obs_") :]
            for k in f
            if k.startswith("mag_obs_") and k[len("mag_obs_") :] in DEPTHS
        ]
        mass = f["StellarMass"][:].astype(np.float64)
        bt = np.clip(f["BulgeMass"][:] / np.maximum(mass, 1e-30), 0, 1)
        re_mpc = (1 - bt) * DISK_RE * f["DiskRadius"][:] / hub + bt * f[
            "BulgeRadius"
        ][:] / hub
        z = f["redshift_cosmological"][:]
        d_a = f["distance"][:] / hub / (1 + z)
        size = re_mpc / np.maximum(d_a, 1e-6) * 206265.0
        for b in bands:
            true = ujy(f[f"mag_obs_{b}"][:])
            err = flux_error(b, true, size)
            for name, values, what in (
                (
                    f"flux_obs_{b}",
                    true + rng.normal(0.0, err),
                    "Observed flux with survey noise",
                ),
                (f"fluxerr_obs_{b}", err, "1-sigma error on the flux"),
            ):
                if name in f:
                    del f[name]
                ds = f.create_dataset(name, data=values.astype(np.float32))
                ds.attrs["Description"] = f"{what} ({b})"
                ds.attrs["Units"] = "uJy"
                ds.attrs["Source"] = "ViSAGE survey noise (depths in noise.py)"
        if bands:
            f["PhotometryHeader"].attrs["Noise"] = (
                "survey depths, matched-filter area, 1% calibration floor; "
                f"seed {seed}"
            )
    return bands


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="visage-sed-noise",
        description="Add survey-noise fluxes to a lightcone's photometry.",
    )
    p.add_argument("--input", required=True, metavar="FILE")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)
    path = native_path(args.input)
    bands = add_noise(path, args.seed)
    print(f"Wrote noisy fluxes for {len(bands)} bands into {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
