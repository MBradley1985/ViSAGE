"""Updating ViSAGE itself from PyPI, for every mode's toolbar.

`register(server)` adds the controller `check_for_updates`: it compares the
installed version with PyPI's and, if newer, pip-installs it, reporting
through the `notice_*` state a VSnackbar shows."""

from __future__ import annotations

import os


def _fetch_latest() -> str:
    """PyPI's newest sage-viewer version."""
    import json
    import ssl
    import urllib.request

    url = "https://pypi.org/pypi/sage-viewer/json"
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, timeout=8, context=ctx) as r:
            return json.loads(r.read())["info"]["version"]
    except ssl.SSLError:
        # macOS Python may lack system CA certs; retry unverified
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(url, timeout=8, context=ctx) as r:
            return json.loads(r.read())["info"]["version"]


def register(server) -> None:
    """Add `check_for_updates` and the notice state it reports through."""
    state = server.state
    state.setdefault("notice_show", False)
    state.setdefault("notice_text", "")
    state.setdefault("notice_color", "warning")
    state.setdefault("notice_timeout", 4500)
    state.setdefault("update_checking", False)

    def notice(text, color, timeout):
        state.notice_text = text
        state.notice_color = color
        state.notice_timeout = timeout
        state.notice_show = True
        state.flush()

    @server.controller.set("check_for_updates")
    async def _on_check_for_updates():
        import asyncio
        import sys

        from visage._version import __version__ as current

        state.update_checking = True
        state.flush()
        await asyncio.sleep(0)
        try:
            latest = await asyncio.get_event_loop().run_in_executor(
                None, _fetch_latest
            )
        except Exception as exc:
            state.update_checking = False
            notice(f"Update check failed: {exc}", "error", 5000)
            return
        if latest == current:
            state.update_checking = False
            notice(f"ViSAGE {current} is up to date.", "success", 4500)
            return

        notice(f"Updating {current} → {latest}…", "info", -1)
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "sage-viewer",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=os.name != "nt",
            )
            from visage import procs

            procs.track(proc)  # stopped if ViSAGE closes mid-install
            try:
                _, stderr = await proc.communicate()
            finally:
                procs.untrack(proc)
            if proc.returncode == 0:
                text = f"Updated to {latest}. Restart ViSAGE to apply."
                color, timeout = "success", -1
            else:
                text = f"pip failed: {stderr.decode(errors='replace')[:140]}"
                color, timeout = "error", 7000
        except Exception as exc:
            text, color, timeout = f"Install failed: {exc}", "error", 7000
        state.update_checking = False
        notice(text, color, timeout)
