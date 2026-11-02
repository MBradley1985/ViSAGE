"""Soft gradients in GIFs."""

from __future__ import annotations

import numpy as np
from PIL import Image

from visage.utils.gif import dithered, shared_palette


def _glow(tmp_path, name="a.png"):
    y, x = np.mgrid[-1:1:400j, -1:1:400j]
    v = 230 * np.exp(-4 * (x**2 + y**2))
    rgb = np.stack([v, 0.45 * v, 0.4 * v], axis=-1).astype(np.uint8)
    path = tmp_path / name
    Image.fromarray(rgb).save(path)
    return path, rgb


def _smoothed(img):
    """Colour averaged over 8 px blocks, roughly what the eye sees."""
    a = np.asarray(img.convert("RGB")).astype(float)
    return a.reshape(50, 8, 50, 8, 3).mean(axis=(1, 3))


def _crowded(tmp_path):
    """Glows of several hues: more colours than a palette holds, as in a
    real frame."""
    y, x = np.mgrid[-1:1:400j, -1:1:400j]
    rgb = np.zeros((400, 400, 3))
    for cx, cy, colour in (
        (-0.4, -0.3, (230, 100, 90)),
        (0.3, 0.2, (120, 220, 200)),
        (0.1, -0.5, (210, 160, 230)),
        (-0.3, 0.5, (240, 210, 120)),
    ):
        rgb += np.exp(-6 * ((x - cx) ** 2 + (y - cy) ** 2))[..., None] * colour
    path = tmp_path / "crowded.png"
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(path)
    return path


def test_a_glow_has_no_contour_lines(tmp_path):
    path = _crowded(tmp_path)
    frame = Image.open(path)
    plain = frame.convert("P", palette=Image.Palette.ADAPTIVE)
    new = dithered(frame, shared_palette([path]))
    truth = _smoothed(frame)
    assert (
        np.abs(_smoothed(new) - truth).max()
        < np.abs(_smoothed(plain) - truth).max()
    )


def test_dithering_keeps_the_brightness(tmp_path):
    path, _ = _glow(tmp_path)
    frame = Image.open(path)
    got = dithered(frame, shared_palette([path]))
    assert np.abs(_smoothed(got) - _smoothed(frame)).max() < 6


def test_every_frame_shares_the_palette(tmp_path):
    a, _ = _glow(tmp_path, "a.png")
    b, _ = _glow(tmp_path, "b.png")
    palette = shared_palette([a, b])
    one = dithered(Image.open(a), palette).getpalette()
    two = dithered(Image.open(b), palette).getpalette()
    assert one == two
