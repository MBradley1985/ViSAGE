from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from visage import system
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
        default=system.default_workers(),
        metavar="N",
        help=(
            "Worker threads for parallel halo loading (default: the CPUs "
            "this process may use, minus one)"
        ),
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
        "--cache-gb",
        type=float,
        default=None,
        metavar="GB",
        help=(
            "Memory budget for cached snapshots in GB "
            "(default: half of system RAM; also settable via VISAGE_CACHE_GB)"
        ),
    )
    p.add_argument(
        "--max-halos",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Optional downsample ceiling for haloes per snapshot "
            "(default: no limit — every halo is loaded)"
        ),
    )
    p.add_argument(
        "--gpu",
        choices=("auto", "high", "low", "system"),
        default=os.environ.get("VISAGE_GPU", "auto"),
        help=(
            "Which GPU renders. auto (default): on a Windows laptop with "
            "integrated + discrete graphics, prefer the discrete GPU. "
            "high / low: force the discrete / integrated GPU. system: leave "
            "the OS default alone. Also settable via VISAGE_GPU."
        ),
    )
    p.add_argument(
        "--perf",
        action="store_true",
        default=bool(os.environ.get("VISAGE_PERF")),
        help=(
            "Print frame-delivery timing (fps, render / encode ms, frame "
            "size) every few seconds — for diagnosing a sluggish view. "
            "Also settable via VISAGE_PERF=1."
        ),
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"visage {__version__}",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    if system.IS_WINDOWS:
        # Status lines use characters (—, →) a redirected cp1252 console
        # can't encode; never crash over one.
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(errors="replace")
            except (AttributeError, ValueError):
                pass

    args = build_parser().parse_args(argv)
    tuned = system.tune_for_interactivity()
    if tuned:
        print(f"Tuning   : {', '.join(tuned)}")

    if args.lightcone is not None:
        _lightcone_mode(args)
    elif args.par is None:
        _launch_mode(args)
    else:
        _explore_mode(args)


def _launch_mode(args) -> None:
    from visage._version import __version__ as _ver

    print(f"\nViSAGE {_ver}  —  Launch Mode")
    print(f"System   : {system.system_summary()}")
    print(f"Port     : {args.port}")
    print(f"\n  --> Open http://localhost:{args.port} in your browser\n")

    from visage.wizard.launch import create_launch_app

    server = create_launch_app(port=args.port)
    server.start(port=args.port, open_browser=False)


def _print_system(args) -> None:
    """Report the machine and what this session will use of it, and steer
    rendering onto the right GPU before VTK creates its OpenGL context."""
    from visage.parallel.loader import default_cache_bytes

    cache = (
        int(args.cache_gb * 1024**3)
        if args.cache_gb is not None
        else default_cache_bytes()
    )
    print(f"System   : {system.system_summary(args.n_jobs, cache)}")
    note = system.apply_gpu_preference(args.gpu)
    if note:
        print(f"GPU      : {note}")


def _explore_mode(args) -> None:
    par_path = Path(args.par)
    if not par_path.exists():
        print(f"Error: par file not found: {par_path}", file=sys.stderr)
        sys.exit(1)

    from visage._version import __version__ as _ver

    print(f"\nViSAGE {_ver}  —  Explore Mode")
    print(f"Par file : {par_path.resolve()}")
    _print_system(args)
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
        cache_gb=args.cache_gb,
        port=args.port,
        perf=args.perf,
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
    _print_system(args)
    print("\n[1/3] Reading lightcone galaxies + host haloes...")

    from visage.app import create_app

    server, scene = create_app(
        par_path="",
        initial_snap=args.snap,
        n_jobs=args.n_jobs,
        min_halo_mass=args.min_halo_mass,
        min_stellar_mass=args.min_stellar_mass,
        max_halos=args.max_halos,
        cache_gb=args.cache_gb,
        port=args.port,
        lightcone_path=lc_path,
        perf=args.perf,
    )
    print("[2/3] Building scene and Trame UI...")
    print(f"[3/3] Starting server on port {args.port}...")
    print(f"\n  --> Open http://localhost:{args.port} in your browser\n")

    server.start(port=args.port, open_browser=False)


if __name__ == "__main__":
    main()
