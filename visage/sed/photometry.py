"""Synthetic broadband photometry for a LightSAGE lightcone.

Forward-models AB magnitudes per galaxy from its actual star-formation
history (SFHMassDisk/SFHMassBulge), using FSPS (Conroy, Gunn & White 2009,
ApJ 699, 486; Conroy & Gunn 2010, ApJ 712, 833) as the stellar population
synthesis engine. This is SED *synthesis* from known simulated truth, not
inverse fitting of observed data.

How each galaxy's light is built (references in docs/physics/photometry.md):
  - Star-formation history: SAGE26 files the stars formed between
    snapshots k-1 and k in bin k (older outputs, k and k+1), as the mass
    that survives recycling ((1 - R) of what formed). Each bin is turned
    back into mass formed
    (/ (1 - R), R = the run's RecycleFraction) and spread at a constant
    rate over its own time span, integrating the SSPs over age (as TAO:
    Shamshiri et al. 2015, MNRAS 451, 2681). The youngest stars (< 100 Myr)
    come from the galaxy's current SFR (SfrDisk + SfrBulge).
  - IMF: Chabrier (2003), as SAGE26 assumes.
  - Metallicity: each bin's own (MHMetalsDisk / MHMetalsBulge, with
    SAGE26's SaveFullMH), or else one present-day value per galaxy
    (MetalsStellarMass / StellarMass), the spectrum linearly interpolated
    in log Z between fixed SSP nodes.
  - Observed frame: K-corrected at each galaxy's own observed redshift
    (interpolated from a fine redshift grid within its snapshot shell),
    with luminosity distance D_L = (1 + z_obs) D_C(z_cos) (peculiar
    velocities included; Davis et al. 2011, ApJ 741, 67).
  - Dust: none by default (see --dust).
  - Intergalactic absorption: Madau (1995) on the observed frame
    (visage/sed/igm.py).

Scale: a lightcone can carry millions of galaxies, and FSPS is far too slow
to call per-galaxy. So galaxies are grouped by snapshot; each group's
composite spectra are matrix multiplies (mass per bin x cached bin spectra),
one per metallicity node, summed, then projected through the filters.

Output: new `mag_rest_<band>` / `mag_obs_<band>` datasets written into the
same lightcone HDF5 file (float32, AB magnitudes), with the settings used
recorded in the file's `PhotometryHeader` attributes.
"""

from __future__ import annotations

import argparse
import functools
import sys
from pathlib import Path
from collections.abc import Callable

import h5py
import numpy as np

from visage.io.galaxy_reader import sfh_step_offset
from visage.system import native_path
from visage.sed.cosmology import (
    MPC_TO_CM,
    age_at_scale_factor,
    luminosity_distance_mpc,
)
from visage.sed import igm
from visage.sed.filters import DEFAULT_BANDS, filter_transmission
from visage.sed.ssp_grid import (
    IMF_CHABRIER,
    METALLICITY_NODES,
    SSPGrid,
    metallicity_weights,
)

L_SUN_ERG_S = 3.828e33  # erg/s, IAU 2015 nominal solar luminosity
PC_TO_CM = 3.0856775814913673e18
# Bounds peak memory for the (chunk, n_wave) composite-spectrum matmul —
# a full (N_galaxies, 5994) array would be tens of GB for a real lightcone.
MAX_GROUP_CHUNK = 50_000

ProgressCB = Callable[[int, int, int, int], None]  # (done, total, snap, znode)

# The youngest stars of each galaxy (formed in the last YOUNG_GYR) come from
# its current SFR rather than its last SFH bin spread evenly: that bin
# spans ~0.3-0.6 Gyr at low z, which would dilute the newest stars that
# dominate the UV.
YOUNG_GYR = 0.1
# Redshift points per snapshot shell at which the K-correction shape is
# computed (interpolated to each galaxy's own redshift between them).
N_KZ = 6


def _trapz_weights(x: np.ndarray) -> np.ndarray:
    """Per-point trapezoidal weights for a (possibly non-uniform) grid x,
    such that sum(f * weights) approximates trapz(f, x)."""
    w = np.zeros_like(x)
    w[1:-1] = (x[2:] - x[:-2]) / 2.0
    w[0] = (x[1] - x[0]) / 2.0
    w[-1] = (x[-1] - x[-2]) / 2.0
    return w


class _FilterProjector:
    """Precomputes everything about one band that doesn't depend on the
    spectrum or redshift, then projects batches of rest-frame composite
    spectra through it at an arbitrary (small, per-group) redshift shift.

    Derivation (photon-counting AB magnitude convention, matching FSPS's own
    filter curves): for a rest-frame specific luminosity L_nu,rest(lambda)
    [L_sun/Hz] observed at redshift z through a fixed observed-frame filter
    R(lambda_obs), substituting lambda_rest = lambda_obs/(1+z) gives

        f_nu_eff(z) = (1+z) * [ ∫ L_nu,rest(lambda) R((1+z) lambda) dlambda/lambda ]
                              / [ ∫ R(lambda_obs) dlambda_obs/lambda_obs ]

    i.e. shift the FILTER (evaluated at the spectrum's own fixed wavelength
    grid), not the spectrum — the ``project()`` numerator below — then the
    caller applies the (1+z) prefactor and the distance conversion (which
    differ between rest-frame/10pc and observed-frame/luminosity-distance).
    z=0 reduces this to the ordinary rest-frame projection.
    """

    def __init__(self, band: str, ssp_wave: np.ndarray) -> None:
        filt_wave, filt_trans = filter_transmission(band)
        self.band = band
        self._filt_wave = filt_wave
        self._filt_trans = filt_trans
        self._ssp_wave = ssp_wave
        self._dw = _trapz_weights(ssp_wave)
        # Filter-only integral — independent of the spectrum and of redshift.
        self._denom = np.trapezoid(filt_trans / filt_wave, filt_wave)

    def project(self, spectra: np.ndarray, z: float) -> np.ndarray:
        """f_nu_eff (L_sun/Hz per Msun formed) for a batch of rest-frame
        composite spectra (n_obj, n_wave) — NOT yet distance/prefactor
        corrected; see the class docstring."""
        shifted_r = np.interp(
            self._ssp_wave * (1.0 + z),
            self._filt_wave,
            self._filt_trans,
            left=0.0,
            right=0.0,
        )
        if z > 0 and self._filt_wave[0] / (1.0 + z) < igm.LY_ALPHA_A:
            shifted_r = shifted_r * igm.transmission(self._ssp_wave, z)
        weights = shifted_r / self._ssp_wave * self._dw
        # Verified benign: this matmul reliably trips spurious divide/
        # overflow/invalid FPE flags on Apple's Accelerate BLAS backend
        # without corrupting the result (checked element-by-element against
        # an independent computation) — suppressed rather than left as
        # alarming noise on every run.
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            return spectra @ weights / self._denom


