"""Install and Clone on the tool's own button: the button spins and shows
the step it's on and the latest output line, then says how it went. The
output still goes to the wizard terminal, which a failed button opens.

What Install does, per tool:

- SAGE26: first_run.sh on a first install (makes the folders, downloads
  the mini-Millennium trees, points millennium.par at them), then make
  on every core (serial when there is no MPI compiler).
- LightSAGE: the C/C++ libraries its tools need (Homebrew on macOS, apt
  inside WSL on Windows), the photometry packages (fsps, astropy) and the
  FSPS stellar libraries they read, then the two tools (sage2kdtree,
  cli_lightcone).
- SAGEswarm: its Python requirements (it runs SAGE26, so it says when
  SAGE26 isn't compiled yet).

Clone fetches a fresh copy (an existing one is moved aside, never
deleted) and then installs it.
"""

from __future__ import annotations

import codecs
import importlib.util
import os
import shutil
import sys
import time
from pathlib import Path

from visage.wizard.screens import _ANSI

_FSPS_REPO = "https://github.com/cconroy20/fsps"
# Homebrew formulae LightSAGE's tools build against.
_LC_BREW = ("cmake", "boost", "hdf5")


def fsps_data_dir() -> Path | None:
    """Where the FSPS stellar libraries are: $SPS_HOME, or the copy
    LightSAGE's Install puts in ~/.visage/fsps."""
    for cand in (os.environ.get("SPS_HOME"), Path.home() / ".visage" / "fsps"):
        if cand and (Path(cand) / "SPECTRA").is_dir():
            if (Path(cand) / "ISOCHRONES").is_dir():
                return Path(cand)
    return None


