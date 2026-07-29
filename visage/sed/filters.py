from __future__ import annotations

import numpy as np

# Pre-checked default band set in the wizard's SED options (any FSPS filter
# name — see fsps.list_filters() — can be requested; this is only the
# default selection). UV + optical + near-IR, chosen to be meaningful with
# add_dust_emission=False (see ssp_grid.py) — mid-IR (e.g. WISE) would be
# dominated by dust emission we don't model, so it's deliberately excluded
# from the default even though FSPS can compute it if requested explicitly.
DEFAULT_BANDS = (
    "galex_fuv",
    "galex_nuv",
    "sdss_u",
    "sdss_g",
    "sdss_r",
    "sdss_i",
    "sdss_z",
    "2mass_j",
    "2mass_h",
    "2mass_ks",
)


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
