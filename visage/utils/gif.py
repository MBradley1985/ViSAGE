"""Colour for GIFs, which allow 256 colours per frame.

Pillow's ``convert("P", palette=ADAPTIVE)`` ignores its ``dither`` argument,
so a splat's soft glow comes out as contour lines.  Dithering needs a fixed
palette, passed to ``quantize``; sharing it across the frames also stops the
colours shimmering from one frame to the next.
"""

from __future__ import annotations

from PIL import Image

_SAMPLES = 12  # frames the palette is drawn from
_THUMB = 256  # their size, on the long side


def shared_palette(paths: list) -> Image.Image:
    """A 256-colour palette for all of the frames in ``paths``."""
    step = max(1, len(paths) // _SAMPLES)
    thumbs = []
    for path in paths[::step]:
        with Image.open(path) as frame:
            thumb = frame.convert("RGB")
        thumb.thumbnail((_THUMB, _THUMB))
        thumbs.append(thumb)
    sheet = Image.new(
        "RGB", (sum(t.width for t in thumbs), max(t.height for t in thumbs))
    )
    x = 0
    for thumb in thumbs:
        sheet.paste(thumb, (x, 0))
        x += thumb.width
    # Median cut shares colours out by pixel count, so a dark background
    # takes most of them and bright glows step; this keeps the local error
    # about five times smaller on a track frame.
    return sheet.quantize(colors=256, method=Image.Quantize.MAXCOVERAGE)


def dithered(frame: Image.Image, palette: Image.Image) -> Image.Image:
    """``frame`` in ``palette``'s colours, dithered."""
    return frame.convert("RGB").quantize(
        palette=palette, dither=Image.Dither.FLOYDSTEINBERG
    )
