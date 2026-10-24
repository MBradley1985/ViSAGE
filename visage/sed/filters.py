from __future__ import annotations

import numpy as np

# Surveys the LightSAGE flow offers, as presets of FSPS filters:
# (key, label, filters, on by default). The wizard's run script gets one
# SURVEY_<key>_ENABLED checkbox per survey. DESI's Legacy Imaging uses
# DECam (the DES filters); HSC isn't in FSPS.
SURVEYS = (
    ("GALEX", "GALEX (FUV, NUV)", ("galex_fuv", "galex_nuv"), True),
    (
        "SDSS",
        "SDSS (ugriz)",
        ("sdss_u", "sdss_g", "sdss_r", "sdss_i", "sdss_z"),
        True,
    ),
    ("2MASS", "2MASS (JHKs)", ("2mass_j", "2mass_h", "2mass_ks"), True),
    (
        "WISE",
        "WISE (W1-W4)",
        ("wise_w1", "wise_w2", "wise_w3", "wise_w4"),
        True,
    ),
    (
        "DECAM",
        "DES / DESI Legacy (DECam grizY)",
        ("des_g", "des_r", "des_i", "des_z", "des_y"),
        False,
    ),
    (
        "PS1",
        "Pan-STARRS1 (grizy)",
        ("ps1_g", "ps1_r", "ps1_i", "ps1_z", "ps1_y"),
        False,
    ),
    (
        "LSST",
        "Rubin LSST (ugrizy)",
        ("lsst_u", "lsst_g", "lsst_r", "lsst_i", "lsst_z", "lsst_y"),
        False,
    ),
    (
        "EUCLID",
        "Euclid (VIS, Y, J, H)",
        ("euclid_vis", "euclid_y", "euclid_j", "euclid_h"),
        False,
    ),
    (
        "ROMAN",
        "Roman (F062-F184)",
        (
            "roman_f062",
            "roman_f087",
            "roman_f106",
            "roman_f129",
            "roman_f158",
            "roman_f184",
        ),
        False,
    ),
    (
        "JWST",
        "JWST NIRCam (F070W-F444W)",
        (
            "jwst_f070w",
            "jwst_f090w",
            "jwst_f115w",
            "jwst_f150w",
            "jwst_f200w",
            "jwst_f277w",
            "jwst_f356w",
            "jwst_f444w",
        ),
        False,
    ),
    (
        "HST",
        "HST ACS/WFC3 (F435W, F606W, F814W, F125W, F160W)",
        (
            "wfc_acs_f435w",
            "wfc_acs_f606w",
            "wfc_acs_f814w",
            "wfc3_ir_f125w",
            "wfc3_ir_f160w",
        ),
        False,
    ),
    (
        "VISTA",
        "VISTA (YJHKs)",
        ("vista_y", "vista_j", "vista_h", "vista_k"),
        False,
    ),
    (
        "UKIDSS",
        "UKIDSS / WFCAM (ZYJHK)",
        ("wfcam_z", "wfcam_y", "wfcam_j", "wfcam_h", "wfcam_k"),
        False,
    ),
    (
        "SPITZER",
        "Spitzer (IRAC 1-4, MIPS 24)",
        ("irac_1", "irac_2", "irac_3", "irac_4", "mips_24"),
        False,
    ),
    (
        "HERSCHEL",
        "Herschel (PACS 70-160, SPIRE 250-500)",
        (
            "pacs_70",
            "pacs_100",
            "pacs_160",
            "spire_250",
            "spire_350",
            "spire_500",
        ),
        False,
    ),
)

# The default band set: every survey on by default.
DEFAULT_BANDS = tuple(f for _, _, fs, on in SURVEYS if on for f in fs)


def survey_bands(keys) -> tuple[str, ...]:
    """FSPS filters of the given survey keys, in survey order."""
    want = {k.upper() for k in keys}
    return tuple(f for k, _, fs, _ in SURVEYS if k in want for f in fs)


def available_bands() -> list[str]:
    import fsps

    return list(fsps.list_filters())


