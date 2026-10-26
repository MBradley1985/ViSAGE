"""ViSAGE's reaper (see visage/procs.py): started by ViSAGE in a session
of its own, told on stdin which process groups ("+g PID" / "-g PID") and
single processes ("+p PID" / "-p PID") ViSAGE has running. When stdin
closes -- ViSAGE ended, cleanly or not -- it stops whatever is left:
SIGTERM, then SIGKILL after a grace period."""

import os
import signal
import sys
import time


def _alive(kind: str, pid: int) -> bool:
    try:
        (os.killpg if kind == "g" else os.kill)(pid, 0)
        return True
    except OSError:
        return False


def _send(kind: str, pid: int, sig) -> None:
    try:
        (os.killpg if kind == "g" else os.kill)(pid, sig)
    except OSError:
        pass


def main() -> None:
    for name in ("SIGINT", "SIGHUP", "SIGTERM"):
        signal.signal(getattr(signal, name), signal.SIG_IGN)
    running: set[tuple[str, int]] = set()
    for line in sys.stdin:  # until ViSAGE's end closes
        try:
            op, kind, pid = line[0], line[1:].split()[0], int(line.split()[1])
        except (IndexError, ValueError):
            continue
        if op == "+":
            running.add((kind, pid))
        else:
            running.discard((kind, pid))
    left = [k for k in running if _alive(*k)]
    for k in left:
        _send(*k, signal.SIGTERM)
    t_end = time.monotonic() + 3.0
    while time.monotonic() < t_end and any(_alive(*k) for k in left):
        time.sleep(0.1)
    for k in left:
        if _alive(*k):
            _send(*k, signal.SIGKILL)


if __name__ == "__main__":
    main()
