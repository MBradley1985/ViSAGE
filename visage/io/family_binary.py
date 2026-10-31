"""Binary output of the wider SAGE family as a run ViSAGE can read.

DarkSAGE and DustySAGE write SAGE's binary format: for each snapshot, files
`<name>_z<redshift>_<n>` holding Ntrees, the galaxy total, the galaxies per
tree, then packed C structs. ViSAGE reads SAGE26's HDF5, so a finished run is
converted to that layout, `<name>_0.hdf5`, with `Snap_<n>` groups and a
`Header`. The struct is read from the code's own header, so the conversion
follows the code. Models' extra fields keep their names: DarkSAGE's radial
arrays stay 2D.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import h5py
import numpy as np

TYPES = {
    "short": "i2",
    "int": "i4",
    "long long": "i8",
    "float": "f4",
    "double": "f8",
}
# Fields under SAGE26's name.
RENAME = {
    "DiskScaleRadius": "DiskRadius",
    "ICS": "IntraClusterStars",
    "MetalsICS": "MetalsIntraClusterStars",
}
MIN_PLOT_KPC = 0.1  # annuli inside this are too small to mean anything
FIELD = re.compile(r"^\s*(long long|short|int|float|double)\s+(.+);\s*$")


def _clean(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _active(text: str) -> str:
    """The lines the compiler sees: nothing here is built with a -D flag,
    so #ifdef branches are out and their #else branches in."""
    keep, out = [True], []
    for line in text.splitlines():
        word = line.split()[0] if line.split() else ""
        if word in ("#ifdef", "#if"):
            keep.append(False)
        elif word == "#ifndef":
            keep.append(True)
        elif word == "#else":
            keep[-1] = not keep[-1]
        elif word == "#endif":
            keep.pop()
        elif all(keep):
            out.append(line)
    return "\n".join(out)


def struct_dtype(
    header: str | Path, name: str = "GALAXY_OUTPUT", defines: dict = None
) -> np.dtype:
    """The numpy layout of C struct `name` in `header`, padded as the
    compiler pads it."""
    text = _active(_clean(Path(header).read_text()))
    macros = {
        k: int(v)
        for k, v in re.findall(r"#define\s+(\w+)\s+(\d+)\s*$", text, re.M)
    } | (defines or {})
    match = re.search(rf"struct\s+{name}\s*\{{(.*?)\n\s*\}}", text, re.S)
    if match is None:
        raise ValueError(f"No struct {name} in {header}")
    names, formats = [], []
    for line in match.group(1).splitlines():
        found = FIELD.match(line)
        if found is None:
            continue
        kind, rest = found.groups()
        for item in rest.split(","):
            m = re.match(r"\s*(\w+)\s*((?:\[.+?\])*)\s*$", item)
            field, sizes = m.groups()
            fmt = TYPES[kind]
            shape = tuple(
                int(eval(n, {"__builtins__": {}}, macros))  # noqa: S307
                for n in re.findall(r"\[(.+?)\]", sizes)
            )
            if shape:
                fmt = (fmt, shape)
            names.append(field)
            formats.append(fmt)
    return np.dtype({"names": names, "formats": formats}, align=True)


def read_par(path: str | Path) -> dict:
    """A SAGE parameter file as {name: text}."""
    out = {}
    for line in Path(path).read_text().splitlines():
        line = re.split(r"[;%#]", line, maxsplit=1)[0].strip()
        parts = line.split()
        if len(parts) >= 2 and parts[0] != "->":
            out[parts[0]] = parts[1]
    return out


def record_dtype(header: str | Path, path: str | Path) -> np.dtype:
    """The output struct whose size fits file `path`: DarkSAGE writes a
    larger one with AgeStructOut on."""
    with open(path, "rb") as f:
        ntrees, total = np.fromfile(f, np.int32, 2)
    size = Path(path).stat().st_size - 8 - 4 * int(ntrees)
    text = Path(header).read_text()
    for name in re.findall(r"struct\s+(GALAXY_OUTPUT\w*)\s*(?://.*)?\n", text):
        dtype = struct_dtype(header, name)
        if total and size == total * dtype.itemsize:
            return dtype
    raise ValueError(f"No output struct in {header} fits {path}")


def read_galaxies(path: str | Path, dtype: np.dtype) -> np.ndarray:
    """The galaxies of one output file."""
    with open(path, "rb") as f:
        ntrees, total = np.fromfile(f, np.int32, 2)
        f.seek(4 * int(ntrees), 1)
        gals = np.fromfile(f, dtype, int(total))
    if len(gals) != total:
        raise ValueError(f"{path} is short: {len(gals)} of {total} galaxies")
    return gals


