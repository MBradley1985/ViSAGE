"""Frame delivery to the browser (visage.utils.frame_delivery) and the
wall-clock pacing of camera motion (visage.scene.camera_motion)."""

from __future__ import annotations

import asyncio
import io
import time

import numpy as np
import pytest
from PIL import Image

from visage.scene import camera_motion
from visage.utils import frame_delivery

pv = pytest.importorskip("pyvista")


@pytest.fixture
def plotter():
    pl = pv.Plotter(off_screen=True, window_size=[64, 48])
    # Blue at the bottom, red at the top: catches an upside-down frame.
    pl.set_background("blue", top="red")
    yield pl
    pl.close()


def _decode(jpeg: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB")).astype(int)


def test_render_jpeg_is_upright_and_full_size(plotter):
    jpeg, size = frame_delivery.render_jpeg(plotter.ren_win, 100, {})
    assert size == (64, 48)
    img = _decode(jpeg)
    assert img.shape == (48, 64, 3)
    top, bottom = img[1].mean(axis=0), img[-2].mean(axis=0)
    assert top[0] > 200 and top[2] < 60  # red
    assert bottom[2] > 200 and bottom[0] < 60  # blue


@pytest.fixture
def patched(monkeypatch):
    """install() on trame-vtk's classes, undone after the test."""
    from trame_vtk.modules.vtk.protocols import (
        vtkWebMouseHandler,
        vtkWebPublishImageDelivery,
    )

    D = vtkWebPublishImageDelivery
    for cls, name in (
        (D, "still_render"),
        (D, "image_push"),
        (D, "animate"),
        (D, "start_view_animation"),
        (vtkWebMouseHandler, "mouse_interaction"),
        (vtkWebMouseHandler, "update_zoomFromWheel"),
    ):
        monkeypatch.setattr(cls, name, getattr(cls, name))
    monkeypatch.setattr(frame_delivery, "_installed", [])
    monkeypatch.setattr(frame_delivery, "_dirty", [True])
    monkeypatch.setattr(frame_delivery, "_in_timer", [False])
    frame_delivery.install()
    return D, vtkWebMouseHandler


class _App:
    def __init__(self):
        self.observers = []

    def AddObserver(self, event, fn):
        self.observers.append((event, fn))


class _Protocol:
    decode = False

    def __init__(self, view):
        self.view = view
        self.app = _App()

    def get_view(self, _vid):
        return self.view

    def get_global_id(self, _view):
        return 1


def test_frames_are_encoded_at_once(patched, plotter):
    D, _ = patched
    proto = _Protocol(plotter.ren_win)
    reply = D.still_render(
        proto, {"view": "1", "quality": 100, "size": [64, 48]}
    )
    assert reply["stale"] is False
    assert reply["size"] == [64, 48]
    assert reply["memsize"] == len(reply["image"]) > 0
    assert _decode(reply["image"]).shape == (48, 64, 3)
    # trame's UpdateEvent marks the picture as changed.
    assert [e for e, _ in proto.app.observers] == ["UpdateEvent"]
    again = D.still_render(proto, {"view": "1", "quality": 100})
    assert again["mtime"] > reply["mtime"]


def test_interaction_timer_skips_frames_without_input(patched, plotter):
    D, _ = patched
    proto = _Protocol(plotter.ren_win)
    D.still_render(proto, {"view": "1"})  # clears the change flag
    frame_delivery._in_timer[0] = True
    try:
        idle = D.still_render(proto, {"view": "1"})
        assert idle["image"] is None and idle["memsize"] == 0
        frame_delivery._mark_dirty()  # e.g. a mouse move
        moved = D.still_render(proto, {"view": "1"})
        assert moved["memsize"] > 0
    finally:
        frame_delivery._in_timer[0] = False


def test_wrapped_rpcs_stay_registered(patched):
    """trame routes RPCs by the attribute @export_rpc sets; losing it
    silently disables mouse input."""
    D, M = patched
    for method, uri in (
        (M.mouse_interaction, "viewport.mouse.interaction"),
        (M.update_zoomFromWheel, "viewport.mouse.zoom.wheel"),
        (D.image_push, "viewport.image.push"),
        (D.start_view_animation, "viewport.image.animation.start"),
    ):
        assert method._wslinkuris == [{"uri": uri}]


def test_interaction_frame_rate_cap_is_raised(patched):
    D, _ = patched

    class _Anim:
        max_frame_rate = 30.0
        views_in_animations: list = []

        def get_view(self, _vid):
            return object()

        def get_global_id(self, _view):
            return 1

        def animate(self):
            pass

    anim = _Anim()
    D.start_view_animation(anim, "1")
    assert anim.max_frame_rate == frame_delivery.MAX_FPS


class _Cam:
    position = (0.0, 0.0, 0.0)
    focal_point = (0.0, 0.0, -1.0)
    up = (0.0, 1.0, 0.0)


def test_smooth_move_keeps_its_duration_on_a_slow_machine():
    """Each frame takes 40 ms to "render" (slower than 60 fps): the move still
    lasts its 0.3 s, with fewer frames, and ends exactly on target."""
    cam = _Cam()
    frames = []

    def push():
        frames.append((time.perf_counter(), cam.position))
        time.sleep(0.04)

    async def move():
        # Timed inside the event loop: starting a loop can itself take
        # a good fraction of a second on a cold Windows CI runner.
        done = await camera_motion.smooth_move(
            cam,
            np.zeros(3),
            np.array([0.0, 0.0, -1.0]),
            np.array([10.0, 0.0, 0.0]),
            np.array([10.0, 0.0, -1.0]),
            0.3,
            60.0,
            is_active=lambda: True,
            push=push,
        )
        return done, time.perf_counter()

    done, end = asyncio.run(move())
    elapsed = end - frames[0][0]
    assert done
    assert 0.2 < elapsed < 0.6  # slack for a loaded CI runner
    # Far fewer than the 18 frames 60 fps would give (a slow CI runner's
    # 40 ms sleeps run long, so the lower bound is loose).
    assert 2 <= len(frames) <= 9
    assert cam.position == (10.0, 0.0, 0.0)


def test_orbit_spins_the_requested_angle():
    cam = _Cam()
    cam.position = (0.0, 0.0, 5.0)  # bearing 0 around the origin
    done = asyncio.run(
        camera_motion.orbit_around(
            cam,
            (0.0, 0.0, 0.0),
            5.0,
            90.0,
            450.0,  # 0.2 s
            60.0,
            is_active=lambda: True,
            push=lambda: None,
        )
    )
    assert done
    np.testing.assert_allclose(cam.position, (5.0, 0.0, 0.0), atol=1e-9)


def test_frame_pacer_holds_the_rate():
    async def go():
        pacer = camera_motion.FramePacer(100.0)
        for _ in range(10):
            await pacer.wait()
        return pacer.elapsed()

    assert 0.08 < asyncio.run(go()) < 0.35  # coarse sleep on Windows CI


def test_closing_socket_errors_are_dropped():
    seen = []

    async def go():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda _loop, ctx: seen.append(ctx))
        frame_delivery._quiet_closed_sockets()
        frame_delivery._quiet_closed_sockets()  # idempotent
        handler = loop.get_exception_handler()
        handler(loop, {"exception": ConnectionResetError("closing transport")})
        handler(loop, {"exception": ValueError("real bug")})

    asyncio.run(go())
    assert [type(c["exception"]) for c in seen] == [ValueError]


