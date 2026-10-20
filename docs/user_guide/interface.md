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
| ☰ (hamburger) | Open the dropdown: switch tabs, switch primary model, toggle overlay models |
| Reverse | Play backwards in time |
| Play / Pause / Stop | Snapshot transport. Stop returns to z = 0 |
| Loop | Continue playback past the endpoints |
| Snapshot slider | Jump directly to any snapshot |
| Snapshot chip | `Snap N  \|  z = X.XX  \|  a = X.XXXX` |
| Speed selector | 0.1× / 0.25× / 0.5× / 0.75× / 1× / 2× / 5× |
| Rotate selector | Off / CW / CCW × 15 / 30 / 60 ° s⁻¹ — continuous camera orbit |

## Right tabs panel

Seven tabs in two rows:

| Tab | Purpose |
|---|---|
| Structure   | Layer visibility, opacity, colour-by mode, colormap (inline colorbar beneath each); environment filter and **Show info** (the selection card) |
| Filters     | Range sliders for halo (Mvir / Rvir / Vvir) and galaxy (stellar mass, sSFR, B/T, age, BH mass, ICS mass, type, FFB regime, CGM regime); **Find** presets |
| Box         | Zoom to axis-aligned sub-box; **Draw Box** for interactive focus region |
| Coords      | Fly to arbitrary (x, y, z); **Draw Sphere** for interactive focus region |
| Record      | Screenshots (PNG / JPG / TIFF) and movies (GIF / MOV / PNG sequence) |
| Console     | PTY-backed xterm.js terminal + Python REPL + SAGE command mode; multiple sessions; pop-out window |
| Library     | Browse screenshots and movies; double-click a row to open as a floating card over the viewport |

Above the tabs sit **Reset Camera**, **Focus**, **Info (i)**, **Centre**, **Isolate** and **HD**, which work regardless of which tab is active (see [Navigation](navigation.md)).

## Multi-box strip

When two or more SAGE models are loaded side-by-side (via `+SBS` in the hamburger menu), a **box strip** appears at the bottom of the viewport. Each box is shown as a labelled chip:

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
| Selection card    | Top-left, draggable; opened by the header's **i** button or **Show info** — properties, group list, Go / Isolate / HD / Gas, browsing (see [Navigation](navigation.md#the-selection-card)) |
| HD build card     | Centre, while an HD model builds: progress and **Cancel** (or Esc) |

## Info bar (bottom)

Double-click any point in the render window to select the galaxy there. The info bar then shows:

* The world-space (x, y, z) you clicked
* Nearest halo Mvir and index
* Nearest galaxy stellar mass / sSFR / central-or-satellite / index

The galaxy is then selected: ringed, with its card a click away (the header's **i** button).

Single clicks (no double) are treated as pure camera interactions — they don't move selection and don't trigger any overlays.
