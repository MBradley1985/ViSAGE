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
| Pseudo-bulge | `InstabilityBulgeMass`, `InstabilityBulgeRadius` | Compact and flattened, at the instability bulge's radius. It holds whatever instability mass doesn't go into the bar. |
| Bar and peanut | `InstabilityBulgeMass` | Barred if the instability bulge is more than 6% of M\*. At most 8% of M\* goes into the bar, whose half-length grows with that fraction (0.9–1.8 disk scale lengths). A boxy/peanut thickening comes with it. |
| Old stellar colour | `MetalsStellarMass`, `MetalsBulgeMass` | The disk and bulge are each tinted by their own stars' metallicity: metal-rich is redder. |
| Brightness | `StellarMass`, `BulgeMass` | Brightness ∝ M\*^0.35, using disk mass for disks. Every member of a group shares one exposure, so relative brightness follows mass. |

## Spiral structure

| Component | SAGE26 fields | How |
|---|---|---|
| Arm class: grand-design, multi-arm, partial or flocculent | `InstabilityBulgeMass`, `StellarMass`, `ColdGas` | Drawn from probabilities set by the galaxy. Barred and massive disks are mostly grand-design or multi-arm. Gas-rich or low-mass disks lean flocculent. |
| Pitch angle | B/T, `Vmax` | Bigger bulges and faster rotation (more shear) wind the arms tighter. |
| Flocculence | `ColdGas` / (`ColdGas` + `StellarMass`), `StellarMass` | Gas-rich, low-mass disks are patchier within their arm class. |
| Clumpy disk | redshift, `ColdGas`, `FFBRegime` | Gas-rich disks at z ≳ 1 become clumpy and turbulent instead of spiral, with probability rising with z and gas fraction. FFB galaxies always do. Clumps (4–12) are drawn diffuse and blend into the disk. |

## Star formation

| Component | SAGE26 fields | How |
|---|---|---|
| Young (blue) light | `SfrDisk`, disk mass | Scales with the disk's specific SFR as (sSFR / 10⁻¹⁰)^0.7. FFB galaxies are bluer still. |
| Young star clusters | `SfrDisk` | Their number scales as SFR^0.5 (400–20,000). They follow the young-light map. |
| HII regions | `H2gas`, `SfrDiskZ` | Their number scales with the H₂ reservoir. Their colour runs from metal-poor to metal-rich with the star-forming gas's metallicity. |
| Nuclear ring | `SfrBulge`, `SfrDisk` | A ring of clusters and dust appears when the bulge forms more than 8% of all stars (with SfrBulge > 0.05 M☉/yr). It sits just inside the bar ends. |
| Gas-disk truncation (satellites) | `Type`, `TimeOfInfall`, `Mvir`, `infallMvir` | Satellites lose their outer gas disk the longer since infall and the more of their subhalo they have lost. Star formation stops beyond the cut. |

## Dust

| Component | SAGE26 fields | How |
|---|---|---|
| Disk dust | `H2gas`, `H1gas`, `MetalsColdGas`, `ColdGas` | Face-on optical depth ∝ (Σ_H₂ + 0.4 Σ_HI) × gas metallicity. It follows the arms and the H₂, and reddens what it dims. |
| Elliptical dust lane | `H2gas` | A nuclear lane in ellipticals that hold molecular gas. |

## Nucleus

| Component | SAGE26 fields | How |
|---|---|---|
| Nucleus | `BlackHoleMass`, `BulgeMass` | Brightness and compactness grow with black-hole mass (relative to the bulge, for ellipticals). |
| AGN point source | `QuasarModeBHaccretionMass` | Quasar-mode accretion this snapshot adds a bright, bluish point. |

## Merger debris and the intracluster light