def test_background_loads_wait_while_frames_flow(monkeypatch):
    from visage.parallel import loader

    monkeypatch.setattr(loader, "_quiet_until", [0.0])
    monkeypatch.setattr(loader, "_needed", [0])
    t0 = time.monotonic()
    loader._wait_until_quiet()
    assert time.monotonic() - t0 < 0.05  # idle view: no wait

    loader.hold_background(0.2)
    loader._wait_until_quiet()
    assert time.monotonic() - t0 >= 0.19  # lapses by itself

    loader.hold_background(30.0)
    t1 = time.monotonic()
    with loader.background_needed():  # e.g. playback waiting on the preload
        loader._wait_until_quiet()
    assert time.monotonic() - t1 < 0.05


def test_frame_gate_waits_for_the_send():
    sent = []

    async def gate():
        await asyncio.sleep(0.05)
        sent.append(True)

    async def go():
        camera_motion.set_frame_gate(gate)
        try:
            pacer = camera_motion.FramePacer(1000.0)
            await pacer.wait()
        finally:
            camera_motion.set_frame_gate(None)
        return pacer.elapsed()

    assert asyncio.run(go()) >= 0.045 and sent == [True]


def test_a_drag_skips_frames_while_the_browser_is_behind(
    patched, plotter, monkeypatch
):
    """More than two frames in flight: a drag tick sends nothing (no
    backlog of old frames), and the next tick once it has caught up sends
    the latest view."""
    D, _ = patched
    proto = _Protocol(plotter.ren_win)
    pending = [5]
    monkeypatch.setattr(frame_delivery, "backlog", [lambda: pending[0]])
    frame_delivery._in_timer[0] = True
    try:
        frame_delivery._mark_dirty()  # the mouse moved
        behind = D.still_render(proto, {"view": "1"})
        assert behind["image"] is None
        pending[0] = 1  # caught up
        latest = D.still_render(proto, {"view": "1"})
        assert latest["memsize"] > 0
    finally:
        frame_delivery._in_timer[0] = False


def test_a_browser_that_has_not_caught_up_holds_drag_frames(monkeypatch):
    """A ping unanswered past the slack: behind; answered: not; never
    answered (closed page): stops holding after PING_GIVEUP."""
    import time as _t

    fd = frame_delivery
    monkeypatch.setattr(fd, "_ping", {"id": 0, "sent": None})
    sent = []
    monkeypatch.setattr(fd, "ping_sender", [sent.append])
    fd._send_ping()
    assert sent == [1] and not fd.browser_behind()  # just sent
    fd._ping["sent"] = _t.monotonic() - 0.5  # half a second unanswered
    assert fd.browser_behind()
    fd.pong(1)  # the page caught up
    assert not fd.browser_behind()
    fd._send_ping()
    fd._ping["sent"] = _t.monotonic() - 5.0  # no answer coming
    assert not fd.browser_behind() and fd._ping["sent"] is None
    monkeypatch.setenv("VISAGE_BROWSER_FLOW", "0")
    fd._ping["sent"] = _t.monotonic() - 0.5
    assert not fd.browser_behind()
