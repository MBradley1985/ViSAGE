"""Tests for the LightSAGE (sage-lightcone) wizard flow (discovery, build
detection, run-script seeding). The flow clones/builds/runs a third-party
package, so we only ever exercise the pure helpers here — no network or
subprocess calls."""

from __future__ import annotations

import asyncio
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


def _make_checkout(root: Path, name: str = "LightSAGE") -> Path:
    """A minimal directory that looks like a LightSAGE (sage-lightcone) checkout."""
    lc = root / name
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
    lc = _make_checkout(tmp_path)  # default name: LightSAGE
    monkeypatch.chdir(tmp_path)
    c = _ctrl()
    # Discovery searches cwd/parent/home; cwd is tmp_path so it finds lc.
    assert c._find_sagelightcone() == lc


def test_find_sagelightcone_back_compat_alias(tmp_path, monkeypatch):
    # A checkout under the upstream repo's own name (pre-rebrand / manual
    # clone) is still discovered.
    lc = _make_checkout(tmp_path, name="sage-lightcone")
    monkeypatch.chdir(tmp_path)
    c = _ctrl()
    assert c._find_sagelightcone() == lc


def test_find_sagelightcone_requires_wrapper_script(tmp_path, monkeypatch):
    # A directory named LightSAGE but without the wrapper script is not it.
    (tmp_path / "LightSAGE").mkdir()
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
    assert "LightSAGE" not in str(p)


def test_lc_config_resyncs_stale_lightcone_dir(tmp_path, monkeypatch):
    # A saved run_lightcone.sh can point at a checkout that no longer exists
    # (moved, deleted, or cloned under an older folder-naming convention).
    # LIGHTCONE_DIR is an environment fact with exactly one correct answer
    # (unlike the ra/dec/z ranges, which are genuine user preferences), so
    # loading a stale script must still resync it to whatever this session
    # actually found and verified.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    lc = _make_checkout(tmp_path, name="LightSAGE")
    (lc / "bin").mkdir()
    (lc / "bin" / "sage2kdtree").write_text("")
    (lc / "bin" / "cli_lightcone").write_text("")

    stale_dir = tmp_path / "sage-lightcone"  # old alias; doesn't exist anymore
    script_path = tmp_path / ".visage" / _LC_RUN_SCRIPT
    script_path.parent.mkdir(parents=True)
    script_path.write_text(
        _LC_RUN_SCRIPT_TEMPLATE.format(
            lightcone_dir=str(stale_dir),
            sage_output_dir="/x/out",
            param_file="/x/m.par",
            alist_file="/x/a_list",
            outdir="/x/sage_outputs/lightcone",
            python_exe="/usr/bin/python3",
        )
    )

    c = _ctrl()
    c._lc_dir = lc
    asyncio.run(c._step_lc_config())

    text = c._st.wiz_lc_script_text
    assert f'LIGHTCONE_DIR="{lc}"' in text
    assert str(stale_dir) not in text


def test_lc_scan_offers_load_existing(tmp_path, monkeypatch):
    # The LightSAGE scan step always offers "Load Existing Lightcone", and it
    # discovers cli_lightcone .h5 files in the standard output folder so they
    # can be opened without building/running anything.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # no legacy dir
    monkeypatch.chdir(tmp_path)
    lcdir = tmp_path / "sage_outputs" / "lightcone"
    lcdir.mkdir(parents=True)
    import numpy as _np
    import h5py as _h5

    cone = lcdir / "lightcone.h5"
    with _h5.File(cone, "w") as f:
        f["Posx"] = _np.zeros(3)
        f["Posy"] = _np.zeros(3)
        f["Posz"] = _np.zeros(3)

    c = _ctrl()
    found = c._discover_lightcones()
    assert cone.resolve() in found

    asyncio.run(c._step_lc_scan())
    assert "lc_load" in [ch["value"] for ch in c._st.wiz_choices]

    asyncio.run(c._step_lc_load())
    vals = [ch["value"] for ch in c._st.wiz_choices]
    assert any(v == f"lc_open:{cone.resolve()}" for v in vals)