def filter_transmission(name: str) -> tuple[np.ndarray, np.ndarray]:
    """(wavelength [Angstrom], transmission) for a named FSPS filter."""
    import fsps

    filt = fsps.filters.get_filter(name)
    wave, trans = filt.transmission
    return np.asarray(wave, dtype=np.float64), np.asarray(
        trans, dtype=np.float64
    )


# Effective (transmission-weighted mean) wavelength in Angstrom, precomputed
# from each filter's real FSPS transmission curve. Used only to order colour
# indices blue-to-red in the UI (visage.ui.navigation_panel) — NOT used in
# any flux/magnitude calculation — so this module never needs to import fsps
# just to view an already-computed lightcone. Add an entry here (compute it
# once with filter_transmission()) for any other band you want ordered
# correctly; unlisted bands still work, just sort after the known ones.
EFFECTIVE_WAVELENGTH_A = {
    "galex_fuv": 1538.6,
    "galex_nuv": 2315.7,
    "sdss_u": 3561.8,
    "sdss_g": 4718.9,
    "sdss_r": 6185.2,
    "sdss_i": 7499.7,
    "sdss_z": 8961.5,
    "2mass_j": 12407.2,
    "2mass_h": 16513.7,
    "2mass_ks": 21655.4,
    "wise_w1": 33791.9,
    "wise_w2": 46293.0,
    "wise_w3": 123321.6,
    "wise_w4": 222532.7,
}

# AB absolute magnitude of the Sun, per band — converts a rest-frame absolute
# magnitude into a luminosity (Lsun) for the mass-to-light dropdown entries.
# Approximate (~0.05 mag), from Willmer (2018), ApJS 236, 47. Only bands
# listed here get a mass-to-light entry — add more only with a sourced value,
# never a guess (an M/L ratio is only as good as this zeropoint).
SOLAR_ABSMAG_AB = {
    "sdss_u": 6.39,
    "sdss_g": 5.11,
    "sdss_r": 4.65,
    "sdss_i": 4.53,
    "sdss_z": 4.50,
}

# Representative display colour (linear-sRGB, 0..1) for each filter, chosen to
# read as the band's own light: UV → violet, optical U/B/g/V/r → its hue,
# and the redward/IR bands (i, z, JHK, WISE) as deepening reds since the eye
# has no colour there. Used both for the single-band colourmap (black → this
# colour) and for stacking several bands into an additive false-colour
# composite ("mock image"). Keyed by the bare FSPS filter name.
BAND_COLOUR = {
    # ── UV (GALEX) ──
    "galex_fuv": (0.40, 0.00, 0.90),  # far-UV → deep violet
    "galex_nuv": (0.55, 0.20, 0.95),  # near-UV → violet
    # ── SDSS optical/NIR ──
    "sdss_u": (0.50, 0.10, 0.90),  # u → violet-blue
    "sdss_g": (0.10, 0.85, 0.25),  # g → green
    "sdss_r": (0.95, 0.20, 0.15),  # r → red
    "sdss_i": (0.80, 0.10, 0.08),  # i → deep red (near-IR)
    "sdss_z": (0.60, 0.06, 0.06),  # z → dark red (IR)
    # ── Johnson–Cousins optical/NIR ──
    "u": (0.50, 0.10, 0.90),
    "b": (0.10, 0.35, 1.00),  # B → blue
    "v": (0.65, 0.90, 0.15),  # V → green-yellow
    "r": (0.95, 0.20, 0.15),
    "i": (0.80, 0.10, 0.08),
    # ── 2MASS near-IR ──
    "2mass_j": (0.75, 0.15, 0.10),
    "2mass_h": (0.62, 0.10, 0.09),
    "2mass_ks": (0.52, 0.08, 0.07),
    # ── WISE mid-IR ──
    "wise_w1": (0.60, 0.18, 0.10),
    "wise_w2": (0.55, 0.22, 0.14),
    "wise_w3": (0.50, 0.28, 0.20),
    "wise_w4": (0.45, 0.30, 0.26),
}


def band_colour(name: str) -> tuple[float, float, float]:
    """Representative sRGB colour for a filter (bare name, e.g. "sdss_g").
    Falls back to a neutral warm grey for any band not tabulated above."""
    return BAND_COLOUR.get(name, (0.8, 0.75, 0.7))
