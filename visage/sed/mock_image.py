"""Mock survey images of a lightcone with synthetic photometry: what a
telescope would see.

Each galaxy is an exponential disk (DiskRadius as its scale length) plus a
de Vaucouleurs bulge (BulgeRadius as its half-light radius) at its angular
size (radius over the angular-diameter distance), with the disk flattened
by its inclination, axis ratio q = sqrt(cos^2 i + q0^2 sin^2 i), q0 = 0.2
(Hubble 1926; Holmberg 1958), and turned to the position angle of its
spin on the sky. Its disk and bulge fluxes come from its observed-frame
disk_mag_obs_* and bulge_mag_obs_* magnitudes (total magnitudes split by
bulge-to-total stellar mass when a cone has no disk/bulge photometry).
The image is blurred by a Gaussian PSF of the survey's median seeing on
its pixel grid. "Survey depth" adds sky noise so that a point source at
the survey's quoted limit has that signal-to-noise. Colour images are
asinh composites (Lupton et al. 2004, PASP 116, 133).

Survey numbers (pixel scale, median seeing, depth):

- SDSS: 0.396"/pixel, 1.4" in r (Gunn et al. 2006; Abazajian et al. 2009),
  depth the DR7 95%-completeness limits for point sources, g 22.2,
  r 22.2, i 21.3 (Abazajian et al. 2009, ApJS 182, 543), taken as 5 sigma.
- DES DR2 (DECam): 0.263"/pixel, seeing g 1.11", r 0.95", z 0.83", 10 sigma
  in a 1.95" aperture g 24.7, r 24.4, z 23.1 (Abbott et al. 2021,
  ApJS 255, 20).
- Pan-STARRS1 3pi: 0.25"/pixel, seeing g 1.31", r 1.19", i 1.11", 5 sigma
  point sources g 23.3, r 23.2, i 23.1 (Chambers et al. 2016,
  arXiv:1612.05560).
- Rubin LSST, 10-year: 0.2"/pixel, 0.7" seeing, 5 sigma point sources
  g 27.4, r 27.5, i 26.8 (Ivezic et al. 2019, ApJ 873, 111).
- 2MASS: 1"/pixel (Atlas images), 2.5" seeing, 10 sigma point sources
  J 15.8, H 15.1, Ks 14.3 Vega (Skrutskie et al. 2006, AJ 131, 1163),
  +0.91, +1.39, +1.85 to AB (Blanton & Roweis 2007, AJ 133, 734).
- WISE: 1.375"/pixel (Atlas), PSF 6.1", 6.4", 6.5", 5 sigma point sources
  0.08, 0.11, 1 mJy in W1-W3 (Wright et al. 2010, AJ 140, 1868).
- GALEX AIS: 1.5"/pixel, PSF FUV 4.2", NUV 5.3", 5 sigma FUV 19.9,
  NUV 20.8 (Morrissey et al. 2007, ApJS 173, 682).
- JWST NIRCam: 0.031"/pixel, PSF F115W 0.040", F200W 0.066", F444W 0.145"
  (JWST User Documentation); depth depends on the programme, so noiseless.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np
from scipy.ndimage import gaussian_filter

Q0 = 0.2  # intrinsic disk thickness (Hubble 1926; Holmberg 1958)
MAX_PIXELS = 2400  # longest side of an image
MARGIN = 200  # pixels beyond the field whose light can fall in it


@dataclass(frozen=True)
class Survey:
    label: str
    bands: tuple[str, ...]  # FSPS filters, reddest first (R, G, B)
    pixel: float  # arcsec
    seeing: tuple[float, ...]  # PSF FWHM per band, arcsec
    # Depth per band: (AB mag, signal-to-noise, aperture diameter in arcsec
    # or None for a PSF-fitted point source); empty = noiseless only.
    depth: tuple = ()
    ref: str = ""
    # Colour balance per band; empty = each band scaled by its own noise
    # (for surveys whose bands differ a lot in depth, like WISE).
    weights: tuple[float, ...] = field(default=())


def _ab_from_mjy(mjy: float) -> float:
    return float(-2.5 * np.log10(mjy * 1e-3 / 3631.0))


SURVEYS: dict[str, Survey] = {
    "sdss": Survey(
        "SDSS (gri)",
        ("sdss_i", "sdss_r", "sdss_g"),
        0.396,
        (1.4, 1.4, 1.4),
        ((21.3, 5, None), (22.2, 5, None), (22.2, 5, None)),
        "Abazajian et al. 2009",
        (1.0, 1.1, 1.4),
    ),
    "des": Survey(
        "DES DR2 (DECam grz)",
        ("des_z", "des_r", "des_g"),
        0.263,
        (0.83, 0.95, 1.11),
        ((23.1, 10, 1.95), (24.4, 10, 1.95), (24.7, 10, 1.95)),
        "Abbott et al. 2021",
        (1.0, 1.1, 1.4),
    ),
    "ps1": Survey(
        "Pan-STARRS1 3π (gri)",
        ("ps1_i", "ps1_r", "ps1_g"),
        0.25,
        (1.11, 1.19, 1.31),
        ((23.1, 5, None), (23.2, 5, None), (23.3, 5, None)),
        "Chambers et al. 2016",
        (1.0, 1.1, 1.4),
    ),
    "lsst": Survey(
        "Rubin LSST 10-year (gri)",
        ("lsst_i", "lsst_r", "lsst_g"),
        0.2,
        (0.7, 0.7, 0.7),
        ((26.8, 5, None), (27.5, 5, None), (27.4, 5, None)),
        "Ivezić et al. 2019",
        (1.0, 1.1, 1.4),
    ),
    "2mass": Survey(
        "2MASS (JHKs)",
        ("2mass_ks", "2mass_h", "2mass_j"),
        1.0,
        (2.5, 2.5, 2.5),
        (
            (14.3 + 1.85, 10, None),
            (15.1 + 1.39, 10, None),
            (15.8 + 0.91, 10, None),
        ),
        "Skrutskie et al. 2006",
        (1.0, 1.0, 1.0),
    ),
    "wise": Survey(
        "WISE (W1-W3)",
        ("wise_w3", "wise_w2", "wise_w1"),
        1.375,
        (6.5, 6.4, 6.1),
        (
            (_ab_from_mjy(1.0), 5, None),
            (_ab_from_mjy(0.11), 5, None),
            (_ab_from_mjy(0.08), 5, None),
        ),
        "Wright et al. 2010",
    ),
    "galex": Survey(
        "GALEX AIS (FUV, NUV)",
        ("galex_nuv", "galex_fuv"),
        1.5,
        (5.3, 4.2),
        ((20.8, 5, None), (19.9, 5, None)),
        "Morrissey et al. 2007",
    ),
    "nircam": Survey(
        "JWST NIRCam (F115W, F200W, F444W)",
        ("jwst_f444w", "jwst_f200w", "jwst_f115w"),
        0.031,
        (0.145, 0.066, 0.040),
        (),
        "JWST User Documentation",
        (1.0, 1.0, 1.0),
    ),
}

# Field sizes offered (arcmin), kept to those under MAX_PIXELS.
FIELDS_ARCMIN = (0.5, 1, 2, 5, 10, 20, 30)


def available_surveys(present: set[str]) -> list[str]:
    """Surveys whose every band this cone has in the observed frame."""
    return [
        k
        for k, s in SURVEYS.items()
        if all(f"mag_obs_{b}" in present for b in s.bands)
    ]


def field_sizes(survey: str) -> list[float]:
    pix = SURVEYS[survey].pixel
    return [f for f in FIELDS_ARCMIN if f * 60 / pix <= MAX_PIXELS]


def nmgy(mag: np.ndarray) -> np.ndarray:
    """AB magnitude to nanomaggies (0 for missing)."""
    mag = np.asarray(mag, dtype=np.float64)
    return np.where(np.isfinite(mag), 10 ** (-0.4 * (mag - 22.5)), 0.0)


def sersic_stamp(n, re_pix, q, pa, size, sub=5, off=(0.0, 0.0)):
    """Unit-flux Sersic profile on a size x size grid, oversampled, its
    centre `off` (x, y) pixels from the stamp's middle."""
    bn = 2 * n - 1 / 3 + 0.009876 / n
    g = (np.arange(size * sub) + 0.5) / sub - size / 2
    x, y = np.meshgrid(g, g)
    x, y = x - off[0], y - off[1]
    c, s = np.cos(pa), np.sin(pa)
    xr = x * c + y * s
    yr = -x * s + y * c
    r = np.sqrt(xr**2 + (yr / max(q, 0.05)) ** 2)
    img = np.exp(-bn * ((r / max(re_pix, 0.05)) ** (1 / n) - 1))
    # Fade the outer 30% of the stamp to zero, so a stretched image shows
    # no edge where the stamp ends.
    edge = np.clip((np.hypot(x, y) / (size / 2) - 0.7) / 0.3, 0, 1)
    img *= 0.5 * (1 + np.cos(np.pi * edge))
    img = img.reshape(size, sub, size, sub).mean(axis=(1, 3))
    tot = img.sum()
    return img / tot if tot > 0 else img