_OLD_FORMAT_LC_SCRIPT = """\
#!/bin/bash
set -e
LIGHTCONE_DIR="/old/LightSAGE"
SAGE_OUTPUT_DIR="/x/sage/output/millennium"
PARAM_FILE="/x/sage/input/millennium.par"
ALIST_FILE="/x/sage/input/millennium/trees/millennium.a_list"
KDTREE_OUT="./millennium-kdtree.h5"
RAMIN=0
RAMAX=10
DECMIN=0
DECMAX=5
ZMIN=0
ZMAX=0.1
OUTDIR="./lightcone_output"
OUTFILE="lightcone.h5"
SED_ENABLED=1
SED_BANDS="sdss_u sdss_g sdss_r sdss_i sdss_z"
SED_FRAME="both"
"""


def test_lc_config_migrates_old_format_script(tmp_path, monkeypatch):
    # A script saved before the per-band checkbox refactor has a single
    # SED_BANDS text field and no BAND_*_ENABLED keys at all -- loading it
    # must upgrade the structure (so the new checkboxes actually appear in
    # the parameter form) while carrying forward every value the user could
    # have customized, mapping the old band list onto the new checkboxes.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    lc = _make_checkout(tmp_path, name="LightSAGE")
    (lc / "bin").mkdir()
    (lc / "bin" / "sage2kdtree").write_text("")
    (lc / "bin" / "cli_lightcone").write_text("")

    script_path = tmp_path / ".visage" / _LC_RUN_SCRIPT
    script_path.parent.mkdir(parents=True)
    script_path.write_text(_OLD_FORMAT_LC_SCRIPT)

    c = _ctrl()
    c._lc_dir = lc
    asyncio.run(c._step_lc_config())

    text = c._st.wiz_lc_script_text
    # Structure upgraded: checkboxes present, old text field gone.
    assert "BAND_GALEX_FUV_ENABLED" in text
    assert "SED_BANDS" not in text
    # User's chosen values carried forward.
    assert 'SAGE_OUTPUT_DIR="/x/sage/output/millennium"' in text
    assert "DECMAX=5" in text and "ZMAX=0.1" in text
    assert "SED_ENABLED=1" in text
    assert 'SED_FRAME="both"' in text
    # Old SED_BANDS mapped onto the matching checkboxes...
    assert "BAND_SDSS_U_ENABLED=1" in text
    assert "BAND_SDSS_G_ENABLED=1" in text
    assert "BAND_SDSS_R_ENABLED=1" in text
    assert "BAND_SDSS_I_ENABLED=1" in text
    assert "BAND_SDSS_Z_ENABLED=1" in text
    # ...and everything NOT in the old list is off, not defaulted on.
    assert "BAND_GALEX_FUV_ENABLED=0" in text
    assert "BAND_WISE_W1_ENABLED=0" in text
    # Old hardcoded OUTDIR default upgraded to the new convention.
    assert 'OUTDIR="./lightcone_output"' not in text
    assert "sage_outputs/lightcone" in text
    # LIGHTCONE_DIR also resynced (migration regenerates from the seed
    # template, which already fills the verified checkout).
    assert f'LIGHTCONE_DIR="{lc}"' in text


def test_lc_migrate_script_is_noop_for_current_format():
    from visage.wizard.controller import _LC_RUN_SCRIPT_TEMPLATE

    c = _ctrl()
    current = _LC_RUN_SCRIPT_TEMPLATE.format(
        lightcone_dir="/x/LightSAGE",
        sage_output_dir="/x/out",
        param_file="/x/m.par",
        alist_file="/x/a_list",
        outdir="/x/sage_outputs/lightcone",
        python_exe="/usr/bin/python3",
    )
    assert c._lc_migrate_script(current) == current


def test_lc_migrate_adds_alist_and_keeps_choices(tmp_path, monkeypatch):
    # A 2.2.0-era script has the band checkboxes but predates --alist. Loading
    # it must upgrade the SED call to pass --alist (so relative header a_list
    # paths resolve) while preserving the user's band + dust choices.
    from visage.wizard.controller import _LC_RUN_SCRIPT_TEMPLATE

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    lc = _make_checkout(tmp_path, name="LightSAGE")
    (lc / "bin").mkdir()
    (lc / "bin" / "sage2kdtree").write_text("")
    (lc / "bin" / "cli_lightcone").write_text("")

    # Simulate a pre-alist script: current template with the --alist line and
    # a couple of choices changed.
    text = _LC_RUN_SCRIPT_TEMPLATE.format(
        lightcone_dir=str(lc),
        sage_output_dir="/x/out",
        param_file="/x/m.par",
        alist_file="/x/trees/a_list",
        outdir="/x/sage_outputs/lightcone",
        python_exe="/usr/bin/python3",
    )
    text = text.replace('\\\n      --alist "$ALIST_FILE"', "")  # drop --alist
    text = text.replace("BAND_WISE_W4_ENABLED=1", "BAND_WISE_W4_ENABLED=0")
    text = text.replace("SED_DUST_ENABLED=0", "SED_DUST_ENABLED=1")
    assert "--alist" not in text  # precondition

    script_path = tmp_path / ".visage" / _LC_RUN_SCRIPT
    script_path.parent.mkdir(parents=True)
    script_path.write_text(text)

    c = _ctrl()
    c._lc_dir = lc
    asyncio.run(c._step_lc_config())
    out = c._st.wiz_lc_script_text

    assert '--alist "$ALIST_FILE"' in out  # upgraded
    assert "BAND_WISE_W4_ENABLED=0" in out  # user's unticked band preserved
    assert "SED_DUST_ENABLED=1" in out  # user's dust choice preserved