@functools.lru_cache(maxsize=8)
def _ssp_grid(logzsol, dust, dust2, dust_emission, imf_type, nebular):
    """An SSPGrid, kept: each costs FSPS ~15-20 s to build, and the
    viewer's one-galaxy spectra (visage/sed/spectrum.py) reuse them."""
    return SSPGrid(
        logzsol,
        dust=dust,
        dust2=dust2,
        dust_emission=dust_emission,
        imf_type=imf_type,
        nebular=nebular,
    )


def _mag_from_fnu(f_nu: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        mag = -2.5 * np.log10(np.maximum(f_nu, 1e-300)) - 48.6
    return mag.astype(np.float32)


def _resolve_alist(
    header_val: str,
    override: str | Path | None,
    lightcone_path: Path,
) -> Path | None:
    """Find the scale-factor list. An explicit ``override`` (the absolute
    ALIST_FILE the wizard already has) wins; otherwise the header value is
    tried as-is (absolute or CWD-relative) and, if relative, resolved against
    the lightcone file's directory and its ancestors — since the header path
    is relative to the original SAGE run dir, not wherever we run now.
    Returns the first existing path, or None."""
    candidates: list[Path] = []
    if override:
        candidates.append(native_path(override))
    hv = native_path(header_val)
    candidates.append(hv)
    if not hv.is_absolute():
        base = lightcone_path.resolve().parent
        for anc in [base, *base.parents]:
            candidates.append(anc / hv)
        candidates.append(base / hv.name)  # last resort: basename only
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def _bin_spectra(grid, age_lo, age_hi, dt_y, width, bc_age) -> dict:
    """One metallicity's spectra for a snapshot: of each bin, of the last
    bin's stars younger than `dt_y` outside and inside the birth clouds
    (younger than `bc_age`, 0 without clouds), and of its older stars."""
    young = grid.mean_spectrum(0.0, dt_y)
    bc = grid.mean_spectrum(0.0, bc_age) if bc_age > 0 else young
    return {
        "bins": grid.mean_spectra(age_lo, age_hi),
        "bc": bc,
        "bc_frac": bc_age / dt_y if dt_y > 0 else float(bc_age > 0),
        "after_bc": (
            grid.mean_spectrum(bc_age, dt_y)
            if bc_age > 0 and dt_y > bc_age
            else bc
        ),
        "rest": grid.mean_spectrum(dt_y, width) if width > dt_y else young,
    }


def _stars(wts_in, sfr, spec, last, dt_y):
    """Rest-frame light (chunk, n_wave, L_sun/Hz) of stars formed as
    `wts_in` (Msun per bin), the youngest of bin `last` (if any) from the
    current SFR `sfr`: that outside the birth clouds, and that inside."""
    wts = wts_in.copy()
    m_young = np.zeros(len(wts))
    m_rest = np.zeros(len(wts))
    if last is not None:
        m_last = wts[:, last]
        m_young = np.minimum(sfr * dt_y * 1e9, m_last)
        m_rest = m_last - m_young
        wts[:, last] = 0.0
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        older = (
            wts @ spec["bins"]
            + (m_young * (1 - spec["bc_frac"]))[:, None] * spec["after_bc"]
            + m_rest[:, None] * spec["rest"]
        )
        return older, (m_young * spec["bc_frac"])[:, None] * spec["bc"]


def compute_photometry(
    path: str | Path,
    bands: tuple[str, ...] = DEFAULT_BANDS,
    frame: str = "both",  # "rest" | "obs" | "both"
    use_metallicity: bool = True,
    dust: bool = False,
    dust2: float = 0.3,
    dust_emission: bool = False,
    alist: str | Path | None = None,
    progress_cb: ProgressCB | None = None,
    rows: np.ndarray | None = None,
    imf_type: int = IMF_CHABRIER,
    recycle_fraction: float | None = None,
    dust_model: str | None = None,
    disk_bulge: bool = False,
    spectra_out: dict | None = None,
    lines: bool = False,
    metal_history: bool = True,
) -> dict[str, np.ndarray]:
    """Compute AB magnitudes for every galaxy in a lightcone HDF5 file
    (or just `rows`, sorted row indices).

    ``alist`` overrides the scale-factor list. If omitted, the path recorded
    in the lightcone header (``FileWithSnapList``) is used — but that can be a
    relative path (relative to the original SAGE run dir) that no longer
    resolves, so passing the absolute a_list here is more reliable.

    ``use_metallicity`` (default True) uses each galaxy's own stellar
    metallicity (Z = MetalsStellarMass / StellarMass); False forces solar.
    ``metal_history`` (default True) uses each star-formation bin's own
    metallicity (MHMetalsDisk / MHMetalsBulge) where the file has them.
    ``dust`` (default False) applies a Calzetti starburst attenuation of
    V-band optical depth ``dust2`` to the synthesized spectra.
    ``dust_emission`` (default False) additionally re-emits the absorbed
    energy in the IR (Draine & Li 2007) — only with ``dust`` on.
    ``recycle_fraction`` defaults to the run's own (header RecycleFraction).
    ``disk_bulge`` also gives the disk's and the bulge's own magnitudes
    (``disk_mag_*`` / ``bulge_mag_*``; the totals are their sum).
    With "charlot_fall" dust, ``dust_emission`` re-emits each galaxy's
    absorbed light in the infrared (Draine & Li 2007, energy balance, at
    the U_min of its L_dust / M_dust), ``LDust`` (L_sun) is each galaxy's
    dust luminosity and ``DustUmin`` that U_min.
    ``lines``: nebular emission (lines and continuum) in the spectra, and
    each galaxy's emission lines from its HII regions (visage/sed/
    nebular.py) and AGN (visage/sed/agn.py) as ``LineLum_<line>`` (erg/s,
    through its dust), ``LineLumIntr_<line>`` (erg/s, no dust),
    ``LineLumAGN_<line>`` (the AGN's, no dust) and ``LineFlux_<line>``
    (erg/s/cm^2, observed).
    ``spectra_out``: a dict to fill with rest-frame spectra (L_sun/Hz) of
    every galaxy -- "wave" (Angstrom), "observed" (through the dust, with
    its emission and any AGN's lines), "intrinsic" (the stars alone), with
    ``disk_bulge`` "disk" and "bulge", and with ``lines`` "agn" -- for a few ``rows`` only (n x 6000 floats each).
    ``dust_model``: "none", "calzetti" (the ``dust``/``dust2`` screen) or
    "charlot_fall": each galaxy's own dust (Dusty-SAGE equilibrium) in
    birth clouds and a diffuse ISM slab at its inclination (see
    visage/sed/dust.py). Default: "calzetti" if ``dust`` else "none".

    Returns a dict of ``mag_rest_<band>`` / ``mag_obs_<band>`` -> (N,)
    float32 arrays, aligned to the file's row order (or to ``rows``); the
    settings used are under the key ``"_settings"``.
    """
    path = Path(path)
    sel = slice(None) if rows is None else np.asarray(rows)
    with h5py.File(path, "r", locking=False) as f:

        def get(name: str) -> np.ndarray | None:
            return np.asarray(f[name][sel]) if name in f else None

        stellar_mass_raw = get("StellarMass")
        if stellar_mass_raw is None:
            raise KeyError(f"{path} has no StellarMass — not a lightcone file")
        n = len(stellar_mass_raw)
        sfh_disk = get("SFHMassDisk")
        sfh_bulge = get("SFHMassBulge")
        if sfh_disk is None or sfh_bulge is None:
            raise KeyError(
                f"{path} has no SFHMassDisk/SFHMassBulge — SED synthesis "
                "needs the full star-formation history"
            )
        metals = get("MetalsStellarMass")
        bulge_mass = get("BulgeMass")
        mh_disk = get("MHMetalsDisk")
        mh_bulge = get("MHMetalsBulge")
        snapnum = get("SnapNum")
        if snapnum is None:
            raise KeyError(f"{path} has no SnapNum")
        z_cos = get("redshift_cosmological")
        z_obs = get("redshift_observed")
        if z_cos is None:
            z_cos = z_obs
        if z_cos is None:
            raise KeyError(f"{path} has no redshift field")
        if z_obs is None:
            z_obs = z_cos
        sfr_parts = {}
        for name in ("SfrDisk", "SfrBulge"):
            v = get(name)
            sfr_parts[name] = (
                v.astype(np.float64) if v is not None else np.zeros(n)
            )  # Msun/yr
        sfr_now = sfr_parts["SfrDisk"] + sfr_parts["SfrBulge"]
        dist = get("distance")  # comoving, Mpc/h
        if dust_model is None:
            dust_model = "calzetti" if dust else "none"
        cf = dust_model == "charlot_fall"
        if cf or lines:
            cold = get("ColdGas")
            metals_cold = get("MetalsColdGas")
            disk_r = get("DiskRadius")
        if lines:
            bh_mass = get("BlackHoleMass")
            quasar_acc = get("QuasarModeBHaccretionMass")
            galaxy_id = get("GalaxyIndex")
            # Radio-mode accretion since the last snapshot (newer SAGE26);
            # older outputs only have its power, Heating.
            radio_acc = get("RadioModeBHaccretionMass")
            radio_heating = get("Heating")
            # The time step, in h^-1 Myr (SAGE26's internal time unit).
            step_myr = get("dT")
        if cf:
            h2 = get("H2gas")
            spin = np.column_stack([get(f"Spin{c}") for c in "xyz"])
            pos = np.column_stack([get(f"Pos{c}") for c in "xyz"])

        # From the file, not `rows`: a quiescent galaxy alone can't tell.
        first = slice(0, 20_000)
        sfh_shift = sfh_step_offset(
            f["SFHMassDisk"][first] + f["SFHMassBulge"][first],
            f["SnapNum"][first],
        )

        if (
            "SageOutputHeader" not in f
            or "Simulation" not in f["SageOutputHeader"]
        ):
            raise KeyError(f"{path} has no SageOutputHeader/Simulation")
        sim = f["SageOutputHeader"]["Simulation"].attrs
        hubble_h = float(sim["hubble_h"])
        omega_m = float(sim["omega_matter"])
        omega_l = float(sim["omega_lambda"])
        header_alist = sim["FileWithSnapList"]
        if isinstance(header_alist, bytes):
            header_alist = header_alist.decode()
        run = f["SageOutputHeader"].get("Runtime")
        yield_ = (
            float(run.attrs["Yield"])
            if run is not None and "Yield" in run.attrs
            else 0.025
        )
        if recycle_fraction is None:
            recycle_fraction = (
                float(run.attrs["RecycleFraction"])
                if run is not None and "RecycleFraction" in run.attrs
                else 0.43
            )

    alist_path = _resolve_alist(header_alist, alist, path)
    if alist_path is None:
        tried = [alist, header_alist] if alist else [header_alist]
        raise FileNotFoundError(
            "Scale-factor list not found (needed to convert SFH bins to "
            "stellar ages). The lightcone header records it as a relative "
            f"path ({header_alist!r}); pass --alist with its absolute path. "
            f"Tried: {', '.join(str(t) for t in tried if t)}"
        )

    mfac = 1.0e10 / max(hubble_h, 1e-6)
    stellar_mass = stellar_mass_raw.astype(np.float64) * mfac
    metals_mass = (
        metals.astype(np.float64) * mfac if metals is not None else np.zeros(n)
    )
    # (n, n_bins) Msun FORMED per SFH bin (disk + bulge): SAGE stores what
    # survives recycling, (1 - R) of it.
    sfh_disk_f = sfh_disk.astype(np.float64) * mfac / (1.0 - recycle_fraction)
    sfh_bulge_f = (
        sfh_bulge.astype(np.float64) * mfac / (1.0 - recycle_fraction)
    )
    if bulge_mass is not None:
        # SAGE26's bulge history holds only stars formed in the bulge; the
        # disk stars instabilities and mergers move into it stay in the
        # disk's (model_mergers.c). Move the share of the disk's history
        # that makes the bulge's total its BulgeMass -- those stars taken
        # to have the disk's age mix (SAGE26 doesn't record when they moved).
        sd = sfh_disk_f.sum(1)
        need = bulge_mass.astype(np.float64) * mfac / (1.0 - recycle_fraction)
        f_move = np.clip(
            (need - sfh_bulge_f.sum(1)) / np.maximum(sd, 1e-30), 0.0, 1.0
        )
        moved = f_move[:, None] * sfh_disk_f
        sfh_disk_f = sfh_disk_f - moved
        sfh_bulge_f = sfh_bulge_f + moved
    sfh_formed = sfh_disk_f + sfh_bulge_f
    n_bins = sfh_formed.shape[1]
    prefixes = ("", "disk_", "bulge_") if disk_bulge else ("",)

    dust_info = {}
    if cf:
        from visage.sed import dust as dm

        cold_m = cold.astype(np.float64) * mfac
        delta = dm.cold_dust_ratio(
            cold_m,
            metals_cold.astype(np.float64) * mfac,
            h2.astype(np.float64) * mfac,
            sfr_now,
            recycle=recycle_fraction,
            yield_=yield_,
        )
        dust_mass = delta * cold_m
        cos_i = dm.cos_inclination(spin, pos)
        radius_kpc = disk_r * 1e3 / hubble_h
        tau_v, eta_v = dm.tau_eta_ism(
            dm.sigma_dust(dust_mass, radius_kpc, cos_i)
        )
        tau_birth = dm.tau_bc(delta, cold_m, radius_kpc, tau_v)
        dust_info = {
            "DustMassCold": dust_mass.astype(np.float32),
            "DustToGas": delta.astype(np.float32),
            "TauV_ISM": dm.tau_eta_ism(
                dm.sigma_dust(dust_mass, radius_kpc, 1.0)
            )[0].astype(np.float32),
            "TauV_BC": tau_birth.astype(np.float32),
            "CosInclination": cos_i.astype(np.float32),
        }
        dust = False  # (the SSPs stay unattenuated; dust is applied here)

    import fsps

    zsun = fsps.StellarPopulation(zcontinuous=1, sfh=0).solar_metallicity
    has_history = (
        use_metallicity
        and metal_history
        and mh_disk is not None
        and mh_bulge is not None
    )
    if use_metallicity:
        nodes = METALLICITY_NODES
        z_frac = np.where(
            stellar_mass > 0,
            metals_mass / np.maximum(stellar_mass, 1e-30),
            0.0,
        )
        log_z_now = np.log10(np.clip(z_frac, 1e-6, 0.1) / zsun)[:, None]
    else:
        nodes = np.array([0.0])
        log_z_now = np.zeros((n, 1))

    def bin_log_z(metals, mass):
        """log Z/Zsun of each bin's stars (n, n_bins); empty bins, which
        hold no light, take the present-day value."""
        with np.errstate(divide="ignore", invalid="ignore"):
            z = np.clip(metals.astype(np.float64) / mass, 1e-6, 0.1)
            return np.where(mass > 0, np.log10(z / zsun), log_z_now)

    # Each component: (Msun formed per bin, current SFR, log Z of its bins
    # (n, n_bins) or, without a history, of the galaxy (n, 1)).
    if disk_bulge:
        log_z_d = log_z_b = log_z_now
        if has_history:
            log_z_d = bin_log_z(mh_disk, sfh_disk.astype(np.float64))
            log_z_b = bin_log_z(mh_bulge, sfh_bulge.astype(np.float64))
        components = {
            "disk_": (sfh_disk_f, sfr_parts["SfrDisk"], log_z_d),
            "bulge_": (sfh_bulge_f, sfr_parts["SfrBulge"], log_z_b),
        }
    else:
        log_z = log_z_now
        if has_history:
            log_z = bin_log_z(
                mh_disk.astype(np.float64) + mh_bulge,
                sfh_disk.astype(np.float64) + sfh_bulge,
            )
        components = {"": (sfh_formed, sfr_now, log_z)}

    def node_share(log_z_c, zi):
        """Each bin's share of the population at node zi."""
        if len(nodes) == 1:
            return np.ones_like(log_z_c)
        lo, hi, w = metallicity_weights(log_z_c, nodes)
        return np.where(lo == zi, 1.0 - w, 0.0) + np.where(hi == zi, w, 0.0)

    a_list = np.loadtxt(alist_path)[: n_bins + 1]
    t_snap = age_at_scale_factor(a_list, hubble_h, omega_m, omega_l)  # Gyr

    # Luminosity distance, peculiar velocities included (Davis et al. 2011):
    # D_L = (1 + z_obs) D_C(z_cos).
    if dist is not None:
        d_c_cm = dist.astype(np.float64) / hubble_h * MPC_TO_CM
        d_l_cm = (1.0 + z_obs) * d_c_cm
    else:
        d_l_cm = (
            luminosity_distance_mpc(z_cos, hubble_h, omega_m, omega_l)
            * MPC_TO_CM
        )
    d10_cm = 10.0 * PC_TO_CM

    want_rest = frame in ("rest", "both")
    want_obs = frame in ("obs", "both")
    if not want_rest and not want_obs:
        raise ValueError(
            f"frame must be 'rest', 'obs', or 'both', got {frame!r}"
        )

    # Fluxes are summed over the metallicity nodes, magnitudes at the end.
    flux: dict[str, np.ndarray] = {}
    for pre in prefixes:
        for band in bands:
            if want_rest:
                flux[f"{pre}mag_rest_{band}"] = np.zeros(n)
            if want_obs:
                flux[f"{pre}mag_obs_{band}"] = np.zeros(n)
    re_emit = cf and dust_emission
    l_dust = np.zeros(n)
    dust_umin = np.zeros(n)
    if lines:
        from visage.sed import nebular as nb

        line_wave = np.array([w[0] for w, _ in nb.LINES.values()])
        line_intr = np.zeros((n, len(nb.LINES)))
        line_seen = np.zeros((n, len(nb.LINES)))
        z_gas = np.where(
            cold > 0,
            metals_cold.astype(np.float64)
            / np.maximum(cold.astype(np.float64), 1e-30),
            1e-4,
        )
        ssfr_now = sfr_now / np.maximum(stellar_mass, 1.0)
        gas_logu = nb.kashino_inoue_logu(z_gas, ssfr_now, stellar_mass)
        gas_log_ne = nb.kashino_inoue_log_ne(ssfr_now, stellar_mass)
        # L_sun per Msun/yr of current star formation (Gutkin et al. 2016).
        hii_per_sfr = (
            nb.hii_lines_per_sfr(z_gas, gas_logu, gas_log_ne) / L_SUN_ERG_S
        )

    has_light = stellar_mass > 0
    unique_snaps = np.unique(snapnum)
    used_nodes = [
        zi
        for zi in range(len(nodes))
        if any((node_share(c[2], zi) > 0).any() for c in components.values())
    ]
    n_steps = len(used_nodes) + len(unique_snaps)
    grids = {}
    for k_done, zi in enumerate(used_nodes, 1):
        grids[zi] = _ssp_grid(
            float(nodes[zi]),
            bool(dust),
            float(dust2),
            bool(dust_emission),
            int(imf_type),
            bool(lines),
        )
        if progress_cb is not None:
            progress_cb(k_done, n_steps, -1, int(zi))
    grid = grids[used_nodes[0]]
    wave = grid.wave
    libraries = grid.libraries
    projectors = {b: _FilterProjector(b, wave) for b in bands}
    nu_w = dm.frequency_weights(wave) if re_emit else None

    for k_done, snap in enumerate(unique_snaps, len(used_nodes) + 1):
        idx = np.where(has_light & (snapnum == snap))[0]
        s = int(snap)
        if len(idx) == 0:
            if progress_cb is not None:
                progress_cb(k_done, n_steps, s, -1)
            continue
        t_now = t_snap[min(s, len(t_snap) - 1)]
        # Ages of the stars in each bin (see sfh_step_offset); empty after
        # the galaxy's own snapshot.
        k = np.arange(n_bins) - sfh_shift
        t_lo = t_snap[np.clip(k, 0, len(t_snap) - 1)]
        t_hi = t_snap[np.clip(k + 1, 0, len(t_snap) - 1)]
        age_lo = np.clip(t_now - t_hi, 0.0, None)
        age_hi = np.clip(t_now - t_lo, 0.0, None)
        # The last bin, split: its youngest YOUNG_GYR from the current SFR,
        # the rest spread over the remainder.
        last = s - 1 + sfh_shift
        width = age_hi[last] - age_lo[last] if 0 <= last < n_bins else 0.0
        dt_y = min(YOUNG_GYR, width)
        # Stars younger than 10 Myr sit in their birth clouds.
        bc_age = (
            (min(dm.BC_AGE_GYR, dt_y) if dt_y > 0 else dm.BC_AGE_GYR)
            if cf
            else 0.0
        )
        specs = {
            zi: _bin_spectra(g, age_lo, age_hi, dt_y, width, bc_age)
            for zi, g in grids.items()
        }
        z_shell = z_obs[idx]
        kz = np.linspace(z_shell.min(), z_shell.max(), N_KZ)
        if kz[-1] - kz[0] < 1e-6:
            kz = kz[:1]
        has_last = 0 <= last < n_bins and width > 0

        step = 4000 if cf else MAX_GROUP_CHUNK
        for start in range(0, len(idx), step):
            ci = idx[start : start + step]
            parts = {}
            for pre, (mass, sfr, log_z_c) in components.items():
                older = np.zeros((len(ci), len(wave)))
                young = np.zeros_like(older) if cf else None
                lz = log_z_c[ci]
                for zi in used_nodes:
                    share = np.broadcast_to(
                        node_share(lz, zi), (len(ci), n_bins)
                    )
                    use = np.flatnonzero(share.any(axis=1))
                    if len(use) == 0:
                        continue
                    o, y = _stars(
                        mass[ci[use]] * share[use],
                        sfr[ci[use]] * (share[use, last] if has_last else 0),
                        specs[zi],
                        last if has_last else None,
                        dt_y,
                    )
                    older[use] += o
                    if cf:
                        young[use] += y
                parts[pre] = (older, young)
            if cf:
                t_ism = dm.ism_transmission(wave, tau_v[ci], eta_v[ci])
                t_bc = dm.bc_transmission(wave, tau_birth[ci])
                spectra = {
                    pre: t_ism * (o + y * t_bc)
                    for pre, (o, y) in parts.items()
                }
                unseen = {
                    pre: o + y for pre, (o, y) in parts.items()
                }  # the stars alone
            else:
                spectra = {pre: o for pre, (o, _) in parts.items()}
                unseen = spectra
            zg = z_obs[ci]
            if re_emit:
                # All of a galaxy's dust shares one radiation field.
                with np.errstate(
                    over="ignore", invalid="ignore", divide="ignore"
                ):
                    absorbed = {
                        pre: (unseen[pre] - spectra[pre]) @ nu_w
                        for pre in parts
                    }
                total = sum(absorbed.values())
                u_min = dm.umin_from_luminosity(total, dust_mass[ci])
                l_dust[ci] = total
                dust_umin[ci] = u_min
                ir = dm.emission_spectra(wave, u_min)
                for pre, lum in absorbed.items():
                    spectra[pre] = spectra[pre] + lum[:, None] * ir
            if disk_bulge:
                spectra[""] = spectra["disk_"] + spectra["bulge_"]
            if lines and has_last:
                # Lines from the young stars (current SFR), in each
                # galaxy's own gas, through its birth cloud and ISM.
                # (the rate of the young stars the spectra hold)
                sfr_y = np.minimum(
                    sfr_now[ci],
                    sfh_formed[ci, last] / max(dt_y * 1e9, 1.0),
                )
                intr = sfr_y[:, None] * hii_per_sfr[ci]
                seen = intr
                if cf:
                    seen = (
                        intr
                        * dm.ism_transmission(line_wave, tau_v[ci], eta_v[ci])
                        * dm.bc_transmission(line_wave, tau_birth[ci])
                    )
                line_intr[ci] = intr
                line_seen[ci] = seen
            if spectra_out is not None:
                _keep_spectra(
                    spectra_out, wave, ci, spectra, sum(unseen.values()), n
                )
            for pre, composite in spectra.items():
                for band in bands:
                    proj = projectors[band]
                    if want_rest:
                        f_nu = (
                            proj.project(composite, 0.0)
                            * L_SUN_ERG_S
                            / (4 * np.pi * d10_cm**2)
                        )
                        flux[f"{pre}mag_rest_{band}"][ci] = f_nu
                    if want_obs:
                        # K-correction shape at each galaxy's own z_obs.
                        fk = np.stack(
                            [
                                (1.0 + z) * proj.project(composite, z)
                                for z in kz
                            ]
                        )  # (n_kz, chunk)
                        if len(kz) > 1:
                            j = np.clip(
                                np.searchsorted(kz, zg) - 1, 0, len(kz) - 2
                            )
                            t = np.clip(
                                (zg - kz[j]) / (kz[j + 1] - kz[j]), 0, 1
                            )
                            cols = np.arange(len(ci))
                            f_eff = (1 - t) * fk[j, cols] + t * fk[j + 1, cols]
                        else:
                            f_eff = fk[0]
                        f_nu = (
                            f_eff * L_SUN_ERG_S / (4 * np.pi * d_l_cm[ci] ** 2)
                        )
                        flux[f"{pre}mag_obs_{band}"][ci] = f_nu

        if progress_cb is not None:
            progress_cb(k_done, n_steps, s, -1)

    out: dict = {}
    for name, f_nu in flux.items():
        mag = _mag_from_fnu(f_nu)
        mag[~has_light] = np.nan
        out[name] = mag
    out.update(dust_info)
    if re_emit:
        out["LDust"] = l_dust.astype(np.float32)
        out["DustUmin"] = dust_umin.astype(np.float32)
    if lines:
        # The AGN's narrow-line region (visage/sed/agn.py), through the
        # diffuse ISM's dust (not the birth clouds).
        from visage.sed import agn as ag

        zeros = np.zeros(n)
        mdot_q = np.zeros(n)
        mdot_r = None
        if step_myr is not None:
            # dT is in h^-1 Myr: years = dT / h * 1e6.
            step_yr = np.maximum(
                step_myr.astype(np.float64) / hubble_h * 1e6, 1.0
            )
            if quasar_acc is not None:
                # Without an id, the mean over the step.
                mdot_q = quasar_acc.astype(np.float64) * mfac / step_yr
                if galaxy_id is not None:
                    mdot_q = ag.burst_rate(
                        quasar_acc.astype(np.float64) * mfac,
                        ag.burst_phase(galaxy_id, snapnum) * step_yr / 1e6,
                        (
                            bh_mass.astype(np.float64) * mfac
                            if bh_mass is not None
                            else zeros
                        ),
                    )
            if radio_acc is not None:
                mdot_r = radio_acc.astype(np.float64) * mfac / step_yr
        l_agn, edd = ag.luminosity(
            (
                bh_mass.astype(np.float64) * mfac
                if bh_mass is not None
                else zeros
            ),
            mdot_q,
            radio_heating if radio_heating is not None else zeros,
            mdot_radio=mdot_r,
        )
        n_c = ag.central_gas_density(
            cold.astype(np.float64) * mfac,
            (disk_r if disk_r is not None else zeros + 3.0) * 1e3 / hubble_h,
        )
        agn_logu = ag.log_u(l_agn, n_c)
        agn_intr = ag.line_luminosities(l_agn, z_gas, agn_logu) / L_SUN_ERG_S
        agn_intr[cold <= 0] = 0.0  # no gas, no narrow-line region
        agn_seen = agn_intr
        if cf:
            # From the disk's mid-plane: half the ISM screen.
            agn_seen = agn_intr * np.sqrt(
                dm.ism_transmission(line_wave, tau_v, eta_v)
            )
        line_intr += agn_intr
        line_seen += agn_seen
        if spectra_out is not None and "wave" in spectra_out:
            agn_spec = np.stack(
                [ag.line_spectrum(spectra_out["wave"], x) for x in agn_seen]
            )
            spectra_out["agn"] = agn_spec
            spectra_out["observed"] = spectra_out["observed"] + agn_spec
        out["LAGN"] = l_agn
        out["EddingtonRatio"] = edd.astype(np.float32)
        out["LogU_HII"] = gas_logu.astype(np.float32)
        out["LogU_AGN"] = np.where(l_agn > 0, agn_logu, np.nan).astype(
            np.float32
        )
        for k, name in enumerate(nb.LINES):
            # float64: bright galaxies' lines pass float32's 3.4e38 erg/s
            seen_erg = line_seen[:, k] * L_SUN_ERG_S
            out[f"LineLum_{name}"] = seen_erg
            out[f"LineLumIntr_{name}"] = line_intr[:, k] * L_SUN_ERG_S
            out[f"LineLumAGN_{name}"] = agn_intr[:, k] * L_SUN_ERG_S
            out[f"LineFlux_{name}"] = (
                seen_erg / (4 * np.pi * d_l_cm**2)
            ).astype(np.float32)
    out["_settings"] = {
        "Method": "FSPS SSPs integrated over each SFH bin's time span",
        "SSPLibraries": ", ".join(libraries),
        "IMF": {0: "Salpeter 1955", 1: "Chabrier 2003", 2: "Kroupa 2001"}.get(
            imf_type, str(imf_type)
        ),
        "RecycleFraction": float(recycle_fraction),
        "YoungFromCurrentSFR_Gyr": float(YOUNG_GYR),
        "Metallicity": (
            "per SFH bin (MHMetals), interpolated between SSP nodes"
            if has_history
            else (
                "per galaxy, present-day stellar Z, interpolated between "
                "SSP nodes"
                if use_metallicity
                else "solar"
            )
        ),
        "KCorrection": "per galaxy at z_obs",
        "LuminosityDistance": "(1+z_obs) D_C(z_cos)",
        "IGM": "Madau 1995",
        "Dust": (
            "Charlot & Fall 2000 as Dusty SAGE (Lagos+19 birth clouds, "
            "Trayford+20 ISM) at each galaxy's inclination; cold dust from "
            "Dusty-SAGE (Triani+20) equilibrium"
            + (
                "; re-emitted in the IR (Draine & Li 2007, energy balance, "
                "U_min from L_dust/M_dust)"
                if re_emit
                else ""
            )
            if cf
            else (
                f"Calzetti 2000, tau_V={dust2}"
                + (" + DL07 emission" if dust_emission else "")
                if dust
                else "none"
            )
        ),
        "NebularEmission": (
            "HII regions: Gutkin+16 grids (lines; FSPS nebular in the "
            "spectra), gas Z = cold-gas Z, "
            "log U from Kashino & Inoue 2019, through birth cloud + ISM; "
            "AGN narrow-line region: Feltre+16 grids coupled as Hirschmann+17 "
            "(quasar bursts on a Hopkins & Hernquist 2009 light curve, placed "
            "uniformly in their step; radio-mode accretion; inefficient below "
            "1% Eddington), "
            "through half the ISM"
            if lines
            else "none"
        ),
    }
    return out


_AGN_FIELDS = {
    "LAGN": (
        "AGN luminosity from SAGE26's quasar- and radio-mode accretion "
        "(radiatively inefficient below 1% Eddington)",
        "erg/s",
    ),
    "EddingtonRatio": ("AGN luminosity / Eddington luminosity", ""),
    "LogU_HII": (
        "log ionisation parameter of the HII regions (Kashino & Inoue 2019)",
        "",
    ),
    "LogU_AGN": (
        "log ionisation parameter of the AGN narrow-line region at the "
        "Stromgren radius (Feltre+16, Hirschmann+17)",
        "",
    ),
}
_DUST_FIELDS = {
    "DustMassCold": ("Cold-ISM dust mass", "Msun"),
    "DustToGas": ("Cold-ISM dust-to-gas mass ratio", ""),
    "TauV_ISM": ("Face-on V-band optical depth of the diffuse ISM", ""),
    "TauV_BC": ("V-band optical depth of the birth clouds", ""),
    "CosInclination": ("|cos| of the angle between spin and sight line", ""),
    "LDust": (
        "Dust luminosity (absorbed starlight re-emitted in the IR)",
        "Lsun",
    ),
    "DustUmin": ("Draine & Li (2007) U_min, from LDust / DustMassCold", ""),
}


def _keep_spectra(store, wave, rows, spectra, intrinsic, n):
    """Keep the rest-frame spectra of `rows` in `store` (see
    compute_photometry)."""
    names = {"": "observed", "disk_": "disk", "bulge_": "bulge"}
    store.setdefault("wave", wave)
    for pre, spec in spectra.items():
        arr = store.setdefault(names[pre], np.zeros((n, len(wave))))
        arr[rows] = spec
    arr = store.setdefault("intrinsic", np.zeros((n, len(wave))))
    arr[rows] = intrinsic


def write_photometry(path: str | Path, results: dict[str, np.ndarray]) -> None:
    """Append/overwrite the computed magnitude datasets in the lightcone file."""
    settings = results.get("_settings", {})
    with h5py.File(path, "a") as f:
        hdr = f.require_group("PhotometryHeader")
        for k in list(hdr.attrs):
            del hdr.attrs[k]
        for k, v in settings.items():
            hdr.attrs[k] = v
        for name, values in results.items():
            if name.startswith("_"):
                continue
            if name in f:
                del f[name]
            # Each output keeps its own dtype (line luminosities are float64).
            ds = f.create_dataset(name, data=values)
            if name.startswith(
                ("LineLum_", "LineLumIntr_", "LineLumAGN_", "LineFlux_")
            ):
                kind, line = name.split("_", 1)
                ds.attrs["Description"] = {
                    "LineLum": "Emission-line luminosity (star formation + AGN), through the galaxy's dust",
                    "LineLumIntr": "Emission-line luminosity (star formation + AGN), no dust",
                    "LineLumAGN": "Emission-line luminosity of the AGN narrow-line region, no dust",
                    "LineFlux": "Observed emission-line flux, through the dust",
                }[kind] + f" ({line})"
                ds.attrs["Units"] = (
                    "erg/s/cm^2" if kind == "LineFlux" else "erg/s"
                )
                ds.attrs["Source"] = (
                    "ViSAGE nebular emission (HII regions: Gutkin+16; "
                    "AGN: Feltre+16)"
                )
                continue
            if name in _AGN_FIELDS:
                ds.attrs["Description"], ds.attrs["Units"] = _AGN_FIELDS[name]
                ds.attrs["Source"] = "ViSAGE nebular emission"
                continue
            if name in _DUST_FIELDS:
                ds.attrs["Description"], ds.attrs["Units"] = _DUST_FIELDS[name]
                ds.attrs["Source"] = "ViSAGE dust (Dusty-SAGE equilibrium)"
                continue
            band = name.split("mag_", 1)[1].split("_", 1)[1]
            frame_word = (
                "Rest-frame absolute"
                if "_rest_" in name
                else "Observed-frame apparent"
            )
            ds.attrs["Description"] = (
                f"{frame_word} AB magnitude, synthetic ({band})"
            )
            ds.attrs["Units"] = "AB mag"
            ds.attrs["Source"] = "ViSAGE SED synthesis (FSPS)"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="visage-sed",
        description="Synthesize broadband AB magnitudes for a LightSAGE lightcone.",
    )
    p.add_argument(
        "--input", required=True, metavar="FILE", help="Lightcone HDF5 file"
    )
    p.add_argument(
        "--bands",
        default=",".join(DEFAULT_BANDS),
        help=f"Comma-separated FSPS filter names (default: {','.join(DEFAULT_BANDS)})",
    )
    p.add_argument(
        "--frame",
        choices=("rest", "obs", "both"),
        default="both",
        help="Which magnitude frame(s) to compute (default: both)",
    )
    p.add_argument(
        "--zbins",
        type=int,
        default=6,
        help=argparse.SUPPRESS,  # (unused: metallicity is interpolated)
    )
    p.add_argument(
        "--no-metallicity",
        dest="metallicity",
        action="store_false",
        help="Force solar metallicity for every galaxy instead of using its "
        "own mass-weighted stellar Z (MetalsStellarMass/StellarMass).",
    )
    p.add_argument(
        "--no-metal-history",
        dest="metal_history",
        action="store_false",
        help="Use one metallicity per galaxy even if the file has each star-"
        "formation bin's (MHMetalsDisk, MHMetalsBulge).",
    )
    p.add_argument(
        "--dust",
        action="store_true",
        help="Apply Calzetti starburst dust attenuation to the SEDs.",
    )
    p.add_argument(
        "--dust-model",
        dest="dust_model",
        choices=("none", "calzetti", "charlot_fall"),
        default=None,
        help="charlot_fall: each galaxy's own dust (Dusty-SAGE physics) in "
        "birth clouds and a disk at its inclination (Charlot & Fall 2000); "
        "calzetti: the --dust2 screen; none. (Default: calzetti with --dust, "
        "else none.)",
    )
    p.add_argument(
        "--dust2",
        type=float,
        default=0.3,
        help="Diffuse V-band optical depth when --dust is set (default: 0.3)",
    )
    p.add_argument(
        "--dust-emission",
        dest="dust_emission",
        action="store_true",
        help="Also re-emit the absorbed energy in the IR (Draine & Li 2007), "
        "making the mid/far-IR bands (WISE, Spitzer, Herschel) physical. "
        "Needs dust (--dust or --dust-model charlot_fall).",
    )
    p.add_argument(
        "--lines",
        action="store_true",
        help="Nebular emission: lines and continuum in the spectra, and each "
        "galaxy's H-alpha, H-beta, [OII], [OIII], [NII], [SII] luminosities "
        "and fluxes, from its star formation and its AGN.",
    )
    p.add_argument(
        "--disk-bulge",
        dest="disk_bulge",
        action="store_true",
        help="Also write the disk's and the bulge's own magnitudes "
        "(disk_mag_* / bulge_mag_*).",
    )
    p.add_argument(
        "--noise",
        action="store_true",
        help="Also write each band's flux with survey noise, and its error "
        "(flux_obs_* / fluxerr_obs_*, µJy; see visage/sed/noise.py).",
    )
    p.add_argument(
        "--alist",
        default=None,
        metavar="FILE",
        help="Scale-factor list (a_list). Overrides the path recorded in the "
        "lightcone header, which may be relative and fail to resolve.",
    )
    args = p.parse_args(argv)
    # The wizard's LightSAGE run calls this from bash; inside WSL on Windows
    # that hands a Windows python /mnt/c/... paths.
    args.input = str(native_path(args.input))

    bands = tuple(b.strip() for b in args.bands.split(",") if b.strip())

    def _progress(done: int, total: int, snap: int, znode: int) -> None:
        print(f"  [{done}/{total}] snap={snap} Z node={znode}", flush=True)

    try:
        import astropy  # noqa: F401
        import fsps  # noqa: F401
    except ImportError as exc:
        print(
            f"Error: {exc}. SED synthesis needs FSPS + astropy, which are "
            "optional (not installed with the base ViSAGE package).\n"
            'Install them with:  pip install "sage-viewer[sed]"',
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Computing synthetic photometry for {args.input} ...")
    _zdesc = "per-galaxy (interpolated)" if args.metallicity else "solar"
    if args.dust_model == "charlot_fall":
        _ddesc = "each galaxy's own (Charlot & Fall)" + (
            ", re-emitted in the IR" if args.dust_emission else ""
        )
    elif args.dust:
        _ddesc = f"on (dust2={args.dust2}" + (
            ", +emission)" if args.dust_emission else ")"
        )
    else:
        _ddesc = "off"
    print(
        f"  bands: {', '.join(bands)}  frame: {args.frame}  "
        f"metallicity: {_zdesc}  dust: {_ddesc}"
    )
    results = compute_photometry(
        args.input,
        bands=bands,
        frame=args.frame,
        use_metallicity=args.metallicity,
        dust=args.dust,
        dust2=args.dust2,
        dust_emission=args.dust_emission,
        alist=args.alist,
        progress_cb=_progress,
        dust_model=args.dust_model,
        disk_bulge=args.disk_bulge,
        lines=args.lines,
        metal_history=args.metal_history,
    )
    write_photometry(args.input, results)
    n_mags = sum(1 for k in results if not k.startswith("_"))
    print(f"Wrote {n_mags} magnitude datasets into {args.input}")
    if args.noise:
        from visage.sed.noise import add_noise

        print(f"Added survey noise in {len(add_noise(args.input))} bands")


if __name__ == "__main__":
    main(sys.argv[1:])
