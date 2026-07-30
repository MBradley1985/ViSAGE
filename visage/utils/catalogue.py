from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import numpy as np

if TYPE_CHECKING:
    from visage.config import SimConfig
    from visage.io.snapshot_table import SnapshotTable

# 2D arrays — included in HDF5 output, skipped for flat (CSV/TXT/FITS) formats
_2D_KEYS = {"SFHMassDisk", "SFHMassBulge"}

# Unit annotations — purely informational, no conversion applied
_UNITS: dict[str, str] = {
    "Posx": "Mpc/h",
    "Posy": "Mpc/h",
    "Posz": "Mpc/h",
    "StellarMass": "10^10 Msun/h",
    "BulgeMass": "10^10 Msun/h",
    "ColdGas": "10^10 Msun/h",
    "Mvir": "10^10 Msun/h",
    "CentralMvir": "10^10 Msun/h",
    "BlackHoleMass": "10^10 Msun/h",
    "IntraClusterStars": "10^10 Msun/h",
    "H2gas": "10^10 Msun/h",
    "CGMgas": "10^10 Msun/h",
    "HotGas": "10^10 Msun/h",
    "SfrDisk": "Msun/yr",
    "SfrBulge": "Msun/yr",
    "SFHMassDisk": "10^10 Msun/h",
    "SFHMassBulge": "10^10 Msun/h",
}


def _read_snap_fields(
    hdf5_path: Path,
    snap_num: int,
    sage_indices: np.ndarray,
) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """Read ALL fields from a SAGE HDF5 snapshot group for the given row indices.

    Data is returned exactly as stored — no unit conversion.
    """
    data: dict[str, np.ndarray] = {}
    units: dict[str, str] = {}

    with h5py.File(str(hdf5_path), "r") as hf:
        grp = hf[f"Snap_{snap_num}"]
        n_total = len(grp["Posx"]) if "Posx" in grp else None

        for key in sorted(grp.keys()):
            raw = np.asarray(grp[key])

            if raw.ndim == 1:
                if n_total is not None and len(raw) != n_total:
                    continue
                data[key] = raw[sage_indices]
                units[key] = _UNITS.get(key, "")

            elif raw.ndim == 2 and key in _2D_KEYS:
                if n_total is None or raw.shape[0] == n_total:
                    data[key] = raw[sage_indices]
                    units[key] = _UNITS.get(key, "")

    return data, units


def _read_flat_fields(
    hdf5_path: Path,
    sage_indices: np.ndarray,
) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """Read ALL top-level fields from a flat ``cli_lightcone`` HDF5 file for
    the given row indices — a lightcone has no ``Snap_N`` groups, its galaxy
    columns (including any synthetic-photometry ``mag_rest_*`` / ``mag_obs_*``
    datasets) live at the file root. Data is returned exactly as stored."""
    data: dict[str, np.ndarray] = {}
    units: dict[str, str] = {}

    with h5py.File(str(hdf5_path), "r") as hf:
        n_total = len(hf["Posx"]) if "Posx" in hf else None
        for key in sorted(hf.keys()):
            item = hf[key]
            if not isinstance(item, h5py.Dataset):
                continue  # skip header/metadata groups
            raw = np.asarray(item)
            if raw.ndim == 1 and (n_total is None or len(raw) == n_total):
                data[key] = raw[sage_indices]
                units[key] = _UNITS.get(key, "")
            elif raw.ndim == 2 and key in _2D_KEYS:
                if n_total is None or raw.shape[0] == n_total:
                    data[key] = raw[sage_indices]
                    units[key] = _UNITS.get(key, "")

    return data, units


def _scalar_only(data: dict) -> dict[str, np.ndarray]:
    return {k: v for k, v in data.items() if np.ndim(v) == 1}


