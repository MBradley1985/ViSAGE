# Story Mode — Design Reference

!!! note "Status"
    Design spec written before and during the build; kept as the internal
    reference. The shipped, user-facing behaviour is documented in
    `docs/user_guide/story_mode.md` — where the two disagree, the user guide
    is authoritative.

## Overview

**Story Mode** turns ViSAGE into a guided, data-driven presentation tool.
A *story* is an ordered set of *scenes* — each a fully captured viewpoint
(camera + render state + narration) — that the viewer steps through with
Next / Previous, or plays back automatically. Stories live as JSON files in a
`sage_stories/` folder so users can author their own; bundled example stories
ship with the package in `visage/examples/`.

Conceptually, Story Mode is a generalisation of the existing **fly-through**
(`toolbar.py`): the fly-through is a single hard-coded, non-interactive tour;
a story is data-driven, user-steppable, and pausable.

### Design pillars

- **Sandbox** — everything a story needs (model + all referenced snapshots) is
  preloaded before the story starts, using the existing snapshot preload cache.
- **Non-destructive overlay** — Story Mode never locks the UI. All normal
  panels and tools stay live; pausing hands full control back to the user.
- **Smooth & reversible** — transitions reuse the fly-through ease-in/out
  camera mover. Pausing then resuming flies smoothly back to the current scene.
- **Self-contained scenes** — each scene captures the *complete* state, so
  scenes are reorderable with no hidden inter-scene dependencies.
- **Theme-aware** — the active Vuetify theme is already reactive
  (`state.ui_theme`, bound at `app.py`); a story or scene can set it, and exit
  restores the user's prior theme. The DOS-blue palette is not wired in.

## Story file format

One JSON file per story in `sage_stories/` (discovered the same way the Library
tab scans `sage_library/` / `sage_outputs/`).

```jsonc
{
  "schema_version": 1,
  "title": "My Conference Talk",
  "author": "A. Presenter",
  "description": "A guided tour of the SAGE26 galaxy formation story.",
  "theme": "dos_blue",              // story-wide default theme
  "requirements": {
    "model": "miniMillennium",      // single-box for MVP
    "snapshots": [63, 50, 40, 32]   // explicit list OR {"from": 0, "to": 63}
  },
  "scenes": [ /* … scene objects … */ ]
}
```

The sandbox uses `requirements` to switch to the right model and warm the
snapshot cache (KDTrees included) before the first scene renders, surfacing the
existing "Loading snapshots… X/Y" chip. Any snapshot referenced by a scene —
including the full range of a `snapshot_sweep` motion — must appear here.

## Scene object

Every scene captures the **complete** state (full snapshot per scene, not a
delta from the previous one).

```jsonc
{
  // ── Identity / narration ────────────────────────────────────
  "id": "intro-box",
  "title": "The cosmic web at z=0",
  "caption": "...markdown narration shown in the HUD...",

  // ── Context (sandbox resolves these to loaded data) ─────────
  "snap_num": 63,
  "theme": "dos_blue",                  // optional; omit = inherit story theme

  // ── Camera ──────────────────────────────────────────────────
  "camera": { "position": [..], "focal_point": [..], "up": [0, 1, 0] },
  // …or "box" / "reset" to frame all loaded boxes, or a box-framing dict
  // with a pull-back factor: { "frame": "box", "zoom": 1.4 }  (zoom>1 = further back)

  // ── Full captured state ─────────────────────────────────────
  "layers":  { /* all LAYER_KEYS + cbar keys */ },
  "filters": { /* all FILTER_KEYS */ },
  "environment": {
    "cluster": true, "field": false, "group": true,
    "isolated": false, "pairs": false
  },

  // ── Focus + target ─────────────────────────────────────────
  "focus":  { "kind": "sphere", "center": [..], "radius": 30.0 }, // none|sphere|box
  "target": {
    "position": [40.1, 22.3, 18.7],     // PRIMARY: resolved by nearest-position
    "radius": 30.0,
    "galaxy_index": 81234,              // HINT: used only if data matches
    "highlight_group": true
  },

  // ── In-view text / equations (over the render) ──────────────
  "overlays": [
    { "kind": "title", "text": "The SAGE26 Universe", "anchor": "top", "y": 8 },
    { "kind": "citation", "text": "Croton et al. (2016)", "anchor": "bottom-right" },
    { "kind": "equation", "latex": "\\dot{M}_* = \\alpha\\,M_{\\rm cold}/t_{\\rm dyn}",
      "anchor": "center", "size": 2.0 }
  ],

  // ── UI chrome (presentation) ────────────────────────────────
  "chrome": { "hide_panel": true },      // collapse the right navigation panel

  // ── Model / multi-box layout (optional) ─────────────────────
  "models": { "primary": "miniMillennium", "adjacent": ["microUchuu"] },

  // ── Playback ────────────────────────────────────────────────
  "transition": { "duration_secs": 6.0, "easing": "smoothstep" }, // fly INTO scene
  "dwell_secs": 8.0,                     // auto-advance delay in Play
  "hold": false,                         // true = park here in Play after motion
                                         //   (no auto-advance; Next still steps on)
  "motion": { "kind": "still" }          // see Motion below
}
```

