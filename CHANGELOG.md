# Changelog

All notable changes to ViSAGE are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

- **Catalogue export supports lightcones.** Export now reads a flat
  `cli_lightcone` file directly (no `Snap_N` group) — so its columns,
  including any synthetic-photometry `mag_rest_*` / `mag_obs_*` datasets,
  come through — and a **Whole Lightcone** scope (the default in Lightcone
  Mode) exports every galaxy in the cone.

### Changed

- **The Structure panel's Synthetic Photometry (SED) section is now fully
  independent of the GALAXIES section.** It has its own colormap and
  colourbar state, so changing one section no longer mirrors into the
  other; both still colour the single galaxy layer, with whichever you
  touched last driving the render. The SED section also gains a **Visible**
  checkbox and loads with a band already selected and applied (instead of a
  blank dropdown), mirroring the other Structure sections.
- **Lightcone camera framing.** Reset / default view now zooms in on the
  cone (filling the viewport width rather than fitting the bounding sphere
  to the shorter axis, which left it a tiny sliver), kept horizontal and
  centred end to end. The **go-to-centre** button in Lightcone Mode now
  stands at the observer (coordinate origin) looking outward along the
  cone, sky spread horizontally, instead of using box-centre math.
- **Colourbar limit labels lightened** in the Structure panel (`#6b7280` →
  `#a3adbb`) so the min/max values are legible.
- **Lightcone flythrough — gentler first zoom.** The first move (from the
  whole-cone framing into the nearest group) is now distance-scaled to fly
  at the same linear speed as Box Mode's approach, instead of swooping the
  much larger distance in the same fixed time.

### Fixed

- **SED colormaps sometimes didn't apply.** Because the SED colormap shared
  state with the GALAXIES section, switching bands could reset a colormap
  you'd just picked; with the sections decoupled, SED colormap changes
  always take effect.

## [2.1.3] — 2026-07-29

### Fixed

- **Session Models could show entries pointing at files that no longer
  exist**, with no way to tell why or where they came from — every launch
  ever recorded a path into `~/.visage/session_models.json` and nothing
  ever pruned it. Loading the registry now drops any entry whose file is
  gone (and persists that cleanup); the dropdown also shows each entry's
  containing folder as its subtitle (full path on hover), so two entries
  with the same name/kind — e.g. two lightcones — are distinguishable.

### Fixed

- **SED Structure-panel section was showing colour indices/mass-to-light as
  dropdown options that silently did nothing, and the "Colour by band"
  picker displayed the general dropdown's current mode (e.g. "structure")
  as if it were selected.** Both were wiring bugs from the previous
  release: the colour-index/mass-to-light list-building helper was written
  but never actually called, and the picker shared its `v_model` with the
  general "Colour by" dropdown instead of its own dedicated state. The
  picker now has its own state (clearing back to a placeholder whenever a
  non-SED mode is active elsewhere), and colour-index/M\*/L modes get their
  intended default colormap (diverging `coolwarm` / mass-like `cividis`)
  and computed colorbar range, not the generic fallback.

- **A `run_lightcone.sh` saved by an older ViSAGE version never gained new
  wizard features.** Since a saved script was loaded verbatim, one saved
  before the per-band checkbox refactor kept its old single `SED_BANDS`
  text field forever — the new 14-checkbox grid simply never appeared,
  even after upgrading ViSAGE. Loading a script now detects an outdated
  structure and regenerates it from the current template, carrying every
  customizable value forward (paths, ra/dec/z, SED settings) and mapping
  the old space-separated band list onto the matching new checkboxes.

### Changed

- **All 14 SED filter-band checkboxes are checked by default** in the
  LightSAGE run script (previously WISE W1-4 defaulted off); uncheck any
  you don't want. `visage.sed.filters.DEFAULT_BANDS` (used by the
  standalone `visage-sed` CLI) matches. WISE's mid-IR flux is still
  dominated by dust emission this pipeline doesn't model — that caveat
  applies regardless of the checkbox default.

## [2.1.1] — 2026-07-29

### Fixed

- **Stale `LIGHTCONE_DIR` in a saved `run_lightcone.sh`.** A previously-saved
  run script could reference a LightSAGE checkout that no longer exists —
  moved, deleted, or cloned under an older ViSAGE version's folder-naming
  convention (`sage-lightcone` vs `LightSAGE`) — failing stage 1 outright
  with "No such file or directory". `LIGHTCONE_DIR` is now always resynced
  to whatever the current session's scan actually found and verified when
  loading a saved script, while every genuine user preference in it (ra/dec/z
  ranges, output dir, SED settings) is left untouched.

## [2.1.0] — 2026-07-29

### Added

- **LightSAGE lightcone extraction flow in the Launch wizard.** A third guided
  flow, alongside SAGE26 setup and SAGEswarm: clone LightSAGE (upstream repo
  `sage-home/sage-lightcone`) → build *only* the `sage2kdtree` / `cli_lightcone`
  tools (SAGE itself is never rebuilt — ViSAGE feeds in your existing SAGE26
  output) → configure the two-stage pipeline → run it, streamed to the wizard
  terminal → **Visualize lightcone** launches straight into Lightcone Mode on
  the result. The macOS build step auto-detects an Apple-clang/SDK mismatch
  (Xcode's newest SDK ships libc++ headers newer LLVMs don't support) and
  falls back to a compatible installed SDK. All generated build/run scripts
  live under `~/.visage/`, never inside the third-party checkout. Reachable
  from the wizard menu ("LightSAGE") and a new toolbar button beside the
  SAGEswarm one. The produced lightcone is written to `<cwd>/sage_outputs/
  lightcone/` — ViSAGE's standard output folder, alongside screenshots,
  recordings, and exported catalogues.

