# Lightcone Photometry

The LightSAGE flow's photometry stage (`python -m visage.sed.photometry`) gives every galaxy in a lightcone the magnitudes an observer would measure, built forward from its own SAGE26 star-formation history. The settings used are recorded in the file's `PhotometryHeader` attributes.

## Stellar light

| Step | How |
|---|---|
| Stellar populations | FSPS (Conroy, Gunn & White 2009; Conroy & Gunn 2010) with MIST isochrones and MILES spectra, Chabrier (2003) IMF, as SAGE26 assumes. |
| Star-formation history | SAGE26 files the stars formed between snapshots *k*−1 and *k* in bin *k* (outputs from before its snapshot-lag fix, *k* and *k*+1; read from the file), as the mass that survives recycling. Each bin is turned back into the mass formed, ÷ (1 − *R*) with the run's `RecycleFraction`, and spread at a constant rate over its own time span by integrating the populations over age (as TAO does: Shamshiri et al. 2015). |
| Youngest stars | The last 100 Myr come from the galaxy's current SFR (`SfrDisk` + `SfrBulge`), not the last bin spread evenly over its 0.3–0.6 Gyr. |
| Metallicity | Each star-formation bin's own, from SAGE26's metallicity history (`MHMetalsDisk`, `MHMetalsBulge`, with `SaveFullMH`), for the disk and bulge separately; the spectrum is interpolated in log *Z* between population nodes. Without a history, or with `--no-metal-history`, one present-day value per galaxy, `MetalsStellarMass` / `StellarMass`. |

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

**How it dims the light.** The two-component model of Charlot & Fall (2000), as Dusty SAGE's default variant uses it (Triani et al. 2023, after Lagos et al. 2019):

