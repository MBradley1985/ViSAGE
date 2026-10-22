# HD Galaxy Components

Every part of an [HD Mode](../user_guide/hd_mode.md) galaxy is built from the galaxy's own row in the SAGE26 output. These tables list each component, the SAGE26 fields it uses (HDF5 names, as written in `model_N.hdf5`), and how they set it.

- **Masses** are converted to M☉ and **radii** to kpc on reading.
- **Metallicities** are in solar units, with Z☉ = 0.02.
- **Optional fields:** if one is missing from a catalogue, the component it drives is simply left out.
- **Randomness:** random choices, such as arm class, are seeded by `GalaxyIndex`, so a galaxy always looks the same.

## Shape and size

| Component | SAGE26 fields | How |
|---|---|---|
| Disk or elliptical | `BulgeMass` / `StellarMass` (B/T), `ColdGas`, `Regime` | Elliptical if B/T > 0.75, or if B/T > 0.5 in a hot-regime halo with a cold-gas fraction under 2%. Otherwise a disk. |
| Size | `StellarMass`, `DiskRadius`, `BulgeRadius`, snapshot redshift, `FFBRegime` | The Shen et al. (2003) size–mass relations set the size. SAGE's own radius nudges it as (R_SAGE / R_relation)^¼, by at most ±30%. Sizes shrink with redshift, as (1+z)^−0.75 for disks and (1+z)^−1 for ellipticals (van der Wel et al. 2014). An FFB galaxy is 0.6× more compact. |
| Disk thickness | `StellarMass`, `VelDisp`, `Vmax`, redshift | Low-mass disks are thicker, by M*^−0.15. Thickness grows by (1 + 0.5z) and with (σ/Vmax)⁶. |
| Elliptical shape | `StellarMass`, `Vmax`, `VelDisp` | More massive ellipticals are rounder and have more extended (cD-like) envelopes. Fast rotators (high Vmax/σ) are flatter. |
| Classical bulge | `MergerBulgeMass`, `MergerBulgeRadius` | Round, at the merger bulge's radius. Its light scales with the merger-bulge mass relative to the disk. |
| Pseudo-bulge | `InstabilityBulgeMass`, `InstabilityBulgeRadius`, `VelDisp`, `Vmax` | Compact, at the instability bulge's radius, flatter in rotation-dominated (low σ/Vmax) disks. It holds whatever instability mass doesn't go into the bar. |
| Bar and peanut | `InstabilityBulgeMass`, `ColdGas` | Barred if the instability bulge is more than 6% of M\*. At most 8% of M\* goes into the bar, whose half-length grows with that fraction (0.9–1.8 disk scale lengths) and which is thinner the stronger it is. Gas-poor disks buckle it into a stronger boxy/peanut bulge. |
| Old stellar colour | `MetalsStellarMass`, `MetalsBulgeMass` | The disk and bulge are each tinted by their own stars' metallicity: metal-rich is redder. |
| Stellar populations by age | `SFHMassDisk`, `SFHMassBulge` (with SAGE's `SaveFullSFH 1`) | The disk's and the bulge's histories are summed as populations of known age: each population's colour and light per unit mass follow its age (younger: bluer, brighter), with metallicity still tinting them. A recently quenched (post-starburst) galaxy turns white-blue with no HII regions, a rejuvenated bulge turns blue, and 0.1–1 Gyr-old star clusters spread through the disk. Without a saved history, colours come from metallicity alone. |
| Brightness | `StellarMass`, `BulgeMass` | Brightness ∝ M\*^0.35, using disk mass for disks. Every member of a group shares one exposure, so relative brightness follows mass. |

## Spiral structure

| Component | SAGE26 fields | How |
|---|---|---|
| Arm class: grand-design, multi-arm, partial or flocculent | `InstabilityBulgeMass`, `StellarMass`, `ColdGas` | Drawn from probabilities set by the galaxy. Barred and massive disks are mostly grand-design or multi-arm. Gas-rich or low-mass disks lean flocculent. |
| Pitch angle | B/T, `Vmax` | Bigger bulges and faster rotation (more shear) wind the arms tighter. |
| Flocculence | `ColdGas` / (`ColdGas` + `StellarMass`), `StellarMass` | Gas-rich, low-mass disks are patchier within their arm class. |
| Clumpy disk | redshift, `ColdGas`, `VelDisp`, `Vmax`, `FFBRegime` | Gas-rich, turbulent disks at z ≳ 1 are clumpy instead of spiral: a Toomre-like score from redshift, gas fraction and σ/Vmax decides it, not chance. FFB galaxies always are. Clumps (4–12) are drawn diffuse and blend into the disk. |

## Star formation

| Component | SAGE26 fields | How |
|---|---|---|
| Young (blue) light | `SfrDisk`, disk mass | Scales with the disk's specific SFR as (sSFR / 10⁻¹⁰)^0.7. FFB galaxies are bluer still. |
| Young star clusters | `SfrDisk` | Their number scales as SFR^0.5 (400–20,000). They follow the young-light map. |
| HII regions | `H2gas`, `SfrDisk`, `DiskRadius`, `ColdGas`, `SfrDiskZ` | Hα-pink star-forming complexes along the arms, in number following the H₂ reservoir. Each complex is richer the denser the star formation (SFR surface density) and bigger the more gas-rich the disk. Their colour runs from pink in metal-poor gas to orange in metal-rich gas, with the star-forming gas's metallicity. |
| Nuclear ring | `SfrBulge`, `SfrDisk` | A faint, diffuse ring of clusters and dust appears when the bulge forms more than 8% of all stars (with SfrBulge > 0.05 M☉/yr). It sits just inside the bar ends. |
| Gas-disk truncation (satellites) | `Type`, `TimeOfInfall`, `Mvir`, `infallMvir` | Satellites lose their outer gas disk the longer since infall and the more of their subhalo they have lost. Star formation stops beyond the cut. |

## Dust

| Component | SAGE26 fields | How |
|---|---|---|
| Disk dust | `H2gas`, `H1gas`, `MetalsColdGas`, `ColdGas` | Face-on optical depth ∝ (Σ_H₂ + 0.4 Σ_HI) × gas metallicity. It follows the arms and the H₂, and reddens what it dims. Thin, streaky dark lanes run along the arms' inner edges, darker the larger that dust column (on a log scale), so gas-poor disks have almost none. |
| Elliptical dust lane | `H2gas` | A nuclear lane in ellipticals that hold molecular gas. |

## Nucleus

| Component | SAGE26 fields | How |
|---|---|---|
| Nucleus | `BlackHoleMass`, `BulgeMass` | Brightness and compactness grow with black-hole mass (relative to the bulge, for ellipticals). |
| AGN point source | `QuasarModeBHaccretionMass` | Quasar-mode accretion this snapshot adds a bright, bluish point. |

## Merger debris and the intracluster light

| Component | SAGE26 fields | How |
|---|---|---|
| Shells (ellipticals) or tidal tails (disks) | `TimeOfLastMajorMerger`, redshift | A major merger leaves debris that fades over 4 Gyr at z = 0, and faster at high z (4 Gyr / (1+z), as dynamical times shorten). |
| Stellar stream | `TimeOfLastMinorMerger`, redshift | A minor merger leaves a stream, fading over 2.5 Gyr / (1+z). |
| Intracluster light (ICL) | `IntraClusterStars`, `MetalsIntraClusterStars`, `Rvir` | A faint, extended envelope (scale 0.12 Rvir, up to 250 kpc), brighter with log(ICS / M\*), so richer clusters keep getting brighter. Its colour follows the ICS metallicity. |
| Streams feeding the ICL | `ICS_disrupt` | Visible when satellites torn apart into the ICL exceed ~10^10.5 M☉. |

## Halo gas (the Gas button)

| Component | SAGE26 fields | How |
|---|---|---|
| CGM and cold streams | `CGMgas`, `MetalsCGMgas`, `mdot_stream`, redshift, neighbouring haloes | Cold-regime haloes. Three curling streams plus filaments out to Rvir, brighter with log CGMgas (or the stream rate), tinted by metallicity. The streams follow the cosmic web: two come in from opposite sides along the direction of the biggest halo within 4 Mpc/h (the filament the galaxy sits in), the third from the next biggest, each brighter the bigger its halo. At high z they are narrower, brighter and reach in to the galaxy (×(1 + 0.15z), width / (1 + 0.35z)). |
| Cold streams into a hot halo | `mdot_stream`, `HotGas` | Hot haloes still fed by cold streams draw them by mdot_stream, aimed and scaled with redshift as above. |
| Hot halo / intracluster medium | `HotGas`, `Mvir`, `Concentration`, `MetalsHotGas`, `Rvir`, redshift | A textured atmosphere to Rvir. Its opacity rises with log HotGas, with the hot gas's share of the halo's baryons, and with redshift (denser haloes). Its core is 1.5 Rvir / c, so concentrated haloes are peakier. Its colour follows the virial temperature (Mvir, hotter at high z): magenta in small haloes, violet in groups, ice-blue in rich clusters, tinted by metallicity. |
| X-ray cavities | `Heating`, `r_heat`, `Regime`, `HotGas` | Bubbles at the radio-heating radius r_heat, along the jet axis, in hot haloes with radio heating. |
| Radio jets | `Heating`, `BlackHoleMass`, `r_heat`, `Rvir` | Jets and lobes along the spin axis, brighter with radio-mode heating and black-hole mass, reaching about the radius the AGN heats (r_heat, or 8% of Rvir). |
| Galactic winds | `OutflowRate`, `SfrDisk`, `SfrBulge`, `DiskRadius`, `MassLoading`, `Vmax`, `EjectedMass` | A hollow bipolar cone along the spin axis, in Hα red (as M82's wind), with a few thin streamers running outward through it. It is brighter with the outflow rate and with the SFR surface density (so compact high-z disks drive stronger winds). It reaches further in deeper potentials (Vmax) and the more of the halo gas has been ejected, and fades out by three times that reach. MassLoading opens it wider (20–60°, on a log scale). It is drawn in 3D, so it looks right from any angle. |
| Extended HI disk | `H1gas`, `H2gas`, `Type`, `TimeOfInfall` | A faint, clumpy, pale-blue gas disk well past the stars, sized by the HI size–mass relation (Wang et al. 2016). It is clumpier where more of the cold gas is molecular, and warped in satellites, more so the longer since infall. |

## Environment (groups, pairs, satellites)

| Component | SAGE26 fields | How |
|---|---|---|
| Group members | `CentralGalaxyIndex`, `Type`, `Pos*` | Every member of the FOF group is drawn at its own position, magnified to its normal-view size (at most 5×). A galaxy alone in its halo is drawn at true size. |
| Spin and orientation | `Spinx`, `Spiny`, `Spinz` | Each disk's plane is set by its spin vector. |
| Tidal bridges and tails | `Pos*`, `StellarMass`, `Vel*`, `Spin*` | Group members within 100 kpc of each other with mass ratio above 1:10 raise tidal features. These are stronger the closer and more massive the companion, and weaker (×0.6) for retrograde encounters. |
| Merger about to happen | `mergeType` | A galaxy SAGE merges before the next snapshot interacts with the nearest more massive galaxy, at a strength set by the merger type. |
| Jellyfish (ram-pressure) tail | `Vel*`, `Pos*`, `HotGas` (host), `Rvir` (host), `StellarMass`, `ColdGas`, `DiskRadius` | The strength is ρ_ICM v² against the disk's restoring force (Σ\* Σ_gas). It is calibrated on SAGE26 so that about 27% of satellites in hot haloes get a tail and about 1% a full one. The tail is a pink Hα streamer with blue knots, trailing the motion. It is brightened to undo the group's shared exposure, and ram pressure also strips up to half the satellite's CGM. |
| Tidal stripping (satellites) | `Mvir`, `infallMvir` | A satellite that has lost more than 65% of its infall subhalo mass sheds stars into tidal streams. |

## Fields not used for visuals

`Concentration`, `ICS_accrete` and `infallStellarMass` are read but don't change the picture. `Cooling` was used only by an early offline prototype.
