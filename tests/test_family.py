"""DarkSAGE and DustySAGE output as a run ViSAGE reads."""

from __future__ import annotations

import h5py
import numpy as np

from visage.io import family_binary as fb

HEADER = """
#define N_BINS 3
struct GALAXY_OUTPUT
{
#ifdef MINIMIZE_IO
  short Type;
#else
  int   Type;
#endif
  long long GalaxyIndex;
  float Pos[3];
  float StellarMass;
  float DiskScaleRadius;
  float DiscGas[N_BINS];
  float DiscStars[N_BINS][N_BINS];
};
"""


def _run(tmp_path):
    (tmp_path / "h.h").write_text(HEADER)
    (tmp_path / "a.list").write_text("0.5\n1.0\n")
    out = tmp_path / "out"
    out.mkdir()
    (tmp_path / "x.par").write_text(
        f"OutputDir {out}/\nFileNameGalaxies model\nHubble_h 0.7\n"
        f"Omega 0.3\nOmegaLambda 0.7\nBoxLen 10\n"
        f"FileWithSnapList {tmp_path}/a.list ; comment\n-> 1\n"
    )
    dtype = fb.struct_dtype(tmp_path / "h.h")
    gals = np.zeros(2, dtype)
    gals["Pos"][:, 1] = (3, 4)
    gals["StellarMass"] = (1, 2)
    gals["DiskScaleRadius"] = 0.1
    with open(out / "model_z0.000_0", "wb") as f:
        np.array([1, 2, 2], np.int32).tofile(f)
        gals.tofile(f)
    return tmp_path


def test_struct_takes_the_compiled_branch_and_c_padding(tmp_path):
    (tmp_path / "h.h").write_text(HEADER)
    d = fb.struct_dtype(tmp_path / "h.h")
    assert d["Type"].itemsize == 4
    assert d.fields["GalaxyIndex"][1] == 8
    assert d["DiscStars"].shape == (3, 3)


def test_convert_writes_the_layout_viewer_reads(tmp_path):
    t = _run(tmp_path)
    path = fb.convert(t / "x.par", t / "h.h", "Test")
    with h5py.File(path) as f:
        g = f["Snap_1"]
        assert path.name == "model_0.hdf5"
        assert list(g["Posy"][:]) == [3, 4] and "DiskRadius" in g
        assert g.attrs["num_gals"] == 2
        assert f["Header/Simulation"].attrs["box_size"] == 10


def test_a_struct_that_does_not_fit_is_refused(tmp_path):
    t = _run(tmp_path)
    (t / "h.h").write_text(HEADER.replace("N_BINS 3", "N_BINS 4"))
    try:
        fb.convert(t / "x.par", t / "h.h", "Test")
    except ValueError as exc:
        assert "No output struct" in str(exc)
    else:
        raise AssertionError("should refuse")


def test_tested_parameter_files_ship_with_paths_to_fill():
    from visage.wizard.family import FAMILY, PARS

    for spec in FAMILY.values():
        text = (PARS / spec["par"]).read_text()
        assert (
            "@OUTPUT@" in text and "@TREES@" in text and "/Users" not in text
        )


def test_derived_fields_close_on_darksage_arrays():
    dtype = np.dtype(
        [
            (n, "f4", (2,))
            for n in (
                "DiscGas",
                "ClassicalBulgeMass",
                "SecularBulgeMass",
                "ClassicalMetalsBulgeMass",
                "SecularMetalsBulgeMass",
                "DiscSFR",
                "DiscH2",
                "DiscHI",
            )
        ]
        + [
            (n, "f4")
            for n in (
                "SfrMerge",
                "SfrInstab",
                "LastMajorMerger",
                "LastMinorMerger",
            )
        ]
    )
    g = np.zeros(1, dtype)
    g["ClassicalBulgeMass"], g["SecularBulgeMass"] = (1, 2), (3, 4)
    assert fb._derived(g)["BulgeMass"][0] == 10