def test_lc_seed_script_prefills_sage_paths(tmp_path):
    c = _ctrl()
    c._lc_dir = tmp_path / "LightSAGE"
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
    assert "/path/to/LightSAGE" in text
    assert "../SAGE26/output/millennium" in text


def test_lc_seed_script_outdir_uses_sage_outputs(tmp_path, monkeypatch):
    # Output should land in ViSAGE's standard sage_outputs/ folder (same
    # convention as screenshots/recordings/catalogues), not a scratch dir
    # buried in ~/.visage.
    monkeypatch.chdir(tmp_path)
    c = _ctrl()
    text = c._lc_seed_script()
    expected = str(tmp_path / "sage_outputs" / "lightcone")
    assert f'OUTDIR="{expected}"' in text
    assert 'mkdir -p "$OUTDIR"' in text


def test_run_template_formats_cleanly():
    # No stray braces that would break str.format on the shell body.
    s = _LC_RUN_SCRIPT_TEMPLATE.format(
        lightcone_dir="/x/LightSAGE",
        sage_output_dir="/x/out",
        param_file="/x/m.par",
        alist_file="/x/a_list",
        outdir="/x/sage_outputs/lightcone",
        python_exe="/usr/bin/python3",
    )
    assert "sage2kdtree.sh" in s and "lightcone.sh" in s
    assert "$LIGHTCONE_DIR" in s
    assert "/usr/bin/python3" in s and "visage.sed.photometry" in s


def test_run_template_sed_bands_are_individual_checkboxes():
    # Each filter is its own BAND_<NAME>_ENABLED checkbox (not a single
    # space-separated SED_BANDS text field), and the params parser must pick
    # up all of them plus SED_ENABLED/SED_FRAME — but NOT the lowercase
    # internal accumulator vars (those must never become editable params,
    # or a user's edit could desync them from the checkboxes above).
    s = _LC_RUN_SCRIPT_TEMPLATE.format(
        lightcone_dir="/x/LightSAGE",
        sage_output_dir="/x/out",
        param_file="/x/m.par",
        alist_file="/x/a_list",
        outdir="/x/sage_outputs/lightcone",
        python_exe="/usr/bin/python3",
    )
    assert "SED_BANDS" not in s
    for band in (
        "GALEX_FUV",
        "GALEX_NUV",
        "SDSS_U",
        "SDSS_G",
        "SDSS_R",
        "SDSS_I",
        "SDSS_Z",
        "2MASS_J",
        "2MASS_H",
        "2MASS_KS",
        "WISE_W1",
        "WISE_W2",
        "WISE_W3",
        "WISE_W4",
    ):
        assert f"BAND_{band}_ENABLED" in s

    from visage.wizard.controller import _parse_params

    keys = [p["key"] for p in _parse_params(s, "sh")]
    band_keys = [k for k in keys if k.startswith("BAND_")]
    assert len(band_keys) == 14
    assert "SED_ENABLED" in keys and "SED_FRAME" in keys
    assert "sed_bands" not in keys and "bands_csv" not in keys


