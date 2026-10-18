"""Platform and hardware detection.

ViSAGE runs on macOS, Linux (desktop, HPC, WSL) and Windows.  Everything
that differs between them — how much memory and how many CPUs this process
may use, which GPU renders, how a path looks to WSL, how to restart the
viewer — is answered here so the rest of the code never branches on the OS.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


@lru_cache(maxsize=1)
def is_wsl() -> bool:
    """True when running inside Windows Subsystem for Linux."""
    if not IS_LINUX:
        return False
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def os_label() -> str:
    """Short human-readable platform name, e.g. 'macOS 15.1 (arm64)'."""
    arch = platform.machine() or "?"
    if IS_MAC:
        return f"macOS {platform.mac_ver()[0] or ''} ({arch})".replace(
            "  ", " "
        )
    if IS_WINDOWS:
        return f"Windows {platform.release()} ({arch})"
    if is_wsl():
        return f"Linux on WSL ({arch})"
    return f"Linux ({arch})"


# ── memory ────────────────────────────────────────────────────────────────


def _windows_total_memory() -> int | None:
    import ctypes

    class _MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = _MemoryStatusEx()
    stat.dwLength = ctypes.sizeof(stat)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullTotalPhys)
    except (AttributeError, OSError):
        pass
    return None


def _cgroup_memory_limit() -> int | None:
    """Memory cap imposed on this process by a container or batch scheduler
    (Slurm, Docker, Kubernetes), or None when uncapped."""
    for f in (
        "/sys/fs/cgroup/memory.max",  # cgroup v2
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",  # cgroup v1
    ):
        try:
            raw = Path(f).read_text().strip()
        except OSError:
            continue
        if raw.isdigit():
            return int(raw)
    return None


def total_memory_bytes() -> int | None:
    """Physical memory this process can use, or None if it can't be told.

    On Linux a cgroup limit (an HPC job's allocation, a container's cap)
    wins over the machine's RAM, since exceeding it gets the job killed.
    """
    total: int | None = None
    if IS_WINDOWS:
        total = _windows_total_memory()
    else:
        try:
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError, AttributeError):
            total = None
    if IS_LINUX:
        limit = _cgroup_memory_limit()
        if limit and (total is None or limit < total):
            total = limit
    return total


# ── CPUs ──────────────────────────────────────────────────────────────────


def cpu_count() -> int:
    """CPUs this process may run on — the job's allocation on a cluster
    (CPU affinity), not every core in the node."""
    n = None
    fn = getattr(os, "process_cpu_count", None)  # Python 3.13+
    if fn is not None:
        n = fn()
    elif hasattr(os, "sched_getaffinity"):
        try:
            n = len(os.sched_getaffinity(0))
        except OSError:
            n = None
    return max(1, n or os.cpu_count() or 1)


def default_workers() -> int:
    """Worker threads for parallel loading: every CPU but one, so the UI
    and render loop keep a core to themselves."""
    return max(1, cpu_count() - 1)


def system_summary(
    workers: int | None = None, cache_bytes: int | None = None
) -> str:
    """One line describing the machine and what ViSAGE will use of it."""
    gb = 1024**3
    mem = total_memory_bytes()
    cpus = f"{cpu_count()} CPUs"
    if workers:
        cpus += f" ({workers} workers)"
    parts = [os_label(), cpus]
    if mem:
        ram = f"{mem / gb:.1f} GB RAM"
        if cache_bytes:
            ram += f" (cache {cache_bytes / gb:.1f} GB)"
        parts.append(ram)
    return " · ".join(parts)


# ── responsiveness ────────────────────────────────────────────────────────

# PROCESS_POWER_THROTTLING_STATE flags (processthreadsapi.h)
_THROTTLE_EXECUTION_SPEED = 0x1
_THROTTLE_IGNORE_TIMER_RESOLUTION = 0x4  # Windows 11+


def tune_for_interactivity() -> list[str]:
    """Undo two Windows defaults that make the viewer feel sluggish.

    * Timer resolution.  Windows wakes sleeping threads on a ~15.6 ms
      system tick, so asyncio's short waits — the frame scheduler's 1 ms
      reschedule, the playback and camera-motion sleeps — each round up
      to a whole tick.  Asking for 1 ms makes them land when intended
      (macOS and Linux already behave this way).
    * Power throttling (EcoQoS).  Windows 11 throttles processes with no
      foreground window — and ViSAGE's console sits in the background
      while you use the browser — moving it to efficiency cores and
      ignoring its timer requests.  ViSAGE opts out, as a game would.

    Both apply to this process only and end with it.  Returns what was
    changed, for the startup report; a no-op elsewhere.
    """
    if not IS_WINDOWS:
        return []
    import atexit
    import ctypes

    notes: list[str] = []
    try:
        winmm = ctypes.WinDLL("winmm")
        if winmm.timeBeginPeriod(1) == 0:  # TIMERR_NOERROR
            atexit.register(winmm.timeEndPeriod, 1)
            notes.append("1 ms timer resolution")
    except (OSError, AttributeError):
        pass

    class _PowerThrottlingState(ctypes.Structure):
        _fields_ = [
            ("Version", ctypes.c_ulong),
            ("ControlMask", ctypes.c_ulong),
            ("StateMask", ctypes.c_ulong),
        ]

    try:
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        proc = ctypes.c_void_p(kernel32.GetCurrentProcess())
        # ControlMask = the policies we take charge of; StateMask 0 = off.
        # Windows 10 rejects the Windows 11-only timer flag, so retry
        # without it.
        for mask in (
            _THROTTLE_EXECUTION_SPEED | _THROTTLE_IGNORE_TIMER_RESOLUTION,
            _THROTTLE_EXECUTION_SPEED,
        ):
            state = _PowerThrottlingState(1, mask, 0)
            if kernel32.SetProcessInformation(
                proc, 4, ctypes.byref(state), ctypes.sizeof(state)
            ):  # 4 = ProcessPowerThrottling
                notes.append("power throttling off")
                break
    except (OSError, AttributeError):
        pass
    return notes


# ── rendering / GPU ───────────────────────────────────────────────────────


def prefer_offscreen_rendering() -> bool:
    """Whether VTK should render into an off-screen buffer.

    The browser shows a stream of server-rendered frames, so the native
    render window is never needed.  On Windows an on-screen one pops up as
    a stray empty window (and stops updating if minimised); on a Linux box
    with no display there is nowhere to open it.  macOS and Linux desktops
    keep the on-screen window they have always used.
    """
    if IS_WINDOWS:
        return True
    if IS_LINUX and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return True
    return False


# Renderer strings that mean OpenGL is running on the CPU.
_SOFTWARE_RENDERERS = (
    "llvmpipe",
    "softpipe",
    "swrast",
    "software rasterizer",
    "gdi generic",
    "microsoft basic render",
    "svga3d",
)


@dataclass
class GPUInfo:
    vendor: str
    renderer: str
    version: str

    @property
    def software(self) -> bool:
        r = self.renderer.lower()
        return any(s in r for s in _SOFTWARE_RENDERERS)

    def describe(self) -> str:
        gl = self.version.split()[0] if self.version else "?"
        kind = "software, CPU" if self.software else f"OpenGL {gl}"
        return f"{self.renderer} ({kind})"


def parse_capabilities(text: str) -> GPUInfo | None:
    """Pull vendor / renderer / version out of VTK's ReportCapabilities()."""
    found: dict[str, str] = {}
    for line in (text or "").splitlines():
        m = re.match(
            r"\s*OpenGL (vendor|renderer|version) string:\s*(.*)", line
        )
        if m:
            found[m.group(1)] = m.group(2).strip()
    if "renderer" not in found:
        return None
    return GPUInfo(
        vendor=found.get("vendor", ""),
        renderer=found["renderer"],
        version=found.get("version", ""),
    )


