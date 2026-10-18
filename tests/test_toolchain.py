"""Where the extension tools run (visage.wizard.toolchain) and how the
wizard uses it: native on macOS/Linux, inside WSL on Windows."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path, PureWindowsPath

import pytest

from visage.wizard import toolchain as tcmod
from visage.wizard.controller import (
    WizardController,
    _SAGE26_BUILD_SCRIPT_TEMPLATE,
)
from visage.wizard.toolchain import Toolchain, ToolchainUnavailable

from test_lightcone_flow import _FakeServer

WSL = Toolchain("wsl", "Ubuntu")
NATIVE = Toolchain("native")


def test_native_wrap_is_passthrough():
    argv, cwd, env = NATIVE.wrap(
        ["make", Path("/x/y"), "-j4"], Path("/src"), env={"A": "1"}
    )
    assert argv == ["make", "/x/y", "-j4"]
    assert cwd == "/src"
    assert env == {"A": "1"}


def test_wsl_wrap_translates_paths_and_cwd():
    argv, cwd, env = WSL.wrap(
        ["bash", PureWindowsPath(r"C:\Users\me\.visage\build_sage26.sh")],
        PureWindowsPath(r"C:\Users\me\SAGE26"),
    )
    assert argv[:5] == ["wsl.exe", "-d", "Ubuntu", "-e", "bash"]
    assert argv[5] == "-lc"
    assert argv[6] == (
        "cd /mnt/c/Users/me/SAGE26 && "
        "exec bash /mnt/c/Users/me/.visage/build_sage26.sh"
    )
    assert cwd is None and env is None


def test_wsl_wrap_quotes_spaces_and_exports_env():
    argv, _, _ = WSL.wrap(
        [
            "git",
            "clone",
            "URL",
            PureWindowsPath(r"C:\Users\John Smith\SAGE26"),
        ],
        PureWindowsPath(r"C:\Users\John Smith"),
        env={"PATH_EXTRA": "a b"},
    )
    script = argv[-1]
    assert script.startswith("cd '/mnt/c/Users/John Smith' && ")
    assert "export PATH_EXTRA='a b' && " in script
    assert script.endswith(
        "exec git clone URL '/mnt/c/Users/John Smith/SAGE26'"
    )


def test_wsl_wrap_as_root():
    argv, _, _ = WSL.wrap(["apt-get", "update"], as_root=True)
    assert argv[:5] == ["wsl.exe", "-d", "Ubuntu", "-u", "root"]


def test_missing_toolchain_raises_with_install_help():
    with pytest.raises(ToolchainUnavailable, match="wsl --install"):
        Toolchain("missing").wrap(["make"])


def test_wsl_native_paths():
    assert WSL.native("/mnt/d/data/x.h5") == Path("D:\\data\\x.h5")
    assert WSL.native("/home/me/x") == Path(
        r"\\wsl.localhost\Ubuntu\home\me\x"
    )
    assert WSL.native("./rel") == Path("./rel")


def test_install_command_covers_every_flow():
    script = WSL.install_command()[-1]
    for pkg in ("build-essential", "cmake", "libhdf5-dev", "libgsl-dev"):
        assert pkg in script
    assert "openmpi-bin" in script and "libboost-filesystem-dev" in script
    assert "python3-venv" in script


def test_native_toolchain_reports_no_missing_tools():
    assert NATIVE.missing_tools() == []


def test_detect_is_native_off_windows():
    if sys.platform == "win32":
        pytest.skip("Windows probes WSL")
    assert tcmod.detect(refresh=True).kind == "native"


# ── the wizard on the WSL toolchain ───────────────────────────────────────


def _wizard(tc: Toolchain) -> WizardController:
    w = WizardController(_FakeServer(), 0, auto_start=False)
    w._tc = tc
    return w


def test_lc_seed_script_uses_wsl_paths():
    w = _wizard(WSL)
    w._lc_dir = PureWindowsPath(r"C:\Users\me\LightSAGE")
    w._sage26_dir = PureWindowsPath(r"C:\Users\me\SAGE26")
    text = w._lc_seed_script()
    assert 'LIGHTCONE_DIR="/mnt/c/Users/me/LightSAGE"' in text
    assert 'SAGE_OUTPUT_DIR="/mnt/c/Users/me/SAGE26/output/millennium"' in text
    assert 'PARAM_FILE="/mnt/c/Users/me/SAGE26/input/millennium.par"' in text


def test_par_windows_paths_converted_for_wsl():
    w = _wizard(WSL)
    text = (
        "OutputDir   C:\\Users\\me\\SAGE26\\output\\millennium\\  % out\n"
        "TreeName    trees_063\n"
        "SimulationDir  /mnt/c/already/linux\n"
    )
    out = w._par_paths_for_toolchain(text)
    assert "OutputDir   /mnt/c/Users/me/SAGE26/output/millennium  % out" in out
    assert "TreeName    trees_063" in out
    assert "SimulationDir  /mnt/c/already/linux" in out


@pytest.mark.skipif(
    sys.platform != "win32", reason="C:\\ is only absolute on Windows"
)
def test_lc_output_file_reads_wsl_outdir():
    w = _wizard(WSL)
    w._st.wiz_lc_script_text = 'OUTDIR="/mnt/c/out"\nOUTFILE="cone.h5"\n'
    assert w._lc_output_file() == Path("C:\\out") / "cone.h5"


def test_scripts_are_written_with_unix_line_endings(tmp_path):
    p = tmp_path / "run.sh"
    WizardController._write_unix_text(p, "#!/bin/bash\necho hi\n")
    assert p.read_bytes() == b"#!/bin/bash\necho hi\n"


def test_crlf_checkout_is_flagged(tmp_path):
    w = _wizard(WSL)
    good, bad = tmp_path / "good.sh", tmp_path / "bad.sh"
    good.write_bytes(b"echo ok\n")
    bad.write_bytes(b"echo ok\r\n")
    w._warn_crlf([good, bad])
    log = bytes(w._wiz_buf)
    assert b"bad.sh has Windows (CRLF)" in log and b"good.sh" not in log


def test_sage26_build_script_template():
    text = _SAGE26_BUILD_SCRIPT_TEMPLATE.format(sage_dir="/mnt/c/SAGE26")
    assert 'cd "/mnt/c/SAGE26"' in text
    assert 'make -j"$NJOBS" $MAKE_ARGS' in text
    assert 'MAKE_ARGS="USE-MPI="' in text  # serial fallback without mpicc
    assert "hdf5/serial" in text


# ── the wizard's command runner, end to end ───────────────────────────────


def test_run_cmd_streams_output_and_returns_exit_code():
    w = _wizard(NATIVE)

    async def go():
        return await w._run_cmd(
            [sys.executable, "-c", "print('from-child'); raise SystemExit(2)"]
        )

    assert asyncio.run(go()) == 2
    assert b"from-child" in bytes(w._wiz_buf)
    assert w._run_proc is None and w._st.wiz_run_active is False


def test_run_cmd_missing_program_fails_cleanly():
    w = _wizard(NATIVE)
    rc = asyncio.run(w._run_cmd(["definitely-not-a-real-program-xyz"]))
    assert rc == 1
    assert b"Error" in bytes(w._wiz_buf)


def test_run_cmd_without_wsl_explains_how_to_install():
    w = _wizard(Toolchain("missing"))
    assert asyncio.run(w._run_cmd(["make"])) == 1
    assert b"wsl --install" in bytes(w._wiz_buf)


def test_cancel_interrupts_the_running_command():
    w = _wizard(NATIVE)
    code = (
        "import time; print('ready', flush=True)\n"
        "try:\n    time.sleep(60)\n"
        "except KeyboardInterrupt:\n    raise SystemExit(7)\n"
    )

    async def go():
        task = asyncio.ensure_future(w._run_cmd([sys.executable, "-c", code]))
        for _ in range(200):
            await asyncio.sleep(0.05)
            if b"ready" in bytes(w._wiz_buf):
                break
        w._on_cancel_run()
        return await asyncio.wait_for(task, 30)

    rc = asyncio.run(go())
    assert rc != 0
    assert b"interrupt sent" in bytes(w._wiz_buf)
