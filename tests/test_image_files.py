"""Saving a screenshot in the file types the Plotting tab offers."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from visage.plots.style import FORMATS
from visage.utils.image_files import SCREENSHOT_FORMATS, save_image


def _picture():
    return Image.fromarray(np.full((8, 12, 3), 200, dtype=np.uint8))


def test_the_types_match_plotting():
    assert SCREENSHOT_FORMATS == FORMATS


@pytest.mark.parametrize(
    "kind, start",
    [("png", b"\x89PNG"), ("jpeg", b"\xff\xd8"), ("pdf", b"%PDF")],
)
def test_each_type_is_really_that_type(tmp_path, kind, start):
    path = tmp_path / f"shot.{kind}"
    save_image(_picture(), path)
    assert path.read_bytes().startswith(start)


def test_an_svg_holds_the_picture_at_its_size(tmp_path):
    path = tmp_path / "shot.svg"
    save_image(_picture(), path)
    text = path.read_text()
    assert text.startswith("<svg") and text.endswith("</svg>")
    assert 'width="12" height="8"' in text
    assert "data:image/png;base64," in text
