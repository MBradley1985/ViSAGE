# Lightcone Photometry

The LightSAGE flow's photometry stage (`python -m visage.sed.photometry`) gives every galaxy in a lightcone the magnitudes an observer would measure, built forward from its own SAGE26 star-formation history. The settings used are recorded in the file's `PhotometryHeader` attributes.

## Stellar light

| Step | How |
|---|---|
| Stellar populations | FSPS (Conroy, Gunn & White 2009; Conroy & Gunn 2010) with MIST isochrones and MILES spectra, Chabrier (2003) IMF, as SAGE26 assumes. |
| Star-formation history | SAGE26 files the stars formed between snapshots *k* and *k*+1 in bin *k*, as the mass that survives recycling. Each bin is turned back into the mass formed, ÷ (1 − *R*) with the run's `RecycleFraction`, and spread at a constant rate over its own time span by integrating the populations over age (as TAO does: Shamshiri et al. 2015). |
| Youngest stars | The last 100 Myr come from the galaxy's current SFR (`SfrDisk` + `SfrBulge`), not the last bin spread evenly over its 0.3–0.6 Gyr. |
| Metallicity | One present-day value per galaxy, `MetalsStellarMass` / `StellarMass`; the spectrum is interpolated in log *Z* between population nodes. SAGE26 doesn't keep a metallicity history. |

## Observed magnitudes

| Step | How |
|---|---|
| Redshifting | The filter is shifted onto the rest-frame spectrum at each galaxy's own observed redshift (K-correction), photon-counting AB magnitudes. |
| Distance | *D*<sub>L</sub> = (1 + *z*<sub>obs</sub>) *D*<sub>C</sub>(*z*<sub>cos</sub>), so peculiar velocities count (Davis et al. 2011). |
| Absolute magnitudes | Rest frame, at 10 pc. |

## Dust (`--dust-model charlot_fall`)

**How much dust.** Dusty-SAGE's dust model (Triani et al. 2020), solved for each galaxy's steady state from its SAGE26 cold gas, metals, H₂ and SFR. It is solved for the dust-to-metal ratio μ: gas inflow, outflows and locking into new stars move dust and metals together, so they cancel.

0 = *Y* (δ<sub>c</sub> − μ) − η *m*<sub>swept</sub>(*Z*) *N*<sub>SN</sub> *Z* μ + *t*<sub>dep</sub> *Z* (*f*<sub>H₂</sub> / τ<sub>acc</sub>) μ (1 − 2μ) / (1 − μ)

