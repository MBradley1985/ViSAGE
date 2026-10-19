"""Frame-delivery timing (``visage --perf``).

Every frame the browser shows is rendered on the server, read back from
the GPU, JPEG-encoded and pushed over the websocket.  When the view feels
slow, the question is which of those steps is slow on this machine.  This
prints, every few seconds while frames are flowing, a line such as::

    perf: 24.6 fps · 1600x900 · render 6.1 ms · frame 31.4 ms · between 9 ms · 412 KB (9.9 MB/s)

* render — VTK drawing the scene, until the GPU has finished
* frame  — render + GPU readback + JPEG encode, per delivered frame
* between — the rest of each frame's share of a second: handling input,
  sending the image, and waiting for the next one to be asked for
* KB     — encoded frame size; MB/s is what the websocket carries

A frame time much larger than render points at readback/encoding (CPU
speed, frame size); a large "between" points at the rest of the server
(input handling, background work competing for the CPU).
"""

from __future__ import annotations

import asyncio
import time


class _Stats:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.started = time.perf_counter()
        self.frames = 0
        self.frame_s = 0.0
        self.bytes = 0
        self.renders = 0
        self.render_s = 0.0
        self.size = (0, 0)


def describe(stats: _Stats, elapsed: float) -> str | None:
    """The report line for one interval, or None if no frames were sent."""
    if not stats.frames or elapsed <= 0:
        return None
    fps = stats.frames / elapsed
    kb = stats.bytes / stats.frames / 1024
    parts = [
        f"{fps:.1f} fps",
        f"{stats.size[0]}x{stats.size[1]}",
    ]
    if stats.renders:
        parts.append(f"render {1000 * stats.render_s / stats.renders:.1f} ms")
        per_frame = stats.renders / stats.frames
        if per_frame > 1.1:  # drawing frames nobody sees
            parts.append(f"{per_frame:.1f} renders/frame")
    frame_ms = 1000 * stats.frame_s / stats.frames
    parts.append(f"frame {frame_ms:.1f} ms")
    parts.append(f"between {max(0.0, 1000 / fps - frame_ms):.0f} ms")
    parts.append(f"{kb:.0f} KB ({stats.bytes / elapsed / 1024**2:.1f} MB/s)")
    return "perf: " + " · ".join(parts)


def install(ren_win, interval: float = 5.0, out=print) -> None:
    """Start timing renders of ``ren_win`` and every frame trame delivers,
    reporting via ``out`` every ``interval`` seconds while frames flow."""
    stats = _Stats()
    render_t0: list[float] = []

    def _start(_obj, _evt):
        render_t0[:] = [time.perf_counter()]

    def _end(_obj, _evt):
        # Render() only queues the drawing; wait for the GPU to finish so
        # "render" is the real drawing time.  The readback that follows
        # waits for it anyway, so this costs nothing extra.
        try:
            ren_win.WaitForCompletion()
        except AttributeError:
            pass
        if render_t0:
            stats.renders += 1
            stats.render_s += time.perf_counter() - render_t0.pop()

    ren_win.AddObserver("StartEvent", _start)
    ren_win.AddObserver("EndEvent", _end)

    from trame_vtk.modules.vtk.protocols import vtkWebPublishImageDelivery

    original = vtkWebPublishImageDelivery.still_render
    timer: list = []

    def _report() -> None:
        line = describe(stats, time.perf_counter() - stats.started)
        if line:
            out(line)
        stats.reset()
        timer.clear()
        if line:  # keep reporting while frames flow; go quiet when idle
            _schedule()

    def _schedule() -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        timer.append(loop.call_later(interval, _report))

    def still_render(self, options):
        t0 = time.perf_counter()
        reply = original(self, options)
        if not timer:
            stats.reset()
            _schedule()
        if reply.get("memsize"):
            stats.frames += 1
            stats.frame_s += time.perf_counter() - t0
            stats.bytes += int(reply["memsize"])
            stats.size = tuple(reply.get("size") or (0, 0))
        return reply

    vtkWebPublishImageDelivery.still_render = still_render
