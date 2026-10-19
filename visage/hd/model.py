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
GC_RGB = np.array([1.00, 0.85, 0.65])
# Gas-halo overlay (X-ray / CGM composite style, not optical light).
HOT_GAS_RGB = np.array([0.62, 0.45, 1.00])
CGM_RGB = np.array([0.35, 0.62, 1.00])
# Galactic-wind filaments (H-alpha-like, warm).
WIND_RGB = np.array([1.00, 0.55, 0.38])
# Radio jets / lobes (radio-composite orange-gold).
JET_RGB = np.array([1.00, 0.72, 0.30])
# Light per unit mass of old stars relative to the young-star scaling; below
# 1 so the old disk, bulge and bar don't wash an orange haze over the arms.
OLD_LIGHT = 0.4
# Extinction relative to the "V" (green) channel: dust reddens what it dims.
DUST_K = np.array([0.72, 1.00, 1.35])


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
    unit_kpc: float = 1.0  # physical size of one model length unit
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
    # Stellar metallicity tints the old light: metal-rich -> redder.
    zs = np.clip(np.log10(max(g.stellar_metallicity, 1e-3)), -1.0, 0.5)
    tint = np.array([1.0, 0.80 - 0.06 * zs, 0.56 - 0.12 * zs])
    out = dict(
        old_rgb=tuple(tint), bulge_rgb=tuple(tint * np.array([1.0, 0.9, 0.82]))
    )
    notes.append(
        f"Z*={g.stellar_metallicity:.2f} Zsun -> old-star tint {np.round(tint, 2)}"
    )

    # Intracluster stars: a faint, very extended envelope (~50 kpc).
    if g.ics > 0:
        out["l_icl"] = float(
            0.5 * main_light * g.ics / max(g.stellar_mass, 1.0)
        )
        out["icl_a"] = float(np.clip(0.12 * g.rvir_kpc, 20, 120) / unit_kpc)
        notes.append(
            f"ICS={g.ics:.2e} ({g.ics / g.stellar_mass:.2f} of M*) -> ICL envelope"
        )

    # Merger debris fades over a few Gyr (lookback times in Myr).
    if 0 <= g.t_major_myr < 4000:
        f = float(1 - g.t_major_myr / 4000)
        out["shells" if rc_kw.get("kind") == "elliptical" else "tails"] = f
        notes.append(
            f"major merger {g.t_major_myr / 1e3:.1f} Gyr ago -> "
            f"{'shells' if rc_kw.get('kind') == 'elliptical' else 'tidal tails'} {f:.2f}"
        )
    if 0 <= g.t_minor_myr < 2500:
        out["stream"] = float(1 - g.t_minor_myr / 2500)
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


