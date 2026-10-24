from __future__ import annotations

import numpy as np

# Empirically measured on this stack (python-fsps 0.4.7): the FIRST
# get_spectrum() call after (re)setting logzsol costs ~15-20s (builds the
# SSP grid for that metallicity); every subsequent get_spectrum() call at the
# SAME metallicity is cheap. So: few metallicity nodes (outer, expensive),
# many age queries per node (inner, cheap). Never re-set logzsol on a
# StellarPopulation that's already been queried — create a fresh one.

# FSPS imf_type: 0 Salpeter (1955), 1 Chabrier (2003), 2 Kroupa (2001).
# SAGE26 is calibrated assuming a Chabrier IMF, as SAGE is (Croton et al.
# 2016, ApJS 222, 22), so the light must use it too.
IMF_CHABRIER = 1


class SSPGrid:
    """One metallicity's simple stellar populations (FSPS, 1 Msun formed).

    Besides single ages, it gives the mean spectrum of stars formed at a
    constant rate between two ages -- what one SAGE star-formation-history
    bin holds -- by integrating the SSP over age on FSPS's own age grid
    (as TAO does: Shamshiri et al. 2015, MNRAS 451, 2681; Bernyk et al.
    2016, ApJS 223, 9), rather than placing all of a bin's stars at one age.
    """

    def __init__(
        self,
        logzsol: float,
        dust: bool = False,
        dust2: float = 0.3,
        dust_emission: bool = False,
        imf_type: int = IMF_CHABRIER,
        nebular: bool = False,
    ) -> None:
        import fsps

        from visage.sed.nebular import kashino_inoue_logu

        # dust: a Calzetti (2000) starburst attenuation curve (dust_type=2)
        # with diffuse V-band optical depth `dust2`. Off by default —
        # dust_type=0 is a pure, unattenuated stellar SED.
        # dust_emission: re-emit the absorbed energy in the IR (Draine & Li
        # 2007), energy-balanced per SSP. Only meaningful WITH attenuation,
        # so it's forced off unless dust is on.
        self._sp = fsps.StellarPopulation(
            zcontinuous=1,
            sfh=0,  # SSP mode: single-age burst, 1 Msun formed
            imf_type=int(imf_type),
            logzsol=float(logzsol),
            dust_type=2 if dust else 0,
            dust2=float(dust2) if dust else 0.0,
            add_dust_emission=bool(dust and dust_emission),
            # Nebular lines and continuum in the spectra, for gas at this
            # metallicity (visage/sed/nebular.py).
            add_neb_emission=bool(nebular),
            gas_logz=float(logzsol),
            # (U for a main-sequence galaxy, sSFR 1e-10/yr at 1e10 Msun;
            # the photometry's own line luminosities use each galaxy's.)
            gas_logu=float(
                kashino_inoue_logu(0.0142 * 10 ** float(logzsol), 1e-10, 1e10)
            ),
        )
        self.nebular = bool(nebular)
        self.logzsol = float(logzsol)
        self.imf_type = int(imf_type)
        self.libraries = tuple(
            s.decode() if isinstance(s, bytes) else str(s)
            for s in self._sp.libraries
        )
        self._cache: dict[float, np.ndarray] = {}
        # The whole age grid at once (pays the one-time cost).
        wave, spec = self._sp.get_spectrum(tage=0.0)
        self.wave = np.asarray(wave, dtype=np.float64)  # Angstrom
        ages = 10.0 ** np.asarray(self._sp.log_age, dtype=np.float64) / 1e9
        spec = np.asarray(spec, dtype=np.float64)  # (n_age, n_wave)
        # Cumulative integral over age (Gyr), from age 0 (the youngest SSP
        # held constant below FSPS's first age, ~0.3 Myr).
        self._ages = np.concatenate([[0.0], ages])
        spec = np.vstack([spec[:1], spec])
        da = np.diff(self._ages)[:, None]
        steps = 0.5 * (spec[1:] + spec[:-1]) * da
        self._cum = np.vstack(
            [np.zeros((1, spec.shape[1])), np.cumsum(steps, 0)]
        )

    def _cum_at(self, age: float) -> np.ndarray:
        a = float(np.clip(age, 0.0, self._ages[-1]))
        i = int(
            np.clip(np.searchsorted(self._ages, a) - 1, 0, len(self._ages) - 2)
        )
        f = (a - self._ages[i]) / (self._ages[i + 1] - self._ages[i])
        return self._cum[i] + f * (self._cum[i + 1] - self._cum[i])

    def mean_spectrum(self, age_lo: float, age_hi: float) -> np.ndarray:
        """L_nu (L_sun/Hz per 1 Msun formed) of stars formed at a constant
        rate between ages age_lo and age_hi (Gyr)."""
        lo, hi = max(float(age_lo), 0.0), max(float(age_hi), 0.0)
        if hi - lo < 1e-6:
            return self.spectrum_at_age(lo)
        return (self._cum_at(hi) - self._cum_at(lo)) / (hi - lo)

    def mean_spectra(self, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        """(n, n_wave): mean_spectrum for each (lo, hi) pair."""
        return np.stack(
            [self.mean_spectrum(a, b) for a, b in zip(lo, hi, strict=True)]
        )

    # FSPS treats tage=0.0 as a sentinel meaning "return the whole age grid"
    # (matches get_mags' documented default), not "age exactly zero" — so an
    # age at or below this floor is clamped.
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


# Metallicity nodes (log Z/Zsun) that every galaxy's spectrum is linearly
# interpolated between -- spanning SAGE26's stellar metallicities within
# the MIST range (-2.5 to +0.5).
METALLICITY_NODES = np.array(
    [-2.0, -1.5, -1.0, -0.7, -0.4, -0.2, 0.0, 0.2, 0.4]
)


def metallicity_weights(
    logzsol: np.ndarray, nodes: np.ndarray = METALLICITY_NODES
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Each galaxy's two bracketing nodes and their weights (linear in log
    Z): returns (lower node index, upper node index, upper weight)."""
    z = np.clip(logzsol, nodes[0], nodes[-1])
    hi = np.clip(np.searchsorted(nodes, z, side="right"), 1, len(nodes) - 1)
    lo = hi - 1
    w = (z - nodes[lo]) / (nodes[hi] - nodes[lo])
    return lo, hi, w


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