- **Synthetic photometry (SED) for LightSAGE lightcones.** An optional third
  pipeline stage forward-models broadband AB magnitudes for every lightcone
  galaxy from its star-formation history, using
  [python-fsps](https://github.com/dfm/python-fsps) (`pip install
  "sage-viewer[sed]"`). Enabled via **SED_ENABLED** in the LightSAGE
  run-script parameter form, with a **SED_FRAME** choice (rest / observed /
  both) and a 14-checkbox, 2-column grid of individual filter bands (GALEX
  FUV/NUV, SDSS ugriz, 2MASS JHKs, WISE W1-4 — UV/optical/NIR checked by
  default, WISE off by default since its mid-IR flux needs a dust model this
  pipeline doesn't have). Computes rest-frame (10 pc), observed-frame
  (luminosity-distance, K-corrected), or both, using the simulation's own
  cosmology rather than an assumed one. Results are written back into the
  lightcone HDF5 file as `mag_rest_<band>` / `mag_obs_<band>` datasets. When
  present, a new **Synthetic Photometry (SED)** section appears in the
  Structure panel (LightSAGE mode only) with a dedicated colour-by-band
  dropdown — every raw band, every derived colour index (e.g. g-r) between
  adjacent/broadest bands in a frame, and mass-to-light ratio for bands with
  a known solar magnitude — via the same colormap mechanism as every other
  property, with mode-appropriate default colormaps (diverging for colour
  indices, frame-distinct sequential for raw bands).
- **Wizard checkbox parameters render in a 2-column grid.** Any
  `*_ENABLED`-suffixed parameter-form field is now laid out half-width so
  consecutive checkboxes (like the new SED band picks) wrap into two columns
  instead of one long vertical list; text fields are unaffected (still
  full-width, one per row).

- **Lightcone Mode — the full Explore UI on a lightcone.** `visage --lightcone
  FILE` opens a `cli_lightcone` HDF5 output in the exact same toolbar,
  navigation panel, and info panel as a SAGE box — same gaussian-splat
  rendering, colour-by modes, and colormaps. Reads every SAGE field carried in
  the flat lightcone file into a full galaxy snapshot plus host haloes built
  from the `Type == 0` centrals. The snapshot slider becomes a redshift/time
  cut spanning only the snapshots present in the cone: moving it removes the
  near (lower-redshift) side, keeping the far side, with the full cone shown
  at the slider's maximum. Camera reset frames the cone horizontally, centred
  in the viewport.

- **Wizard parameter form.** Every editable config the wizard opens (SAGE26
  `.par`, SAGEswarm `run_pso.sh`, LightSAGE `run_lightcone.sh`) is now shown as
  a list of labelled boxes — one per option, pre-filled with its current value
  — instead of a raw text editor. Edits fold back into the file on Save & Run,
  preserving comments, quoting, and layout.

- **Session models.** The Launch-Mode dropdown now lists every box and
  lightcone opened so far in the session under **Session Models**, and
  clicking one jumps straight back to it. Persisted across relaunches in
  `~/.visage/session_models.json`, so switching from a lightcone to a box (or
  back) never loses track of what was open.

### Changed

- **No galaxy display cap.** Every galaxy passing the mass floor now loads —
  there's no benefit to downsampling since all snapshots are preloaded up
  front. `--max-galaxies` is removed from the CLI.

- **Flythrough tours groups and clusters continuously.** In both Explore and
  Lightcone Mode, flythrough no longer ends by zooming out to orbit the whole
  box/cone forever — it now keeps moving from one group/cluster to the next
  indefinitely. Reset Camera in Lightcone Mode now correctly reframes the
  cone (`Scene.is_lightcone`-aware) instead of using box-at-the-origin math.

- **Launch-wizard menu cleanup.** The hamburger dropdown's "EXPLORE MODE"
  heading is removed (the menu now serves both Explore and Lightcone Mode).
  "Start Fresh" moved to the end of the setup-choice list, and both
  "Switch to SAGE26 setup" buttons (in the SAGEswarm and LightSAGE flows) are
  now labelled "Back".

### Removed

- **FoF (friends-of-friends) satellite→central link lines.** The gold link
  overlay, its toggle button, and the underlying `fof_segments` data have been
  removed entirely. The separate FOF-*group* inspection features (Group Info
  panel, Highlight Members, environment classification) are unaffected.

---

## [2.0.0] — 2026-07-24

### Added

- **SAGEswarm calibration flow in the Launch wizard.** A new guided flow mirrors
  the SAGE26 setup path — clone SAGEswarm → `pip install -r requirements.txt` →
  pick the compiled `./sage` binary + `.par` → set constraints (`-x`) + output
  dir (`-o`) → run `python main.py …`, streamed to the wizard terminal. Reachable
  from the wizard menu ("SAGEswarm") and from a new toolbar button beside the
  Launch Mode button. The header step chips are now flow-aware (`wiz_steps`
  state var).
- **Live PSO plot gallery.** While a SAGEswarm run is in progress, ViSAGE watches
  the SAGEswarm main folder (the run's cwd) for `*.png` diagnostics and shows
  them in a dedicated, right-docked gallery panel that refreshes as plots appear
  or change (mtime-diffed, base64-inlined; server-side timer, no client polling).

### Changed

- **Rebrand: SAGE-Viewer is now ViSAGE.** The import package `sage_viewer`
  is renamed to `visage` and the CLI command `sage-viewer` becomes `visage`.
  GitHub URLs point to `MBradley1985/ViSAGE`. The PyPI distribution stays
  **`sage-viewer`** (`pip install sage-viewer`) — `visage`/`vi-sage` are blocked
  on PyPI by the existing `visage` project. This is a breaking change for anyone
  importing `sage_viewer` or invoking the old `sage-viewer` command.

- **Galaxy splats scale with the subhalo virial radius.** All galaxy layers
  (CGM/Hot outer envelope, cold-gas envelope, focus-only disk/bulge, and the
  Colour-by halo) are now sized by the galaxy's `Rvir` (read from the SAGE
  output; analytic Δ=200 fallback from Mvir where missing) instead of a fixed
  stellar-mass mapping. Most galaxies render tighter and less diffuse, while
  massive cluster centrals gain their true extent.

---

## [1.3.0] — 2026-07-17

### Added

#### Story Mode — presentation playback over the live 3D view

A new **Story Mode** button (next to Fly-through) opens a dropdown of
*stories* — JSON files defining an ordered set of *scenes*, each a fully
captured viewer state (snapshot, camera, layer/filter/environment state,
focus) plus overlays and an optional camera motion — played back like slides
with Previous / Play / Pause / Next in a bottom HUD.

- **Discovery.** Stories load from `sage_stories/` in the launch directory
  (user stories, local-only) plus the examples bundled with the package
  (`sage_viewer/examples/`); a local story overrides a bundled one with the
  same title. Two examples ship: **Example Tour** (minimal) and
  **Presentation Template** (a full talk skeleton to copy and fill in).
- **Portable scenes.** Snapshots may be symbolic — `"first"`, `"last"`,
  `"40%"`, or a redshift like `"z=1.5"` — resolved against whatever model is
  loaded, and `camera: "box"` frames the box regardless of box size, so
  stories carry across outputs.
- **Motion.** Scenes can be `still`, `orbit`, `snapshot_sweep` (animate
  through cosmic time, with optional looping and pre-rendering during story
  load for instant playback), or `flythrough` (tour the massive structures;
  optional `rewind_to` plays a cached snapshot rewind back to a target
  redshift; `targets` can select galaxies instead of haloes; `style:
  "normal"` gives the calmer toolbar-style tour).
- **Overlays.** Titles, headings, body text, citations, LaTeX equations
  (vendored KaTeX under `static/katex/` — no network needed), images, videos,
  audio, and a clickable `scene_menu` grid of every scene. Overlays are
  authored on a fixed virtual stage that scales uniformly to fit any window,
  and media is served from `sage_viewer/static/` at `/sage_static/`.
- **Playback behaviour.** Story-level `autoplay` starts playback on entry;
  per-scene `hold` waits for Next instead of auto-advancing; scene changes
  are smoothed with a freeze-frame crossfade; per-scene `theme` and
  `chrome.hide_panel` give full-bleed presentation chrome. Scenes can declare
  a `models` layout (`primary` + `adjacent`); the pre-story layout, camera,
  state, and theme are restored on exit.
- **Sandbox preload.** Entering a story warms the snapshot cache for every
  snapshot the story references before the first scene renders.
- **Thumbnails.** A "Capture thumbnails" action screenshots every scene for
  the scene-menu grid.
- Camera moves reuse the shared `scene/camera_motion.py` helpers, which the
  Fly-through now also uses. Authoring guide: `docs/user_guide/story_mode.md`;
  design notes: `docs/project/story_mode_design.md`.

#### Library panel

- The Library panel sorts entries by file type with dividers, and supports
  multiple `sage_library` folders.

### Changed

- User stories in `sage_stories/` are no longer tracked in the repository —
  they stay local to the machine. Stories that should ship with the package
  belong in `sage_viewer/examples/`.
- The Story Mode HUD no longer shows a close cross, preventing accidental
  exits mid-presentation.

---

## [1.2.1] — 2026-06-25

> **Note:** the `1.2.0` artifact on PyPI was built from the wrong commit (the
> release tag pointed at a pre-release merge) and is missing the changes below.
> `1.2.1` is the first complete 1.2.x release. The `1.2.0` PyPI release has been
> yanked.

The following changes were intended for 1.2.0 and ship in 1.2.1:

### Changed

#### Pop-outs (terminal + library) resize freely, with a fullscreen toggle

The floating pop-out cards (console / terminal pop-out and library media items) could only
be shrunk, and growth was capped by `max-width` / `max-height` limits — the terminal hit a
~60% width wall and library cards couldn't widen past 540px or grow their media past `60vh`.

- **Removed the size caps.** Both card types are now `resize:both` with only small
  `min-width` / `min-height` floors, so they can be dragged to any size up to the viewport.
- **Library cards are flex columns** whose media (`<img>` / `<video>`) scales with
  `object-fit:contain` to fill the resized card, vertically as well as horizontally.
- **New fullscreen button** (`mdi-fullscreen`, beside the close button on each pop-out)
  toggles a `sage-popout-max` class that pins the card to fill the VTK render area; the glyph
  flips to `mdi-fullscreen-exit` and clicking again restores the previous size / position.
  Handled client-side in `sage_viewer.js` with the CSS in `sage_theme.css`.
- **Galaxy / Group info panels stay fixed-size but no longer squish in recordings.** The
  recording compositor (`_draw_info_panel`) drew labels left-aligned and values right-aligned
  at a fixed width, so long rows collided. It now measures each row and sizes the card to the
  widest `label + gap + value`, capped to the frame, so every field stays legible.
- **Static assets are cache-busted** (`?v=<mtime>` on `sage_viewer.js` / `sage_theme.css`)
  so client-side changes take effect on server restart instead of replaying a stale cached
  copy — this is why the fullscreen toggle initially appeared to do nothing.

#### Switching models now carries over the current view settings

Previously, switching the primary model (Models menu) reset the new model to its defaults:
snapshot jumped to z=0 and all filters, structure / colour modes, colormaps, opacities and
layer visibility reverted to factory values.  Now the full UI state transfers to the model
you switch to, and the settings apply to that model:

- **Filters, structure, colour modes, colormaps, opacities, layer visibility** are captured
  from the outgoing model and re-applied to the new one via the existing per-box profile
  machinery (`save_profile` / `load_profile`), with `state.dirty(*BOX_PROFILE_KEYS)` forcing
  every change handler to re-run against the new primary's layers.
- **Redshift (not raw snapshot index) is preserved.**  The outgoing model's current redshift
  is mapped onto the new model's snapshot list via `SnapshotTable.z_to_snap()` (closest
  match, clamped to range).  Models that share a snapshot list land on the identical snap;
  models with different lists (e.g. miniMillennium 64 snaps ↔ microUchuu 50 snaps) land on
  the snapshot closest in cosmic time rather than the same slider position.
- The new model's stored side-by-side profile (`_profiles[name]`) is updated to the carried
  state so a later Side-by-Side activation restores the same view.

### Fixed

#### Console commands — environment / type filters now do what they say

- **"show only clusters" (or any single class) now turns every other class off**,
  including pairs. Previously the "show only …" handler never touched the pairs
  flag, so pairs stayed visible.
- **"pair(s)" is its own class.** The parser mapped pairs into the isolated
  bucket, so "show only pairs" actually showed isolated. It now drives
  `env_show_pairs` correctly.
- **"show only centrals" / "show centrals" work.** A greedy "show only …" regex
  swallowed centrals/satellites (→ "unknown environment class"), and plain
  "show centrals" wasn't matched at all despite being documented. Both are fixed.

#### Terminal pop-out re-fits when resized

Resizing (or maximising) the console terminal pop-out grew the card but left the
xterm at its original size, so the terminal filled only part of the window. The
pop-out now attaches a `ResizeObserver` that calls the xterm `FitAddon` on every
resize (mirroring the wizard terminal), so the terminal always fills the card.

#### Recording — playback smoothness (root-cause investigation, two-session fix)

This section documents a chain of bugs that were introduced and resolved over two sessions.
The full causal chain is recorded here so it is not repeated.

**Stage 1 — original symptom:** Recording during snapshot playback was choppy because
`_record_loop` captured the pre-rendered overlay JPEGs and duplicated each 3 fps frame to
fill the 30 fps output.  Fix: dedicated VTK capture path reads directly from the render
window via `_vtk_to_pil()`.

**Stage 2 — double-play regression:** After the Stage 1 fix, recordings played through the
snapshot sequence twice when `is_repeat` was enabled.  Root cause: `_record_loop` followed
`state.snap_num`, which `_image_playback` loops indefinitely on repeat.  Fix: introduced
`_pb_order` — a one-pass list built from the starting snapshot to the last snapshot — and
`_pb_done` flag that stops capture after the list is exhausted.

**Stage 3 — live-recording slowdown:** With a 30 fps recording active, moving the camera on
a single snapshot (no playback) became sluggish.  Root cause: `_vtk_to_pil()` calls
`rw.SetOffScreenRendering(1)` + `rw.Render()` every recording tick, blocking the asyncio
event loop at 30 Hz and competing with interactive rendering.  Fix: added
`_vtk_to_pil_passive()`, which reads the last completed framebuffer via
`vtkWindowToImageFilter` with `ShouldRerenderOff()` / `ReadFrontBufferOff()` — no extra
`Render()` call.  Live recording with no rotation now uses the passive path; rotation and
snap changes still use `_vtk_to_pil()`.

**Stage 4 — rotation double-step:** Both `_rotate_loop` (toolbar.py, 12 Hz) and
`_record_loop` applied a camera rotation per tick.  Result: rotation rate doubled during
recording.  Fix: `_rotate_loop` checks `state.recording_active` at each tick and skips both
the rotation step and the `_push()` call when True.  The recording loop owns all camera
movement while a recording is active; `_rotate_loop` resumes ownership when recording stops.

**Stage 5 — playback smoothness regression (this session):** After Stage 2–4, playback
recordings were choppy again at any FPS.  Root cause had two independent components:

- *Pre-render phase interference:* `playback_active=True` is set by `_render_frames()` as
  soon as the first frame is pre-rendered, which is well before `_image_playback()` starts.
  Because `_record_loop` started its `_pb_order` pass the moment it saw
  `playback_active=True`, `_pb_idx` advanced through 10–30 snaps during the pre-render
  phase (several seconds at 30 fps).  When `_image_playback` finally started, recording
  was already deep into the sequence and the camera angles were mismatched (pre-render
  restores the camera to its starting position at the end; recording had already baked in
  extra rotation from the pre-render window).

- *PIL caching eliminated VTK temporal variation:* The Stage 3 optimisation cached the raw
  PIL image for frames where neither snap nor rotation changed (up to 9 out of every 10
  frames at 1× speed without rotation).  VTK's MSAA jitter produces subtly different renders
  on successive `Render()` calls for the same scene; caching the PIL bypassed this and
  produced runs of byte-identical frames that the human eye perceives as harder / choppier
  than renders with natural inter-frame variation.

  **Final fix:** Replaced `_pb_order` with overlay-driven `state.snap_num` tracking plus a
  `prerender_busy` guard that holds capture until `_image_playback()` is actually running.
  Removed all PIL caching in the playback path; every recording frame now calls
  `_vtk_to_pil()` (force render).  One-pass detection uses end-snap rollover: when
  `state.snap_num` reaches `_pb_end_snap` the `_pb_at_end` flag is set; when `snap_num`
  subsequently changes away from the end snap (repeat wrap-around), `_pb_done` is set and
  capture stops.  `is_repeat=False` (default) still terminates naturally when
  `playback_active` goes False.

**Key invariant for future work:** `playback_active=True` does NOT mean `_image_playback()`
is running — it is also True during `_render_frames()` pre-render.  Always gate playback
recording on `prerender_busy=False`.

#### Recording — reset camera not showing all structure

`on_reset()` called `scene.camera.focus_on_boxes()` then `_sync_fof_layer()`, which
shows/hides FoF-link actors.  `scene.plotter.renderer.ResetCameraClippingRange()` was called
before the visibility change, so near/far clipping planes were computed against the wrong
actor set and some geometry was clipped out of view.  Fix: moved
`ResetCameraClippingRange()` to after `_sync_fof_layer()`.

#### Recording — galaxy/group info card absent from output frames

The Galaxy Information and Group Information overlay cards were being composited during
screenshots but not during recording.  Root cause: `_composite_overlays()` was accidentally
dropped from `_save_frame()` during a `_record_loop` refactor.  Fix: re-added
`_composite_overlays(raw).save(...)` as the final step of `_save_frame()` so every captured
frame, regardless of recording mode, has the same overlay compositing as a screenshot.

Note: highlight markers (Highlight Galaxy / Highlight Members) are baked into the
pre-rendered frames via `_render_frames()` and are therefore always present in recordings.
Info cards are composited separately from current `state` at capture time.

#### Launch Mode terminal — persistent 1-row sliver (root-cause investigation)

Three successive fixes were required before the sliver was eliminated.  The full history is
recorded here to avoid re-treading the same ground.

**Attempt 1 — height guard:** `_initWizTerm()` polled until `container.offsetWidth > 0` but
did not check height.  In the VCard's `display:flex;flex-direction:column` layout, height
resolves after width, so the poll could pass with `offsetHeight=0`.  `fitAddon.fit()` then
called `getComputedStyle(container).height` → "0px" → 0 rows → 1-row sliver.
Fix: added `container.offsetHeight < 50` to the poll condition.

**Attempt 2 — requestAnimationFrame:** Even with the height guard passing (container had a
real height), the sliver reappeared after server hot-restarts.  Root cause: `fitAddon.fit()`
was called synchronously after `term.open()`, before xterm.js had completed its first
browser paint cycle and measured character cell dimensions (`actualCellHeight` was 0).
`fitAddon.proposeDimensions()` returns `undefined` when cell height is 0; `fit()` silently
no-ops; the terminal keeps its default 1-row height.  Fix: moved the first `fit()` call into
a `requestAnimationFrame` callback (after the initial paint) with 150 ms and 500 ms deferred
re-fits as insurance.

**Attempt 3 — CSS grid (final fix):** The sliver persisted through Attempt 2 because the
root cause was not timing but layout: `display:flex;flex-direction:column` with `flex:1` on
the terminal div does not always produce a pixel height readable by `getComputedStyle()` at
the moment xterm.js needs it — the browser may report `height:auto` for flex children under
certain conditions.  `fitAddon.proposeDimensions()` calls `parseInt(height)` on that value,
which returns `NaN`, causing `fit()` to bail silently.

  **Final fix:** Changed the VCard from `display:flex;flex-direction:column` to
  `display:grid;grid-template-rows:1fr auto`.  The terminal div occupies the `1fr` row and
  the action bar occupies the `auto` row.  CSS grid always resolves grid track sizes to
  explicit pixel values before layout completes — `getComputedStyle(terminal).height` is
  always a number, never `"auto"`.  `fitAddon.fit()` reliably reads the correct height
  regardless of when it is called.  The `offsetHeight < 50` poll guard and
  `requestAnimationFrame` deferral are retained as belt-and-suspenders.

  **Rule for future layout changes in the Launch Mode card:** the terminal container
  (`sage-wiz-pty`) must always sit in a CSS context that resolves its height to an explicit
  pixel value — grid `1fr`, absolute with known `top`/`bottom`, or an explicit `height:`.
  Do not use `flex:1;min-height:0` as the sole height source for an xterm.js container.

#### Recording — finalization silently abandoned after stop

Stopping a recording produced a frames folder full of images but no output file (GIF / MOV /
PNG sequence).  Root cause: the finalization daemon thread (`_do_finalize`) had no top-level
exception handler.  Any error inside `_finalize_movie` — including the completely unguarded
`_expand_with_crossfade` call that expands playback snap files into the crossfaded frame
sequence — would kill the thread silently, leaving `state.last_movie` stuck at `"Encoding…"`
and the frames folder on disk with no assembled output.

Fix: wrapped the `_finalize_movie` call in `_do_finalize` with a `try/except` so any
failure is reported in the Record tab's "Last:" label.  Also wrapped the
`_expand_with_crossfade` call inside `_finalize_movie` with its own `try/except` so errors
from that stage surface as a readable error string rather than an uncaught exception.

#### Coords / Box tabs — Clear button now clears indicator and undoes focus

The **Clear** button in the Coords and Box tabs previously only appeared while a Draw Sphere
or Draw Box widget was actively being placed, and only removed the interactive handles — it
did not clear the grey wireframe indicator left by the Zoom operation, and did not undo the
focus region.

Fix:
- `on_clear_draw_sphere` / `on_clear_draw_box` now also call
  `scene.camera._clear_indicator()`, `scene.clear_focus()`, `state.focus_active = False`,
  and `_sync_fof_layer()`, fully reversing a Zoom + Focus action in one click.
- The Clear button visibility condition changed from `draw_sphere_active` /
  `draw_box_active` to `draw_sphere_active || focus_active` (and equivalent for box), so the
  button appears as soon as a zoom is committed — not only during active drawing.

#### Coords / Box — Reset Camera left zoom indicator wireframe on screen

Pressing **Reset Camera** after zooming to a sphere or box region left the grey wireframe
indicator actor on screen.  Root cause: `on_reset` called `_clear_draw_widgets()` (which
removes the interactive cyan draw handles) but never called
`scene.camera._clear_indicator()`, which is the separate actor placed by `zoom_to_radius()`
/ `zoom_to_box()`.  Fix: one `scene.camera._clear_indicator()` call added to `on_reset`
immediately after `_clear_draw_widgets()`.

#### Library — GIF animations started mid-way instead of from frame 0

Opening a GIF in the Library viewer showed the animation already several frames in rather
than starting from the beginning.  Root cause: the browser starts decoding and playing a GIF
as soon as the `<img>` src attribute is set, but the Vue render cycle and DOM compositing
(backdrop-filter, elevation shadow) mean the card is not visible to the user until 1–2
animation frames later.  For a 10 fps GIF, one frame is 100 ms — already past the start.

Fix: added a `MutationObserver` in `sage_viewer.js` that watches for new `<img>` elements
inside `.sage-popout` cards.  When a GIF `<img>` is detected, the observer waits two
`requestAnimationFrame` callbacks (allowing the card to be painted), then synchronously
resets `img.src = ''` followed by `img.src = originalSrc` in the same JavaScript event.
Both assignments are synchronous so no blank frame is visible; the GIF animation restarts
from frame 0 exactly when the card becomes visible to the user.

---

## [1.0.9] — 2026-06-22

### Fixed

- GIF recordings no longer show visible contour lines around gaussian splat points — switched from `imageio` (no dithering) to PIL's native GIF writer with Floyd-Steinberg dithering, which distributes colour quantisation error across neighbouring pixels and produces smooth gradients instead of hard bands

---

## [1.0.8] — 2026-06-22

### Added

- **Galaxy Info and Group Info panels now appear in screenshots and recordings** — the info card is composited as a PIL overlay (matching its on-screen position at top-right) whenever it is visible at capture time, same technique already used for the console pop-out and library cards
- **Highlight actors (Highlight Galaxy / Highlight Members) now appear in playback recordings** — the pre-rendered frame cache is invalidated whenever the indicator state changes, so pressing Play after adding highlights always re-renders with them included

### Fixed

- Screenshots taken while **not** in playback no longer use a stale pre-rendered JPEG from a previous playback session; they always capture the live VTK render window

---

## [1.0.7] — 2026-06-22

### Fixed

- Library tab now scans `sage_library/` and `sage_outputs/` relative to the **working directory** instead of the package install location — items are found correctly when installed via `pip`
- `sage_library/` folder is created in the working directory on startup (alongside `sage_outputs/`)
- `./sage-viewer` launcher now finds whichever Python version has `trame` installed, instead of assuming the shell's default `python3` — fixes failures on macOS where multiple Python versions coexist

---

## [1.0.6] — 2026-06-22

### Fixed

- Screenshots, recordings, GIFs, and catalogue exports now save to a `sage_outputs/` folder in the **current working directory** rather than inside the Python package installation (a `site-packages` subfolder), which made them inaccessible when installed via `pip`
- `.par` template no longer contains hardcoded personal paths — `OutputDir`, `SimulationDir`, and `FileWithSnapList` are now filled in dynamically from the detected or cloned SAGE26 directory
- README: replaced 47 MB and 13 MB embedded GIFs (which overran PyPI's image proxy) with text links to the animated demos on GitHub

### Added

- Launch Mode wizard: **Clone SAGE26** step now prompts for the parent directory (defaults to home folder) before cloning, so pip-installed users can choose where SAGE26 lands rather than having it hardcoded relative to CWD

---

## [1.0.4] — 2026-06-22

### Fixed

- Launch Mode: clicking **×** to close now properly stops the server (`asyncio.ensure_future` instead of bare `await` in sync handler, which caused a `RuntimeWarning: coroutine was never awaited` and left the process running)

---

## [1.0.3] — 2026-06-22

### Fixed

- Launch Mode: **×** button now calls `server.stop()` to shut down the process when running standalone; previously it only hid the wizard UI without terminating the server

---

## [1.0.1] — 2026-06-22

### Fixed

- GIF frames resized to canonical resolution when a mixed native/supersampled frame arrives mid-recording — prevents dimension mismatch crash
- `scipy` added to declared package dependencies (was used but omitted from `pyproject.toml`, breaking `pip install` environments)
- CI: `libgl1-mesa-glx` → `libgl1` (package renamed in Ubuntu 22+)
- CI: removed invalid `W503` ruff selector; added intentional-style codes (`E402`, `E701`, `E702`, `E401`, `C408`) to ignore list; auto-fixed `UP037`/`UP035` quoted annotations and deprecated `Callable` import
- Docs URL updated from readthedocs.io to GitHub Pages (`mbradley1985.github.io/SAGE-Viewer`)
- README image paths changed to absolute `raw.githubusercontent.com` URLs so images render on PyPI

### Added

- GitHub Actions publish workflow (`.github/workflows/publish.yml`) — builds wheel + sdist and publishes to PyPI via Trusted Publishing on every `v*` tag push; no API token needed in CI
- Docs pages: Multi-Box Comparison, Launch Mode, Recording, Library (all new)
- `docs/mkdocs.yml` nav updated with new pages

### Changed

- `docs/getting_started/installation.md`: removed broken `pip install sage-viewer` section; HPC section updated to use `install_hpc.sh` instead of conda
- `docs/getting_started/quickstart.md`: fixed "left panel" → Structure tab (right panel); "click" → double-click
- `docs/user_guide/console.md`: rewrote Terminal mode to reflect PTY backend; removed stale "no pty" limitations section
- `docs/user_guide/interface.md`: seven tabs → nine tabs; added Console and Library rows; added Multi-Box Strip section

---

## [1.0.0] — 2026-06-22

First public release on PyPI.

### Added

#### HPC install script (`install_hpc.sh`)
- Creates a Python venv and pip-installs SAGE-Viewer in editable mode in one step
- Checks Python ≥ 3.10; accepts optional positional argument for venv path on scratch filesystems
- Checks for `ffmpeg` separately and prints a `module load ffmpeg` hint if absent

#### Side-by-side multi-box comparison
- Load two or more SAGE models side-by-side via `+SBS` in the hamburger Models section
- Each box is fully independent: snapshot, filters, colormaps, opacity, layer visibility
- Box strip at the bottom of the viewport; clicking a box makes it active (green label)
- Play, step, and snapshot slider advance only the active box's snapshot
- Halo Mvir colour mode locked to Viridis for visual consistency across boxes
- Background snapshot preloading and per-snapshot KDTree pre-building

#### Launch Mode wizard (`sage_viewer/wizard/`)
- Guided setup flow for configuring and launching SAGE26
- Step chips in the header track progress (cyan = current, green = done, white = pending)
- **Rescan** button restarts the environment scan at any point
- **Create config file** option writes a new `.par` from the built-in template
- Par file editor opens side-by-side with the terminal for simultaneous editing and output review
- SAGE26 `OutputDir` is created automatically before the binary runs
- Wizard always resets cleanly when re-opened from Explore Mode

#### PTY-backed xterm.js terminal (Console tab)
- Terminal mode replaced with a real PTY (`pty.openpty()`) — full ANSI colour, cursor control, interactive programs (`vim`, `top`, `htop`, `less`) all work
- PTY sessions cleaned up automatically on app exit via `atexit` handler
- Multiple sessions, each with their own PTY process, history, mode, cwd, env, and Python interpreter

#### Interactive draw widgets — Coords and Box tabs
- **Draw Sphere**: two draggable handle balls (centre + edge) with live field updates; **Lock Sphere** commits as the active focus region
- **Draw Box**: native `vtkBoxWidget2` with face and corner handles; **Lock Box** commits; **Clear** cancels without navigating
- Both widgets centre on the camera focal point when first placed; cleared automatically on Reset Camera and model switch

#### Library pop-out improvements
- Multiple items open simultaneously as independent floating cards with diagonal cascade positioning
- GIF always restarts from frame 0 on open (unique `#N` URL fragment busts browser animation cache)
- Close reliability fixed: authoritative Python list as source of truth instead of reading stale Trame proxy state

#### Movie recording fixes
- FPS now honoured: frame written every `1/fps` seconds, reusing cached image when playback frame hasn't changed
- Encoding offloaded to a daemon thread so UI stays responsive during GIF/MOV assembly
- Intermediate frames saved as JPEG quality 95 (~10 ms/frame) instead of PNG (~100 ms/frame)
- Minimum 1 ms sleep per tick prevents event-loop starvation when frame capture exceeds `1/fps`

### Fixed

#### Launch Mode wizard
- **Back navigation**: clicking Back from any downstream step (run SAGE26, par edit, compile failure) now correctly returns to the main menu instead of the Start Fresh submenu
- UI text: "Edit the file below" → "Edit the file to the right" (par editor is side-by-side); "Running SAGE26 — output streams below" → "Running SAGE26 — output follows"
- Layout: terminal card `max-width` dynamic (1100 px solo, 860 px with par editor); choice buttons scroll within `max-height:120px`; buttons shrink to `x-small` when more than 5 choices
- xterm.js CDN entries and `wiz_active` state initialisation fixed — terminal was blank on launch via `./sage-viewer` with no `--par` flag

#### Draw Box / Draw Sphere widget placement
- Both widgets now appear centred on the camera focal point at field-of-view-appropriate size
- Box widget handles restored to constant size after each drag via `EndInteractionEvent` observer

#### Double-click galaxy selection accuracy
- Two-stage selection: find 50 nearest galaxies in 3D (KDTree), then project to screen and pick the visually closest
- Respects environment checkbox state and `_combined_mask()` so only visible galaxies are selectable

#### Trame / rendering
- `view_update()` called after `plotter.render()` in box-switch and toggle handlers so new frames reach the browser immediately
- FoF satellite→central links respect active halo filter mask, focus region, and halos-visible toggle
- Playback frame cache keyed on a `_scene_hash()` covering all filter, visibility, colormap, and focus state — cached frames never replayed after scene changes

---

## [0.3.0]

### Added

#### Embedded shell console
- Real shell via `asyncio.create_subprocess_shell`; globs, pipes, redirects, backgrounding all work
- `cd`, `pwd`, `export` handled as in-process built-ins
- Python REPL mode; SAGE natural-language command mode
- Multiple sessions, Load Script, Pop-out floating card

#### Tab-aware Focus button
- Focuses on whatever is active in the current tab (target galaxy, environment halo, coords point, or box region)

#### Dynamic colour-by dropdowns
- Only modes whose underlying field is present in the loaded model appear; rebuild automatically on model switch

#### Library tab — per-row delete
- Red trash button permanently removes the file from disk and refreshes the list immediately

#### Filter active-only architecture
- Filters only take effect when moved from full-range defaults; all galaxies visible at startup

#### Double-click everywhere
- Picker globally on; double-click populates Target tab fields and draws the red marker

#### Switching-models overlay
- Cyan-bordered overlay covers the viewport while a model is loading; rotating quip shows server is alive

### Changed
- Toolbar re-arranged: hamburger left, transport + controls right
- Right panel locked at 300 px, never scrolls
- Indicators persist across tab switches
- Structure mode simplified to three layers (outer envelope, cold-gas envelope, property shell)
- All Unicode super/subscripts replaced with ASCII across user-visible strings
- Full still-quality rendering at all times (no interactive quality reduction)

### Fixed
- Galaxy filters silently excluding low-mass galaxies — active-only architecture resolves this
- Double-click could select invisible (filtered / out-of-focus) galaxies
- Snapshot-slider crash when focus mask and filter mask have different lengths after snapshot change
- Pop-out console now actually draggable (static asset replaces inline `<script>` stripped by Vue 3)
- FoF links hidden for halos that don't pass active filters or focus region

---

## [0.2.0]

### Added

#### Multi-model support
- Scan `<sage_root>/output/` for subfolders; switch primary model from hamburger menu
- Overlay a second compatible model (same box size + snap count)
- Loading overlay + compatibility-error snackbar

#### Filters tab
- Halo filters: Mvir, Rvir, Vvir
- Galaxy filters: stellar mass, sSFR, B/T, age, BH mass, ICS mass, Type, FFB regime, CGM/Hot regime
- Reset Filters button; filters auto-disable for fields not present in the loaded model

#### Environment tab
- Halo selector + Group Info card + Highlight Members (cyan splats on FOF members)
- Field / Isolated / Group / Cluster environment-class checkboxes

#### Target tab additions
- Galaxy Info card; Highlight Galaxy toggle; Clear Indicator button

#### Structure render mode
- Multi-layer galaxy splats: cold-gas envelope (blue), outer envelope (CGM green / Hot red), property shell
- Colormap expanded to 27 maps; inline colorbar beneath each selector

#### Record tab
- Screenshots (PNG / JPG / TIFF); movies (GIF / MOV / PNG sequence)
- FPS slider, resolution selector (Native / 2× / 4×), per-session output folder

#### Camera
- Centre button; Camera bookmarks (save, restore, delete)

### Self-contained HDF5 metadata
- Cosmology, box size, and snapshot redshifts read from `model_0.hdf5` — `.par` file only needed for tree paths

### Rendering overhaul
- World-space gaussian splats (`vtkPointGaussianMapper`) with per-point `radius` array
- In-place PolyData updates across snapshot transitions

---

## [0.1.0]

### Added — Initial release
- PyVista + Trame stack (Vue 3 frontend)
- `io/` layer: lhalo_binary halo reader, SAGE HDF5 galaxy reader, snapshot table, par file parser
- `scene/` layer: Scene, HaloLayer, GalaxyLayer, CameraController
- `parallel/` loader with prefetch pool and LRU snapshot cache
- `sage-viewer` CLI entry point
- miniMillennium and microUchuu support
- Play / Pause / Stop / Reverse / Repeat transport; speed selector; snapshot slider
- Fly to halo, galaxy, coordinates, or sub-box; Focus mode; Camera bookmarks
- MkDocs Material documentation; GitHub Actions CI and docs deployment
