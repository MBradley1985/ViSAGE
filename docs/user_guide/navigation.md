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

## View controls

These work no matter which tab is active. **HD** and **Reset** are in the top bar; the rest are at the bottom of the icon rail. Go, Info and Isolate need a selection.

| Button | Action |
|---|---|
| Reset | Puts everything back to default and shows the whole run |
| HD | Detailed 3D model of the selection and its group — see [HD Mode](hd_mode.md) |
| Go | Flies to the selection: the galaxy, or in halo context its halo and group |
| Info | Opens or closes the selection card |
| Focus | Masks haloes and galaxies outside the current zoom region. Galaxy zooms auto-enable focus |
| Isolate | Shows only the selection, 3 Mpc/h away as Go: the galaxy, or in halo context its halo and whole group |
| Box Centre | Places the camera AT the box centre, looking out. In a lightcone this is **Observer**, at the observer looking along the cone |

## Selecting a galaxy

Double-click a galaxy to select it. A cyan ring marks it. In the card's **Halo + group** context every member of its FOF group is ringed alike; rings that would pile up on screen merge into one. The selection is the galaxy itself, not its row: changing snapshot finds it again by its GalaxyIndex, or says it isn't there (not formed yet, or merged).

The Console also selects (`go to halo 42` selects that halo's central), and so do the card's group list and the Find list.

### The selection card

The **i** button in the header (or **Show info** at the end of the Structure tab) opens the card:

| Part | What it does |
|---|---|
| Galaxy / Halo + group | What the actions apply to: the galaxy, or its host halo with the whole group |
| Go | Fly to it, 3 Mpc/h away: the galaxy, or in halo context the halo and its group (inside HD, to it in close-up). Everything else stays shown, within a 10 Mpc/h focus sphere |
| Isolate, HD | As the rail's Isolate and the header's HD. In **Galaxy** context HD draws just the galaxy; in **Halo + group** context, the whole group |
| Gas | HD's halo gas on or off |
| ← → | Back and forward through what you've selected |
| ‹ › | Previous / next member of the group, flying to it (the card keeps its Galaxy / Halo + group context) |
| ☆ | Up to the group's central |
| Nearest | Hop to the nearest galaxy and fly there; amber rings mark the next nearest (the next hop larger). Hopping again carries on to the nearest not yet visited, so it never bounces back |
| Zoom 3 / 5 / 10 | Fly in at that radius (Mpc/h), with focus |
| Clear / Show indicator | Rings off or on. The galaxy stays selected, and the choice holds through HD, Gas and new selections |
| Host halo · Go to halo | The halo the central sits on, and a flight to it |
| Properties | Key properties; **All properties** lists every field (Approx Age needs SAGE's full star-formation histories, `SaveFullSFH 1`) |
| Group | Every member (central first); click one to select it and fly there |

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

## Regions tab

Pick a **Sphere**, **Box**, **Slice** or **Selection**. What is on the tab is the active region: the count below it, and **Active region** in Plotting and Export, all use it. In a periodic box, regions wrap around the edges.

- **Fit to view** centres a sphere or box on the view and sizes it to what the view shows. Pressing Enter in a field is the same as **Go**.
- **Go** isolates the region and frames it; **Clear** puts the view back. **Dim outside the region** dims the galaxies outside it (haloes outside are still hidden).
- **Create sphere**, **Create box** and **Create slice** show it in the view: drag a sphere or box to move and size it.
- **Slice:** pick an axis or the current view, then set the position and thickness. **Animate through the volume** moves it through the volume.
- **Selection:** draw a lasso or rectangle over the view, or click galaxies, and Add, Remove or Replace. While you choose, everything else is dimmed. A drawn shape takes everything through the depth; **Nearest galaxies only** keeps the nearest in each part of the screen. **Add all from** Filters, Group or Last region adds those galaxies. In a box, a selection follows its galaxies through snapshots.
- **Save** keeps a region with its model. Click a saved name to bring it back.

Box mode and Lightcone Mode have the same tab. A lightcone also has a **Photometry** tab: see [Lightcone Mode → Synthetic photometry](lightcone.md#synthetic-photometry-sed).

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