def _build_metadata(
    snap_num: int,
    snap_label: str,
    n_galaxies: int,
    scope_label: str,
    scope_bounds: dict | None,
    cfg: SimConfig | None,
    snap_table: SnapshotTable | None,
) -> dict[str, str]:
    """Build an ordered metadata dict covering export info, simulation
    parameters, cosmology, and selection bounds."""
    meta: dict[str, str] = {}

    # ── Export info ───────────────────────────────────────────────────────
    meta["exported"] = datetime.datetime.now().isoformat(timespec="seconds")
    meta["scope"] = scope_label
    meta["n_galaxies"] = str(n_galaxies)
    meta["snapshot"] = str(snap_num)
    meta["snap_label"] = snap_label

    if snap_table is not None:
        try:
            z = snap_table.snap_to_z(snap_num)
            a = snap_table.snap_to_a(snap_num)
            meta["redshift"] = np.format_float_positional(
                z, unique=True, trim="-"
            )
            meta["scale_factor"] = np.format_float_positional(
                a, unique=True, trim="-"
            )
            meta["n_snapshots"] = str(snap_table.count)
        except Exception:
            pass

    # ── Simulation parameters ─────────────────────────────────────────────
    if cfg is not None:
        meta["par_file"] = str(cfg.par_path)
        meta["output_dir"] = str(cfg.output_dir)
        meta["file_name_galaxies"] = cfg.file_name_galaxies
        meta["first_file"] = str(cfg.first_file)
        meta["last_file"] = str(cfg.last_file)
        meta["tree_type"] = cfg.tree_type
        meta["tree_name"] = cfg.tree_name
        meta["simulation_dir"] = str(cfg.simulation_dir)
        meta["snap_list_path"] = str(cfg.snap_list_path)
        meta["last_snapshot_nr"] = str(cfg.last_snapshot_nr)
        meta["num_sim_tree_files"] = str(cfg.num_sim_tree_files)

        # ── Cosmology + box ───────────────────────────────────────────────
        meta["hubble_h"] = np.format_float_positional(
            cfg.hubble_h, unique=True, trim="-"
        )
        meta["H0_km_s_Mpc"] = np.format_float_positional(
            cfg.hubble_h * 100, unique=True, trim="-"
        )
        meta["omega_matter"] = np.format_float_positional(
            cfg.omega, unique=True, trim="-"
        )
        meta["omega_lambda"] = np.format_float_positional(
            cfg.omega_lambda, unique=True, trim="-"
        )
        meta["box_size_Mpch"] = np.format_float_positional(
            cfg.box_size, unique=True, trim="-"
        )
        meta["part_mass_1e10Msun_h"] = np.format_float_positional(
            cfg.part_mass, unique=True, trim="-"
        )

        # Extra keys from the par file (anything not in the standard fields)
        for k, v in sorted(cfg.extra.items()):
            meta[f"par_{k}"] = str(v)

    meta["units_note"] = (
        "Raw SAGE26 output — no unit conversion. "
        "Masses in 10^10 Msun/h, positions in Mpc/h, SFR in Msun/yr."
    )

    # ── Selection bounds ──────────────────────────────────────────────────
    if scope_bounds:
        for k, v in scope_bounds.items():
            meta[f"selection_{k}"] = str(v)

    return meta


