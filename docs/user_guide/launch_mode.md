# Launch Mode (Wizard)

Launch Mode is a guided setup flow for configuring and running SAGE26 — and two
companion tools, **SAGEswarm** and **LightSAGE** — accessible without leaving
the viewer. All three flows share the same wizard shell (terminal + step chips
+ parameter form) and you can switch between them at any time.

## Entering Launch Mode

```bash
cd /path/to/SAGE26
visage
```

Then open the printed URL in your browser. The wizard launches directly into
**SAGE26 setup**.

You can also enter Launch Mode from inside Explore Mode via the SAGE-logo
dropdown (top-left of the toolbar) → **Setup Wizard**, or jump straight into
one of the other two flows from the same dropdown (**SAGEswarm** /
**LightSAGE**) or their dedicated toolbar buttons.

## The three flows

| Flow | What it does | Wizard menu entry |
|---|---|---|
| **SAGE26 setup** | Clone, compile, configure, and run SAGE26 | Setup Wizard |
| **SAGEswarm** | Clone [SAGEswarm](https://github.com/MBradley1985/SAGEswarm), install its Python requirements, configure `run_pso.sh`, and run a PSO calibration against a compiled SAGE binary — with a live plot gallery | SAGEswarm |
| **LightSAGE** | Clone [LightSAGE](https://github.com/sage-home/sage-lightcone) (upstream repo `sage-home/sage-lightcone`), build its `sage2kdtree` / `cli_lightcone` tools, and run the two-stage lightcone-extraction pipeline against existing SAGE26 output — optionally followed by a third stage that synthesizes broadband photometry (SED) for every lightcone galaxy | LightSAGE |

Each flow's header shows its own 6-step progress chips. From any flow's first
step you can switch to another (e.g. click "Back" from the SAGEswarm or
LightSAGE scan step to return to SAGE26 setup) without closing the wizard.

## Where visage looks for things

The working directory you launch from is the anchor for the entire session:

| What | Where |
|---|---|
| SAGE26 executable & source | Searched in CWD, parent of CWD, then home folder |
| `.par` files | `<SAGE26>/input/` and `<CWD>/input/` |
| Existing models | `<SAGE26>/output/`, `<CWD>/output/`, `<CWD>/sage_outputs/` |
| Screenshots / recordings / exports | `<CWD>/sage_outputs/session_<timestamp>/` |
| LightSAGE lightcone output | `<CWD>/sage_outputs/lightcone/` (editable in the run script's `OUTDIR`) |

**First-time install (no SAGE26 yet):** run `visage` from the folder where you want SAGE26 to live, then use **Clone SAGE26** in the wizard. The wizard will ask which parent directory to clone into (defaulting to your home folder), and will use that cloned directory for the rest of the session.

**Existing SAGE26:** run from the SAGE26 root and the wizard finds everything automatically.

## Step indicator

A row of chips in the header tracks progress through the wizard:

| Chip colour | Meaning |
|---|---|
| Cyan / elevated | Current step |
| Green | Completed step |
| White / outlined | Pending step |

## SAGE26 setup steps

### 1 — Scan environment

The wizard checks for a SAGE26 executable, locates any existing `.par` files under your SAGE root, and reports what it finds.

### 2 — Choose action

| Option | Description |
|---|---|
| **Use existing par file** | Select from the list of discovered `.par` files to edit and run |
| **Create new config file** | Generates a new `.par` from the built-in millennium.par template; you choose the filename before writing |

### 3 — Edit par file (when needed)

The `.par` file opens as a [parameter form](#parameter-form) — one labelled box per option — side-by-side with the terminal output. Both panels are visible simultaneously.

### 4 — Run SAGE26

The wizard creates the `OutputDir` declared in the `.par` file (if it doesn't exist), then launches SAGE26 and streams all output into the terminal.

**Back** at this step returns to the par-file selection step, not to the start of the wizard.

## SAGEswarm steps

1. **Scan** — reports whether an existing SAGEswarm checkout and a compiled SAGE binary were found.
2. **Clone SAGEswarm** — choose a parent directory (defaults to home); clones `MBradley1985/SAGEswarm` into `SAGEswarm/` inside it.
3. **Install deps** — runs `python3 -m pip install -r requirements.txt` in the checkout.
4. **Configure** — `run_pso.sh` opens as a [parameter form](#parameter-form): PSO particle/iteration counts, constraints (`-x`), simulation settings, and paths to the compiled SAGE binary + `.par` file. Valid constraint names (read from the checkout's `src/constraints.py`) are listed above the form.
5. **Run PSO** — saves your edits back into `run_pso.sh` and runs it; a live plot gallery (right-docked panel) shows diagnostic PNGs as SAGEswarm writes them, refreshing automatically.
6. **View plots** — run again, or finish.

## LightSAGE steps

LightSAGE turns existing SAGE26 HDF5 output into a lightcone catalogue — see
**[Lightcone Mode](lightcone.md)** for what you can do with the result.

1. **Scan** — reports whether an existing LightSAGE checkout is found, and whether its `sage2kdtree` / `cli_lightcone` tools are built.
2. **Clone** — choose a parent directory; clones the upstream repo (`sage-home/sage-lightcone`) into a `LightSAGE/` folder inside it.
3. **Build** — builds *only* the two C++ tools (`sage2kdtree`, `cli_lightcone`) — SAGE itself is never rebuilt, since ViSAGE feeds in your existing SAGE26 output. On macOS, if the active Apple-clang toolchain can't parse the default SDK's libc++ headers, the build automatically falls back to a compatible installed SDK.
4. **Configure** — `run_lightcone.sh` opens as a [parameter form](#parameter-form): the SAGE output directory / `.par` / scale-factor list feeding stage 1 (`sage2kdtree`), the sky/redshift bounds (`ra`, `dec`, `z`) and output path feeding stage 2 (`cli_lightcone`), and an optional stage 3 — check **SED_ENABLED** to synthesize broadband photometry (AB magnitudes, via FSPS) for every galaxy in the cone, pick a frame (`SED_FRAME`: rest, observed, or both), and uncheck any of the 14 filter bands (GALEX FUV/NUV, SDSS ugriz, 2MASS JHKs, WISE W1-4 — all checked by default) you don't want. Note WISE's mid-IR flux is dominated by dust emission this pipeline doesn't model — treat those bands with that caveat in mind. Requires `pip install "sage-viewer[sed]"`.
5. **Run** — saves your edits and runs the pipeline stages in sequence, streamed to the terminal.
6. **Done** — once a run succeeds, click **Visualize lightcone** to relaunch ViSAGE directly into [Lightcone Mode](lightcone.md) on the output file, or **Run again**.

All generated build/run scripts (and the LightSAGE checkout itself) live outside the ViSAGE repository — the build/run scripts specifically under `~/.visage/` — so nothing is ever written into the third-party checkout. The lightcone output itself is written to `<cwd>/sage_outputs/lightcone/` (the `OUTDIR` variable in `run_lightcone.sh`), alongside ViSAGE's other exports.

## Parameter form

Every editable config the wizard opens — the SAGE26 `.par`, SAGEswarm's
`run_pso.sh`, or LightSAGE's `run_lightcone.sh` — is shown as a list of
labelled boxes, one per option, pre-filled with its current value, instead of
raw text. Hover a label to see its inline comment (e.g. units or valid
values) as a tooltip. Edits are folded back into the underlying file when you
click **Save & Run** — comments, quoting, and layout are all preserved; only
the values you changed are different on disk afterwards.

## Where visage looks for things

The working directory you launch from is the anchor for the entire session:

| What | Where |
|---|---|
| SAGE26 executable & source | Searched in CWD, parent of CWD, then home folder |
| `.par` files | `<SAGE26>/input/` and `<CWD>/input/` |
| Existing models | `<SAGE26>/output/`, `<CWD>/output/`, `<CWD>/sage_outputs/` |
| Screenshots / recordings / exports | `<CWD>/sage_outputs/session_<timestamp>/` |
| LightSAGE lightcone output | `<CWD>/sage_outputs/lightcone/` (editable in the run script's `OUTDIR`) |

**First-time install (no SAGE26 yet):** run `visage` from the folder where you want SAGE26 to live, then use **Clone SAGE26** in the wizard. The wizard will ask which parent directory to clone into (defaulting to your home folder), and will use that cloned directory for the rest of the session.

**Existing SAGE26:** run from the SAGE26 root and the wizard finds everything automatically.

## Step indicator

A row of chips in the header tracks progress through the wizard:

| Chip colour | Meaning |
|---|---|
| Cyan / elevated | Current step |
| Green | Completed step |
| White / outlined | Pending step |

## Rescan

The **Rescan** button (top-right of the header) re-runs the environment scan from scratch at any point — useful if you've just compiled SAGE26 (or LightSAGE) or moved files.

## Session models

The Launch-Mode dropdown (SAGE-logo button) lists every box and lightcone
opened so far this session under **Session Models** — click any entry to jump
straight back to it. See [Lightcone Mode](lightcone.md#session-models) for
details.

## Closing the wizard

The **×** button in the header closes the wizard and returns to Explore Mode. The wizard always resets cleanly when reopened.