| Term | Source |
|---|---|
| Stars: new metals *Y* (the run's `Yield`), a share δ<sub>c</sub> = 0.2 condensed into dust | Dusty-SAGE, after Popping et al. (2017) |
| Supernova destruction: η = 0.1 of the swept mass, *m*<sub>swept</sub> = 1535 (*Z*/0.02 + 0.039)<sup>−0.289</sup> M☉ per SN; SNe per mass formed from the Chabrier IMF (8–40 M☉) | Asano et al. (2013) |
| Grain growth in molecular clouds, τ<sub>acc</sub> = 20 Myr × 0.02/*Z*, stopping at μ = ½ | Asano et al. (2013) |

Metal-poor gas ends near μ = δ<sub>c</sub> and metal-rich gas near ½, the critical-metallicity behaviour of Asano et al. (2013). Dust in hot gas and the CGM is sputtered (Tsai & Mathews 1995) and its column is far below the disk's, so it isn't included.

**Where the dust is.** The molecular gas follows the stars (Leroy et al. 2008). The atomic gas sits in its own exponential disk sized by the HI size–mass relation (Wang et al. 2016). The optical depth in front of the starlight is the mean hydrogen column inside the stellar half-light radius, with the Milky Way's *A*<sub>V</sub>/*N*<sub>H</sub> (Bohlin, Savage & Drake 1978; *R*<sub>V</sub> = 3.1) scaled by the galaxy's dust per hydrogen over the Milky Way's 0.010 (Draine & Li 2007).

**How it dims the light** (Charlot & Fall 2000):

- **Diffuse ISM:** dust mixed with the stars in a slab seen at the galaxy's inclination (its spin against the line of sight), τ<sub>λ</sub> ∝ λ<sup>−0.7</sup>.
- **Birth clouds:** stars younger than 10 Myr are also behind their birth cloud, of optical depth τ<sub>ISM</sub>(1 − μ<sub>CF</sub>)/μ<sub>CF</sub> with μ<sub>CF</sub> = 0.3, τ<sub>λ</sub> ∝ λ<sup>−1.3</sup> (da Cunha, Charlot & Elbaz 2008; Charlot & Fall used λ<sup>−0.7</sup> for both).

**Where the absorbed light goes** (`--dust-emission`). Each galaxy re-emits exactly the starlight its dust absorbed (energy balance, as in da Cunha et al. 2008), with the Draine & Li (2007) dust-emission spectrum FSPS uses (its default *U*<sub>min</sub> = 1, γ = 0.01, *q*<sub>PAH</sub> = 3.5 %). `LDust` is the total.

## Disk and bulge (`--disk-bulge`)

`disk_mag_*` and `bulge_mag_*` are built from each component's own star-formation history and current SFR, through the same dust. SAGE26's `SFHMassBulge` holds only the stars formed in bulge starbursts: the disk stars that mergers and disk instabilities move into the bulge stay in `SFHMassDisk`. So the share of the disk's history that makes the bulge's total equal its `BulgeMass` is moved into the bulge, taking those stars to have the disk's age mix.

## Emission lines (`--lines`)

[OII] 3727, Hβ, [OIII] 5007, Hα, [NII] 6584 and [SII] 6716+6731: `LineLum_*` (erg/s, through the dust), `LineLumIntr_*` (no dust), `LineLumAGN_*` (the AGN's share, no dust) and `LineFlux_*` (erg/s/cm², observed).

**HII regions.** Lines from the star-forming nebular models of Gutkin, Charlot & Bruzual (2016): Bruzual & Charlot stellar populations through Cloudy, for a Chabrier IMF and constant star formation over 100 Myr, given per unit SFR. They are the companions of the AGN models below and are coupled to each galaxy the same way (Hirschmann et al. 2017). Each galaxy's lines are its current SFR times the grid at:

- the cold gas's metallicity;
- the ionisation parameter of SDSS galaxies with its specific SFR, metallicity and density (Kashino & Inoue 2019, eq. 5), with O/H from the solar 12 + log O/H = 8.69 (Asplund et al. 2009);
- the electron density from their eq. 3 (within the grid's 100–1000 cm⁻³);
- dust-to-metal ratio 0.3 and solar C/O, the models' fiducial values.

The lines pass through the birth cloud and the diffuse ISM. The FSPS spectra used for the magnitudes include FSPS's own nebular lines and continuum (Byler et al. 2017), for each metallicity node at a main-sequence galaxy's ionisation parameter.

**AGN.** SAGE26's black holes accrete in quasar mode (`QuasarModeBHaccretionMass` over the snapshot step `dT`) and radio mode (`Heating` = η*Ṁc*², η = 0.1). Their luminosity is η*Ṁc*² above 1 % of Eddington and falls as *ṁ*² below it, where the flow becomes radiatively inefficient (Narayan & Yi 1995; Merloni & Heinz 2008). The narrow-line region uses the photoionisation models of Feltre, Charlot & Gutkin (2016), coupled to each galaxy as Hirschmann et al. (2017) do: an ionising spectrum *S*<sub>ν</sub> ∝ ν<sup>−1.7</sup>, gas clumps of *n*<sub>H</sub> = 10³ cm⁻³, dust-to-metal ratio 0.3, the cold gas's metallicity, and the ionisation parameter at the Strömgren radius from the AGN's ionising photons and the filling factor of the cold gas within 1 kpc. The lines pass through half the disk's dust, as a screen. `LAGN`, `EddingtonRatio`, `LogU_HII` and `LogU_AGN` are written too.

## Not included (yet)

- IGM absorption (irrelevant below *z* ≈ 2).
- The AGN's own continuum in the magnitudes (its lines aren't in the broad bands either).
- Line emission from old (post-AGB) stars, which powers many LINER-like spectra in quiescent galaxies.

## References

- Asano R. S. et al. 2013, *Earth, Planets and Space* 65, 213
- Asplund M. et al. 2009, *ARA&A* 47, 481
- Bohlin R. C., Savage B. D., Drake J. F. 1978, *ApJ* 224, 132
- Byler N. et al. 2017, *ApJ* 840, 44
- Chabrier G. 2003, *PASP* 115, 763
- Charlot S., Fall S. M. 2000, *ApJ* 539, 718
- da Cunha E., Charlot S., Elbaz D. 2008, *MNRAS* 388, 1595
- Conroy C., Gunn J. E., White M. 2009, *ApJ* 699, 486; Conroy C., Gunn J. E. 2010, *ApJ* 712, 833
- Davis T. M. et al. 2011, *ApJ* 741, 67
- Draine B. T., Li A. 2007, *ApJ* 657, 810
- Feltre A., Charlot S., Gutkin J. 2016, *MNRAS* 456, 3354
- Gutkin J., Charlot S., Bruzual G. 2016, *MNRAS* 462, 1757
- Hirschmann M. et al. 2017, *MNRAS* 472, 2468
- Kashino D., Inoue A. K. 2019, *MNRAS* 486, 1053
- Leroy A. K. et al. 2008, *AJ* 136, 2782
- Merloni A., Heinz S. 2008, *MNRAS* 388, 1011
- Narayan R., Yi I. 1995, *ApJ* 452, 710
- Popping G., Somerville R. S., Galametz M. 2017, *MNRAS* 471, 3152
- Shamshiri S. et al. 2015, *MNRAS* 451, 2681
- Triani D. P. et al. 2020, *MNRAS* 493, 2490
- Tsai J. C., Mathews W. G. 1995, *ApJ* 448, 84
- Wang J. et al. 2016, *MNRAS* 460, 2143
