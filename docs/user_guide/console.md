# Console

The **Console** tab is a multi-mode terminal embedded in the viewer's right panel. It runs on the server side of the Trame app, so its working directory, environment, and process namespace are wherever you launched `visage` from — including remote compute nodes.

## Modes

| Mode | How to enter | Prompt |
|---|---|---|
| **Terminal** (default) | (active on open) | `host:basename user$` |
| **Python REPL** | type `python` / `python3` / `py` | `>>>` |
| **SAGE commands** | click **SAGE Cmds** button | `cmd>` |

Type `terminal` from any non-default mode to return to the shell. Type `exit` or `quit` from REPL or SAGE command mode to return to the shell.

## Terminal mode

The terminal is backed by a real PTY (`$SHELL -l` on macOS/Linux; PowerShell in a ConPTY on Windows), so full ANSI colour, cursor control, and interactive programs (`vim`, `top`, `htop`, `less`, ncurses apps) all work exactly as they would in your local terminal.

Three built-ins are intercepted in-process so they persist between commands:

| Built-in | Behaviour |
|---|---|
| `cd <path>` / `cd` | Change directory (no arg → `~`). Updates the session cwd; the prompt refreshes accordingly. |
| `pwd` | Print the session cwd. |
| `export FOO=bar` | Set an env var on the session; future commands inherit it. `export FOO=` clears the var. |

## Python REPL mode

REPL execution runs in a background thread via `asyncio.to_thread`, so the viewer stays responsive while a long script runs — you can still interact with the 3D viewport during execution.

Inside the REPL, the following names are pre-bound:

| Name | Description |
|---|---|
| `scene` | The `Scene` instance — `scene.primary`, `scene.set_snapshot(n)`, `scene.halo_layer`, `scene.galaxy_layer`, `scene.camera`, ... |
| `state` | The Trame state proxy — read or mutate any UI state variable |
| `ctrl` | The Trame controller — call any registered handler (`ctrl.go_to_halo()`, `ctrl.take_screenshot()`, ...) |
| `server` | The Trame server |
| `plotter` | The PyVista Plotter |
| `np` | NumPy |

Multi-line statements (function defs, for-loops, `with` blocks) are accumulated until the parser says the input is complete; the continuation prompt is `...`. To force-execute a buffered block (e.g. an indented `def`), press Enter on an empty line.

Example:

```python
>>> halos, galaxies = scene.primary.loader.get(63)
>>> galaxies.stellar_mass.shape
(17907,)
>>> import matplotlib
>>> matplotlib.use("Agg")
>>> import matplotlib.pyplot as plt
>>> plt.hist(np.log10(galaxies.stellar_mass), bins=40)
>>> plt.savefig("/tmp/smf.png")
>>> "done"
'done'
```

## SAGE command mode

The same parser that backed the previous Console tab. Useful for one-shot commands without remembering exact Python or shell syntax:

| Phrase | Action |
|---|---|
| `show only clusters` | Filter to environment-class clusters |
| `go to halo 42` | Fly to halo idx 42 (and select its central) |
| `snap 30` | Switch to snapshot 30 |
| `galaxy info` | Open the selection card with every property listed |
| `rotate cw 30` | Start CW rotation at 30°/s |
| `screenshot` | Take a screenshot |
| `help` | List every recognised phrase |

## Multiple sessions

Click the `+` button in the tab strip at the top to spawn another console. Each session has its own:

- PTY process (`$SHELL -l`)
- Command history
- Mode (one can be in Python while another is in shell)
- Shell `cwd` and `env`
- Python interpreter (variables defined in Console 1 are not visible in Console 2)

Close a session via its `×` (only shown when more than one exists). All PTY sessions are cleaned up automatically when the viewer exits.

## Load Script

The **Load Script** button reads the path from the "Script path" field and `exec()`s the file in the active session's Python locals — regardless of which mode the session is in. Variables defined by the script become available in subsequent Python-mode commands in the same session.

```
Script path: /home/me/analyses/smf_plot.py
[Load Script]
```

Use Enter on the script-path field to load + run without taking your hands off the keyboard.

## Pop-out

The **Pop-out** button toggles a floating, draggable, resizable card over the viewport showing the active session's history + input. Drag the title bar to move it; drag the bottom-right corner to resize. Closing the pop-out (× in its title bar) doesn't affect the session — it's just a second surface onto the same console.

## Enter keys

Both input fields (command + script path) submit on Enter, equivalent to clicking the corresponding button (Run / Load Script). This is consistent with every other input across the viewer.
