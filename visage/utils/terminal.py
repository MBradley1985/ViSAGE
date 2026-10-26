"""Child processes attached to a terminal, on every platform.

The Launch-Mode wizard and the Console both stream a child process into an
xterm.js terminal in the browser.  A real pseudo-terminal matters: programs
only print colours and ``\\r`` progress bars when they think a person is
watching, and an interactive shell needs one to show a prompt at all.

Backends, picked automatically:

* ``pty``    — macOS / Linux: a POSIX pty in its own session, so Ctrl+C
  reaches the whole job (e.g. SAGEswarm and every SAGE it spawned).
* ``winpty`` — Windows: a ConPTY via the pywinpty package.
* ``pipe``   — fallback anywhere: plain pipes.  No colours or prompts, but
  output still streams and the process can still be interrupted.

Every child is registered with visage.procs: closing its terminal, or
ViSAGE stopping however it does, stops it and everything it started.
"""

from __future__ import annotations

import os
import queue
import select
import signal
import subprocess
import sys
import threading
import time

from visage import procs

IS_WINDOWS = sys.platform == "win32"

# pywinpty pads its socket stream with this marker when a read comes back
# empty; it is never real program output.
_WINPTY_IDLE = b"0011Ignore"


class TerminalProcess:
    """A running child process and the terminal it writes to."""

    def read(self, timeout: float = 1.0) -> bytes | None:
        """Wait up to ``timeout`` s for output, then return everything that
        is ready.  None means nothing arrived yet; b"" means the terminal
        closed (the process exited and all its output has been read)."""
        raise NotImplementedError

    def write(self, data: bytes) -> None:
        """Send keystrokes to the process."""
        raise NotImplementedError

    def resize(self, rows: int, cols: int) -> None:
        """Tell the process the terminal changed size."""

    def poll(self) -> int | None:
        """Exit code, or None while still running."""
        raise NotImplementedError

    def wait(self) -> int:
        raise NotImplementedError

    def interrupt(self) -> None:
        """The equivalent of pressing Ctrl+C."""
        raise NotImplementedError

    def close(self) -> None:
        """Release the terminal, killing the process if it still runs."""
        raise NotImplementedError

    def is_alive(self) -> bool:
        return self.poll() is None


def default_backend() -> str:
    if not IS_WINDOWS:
        return "pty"
    try:
        import winpty  # noqa: F401
    except ImportError:
        return "pipe"
    return "winpty"


def spawn(
    argv: list,
    cwd=None,
    env: dict | None = None,
    rows: int = 24,
    cols: int = 80,
    backend: str | None = None,
) -> TerminalProcess:
    """Start ``argv`` attached to a new terminal of ``rows`` x ``cols``."""
    argv = [str(a) for a in argv]
    cwd = str(cwd) if cwd else None
    backend = backend or default_backend()
    if backend == "pty":
        return _PosixPty(argv, cwd, env, rows, cols)
    if backend == "winpty":
        return _WinPty(argv, cwd, env, rows, cols)
    if backend == "pipe":
        return _PipeProcess(argv, cwd, env)
    raise ValueError(f"unknown terminal backend {backend!r}")


# ── POSIX pty ─────────────────────────────────────────────────────────────


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    import fcntl
    import struct
    import termios

    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class _PosixPty(TerminalProcess):
    def __init__(self, argv, cwd, env, rows, cols) -> None:
        import pty

        master, slave = pty.openpty()
        try:
            _set_winsize(slave, rows, cols)
        except OSError:
            pass
        try:
            # A new session makes the child a process-group leader, so an
            # interrupt reaches everything it starts, not just itself.
            self._proc = subprocess.Popen(
                argv,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True,
                cwd=cwd,
                env=env,
                start_new_session=True,
            )
        except BaseException:
            os.close(master)
            os.close(slave)
            raise
        os.close(slave)
        procs.track(self._proc)
        self._fd = master
        self._closed = False

    def read(self, timeout: float = 1.0) -> bytes | None:
        if self._closed:
            return b""
        try:
            ready, _, _ = select.select([self._fd], [], [], timeout)
        except (OSError, ValueError):
            return b""
        if not ready:
            return None
        try:
            chunk = os.read(self._fd, 4096)
        except OSError:  # EIO on Linux once the child has gone
            return b""
        if not chunk:
            return b""
        # Drain whatever else is already buffered so a burst arrives whole.
        buf = bytearray(chunk)
        while True:
            try:
                ready, _, _ = select.select([self._fd], [], [], 0)
                if not ready:
                    break
                more = os.read(self._fd, 4096)
            except OSError:
                break
            if not more:
                break
            buf.extend(more)
        return bytes(buf)

    def write(self, data: bytes) -> None:
        os.write(self._fd, data)

    def resize(self, rows: int, cols: int) -> None:
        try:
            _set_winsize(self._fd, rows, cols)
        except OSError:
            pass

    def poll(self) -> int | None:
        return self._proc.poll()

    def wait(self) -> int:
        return self._proc.wait()

    def interrupt(self) -> None:
        os.killpg(os.getpgid(self._proc.pid), signal.SIGINT)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                os.close(self._fd)
            except OSError:
                pass
        # The whole job: what the command started may outlive it.
        procs.stop_group(self._proc)


