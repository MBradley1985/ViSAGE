"""Tests for Launch Mode's setup and run screens (visage/wizard/screens.py):
reading progress from each tool's output, and the setup choices that edit
its config."""

from __future__ import annotations

import asyncio

from visage.wizard.controller import WizardController
from pathlib import Path

from visage.wizard.screens import _fill_frame, _readable


class _State(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def flush(self):
        pass


class _Ctrl:
    def set(self, _name):
        return lambda f: f


class _Server:
    def __init__(self):
        self.state = _State()
        self.controller = _Ctrl()


def _ctrl() -> WizardController:
    return WizardController(_Server(), 8765, auto_start=False)


_SW_SCRIPT = """\
CONFIG_PATH="../SAGE26/input/millennium.par"
BASE_PATH="../SAGE26/sage"
OUTPUT_PATH="./millennium_pso"
PARTICLES=10
ITERATIONS=10
TEST="chi2"
CONSTRAINTS="SMF_z0(8-11)*10"
CSVOUTPUT="./millennium_pso/pso.csv"
SPACEFILE="./space.txt"
"""


def test_readable():
    assert _readable("ThisTask = 0 done processing all forests assigned.")
    assert _readable("[3/35] snap=61 Z node=5")
    assert not _readable("Progress: [**>   ]  3% | ETA: 00:00:12")
    assert not _readable(" ██████   █████ ")
    assert not _readable("   ......  ......   ......  . . .")
    assert not _readable("==========================")


def test_sage26_progress_from_terminal_output():
    c = _ctrl()
    c._st.wiz_par_text = "OutputDir output/x/\n"
    c._run_init("sage26")
    c._st.wiz_view = "run"
    # A terminal ends lines with \r\n, and the bar redraws in place.
    c._run_output(b"reading parameter file:\r\n")
    c._run_output(
        b"\x1b[1;32mProgress: [**>   ]\x1b[0m  42% | ETA: 00:01:05\x1b[K\r\n"
    )
    c._run_publish(force=True)
    assert c._run["stage"] == 1
    assert c._st.wiz_run["pct"] == 42
    assert {"k": "Time left", "v": "1:05"} in c._st.wiz_run["stats"]
    assert c._st.wiz_run["log"] == ["reading parameter file:"]


def test_lightsage_stages():
    c = _ctrl()
    c._st.wiz_lc_script_text = "SED_ENABLED=1\n"
    c._run_init("sagelightcone")
    c._st.wiz_view = "run"
    c._run_live_cone = lambda path: asyncio.sleep(0)  # no file to draw
    c._run_output(b"==> Stage 1/2: sage2kdtree\r\n")
    assert c._run["stage"] == 0
    c._run_output(b"==> Stage 2/2: cli_lightcone\r\n")
    assert c._run["stage"] == 1

    async def _written():
        c._run_output(b"==> Lightcone written to ./out/cone.h5\r\n")

    asyncio.run(_written())
    assert c._run["stage"] == 2
    c._run_output(b"  [7/35] snap=61 Z node=1\r\n")
    assert 55 < c._run["pct"] < 70


def test_sageswarm_iterations_and_best():
    c = _ctrl()
    c._st.wiz_sw_script_text = _SW_SCRIPT
    c._run_init("sageswarm")
    c._st.wiz_view = "run"
    c._run_output("\r  Iter 3  [████░░░]  4/10 particles complete  ".encode())
    assert c._run["iter"] == 3 and c._run["parts"] == "4 / 10"
    # 3 full iterations + 4 particles of 11 rounds of 10
    assert abs(c._run["pct"] - 100 * 34 / 110) < 1e-6
    c._run_output(b"\r\n  -> New swarm best: 1.84 at [0.06, 3.1, 0.27]\r\n")
    assert c._run["best"] == "1.84"


def test_swarm_setup_choices_edit_the_script():
    c = _ctrl()
    c._setup_mode = "sageswarm"
    c._st.wiz_sw_script_text = _SW_SCRIPT
    c._render_setup = lambda: None
    # A suffix (range, weight) survives turning other constraints on/off.
    asyncio.run(c._setup_choose("con:BHBM"))
    vals = c._cfg_values("sageswarm")
    assert vals["CONSTRAINTS"]["value"] == "SMF_z0(8-11)*10,BHBM"
    asyncio.run(c._setup_choose("con:BHBM"))
    assert c._cfg_values("sageswarm")["CONSTRAINTS"]["value"] == (
        "SMF_z0(8-11)*10"
    )
    # The last constraint can't be switched off.
    asyncio.run(c._setup_choose("con:SMF_z0"))
    assert c._cfg_values("sageswarm")["CONSTRAINTS"]["value"] == (
        "SMF_z0(8-11)*10"
    )
    asyncio.run(c._setup_choose("effort:standard"))
    vals = c._cfg_values("sageswarm")
    assert vals["PARTICLES"]["value"] == "20"
    assert vals["ITERATIONS"]["value"] == "30"
    # The run name sets the output folder.
    c._st.wiz_setup_name = "my calib"
    c._apply_setup_name()
    vals = c._cfg_values("sageswarm")
    assert vals["OUTPUT_PATH"]["value"] == "./my_calib"
    assert vals["CSVOUTPUT"]["value"] == "./my_calib/pso.csv"


def test_physics_toggle_and_run_name(tmp_path):
    c = _ctrl()
    c._setup_mode = "sage26"
    par = tmp_path / "millennium.par"
    par.write_text(
        "OutputDir   output/millennium/  % where to write\n"
        "AGNrecipeOn 2  % 0: off; 2: Bondi-Hoyle\n"
        "SupernovaRecipeOn 1\n"
    )
    c._par_path = par
    c._st.wiz_par_text = par.read_text()
    c._render_setup = lambda: None
    asyncio.run(c._setup_choose("tog:SupernovaRecipeOn"))
    assert c._cfg_values("sage26")["SupernovaRecipeOn"]["value"] == "0"
    # AGN off, then back on with the recipe it had.
    asyncio.run(c._setup_choose("tog:AGNrecipeOn"))
    assert c._cfg_values("sage26")["AGNrecipeOn"]["value"] == "0"
    asyncio.run(c._setup_choose("tog:AGNrecipeOn"))
    assert c._cfg_values("sage26")["AGNrecipeOn"]["value"] == "2"
    # A new name makes a new .par whose OutputDir matches it.
    c._st.wiz_setup_name = "test_run"
    c._apply_setup_name()
    assert c._par_path.name == "test_run.par"
    assert c._cfg_values("sage26")["OutputDir"]["value"] == "output/test_run/"


def test_fill_frames_follow_progress():
    static = Path(__file__).resolve().parents[1] / "visage" / "static"
    assert _fill_frame("sage26", 0).startswith(
        "/sage_static/wizard/fill/box_000.webp?v="
    )
    assert _fill_frame("sage26", 47).startswith(
        "/sage_static/wizard/fill/box_045.webp?v="
    )
    # The cone is full once it has been cut (55%), before photometry.
    assert "cone_100.webp" in _fill_frame("sagelightcone", 60)
    for mode in ("sage26", "sagelightcone"):
        for pct in range(0, 101):
            url = _fill_frame(mode, pct).split("?")[0]
            assert (static / url[len("/sage_static/") :]).is_file()


def test_newest_plot_per_constraint():
    from visage.wizard.controller import _latest_per_constraint

    plots = [
        {"name": "plots/SMF_z0_iter1_all.png", "data_url": "a", "mtime": 1},
        {"name": "plots/SMF_z0_iter2_all.png", "data_url": "b", "mtime": 2},
        {"name": "plots/BHBM_all.png", "data_url": "c", "mtime": 1},
    ]
    got = _latest_per_constraint(plots)
    assert [(p["group"], p["data_url"]) for p in got] == [
        ("BHBM", "c"),
        ("SMF_z0", "b"),
    ]


def test_terminal_size_reaches_the_running_command():
    c = _ctrl()
    sizes = []

    class _Proc:
        def resize(self, rows, cols):
            sizes.append((rows, cols))

    c._run_proc = _Proc()
    c._on_term_size(wiz_term_size="142,30")
    assert c._term_size == (30, 142) and sizes == [(30, 142)]
    c._on_term_size(wiz_term_size="junk")  # ignored
    c._on_term_size(wiz_term_size="3,2")  # too small: ignored
    assert c._term_size == (30, 142)


def test_swarm_tiles_bar_and_particles():
    from visage.wizard.screens import _swarm_stats

    run = {"M": 3, "S": 5, "iter": 2, "pdone": 2, "ptot": 5}
    it, parts = _swarm_stats(run, "running")
    # Initial round + 3 iterations; rounds 0-1 done, round 2 at 2/5.
    assert it["segs"] == [1.0, 1.0, 0.4, 0.0]
    assert it["v"] == "2 / 3"
    assert parts["dots"] == [1, 1, 0, 0, 0] and parts["v"] == "2 / 5"
    it, parts = _swarm_stats(run, "done")
    assert set(it["segs"]) == {1.0} and parts["dots"] == [1] * 5


def test_branch_grows_from_left_to_right():
    import base64
    import re

    from visage.wizard.screens import tree_svg

    def fill(pct):
        svg = base64.b64decode(tree_svg(pct, "#fff").split(",")[1]).decode()
        return float(
            re.search(r'clipPath id="f"><rect [^>]*width="([\d.]+)"', svg)[1]
        )

    assert fill(0) == 0 and fill(50) == 150 and fill(100) == 300


def test_clone_goes_over_the_old_copy_or_beside_the_others(tmp_path):
    c = _ctrl()
    c._sage26_dir = tmp_path / "SAGE26"
    c._lc_dir = c._sw_dir = None
    assert c._clone_target("sage26") == tmp_path / "SAGE26"
    assert c._clone_target("sageswarm") == tmp_path / "SAGEswarm"
    assert c._clone_target("sagelightcone") == tmp_path / "LightSAGE"


def test_terminal_output_is_never_skipped():
    import base64

    c = _ctrl()
    c._push_bytes(b"hello ")
    c._push_bytes(b"world")
    assert c._st.wiz_pty_chunk["o"] == 6  # each piece knows its position
    # A browser that missed output asks from where it got to...
    c._on_pty_need(wiz_pty_need="2:1")
    ch = c._st.wiz_pty_chunk
    assert (ch["o"], ch["full"]) == (2, False)
    assert base64.b64decode(ch["d"]) == b"llo world"
    # ...and a terminal just starting (or too far behind) gets all of it.
    c._on_pty_need(wiz_pty_need="-1:2")
    ch = c._st.wiz_pty_chunk
    assert ch["full"] and base64.b64decode(ch["d"]) == b"hello world"