def write_catalogue(
    hdf5_path: Path,
    snap_num: int,
    snap_label: str,
    sage_indices: np.ndarray,
    out_path: Path,
    fmt: str,
    hubble_h: float = 0.73,
    scope_label: str = "",
    scope_bounds: dict | None = None,
    cfg: SimConfig | None = None,
    snap_table: SnapshotTable | None = None,
    flat: bool = False,
) -> str:
    """Export raw SAGE HDF5 galaxy rows to *out_path* in format *fmt*.

    No unit conversion is applied — values are exactly as stored by SAGE26.
    ``flat=True`` reads a flat lightcone file (top-level datasets, no
    ``Snap_N`` group), which also carries any synthetic-photometry columns.
    Returns the resolved output path string.
    """
    sage_indices = np.asarray(sage_indices, dtype=np.int64)
    if len(sage_indices) == 0:
        raise ValueError("No galaxies match the selected scope.")

    if flat:
        data, units = _read_flat_fields(hdf5_path, sage_indices)
    else:
        data, units = _read_snap_fields(hdf5_path, snap_num, sage_indices)

    meta = _build_metadata(
        snap_num=snap_num,
        snap_label=snap_label,
        n_galaxies=len(sage_indices),
        scope_label=scope_label,
        scope_bounds=scope_bounds,
        cfg=cfg,
        snap_table=snap_table,
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "csv":
        _write_csv(data, units, meta, out_path)
    elif fmt == "hdf5":
        _write_hdf5(data, units, meta, out_path)
    elif fmt == "fits":
        _write_fits(data, units, meta, out_path)
    elif fmt == "txt":
        _write_txt(data, units, meta, out_path)
    else:
        raise ValueError(f"Unknown format: {fmt!r}")

    return str(out_path)


# ── Formatting ────────────────────────────────────────────────────────────────


def _fmt(val, dtype) -> str:
    """Format a scalar without scientific notation and without truncation.

    Integers → plain int string.
    Floats → fixed-point with just enough digits to round-trip the stored
    value (np.format_float_positional with unique=True).
    """
    if dtype.kind in ("i", "u"):
        return str(int(val))
    return np.format_float_positional(val, unique=True, trim="-")


# ── Format writers ────────────────────────────────────────────────────────────


def _write_csv(data: dict, units: dict, meta: dict, out_path: Path) -> None:
    import csv

    scalar = _scalar_only(data)
    with open(out_path, "w", newline="") as f:
        for k, v in meta.items():
            f.write(f"# {k}: {v}\n")
        unit_notes = ", ".join(
            f"{k}[{u}]" for k, u in units.items() if u and k in scalar
        )
        if unit_notes:
            f.write(f"# column_units: {unit_notes}\n")
        writer = csv.writer(f)
        writer.writerow(list(scalar.keys()))
        arrs = list(scalar.values())
        n = len(arrs[0])
        for i in range(n):
            writer.writerow([_fmt(a[i], a.dtype) for a in arrs])


def _write_txt(data: dict, units: dict, meta: dict, out_path: Path) -> None:
    scalar = _scalar_only(data)
    cols = list(scalar.keys())
    arrs = [scalar[c] for c in cols]
    with open(out_path, "w") as f:
        for k, v in meta.items():
            f.write(f"# {k}: {v}\n")
        header = "  ".join(
            f"{c}[{units.get(c, '')}]" if units.get(c) else c for c in cols
        )
        f.write(f"# {header}\n")
        n = len(arrs[0])
        for i in range(n):
            f.write("  ".join(_fmt(a[i], a.dtype) for a in arrs) + "\n")


def _write_hdf5(data: dict, units: dict, meta: dict, out_path: Path) -> None:
    with h5py.File(str(out_path), "w") as hf:
        mg = hf.create_group("Metadata")
        for k, v in meta.items():
            mg.attrs[k] = str(v)
        gg = hf.create_group("Galaxies")
        for key, arr in data.items():
            ds = gg.create_dataset(
                key, data=arr, compression="gzip", compression_opts=4
            )
            u = units.get(key, "")
            if u:
                ds.attrs["units"] = u


def _write_fits(data: dict, units: dict, meta: dict, out_path: Path) -> None:
    from astropy.io import fits
    from astropy.table import Table

    scalar = _scalar_only(data)
    tbl = Table()
    for col, arr in scalar.items():
        tbl[col] = arr
        u = units.get(col, "")
        if u:
            tbl[col].unit = u

    hdr = fits.Header()
    for k, v in meta.items():
        # FITS keyword: max 8 chars, uppercase, no spaces
        fits_key = k.upper().replace(" ", "_")[:8]
        hdr[fits_key] = str(v)[:72]

    hdu = fits.BinTableHDU(tbl, header=hdr, name="GALAXIES")
    fits.HDUList([fits.PrimaryHDU(), hdu]).writeto(
        str(out_path), overwrite=True
    )
