"""Synthetic broadband photometry for a LightSAGE lightcone.

Forward-models AB magnitudes per galaxy from its actual star-formation
history (SFHMassDisk/SFHMassBulge), using FSPS (Conroy, Gunn & White 2009,
ApJ 699, 486; Conroy & Gunn 2010, ApJ 712, 833) as the stellar population
synthesis engine. This is SED *synthesis* from known simulated truth, not
inverse fitting of observed data.

How each galaxy's light is built (references in docs/physics/photometry.md):
  - Star-formation history: SAGE26 files the stars formed between
    snapshots k and k+1 in bin k, as the mass that survives recycling
    ((1 - R) of what formed). Each bin is turned back into mass formed
    (/ (1 - R), R = the run's RecycleFraction) and spread at a constant
    rate over its own time span, integrating the SSPs over age (as TAO:
    Shamshiri et al. 2015, MNRAS 451, 2681). The youngest stars (< 100 Myr)
    come from the galaxy's current SFR (SfrDisk + SfrBulge).
  - IMF: Chabrier (2003), as SAGE26 assumes.
  - Metallicity: one present-day value per galaxy (MetalsStellarMass /
    StellarMass), the spectrum linearly interpolated in log Z between
    fixed SSP nodes -- SAGE doesn't output a metallicity history.
  - Observed frame: K-corrected at each galaxy's own observed redshift
    (interpolated from a fine redshift grid within its snapshot shell),
    with luminosity distance D_L = (1 + z_obs) D_C(z_cos) (peculiar
    velocities included; Davis et al. 2011, ApJ 741, 67).
  - Dust: none by default (see --dust).

Scale: a lightcone can carry millions of galaxies, and FSPS is far too slow
to call per-galaxy. So galaxies are grouped by snapshot; each group's
composite spectra are one matrix multiply (mass per bin x cached bin
spectra), at each metallicity node, then projected through the filters.

Output: new `mag_rest_<band>` / `mag_obs_<band>` datasets written into the
same lightcone HDF5 file (float32, AB magnitudes), with the settings used
recorded in the file's `PhotometryHeader` attributes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from collections.abc import Callable

import h5py
import numpy as np

from visage.system import native_path
from visage.sed.cosmology import (
    MPC_TO_CM,
    age_at_scale_factor,
    luminosity_distance_mpc,
)
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
        weights = shifted_r / self._ssp_wave * self._dw
        # Verified benign: this matmul reliably trips spurious divide/
        # overflow/invalid FPE flags on Apple's Accelerate BLAS backend
        # without corrupting the result (checked element-by-element against
        # an independent computation) — suppressed rather than left as
        # alarming noise on every run.
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            return spectra @ weights / self._denom


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
) -> dict[str, np.ndarray]:
    """Compute AB magnitudes for every galaxy in a lightcone HDF5 file
    (or just `rows`, sorted row indices).

    ``alist`` overrides the scale-factor list. If omitted, the path recorded
    in the lightcone header (``FileWithSnapList``) is used — but that can be a
    relative path (relative to the original SAGE run dir) that no longer
    resolves, so passing the absolute a_list here is more reliable.

    ``use_metallicity`` (default True) uses each galaxy's own stellar
    metallicity (Z = MetalsStellarMass / StellarMass); False forces solar.
    ``dust`` (default False) applies a Calzetti starburst attenuation of
    V-band optical depth ``dust2`` to the synthesized spectra.
    ``dust_emission`` (default False) additionally re-emits the absorbed
    energy in the IR (Draine & Li 2007) — only with ``dust`` on.
    ``recycle_fraction`` defaults to the run's own (header RecycleFraction).
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
        sfr_now = np.zeros(n)
        for name in ("SfrDisk", "SfrBulge"):
            v = get(name)
            if v is not None:
                sfr_now = sfr_now + v.astype(np.float64)  # Msun/yr
        dist = get("distance")  # comoving, Mpc/h
        if dust_model is None:
            dust_model = "calzetti" if dust else "none"
        cf = dust_model == "charlot_fall"
        if cf:
            cold = get("ColdGas")
            metals_cold = get("MetalsColdGas")
            h2 = get("H2gas")
            h1 = get("H1gas")
            disk_r = get("DiskRadius")
            spin = np.column_stack([get(f"Spin{c}") for c in "xyz"])
            pos = np.column_stack([get(f"Pos{c}") for c in "xyz"])

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
    sfh_formed = (
        (sfh_disk.astype(np.float64) + sfh_bulge.astype(np.float64))
        * mfac
        / (1.0 - recycle_fraction)
    )
    n_bins = sfh_formed.shape[1]

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
        tau_v = dm.tau_v_ism(
            h1.astype(np.float64) * mfac,
            h2.astype(np.float64) * mfac,
            cold_m,
            disk_r * 1e3 / hubble_h,
            delta,
        )
        cos_i = dm.cos_inclination(spin, pos)
        dust_info = {
            "DustMassCold": (delta * cold_m).astype(np.float32),
            "DustToGas": delta.astype(np.float32),
            "TauV_ISM": tau_v.astype(np.float32),
            "CosInclination": cos_i.astype(np.float32),
        }
        dust = False  # (the SSPs stay unattenuated; dust is applied here)

    import fsps

    zsun = fsps.StellarPopulation(zcontinuous=1, sfh=0).solar_metallicity
    if use_metallicity:
        z_frac = np.where(
            stellar_mass > 0,
            metals_mass / np.maximum(stellar_mass, 1e-30),
            0.0,
        )
        logzsol_all = np.log10(np.clip(z_frac, 1e-6, 0.1) / zsun)
        nodes = METALLICITY_NODES
        z_lo, z_hi, z_w = metallicity_weights(logzsol_all, nodes)
    else:
        nodes = np.array([0.0])
        z_lo = z_hi = np.zeros(n, dtype=np.int64)
        z_w = np.zeros(n)

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
    for band in bands:
        if want_rest:
            flux[f"mag_rest_{band}"] = np.zeros(n)
        if want_obs:
            flux[f"mag_obs_{band}"] = np.zeros(n)

    has_light = stellar_mass > 0
    unique_snaps = np.unique(snapnum)
    used_nodes = np.unique(np.concatenate([z_lo, z_hi]))
    n_groups_total = max(len(used_nodes) * len(unique_snaps), 1)
    done_groups = 0
    libraries = ()

    for zi in used_nodes:
        w_node = np.where(z_lo == zi, 1.0 - z_w, 0.0) + np.where(
            z_hi == zi, z_w, 0.0
        )
        if not use_metallicity:
            w_node = np.ones(n)
        grid = SSPGrid(
            nodes[zi],
            dust=dust,
            dust2=dust2,
            dust_emission=dust_emission,
            imf_type=imf_type,
        )
        libraries = grid.libraries
        projectors = {b: _FilterProjector(b, grid.wave) for b in bands}

        for snap in unique_snaps:
            group = has_light & (snapnum == snap) & (w_node > 0)
            idx = np.where(group)[0]
            if len(idx) == 0:
                done_groups += 1
                continue
            s = int(snap)
            t_now = t_snap[min(s, len(t_snap) - 1)]
            # Bin k holds stars formed between snapshots k and k+1: ages
            # t_now - t[k+1] .. t_now - t[k] (empty for k >= s).
            k = np.arange(n_bins)
            t_lo = t_snap[np.minimum(k, len(t_snap) - 1)]
            t_hi = t_snap[np.minimum(k + 1, len(t_snap) - 1)]
            age_lo = np.clip(t_now - t_hi, 0.0, None)
            age_hi = np.clip(t_now - t_lo, 0.0, None)
            bin_spec = grid.mean_spectra(age_lo, age_hi)  # (n_bins, n_wave)
            # The last bin, split: its youngest YOUNG_GYR from the current
            # SFR, the rest spread over the remainder.
            last = s - 1
            width = age_hi[last] - age_lo[last] if 0 <= last < n_bins else 0.0
            dt_y = min(YOUNG_GYR, width)
            young_spec = grid.mean_spectrum(0.0, dt_y)
            rest_spec = (
                grid.mean_spectrum(dt_y, width) if width > dt_y else young_spec
            )
            z_shell = z_obs[idx]
            kz = np.linspace(z_shell.min(), z_shell.max(), N_KZ)
            if kz[-1] - kz[0] < 1e-6:
                kz = kz[:1]

            step = 4000 if cf else MAX_GROUP_CHUNK
            if cf:
                # Stars younger than 10 Myr sit in their birth clouds.
                bc_age = (
                    min(dm.BC_AGE_GYR, dt_y) if dt_y > 0 else dm.BC_AGE_GYR
                )
                bc_spec = grid.mean_spectrum(0.0, bc_age)
                y2_spec = (
                    grid.mean_spectrum(bc_age, dt_y)
                    if dt_y > bc_age
                    else bc_spec
                )
                bc_frac = bc_age / dt_y if dt_y > 0 else 1.0
            for start in range(0, len(idx), step):
                ci = idx[start : start + step]
                wts = sfh_formed[ci].copy()  # (chunk, n_bins)
                m_young = np.zeros(len(ci))
                m_rest = np.zeros(len(ci))
                if 0 <= last < n_bins and width > 0:
                    m_last = wts[:, last]
                    m_young = np.minimum(sfr_now[ci] * dt_y * 1e9, m_last)
                    m_rest = m_last - m_young
                    wts[:, last] = 0.0
                with np.errstate(
                    divide="ignore", over="ignore", invalid="ignore"
                ):
                    if cf:
                        older = (
                            wts @ bin_spec
                            + (m_young * (1 - bc_frac))[:, None] * y2_spec
                            + m_rest[:, None] * rest_spec
                        )
                        t_ism = dm.ism_transmission(
                            grid.wave, tau_v[ci], cos_i[ci]
                        )
                        t_bc = dm.bc_transmission(grid.wave, tau_v[ci])
                        composite = t_ism * (
                            older
                            + (m_young * bc_frac)[:, None] * bc_spec * t_bc
                        )
                    else:
                        composite = (
                            wts @ bin_spec
                            + m_young[:, None] * young_spec
                            + m_rest[:, None] * rest_spec
                        )  # (chunk, n_wave) L_sun/Hz
                wn = w_node[ci]
                zg = z_obs[ci]
                for band in bands:
                    proj = projectors[band]
                    if want_rest:
                        f_nu = (
                            proj.project(composite, 0.0)
                            * L_SUN_ERG_S
                            / (4 * np.pi * d10_cm**2)
                        )
                        flux[f"mag_rest_{band}"][ci] += wn * f_nu
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
                        flux[f"mag_obs_{band}"][ci] += wn * f_nu

            done_groups += 1
            if progress_cb is not None:
                progress_cb(done_groups, n_groups_total, s, int(zi))

    out: dict = {}
    for name, f_nu in flux.items():
        mag = _mag_from_fnu(f_nu)
        mag[~has_light] = np.nan
        out[name] = mag
    out.update(dust_info)
    out["_settings"] = {
        "Method": "FSPS SSPs integrated over each SFH bin's time span",
        "SSPLibraries": ", ".join(libraries),
        "IMF": {0: "Salpeter 1955", 1: "Chabrier 2003", 2: "Kroupa 2001"}.get(
            imf_type, str(imf_type)
        ),
        "RecycleFraction": float(recycle_fraction),
        "YoungFromCurrentSFR_Gyr": float(YOUNG_GYR),
        "Metallicity": (
            "per galaxy, present-day stellar Z, interpolated between SSP nodes"
            if use_metallicity
            else "solar"
        ),
        "KCorrection": "per galaxy at z_obs",
        "LuminosityDistance": "(1+z_obs) D_C(z_cos)",
        "Dust": (
            "Charlot & Fall 2000 birth clouds + ISM slab at each galaxy's "
            "inclination; cold dust from Dusty-SAGE (Triani+20) equilibrium"
            if cf
            else (
                f"Calzetti 2000, tau_V={dust2}"
                + (" + DL07 emission" if dust_emission else "")
                if dust
                else "none"
            )
        ),
        "NebularEmission": "none",
    }
    return out


_DUST_FIELDS = {
    "DustMassCold": ("Cold-ISM dust mass", "Msun"),
    "DustToGas": ("Cold-ISM dust-to-gas mass ratio", ""),
    "TauV_ISM": ("Face-on V-band optical depth of the diffuse ISM", ""),
    "CosInclination": ("|cos| of the angle between spin and sight line", ""),
}


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
            ds = f.create_dataset(name, data=values.astype(np.float32))
            if name in _DUST_FIELDS:
                ds.attrs["Description"], ds.attrs["Units"] = _DUST_FIELDS[name]
                ds.attrs["Source"] = "ViSAGE dust (Dusty-SAGE equilibrium)"
                continue
            band = name.split("_", 2)[-1]
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
        help="Also re-emit absorbed energy in the IR (Draine & Li), making "
        "the mid/far-IR bands (WISE) physical. Needs --dust.",
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
        _ddesc = "each galaxy's own (Charlot & Fall)"
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
    )
    write_photometry(args.input, results)
    n_mags = sum(1 for k in results if not k.startswith("_"))
    print(f"Wrote {n_mags} magnitude datasets into {args.input}")


if __name__ == "__main__":
    main(sys.argv[1:])
