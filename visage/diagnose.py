"""``visage --diagnose``: a performance check to run on a machine where the
view is slow, writing everything to one log file.

It needs no browser.  It reports the machine and the Python stack, which
GPU OpenGL actually renders on (off-screen and on-screen windows), and
times the steps every frame of the live view goes through: drawing a
galaxy-sized point cloud, reading the image back from the GPU, and
encoding it as JPEG -- at a typical and a large window size.  It also
times the CPU, starting a worker process, an HD galaxy, and (with --par)
loading and drawing your own model.  Each step is guarded: a failure is
logged and the rest still runs.
"""

from __future__ import annotations

import io
import os
import platform
import sys
import time
import traceback
from pathlib import Path

LOG_NAME = "visage_diagnostics.txt"


class _Log:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines: list[str] = []

    def __call__(self, text: str = "") -> None:
        print(text, flush=True)
        self.lines.append(text)
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def _step(log, title, fn) -> None:
    log(f"\n== {title}")
    t = time.perf_counter()
    try:
        fn()
        log(f"   ({time.perf_counter() - t:.1f} s)")
    except Exception as exc:  # keep going: the rest may still tell us a lot
        log(f"   FAILED: {type(exc).__name__}: {exc}")
        for line in traceback.format_exc().splitlines()[-6:]:
            log(f"   | {line}")


def _versions(log) -> None:
    from visage import system
    from visage._version import __version__

    log(f"ViSAGE   : {__version__}")
    log(f"OS       : {system.os_label()} ({platform.platform()})")
    log(f"WSL      : {system.is_wsl()}")
    log(f"Python   : {sys.version.split()[0]} at {sys.executable}")
    log(f"CPU      : {platform.processor() or '?'} · {os.cpu_count()} threads")
    mem = system.total_memory_bytes()
    log(f"RAM      : {mem / 1024**3:.1f} GB" if mem else "RAM      : ?")
    for mod in (
        "vtk",
        "pyvista",
        "numpy",
        "trame",
        "trame_vtk",
        "PIL",
        "h5py",
    ):
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", None) or getattr(
                m, "VTK_VERSION", "?"
            )
            log(f"  {mod:10s} {ver}")
        except Exception as exc:
            log(f"  {mod:10s} not importable: {exc}")
    env = {k: v for k, v in os.environ.items() if k.startswith("VISAGE")}
    log(f"VISAGE_* : {env or 'none'}")
    log(
        f"Off-screen rendering preferred: {system.prefer_offscreen_rendering()}"
    )
    if system.IS_WINDOWS:
        try:
            log(f"Display adapters: {system.windows_display_adapters()}")
        except Exception as exc:
            log(f"Display adapters: ? ({exc})")
    note = system.apply_gpu_preference("auto")
    log(f"GPU preference: {note or 'left as is'}")


def _gpu(log, off_screen: bool) -> None:
    import pyvista as pv

    from visage import system

    pl = pv.Plotter(off_screen=off_screen, window_size=[640, 360])
    pl.add_mesh(pv.Sphere())
    pl.ren_win.Render()
    info = system.parse_capabilities(pl.ren_win.ReportCapabilities())
    if info is None:
        log("   renderer: could not be read")
    else:
        log(f"   vendor  : {info.vendor}")
        log(f"   renderer: {info.renderer}")
        log(f"   version : {info.version}")
        log(f"   software (CPU) rendering: {info.software}")
        reason = system.hd_unavailable_reason(info)
        log(
            f"   HD mode : {'available' if not reason else 'off -- ' + reason}"
        )
    pl.close()


def _cloud(pv, n, rng, scale_mpc=62.5):
    import numpy as np

    pts = rng.uniform(0, scale_mpc, (n, 3)).astype(np.float32)
    cloud = pv.PolyData(pts)
    cloud["rgb"] = rng.uniform(0.3, 1.0, (n, 3)).astype(np.float32)
    cloud["radius"] = rng.uniform(0.02, 0.3, n).astype(np.float32)
    return cloud


