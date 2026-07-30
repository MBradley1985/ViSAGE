"""Synthetic broadband photometry for a LightSAGE lightcone.

Forward-models AB magnitudes per galaxy from its actual star-formation
history (SFHMassDisk/SFHMassBulge), using FSPS as the stellar population
synthesis engine. This is SED *synthesis* from known simulated truth, not
inverse fitting of observed data.

Scale: a lightcone can carry millions of galaxies, and FSPS is far too slow
to call per-galaxy (see visage/sed/ssp_grid.py). So this groups galaxies by
(metallicity bin, SnapNum) — a few hundred groups at most — builds one
composite spectrum per galaxy within a group via a single matrix multiply
(mass-weighted sum of cached SSP spectra), then projects each composite
through the requested filters.

Simplifications (also documented in the wizard UI and README):
  - Metallicity: one present-day value per galaxy (MetalsStellarMass /
    StellarMass), not a star-formation-weighted history — SAGE doesn't
    output the latter.
  - No dust attenuation — SAGE has no first-class dust optical-depth field.
  - The observed-frame K-correction's spectral *shape* uses one
    representative redshift per (metallicity bin, SnapNum) group (the
    group's mean — empirically a small spread, ~0.003-0.01 in z, within one
    SnapNum). The *distance modulus* (by far the dominant brightness term)
    uses each galaxy's own exact redshift — never binned or approximated.

Output: new `mag_rest_<band>` / `mag_obs_<band>` datasets written into the
same lightcone HDF5 file (float32, AB magnitudes).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from collections.abc import Callable

import h5py
import numpy as np

from visage.sed.cosmology import (
    MPC_TO_CM,
    age_at_scale_factor,
    luminosity_distance_mpc,
)
from visage.sed.filters import DEFAULT_BANDS, filter_transmission
from visage.sed.ssp_grid import (
    SSPGrid,
    assign_metallicity_bins,
    metallicity_bin_edges,
)

L_SUN_ERG_S = 3.828e33  # erg/s, IAU 2015 nominal solar luminosity
PC_TO_CM = 3.0856775814913673e18
# Bounds peak memory for the (chunk, n_wave) composite-spectrum matmul —
# a full (N_galaxies, 5994) array would be tens of GB for a real lightcone.
MAX_GROUP_CHUNK = 50_000

ProgressCB = Callable[[int, int, int, int], None]  # (done, total, snap, zbin)


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


def compute_photometry(
    path: str | Path,
    bands: tuple[str, ...] = DEFAULT_BANDS,
    frame: str = "both",  # "rest" | "obs" | "both"
    n_zbins: int = 6,
    use_metallicity: bool = True,
    dust: bool = False,
    dust2: float = 0.3,
    dust_emission: bool = False,
    progress_cb: ProgressCB | None = None,
) -> dict[str, np.ndarray]:
    """Compute AB magnitudes for every galaxy in a lightcone HDF5 file.

    ``use_metallicity`` (default True) uses each galaxy's own stellar
    metallicity (Z = MetalsStellarMass / StellarMass), binned into ``n_zbins``
    bins; set False to force solar metallicity for every galaxy.
    ``dust`` (default False) applies a Calzetti starburst attenuation of
    V-band optical depth ``dust2`` to the synthesized spectra.
    ``dust_emission`` (default False) additionally re-emits the absorbed
    energy in the IR (Draine & Li 2007), making the mid/far-IR bands (e.g.
    WISE) physical — only takes effect when ``dust`` is also on.

    Returns a dict of ``mag_rest_<band>`` / ``mag_obs_<band>`` -> (N,)
    float32 arrays, aligned to the file's row order (does not write anything;
    see :func:`write_photometry`).
    """
    path = Path(path)
    with h5py.File(path, "r", locking=False) as f:

        def get(name: str) -> np.ndarray | None:
            return np.asarray(f[name][:]) if name in f else None

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
        redshift = get("redshift_cosmological")
        if redshift is None:
            redshift = get("redshift_observed")
        if redshift is None:
            raise KeyError(f"{path} has no redshift field")

        if (
            "SageOutputHeader" not in f
            or "Simulation" not in f["SageOutputHeader"]
        ):
            raise KeyError(f"{path} has no SageOutputHeader/Simulation")
        sim = f["SageOutputHeader"]["Simulation"].attrs
        hubble_h = float(sim["hubble_h"])
        omega_m = float(sim["omega_matter"])
        omega_l = float(sim["omega_lambda"])
        alist_path = sim["FileWithSnapList"]
        if isinstance(alist_path, bytes):
            alist_path = alist_path.decode()

    if not Path(alist_path).is_file():
        raise FileNotFoundError(
            f"Scale-factor list not found: {alist_path} "
            "(needed to convert SFH bins to stellar ages)"
        )

    mfac = 1.0e10 / max(hubble_h, 1e-6)
    stellar_mass = stellar_mass_raw.astype(np.float64) * mfac
    metals_mass = (
        metals.astype(np.float64) * mfac if metals is not None else np.zeros(n)
    )
    # (n, n_bins) Msun formed per SFH bin (disk + bulge).
    sfh_total = (
        sfh_disk.astype(np.float64) + sfh_bulge.astype(np.float64)
    ) * mfac
    n_bins = sfh_total.shape[1]

    # Per-galaxy metallicity -> logzsol, binned coarsely (FSPS is expensive
    # to re-metallicity-switch; see ssp_grid.py).
    import fsps

    if use_metallicity:
        zsun = fsps.StellarPopulation(zcontinuous=1, sfh=0).solar_metallicity
        z_frac = np.where(
            stellar_mass > 0,
            metals_mass / np.maximum(stellar_mass, 1e-30),
            0.0,
        )
        z_frac = np.clip(z_frac, 1e-6, 0.1)
        logzsol_all = np.log10(z_frac / zsun)
        edges = metallicity_bin_edges(n_zbins)
        zbin_idx, zbin_centers = assign_metallicity_bins(logzsol_all, edges)
    else:
        # One solar-metallicity bin for everyone.
        zbin_idx = np.zeros(n, dtype=np.int64)
        zbin_centers = np.array([0.0])

    a_list = np.loadtxt(alist_path)[:n_bins]

    # Distance is exact per-galaxy — cheap, one vectorized call for the
    # whole file regardless of size (benchmarked: ~0.5s for 2M galaxies).
    d_l_cm = (
        luminosity_distance_mpc(redshift, hubble_h, omega_m, omega_l)
        * MPC_TO_CM
    )
    d10_cm = 10.0 * PC_TO_CM

    want_rest = frame in ("rest", "both")
    want_obs = frame in ("obs", "both")
    if not want_rest and not want_obs:
        raise ValueError(
            f"frame must be 'rest', 'obs', or 'both', got {frame!r}"
        )

    out: dict[str, np.ndarray] = {}
    for band in bands:
        if want_rest:
            out[f"mag_rest_{band}"] = np.full(n, np.nan, dtype=np.float32)
        if want_obs:
            out[f"mag_obs_{band}"] = np.full(n, np.nan, dtype=np.float32)

    # Galaxies with no formed stars have no light and no defined magnitude —
    # exclude them up front (left as NaN in the output) rather than compute
    # a degenerate zero/zero case through FSPS.
    has_light = stellar_mass > 0

    unique_snaps = np.unique(snapnum)
    present_zbins = np.unique(zbin_idx)
    n_groups_total = max(len(present_zbins) * len(unique_snaps), 1)
    done_groups = 0

    for zi in present_zbins:
        z_mask_bin = zbin_idx == zi
        # ~18s one-time cost per Zbin (per dust setting).
        grid = SSPGrid(
            zbin_centers[zi],
            dust=dust,
            dust2=dust2,
            dust_emission=dust_emission,
        )
        projectors = {b: _FilterProjector(b, grid.wave) for b in bands}

        for snap in unique_snaps:
            group_mask = z_mask_bin & (snapnum == snap) & has_light
            n_group = int(group_mask.sum())
            if n_group == 0:
                continue
            idx = np.where(group_mask)[0]

            snap_i = min(int(snap), n_bins - 1)
            age_now = age_at_scale_factor(
                a_list[snap_i], hubble_h, omega_m, omega_l
            )
            age_bins = np.clip(
                age_now
                - age_at_scale_factor(a_list, hubble_h, omega_m, omega_l),
                0.0,
                None,
            )
            spectra_grid = grid.spectra_at_ages(age_bins)  # (n_bins, n_wave)

            # Representative z for the K-correction SHAPE only (the group's
            # own within-snapshot spread is small — see module docstring);
            # the DISTANCE below always uses each galaxy's exact redshift.
            z_repr = float(np.mean(redshift[idx]))

            for start in range(0, n_group, MAX_GROUP_CHUNK):
                chunk_idx = idx[start : start + MAX_GROUP_CHUNK]
                weights = sfh_total[chunk_idx]  # (chunk, n_bins)
                # See _FilterProjector.project — same verified-benign
                # Accelerate/BLAS FPE noise on this matmul shape.
                with np.errstate(
                    divide="ignore", over="ignore", invalid="ignore"
                ):
                    composite = (
                        weights @ spectra_grid
                    )  # (chunk, n_wave) L_sun/Hz

                for band in bands:
                    proj = projectors[band]
                    if want_rest:
                        f_nu_eff = proj.project(composite, 0.0)
                        f_nu = f_nu_eff * L_SUN_ERG_S / (4 * np.pi * d10_cm**2)
                        out[f"mag_rest_{band}"][chunk_idx] = _mag_from_fnu(
                            f_nu
                        )
                    if want_obs:
                        f_nu_eff = proj.project(composite, z_repr)
                        d_cm_chunk = d_l_cm[chunk_idx]
                        f_nu = (
                            (1.0 + z_repr)
                            * f_nu_eff
                            * L_SUN_ERG_S
                            / (4 * np.pi * d_cm_chunk**2)
                        )
                        out[f"mag_obs_{band}"][chunk_idx] = _mag_from_fnu(f_nu)

            done_groups += 1
            if progress_cb is not None:
                progress_cb(done_groups, n_groups_total, int(snap), int(zi))

    return out


def write_photometry(path: str | Path, results: dict[str, np.ndarray]) -> None:
    """Append/overwrite the computed magnitude datasets in the lightcone file."""
    with h5py.File(path, "a") as f:
        for name, values in results.items():
            if name in f:
                del f[name]
            ds = f.create_dataset(name, data=values.astype(np.float32))
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
        help="Metallicity bin count (default: 6)",
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
    args = p.parse_args(argv)

    bands = tuple(b.strip() for b in args.bands.split(",") if b.strip())

    def _progress(done: int, total: int, snap: int, zbin: int) -> None:
        print(f"  [{done}/{total}] snap={snap} Zbin={zbin}", flush=True)

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
    _zdesc = f"per-galaxy ({args.zbins} bins)" if args.metallicity else "solar"
    if args.dust:
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
        n_zbins=args.zbins,
        use_metallicity=args.metallicity,
        dust=args.dust,
        dust2=args.dust2,
        dust_emission=args.dust_emission,
        progress_cb=_progress,
    )
    write_photometry(args.input, results)
    print(f"Wrote {len(results)} magnitude datasets into {args.input}")


if __name__ == "__main__":
    main(sys.argv[1:])
