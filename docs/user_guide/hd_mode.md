# HD Mode

HD replaces the selected galaxy's splat with a detailed 3D model built from its SAGE properties, ray-marched on the GPU every frame. If the galaxy has company, HD draws its whole pair, group or cluster, along with its surroundings.

Select a galaxy (double-click it), then press **HD**. The button sits next to Isolate (🔍) at the top of the right panel, and also on the selection card. Press **HD** again, or **Esc**, to go back to the normal view at a 10 Mpc/h standoff.

## What is drawn

Each galaxy's model follows from its own catalogue row:

| Component | From |
|---|---|
| Disk or elliptical, size and brightness | Stellar mass, bulge-to-total ratio, disk and bulge radii |
| Spiral arms (several arm classes), bars, peanut bulges | Disk mass, instability bulge, Vmax |
| Classical and pseudo-bulges | Merger vs. instability bulge masses |
| Young star clusters and HII regions | Disk SFR, cold and H₂ gas, gas metallicity |
| Dust | Cold-gas metals, seen edge-on as lanes |
| Shells, tails and streams | Merger history (merger bulge, mergeType) |
| Intracluster light and its streams | ICS mass, ICS disruption |
| AGN nucleus | Black hole mass and radio heating |
| Disk thickness and clumpiness | Velocity dispersion over rotation, redshift, FFB regime |

Sizes shrink with redshift as in the size–mass relation, and disks at high redshift are thicker and clumpier.

The full list of components, the SAGE26 fields each one uses and how, is in [HD Galaxy Components](../physics/hd_components.md).

## Groups, clusters and surroundings

If the selected galaxy is in a FOF group, HD draws every member at its own position and spin:

- **Members** are drawn at the size they have in the normal view, so the group keeps its layout. The halo gas keeps its true size.
- **Neighbours:** the 16 most massive galaxies (M\* > 10⁹ M☉) within 1.5 Mpc/h are drawn in HD too.
- **Tidal features:** close pairs (within 100 kpc, mass ratio above 1:10) and galaxies that SAGE merges before the next snapshot raise tidal bridges and tails. These are stronger for prograde encounters.
- **Satellites** in hot haloes can show ram-pressure ("jellyfish") tails and tidal stripping.

In the card's **Galaxy** context, HD frames the selected galaxy. In **Halo + group** context, it frames the whole group around its central.

Inside HD, double-click picks among the galaxies HD draws; under the cursor, the most massive one wins. **Go** on the card flies to that galaxy without leaving HD.

## Gas

The card's **Gas** button adds the halo gas: every member of the group gets its own, out to its own Rvir. It is off by default; with it off, nothing but the galaxies (and their starlight) is drawn.

| Gas | From |
|---|---|
| CGM with cold streams | CGMgas (cold regime), mdot_stream |
| Hot halo / intracluster medium, with X-ray cavities | HotGas, metals, radio heating radius |
| Galactic winds | OutflowRate, ejected gas |
| Radio jets | Heating |
| Hα cooling filaments | Cooling rate in cluster-mass haloes |

Gas is a shader switch: turning it on or off doesn't rebuild anything.

## Building

The CPU side of a build runs in background worker processes. A card shows the progress, with a **Cancel** button (or press **Esc**). A build takes a few seconds; a rich cluster takes longer.

To keep it quick:

- the worker processes are started, and the shaders compiled, a few seconds after ViSAGE opens;
- recent builds are kept in memory (a tenth of the machine's RAM, between 0.5 and 3 GB), so turning HD off and on again, or going back to a group you just viewed, is immediate.

Changing snapshot or model leaves HD, because the model shows one snapshot.

## GPU requirement

HD needs a GPU. If OpenGL is running on the CPU (llvmpipe, Apple Software Renderer, a Remote Desktop session, a VM without graphics drivers), the HD buttons are greyed out, and hovering over them says why. Set `VISAGE_HD=1` to turn HD on anyway; expect seconds per frame.