def _bench_view(log, off_screen: bool, size, n_gal=150_000, n_halo=60_000):
    """Draw a galaxy + halo point cloud like the live view, then time the
    three steps of a frame: render, read back, JPEG encode."""
    import numpy as np
    import pyvista as pv
    from PIL import Image
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

    rng = np.random.default_rng(0)
    pl = pv.Plotter(off_screen=off_screen, window_size=list(size))
    pl.set_background("black")
    for n, op in ((n_halo, 0.05), (n_gal, 1.0)):
        a = pl.add_mesh(
            _cloud(pv, n, rng),
            scalars="rgb",
            rgb=True,
            style="points_gaussian",
            emissive=True,
            opacity=op,
            show_scalar_bar=False,
            render=False,
        )
        a.mapper.SetScaleArray("radius")
    pl.camera_position = [(31, 31, 160), (31, 31, 31), (0, 1, 0)]
    win = pl.ren_win
    win.Render()  # first frame: setup, shader compile
    w2i = vtkWindowToImageFilter()
    w2i.SetInput(win)
    w2i.ReadFrontBufferOff()
    w2i.ShouldRerenderOff()
    w2i.SetInputBufferTypeToRGB()
    render, read, enc, kb = [], [], [], []
    for k in range(20):
        pl.camera.azimuth = 2.0 * k
        t0 = time.perf_counter()
        win.Render()
        try:
            win.WaitForCompletion()
        except AttributeError:
            pass
        t1 = time.perf_counter()
        w2i.Modified()
        w2i.Update()
        img = w2i.GetOutput()
        w, h, _ = img.GetDimensions()
        px = memoryview(img.GetPointData().GetScalars())
        t2 = time.perf_counter()
        frame = Image.frombuffer("RGB", (w, h), px, "raw", "RGB", 0, -1)
        buf = io.BytesIO()
        frame.save(buf, "JPEG", quality=100)
        t3 = time.perf_counter()
        render.append(t1 - t0)
        read.append(t2 - t1)
        enc.append(t3 - t2)
        kb.append(len(buf.getvalue()) / 1024)
    pl.close()

    def ms(v):
        v = sorted(v)
        return f"{1000 * v[len(v) // 2]:.1f} ms (worst {1000 * v[-1]:.1f})"

    total = sorted(np.add(np.add(render, read), enc))[len(render) // 2]
    log(f"   {size[0]}x{size[1]}, {n_gal + n_halo:,} points")
    log(f"   render  : {ms(render)}")
    log(f"   readback: {ms(read)}")
    log(f"   encode  : {ms(enc)}  ·  {np.median(kb):.0f} KB per frame")
    log(f"   => {1000 * total:.1f} ms per frame, up to {1 / total:.0f} fps")


def _cpu(log) -> None:
    import numpy as np

    a = np.random.default_rng(0).random((800, 800))
    t = time.perf_counter()
    with np.errstate(all="ignore"):  # (spurious on macOS Accelerate)
        for _ in range(10):
            a @ a
    log(
        f"   numpy 800x800 matmul x10: {1000 * (time.perf_counter() - t):.0f} ms"
    )


def _pool(log) -> None:
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor

    from visage.hd.group import _warm_worker

    t = time.perf_counter()
    with ProcessPoolExecutor(1, mp_context=mp.get_context("spawn")) as ex:
        ex.submit(_warm_worker).result()
    log(
        f"   start a worker + import the HD code: "
        f"{time.perf_counter() - t:.1f} s"
    )


def _hd(log) -> None:
    import pyvista as pv

    from visage.hd.layer import HDGalaxyLayer, _warm_galaxy

    gal = _warm_galaxy()
    t = time.perf_counter()
    prep = HDGalaxyLayer.prepare(gal, "full")
    log(f"   build (CPU, full quality): {time.perf_counter() - t:.1f} s")
    pl = pv.Plotter(off_screen=True, window_size=[1600, 900])
    pl.set_background("black")
    lay = HDGalaxyLayer(pl)
    t = time.perf_counter()
    lay.show(gal, (0, 0, 0), None, 0.73, prep=prep)
    pl.camera.focal_point = (0, 0, 0)
    pl.camera.position = (0, -0.04, 0.03)
    pl.renderer.ResetCameraClippingRange()
    pl.ren_win.Render()
    log(f"   upload + first frame: {time.perf_counter() - t:.2f} s")
    ts = []
    for k in range(10):
        pl.camera.azimuth = 3.0 * k
        t = time.perf_counter()
        pl.ren_win.Render()
        try:
            pl.ren_win.WaitForCompletion()
        except AttributeError:
            pass
        ts.append(time.perf_counter() - t)
    ts.sort()
    log(f"   frame (1600x900): {1000 * ts[len(ts) // 2]:.1f} ms")
    pl.close()


def _model(log, par: str) -> None:
    from visage.scene.scene import Scene

    t = time.perf_counter()
    scene = Scene(par, off_screen=True)
    log(f"   load model + first snapshot: {time.perf_counter() - t:.1f} s")
    m = scene.active_model
    halos, galaxies = m.loader.get(m.current_snap)
    log(f"   {halos.count:,} haloes, {galaxies.count:,} galaxies drawn")
    win = scene.plotter.ren_win
    win.SetSize(1600, 900)
    win.Render()
    ts = []
    for k in range(10):
        scene.plotter.camera.azimuth = 2.0 * k
        t = time.perf_counter()
        win.Render()
        try:
            win.WaitForCompletion()
        except AttributeError:
            pass
        ts.append(time.perf_counter() - t)
    ts.sort()
    log(f"   frame of your model (1600x900): {1000 * ts[len(ts) // 2]:.1f} ms")
    snaps = [s for s in (m.current_snap - 1, m.current_snap - 2) if s >= 0]
    if snaps:
        t = time.perf_counter()
        m.set_snapshot(snaps[0])
        log(
            f"   change snapshot ({m.current_snap}): "
            f"{time.perf_counter() - t:.1f} s"
        )


def _platform_checks(log) -> None:
    """Things that differ between machines and can slow everything down:
    timer resolution, power plan, the NVIDIA driver and load, the JPEG
    encoder, the VTK window class."""
    import asyncio
    import subprocess

    ts = []
    for _ in range(20):
        t = time.perf_counter()
        time.sleep(0.001)
        ts.append(time.perf_counter() - t)
    log(f"   time.sleep(1 ms) actually takes {1000 * sorted(ts)[10]:.1f} ms")

    async def _a():
        out = []
        for _ in range(20):
            t = time.perf_counter()
            await asyncio.sleep(0.001)
            out.append(time.perf_counter() - t)
        return out

    ts = asyncio.run(_a())
    log(
        f"   asyncio.sleep(1 ms) actually takes {1000 * sorted(ts)[10]:.1f} ms"
    )
    log(f"   event loop: {type(asyncio.new_event_loop()).__name__}")
    try:
        from PIL import features

        log(
            f"   Pillow libjpeg-turbo: {features.check_feature('libjpeg_turbo')}"
        )
    except Exception as exc:
        log(f"   Pillow libjpeg-turbo: ? ({exc})")
    try:
        import pyvista as pv

        pl = pv.Plotter(off_screen=True, window_size=[64, 64])
        log(f"   VTK render window: {pl.ren_win.GetClassName()}")
        pl.close()
    except Exception as exc:
        log(f"   VTK render window: ? ({exc})")
    for cmd in (
        ["powercfg", "/getactivescheme"],
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,pstate,utilization.gpu,"
            "memory.used,memory.total",
            "--format=csv",
        ],
    ):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            text = (r.stdout or r.stderr).strip()
            log(f"   {cmd[0]}:")
            for line in text.splitlines()[:6]:
                log(f"     {line}")
        except FileNotFoundError:
            log(f"   {cmd[0]}: not on this machine")
        except Exception as exc:
            log(f"   {cmd[0]}: {exc}")