def noise_sigma(survey: Survey, i: int) -> float:
    """Sky noise per pixel (nanomaggies) for band i at the survey depth."""
    mag, snr, ap = survey.depth[i]
    flux = float(nmgy(mag))
    if ap is None:  # PSF-fitted: effective area 4 pi sigma_psf^2
        sig = survey.seeing[i] / 2.3548 / survey.pixel
        n_pix = 4 * np.pi * sig**2
    else:
        n_pix = np.pi * (ap / 2 / survey.pixel) ** 2
    return flux / snr / np.sqrt(n_pix)


def lupton_rgb(chans, stretch, q=8.0):
    """asinh colour composite (Lupton et al. 2004) of up to three images
    (R, G, B); fewer than three are spread across the channels."""
    if len(chans) == 1:
        chans = [chans[0]] * 3
    elif len(chans) == 2:
        chans = [chans[0], 0.5 * (chans[0] + chans[1]), chans[1]]
    r, g, b = (np.clip(c, 0, None) for c in chans)
    i = (r + g + b) / 3
    # Faint (sky) pixels keep their brightness, not an amplified colour.
    i_safe = np.maximum(i, 1e-3 * stretch)
    f = np.arcsinh(q * i_safe / stretch) / q / i_safe
    rgb = np.stack([r * f, g * f, b * f], -1)
    peak = np.maximum(rgb.max(-1, keepdims=True), 1.0)
    return np.clip(rgb / peak, 0, 1)


