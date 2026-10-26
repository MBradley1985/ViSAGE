"""Everything ViSAGE starts stops with it.

Every process ViSAGE starts is registered here, and all of them go when
ViSAGE closes, is interrupted (Ctrl+C), loses its terminal (SIGHUP) or is
told to stop (SIGTERM):

  process groups   runs started in their own session (the wizard's builds
                   and runs, the Console's shells, pip, ffmpeg): the
                   whole group, so what they started goes too -- SIGTERM,
                   then SIGKILL for anything still there after a grace
  clean-ups        callables (the HD and spectrum worker processes)

ViSAGE killed outright (SIGKILL, a crash) runs no code at all, so:

  the reaper       a small process in its own session, told each group
                   as it starts and ends; when ViSAGE's end of its pipe
                   closes -- however ViSAGE ended -- it stops what's left
  watch_parent     Python workers (process pools) exit themselves once
                   the process that started them has gone

Windows has no process groups or SIGHUP: there trees go with taskkill /T
on the same paths, and the reaper and watch_parent are POSIX-only.
"""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import threading
import time

IS_WINDOWS = os.name == "nt"
GRACE_S = 3.0  # SIGTERM -> SIGKILL

_lock = threading.RLock()
_groups: dict[int, object] = {}  # leader pid -> its process object
_pids: set[int] = set()  # single processes (the spectrum worker)
_cleanups: list = []
_reaper: dict = {"proc": None}
_installed = [False]


# ── The reaper ───────────────────────────────────────────────────────


def _env_here() -> dict:
    """Environment that runs this same copy of ViSAGE (not whichever
    `visage` another install puts first on the path)."""
    from pathlib import Path

    env = dict(os.environ)
    here = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = os.pathsep.join(
        [here, *filter(None, [env.get("PYTHONPATH")])]
    )
    return env


def _tell_reaper(line: str) -> None:
    if IS_WINDOWS:
        return
    p = _reaper["proc"]
    if p is None or p.poll() is not None:
        try:
            p = _reaper["proc"] = subprocess.Popen(
                [sys.executable, "-m", "visage._reaper"],
                env=_env_here(),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Ctrl+C / SIGHUP don't reach it
                text=True,
                bufsize=1,
            )
            # Re-tell it what's running (a new reaper knows nothing).
            for pid in _groups:
                p.stdin.write(f"+g {pid}\n")
            for pid in _pids:
                p.stdin.write(f"+p {pid}\n")
        except OSError:
            _reaper["proc"] = None
            return
    try:
        p.stdin.write(line + "\n")
        p.stdin.flush()
    except (OSError, ValueError):
        pass


# ── Registration ─────────────────────────────────────────────────────


def track(proc, group: bool = True):
    """Register a started process (subprocess.Popen, an asyncio process,
    anything with ``pid``) to be stopped with ViSAGE. ``group``: it leads
    its own process group (started with start_new_session=True), and the
    whole group is stopped. Returns ``proc``."""
    install()
    pid = int(proc.pid)
    with _lock:
        if group:
            _groups[pid] = proc
            _tell_reaper(f"+g {pid}")
        else:
            _pids.add(pid)
            _tell_reaper(f"+p {pid}")
    return proc


def untrack(proc) -> None:
    """It has ended (or was stopped): forget it."""
    pid = int(proc.pid)
    with _lock:
        if _groups.pop(pid, None) is not None:
            _tell_reaper(f"-g {pid}")
        if pid in _pids:
            _pids.discard(pid)
            _tell_reaper(f"-p {pid}")


def add_cleanup(fn) -> None:
    """Call ``fn()`` when ViSAGE stops (e.g. to end a worker pool)."""
    install()
    with _lock:
        _cleanups.append(fn)


# ── Stopping ─────────────────────────────────────────────────────────


def _alive(proc) -> bool:
    poll = getattr(proc, "poll", None)
    if poll is not None:  # subprocess.Popen
        return poll() is None
    return getattr(proc, "returncode", 0) is None  # asyncio process


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def stop_group(proc, grace: float = GRACE_S) -> None:
    """Stop ``proc`` and everything in its process group: SIGTERM, then
    SIGKILL whatever is left after ``grace`` seconds."""
    pid = int(proc.pid)
    if IS_WINDOWS:
        if _alive(proc):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        untrack(proc)
        return
    _signal_group(pid, signal.SIGTERM)
    t_end = time.monotonic() + grace
    while _group_alive(pid) and time.monotonic() < t_end:
        _reap(proc)
        time.sleep(0.05)
    if _group_alive(pid):
        _signal_group(pid, signal.SIGKILL)
    _reap(proc)
    untrack(proc)


def _signal_group(pgid: int, sig) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _reap(proc) -> None:
    """Collect the leader's exit status (no zombie left)."""
    poll = getattr(proc, "poll", None)
    if poll is not None:
        try:
            poll()
        except Exception:
            pass


def cleanup() -> None:
    """Stop everything ViSAGE started. Safe to call more than once."""
    with _lock:
        fns, _cleanups[:] = list(_cleanups), []
        groups = list(_groups.values())
        pids = list(_pids)
    for fn in fns:
        try:
            fn()
        except Exception:
            pass
    if IS_WINDOWS:
        for proc in groups:
            stop_group(proc)
    else:
        # All at once, then one shared grace period.
        for proc in groups:
            _signal_group(int(proc.pid), signal.SIGTERM)
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        t_end = time.monotonic() + GRACE_S
        while time.monotonic() < t_end and any(
            _group_alive(int(p.pid)) for p in groups
        ):
            for p in groups:
                _reap(p)
            time.sleep(0.05)
        for proc in groups:
            if _group_alive(int(proc.pid)):
                _signal_group(int(proc.pid), signal.SIGKILL)
            _reap(proc)
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    with _lock:
        _groups.clear()
        _pids.clear()
        p = _reaper["proc"]
        _reaper["proc"] = None
    if p is not None:
        try:
            p.stdin.close()  # nothing left for it: it exits
            p.wait(timeout=2)
        except Exception:
            pass


def _on_signal(signum, _frame) -> None:
    cleanup()
    # Then end as that signal would have.
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def install() -> None:
    """Stop everything at exit and on SIGTERM / SIGHUP (once; main
    thread only for the signals)."""
    if _installed[0]:
        return
    _installed[0] = True
    atexit.register(cleanup)
    if threading.current_thread() is not threading.main_thread():
        return
    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            if signal.getsignal(sig) in (signal.SIG_DFL, None):
                signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass


# ── Workers ──────────────────────────────────────────────────────────


def watch_parent(parent: int | None = None) -> None:
    """In a worker process (e.g. a pool's initializer): exit once the
    process that started it has gone, however it ended."""
    if IS_WINDOWS:
        return
    parent = int(parent) if parent else os.getppid()

    def watch():
        while True:
            time.sleep(1.0)
            if os.getppid() != parent:
                os._exit(0)

    threading.Thread(target=watch, daemon=True, name="watch-parent").start()


def stop_pool(pool) -> None:
    """End a ProcessPoolExecutor now: its workers, mid-task or not."""
    if pool is None:
        return
    procs = list(getattr(pool, "_processes", {}).values())
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    t_end = time.monotonic() + GRACE_S
    for p in procs:
        try:
            p.join(max(0.0, t_end - time.monotonic()))
            if p.is_alive():
                p.kill()
                p.join(1)
        except Exception:
            pass