def report_renderer_once(ren_win, on_report) -> None:
    """Call ``on_report(GPUInfo)`` after the first frame renders.

    The first frame is the earliest point VTK has an OpenGL context to ask,
    and waiting for it means we never force a render (or a window) early.
    """
    tag: list[int] = []

    def _on_end(_obj, _event):
        if tag:
            ren_win.RemoveObserver(tag.pop())
        try:
            info = parse_capabilities(ren_win.ReportCapabilities())
        except Exception:
            info = None
        if info is not None:
            on_report(info)

    tag.append(ren_win.AddObserver("EndEvent", _on_end))


def is_discrete_gpu(name: str) -> bool:
    """Best guess at whether a display adapter is a discrete card, from its
    driver name.  Integrated parts are named '... Graphics' (Intel UHD/Iris,
    AMD Radeon(TM) Graphics / Radeon 780M Graphics / RX Vega 11 Graphics)."""
    n = name.lower()
    if any(k in n for k in ("nvidia", "geforce", "quadro", "tesla")):
        return True
    if ("amd" in n or "radeon" in n) and not n.endswith("graphics"):
        return bool(re.search(r"\b(rx|pro|firepro)\b", n))
    if "intel" in n:
        return bool(re.search(r"arc(\(tm\))?\s+[ab]\d{3}", n))
    return False


