from __future__ import annotations

from pathlib import Path


def find_par_files(scan_dir: str | Path) -> list[Path]:
    """Return a sorted list of .par files in `scan_dir` (non-recursive)."""
    d = Path(scan_dir)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.par") if p.is_file())


def _output_folder(par: Path) -> str | None:
    """The last folder of a .par file's OutputDir, or None."""
    try:
        text = par.read_text(errors="ignore")
    except OSError:
        return None
    for line in text.splitlines():
        words = line.split()
        if len(words) >= 2 and words[0] == "OutputDir":
            return Path(words[1]).name
    return None


def find_models(
    output_dir: str | Path,
    par_dir: str | Path | None = None,
) -> list[dict]:
    """Discover SAGE models by scanning the output directory.

    Each subdirectory of `output_dir` that contains a `model_0.hdf5` is one
    model, named after the subdirectory.  Pairs each with the `.par` file
    from `par_dir` (defaults to the sibling `input/` directory in the typical
    SAGE layout) of the same name, or else whose OutputDir is that
    subdirectory.  Models without a discoverable `.par` are skipped.

    Returns list[{"name", "par", "hdf5"}], sorted by name.
    """
    out_d = Path(output_dir)
    if not out_d.is_dir():
        return []
    if par_dir is None:
        par_dir = out_d.parent / "input"
    par_d = Path(par_dir)

    by_output: dict[str, Path] = {}
    for par in find_par_files(par_d):
        by_output.setdefault(_output_folder(par), par)

    found: list[dict] = []
    for sub in sorted(out_d.iterdir()):
        if not sub.is_dir():
            continue
        hdf5 = sub / "model_0.hdf5"
        if not hdf5.is_file():
            continue
        par_candidate = par_d / f"{sub.name}.par"
        if not par_candidate.is_file():
            par_candidate = by_output.get(sub.name)
        if par_candidate is None:
            # Skip models without a matching .par for now — Model() still
            # needs it for tree paths.  Could be lifted once SimConfig can
            # be derived from the HDF5 alone.
            continue
        found.append({"name": sub.name, "par": par_candidate, "hdf5": hdf5})
    return found
