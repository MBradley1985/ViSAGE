"""Synthetic photometry (SED synthesis) for LightSAGE lightcone output.

Forward-models broadband magnitudes for every galaxy in a lightcone from its
actual star-formation history (SFHMassDisk/SFHMassBulge), using FSPS as the
stellar population synthesis engine. This is synthesis from known simulated
truth, not inverse fitting of observed data.
"""

import os as _os
from pathlib import Path as _Path

# FSPS reads its stellar libraries from $SPS_HOME when it's imported. When
# that isn't set, use the copy LightSAGE's Install puts in ~/.visage/fsps.
if not _os.environ.get("SPS_HOME"):
    _fsps = _Path.home() / ".visage" / "fsps"
    if (_fsps / "SPECTRA").is_dir():
        _os.environ["SPS_HOME"] = str(_fsps)
