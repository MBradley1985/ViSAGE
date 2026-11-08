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
| Size | `DiskRadius`, `BulgeRadius`, `StellarMass`, snapshot redshift, `FFBRegime` | SAGE26's own sizes: the disk is an exponential of scale length `DiskRadius` (Mo, Mao & White 1998), so its half-light radius is 1.68 × `DiskRadius`, as observers measure; bulges and ellipticals are drawn at `BulgeRadius` (a 3D half-mass radius; projected Re = 0.752 of it for a Hernquist profile), the elliptical's two-component profile scaled so its projected half-light radius matches. Without them, the Shen et al. (2003) size–mass relations, smaller in the past (van der Wel et al. 2014: late types (1+z)^−0.75, early types (1+z)^−1.48). |
| Disk thickness | `DiskRadius`, redshift | From the disk's size, as measured edge-on (Bershady et al. 2010, from Kregel et al. 2002: log(hR/hz) = 0.367 log(hR/kpc) + 0.708): smaller disks are relatively thicker. High-z (turbulent) disks are thicker still, by (1 + 0.5z) to z = 3. Dwarf irregulars are thick (intrinsic b/a ~ 0.3–0.4: Roychowdhury et al. 2013). With DarkSAGE, the stellar dispersion sets it (below). |
| Thick disc | `Vmax` (or DarkSAGE's disc rotation) | A share of the old disc's light in a thick disc 2.5 times the thin disc's height (2–3 times: Yoachim & Dalcanton 2006): 0.2 in disks rotating above 150 km/s, rising to 0.6 below 80 km/s (Comerón et al. 2011). |
| Elliptical shape | `StellarMass`, `TimeOfLastMajorMerger` | Fast rotators (flattened, c/a 0.3–0.5) below ~2×10¹¹ M☉, slow rotators (round, triaxial) above it (Emsellem et al. 2011; Cappellari 2016); a recent major merger makes a slow rotator likelier. More massive ellipticals have more extended (cD-like) envelopes. |
| Classical bulge | `BulgeMass`, `BulgeRadius`, `MergerBulgeMass` | `BulgeMass` and `BulgeRadius` are the whole bulge (merger + instability parts, mass-weighted radius); the merger part's share is the classical bulge, a round Hernquist profile at `BulgeRadius`. |
| Pseudo-bulge | `BulgeMass`, `BulgeRadius`, `InstabilityBulgeMass` | The instability part's share of the bulge: a flattened exponential (Sérsic n ~ 1, q = 0.45), as pseudo-bulges are (Kormendy & Kennicutt 2004), at `BulgeRadius`. |
| Bar | `Vmax` (or DarkSAGE's disk rotation), disk stars (`StellarMass` − `BulgeMass`), `DiskRadius`, B/T | Barred where the stellar disk is unstable to a bar: ε = Vmax / √(G M_disk / Rd) < 1.1 (Efstathiou, Lake & Negroponte 1982), stronger the further below. Up to 8% of M\* in the bar; half-length 0.6–1.4 Rd from late to early types (Erwin 2005), thinner the stronger (b/a 0.5–0.2). The bar's light fades out by 1.25 bar lengths. Gas-rich disks, with fewer stars for their size, are barred less often, as observed (Masters et al. 2012). |
| Old stellar colour | `MetalsStellarMass`, `MetalsBulgeMass` | The disk and bulge are each tinted by their own stars' metallicity: metal-rich is redder. |
| Stellar populations by age | `SFHMassDisk`, `SFHMassBulge` (with SAGE's `SaveFullSFH 1`) | The disk's and the bulge's histories are summed as populations of known age: each population's colour and light per unit mass follow its age (younger: bluer, brighter), with metallicity still tinting them. A recently quenched (post-starburst) galaxy turns white-blue with no HII regions, a rejuvenated bulge turns blue, and 0.1–1 Gyr-old star clusters spread through the disk. Without a saved history, colours come from metallicity alone. |
| Brightness | `StellarMass`, `BulgeMass` | Brightness ∝ M\*^0.35, the disk's stars plus its bulge at old-star light per unit mass (as an elliptical's). Every member of a group shares one exposure, at its true brightness against the others. HD's exposure lifts faint light (merger debris, streams, intracluster light) a little, as moderately deep imaging does. |

## Spiral structure

| Component | SAGE26 fields | How |
|---|---|---|
| Arm class: grand-design, multi-arm, partial, flocculent or irregular | `StellarMass`, `ColdGas`, bar | Drawn from probabilities set by mass, gas fraction and whether the disk is barred. Gas-rich dwarfs (below 10^9.5 M☉, gas fraction > 0.15) are irregulars: no spiral arms, patchy star formation in large complexes (more with more star formation: Hunter & Elmegreen 2004), lopsided (Zaritsky et al. 2013) and thick. Disks with no star formation are lenticulars (S0): smooth, no arms. |
| Irregular types | bar, `TimeOfLastMinorMerger`, `Type`, `TimeOfInfall`, sSFR | **Magellanic barred** if barred: an off-centre bar (de Vaucouleurs & Freeman 1972) and one arm. **Disturbed** after a minor merger within 1.5 Gyr / (1+z) or within 1.5 Gyr of infall: elongated. Otherwise by sSFR: **starburst** above 10^−9.7 yr⁻¹ (3–6 compact bright complexes), **fading** below 10^−10.7 (1–3 faint ones), **patchy clouds** between (6–12). With DarkSAGE the complexes are placed by the annuli's star formation and sized by Toomre Q. |
| Lenticular types | `ColdDust` (or ~1% of the cold gas at its metallicity), `H2gas`, merger times, bar, DarkSAGE's gas tilt | A lenticular with dust (above 10⁵ M☉, or 10⁷ M☉ of H₂) shows it: a **disturbed dust** sheet, tilted 20–50° to the stars, after a merger (minor within 1.5 Gyr / (1+z), major within 2 Gyr) or where DarkSAGE's gas disc is tilted more than 30° from its stars; else a **dust lane** above 3×10⁶ M☉ of dust, a **nuclear dust ring** below. Without dust, **barred** (a lens round the bar and inner and outer rings at 1 and 2.2 bar lengths: Kormendy 1979; Buta & Combes 1996) or **smooth**. The dust is its mass, gathered where its type puts it. |
| Flocculent types | `StellarMass`, sSFR | Many short arcs (18–30) rather than arms (Elmegreen & Elmegreen 1987): **massive** above 10^10.3 M☉ (25–40 arcs, a bigger bulge), **fading** below an sSFR of 10^−11.5 yr⁻¹, else **star-forming**. |
| Pitch angle | `BlackHoleMass` (or DarkSAGE's rotation curve) | From the black hole: log M_BH = 7.01 − 0.171 (\|φ\| − 15°) (Davis et al. 2017), with ~3° scatter, 5–40°. With DarkSAGE, from the disk's shear (Seigar et al. 2006). Without a black hole yet, tighter with a bigger bulge. |
| Flocculence | `ColdGas` / (`ColdGas` + `StellarMass`), `StellarMass` | Gas-rich, low-mass disks are patchier within their arm class. |
| Clumpy disk | redshift, `ColdGas`, `StellarMass`, `FFBRegime` | Clumpy star-forming disks in ~60% of gas-rich galaxies at z ~ 2, fewer at higher mass and few below z ~ 0.5 (Guo et al. 2015); a feedback-free starburst always is. No spiral arms. |

## Star formation

| Component | SAGE26 fields | How |
|---|---|---|
| Young (blue) light | `SfrDisk`, disk mass | Scales with the disk's specific SFR as (sSFR / 10⁻¹⁰)^0.7. FFB galaxies are bluer still. |
| Young star clusters | `SfrDisk` | Their number scales as SFR^0.5 (none without star formation). They follow the young-light map. |
| HII regions | `H2gas`, `SfrDisk`, `DiskRadius`, `ColdGas`, `SfrDiskZ` | Star-forming complexes along the arms, in number following the H₂ reservoir: small crisp knots (the glowing gas round them is the disc's ionised gas, drawn with Gas). Each complex is richer the denser the star formation (SFR surface density) and bigger the more gas-rich the disk. Each complex's colour runs from pink (metal-poor gas) to orange (metal-rich): the galaxy's star-forming gas metallicity sets which dominates (dwarfs pinker, massive disks oranger), an abundance gradient makes the inner disk oranger and the outer disk pinker (about −0.1 dex per effective radius; Sánchez et al. 2014), and each region scatters about that. |
| Nuclear ring | bar strength, `H2gas`, `SfrBulge`, `SfrDisk` | A star-forming ring at the bar's inner Lindblad resonance, in strongly barred disks with molecular gas (~20% of disks: Comerón et al. 2010), brighter with the bulge's share of the star formation. |
| Gas-disk truncation (satellites) | `Type`, `TimeOfInfall`, `Mvir`, `infallMvir` | Satellites lose their outer gas disk the longer since infall and the more of their subhalo they have lost. Star formation stops beyond the cut. |

## Dust

| Component | SAGE26 fields | How |
|---|---|---|
| Disk dust | `H2gas`, `H1gas`, `MetalsColdGas`, `ColdGas`, `DiskRadius`, `Vmax` | Dust follows the hydrogen at the Milky Way's dust per hydrogen, A_V/N_H = 5.3×10⁻²² mag cm² (Bohlin et al. 1978: τ_V = 0.061 per M☉ pc⁻²), times the gas metallicity (SAGE26's Z / 0.02), falling faster below a quarter solar (Rémy-Ruyer et al. 2014). Each gas phase carries its share. Thin dark lanes only in disks rotating faster than ~120 km/s (Dalcanton et al. 2004), dimming what lies behind them. The dust layer is half as thick as the stars (Xilouris et al. 1999), and stars inside the disk are dimmed by the dust in front of them, so edge-on disks show their midplane lane. No place in a disk is given a face-on optical depth above 5 (its 99th percentile; arms reach ~1–2 and centres a few: Holwerda et al. 2005). |
| Elliptical dust | `H2gas` (or DustySAGE's `ColdDust`) | In ellipticals that hold molecular gas or dust, a nuclear lane and irregular dark filaments through the core: about four in ten ellipticals show dust, as discs, lanes, filaments and patches (van Dokkum & Franx 1995; Tran et al. 2001; Lauer et al. 2005). |

## Nucleus

| Component | SAGE26 fields | How |
|---|---|---|
| Nucleus | `BlackHoleMass`, `BulgeMass` | Brightness and compactness grow with black-hole mass (relative to the bulge, for ellipticals). |
| AGN point source | `QuasarModeBHaccretionMass`, the snapshot's time step | The mean quasar-mode accretion rate over the step at a radiative efficiency of 0.1 (L = 0.1 Ṁc²), a tenth in the optical (Elvis et al. 1994), against the host's light (M/L ~ 2). |

## Merger debris and the intracluster light

| Component | SAGE26 fields | How |
|---|---|---|
| Tidal tails, then shells | `TimeOfLastMajorMerger`, redshift | SAGE26 writes it as the merger's lookback time from z = 0 (in Myr/h); HD takes the time since the merger at the galaxy's own epoch. A major merger throws out tidal tails (Toomre & Toomre 1972) for its first ~1.5 Gyr, then the remnant shows shells; the debris fades over 4 Gyr / (1+z). Just after a merger the tails carry ~10% of the galaxy's light and shells up to ~6%. |
| Shells or a stream (minor merger) | `TimeOfLastMinorMerger`, B/T, redshift | A minor merger leaves shells round a bulge-dominated host (Quinn 1984), a stream round a disk, fading over 2.5 Gyr / (1+z). |
| Intracluster light (ICL) | `IntraClusterStars`, `MetalsIntraClusterStars`, `Rvir` | A faint envelope as bright as SAGE26's ICS against the galaxy's own stars (both old), spread over the halo; it fades out smoothly at its edge. |

## Gas in the disc (the Gas button)

| Component | SAGE26 fields | How |
|---|---|---|
| Ionised gas | `SfrDisk`, `H2gas` | Glowing H-alpha clouds and filaments (the ridges of a random field) round where the stars form, spread a little beyond it, in the HII regions' colour, at 1.5 times the young light (more in starbursts, less in fading discs). |
| Molecular clouds | `H2gas`, the disc's dust | In optical light H₂ is seen by its dust: dark filaments across the disc where the H₂ is, as dust lanes cross real discs, within the same face-on optical depth of 5. |

Both are drawn inside the disk with its stars and dust. With Gas off, HD draws the optical galaxy alone.

## Halo gas (the Gas button)

| Component | SAGE26 fields | How |
|---|---|---|
| CGM and cold streams | `CGMgas`, `MetalsCGMgas`, `mdot_stream`, redshift, neighbouring haloes | The CGM glows smooth and filamentary from `CGMgas`, its brightness set over the whole halo and thinned over the galaxy, as the hot halo is; cold streams run through it only where SAGE26 has inflow (`mdot_stream`, in M☉/yr: 1 to 1000; ~100 into 10¹² M☉ haloes at z ~ 2.5, Dekel et al. 2009), as SAGE26 itself has inflow only at high z and below the shock mass (Dekel & Birnboim 2006). |
| Cold streams into a hot halo | `mdot_stream`, `HotGas` | Hot haloes still fed by cold streams draw them by mdot_stream, aimed and scaled with redshift as above. |
| Hot halo / intracluster medium | `HotGas`, `Vvir`, `Rvir`, `Mvir`, `Concentration`, `MetalsHotGas` | A textured atmosphere to Rvir, its brightness from its bremsstrahlung X-ray luminosity (1.4×10⁻²⁷ T^0.5 n² V, T = 35.9 Vvir² K, `HotGas` at its mean density within Rvir): 10³⁹ to 10^44.5 erg/s, the ~4 dex observed from galaxies to clusters (e.g. Anderson et al. 2015). |
| X-ray cavities | `Heating`, `r_heat`, `Regime`, `HotGas` | Bubbles at the radio-heating radius r_heat, along the jet axis, in hot haloes with radio heating. |
| Radio jets | `RadioModeBHaccretionMass` (`RadioModeBHaccretionMassUncapped` as a fallback), the snapshot's time step, `r_heat`, `Rvir`; for satellites the host's `HotGas` and `Rvir`, positions and velocities | Jets in radio-loud AGN, from 10⁴² erg/s of jet power (0.1 Ṁc² this step; Best & Heckman 2012; Cavagnolo et al. 2010), brightest at 10⁴⁴·⁵, reaching about 0.6 of the radius the AGN heats. The capped accretion sets the power; the uncapped one stands in only for a snapshot with no radio-loud galaxy of its own (runs before SAGE26's radio-mode update). **Shape:** below the FR break (~10⁴⁴ erg/s) FR I plumes, brightest near the core; above it a jet carrying its light to edge-brightened FR II lobes ending in hotspots (Fanaroff & Riley 1974; Scheuer 1974; Rawlings & Saunders 1991); the plume starts clear of the core. **Beaming:** the jets, not the lobes, are brighter toward us and fainter away by ((1 + β cos θ)/(1 − β cos θ))^(2+α), β 0.8 → 0.2 in FR I (Laing & Bridle 2002), 0.6 in FR II (Wardle & Aaron 1997), α 0.6; the approaching lobe looks longer, its hotspot advancing at 0.1 c (Longair & Riley 1979). **Bending:** a satellite's jets curve back along its motion through its host's hot gas (the cored isothermal ICM used for jellyfish), with radius (P_jet/c)/(ρv² · 2r_j), r_j 0.5 kpc (Begelman, Rees & Blandford 1979; Jones & Owen 1979), into narrow-angle tails (Owen & Rudnick 1976); centrals stay straight. **Colour:** blue, purple, red and fiery patches, more fiery the stronger the jet. **Gas off:** only the inner optical jet, blue-white. |
| Galactic winds | `OutflowRate`, `SfrDisk`, `SfrBulge`, `DiskRadius`, `MassLoading`, `Vmax`, `EjectedMass` | A bipolar cone from SAGE26's `OutflowRate` (1 to 1000 M☉/yr), only where star formation is concentrated enough to drive it: SFR surface density above ~0.1 M☉/yr/kpc² within the star-forming half-light radius (Heckman 2002). |
| Extended HI disk | `H1gas`, `H2gas`, `Type`, `TimeOfInfall` | A faint, clumpy, pale-blue gas disk well past the stars, sized by the HI size–mass relation (Wang et al. 2016), brighter with `H1gas` from 10⁷ M☉. |

## Environment (groups, pairs, satellites)

| Component | SAGE26 fields | How |
|---|---|---|
| Group members | `CentralGalaxyIndex`, `Type`, `Pos*` | Every member of the FOF group is drawn at its own position and real size. |
| Spin and orientation | `Spinx`, `Spiny`, `Spinz` | Each disk's plane is set by its spin vector. |
| Tidal bridges and tails | `Pos*`, `StellarMass`, `Vel*`, `Spin*`, redshift | Group members within 100 physical kpc of each other (positions are comoving) with mass ratio above 1:10 raise tidal features, weaker for fast fly-bys above ~300–500 km/s (Patton et al. 2013; Ellison et al. 2008). |
| Merger about to happen | `mergeType` | A galaxy SAGE merges before the next snapshot interacts with the nearest more massive galaxy, at a strength set by the merger type. |
| Jellyfish (ram-pressure) tail | `Vel*`, `Pos*`, `HotGas`, `Rvir` and `Regime` (host), `StellarMass`, `BulgeMass`, `ColdGas`, `DiskRadius`, `TimeOfInfall` | Ram-pressure stripping (Gunn & Gott 1972): the host's hot gas, a cored isothermal sphere (Cavaliere & Fusco-Femiano 1976), pushes at ρ v² against 2πG Σ\* Σ_gas of the disk, and the gas beyond where they balance is stripped. A satellite has a tail when it is drawn as a disk, fell in less than 1 Gyr ago, and more than 25% of its cold gas is being stripped, as observed jellyfish are disks on their first infall (Poggianti et al. 2016; Jaffé et al. 2018): on SAGE26 at z = 0, 15% of satellites in hot haloes. The tail trails the motion: threads of young stars off the disc with compact star-forming knots strung along them, blue and H-alpha magenta, a few long blue ones curling (JW100, JO206, JO201: Poggianti et al. 2017, 2019); and, with Gas, the stripped gas round them, drawn as HD draws the CGM, and eight long soft plumes of gas in a range of blues, twisting and fading out at their ends (ESO 137-001: Sun et al. 2006, 2010). How many threads follows the cold gas, how long the ram pressure and time since infall, the gas its gas fraction. It is brightened to undo the group's shared exposure, and ram pressure also strips up to half the satellite's CGM. |
| Tidal streams (stripped satellites) | `Mvir`, `infallMvir` | A satellite's stars are stripped only once ~90% of its dark matter is gone (Peñarrubia et al. 2008), so streams appear below 10% of its infall subhalo mass left. They curve along an arc of the orbit round the host, clumped along it (Küpper et al. 2012), and are faint: a few per cent of the galaxy's light. |

## DarkSAGE and DustySAGE

On these models' runs, HD replaces several of the estimates above with what the model itself computed. On any other model nothing changes.

| Component | Fields | How |
|---|---|---|
| Disc size (DarkSAGE) | `DiskRadius`, `StellarDiscScaleRadius` | The disc is drawn at `DiskRadius`, its physical size; the annuli, whose own scale radius is much smaller (the annulus discs are compact), are stretched to it and give only its shape. |
| Disc profiles (DarkSAGE) | The radial stars, HI, H₂ and star-formation arrays | Older stars, HI, H₂ and young stars each follow their own surface-density profile in place of an exponential, falling away beyond the last annulus that has any. |
| Disc rotation and shear (DarkSAGE) | `DiscVcirc`, `DiskRadius` | The disk's own rotation at 2.2 `DiskRadius` (the disc's physical size; the annuli's own scale radius is much smaller) replaces the halo's Vmax for dust lanes and the bar's stability test, and its shear sets the pitch angle (Seigar et al. 2006). |
| Disc thickness (DarkSAGE) | the stellar dispersion, `StellarDiscHalfMassRadius` | σ² / (π G Σ) at the half-mass radius, a self-gravitating isothermal sheet (Spitzer 1942). |
| Gas disc tilt (DarkSAGE) | `SpinGas`, `SpinStars` | The angle between the gas and stellar discs: a lenticular's dust tilted more than 30° is drawn as a disturbed, tilted sheet. |
| Dust (DustySAGE, without annuli) | `ColdDust`, `DiskRadius` | The same Milky Way opacity as without it, per unit of DustySAGE's own dust mass (dust / H = 0.010: Draine 2011) instead of from metallicity: the same picture where the dust follows the metals, different where DustySAGE says so. |
| Disc dust (DarkSAGE, with or without DustySAGE) | `DiscDust`, or `DiscGas` with the galaxy's dust-to-gas ratio; `DiscStars`, `BulgeMass`, `BulgeRadius` | As the [photometry](photometry.md) finds it: each annulus a screen of its own dust (DustySAGE's `DiscDust`, else the photometry's dust-to-gas ratio for the galaxy times the annulus's gas), weighted by its share of the old stars, bulge included: τ = −ln Σ share e^−τ. HD's dust map keeps its shape from the annuli and is scaled so that its own star-weighted face-on screen is this τ, in a box as on a lightcone. |
| Halo dust (DustySAGE) | `HotDust`, `CGMDust`, `Rvir` | Reddens the hot gas and CGM by their mean dust column over the halo. |

## Fields not used for visuals

`Concentration`, `ICS_accrete` and `infallStellarMass` are read but don't change the picture. `Cooling` was used only by an early offline prototype.