def _live(log, par: str) -> None:
    """The real app, served as when you run it, exercised as you use it.

    While each action runs, how late the server's event loop handles
    things ("lag") is measured, and asyncio's debug mode names every
    callback that held the loop for more than 0.1 s -- the work that makes
    clicks and the view wait."""
    import asyncio
    import logging

    import numpy as np

    from visage.app import create_app
    from visage.utils import frame_delivery

    t = time.perf_counter()
    server, scene = create_app(par_path=par)
    log(f"   build the app: {time.perf_counter() - t:.1f} s")
    state, ctrl = server.state, server.controller

    slow: list[tuple[float, str, str]] = []
    phase = ["startup"]

    class _Slow(logging.Handler):
        def emit(self, record):
            msg = record.getMessage()
            if "took" in msg:
                try:
                    secs = float(msg.rsplit("took", 1)[1].split()[0])
                except ValueError:
                    secs = 0.0
                slow.append((secs, phase[0], msg[:300]))

    alog = logging.getLogger("asyncio")
    alog.addHandler(_Slow())
    alog.setLevel(logging.WARNING)

    lag: list[float] = []

    async def _watch():
        while True:
            t0 = time.perf_counter()
            await asyncio.sleep(0.05)
            lag.append(max(0.0, time.perf_counter() - t0 - 0.05))

    async def _measure(name, seconds, action=None):
        phase[0] = name
        lag.clear()
        took = 0.0
        if action is not None:
            t0 = time.perf_counter()
            res = action()
            if asyncio.iscoroutine(res):
                await res
            state.flush()
            took = time.perf_counter() - t0
        await asyncio.sleep(seconds)
        worst = max(lag) if lag else 0.0
        mean = float(np.mean(lag)) if lag else 0.0
        log(
            f"   {name:34s} action {1000 * took:7.0f} ms · lag mean "
            f"{1000 * mean:5.0f} ms, worst {1000 * worst:6.0f} ms"
        )

    grabbers: dict = {}

    async def _drag(seconds=4.0):
        """As a mouse drag: the camera turns and a frame is rendered and
        JPEG-encoded at up to 60 fps."""
        win = scene.plotter.ren_win
        win.SetSize(1600, 900)
        n, t0 = 0, time.perf_counter()
        while time.perf_counter() - t0 < seconds:
            scene.plotter.camera.azimuth = 1.0
            frame_delivery.render_jpeg(win, 100, grabbers)
            n += 1
            await asyncio.sleep(1 / 60)
        log(f"   ({n / seconds:.0f} frames/s rendered + encoded)")

    async def _hd():
        ctrl.toggle_hd()
        t0 = time.perf_counter()
        while state.hd_building and time.perf_counter() - t0 < 120:
            await asyncio.sleep(0.1)
        log(
            f"   (HD build finished in {time.perf_counter() - t0:.1f} s, "
            f"active: {bool(state.hd_active)})"
        )

    async def main():
        loop = asyncio.get_running_loop()
        loop.set_debug(True)
        loop.slow_callback_duration = 0.1
        server.start(
            port=0,
            open_browser=False,
            exec_mode="task",
            timeout=0,
            show_connection_info=False,
            disable_logging=True,
        )
        watcher = loop.create_task(_watch())
        await asyncio.sleep(1.0)
        m = scene.active_model
        _, gal = m.loader.get(m.current_snap)
        top = int(np.argmax(gal.stellar_mass))
        snaps = [s for s in (m.current_snap - 1, m.current_snap - 2) if s >= 0]

        def _set(**kw):
            def f():
                for k, v in kw.items():
                    state[k] = v

            return f

        await _measure("idle (startup work, preloading)", 8.0)
        await _measure("drag the view", 0.5, _drag)
        await _measure("select a galaxy", 1.0, _set(nav_gal_idx=top))
        await _measure("colour by sSFR", 1.0, _set(galaxy_color_mode="ssfr"))
        for sn in snaps:
            await _measure(f"change snapshot -> {sn}", 2.0, _set(snap_num=sn))
        await _measure(
            "back to the first snapshot", 2.0, _set(snap_num=m.snap_count - 1)
        )
        await _measure("select it again", 1.0, _set(nav_gal_idx=top))
        await _measure("Go", 1.0, ctrl.go_to_galaxy_enter)
        await _measure("Isolate on", 1.0, ctrl.toggle_isolate)
        await _measure("Isolate off", 1.0, ctrl.toggle_isolate)
        if state.has("hd_available") and not state.hd_available:
            log("   (HD unavailable on this renderer: skipped)")
        else:
            await _measure("HD build", 1.0, _hd)
            await _measure("drag the view in HD", 0.5, _drag)
            await _measure("HD off", 1.0, ctrl.toggle_hd)
        watcher.cancel()

    asyncio.run(main())
    if slow:
        log("   Work that held the event loop over 0.1 s (longest first):")
        for secs, ph, msg in sorted(slow, reverse=True)[:15]:
            log(f"     {secs:6.2f} s during '{ph}': {msg}")
    else:
        log("   Nothing held the event loop over 0.1 s.")


