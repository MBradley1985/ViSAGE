"""One galaxy's spectrum from a LightSAGE lightcone.

The spectrum is made exactly as the cone's synthetic photometry was: the
same SED synthesis (visage/sed/photometry.py) with the settings recorded
in the file's ``PhotometryHeader`` -- IMF, recycling, metallicity, dust
model and its infrared re-emission, nebular emission -- for this one
galaxy. So the magnitudes stored in the file are this spectrum seen
through each filter, and the plot marks them on it as a check.

Shown in the observed frame, as a telescope would see it:
f_nu(lambda_obs) = (1 + z_obs) L_nu(lambda_obs / (1 + z_obs)) / (4 pi D_L^2),
D_L = (1 + z_obs) D_C(z_cos) (as the photometry; Davis et al. 2011, ApJ
741, 67), and through the IGM (visage/sed/igm.py) when the cone's
photometry was. It starts at the rest-frame Lyman limit (912 A).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

from visage.sed import igm
from visage.sed.cosmology import MPC_TO_CM, luminosity_distance_mpc
from visage.sed.photometry import (
    L_SUN_ERG_S,
    _resolve_alist,
    compute_photometry,
)

LYMAN_LIMIT_A = 911.8


@dataclass
class GalaxySpectrum:
    row: int
    label: str
    z_obs: float
    d_l_cm: float
    wave: np.ndarray  # rest-frame Angstrom
    lnu: dict[str, np.ndarray]  # observed/intrinsic/disk/bulge, L_sun/Hz
    mags: dict[str, float]  # stored observed-frame AB mags, by band
    info: dict[str, float] = field(default_factory=dict)
    settings: dict[str, str] = field(default_factory=dict)

    def fnu_ujy(self, key: str = "observed") -> np.ndarray:
        """Observed-frame flux density (µJy) at wave * (1 + z_obs)."""
        f = (
            (1.0 + self.z_obs)
            * self.lnu[key]
            * L_SUN_ERG_S
            / (4 * np.pi * self.d_l_cm**2)
        )
        if "IGM" in self.settings:
            f = f * igm.transmission(self.wave, self.z_obs)
        return f * 1e29  # erg/s/cm^2/Hz -> µJy

    @property
    def wave_obs(self) -> np.ndarray:
        return self.wave * (1.0 + self.z_obs)


def run_settings(path: str | Path) -> tuple[dict, dict]:
    """compute_photometry keyword arguments reproducing the cone's own
    photometry, read back from its ``PhotometryHeader`` (and the header)."""
    with h5py.File(path, "r", locking=False) as f:
        if "PhotometryHeader" not in f:
            raise KeyError(f"{path} has no synthetic photometry")
        hdr = {
            k: (v.decode() if isinstance(v, bytes) else v)
            for k, v in f["PhotometryHeader"].attrs.items()
        }
        disk_bulge = any(k.startswith("disk_mag_") for k in f)
    dust = str(hdr.get("Dust", "none"))
    kw: dict = {
        "use_metallicity": str(hdr.get("Metallicity", "")) != "solar",
        "lines": str(hdr.get("NebularEmission", "none")) != "none",
        "disk_bulge": disk_bulge,
        "metal_history": "per SFH bin" in str(hdr.get("Metallicity", "")),
        "imf_type": {"Salpeter": 0, "Chabrier": 1, "Kroupa": 2}.get(
            str(hdr.get("IMF", "Chabrier")).split()[0], 1
        ),
    }
    if "RecycleFraction" in hdr:
        kw["recycle_fraction"] = float(hdr["RecycleFraction"])
    if dust.startswith("Charlot"):
        kw["dust_model"] = "charlot_fall"
        kw["dust_emission"] = "re-emitted" in dust
    elif dust.startswith("Calzetti"):
        kw["dust_model"] = "calzetti"
        kw["dust"] = True
        kw["dust_emission"] = "emission" in dust
        try:
            kw["dust2"] = float(dust.split("tau_V=")[1].split()[0])
        except (IndexError, ValueError):
            pass
    else:
        kw["dust_model"] = "none"
    return kw, hdr


def find_alist(path: str | Path, hint: str | None = None) -> Path | None:
    """The run's scale-factor list. The header records it relative to the
    SAGE run directory, so besides the photometry's own search (the file's
    folder and its ancestors) try it under each ancestor's sibling folders
    (e.g. ../SAGE26/input/...)."""
    path = Path(path)
    with h5py.File(path, "r", locking=False) as f:
        rel = f["SageOutputHeader"]["Simulation"].attrs["FileWithSnapList"]
    rel = rel.decode() if isinstance(rel, bytes) else str(rel)
    found = _resolve_alist(rel, hint, path)
    if found is not None and found.name == Path(rel).name:
        return found
    if Path(rel).is_absolute():
        return found
    for anc in path.resolve().parents:
        try:
            for sib in anc.iterdir():
                c = sib / rel
                if sib.is_dir() and c.is_file():
                    return c
        except OSError:
            continue
    return found


def galaxy_spectrum(
    path: str | Path,
    row: int,
    label: str = "",
    alist: str | Path | None = None,
    progress_cb=None,
) -> GalaxySpectrum:
    """Synthesise galaxy `row`'s spectrum as the cone's photometry was
    (``progress_cb`` as compute_photometry's: one call per metallicity
    node, which builds its FSPS grid, then per snapshot)."""
    path = Path(path)
    kw, hdr = run_settings(path)
    al = find_alist(path, alist)
    if al is None:
        raise FileNotFoundError(
            "Couldn't find the run's scale-factor list (the lightcone "
            "header's FileWithSnapList), which the stars' ages need."
        )
    rows = np.array([int(row)])
    spec: dict = {}
    res = compute_photometry(
        path,
        bands=("sdss_r",),
        alist=al,
        rows=rows,
        spectra_out=spec,
        frame="obs",
        progress_cb=progress_cb,
        **kw,
    )
    if "wave" not in spec:
        raise ValueError("This galaxy has no stars, so no spectrum.")
    with h5py.File(path, "r", locking=False) as f:

        def one(name, default=np.nan):
            return float(f[name][row]) if name in f else default

        sim = f["SageOutputHeader"]["Simulation"].attrs
        h = float(sim["hubble_h"])
        z_cos = one("redshift_cosmological")
        z_obs = one("redshift_observed", z_cos)
        if np.isnan(z_cos):
            z_cos = z_obs
        dist = one("distance")
        if np.isfinite(dist):
            d_l = (1.0 + z_obs) * dist / h * MPC_TO_CM
        else:
            d_l = float(
                luminosity_distance_mpc(
                    np.array([z_cos]),
                    h,
                    float(sim["omega_matter"]),
                    float(sim["omega_lambda"]),
                )[0]
                * MPC_TO_CM
            )
        mags = {
            k[len("mag_obs_") :]: float(f[k][row])
            for k in f
            if k.startswith("mag_obs_")
        }
        mfac = 1e10 / h
        info = {
            "log_mstar": np.log10(max(one("StellarMass", 0) * mfac, 1.0)),
            "sfr": one("SfrDisk", 0) + one("SfrBulge", 0),
            "bt": one("BulgeMass", 0) / max(one("StellarMass", 0), 1e-12),
        }
    for k in (
        "TauV_ISM",
        "CosInclination",
        "LDust",
        "DustUmin",
        "LineFlux_Halpha",
    ):
        if k in res:
            info[k] = float(res[k][0])
    lnu = {
        k: np.asarray(spec[k][0], dtype=np.float64)
        for k in ("observed", "intrinsic", "disk", "bulge", "agn")
        if k in spec
    }
    return GalaxySpectrum(
        row=int(row),
        label=label or f"row {int(row)}",
        z_obs=z_obs,
        d_l_cm=d_l,
        wave=np.asarray(spec["wave"], dtype=np.float64),
        lnu=lnu,
        mags=mags,
        info=info,
        settings=hdr,
    )


def _pivot_a(band: str) -> float | None:
    from visage.sed.filters import filter_transmission

    try:
        w, t = filter_transmission(band)
    except Exception:
        return None
    return float(np.sqrt(np.trapezoid(t * w, w) / np.trapezoid(t / w, w)))


def plot_png(s: GalaxySpectrum, dpi: int = 130, dark: bool = False) -> bytes:
    """The spectrum figure as a PNG."""
    from visage.plots.style import theme

    with theme(dark):
        return _plot(s, dpi, dark)


def _plot(s: GalaxySpectrum, dpi: int, dark: bool) -> bytes:
    """The observed-frame spectrum, the cone's stored magnitudes on it."""
    import matplotlib

    matplotlib.use("Agg", force=False)
    from matplotlib.figure import Figure

    from visage.plots.style import ink
    from visage.sed.filters import band_label

    lo = LYMAN_LIMIT_A
    hi = 1e7 if s.settings.get("Dust", "").find("re-emitted") >= 0 else 5e4
    keep = (s.wave >= lo) & (s.wave <= hi)
    x = s.wave_obs[keep] / 1e4  # µm
    fig = Figure(figsize=(9.0, 5.2), dpi=dpi)
    ax = fig.add_subplot(111)
    y_obs = s.fnu_ujy("observed")[keep]
    ax.loglog(x, y_obs, color=ink(dark), lw=1.1, label="observed", zorder=3)
    if "intrinsic" in s.lnu and "observed" in s.lnu:
        if not np.allclose(s.lnu["intrinsic"], s.lnu["observed"]):
            ax.loglog(
                x,
                s.fnu_ujy("intrinsic")[keep],
                color="0.55",
                lw=0.9,
                ls="--",
                label="stars, no dust",
                zorder=2,
            )
    for key, col in (
        ("disk", "#1f77b4"),
        ("bulge", "#d62728"),
        ("agn", "#2ca02c"),
    ):
        if key in s.lnu and np.any(s.lnu[key] > 0):
            ax.loglog(
                x,
                s.fnu_ujy(key)[keep],
                color=col,
                lw=0.7,
                alpha=0.75,
                label="AGN lines" if key == "agn" else key,
                zorder=2,
            )
    good = y_obs[np.isfinite(y_obs) & (y_obs > 0)]
    top = float(good.max()) if len(good) else 1.0
    floor = float(good.min()) * 0.3 if len(good) else top * 1e-5
    ax.set_ylim(max(floor, top * 1e-5), top * 4)
    ax.set_xlim(x[0], x[-1])
    # The file's own photometry: this spectrum through each filter.
    px, py, names = [], [], []
    for band, m in s.mags.items():
        if not np.isfinite(m) or m > 60:
            continue
        lam = _pivot_a(band)
        if lam is None:
            continue
        px.append(lam / 1e4)
        py.append(10 ** ((23.9 - m) / 2.5))
        names.append(band_label(band))
    if px:
        ax.scatter(
            px,
            py,
            s=34,
            facecolor="none",
            edgecolor="#e6550d",
            lw=1.3,
            zorder=4,
            label="catalogue photometry",
        )
    ax.set_xlabel("observed wavelength [µm]")
    ax.set_ylabel("f$_ν$ [µJy]")
    sec = ax.secondary_xaxis(
        "top",
        functions=(lambda v: v / (1 + s.z_obs), lambda v: v * (1 + s.z_obs)),
    )
    sec.set_xlabel("rest wavelength [µm]")
    ax.grid(True, which="major", color="0.3" if dark else "0.9", lw=0.6)
    ax.legend(fontsize=8, loc="lower center", ncol=6, frameon=False)
    i = s.info
    ssfr = i["sfr"] / max(10 ** i["log_mstar"], 1.0)
    ax.set_title(
        f"Galaxy {s.label}   z = {s.z_obs:.4f}   "
        f"log M* = {i['log_mstar']:.2f}   SFR = {i['sfr']:.2g} M☉/yr   "
        f"log sSFR = {np.log10(max(ssfr, 1e-14)):.1f}   B/T = {i['bt']:.2f}",
        fontsize=9.5,
    )
    notes = []
    if "TauV_ISM" in i:
        notes.append(f"τ$_V$ (face-on) {i['TauV_ISM']:.2f}")
    if "CosInclination" in i:
        notes.append(f"|cos i| {i['CosInclination']:.2f}")
    if i.get("LDust", 0) > 0:
        notes.append(f"L$_{{dust}}$ {i['LDust']:.2e} L☉")
    if "DustUmin" in i:
        notes.append(f"U$_{{min}}$ {i['DustUmin']:.2g}")
    if np.isfinite(i.get("LineFlux_Halpha", np.nan)):
        notes.append(f"Hα {i['LineFlux_Halpha']:.2e} erg/s/cm²")
    if notes:
        ax.text(
            0.01,
            0.97,
            "\n".join(notes),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8,
        )
    fig.text(
        0.01,
        0.01,
        "SAGE26 / LightSAGE, FSPS "
        f"({s.settings.get('SSPLibraries', '')}), "
        f"{s.settings.get('IMF', '')} IMF; dust: "
        f"{str(s.settings.get('Dust', 'none')).split(';')[0]}",
        fontsize=6.5,
        color="0.6" if dark else "0.4",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()


def write_csv(s: GalaxySpectrum, path: str | Path) -> None:
    """The spectrum as a table: rest and observed wavelength, observed-
    frame f_nu of each component, and the rest-frame L_nu."""
    keys = list(s.lnu)
    cols = [s.wave, s.wave_obs]
    cols += [s.fnu_ujy(k) for k in keys]
    cols += [s.lnu[k] for k in keys]
    head = (
        f"# Galaxy {s.label} (lightcone row {s.row}), z_obs = {s.z_obs:.6f}, "
        f"D_L = {s.d_l_cm / MPC_TO_CM:.3f} Mpc\n"
        "# Made with the cone's own photometry settings:\n"
        + "".join(f"#   {k}: {v}\n" for k, v in s.settings.items())
        + "lambda_rest_A,lambda_obs_A,"
        + ",".join(f"fnu_{k}_uJy" for k in keys)
        + ","
        + ",".join(f"Lnu_rest_{k}_Lsun_per_Hz" for k in keys)
        + "\n"
    )
    with open(path, "w") as fh:
        fh.write(head)
        np.savetxt(fh, np.column_stack(cols), delimiter=",", fmt="%.6e")


# ── The viewer's spectrum worker ─────────────────────────────────────
# FSPS holds the GIL while it builds a grid (~45 s per metallicity), which
# would freeze the viewer's server -- the browser loses its connection. So
# spectra are made in a process of their own, kept for the session so the
# grids it has built stay built.


def _worker_main(inbox, outbox, parent: int) -> None:
    import os
    import queue
    import time

    import visage.sed  # noqa: F401  (sets SPS_HOME)
    from visage import procs

    procs.watch_parent(parent)
    while True:
        try:
            job = inbox.get(timeout=2.0)
        except queue.Empty:
            # The viewer was killed (not closed): don't outlive it.
            if os.getppid() != parent:
                return
            continue
        except (EOFError, OSError):
            return  # the viewer's end of the queue is gone
        if job is None:
            return
        jid = job["id"]
        try:
            t = [time.monotonic()]

            def cb(done, total, _snap, _zi, jid=jid, t=t):
                now = time.monotonic()
                outbox.put(("node", jid, int(done), int(total), now - t[0]))
                t[0] = now

            outbox.put(("stage", jid, "synthesis"))
            s = galaxy_spectrum(
                job["path"], job["row"], job["label"], progress_cb=cb
            )
            outbox.put(("stage", jid, "plot"))
            Path(job["png"]).write_bytes(plot_png(s, dark=job["dark"]))
            write_csv(s, job["csv"])
            outbox.put(("done", jid, {"z_obs": s.z_obs}))
        except Exception as exc:
            outbox.put(("error", jid, f"{exc!s}"))


class SpectrumWorker:
    """One spawned process making spectra, one at a time. ``submit`` a
    job, then ``poll`` its messages: ("stage", id, name), ("node", id,
    done, total, seconds), ("done", id, info) or ("error", id, text)."""

    def __init__(self) -> None:
        self._proc = None
        self._inbox = self._outbox = None
        self._id = 0

    def _start(self) -> None:
        import multiprocessing as mp
        import os

        ctx = mp.get_context("spawn")
        # The replies on a SimpleQueue: written straight to the pipe, not
        # by a feeder thread, which can't run while FSPS holds the GIL --
        # the progress would only arrive once the build was over.
        self._inbox, self._outbox = ctx.Queue(), ctx.SimpleQueue()
        self._proc = ctx.Process(
            target=_worker_main,
            args=(self._inbox, self._outbox, os.getpid()),
            daemon=True,
            name="visage-spectrum",
        )
        self._proc.start()
        from visage import procs

        procs.track(self._proc, group=False)

    def alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    def submit(self, path, row, label, png, csv, dark=False) -> int:
        if not self.alive():
            self._start()
        self._id += 1
        self._inbox.put(
            {
                "id": self._id,
                "path": str(path),
                "row": int(row),
                "label": str(label),
                "png": str(png),
                "csv": str(csv),
                "dark": bool(dark),
            }
        )
        return self._id

    def poll(self) -> list:
        out = []
        while self._outbox is not None and not self._outbox.empty():
            out.append(self._outbox.get())
        return out

    def stop(self) -> None:
        """End the process now (its built grids go with it)."""
        from visage import procs

        p, self._proc = self._proc, None
        if p is None:
            return
        if p.is_alive():
            p.terminate()
            p.join(3)
            if p.is_alive():
                p.kill()
                p.join(1)
        procs.untrack(p)
