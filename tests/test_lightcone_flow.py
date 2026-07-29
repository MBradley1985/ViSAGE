"""Tests for the sage-lightcone wizard flow (discovery, build detection,
run-script seeding). The flow clones/builds/runs a third-party package, so we
only ever exercise the pure helpers here — no network or subprocess calls."""

from __future__ import annotations

from pathlib import Path

from visage.wizard.controller import (
    WizardController,
    _STEPS,
    _STEPS_SAGELIGHTCONE,
    _LC_RUN_SCRIPT,
    _LC_RUN_SCRIPT_TEMPLATE,
)


class _FakeState:
    def __init__(self):
        object.__setattr__(self, "_d", {})

    def __setattr__(self, k, v):
        self._d[k] = v

    def __getattr__(self, k):
        try:
            return self._d[k]
        except KeyError as exc:
            raise AttributeError(k) from exc

    def __setitem__(self, k, v):
        self._d[k] = v

    def __getitem__(self, k):
        return self._d[k]

    def flush(self):
        pass


class _FakeCtrl:
    def set(self, name):
        def deco(fn):
            return fn

        return deco


class _FakeServer:
    def __init__(self):
        self.state = _FakeState()
        self.controller = _FakeCtrl()


def _ctrl():
    return WizardController(_FakeServer(), 0, auto_start=False)


def _make_checkout(root: Path) -> Path:
    """A minimal directory that looks like a sage-lightcone checkout."""
    lc = root / "sage-lightcone"
    (lc / "scripts").mkdir(parents=True)
    (lc / "scripts" / "sage2kdtree.sh").write_text("#!/bin/bash\n")
    (lc / "scripts" / "lightcone.sh").write_text("#!/bin/bash\n")
    (lc / "build_platform_aware.sh").write_text("#!/bin/bash\n")
    return lc


def test_steps_have_same_chip_count():
    # The header renders a fixed number of chips (len(_STEPS)); the lightcone
    # labels must match that count or the UI would over/under-fill.
    assert len(_STEPS_SAGELIGHTCONE) == len(_STEPS) == 6


def test_find_sagelightcone_by_scripts(tmp_path, monkeypatch):
    lc = _make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    c = _ctrl()
    # Discovery searches cwd/parent/home; cwd is tmp_path so it finds lc.
    assert c._find_sagelightcone() == lc


def test_find_sagelightcone_requires_wrapper_script(tmp_path, monkeypatch):
    # A directory named sage-lightcone but without the wrapper script is not it.
    (tmp_path / "sage-lightcone").mkdir()
    monkeypatch.chdir(tmp_path)
    c = _ctrl()
    assert c._find_sagelightcone() is None


def test_lc_built_detects_executables(tmp_path):
    lc = _make_checkout(tmp_path)
    c = _ctrl()

    built, tools = c._lc_built(lc)
    assert built is False and tools == []

    (lc / "bin").mkdir()
    (lc / "bin" / "sage2kdtree").write_text("")
    built, tools = c._lc_built(lc)
    assert built is True and tools == ["sage2kdtree"]

    (lc / "bin" / "cli_lightcone").write_text("")
    built, tools = c._lc_built(lc)
    assert built is True and tools == ["sage2kdtree", "cli_lightcone"]


def test_lc_script_path_is_outside_repo(tmp_path):
    # The editable run script must live under ~/.visage, never in the checkout.
    c = _ctrl()
    p = c._lc_script_path()
    assert p == Path.home() / ".visage" / _LC_RUN_SCRIPT
    assert "sage-lightcone" not in str(p)


def test_lc_seed_script_prefills_sage_paths(tmp_path):
    c = _ctrl()
    c._lc_dir = tmp_path / "sage-lightcone"
    c._sage26_dir = tmp_path / "SAGE26"
    text = c._lc_seed_script()

    assert str(c._lc_dir) in text  # LIGHTCONE_DIR filled in
    assert str(c._sage26_dir / "output" / "millennium") in text
    assert str(c._sage26_dir / "input" / "millennium.par") in text
    # Calls the repo wrappers, never edits the repo.
    assert "scripts/sage2kdtree.sh" in text
    assert "scripts/lightcone.sh" in text