_BROWSER_CHECKS = """
Browser checks (please do these too and note the answers):
  1. Open chrome://gpu (Chrome) or edge://gpu (Edge). Under "Graphics
     Feature Status", is "Hardware accelerated" shown for Canvas, Compositing
     and Rasterization, or "Software only"?
  2. Windows Settings > System > Display: what is the resolution and the
     Scale (100% / 125% / 150%...) of the screen the browser is on?
  3. Is the browser on the same PC as ViSAGE (http://localhost:...)?
"""


def run(par: str | None = None, out_dir: str | Path = ".") -> Path:
    """Run every check; return the log file's path."""
    path = Path(out_dir).resolve() / LOG_NAME
    log = _Log(path)
    log(f"ViSAGE diagnostics -- {time.strftime('%Y-%m-%d %H:%M:%S')}")
    _step(log, "Machine and software", lambda: _versions(log))
    _step(log, "GPU, off-screen window", lambda: _gpu(log, True))
    _step(log, "GPU, on-screen window", lambda: _gpu(log, False))
    _step(log, "CPU", lambda: _cpu(log))
    for off in (True, False):
        for size in ((1600, 900), (2560, 1440)):
            _step(
                log,
                f"Live-view frame, {'off' if off else 'on'}-screen "
                f"{size[0]}x{size[1]}",
                lambda off=off, size=size: _bench_view(log, off, size),
            )
    _step(log, "Platform", lambda: _platform_checks(log))
    _step(log, "Worker process start", lambda: _pool(log))
    _step(log, "HD galaxy", lambda: _hd(log))
    if par:
        _step(log, f"Your model ({par})", lambda: _model(log, par))
        _step(
            log, "Live app (the server as you run it)", lambda: _live(log, par)
        )
    for line in _BROWSER_CHECKS.strip("\n").splitlines():
        log(line)
    log(f"\nDone. Log: {path}")
    return path
