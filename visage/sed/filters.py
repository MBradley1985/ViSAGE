from __future__ import annotations

import numpy as np

# Pre-checked default band set in the wizard's SED options (any FSPS filter
# name — see fsps.list_filters() — can be requested; this is only the
# default selection).
DEFAULT_BANDS = ("sdss_u", "sdss_g", "sdss_r", "sdss_i", "sdss_z")


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