def test_lc_seed_script_falls_back_without_sage26():
    c = _ctrl()
    c._lc_dir = None
    c._sage26_dir = None
    text = c._lc_seed_script()
    assert "/path/to/sage-lightcone" in text
    assert "../SAGE26/output/millennium" in text


def test_run_template_formats_cleanly():
    # No stray braces that would break str.format on the shell body.
    s = _LC_RUN_SCRIPT_TEMPLATE.format(
        lightcone_dir="/x/sage-lightcone",
        sage_output_dir="/x/out",
        param_file="/x/m.par",
        alist_file="/x/a_list",
    )
    assert "sage2kdtree.sh" in s and "lightcone.sh" in s
    assert "$LIGHTCONE_DIR" in s


# ── Lightcone reader / output-format tests ────────────────────────────────

import numpy as np  # noqa: E402
import h5py  # noqa: E402


def _make_lightcone(path, n=200):
    """Write a minimal but conformant flat lightcone HDF5 file."""
    rng = np.random.default_rng(0)
    with h5py.File(path, "w") as f:
        # Observer-frame cone-ish positions
        dist = rng.uniform(20, 400, n)
        f["Posx"] = dist.astype(np.float64)
        f["Posy"] = rng.uniform(0, 40, n)
        f["Posz"] = rng.uniform(0, 40, n)
        f["StellarMass"] = rng.uniform(0.001, 5.0, n)  # 1e10 Msun/h
        f["Mvir"] = rng.uniform(0.01, 50.0, n)
        f["Rvir"] = rng.uniform(0.05, 0.5, n)
        f["Vmax"] = rng.uniform(50, 400, n)
        f["ColdGas"] = rng.uniform(0.0, 1.0, n)
        f["SfrDisk"] = rng.uniform(0, 5, n)
        f["SfrBulge"] = rng.uniform(0, 1, n)
        # half centrals, half satellites
        t = np.zeros(n, np.int64)
        t[n // 2 :] = 1
        f["Type"] = t
        f["GalaxyIndex"] = np.arange(n, dtype=np.int64)
        f["CentralGalaxyIndex"] = np.arange(n, dtype=np.int64)
        f["SnapNum"] = rng.integers(58, 64, n).astype(np.int64)
        f["redshift_cosmological"] = rng.uniform(0.0, 0.2, n)
        hdr = f.create_group("SageOutputHeader")
        sim = hdr.create_group("Simulation")
        sim.attrs["hubble_h"] = 0.73
        lch = f.create_group("LightconeOutputHeader")
        lch.attrs["zmax"] = 0.2


def test_reader_builds_galaxies_and_haloes(tmp_path):
    from visage.io.lightcone_reader import load_lightcone_snapshot

    p = tmp_path / "lightcone.h5"
    _make_lightcone(p, n=200)
    lc = load_lightcone_snapshot(p, min_stellar_mass=0.0, min_halo_mass=0.0)

    assert lc.count == 200
    assert lc.galaxies.positions.shape == (200, 3)
    # StellarMass converted 1e10 Msun/h -> Msun
    assert lc.galaxies.stellar_mass.max() > 1e9
    # Host haloes = the Type==0 centrals (100 of them).
    assert lc.halos.count == 100
    assert lc.hubble_h == 0.73
    assert lc.snapnum.min() >= 58 and lc.snapnum.max() <= 63
    assert 0.0 <= lc.redshift.min() and lc.redshift.max() <= 0.2
    # bounds/extent sane
    assert lc.box_extent > 0
    assert "StellarMass" in lc.present_fields


def test_reader_mass_floor_and_downsample(tmp_path):
    from visage.io.lightcone_reader import load_lightcone_snapshot

    p = tmp_path / "lightcone.h5"
    _make_lightcone(p, n=500)
    lc = load_lightcone_snapshot(p, min_stellar_mass=1e30, min_halo_mass=0.0)
    assert lc.count == 0  # impossible floor drops everything

    lc2 = load_lightcone_snapshot(p, min_stellar_mass=0.0, max_galaxies=50)
    assert lc2.count == 50  # downsampled


def test_reader_rejects_non_lightcone(tmp_path):
    from visage.io.lightcone_reader import load_lightcone_snapshot

    p = tmp_path / "bad.h5"
    with h5py.File(p, "w") as f:
        f["NotPositions"] = np.arange(10)
    try:
        load_lightcone_snapshot(p)
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_param_form_parse_apply_shell():
    from visage.wizard.controller import _parse_params, _apply_params

    sh = (
        'CONFIG="../a b.par"   # config path\n'
        "RAMIN=0;  RAMAX=10    # ra range\n"
        "PARTICLES=25\n"
        'python3 ./main.py -c "$CONFIG" -o "$OUT"\n'
    )
    params = _parse_params(sh, "sh")
    keys = [p["key"] for p in params]
    # every VAR=value parses, incl. two on one line; $refs/flags ignored
    assert keys == ["CONFIG", "RAMIN", "RAMAX", "PARTICLES"]
    assert {p["key"]: p["value"] for p in params}["CONFIG"] == "../a b.par"

    for p in params:
        if p["key"] == "RAMAX":
            p["value"] = "4"
        if p["key"] == "CONFIG":
            p["value"] = "/new path.par"
    out = _apply_params(sh, params, "sh")
    assert "RAMIN=0;  RAMAX=4" in out  # only RAMAX changed, layout kept
    assert 'CONFIG="/new path.par"' in out  # stayed quoted
    assert "# ra range" in out and "# config path" in out  # comments kept
    assert '-c "$CONFIG"' in out  # command line untouched


def test_param_form_parse_apply_par():
    from visage.wizard.controller import _parse_params, _apply_params

    par = (
        "%----- section -----\n"
        "FileNameGalaxies   model\n"
        "%OutputDir  /commented/out\n"
        "Omega           0.25\n"
        "OmegaLambda     0.75\n"
        "OutputFormat    sage_hdf5 % binary or hdf5\n"
        "-> 63 37 32\n"
    )
    params = _parse_params(par, "par")
    keys = [p["key"] for p in params]
    assert keys == ["FileNameGalaxies", "Omega", "OmegaLambda", "OutputFormat"]

    for p in params:
        if p["key"] == "Omega":
            p["value"] = "0.30"
    out = _apply_params(par, params, "par")
    lines = out.splitlines()
    assert any(ln.startswith("Omega ") and "0.30" in ln for ln in lines)
    # OmegaLambda (prefix collision) is untouched
    assert any("OmegaLambda" in ln and "0.75" in ln for ln in lines)
    # comments, commented-out line and the -> directive are preserved
    assert "%OutputDir  /commented/out" in out
    assert "% binary or hdf5" in out
    assert "-> 63 37 32" in out


def test_param_form_pool_roundtrip():
    """The form binds each option to its own wiz_pv_<i> scalar; edits made
    there must fold back into the config text on sync."""
    c = _ctrl()
    text = "CONFIG_PATH=/a.par\nRAMIN=0\nRAMAX=10\nOUTFILE=out.h5\n"
    c._st.wiz_lc_script_text = text
    c._show_params(text, "sh", "lc")
    # pool populated + count set
    assert c._st.wiz_param_count == 4
    assert c._param_keys == ["CONFIG_PATH", "RAMIN", "RAMAX", "OUTFILE"]
    assert c._st["wiz_pl_2"] == "RAMAX" and c._st["wiz_pv_2"] == "10"
    # simulate the user editing the RAMAX + OUTFILE boxes (client → scalar var)
    c._st["wiz_pv_2"] = "4"
    c._st["wiz_pv_3"] = "cone.h5"
    # sync folds the edited scalar values back into the script text
    c._sync_params_to_text()
    out = c._st.wiz_lc_script_text
    assert "RAMAX=4" in out and "OUTFILE=cone.h5" in out
    assert "RAMIN=0" in out  # untouched value preserved


def test_wizard_parses_output_file():
    c = _ctrl()
    c._st.wiz_lc_script_text = (
        'OUTDIR="./lightcone_output"\nOUTFILE="cone.h5"\n'
    )
    out = c._lc_output_file()
    assert out is not None
    assert out.name == "cone.h5"
    assert out.parent.name == "lightcone_output"
    # lives under the ViSAGE-managed run dir, never the repo
    assert ".visage" in str(out)