_DISPLAY_CLASS = (
    r"SYSTEM\CurrentControlSet\Control\Class"
    r"\{4d36e968-e325-11ce-bfc1-08002be10318}"
)
_VIRTUAL_ADAPTERS = ("basic display", "remote display", "virtual", "parsec")


def windows_display_adapters() -> list[str]:
    """Names of the display adapters installed on this Windows machine."""
    if not IS_WINDOWS:
        return []
    import winreg

    names: list[str] = []
    try:
        cls = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS)
    except OSError:
        return names
    with cls:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(cls, i)
            except OSError:
                break
            i += 1
            if not sub.isdigit():
                continue
            try:
                with winreg.OpenKey(cls, sub) as k:
                    desc = str(winreg.QueryValueEx(k, "DriverDesc")[0])
            except OSError:
                continue
            if desc in names or any(
                v in desc.lower() for v in _VIRTUAL_ADAPTERS
            ):
                continue
            names.append(desc)
    return names


_GPU_PREF_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
_GPU_PREF_VALUE = {"high": "GpuPreference=2;", "low": "GpuPreference=1;"}


def _windows_gpu_preference(mode: str) -> str | None:
    """Set the per-app Windows graphics preference for this interpreter —
    the same setting as Settings › Display › Graphics.  Laptops with an
    integrated and a discrete GPU otherwise render python.exe on the slow
    integrated one."""
    import winreg

    adapters = windows_display_adapters()
    discrete = [a for a in adapters if is_discrete_gpu(a)]
    exe = sys.executable
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _GPU_PREF_KEY) as k:
            current = str(winreg.QueryValueEx(k, exe)[0])
    except OSError:
        current = None

    if mode == "auto":
        # Only when there is a real choice to make, and never over a
        # preference the user set themselves.
        if not discrete or len(adapters) < 2 or current:
            return None
        mode = "high"
    target = _GPU_PREF_VALUE.get(mode)
    if target is None or current == target:
        return None
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _GPU_PREF_KEY) as k:
            winreg.SetValueEx(k, exe, 0, winreg.REG_SZ, target)
    except OSError as exc:
        return f"could not set the Windows graphics preference: {exc}"
    label = "high performance" if mode == "high" else "power saving"
    which = f" ({discrete[0]})" if mode == "high" and discrete else ""
    return (
        f"set Windows graphics preference for {Path(exe).name} to "
        f"{label}{which}; if this launch still renders on the other GPU, "
        "restart ViSAGE"
    )


