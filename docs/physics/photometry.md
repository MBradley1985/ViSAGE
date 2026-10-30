# Lightcone Photometry

The LightSAGE flow's photometry stage (`python -m visage.sed.photometry`) gives every galaxy in a lightcone the magnitudes an observer would measure, built forward from its own SAGE26 star-formation history. The settings used are recorded in the file's `PhotometryHeader` attributes.

## Stellar light

| Step | How |
|---|---|
| Stellar populations | FSPS (Conroy, Gunn & White 2009; Conroy & Gunn 2010) with MIST isochrones and MILES spectra, Chabrier (2003) IMF, as SAGE26 assumes. |
| Star-formation history | SAGE26 files the stars formed between snapshots *k*−1 and *k* in bin *k* (outputs from before its snapshot-lag fix, *k* and *k*+1; read from the file), as the mass that survives recycling. Each bin is turned back into the mass formed, ÷ (1 − *R*) with the run's `RecycleFraction`, and spread at a constant rate over its own time span by integrating the populations over age (as TAO does: Shamshiri et al. 2015). |
| Youngest stars | The last 100 Myr come from the galaxy's current SFR (`SfrDisk` + `SfrBulge`), not the last bin spread evenly over its 0.3–0.6 Gyr. |
| Metallicity | One present-day value per galaxy, `MetalsStellarMass` / `StellarMass`; the spectrum is interpolated in log *Z* between population nodes. SAGE26 doesn't keep a metallicity history. |

## Observed magnitudes

| Step | How |
|---|---|
| Redshifting | The filter is shifted onto the rest-frame spectrum at each galaxy's own observed redshift (K-correction), photon-counting AB magnitudes. |
| Distance | *D*<sub>L</sub> = (1 + *z*<sub>obs</sub>) *D*<sub>C</sub>(*z*<sub>cos</sub>), so peculiar velocities count (Davis et al. 2011). |
| Intergalactic absorption | The mean Lyman-series and Lyman-continuum absorption of Madau (1995) on the observed frame. It matters where a band sees the rest-frame UV below 1216 Å, so mostly above *z* ≈ 2. |
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

**Where the dust is.** The molecular gas follows the stars (Leroy et al. 2008). The atomic gas sits in its own exponential disk sized by the HI size–mass relation (Wang et al. 2016); above *M*<sub>HI</sub> ≈ 10<sup>10.3</sup> M☉ no exponential disk reaches 1 M☉ pc⁻² at that size, so those disks take the scale length that comes closest. The optical depth in front of the starlight is the mean hydrogen column inside the stellar half-light radius, with the Milky Way's *A*<sub>V</sub>/*N*<sub>H</sub> (Bohlin, Savage & Drake 1978; *R*<sub>V</sub> = 3.1) scaled by the galaxy's dust per hydrogen over the Milky Way's 0.010 (Draine & Li 2007).

**How it dims the light** (Charlot & Fall 2000):

- **Diffuse ISM:** dust mixed with the stars in a slab seen at the galaxy's inclination (its spin against the line of sight), τ<sub>λ</sub> ∝ λ<sup>−0.7</sup>.
- **Birth clouds:** stars younger than 10 Myr are also behind their birth cloud, of optical depth τ<sub>ISM</sub>(1 − μ<sub>CF</sub>)/μ<sub>CF</sub> with μ<sub>CF</sub> = 0.3, τ<sub>λ</sub> ∝ λ<sup>−1.3</sup> (da Cunha, Charlot & Elbaz 2008; Charlot & Fall used λ<sup>−0.7</sup> for both).

**Where the absorbed light goes** (`--dust-emission`). Each galaxy re-emits exactly the starlight its dust absorbed (energy balance, as in da Cunha et al. 2008), with the Draine & Li (2007) dust-emission spectrum FSPS uses (γ = 0.01, *q*<sub>PAH</sub> = 3.5 %). Its *U*<sub>min</sub> comes from the galaxy's own light per unit dust mass, *L*<sub>dust</sub> = *P*<sub>0</sub> ⟨*U*⟩ *M*<sub>dust</sub> with *P*<sub>0</sub> ≈ 125 L☉ M☉⁻¹ (Magdis et al. 2012), within the models' 0.1–25, so more light on less dust is warmer. `LDust` is the total and `DustUmin` the *U*<sub>min</sub>.

