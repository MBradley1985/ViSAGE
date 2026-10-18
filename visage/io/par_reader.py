from __future__ import annotations

from pathlib import Path

from visage.config import SimConfig
from visage.system import native_path


def parse_par(par_path: str | Path) -> SimConfig:
    """Parse a SAGE .par file into a SimConfig.

    Handles both absolute and relative paths. Relative paths in the par file
    are resolved relative to the par file's parent directory (the SAGE root).
    On Windows, /mnt/c/... paths (written for SAGE running inside WSL) are
    read as C:\\... .
    """
    par_path = Path(par_path).resolve()
    # Paths in the par file are relative to the SAGE root (parent of input/)
    root = par_path.parent.parent

    raw: dict[str, str] = {}
    with open(par_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            # Strip inline comments — SAGE par files use either '%' (old
            # style) or ';' (newer style) as the comment marker.
            for marker in ("%", ";", "#"):
                if marker in line:
                    line = line[: line.index(marker)].strip()
            if not line:
                continue
            # Skip snapshot list arrow
            if line.startswith("->"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                raw[parts[0]] = parts[1].strip()

    def _path(key: str, default: str) -> Path:
        p = native_path(raw.get(key, default))
        return p if p.is_absolute() else root / p

    def _int(key: str, default: int) -> int:
        return int(raw.get(key, default))

    def _float(key: str, default: float) -> float:
        return float(raw.get(key, default))

    def _str(key: str, default: str) -> str:
        return raw.get(key, default)

    known_keys = {
        "OutputDir",
        "FileNameGalaxies",
        "FirstFile",
        "LastFile",
        "OutputFormat",
        "TreeName",
        "TreeType",
        "SimulationDir",
        "FileWithSnapList",
        "LastSnapShotNr",
        "NumSimulationTreeFiles",
        "Omega",
        "OmegaLambda",
        "Hubble_h",
        "BoxSize",
        "PartMass",
        "NumOutputs",
    }
    extra = {k: v for k, v in raw.items() if k not in known_keys}

    snap_list_default = "input/millennium/trees/millennium.a_list"

    cfg = SimConfig(
        par_path=par_path,
        output_dir=_path("OutputDir", "output"),
        file_name_galaxies=_str("FileNameGalaxies", "model"),
        first_file=_int("FirstFile", 0),
        last_file=_int("LastFile", 7),
        output_format=_str("OutputFormat", "sage_hdf5"),
        tree_name=_str("TreeName", "trees_063"),
        tree_type=_str("TreeType", "lhalo_binary"),
        simulation_dir=_path("SimulationDir", "input/millennium/trees"),
        snap_list_path=_path("FileWithSnapList", snap_list_default),
        last_snapshot_nr=_int("LastSnapShotNr", 63),
        num_sim_tree_files=_int("NumSimulationTreeFiles", 8),
        omega=_float("Omega", 0.25),
        omega_lambda=_float("OmegaLambda", 0.75),
        hubble_h=_float("Hubble_h", 0.73),
        box_size=_float("BoxSize", 62.5),
        part_mass=_float("PartMass", 0.086),
        extra=extra,
    )
    return cfg
