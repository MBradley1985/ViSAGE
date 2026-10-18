"""Where SAGE26, SAGEswarm and LightSAGE's build and run commands execute.

All three are Unix programs: SAGE26 and LightSAGE are C/C++ built with
make/CMake against unistd.h, MPI, HDF5, GSL and Boost, and every step is
driven by bash scripts.  None of that builds with Windows compilers.

* macOS / Linux / WSL — commands run natively, exactly as typed.
* Windows — commands run inside WSL (Windows Subsystem for Linux).  The
  checkouts stay on the Windows drive (C:\\Users\\me\\SAGE26 is
  /mnt/c/Users/me/SAGE26 inside WSL), so the native ViSAGE viewer reads
  SAGE's output directly; only the Unix tools cross over.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePath

from visage import system

# Tools the wizard's flows call inside the Unix environment.  python3-venv
# is not a command; it is checked separately (LightSAGE makes a venv).
LINUX_TOOLS = (
    "git",
    "make",
    "gcc",
    "g++",
    "cmake",
    "mpicc",
    "mpirun",
    "h5cc",
    "python3",
)

# Ubuntu/Debian packages that provide LINUX_TOOLS plus the libraries
# SAGE26 (HDF5, GSL, MPI) and LightSAGE (Boost, HDF5) link against.
LINUX_PACKAGES = (
    "build-essential",
    "git",
    "cmake",
    "pkg-config",
    "wget",
    "curl",
    "ca-certificates",
    "libhdf5-dev",
    "hdf5-tools",
    "libgsl-dev",
    "libopenmpi-dev",
    "openmpi-bin",
    "libboost-program-options-dev",
    "libboost-regex-dev",
    "libboost-filesystem-dev",
    "libboost-chrono-dev",
    "libboost-test-dev",
    "python3",
    "python3-pip",
    "python3-venv",
)

WSL_INSTALL_HELP = (
    "On Windows, SAGE26, SAGEswarm and LightSAGE run inside WSL "
    "(Windows Subsystem for Linux). Install it once from an administrator "
    "PowerShell with:  wsl --install   then restart Windows, open the new "
    "Ubuntu app once to create a user, and click Rescan."
)


class ToolchainUnavailable(RuntimeError):
    """Raised when a command needs WSL on a Windows machine without it."""


@dataclass(frozen=True)
class Toolchain:
    """``kind`` is "native", "wsl", or "missing" (Windows without WSL)."""

    kind: str
    distro: str = ""

    @property
    def available(self) -> bool:
        return self.kind != "missing"

    def describe(self) -> str:
        if self.kind == "wsl":
            return f"WSL ({self.distro or 'default distro'})"
        if self.kind == "missing":
            return "WSL not installed"
        return "native"

    # ── paths ─────────────────────────────────────────────────────────────

    def path(self, p) -> str:
        """``p`` as the toolchain sees it (for command args and the paths
        written into .par files and run scripts)."""
        if self.kind == "wsl":
            return system.to_wsl_path(p)
        return str(p)

    def native(self, s) -> Path:
        """A path the toolchain wrote, as ViSAGE should open it."""
        if self.kind == "wsl":
            return Path(system.from_wsl_path(str(s).strip(), self.distro))
        return Path(str(s).strip()).expanduser()

    # ── commands ──────────────────────────────────────────────────────────

    def wrap(
        self,
        cmd: list,
        cwd=None,
        *,
        env: dict | None = None,
        as_root: bool = False,
    ) -> tuple[list[str], str | None, dict | None]:
        """Turn a logical command into what to actually spawn.

        ``cmd`` items that are Path objects are converted with path().
        Returns (argv, cwd, extra_env) — extra_env is None or variables to
        add on top of os.environ for a native spawn.
        """
        args = [
            self.path(c) if isinstance(c, PurePath) else str(c) for c in cmd
        ]
        if self.kind == "native":
            return args, (str(cwd) if cwd else None), env
        if self.kind == "missing":
            raise ToolchainUnavailable(WSL_INSTALL_HELP)
        # Environment variables don't cross into WSL, so export them in the
        # login shell that runs the command.
        script = []
        if cwd:
            script.append(f"cd {shlex.quote(self.path(cwd))}")
        for k, v in (env or {}).items():
            script.append(f"export {k}={shlex.quote(str(v))}")
        script.append("exec " + shlex.join(args))
        argv = ["wsl.exe"]
        if self.distro:
            argv += ["-d", self.distro]
        if as_root:
            argv += ["-u", "root"]
        argv += ["-e", "bash", "-lc", " && ".join(script)]
        return argv, None, None

    def display(self, cmd: list) -> str:
        """The command line shown in the wizard terminal."""
        args = [
            self.path(c) if isinstance(c, PurePath) else str(c) for c in cmd
        ]
        prefix = "[WSL] " if self.kind == "wsl" else ""
        return prefix + " ".join(args)

    def capture(
        self, cmd: list, cwd=None, timeout: float = 30
    ) -> tuple[int, str]:
        """Run quietly and return (returncode, stdout)."""
        try:
            argv, run_cwd, extra = self.wrap(cmd, cwd)
        except ToolchainUnavailable:
            return 1, ""
        env = {**os.environ, **extra} if extra else None
        try:
            res = subprocess.run(
                argv,
                cwd=run_cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 1, ""
        return res.returncode, res.stdout.decode(errors="replace").strip()

    def missing_tools(self) -> list[str]:
        """Which of LINUX_TOOLS (and python3-venv) the environment lacks.
        Only meaningful under WSL; natively the user manages their tools."""
        if self.kind != "wsl":
            return []
        probe = (
            f"for t in {' '.join(LINUX_TOOLS)}; do "
            'command -v "$t" >/dev/null 2>&1 || echo "$t"; done; '
            "python3 -c 'import ensurepip' >/dev/null 2>&1 "
            "|| echo python3-venv"
        )
        rc, out = self.capture(["bash", "-c", probe], timeout=60)
        if rc != 0 and not out:
            return list(LINUX_TOOLS)
        return out.split()

    def install_command(self) -> list[str]:
        """apt command (run as root) that installs LINUX_PACKAGES."""
        pkgs = " ".join(LINUX_PACKAGES)
        return [
            "bash",
            "-c",
            "export DEBIAN_FRONTEND=noninteractive && apt-get update && "
            f"apt-get install -y --no-install-recommends {pkgs}",
        ]


def _probe_wsl() -> Toolchain:
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl:
        return Toolchain("missing")
    try:
        res = subprocess.run(
            [wsl, "-e", "sh", "-c", "echo VISAGE_OK:$WSL_DISTRO_NAME"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=60,  # the first call may boot the WSL VM
        )
    except (OSError, subprocess.TimeoutExpired):
        return Toolchain("missing")
    out = res.stdout.decode(errors="replace")
    if res.returncode != 0 or "VISAGE_OK:" not in out:
        # wsl.exe exists but no Linux distribution is installed yet.
        return Toolchain("missing")
    distro = out.split("VISAGE_OK:", 1)[1].strip()
    return Toolchain("wsl", distro)


_detected: Toolchain | None = None


def detect(refresh: bool = False) -> Toolchain:
    """The toolchain for this machine (cached; ``refresh`` re-probes, e.g.
    after the user installs WSL and clicks Rescan)."""
    global _detected
    if _detected is None or refresh:
        _detected = _probe_wsl() if system.IS_WINDOWS else Toolchain("native")
    return _detected