| Component | SAGE26 fields | How |
|---|---|---|
| Shells (ellipticals) or tidal tails (disks) | `TimeOfLastMajorMerger` | A major merger in the last 4 Gyr leaves debris that fades with time. |
| Stellar stream | `TimeOfLastMinorMerger` | A minor merger in the last 2.5 Gyr leaves a stream. |
| Intracluster light (ICL) | `IntraClusterStars`, `MetalsIntraClusterStars`, `Rvir` | A faint, extended envelope (scale ~0.12 Rvir), brighter with ICS / M\*. Its colour follows the ICS metallicity. |
| Streams feeding the ICL | `ICS_disrupt` | Visible when satellites torn apart into the ICL exceed ~10^10.5 M☉. |

## Halo gas (the Gas button)

| Component | SAGE26 fields | How |
|---|---|---|
| CGM and cold streams | `CGMgas`, `MetalsCGMgas` | Cold-regime haloes. Three curling streams plus filaments out to Rvir, brighter with log CGMgas, tinted by its metallicity. |
| Cold streams into a hot halo | `mdot_stream`, `HotGas` | Hot haloes still fed by cold streams draw them by mdot_stream. |
| Hot halo / intracluster medium | `HotGas`, `MetalsHotGas`, `Rvir` | A textured atmosphere to Rvir. Its opacity rises with log HotGas, and its colour is tinted by metallicity. |
| X-ray cavities | `Heating`, `r_heat`, `Regime`, `HotGas` | Bubbles at the radio-heating radius r_heat, along the jet axis, in hot haloes with radio heating. |
| Radio jets | `Heating` | Jets and lobes along the spin axis, longer and brighter with radio-mode heating. |
| Galactic winds | `OutflowRate`, `MassLoading`, `EjectedMass` | A bipolar cone that is brighter with the outflow rate. MassLoading sets its opening angle (20–45°). It reaches further the more of the halo gas has been ejected. |
| Hα cooling filaments | `mdot_cool`, `RcoolToRvir`, `r_heat`, `tcool`, `tff`, `Mvir` | In hot haloes above 10¹² M☉ that are still cooling, gas rains out into filaments. Still cooling means a cooling radius at least 30% beyond r_heat, or t_cool/t_ff ≲ 6. These are brighter with mdot_cool and reach at most 0.8 r_heat. |

## Environment (groups, pairs, satellites)

| Component | SAGE26 fields | How |
|---|---|---|
| Group members | `CentralGalaxyIndex`, `Type`, `Pos*` | Every member of the FOF group is drawn at its own position, magnified to its normal-view size (at most 5×). A galaxy alone in its halo is drawn at true size. |
| Spin and orientation | `Spinx`, `Spiny`, `Spinz` | Each disk's plane is set by its spin vector. |
| Neighbours | `Pos*`, `StellarMass` | The 16 most massive galaxies (M\* > 10⁹ M☉) within 1.5 Mpc/h are drawn in HD. Everything within 12 Mpc/h is drawn as glows: blue if sSFR > 10⁻¹¹ yr⁻¹, otherwise orange. |
| Tidal bridges and tails | `Pos*`, `StellarMass`, `Vel*`, `Spin*` | Neighbours within 100 kpc with mass ratio above 1:10 raise tidal features. These are stronger the closer and more massive the neighbour, and weaker (×0.6) for retrograde encounters. |
| Merger about to happen | `mergeType` | A galaxy SAGE merges before the next snapshot interacts with the nearest more massive galaxy, at a strength set by the merger type. |
| Jellyfish (ram-pressure) tail | `Vel*`, `Pos*`, `HotGas` (host), `Rvir` (host), `StellarMass`, `ColdGas`, `DiskRadius` | The strength is ρ_ICM v² against the disk's restoring force (Σ\* Σ_gas). It is calibrated on SAGE26 so that about 27% of satellites in hot haloes get a tail and about 1% a full one. The tail is a pink Hα streamer with blue knots, trailing the motion. It is brightened to undo the group's shared exposure, and ram pressure also strips up to half the satellite's CGM. |
| Tidal stripping (satellites) | `Mvir`, `infallMvir` | A satellite that has lost more than 65% of its infall subhalo mass sheds stars into tidal streams. |

## Fields not used for visuals

`Concentration`, `ICS_accrete` and `infallStellarMass` are read but don't change the picture. `Cooling` is used only by the offline prototype in `scripts/hd_galaxy`.
