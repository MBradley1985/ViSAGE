"""visage.procs: whatever ViSAGE starts stops with it -- whole process
trees, on close, on SIGTERM/SIGHUP, and (via the reaper / watch_parent)
even when ViSAGE is killed outright."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="process groups / signals are POSIX"
)

REPO = str(Path(__file__).resolve().parent.parent)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); it has stopped, just not been reaped.
    out = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
    ).stdout.strip()
    return bool(out) and not out.startswith("Z")


def _wait_gone(pids, timeout=10.0) -> list[int]:
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        left = [p for p in pids if _alive(p)]
        if not left:
            return []
        time.sleep(0.1)
    return [p for p in pids if _alive(p)]


def _tree(tmp_path, name="t"):
    """bash in its own session, with a grandchild (`sleep`, in the
    background) that would outlive bash if only bash were stopped."""
    pidfile = tmp_path / f"{name}.pid"
    proc = subprocess.Popen(
        ["bash", "-c", f"sleep 300 & echo $! > {pidfile}; wait"],
        start_new_session=True,
    )
    t_end = time.monotonic() + 5
    while not (pidfile.exists() and pidfile.read_text().strip()):
        assert time.monotonic() < t_end
        time.sleep(0.05)
    return proc, int(pidfile.read_text())


def test_stop_group_takes_the_whole_tree(tmp_path):
    from visage import procs

    proc, grandchild = _tree(tmp_path)
    procs.track(proc)
    procs.stop_group(proc)
    assert _wait_gone([proc.pid, grandchild]) == []
    assert proc.pid not in procs._groups


def test_cleanup_stops_everything_tracked(tmp_path):
    from visage import procs

    trees = [_tree(tmp_path, f"t{i}") for i in range(2)]
    for p, _ in trees:
        procs.track(p)
    procs.cleanup()
    pids = [x for p, g in trees for x in (p.pid, g)]
    assert _wait_gone(pids) == []


def _viewer_script(tmp_path, body: str) -> Path:
    """A stand-in for ViSAGE: starts a tracked tree, writes its pids,
    then `body` ends it."""
    script = tmp_path / "viewer.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os, signal, subprocess, sys, time
            sys.path.insert(0, {REPO!r})
            from visage import procs
            procs.install()
            pidfile = {str(tmp_path / "g.pid")!r}
            p = subprocess.Popen(
                ["bash", "-c", f"sleep 300 & echo $! > {{pidfile}}; wait"],
                start_new_session=True,
            )
            procs.track(p)
            while not (os.path.exists(pidfile) and open(pidfile).read().strip()):
                time.sleep(0.05)
            print(p.pid, open(pidfile).read().strip(), flush=True)
            """
        )
        + textwrap.dedent(body)
    )
    return script


@pytest.mark.parametrize("sig", ["SIGTERM", "SIGHUP", "SIGKILL"])
def test_tree_goes_when_the_viewer_is_stopped(tmp_path, sig):
    # SIGTERM / SIGHUP: procs' handlers; SIGKILL: no code runs in the
    # viewer at all, so the reaper does it.
    script = _viewer_script(tmp_path, "time.sleep(300)\n")
    viewer = subprocess.Popen(
        [sys.executable, str(script)], stdout=subprocess.PIPE, text=True
    )
    leader, grandchild = map(int, viewer.stdout.readline().split())
    assert _alive(grandchild)
    viewer.send_signal(getattr(signal, sig))
    viewer.wait(10)
    assert _wait_gone([leader, grandchild]) == []


def test_tree_goes_on_a_normal_exit(tmp_path):
    script = _viewer_script(tmp_path, "sys.exit(0)\n")
    out = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    leader, grandchild = map(int, out.split())
    assert _wait_gone([leader, grandchild]) == []


def test_pool_workers_exit_when_their_parent_is_killed(tmp_path):
    script = tmp_path / "pool.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import multiprocessing as mp, os, sys, time
            sys.path.insert(0, {REPO!r})
            from concurrent.futures import ProcessPoolExecutor
            from visage import procs
            if __name__ == "__main__":
                ex = ProcessPoolExecutor(
                    2, mp_context=mp.get_context("spawn"),
                    initializer=procs.watch_parent, initargs=(os.getpid(),),
                )
                for f in [ex.submit(os.getpid) for _ in range(4)]:
                    f.result()
                print(*ex._processes, flush=True)
                time.sleep(300)
            """
        )
    )
    parent = subprocess.Popen(
        [sys.executable, str(script)], stdout=subprocess.PIPE, text=True
    )
    workers = list(map(int, parent.stdout.readline().split()))
    assert workers and all(_alive(w) for w in workers)
    parent.kill()
    parent.wait(10)
    assert _wait_gone(workers) == []


def test_spectrum_worker_stops_and_untracks():
    from visage import procs
    from visage.sed.spectrum import SpectrumWorker

    w = SpectrumWorker()
    w._start()  # (registers itself)
    pid = w._proc.pid
    assert pid in procs._pids
    w.stop()
    assert _wait_gone([pid]) == []
    assert pid not in procs._pids