def snapshot_files(directory: Path, name: str) -> dict:
    """{redshift text: output files}, in file order."""
    found: dict = {}
    for p in directory.glob(f"{name}_z*_*"):
        m = re.fullmatch(rf"{re.escape(name)}_z([\d.]+)_(\d+)", p.name)
        if m:
            found.setdefault(m.group(1), []).append((int(m.group(2)), p))
    return {z: [p for _, p in sorted(v)] for z, v in found.items()}


def _derived(gals: np.ndarray) -> dict:
    """SAGE26's fields that a model gives another way, and the ratios its
    extra physics is coloured by."""
    names = gals.dtype.names
    out = {}
    if "ClassicalBulgeMass" in names:  # DarkSAGE: by radial bin or channel

        def total(*fields):
            return sum(gals[f].sum(axis=1) for f in fields)

        merger = total("ClassicalBulgeMass")
        secular = total("SecularBulgeMass")
        r_m = gals["HalfMassRadiusMergerBulge"]
        r_i = gals["HalfMassRadiusInstabilityBulge"]
        h2, hi = total("DiscH2"), total("DiscHI")
        out = {
            "BulgeMass": merger + secular,
            "MergerBulgeMass": merger,
            "InstabilityBulgeMass": secular,
            "MergerBulgeRadius": r_m,
            "InstabilityBulgeRadius": r_i,
            "BulgeRadius": (merger * r_m + secular * r_i)
            / np.maximum(merger + secular, 1e-30),
            "MetalsBulgeMass": total(
                "ClassicalMetalsBulgeMass", "SecularMetalsBulgeMass"
            ),
            "SfrDisk": total("DiscSFR"),
            "SfrBulge": gals["SfrMerge"] + gals["SfrInstab"],
            "H2gas": h2,
            "H1gas": hi,
            "H2Fraction": h2 / np.maximum(h2 + hi, 1e-30),
            "TimeOfLastMajorMerger": gals["LastMajorMerger"],
            "TimeOfLastMinorMerger": gals["LastMinorMerger"],
        }
    if "ColdDust" in names:  # DustySAGE
        cold = gals["ColdGas"]
        h2, hi = gals["f_H2"] * cold, gals["f_HI"] * cold
        out = {
            "H2gas": h2,
            "H1gas": hi,
            "H2Fraction": h2 / np.maximum(h2 + hi, 1e-30),
            "DustToGas": gals["ColdDust"] / np.maximum(cold, 1e-30),
            "InstabilityBulgeMass": gals["BulgeInstability"],
            "MergerBulgeMass": gals["BulgeMass"] - gals["BulgeInstability"],
        }
    return out


def radial_profiles(path, snap: int, rows, hubble_h: float) -> dict:
    """DarkSAGE's discs for galaxy rows of a converted run: "r" (kpc, annulus
    middles) and surface densities (Msun/pc^2) of stars, gas, HI and H2, and
    of star formation (Msun/yr/kpc^2)."""
    rows = np.atleast_1d(rows)
    with h5py.File(path, "r") as f:
        g = f[f"Snap_{snap}"]
        edges = g["DiscRadii"][rows].astype(float) * 1e3 / hubble_h  # kpc
        mass = 1e10 / hubble_h
        stars = g["DiscStars"][rows].astype(float)
        if stars.ndim == 3:  # by age
            stars = stars.sum(axis=2)
        out = {
            "stars": stars,
            "gas": g["DiscGas"][rows].astype(float),
            "hi": g["DiscHI"][rows].astype(float),
            "h2": g["DiscH2"][rows].astype(float),
        }
        sfr = g["DiscSFR"][rows].astype(float)
    area = np.maximum(np.pi * (edges[:, 1:] ** 2 - edges[:, :-1] ** 2), 1e-12)
    res = {k: v * mass / (area * 1e6) for k, v in out.items()}
    res["sfr"] = sfr / area
    res["r"] = 0.5 * (edges[:, 1:] + edges[:, :-1])
    return res


