# HD Mode

HD replaces the selected galaxy's splat with a detailed 3D model built from its SAGE properties, ray-marched on the GPU every frame. In the selection card's **Galaxy** context HD draws just that galaxy; in **Halo + group** context it draws its whole pair, group or cluster. Nothing else is drawn: no other galaxies or background.

Select a galaxy (double-click it), then press **HD**. The top bar's **HD** turns on HD with its halo gas; the selection card has **HD** and **Gas** as separate buttons. Press **HD** again, or **Esc**, to go back: to Isolate if you were in Isolate, otherwise to the normal view, framed as **Go** frames it.

## What is drawn

Each galaxy's model follows from its own catalogue row:

| Component | From |
|---|---|
| Disk or elliptical, size and brightness | Stellar mass, bulge-to-total ratio, SAGE26's own disk and bulge radii |
| Spiral arms (several arm classes) and pitch | Disk mass, gas fraction, star formation, black-hole mass |
| Types of irregular (patchy clouds, fading, starburst, disturbed, Magellanic barred), lenticular (smooth, barred with a lens and rings, dust ring, dust lane, disturbed dust) and flocculent spiral (star-forming, massive, fading) | Star formation rate, mass, bar, recent mergers and infall, dust and molecular gas, the gas disc's tilt against the stars (DarkSAGE) |
| Bars | Disk stability (Vmax against the disk's stars and radius) and B/T |
| Fast and slow rotators | Stellar mass and recent major mergers |
| Classical and pseudo-bulges | Merger vs. instability bulge masses |
| Young star clusters and HII regions | Disk SFR, cold and H₂ gas, gas metallicity |
| Dust | HI + H₂ and metallicity; lanes in disks rotating faster than ~120 km/s; filaments through the core of ellipticals with molecular gas or dust |
| Shells, tails and streams | Time since the last major and minor merger |
| Tidal streams of stripped satellites | Subhalo mass lost since infall |
| Intracluster light | ICS mass |
| AGN nucleus | Quasar-mode accretion rate |
| Disk thickness (a thin and a thick disc) and clumpiness | Disk size, rotation speed, redshift, gas fraction, FFB regime |

Sizes shrink with redshift as in the size–mass relation, and disks at high redshift are thicker and clumpier.

If the run saved its star-formation histories (SAGE's `SaveFullSFH 1`), colours also follow the stars' ages: young disks are bluer, recently quenched galaxies white-blue, and a rejuvenated bulge stands out from an older disk. Without them, colours follow metallicity only.

On a DarkSAGE run the disc follows the model's own radial profiles, and on a DustySAGE run the dust follows its own dust mass.

The full list of components, the SAGE26 fields each one uses and how, is in [HD Galaxy Components](../physics/hd_components.md). [HD Components, Illustrated](../physics/hd_components_illustrated.md) shows each one rendered on real galaxies, beside how it is built.

Every disc is drawn at the model's own `DiskRadius`. With SAGE26's `DarkSAGEMode` the annuli set the shape of its light, star formation and dust, its height comes from `VelDispStars` (σ² / πGΣ at the half-mass radius), and spiral arms fade between Toomre Q of 1 and 2, where the disc is stable. Q decides where arms end, not whether a galaxy has them. The profile is held flat inside 0.15 of the disc radius: the disc has one height, so a peak there would be drawn as a column of light.

## Groups and clusters

In **Halo + group** context, HD draws every member of the FOF group at its own position and spin:

- **Members** are drawn at the size they have in the normal view, so the group keeps its layout. The halo gas keeps its true size.
- **Tidal features:** close pairs (within 100 kpc, mass ratio above 1:10) and galaxies that SAGE merges before the next snapshot raise tidal bridges and tails. These are stronger for prograde encounters.
- **Satellites** in hot haloes can show ram-pressure ("jellyfish") tails and tidal stripping.

In **Galaxy** context HD draws the selected galaxy alone, at its true size and its own exposure. Its group still shapes it: a satellite keeps its jellyfish tail, and a close companion still raises tidal features, though the companion isn't drawn.

A big group or cluster has its 100 most massive members drawn as models (the 4 most massive in full detail) and the rest as soft glows. **Go** on a glow (from the card's member list, a double-click or the browsing keys) builds that galaxy on its own and adds it to the scene. The galaxy you selected is always a model. The card tags each member **HD**, **glow** or **HD extra**.

Inside HD, double-click picks among the galaxies HD draws; under the cursor, the most massive one wins. **Go** on the card flies to that galaxy without leaving HD.

## The group on the card

The card lists every member of the selected galaxy's group (scroll for the rest). In **Halo + group** context it also describes the group:

- **Type:** a **Cluster** (host halo from 10¹⁴ M☉) or **Group** (10¹³–10¹⁴ M☉) by its halo mass (e.g. Kravtsov & Borgani 2012; Lovisari et al. 2021); in smaller haloes a **Small group**, **Pair** or **Isolated** galaxy by how many members have at least 10⁹ M☉ of stars, so the name doesn't change with the resolution cut.
- the host halo's Mvir and Rvir, the members (and how many have M* ≥ 10⁹ M☉), their velocity dispersion along one axis, total stellar mass, the gap in stellar mass between the two most massive (and in a lightcone with photometry, the r-band gap Δm₁₂, a **fossil** group from 2 mag; Jones et al. 2003), the share quenched (sSFR < 10⁻¹¹ yr⁻¹; Weinmann et al. 2006), the intracluster light and the hot gas.

## In a lightcone

HD works in Lightcone Mode with each galaxy as an observer sees it:

- **Its own redshift**, star-formation history and spin, and its group (the cone repeats the simulation box, so a group is the copies of its members around this copy of its central).
- **Seen from the observer:** HD frames the galaxy along the line of sight from the cone's apex, so it is at the inclination its photometry used.
- **Its photometry's dust:** with each galaxy's own dust (the Charlot & Fall model of the photometry), HD dims and reddens it with the same face-on optical depth (`TauV_ISM`) and attenuation curve as its magnitudes, DustySAGE's dust included. Where the run has annuli, that depth is the photometry's star-weighted one, annulus by annulus, and HD's dust map is scaled to match it exactly. Photometry made with one dust screen for every galaxy, or without dust, leaves HD its own dust.
- **Its colours:** the galaxy's overall colour is matched to its observed g, r and i magnitudes, on HD's colour scale (fitted on 300 cone galaxies) and on the colours stars can have: emission lines in the broadband magnitudes are drawn as its HII regions, not as a tint.

The card shows its redshift, distance, apparent and absolute r magnitude, rest-frame g − r and A_V at its inclination; **All properties** adds the sky position, dust mass, dust-to-gas ratio, face-on optical depth, emission-line fluxes, AGN and dust luminosities and every magnitude. Galaxies are named by SAGE's GalaxyIndex.

## Components

In **Galaxy** context, the card's **?** (Components) button, next to the nearest-galaxy button, puts a numbered marker on each part of the HD galaxy and lists them in a key along the bottom of the view. Only what the galaxy has, from its SAGE26 properties, is marked:

| Category | Parts |
|---|---|
| Stars and structure | bulge or pseudo-bulge, bar, spiral or flocculent arms, the elliptical body |
| Star formation | star-forming regions, nuclear ring, giant clumps |
| Dust | arm dust lanes, an elliptical's dust lane |
| Black hole and AGN | central black hole, quasar nucleus, radio jet (with **Gas**) |
| Mergers and environment | merger shells, tidal tails and streams, tidal debris, stripped stars, ram-pressure tail, intracluster light |
| Halo gas (with **Gas**) | galactic wind, HI disc, cold stream, hot halo |

- **Each marker has one fixed point on its part**, chosen once from the model: the arm ridge where its young light peaks, the brightest star-forming complex, the darkest dust lane, the densest shell, and so on, spread round the disc. Turning or zooming moves the marker with the galaxy; it never jumps to another point.
- **The key never moves.** It sits along the bottom, centred in the space left by the selection card, the icon rail and any open panel. Each entry gives the part's name and a line from this galaxy's own values (its masses, rates, pitch angle, merger time). A part that is out of view, or whose marker would sit under the key, is greyed out.
- **Colours** mark the category, on the markers, their numbers and the key's headings. They're chosen to stay distinct for colour-blind viewers. Markers closer than 24 px share one bubble, its rim fading from one category's colour to the next and each number in its own colour.
- The intracluster light is marked only when SAGE26's ICS is at least 5% of the galaxy's stars; fainter than that, it can't be seen.

Press **?** again to hide them. (It isn't offered in **Halo + group** context.)

## Gas

The card's **Gas** button switches between the galaxy as an optical image shows it and the galaxy with its gas: with Gas off you see the stars, the star clusters and HII regions, and the dust; with Gas on, the gas in the disc and the gas in the halo are added. Every member of the group gets its own, out to its own Rvir. It is off by default.

| Gas | From |
|---|---|
| Ionised gas: glowing H-alpha clouds and filaments round the star formation | Disk SFR, H₂ |
| Molecular clouds, seen by their dust as dark filaments across the disc | H₂, the disc's dust |
| Extended HI disk, past the stars | H1gas |
| A jellyfish's stripped gas, its tail's soft plumes included | The ram pressure on a satellite |
| CGM with cold streams along the cosmic web | CGMgas (cold regime), mdot_stream |
| Hot halo / intracluster medium, coloured by temperature, with X-ray cavities | HotGas, Mvir, concentration, metals, radio heating radius |
| Galactic winds | OutflowRate, ejected gas |
| Radio jets, in radio-loud AGN (from 10⁴² erg/s) | Radio-mode accretion |

The disc's gas is drawn inside the disc with its stars and dust, so it is lit, dimmed and reddened with them; the halo's lies over the whole view, thinned over the galaxy so it doesn't hide it. Gas is a shader switch: turning it on or off doesn't rebuild anything.

The card's **Rotation** button opens maps of the stars and gas as line-of-sight velocities. Counter-rotating gas is what the model predicts, and can only be seen there.

## Building

The CPU side of a build runs in background worker processes. A card shows the progress, with a **Cancel** button (or press **Esc**). A build takes a few seconds; a rich cluster takes longer.

To keep it quick:

- the worker processes are started, and the shaders compiled, a few seconds after ViSAGE opens;
- recent builds are kept in memory (a tenth of the machine's RAM, between 0.5 and 3 GB), so turning HD off and on again, or going back to a group you just viewed, is immediate;
- a moment after you select a galaxy, its HD is built quietly in the background, so pressing **HD** is usually immediate;
- while HD is on, the same galaxy is built at the previous and next snapshots, so stepping through time in HD doesn't wait for a build.

Changing snapshot rebuilds HD for the same galaxy (found again by its GalaxyIndex), keeping your view of it, once the slider settles: you can step a galaxy through time in HD. If it isn't in the new snapshot (not formed yet, or merged), HD switches off and says so. Playback, and changing model or box, leave HD.

## GPU requirement

HD needs a GPU. If OpenGL is running on the CPU (llvmpipe, Apple Software Renderer, a Remote Desktop session, a VM without graphics drivers), the HD buttons are greyed out, and hovering over them says why. Set `VISAGE_HD=1` to turn HD on anyway; expect seconds per frame.
