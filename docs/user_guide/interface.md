# Interface

ViSAGE's browser UI has three main regions and a number of overlays that appear when needed:

```
┌──────────────────────────────────────────────────────────────────┐
│ ☰  ViSAGE  ◀◀ ▶ ⏸ ⏹ 🔁  ──slider──  Snap N│z│a   1×  Off ⤴  │
├──────────────────────────────────────────────────────────────┬───┤
│                                                              │ T │
│                                                              │ a │
│                  PyVista render window                       │ b │
│                                                              │ p │
│                  (overlays appear here:                      │ a │
│                   loading spinner,                           │ n │
│                   warning snackbar,                          │ e │
│                   selection card, HD build card)             │ l │
├──────────────────────────────────────────────────────────────┴───┤
│ Info bar: position + nearest halo / galaxy on double-click       │
└──────────────────────────────────────────────────────────────────┘
```

## Toolbar (top)

| Control | Action |
|---|---|
| ViSAGE / Launch | Open the menu: Launch Mode tools, switch primary model, toggle overlay models |
| Reverse · Play · Pause · Stop · Loop | Snapshot playback (one pill). Reverse plays backwards in time, Stop returns to z = 0, Loop continues past the endpoints |
| ‹ Snapshot slider › | Step one snapshot, or jump to any |
| Snapshot | The redshift, then snapshot number, scale factor and the Universe's age (the run's own cosmology) |
| HD | HD of the selected galaxy, with its halo gas (the card's HD and Gas buttons work separately) |
| Reset | Reset the view |

Playback speed and camera rotation are in the **Record** tab.

## Right tabs panel

Eight tabs in two rows of four:

| Tab | Purpose |
|---|---|
| Structure   | Layer visibility, opacity, colour-by mode, colormap (inline colorbar beneath each); environment filter |
| Filters     | Range sliders for halo (Mvir / Rvir / Vvir) and galaxy (stellar mass, sSFR, B/T, age, BH mass, ICS mass, type, FFB regime, CGM regime); **Find** presets |
| Regions     | Spheres, boxes and slices, with live counts and saved regions |
| Record      | Screenshots (PNG / JPG / TIFF) and movies (GIF / MOV / PNG sequence); playback speed and camera rotation |
| Console     | PTY-backed xterm.js terminal + Python REPL + SAGE command mode; multiple sessions; pop-out window |
| Library     | Browse screenshots and movies; double-click a row to open as a floating card over the viewport |
| Plotting    | SAGE26's diagnostic plots, with observations, for the whole catalogue or any selection (see [Plotting](plotting.md)) |

The tabs are icons on the right; clicking one opens its panel over the view, and clicking it again closes it. Drag a panel by the grip along its top to move it anywhere in the window; double-click the grip to put it back by the rail. The bottom of the rail has **Go**, **Info**, **Focus**, **Isolate** and **Box Centre**, and the top bar has **HD** and **Reset**, which all work whichever tab is open (see [Navigation](navigation.md)). The top bar also has Export, Fly-through, updates and Close.

## Multi-box strip

When two or more SAGE models are loaded side-by-side (via `+SBS` in the Launch menu), a **box strip** appears at the bottom of the viewport. Each box is shown as a labelled chip:

- Click any chip to make that box **active** (label turns green)
- All right-panel tab controls then target the active box
- **CLR** in the strip resets that box to default settings without affecting others

The box strip is hidden in single-model mode.

## Render-window overlays

| Overlay | When |
|---|---|
| Loading spinner   | Dimmed cover while a new model loads from disk |
| Warning snackbar  | Top of the render view; appears when an overlay attempt is rejected (e.g. incompatible box size) |
| Selection rings   | A cyan ring on the selected galaxy, smaller rings on the rest of its group (merged where they would pile up) |
| Selection card    | Top-left, draggable; opened by the rail's **Info** button — properties, group list, Go / Isolate / HD / Gas, browsing (see [Navigation](navigation.md#the-selection-card)) |
| HD build card     | Centre, while an HD model builds: progress and **Cancel** (or Esc) |

## Info bar (bottom)

Double-click any point in the render window to select the galaxy there. The info bar then shows:

* The world-space (x, y, z) you clicked
* Nearest halo Mvir and index
* Nearest galaxy stellar mass / sSFR / central-or-satellite / index

The galaxy is then selected: ringed, with its card a click away (the header's **i** button).

Single clicks (no double) are treated as pure camera interactions — they don't move selection and don't trigger any overlays.

## Dusty and Dark 'n Dusty

Under Galaxies in the Structure tab, on runs with SAGE26's `DustySAGEMode` and `DarkSAGEMode`. **Dusty** adds a warm glow of each galaxy's cold, hot and CGM dust. **Dark 'n Dusty** lays ellipses over the usual colours, tilted to each galaxy's stellar spin, blue if it's forming stars and amber if not, with a core sized by its bulge and its gas disc at the real size against its stars. It applies with Colour by on Structure.