def plot_profile(prof: dict, label: str) -> bytes:
    """One galaxy's radial profiles as a PNG."""
    import io

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=(8.5, 4.6), dpi=130)
    FigureCanvasAgg(fig)
    a, b = fig.subplots(1, 2)
    r = prof["r"][0]
    for key, name, colour in (
        ("stars", "Stars", "#d9622b"),
        ("gas", "Cold gas", "#7a2fb0"),
        ("hi", "HI", "#3aa655"),
        ("h2", "H2", "#2a78b5"),
    ):
        v = prof[key][0]
        keep = (v > 0) & (r > MIN_PLOT_KPC)
        a.plot(r[keep], v[keep], label=name, color=colour, lw=2)
    a.set(
        xscale="log",
        yscale="log",
        xlabel="R (kpc)",
        ylabel="Surface density (M☉ pc⁻²)",
    )
    a.legend(frameon=False)
    s = prof["sfr"][0]
    keep = (s > 0) & (r > MIN_PLOT_KPC)
    b.plot(r[keep], s[keep], color="#17324d", lw=2)
    b.set(
        xscale="log",
        yscale="log",
        xlabel="R (kpc)",
        ylabel="Star formation (M☉ yr⁻¹ kpc⁻²)",
    )
    fig.suptitle(f"Galaxy {label}: DarkSAGE discs")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()


def _write_snapshot(group, gals: np.ndarray) -> None:
    for field in gals.dtype.names:
        data = gals[field]
        if (
            data.ndim == 2
            and data.shape[1] == 3
            and field in ("Pos", "Vel", "Spin")
        ):
            for i, axis in enumerate("xyz"):
                group[f"{field}{axis}"] = data[:, i]
        elif field in ("ICS", "MetalsICS") and data.ndim == 2:
            # DarkSAGE's are by radial bin; the total is SAGE26's field.
            group[RENAME[field]] = data.sum(axis=1)
            group[f"{field}Radial"] = data
        else:
            group[RENAME.get(field, field)] = data
    for field, data in _derived(gals).items():
        group[field] = data


def convert(par: str | Path, header: str | Path, model: str) -> Path:
    """Write a run's binary output as `<OutputDir>/<name>_0.hdf5`; the path."""
    par = Path(par)
    p = read_par(par)
    out_dir = Path(p["OutputDir"])
    if not out_dir.is_absolute():
        out_dir = par.parent / out_dir
    name = p.get("FileNameGalaxies", "model")
    alist = Path(p["FileWithSnapList"])
    if not alist.is_absolute():
        alist = par.parent / alist
    a = np.loadtxt(alist)
    z_snap = 1 / a - 1
    files = snapshot_files(out_dir, name)
    if not files:
        raise FileNotFoundError(f"No {name}_z* files in {out_dir}")
    dtype = record_dtype(header, next(iter(files.values()))[0])
    box = float(p.get("BoxLen", p.get("BoxSize", 0.0)))
    out = out_dir / f"{name}_0.hdf5"
    with h5py.File(out, "w") as f:
        hdr = f.create_group("Header")
        sim = hdr.create_group("Simulation")
        sim.attrs["hubble_h"] = float(p["Hubble_h"])
        sim.attrs["omega_matter"] = float(p["Omega"])
        sim.attrs["omega_lambda"] = float(p["OmegaLambda"])
        sim.attrs["box_size"] = box
        sim.attrs["FileWithSnapList"] = str(alist)
        sim.attrs["LastSnapshotNr"] = len(a) - 1
        run = hdr.create_group("Runtime")
        for key in ("PartMass", "BaryonFrac", "Yield", "RecycleFraction"):
            if key in p:
                run.attrs[key] = float(p[key])
        hdr.create_group("Misc").attrs["sage_version"] = model
        hdr.create_group("output_snapshots")
        reds = hdr.create_group("snapshot_redshifts")
        for i, z in enumerate(z_snap):
            reds.attrs[f"Snap_{i}"] = float(z)
        for text, paths in files.items():
            gals = np.concatenate([read_galaxies(q, dtype) for q in paths])
            snap = int(np.abs(z_snap - float(text)).argmin())
            group = f.create_group(f"Snap_{snap}")
            group.attrs["num_gals"] = len(gals)
            group.attrs["redshift"] = float(z_snap[snap])
            _write_snapshot(group, gals)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="visage-family",
        description="Convert a DarkSAGE or DustySAGE run for ViSAGE.",
    )
    ap.add_argument("--par", required=True, metavar="FILE")
    ap.add_argument("--header", required=True, metavar="FILE")
    ap.add_argument("--model", required=True)
    a = ap.parse_args(argv)
    print(convert(a.par, a.header, a.model))


if __name__ == "__main__":
    main()
