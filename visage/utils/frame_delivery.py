"""Fast JPEG encoding for the frames trame sends to the browser.

trame-vtk renders each frame and hands it to VTK's built-in JPEG encoder.
That encoder is built without SIMD.  At quality 100 it needs ~35 ms for a
typical ViSAGE frame, three to four times longer than the GPU takes to draw
it, which caps the frame rate and makes the view lag a frame behind input.
Pillow's libjpeg-turbo produces the same quality-100 JPEG in ~3 ms.

``install()`` swaps trame's frame step for render, read back, encode with
Pillow, at the same resolution and quality.  Encoding finishes before the
frame is sent, so each push carries the image just drawn and none are
dropped.

During a mouse drag trame asks for frames on a timer, capped at 30 fps;
the cap is raised to MAX_FPS, and a tick with no input since the last frame
(the mouse held still) sends nothing instead of drawing the same frame
again.
"""

from __future__ import annotations

import asyncio
import functools
import io
import itertools
import time

from PIL import Image

from visage.scene.camera_motion import MOTION_FPS

# Highest frame rate trame's interaction timer may reach.
MAX_FPS = MOTION_FPS

_installed: list[bool] = []
_mtime = itertools.count(1)
# Set by anything that may change the picture; cleared by each render.
_dirty = [True]
_in_timer = [False]
# Called after every frame sent (e.g. to hold back background work).
on_frame: list = []


def _mark_dirty(*_args) -> None:
    _dirty[0] = True


def _quiet_closed_sockets() -> None:
    """Drop the error a frame raises when it is sent just as a browser tab
    closes.  wslink still lists the closing socket, the send fails inside
    a task nobody awaits, and asyncio prints a traceback, almost every time
    a tab closes while the view is moving.  It is harmless."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    previous = loop.get_exception_handler()
    if getattr(previous, "_visage_quiet", False):
        return

    def handler(loop, context):
        if isinstance(context.get("exception"), ConnectionResetError):
            return
        if previous is not None:
            previous(loop, context)
        else:
            loop.default_exception_handler(context)

    handler._visage_quiet = True
    loop.set_exception_handler(handler)


def _marking(method):
    # functools.wraps keeps the attributes @export_rpc put on the method;
    # without them trame no longer routes the RPC to it.
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        _dirty[0] = True
        return method(self, *args, **kwargs)

    return wrapper


class _Grabber:
    """Reads a render window's back buffer the way vtkWebApplication does."""

    def __init__(self, view) -> None:
        from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

        self._w2i = vtkWindowToImageFilter()
        self._w2i.SetInput(view)
        self._w2i.SetScale(1)
        self._w2i.ReadFrontBufferOff()
        self._w2i.ShouldRerenderOff()
        self._w2i.SetInputBufferTypeToRGB()

    def jpeg(self, quality: int) -> tuple[bytes, tuple[int, int]]:
        self._w2i.Modified()
        self._w2i.Update()
        img = self._w2i.GetOutput()
        w, h, _ = img.GetDimensions()
        pixels = memoryview(img.GetPointData().GetScalars())
        # VTK rows run bottom-up; a -1 stride flips them without a copy.
        frame = Image.frombuffer("RGB", (w, h), pixels, "raw", "RGB", 0, -1)
        out = io.BytesIO()
        frame.save(out, "JPEG", quality=int(quality))
        return out.getvalue(), (w, h)


def render_jpeg(
    view, quality: int, grabbers: dict
) -> tuple[bytes, tuple[int, int]]:
    """Render ``view`` and return (JPEG bytes, (width, height))."""
    grabber = grabbers.get(view)
    if grabber is None:
        grabber = grabbers[view] = _Grabber(view)
    view.Render()
    return grabber.jpeg(quality)


def install() -> None:
    """Patch trame-vtk's image delivery (once per process)."""
    if _installed:
        return
    from trame_vtk.modules.vtk.protocols import (
        vtkWebMouseHandler,
        vtkWebPublishImageDelivery,
    )

    D = vtkWebPublishImageDelivery
    original = D.still_render
    grabbers: dict = {}
    observed: set[int] = set()

    # Input and explicit pushes mark the picture as changed.  Everything
    # else trame does to a view (camera reset/update, ...) fires the
    # application's UpdateEvent, observed below.
    D.image_push = _marking(D.image_push)
    vtkWebMouseHandler.mouse_interaction = _marking(
        vtkWebMouseHandler.mouse_interaction
    )
    vtkWebMouseHandler.update_zoomFromWheel = _marking(
        vtkWebMouseHandler.update_zoomFromWheel
    )

    animate = D.animate

    @functools.wraps(animate)
    def timed_animate(self):
        _in_timer[0] = True
        try:
            animate(self)
        finally:
            _in_timer[0] = False

    D.animate = timed_animate

    start_view_animation = D.start_view_animation

    @functools.wraps(start_view_animation)
    def faster_start(self, *args, **kwargs):
        self.max_frame_rate = max(self.max_frame_rate, MAX_FPS)
        return start_view_animation(self, *args, **kwargs)

    D.start_view_animation = faster_start

    def still_render(self, options):
        if self.decode:  # base64 delivery: not used by ViSAGE
            return original(self, options)
        begin = time.time()
        view = self.get_view(options["view"])
        if not view:
            return original(self, options)
        if id(self.app) not in observed:
            observed.add(id(self.app))
            self.app.AddObserver("UpdateEvent", _mark_dirty)
            _quiet_closed_sockets()
        if _in_timer[0] and not _dirty[0]:
            return {"image": None, "stale": False, "memsize": 0}
        _dirty[0] = False
        size = list(options.get("size") or view.GetSize()[0:2])
        if size != list(view.GetSize()[0:2]) and size[0] > 10 and size[1] > 10:
            view.SetSize(size)
        quality = options.get("quality", 100)
        image, real_size = render_jpeg(view, quality, grabbers)
        for fn in on_frame:
            fn()
        return {
            "stale": False,
            "mtime": next(_mtime),
            "size": list(real_size),
            "memsize": len(image),
            "format": "jpeg",
            "global_id": str(self.get_global_id(view)),
            "localTime": options.get("localTime", 0),
            "image": image,
            "workTime": round((time.time() - begin) * 1000),
        }

    vtkWebPublishImageDelivery.still_render = still_render
    _installed.append(True)
