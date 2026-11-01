"""ViSAGE's fixes to the LightSAGE tools ship as patches, applied for the
build and taken out again (visage/wizard/controller.py)."""

from __future__ import annotations

import shutil
import subprocess

import pytest


def test_patches_ship_and_build_script_applies_then_removes_them():
    from visage.wizard import controller as c

    patches = sorted(c._LC_PATCH_DIR.glob("*.patch"))
    names = [p.name for p in patches]
    assert "0001-rotate-spins-with-box-tiling.patch" in names
    assert "0002-sort-iterator-for-new-libcxx.patch" in names
    assert "0003-rotate-disc-spins-with-box-tiling.patch" in names
    for p in patches:
        text = p.read_text()
        assert text.startswith("diff --git a/") and "\n+" in text

    script = c._LC_BUILD_SCRIPT_TEMPLATE.format(
        lc_dir="/tmp/lightsage", patch_dir="/tmp/patches"
    )
    assert 'PATCH_DIR="/tmp/patches"' in script
    # Applied before cmake, always removed on exit (even if the build fails).
    assert script.index('git apply "$P"') < script.index("cmake -B bin")
    assert "trap unpatch EXIT" in script
    assert "git apply -R" in script


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_build_script_is_valid_bash(tmp_path):
    from visage.wizard import controller as c

    path = tmp_path / "build.sh"
    path.write_text(
        c._LC_BUILD_SCRIPT_TEMPLATE.format(lc_dir="/x", patch_dir="/y")
    )
    assert subprocess.run(["bash", "-n", str(path)]).returncode == 0