class InstallMixin:
    """Install / Clone run on their buttons (see the module docstring)."""

    # ── progress on the button ───────────────────────────────────────────

    def _inline_begin(self, mode: str, act: str) -> None:
        self._inline = {
            "mode": mode,
            "act": act,
            "step": "",
            "last": "",
            "pushed": 0.0,
            "decoder": codecs.getincrementaldecoder("utf-8")("replace"),
        }
        # One job at a time: the other buttons wait.
        info = dict(self._st.wiz_mode_info)
        info["actions"] = [
            (
                {**a, "disabled": True}
                if not a["value"].endswith(f":{act}")
                else a
            )
            for a in info.get("actions", [])
        ]
        self._st.wiz_mode_info = info
        self._wiz_buf = bytearray()
        self._push_bytes(b"\x1b[2J\x1b[3J\x1b[H")
        self._set_action(mode, act, busy=True, sub="Starting ...")

    def _inline_step(self, text: str) -> None:
        job = self._inline
        job["step"], job["last"] = text, ""
        self._emit(text, "info")
        self._set_action(job["mode"], job["act"], busy=True, sub=text + " ...")

    def _inline_output(self, data: bytes) -> None:
        """A command's output while a button runs it: show its latest line
        on the button (a few times a second)."""
        job = getattr(self, "_inline", None)
        if not job:
            return
        text = _ANSI.sub("", job["decoder"].decode(data))
        for seg in reversed(text.replace("\r", "\n").split("\n")):
            seg = seg.strip()
            if seg and sum(ch.isalnum() for ch in seg) >= 0.4 * len(seg):
                job["last"] = seg
                break
        now = time.time()
        if now - job["pushed"] < 0.3 or not job["last"]:
            return
        job["pushed"] = now
        last = job["last"]
        if len(last) > 70:
            last = last[:67] + "..."
        self._set_action(
            job["mode"], job["act"], busy=True, sub=f"{job['step']} · {last}"
        )

    async def _inline_end(self, ok: bool, sub: str) -> None:
        job, self._inline = self._inline, None
        mode, act = job["mode"], job["act"]
        # Kept, so the tool's page shows it whenever it's next opened.
        self._job_results[mode] = (act, ok, sub)
        await self._refresh_status()
        if self._st.wiz_view == "mode" and self._st.wiz_mode == mode:
            self._show_mode(mode)

    def _apply_job_result(self, mode: str) -> None:
        """Show the last Install / Clone result on its button."""
        if mode not in self._job_results:
            return
        act, ok, sub = self._job_results[mode]
        if ok:
            self._set_action(mode, act, sub=sub, tone="ok")
        else:
            self._set_action(
                mode,
                act,
                sub=f"{sub} — click to see the output",
                tone="err",
                value=f"act:{mode}:log",
            )

    def _show_log(self, mode: str) -> None:
        """The full output of a button's job (a failed Install / Clone)."""
        self._st.wiz_view = "term"
        self._st.wiz_mode = mode
        self._set_choices([self._mode_back_choice(mode)])

    # ── Install ──────────────────────────────────────────────────────────

    async def _install_inline(self, mode: str, act: str = "install") -> None:
        if getattr(self, "_inline", None):
            return
        self._set_flow(mode)
        self._inline_begin(mode, act)
        try:
            ok, sub = await {
                "sage26": self._install_sage26,
                "sagelightcone": self._install_lightsage,
                "sageswarm": self._install_sageswarm,
            }[mode]()
        except Exception as exc:  # keep the screen usable
            ok, sub = False, f"Stopped: {exc}"
        await self._inline_end(ok, sub)

    async def _install_sage26(self) -> tuple[bool, str]:
        from visage.wizard import controller as c

        d = self._sage26_dir
        if not d:
            return False, "SAGE26 isn't cloned yet"
        # first_run.sh downloads the trees and rewrites millennium.par's
        # paths, so only on a first install (no trees yet).
        trees = d / "input" / "millennium" / "trees" / "trees_063.7"
        fetched = False
        if (d / "first_run.sh").is_file() and not trees.is_file():
            fetched = True
            self._warn_crlf([d / "first_run.sh"])
            self._inline_step("Downloading the Millennium trees")
            if await self._run_cmd(["bash", "first_run.sh"], cwd=d) != 0:
                return False, "first_run.sh failed"
        script = Path.home() / ".visage" / c._SAGE26_BUILD_SCRIPT
        script.parent.mkdir(parents=True, exist_ok=True)
        self._write_unix_text(
            script,
            c._SAGE26_BUILD_SCRIPT_TEMPLATE.format(sage_dir=self._tc_path(d)),
        )
        self._inline_step("Compiling SAGE26")
        if await self._run_cmd(["bash", script], cwd=d) != 0:
            return False, "Compiling failed"
        return True, (
            "Installed: Millennium trees downloaded, SAGE26 compiled"
            if fetched
            else "Installed: SAGE26 compiled"
        )

    async def _install_lightsage(self) -> tuple[bool, str]:
        from visage.wizard import controller as c

        d = self._lc_dir
        if not d:
            return False, "LightSAGE isn't cloned yet"
        notes = []
        # The C/C++ libraries its tools build against.
        if self._toolchain.kind == "wsl":
            if self._missing_tools:
                self._inline_step("Installing the Linux build tools")
                rc = await self._run_cmd(
                    self._toolchain.install_command(), as_root=True
                )
                if rc != 0:
                    return False, "Installing the Linux build tools failed"
        elif sys.platform == "darwin":
            brew = shutil.which("brew") or (
                "/opt/homebrew/bin/brew"
                if Path("/opt/homebrew/bin/brew").is_file()
                else None
            )
            if brew:
                self._inline_step("Checking CMake, Boost and HDF5")
                missing = []
                for f in _LC_BREW:
                    rc = await self._run_quiet([brew, "list", "--versions", f])
                    if rc != 0:
                        missing.append(f)
                if missing:
                    self._inline_step("Installing " + ", ".join(missing))
                    if await self._run_cmd([brew, "install", *missing]) != 0:
                        return False, "Homebrew couldn't install " + ", ".join(
                            missing
                        )
            else:
                notes.append(
                    "no Homebrew: CMake, Boost and HDF5 must be there"
                )
        # Photometry: fsps + astropy in ViSAGE's own Python, and the
        # stellar libraries FSPS reads.
        need = [
            pkg
            for pkg, mod in (
                ("fsps>=0.4", "fsps"),
                ("astropy>=5.0", "astropy"),
            )
            if importlib.util.find_spec(mod) is None
        ]
        if need:
            self._inline_step("Installing the photometry packages")
            rc = await self._run_cmd(
                [sys.executable, "-m", "pip", "install", *need]
            )
            if rc != 0:
                return False, "Installing fsps / astropy failed"
        if fsps_data_dir() is None:
            target = Path.home() / ".visage" / "fsps"
            if target.exists():
                self._move_aside(target)
            self._inline_step("Downloading the FSPS stellar libraries (~1 GB)")
            rc = await self._run_cmd(
                ["git", "clone", "--depth", "1", _FSPS_REPO, target],
                cwd=target.parent,
            )
            if rc != 0:
                return False, "Downloading the FSPS libraries failed"
            os.environ.setdefault("SPS_HOME", str(target))
        # The two tools.
        script = self._lc_build_script_path()
        script.parent.mkdir(parents=True, exist_ok=True)
        self._write_unix_text(
            script,
            c._LC_BUILD_SCRIPT_TEMPLATE.format(
                lc_dir=self._tc_path(d),
                patch_dir=self._tc_path(c._LC_PATCH_DIR),
            ),
        )
        self._warn_crlf([d / "setup.sh", d / "install.sh"])
        self._inline_step("Building sage2kdtree and cli_lightcone")
        if await self._run_cmd(["bash", script], cwd=d) != 0:
            return False, "Building the tools failed"
        if not self._lc_built(d)[0]:
            return False, "The build left no tools in bin/"
        done = "Installed: libraries, photometry and both tools"
        return True, done + (f" ({notes[0]})" if notes else "")

    async def _install_sageswarm(self) -> tuple[bool, str]:
        d = self._sw_dir
        if not d:
            return False, "SAGEswarm isn't cloned yet"
        if (d / "requirements.txt").is_file():
            self._inline_step("Installing the Python packages")
            cmd = ["python3", "-m", "pip", "install", "-r", "requirements.txt"]
            if self._toolchain.kind == "wsl":
                # Ubuntu's python3 refuses system-wide installs (PEP 668).
                cmd = [
                    "bash",
                    "-c",
                    "python3 -m pip install --user --break-system-packages "
                    "-r requirements.txt || "
                    "python3 -m pip install --user -r requirements.txt",
                ]
            if await self._run_cmd(cmd, cwd=d) != 0:
                return False, "pip install failed"
        if self._locate_sage_bin() is None:
            return True, "Installed; it runs SAGE26, so install SAGE26 too"
        return True, "Installed: Python packages ready, SAGE26 found"

    async def _run_quiet(self, cmd: list) -> int:
        """Run a quick check command without showing its output."""
        import asyncio

        try:
            proc = await asyncio.create_subprocess_exec(
                *map(str, cmd),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return await proc.wait()
        except OSError:
            return 127

    # ── Clone ────────────────────────────────────────────────────────────

    def _clone_target(self, mode: str) -> Path:
        """Where a clone goes: over the existing checkout (moved aside
        first), else beside the other tools, else beside ViSAGE."""
        name = {
            "sage26": "SAGE26",
            "sagelightcone": "LightSAGE",
            "sageswarm": "SAGEswarm",
        }[mode]
        here = self._repo_of(mode)
        if here is not None:
            return here
        for other in (self._sage26_dir, self._lc_dir, self._sw_dir):
            if other is not None:
                return other.parent / name
        return Path.cwd().resolve().parent / name

    async def _clone_inline(self, mode: str) -> None:
        if getattr(self, "_inline", None):
            return
        from visage.wizard import controller as c

        self._set_flow(mode)
        self._inline_begin(mode, "clone")
        target = self._clone_target(mode)
        repo = {
            "sage26": c._SAGE26_REPO,
            "sagelightcone": c._LIGHTSAGE_REPO,
            "sageswarm": c._SAGESWARM_REPO,
        }[mode]
        try:
            moved = None
            if target.exists():
                moved = self._move_aside(target)
                self._emit(f"Existing checkout moved to {moved}", "warn")
            self._inline_step(f"Cloning into {target}")
            cmd = ["git", "clone", repo, target]
            if mode == "sagelightcone":  # as its README says
                cmd.insert(2, "--recurse-submodules")
            if await self._run_cmd(cmd, cwd=target.parent) != 0:
                await self._inline_end(False, "Cloning failed")
                return
            if mode == "sage26":
                self._sage26_dir = target
                ok, sub = await self._install_sage26()
            elif mode == "sagelightcone":
                self._lc_dir = target
                ok, sub = await self._install_lightsage()
            else:
                self._sw_dir = target
                ok, sub = await self._install_sageswarm()
            if ok:
                sub = "Cloned and installed" + (
                    f"; the old copy is at {moved.name}" if moved else ""
                )
        except Exception as exc:
            ok, sub = False, f"Stopped: {exc}"
        await self._inline_end(ok, sub)
