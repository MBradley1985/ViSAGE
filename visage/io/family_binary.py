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

from visage.io.sage_files import open_snapshot

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
FADE_DEX = 1.5  # rotation maps fade out this far below the half-mass radius
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


def _disc_group(path, snap: int):
    """Where the annuli are: a snapshot of a run, or a flat lightcone."""
    with h5py.File(path, "r") as f:
        flat = "StellarMass" in f
    return h5py.File(path, "r") if flat else open_snapshot(path, snap)


def radial_profiles(path, snap: int, rows, hubble_h: float) -> dict:
    """The discs of galaxy rows of a run with annuli: "r" (kpc, annulus
    middles), surface densities (Msun/pc^2) of stars, gas, HI and H2, and of
    star formation (Msun/yr/kpc^2). As the run has them: "dust" (likewise),
    "z_gas" and "z_stars" (metal mass fractions), "vcirc" (km/s, at "edges",
    kpc) and "sigma" (km/s)."""
    rows = np.atleast_1d(rows)
    with _disc_group(path, snap) as g:

        def read(name):
            return np.asarray(g[name][rows]).astype(float)

        def have(name):
            return name in g

        edges = read("DiscRadii") * 1e3 / hubble_h  # kpc
        mass = 1e10 / hubble_h
        stars = read("DiscStars")
        if stars.ndim == 3:  # by age
            stars = stars.sum(axis=2)
        out = {
            "stars": stars,
            "gas": read("DiscGas"),
            "hi": read("DiscHI"),
            "h2": read("DiscH2"),
        }
        if have("DiscDust"):
            out["dust"] = read("DiscDust")
        sfr = read("DiscSFR")
        extra = {}
        if have("DiscGasMetals"):
            extra["z_gas"] = read("DiscGasMetals") / np.maximum(
                out["gas"], 1e-30
            )
        if have("DiscStarsMetals"):
            metals = read("DiscStarsMetals")
            if metals.ndim == 2:
                extra["z_stars"] = metals / np.maximum(stars, 1e-30)
        if have("DiscVcirc"):
            extra["vcirc"] = read("DiscVcirc")
        if have("VelDispStars"):
            sigma = read("VelDispStars")
            if sigma.ndim == 2:
                extra["sigma"] = sigma
        if have("SpinClassicalBulge"):
            extra["bulge_j"] = read("SpinClassicalBulge")
        if have("SpinGas") and have("SpinStars"):
            extra["spin_stars"] = read("SpinStars")
            extra["spin_dot"] = (read("SpinGas") * extra["spin_stars"]).sum(1)
    area = np.maximum(np.pi * (edges[:, 1:] ** 2 - edges[:, :-1] ** 2), 1e-12)
    res = {k: v * mass / (area * 1e6) for k, v in out.items()}
    res.update(extra)
    res["sfr"] = sfr / area
    res["r"] = 0.5 * (edges[:, 1:] + edges[:, :-1])
    res["edges"] = edges
    return res


def plot_profile(prof: dict, label: str, dark: bool = False) -> bytes:
    """One galaxy's radial profiles as a PNG."""
    from visage.plots.style import theme

    with theme(dark):
        return _profile_png(prof, label, dark)


def _profile_png(prof, label, dark) -> bytes:
    import io

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from visage.plots.style import ink

    fig = Figure(figsize=(9.5, 7.6), dpi=130)
    FigureCanvasAgg(fig)
    (a, b), (c, d) = fig.subplots(2, 2)
    r = prof["r"][0]
    middle = r > MIN_PLOT_KPC
    for key, name, colour, ls, scale in (
        ("stars", "Stars", "#d9622b", "-", 1),
        ("gas", "Cold gas", "#7a2fb0", "-", 1),
        ("hi", "HI", "#3aa655", "-", 1),
        ("h2", "H2", "#2a78b5", "-", 1),
        ("dust", "Dust x 100", ink(dark), "--", 100),
    ):
        if key in prof:
            v = prof[key][0] * scale
            keep = (v > 0) & middle
            a.plot(r[keep], v[keep], label=name, color=colour, ls=ls, lw=2)
    a.set(
        xscale="log",
        yscale="log",
        xlabel="R (kpc)",
        ylabel="Surface density (M☉ pc⁻²)",
    )
    a.legend(frameon=False)
    s = prof["sfr"][0]
    keep = (s > 0) & middle
    b.plot(r[keep], s[keep], color=ink(dark), lw=2)
    b.set(
        xscale="log",
        yscale="log",
        xlabel="R (kpc)",
        ylabel="Star formation (M☉ yr⁻¹ kpc⁻²)",
    )
    if s.max() > 0:
        b.set_ylim(s[middle].max() * 1e-7, s[middle].max() * 3)
    for key, name, colour, mass_key in (
        ("z_gas", "Gas", "#3aa655", "gas"),
        ("z_stars", "Stars", "#d9622b", "stars"),
    ):
        if key in prof:
            keep = (prof[mass_key][0] > 1e-3) & middle
            c.plot(
                r[keep],
                prof[key][0][keep] / 0.014,
                label=name,
                color=colour,
                lw=2,
            )
    if c.has_data():
        c.set(xscale="log", yscale="log", xlabel="R (kpc)", ylabel="Z / Z☉")
        c.legend(frameon=False)
    else:
        c.axis("off")
    if "vcirc" in prof:
        e = prof["edges"][0]
        keep = e > MIN_PLOT_KPC
        d.plot(
            e[keep],
            prof["vcirc"][0][keep],
            label="Rotation",
            color="#2a78b5",
            lw=2,
        )
    if "sigma" in prof:
        keep = (prof["stars"][0] > 1e-3) & middle
        d.plot(
            r[keep],
            prof["sigma"][0][keep],
            label="Stellar σ",
            color="#d9622b",
            lw=2,
        )
    if d.has_data():
        d.set(xscale="log", xlabel="R (kpc)", ylabel="km/s", ylim=(0, None))
        d.legend(frameon=False)
    else:
        d.axis("off")
    fig.suptitle(f"Galaxy {label}: discs")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()


