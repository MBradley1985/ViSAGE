"""Shim: the recipe model now lives in the viewer package (visage.hd.model)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from visage.hd.model import *  # noqa: E402,F401,F403
from visage.hd.model import _sample_map  # noqa: E402,F401
