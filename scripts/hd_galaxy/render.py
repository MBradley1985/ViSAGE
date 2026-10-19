"""Shim: the ray-marcher now lives in the viewer package (visage.hd.raymarch)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from visage.hd.raymarch import *  # noqa: E402,F401,F403
