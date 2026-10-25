# Lightcone Mode

Lightcone Mode opens a [LightSAGE](https://github.com/sage-home/sage-lightcone) `cli_lightcone` HDF5 output — a flat catalogue of galaxies spanning a range of redshifts along an observer's line of sight — in the **exact same Explore UI** as a SAGE box: same toolbar, navigation panel (every colour-by mode), info panel, and gaussian-splat rendering.

See [Launch Mode → Setting up a run](launch_mode.md#setting-up-a-run) for how to build a lightcone from a SAGE26 model.

## Opening a lightcone

```bash
visage --lightcone /path/to/lightcone.h5
```

Or, in Launch Mode, click **Open in Lightcone view** when a build finishes, or pick it under LightSAGE's **Load existing** or the home page's **Load a previous model**. Or pick it from the **Session Models** list (see below) if you've opened it before. The page shows **Opening …** and reloads itself when ViSAGE is ready.

## What gets loaded

Every SAGE field carried in the flat lightcone file is read into a full galaxy snapshot — so every Structure tab colour-by mode (stellar mass, sSFR, cold gas, B/T, …) works exactly as it does for a SAGE box. Host haloes are built from the galaxies with `Type == 0` (centrals).

A lightcone is a single static point cloud (it already spans every redshift at once), not a per-snapshot simulation — so there's no background snapshot preloading and no per-model output-directory scan.

## The snapshot slider is a redshift/time cut

Unlike a SAGE box, where the slider selects one snapshot to display, in Lightcone Mode the slider:

- only spans the snapshots actually **present in the cone** (not the full 0–63 range of the underlying simulation)
- **removes** galaxies nearer than the selected point (lower redshift), keeping everything farther away (higher redshift)
- shows the **full cone** when pulled to its maximum (the default on load)

Drag it inward from the maximum to peel away the near side of the cone and see what's left at higher redshift.

## Synthetic photometry (SED)

If the lightcone was built with photometry (see
[Launch Mode → Setting up a run](launch_mode.md#setting-up-a-run)), Lightcone Mode
replaces the **Box** tab (a periodic box has no meaning for a cone) with a
**Photometry** tab — a false-colour **image builder**.

Photometry is its **own independent layer**, separate from the galaxies, with
its own **Visible** checkbox and **Opacity** slider. It's hidden by default;
ticking **Visible** shows it and hides the normal galaxies by default so the
image reads cleanly (unticking it brings them back). Because it's a separate
layer you can view it however you like — re-enable the galaxies (Structure
tab) to overlay both, or keep them off for the photometry image on its own.
Galaxies with no flux in the stacked filters are simply not drawn.

When shown, it draws the galaxies as Rvir-sized gaussian splats painted from a
**stack** of the filters you tick in the **Filters** dropdown. Filters are
named by survey ("SDSS g", "2MASS Ks", "IRAC 3.6 µm") and listed blue to red,
observed frame first; SDSS r is the default. Each filter is
tinted a representative colour — UV/`u` violet, `g` green, `r`/`i`/`z` and the
near-/mid-IR bands (J, H, K, WISE) deepening reds — and scaled by the galaxy's
brightness in that band; the ticked filters are summed into an additive
false-colour composite. Tick one filter for a single-band image, or several to
build a multi-band colour image; **mass-to-light** (`M*/L`) entries can be
stacked the same way. A colour-swatch legend shows the current stack.

The Photometry tab only appears for lightcones that actually carry SED data
(otherwise it shows a short note explaining how to produce it).

### Mock images

**Create mock image** (in the Photometry tab) makes a survey image of the sky
around the selected galaxy, or the cone's brightest galaxy if none is
selected: what SDSS, DES, Pan-STARRS1, LSST, 2MASS, WISE, GALEX or JWST NIRCam
would record. Only surveys whose filters the cone has are offered. Choose the
field (½′ to 30′, kept under 2400 pixels a side) and whether to add the
survey's sky noise. Each galaxy is drawn as its disk and bulge at its own size,
inclination and colours, blurred by the survey's seeing on its pixel grid. The
image opens in a Library card and is saved in the session folder as a PNG and
a FITS file (one band per extension, in nanomaggies, with a WCS). Only the
cone's own galaxies are on the sky, so a shallow cone looks sparser than the
real sky. The method and survey numbers are in
[Lightcone photometry → Mock images](../physics/photometry.md#mock-images).

## Camera

Resetting the camera frames the cone **horizontally, centred and zoomed in**,
showing it end to end (rather than the cubic-box framing used for a SAGE box) —
this is also the initial view on load, framed to your window once the page
has opened.

The **go-to-centre** button (▶ centre icon) doesn't use a box centre in
Lightcone Mode — instead it stands you at the **observer** (the coordinate
origin) looking **outward** along the cone, with the sky spread horizontally,
as if gazing out into the lightcone.

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
