"""Tests for the SAGEswarm live-plot scanner used by the PSO gallery."""

from __future__ import annotations

import os

from visage.wizard.controller import WizardController


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


def test_scan_plots_picks_up_pngs(tmp_path):
    (tmp_path / "plot_a.png").write_bytes(b"AAAA")
    (tmp_path / "plot_b.png").write_bytes(b"BBBB")
    (tmp_path / "notes.txt").write_text("ignore me")

    c = _ctrl()
    c._scan_plots(tmp_path)

    names = {p["name"] for p in c._st.pso_plots}
    assert names == {"plot_a.png", "plot_b.png"}
    assert all(
        p["data_url"].startswith("data:image/png;base64,")
        for p in c._st.pso_plots
    )


def test_scan_plots_reencodes_on_mtime_change(tmp_path):
    f = tmp_path / "plot_a.png"
    f.write_bytes(b"AAAA")

    c = _ctrl()
    c._scan_plots(tmp_path)
    first = c._st.pso_plots[0]["data_url"]

    # Rewrite with new content and a newer mtime -> must re-encode.
    f.write_bytes(b"CCCCDDDD")
    st = f.stat()
    os.utime(f, (st.st_atime, st.st_mtime + 10))
    c._scan_plots(tmp_path)

    assert len(c._st.pso_plots) == 1
    assert c._st.pso_plots[0]["data_url"] != first


def test_scan_plots_no_dir_is_noop(tmp_path):
    c = _ctrl()
    c._scan_plots(None)
    assert c._st.pso_plots == []


def test_scan_plots_recurses_into_output_subdir(tmp_path):
    out = tmp_path / "millennium_pso"
    out.mkdir()
    (out / "smf.png").write_bytes(b"X")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "obs.png").write_bytes(b"Y")  # skipped dir

    c = _ctrl()
    c._scan_plots(tmp_path)
    names = {p["name"] for p in c._st.pso_plots}
    assert names == {"millennium_pso/smf.png"}  # obs data dir excluded


def test_sw_output_dir_parsed_from_script(tmp_path):
    c = _ctrl()
    c._sw_dir = tmp_path
    c._st.wiz_sw_script_text = 'OUTPUT_PATH="./millennium_pso"\n'
    assert c._sw_output_dir() == tmp_path / "millennium_pso"

    c._st.wiz_sw_script_text = "python3 main.py -o /abs/out -x SMF_z0\n"
    assert c._sw_output_dir() == __import__("pathlib").Path("/abs/out")

    c._st.wiz_sw_script_text = "no output here\n"
    assert c._sw_output_dir() == tmp_path  # falls back to the SAGEswarm dir
