# Navigation

## Mouse and keyboard (render window)

PyVista's standard trackball controls apply inside the render window:

| Input | Action |
|---|---|
| Left drag | Rotate |
| Right drag / scroll | Zoom |
| Middle drag (or Shift + left drag) | Pan |
| **Double-click** | Select the nearest galaxy (only registers on the Target / Environment tabs to avoid wasted work) |
| Single click | Nothing — pure camera interaction (no selection state change) |

## Persistent header controls

Three buttons sit above the tab panel and work no matter which tab is active:

| Button | Action |
|---|---|
| Reset Camera | Returns to a full-box view from outside the box |
| Focus toggle (◎ target icon) | Masks haloes and galaxies outside the current zoom region. Galaxy zooms auto-enable focus |
| Centre (✛ crosshair icon) | Places the camera AT the box centre, looking out |

## Target tab

| Control | Action |
|---|---|
| Halo index + Standoff + Go | Fly to a halo by index at the given standoff |
| Galaxy index + Go (Enter) | Fly to a galaxy by index |
| Zoom preset buttons (3 / 5 / 10) | Galaxy zoom radii in Mpc/h. Engages a focus sphere |
| Galaxy Info | Open the per-galaxy properties card; flies to 30 Mpc/h standoff and locks a 10 Mpc/h focus sphere |
| Highlight Galaxy | Add a cyan splat on the picked galaxy (toggle) |
| Clear Indicator | Clear all overlays and close Galaxy / Group Info cards |

## Environment tab

| Control | Action |
|---|---|
| Halo index + Standoff + Go | Same flight as Target's halo Go, but also snaps the selected galaxy to the FOF central at that halo |
| Field / Isolated / Group / Cluster checkboxes | Show galaxies in the selected environment classes (Field < 10¹¹ M☉; Isolated 10¹¹⁻¹²·⁵; Group 10¹²·⁵⁻¹⁴; Cluster > 10¹⁴) |
| Group Info | Open the FOF-aggregate properties card |
| Highlight Members | Cyan splats on every FOF group member (toggle) |
| Clear | Clear all overlays and close the panel |

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