@dataclass
class MockImage:
    survey: str
    field_arcmin: float
    ra0: float
    dec0: float
    z0: float
    images: dict  # band -> 2D array, nanomaggies per pixel
    rgb: np.ndarray  # H x W x 3, 0..1
    n_galaxies: int
    centre_label: str
    noisy: bool

    def png_bytes(self) -> bytes:
        from PIL import Image

        buf = io.BytesIO()
        img = (self.rgb[::-1] * 255).astype(np.uint8)  # north up
        Image.fromarray(img).save(buf, "PNG")
        return buf.getvalue()

    def write_fits(self, path: Path) -> bool:
        """One image extension per band with a TAN WCS; False without
        astropy."""
        try:
            from astropy.io import fits
        except ImportError:
            return False
        s = SURVEYS[self.survey]

        def ascii(text: str) -> str:
            import unicodedata

            t = unicodedata.normalize("NFKD", text.replace("π", "pi"))
            return t.encode("ascii", "ignore").decode()[:68]

        hdus = [fits.PrimaryHDU()]
        hdr = hdus[0].header
        hdr["SURVEY"] = ascii(s.label)
        hdr["REF"] = ascii(s.ref)
        hdr["NOISE"] = (self.noisy, "sky noise at the survey depth")
        hdr["RA_CEN"] = (self.ra0, "centre RA, deg")
        hdr["DEC_CEN"] = (self.dec0, "centre Dec, deg")
        hdr["Z_CEN"] = (self.z0, "redshift of the centre galaxy")
        hdr["ORIGIN"] = "ViSAGE mock image (visage.sed.mock_image)"
        for i, b in enumerate(s.bands):
            img = self.images[b]
            ny, nx = img.shape
            h = fits.ImageHDU(img.astype(np.float32), name=b.upper())
            h.header["BUNIT"] = "nanomaggy"
            h.header["FILTER"] = b
            h.header["SEEING"] = (s.seeing[i], "PSF FWHM, arcsec")
            h.header["CTYPE1"], h.header["CTYPE2"] = "RA---TAN", "DEC--TAN"
            h.header["CRVAL1"], h.header["CRVAL2"] = self.ra0, self.dec0
            h.header["CRPIX1"], h.header["CRPIX2"] = nx / 2 + 0.5, ny / 2 + 0.5
            h.header["CDELT1"] = -s.pixel / 3600
            h.header["CDELT2"] = s.pixel / 3600
            h.header["CUNIT1"] = h.header["CUNIT2"] = "deg"
            hdus.append(h)
        fits.HDUList(hdus).writeto(path, overwrite=True)
        return True


