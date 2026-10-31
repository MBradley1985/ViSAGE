# ViSAGE

An interactive 3D visualization package for [SAGE26](https://github.com/MBradley1985/SAGE26) semi-analytic galaxy formation outputs.

Renders dark matter haloes and SAGE galaxies together in a browser-based interactive viewer powered by [PyVista](https://pyvista.org) and [Trame](https://kitware.github.io/trame/).

## Quick start

```bash
pip install sage-viewer
```

**Explore Mode** — view existing SAGE26 results by pointing at a `.par` file:

```bash
visage --par /path/to/SAGE26/input/millennium.par
```

**Launch Mode** — install, set up and run SAGE26, LightSAGE and SAGEswarm. Run from your SAGE26 root (or the folder you want SAGE26 in) so ViSAGE finds your `.par` files and the tools automatically:

```bash
cd /path/to/SAGE26
visage
```

Open the printed URL in any browser. To launch on a remote cluster and view locally, use SSH port-forwarding:

```bash
# On the cluster
visage --par millennium.par --port 8080

# In a local terminal
ssh -L 8080:localhost:8080 user@cluster
# Then open http://localhost:8080 in your browser
```

## Command-line options

```text
--par FILE              Path to a SAGE .par file — omit (with --lightcone) to start in Launch Mode
--lightcone FILE        Path to a cli_lightcone HDF5 output file — opens the
                        full Explore UI on the lightcone instead of a SAGE box
--par-dir DIR           Directory to scan for additional .par files
                        (defaults to the parent of --par; used for the
                        multi-model dropdown)
--snap N                Initial snapshot number (default: last = z=0)
--port N                Trame server port (default: 8080)
--n-jobs N              Worker threads for parallel halo file reads
                        (default: the CPUs this process may use, minus one)
--cache-gb GB           Snapshot cache budget (default: half of RAM, or of
                        an HPC job's memory allocation; env VISAGE_CACHE_GB)
--gpu MODE              auto | high | low | system — which GPU renders
                        (default auto; env VISAGE_GPU). See below.
--perf                  Print frame timing (fps, render/encode ms, KB/frame)
                        every few seconds while the view moves
--max-halos N           Downsample ceiling per snapshot
--min-particles N       Resolved haloes have N particles (default 20): sets the mass cuts
--min-halo-mass MSUN    A fixed minimum halo mass instead
--min-stellar-mass MSUN A fixed minimum stellar mass instead
```

ViSAGE sizes itself to the machine. At startup it prints what it found,
for example `System : Windows 11 (AMD64) · 16 CPUs (15 workers) · 31.8 GB RAM (cache 15.9 GB)`,
and, after the first frame, the GPU that is actually rendering. If OpenGL has
fallen back to the CPU (Remote Desktop, a VM, a missing driver), a warning
appears in the viewer. On a Windows laptop with both integrated and discrete
graphics, `--gpu auto` sets the Windows "High performance" graphics
preference for Python so the discrete GPU renders. `high`/`low` force the
choice, and `system` leaves the OS default alone.

Galaxies have no display cap — every galaxy above the mass floor loads, since all snapshots are preloaded up front.

## Multi-model workflow

If your SAGE root looks like:

```
SAGE26/
├── input/
│   ├── millennium.par
│   ├── millennium_vanilla.par
│   └── microuchuu.par
└── output/
    ├── millennium/model_0.hdf5
    ├── millennium_vanilla/model_0.hdf5
    └── microuchuu/model_0.hdf5
```

then `visage --par input/millennium.par` discovers all three models automatically. Click the hamburger icon (top-left) → Models section to switch, or click "+ overlay" next to a compatible model to render both at once.

## Installation

### PyPI (recommended)

```bash
pip install sage-viewer
```

Requires Python ≥ 3.11. After install, `visage` is available as a command. If your shell can't find it, add the user bin directory to your PATH:

```bash
# macOS (Python 3.12 user install)
export PATH="$HOME/Library/Python/3.12/bin:$PATH"
```

Movie recording in MOV format uses `ffmpeg` from your `PATH`. On Windows, a bundled copy is installed automatically.

Synthetic photometry (SED synthesis for lightcones) is an optional extra — it pulls in FSPS + astropy, which the base install omits:

```bash
pip install "sage-viewer[sed]"
```

FSPS also needs its stellar-population data on disk, pointed at by the `SPS_HOME` environment variable (see the [python-fsps](https://github.com/dfm/python-fsps) docs). Nothing else in ViSAGE depends on it.

### From source

```bash
git clone https://github.com/MBradley1985/ViSAGE
cd ViSAGE
pip install .
```

### Windows

```powershell
py -m pip install sage-viewer
visage
```

The viewer (Explore, Lightcone, Story Mode, recording, the Console) runs
natively on Windows. The Launch Mode flows, **SAGE26**, **SAGEswarm** and
**LightSAGE**, build and run Unix C/C++ code, so on Windows ViSAGE runs
those tools inside **WSL** (Windows Subsystem for Linux) for you. Your
checkouts stay on your Windows drive (`C:\Users\you\SAGE26` is
`/mnt/c/Users/you/SAGE26` inside WSL), and the native viewer reads their
output directly. Set it up once:

1. In an **administrator** PowerShell, run `wsl --install`, then restart Windows.
2. Open the new **Ubuntu** app once and create a Linux user.
3. Start `visage`, open a flow, and click **Install Linux build tools**. This
   installs the compilers, HDF5, GSL, OpenMPI, Boost and Python inside WSL.

You can also run ViSAGE entirely inside WSL (`pip install sage-viewer` in
the Ubuntu terminal). It then behaves exactly as on Linux, and your Windows
browser opens `http://localhost:8080` as usual.

### HPC / supercomputer

A helper script is included for module-system clusters (Slurm, PBS, etc.):

```bash
# Load a Python module first (name varies by cluster)
module load python/3.12.0

# Create a venv and install ViSAGE in one step
./install_hpc.sh

# Optional: place the venv on scratch for faster I/O
./install_hpc.sh /scratch/$USER/visage-env
```

The install is editable (`pip install -e .`) so a `git pull` updates the code immediately with no reinstall. Load `ffmpeg` via your module system if you need MOV recording.

In every session:

```bash
source .venv/bin/activate
visage --par /path/to/millennium.par --port 8080
# SSH-tunnel the port to your local browser
```

## Documentation

Full documentation at [mbradley1985.github.io/ViSAGE](https://mbradley1985.github.io/ViSAGE/).

## Tabs at a glance

When multiple boxes are loaded a **box strip** appears at the bottom of the viewport. Click any box to make it active (green label). All tab controls then target that box.

| Tab | Purpose |
|---|---|
| Structure  | Layer visibility, opacity, colour-by mode, colormap (with inline colorbar); environment filter, Show info (selection card) |
| Filters    | Range sliders for halo and galaxy properties; Find presets |
| Box        | Zoom to axis-aligned sub-box — "Use Current View" populates from camera; **Draw Box** places a resizable interactive box; **Lock Box** commits it as the focus region. *In Lightcone Mode this tab becomes **Photometry**: a separate false-colour image layer built from a stack of synthetic-photometry filters (own Visible/Opacity, independent of the galaxies)* |
| Coords     | Fly to arbitrary (x, y, z) — "Use Current Position" populates from camera; **Draw Sphere** places an interactive two-handle sphere (drag centre ball to translate, drag edge ball to resize); **Lock Sphere** commits it as the focus region |
| Record     | Screenshots (PNG/JPG/TIFF) and movie recording (GIF/MOV/PNG); overlays composite into captures |
| Console    | Live xterm.js shell terminal (PTY-backed) + SAGE natural-language command mode. Multiple sessions, pop-out window |
| Library    | Browse stored screenshots / movies; double-click a row to open as a movable, resizable floating card over the viewport (multiple items open simultaneously); per-row delete button removes the file from disk immediately |

The **Focus button** (top of the right panel) is tab-aware: it focuses on the selection (galaxy, or halo and group), the coords point, or the box region.

![Launch](https://raw.githubusercontent.com/MBradley1985/ViSAGE/main/docs/images/launch.png)

### Launch Mode
- Set up and run SAGE26, LightSAGE (lightcones) and SAGEswarm (calibration) without leaving the viewer: `visage` with no `--par`/`--lightcone`, or the Launch Mode menu (SAGE-logo button, top-left of the toolbar), which opens **SAGE26**, **LightSAGE** or **SAGEswarm** directly, or the home page
- **Home:** a picture card per tool, showing whether it's installed, and **Load a previous model**, listing every SAGE26 model and lightcone found
- **Each tool's page:** Run, Load existing, Install, Check for update (turns into Update when behind) and Clone / Re-clone. Install and Clone run on their button, showing the step and latest output, then the result:
  - **SAGE26:** downloads the mini-Millennium trees on a first install, then `make` on every core (serial when there's no MPI compiler)
  - **LightSAGE:** CMake, Boost and HDF5 (Homebrew / apt in WSL), the photometry packages and FSPS stellar libraries, then *only* its `sage2kdtree` / `cli_lightcone` tools; SAGE itself is never rebuilt, since ViSAGE feeds it your SAGE26 output
  - **SAGEswarm:** its Python packages
- **Setting up a run:** the key choices as big buttons (SAGE26: simulation, physics switches, and **Run on** 1 process or several under MPI; LightSAGE: source model, sky-and-depth presets, surveys, dust/IR/lines/disk-bulge; SAGEswarm: observations to match, search effort, free parameters), a **Name** that sets the run's output (with a warning when it would replace an existing model), and **All settings**: every value of the file in sections, with a search. The two always agree
- **While it runs:** the stages, a progress bar and numbers read from the tool's output (a growing tree branch for SAGE26; rounds and particle circles for SAGEswarm), and the tool's terminal beside what it's making: a SAGE26 box filling with galaxies, a lightcone filling outwards, or SAGEswarm's latest plots. Then **Open in Explore** / **Open in Lightcone view**
- Opening any model or lightcone shows **Opening …** and reloads the page by itself when ViSAGE is ready
- **Windows:** all three tools run inside WSL automatically, with a one-click **Install Linux build tools** — see [Windows](#windows)
- Screenshots, recordings, catalogue exports and lightcones save to `sage_outputs/` in the directory you launched from; build and run scripts live in `~/.visage/`, never inside a tool's checkout

![ViSAGE](https://raw.githubusercontent.com/MBradley1985/ViSAGE/main/docs/images/hero.png)

## Features

### Rendering
- World-space gaussian splat rendering of haloes and galaxies — splats scale with camera distance and stay physically meaningful at any zoom
- **Structure** render mode: each galaxy drawn as a layered composition — cold-gas envelope (blue, sized by ColdGas) + outer envelope (green for CGM-regime sized by CGMgas, red for Hot-regime sized by HotGas)
- 27 selectable matplotlib colormaps, identical lists for halo and galaxy layers
- Live colormap, colour-by mode, opacity and visibility controls per layer
- Colour-by dropdowns are model-aware — only modes whose underlying field is present in the loaded model appear in the list; they update automatically on model switch
- Full still-quality rendering at all times — no resolution drop during camera drag or playback

![Structure mode](https://raw.githubusercontent.com/MBradley1985/ViSAGE/main/docs/images/structure_mode.png)

### Playback & camera
- Play / Pause / Stop / Reverse / Repeat transport at 0.1× – 5× speeds
- Continuous camera rotation (CW / CCW at 15° / 30° / 60° per second)
- Reset / Centre / Focus buttons
- Fly to halo, galaxy, coordinates, or sub-box (with focus mode that masks everything outside)
- **Draw Sphere** (Coords tab): place a live two-handle sphere in the viewport — drag the centre ball to translate, drag the edge ball to resize; **Lock Sphere** commits it as the active focus region
- **Draw Box** (Box tab): place a live resizable box widget — drag any face or corner handle; **Lock Box** commits it; **Clear** on both tabs cancels the widget without navigating
- Switching models always lands at z=0 of the new model; slider and snap chip update immediately
- Camera bookmarks (save, restore, delete)

### Selection & inspection
- **Double-click a galaxy** (any tab, and inside HD) to select it: a cyan ring on it and smaller rings on the rest of its FOF group (merged where they would pile up). The selection follows the galaxy through snapshots by its GalaxyIndex.
- **Selection card** (the **i** button beside Focus, or **Show info** in the Structure tab) — key properties and every field on demand, its host halo, the group's members (click to select), and Go / Isolate / HD / Gas. A **Galaxy / Halo + group** switch sets what Go and Isolate act on.
- **Browsing** — previous / next member, up to the central, hop to the nearest galaxy, back / forward history; on the card and on keys (`[` `]` `C` `N` `B` `Shift+B`)
- **Find** (Filters tab) — presets such as most massive galaxies, richest clusters, Milky Way analogues, close pairs, mergers, starbursts and quenched centrals; click a result to select it and fly there
- **HD mode** — the selected galaxy, and its whole pair, group or cluster, as detailed 3D models built from SAGE properties (arms, bars, bulges, star clusters, HII regions, dust, merger debris, tidal features, ICL, optional halo gas), ray-marched on the GPU. See the [HD Mode guide](https://mbradley1985.github.io/ViSAGE/user_guide/hd_mode/). Needs a GPU.
- **Enter to run** in every input field — Coords X/Y/Z, Box bounds, Console command, script path, screenshot/movie label all submit on Enter, equivalent to clicking the paired Go / Zoom / Run / Take Screenshot button

![Filters in action](https://raw.githubusercontent.com/MBradley1985/ViSAGE/main/docs/images/filters.gif)

### Filtering
- Halo filters: Mvir (log10), Rvir (Mpc/h), Vvir (km/s)
- Galaxy filters: stellar mass, sSFR, B/T, age, BH mass, ICS mass, type (centrals / satellites), FFB regime, CGM / Hot regime, environment class (Field / Isolated / Pairs / Groups / Clusters, via the Environment filter in the Structure tab)
- Filters are **active-only** — a slider sitting at its full-range endpoints has no effect; move it inward to filter. Every galaxy with detectable mass is visible at startup.
- Filters auto-disable when the loaded model doesn't contain the underlying field
- Reset Filters button restores defaults
- **Playback respects all scene state** — the pre-render frame cache is keyed on filter values, focus region, layer visibility/opacity/color-mode, and highlight indicator state; changing any of these and pressing Play again always produces fresh frames

![Draw Sphere](https://raw.githubusercontent.com/MBradley1985/ViSAGE/main/docs/images/draw_sphere.gif)

### Side-by-side multi-box comparison
- Load two or more SAGE models side-by-side in a single viewport with `+SBS` in the Models section of the hamburger menu
- Each box is fully independent: its own snapshot, filters, colormaps, opacity, and visibility settings
- A box strip at the bottom of the viewport shows all loaded boxes; click any box label to make it active — the entire right panel (Structure, Filters, Coords, Console, …) then controls that box
- Active box label is **green**; idle boxes are **white**
- Play, step, and the snapshot slider advance only the active box's snapshot
- Rotation is disabled in multi-box mode (all boxes share one camera; independent rotation is not supported)
- Halo Mvir colour mode is always locked to Viridis; the colormap selector is greyed out when Mvir is selected
- CLR button in the box strip resets that box to its defaults without affecting others

### Multi-model (overlays)
- Auto-scans `<sage_root>/output/` for SAGE model subfolders
- Switch the primary model from the hamburger menu (any box size)
- Overlay a second compatible model on top (same box size + snap count)
- Loading spinner during model swaps; warning snackbar for incompatible overlays

![Multi-box](https://raw.githubusercontent.com/MBradley1985/ViSAGE/main/docs/images/multibox.png)

### Output
- Screenshots in PNG / JPG / TIFF
- Movie recording in GIF / MOV (H.264, via ffmpeg) / PNG sequence
- Configurable FPS (1 – 60) and resolution (Native / 2× / 4× supersampled)
- Optional user-typed label per capture; everything saves into `sage_outputs/session_<timestamp>/` in your current working directory
- **Overlay compositing** — Galaxy Info, Group Info, console pop-out, and open Library cards are all composited into screenshots and recordings exactly as they appear on screen
- Catalogue export (CSV, HDF5, FITS, TXT) for the current filter selection, target, or box region — or, in Lightcone Mode, the whole cone (including any synthetic-photometry columns) — saves to `sage_outputs/catalogues/`

### Story Mode
- Play JSON-defined **stories** — ordered scenes of captured viewer state (snapshot, camera, layers, filters, focus) with text/media overlays — as full presentations over the live 3D view
- Scenes carry titles, headings, body text, citations, LaTeX equations (vendored KaTeX, offline), images, videos, audio, and a clickable scene-menu grid
- Camera motions per scene: orbit, snapshot sweeps through cosmic time (with pre-rendering for instant playback), and fly-throughs with optional snapshot rewind to a target redshift
- Portable stories: symbolic snapshot references (`"first"`, `"last"`, `"40%"`, `"z=1.5"`) resolve against whatever model is loaded
- Stories load from `sage_stories/` in your launch directory; a bundled **Presentation Template** provides a full talk skeleton to copy and fill in — see the [Story Mode guide](https://mbradley1985.github.io/ViSAGE/user_guide/story_mode/)

### HD Mode
- Using the galactic properties from the SAGE26 run, selecting this allows for a HD depiction of what the selected galaxies could/should/would appear.
- Within LightSAGE mode the galaxy is modified based on the photometry and dust properties calculated.
- The more galaxies selected, the more CPU and GPU usage, be warned.

![HD Mode](https://raw.githubusercontent.com/MBradley1985/ViSAGE/main/docs/images/HD_mode.png)

### Lightcone Mode
- `visage --lightcone FILE` opens a `cli_lightcone` HDF5 output in the **exact same Explore UI** as a SAGE box — same toolbar, navigation panel (every colour-by mode), info panel, and gaussian-splat rendering
- Reads every SAGE field carried in the flat lightcone file into a full galaxy snapshot, plus host haloes built from the `Type == 0` centrals
- The snapshot slider becomes a **redshift/time cut**: it only spans the snapshots actually present in the cone, and moving it removes the near (lower-redshift) side of the cone, keeping the far side — the full cone shows at the slider's maximum
- **Camera** — reset frames the cone zoomed-in, horizontal and centred, end to end; the go-to-centre button stands you at the observer (coordinate origin) looking outward along the cone
- **Photometry tab** (replaces the Box tab) — if the cone carries synthetic photometry, a separate, independent splat layer that builds a **false-colour image** from a stack of the ticked filters (named by survey, blue to red; each tinted its representative colour; mass-to-light stackable too). Own Visible/Opacity; show it with the galaxies on, off, or on its own
- **Mock images** — **Create mock image**, under **Image** in the Photometry tab, draws the sky around a galaxy as SDSS, DES, Pan-STARRS1, LSST, 2MASS, WISE, GALEX or JWST NIRCam would record it (each galaxy's disk and bulge at its size, inclination and colours; the survey's pixels, seeing and, optionally, its sky noise), saved as PNG and FITS (with WCS)
- Reach it from Launch Mode (**Open in Lightcone view** after a build, LightSAGE's **Load existing**, or **Load a previous model**), the **Session Models** list (see below), or directly via `--lightcone`

![Example lightcone](https://raw.githubusercontent.com/MBradley1985/ViSAGE/main/docs/images/lightcone.png)
![Example lightcone](https://raw.githubusercontent.com/MBradley1985/ViSAGE/main/docs/images/lightcone_spectra.png)

### Session models
- The Launch-Mode dropdown lists every box and lightcone opened so far this session under **Session Models**, with a box or telescope icon per kind and the active one marked
- Click any entry to jump straight back to it (a quick relaunch on the same port) — so loading a box after a lightcone (or vice versa) never loses track of what you had open
- Persisted in `~/.visage/session_models.json` across relaunches

### Embedded console (Console tab)
- **Terminal mode** — a live xterm.js terminal backed by a real PTY (`$SHELL -l` on macOS/Linux, PowerShell on Windows); full ANSI colour, cursor control, and interactive programs (`vim`, `top`, `htop`, `less`) all work
- **SAGE command mode** — natural-language SAGE commands (`show only clusters`, `go to halo 42`, `snap 30`, `screenshot`, …); switch via the **SAGE Cmds** button, `terminal` returns to the shell
- **Multiple sessions** with a `+` button — each console has its own PTY process and command history
- **Pop-out** floats a movable / resizable console card over the viewport so you can keep typing while watching the render

### Self-contained metadata
- Cosmology (h, Ω_m, Ω_Λ), box size, and snapshot redshifts are read directly from `model_0.hdf5`'s `Header/Simulation`
- The `.par` file is now only needed for tree-file paths

## Supported simulations

| Simulation | Box size | Snapshots | Tree format |
|---|---|---|---|
| miniMillennium | 62.5 Mpc/h | 64 | lhalo_binary |
| microUchuu | 96 Mpc/h | 50 | lhalo_binary |

Both supported automatically — point at the `.par` file and ViSAGE figures out the rest from the HDF5.

## Citation

If you use ViSAGE in published work, please cite it using [CITATION.cff](CITATION.cff), and the models it runs:

- **SAGE26:** Bradley M., Croton D. J., Mostoghiu Paun R. A., Dutta Chowdhury D., Willingham J. 2026, *SAGE26 Paper I: Modelling the baryon cycle from cosmic dawn to the present day*, [arXiv:2610.09564](https://arxiv.org/abs/2610.09564)
- **SAGE:** Croton D. J. et al. 2016, *ApJS* 222, 22, [doi:10.3847/0067-0049/222/2/22](https://doi.org/10.3847/0067-0049/222/2/22)

LightSAGE's synthetic photometry, spectra and mock images build on the following. The full list is in [Lightcone Photometry](docs/physics/photometry.md#references).

- **Stellar populations (FSPS):** Conroy C., Gunn J. E., White M. 2009, *ApJ* 699, 486; Conroy C., Gunn J. E. 2010, *ApJ* 712, 833
- **Dust mass:** Triani D. P. et al. 2020, *MNRAS* 493, 2490 (Dusty SAGE)
- **Dust attenuation:** Charlot S., Fall S. M. 2000, *ApJ* 539, 718; Trayford J. W. et al. 2020, *MNRAS* 491, 3937; Lagos C. d. P. et al. 2019, *MNRAS* 489, 4196 (Shark); Triani D. P. et al. 2023, *MNRAS* 519, 2500
- **Dust emission:** Draine B. T., Li A. 2007, *ApJ* 657, 810
- **Emission lines:** Gutkin J., Charlot S., Bruzual G. 2016, *MNRAS* 462, 1757; Feltre A., Charlot S., Gutkin J. 2016, *MNRAS* 456, 3354; Hirschmann M. et al. 2017, *MNRAS* 472, 2468
- **AGN light curves:** Hopkins P. F., Hernquist L. 2009, *ApJ* 698, 1550
- **Intergalactic absorption:** Madau P. 1995, *ApJ* 441, 18
- **Mock spectroscopy:** Smee S. A. et al. 2013, *AJ* 146, 32; Balogh M. L. et al. 1999, *ApJ* 527, 54
- **Group finding:** Van Kempen W. et al. 2024, arXiv:2410.15548; Van Kempen W. et al. 2025, arXiv:2508.12556; Lambert T. S. et al. 2020, *MNRAS* 497, 2954; Huchra J. P., Geller M. J. 1982, *ApJ* 257, 423; Robotham A. S. G. et al. 2011, *MNRAS* 416, 2640; Beers T. C., Flynn K., Gebhardt K. 1990, *AJ* 100, 32; Blanton M. R. et al. 2003, *ApJ* 592, 819
- **Survey catalogues:** Strauss M. A. et al. 2002, *AJ* 124, 1810; Baldry I. K. et al. 2018, *MNRAS* 474, 3875
- **Mock image display and PSF:** Lupton R. et al. 2004, *PASP* 116, 133; Trujillo I. et al. 2001, *MNRAS* 328, 977
- **Mock image noise:** Nguyen H. T. et al. 2010, *A&A* 518, L5 (SPIRE confusion); Bagley M. B. et al. 2023, *ApJL* 946, L12 (CEERS depths); Abbott T. M. C. et al. 2018, *ApJS* 239, 18 (DES sky); Leinert C. et al. 1998, *A&AS* 127, 1 (zodiacal light)
- **Mock image saturation:** Stoughton C. et al. 2002, *AJ* 123, 485; Ivezić Ž. et al. 2019, *ApJ* 873, 111
- **Mock image stars:** Skrutskie M. F. et al. 2006, *AJ* 131, 1163 (2MASS); Almeida A. et al. 2023, *ApJS* 267, 44 (SDSS DR18); Jester S. et al. 2005, *AJ* 130, 873; Ballesteros F. J. 2012, *EPL* 97, 34008

## License

MIT — see [LICENSE](LICENSE).