## In-view text & equations

Each scene may carry an ordered `overlays` list rendered as an HTML layer over
the VTK view (`#sage-overlay-root`, `pointer-events:none` so it never blocks
camera interaction). Overlay item fields:

| Field | Meaning |
|---|---|
| `kind` | `title` · `heading` · `text` · `citation` · `equation` (text kinds — set size/weight/italic defaults) · `image` · `video` · `audio` (sound only, no visual) · `scene_menu` (clickable scene grid — see below) |
| `text` | content for non-equation kinds |
| `latex` | LaTeX source for `equation` kind; set `"inline": true` for inline math |
| `src` | for `image` / `video` / `audio`: file served from `visage/static/` at `/sage_static/<file>` (NOT the data Library) |
| `width` | for `image` / `video`: px (number) or any CSS length (e.g. `"55vw"`) |
| `opacity` | for `image` / `video`: 0–1 (default 1.0) |
| `loop`, `autoplay`, `muted` | `video`: all default `true`. `audio`: `autoplay` default `true`, `loop`/`muted` default `false` |
| `volume` | `audio` only — 0–1 (default 1.0) |
| `controls` | `video` only — show native transport (default `false`); when `true` the video accepts clicks (otherwise it's click-through) |
| `anchor` | 9-grid: `top-left`…`center`…`bottom-right` |
| `x`, `y` | nudge from the anchor edges — **percentage when numeric, a CSS length when a string** (e.g. `"150px"`) |
| `size` | font size in rem (override) |
| `color`, `weight`, `align`, `max_width` | style overrides |

`image` overlays carry only `src` + sizing (`width`, `opacity`). `video` overlays add
the playback flags above; use **MP4/WebM** (and **PNG/JPG/SVG, not PDF** for images).
`audio` overlays carry just `src` + `volume`/`loop`/`autoplay` and render **no visible
element** — a sound cue tied to the scene (use **MP3/OGG**). They play independently of
the engine, so the client pauses/resumes them with the show's play/pause state
(`#sage-story-playing-relay`), and they stop when the scene changes (the overlay layer
is rebuilt). Pair with scene `"hold": true` so a short clip isn't cut off by
auto-advance. All are normalised in `engine._normalize_overlay` and emitted by
`visage.js`.

### Scene-selector grid (`scene_menu`)

`{ "kind": "scene_menu" }` expands at apply-time into a **clickable grid of the
story's scenes** — a "jump to a scene" slide. Each cell shows a captured
thumbnail (or a numbered placeholder) and, on click, flies to that scene.

```jsonc
{ "kind": "scene_menu", "title": "Jump to a scene", "anchor": "center",
  "cols": 4, "max_width": 88, "include_cards": false }
```

| Field | Meaning |
|---|---|
| `cols` | grid columns (default 4) |
| `title` | optional heading above the grid |
| `include_cards` | include `card-*` divider scenes (default `false`) |
| `anchor`, `x`, `y`, `max_width` | placement of the grid container |

Mechanics: the menu scene is itself a scene (usually the last, with
`"hold": true`). `engine._build_scene_menu` lists every other scene as a cell
`{index, n, label, thumb}`; `visage.js` renders the grid and a cell click
writes the target index to a hidden relay input (`#sage-story-goto-relay`,
`v_model="story_goto_relay"`) whose server `@state.change` handler calls
`player.goto(index)` — the same external-JS→server relay path the PTY uses.

**Thumbnails** are an authoring one-off: Story Mode menu → **"Capture
thumbnails"** (`ctrl.story_capture_thumbs` → `player.capture_thumbnails()`)
steps through every scene, screenshots the render window via
`vtkWindowToImageFilter` (the remote plotter is never `.show()`n, so pyvista's
`screenshot()` can't run), downscales, and writes
`static/story_thumbs/<story>__<scene_id>.png` (served at
`/sage_static/story_thumbs/…`). A cell with no captured thumbnail falls back to
a numbered placeholder, so the selector works before any capture. Thumbnails
are **story content, not framework** — they belong to the story that generated
them and are not committed or shipped.

The overlay layer is rendered **entirely outside Vue**: the server ships the
items as JSON (`story_overlays_json`) and `visage.js` builds the children of
`#sage-overlay-root` itself. Vue owns the (empty) container element but never its
children, so KaTeX's DOM writes cannot corrupt Vue's virtual DOM. Equations are
typeset with **vendored KaTeX** (`static/katex/`, woff2-only, no network) via a
direct `katex.render(latex, el, {displayMode})` call. The overlay layer and the
playback HUD track the panel's right edge so text stays in the visible area when
the panel is shown.

## Chrome / panel visibility

`scene.chrome.hide_panel` collapses the right navigation panel for a clean,
full-bleed presentation view (bound to `state.panels_hidden` via `v-show` on the
panel). This is a **Story Mode scene option only** — there is no general-use
toggle button; in normal use the panel is always shown. The panel is a fixed
300px flex child, so hiding it widens the VTK canvas to full width (the box
re-centres for presentation). Exiting Story Mode restores its pre-story
visibility.

## Models & multi-box

`scene.models` declares the model layout for a scene and is applied via the
existing async controllers — `switch_model` (primary) and `toggle_adjacent`
(side-by-side boxes):

```jsonc
"models": { "primary": "miniMillennium", "adjacent": ["microUchuu"] }
```

The engine no-ops when the layout already matches, switches the primary when it
differs, and adds/removes adjacent boxes to match `adjacent`. Omitting `models`
leaves the current layout untouched. On exit, the pre-story primary + adjacent
layout is restored. Story-level `requirements.models` may list every model the
story uses so they can be discovered/preloaded up front.

### Captured-state keys

Camera, focus, and target are **not** plain state keys — they are captured and
applied via the plotter camera and `scene.set_focus_*` / highlight controllers,
and live in their own scene sub-objects. Everything else is a flat state key,
captured/restored with the `box_profile` save/load pattern.

| Group | Keys |
|---|---|
| **Context** | `snap_num` (model + theme handled at story/scene level) |
| **Layers** (8) | `halos_visible`, `galaxies_visible`, `halo_opacity`, `galaxy_opacity`, `halo_color_mode`, `halo_colormap`, `galaxy_color_mode`, `galaxy_colormap` |
| **Colourbars** (6) | `gal_cbar_min`, `gal_cbar_max`, `gal_cbar_style`, `halo_cbar_min`, `halo_cbar_max`, `halo_cbar_style` |
| **Filters** (43) | 7 × `filter_halo_*` + 36 × `filter_gal_*` — from the canonical list below |
| **Environment** (5) | `env_show_cluster`, `env_show_field`, `env_show_group`, `env_show_isolated`, `env_show_pairs` |

#### Canonical filter-key list

These are the filter keys actually bound in `navigation_panel.py`. The build
must define this list **once** as the single source of truth; the existing
`box_profile.FILTER_KEYS` has drifted (it lists `filter_gal_h2` /
`filter_gal_h1gas`, which are no longer bound) and should be re-pointed at the
canonical list rather than duplicated.

```
# Halo (7)
filter_halo_mvir  filter_halo_rvir  filter_halo_vvir  filter_halo_len
filter_halo_vmax  filter_halo_conc  filter_halo_spin

# Galaxy (36)
filter_gal_smass     filter_gal_sfr        filter_gal_ssfr      filter_gal_coldgas
filter_gal_bulge     filter_gal_bt         filter_gal_bhmass    filter_gal_ics
filter_gal_cgmgas    filter_gal_hotgas     filter_gal_ejected   filter_gal_outflow
filter_gal_massload  filter_gal_cooling    filter_gal_heating   filter_gal_diskrad
filter_gal_bulgerad  filter_gal_mb_mass    filter_gal_mb_rad    filter_gal_ib_mass
filter_gal_ib_rad    filter_gal_sfr_bulge  filter_gal_sfr_disk  filter_gal_sfr_blg_z
filter_gal_sfr_dsk_z filter_gal_met_cg     filter_gal_met_sm    filter_gal_met_bm
filter_gal_met_hg    filter_gal_met_em     filter_gal_met_ics   filter_gal_met_cgm
filter_gal_age       filter_gal_type       filter_gal_ffb       filter_gal_cgm
```

## Portability (self-contained stories)

So a story works on **whatever output is connected** (no hardcoded model names,
snapshot counts, or box sizes), these fields accept symbolic values resolved at
runtime against the active model:

| Field | Symbolic values | Resolves to |
|---|---|---|
| `snap_num`, sweep `from`/`to` | `"first"`, `"last"`, `"40%"`, `"z=1.5"`, or an int | index in `[0, snap_count-1]` (a `"z=…"` spec → closest snapshot to that redshift via the box's redshift table, so it carries over on a model switch) |
| `camera` | `"box"` / `"reset"`, `{ "frame": "box", "zoom": 1.4 }`, or an explicit `{position, focal_point, up}` dict | box-framing from the model's box size (`zoom` > 1 pulls the camera further back) |
| `focus.center` | `"box"` (or a `[x,y,z]` list) | box centre |
| `focus.radius` | `radius_frac` (fraction of box size) as an alternative | `frac × box_size` |

The shipped **`example_tour.json` uses only these symbolic forms** and the
currently-loaded model (no `models` block, no multi-box), so a fresh install
plays it correctly regardless of which simulation is open. Model-specific stories
(e.g. a personal talk, or the dev `smoke_test.json`) may use absolute snapshots,
explicit cameras, and named `models` since their environment is known.

## Targeting resolution (position + index hint)

A scene's `target` is resolved at apply-time, in order:

1. If `galaxy_index` is present **and** a galaxy with that `GalaxyIndex` exists
   in the current `snap_num` data → use it (exact).
2. Otherwise → KDTree nearest-neighbour to `position` within `radius`
   (robust fallback).
3. Otherwise → render the `focus` sphere/box geometry only, no object highlight.

This makes scenes exact on the author's data while surviving data re-runs and
version bumps. Note: `GalaxyIndex` is unique *per snapshot* only — following the
*same* galaxy across snapshots needs merger-tree traversal, which the current
source does not implement (`merger_tree_reader.py` exists only under `build/`).
Cross-time object tracking is therefore out of scope for the MVP.

## Motion

`motion.kind` controls intra-scene animation. `still` is the default.

| kind | fields | behaviour |
|---|---|---|
| `still` | — | hold the captured pose for `dwell_secs` |
| `orbit` | `radius`, `dps`, `degrees`, `axis?` | spin around the `target` / `focus` centre — reuses the fly-through `_orbit_around` helper |
| `snapshot_sweep` | `from`, `to`, `fps?`, `loop?`, `prerender?` | step `snap_num` across cosmic time while holding/orbiting the camera — reuses the preloaded cache. `prerender:true` plays cached pre-rendered frames (smooth, ≤30 fps display + frame-skip speed; single box only) |
| `flythrough` | `style?` (`"story"`/`"normal"`), `approach_secs?`, `fly_secs?`, `group_radius?`, `cluster_radius?`, `group_dps?`, `cluster_dps?`, `spin_degrees?` (default 180), `targets?` (`"halos"`/`"ffb"`), `galaxy_radius?`, `galaxy_dps?`, `rewind_to?`, `rewind_fps?` | **`style:"story"` (default):** reset camera → fly into box centre → tour targets (fly in → focus → orbit `spin_degrees` → unfocus → next) until Next; no settling box orbit. `targets:"halos"` = clusters→groups; `targets:"ffb"` = FFB galaxies. `rewind_to` first steps the box's snapshot from `snap_num` to that redshift before touring. **`style:"normal"`:** the normal-mode (toolbar) fly-through — approach → group → clusters (focus+spin) → return → continuous gentle box orbit forever (calm background, e.g. the scene selector). Full sequence replays each staging; pause→play continues in place |

`snapshot_sweep` is the headline presentation capability (e.g. "watch this halo
assemble from z = 6 to z = 0"). Every snapshot in `[from, to]` must be declared
in the story's `requirements.snapshots`. `fps` defaults to 4.0. `loop` (default
`false`) replays the sweep until Next/Pause — auto-advance never fires, so the
scene holds until the user steps on. A pause/resume continues the sweep **in
place** (the per-scene frame index is checkpointed) rather than restarting from
the first frame.

## Playback semantics

- **Next / Previous** — `_smooth_move` the camera to the target scene's pose,
  apply its full state (filters/layers/env), reconstruct focus, set theme.
- **Play** — auto-advance: run each scene's `motion`, wait `dwell_secs`,
  transition to the next. A scene with `"hold": true` parks after its motion
  (no auto-advance) until the user presses Next — useful for title cards, videos,
  and looping sweeps.
- **Pause** — stop auto-advance, hand full normal control to the user. The HUD
  remains; nothing is locked.
- **Resume (Play after Pause)** — smoothly fly back to the *current* scene's
  pose/state, then continue.
- **Exit** — restore the user's pre-story state profile and prior theme.

## Capture / restore mechanism

Reuses the `box_profile.py` pattern (a key whitelist plus `save_profile(state)`
/ `load_profile(state, profile)`):

- `STORY_SCENE_KEYS` = layer keys + cbar keys + canonical filter keys + env
  keys. Camera / focus / target are handled separately (they are
  scene/plotter objects, not flat state).
- **Capture scene** (authoring button, designed but not implemented — stories
  are currently authored by editing the JSON directly) → would read
  `STORY_SCENE_KEYS` + the current camera pose + current focus geometry →
  append a scene dict → write JSON.
- **Enter Story Mode** → `save_profile()` of the user's current state is
  stashed for restore on exit.
- **Apply scene** → `load_profile`-style write of `STORY_SCENE_KEYS`,
  `_smooth_move` the camera, reconstruct focus via `scene.set_focus_sphere` /
  `set_focus_box`, resolve + highlight target, set `ui_theme`.

## UI surface

- A **Story Mode** button next to the fly-through button (`app.py`), opening a
  `VMenu` dropdown of discovered stories (same pattern as the Launch Mode /
  Explore Mode menus).
- A **HUD overlay** while a story is active: Previous / Play / Pause / Next,
  scene title + markdown caption, and progress ("Scene 3 / 12").
- A **Capture scene** authoring affordance for building stories in-app.

## Build-time obligations

1. Define the canonical filter-key list once; re-point `box_profile.FILTER_KEYS`
   at it to end the drift.
2. Capture camera / focus / target outside the flat-state whitelist.
3. Generalise the theme CSS — `_THEME_CSS` / `sage_theme.css` is currently
   scoped almost entirely to `.v-theme--dos_blue`; a second theme needs its own
   block or de-scoping, and additional palettes registered in the Vuetify
   config. (Theme-switching infra itself is already reactive.)
