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
from scipy.ndimage import map_coordinates

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
HII_LOOK = dict(
    poor=(1.00, 0.40, 0.80),
    rich=(1.00, 0.55, 0.32),
    size=1.3,
    gain=0.8,
    conc=0.7,
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
# Dwarf irregulars: gas-rich disks below max_lm are drawn without spiral
# arms, with a few soft star-forming clumps and an m=1 lopsided disk.
DWARF = dict(on=False, max_lm=9.3, lopsided=0.4, clumps=3)
# ICL streams: "threshold" (any ICS torn from satellites in place above
# ~10^10.5 Msun) or "share" (scaled by the in-place share of all the ICS,
# accreted ICS making a smoother envelope).
ICL_MODE = "threshold"
# Streams of satellite debris feeding the ICL (off: removed by choice).
ICL_STREAMS = False
# The ICL's look: envelope brightness (x), glow brightness (x), the glow's
# and stripped stars' extent (0: the galaxy's size; >0: that many times the
# envelope scale 0.12 Rvir), stripped-star count (x), colour (None: from
# its metallicity).
# mass: >0 scales the glow and envelope with the ICS mass itself (power).
# Chosen from options on SAGE26 centrals ("D"): halo-wide, its glow and
# envelope scaled by the ICS mass.
ICL_LOOK = dict(env=0.45, glow=0.55, size=1.0, stars=1.0, rgb=None, mass=0.35)

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
    t_major_myr: float = -1.0  # lookback time of last major merger (<0: never)
    t_minor_myr: float = -1.0
    qso_accretion: float = 0.0  # Msun accreted in quasar mode this step
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
    sfh_disk: tuple = ()
    sfh_bulge: tuple = ()
    # The massive haloes around it (its cosmic web): (dx, dy, dz, weight)
    # per neighbour, unit directions in the simulation frame, weight
    # Mvir / d^2 relative to the strongest.
    web: tuple = ()
    # Face-on V-band optical depth of its diffuse ISM from the lightcone's
    # synthetic photometry (TauV_ISM); <0: none, HD estimates its own.
    tau_v_ism: float = -1.0
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
    dust_k: tuple = tuple(DUST_K)  # extinction per channel, relative to V
    # Per-channel gain on the galaxy's light (I, V, B channels) matching
    # its integrated colour to its synthetic photometry (lightcone); 1 =
    # HD's own colours.
    col_gain: tuple = (1.0, 1.0, 1.0)
    lane: float = 1.0  # darkness of the arm dust lanes (dust column, log)
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
    notes: list = field(default_factory=list)


def display_sizes(g: SageGalaxy) -> tuple[float, float, list]:
    """Disk scale length and elliptical half-light radius, in kpc.

    SAGE's spin-based DiskRadius scatters a lot at fixed mass (a few
    galaxies come out tens of kpc), so the picture's size follows the
    observed size-mass relations of Shen et al. (2003) and SAGE's own
    radius only nudges it (to the 1/4 power, at most ~+-30%).
    """
    m = max(g.stellar_mass, 1e7)
    r50_late = 0.10 * m**0.14 * (1 + m / 3.98e10) ** 0.25
    rd_rel = r50_late / 1.678
    r50_early = 2.88e-6 * m**0.56
    # Galaxies were smaller at fixed mass in the past (van der Wel et al.
    # 2014): late types ~ (1+z)^-0.75, early types ~ (1+z)^-1.  A
    # feedback-free starburst is more compact still.
    zf = 1.0 + max(g.redshift, 0.0)
    rd_rel *= zf**-0.75 * (0.6 if g.ffb else 1.0)
    r50_early *= zf**-1.0
    mod_d = (
        np.clip((g.disk_radius_kpc / rd_rel) ** 0.25, 0.75, 1.35)
        if g.disk_radius_kpc > 0
        else 1.0
    )
    mod_e = (
        np.clip((g.bulge_radius_kpc / r50_early) ** 0.25, 0.75, 1.35)
        if g.bulge_radius_kpc > 0
        else 1.0
    )
    notes = [
        f"size: Rd={rd_rel * mod_d:.2f} kpc, R50(early)={r50_early * mod_e:.2f} kpc "
        f"(Shen+03 x SAGE nudge {mod_d:.2f}/{mod_e:.2f})"
    ]
    return float(rd_rel * mod_d), float(r50_early * mod_e), notes


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
    if g.ics > 0:
        # Diffuse emission only (the ICL's look is its display overlay and
        # stripped stars); capped, as ICS can exceed M* many times and its
        # glow would otherwise haze over the whole view.
        # (log in ICS / M*, so richer clusters keep getting brighter
        # rather than all hitting one cap)
        ratio = g.ics / max(g.stellar_mass, 1.0)
        out["l_icl"] = float(
            0.12
            * ICL_LOOK["env"]
            * main_light
            * (
                np.clip(1 + 0.5 * np.log10(ratio / 3), 0.05, 1.3)
                if ICL_LOOK["mass"] <= 0
                else np.clip((ratio / 3) ** ICL_LOOK["mass"], 0.05, 6.0)
            )
        )
        out["icl_a"] = float(np.clip(0.12 * g.rvir_kpc, 20, 250) / unit_kpc)
        notes.append(
            f"ICS={g.ics:.2e} ({g.ics / g.stellar_mass:.2f} of M*) -> ICL envelope"
        )

    # Merger debris fades over a few dynamical times, which are shorter at
    # high z: 4 Gyr (major) and 2.5 Gyr (minor) at z = 0, / (1+z).
    zf = 1.0 + max(g.redshift, 0.0)
    t_maj, t_min = 4000 / zf, 2500 / zf
    if 0 <= g.t_major_myr < t_maj:
        f = float(1 - g.t_major_myr / t_maj)
        out["shells" if rc_kw.get("kind") == "elliptical" else "tails"] = f
        notes.append(
            f"major merger {g.t_major_myr / 1e3:.1f} Gyr ago -> "
            f"{'shells' if rc_kw.get('kind') == 'elliptical' else 'tidal tails'} {f:.2f}"
        )
    if 0 <= g.t_minor_myr < t_min:
        out["stream"] = float(1 - g.t_minor_myr / t_min)
        notes.append(
            f"minor merger {g.t_minor_myr / 1e3:.1f} Gyr ago -> stellar stream"
        )

    # Quasar-mode accretion this step: a bright, bluish point nucleus.
    if g.qso_accretion > 0:
        out["agn"] = float(
            0.05 * np.clip(g.qso_accretion / 1e6, 0.01, 1e3) ** 0.4
        )
        notes.append(
            f"quasar-mode accretion {g.qso_accretion:.2e} Msun -> AGN {out['agn']:.3f}"
        )
    return out


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

    # Morphology: bulge fraction decides, Regime only breaks ties in the
    # ambiguous middle (hot-mode haloes with a big bulge and no gas).
    elliptical = bt > 0.75 or (bt > 0.5 and g.regime == 1 and gas_frac < 0.02)
    notes.append(
        f"B/T={bt:.2f}, regime={'hot' if g.regime else 'cold'}, "
        f"f_gas={gas_frac:.3f} -> {'elliptical' if elliptical else 'disk'}"
    )

    if elliptical:
        # Massive ellipticals are rounder, with a more extended envelope
        # (higher Sersic n, cD-like) and far richer globular systems.
        mfac = np.clip((lm - 10.0) / 2.0, 0.0, 1.0)
        b = rng.uniform(0.68 + 0.2 * mfac, 0.9 + 0.08 * mfac)
        c = b * rng.uniform(0.6 + 0.25 * mfac, 0.9)
        # Rotation support (halo Vmax / dispersion): fast rotators are
        # flatter, slow rotators rounder.
        if g.vmax > 0 and g.vel_disp > 0:
            c *= float(np.clip(1.25 - 0.18 * g.vmax / g.vel_disp, 0.7, 1.1))
            c = min(c, b)
        env_a = float(0.6 + 0.6 * mfac)
        core_frac = float(0.5 - 0.2 * mfac)
        n_gc = int(np.clip(30 * (g.stellar_mass / 1e10) ** 1.2, 20, 4000))
        dust = np.clip(np.log10(max(g.h2_gas, 1.0)) - 7.5, 0.0, 2.0) / 2.0
        if g.tau_v_ism == 0:
            dust = 0.0  # its photometry's dust: none
        notes.append(
            f"envelope a={env_a:.2f}, core {core_frac:.2f}, b/a={b:.2f}, {n_gc} globulars"
        )
        if dust > 0:
            notes.append(
                f"H2={g.h2_gas:.2e} -> nuclear dust lane strength {dust:.2f}"
            )
        unit = float(r50e / 1.36)
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

    # Hubble sequence: bigger bulge -> tighter arms; more gas -> more arms
    # and more flocculent structure.  Massive disks are grand-design.
    pitch = float(np.clip(28.0 - 30.0 * bt + rng.normal(0, 2.5), 9.0, 30.0))
    # Faster rotation (more shear) winds the arms tighter.
    if g.vmax > 0:
        pitch -= 6.0 * float(np.clip((g.vmax - 150.0) / 150.0, -1.0, 1.0))
    ib_frac = g.instability_bulge_mass / max(g.stellar_mass, 1.0)
    barred = ib_frac > 0.06
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
    # High-z gas-rich disks are turbulent and clumpy rather than spiral;
    # a feedback-free starburst always is.
    # (A Toomre-like score from redshift, gas fraction and turbulence,
    # sigma / Vmax: decided by the galaxy, not by chance.)
    turb = 1.0
    if g.vmax > 0 and g.vel_disp > 0:
        turb = float(np.clip((g.vel_disp / g.vmax) / 0.55, 0.7, 1.4))
    p_clumpy = float(
        np.clip((g.redshift - 0.8) / 1.2, 0.0, 1.0)
        * np.clip(gas_frac / 0.2, 0.3, 1.0)
        * turb
    )
    if g.ffb or p_clumpy >= 0.45:
        drawn = "clumpy"
    if DWARF["on"] and lm < DWARF["max_lm"] and gas_frac > 0.15:
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
    pitch = float(
        np.clip(
            pitch
            + {
                "grand": -3.0,
                "multi": 0.0,
                "partial": 3.0,
                "flocculent": 6.0,
                "clumpy": 8.0,
                "irregular": 8.0,
            }[arm_class],
            9.0,
            35.0,
        )
    )
    sharp = float(np.clip(5.0 * (1 - flocc) + 1.5, 1.5, 6.0))
    # Low-mass disks are thicker; so are high-z (turbulent) disks and
    # dispersion-supported ones (halo sigma / Vmax).
    hz = float(np.clip(0.10 * 10 ** (-0.15 * (lm - 10.5)), 0.08, 0.2))
    hz *= 1.0 + 0.5 * min(max(g.redshift, 0.0), 3.0)
    if g.vmax > 0 and g.vel_disp > 0:
        # (steep: the population's sigma/Vmax spans only ~0.45-0.65)
        hz *= float(np.clip(((g.vel_disp / g.vmax) / 0.55) ** 6, 0.6, 2.0))
    hz = float(min(hz, 0.45))

    # Bulges: the classical (merger-built) one round, at its own radius;
    # the pseudo-bulge (instability-built) compact and flattened at its own.
    rb = g.bulge_radius_kpc if g.bulge_radius_kpc > 0 else 0.2 * rd
    split = g.merger_bulge_radius_kpc > 0 or g.instability_bulge_radius_kpc > 0
    if split and g.merger_bulge_radius_kpc > 0:
        rb = g.merger_bulge_radius_kpc
    bulge_a = float(np.clip(rb / rd / (1 + np.sqrt(2)), 0.03, 0.4))
    merger_share = g.merger_bulge_mass / max(g.bulge_mass, 1.0)
    bulge_q = float(0.85 if split else 0.5 + 0.4 * merger_share)
    rp = g.instability_bulge_radius_kpc
    pseudo_a = float(
        np.clip(
            (rp if rp > 0 else 0.1 * rd) / rd / (1 + np.sqrt(2)), 0.02, 0.25
        )
    )

    # Bar: at most ~8% of M* goes into the bar; the rest of the
    # instability-grown bulge is a compact, flattened pseudobulge.  This
    # keeps gas-poor lenticulars from turning into one giant bar.
    bar_len = 0.0
    bar_axis = 0.28
    l_bar = 0.0
    bar_mass = 0.0
    if barred:
        bar_mass = min(g.instability_bulge_mass, 0.08 * g.stellar_mass)
        bar_frac = bar_mass / max(g.stellar_mass, 1.0)
        bar_len = float(np.clip(0.9 + 10.0 * bar_frac, 0.9, 1.8))
        # Stronger bars are thinner.
        bar_axis = float(np.clip(0.36 - 1.5 * bar_frac, 0.22, 0.36))
        l_bar = 1.8 * OLD_LIGHT * bar_mass / max(disk_mass, 1.0)
        notes.append(
            f"instability bulge {ib_frac:.2f} of M* -> bar {bar_frac:.2f} of M*, "
            f"half-length {bar_len:.1f} Rd; rest pseudobulge"
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
    l_young = float(np.clip(0.55 * (ssfr_disk / 1e-10) ** 0.7, 0.01, 1.5))
    if g.ffb:
        l_young = min(1.5 * l_young + 0.2, 2.0)  # very blue
    n_clusters = int(np.clip(6000 * max(g.sfr_disk, 1e-3) ** 0.5, 400, 20000))
    # (Against a younger, brighter-per-mass disk the current young light
    # stands out less.)
    l_young /= lm_d
    # HII regions: number follows the molecular gas reservoir.
    n_hii = int(np.clip(350 * (g.h2_gas / 1e9) ** 0.8, 10, 3000))
    notes.append(f"H2={g.h2_gas:.2e} -> {n_hii} HII complexes")

    # Dust: H2 surface density x metallicity, face-on tau at ~Rd.
    sigma_h2 = g.h2_gas / (2 * np.pi * (rd * 1e3) ** 2)  # Msun/pc^2
    sigma_hi = g.h1_gas / (2 * np.pi * (rd * 2.2e3) ** 2 + 1)
    zfac = np.clip(g.metallicity, 0.1, 3.0)
    tau0 = float(
        np.clip(0.015 * (sigma_h2 + 0.4 * sigma_hi) * zfac, 0.05, 3.0)
    )
    notes.append(
        f"Sigma_H2~{sigma_h2:.1f} Msun/pc^2, Z~{zfac:.2f} Zsun -> tau0={tau0:.2f}"
    )
    # Arm dust lanes from the same dust column, unclipped and on a log
    # scale, so they keep varying where tau0 saturates.
    column = 0.015 * (sigma_h2 + 0.4 * sigma_hi) * zfac
    dust_k = tuple(DUST_K)
    if np.isfinite(g.tau_v_ism) and g.tau_v_ism >= 0:
        # The photometry's own dust (lightcone): the same optical depth
        # in front of the stars, so HD dims and reddens the galaxy as its
        # magnitudes do, and with the same attenuation curve.
        tau0 = column = float(g.tau_v_ism / SED_TAU_MEAN)
        dust_k = tuple(SED_DUST_K)
        notes.append(
            f"photometry: tau_V(ISM)={g.tau_v_ism:.2f} -> tau0={tau0:.2f}"
        )
    lane = float(
        np.clip(1.0 + 1.5 * np.log10(max(column, 1e-4) / 2.0), 0.15, 2.5)
    )
    if g.tau_v_ism == 0:
        lane = 0.0  # its photometry's dust: none
    # Star-forming complexes: richer where star formation is denser
    # (SFR surface density), bigger in gas-richer disks (larger Jeans
    # mass: cold-gas fraction).
    sig_sfr = g.sfr_disk / (np.pi * max(rd, 0.3) ** 2)  # Msun/yr/kpc^2
    hii_group = int(
        np.clip(8 + 10 * np.log10(max(sig_sfr, 1e-6) / 0.1), 2, 24)
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
    # Star formation in the bulge: a nuclear starburst ring, just inside
    # the bar ends / around the bulge (an inner Lindblad resonance ring).
    sfr_tot = g.sfr_disk + g.sfr_bulge
    if g.sfr_bulge > 0.05 and g.sfr_bulge > 0.08 * sfr_tot:
        ex["ring"] = float(np.clip(g.sfr_bulge / max(sfr_tot, 1e-9), 0.1, 1.0))
        ex["ring_r"] = float(max(0.35 * bar_len, 3.0 * bulge_a, 0.25))
        notes.append(
            f"SfrBulge={g.sfr_bulge:.2f} ({ex['ring']:.2f} of SFR) -> nuclear ring "
            f"at {ex['ring_r']:.2f} Rd"
        )

    arms = arm_layout(
        arm_class,
        extent,
        max(bar_len, 0.3),
        np.random.default_rng(rng.integers(1 << 31)),
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
        clumps = int(DWARF["clumps"])
        lopsided = float(DWARF["lopsided"])
        lop_phase = float(rng.uniform(0, 2 * np.pi))
        notes.append(
            f"dwarf irregular: {clumps} clumps, lopsided {lopsided:.2f}"
        )
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
        bulge_a=bulge_a,
        bulge_q=bulge_q,
        bar_len=bar_len,
        l_bar=l_bar,
        l_pseudo=float(l_pseudo),
        pseudo_a=pseudo_a,
        bar_axis=bar_axis,
        # Bars buckle into a peanut once the disk is gas-poor.
        peanut=float(
            np.clip(1.3 - 2.0 * gas_frac, 0.4, 1.0) if bar_len > 0 else 0.0
        ),
        # Pseudo-bulges are flatter in colder (rotation-dominated) disks.
        pseudo_q=float(
            np.clip(0.25 + 0.2 * (g.vel_disp / g.vmax), 0.25, 0.5)
            if g.vmax > 0 and g.vel_disp > 0
            else 0.35
        ),
        clumps=clumps,
        trunc_r=trunc_r,
        lopsided=lopsided,
        lop_phase=lop_phase,
        hole=float(max(bar_len * 0.9, 2.5 * bulge_a, 0.25)),
        hi_scale=hi_scale,
        arm_old_amp=float(0.45 * min(1.0, gas_frac / 0.08)),
        l_disk=OLD_LIGHT,
        l_bulge=float(l_bulge),
        l_young=l_young,
        l_nucleus=l_nuc,
        nucleus_sigma=nuc_sig,
        tau0=tau0,
        dust_k=dust_k,
        lane=lane,
        hii_group=hii_group,
        hii_spread=hii_spread,
        n_clusters=n_clusters,
        n_hii=n_hii,
        n_field=60000,
        notes=notes,
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
# Merger debris (shells, tails, streams): its share of the galaxy's light.
DEBRIS = 0.65


def arm_layout(cls: str, extent: float, r_base: float, rng):
    """Individual arms for an arm class: (amplitudes, start radii, end
    radii, angular offsets), radii in model units."""
    u = rng.uniform
    amp, r0, r1, off = [], [], [], []

    def arm(a, ra, rb, o):
        amp.append(float(a))
        r0.append(float(ra))
        r1.append(float(rb))
        off.append(float(o))

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
    return 1 - out


def build_disk_maps(rc: GalaxyRecipe, n=2048) -> PlaneMaps:
    rng = np.random.default_rng(rc.seed)
    half = rc.extent * 1.6
    ax = np.linspace(-half, half, n)
    x, y = np.meshgrid(ax, ax)
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
    arm = (1 - rc.flocculence) * arm_grand + rc.flocculence * floc * (
        fl_base + 1.0 * arm_grand
    )
    # Arms fade inside the bar / bulge.
    inner = 1 - np.exp(-((r / max(rc.hole, 0.2)) ** 4))
    arm_eff = arm * inner

    exp_d = np.exp(-r / 0.85)
    outer_cut = 1 / (1 + np.exp((r - rc.extent * 1.05) / 0.25))

    old = (
        exp_d
        * (1 + rc.arm_old_amp * (arm_eff - arm_eff.mean()))
        * np.exp(0.08 * clumps)
    )
    if rc.bar_len > 0:
        # The bar is built from the inner disk: hollow it out to match.
        old *= 1 - 0.65 * np.exp(-((r / (0.8 * rc.bar_len)) ** 2))

    young = (
        np.exp(-r / 1.35)
        * arm_eff**1.4
        * np.exp(0.6 * clumps - 0.18)
        * outer_cut
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
        for _ in range(rc.clumps):
            rr = rc.extent * 0.75 * np.sqrt(crng.random())
            tt = crng.uniform(0, 2 * np.pi)
            w = crng.uniform(*CLUMPY["width"])
            d2 = (x - rr * np.cos(tt)) ** 2 + (y - rr * np.sin(tt)) ** 2
            giant += crng.uniform(0.5, 1.0) * (
                np.exp(-d2 / (2 * w * w))
                + CLUMPY["wing"] * np.exp(-d2 / (2 * (2.2 * w) ** 2))
            )
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
    if rc.clumps:
        h2 = h2 + 1.5 * giant * np.exp(-r / 3.0)
    dust = (h2 + 0.35 * hi) * outer_cut * inner
    # Normalise the total dust column to that of a smooth exponential disk
    # with face-on optical depth tau0 at its centre (2 pi tau0 Rd^2).  An
    # integral rather than a ring average, so a central hole (bar) doesn't
    # inflate the normalisation.
    dA = (ax[1] - ax[0]) ** 2
    dust *= 2 * np.pi * rc.tau0 / max(dust.sum() * dA, 1e-9)
    lane_screen = None
    if dl["boost"] > 0:
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
        n_cx = max(rc.n_clusters // 6, 10)
        conc = CLUMPY["conc"] if rc.clumps else 1.3
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
        lum *= rc.l_young * 0.6 / lum.sum()
        pz = rng.normal(0, 0.04, m)
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
        hi = max(int(rc.hii_group), 1)
        k = rng.integers(max(hi // 3, 1), hi + 1, len(hx))
        sp = rc.hii_spread
        hx = np.repeat(hx, k) + rng.normal(0, sp, k.sum())
        hy = np.repeat(hy, k) + rng.normal(0, sp, k.sum())
        m = len(hx)
        lum = rng.pareto(1.5, m) + 1
        lum = np.minimum(lum, 12)
        lum *= rc.l_young * HII_LOOK["gain"] / lum.sum()
        out.append(
            Points(
                np.c_[hx, hy, rng.normal(0, 0.03, m)],
                lum,
                np.tile(np.asarray(rc.hii_rgb), (m, 1)),
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

        # Resolved old field stars: sparkle over the smooth disk light.
        fx, fy = _sample_map(maps.old, maps.half, rc.n_field, rng)
        m = rc.n_field
        lum = rng.exponential(1.0, m) ** 2
        lum *= 0.06 / lum.sum()
        out.append(
            Points(
                np.c_[fx, fy, rng.normal(0, 0.15, m)],
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


# Jellyfish tails: brightness (x the galaxy's light) and how it splits
# between pink H-alpha streamers and blue star-forming knots.
JELLY = dict(gain=1.0, halpha=0.45, knots=0.55)


def jelly_points(
    rc: GalaxyRecipe, direction, strength: float, seed: int, gain: float = 1.0
) -> list[Points]:
    """A ram-pressure-stripped ("jellyfish") gas tail: the galaxy's gas
    pushed out behind it by the hot halo it is ploughing through, forming
    stars as it goes -- blue knots and pink H-alpha streaks trailing
    along `direction` (model frame, away from the motion).  `gain`
    brightens it to undo a group's shared exposure, which dims a satellite
    next to a much brighter central: the tail then looks as it does at the
    satellite's own exposure."""
    rng = np.random.default_rng(seed)
    u = np.asarray(direction, float)
    u = u / max(np.linalg.norm(u), 1e-9)
    a = np.cross(u, [0.0, 0.0, 1.0])
    if np.linalg.norm(a) < 1e-3:
        a = np.cross(u, [1.0, 0.0, 0.0])
    a /= np.linalg.norm(a)
    b = np.cross(u, a)
    e = rc.extent
    length = (1.5 + 3.5 * strength) * e
    n = int(6000 + 14000 * strength)
    # Streamers start across the disk's trailing side and fan out.
    k = int(5 + 7 * strength)
    starts = rng.normal(0, 0.35 * e, (k, 2))
    which = rng.integers(0, k, n)
    t = rng.random(n) ** 0.7
    spread = 0.05 * e + 0.15 * e * t
    off = starts[which] * (1 + 0.6 * t[:, None])
    pos = (
        (0.4 * e + t * length)[:, None] * u
        + (off[:, 0] + rng.normal(0, 1, n) * spread)[:, None] * a
        + (off[:, 1] + rng.normal(0, 1, n) * spread)[:, None] * b
    )
    main_light = rc.l_disk + rc.l_bulge if rc.kind == "disk" else 1.0
    # (Bright for its surface: real tails stand out in H-alpha imaging.)
    total = 3.0 * JELLY["gain"] * gain * strength * main_light
    # Ionised gas: diffuse pink streamers.
    lum = 1.15 - t
    lum = lum * JELLY["halpha"] * total / lum.sum()
    gas = Points(
        pos, lum, np.tile(HALPHA_RGB, (n, 1)), np.full(n, 1.0), "jelly"
    )
    # Stars formed in the tail: compact blue knots along the streamers.
    m = int(200 + 900 * strength)
    w = (1.15 - t) / (1.15 - t).sum()
    pick = rng.choice(n, m, p=w)
    klum = rng.pareto(1.6, m) + 1
    klum *= JELLY["knots"] * total / klum.sum()
    knots = Points(
        pos[pick] + rng.normal(0, 0.02 * e, (m, 3)),
        klum,
        np.tile(YOUNG_RGB * 1.1, (m, 1)),
        rng.uniform(0.5, 1.0, m),
        "jellyknots",
    )
    return [gas, knots]


def strip_points(
    rc: GalaxyRecipe, direction, strength: float, seed: int
) -> Points:
    """Tidal stripping of a satellite deep in its host: leading and
    trailing streams of its stars along the orbit (`direction`, model
    frame), the more of its subhalo it has lost the longer."""
    rng = np.random.default_rng(seed)
    u = np.asarray(direction, float)
    u = u / max(np.linalg.norm(u), 1e-9)
    side = np.cross(u, [0.0, 0.0, 1.0])
    if np.linalg.norm(side) < 1e-3:
        side = np.cross(u, [1.0, 0.0, 0.0])
    side /= np.linalg.norm(side)
    e = rc.extent
    n = int(6000 + 12000 * strength)
    sgn = np.where(rng.random(n) < 0.5, 1.0, -1.0)
    t = rng.random(n) ** 0.8
    length = (2.0 + 4.0 * strength) * e
    r = 0.7 * e + t * length
    # Streams bend gently (the orbit curves).
    pos = (sgn * r)[:, None] * u + (0.12 * r**2 / length)[:, None] * side
    pos += rng.normal(0, 1, (n, 3)) * (0.05 * e + 0.08 * e * t)[:, None]
    main_light = rc.l_disk + rc.l_bulge if rc.kind == "disk" else 1.0
    lum = (1.2 - t) * 0.8 * strength * main_light
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
        arms = {
            "grand": "grand-design arms",
            "multi": "multi-arm spiral",
            "partial": "partial arms",
            "flocculent": "flocculent arms",
            "clumpy": f"clumpy disk ({rc.clumps} clumps)",
        }.get(rc.arm_class, rc.arm_class)
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
    if g.heating_log > 40.0:
        gas.append("radio jets")
    if g.outflow_rate > 0.05:
        gas.append("winds")
    if gas:
        out.append("gas: " + ", ".join(gas))
    return out
