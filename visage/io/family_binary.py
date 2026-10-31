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
    """SAGE26's fields that DarkSAGE gives by radial bin or another name."""
    names = gals.dtype.names
    if "ClassicalBulgeMass" not in names:
        return {}

    def total(*fields):
        return sum(gals[f].sum(axis=1) for f in fields)

    return {
        "BulgeMass": total("ClassicalBulgeMass", "SecularBulgeMass"),
        "MetalsBulgeMass": total(
            "ClassicalMetalsBulgeMass", "SecularMetalsBulgeMass"
        ),
        "SfrDisk": gals["DiscSFR"].sum(axis=1),
        "SfrBulge": gals["SfrMerge"] + gals["SfrInstab"],
        "H2gas": gals["DiscH2"].sum(axis=1),
        "H1gas": gals["DiscHI"].sum(axis=1),
        "TimeOfLastMajorMerger": gals["LastMajorMerger"],
        "TimeOfLastMinorMerger": gals["LastMinorMerger"],
    }


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