def _read(path: Path, rows, bands):
    from visage.io.lightcone_reader import _read_hubble_h

    with h5py.File(path, "r") as f:
        hub = _read_hubble_h(f)
        need = (
            "ra",
            "dec",
            "distance",
            "redshift_cosmological",
            "DiskRadius",
            "BulgeRadius",
            "Spinx",
            "Spiny",
            "Spinz",
            "Posx",
            "Posy",
            "Posz",
            "StellarMass",
            "BulgeMass",
        )
        d = {k: f[k][:] if rows is None else f[k][rows] for k in need}
        if "CosInclination" in f:
            d["CosInclination"] = (
                f["CosInclination"][:]
                if rows is None
                else f["CosInclination"][rows]
            )
        for b in bands:
            split = f"disk_mag_obs_{b}" in f and f"bulge_mag_obs_{b}" in f
            for comp in ("disk", "bulge"):
                key = f"{comp}_mag_obs_{b}" if split else f"mag_obs_{b}"
                v = f[key][:] if rows is None else f[key][rows]
                d[f"{comp}_{b}"] = nmgy(v)
            if not split:  # share the total by bulge-to-total mass
                bt = np.clip(
                    d["BulgeMass"] / np.maximum(d["StellarMass"], 1e-30), 0, 1
                )
                d[f"disk_{b}"] *= 1 - bt
                d[f"bulge_{b}"] *= bt
    return hub, d


