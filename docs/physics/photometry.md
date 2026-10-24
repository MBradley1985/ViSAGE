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
- **Birth clouds:** stars younger than 10 Myr are also behind their birth cloud, of optical depth τ<sub>ISM</sub>(1 − μ<sub>CF</sub>)/μ<sub>CF</sub> with μ<sub>CF</sub> = 0.3, τ<sub>λ</sub> ∝ λ<sup>−1.3</sup>.

## Not included (yet)

Nebular emission lines, IGM absorption (irrelevant below *z* ≈ 2), dust emission with this dust model, and separate disk and bulge magnitudes.

## References

- Asano R. S. et al. 2013, *Earth, Planets and Space* 65, 213
- Bohlin R. C., Savage B. D., Drake J. F. 1978, *ApJ* 224, 132
- Chabrier G. 2003, *PASP* 115, 763
- Charlot S., Fall S. M. 2000, *ApJ* 539, 718
- Conroy C., Gunn J. E., White M. 2009, *ApJ* 699, 486; Conroy C., Gunn J. E. 2010, *ApJ* 712, 833
- Davis T. M. et al. 2011, *ApJ* 741, 67
- Draine B. T., Li A. 2007, *ApJ* 657, 810
- Leroy A. K. et al. 2008, *AJ* 136, 2782
- Popping G., Somerville R. S., Galametz M. 2017, *MNRAS* 471, 3152
- Shamshiri S. et al. 2015, *MNRAS* 451, 2681
- Triani D. P. et al. 2020, *MNRAS* 493, 2490
- Tsai J. C., Mathews W. G. 1995, *ApJ* 448, 84
- Wang J. et al. 2016, *MNRAS* 460, 2143