## Disk and bulge (`--disk-bulge`)

`disk_mag_*` and `bulge_mag_*` are built from each component's own star-formation history and current SFR, through the same dust. In current SAGE26 outputs `SFHMassBulge` adds up to `BulgeMass`. In older ones it holds only the stars formed in bulge starbursts, with the disk stars that mergers and disk instabilities moved into the bulge still in `SFHMassDisk`; there, the share of the disk's history that makes the bulge's total equal its `BulgeMass` is moved into the bulge, taking those stars to have the disk's age mix.

## Emission lines (`--lines`)

[OII] 3727, Hβ, [OIII] 5007, Hα, [NII] 6584 and [SII] 6716+6731: `LineLum_*` (erg/s, through the dust), `LineLumIntr_*` (no dust), `LineLumAGN_*` (the AGN's share, no dust) and `LineFlux_*` (erg/s/cm², observed).

**HII regions.** Lines from the star-forming nebular models of Gutkin, Charlot & Bruzual (2016): Bruzual & Charlot stellar populations through Cloudy, for a Chabrier IMF and constant star formation over 100 Myr, given per unit SFR. They are the companions of the AGN models below and are coupled to each galaxy the same way (Hirschmann et al. 2017). Each galaxy's lines are its current SFR times the grid at:

- the cold gas's metallicity;
- the ionisation parameter of SDSS galaxies with its specific SFR, metallicity and density (Kashino & Inoue 2019, eq. 5), with O/H from the solar 12 + log O/H = 8.69 (Asplund et al. 2009);
- the electron density from their eq. 3 (within the grid's 100–1000 cm⁻³);
- dust-to-metal ratio 0.3 and solar C/O, the models' fiducial values.

The lines pass through the birth cloud and the diffuse ISM. The FSPS spectra used for the magnitudes include FSPS's own nebular lines and continuum (Byler et al. 2017), for each metallicity node at a main-sequence galaxy's ionisation parameter.

**AGN.** SAGE26's black holes accrete in quasar mode (`QuasarModeBHaccretionMass` over the snapshot step `dT`, which is in *h*⁻¹ Myr) and radio mode (`RadioModeBHaccretionMass` over the same step, or in older outputs its power `Heating` = η*Ṁc*², η = 0.1). SAGE26's black holes start at zero mass, so a dwarf's first merger or disk instability makes one of a tiny mass all at once; its Eddington ratio then reflects only the step's length (the card notes such a black hole), and its luminosity is negligible. Their luminosity is η*Ṁc*² above 1 % of Eddington and falls as *ṁ*² below it, where the flow becomes radiatively inefficient (Narayan & Yi 1995; Merloni & Heinz 2008). The narrow-line region uses the photoionisation models of Feltre, Charlot & Gutkin (2016), coupled to each galaxy as Hirschmann et al. (2017) do: an ionising spectrum *S*<sub>ν</sub> ∝ ν<sup>−1.7</sup>, gas clumps of *n*<sub>H</sub> = 10³ cm⁻³, dust-to-metal ratio 0.3, the cold gas's metallicity, and the ionisation parameter at the Strömgren radius from the AGN's ionising photons and the filling factor of the cold gas within 1 kpc. A galaxy with no cold gas has no narrow-line region. The lines pass through half the disk's dust, as a screen. `LAGN`, `EddingtonRatio`, `LogU_HII` and `LogU_AGN` are written too.

## Survey noise (`--noise`)

`flux_obs_*` and `fluxerr_obs_*` (µJy, in `visage/sed/noise.py`) are the fluxes a survey would catalogue, beside the noiseless magnitudes, for the bands of surveys with a quoted depth. It can also be run on an existing cone: `python -m visage.sed.noise --input <lightcone.h5>`.

Each band's sky noise is set so that a point source at the survey's limit has its quoted signal-to-noise. A galaxy covers more sky than a point source, so its error is that noise over a matched-filter area, 4π(σ<sub>PSF</sub>² + σ<sub>gal</sub>²), with σ<sub>gal</sub> from its half-light radius, plus a 1 % calibration floor in quadrature (Padmanabhan et al. 2008). Source shot noise isn't included. Noise is Gaussian in flux, so a faint galaxy's flux can be negative. Nothing is removed: a catalogue cut is the flux over its error, at the survey's chosen limit.

Depths are those of the mock-image table below, plus SDSS *u* 22.0, *z* 20.5 (Abazajian et al. 2009); DES *i* 23.8, *Y* 21.7 (10σ; Abbott et al. 2021); Pan-STARRS1 *z* 22.3, *y* 21.4 (Chambers et al. 2016); LSST *u* 26.1, *z* 26.1, *y* 24.9 (Ivezić et al. 2019); and WISE W4 6 mJy (Wright et al. 2010).

## Mock images

Lightcone Mode's **Create mock image** (`visage/sed/mock_image.py`) draws the
sky around a galaxy as a survey would record it. Each galaxy is an exponential
disk (`DiskRadius` as its scale length) plus a de Vaucouleurs bulge
(`BulgeRadius` as its half-light radius), at its angular size (radius over the
angular-diameter distance). The disk is flattened by its inclination, with
axis ratio *q* = (cos² *i* + *q*₀² sin² *i*)<sup>½</sup>, *q*₀ = 0.2 (Hubble
1926; Holmberg 1958), and turned to the position angle of its spin on the sky.
Disk and bulge fluxes come from their observed-frame magnitudes (or the total,
shared by bulge-to-total stellar mass, when a cone has no disk/bulge
photometry). The image is blurred by a Gaussian of the survey's median seeing
on its pixel grid, with profile centres integrated finely so a cusp doesn't depend on where it falls in a pixel; at survey depth, sky noise is added so that a point source
at the quoted limit has the quoted signal-to-noise. For SDSS and LSST, whose median sky brightness is given below, the galaxies' own shot noise is added too: the sky's mean over its variance gives the electrons per nanomaggy. Colour images are asinh
composites (Lupton et al. 2004).

| Survey | Bands | Pixel | Seeing (FWHM) | Depth | Source |
|---|---|---|---|---|---|
| SDSS | g, r, i | 0.396″ | 1.4″ | 95 % completeness for point sources: g 22.2, r 22.2, i 21.3 (taken as 5σ) | Gunn et al. 2006; Abazajian et al. 2009 |
| DES DR2 (DECam) | g, r, z | 0.263″ | 1.11″, 0.95″, 0.83″ | 10σ in a 1.95″ aperture: g 24.7, r 24.4, z 23.1 | Abbott et al. 2021 |
| Pan-STARRS1 3π | g, r, i | 0.25″ | 1.31″, 1.19″, 1.11″ | 5σ point source: g 23.3, r 23.2, i 23.1 | Chambers et al. 2016 |
| Rubin LSST, 10 years | g, r, i | 0.2″ | 0.7″ | 5σ point source: g 27.4, r 27.5, i 26.8 | Ivezić et al. 2019 |
| 2MASS | J, H, Ks | 1″ (Atlas) | 2.5″ | 10σ point source: J 15.8, H 15.1, Ks 14.3 Vega (+0.91, +1.39, +1.85 to AB) | Skrutskie et al. 2006; Blanton & Roweis 2007 |
| WISE | W1, W2, W3 | 1.375″ (Atlas) | 6.1″, 6.4″, 6.5″ | 5σ point source: 0.08, 0.11, 1 mJy | Wright et al. 2010 |
| GALEX AIS | FUV, NUV | 1.5″ | 4.2″, 5.3″ | 5σ: FUV 19.9, NUV 20.8 | Morrissey et al. 2007 |
| JWST NIRCam | F115W, F200W, F444W | 0.031″ | 0.040″, 0.066″, 0.145″ | noiseless (depth depends on the programme) | JWST User Documentation |

Sky brightness (AB mag arcsec⁻²): SDSS *g* 21.84, *r* 20.84, *i* 20.16 (SDSS DR15 imaging data quality); LSST *g* 22.26, *r* 21.20, *i* 20.48 (Ivezić et al. 2019). The other surveys have sky noise only.

The PNG is the colour composite (north up, east left); the FITS file holds one
extension per band in nanomaggies, with a TAN WCS centred on the chosen
galaxy. Only the cone's own galaxies are drawn: there are no stars, and no
galaxies beyond the cone's redshift range.

## Not included (yet)

- The AGN's own continuum, in the magnitudes or spectra. Its lines are in spectra, but not in the broad bands.
- Line emission from old (post-AGB) stars, which powers many LINER-like spectra in quiescent galaxies.

## References

- Abazajian K. N. et al. 2009, *ApJS* 182, 543
- Abbott T. M. C. et al. 2021, *ApJS* 255, 20
- Asano R. S. et al. 2013, *Earth, Planets and Space* 65, 213
- Asplund M. et al. 2009, *ARA&A* 47, 481
- Blanton M. R., Roweis S. 2007, *AJ* 133, 734
- Bohlin R. C., Savage B. D., Drake J. F. 1978, *ApJ* 224, 132
- Byler N. et al. 2017, *ApJ* 840, 44
- Chabrier G. 2003, *PASP* 115, 763
- Chambers K. C. et al. 2016, arXiv:1612.05560
- Charlot S., Fall S. M. 2000, *ApJ* 539, 718
- Conroy C., Gunn J. E., White M. 2009, *ApJ* 699, 486; Conroy C., Gunn J. E. 2010, *ApJ* 712, 833
- da Cunha E., Charlot S., Elbaz D. 2008, *MNRAS* 388, 1595
- Davis T. M. et al. 2011, *ApJ* 741, 67
- Draine B. T., Li A. 2007, *ApJ* 657, 810
- Feltre A., Charlot S., Gutkin J. 2016, *MNRAS* 456, 3354
- Gunn J. E. et al. 2006, *AJ* 131, 2332
- Gutkin J., Charlot S., Bruzual G. 2016, *MNRAS* 462, 1757
- Hirschmann M. et al. 2017, *MNRAS* 472, 2468
- Holmberg E. 1958, *Medd. Lunds Astron. Obs. Ser. II* 136, 1
- Hubble E. P. 1926, *ApJ* 64, 321
- Ivezić Ž. et al. 2019, *ApJ* 873, 111
- Kashino D., Inoue A. K. 2019, *MNRAS* 486, 1053
- Leroy A. K. et al. 2008, *AJ* 136, 2782
- Lupton R. et al. 2004, *PASP* 116, 133
- Madau P. 1995, *ApJ* 441, 18
- Magdis G. E. et al. 2012, *ApJ* 760, 6
- Merloni A., Heinz S. 2008, *MNRAS* 388, 1011
- Morrissey P. et al. 2007, *ApJS* 173, 682
- Narayan R., Yi I. 1995, *ApJ* 452, 710
- Padmanabhan N. et al. 2008, *ApJ* 674, 1217
- Popping G., Somerville R. S., Galametz M. 2017, *MNRAS* 471, 3152
- Shamshiri S. et al. 2015, *MNRAS* 451, 2681
- Skrutskie M. F. et al. 2006, *AJ* 131, 1163
- Triani D. P. et al. 2020, *MNRAS* 493, 2490
- Tsai J. C., Mathews W. G. 1995, *ApJ* 448, 84
- Wang J. et al. 2016, *MNRAS* 460, 2143
- Wright E. L. et al. 2010, *AJ* 140, 1868
