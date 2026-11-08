"""Procedural high-definition galaxy built from one SAGE galaxy's properties.

Prototype for an "HD isolate" mode.  SAGE has no resolved structure inside a
galaxy, so everything spatial here (arm pattern, cluster positions, dust
filaments) is invented; only the global numbers come from the model:

    StellarMass, BulgeMass        -> total / bulge light, disk vs elliptical
    InstabilityBulgeMass          -> bar strength (secular growth)
    MergerBulgeMass               -> classical bulge
    DiskRadius, BulgeRadius       -> scale lengths
    SfrDisk                       -> young blue clusters and diffuse blue light
    H2gas (+ MetalsColdGas)       -> dust lanes on the arms, HII knots
    H1gas                         -> extended outer disk (faint clusters, dust)
    BlackHoleMass                 -> brightness / compactness of the nucleus
    Regime                        -> tie-breaker for disk vs elliptical

All lengths are in units of the disk scale length Rd (the effective radius
for ellipticals), so the picture is self-similar and the camera just frames
a fixed number of scale lengths.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates

# Linear-light colours (roughly a Hubble B/V/I composite palette).
OLD_RGB = np.array([1.00, 0.78, 0.52])
BULGE_RGB = np.array([1.00, 0.70, 0.42])
YOUNG_RGB = np.array([0.50, 0.68, 1.00])
CLUSTER_RGB = np.array([0.62, 0.78, 1.00])
# Teal-green, as in the Hubble (SHO) palette where H-alpha maps to green
# and [OIII] to blue.
HII_RGB = np.array([0.40, 1.00, 0.78])
# HII colour by metallicity: metal-poor gas is hotter, brighter in [OIII]
# (cyan); metal-rich, greener.  HII_RGB sits at about half solar.
HII_POOR_RGB = np.array([0.30, 0.92, 1.00])
HII_RICH_RGB = np.array([0.45, 1.00, 0.62])
# HII regions' look: colours for metal-poor / metal-rich star-forming gas
# (None: the teal palette above), and their size.
# Chosen from options on SAGE26 disks ("B"): Halpha pink in metal-poor gas
# to orange in metal-rich, gathered into complexes along the arms.  How
# rich and how spread out each complex is comes from the galaxy (recipe
# hii_group, hii_spread).
# Chosen from options on SAGE26 disks (2026-10-25, "H, but less"): small
# crisp knots, every one equally sharp, dimmer than before (was size 1.3,
# gain 0.8, one knot group, blurred splats); their nebula is now gas.
# (gain 0.41: the knots' share when a quarter went to the nebula.)
HII_LOOK = dict(
    poor=(1.00, 0.40, 0.80),
    rich=(1.00, 0.55, 0.32),
    size=0.5,
    gain=0.41,
    conc=0.7,
    # How a complex is built: sub-regions per complex (x the recipe's
    # hii_group) and how tightly they cluster (x hii_spread).  (The gas
    # round them is the disc's ionised gas, GAS: drawn with Gas on.)
    knots=2.5,
    spread=0.6,
    # Splatted (not drawn exactly) HII regions at the exact ones' size.
    sharp=True,
    # Each complex's colour between poor and rich: the galaxy's own (its
    # star-forming gas's metallicity), an abundance gradient (orange
    # inside, pink outside; ~-0.1 dex per effective radius, Sanchez et al.
    # 2014, A&A 563, A49: -0.067 of the colour range per disk scale
    # length), and a scatter for each region's own abundance and
    # reddening.  gradient = 0 and mix = 0: one colour per galaxy.
    gradient=-0.067,
    mix=0.18,
)
# Dust lanes along the arms: width of the lane profile (arm-phase units),
# extra sharpness, contrast power, and streaks (0-1: lanes broken into
# thin filaments running along the arms).
# Chosen from options ("B"): faint, streaky lanes, darker in dustier
# disks (recipe lane).
DUST_LANES = dict(
    width=0.22, sharp=3.0, power=1.8, streaks=0.6, boost=0.8, reach=4.0
)
# Cooling-flow filaments (H-alpha) in cluster cores; ram-pressure tails.
HALPHA_RGB = np.array([1.00, 0.36, 0.46])
ICL_RGB = np.array([1.00, 0.82, 0.60])
GC_RGB = np.array([1.00, 0.85, 0.65])
# Gas-halo overlay (X-ray / CGM composite style, not optical light).
HOT_GAS_RGB = np.array([0.62, 0.45, 1.00])
CGM_RGB = np.array([0.35, 0.62, 1.00])
# H-alpha cooling filaments raining out of a still-cooling hot halo
# (off: in SAGE26 they only arise around a few ~1e12 Msun disks).
HALPHA_FILAMENTS = False
# Galactic wind: H-alpha red, as M82's.
WIND_RGB = np.array([1.00, 0.38, 0.40])
# Radio jets / lobes (radio-composite orange-gold).
JET_RGB = np.array([1.00, 0.72, 0.30])
# Light per unit mass of old stars relative to the young-star scaling; below
# 1 so the old disk, bulge and bar don't wash an orange haze over the arms.
OLD_LIGHT = 0.4

# Stellar populations by age, for galaxies with a star-formation history
# (lookback bins as visage.io.galaxy_reader.SFH_AGE_EDGES: <0.1, 0.1-0.5,
# 0.5-1, 1-3, 3-6, 6-10, >10 Gyr).  A representative age per bin, its
# colour at solar metallicity (the 10+ Gyr one is the old-star colour used
# without an SFH) and light per unit mass relative to a 10 Gyr population
# (~ age^-0.8, optical).  The <0.1 Gyr bin is the current star formation,
# drawn as young light, clusters and HII regions; it isn't counted here.
SFH_AGES = (0.05, 0.25, 0.7, 1.8, 4.3, 7.8, 12.0)  # Gyr
SFH_RGB = np.array(
    [
        (0.70, 0.82, 1.00),
        (0.82, 0.88, 1.00),
        (0.95, 0.94, 0.97),
        (1.00, 0.90, 0.80),
        (1.00, 0.84, 0.64),
        (1.00, 0.80, 0.56),
        (1.00, 0.78, 0.52),
    ]
)
SFH_LM = np.array([(t / 10.0) ** -0.8 for t in SFH_AGES])
# Switch for comparisons (False: colours from metallicity alone, as
# without an SFH).
USE_SFH = True
# Dwarf irregulars: gas-rich disks below max_lm (the LMC's mass, the
# Magellanic irregulars' upper end) are drawn without spiral arms, with a
# few large star-forming complexes (more the more star formation: Hunter &
# Elmegreen 2004), a lopsided (m = 1) disk (Zaritsky et al. 2013) and a
# thick one (intrinsic b/a ~ 0.3-0.4: Roychowdhury et al. 2013).
DWARF = dict(max_lm=9.5, lopsided=(0.3, 0.8), clumps=(3, 8), hz=0.5)
# ICL streams: "threshold" (any ICS torn from satellites in place above
# ~10^10.5 Msun) or "share" (scaled by the in-place share of all the ICS,
# accreted ICS making a smoother envelope).
ICL_MODE = "threshold"
# Streams of satellite debris feeding the ICL (off: removed by choice).
ICL_STREAMS = False
# The ICL's look (its envelope's light is SAGE26's ICS): glow brightness (x), the glow's
# and stripped stars' extent (0: the galaxy's size; >0: that many times the
# envelope scale 0.12 Rvir), stripped-star count (x), colour (None: from
# its metallicity).
# mass: >0 scales the glow and envelope with the ICS mass itself (power).
# Chosen from options on SAGE26 centrals ("D"): halo-wide, its glow and
# envelope scaled by the ICS mass.
ICL_LOOK = dict(glow=0.55, size=1.0, stars=1.0, rgb=None, mass=0.35)

# Inside-out gradient strength (0: none): the inner disk's colour weights
# the older part of the history up by (age / mean age)^GRADIENT, the outer
# disk's the younger part.
GRADIENT = 0.0  # (off: the user kept the current look)


def _weighted(bins, power: float):
    """The SFH bins re-weighted towards older (power > 0) or younger
    (power < 0) stars, mass preserved."""
    m = np.maximum(np.asarray(bins, float), 0.0)
    ages = np.asarray(SFH_AGES)
    tot = m[1:].sum()
    if tot <= 0:
        return m
    mean = (m[1:] * ages[1:]).sum() / tot
    w = m * (ages / max(mean, 1e-3)) ** power
    return w * tot / max(w[1:].sum(), 1e-30)


def population(bins) -> tuple[np.ndarray, float, float] | None:
    """Light-weighted colour, light per unit mass (relative to 10 Gyr) and
    the share of light from 0.1-1 Gyr stars, of the population formed in
    SFH_AGES bins (current star formation, < 0.1 Gyr, left out); None
    without one."""
    m = np.asarray(bins, float)
    if not USE_SFH or m.size != len(SFH_AGES) or m[1:].sum() <= 0:
        return None
    m = np.maximum(m[1:], 0.0)
    w = m * SFH_LM[1:]
    rgb = (w[:, None] * SFH_RGB[1:]).sum(axis=0) / w.sum()
    lm = float(np.clip(w.sum() / m.sum(), 0.8, 6.0))
    inter = float(w[:2].sum() / w.sum())
    return rgb, lm, inter


# Extinction relative to the "V" (green) channel: dust reddens what it dims.
DUST_K = np.array([0.72, 1.00, 1.35])


# The most face-on V-band optical depth HD gives any place in a disc (arms
# reach ~1-2 and centres a few; Holwerda et al. 2005, AJ 129, 1381).
TAU_MAX = 5.0


# The young light (x the recipe's l_young): its smooth part, along the arms,
# and its young star clusters' share, drawn as points.
YOUNG_SMOOTH = 1.2
YOUNG_CLUSTERS = 0.6


# The thick disc: its height (x the thin disc's; 2-3, Yoachim & Dalcanton
# 2006, AJ 131, 226) and its share of the old disc, from the rotation
# speed: ~0.2 in fast rotators, about half and more below ~120 km/s
# (Comeron et al. 2011, ApJ 741, 28), interpolated between these speeds.
THICK = dict(height=2.5, share=(0.6, 0.2), vc=(80.0, 150.0))


def thick_share(g) -> float:
    """The thick disc's share of the old disc's light, from the disc's
    rotation (DarkSAGE's, else the halo's Vmax)."""
    vc = g.disc_vrot if g.disc_vrot > 0 else g.vmax
    if vc <= 0:
        return 0.0
    return float(np.interp(vc, THICK["vc"], THICK["share"]))


# An elliptical's dust (strength from its H2 or DustySAGE dust): a nuclear
# lane or disc (radius and half-thickness, model units; the core's
# Hernquist scale is 0.22) and irregular filaments through the core (their
# share, their reach, and the size of their pattern).  About four in ten
# ellipticals show dust: discs and lanes, filaments and patches (van
# Dokkum & Franx 1995, AJ 110, 2027; Tran et al. 2001, AJ 121, 2928;
# Lauer et al. 2005, AJ 129, 2138).
ELL_DUST = dict(lane_r=0.25, lane_h=0.02, fil=12.0, fil_r=0.45, fil_size=0.35)


# Radio-loud AGN, which drive visible jets: from this jet power (log10
# erg/s; Best & Heckman 2012, MNRAS 421, 1569; Cavagnolo et al. 2010, ApJ
# 720, 1066).
RADIO_LOUD = 42.0


def jet_power_log(g) -> float:
    """log10 of the radio-mode jet power, 0.1 Mdot c^2 (erg/s) over the
    step; 0 with none.  From the accretion before SAGE26's cap of heating
    at cooling where the adapter passes it on (only for snapshots whose
    capped accretion makes no radio-loud galaxy), else the capped one."""
    acc = (
        g.radio_accretion_uncapped
        if g.radio_accretion_uncapped >= 0
        else g.radio_accretion
    )
    if acc <= 0 or g.dt_myr <= 0:
        return 0.0
    mdot = acc / (g.dt_myr * 1e6)  # Msun/yr
    return float(np.log10(0.1 * mdot * 5.66e46))


def dust_height(rc) -> float:
    """The dust layer's sech^2 scale height (Rd): about half the stars'
    (Xilouris et al. 1999, A&A 344, 868), and no more than 0.045, so a thin
    disc's stars aren't all buried in it."""
    return float(min(0.045, 0.5 * rc.hz))


# A lightcone galaxy with synthetic photometry is drawn with that dust
# (visage.sed.dust): its face-on V-band optical depth, and the Charlot &
# Fall (2000) diffuse-ISM curve tau ~ lambda^-0.7 at the channels'
# wavelengths (B 4350, V 5500, I 8140 A), relative to V.
SED_DUST_K = np.array([(8140 / 5500) ** -0.7, 1.0, (4350 / 5500) ** -0.7])
# TauV_ISM is the mean face-on optical depth inside the stellar half-light
# radius (1.68 Rd); an exponential disk's mean there is this share of its
# central value (2 [1 - (1 + x) e^-x] / x^2 at x = 1.68).
_X = 1.68
SED_TAU_MEAN = 2.0 * (1.0 - (1.0 + _X) * np.exp(-_X)) / _X**2


@dataclass
class SageGalaxy:
    """The handful of SAGE quantities the generator uses (physical units)."""

    galaxy_index: int
    stellar_mass: float  # Msun
    bulge_mass: float
    merger_bulge_mass: float
    instability_bulge_mass: float
    cold_gas: float
    h2_gas: float
    h1_gas: float
    metals_cold_gas: float
    bh_mass: float
    sfr_disk: float  # Msun/yr
    sfr_bulge: float
    disk_radius_kpc: float
    bulge_radius_kpc: float
    regime: int  # 0 = cold CGM, 1 = hot
    gtype: int = 0
    hot_gas: float = 0.0  # Msun
    cgm_gas: float = 0.0  # Msun
    rvir_kpc: float = 200.0
    metals_stellar_mass: float = 0.0  # Msun
    t_major_myr: float = -1.0  # Myr since the last major merger (<0: never)
    t_minor_myr: float = -1.0
    qso_accretion: float = 0.0  # Msun accreted in quasar mode this step
    dt_myr: float = 0.0  # Myr the step took (SAGE26's dT)
    radio_accretion: float = 0.0  # Msun accreted in radio mode this step
    # Its accretion before SAGE26 caps heating at cooling (newer SAGE26's
    # RadioModeBHaccretionMassUncapped; -1 without): the jet's power.
    radio_accretion_uncapped: float = -1.0
    ics: float = 0.0  # IntraClusterStars, Msun
    outflow_rate: float = 0.0  # Msun/yr
    mdot_stream: float = 0.0  # cold-stream accretion through a hot halo
    cooling_log: float = 0.0  # log10 cooling luminosity, erg/s
    rcool_to_rvir: float = -1.0
    concentration: float = 8.0
    mass_loading: float = 1.5
    heating_log: float = 0.0  # radio-mode AGN heating, log10 erg/s
    # -- the snapshot and the halo --
    redshift: float = 0.0
    ffb: int = 0  # feedback-free starburst halo (FFBRegime)
    vel: tuple = (0.0, 0.0, 0.0)  # km/s, box frame
    vmax: float = 0.0  # km/s (halo)
    vvir: float = 0.0  # km/s (halo virial velocity)
    vel_disp: float = 0.0  # km/s (halo)
    mvir: float = 0.0  # Msun
    # -- satellites --
    infall_mvir: float = 0.0  # Msun (subhalo mass when it fell in)
    infall_stellar_mass: float = 0.0  # Msun
    t_since_infall_gyr: float = -1.0  # <0: a central
    merge_type: int = 0  # 1 minor, 2 major, 4 disrupting (before next snap)
    # -- structure --
    merger_bulge_radius_kpc: float = 0.0  # classical bulge
    instability_bulge_radius_kpc: float = 0.0  # pseudo-bulge
    # -- metals (Msun) --
    metals_bulge: float = 0.0
    metals_hot: float = 0.0
    metals_cgm: float = 0.0
    metals_ics: float = 0.0
    sfr_disk_z: float = 0.0  # metal mass fraction of star-forming gas
    # -- gas cycle --
    ejected: float = 0.0  # Msun
    ics_disrupt: float = 0.0  # Msun (in-situ ICS)
    ics_accrete: float = 0.0  # Msun (accreted ICS)
    r_heat_kpc: float = 0.0  # AGN heating radius
    tcool_gyr: float = 0.0
    tff_gyr: float = 0.0
    mdot_cool: float = 0.0  # hot-halo cooling rate (relative units)
    # Stellar mass formed (Msun) in each SFH_AGES lookback bin, disk and
    # bulge; empty without SAGE's full SFH (SaveFullSFH).
    # A lightcone's photometry by component: (f_I / f_V, f_B / f_V) of the
    # disk, bulge and intracluster stars, and shares of the light in V.
    sed_disk: tuple = ()
    sed_bulge: tuple = ()
    sed_ics: tuple = ()
    bulge_share: float = -1.0  # <0: no such photometry
    agn_share: float = 0.0
    ics_share: float = 0.0
    ha_share: float = 0.0
    lum_v: float = 0.0  # relative luminosity in V, 0 without photometry
    # Discs in annuli: radii (kpc), surface densities of stars, HI, H2 and
    # star formation, then dust and Toomre Q if the run has them (else ());
    # () for a run without annuli.
    radial: tuple = ()
    disc_height_kpc: float = 0.0  # stars, from their dispersion; 0 unknown
    bulge_rotation: float = 0.0  # merger bulge's j / (r sigma); 0 unknown
    sfh_disk: tuple = ()
    sfh_bulge: tuple = ()
    # The massive haloes around it (its cosmic web): (dx, dy, dz, weight)
    # per neighbour, unit directions in the simulation frame, weight
    # Mvir / d^2 relative to the strongest.
    web: tuple = ()
    # Face-on V-band optical depth of its diffuse ISM from the lightcone's
    # synthetic photometry (TauV_ISM); <0: none, HD estimates its own.
    tau_v_ism: float = -1.0
    # A disc in annuli: its face-on optical depth as the photometry finds
    # it, each annulus a screen of its own dust weighted by its share of the
    # old stars (adapter.disc_screen); <0: no annuli.
    tau_disc: float = -1.0
    # DarkSAGEMode: angle (deg) between the gas disc's spin and the stars';
    # <0: not in the run.
    gas_tilt_deg: float = -1.0
    # DustySAGEMode: dust masses (Msun); DarkSAGEMode: the disc's rotation
    # (km/s) and shear (1 - dlnV/dlnR) at 2.2 Rd.  0: not in the run.
    cold_dust: float = 0.0
    hot_dust: float = 0.0
    cgm_dust: float = 0.0
    disc_vrot: float = 0.0
    disc_shear: float = 0.0
    # Its observed-frame flux ratios in the bands standing in for HD's
    # I and B channels, relative to V (f_I / f_V, f_B / f_V), from the
    # lightcone's synthetic photometry; () = none.
    sed_ratio: tuple = ()
    # Unit vector from the galaxy to the observer (world frame); () = none.
    los: tuple = ()

    @property
    def bt(self) -> float:
        return self.bulge_mass / max(self.stellar_mass, 1.0)

    @property
    def ssfr(self) -> float:
        return (self.sfr_disk + self.sfr_bulge) / max(self.stellar_mass, 1.0)

    @property
    def stellar_metallicity(self) -> float:
        """Stellar metallicity in solar units (Z_sun = 0.02)."""
        return self.metals_stellar_mass / max(self.stellar_mass, 1.0) / 0.02

    @property
    def metallicity(self) -> float:
        """Cold-gas metallicity in solar units (Z_sun = 0.02)."""
        return self.metals_cold_gas / max(self.cold_gas, 1.0) / 0.02


@dataclass
class GalaxyRecipe:
    """Morphological parameters derived from the SAGE numbers."""

    kind: str  # "disk" | "elliptical"
    seed: int
    extent: float  # half-width of the frame, in Rd
    # Disk
    n_arms: int = 2
    pitch_deg: float = 18.0
    arm_sharpness: float = 4.0
    flocculence: float = 0.3
    # Individual arms (model units / radians): class, strength, start and
    # end radius, angular offset.  Empty -> n_arms identical full arms.
    arm_class: str = "grand"
    arm_amp: tuple = ()
    arm_r0: tuple = ()
    arm_r1: tuple = ()
    arm_off: tuple = ()
    hz: float = 0.10
    thick_frac: float = 0.0  # the thick disc's share of the old disc's light
    bulge_a: float = 0.15  # Hernquist scale, in Rd
    bulge_q: float = 0.75
    bar_len: float = 0.0  # bar half-length, in Rd (0 = no bar)
    bar_axis: float = 0.28
    hole: float = 0.5  # radius of the gas/young-star deficit at the centre
    hi_scale: float = 2.2
    arm_old_amp: float = 0.45  # spiral contrast in the old stars
    # Luminosities (arbitrary units, relative)
    l_disk: float = 1.0
    l_bulge: float = 0.2
    l_bar: float = 0.0
    l_young: float = 0.3
    l_nucleus: float = 0.0
    nucleus_sigma: float = 0.02
    tau0: float = 1.0  # face-on V-band optical depth scale of the dust
    # (Annuli) The star-weighted face-on optical depth the dust map is
    # scaled to, -ln sum(w e^-tau) with w the old stars' (disc and bulge)
    # share of each place; <0: none (tau0 sets the map).  The bulge's share
    # of the old stars and its radius (model units), for w.
    tau_star: float = -1.0
    l_ion: float = 0.0  # ionised gas's light (GAS), relative like l_young
    dust_wb: float = 0.0
    dust_rb: float = 0.2
    dust_k: tuple = tuple(DUST_K)  # extinction per channel, relative to V
    # Per-channel gain on the galaxy's light (I, V, B channels) matching
    # its integrated colour to its synthetic photometry (lightcone); 1 =
    # HD's own colours.
    col_gain: tuple = (1.0, 1.0, 1.0)
    # DarkSAGE's discs (model units): radii, then stars, HI, H2, SFR.
    radial: tuple = ()
    lane: float = 1.0  # darkness of the arm dust lanes
    h2_share: float = 0.5  # of the dust: in the H2 (the rest with the HI)
    hii_group: int = 4  # HII regions per star-forming complex (up to)
    hii_spread: float = 0.06  # a complex's size, Rd
    n_clusters: int = 1500
    n_hii: int = 300
    n_field: int = 25000
    # Elliptical
    axes: tuple = (1.0, 0.8, 0.65)
    env_a: float = 0.75
    core_frac: float = 0.4
    # Shared extras (both kinds)
    old_rgb: tuple = (1.00, 0.78, 0.52)  # tinted by stellar metallicity
    bulge_rgb: tuple = (1.00, 0.70, 0.42)
    l_icl: float = 0.0  # intracluster light, relative to the main body
    icl_a: float = 3.0  # its Hernquist scale, model units
    shells: float = 0.0  # merger shell strength (0-1)
    tails: float = 0.0  # tidal tail strength (0-1)
    stream: float = 0.0  # minor-merger stream strength (0-1)
    agn: float = 0.0  # quasar-mode nucleus luminosity
    ring: float = 0.0  # nuclear starburst ring strength
    ring_r: float = 0.4
    agn_style: str = "glow"  # point | glow | spikes
    ring_style: str = (
        "clusters_dust"  # clusters | clusters_dust | starburst | starburst_dust
    )
    n_gc: int = 0
    dust_lane: float = 0.0
    # Pseudo-bulge (instability-built: compact, flattened) beside the
    # classical (merger) bulge above; peanut: the bar's vertical buckle.
    l_pseudo: float = 0.0
    pseudo_a: float = 0.08
    pseudo_q: float = 0.35
    peanut: float = 0.0
    clumps: int = 0  # giant star-forming clumps (high-z / FFB disks)
    trunc_r: float = 0.0  # gas/young-star disk cut-off radius (0 = none)
    hii_rgb: tuple = tuple(HII_RGB)
    hii_f: float = 0.5  # its HII colour between poor (0) and rich (1)
    icl_rgb: tuple = tuple(ICL_RGB)
    icl_streams: float = 0.0  # streams feeding the ICL (0-1)
    icl_n_streams: int = 3  # how many disrupted satellites they come from
    halpha: float = 0.0  # cluster-core cooling filaments (0-1)
    halpha_len: float = 0.0  # their reach, model units
    unit_kpc: float = 1.0  # physical size of one model length unit
    # From the star-formation history (1 without it): light per unit mass
    # of the disk / bulge populations relative to a 10 Gyr one, and the
    # share of the disk's light from 0.1-1 Gyr-old stars.
    lm_disk: float = 1.0
    lm_bulge: float = 1.0
    inter_frac: float = 0.0
    inter_rgb: tuple = (0.95, 0.94, 0.97)
    # Inside-out colour gradient of a disk's old light (from its SFH):
    # colour at the centre and from grad_r (model units) out; () = none.
    lopsided: float = 0.0  # m=1 asymmetry of a dwarf irregular (0-1)
    lop_phase: float = 0.0
    old_in_rgb: tuple = ()
    old_out_rgb: tuple = ()
    grad_r: float = 3.0
    # Type within its class (morph_subtype), and what it draws: an
    # irregular's in-plane axis ratio and its angle, a bar's offset from the
    # centre (model units); a lenticular's lens, rings (radii, Rd), dust
    # ("ring", "lane", "twisted") and the dust sheet's tilt and its axis
    # (deg).
    subtype: str = ""
    elong: float = 1.0
    elong_pa: float = 0.0
    bar_off: tuple = (0.0, 0.0)
    lens: float = 0.0
    s0_rings: tuple = ()
    dust_style: str = ""
    lane_tilt: float = 0.0
    lane_pa: float = 0.0
    notes: list = field(default_factory=list)


def display_sizes(g: SageGalaxy) -> tuple[float, float, list]:
    """Disk scale length and elliptical half-light radius, in kpc: SAGE26's
    own.  DiskRadius is the disk's exponential scale length (Mo, Mao &
    White 1998, from the halo's spin); BulgeRadius the bulge's 3D
    half-mass radius, whose projected half-light radius is 0.752 times it
    for a Hernquist profile.  Without them, the observed size-mass
    relations of Shen et al. (2003), smaller in the past (van der Wel et
    al. 2014: late types ~ (1+z)^-0.75, early types ~ (1+z)^-1.48).
    """
    m = max(g.stellar_mass, 1e7)
    if g.los and g.disk_radius_kpc > 0:
        # On a lightcone: SAGE26's own radii, as its images and photometry.
        r50 = (
            HERNQUIST_RE / (1 + np.sqrt(2)) * g.bulge_radius_kpc
            if g.bulge_radius_kpc > 0
            else 2.88e-6 * m**0.56
        )
        note = f"size: SAGE26 Rd={g.disk_radius_kpc:.2f}, R50={r50:.2f} kpc"
        return float(g.disk_radius_kpc), float(r50), [note]
    zf = 1.0 + max(g.redshift, 0.0)
    if g.disk_radius_kpc > 0:
        rd = g.disk_radius_kpc
    else:
        r50_late = 0.10 * m**0.14 * (1 + m / 3.98e10) ** 0.25
        rd = r50_late / 1.678 * zf**-0.75 * (0.6 if g.ffb else 1.0)
    if g.bulge_radius_kpc > 0:
        r50e = HERNQUIST_RE / (1 + np.sqrt(2)) * g.bulge_radius_kpc
    else:
        r50e = 2.88e-6 * m**0.56 * zf**-1.48
    notes = [f"size: Rd={rd:.2f} kpc, R50(early)={r50e:.2f} kpc"]
    return float(rd), float(r50e), notes


# Projected half-light radius of a Hernquist profile (Hernquist 1990), and
# the 3D half-mass radius of a 3D exponential, in units of their scales.
HERNQUIST_RE = 1.8153
EXPONENTIAL_R3 = 2.674


def _hernquist_light(s):
    """Fraction of a Hernquist profile's light projected within s = R / a
    (Hernquist 1990, eq. 37)."""
    s = np.asarray(s, float)
    if abs(s - 1.0) < 1e-6:
        return 1.0 / 3.0
    x = (
        np.arccosh(1.0 / s) / np.sqrt(1.0 - s * s)
        if s < 1
        else np.arccos(1.0 / s) / np.sqrt(s * s - 1.0)
    )
    return float(s * s * (x - 1.0) / (1.0 - s * s))


def two_hernquist_re(core_frac: float, a_core: float, a_env: float) -> float:
    """Projected half-light radius of core + envelope Hernquist profiles
    (an elliptical's body), in their own units."""
    lo, hi = 1e-3, 100.0
    for _ in range(60):
        r = 0.5 * (lo + hi)
        f = core_frac * _hernquist_light(r / a_core) + (
            1 - core_frac
        ) * _hernquist_light(r / a_env)
        lo, hi = (r, hi) if f < 0.5 else (lo, r)
    return 0.5 * (lo + hi)


def _extras(
    g: SageGalaxy,
    rc_kw: dict,
    main_light: float,
    unit_kpc: float,
    notes: list,
    rng,
) -> dict:
    """Properties both kinds share: colour, ICL, merger debris, AGN."""

    # Metallicity tints old light (metal-rich -> redder): the disk by its
    # own stars' metallicity, the bulge by the bulge's.
    def tint(z_solar):
        zs = np.clip(np.log10(max(z_solar, 1e-3)), -1.0, 0.5)
        return np.array([1.0, 0.80 - 0.06 * zs, 0.56 - 0.12 * zs])

    z_disk = g.stellar_metallicity
    z_bulge = g.stellar_metallicity
    if g.metals_bulge > 0 and g.bulge_mass > 0:
        z_bulge = g.metals_bulge / g.bulge_mass / 0.02
        disk_m = g.stellar_mass - g.bulge_mass
        if disk_m > 0:
            z_disk = (
                max(g.metals_stellar_mass - g.metals_bulge, 0.0)
                / disk_m
                / 0.02
            )
    out = dict(
        old_rgb=tuple(tint(z_disk)),
        bulge_rgb=tuple(tint(z_bulge) * np.array([1.0, 0.9, 0.82])),
    )
    notes.append(
        f"Z(disk)={z_disk:.2f}, Z(bulge)={z_bulge:.2f} Zsun -> old-star tints"
    )
    # With a star-formation history: each population's colour and light
    # follow its age too (younger: bluer, brighter per unit mass), the
    # disk's and the bulge's from their own histories (an elliptical's
    # from both); metallicity still tints them as above.
    elliptical = rc_kw.get("kind") == "elliptical"
    both = (
        tuple(np.add(g.sfh_disk, g.sfh_bulge))
        if g.sfh_disk and g.sfh_bulge
        else ()
    )
    pd = population(both if elliptical else g.sfh_disk)
    pb = population(both if elliptical else g.sfh_bulge)
    solar = tint(1.0)
    if pd is not None:
        rgb, lm, inter = pd
        out["old_rgb"] = tuple(rgb * tint(z_disk) / solar)
        out["lm_disk"] = lm
        out["inter_frac"] = inter
        # Inside-out: the centre older, the outskirts younger.
        if not elliptical and GRADIENT > 0:
            pin = population(_weighted(g.sfh_disk, GRADIENT))
            pout = population(_weighted(g.sfh_disk, -GRADIENT))
            if pin is not None and pout is not None:
                out["old_in_rgb"] = tuple(pin[0] * tint(z_disk) / solar)
                out["old_out_rgb"] = tuple(pout[0] * tint(z_disk) / solar)
        mi = np.maximum(np.asarray(g.sfh_disk, float)[1:3], 0.0) * SFH_LM[1:3]
        if mi.sum() > 0:
            out["inter_rgb"] = tuple(
                (mi[:, None] * SFH_RGB[1:3]).sum(axis=0) / mi.sum()
            )
        notes.append(
            f"disk SFH -> light/mass x{lm:.2f}, {inter:.0%} of its light "
            "from 0.1-1 Gyr stars"
        )
    if pb is not None:
        rgb, lm, _ = pb
        out["bulge_rgb"] = tuple(
            rgb * tint(z_bulge) / solar * np.array([1.0, 0.9, 0.82])
        )
        out["lm_bulge"] = lm
        notes.append(f"bulge SFH -> light/mass x{lm:.2f}")
    # HII colour from the star-forming gas's metallicity.
    if g.sfr_disk_z > 0:
        f = float(np.clip((np.log10(g.sfr_disk_z / 0.02) + 1.0) / 1.5, 0, 1))
        poor = HII_LOOK["poor"] or HII_POOR_RGB
        rich = HII_LOOK["rich"] or HII_RICH_RGB
        out["hii_rgb"] = tuple(
            np.asarray(poor) * (1 - f) + np.asarray(rich) * f
        )
        out["hii_f"] = f
    elif HII_LOOK["poor"] is not None:
        out["hii_rgb"] = tuple(
            0.5 * (np.asarray(HII_LOOK["poor"]) + np.asarray(HII_LOOK["rich"]))
        )
    # ICL colour from its metallicity, and streams where satellites were
    # recently torn apart into it (in-situ ICS).
    if g.ics > 0 and g.metals_ics > 0:
        zi = np.clip(np.log10(g.metals_ics / g.ics / 0.02), -1.0, 0.3)
        out["icl_rgb"] = tuple(
            ICL_RGB * np.array([1.0, 1.0 - 0.05 * zi, 1.0 - 0.18 * zi])
        )
    if ICL_LOOK["rgb"] is not None:
        out["icl_rgb"] = tuple(ICL_LOOK["rgb"])
    if ICL_MODE == "share" and g.ics > 0:
        # Streams where the ICS was torn from satellites in place; ICS that
        # arrived already diffuse (accreted) makes a smooth envelope.
        made = g.ics_disrupt + g.ics_accrete
        share = g.ics_disrupt / made if made > 0 else 0.0
        amount = np.clip((np.log10(g.ics) - 10.0) / 1.5, 0.0, 1.0)
        if share * amount > 0.05:
            out["icl_streams"] = float(amount * share**0.5)
    elif g.ics_disrupt > 0:
        out["icl_streams"] = float(
            np.clip((np.log10(g.ics_disrupt) - 10.5) / 1.5, 0.0, 1.0)
        )
    if g.ics_disrupt > 0:
        # More streams the more satellite mass was torn apart (log, 1-6).
        out["icl_n_streams"] = int(
            np.clip(round(1 + 2.5 * np.log10(g.ics_disrupt / 1e11)), 1, 6)
        )
    # Cluster cores: where the hot atmosphere still cools -- faster than
    # ~10 free-fall times where SAGE has tcool/tff, or (hot regime) with a
    # cooling radius reaching beyond the AGN-heated core r_heat -- gas
    # rains out into cold H-alpha filaments (Perseus-like), brighter the
    # more is cooling.
    # (SAGE's radio-mode heating reaches past the cooling radius in every
    # cluster-mass halo, so in practice this picks out the rare ~1e12 Msun
    # hot haloes still cooling: gas raining onto the galaxy.)
    unstable = 0.0
    if g.regime == 1 and g.mdot_cool > 0 and g.mvir > 1e12:
        if g.tcool_gyr > 0 and g.tff_gyr > 0:
            unstable = float(np.clip((10 - g.tcool_gyr / g.tff_gyr) / 8, 0, 1))
        if g.rcool_to_rvir > 0:
            rcool = g.rcool_to_rvir * g.rvir_kpc
            net = (rcool - g.r_heat_kpc) / max(rcool, 1e-6)
            unstable = max(unstable, float(np.clip(net / 0.6, 0, 1)))
    if HALPHA_FILAMENTS and unstable > 0.5:
        out["halpha"] = float(
            unstable * np.clip(np.log10(g.mdot_cool) / 2.2, 0.25, 1.0)
        )
        reach = np.clip(0.15 * g.rvir_kpc, 20.0, 80.0)
        if g.r_heat_kpc > 0:
            reach = min(reach, 0.8 * g.r_heat_kpc)
        out["halpha_len"] = float(max(reach, 8.0) / unit_kpc)
        notes.append(
            f"core still cooling ({unstable:.2f}) -> H-alpha filaments "
            f"{out['halpha']:.2f}"
        )

    # Intracluster stars: a faint, very extended envelope (~50 kpc).
    if g.ics > 0 and g.bulge_share >= 0:
        # Set against the photometry once built (layer.photometry_closure),
        # spread like the images' NFW, to its half-light radius.
        from visage.sed.mock_image import _concentration, nfw_half_light

        c = float(_concentration(np.array(g.concentration), g.mvir))
        half = nfw_half_light(c) * g.rvir_kpc
        out["l_icl"] = float(0.1 * main_light) if g.ics_share > 0 else 0.0
        out["icl_a"] = float(half / (1 + np.sqrt(2)) / unit_kpc)
    elif g.ics > 0:
        # As bright as SAGE26's IntraClusterStars against the galaxy's own
        # stars (both old: the same light per unit mass), spread over the
        # halo, so its surface brightness stays low.
        ratio = g.ics / max(g.stellar_mass, 1.0)
        out["l_icl"] = float(ratio * main_light)
        out["icl_a"] = float(np.clip(0.12 * g.rvir_kpc, 20, 250) / unit_kpc)
        notes.append(
            f"ICS={g.ics:.2e} ({g.ics / g.stellar_mass:.2f} of M*) -> ICL envelope"
        )

    # Merger debris fades over a few dynamical times, which are shorter at
    # high z: 4 Gyr (major) and 2.5 Gyr (minor) at z = 0, / (1+z).
    zf = 1.0 + max(g.redshift, 0.0)
    t_maj, t_min = 4000 / zf, 2500 / zf
    # A major merger throws out tidal tails (Toomre & Toomre 1972) for its
    # first ~1.5 Gyr, then the remnant shows shells; a minor one leaves
    # shells round a bulge-dominated host (Quinn 1984), a stream round a
    # disk.
    if 0 <= g.t_major_myr < t_maj:
        f = float(1 - g.t_major_myr / t_maj)
        kind = "tails" if g.t_major_myr < 1500 / zf else "shells"
        out[kind] = f
        notes.append(
            f"major merger {g.t_major_myr / 1e3:.1f} Gyr ago -> {kind} {f:.2f}"
        )
    if 0 <= g.t_minor_myr < t_min:
        f = float(1 - g.t_minor_myr / t_min)
        kind = "shells" if g.bt > 0.5 else "stream"
        out[kind] = max(out.get(kind, 0.0), f)
        notes.append(
            f"minor merger {g.t_minor_myr / 1e3:.1f} Gyr ago -> {kind} {f:.2f}"
        )

    # Quasar-mode accretion this step: a bright, bluish point nucleus.
    # (Below ~1e4 Msun a step there is nothing an observer would see:
    # SAGE26's black holes start at zero, so a dwarf's first merger or
    # instability "accretes" its whole, tiny new black hole at once.)
    if g.bulge_share >= 0:
        # Its share of the light, set once built; none if hidden.
        out["agn"] = 0.01 if g.agn_share > 0 else 0.0
    elif g.qso_accretion >= 1e4 and g.dt_myr > 0:
        # Its mean accretion rate over the step, at a radiative efficiency
        # of 0.1 (L = 0.1 Mdot c^2), a tenth of it in the optical (Elvis
        # et al. 1994), against the host's light (M/L ~ 2).  The shader
        # draws 9.6 x agn against the galaxy's main light.
        mdot = g.qso_accretion / (g.dt_myr * 1e6)  # Msun/yr
        l_opt = 0.1 * mdot * 5.66e46 / 10.0 / 3.828e33  # Lsun
        ratio = l_opt / max(g.stellar_mass / 2.0, 1.0)
        out["agn"] = float(np.clip(ratio * main_light / 9.6, 0.0, 20.0))
        notes.append(
            f"quasar-mode accretion {mdot:.2e} Msun/yr -> AGN/host {ratio:.3f}"
        )
    return out


def is_elliptical(g: SageGalaxy) -> bool:
    """HD draws `g` as an elliptical, not a disk.  Morphology: bulge
    fraction decides, Regime only breaks ties in the ambiguous middle
    (hot-mode haloes with a big bulge and no gas)."""
    gas_frac = g.cold_gas / max(g.cold_gas + g.stellar_mass, 1.0)
    return g.bt > 0.75 or (g.bt > 0.5 and g.regime == 1 and gas_frac < 0.02)


def recipe_from_sage(
    g: SageGalaxy, arm_class: str | None = None
) -> GalaxyRecipe:
    """`arm_class` forces a disk's arm class (default: drawn from its
    SAGE properties)."""
    rng = np.random.default_rng(int(g.galaxy_index) & 0x7FFFFFFF)
    gas_frac = g.cold_gas / max(g.cold_gas + g.stellar_mass, 1.0)
    bt = g.bt
    lm = np.log10(max(g.stellar_mass, 1.0))
    rd, r50e, notes = display_sizes(g)

    elliptical = is_elliptical(g)
    notes.append(
        f"B/T={bt:.2f}, regime={'hot' if g.regime else 'cold'}, "
        f"f_gas={gas_frac:.3f} -> {'elliptical' if elliptical else 'disk'}"
    )

    if elliptical:
        # Massive ellipticals are rounder, with a more extended envelope
        # (higher Sersic n, cD-like) and far richer globular systems.
        mfac = np.clip((lm - 10.0) / 2.0, 0.0, 1.0)
        # Fast rotators (flattened, nearly oblate) below ~2e11 Msun, slow
        # rotators (round, triaxial) above it (Emsellem et al. 2011;
        # Cappellari 2016); a recent major merger makes a slow one likelier.
        p_slow = 1.0 / (1.0 + (2e11 / max(g.stellar_mass, 1.0)) ** 2)
        if 0 <= g.t_major_myr < 3000:
            p_slow = min(1.0, p_slow + 0.2)
        slow = rng.random() < p_slow
        if slow:
            b = rng.uniform(0.8, 0.95)
            c = b * rng.uniform(0.75, 0.95)
        else:
            b = rng.uniform(0.9, 1.0)
            c = rng.uniform(0.3, 0.5)
        if g.bulge_rotation > 0:
            # With annuli, the bulge's own rotation (j / r sigma, about 1 to
            # 15) in place of the halo's: slow rotators are rounder.
            spin = np.log10(np.clip(g.bulge_rotation, 1.0, 15.0)) / np.log10(
                15.0
            )
            c = b * float(0.9 - 0.4 * spin)
        env_a = float(0.6 + 0.6 * mfac)
        core_frac = float(0.5 - 0.2 * mfac)
        n_gc = int(np.clip(30 * (g.stellar_mass / 1e10) ** 1.2, 20, 4000))
        dust = np.clip(np.log10(max(g.h2_gas, 1.0)) - 7.5, 0.0, 2.0) / 2.0
        if g.cold_dust > 0:
            # DustySAGE's dust (~1% of the gas: 10^7.5 Msun of H2 ~ 10^5.5).
            dust = np.clip(np.log10(g.cold_dust) - 5.5, 0.0, 2.0) / 2.0
        if g.tau_v_ism == 0:
            dust = 0.0  # its photometry's dust: none
        notes.append(
            f"{'slow' if slow else 'fast'} rotator (p_slow {p_slow:.2f}): "
            f"b/a={b:.2f}, c/a={c:.2f}; envelope a={env_a:.2f}, "
            f"core {core_frac:.2f}, {n_gc} globulars"
        )
        if dust > 0:
            notes.append(
                f"H2={g.h2_gas:.2e} -> nuclear dust lane strength {dust:.2f}"
            )
        # So the body's projected half-light radius is r50e (its core's
        # Hernquist scale is 0.22, as gpu.py draws it).
        unit = float(r50e / two_hernquist_re(core_frac, 0.22, env_a))
        ex = _extras(g, {"kind": "elliptical"}, 1.0, unit, notes, rng)
        return GalaxyRecipe(
            **ex,
            kind="elliptical",
            seed=int(rng.integers(1 << 31)),
            extent=3.5 + 2.0 * mfac,
            axes=(1.0, b, c),
            n_gc=n_gc,
            dust_lane=float(dust),
            l_bulge=1.0,
            env_a=env_a,
            core_frac=core_frac,
            l_nucleus=float(
                0.03
                * np.clip((g.bh_mass / max(g.bulge_mass, 1)) / 2e-3, 0.2, 5)
                ** 0.5
            ),
            nucleus_sigma=0.01,
            n_clusters=0,
            n_hii=0,
            n_field=40000,
            notes=notes,
            unit_kpc=unit,
        )

    # --- Disk ---------------------------------------------------------
    disk_mass = g.stellar_mass - g.bulge_mass

    # Pitch angle from the black hole (Davis et al. 2017: log M_BH = 7.01 -
    # 0.171 (|phi| - 15 deg), scatter ~3 deg); without one yet (SAGE26's
    # black holes start at zero), tighter arms with a bigger bulge.
    # With DarkSAGE's rotation curve, from the disc's shear instead (Seigar
    # et al. 2006: pitch = 64.25 - 36.62 shear).
    if g.disc_shear > 0:
        pitch = 64.25 - 36.62 * g.disc_shear
    elif g.bh_mass > 0:
        pitch = 15.0 + (7.01 - np.log10(g.bh_mass)) / 0.171
    else:
        pitch = 28.0 - 30.0 * bt
    pitch = float(np.clip(pitch + rng.normal(0, 3.0), 5.0, 40.0))
    # Bars where the stellar disk is unstable to them (Efstathiou, Lake &
    # Negroponte 1982: eps = Vmax / sqrt(G M_disk / Rd) < 1.1, from
    # SAGE26's Vmax, disk stars and DiskRadius), stronger the further below.
    # Gas-rich disks, with fewer stars for their size, are barred less
    # often, as observed (Masters et al. 2012).
    bar_strength = 0.0
    v_bar = g.disc_vrot if g.disc_vrot > 0 else g.vmax
    if v_bar > 0 and disk_mass > 0:
        eps = v_bar / np.sqrt(4.30091e-6 * disk_mass / max(rd, 0.1))
        bar_strength = float(np.clip((1.1 - eps) / 0.4, 0.0, 1.0))
    barred = bar_strength > 0.05
    # Arm class (`arm_class` forces one): grand design, multi-arm (or 2 arms branching into 4),
    # partial / not fully formed (lopsided, short arms) or flocculent.
    if barred:
        p_cls = (0.55, 0.25, 0.20, 0.0)
    elif lm > 10.8:
        p_cls = (0.45, 0.30, 0.25, 0.0)
    elif gas_frac > 0.15 or lm < 10.0:
        p_cls = (0.10, 0.25, 0.30, 0.35)
    else:
        p_cls = (0.30, 0.35, 0.25, 0.10)
    drawn = str(
        rng.choice(["grand", "multi", "partial", "flocculent"], p=p_cls)
    )
    # Clumpy star-forming disks: ~60% of star-forming galaxies at z ~ 2,
    # fewer at higher mass and few below z ~ 0.5 (Guo et al. 2015), and
    # gas-rich ones (SAGE26's cold-gas fraction); a feedback-free starburst
    # always is.
    p_clumpy = float(
        0.6
        * np.clip((g.redshift - 0.5) / 1.5, 0.0, 1.0)
        * np.clip(gas_frac / 0.2, 0.0, 1.0)
        * np.clip(1.0 - 0.3 * (lm - 9.5), 0.5, 1.0)
    )
    if g.ffb or rng.random() < p_clumpy:
        drawn = "clumpy"
    if lm < DWARF["max_lm"] and gas_frac > 0.15:
        drawn = "irregular"
    arm_class = arm_class or drawn
    # Gas richness places the flocculence within the class's range.
    gasness = float(
        np.clip(
            (3.0 * gas_frac + 0.15 * (10.3 - lm) + rng.normal(0, 0.08)) / 0.75,
            0.0,
            1.0,
        )
    )
    lo, hi = {
        "grand": (0.05, 0.25),
        "multi": (0.15, 0.4),
        "partial": (0.3, 0.55),
        "flocculent": (0.6, 0.85),
        "clumpy": (0.7, 0.9),
        "irregular": (0.8, 0.95),
    }[arm_class]
    flocc = lo + (hi - lo) * gasness
    sharp = float(np.clip(5.0 * (1 - flocc) + 1.5, 1.5, 6.0))
    if MORPHOLOGY and arm_class == "flocculent":
        # Far more flocculent: many short, thin arcs (FLOCCULENT).
        lo, hi = FLOCCULENT["flocc"]
        flocc = lo + (hi - lo) * gasness
        sharp = FLOCCULENT["sharp"]
    # Thickness (sech^2 z0, in Rd) from the disk's size, as observed edge-on
    # (Bershady et al. 2010, from Kregel et al. 2002: log(hR/hz) =
    # 0.367 log(hR/kpc) + 0.708, hz exponential = z0 / 2): smaller disks
    # are relatively thicker.  High-z (turbulent) disks are thicker still.
    hz = 2.0 / (5.11 * max(rd, 0.3) ** 0.367)
    hz *= 1.0 + 0.5 * min(max(g.redshift, 0.0), 3.0)
    hz = float(min(hz, 0.6))
    if g.disc_height_kpc > 0:
        hz = float(np.clip(g.disc_height_kpc / rd, 0.02, 0.6))

    # Bulges: the classical (merger-built) one round, at its own radius;
    # the pseudo-bulge (instability-built) compact and flattened at its own.
    # SAGE26's BulgeMass and BulgeRadius (3D half-mass) are the whole bulge
    # (MergerBulge + InstabilityBulge, mass-weighted radius); the two parts
    # only say how much of it is classical (merger-built) and how much
    # pseudo (instability-built).  Both are drawn at BulgeRadius.
    rb = g.bulge_radius_kpc if g.bulge_radius_kpc > 0 else 0.2 * rd
    split = g.merger_bulge_mass > 0 or g.instability_bulge_mass > 0
    bulge_a = float(np.clip(rb / rd / (1 + np.sqrt(2)), 0.03, 0.4))
    merger_share = g.merger_bulge_mass / max(g.bulge_mass, 1.0)
    bulge_q = float(0.85 if split else 0.5 + 0.4 * merger_share)
    if g.los:
        from visage.sed.mock_image import bulge_axis_ratio

        bulge_q = float(bulge_axis_ratio(g.galaxy_index))
    # (An exponential, Sersic n ~ 1, as pseudo-bulges are: Kormendy &
    # Kennicutt 2004.)
    pseudo_a = float(np.clip(rb / rd / EXPONENTIAL_R3, 0.02, 0.25))

    # Bar: at most ~8% of M* goes into the bar; the rest of the
    # instability-grown bulge is a compact, flattened pseudobulge.  This
    # keeps gas-poor lenticulars from turning into one giant bar.
    bar_len = 0.0
    bar_axis = 0.28
    l_bar = 0.0
    bar_mass = 0.0
    if barred:
        # Up to ~8% of M* in the bar, taken from the instability bulge
        # where it has one; the rest of that bulge is a pseudo-bulge.
        bar_mass = bar_strength * 0.08 * g.stellar_mass
        bar_frac = bar_mass / max(g.stellar_mass, 1.0)
        # Half-length ~0.6 Rd in late types to ~1.4 Rd in early types
        # (Erwin 2005), by B/T; stronger bars are thinner (b/a 0.5 to 0.2).
        bar_len = float(0.6 + 0.8 * np.clip(bt / 0.3, 0.0, 1.0))
        bar_axis = float(0.5 - 0.3 * bar_strength)
        l_bar = 1.8 * OLD_LIGHT * bar_mass / max(disk_mass, 1.0)
        notes.append(
            f"bar strength {bar_strength:.2f} (disk stability) -> bar "
            f"{bar_frac:.2f} of M*, half-length {bar_len:.1f} Rd, b/a {bar_axis:.2f}"
        )
    pops = {"disk": population(g.sfh_disk), "bulge": population(g.sfh_bulge)}
    lm_d = pops["disk"][1] if pops["disk"] else 1.0
    lm_b = pops["bulge"][1] if pops["bulge"] else 1.0
    if split:
        l_bulge = OLD_LIGHT * g.merger_bulge_mass / max(disk_mass, 1.0)
        l_pseudo = (
            OLD_LIGHT
            * max(g.instability_bulge_mass - bar_mass, 0.0)
            / max(disk_mass, 1.0)
        )
    else:
        l_bulge = OLD_LIGHT * (g.bulge_mass - bar_mass) / max(disk_mass, 1.0)
        l_pseudo = 0.0
    # (Younger populations are brighter per unit mass: the disk's light
    # against the bulge's follows their histories.)
    l_bulge *= lm_b / lm_d

    # Young light relative to the old disk scales with specific SFR.
    ssfr_disk = g.sfr_disk / max(disk_mass, 1.0)
    l_young = float(np.clip(0.55 * (ssfr_disk / 1e-10) ** 0.7, 0.0, 1.5))
    if g.ffb:
        l_young = min(1.5 * l_young + 0.2, 2.0)  # very blue
    # (No floors: with no star formation, a disk has none -- a lenticular.)
    n_clusters = int(np.clip(6000 * max(g.sfr_disk, 0.0) ** 0.5, 0, 20000))
    # (Against a younger, brighter-per-mass disk the current young light
    # stands out less.)
    l_young /= lm_d
    # HII regions: number follows the molecular gas reservoir.
    n_hii = int(np.clip(350 * (max(g.h2_gas, 0.0) / 1e9) ** 0.8, 0, 3000))
    notes.append(f"H2={g.h2_gas:.2e} -> {n_hii} HII complexes")

    # Dust follows the hydrogen (SAGE26's H2gas and H1gas), at the Milky
    # Way's dust per hydrogen, A_V / N_H = 5.3e-22 mag cm^2 (Bohlin et al.
    # 1978): tau_V = 0.061 per Msun pc^-2, scaled by metallicity (SAGE26's
    # Z / 0.02) and falling faster below a quarter solar (Remy-Ruyer et al.
    # 2014).  tau0: the face-on optical depth at the centre of an
    # exponential disk holding it all.
    zfac = max(g.metallicity, 0.0)
    dgr = zfac if zfac >= 0.26 else 0.26 * (zfac / 0.26) ** 3.1
    gas_h = g.h2_gas + g.h1_gas
    area = 2 * np.pi * (rd * 1e3) ** 2  # pc^2
    tau0 = float(np.clip(0.061 * dgr * gas_h / area, 0, 5))
    notes.append(
        f"H2+HI={gas_h:.2e} Msun, Z={zfac:.2f} Zsun -> tau0={tau0:.2f}"
    )
    if g.cold_dust > 0:
        # DustySAGE's own dust mass: the same Milky Way opacity, per unit
        # dust (dust / H = 0.010: Draine 2011) instead of from metallicity.
        tau0 = float(np.clip(0.061 / 0.010 * g.cold_dust / area, 0, 5))
        notes.append(f"ColdDust={g.cold_dust:.2e} Msun -> tau0={tau0:.2f}")
    dust_k = tuple(DUST_K)
    if np.isfinite(g.tau_v_ism) and g.tau_v_ism >= 0:
        # The photometry's own dust (lightcone): the same optical depth
        # in front of the stars, so HD dims and reddens the galaxy as its
        # magnitudes do, and with the same attenuation curve.
        tau0 = float(g.tau_v_ism / SED_TAU_MEAN)
        dust_k = tuple(SED_DUST_K)
        notes.append(
            f"photometry: tau_V(ISM)={g.tau_v_ism:.2f} -> tau0={tau0:.2f}"
        )
    tau_star = -1.0
    if g.tau_disc >= 0 and g.radial:
        # A disc in annuli, box or lightcone: its dust is the annuli's, as
        # the photometry has it (by annulus, star-weighted); the map keeps
        # its shape and is scaled to it (build_disk_maps).
        tau_star = float(g.tau_disc)
        tau0 = float(g.tau_disc / SED_TAU_MEAN)
        notes.append(f"annuli: star-weighted face-on tau_V={g.tau_disc:.2f}")
    # Thin dark lanes only in disks rotating faster than ~120 km/s
    # (Dalcanton et al. 2004; SAGE26's Vmax for the rotation).
    # (The disc's own rotation where DarkSAGE has it, else the halo's Vmax.)
    vrot = g.disc_vrot if g.disc_vrot > 0 else g.vmax
    fast = float(np.clip((vrot - 100.0) / 40.0, 0.0, 1.0))
    lane = float(np.clip(tau0 / 2.0, 0.0, 2.5)) * fast
    if g.tau_v_ism == 0:
        lane = 0.0  # its photometry's dust: none
    # Star-forming complexes: richer where star formation is denser
    # (SFR surface density), bigger in gas-richer disks (larger Jeans
    # mass: cold-gas fraction).
    sig_sfr = g.sfr_disk / (np.pi * max(rd, 0.3) ** 2)  # Msun/yr/kpc^2
    hii_group = int(
        # (8 at a typical disk's ~3e-3 Msun/yr/kpc^2: Kennicutt 1998.)
        np.clip(8 + 10 * np.log10(max(sig_sfr, 1e-6) / 3e-3), 2, 24)
    )
    hii_spread = float(0.06 * np.clip(0.4 + 1.5 * gas_frac, 0.4, 1.8))

    # Black hole sets how concentrated / bright the nucleus is.
    l_nuc = float(0.012 * np.clip(g.bh_mass / 1e7, 0.01, 300) ** 0.5)
    nuc_sig = float(
        np.clip(0.03 / (1 + np.log10(max(g.bh_mass, 1e6) / 1e6)), 0.006, 0.04)
    )
    notes.append(
        f"M_BH={g.bh_mass:.2e} -> nucleus L={l_nuc:.3f}, sigma={nuc_sig:.3f} Rd"
    )

    hi_scale = float(
        np.clip(1.6 + g.h1_gas / max(g.h2_gas, 1) * 0.15, 1.6, 3.5)
    )
    extent = float(np.clip(3.2 + 0.9 * hi_scale, 4.5, 6.5))

    ex = _extras(
        g,
        {"kind": "disk"},
        OLD_LIGHT * g.stellar_mass / max(disk_mass, 1.0),
        rd,
        notes,
        rng,
    )
    # A nuclear star-forming ring at the bar's inner Lindblad resonance:
    # bars funnel gas there, so rings sit in barred, gas-bearing disks
    # (~20% of disks: Comeron et al. 2010), brighter the stronger the bar
    # and the more of the star formation SAGE26 puts in the bulge.
    sfr_tot = g.sfr_disk + g.sfr_bulge
    if bar_strength > 0.5 and g.h2_gas > 0 and sfr_tot > 0:
        share = g.sfr_bulge / sfr_tot
        ex["ring"] = float(np.clip(bar_strength * (0.4 + share), 0.1, 1.0))
        ex["ring_r"] = float(max(0.35 * bar_len, 3.0 * bulge_a, 0.25))
        notes.append(
            f"bar {bar_strength:.2f}, SfrBulge share {share:.2f} -> nuclear "
            f"ring {ex['ring']:.2f} at {ex['ring_r']:.2f} Rd"
        )

    subtype = morph_subtype(g, arm_class, barred, l_young)
    arms = arm_layout(
        arm_class,
        extent,
        max(bar_len, 0.3),
        np.random.default_rng(rng.integers(1 << 31)),
        subtype,
    )
    notes.append(f"arms: {arm_class}, {len(arms[0])} arm(s)")
    clumps = 0
    if arm_class == "clumpy":
        clumps = int(
            np.clip(4 + 6 * gas_frac / 0.3 + (3 if g.ffb else 0), 4, 12)
        )
        notes.append(
            f"z={g.redshift:.1f}{' FFB' if g.ffb else ''} -> {clumps} giant clumps"
        )
        l_young *= CLUMPY["young"]
        n_clusters = max(int(n_clusters * CLUMPY["clusters"]), 50)
    lopsided = lop_phase = 0.0
    if arm_class == "irregular":
        lo, hi = DWARF["clumps"]
        clumps = int(
            np.clip(lo + (hi - lo) * np.log10(1 + 10 * g.sfr_disk), lo, hi)
        )
        lopsided = float(rng.uniform(*DWARF["lopsided"]))
        lop_phase = float(rng.uniform(0, 2 * np.pi))
        hz = max(hz, DWARF["hz"])
        notes.append(
            f"dwarf irregular: {clumps} clumps, lopsided {lopsided:.2f}"
        )
    morph = {}
    if subtype in IRREGULAR:
        par = IRREGULAR[subtype]
        lo, hi = par["clumps"]
        clumps = int(
            np.clip(lo + (hi - lo) * np.log10(1 + 10 * g.sfr_disk), lo, hi)
        )
        n_hii = int(n_hii * par["hii"])
        if "elong" in par:
            morph.update(
                elong=par["elong"], elong_pa=float(rng.uniform(0, np.pi))
            )
        if "bar_off" in par and bar_len > 0:
            a = rng.uniform(0, 2 * np.pi)
            off = par["bar_off"] * bar_len
            morph["bar_off"] = (float(off * np.cos(a)), float(off * np.sin(a)))
        notes.append(f"irregular: {subtype}, {clumps} star clouds")
    elif subtype.startswith("s0_"):
        # A lenticular: no spiral, and dust only where its type puts it.
        peak = _peak_radius(g.radial, rd)
        if subtype == "s0_barred":
            r_in, r_out = (k * max(bar_len, 0.5) for k in LENTICULAR["rings"])
            if peak > 1.3 * r_in:
                r_out = peak  # (DarkSAGE: where its gas is)
            morph.update(lens=LENTICULAR["lens"], s0_rings=(r_in, r_out))
        if subtype == "s0_ring":
            morph.update(
                dust_style="ring", s0_rings=(peak if 0 < peak < 2.5 else 0.8,)
            )
        if subtype == "s0_lane":
            morph["dust_style"] = "lane"
        if subtype == "s0_disturbed":
            tilt = (
                g.gas_tilt_deg
                if g.gas_tilt_deg > 30
                else rng.uniform(*LENTICULAR["tilt"])
            )
            morph.update(
                dust_style="twisted",
                lane_tilt=float(min(tilt, 90.0)),
                lane_pa=float(rng.uniform(0, 180)),
            )
        if not morph.get("dust_style"):
            tau0 = 0.0
        elif LENTICULAR["dust"] == "mass":
            # Its dust mass (DustySAGE's, else ~1% of its gas at solar
            # metallicity) at the Milky Way's opacity, not the photometry's
            # star-weighted depth: gathered into its ring or lane, it shows.
            m_dust = (
                g.cold_dust
                if g.cold_dust > 0
                else 0.01 * g.metallicity * g.cold_gas
            )
            tau0 = float(
                0.061 / 0.010 * m_dust / (2 * np.pi * (rd * 1e3) ** 2)
            )
            tau_star = -1.0
        lane = 0.0
        notes.append(f"lenticular: {subtype}")
    elif subtype:
        notes.append(f"flocculent: {subtype}")
    # Satellites: ram pressure and tides strip the gas disk from the
    # outside in, the longer since infall and the more of the subhalo
    # lost; star formation (young light, dust) stops beyond the cut.
    trunc_r = 0.0
    if g.gtype > 0 and g.t_since_infall_gyr >= 0:
        f_dm = (
            np.clip(g.mvir / g.infall_mvir, 0.0, 1.0)
            if g.infall_mvir > 0
            else 1.0
        )
        keep = (
            1.0
            - 0.55 * (1 - np.exp(-g.t_since_infall_gyr / 1.5))
            - 0.35 * (1 - f_dm)
        )
        keep = float(np.clip(keep, 0.25, 1.0))
        if keep < 0.97:
            trunc_r = keep * extent
            notes.append(
                f"satellite {g.t_since_infall_gyr:.1f} Gyr since infall, "
                f"subhalo {f_dm:.2f} of infall -> gas disk cut at {keep:.2f} of R"
            )

    return GalaxyRecipe(
        **ex,
        kind="disk",
        seed=int(rng.integers(1 << 31)),
        extent=extent,
        n_arms=len(arms[0]),
        arm_class=arm_class,
        arm_amp=arms[0],
        arm_r0=arms[1],
        arm_r1=arms[2],
        arm_off=arms[3],
        pitch_deg=pitch,
        arm_sharpness=sharp,
        flocculence=flocc,
        hz=hz,
        thick_frac=thick_share(g),
        bulge_a=bulge_a,
        bulge_q=bulge_q,
        bar_len=bar_len,
        l_bar=l_bar,
        l_pseudo=float(l_pseudo),
        pseudo_a=pseudo_a,
        bar_axis=bar_axis,
        peanut=0.0,
        # Pseudo-bulges are disk-like: flattened (Kormendy & Kennicutt 2004).
        pseudo_q=0.45,
        clumps=clumps,
        subtype=subtype,
        **morph,
        trunc_r=trunc_r,
        lopsided=lopsided,
        lop_phase=lop_phase,
        hole=float(max(bar_len * 0.9, 2.5 * bulge_a, 0.25)),
        hi_scale=hi_scale,
        arm_old_amp=(
            0.0
            if arm_class in ("clumpy", "irregular")
            or subtype.startswith("s0_")
            else float(0.45 * min(1.0, gas_frac / 0.08))
        ),
        l_disk=OLD_LIGHT,
        l_bulge=float(l_bulge),
        l_young=l_young,
        l_nucleus=l_nuc,
        nucleus_sigma=nuc_sig,
        tau0=tau0,
        tau_star=tau_star,
        l_ion=float(l_young * GAS["ion"] * NEBULA.get(subtype, 1.0)),
        dust_wb=float(np.clip(g.bt, 0.0, 1.0)),
        dust_rb=float(max(g.bulge_radius_kpc, 0.05) / rd),
        h2_share=float(g.h2_gas / gas_h) if gas_h > 0 else 0.5,
        dust_k=dust_k,
        lane=lane,
        hii_group=hii_group,
        hii_spread=hii_spread,
        n_clusters=n_clusters,
        n_hii=n_hii,
        n_field=60000,
        notes=notes,
        radial=(
            ()
            if not g.radial
            else (tuple(x / rd for x in g.radial[0]), *g.radial[1:])
        ),
        unit_kpc=float(rd),
    )


# ----------------------------------------------------------------------
# Noise
# ----------------------------------------------------------------------


def gaussian_field(shape, slope, rng, aniso=(1.0, 1.0), periodic_only=True):
    """Unit-variance Gaussian random field with P(k) ~ k^-slope."""
    ky = np.fft.fftfreq(shape[0])[:, None] * aniso[0]
    kx = np.fft.fftfreq(shape[1])[None, :] * aniso[1]
    k = np.sqrt(kx**2 + ky**2)
    k[0, 0] = np.inf
    amp = k ** (-slope / 2.0)
    phase = rng.normal(size=shape) + 1j * rng.normal(size=shape)
    f = np.real(np.fft.ifft2(amp * phase))
    return (f - f.mean()) / f.std()


# ----------------------------------------------------------------------
# Disk-plane maps
# ----------------------------------------------------------------------


@dataclass
class PlaneMaps:
    """Surface-density maps sampled on a square grid in the galaxy plane."""

    half: float  # grid covers [-half, half]^2 in Rd
    old: np.ndarray
    young: np.ndarray
    dust: np.ndarray
    hi: np.ndarray
    h2: np.ndarray
    arm: np.ndarray
    # Dark lanes on the arms' inner edges, as a thin screen in front of the
    # disk's light (optical depth), or None.
    lanes: np.ndarray | None = None
    # Ionised gas round the star formation (emission per area, shape).
    ion: np.ndarray | None = None

    def sample(self, name, xg, yg):
        arr = getattr(self, name)
        n = arr.shape[0]
        ix = (xg + self.half) / (2 * self.half) * (n - 1)
        iy = (yg + self.half) / (2 * self.half) * (n - 1)
        return map_coordinates(
            arr, [iy.ravel(), ix.ravel()], order=1, mode="constant", cval=0.0
        ).reshape(xg.shape)


# Clumpy (high-z / FFB) disks: how their young light and giant clumps are
# drawn.  young / clusters scale the young light and the number of young
# clusters; amp, base, width and wing shape the giant clumps against the
# young disk; conc, spread and hii how the clusters and HII regions follow
# them (higher conc: more on the clumps).
# Chosen by the user from options on SAGE26 galaxies ("E5", a little more
# diffuse): a calm disk, young light only faintly gathered into clumps.
CLUMPY = dict(
    young=0.28,
    clusters=0.08,
    amp=0.12,
    base=1.0,
    width=(0.35, 0.7),
    wing=0.5,
    conc=1.0,
    spread=1.5,
    hii=1.2,
)
# Types of irregulars, lenticulars and flocculent spirals, from their SAGE26
# properties (morph_subtype).  False: one look for each class, as before.
MORPHOLOGY = True
# Irregulars by type: their giant star clouds (how many, how far out as a
# share of the disc, their size in Rd, brightness against the young disc)
# and HII regions (x).  disturbed: in-plane axis ratio; barred: the bar's
# offset from the centre (x its half-length), as in Magellanic irregulars
# (de Vaucouleurs & Freeman 1972).
IRREGULAR = {
    "clouds": dict(
        clumps=(6, 12), spread=0.8, width=(0.2, 0.45), amp=2.0, hii=1.0
    ),
    "fading": dict(
        clumps=(1, 3), spread=0.6, width=(0.3, 0.5), amp=0.5, hii=0.3
    ),
    "starburst": dict(
        clumps=(3, 6), spread=0.35, width=(0.15, 0.3), amp=3.0, hii=1.8
    ),
    "disturbed": dict(
        clumps=(4, 8),
        spread=0.8,
        width=(0.2, 0.4),
        amp=2.0,
        hii=1.0,
        elong=0.45,
    ),
    "barred": dict(
        clumps=(3, 6),
        spread=0.7,
        width=(0.2, 0.4),
        amp=2.0,
        hii=1.0,
        bar_off=0.35,
    ),
}
# Gas in the disc, drawn with Gas (off: the optical galaxy alone) and
# ray-marched with its stars and dust: ionised gas glowing round the star
# formation (its light x the young light, how blue against the HII colour,
# its thickness in Rd), and the molecular clouds' dust: in optical light
# H2 is seen by its dust, not its own glow (optical depth x the disc's
# 99th percentile).  (The HI disc is gpu_gas's.)
GAS = dict(
    ion=1.5,
    ion_blue=0.05,
    ion_h=0.08,
    # (Its filaments: the random field's slope, ridge width, and the diffuse
    # glow between them.)
    ion_slope=3.0,
    ion_ridge=0.25,
    ion_floor=0.05,
    # (How far it spreads round the star formation, disc scale lengths.)
    ion_wide=0.15,
    h2_dust=85.0,
    # (Its filaments: the random field's slope and ridge width, on the H2
    # map smoothed over this many Rd.)
    h2_slope=3.0,
    h2_ridge=0.3,
    h2_smooth=0.25,
)
# The ionised gas's light by type, x GAS's ion.
NEBULA = {"fading": 0.25, "starburst": 1.6, "floc_fading": 0.25}
# Lenticulars: a lens round the bar (its surface brightness x the disc's at
# its edge) and inner and outer rings (x the bar's half-length; Kormendy
# 1979; Buta & Combes 1996); dust (Msun) from which one
# is dusty, and from which a lane; a disturbed one's tilt range (deg); the
# share of the dust drawn as a screen in front of the stars.
LENTICULAR = dict(
    lens=1.5,
    rings=(1.0, 2.2),
    ring_amp=1.0,
    dusty=1e5,
    lane=3e6,
    tilt=(20.0, 50.0),
    screen=0.7,
    # "photometry": the star-weighted depth the photometry finds (runs with
    # annuli); "mass": its dust mass, gathered where its type puts it.
    dust="mass",
)
# Flocculent spirals (Elmegreen & Elmegreen 1987): how many short arcs
# (massive ones more), their length
# (ln of end / start radius), flocculence range and arc sharpness.
FLOCCULENT = dict(
    n=(18, 30),
    massive_n=(25, 40),
    length=(0.15, 0.4),
    flocc=(0.5, 0.7),
    sharp=12.0,
)


def morph_subtype(
    g: SageGalaxy, arm_class: str, barred: bool, l_young: float
) -> str:
    """A disc's type within its class, from its SAGE26 properties: irregulars
    by bar, disturbance and sSFR; flocculent spirals by mass and sSFR;
    lenticulars (discs with no young light) by dust, mergers, misaligned gas
    and bar.  "" for everything else."""
    if not MORPHOLOGY:
        return ""
    lssfr = np.log10(g.ssfr + 1e-14)
    zf = 1.0 + max(g.redshift, 0.0)
    minor = 0 <= g.t_minor_myr < 1500 / zf
    if arm_class == "irregular":
        if barred:
            return "barred"
        if minor or (g.gtype > 0 and 0 <= g.t_since_infall_gyr < 1.5):
            return "disturbed"
        if lssfr > -9.7:
            return "starburst"
        return "fading" if lssfr < -10.7 else "clouds"
    if arm_class == "flocculent" and l_young >= 0.02:
        if np.log10(max(g.stellar_mass, 1.0)) > 10.3:
            return "floc_massive"
        return "floc_fading" if lssfr < -11.5 else "floc_starforming"
    if arm_class == "clumpy" or l_young >= 0.02:
        return ""
    # Lenticular.  Its dust: DustySAGE's, else ~1% of its gas at solar metallicity.
    dust = (
        g.cold_dust if g.cold_dust > 0 else 0.01 * g.metallicity * g.cold_gas
    )
    dusty = dust > LENTICULAR["dusty"] or g.h2_gas > 1e7
    merger = minor or 0 <= g.t_major_myr < 2000 / zf
    if dusty and (merger or g.gas_tilt_deg > 30):
        return "s0_disturbed"
    if dusty:
        return "s0_lane" if dust > LENTICULAR["lane"] else "s0_ring"
    return "s0_barred" if barred else "s0_smooth"


def _peak_radius(rc_radial, rd, rmin=0.4):
    """Model-frame radius (Rd) where a disc in annuli holds most dust, else
    gas (HI + H2), past rmin; 0 without annuli."""
    if not rc_radial:
        return 0.0
    r = np.asarray(rc_radial[0], float) / rd
    v = np.asarray(
        (
            rc_radial[5]
            if len(rc_radial) > 5 and len(rc_radial[5])
            else np.add(rc_radial[2], rc_radial[3])
        ),
        float,
    )
    ok = r > rmin
    if not ok.any() or v[ok].max() <= 0:
        return 0.0
    return float(r[ok][np.argmax(v[ok])])


# Merger debris (shells, tails, streams): its share of the galaxy's light
# (x 0.05 for shells, 0.08 for tails; chosen from options 2026-11-07, twice
# the 0.65 before, as faint debris barely showed: shells up to ~6%, tails
# ~10% of the light just after a merger).
DEBRIS = 1.3


def arm_layout(cls: str, extent: float, r_base: float, rng, subtype: str = ""):
    """Individual arms for an arm class: (amplitudes, start radii, end
    radii, angular offsets), radii in model units."""
    u = rng.uniform
    amp, r0, r1, off = [], [], [], []

    def arm(a, ra, rb, o):
        amp.append(float(a))
        r0.append(float(ra))
        r1.append(float(rb))
        off.append(float(o))

    if cls == "irregular" and subtype == "barred":
        # A Magellanic barred irregular: one loose arm off the bar's end.
        arm(u(0.7, 0.9), r_base, extent * u(0.6, 0.85), u(0, 2 * np.pi))
        return tuple(amp), tuple(r0), tuple(r1), tuple(off)
    if cls in ("clumpy", "irregular"):
        return (), (), (), ()
    if cls == "grand":
        for k in range(2):
            arm(
                u(0.9, 1.0),
                r_base,
                extent * u(0.95, 1.1),
                k * np.pi + rng.normal(0, 0.1),
            )
    elif cls == "multi":
        if rng.random() < 0.5:
            # Two arms that each branch in the outer disk.
            rb = r_base + u(1.0, 2.0)
            for k in range(2):
                o = k * np.pi + rng.normal(0, 0.1)
                arm(u(0.85, 1.0), r_base, extent * u(0.9, 1.05), o)
                arm(u(0.55, 0.8), rb, extent * u(0.8, 1.0), o + u(0.6, 1.0))
        else:
            m = int(rng.choice([3, 4]))
            for k in range(m):
                arm(
                    u(0.6, 1.0),
                    r_base * u(1.0, 1.8),
                    extent * u(0.75, 1.05),
                    2 * np.pi * k / m + rng.normal(0, 0.2),
                )
    elif cls == "partial":
        # Not fully formed: lopsided, arms of unequal strength and length.
        m = int(rng.choice([2, 3], p=[0.6, 0.4]))
        for k in range(m):
            arm(
                1.0 if k == 0 else u(0.3, 0.7),
                r_base * u(1.0, 2.5),
                extent * u(0.45, 0.85),
                2 * np.pi * k / m + rng.normal(0, 0.45),
            )
    elif MORPHOLOGY:
        # Flocculent: many short, thin arcs, no coherent arms.
        n = FLOCCULENT["massive_n" if subtype == "floc_massive" else "n"]
        for _ in range(int(rng.integers(*n))):
            ra = u(0.4, 0.9 * extent)
            arm(
                u(0.3, 1.0),
                ra,
                min(ra * np.exp(u(*FLOCCULENT["length"])), extent),
                u(0, 2 * np.pi),
            )
    else:
        # Flocculent: many short arm segments.
        for _ in range(int(rng.integers(6, 10))):
            ra = u(0.6, 0.65 * extent)
            arm(
                u(0.4, 1.0),
                ra,
                min(ra * np.exp(u(0.5, 1.1)), extent),
                u(0, 2 * np.pi),
            )
    return tuple(amp), tuple(r0), tuple(r1), tuple(off)


def _arm_field(rc, r, th, lnr0, tanp, wobble, shift, sharp):
    """Soft union of the recipe's individual arms (each a log spiral lobe
    tapered between its start and end radius), peak 1."""
    if rc.arm_class in ("clumpy", "irregular") and not rc.arm_amp:
        return np.zeros_like(r)  # (no spiral arms at all)
    amps = rc.arm_amp or (1.0,) * rc.n_arms
    r0s = rc.arm_r0 or (0.0,) * len(amps)
    r1s = rc.arm_r1 or (1e9,) * len(amps)
    offs = rc.arm_off or tuple(
        2 * np.pi * k / len(amps) for k in range(len(amps))
    )
    base = th - (np.log(r) - lnr0) / tanp + 0.45 * wobble
    out = np.ones_like(r)
    for a, ra, rb, o in zip(amps, r0s, r1s, offs, strict=True):
        d = np.angle(np.exp(1j * (base - o))) + shift
        lobe = np.exp(-sharp * d * d)
        taper = 1 / (1 + np.exp(-(r - ra) / (0.15 * max(ra, 0.2))))
        taper *= 1 / (1 + np.exp((r - rb) / (0.12 * rb)))
        out *= 1 - a * lobe * taper
    return (1 - out) * arm_reach(rc, r)


MIN_ANNULUS = 0.15  # of the disc radius


def radial_scale(rc, which: int, r, base) -> np.ndarray | float:
    """What turns an exponential map (`base` at radius r) into DarkSAGE's own
    profile `which`, 1 at the disc's scale radius; 1 for any other model."""
    if not rc.radial:
        return 1.0
    edge = np.asarray(rc.radial[0], float)
    v = np.asarray(rc.radial[which], float)
    # Held flat inside MIN_ANNULUS: the disc has one height, so a peak there
    # would be drawn as a column of light along its axis.
    ok = (v > 0) & (edge >= MIN_ANNULUS)
    if ok.sum() < 3:
        return 1.0
    rc_ = np.maximum(r, edge[ok].min())
    lg = np.interp(
        np.log(np.maximum(rc_, 1e-3)), np.log(edge[ok]), np.log(v[ok])
    )
    # Falls away beyond the last annulus with any of it.
    lg = lg - 4.0 * np.clip(rc_ - edge[ok].max(), 0, None)
    want = np.exp(lg - np.interp(0.0, np.log(edge[ok]), np.log(v[ok])))
    return want / np.maximum(base / np.mean(base[np.abs(r - 1) < 0.05]), 1e-6)


def arm_reach(rc, r) -> np.ndarray | float:
    """How much of a spiral pattern a disc with annuli holds at radius r:
    all where Toomre Q <= 1, none where Q >= 2, as it's stable; 1 without Q."""
    if len(rc.radial) < 7 or not rc.radial[6]:
        return 1.0
    x = np.log(np.maximum(np.asarray(rc.radial[0], float), 1e-4))
    q = np.log(np.maximum(np.asarray(rc.radial[6], float), 0.01))
    here = np.interp(np.log(np.maximum(r, 1e-3)), x, q)
    return np.clip(np.log(2.0 / np.exp(here)) / np.log(2.0), 0.0, 1.0)


def _star_weighted_scale(rc, dust, old, r, dl, lanes, outer_cut, inner):
    """Factor on the dust map making its star-weighted face-on optical depth
    -ln sum(w e^-tau) equal rc.tau_star: w the old stars' share of each
    place (the disc's map and, for the bulge's share of the old stars, an
    exponential of its radius, as the photometry weighs its annuli), tau the
    map plus the arm lanes' screen in front of it (not scaled).  Its
    face-on depth is kept to TAU_MAX: where the stars sit mostly away from
    the dust (a big bulge over a thin disc's), it falls short of tau_star
    rather than piling up dust.  (Its 99th percentile: a narrow lane or
    clump may go deeper.)"""
    w = (1.0 - rc.dust_wb) * old / max(float(old.sum()), 1e-30)
    if rc.dust_wb > 0:
        b = np.exp(-r / max(rc.dust_rb, 1e-3))
        w = w + rc.dust_wb * b / max(float(b.sum()), 1e-30)
    lane = 0.0
    if dl["boost"] > 0:
        lane = (
            dl["boost"]
            * rc.lane
            * lanes
            / max(float(lanes.max()), 1e-9)
            * np.exp(-r / dl["reach"])
            * outer_cut
            * inner
        )

    def screen(s):
        return -np.log(
            max(float(np.sum(w * np.exp(-(s * dust + lane)))), 1e-300)
        )

    if rc.tau_star <= 0 or screen(0.0) >= rc.tau_star:
        return 0.0
    lo, hi = 0.0, 1.0
    while screen(hi) < rc.tau_star and hi < 1e6:
        hi *= 2.0
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if screen(mid) < rc.tau_star else (lo, mid)
    d99 = np.percentile(dust[dust > 0], 99) if (dust > 0).any() else 0.0
    return min(0.5 * (lo + hi), TAU_MAX / max(float(d99), 1e-30))


def _ionised_gas(rc, sf, n, half):
    """Ionised gas round the star formation `sf` (H2 x young light): a
    network of glowing filaments and bubble rims (the ridges of a random
    field, as HD draws the CGM's filaments) over where the stars form."""
    f = gaussian_field(
        (n, n), GAS["ion_slope"], np.random.default_rng(rc.seed + 61)
    )
    ridges = np.exp(-((f / GAS["ion_ridge"]) ** 2))
    sf = gaussian_filter(sf, GAS["ion_wide"] * n / (2 * half))
    return ((sf**0.8) * (GAS["ion_floor"] + ridges)).astype(np.float32)


def cloud_dust(rc, maps):
    """Face-on optical depth of the molecular clouds' dust (drawn with Gas):
    the H2 map (peak 1) as dark filaments, the ridges of a random field (as
    the ionised gas is drawn; mean 1), as dust lanes cross a disc, at GAS's
    h2_dust x the disc dust's 99th percentile and within TAU_MAX.  The H2
    map is smoothed first, so the arm lanes' streaks don't draw it as a
    spiral."""
    d = maps.dust[maps.dust > 0]
    if not d.size:
        return np.zeros_like(maps.dust)
    n = maps.h2.shape[0]
    h2 = gaussian_filter(maps.h2, GAS["h2_smooth"] * n / (2 * maps.half))
    h2 /= max(float(h2.max()), 1e-30)
    f = gaussian_field(
        h2.shape, GAS["h2_slope"], np.random.default_rng(rc.seed + 62)
    )
    ridges = np.exp(-((f / GAS["h2_ridge"]) ** 2))
    tau = GAS["h2_dust"] * float(np.percentile(d, 99)) * h2 * ridges
    return np.minimum(tau / ridges.mean(), TAU_MAX).astype(np.float32)


def build_disk_maps(rc: GalaxyRecipe, n=2048) -> PlaneMaps:
    rng = np.random.default_rng(rc.seed)
    half = rc.extent * 1.6
    ax = np.linspace(-half, half, n)
    x, y = np.meshgrid(ax, ax)
    if rc.elong < 1:
        # A disturbed irregular, drawn out along one axis (area kept).
        c, sn = np.cos(rc.elong_pa), np.sin(rc.elong_pa)
        x, y = (x * c + y * sn) * np.sqrt(rc.elong), (
            y * c - x * sn
        ) / np.sqrt(rc.elong)
    r = np.hypot(x, y) + 1e-3
    th = np.arctan2(y, x)

    tanp = np.tan(np.deg2rad(rc.pitch_deg))
    lnr = np.log(np.maximum(r, 0.05))

    # Log-polar noise, stretched along the spiral: sampled in (u = ln r,
    # v = arm phase) so features become arm-aligned filaments.
    nu, nv = 512, 1024

    def spiral_noise(slope, stretch, seed_off):
        g = gaussian_field(
            (nu, nv),
            slope,
            np.random.default_rng(rc.seed + seed_off),
            aniso=(1.0, stretch),
        )
        u = (
            (lnr - np.log(0.05))
            / (np.log(half * 1.5) - np.log(0.05))
            * (nu - 1)
        )
        v = ((th - lnr / tanp) % (2 * np.pi)) / (2 * np.pi) * nv
        return map_coordinates(
            g, [u.ravel(), v.ravel()], order=1, mode="wrap"
        ).reshape(n, n)

    wobble = spiral_noise(3.5, 1.0, 1)  # large-scale arm irregularity
    fil = spiral_noise(2.2, 0.25, 2)  # fine filaments along arms
    clumps = gaussian_field((n, n), 2.6, rng)  # isotropic patchiness
    if rc.arm_class in ("clumpy", "irregular"):
        # No spiral to follow: star formation in isotropic patches.
        fil = clumps / max(float(clumps.std()), 1e-9)

    # Spiral pattern.  The arm starts at the bar ends (or near the centre).
    r0 = max(rc.bar_len, 0.3)
    rr0 = np.maximum(r, r0)
    arm_grand = _arm_field(
        rc, rr0, th, np.log(r0), tanp, wobble, 0.0, rc.arm_sharpness
    )
    floc = 1 / (1 + np.exp(-2.2 * fil))  # (0,1) filament field
    # Flocculent light sits mostly on the arms (so their shapes and ends
    # show), except in flocculent disks where it is the structure itself.
    fl_base = 0.6 if rc.arm_class == "flocculent" else 0.25
    if rc.subtype.startswith("floc_"):
        fl_base = 0.3  # (gaps between the arcs)
    arm = (1 - rc.flocculence) * arm_grand + rc.flocculence * floc * (
        fl_base + 1.0 * arm_grand
    )
    # Arms fade inside the bar / bulge.
    inner = 1 - np.exp(-((r / max(rc.hole, 0.2)) ** 4))
    arm_eff = arm * inner

    # (r in Rd, SAGE26's DiskRadius: the stars' exponential scale length.)
    exp_d = np.exp(-r)
    outer_cut = 1 / (1 + np.exp((r - rc.extent * 1.05) / 0.25))

    old = (
        exp_d
        * (1 + rc.arm_old_amp * (arm_eff - arm_eff.mean()))
        * np.exp(0.08 * clumps)
    )
    # (Faded smoothly to nothing between the disc's extent and the map's
    # edge, so the square never shows however deep the exposure.)
    s = np.clip((r - rc.extent) / (0.6 * rc.extent), 0.0, 1.0)
    old = old * radial_scale(rc, 1, r, exp_d) * (1 - s * s * (3 - 2 * s))
    if rc.radial:
        # Annuli can stay bright further out than the exponential: fade them
        # gently, so neither a rim nor the square map's edge shows.
        old = old * np.exp(-((r / rc.extent) ** 4))
    if rc.bar_len > 0:
        # The bar is built from the inner disk: hollow it out to match.
        old *= 1 - 0.65 * np.exp(-((r / (0.8 * rc.bar_len)) ** 2))
    if rc.lens > 0:
        # A barred lenticular's lens: a plateau round the bar, then rings.
        edge = 1.3 * max(rc.bar_len, 0.5)
        old = old + rc.lens * np.exp(-edge) * np.exp(-((r / edge) ** 8))
    for rr_ in rc.s0_rings if rc.lens > 0 else ():
        old = old + LENTICULAR["ring_amp"] * np.exp(-rr_) * np.exp(
            -(((r - rr_) / (0.1 * rr_)) ** 2)
        )

    young = (
        np.exp(-r / 1.35)
        * arm_eff**1.4
        * np.exp(0.6 * clumps - 0.18)
        * outer_cut
    )
    young = young * radial_scale(rc, 4, r, np.exp(-r / 1.35))
    for rr_ in rc.s0_rings if rc.lens > 0 else ():
        # (What star formation a ringed lenticular has left is in its rings.)
        young = young + np.exp(-(((r - rr_) / (0.1 * rr_)) ** 2)) * np.exp(
            -rr_ / 1.35
        )
    if rc.lopsided > 0:
        # A dwarf irregular: brighter on one side, its light and star
        # formation pushed off-centre (m = 1).
        lop = 1 + rc.lopsided * np.clip(r / rc.extent, 0, 1.5) * np.cos(
            th - rc.lop_phase
        )
        old = old * np.maximum(lop, 0.1)
        young = young * np.maximum(lop, 0.1) ** 1.5
    giant = np.zeros_like(r)
    if rc.clumps:
        # Giant star-forming clumps (high-z / feedback-free disks): a few
        # kpc-scale complexes in the young light and the gas -- broad, with
        # soft wings, so they blend into the turbulent disk around them
        # rather than sitting on it as separate balls.
        crng = np.random.default_rng(rc.seed + 31)
        par = (
            IRREGULAR.get(rc.subtype) if rc.arm_class == "irregular" else None
        )
        spread = par["spread"] if par else 0.75
        for _ in range(rc.clumps):
            rr = rc.extent * spread * np.sqrt(crng.random())
            tt = crng.uniform(0, 2 * np.pi)
            w = crng.uniform(*(par["width"] if par else CLUMPY["width"]))
            if par and rc.radial:
                # (DarkSAGE) Where its star formation is, by annulus, and
                # bigger where the disc is nearest unstable (Toomre Q ~ 1).
                re_ = np.asarray(rc.radial[0], float)
                sfr = (
                    np.asarray(rc.radial[4], float) * re_ * np.gradient(re_)
                )  # (x area)
                if sfr.sum() > 0:
                    rr = min(
                        float(
                            np.interp(
                                crng.random(), np.cumsum(sfr) / sfr.sum(), re_
                            )
                        ),
                        rc.extent,
                    )
                if len(rc.radial) > 6 and len(rc.radial[6]):
                    q = float(np.interp(rr, re_, rc.radial[6]))
                    w *= float(np.clip(1.4 / max(q, 0.1), 0.7, 1.6))
            d2 = (x - rr * np.cos(tt)) ** 2 + (y - rr * np.sin(tt)) ** 2
            giant += crng.uniform(0.5, 1.0) * (
                np.exp(-d2 / (2 * w * w))
                + CLUMPY["wing"] * np.exp(-d2 / (2 * (2.2 * w) ** 2))
            )
        if par and rc.subtype == "barred" and rc.bar_len > 0:
            # (LMC-like: young star clouds along the off-centre bar.)
            bx, by = rc.bar_off
            giant += np.exp(
                -(((x - bx) / rc.bar_len) ** 2)
                - ((y - by) / (0.3 * rc.bar_len)) ** 2
            )
        if par:
            # An irregular's star clouds: amp x the rest of its young light.
            young = young + par["amp"] * giant * young.sum() / max(
                float(giant.sum()), 1e-12
            )
        else:
            young = (
                CLUMPY["base"] * young
                + CLUMPY["amp"] * giant * np.exp(-r / 3.0) * outer_cut
            )

    # Dust lanes sit on the inner (concave) edge of the arm.
    dl = DUST_LANES
    arm_d = _arm_field(
        rc,
        rr0,
        th,
        np.log(r0),
        tanp,
        wobble,
        dl["width"],
        rc.arm_sharpness + dl["sharp"],
    )
    fil_d = 1 / (1 + np.exp(-3.5 * (fil + 0.3)))
    arm_dust = (
        (1 - rc.flocculence) * arm_d + rc.flocculence * fil_d * (0.4 + arm_d)
    ) * inner
    if dl["streaks"] > 0:
        # Lanes broken into thin filaments along the arms: noise that
        # changes fast across the arms (in arm phase) and slowly along
        # them, thresholded into ridges.
        from visage.hd.gpu import vnoise_baked

        u = th - np.log(rr0) / max(tanp, 1e-3)
        q = np.stack(
            [24 * np.cos(u), 24 * np.sin(u), 3.0 * np.log(rr0) + rc.seed % 97],
            axis=-1,
        )
        ridge = np.exp(-((vnoise_baked(q) / 0.22) ** 2))
        arm_dust = arm_dust * (
            1 - dl["streaks"] + dl["streaks"] * (0.25 + 1.8 * ridge)
        )
    h2 = (
        np.exp(-r / 0.9)
        * (0.08 + 2.5 * arm_dust ** dl["power"])
        * np.exp(0.5 * clumps)
    )
    lanes = arm_dust ** dl["power"]
    hi = (
        np.exp(-r / rc.hi_scale)
        * (1 - 0.7 * np.exp(-((r / 1.2) ** 2)))
        * (0.15 + arm_dust)
    )
    # H2 and HI follow the run's own gas. The dust is laid out as they are,
    # then follows the run's own dust where it has it.
    has_dust = len(rc.radial) > 5 and len(rc.radial[5]) > 0
    laid_h2, laid_hi = h2, hi
    h2 = h2 * radial_scale(rc, 3, r, np.exp(-r / 0.9))
    hi = hi * radial_scale(rc, 2, r, np.exp(-r / rc.hi_scale))
    if has_dust:
        laid_h2 = laid_h2 * radial_scale(rc, 5, r, np.exp(-r / 0.9))
        laid_hi = laid_hi * radial_scale(rc, 5, r, np.exp(-r / rc.hi_scale))
    else:
        laid_h2, laid_hi = h2, hi
    if rc.clumps:
        h2 = h2 + 1.5 * giant * np.exp(-r / 3.0)
        laid_h2 = laid_h2 + 1.5 * giant * np.exp(-r / 3.0)
    # (Each phase's share of the dust by its mass.)
    dust = (
        rc.h2_share * laid_h2 / max(float(laid_h2.sum()), 1e-12)
        + (1 - rc.h2_share) * laid_hi / max(float(laid_hi.sum()), 1e-12)
    ) * (outer_cut * inner)
    # Normalise the total dust column to that of a smooth exponential disk
    # with face-on optical depth tau0 at its centre (2 pi tau0 Rd^2).  An
    # integral rather than a ring average, so a central hole (bar) doesn't
    # inflate the normalisation.
    dA = (ax[1] - ax[0]) ** 2
    dust *= 2 * np.pi * rc.tau0 / max(dust.sum() * dA, 1e-9)
    if rc.dust_style:
        # A lenticular's little dust, gathered where its type puts it: a
        # nuclear ring, a lane across the disc, or twisted filaments.
        if rc.dust_style == "ring":
            R = rc.s0_rings[0] if rc.s0_rings else 0.8
            d = np.exp(-(((r - R) / (0.35 * R)) ** 2)) * (0.3 + floc)
        elif rc.dust_style == "lane":
            d = np.exp(-r / 2.5) * (1 - np.exp(-((r / 1.0) ** 2)))
            d = d * np.exp(-((r / (0.7 * rc.extent)) ** 6)) * (0.5 + floc)
        else:
            f = gaussian_field(
                (n, n), 2.4, np.random.default_rng(rc.seed + 41)
            )
            d = np.exp(-r / 1.5) * np.exp(-((f / 0.3) ** 2))
        dust = d * (2 * np.pi * rc.tau0 / max(d.sum() * dA, 1e-9))
    lane_screen = None
    if rc.tau_star >= 0:
        dust = dust * _star_weighted_scale(
            rc, dust, old, r, dl, lanes, outer_cut, inner
        )
    if dl["boost"] > 0 and not rc.dust_style:
        # Dark lanes on the arms' inner edges: a thin screen in front of the
        # disk's light (mixed in with the stars, as the dust above is, they
        # could never go dark).  Darker in dustier, metal-richer disks.
        lane_screen = (
            dl["boost"]
            * rc.lane
            * lanes
            / max(float(lanes.max()), 1e-9)
            * np.exp(-r / dl["reach"])
            * outer_cut
            * inner
        ).astype(np.float32)
    if rc.dust_style:
        # (Most of it a screen in front of the stars, so so little dust shows.)
        lane_screen = (LENTICULAR["screen"] * dust).astype(np.float32)
        dust = dust * (1 - LENTICULAR["screen"])
    if rc.ring > 0 and rc.ring_style in ("clusters_dust", "starburst_dust"):
        # Gas piles up at the ring: a dusty annulus just outside it, fed
        # (in barred galaxies) by two dust lanes along the bar's leading
        # edges.  Absolute optical depth, added after the normalisation so
        # it isn't diluted into the rest of the disk.
        rr = rc.ring_r
        clump = np.exp(
            0.4
            * gaussian_field((n, n), 2.8, np.random.default_rng(rc.seed + 5))
        )
        rd = RING_DUST
        dust += (
            rd["ring"]
            * rc.ring
            * np.exp(-(((r - 1.25 * rr) / (rd["width"] * rr)) ** 2))
            * clump
        )
        if rc.bar_len > 0 and rd["lanes"] > 0:
            soft = rd["taper"] * rc.bar_len + 1e-6
            for sgn in (1, -1):
                # Offset to the leading side, curving into the ring; faded
                # in and out at its ends rather than cut.
                yl = sgn * (0.10 * rc.bar_len + 0.18 * np.abs(x))
                w = rd["lane_w"] * rc.bar_len
                lane = np.exp(-(((y - yl) / w) ** 2))
                xs = sgn * x
                a = np.clip((xs - 0.9 * rr) / soft, -50, 50)
                b = np.clip((xs - 1.05 * rc.bar_len) / soft, -50, 50)
                lane *= 1 / (1 + np.exp(-a)) / (1 + np.exp(b))
                dust += rd["lanes"] * rc.ring * lane * clump

    if rc.trunc_r > 0:
        # Stripped satellite: no gas (so no young stars or dust) beyond
        # the cut; the old disk carries on, redder for it.
        cut = 1 / (1 + np.exp((r - rc.trunc_r) / 0.2))
        young, dust, h2, hi = young * cut, dust * cut, h2 * cut, hi * cut
    if rc.tau0 <= 0:
        # No dust at all (a lightcone galaxy whose photometry has none).
        dust = np.zeros_like(dust)
    return PlaneMaps(
        half=half,
        old=old.astype(np.float32),
        young=young.astype(np.float32),
        dust=dust.astype(np.float32),
        hi=hi.astype(np.float32),
        h2=h2.astype(np.float32),
        arm=arm_eff.astype(np.float32),
        lanes=lane_screen,
        ion=_ionised_gas(rc, h2 * young, n, half),
    )


# ----------------------------------------------------------------------
# Point populations (clusters, HII regions, globular clusters, field stars)
# ----------------------------------------------------------------------


@dataclass
class Points:
    pos: np.ndarray  # (N, 3) galaxy frame
    lum: np.ndarray  # (N,)
    rgb: np.ndarray  # (N, 3)
    sigma: np.ndarray  # (N,) PSF width in pixels
    name: str = ""


def _hii_colours(rc, x, y, rng) -> np.ndarray:
    """(n, 3) colours of HII complexes at (x, y) (model units = disk scale
    lengths): between HII_LOOK's poor and rich colours by the galaxy's own
    position (rc.hii_f), its abundance gradient and a per-region scatter
    (HII_LOOK gradient, mix)."""
    n = len(x)
    poor, rich = HII_LOOK["poor"], HII_LOOK["rich"]
    if poor is None or rich is None or n == 0:
        return np.tile(np.asarray(rc.hii_rgb), (n, 1))
    r = np.hypot(x, y)
    f = (
        rc.hii_f
        + HII_LOOK["gradient"] * (r - 2.0)
        + rng.normal(0.0, HII_LOOK["mix"], n)
    )
    f = np.clip(f, 0.0, 1.0)[:, None]
    return np.asarray(poor) * (1 - f) + np.asarray(rich) * f


def _sample_map(arr, half, n, rng):
    p = arr.ravel().astype(np.float64)
    p = np.clip(p, 0, None)
    p /= p.sum()
    idx = rng.choice(p.size, size=n, p=p)
    m = arr.shape[0]
    iy, ix = np.divmod(idx, m)
    px = (ix + rng.random(n)) / m * 2 * half - half
    py = (iy + rng.random(n)) / m * 2 * half - half
    return px, py


def build_points(rc: GalaxyRecipe, maps: PlaneMaps | None) -> list[Points]:
    rng = np.random.default_rng(rc.seed + 99)
    old_rgb = np.array(rc.old_rgb)
    out = []
    if rc.kind == "disk":
        # Young star clusters: sample complexes on the young map, then
        # scatter members around each complex (clusters of clusters).
        # (A clumpy disk's clusters spread through the turbulent disk
        # between its giant clumps too, not only on them.)
        n_cx = max(rc.n_clusters // 6, 10) if rc.n_clusters > 0 else 0
        conc = CLUMPY["conc"] if rc.clumps else 1.3
        if rc.arm_class == "irregular":
            conc = 2.0  # (its clusters crowd into its star clouds)
        cx, cy = _sample_map(maps.young**conc, maps.half, n_cx, rng)
        k = rng.integers(2, 11, n_cx)
        csz = np.repeat(rng.uniform(0.015, 0.06, n_cx), k)
        if rc.clumps:
            csz *= CLUMPY["spread"]
        px = np.repeat(cx, k) + rng.normal(0, 1, k.sum()) * csz
        py = np.repeat(cy, k) + rng.normal(0, 1, k.sum()) * csz
        m = len(px)
        lum = rng.pareto(1.3, m) + 1
        lum = np.minimum(lum, 25)
        lum *= rc.l_young * YOUNG_CLUSTERS / max(lum.sum(), 1e-30)
        # (A dwarf irregular's young stars fill its thick disc.)
        thick = 0.4 * rc.hz if rc.arm_class == "irregular" else 0.04
        pz = rng.normal(0, thick, m)
        rgb = CLUSTER_RGB[None, :] * rng.uniform(0.85, 1.15, (m, 1))
        out.append(
            Points(
                np.c_[px, py, pz],
                lum,
                rgb,
                rng.uniform(0.45, 0.9, m),
                "clusters",
            )
        )

        # HII regions: follow H2 where young stars are, soft and fuzzy.
        hx, hy = _sample_map(
            (maps.h2 * maps.young)
            ** (CLUMPY["hii"] if rc.clumps else HII_LOOK["conc"]),
            maps.half,
            rc.n_hii,
            rng,
        )
        cx, cy = hx, hy  # the complexes' centres
        # (Its own random stream: the rest of the galaxy is unchanged.)
        crgb = _hii_colours(rc, cx, cy, np.random.default_rng(rc.seed + 77))
        hi = max(int(round(rc.hii_group * HII_LOOK["knots"])), 1)
        k = rng.integers(max(hi // 3, 1), hi + 1, len(hx))
        sp = rc.hii_spread * HII_LOOK["spread"]
        hx = np.repeat(hx, k) + rng.normal(0, sp, k.sum())
        hy = np.repeat(hy, k) + rng.normal(0, sp, k.sum())
        m = len(hx)
        lum = rng.pareto(1.5, m) + 1
        lum = np.minimum(lum, 12)
        lum *= rc.l_young * HII_LOOK["gain"] / max(lum.sum(), 1e-30)
        out.append(
            Points(
                np.c_[hx, hy, rng.normal(0, 0.75 * thick, m)],
                lum,
                np.repeat(crgb, k, axis=0),
                HII_LOOK["size"] * rng.uniform(1.0, 2.0, m),
                "hii",
            )
        )
        # Intermediate-age (0.1-1 Gyr) clusters, from the star-formation
        # history: white to yellow-white, spread through the disk (they
        # have drifted from where they formed) -- a recently quenched or
        # fading disk keeps these after its HII regions are gone.
        if rc.inter_frac > 0.05:
            m = int(np.clip(4000 * rc.inter_frac, 200, 3000))
            ix, iy = _sample_map(
                maps.old**0.7 * (0.3 + maps.young) ** 0.3, maps.half, m, rng
            )
            lum = rng.pareto(1.8, m) + 1
            lum = np.minimum(lum, 15)
            lum *= rc.l_disk * rc.inter_frac * 0.25 / lum.sum()
            rgb = np.asarray(rc.inter_rgb)[None, :] * rng.uniform(
                0.9, 1.1, (m, 1)
            )
            out.append(
                Points(
                    np.c_[ix, iy, rng.normal(0, 0.08, m)],
                    lum,
                    rgb,
                    rng.uniform(0.4, 0.8, m),
                    "midclusters",
                )
            )

        # Resolved old field stars: sparkle over the smooth disk light, as
        # thick as it (sech^2, z0 = hz).
        fx, fy = _sample_map(maps.old, maps.half, rc.n_field, rng)
        m = rc.n_field
        lum = rng.exponential(1.0, m) ** 2
        lum *= 0.06 / lum.sum()
        fz = rc.hz * np.arctanh(rng.uniform(-0.999, 0.999, m))
        out.append(
            Points(
                np.c_[fx, fy, fz],
                lum,
                np.tile(old_rgb, (m, 1)) * rng.uniform(0.8, 1.2, (m, 1)),
                np.full(m, 0.6),
                "field",
            )
        )

        if rc.ring > 0:
            out += _nuclear_ring(rc, rng)
        main_light = rc.l_disk + rc.l_bulge
    else:
        a, b, c = rc.axes
        # Globular clusters: shallow power law well beyond the light.
        m = rc.n_gc
        r = 0.3 * (rng.pareto(1.6, m) + 1) - 0.25
        r = np.clip(r, 0.05, 8.0)
        v = rng.normal(size=(m, 3))
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        pos = v * r[:, None] * np.array([1.0, 0.95, 0.9])
        lum = rng.lognormal(0, 0.5, m)
        lum *= 0.05 / lum.sum()
        out.append(
            Points(
                pos, lum, np.tile(GC_RGB, (m, 1)), np.full(m, 0.7), "globulars"
            )
        )
        # Field stars (bright giants) for texture.
        m = rc.n_field
        rr = _hernquist_radii(rng, m, 0.55)
        v = rng.normal(size=(m, 3))
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        pos = v * rr[:, None] * np.array([a, b, c])
        lum = rng.exponential(1.0, m) ** 2
        lum *= 0.05 / lum.sum()
        out.append(
            Points(
                pos, lum, np.tile(old_rgb, (m, 1)), np.full(m, 0.6), "field"
            )
        )
        main_light = 1.0

    if ICL_STREAMS and rc.icl_streams > 0:
        out.append(_icl_streams(rc, rng, 0.3 * rc.icl_streams * main_light))
    if rc.halpha > 0:
        out.append(_halpha_filaments(rc, rng, 0.3 * rc.halpha * main_light))
    # Merger debris (both kinds), all in old-star colours.
    if rc.shells > 0:
        out.append(
            _shells(rc, rng, DEBRIS * 0.05 * rc.shells * main_light, old_rgb)
        )
    if rc.tails > 0:
        out.append(
            _tails(rc, rng, DEBRIS * 0.08 * rc.tails * main_light, old_rgb)
        )
    if rc.stream > 0:
        out.append(
            _stream(rc, rng, DEBRIS * 0.025 * rc.stream * main_light, old_rgb)
        )
    return out


def _icl_streams(rc, rng, lum_tot, n=16000):
    """Tidal debris feeding the intracluster light: each stream the remains
    of one satellite torn apart in this halo (rc.icl_n_streams of them),
    a leading and a trailing tail along its eccentric, slowly precessing
    orbit, fanning out and clumpy away from the remnant of its core."""
    r_in = max(1.2 * rc.extent, 0.6 * rc.icl_a)
    k = max(int(rc.icl_n_streams), 1)
    pos, lum = [], []
    for _ in range(k):
        u, v, w = _random_frame(rng)
        a = r_in * rng.uniform(0.6, 1.8)  # orbit size
        e = rng.uniform(0.3, 0.7)  # eccentricity
        php = rng.uniform(0, 2 * np.pi)  # pericentre
        ph0 = rng.uniform(0, 2 * np.pi)  # where the satellite was
        lead, trail = rng.uniform(0.3, 1.0, 2) * np.pi
        m = n // k
        # Debris thins away from the remnant along both tails.
        side = np.where(rng.random(m) < 0.5, 1.0, -1.0)
        reach = np.where(side > 0, lead, trail)
        d = np.abs(rng.normal(0, 0.45, m)) * reach
        ph = ph0 + side * d
        r = a * (1 - e * e) / (1 + e * np.cos(ph - php))
        # Fans out with distance from the remnant; precesses out of plane.
        width = 0.025 * r * (1 + 2.5 * d / np.pi)
        off = rng.normal(0, 1, (m, 3)) * width[:, None]
        tilt = 0.12 * r * np.sin(0.5 * (ph - ph0))
        p = (
            (r * np.cos(ph))[:, None] * u
            + (r * np.sin(ph))[:, None] * v
            + tilt[:, None] * w
            + off
        )
        # Clumpy along the stream (lognormal in orbital phase).
        knots = rng.normal(0, 1, 64)
        grid = np.linspace(-np.pi, np.pi, 64)
        clump = np.exp(
            0.4 * np.interp(np.clip(ph - ph0, -np.pi, np.pi), grid, knots)
        )
        lw = clump * np.exp(-d / (0.8 * np.pi))
        # What's left of the satellite's core, in some streams.
        if rng.random() < 0.4:
            mc = m // 16
            rc0 = a * (1 - e * e) / (1 + e * np.cos(ph0 - php))
            core = rc0 * (np.cos(ph0) * u + np.sin(ph0) * v)
            p = np.vstack([p, core + rng.normal(0, 0.02 * rc0, (mc, 3))])
            lw = np.concatenate([lw, np.full(mc, lw.mean())])
        pos.append(p)
        lum.append(lw)
    pos, lum = np.vstack(pos), np.concatenate(lum)
    lum *= lum_tot / lum.sum()
    rgb = np.tile(np.asarray(rc.icl_rgb), (len(lum), 1))
    return Points(pos, lum, rgb, np.full(len(lum), 1.1), "iclstream")


def _halpha_filaments(rc, rng, lum_tot, n=12000):
    """Cold gas raining out of a cooling hot atmosphere: thin, wandering
    H-alpha filaments radiating from the galaxy.  Above and below a disk
    (within 50 degrees of its axis, starting clear of it), so they read as
    gas raining down from the halo, not streaks across the arms."""
    k = int(3 + 4 * rc.halpha)
    disk = rc.kind == "disk"
    pos, lum = [], []
    for j in range(k):
        m = n // k
        d = rng.normal(size=3)
        if disk:
            # Alternate above / below; tilt at most 50 deg from the axis.
            d[2] = (1 if j % 2 == 0 else -1) * (
                np.linalg.norm(d[:2]) / np.tan(np.deg2rad(rng.uniform(10, 50)))
            )
        d /= np.linalg.norm(d)
        length = rc.halpha_len * rng.uniform(0.35, 1.0)
        t = rng.random(m) ** 0.8
        if disk:
            t = 0.25 + 0.75 * t  # start above the disk
        # A gently bending path: the direction drifts along the filament.
        bend = rng.normal(size=3) * 0.35
        path = (d[None, :] + t[:, None] * bend[None, :]) * (t * length)[
            :, None
        ]
        pos.append(path + rng.normal(0, 0.008 * length, (m, 3)))
        lum.append(1.2 - t)
    pos, lum = np.vstack(pos), np.concatenate(lum)
    lum *= lum_tot / lum.sum()
    rgb = np.tile(HALPHA_RGB, (len(lum), 1))
    return Points(pos, lum, rgb, np.full(len(lum), 0.9), "halpha")


def _random_frame(rng):
    """Random orthonormal basis (u, v, w)."""
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    return q[:, 0], q[:, 1], q[:, 2]


def _shells(rc, rng, lum_tot, rgb, n=40000):
    """Sharp-edged shells from a radial merger, alternating sides of an axis."""
    u, v, w = _random_frame(rng)
    n_sh = int(rng.integers(4, 7))
    radii = 0.9 * 1.45 ** np.arange(n_sh) * rng.uniform(0.9, 1.1, n_sh)
    which = rng.integers(0, n_sh, n)
    side = np.where(which % 2 == 0, 1.0, -1.0)
    # Points on a cap of half-angle ~65 deg, piled up toward the sharp edge.
    cos_t = 1 - (1 - np.cos(np.deg2rad(65))) * rng.random(n) ** 0.5
    phi = rng.uniform(0, 2 * np.pi, n)
    sin_t = np.sqrt(1 - cos_t**2)
    r = radii[which] * (1 - np.abs(rng.normal(0, 0.03, n)))
    pos = (
        (r * cos_t * side)[:, None] * u
        + (r * sin_t * np.cos(phi))[:, None] * v
        + (r * sin_t * np.sin(phi))[:, None] * w
    )
    lum = np.full(n, lum_tot / n) / (1 + 0.3 * which)  # outer shells fainter
    return Points(pos, lum, np.tile(rgb, (n, 1)), np.full(n, 1.2), "shells")


def _tails(rc, rng, lum_tot, rgb, n=40000):
    """Two tidal tails peeling off opposite sides of the disk."""
    e = rc.extent
    t0 = rng.uniform(0, 2 * np.pi)
    arm = rng.integers(0, 2, n)
    s = rng.random(n) ** 0.7  # more stars near the root of each tail
    r = e * (0.8 + 1.6 * s)
    th = t0 + np.pi * arm + 1.6 * s
    width = 0.05 * e + 0.25 * e * s
    x = r * np.cos(th) + rng.normal(0, 1, n) * width
    y = r * np.sin(th) + rng.normal(0, 1, n) * width
    z = (
        0.5 * e * s**2 * np.where(arm == 0, 1, -1)
        + rng.normal(0, 0.1 * e, n) * s
    )
    lum = np.full(n, lum_tot / n) * (1.2 - s)
    return Points(
        np.c_[x, y, z], lum, np.tile(rgb, (n, 1)), np.full(n, 1.3), "tails"
    )


def _stream(rc, rng, lum_tot, rgb, n=20000):
    """A thin stellar stream from a disrupted satellite, looping round."""
    u, v, _ = _random_frame(rng)
    rs = rc.extent * rng.uniform(0.55, 0.85)
    ecc = rng.uniform(0.2, 0.5)
    th = rng.uniform(0, 1.4 * np.pi, n)
    r = rs * (1 - ecc) / (1 - ecc * np.cos(th))
    jitter = rng.normal(0, 0.03 * rs, (n, 3))
    pos = (
        (r * np.cos(th))[:, None] * u + (r * np.sin(th))[:, None] * v + jitter
    )
    lum = np.full(n, lum_tot / n) * (
        0.4 + th / (1.4 * np.pi)
    )  # brighter near the progenitor
    return Points(pos, lum, np.tile(rgb, (n, 1)), np.full(n, 1.0), "stream")


def tidal_points(
    rc: GalaxyRecipe,
    direction,
    sep: float,
    strength: float,
    seed: int,
    sense: float = 1.0,
) -> Points:
    """Tidal features raised by a close neighbour (Toomre & Toomre): a
    bridge reaching toward it and a counter-tail flung out on the far side,
    both trailing the disk's rotation (about +z).  `direction`: unit vector
    to the neighbour and `sep` its distance, in this galaxy's model frame;
    `strength` (0-1) from closeness and mass ratio; `sense` (+-1) the
    orbit's turn about the disk axis, which way the features curve.
    Old-star light with a blue tint from star formation the encounter
    triggers."""
    rng = np.random.default_rng(seed)
    u = np.asarray(direction, float)
    u = u / max(np.linalg.norm(u), 1e-9)
    e = rc.extent
    main_light = rc.l_disk + rc.l_bulge if rc.kind == "disk" else 1.0
    n = int(8000 + 24000 * strength)
    bridge = rng.random(n) < 0.45
    s = rng.random(n) ** 0.8  # more stars near the root
    phi0 = np.arctan2(u[1], u[0])
    r0 = 0.85 * e
    # Bridge: out to about half way to the neighbour.
    lb = max(0.5 * sep, r0 + 0.6 * e)
    # Tail: longer the stronger the encounter.
    lt = (1.2 + 2.0 * strength) * e
    r = np.where(bridge, r0 + s * (lb - r0), r0 + s * lt)
    phi = np.where(
        bridge, phi0 - 0.5 * sense * s, phi0 + np.pi + 1.1 * sense * s
    )
    # Leaving the disk plane toward (bridge) / away from (tail) the
    # neighbour's height.
    z = np.where(bridge, 1.0, -0.5) * r * u[2] * s
    w = 0.05 * e + 0.2 * e * s
    pos = np.c_[
        r * np.cos(phi) + rng.normal(0, 1, n) * w,
        r * np.sin(phi) + rng.normal(0, 1, n) * w,
        z + rng.normal(0, 1, n) * 0.4 * w,
    ]
    lum = np.full(n, 0.3 * strength * main_light / n) * (1.25 - s)
    rgb = 0.75 * np.asarray(rc.old_rgb, float) + 0.25 * np.asarray(YOUNG_RGB)
    return Points(pos, lum, np.tile(rgb, (n, 1)), np.full(n, 1.2), "tidal")


# Jellyfish tails, after real ones: knots of young stars strung along
# threads trailing off the disc, blue and H-alpha magenta, a few long ones
# curling (JW100, JO206, JO201: Poggianti et al. 2017, 2019); and, with
# Gas, the stripped gas round them, drawn as HD draws the CGM, and long
# soft twisting plumes of gas in a range of
# blues, trailing off (ESO 137-001: Sun et al. 2006, 2010).  Each is set
# by the galaxy: how many threads by its cold gas, how bright by its
# sSFR, how long by ram pressure and time since infall, the gas by its
# gas fraction.  Lengths are in disk scale lengths.
JELLY_BLUES = (
    (0.55, 0.6, 1.0),
    (0.45, 0.78, 1.0),
    (0.35, 0.42, 1.0),
    (0.7, 0.85, 1.0),
    (0.3, 0.45, 0.95),
    (0.4, 0.7, 0.95),
)
JELLY_MAGENTA = np.array([0.9, 0.35, 0.85])
JELLY_MAGENTA_SHARE = 0.35  # of the threads
JELLY_STARS = 0.2  # brightness of the knots and plumes
JELLY_GAS = 0.5  # brightness of the gas round the threads
# The knots: how many per thread, their size (Rd) and their light (x the
# threads' share); the thin strands of the threads joining them (their
# light, x the same); the plumes' softness (Rd).
JELLY_KNOTS = dict(per_thread=4, size=0.12, gain=2.0, strand=1.0)
JELLY_PLUME_SOFT = 1.0


def jelly_look(g: SageGalaxy, strength: float) -> dict:
    """0 to 1 for a tail's "clumps", "packed", "length" and "glow"."""

    def fit(v, lo, hi):
        return float(np.clip((v - lo) / (hi - lo), 0.0, 1.0))

    fraction = g.cold_gas / max(g.cold_gas + g.stellar_mass, 1.0)
    return dict(
        clumps=fit(np.log10(max(g.cold_gas, 1.0)), 8.3, 10.5),
        packed=fit(np.log10(g.ssfr + 1e-14), -12.0, -9.5),
        length=0.6 * strength + 0.4 * fit(g.t_since_infall_gyr, 0.0, 6.0),
        glow=fit(fraction, 0.0, 0.5),
    )


def _jelly_frame(u):
    a = np.cross(u, [0.0, 0.0, 1.0])
    if np.linalg.norm(a) < 1e-3:
        a = np.cross(u, [1.0, 0.0, 0.0])
    a /= np.linalg.norm(a)
    return a, np.cross(u, a)


def _jelly_threads(rng, u, n, reach):
    """Threads off the trailing half of the disc: lengths spread widely,
    some curling, three long blue ones curling round; one faint knot
    each.  Returns their points and paths."""
    a, b = _jelly_frame(u)
    blues = np.array(JELLY_BLUES[:3])
    pos, lum, rgb, paths = [], [], [], []
    for j in range(n + 3):
        long_one = j >= n
        th = rng.uniform(0, 2 * np.pi)
        if np.array([np.cos(th), np.sin(th), 0.0]) @ u < -0.1:
            continue
        r = rng.uniform(1.6 if long_one else 0.8, 2.6)
        start = np.array([r * np.cos(th), r * np.sin(th), 0.0])
        d = u + rng.normal(0, 0.15, 3)
        d /= np.linalg.norm(d)
        if long_one:
            length = reach * rng.uniform(5, 8)
        else:
            length = reach * float(np.clip(rng.lognormal(0.3, 0.9), 0.3, 6.0))
        m = int(120 + 60 * length)
        s = np.sort(rng.random(m)) * length
        if long_one or rng.random() < 0.5:
            w = rng.uniform(0.9, 1.4) if long_one else rng.uniform(1.5, 3.5)
            amp = rng.uniform(0.6, 1.0) if long_one else rng.uniform(0.25, 0.5)
            amp = amp * s / length
            off = amp[:, None] * (
                np.cos(w * s)[:, None] * a + np.sin(w * s)[:, None] * b
            )
        else:
            bend = rng.normal(0, 0.12, 2)
            off = (s**2 / length)[:, None] * (bend[0] * a + bend[1] * b)
        path = start + s[:, None] * d + off
        k = rng.integers(0, m)
        p = np.vstack(
            [
                path + rng.normal(0, 0.006, (m, 3)),
                path[k] + rng.normal(0, 0.015, (6, 3)),
            ]
        )
        bright = np.r_[
            (1 - 0.7 * s / length) * rng.uniform(0.7, 1.3), [1.3] * 6
        ]
        if long_one:
            c = blues[0] * rng.uniform(0.9, 1.1)
        elif rng.random() < JELLY_MAGENTA_SHARE:
            c = JELLY_MAGENTA
        else:
            c = blues[rng.integers(3)] * rng.uniform(0.9, 1.1)
        pos.append(p)
        lum.append(bright)
        rgb.append(np.tile(c, (len(bright), 1)))
        paths.append(path)
    return np.vstack(pos), np.concatenate(lum), np.vstack(rgb), paths


def _jelly_gas(rng, paths):
    """The stripped gas round the threads, as HD's CGM (gpu_gas.py): a
    soft envelope with a ridged filament network and lognormal
    clumping."""
    from visage.hd.gpu import vnoise_baked

    def fbm(x):
        return sum(0.5**o * vnoise_baked(x * 2**o) for o in range(3))

    pos = []
    for path in paths:
        k = rng.integers(0, len(path), 12 * len(path))
        t = k / max(len(path) - 1, 1)
        w = 0.3 * (1 + 1.5 * t)
        pos.append(path[k] + rng.normal(0, 1, (len(k), 3)) * w[:, None])
    p = np.vstack(pos)
    ridge = np.exp(-((fbm(p / 2.0 + 37.0) / 0.5 / 0.35) ** 2))
    z = np.clip(fbm(p / 0.6 + 51.0) / 0.5, -3.0, 1.2)
    return p, (0.12 + 1.2 * ridge) * np.exp(0.55 * z)


def _jelly_plumes(rng, u, reach):
    """Eight long thin plumes trailing off: two twisting more, and one
    pair braided round each other."""
    a, b = _jelly_frame(u)
    pos, lum, rgb = [], [], []
    start, phase = np.zeros(2), 0.0
    for j in range(8):
        twist, turns = (1.0, (3, 6)) if j in (4, 5) else (0.6, (2, 4))
        if j == 7:  # braided round plume 6
            phase += np.pi
        else:
            start = rng.normal(0, 1.0, 2)
            phase = rng.uniform(0, 2 * np.pi)
        if j in (6, 7):
            twist = 0.8
        m = 6000
        t = rng.random(m)
        length = reach * rng.uniform(12, 32)
        k = rng.uniform(*turns) * 2 * np.pi
        amp = twist * rng.uniform(0.6, 1.2) * (0.3 + t)
        x = (
            start[0]
            + amp * np.cos(k * t + phase)
            + 0.3 * twist * np.sin(2.7 * k * t)
        )
        y = 0.5 * start[1] + 0.6 * amp * np.sin(k * t + phase)
        pos.append(
            (0.5 + t * length)[:, None] * u
            + (x + rng.normal(0, 0.012, m))[:, None] * a
            + (y + rng.normal(0, 0.012, m))[:, None] * b
        )
        # An equal share each, fading to nothing at its end.
        fade = np.clip((1 - t) / 0.6, 0, 1) ** 1.5
        lum.append(fade / fade.sum())
        c = JELLY_BLUES[rng.integers(len(JELLY_BLUES))]
        rgb.append(np.tile(np.array(c) * rng.uniform(0.9, 1.1), (m, 1)))
    return np.vstack(pos), np.concatenate(lum), np.vstack(rgb)


def jelly_points(
    rc: GalaxyRecipe,
    g: SageGalaxy,
    direction,
    strength: float,
    seed: int,
    gain: float = 1.0,
) -> list[Points]:
    """A ram-pressure-stripped ("jellyfish") tail trailing along `direction`
    (model frame, away from the motion): its gas, threads and plumes, as
    `jelly_look`.  `gain` brightens it to undo a group's shared exposure."""
    look = jelly_look(g, strength)
    rng = np.random.default_rng(seed)
    u = np.asarray(direction, float)
    u = u / max(np.linalg.norm(u), 1e-9)
    light = (
        1.05 * gain * (rc.l_disk + rc.l_bulge if rc.kind == "disk" else 1.0)
    )
    young = (0.25 + 0.75 * look["packed"]) * 0.9 * light
    n = int(round(70 * (0.3 + look["clumps"]) / 0.95))
    reach = 0.8 + 1.7 * look["length"]

    pos, lum, rgb, paths = _jelly_threads(rng, u, n, reach)
    # Compact knots strung along the threads (lines of points read as
    # streaks): each a small cloud round a point of a thread, the brighter
    # threads holding more of them.
    nk, per = JELLY_KNOTS["per_thread"] * n, 40
    c = rng.choice(len(lum), nk, p=lum / lum.sum())
    kl = np.repeat(rng.pareto(1.5, nk) + 1, per)
    knots = Points(
        np.repeat(pos[c], per, axis=0)
        + rng.normal(0, JELLY_KNOTS["size"], (nk * per, 3)),
        kl / kl.sum() * JELLY_STARS * 0.5 * JELLY_KNOTS["gain"] * young,
        np.repeat(rgb[c], per, axis=0),
        np.full(nk * per, 0.5),
        "jellyknots",
    )
    pos, lum = _jelly_gas(rng, paths)
    gas_light = JELLY_GAS * 3.0 * young * (0.5 + look["glow"]) / 0.78
    gas = Points(
        pos,
        lum / lum.sum() * gas_light,
        np.tile(CGM_RGB, (len(lum), 1)),
        np.full(len(lum), 1.0),
        "jelly",
    )
    pos, lum, rgb = _jelly_plumes(rng, u, reach)
    # The plumes are gas too: soft, between their blues and the CGM's.
    plumes = Points(
        pos + rng.normal(0, JELLY_PLUME_SOFT, pos.shape),
        lum / lum.sum() * JELLY_STARS * 0.3 * young,
        0.5 * rgb + 0.5 * np.asarray(CGM_RGB),
        np.full(len(lum), JELLY_PLUME_SOFT),
        "jelly",
    )
    strands = Points(
        pos,
        lum / lum.sum() * JELLY_KNOTS["strand"] * JELLY_STARS * 0.5 * young,
        rgb,
        np.full(len(lum), 0.5),
        "jellyknots",
    )
    return [gas, knots, strands, plumes]


def strip_points(
    rc: GalaxyRecipe, direction, strength: float, seed: int, toward=None
) -> Points:
    """Tidal stripping of a satellite deep in its host: leading and
    trailing streams of its stars along the orbit (`direction`, model
    frame), the more of its subhalo it has lost the longer.  The leading
    stream curves toward the host (`toward`), the trailing one away.  Faint:
    a few per cent of the galaxy's light, as observed streams are."""
    rng = np.random.default_rng(seed)
    u = np.asarray(direction, float)
    u = u / max(np.linalg.norm(u), 1e-9)
    side = None
    if toward is not None:
        side = np.asarray(toward, float) - np.dot(toward, u) * u
    if side is None or np.linalg.norm(side) < 1e-3:
        side = np.cross(u, [0.0, 0.0, 1.0])
        if np.linalg.norm(side) < 1e-3:
            side = np.cross(u, [1.0, 0.0, 0.0])
    side /= np.linalg.norm(side)
    e = rc.extent
    n = int(6000 + 12000 * strength)
    sgn = np.where(rng.random(n) < 0.5, 1.0, -1.0)
    length = (2.0 + 4.0 * strength) * e
    # Along an arc of the orbit (curving round the host, which lies along
    # `side`), thin, and bunched into clumps along it: the epicyclic
    # overdensities of tidal streams (Kupper et al. 2012).
    n_clump = 4 + int(3 * strength)
    t = rng.random(3 * n) ** 0.8
    keep = rng.random(3 * n) < 0.5 * (1 + np.cos(2 * np.pi * n_clump * t))
    t = t[keep][:n]
    n = len(t)
    sgn = sgn[:n]
    r_c = 2.5 * length  # radius of the orbit's curve
    phi = sgn * (0.7 * e + t * length) / r_c
    pos = (r_c * np.sin(phi))[:, None] * u + (r_c * (1 - np.cos(phi)))[
        :, None
    ] * side
    pos += rng.normal(0, 1, (n, 3)) * (0.03 * e + 0.05 * e * t)[:, None]
    main_light = rc.l_disk + rc.l_bulge if rc.kind == "disk" else 1.0
    lum = (1.2 - t) * 0.05 * strength * main_light
    lum /= max(n, 1) * (1.2 - t).mean()
    rgb = np.tile(np.asarray(rc.old_rgb), (n, 1))
    return Points(pos, lum, rgb, np.full(n, 1.1), "strip")


# Dust at the nuclear ring: the annulus's optical depth and width (fraction
# of the ring radius), and the bar's dust lanes feeding it (optical depth,
# width and end taper as fractions of the bar half-length).
RING_DUST = dict(ring=0.25, width=0.35, lanes=0.15, lane_w=0.08, taper=0.25)

# Nuclear ring look: width (fraction of its radius), brightness of its
# clusters and HII regions, how many clusters, and how far they scatter
# out of the plane (fraction of its radius).  Chosen by the user from
# options on SAGE26 galaxies ("D"): a faint, diffuse hint of a ring (the
# original thin, bright one was too harsh).
RING = dict(width=0.25, gain=0.2, hii=0.3, n=4000, thick=0.1)


def _nuclear_ring(rc, rng, n=None):
    """Star-forming ring around the bulge (driven by SfrBulge)."""
    n = int(RING["n"]) if n is None else n
    th = rng.uniform(0, 2 * np.pi, n)
    # Clumpy along the ring: a few hot spots.
    th = np.concatenate(
        [
            th[: n // 2],
            rng.normal(
                rng.uniform(0, 2 * np.pi, 8)[rng.integers(0, 8, n - n // 2)],
                0.15,
            ),
        ]
    )
    r = rc.ring_r * (1 + rng.normal(0, RING["width"], n))
    pos = np.c_[
        r * np.cos(th),
        r * np.sin(th),
        rng.normal(0, RING["thick"] * rc.ring_r, n),
    ]
    lum_c = np.full(n, RING["gain"] * rc.l_young * 0.35 * rc.ring / n)
    k = n // 3
    out = [
        Points(
            pos, lum_c, np.tile(CLUSTER_RGB, (n, 1)), np.full(n, 0.8), "ring"
        ),
        Points(
            pos[:k] * 1.01,
            np.full(k, RING["hii"] * rc.l_young * 0.2 * rc.ring / k),
            np.tile(np.asarray(rc.hii_rgb), (k, 1)),
            np.full(k, 1.4),
            "ring_hii",
        ),
    ]
    if rc.ring_style.startswith("starburst"):
        # A bright, continuous starburst ring (NGC 1097 / 1512 style):
        # thousands of faint young stars plus big HII complexes.
        m = 25000
        t = rng.uniform(0, 2 * np.pi, m)
        rr = rc.ring_r * (1 + rng.normal(0, 0.09, m))
        p2 = np.c_[rr * np.cos(t), rr * np.sin(t), rng.normal(0, 0.02, m)]
        out.append(
            Points(
                p2,
                np.full(m, rc.l_young * 1.2 * rc.ring / m),
                np.tile(CLUSTER_RGB, (m, 1)),
                np.full(m, 1.2),
                "ring_glow",
            )
        )
        kk = 60
        t = rng.uniform(0, 2 * np.pi, kk)
        p3 = np.c_[rc.ring_r * np.cos(t), rc.ring_r * np.sin(t), np.zeros(kk)]
        out.append(
            Points(
                p3,
                np.full(kk, rc.l_young * 0.5 * rc.ring / kk),
                np.tile(np.asarray(rc.hii_rgb), (kk, 1)),
                rng.uniform(1.5, 3.0, kk),
                "ring_hii2",
            )
        )
    return out


def _hernquist_radii(rng, n, a):
    u = rng.random(n) * 0.98
    s = np.sqrt(u)
    return a * s / (1 - s)


def describe(g: SageGalaxy, rc: GalaxyRecipe | None = None) -> list[str]:
    """What HD draws for this galaxy, in a few short phrases (the
    selection card's list) -- from the same recipe the model is built
    from.  Context that only the group build knows (tidal features,
    jellyfish tails) isn't included."""
    rc = rc or recipe_from_sage(g)
    out: list[str] = []
    if rc.kind == "elliptical":
        out.append("elliptical" + (", dust lane" if rc.dust_lane > 0 else ""))
    else:
        lenticular = rc.arm_old_amp < 0.05 and rc.l_young < 0.02
        arms = (
            "lenticular (S0)"
            if lenticular
            else {
                "grand": "grand-design arms",
                "multi": "multi-arm spiral",
                "partial": "partial arms",
                "flocculent": "flocculent arms",
                "clumpy": f"clumpy disk ({rc.clumps} clumps)",
            }.get(rc.arm_class, rc.arm_class)
        )
        out.append(arms)
        if rc.bar_len > 0:
            out.append("bar")
        if rc.l_bulge > 0.05:
            out.append("classical bulge")
        if rc.l_pseudo > 0.02:
            out.append("pseudo-bulge")
        if rc.ring > 0:
            out.append("nuclear ring")
        if rc.l_young > 0.05:
            out.append("young star clusters, HII regions")
        if rc.tau0 > 0.3:
            out.append("dusty")
        if rc.trunc_r > 0:
            out.append("gas disk stripped from outside in")
    if rc.lm_disk > 1.05 or rc.lm_bulge > 1.05:
        if rc.inter_frac > 0.05:
            out.append(
                f"{rc.inter_frac:.0%} of disk light from 0.1–1 Gyr stars"
            )
        else:
            out.append("colours from its star-formation history")
    if rc.agn > 0:
        out.append("AGN")
    debris = [
        name
        for name, v in (
            ("shells", rc.shells),
            ("tidal tails", rc.tails),
            ("stellar stream", rc.stream),
        )
        if v > 0
    ]
    if debris:
        out.append("merger " + ", ".join(debris))
    if rc.l_icl > 0:
        out.append(
            "intracluster light" + (" + streams" if rc.icl_streams > 0 else "")
        )
    if rc.halpha > 0:
        out.append("Hα cooling filaments")
    gas = []
    if g.cgm_gas > 0:
        gas.append("CGM streams")
    if g.hot_gas > 0:
        gas.append("hot halo")
    if jet_power_log(g) >= RADIO_LOUD:
        gas.append("radio jets")
    if g.outflow_rate > 0.05:
        gas.append("winds")
    if gas:
        out.append("gas: " + ", ".join(gas))
    return out
