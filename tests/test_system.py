"""Platform / hardware detection (visage.system)."""

from __future__ import annotations

from pathlib import Path

import pytest

from visage import system
from visage.parallel import loader


# ── Windows <-> WSL paths ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "win, wsl",
    [
        (r"C:\Users\me\SAGE26", "/mnt/c/Users/me/SAGE26"),
        (r"D:/data/model_0.hdf5", "/mnt/d/data/model_0.hdf5"),
        (r"C:\Users\John Smith\SAGE26", "/mnt/c/Users/John Smith/SAGE26"),
        ("C:\\", "/mnt/c"),
        ("C:", "/mnt/c"),
        (r"\\wsl.localhost\Ubuntu\home\me\x", "/home/me/x"),
        (r"\\wsl$\Ubuntu-24.04\home\me", "/home/me"),
        (r"input\millennium.par", "input/millennium.par"),
        ("/already/linux", "/already/linux"),
    ],
)
def test_to_wsl_path(win, wsl):
    assert system.to_wsl_path(win) == wsl


@pytest.mark.parametrize(
    "wsl, distro, win",
    [
        ("/mnt/c/Users/me/SAGE26", None, r"C:\Users\me\SAGE26"),
        ("/mnt/d", None, "D:\\"),
        ("/home/me/x.h5", "Ubuntu", r"\\wsl.localhost\Ubuntu\home\me\x.h5"),
        ("/home/me/x.h5", None, "/home/me/x.h5"),
        ("./millennium_pso", "Ubuntu", "./millennium_pso"),
    ],
)
def test_from_wsl_path(wsl, distro, win):
    assert system.from_wsl_path(wsl, distro) == win


def test_wsl_path_round_trip():
    p = r"C:\Users\me\sage_outputs\lightcone\lightcone.h5"
    assert system.from_wsl_path(system.to_wsl_path(p)) == p


def test_native_path_translates_only_on_windows():
    assert str(system.native_path("/mnt/c/x/y", windows=True)) == "C:\\x\\y"
    assert system.native_path("/mnt/c/x/y", windows=False) == Path(
        "/mnt/c/x/y"
    )


@pytest.mark.skipif(not system.IS_WINDOWS, reason="Windows paths")
def test_par_reader_reads_wsl_paths_on_windows(tmp_path):
    """A .par written for SAGE running in WSL opens natively on Windows."""
    from visage.io.par_reader import parse_par

    par = tmp_path / "input" / "m.par"
    par.parent.mkdir()
    par.write_text(
        "OutputDir   /mnt/c/sage/output/m\n"
        "SimulationDir   /mnt/d/trees\n"
        "FileWithSnapList  trees/m.a_list\n"
    )
    cfg = parse_par(par)
    assert cfg.output_dir == Path("C:/sage/output/m")
    assert cfg.simulation_dir == Path("D:/trees")
    assert cfg.snap_list_path == tmp_path / "trees" / "m.a_list"


# ── memory / CPUs ─────────────────────────────────────────────────────────


def test_memory_and_cpus_detected():
    mem = system.total_memory_bytes()
    assert mem is not None and mem > 256 * 1024**2
    assert system.cpu_count() >= 1
    assert 1 <= system.default_workers() <= system.cpu_count()


def test_default_cache_is_half_of_detected_memory(monkeypatch):
    monkeypatch.delenv("VISAGE_CACHE_GB", raising=False)
    monkeypatch.setattr(system, "total_memory_bytes", lambda: 32 * 1024**3)
    assert loader.default_cache_bytes() == 16 * 1024**3


def test_default_cache_env_override(monkeypatch):
    monkeypatch.setenv("VISAGE_CACHE_GB", "3")
    assert loader.default_cache_bytes() == 3 * 1024**3


def test_default_cache_floor_when_memory_unknown(monkeypatch):
    monkeypatch.delenv("VISAGE_CACHE_GB", raising=False)
    monkeypatch.setattr(system, "total_memory_bytes", lambda: None)
    assert loader.default_cache_bytes() == 4 * 1024**3


def test_system_summary_mentions_cpus_and_ram():
    line = system.system_summary(3, 2 * 1024**3)
    assert "CPUs (3 workers)" in line
    assert "cache 2.0 GB" in line


