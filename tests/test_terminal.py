"""Cross-platform terminal processes (visage.utils.terminal).

Runs real child processes on each backend available on this OS: the POSIX
pty or Windows ConPTY, plus the plain-pipe fallback everywhere.
"""

from __future__ import annotations

import sys
import time

import pytest

from visage.utils import terminal

_BACKENDS = ["pipe"]
if terminal.default_backend() != "pipe":
    _BACKENDS.insert(0, terminal.default_backend())


def _read_all(proc, until: bytes | None = None, timeout: float = 30) -> bytes:
    out = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = proc.read(0.5)
        if data is None:
            if proc.poll() is not None and until is None:
                # Give the last bytes a moment to arrive, then stop.
                tail = proc.read(0.5)
                if tail:
                    out.extend(tail)
                break
            continue
        if not data:
            break
        out.extend(data)
        if until is not None and until in out:
            break
    return bytes(out)


@pytest.mark.parametrize("backend", _BACKENDS)
def test_output_and_exit_code(backend):
    proc = terminal.spawn(
        [sys.executable, "-c", "print('hello'); raise SystemExit(3)"],
        backend=backend,
    )
    try:
        out = _read_all(proc)
        assert b"hello" in out
        assert proc.wait() == 3
    finally:
        proc.close()


@pytest.mark.parametrize("backend", _BACKENDS)
def test_env_and_cwd(backend, tmp_path):
    import os

    env = {**os.environ, "VISAGE_TERMINAL_TEST": "xyz"}
    proc = terminal.spawn(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ['VISAGE_TERMINAL_TEST'], "
            "os.path.basename(os.getcwd()))",
        ],
        cwd=tmp_path,
        env=env,
        backend=backend,
    )
    try:
        out = _read_all(proc)
        assert b"xyz" in out and tmp_path.name.encode() in out
    finally:
        proc.close()


@pytest.mark.parametrize("backend", _BACKENDS)
def test_write_reaches_the_process(backend):
    proc = terminal.spawn(
        [sys.executable, "-c", "print('got:' + input().upper())"],
        backend=backend,
    )
    try:
        # A terminal submits a line on Enter (\r); a pipe needs \n.
        proc.write(b"abc\n" if backend == "pipe" else b"abc\r")
        out = _read_all(proc)
        assert b"got:ABC" in out
    finally:
        proc.close()


def test_pipe_backend_emits_crlf():
    proc = terminal.spawn(
        [sys.executable, "-c", "print('a'); print('b')"], backend="pipe"
    )
    try:
        out = _read_all(proc)
        assert b"a\r\nb\r\n" in out
    finally:
        proc.close()


_SLEEPER = (
    "import time, sys\n"
    "print('ready', flush=True)\n"
    "try:\n"
    "    time.sleep(60)\n"
    "except KeyboardInterrupt:\n"
    "    print('interrupted', flush=True)\n"
    "    sys.exit(5)\n"
)


@pytest.mark.parametrize("backend", _BACKENDS)
def test_interrupt_stops_the_job(backend):
    proc = terminal.spawn([sys.executable, "-c", _SLEEPER], backend=backend)
    try:
        assert b"ready" in _read_all(proc, until=b"ready")
        proc.interrupt()
        _read_all(proc, timeout=20)
        deadline = time.monotonic() + 20
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        rc = proc.poll()
        assert rc is not None and rc != 0
        if not terminal.IS_WINDOWS:
            assert rc == 5  # SIGINT -> KeyboardInterrupt in the child
    finally:
        proc.close()


def test_close_kills_a_running_process():
    proc = terminal.spawn([sys.executable, "-c", _SLEEPER])
    _read_all(proc, until=b"ready")
    proc.close()
    deadline = time.monotonic() + 10
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.1)
    assert proc.poll() is not None


def test_unknown_backend():
    with pytest.raises(ValueError):
        terminal.spawn([sys.executable, "-c", "pass"], backend="nope")
