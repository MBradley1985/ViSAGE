"""Writing an image to a file of the type its name asks for."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

# As the Plotting tab offers.
SCREENSHOT_FORMATS = ("png", "pdf", "jpeg", "svg")


def save_image(image: Image.Image, path: str | Path) -> None:
    """Save ``image`` as ``path``'s type.  PDF and SVG hold the picture as
    it is: a screenshot has no vector drawing to give them."""
    path = Path(path)
    kind = path.suffix.lower().lstrip(".")
    rgb = image.convert("RGB")
    if kind in ("jpg", "jpeg"):
        rgb.save(path, "JPEG", quality=95)
    elif kind == "pdf":
        rgb.save(path, "PDF", resolution=100.0)
    elif kind == "svg":
        buf = io.BytesIO()
        rgb.save(buf, "PNG")
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        w, h = rgb.size
        path.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<image width="{w}" height="{h}" '
            f'xlink:href="data:image/png;base64,{data}"/></svg>'
        )
    else:
        rgb.save(path, "PNG")
