from __future__ import annotations

import numpy as np

# Empirically measured on this stack (python-fsps 0.4.7): the FIRST
# get_spectrum() call after (re)setting logzsol costs ~15-20s (builds the
# SSP grid for that metallicity); every subsequent get_spectrum() call at the
# SAME metallicity costs ~0.6ms (just an age interpolation). So the only way
# to make this tractable at lightcone scale is: few metallicity bins (outer,
# expensive), many age queries per bin (inner, cheap). Never re-set logzsol
# on a StellarPopulation that's already been queried — create a fresh one.


class SSPGrid:
    """One metallicity's SSP spectra, queryable at arbitrary ages (Gyr).

    All spectra share the same wavelength grid (an SSP-library property, not
    determined by the requested age or spectrum), so it's exposed once here.
    """

    def __init__(self, logzsol: float) -> None:
        import fsps

        self._sp = fsps.StellarPopulation(
            zcontinuous=1,
            sfh=0,  # SSP mode: single-age burst, 1 Msun formed
            logzsol=float(logzsol),
            dust_type=0,
            add_dust_emission=False,
        )
        self.logzsol = float(logzsol)
        self._cache: dict[float, np.ndarray] = {}
        wave, _ = self._sp.get_spectrum(
            tage=1.0
        )  # pays the ~18s one-time cost
        self.wave = np.asarray(wave, dtype=np.float64)  # Angstrom

    # FSPS treats tage=0.0 as a sentinel meaning "return the whole age grid"
    # (matches get_mags' documented default), not "age exactly zero" — so an
    # age at or below this floor is clamped to avoid silently getting back a
    # (n_ages, n_wave) array instead of the requested single spectrum.
    _MIN_AGE_GYR = 1.0e-4  # 100,000 years — a very young stellar population

    def spectrum_at_age(self, age_gyr: float) -> np.ndarray:
        """L_nu spectrum (L_sun/Hz per 1 Msun formed) at the given age."""
        key = round(max(float(age_gyr), self._MIN_AGE_GYR), 6)
        cached = self._cache.get(key)
        if cached is None:
            _, spec = self._sp.get_spectrum(tage=key)
            cached = np.asarray(spec, dtype=np.float64)
            self._cache[key] = cached
        return cached

    def spectra_at_ages(self, ages_gyr: np.ndarray) -> np.ndarray:
        """(n_ages, n_wave) matrix, one row per requested age, in order."""
        return np.stack([self.spectrum_at_age(a) for a in ages_gyr])


def metallicity_bin_edges(n_bins: int = 6) -> np.ndarray:
    """Fixed log10(Z/Zsun) bin edges spanning FSPS's supported range — fixed
    (not data-derived) so results are reproducible run to run."""
    return np.linspace(-2.0, 0.3, n_bins + 1)


def assign_metallicity_bins(
    logzsol: np.ndarray, edges: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Bin each galaxy's logzsol into one of len(edges)-1 bins (clamped to
    range). Returns (bin_index_per_galaxy, bin_center_logzsol)."""
    logzsol = np.clip(logzsol, edges[0], edges[-1] - 1e-9)
    idx = np.clip(np.digitize(logzsol, edges) - 1, 0, len(edges) - 2)
    centers = 0.5 * (edges[:-1] + edges[1:])
    return idx, centers
