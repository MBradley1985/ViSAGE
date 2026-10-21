# Navigation

## Mouse and keyboard (render window)

PyVista's standard trackball controls apply inside the render window:

| Input | Action |
|---|---|
| Left drag | Rotate |
| Right drag / scroll | Zoom |
| Middle drag (or Shift + left drag) | Pan |
| **Double-click** | Select the galaxy under the cursor (the most massive one, if several) — on any tab, and inside HD |
| Single click | Nothing — pure camera interaction (no selection state change) |

## Persistent header controls

Six buttons sit above the tab panel and work no matter which tab is active:

| Button | Action |
|---|---|
| Reset Camera | Returns to a full-box view from outside the box |
| Info (i) | Opens or closes the selection card |
| Focus toggle (◎ target icon) | Masks haloes and galaxies outside the current zoom region. Galaxy zooms auto-enable focus |
| Centre (✛ crosshair icon) | Places the camera AT the box centre, looking out |
| Isolate (🔍 magnifier icon) | Shows only the selection: the galaxy, or (in halo context) its halo and whole group |
| HD | Detailed 3D model of the selection and its group — see [HD Mode](hd_mode.md) |

## Selecting a galaxy

Double-click a galaxy to select it. A cyan ring marks it, and smaller rings mark the other members of its FOF group; rings that would pile up on screen merge into one. The selection is the galaxy itself, not its row: changing snapshot finds it again by its GalaxyIndex, or says it isn't there (not formed yet, or merged).

The Console also selects (`go to halo 42` selects that halo's central), and so do the card's group list and the Find list.

### The selection card

The **i** button in the header (or **Show info** at the end of the Structure tab) opens the card:

| Part | What it does |
|---|---|
| Galaxy / Halo + group | What the actions apply to: the galaxy, or its host halo with the whole group |
| Go | Fly to it (10 Mpc/h standoff; inside HD, to it in close-up) |
| Isolate, HD | As the header buttons |
| Gas | HD's halo gas on or off |
| ← → | Back and forward through what you've selected |
| ‹ › | Previous / next member of the group |
| ☆ | Up to the group's central |
| Nearest | Hop to the nearest galaxy and fly there; amber rings mark the next nearest (the next hop larger). Hopping again carries on to the nearest not yet visited, so it never bounces back |
| Zoom 3 / 5 / 10 | Fly in at that radius (Mpc/h), with focus |
| Clear indicator | Remove the rings (the galaxy stays selected) |
| Host halo · Go to halo | The halo the central sits on, and a flight to it |
| Properties | Key properties; **All properties** lists every field (Approx Age needs SAGE's full star-formation histories, `SaveFullSFH 1`) |
| Group | Every member (central first); click one to select it |

### Keys

| Key | Action |
|---|---|
| `[` / `]` | Previous / next member of the group |
| `C` | The group's central |
| `N` | The nearest other galaxy |
| `B` / `Shift+B` | Back / forward |
| `Esc` | Cancel an HD build, or leave HD |

## Environment filter and Find

The **Environment filter** at the end of the Structure tab shows only galaxies in the ticked environments: Field (< 10¹¹ M☉), Isolated (10¹¹–10¹²·⁵), Pairs, Groups (10¹²·⁵–10¹⁴) and Clusters (> 10¹⁴).

**Find**, at the end of the Filters tab, lists galaxies worth a look in the current snapshot. Pick a preset, then click a result to select it and fly there. The presets are:

- most massive galaxies;
- richest groups and clusters;
- Milky Way analogues;
- close pairs;
- galaxies merging before the next snapshot;
- starbursts;
- quenched centrals;
- biggest black holes;
- feedback-free starbursts.

The list updates as the snapshot changes.

## Coords tab

Enter **X, Y, Z** in Mpc/h and a standoff distance, press **Go** to point the camera at that location.

## Box tab

Enter an axis-aligned bounding box (Xmin, Xmax, Ymin, Ymax, Zmin, Zmax) in Mpc/h. Press **Zoom** to frame that region. With Focus active, the box also defines the masked region.

> In **Lightcone Mode** the Box tab is replaced by a **Photometry** tab (a lightcone has no periodic sub-box to zoom to) — see [Lightcone Mode → Synthetic photometry](lightcone.md#synthetic-photometry-sed).

## Cam (camera bookmarks)

| Control | Action |
|---|---|
| Label + Save | Save the current camera position with a name |
| Bookmarks dropdown + Go | Restore a saved camera position |
| 🗑 | Delete the selected bookmark |

## Programmatic navigation (Python API)

```python
from visage.scene.camera import CameraController

# After scene is created:
scene.camera.go_to_coords(30.0, 30.0, 30.0, distance=10.0)
scene.camera.go_to_halo(42)
scene.camera.zoom_to_box(0, 30, 0, 30, 0, 30)
scene.camera.zoom_to_radius(center=(31.25, 31.25, 31.25), radius=10.0)
scene.camera.reset()
scene.camera.go_to_box_center()
```