# ── rendering / GPU ───────────────────────────────────────────────────────

_CAPS = """
OpenGL vendor string:  NVIDIA Corporation
OpenGL renderer string:  NVIDIA GeForce RTX 4060 Laptop GPU/PCIe/SSE2
OpenGL version string:  4.6.0 NVIDIA 560.94
OpenGL extensions:
"""


def test_parse_capabilities():
    info = system.parse_capabilities(_CAPS)
    assert info.vendor == "NVIDIA Corporation"
    assert info.renderer.startswith("NVIDIA GeForce RTX 4060")
    assert not info.software
    assert "OpenGL 4.6.0" in info.describe()


@pytest.mark.parametrize(
    "renderer",
    [
        "llvmpipe (LLVM 17.0.6, 256 bits)",
        "GDI Generic",
        "Microsoft Basic Render Driver",
    ],
)
def test_software_renderers_flagged(renderer):
    info = system.parse_capabilities(f"OpenGL renderer string: {renderer}")
    assert info.software


def test_parse_capabilities_without_context():
    assert system.parse_capabilities("") is None


class _FakeRenWin:
    def __init__(self):
        self.observers = {}

    def AddObserver(self, event, cb):
        self.observers[len(self.observers) + 1] = cb
        return len(self.observers)

    def RemoveObserver(self, tag):
        self.observers.pop(tag)

    def ReportCapabilities(self):
        return _CAPS

    def render(self):
        for cb in list(self.observers.values()):
            cb(self, "EndEvent")


def test_report_renderer_once_fires_once():
    win = _FakeRenWin()
    seen = []
    system.report_renderer_once(win, seen.append)
    win.render()
    win.render()
    assert len(seen) == 1
    assert seen[0].renderer.startswith("NVIDIA")


def test_report_renderer_on_real_vtk_window():
    pv = pytest.importorskip("pyvista")
    pl = pv.Plotter(off_screen=True, window_size=[64, 64])
    seen = []
    system.report_renderer_once(pl.ren_win, seen.append)
    pl.add_mesh(pv.Sphere())
    pl.ren_win.Render()
    pl.close()
    assert len(seen) == 1 and seen[0].renderer


@pytest.mark.parametrize(
    "name, discrete",
    [
        ("NVIDIA GeForce RTX 4060 Laptop GPU", True),
        ("NVIDIA RTX A2000", True),
        ("AMD Radeon RX 7600", True),
        ("AMD Radeon Pro W6600", True),
        ("AMD Radeon(TM) Graphics", False),
        ("AMD Radeon 780M Graphics", False),
        ("AMD Radeon RX Vega 11 Graphics", False),
        ("Intel(R) UHD Graphics 620", False),
        ("Intel(R) Iris(R) Xe Graphics", False),
        ("Intel(R) Arc(TM) Graphics", False),
        ("Intel(R) Arc(TM) A770 Graphics", True),
    ],
)
def test_is_discrete_gpu(name, discrete):
    assert system.is_discrete_gpu(name) is discrete


def test_gpu_preference_system_mode_does_nothing():
    assert system.apply_gpu_preference("system") is None


@pytest.mark.skipif(system.IS_WINDOWS, reason="non-Windows behaviour")
def test_gpu_preference_auto_is_a_noop_off_windows(monkeypatch):
    before = dict(__import__("os").environ)
    assert system.apply_gpu_preference("auto") is None
    assert dict(__import__("os").environ) == before


def test_offscreen_choice(monkeypatch):
    monkeypatch.setattr(system, "IS_WINDOWS", True)
    monkeypatch.setattr(system, "IS_LINUX", False)
    assert system.prefer_offscreen_rendering()

    monkeypatch.setattr(system, "IS_WINDOWS", False)
    monkeypatch.setattr(system, "IS_LINUX", True)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert system.prefer_offscreen_rendering()  # headless HPC node
    monkeypatch.setenv("DISPLAY", ":0")
    assert not system.prefer_offscreen_rendering()

    monkeypatch.setattr(system, "IS_LINUX", False)
    assert not system.prefer_offscreen_rendering()  # macOS
