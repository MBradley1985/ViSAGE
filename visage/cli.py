from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from visage._version import __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="visage",
        description="Interactive 3D viewer for SAGE galaxy formation outputs.",
    )
    p.add_argument(
        "--par",
        default=None,
        metavar="FILE",
        help=(
            "Path to SAGE .par file (e.g. input/millennium.par). "
            "Omit to start in Launch Mode (interactive setup wizard)."
        ),
    )
    p.add_argument(
        "--par-dir",
        metavar="DIR",
        default=None,
        help=(
            "Directory to scan for additional .par files (default: parent dir "
            "of --par). The menu lists all .par files found here so you can "
            "switch between or overlay multiple models."
        ),
    )
    p.add_argument(
        "--lightcone",
        default=None,
        metavar="FILE",
        help=(
            "Path to a cli_lightcone HDF5 output file. Opens the full Explore "
            "UI on the lightcone (a flat galaxy cone) instead of a SAGE box; "
            "the snapshot slider highlights redshift/time shells."
        ),
    )
    p.add_argument(
        "--snap",
        type=int,
        default=None,
        metavar="N",
        help="Initial snapshot number (default: last snapshot)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for the Trame web server (default: 8080)",
    )
    p.add_argument(
        "--n-jobs",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 1),
        metavar="N",
        help="Worker threads for parallel halo loading (default: CPUs-1)",
    )
    p.add_argument(
        "--min-halo-mass",
        type=float,
        default=1.0e10,
        metavar="MSUN",
        help="Minimum halo mass in Msun (default: 1e10)",
    )
    p.add_argument(
        "--min-stellar-mass",
        type=float,
        default=1.0e8,
        metavar="MSUN",
        help="Minimum stellar mass in Msun (default: 1e8)",
    )
    p.add_argument(
        "--max-halos",
        type=int,
        default=100_000,
        metavar="N",
        help="Downsample ceiling for haloes per snapshot (default: 100000)",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"visage {__version__}",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.lightcone is not None:
        _lightcone_mode(args)
    elif args.par is None:
        _launch_mode(args)
    else:
        _explore_mode(args)


def _launch_mode(args) -> None:
    from visage._version import __version__ as _ver

    print(f"\nViSAGE {_ver}  —  Launch Mode")
    print(f"Port     : {args.port}")
    print(f"\n  --> Open http://localhost:{args.port} in your browser\n")

    from visage.wizard.launch import create_launch_app

    server = create_launch_app(port=args.port)
    server.start(port=args.port, open_browser=False)


def _explore_mode(args) -> None:
    par_path = Path(args.par)
    if not par_path.exists():
        print(f"Error: par file not found: {par_path}", file=sys.stderr)
        sys.exit(1)

    from visage._version import __version__ as _ver

    print(f"\nViSAGE {_ver}  —  Explore Mode")
    print(f"Par file : {par_path.resolve()}")
    print(f"Workers  : {args.n_jobs}")
    print("\n[1/4] Parsing par file and snapshot table...")

    from visage.app import create_app

    print("[2/4] Loading initial snapshot (haloes + galaxies)...")
    server, scene = create_app(
        par_path=par_path,
        par_dir=args.par_dir,
        initial_snap=args.snap,
        n_jobs=args.n_jobs,
        min_halo_mass=args.min_halo_mass,
        min_stellar_mass=args.min_stellar_mass,
        max_halos=args.max_halos,
        port=args.port,
    )
    print("[3/4] Building scene and Trame UI...")
    print(f"Snapshot : {scene.snap_label}")
    print(f"[4/4] Starting server on port {args.port}...")
    print(
        f"         Background: preloading all {scene.snap_count} snapshots into memory..."
    )
    print(f"\n  --> Open http://localhost:{args.port} in your browser\n")

    server.start(port=args.port, open_browser=False)


def _lightcone_mode(args) -> None:
    lc_path = Path(args.lightcone)
    if not lc_path.exists():
        print(f"Error: lightcone file not found: {lc_path}", file=sys.stderr)
        sys.exit(1)

    from visage._version import __version__ as _ver

    print(f"\nViSAGE {_ver}  —  Lightcone Mode")
    print(f"Lightcone : {lc_path.resolve()}")
    print("\n[1/3] Reading lightcone galaxies + host haloes...")

    from visage.app import create_app

    server, scene = create_app(
        par_path="",
        initial_snap=args.snap,
        n_jobs=args.n_jobs,
        min_halo_mass=args.min_halo_mass,
        min_stellar_mass=args.min_stellar_mass,
        max_halos=args.max_halos,
        port=args.port,
        lightcone_path=lc_path,
    )
    print("[2/3] Building scene and Trame UI...")
    print(f"[3/3] Starting server on port {args.port}...")
    print(f"\n  --> Open http://localhost:{args.port} in your browser\n")

    server.start(port=args.port, open_browser=False)


if __name__ == "__main__":
    main()
