# Multi-Box Comparison

ViSAGE can display two or more SAGE models side-by-side in a single viewport, each rendered as an independent simulation box.

## Loading a second box

Open the Launch menu (top-left) and click **+SBS** next to any model in the Models section. The new box appears immediately to the right of the existing one. Repeat to add more boxes (up to four is practical).

## The box strip

When more than one box is loaded, a **box strip** appears at the bottom of the viewport. Each box is shown as a labelled chip:

| Element | Meaning |
|---|---|
| Green label | The currently **active** box — all right-panel controls target this box |
| White label | Idle box — renders independently but is not the control target |
| **CLR** button | Reset that box to its defaults (snapshot, filters, colormaps) without affecting others |

Click any chip to switch the active box.

## Per-box independence

Each box has its own:

- Current snapshot (use the snapshot slider or Play to advance only the active box)
- Filter settings (stellar mass, Mvir, sSFR, …)
- Colourmap and colour-by mode
- Layer visibility and opacity
- Camera-focus region

## Shared state

- All boxes share a single camera — panning and zooming applies to all.
- Rotation (`CW` / `CCW`) is **disabled** in multi-box mode.
- The `Halo Mvir` colour mode is locked to Viridis; the colormap selector is greyed out when Mvir is selected.

## Removing a box

In the Launch menu, click the **×** next to a loaded model to unload it.
