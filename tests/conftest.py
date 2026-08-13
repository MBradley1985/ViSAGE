"""Shared fixtures for the ViSAGE test suite."""

from __future__ import annotations

import struct
from pathlib import Path

import h5py
import numpy as np
import pytest

from visage.io.halo_reader import HALO_DTYPE

FIXTURE_DIR = Path(__file__).parent / "data"


def _write_mini_tree(out: Path, mass_field: str = "Mvir") -> Path:
    """Write one lhalo_binary tree file: 3 snapshots, 90 haloes.

    mass_field picks which struct column carries the halo mass — tree sets
    differ on this, see visage.io.halo_reader.MASS_FIELDS.
    """
    rng = np.random.default_rng(0)
    n_forests = 3
    n_halos = 90
    halos_per_forest = np.array([30, 30, 30], dtype=np.int32)

    halos = np.zeros(n_halos, dtype=HALO_DTYPE)
    halos[mass_field] = rng.uniform(0.01, 10.0, n_halos)  # in 1e10 Msun/h
    halos["Pos"] = rng.uniform(0, 62.5, (n_halos, 3)).astype(np.float32)
    # Assign each forest a different SnapNum: 61, 62, 63
    for i, snap in enumerate([61, 62, 63]):
        halos[i * 30 : (i + 1) * 30]["SnapNum"] = snap

    with open(out, "wb") as f:
        np.array([n_forests], dtype=np.int32).tofile(f)
        np.array([n_halos], dtype=np.int32).tofile(f)
        halos_per_forest.tofile(f)
        halos.tofile(f)

    return out


@pytest.fixture(scope="session")
def mini_tree_path(tmp_path_factory) -> Path:
    """One synthetic lhalo_binary tree file with 3 snapshots, 90 haloes."""
    return _write_mini_tree(tmp_path_factory.mktemp("trees") / "trees_063.0")


@pytest.fixture(scope="session")
def mini_tree_tophat_path(tmp_path_factory) -> Path:
    """Same tree, but with Mvir left at zero and the mass in M_TopHat."""
    return _write_mini_tree(
        tmp_path_factory.mktemp("trees_tophat") / "trees_063.0",
        mass_field="M_TopHat",
    )


@pytest.fixture(scope="session")
def mini_hdf5_path(tmp_path_factory) -> Path:
    """Synthetic SAGE HDF5 file with 3 snapshots, 30 galaxies each."""
    out = tmp_path_factory.mktemp("galaxies") / "model_0.hdf5"
    rng = np.random.default_rng(1)

    with h5py.File(out, "w") as f:
        for snap in [61, 62, 63]:
            grp = f.create_group(f"Snap_{snap}")
            n = 30
            grp.create_dataset(
                "Posx", data=rng.uniform(0, 62.5, n).astype(np.float32)
            )
            grp.create_dataset(
                "Posy", data=rng.uniform(0, 62.5, n).astype(np.float32)
            )
            grp.create_dataset(
                "Posz", data=rng.uniform(0, 62.5, n).astype(np.float32)
            )
            grp.create_dataset(
                "StellarMass",
                data=rng.uniform(0.01, 1.0, n).astype(np.float32),
            )
            grp.create_dataset(
                "Mvir",
                data=rng.uniform(0.1, 10.0, n).astype(np.float32),
            )
            grp.create_dataset(
                "BulgeMass",
                data=rng.uniform(0.0, 0.3, n).astype(np.float32),
            )
            grp.create_dataset(
                "ColdGas",
                data=rng.uniform(0.0, 0.5, n).astype(np.float32),
            )
            grp.create_dataset(
                "SfrDisk",
                data=rng.uniform(0.0, 0.01, n).astype(np.float32),
            )
            grp.create_dataset(
                "SfrBulge",
                data=rng.uniform(0.0, 0.001, n).astype(np.float32),
            )
            grp.create_dataset(
                "Type",
                data=rng.integers(0, 2, n).astype(np.int32),
            )
    return out


@pytest.fixture(scope="session")
def mini_a_list_path(tmp_path_factory) -> Path:
    """64 scale factors from z~127 to z=0 (same as miniMillennium)."""
    out = tmp_path_factory.mktemp("snaplist") / "millennium.a_list"
    a_values = np.linspace(0.0078125, 1.0, 64)
    out.write_text("\n".join(f"{a:.8f}" for a in a_values) + "\n")
    return out


@pytest.fixture(scope="session")
def mini_par_path(
    tmp_path_factory, mini_hdf5_path, mini_a_list_path, mini_tree_path
) -> Path:
    """Minimal .par file pointing to the synthetic fixtures."""
    tree_dir = mini_tree_path.parent
    out = tmp_path_factory.mktemp("par") / "test.par"
    out.write_text(
        f"OutputDir           {mini_hdf5_path.parent}\n"
        f"FileNameGalaxies    model\n"
        f"FirstFile           0\n"
        f"LastFile            0\n"
        f"OutputFormat        sage_hdf5\n"
        f"TreeName            trees_063\n"
        f"TreeType            lhalo_binary\n"
        f"SimulationDir       {tree_dir}\n"
        f"FileWithSnapList    {mini_a_list_path}\n"
        f"LastSnapShotNr      63\n"
        f"NumSimulationTreeFiles  1\n"
        f"Omega               0.25\n"
        f"OmegaLambda         0.75\n"
        f"Hubble_h            0.73\n"
        f"BoxSize             62.5\n"
        f"PartMass            0.086\n"
    )
    return out