def recipe_from_sage(g: SageGalaxy) -> GalaxyRecipe:
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
        env_a = float(0.6 + 0.6 * mfac)
        core_frac = float(0.5 - 0.2 * mfac)
        n_gc = int(np.clip(30 * (g.stellar_mass / 1e10) ** 1.2, 20, 4000))
        dust = np.clip(np.log10(max(g.h2_gas, 1.0)) - 7.5, 0.0, 2.0) / 2.0
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
    ib_frac = g.instability_bulge_mass / max(g.stellar_mass, 1.0)
    barred = ib_frac > 0.06
    if barred or lm > 10.8:
        n_arms = 2
    else:
        n_arms = int(rng.choice([2, 2, 3, 4], p=[0.4, 0.2, 0.25, 0.15]))
    flocc = float(
        np.clip(
            0.15 + 3.0 * gas_frac + 0.15 * (10.3 - lm) + rng.normal(0, 0.08),
            0.1,
            0.85,
        )
    )
    sharp = float(np.clip(5.0 * (1 - flocc) + 1.5, 1.5, 6.0))
    # Low-mass disks are thicker.
    hz = float(np.clip(0.10 * 10 ** (-0.15 * (lm - 10.5)), 0.08, 0.2))

    # Bulge: classical (merger) part is round, instability part flattened.
    rb = g.bulge_radius_kpc if g.bulge_radius_kpc > 0 else 0.2 * rd
    bulge_a = float(np.clip(rb / rd / (1 + np.sqrt(2)), 0.03, 0.4))
    merger_share = g.merger_bulge_mass / max(g.bulge_mass, 1.0)
    bulge_q = float(0.5 + 0.4 * merger_share)

    # Bar: at most ~8% of M* goes into the bar; the rest of the
    # instability-grown bulge is a compact, flattened pseudobulge.  This
    # keeps gas-poor lenticulars from turning into one giant bar.
    bar_len = 0.0
    l_bar = 0.0
    bar_mass = 0.0
    if barred:
        bar_mass = min(g.instability_bulge_mass, 0.08 * g.stellar_mass)
        bar_frac = bar_mass / max(g.stellar_mass, 1.0)
        bar_len = float(np.clip(0.9 + 10.0 * bar_frac, 0.9, 1.8))
        l_bar = 0.9 * OLD_LIGHT * bar_mass / max(disk_mass, 1.0)
        notes.append(
            f"instability bulge {ib_frac:.2f} of M* -> bar {bar_frac:.2f} of M*, "
            f"half-length {bar_len:.1f} Rd; rest pseudobulge"
        )
    l_bulge = OLD_LIGHT * (g.bulge_mass - bar_mass) / max(disk_mass, 1.0)

    # Young light relative to the old disk scales with specific SFR.
    ssfr_disk = g.sfr_disk / max(disk_mass, 1.0)
    l_young = float(np.clip(0.55 * (ssfr_disk / 1e-10) ** 0.7, 0.01, 1.5))
    n_clusters = int(np.clip(6000 * max(g.sfr_disk, 1e-3) ** 0.5, 400, 20000))
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

    return GalaxyRecipe(
        **ex,
        kind="disk",
        seed=int(rng.integers(1 << 31)),
        extent=extent,
        n_arms=n_arms,
        pitch_deg=pitch,
        arm_sharpness=sharp,
        flocculence=flocc,
        hz=hz,
        bulge_a=bulge_a,
        bulge_q=bulge_q,
        bar_len=bar_len,
        l_bar=l_bar,
        hole=float(max(bar_len * 0.9, 2.5 * bulge_a, 0.25)),
        hi_scale=hi_scale,
        arm_old_amp=float(0.45 * min(1.0, gas_frac / 0.08)),
        l_disk=OLD_LIGHT,
        l_bulge=float(l_bulge),
        l_young=l_young,
        l_nucleus=l_nuc,
        nucleus_sigma=nuc_sig,
        tau0=tau0,
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

    def sample(self, name, xg, yg):
        arr = getattr(self, name)
        n = arr.shape[0]
        ix = (xg + self.half) / (2 * self.half) * (n - 1)
        iy = (yg + self.half) / (2 * self.half) * (n - 1)
        return map_coordinates(
            arr, [iy.ravel(), ix.ravel()], order=1, mode="constant", cval=0.0
        ).reshape(xg.shape)


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
    phase = (
        rc.n_arms * (th - np.log(np.maximum(r, r0) / r0) / tanp) + 0.9 * wobble
    )
    arm_grand = ((1 + np.cos(phase)) / 2) ** rc.arm_sharpness
    floc = 1 / (1 + np.exp(-2.2 * fil))  # (0,1) filament field
    arm = (1 - rc.flocculence) * arm_grand + rc.flocculence * floc * (
        0.6 + 0.8 * arm_grand
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

    # Dust lanes sit on the inner (concave) edge of the arm.
    dphase = phase + 0.55
    arm_d = ((1 + np.cos(dphase)) / 2) ** (rc.arm_sharpness + 1.5)
    fil_d = 1 / (1 + np.exp(-3.5 * (fil + 0.3)))
    arm_dust = (
        (1 - rc.flocculence) * arm_d + rc.flocculence * fil_d * (0.4 + arm_d)
    ) * inner
    h2 = np.exp(-r / 0.9) * (0.08 + 2.5 * arm_dust**1.3) * np.exp(0.5 * clumps)
    hi = (
        np.exp(-r / rc.hi_scale)
        * (1 - 0.7 * np.exp(-((r / 1.2) ** 2)))
        * (0.15 + arm_dust)
    )
    dust = (h2 + 0.35 * hi) * outer_cut * inner
    # Normalise the total dust column to that of a smooth exponential disk
    # with face-on optical depth tau0 at its centre (2 pi tau0 Rd^2).  An
    # integral rather than a ring average, so a central hole (bar) doesn't
    # inflate the normalisation.
    dA = (ax[1] - ax[0]) ** 2
    dust *= 2 * np.pi * rc.tau0 / max(dust.sum() * dA, 1e-9)
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
        dust += (
            1.6
            * rc.ring
            * np.exp(-(((r - 1.25 * rr) / (0.13 * rr)) ** 2))
            * clump
        )
        if rc.bar_len > 0:
            for sgn in (1, -1):
                # Offset to the leading side, curving into the ring.
                yl = sgn * (0.10 * rc.bar_len + 0.18 * np.abs(x))
                lane = np.exp(-(((y - yl) / (0.035 * rc.bar_len)) ** 2))
                lane *= (sgn * x > 0.9 * rr) & (sgn * x < 1.05 * rc.bar_len)
                dust += 1.2 * rc.ring * lane * clump

    return PlaneMaps(
        half=half,
        old=old.astype(np.float32),
        young=young.astype(np.float32),
        dust=dust.astype(np.float32),
        hi=hi.astype(np.float32),
        h2=h2.astype(np.float32),
        arm=arm_eff.astype(np.float32),
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
        n_cx = max(rc.n_clusters // 6, 10)
        cx, cy = _sample_map(maps.young**1.3, maps.half, n_cx, rng)
        k = rng.integers(2, 11, n_cx)
        csz = np.repeat(rng.uniform(0.015, 0.06, n_cx), k)
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
            (maps.h2 * maps.young) ** 1.2, maps.half, rc.n_hii, rng
        )
        k = rng.integers(1, 5, rc.n_hii)
        hx = np.repeat(hx, k) + rng.normal(0, 0.025, k.sum())
        hy = np.repeat(hy, k) + rng.normal(0, 0.025, k.sum())
        m = len(hx)
        lum = rng.pareto(1.5, m) + 1
        lum = np.minimum(lum, 12)
        lum *= rc.l_young * 0.45 / lum.sum()
        out.append(
            Points(
                np.c_[hx, hy, rng.normal(0, 0.03, m)],
                lum,
                np.tile(HII_RGB, (m, 1)),
                rng.uniform(1.0, 2.0, m),
                "hii",
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

    # Merger debris (both kinds), all in old-star colours.
    if rc.shells > 0:
        out.append(_shells(rc, rng, 0.05 * rc.shells * main_light, old_rgb))
    if rc.tails > 0:
        out.append(_tails(rc, rng, 0.08 * rc.tails * main_light, old_rgb))
    if rc.stream > 0:
        out.append(_stream(rc, rng, 0.025 * rc.stream * main_light, old_rgb))
    return out


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


def _nuclear_ring(rc, rng, n=3000):
    """Star-forming ring around the bulge (driven by SfrBulge)."""
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
    r = rc.ring_r * (1 + rng.normal(0, 0.06, n))
    pos = np.c_[r * np.cos(th), r * np.sin(th), rng.normal(0, 0.02, n)]
    lum_c = np.full(n, rc.l_young * 0.35 * rc.ring / n)
    k = n // 3
    out = [
        Points(
            pos, lum_c, np.tile(CLUSTER_RGB, (n, 1)), np.full(n, 0.8), "ring"
        ),
        Points(
            pos[:k] * 1.01,
            np.full(k, rc.l_young * 0.2 * rc.ring / k),
            np.tile(HII_RGB, (k, 1)),
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
                np.tile(HII_RGB, (kk, 1)),
                rng.uniform(1.5, 3.0, kk),
                "ring_hii2",
            )
        )
    return out


def _hernquist_radii(rng, n, a):
    u = rng.random(n) * 0.98
    s = np.sqrt(u)
    return a * s / (1 - s)