def make_mock_image(
    path: str | Path,
    survey: str,
    field_arcmin: float,
    centre_row: int | None = None,
    noisy: bool = True,
    seed: int = 0,
) -> MockImage:
    """A mock `survey` image `field_arcmin` on a side, centred on the galaxy
    in HDF5 row `centre_row` (the brightest galaxy in the reddest band,
    away from the cone's edges, if None)."""
    s = SURVEYS[survey]
    path = Path(path)
    if not s.depth:
        noisy = False
    with h5py.File(path, "r") as f:
        ra_all = f["ra"][:]
        dec_all = f["dec"][:]
        z_all = f["redshift_cosmological"][:]
        red = nmgy(f[f"mag_obs_{s.bands[0]}"][:])
    half_deg = field_arcmin / 120
    if centre_row is None:
        inside = (
            (ra_all > ra_all.min() + half_deg)
            & (ra_all < ra_all.max() - half_deg)
            & (dec_all > dec_all.min() + half_deg)
            & (dec_all < dec_all.max() - half_deg)
        )
        cand = np.where(inside, red, -1.0)
        centre_row = int(np.argmax(cand if inside.any() else red))
        what = "the brightest galaxy"
    else:
        what = f"galaxy row {centre_row}"
    ra0, dec0 = float(ra_all[centre_row]), float(dec_all[centre_row])
    z0 = float(z_all[centre_row])
    centre_label = f"{what} (RA {ra0:.4f}°, Dec {dec0:+.4f}°, z = {z0:.4f})"

    npx = int(round(field_arcmin * 60 / s.pixel))
    cosd = np.cos(np.deg2rad(dec0))
    dx_all = -(ra_all - ra0) * cosd * 3600 / s.pixel + npx / 2
    dy_all = (dec_all - dec0) * 3600 / s.pixel + npx / 2
    near = np.flatnonzero(
        (dx_all > -MARGIN)
        & (dx_all < npx + MARGIN)
        & (dy_all > -MARGIN)
        & (dy_all < npx + MARGIN)
    )
    hub, d = _read(path, near, s.bands)
    dx, dy = dx_all[near], dy_all[near]

    # Angular sizes: comoving distance -> angular-diameter distance.
    d_a = d["distance"] / hub / (1 + d["redshift_cosmological"])
    rd_pix = d["DiskRadius"] / hub / np.maximum(d_a, 1e-6) * 206265 / s.pixel
    rb_pix = d["BulgeRadius"] / hub / np.maximum(d_a, 1e-6) * 206265 / s.pixel
    # Orientation on the sky: the projected spin is the disk's minor axis.
    pos = np.c_[d["Posx"], d["Posy"], d["Posz"]]
    los = pos / np.maximum(np.linalg.norm(pos, axis=1, keepdims=True), 1e-12)
    east = np.cross([0, 0, 1.0], los)
    east /= np.maximum(np.linalg.norm(east, axis=1, keepdims=True), 1e-12)
    north = np.cross(los, east)
    spin = np.c_[d["Spinx"], d["Spiny"], d["Spinz"]]
    pa = (
        np.arctan2(np.sum(spin * north, 1), -np.sum(spin * east, 1))
        + np.pi / 2
    )
    if "CosInclination" in d:
        cosi = np.abs(d["CosInclination"])
    else:
        sn = np.linalg.norm(spin, axis=1)
        cosi = np.abs(np.sum(spin * los, 1)) / np.maximum(sn, 1e-30)
    q_disk = np.sqrt(cosi**2 + Q0**2 * (1 - cosi**2))

    # Skip galaxies far below the noise in every band.
    if noisy:
        floor = [0.05 * noise_sigma(s, i) for i in range(len(s.bands))]
    else:
        floor = [float(nmgy(32.0))] * len(s.bands)

    images = {b: np.zeros((npx, npx)) for b in s.bands}
    drawn = 0
    for k in range(len(near)):
        hit = False
        for comp, n_s, re, q in (
            ("disk", 1.0, 1.678 * rd_pix[k], q_disk[k]),
            ("bulge", 4.0, rb_pix[k], 0.8),
        ):
            fl = [float(d[f"{comp}_{b}"][k]) for b in s.bands]
            if all(v <= fl0 for v, fl0 in zip(fl, floor, strict=True)):
                continue
            # Out to ~1e-4 of the centre (8 Re for a bulge, 10 for a disk).
            size = (
                int(
                    np.clip((16 if n_s > 2 else 20) * max(re, 1.0), 9, 2 * npx)
                )
                | 1
            )
            # Pixel i spans [i, i+1); the stamp's middle pixel sits on
            # (cx, cy) and the profile is shifted onto the exact position.
            cx, cy = int(np.floor(dx[k])), int(np.floor(dy[k]))
            off = (dx[k] - cx - 0.5, dy[k] - cy - 0.5)
            st = sersic_stamp(
                n_s, re, q, pa[k], size, sub=5 if re < 4 else 1, off=off
            )
            x0, y0 = cx - size // 2, cy - size // 2
            xs, ys = max(x0, 0), max(y0, 0)
            xe, ye = min(x0 + size, npx), min(y0 + size, npx)
            if xs >= xe or ys >= ye:
                continue
            cut = st[ys - y0 : ye - y0, xs - x0 : xe - x0]
            for b, v in zip(s.bands, fl, strict=True):
                images[b][ys:ye, xs:xe] += v * cut
            hit = True
        drawn += hit

    rng = np.random.default_rng(seed)
    for i, b in enumerate(s.bands):
        images[b] = gaussian_filter(images[b], s.seeing[i] / 2.3548 / s.pixel)
        if noisy:
            images[b] = images[b] + rng.normal(
                0, noise_sigma(s, i), images[b].shape
            )

    # Stretch: sky noise at survey depth a faint grain (1 sigma ~ 15%
    # grey). A noiseless image is stretched 5x less, so the faint outer
    # light of bright galaxies (below any survey's noise) doesn't wash
    # over the field.
    nb = len(s.bands)
    if s.depth:
        sig = np.array([noise_sigma(s, i) for i in range(nb)])
        stretch = (6 if noisy else 30) * float(sig.mean())
        w = s.weights or tuple(sig.mean() / sig)
    else:
        tot = sum(images.values())
        stretch = 0.02 * float(np.percentile(tot, 99.9) or 1.0)
        w = s.weights or (1.0,) * nb
    rgb = lupton_rgb(
        [images[b] * wi for b, wi in zip(s.bands, w, strict=True)], stretch
    )
    return MockImage(
        survey=survey,
        field_arcmin=field_arcmin,
        ra0=ra0,
        dec0=dec0,
        z0=z0,
        images=images,
        rgb=rgb,
        n_galaxies=drawn,
        centre_label=centre_label,
        noisy=noisy,
    )