def test_run_template_has_metallicity_and_dust_options():
    # Metallicity + dust are exposed as checkboxes (_ENABLED convention) plus
    # a dust2 numeric field, and forwarded to visage.sed.photometry as flags.
    s = _LC_RUN_SCRIPT_TEMPLATE.format(
        lightcone_dir="/x/LightSAGE",
        sage_output_dir="/x/out",
        param_file="/x/m.par",
        alist_file="/x/a_list",
        outdir="/x/sage_outputs/lightcone",
        python_exe="/usr/bin/python3",
    )
    from visage.wizard.controller import _parse_params

    keys = [p["key"] for p in _parse_params(s, "sh")]
    assert "SED_METALLICITY_ENABLED" in keys  # checkbox
    assert "SED_DUST_ENABLED" in keys  # checkbox
    assert "SED_DUST2" in keys  # numeric field
    assert "SED_DUST_EMISSION_ENABLED" in keys  # checkbox
    # forwarded to the CLI
    assert "--no-metallicity" in s and "--dust" in s and "--dust2" in s
    assert "--dust-emission" in s
    # dust emission only forwarded together with dust attenuation
    assert (
        '[ "$SED_DUST_ENABLED" = "1" ] && [ "$SED_DUST_EMISSION_ENABLED" = "1" ]'
        in s
    )

    # compute_photometry accepts the matching kwargs (imports without fsps)
    import inspect
    from visage.sed.photometry import compute_photometry

    params = inspect.signature(compute_photometry).parameters
    assert {
        "use_metallicity",
        "dust",
        "dust2",
        "dust_emission",
    } <= set(params)


def test_run_template_forwards_alist_to_sed():
    # The SED stage must be handed the absolute ALIST_FILE explicitly — the
    # path in the lightcone header is relative to the original SAGE run dir
    # (e.g. microUchuu's) and won't resolve from where the SED step runs.
    s = _LC_RUN_SCRIPT_TEMPLATE.format(
        lightcone_dir="/x/LightSAGE",
        sage_output_dir="/x/out",
        param_file="/x/m.par",
        alist_file="/x/trees/a_list",
        outdir="/x/sage_outputs/lightcone",
        python_exe="/usr/bin/python3",
    )
    assert '--alist "$ALIST_FILE"' in s


def test_resolve_alist(tmp_path):
    from visage.sed.photometry import _resolve_alist

    lc = tmp_path / "sage_outputs" / "lightcone" / "lc.h5"
    lc.parent.mkdir(parents=True)
    al = tmp_path / "trees" / "scale.txt"
    al.parent.mkdir(parents=True)
    al.write_text("1.0\n")

    # explicit override wins even when the header value is bogus
    assert _resolve_alist("bogus/rel.txt", str(al), lc) == al
    # relative header path resolves against an ancestor of the lightcone dir
    got = _resolve_alist("trees/scale.txt", None, lc)
    assert got is not None and got.samefile(al)
    # genuinely missing -> None (caller raises a helpful error)
    assert _resolve_alist("nope/missing.txt", None, lc) is None


def test_pretty_param_label_shortens_band_checkboxes():
    from visage.wizard.controller import WizardController

    assert (
        WizardController._pretty_param_label("BAND_SDSS_G_ENABLED") == "sdss_g"
    )
    assert (
        WizardController._pretty_param_label("BAND_2MASS_KS_ENABLED")
        == "2mass_ks"
    )
    # Non-BAND checkboxes (and everything else) are left alone.
    assert WizardController._pretty_param_label("SED_ENABLED") == "SED_ENABLED"


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


def test_catalogue_export_flat_lightcone_includes_sed(tmp_path):
    # Exporting a lightcone must read the FLAT file (no Snap_N group) and
    # carry its synthetic-photometry columns through.
    from visage.utils.catalogue import write_catalogue

    p = tmp_path / "lightcone.h5"
    _make_lightcone(p, n=60)
    with h5py.File(p, "a") as f:
        f["mag_rest_sdss_g"] = np.linspace(-22, -16, 60).astype(np.float32)
        f["mag_obs_sdss_r"] = np.linspace(18, 24, 60).astype(np.float32)

    out = tmp_path / "cat.csv"
    write_catalogue(
        hdf5_path=p,
        snap_num=0,
        snap_label="lightcone",
        sage_indices=np.arange(30, dtype=np.int64),
        out_path=out,
        fmt="csv",
        scope_label="Whole Lightcone",
        flat=True,
    )
    lines = [
        ln for ln in out.read_text().splitlines() if not ln.startswith("#")
    ]
    header = lines[0].split(",")
    assert "Posx" in header and "StellarMass" in header
    assert "mag_rest_sdss_g" in header and "mag_obs_sdss_r" in header
    assert len(lines) - 1 == 30  # 30 data rows


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