# ── Windows ConPTY (pywinpty) ─────────────────────────────────────────────


class _WinPty(TerminalProcess):
    def __init__(self, argv, cwd, env, rows, cols) -> None:
        from winpty import PtyProcess

        env = {str(k): str(v) for k, v in (env or os.environ).items()}
        self._p = PtyProcess.spawn(
            argv, cwd=cwd, env=env, dimensions=(rows, cols)
        )
        self.pid = self._p.pid
        procs.track(self)
        self._eof = False

    def read(self, timeout: float = 1.0) -> bytes | None:
        if self._eof:
            return b""
        # pywinpty relays the terminal through a local socket, which
        # select() can wait on even on Windows.
        sock = self._p.fileobj
        try:
            ready, _, _ = select.select([sock], [], [], timeout)
        except (OSError, ValueError):
            return b""
        if not ready:
            return None
        try:
            chunk = sock.recv(4096)
        except OSError:
            chunk = b""
        if not chunk:
            self._eof = True
            return b""
        buf = bytearray(chunk)
        while True:
            try:
                ready, _, _ = select.select([sock], [], [], 0)
                if not ready:
                    break
                more = sock.recv(4096)
            except OSError:
                break
            if not more:
                self._eof = True
                break
            buf.extend(more)
        data = bytes(buf).replace(_WINPTY_IDLE, b"")
        return data or None

    def write(self, data: bytes) -> None:
        self._p.write(data.decode("utf-8", errors="replace"))

    def resize(self, rows: int, cols: int) -> None:
        try:
            self._p.setwinsize(rows, cols)
        except Exception:
            pass

    def poll(self) -> int | None:
        if self._p.isalive():
            return None
        status = self._p.exitstatus
        return int(status) if status is not None else 0

    def wait(self) -> int:
        while self._p.isalive():
            time.sleep(0.1)
        return self.poll() or 0

    def interrupt(self) -> None:
        # ConPTY turns ^C into a console Ctrl+C event for every process on
        # the terminal; wsl.exe forwards it into Linux as SIGINT.
        self._p.sendintr()

    def close(self) -> None:
        self._eof = True
        procs.stop_group(self)  # taskkill /T: the process tree
        try:
            self._p.close(force=True)
        except Exception:
            pass


# ── plain pipes (fallback) ────────────────────────────────────────────────


def _to_crlf(data: bytes) -> bytes:
    """A pty turns \\n into \\r\\n for the terminal; pipes don't, and
    xterm.js needs the \\r to return to column 0."""
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


class _PipeProcess(TerminalProcess):
    def __init__(self, argv, cwd, env) -> None:
        env = dict(os.environ if env is None else env)
        # A pipe is not a terminal, so Python would block-buffer its output
        # and the user would see nothing until the run ends.
        env.setdefault("PYTHONUNBUFFERED", "1")
        kwargs: dict = {}
        if IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        self._proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            **kwargs,
        )
        procs.track(self._proc)
        self._q: queue.Queue[bytes] = queue.Queue()
        self._eof = False
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        out = self._proc.stdout
        while True:
            try:
                chunk = out.read(4096)
            except (OSError, ValueError):
                chunk = b""
            self._q.put(chunk or b"")
            if not chunk:
                return

    def read(self, timeout: float = 1.0) -> bytes | None:
        if self._eof:
            return b""
        try:
            chunk = self._q.get(timeout=timeout)
        except queue.Empty:
            return None
        if not chunk:
            self._eof = True
            return b""
        buf = bytearray(chunk)
        while True:
            try:
                more = self._q.get_nowait()
            except queue.Empty:
                break
            if not more:
                self._eof = True  # report it on the next read
                break
            buf.extend(more)
        return _to_crlf(bytes(buf))

    def write(self, data: bytes) -> None:
        self._proc.stdin.write(data)
        self._proc.stdin.flush()

    def poll(self) -> int | None:
        return self._proc.poll()

    def wait(self) -> int:
        return self._proc.wait()

    def interrupt(self) -> None:
        if IS_WINDOWS:
            os.kill(self._proc.pid, signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGINT)

    def close(self) -> None:
        self._eof = True
        procs.stop_group(self._proc)
        for f in (self._proc.stdin, self._proc.stdout):
            try:
                f.close()
            except Exception:
                pass
