"""Finding a run's model: its .par needn't share its output folder's name."""

from __future__ import annotations

from visage.utils.discover import find_models


def _run(tmp_path, folder, par=None, output=None):
    out = tmp_path / "output" / folder
    out.mkdir(parents=True)
    (out / "model_0.hdf5").touch()
    inp = tmp_path / "input"
    inp.mkdir(exist_ok=True)
    if par:
        (inp / par).write_text(
            f"%OutputDir  /elsewhere/\nOutputDir   output/{output}/  % here\n"
        )
    return tmp_path / "output", inp


def test_a_par_is_found_by_its_output_dir(tmp_path):
    out, inp = _run(
        tmp_path, "millennium_DarknDusty", "dd.par", "millennium_DarknDusty"
    )
    (m,) = find_models(out, par_dir=inp)
    assert m["name"] == "millennium_DarknDusty"
    assert m["par"].name == "dd.par"


def test_the_same_name_comes_first(tmp_path):
    out, inp = _run(tmp_path, "a", "a.par", "b")
    (inp / "other.par").write_text("OutputDir output/a/\n")
    assert find_models(out, par_dir=inp)[0]["par"].name == "a.par"


def test_a_run_without_a_par_is_skipped(tmp_path):
    out, inp = _run(tmp_path, "a", "b.par", "b")
    assert find_models(out, par_dir=inp) == []
