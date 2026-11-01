"""Make plots in a process of their own: `python -m visage.plots request`.

`request` is a JSON file of what to plot, with its galaxies in a .npz beside
it: `rows`, the chosen rows of the current snapshot, or of the cone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from visage.plots import catalogue as cat
from visage.plots import history, local, observed, style  # noqa: F401
from visage.plots.base import PLOTS, Options, Plot
from visage.utils import regions


def box_rows(req: dict, snap: int) -> np.ndarray:
    """The rows of snapshot `snap` the request's selection keeps."""
    from visage.io.galaxy_reader import load_galaxy_snapshot
    from visage.utils.filters import galaxy_mask

    gal = load_galaxy_snapshot(
        hdf5_path=req["path"],
        snap_num=snap,
        min_stellar_mass=req["min_stellar_mass"],
        hubble_h=req["h"],
        scale_factors=np.array(req["scale_factors"]),
        omega_m=req["omega_m"],
        omega_l=req["omega_l"],
        min_particles=req["min_particles"],
        particle_mass=req["particle_mass"],
    )
    if gal.count == 0:
        return np.zeros(0, int)
    mask = np.ones(gal.count, bool)
    if req["filters"] is not None:
        mask &= galaxy_mask(
            gal, req["fields"], SimpleNamespace(**req["filters"])
        )
    region = req["region"]
    if region:
        mask &= regions.mask(
            region,
            gal.positions,
            region.get("box_size"),
            regions.identity(gal),
        )
    return np.asarray(gal.sage_indices)[mask]


def box_views(req: dict) -> list:
    """A Sample for every snapshot, from the first with galaxies."""
    h = req["h"]
    zs = 1.0 / np.array(req["scale_factors"]) - 1.0
    views = []
    snaps = req["snapshots"]
    for n, snap in enumerate(snaps):
        print(f"progress {n / len(snaps):.3f} snapshot", flush=True)
        rows = box_rows(req, snap)
        if not len(rows):
            continue
        v = cat.Sample(
            cat.box_reader(req["path"], snap),
            rows,
            h,
            float(zs[snap]),
            req["volume"],
        )
        v.e_z = _e_z(v.z, req)
        views.append(v)
    return views


def _e_z(z: float, req: dict) -> float:
    return float(np.sqrt(req["omega_m"] * (1 + z) ** 3 + req["omega_l"]))


def cone_views(req: dict, rows: np.ndarray) -> list:
    """A Sample for the shell each of the cone's snapshots fills."""
    read = cat.cone_reader(req["path"])
    z, snap = read(local.Z_FIELD), read("SnapNum")
    h, om, ol = req["h"], req["omega_m"], req["omega_l"]
    area = cat.cone_area(read("ra"), read("dec"))
    views = []
    picked = snap[rows]
    for s in np.unique(snap):
        here = z[snap == s]
        v = cat.Sample(
            read,
            rows[picked == s],
            h,
            float(np.median(here)),
            (
                cat.shell_volume(area, here.min(), here.max(), h, om, ol)
                if req["has_volume"]
                else None
            ),
        )
        v.e_z = _e_z(v.z, req)
        v.area = area
        views.append(v)
    return views


def local_sample(req: dict, rows: np.ndarray) -> cat.Sample:
    h = req["h"]
    if req["mode"] == "box":
        return cat.Sample(
            cat.box_reader(req["path"], req["snap"]),
            rows,
            h,
            req["z"],
            req["local_volume"],
        )
    read = cat.cone_reader(req["path"])
    z = read(local.Z_FIELD)
    pick = rows[(z[rows] >= req["zmin"]) & (z[rows] <= req["zmax"])]
    area = cat.cone_area(read("ra"), read("dec"))
    volume = None
    if req["has_volume"]:
        volume = cat.shell_volume(
            area, req["zmin"], req["zmax"], h, req["omega_m"], req["omega_l"]
        )
    s = cat.Sample(read, pick, h, float(np.median(z[pick])), volume)
    s.area = area
    return s


def main() -> None:
    req_path = Path(sys.argv[1])
    req = json.loads(req_path.read_text())
    rows = np.load(req_path.with_suffix(".npz"))["rows"]
    opts = Options(**req["options"])
    keys = req["plots"]
    needs_views = any(PLOTS[k]["kind"] == "history" for k in keys)
    views = []
    if needs_views:
        views = (
            box_views(req) if req["mode"] == "box" else cone_views(req, rows)
        )
    sample = local_sample(req, rows)
    with style.context(opts.dark):
        for n, key in enumerate(keys):
            spec = PLOTS[key]
            print(f"progress {n / len(keys):.3f} {spec['title']}", flush=True)
            if spec["kind"] != "history" and not len(sample):
                print(f"skipped {spec['title']}: no galaxies", flush=True)
                continue
            try:
                fig = spec["fn"](Plot(sample, views, opts))
            except Exception as exc:  # the other plots can still be made
                print(f"failed {spec['title']}: {exc!s}", flush=True)
                continue
            stem = Path(req["out_dir"]) / f"{key}_{req['stamp']}"
            style.save(fig, stem, req["formats"])
            print("made " + str(stem.with_suffix(".png")), flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
