# Lightcone Mode

Lightcone Mode opens a [LightSAGE](https://github.com/sage-home/sage-lightcone) `cli_lightcone` HDF5 output — a flat catalogue of galaxies spanning a range of redshifts along an observer's line of sight — in the **exact same Explore UI** as a SAGE box: same toolbar, navigation panel (every colour-by mode), info panel, and gaussian-splat rendering.

See [Launch Mode → LightSAGE steps](launch_mode.md#lightsage-steps) for how to produce a lightcone file from existing SAGE26 output.

## Opening a lightcone

```bash
visage --lightcone /path/to/lightcone.h5
```

Or, from inside the wizard's LightSAGE flow, click **Visualize lightcone** after a successful run to relaunch straight into it. Or pick it from the **Session Models** list (see below) if you've opened it before.

## What gets loaded

Every SAGE field carried in the flat lightcone file is read into a full galaxy snapshot — so every Structure tab colour-by mode (stellar mass, sSFR, cold gas, B/T, …) works exactly as it does for a SAGE box. Host haloes are built from the galaxies with `Type == 0` (centrals).

A lightcone is a single static point cloud (it already spans every redshift at once), not a per-snapshot simulation — so there's no background snapshot preloading and no per-model output-directory scan.

## The snapshot slider is a redshift/time cut

Unlike a SAGE box, where the slider selects one snapshot to display, in Lightcone Mode the slider:

- only spans the snapshots actually **present in the cone** (not the full 0–63 range of the underlying simulation)
- **removes** galaxies nearer than the selected point (lower redshift), keeping everything farther away (higher redshift)
- shows the **full cone** when pulled to its maximum (the default on load)

Drag it inward from the maximum to peel away the near side of the cone and see what's left at higher redshift.

## Camera

Resetting the camera frames the cone **horizontally, centred** in the viewport (rather than the cubic-box framing used for a SAGE box) — this is also the initial view on load.

## Session models

The Launch-Mode dropdown (SAGE-logo button, top-left of the toolbar) lists
every box and lightcone opened so far this session under **Session Models**,
with a box or telescope icon marking the kind and the currently active one
highlighted. Click any entry to jump straight back to it — a quick relaunch
on the same port — so loading a SAGE box after a lightcone (or vice versa)
never loses track of what you had open.

This list is persisted across relaunches in `~/.visage/session_models.json`.

## Things that don't apply in Lightcone Mode

A lightcone has no periodic box and isn't tied to a single SAGE parameter
file, so a few Explore-mode features that assume a box don't apply:

- Multi-model overlay / side-by-side comparison (a lightcone is always the sole loaded model)
- The `.par`-derived cosmology display (cosmology is read from the lightcone's copied SAGE header instead)