def plot_rotation(
    prof: dict, label: str, inclination: float = 55.0, dark: bool = False
) -> bytes:
    """One galaxy's stars and gas as line-of-sight velocity maps, side by
    side, from the rotation curve of its annuli; a PNG. Each panel is framed
    on its own component, the two the same size. Gas turning against the
    stars has its velocities flipped."""
    from visage.plots.style import theme

    with theme(dark):
        return _rotation_png(prof, label, inclination, dark)


def _rotation_png(prof, label, inclination, dark) -> bytes:
    import io

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    from matplotlib.figure import Figure

    r = prof["r"][0]
    edges = prof["edges"][0]
    v = prof["vcirc"][0]
    sin_i = np.sin(np.radians(inclination))
    cos_i = np.cos(np.radians(inclination))
    # (Annuli inside MIN_PLOT_KPC can spike, and would wash out the rest.)
    top = max(float(v[edges > MIN_PLOT_KPC].max()) * sin_i, 1.0)
    norm = Normalize(-top, top)
    spin = float(prof["spin_dot"][0]) if "spin_dot" in prof else 1.0
    fig = Figure(figsize=(9.5, 4.6), dpi=130)
    FigureCanvasAgg(fig)
    axes = fig.subplots(1, 2)
    back = 0.0 if dark else 1.0
    for ax, key, name, sign in (
        (axes[0], "stars", "Stars", 1.0),
        (axes[1], "gas", "Gas", 1.0 if spin >= 0 else -1.0),
    ):
        surface = np.log10(np.maximum(prof[key][0], 1e-6))
        # Scaled at the half-mass radius: the very centre would hide the rest.
        held = prof[key][0] * np.diff(edges**2)
        k = int(np.searchsorted(np.cumsum(held), 0.5 * held.sum()))
        k = min(k, len(r) - 1)
        half = 1.1 * float(r[surface > surface[k] - FADE_DEX].max())
        grid = np.linspace(-half, half, 400)
        x, y = np.meshgrid(grid, grid)
        rr = np.maximum(np.hypot(x, y / cos_i), 1e-4)
        los = np.interp(rr, edges, v) * sin_i * x / rr
        here = np.interp(np.log(rr), np.log(np.maximum(r, 1e-4)), surface)
        shade = np.clip((here - surface[k] + FADE_DEX) / FADE_DEX, 0, 1)
        shade = shade[..., None]
        rgb = ScalarMappable(norm, "RdBu_r").to_rgba(sign * los)[..., :3]
        ax.imshow(
            rgb * shade + back * (1 - shade),
            extent=(-half, half, -half, half),
            origin="lower",
        )
        ax.set(title=name, xlabel="kpc")
    axes[0].set_ylabel("kpc")
    fig.colorbar(
        ScalarMappable(norm, "RdBu_r"),
        ax=axes,
        label="Line-of-sight velocity (km/s)",
        shrink=0.85,
    )
    angle = np.degrees(np.arccos(np.clip(spin, -1, 1)))
    note = f"gas {angle:.0f}° from stars, seen at {inclination:.0f}°"
    if spin < -0.5:
        note += "; counter-rotating gas is a model prediction"
    fig.suptitle(f"Galaxy {label}: {note}")
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
