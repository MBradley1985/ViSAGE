# Launch Mode

Launch Mode sets up and runs SAGE26 and its two companion tools,
[LightSAGE](https://github.com/sage-home/sage-lightcone) (lightcones) and
[SAGEswarm](https://github.com/MBradley1985/SAGEswarm) (calibration), without
leaving the viewer: big buttons for each choice, a progress page for each run,
and the model opening straight in ViSAGE when it's done.

## Opening Launch Mode

```bash
cd /path/to/SAGE26      # or the folder you want SAGE26 to live in
visage
```

Open the printed URL. From inside a model, the **Launch Mode** menu (the
SAGE-logo button, top-left of the toolbar) lists **SAGE26**, **LightSAGE** and
**SAGEswarm** (each opens that tool's page) and **Setup Wizard** (the home
page), then the models opened this session.

## Home

Three picture cards, one per tool, each saying whether it's installed, and
**Load a previous model**, which lists every SAGE26 model and lightcone ViSAGE
can find (size, date, galaxies, `.par`). Click one to open it.

## A tool's page

The tool's picture and status on the left; its actions on the right:

| Button | What it does |
|---|---|
| **Run** | Opens the tool's setup page (below) |
| **Load existing** | SAGE26 models or LightSAGE lightcones as buttons; click one to open it |
| **Install** | Gets the tool ready (below) |
| **Check for update** | Compares the checkout with GitHub on the button itself; when it's behind, the button becomes **Update** |
| **Clone / Re-clone** | A fresh copy from GitHub, then Install. An existing checkout is moved aside (never deleted); a first clone goes beside your other tools |

Install and Clone run **on their button**: it spins, shows the step it's on
and the latest output line, then says how it went. If something fails, the
button turns red; click it to see the full output.

What **Install** does:

- **SAGE26:** on a first install, `first_run.sh` (makes the folders, downloads
  the mini-Millennium trees); then `make` on every core, falling back to a
  serial build when there's no MPI compiler. On Debian/Ubuntu/WSL the build is
  pointed at the system HDF5.
- **LightSAGE:** the libraries its tools need (CMake, Boost and HDF5, through
  Homebrew on macOS or apt inside WSL), the photometry packages (`fsps`,
  `astropy`) and the FSPS stellar libraries they read (into `~/.visage/fsps`
  when `SPS_HOME` isn't set; about 1 GB), then the two tools, `sage2kdtree` and
  `cli_lightcone`. SAGE itself is never built from LightSAGE: ViSAGE feeds it
  your SAGE26 output.
- **SAGEswarm:** its Python packages (`requirements.txt`). It runs SAGE26, so
  it says if SAGE26 still needs installing.

## Setting up a run

**Run** opens the tool's key choices as big buttons:

- **SAGE26:** which simulation (one card per `.par`, with its box, snapshots
  and tree type), the physics switches (described by the `.par`'s own
  comments), and **Run on**: 1 process, or 2, 4, 8 … up to your cores under
  MPI (`mpirun -np N`). MPI is offered when `mpirun` is installed and SAGE26 was
  built with it; otherwise the row says why.
- **LightSAGE:** which SAGE26 model to build from (models without saved
  star-formation histories are greyed out: they can't have photometry), how
  much sky and how deep (presets, or Custom), the surveys to observe it with,
  and the light: photometry, dust, infrared glow, emission lines, disk & bulge.
  LightSAGE only takes SAGE26 output: a DarkSAGE or DustySAGE run is refused.
- **SAGEswarm:** the observations to match (each constraint, grouped), how hard
  to search (particles × iterations, with the number of SAGE26 runs that
  means), and the free parameters from its space file.

**Name** is the run's name, and it *is* its output: SAGE26's `OutputDir` (and a
`.par` of that name when you run), LightSAGE's `OUTDIR`/`OUTFILE`, SAGEswarm's
`OUTPUT_PATH`. If the name already belongs to a model or lightcone, a warning
says running would replace it.

**All settings** shows every value in the file, grouped into sections, with a
search box; on/off values are switches and each value shows its comment from
the file. The setup page and All settings always agree: change something in
either and the other shows it.

## While it runs

The run page shows:

- the stages, an overall progress bar and a few numbers, read from the tool's
  own output (SAGE26's percentage and time left, with a tree branch growing
  as the trees are built; LightSAGE's stages and photometry steps; SAGEswarm's
  rounds as a bar and its particles as circles that fill as each one runs, and
  the best score so far);
- the tool's terminal, with what the run is making beside it: a SAGE26 box
  filling with galaxies, a lightcone filling outwards from the observer, or
  SAGEswarm's newest plot of each constraint;
- **Cancel**, and when it finishes **Open in Explore** / **Open in Lightcone
  view**, or **Change settings** if it stopped.

The terminal is never narrower than 140 columns (SAGE26 redraws its banner
and progress bar in place, up to 138 columns wide); in a narrow window its
font shrinks, and long lines are cut off at the edge rather than wrapped.

## Opening a model

Opening a model or lightcone, from any of these pages or from the Launch Mode
menu, restarts ViSAGE on it: the page shows **Opening …** and reloads itself
when it's ready.

## Where ViSAGE looks for things

The folder you launch from anchors the session:

| What | Where |
|---|---|
| SAGE26, LightSAGE, SAGEswarm checkouts | The launch folder, its parent, then your home folder |
| `.par` files | `<SAGE26>/input/` and `<launch folder>/input/` |
| Models | `<SAGE26>/output/`, `<launch folder>/output/`, `<launch folder>/sage_outputs/` |
| Lightcones | `<launch folder>/sage_outputs/` (each build in its own folder) |
| Screenshots, recordings, exports | `<launch folder>/sage_outputs/session_<timestamp>/` |
| Build and run scripts | `~/.visage/` (never inside a tool's checkout) |

## On Windows

The three tools build and run Unix programs, so on Windows every install and
run happens inside **WSL** (Windows Subsystem for Linux), automatically:

- If Linux build tools are missing, the home page says so and offers
  **Install Linux build tools** (apt inside WSL, as root, so no password).
- Checkouts stay on your Windows drive; paths are translated both ways
  (`C:\...` ↔ `/mnt/c/...`).
- If WSL isn't installed, the home page says how (`wsl --install` in an
  administrator PowerShell). Opening existing models and lightcones works
  without it.

See [Installation › Windows](../getting_started/installation.md#windows).

## Fixes ViSAGE makes to the LightSAGE tools

ViSAGE builds LightSAGE's two tools itself and carries a few fixes to them as
patches (in `visage/wizard/patches/lightsage/`). Each build applies the
patches, builds, and takes them out again, so your LightSAGE checkout stays
exactly as upstream has it and only the built tools carry the fixes. A patch
LightSAGE already includes is skipped.

| Patch | Fixes |
|---|---|
| Rotate spins with the box tiling | When a lightcone tiles copies of the box, each copy's axes are permuted. Positions and velocities were permuted but galaxy spins weren't, so each galaxy's orientation to the observer (its inclination) was wrong. Spins now get the same permutation, with the sign flip an axial vector takes when two axes swap (a mirror). |
| Sort iterator for newer compilers | Newer C++ standard libraries (Xcode / Command Line Tools 27) sort through `it[n]`, which LightSAGE's sort iterator didn't support, so the tools no longer compiled. |

## Closing

The **×** at the top right closes Launch Mode and returns to the model you
had open. **Rescan** looks for the tools again (after installing one outside
ViSAGE, say).