def apply_gpu_preference(mode: str = "auto") -> str | None:
    """Steer rendering onto the right GPU before VTK creates its context.

    ``mode``: "auto" (pick the discrete GPU on a hybrid Windows laptop),
    "high" (force the discrete GPU), "low" (force the integrated one) or
    "system" (leave the OS default alone).  Returns a line worth printing
    when something was changed, else None.
    """
    mode = (mode or "auto").lower()
    if mode == "system":
        return None
    if IS_WINDOWS:
        try:
            return _windows_gpu_preference(mode)
        except Exception as exc:  # registry access is best-effort
            return f"could not check GPU preference: {exc}"
    if IS_LINUX and mode == "high":
        if is_wsl():
            # WSLg renders through Mesa's D3D12 driver; this picks the card.
            os.environ.setdefault("MESA_D3D12_DEFAULT_ADAPTER_NAME", "NVIDIA")
            return "requested the NVIDIA adapter for WSLg rendering"
        if Path("/proc/driver/nvidia/version").exists():
            os.environ.setdefault("__NV_PRIME_RENDER_OFFLOAD", "1")
            os.environ.setdefault("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
            return "requested NVIDIA PRIME render offload"
        os.environ.setdefault("DRI_PRIME", "1")
        return "requested the discrete GPU (DRI_PRIME=1)"
    return None


# ── paths between Windows and WSL ─────────────────────────────────────────

_DRIVE_PATH = re.compile(r"^([A-Za-z]):(?:[\\/](.*))?$")
_MNT_PATH = re.compile(r"^/mnt/([A-Za-z])(?:/(.*))?$")
_WSL_UNC = re.compile(
    r"^(?:\\\\|//)wsl(?:\$|\.localhost)[\\/]([^\\/]+)(?:[\\/](.*))?$",
    re.IGNORECASE,
)


def to_wsl_path(path) -> str:
    """How WSL sees a Windows path: C:\\Users\\me -> /mnt/c/Users/me.

    \\\\wsl.localhost\\<distro>\\home\\me maps back to /home/me; relative
    paths just get forward slashes.
    """
    s = str(path)
    m = _WSL_UNC.match(s)
    if m:
        return "/" + (m.group(2) or "").replace("\\", "/")
    m = _DRIVE_PATH.match(s)
    if m:
        rest = (m.group(2) or "").replace("\\", "/").rstrip("/")
        drive = f"/mnt/{m.group(1).lower()}"
        return f"{drive}/{rest}" if rest else drive
    return s.replace("\\", "/")


def from_wsl_path(path: str, distro: str | None = None) -> str:
    """How Windows sees a WSL path: /mnt/c/Users/me -> C:\\Users\\me.

    Other absolute paths live inside the distro's own filesystem and are
    reachable as \\\\wsl.localhost\\<distro>\\... when ``distro`` is known.
    Anything else is returned unchanged.
    """
    s = str(path)
    m = _MNT_PATH.match(s)
    if m:
        rest = (m.group(2) or "").replace("/", "\\")
        return f"{m.group(1).upper()}:\\{rest}"
    if s.startswith("/") and distro:
        return f"\\\\wsl.localhost\\{distro}" + s.replace("/", "\\")
    return s


def native_path(value, *, windows: bool | None = None) -> Path:
    """A path read from a file another tool wrote (a .par, a run script).

    On Windows, a SAGE run inside WSL writes /mnt/c/... paths; those are
    translated so ViSAGE can open them.  Elsewhere this is just Path().
    """
    s = str(value).strip()
    if IS_WINDOWS if windows is None else windows:
        s = from_wsl_path(s)
    return Path(s).expanduser()


# ── processes ─────────────────────────────────────────────────────────────


def find_ffmpeg() -> str | None:
    """An ffmpeg executable: the one on PATH, else the copy bundled with the
    imageio-ffmpeg package (installed by default on Windows)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


# Session-wide command-line options (--perf, --gpu, --n-jobs, ...) the user
# started with.  Set by the CLI; every relaunch — the wizard opening a model,
# switching to a recent model — passes them on, so they last the session.
SESSION_ARGS: list[str] = []


def relaunch_visage(argv: list[str]):
    """Replace this ViSAGE process with a new one running ``argv`` (plus
    the session's own options, SESSION_ARGS).

    POSIX swaps the process image in place (same PID, same terminal).
    Windows has no real exec — os.execv there spawns a child without
    quoting its arguments, which breaks any path with a space in it — so
    start the child properly and exit; the server port is released as this
    process ends, well before the child finishes importing.
    """
    argv = [*argv, *SESSION_ARGS]
    if IS_WINDOWS:
        import subprocess

        subprocess.Popen([sys.executable, "-m", "visage.cli", *argv])
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    exe = shutil.which("visage")
    if exe:
        os.execv(exe, [exe, *argv])
    os.execv(sys.executable, [sys.executable, "-m", "visage.cli", *argv])