- **Dust surface density:** Σ<sub>dust</sub> = *M*<sub>dust</sub> / (2π *r* *l*) inside the gas half-mass radius *r* = 1.68 *R*<sub>d</sub> (as Lagos et al.; Dusty SAGE's own radius is set to match its galaxies), with *l* = cos *i* (*r* − *r*/7.3) + *r*/7.3 the projected minor axis at the galaxy's inclination (its spin against the line of sight).
- **Diffuse ISM:** a screen whose optical depth and slope follow Σ<sub>dust</sub>, from the radiative-transfer results of Trayford et al. (2020): the median relations as digitised by Lagos et al.
- **Birth clouds:** stars younger than 10 Myr are also behind a cloud of τ<sub>BC</sub> = δ Σ<sub>cl</sub> / (*f*<sub>DTM,MW</sub> *Z*<sub>☉</sub> Σ<sub>MW,cl</sub>), with δ the dust-to-gas ratio, Σ<sub>cl</sub> = max(85 M☉ pc⁻², the ISM's Σ<sub>gas</sub>), *f*<sub>DTM,MW</sub> = 0.33, *Z*<sub>☉</sub> = 0.0189, at least τ<sub>ISM</sub> and at most 5, with τ<sub>λ</sub> ∝ λ<sup>−0.7</sup>.

**Where the absorbed light goes** (`--dust-emission`). Each galaxy re-emits exactly the starlight its dust absorbed (energy balance, as in da Cunha et al. 2008), with the Draine & Li (2007) dust-emission spectrum FSPS uses (γ = 0.01, *q*<sub>PAH</sub> = 3.5 %). Its *U*<sub>min</sub> comes from the galaxy's own light per unit dust mass, *L*<sub>dust</sub> = *P*<sub>0</sub> ⟨*U*⟩ *M*<sub>dust</sub> with *P*<sub>0</sub> ≈ 125 L☉ M☉⁻¹ (Magdis et al. 2012), within the models' 0.1–25, so more light on less dust is warmer. `LDust` is the total and `DustUmin` the *U*<sub>min</sub>.

**Runs with their own dust.** With SAGE26's `DustySAGEMode`, `ColdDust` replaces the steady state above. With `DarkSAGEMode` as well, each of the 30 annuli has its own screen from `DiscDust`, seen at the galaxy's inclination, and stars see the screen of the annulus they're in: new stars placed by `DiscSFR`, the rest by `DiscStars`, the bulge falling off from the centre. The annuli have no ages, so that placement of new stars is an assumption. Trayford et al. (2020) measured their relation on whole galaxies, so using it for one annulus is an extrapolation, and a screen can't show stars mixed in with the dust. Inclination then comes from the stellar disc's spin.

**The fibre and the HI line.** With annuli, `FibreLight` is the share of V-band light inside a 3 arcsec fibre, and `W50_HI` the width of the HI line at half its peak as inclined: each annulus's HI at its circular speed, with 11 km/s of its own (Stevens et al. 2024). SAGE26's discs follow its own `DiskRadius`, which the annuli don't set in `DarkSAGEMode` 1.

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

**AGN.** SAGE26's black holes accrete in quasar mode (`QuasarModeBHaccretionMass` over the snapshot step `dT`, which is in *h*⁻¹ Myr) and radio mode (`RadioModeBHaccretionMass` over the same step, or in older outputs its power `Heating` = η*Ṁc*², η = 0.1). SAGE26's black holes start at zero mass, so a dwarf's first merger or disk instability makes one of a tiny mass all at once; its Eddington ratio then reflects only the step's length (the card notes such a black hole), and its luminosity is negligible. A quasar burst's mass is added all at once, and its position within the step isn't physical (orphan mergers wait for their halo mass to ramp down at the step's end, and instabilities are triggered by halo properties updating at snapshots), so each burst is placed uniformly within its step, repeatably from `GalaxyIndex`. Its energy η*Mc*² then follows the light curve of Hopkins & Hernquist (2009, eq. 12) with *t*<sub>Q</sub> = 50 Myr and β = 0.6, peaking at most at the Eddington limit; a bigger burst holds that limit until the excess is used up, so all its energy is radiated. The fading tail of a burst from an earlier step isn't included, as its mass is only kept for its own step. Their luminosity is η*Ṁc*² above 1 % of Eddington and falls as *ṁ*² below it, where the flow becomes radiatively inefficient (Narayan & Yi 1995; Merloni & Heinz 2008). The narrow-line region uses the photoionisation models of Feltre, Charlot & Gutkin (2016), coupled to each galaxy as Hirschmann et al. (2017) do: an ionising spectrum *S*<sub>ν</sub> ∝ ν<sup>−1.7</sup>, gas clumps of *n*<sub>H</sub> = 10³ cm⁻³, dust-to-metal ratio 0.3, the cold gas's metallicity, and the ionisation parameter at the Strömgren radius from the AGN's ionising photons and the filling factor of the cold gas within 1 kpc. A galaxy with no cold gas has no narrow-line region. The lines pass through half the disk's dust, as a screen. `LAGN`, `EddingtonRatio`, `LogU_HII` and `LogU_AGN` are written too.

## Survey noise (`--noise`)

`flux_obs_*` and `fluxerr_obs_*` (µJy, in `visage/sed/noise.py`) are the fluxes a survey would catalogue, beside the noiseless magnitudes, for the bands of surveys with a quoted depth. It can also be run on an existing cone: `python -m visage.sed.noise --input <lightcone.h5>`.

Each band's sky noise is set so that a point source at the survey's limit has its quoted signal-to-noise. A galaxy covers more sky than a point source, so its error is that noise over a matched-filter area, 4π(σ<sub>PSF</sub>² + σ<sub>gal</sub>²), with σ<sub>gal</sub> from its half-light radius, plus a 1 % calibration floor in quadrature (Padmanabhan et al. 2008). Source shot noise isn't included. Noise is Gaussian in flux, so a faint galaxy's flux can be negative. Nothing is removed: a catalogue cut is the flux over its error, at the survey's chosen limit.

Depths are those of the mock-image table below, plus SDSS *u* 22.0, *z* 20.5 (Abazajian et al. 2009); DES *i* 23.8, *Y* 21.7 (10σ; Abbott et al. 2021); Pan-STARRS1 *z* 22.3, *y* 21.4 (Chambers et al. 2016); LSST *u* 26.1, *z* 26.1, *y* 24.9 (Ivezić et al. 2019); and WISE W4 6 mJy (Wright et al. 2010).

## Survey catalogues

`python -m visage.sed.survey --input <cone.h5> --survey sdss_main --output <file.fits>` (`visage/sed/survey.py`) measures each galaxy as a survey does, from its disk (exponential) and bulge (de Vaucouleurs), each circularised and broadened by the seeing in quadrature:

- **Petrosian magnitude:** the radius *r*<sub>P</sub> where the surface brightness in 0.8–1.25 *r*<sub>P</sub> is 0.2 of the mean inside it, and the flux inside 2 *r*<sub>P</sub> (Blanton et al. 2001), about 99 % of an exponential and 80 % of a de Vaucouleurs profile.
- **r50 and μ50:** the radius holding half that flux, and the mean surface brightness inside it.
- **Fibre magnitude:** the flux inside the fibre (3″ for SDSS, 2″ for GAMA's).

Apertures are set in the detection band and used in every band. Selections add the survey's noise and its published cuts: the SDSS Main Galaxy Sample, 14.5 < *r* ≤ 17.77 and μ<sub>50</sub> ≤ 24.5 mag arcsec⁻² (Strauss et al. 2002), and GAMA II, *r* < 19.8 (Baldry et al. 2018). One of each pair closer than 55″ is flagged `fibre_collided`, as SDSS can't place fibres closer. Galaxies have no arms or clumps here, so their Petrosian radii are those of smooth profiles.

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
photometry). The image is blurred by the survey's median seeing on its pixel grid (a Moffat profile with β = 4.765 from the ground, Trujillo et al. 2001, and a Gaussian of the quoted FWHM from space; a real SDSS PSF also has a fainter extended wing beyond about 3″ that this omits), with profile centres integrated finely so a cusp doesn't depend on where it falls in a pixel; at survey depth, sky noise is added so that a point source
at the quoted limit has the quoted signal-to-noise. For SDSS and LSST, whose median sky brightness is given below, the galaxies' own shot noise is added too: the sky's mean over its variance gives the electrons per nanomaggy. Colour images are asinh
composites (Lupton et al. 2004).

| Survey | Bands | Pixel | Seeing (FWHM) | Depth | Source |
|---|---|---|---|---|---|
| SDSS | g, r, i | 0.396″ | 1.32″ | 95 % completeness for point sources: g 22.2, r 22.2, i 21.3 (taken as 5σ) | Gunn et al. 2006; Abazajian et al. 2009 |
| DES DR2 (DECam) | g, r, z | 0.263″ | 1.11″, 0.95″, 0.83″ | 10σ in a 1.95″ aperture: g 24.7, r 24.4, z 23.1 | Abbott et al. 2021 |
| Pan-STARRS1 3π | g, r, i | 0.25″ | 1.31″, 1.19″, 1.11″ | 5σ point source: g 23.3, r 23.2, i 23.1 | Chambers et al. 2016 |
| Rubin LSST, 10 years | g, r, i | 0.2″ | 0.7″ | 5σ point source: g 27.4, r 27.5, i 26.8 | Ivezić et al. 2019 |
| 2MASS | J, H, Ks | 1″ (Atlas) | 2.5″ | 10σ point source: J 15.8, H 15.1, Ks 14.3 Vega (+0.91, +1.39, +1.85 to AB) | Skrutskie et al. 2006; Blanton & Roweis 2007 |
| WISE | W1, W2, W3 | 1.375″ (Atlas) | 6.1″, 6.4″, 6.5″ | 5σ point source: 0.08, 0.11, 1 mJy | Wright et al. 2010 |
| GALEX AIS | FUV, NUV | 1.5″ | 4.2″, 5.3″ | 5σ: FUV 19.9, NUV 20.8 | Morrissey et al. 2007 |
| Euclid VIS | VIS | 0.1″ | 0.13″ | 5σ point source: 26.2 | Mellier et al. 2025; Scaramella et al. 2022 |
| Euclid NISP | Y, J, H | 0.298″ | 0.33″, 0.35″, 0.35″ | 5σ point source: 24.4 | Mellier et al. 2025 |
| Roman HLWAS, medium tier | F106, F129, F158 | 0.11″ | diffraction limit: 0.096″, 0.117″, 0.139″ | 5σ point source: 26.5, 26.4, 26.4 | Roman community survey definition |
| HST CANDELS wide | F606W, F814W, F160W | 0.06″ | diffraction limit 0.054″, 0.073″; 0.18″ | 5σ point source: 28.7, 28.0, 27.3 | Grogin et al. 2011; Koekemoer et al. 2011 |
| VISTA VIKING | Y, J, Ks | 0.34″ | 1″ (the survey's limit) | 5σ: 22.3, 22.1, 21.2 AB (as quoted; sources differ on the magnitude system) | Edge et al. 2013 |
| UKIDSS LAS | Y, J, K | 0.4″ | 1.2″ (the survey's limit) | 5σ point source: 20.79, 20.49, 20.09 AB | Lawrence et al. 2007; Hill et al. 2010 |
| Spitzer SWIRE | 3.6, 4.5, 8.0 µm | 0.6″ | 2.05″, 2.05″, 2.5″ | 5σ: 7.3, 9.7, 32.5 µJy (pre-flight) | Lonsdale et al. 2003 |
| Herschel H-ATLAS SPIRE | 250, 350, 500 µm | 6″ | 17.8″, 24″, 35.2″ | 5 × 1σ with confusion: 37, 47, 51 mJy | Valiante et al. 2016; Maddox et al. 2018 |
| Herschel H-ATLAS PACS | 100, 160 µm | 3″ | 11.4″, 13.7″ | 5 × typical noise: 220, 245 mJy | Valiante et al. 2016; Maddox et al. 2018 |
| JWST CEERS | F115W, F200W, F444W | 0.031″ | 0.040″, 0.066″, 0.145″ | 5σ point source: 29.15, 29.17, 28.58 | Bagley et al. 2023 |

Sky brightness (AB mag arcsec⁻²): SDSS *g* 21.84, *r* 20.84, *i* 20.16 (SDSS DR15 imaging data quality); LSST *g* 22.26, *r* 21.20, *i* 20.48 (Ivezić et al. 2019). The other surveys have sky noise only.

The PNG is the colour composite (north up, east left); the FITS file holds one
extension per band in nanomaggies, with a TAN WCS centred on the chosen
galaxy, or on a random point of the cone's sky with **Random patch of sky**.
The image is saved as PNG (default), JPEG or PDF.

`composite` is the one colour renderer, used for mock images and for real FITS
in comparisons, so differences between them aren't display differences. WISE
shows W1 and W2, as unWISE images do, as W3 is far shallower.

With stars on, SDSS, DES and LSST pixels above the CCD full well bleed along
their column, using the published saturation limit of a single exposure.

Colour weights never depend on the cone, so that a model's colours show as
they are. A fixed old population (10 Gyr, solar, FSPS, z = 0.1) has the display
colour of a red galaxy in SDSS's images in optical and near-infrared surveys,
and is white in Spitzer and WISE, so dust shows as red. GALEX and Herschel show
each band in its own noise units. The stretch comes from the mean noise of the
displayed channels, calibrated on SDSS. Real data shown beside a mock goes
through the same weights and renderer.

2MASS, WISE and Herschel maps are smoothed by the beam, so their noise is correlated
on that scale. In SPIRE, the share of the noise from confusion (Nguyen et al.
2010) is common to the bands, as the same unresolved galaxies cause it. The
drawn faint galaxies aren't removed from it, so faint-source confusion is
counted slightly more than once.

**Galaxies beyond this cone** adds a deeper cone's galaxies; it reaches as far
as that cone does, so build a deeper one to see fainter galaxies.

**Subtract sky brightness** (on) sets the sky to black. Off, the sky stays in
the colour image at about 0.1 of full scale, as SDSS, Legacy Survey and
Pan-STARRS cutout services show it. The FITS bands are sky-subtracted either
way.

**Add stars** (off) adds Milky Way stars, which SAGE26 doesn't model, so they
are never on by default. They are a random draw from one square degree at
*b* = 79°: real 2MASS stars at the bright end, where SDSS saturates, and clean
SDSS DR18 stars down to *r* = 22.5. Their number doesn't change with position.
Other bands use a blackbody at each star's temperature (*g*−*r* to *B*−*V*,
Jester et al. 2005; Teff, Ballesteros 2012), which is rough in the UV.

PSFs are measured wherever one exists: real stars stacked from SDSS and
Pan-STARRS FITS, STDPSF for HST, Euclid's Q1 PSF grids, and STPSF for JWST (from
in-flight wavefronts) and Roman (a model, as it hasn't flown). LSST uses Moffat
seeing through its mirror's diffraction; other ground surveys, DES included, use
Moffat seeing at the published value. A small stack of true DES stars agrees
with DES's published seeing, but it's too noisy to use as a kernel.
Stacks of ordinary stars don't reach the wings and spikes of very bright stars.

Sky noise in images is the per-pixel noise measured in real data where it exists:
the median of 11-18 fields for SDSS, DES and Pan-STARRS, about 30% field to
field, and a smaller number of survey fields for Euclid, GALEX, 2MASS, Spitzer
SEIP, H-ATLAS, HST GOODS-S and JWST CEERS, because
resampling coadds smooths it below what a survey's quoted depth implies. Quoted
depths still set the catalogue flux errors.

Source shot noise uses the sky level where it is published: SDSS, LSST and DES
(Abbott et al. 2018). In space the sky is zodiacal light, taken as V = 22.7
(ACS Instrument Handbook) with a solar spectrum, which is too faint at F444W,
where zodiacal and telescope thermal emission take over.

## Not included (yet)

- The AGN's own continuum, in the magnitudes or spectra. Its lines are in spectra, but not in the broad bands.
- A covering factor for AGN narrow lines. As in Hirschmann et al. (2017) the grid is scaled to the AGN's luminosity, so Hα/*L*<sub>AGN</sub> ≈ 0.004, close to case B for every ionising photon, while Feltre et al. (2016) note covering factors are typically below 10 %.
- Central gas metallicity near the black hole: SAGE26 has only each galaxy's mean, so AGN lines use that, which keeps [NII]/Hα low.
- Line emission from old (post-AGB) stars, which powers many LINER-like spectra in quiescent galaxies.

## References

- Abazajian K. N. et al. 2009, *ApJS* 182, 543
- Abbott T. M. C. et al. 2021, *ApJS* 255, 20
- Asano R. S. et al. 2013, *Earth, Planets and Space* 65, 213
- Asplund M. et al. 2009, *ARA&A* 47, 481
- Blanton M. R. et al. 2001, *AJ* 121, 2358
- Blanton M. R., Roweis S. 2007, *AJ* 133, 734
- Bohlin R. C., Savage B. D., Drake J. F. 1978, *ApJ* 224, 132
- Baldry I. K. et al. 2018, *MNRAS* 474, 3875
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
- Hopkins P. F., Hernquist L. 2009, *ApJ* 698, 1550
- Hubble E. P. 1926, *ApJ* 64, 321
- Ivezić Ž. et al. 2019, *ApJ* 873, 111
- Kashino D., Inoue A. K. 2019, *MNRAS* 486, 1053
- Leroy A. K. et al. 2008, *AJ* 136, 2782
- Lupton R. et al. 2004, *PASP* 116, 133
- Madau P. 1995, *ApJ* 441, 18
- Lagos C. d. P. et al. 2019, *MNRAS* 489, 4196
- Magdis G. E. et al. 2012, *ApJ* 760, 6
- Merloni A., Heinz S. 2008, *MNRAS* 388, 1011
- Morrissey P. et al. 2007, *ApJS* 173, 682
- Narayan R., Yi I. 1995, *ApJ* 452, 710
- Padmanabhan N. et al. 2008, *ApJ* 674, 1217
- Popping G., Somerville R. S., Galametz M. 2017, *MNRAS* 471, 3152
- Shamshiri S. et al. 2015, *MNRAS* 451, 2681
- Skrutskie M. F. et al. 2006, *AJ* 131, 1163
- Triani D. P. et al. 2020, *MNRAS* 493, 2490
- Strauss M. A. et al. 2002, *AJ* 124, 1810
- Trayford J. W. et al. 2020, *MNRAS* 491, 3937
- Triani D. P. et al. 2023, *MNRAS* 519, 2500
- Trujillo I. et al. 2001, *MNRAS* 328, 977
- Tsai J. C., Mathews W. G. 1995, *ApJ* 448, 84
- Wang J. et al. 2016, *MNRAS* 460, 2143
- Wright E. L. et al. 2010, *AJ* 140, 1868

## HD on a lightcone

HD stays separate from mock images, but on a lightcone its light comes from the
same photometry. After a first render, `layer.photometry_closure` sets the
disk's and bulge's colours and ratio, and the shares of Halpha, the AGN and
intracluster stars, to the cone's magnitudes as seen from the observer. Dust is
the photometry's `TauV_ISM`. Radii are SAGE26's, bulges take the images' axis
ratios, hidden AGN aren't drawn, and intracluster light has the half-light
radius of the images' NFW, in HD's Hernquist shape. Group members are lit by
their luminosity. Arms, clusters and dust structure are HD's own. A box keeps
HD's own look and sizes throughout.

## What doesn't come from SAGE26

Everything about a galaxy comes from SAGE26's output: stellar mass and its
history in disk and bulge, metallicity per history bin, cold gas and H2, black
hole accretion, position, velocity, spin and radii. These fill what it doesn't
give, each from the literature or real data:

| Stage | Input | Source |
|---|---|---|
| Stars | Spectra of stellar populations, Chabrier IMF | FSPS |
| Stars | Disk stars moved to the bulge keep the disk's age mix, as SAGE26 doesn't record when they moved | Assumption |
| Dust | Dust mass, as a steady state of the Dusty-SAGE model | Triani et al. 2020 |
| Dust | Attenuation and birth clouds | Trayford et al. 2020; Lagos et al. 2019 |
| Dust | Emission | Draine & Li 2007 |
| Lines | HII regions, AGN narrow-line regions | Gutkin et al. 2016; Feltre et al. 2016 |
| AGN | Quasar light curve, placed at random in its step | Hopkins & Hernquist 2009 |
| Light of a galaxy | Exponential disk; de Vaucouleurs bulge, half-light equal to SAGE26's half-mass radius | Assumption |
| Light of a galaxy | Disk thickness 0.2 | Hubble 1926; Holmberg 1958 |
| Light of a galaxy | Bulge axis ratios | Real SDSS early types |
| Images | Noise, seeing, depths, sky levels, saturation | Real data and survey papers |
| Images | PSFs | Measured: stacked real stars (SDSS, Pan-STARRS), STDPSF (HST), Euclid Q1 grids, STPSF (JWST; a model for Roman). Otherwise Moffat seeing |
| Images | Stars (optional) | Real 2MASS and SDSS stars |
| Images | Display stretch, black point, sky level | Display only: never in the FITS. Calibrated on SDSS, and real 2MASS, WISE and Herschel maps reach the same contrast (0.94-1.12 of it) with no change |
| Selections | Survey cuts | Strauss et al. 2002; Baldry et al. 2018 |
| Groups | Linking lengths, virial mass | Van Kempen et al. 2024, 2025 |

Not modelled: arms, rings, dust lanes and tidal features; Galactic extinction.

## AGN and intracluster stars

`visage.sed.components` runs after the photometry, or on its own with `python -m
visage.sed.components --input cone.h5`, and writes `agn_mag_obs_*`,
`ics_mag_obs_*` and `AGNObscured`. `mag_obs_*` stays the galaxy's own light.

Above 1% of Eddington an AGN has the mean quasar spectrum of Shen et al. (2020),
scaled to SAGE26's `LAGN`, and an absorbing column drawn from Ueda et al. (2014).
Below it there is no thin disk, so only narrow lines. AGN are point sources in
images, and are in spectra and survey catalogues.
Narrow lines are in spectra and line fluxes, not in `agn_mag_obs_*`.

**Add intracluster stars** in the Image view draws SAGE26's `IntraClusterStars`
as a projected NFW profile with its `Rvir` and `Concentration`, as the ICL traces
the dark matter (Montes & Trujillo 2019; Alonso Asensio et al. 2020), or with the
Duffy et al. (2008) relation where `Concentration` is 0. SAGE26 gives their mass,
metals and deposit times, so they are one population at SAGE26's metallicity and
the mass-weighted age of the central's own stars, or the deposit's age if older.
That age is an assumption.
