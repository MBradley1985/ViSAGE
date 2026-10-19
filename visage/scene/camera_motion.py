"""Shared async camera-motion helpers.

Smooth ease-in/out moves and orbits used by both the toolbar fly-through and
Story Mode.  Each helper drives a PyVista camera frame-by-frame and yields to
the event loop between frames via ``asyncio.sleep``.

The caller supplies two callbacks:

``is_active()``
    Return ``True`` while the motion should keep running.  Returning ``False``
    aborts the move; the helper returns ``False`` so the caller can bail out of
    its sequence.

``push()``
    Push the freshly-posed frame to the client (typically a wrapper around
    ``server.controller.view_update``).

Motion is paced by the wall clock (FramePacer): the time a frame takes to
render counts towards its slot, and a machine that cannot keep up shows
fewer, larger steps instead of slowing the move down, so a move lasts
*secs* seconds everywhere.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import numpy as np

_UP = (0.0, 1.0, 0.0)

# Target frame rate for camera motion (fly-through, rotation, Story Mode).
# Pushes go straight to the client, so this is the rate the viewer sees
# when the machine can render that fast.
MOTION_FPS = 60.0

# Longest wait for a frame to reach the network before drawing the next.
_SEND_TIMEOUT_S = 0.5
_frame_sent: list[Callable[[], Awaitable] | None] = [None]


def set_frame_gate(sent: Callable[[], Awaitable] | None) -> None:
    """Register an awaitable factory that resolves once earlier frames have
    been written to the browser (ViSAGE allows one still in flight).

    Without it a large scene, whose frames take most of a slot to draw,
    renders back-to-back and the sends never get a turn: frames pile up
    and reach the browser late and in bursts.
    """
    _frame_sent[0] = sent


class FramePacer:
    """Hold a loop to *fps* frames per second of wall-clock time.

    ``wait()`` first lets the last frame reach the browser, then sleeps only
    for what is left of the current frame's slot; when a frame overruns,
    the schedule restarts from now instead of rushing to catch up.
    """

    def __init__(self, fps: float) -> None:
        self.interval = 1.0 / fps
        self.started = time.perf_counter()
        self._next = self.started

    def elapsed(self) -> float:
        """Seconds since the pacer started."""
        return time.perf_counter() - self.started

    async def wait(self) -> None:
        sent = _frame_sent[0]
        if sent is not None:
            try:
                await asyncio.wait_for(sent(), _SEND_TIMEOUT_S)
            except Exception:  # timeout, or no server running
                pass
        self._next += self.interval
        delay = self._next - time.perf_counter()
        if delay < 0:
            self._next = time.perf_counter()
            delay = 0.0
        await asyncio.sleep(delay)


async def smooth_move(
    camera,
    p0: np.ndarray,
    f0: np.ndarray,
    p1: np.ndarray,
    f1: np.ndarray,
    secs: float,
    fps: float,
    *,
    is_active: Callable[[], bool],
    push: Callable[[], None],
) -> bool:
    """Ease the camera from (p0, f0) to (p1, f1) over *secs* seconds.

    ``p*`` are camera positions and ``f*`` are focal points, both length-3
    arrays.  Uses smoothstep easing.  Returns ``True`` if the move completed,
    ``False`` if ``is_active`` went false partway through.
    """
    pacer = FramePacer(fps)
    p0 = np.asarray(p0, dtype=float)
    f0 = np.asarray(f0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    f1 = np.asarray(f1, dtype=float)
    while True:
        if not is_active():
            return False
        # Pose for the moment this frame is seen (one slot ahead).
        t = (
            min(1.0, (pacer.elapsed() + pacer.interval) / secs)
            if secs > 0
            else 1.0
        )
        ts = t * t * (3.0 - 2.0 * t)
        camera.position = tuple(p0 + ts * (p1 - p0))
        camera.focal_point = tuple(f0 + ts * (f1 - f0))
        camera.up = _UP
        push()
        if t >= 1.0:
            return True
        await pacer.wait()


async def orbit_around(
    camera,
    target,
    radius: float,
    spin_degs: float,
    dps: float,
    fps: float,
    *,
    is_active: Callable[[], bool],
    push: Callable[[], None],
) -> bool:
    """Orbit the camera around *target* in the XZ plane.

    Continues from the camera's current bearing — no jump.  Spins *spin_degs*
    total at *dps* degrees/second.  Returns ``True`` if it completed, ``False``
    if aborted.
    """
    pacer = FramePacer(fps)
    t3 = np.asarray(target, dtype=float)
    diff = np.asarray(camera.position, dtype=float) - t3
    diff[1] = 0.0
    nrm = np.linalg.norm(diff)
    theta0 = np.arctan2(diff[0], diff[2]) if nrm > 1e-6 else 0.0
    total = abs(spin_degs / dps) if dps else 0.0
    while True:
        if not is_active():
            return False
        secs = min(total, pacer.elapsed() + pacer.interval)
        theta = theta0 + np.deg2rad(dps * secs)
        camera.position = (
            t3[0] + radius * np.sin(theta),
            t3[1],
            t3[2] + radius * np.cos(theta),
        )
        camera.focal_point = tuple(t3)
        camera.up = _UP
        push()
        if secs >= total:
            return True
        await pacer.wait()


def orbit_start_position(camera, target, radius: float) -> np.ndarray:
    """Return the orbit-start position at *radius* around *target*.

    Keeps the camera on its current bearing so there is no direction flip when
    a move into the orbit begins.
    """
    t3 = np.asarray(target, dtype=float)
    diff = np.asarray(camera.position, dtype=float) - t3
    diff[1] = 0.0
    nrm = np.linalg.norm(diff)
    if nrm > 1e-6:
        diff = diff / nrm * radius
    else:
        diff = np.array([0.0, 0.0, radius])
    return np.array([t3[0] + diff[0], t3[1], t3[2] + diff[2]])
