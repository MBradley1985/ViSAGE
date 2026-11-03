"""What every property is called, and its unit, in one place.

Text for the page is plain ("Msun", "yr^-1", "M_cold"): visage.js typesets
it. Text for a figure is LaTeX. Dropdowns give a name and symbol, sliders a
name and unit, and axes all three.
"""

from __future__ import annotations

# unit: (for the page, for a figure)
MSUN = ("Msun", r"$M_\odot$")
MSUN_YR = ("Msun yr^-1", r"$M_\odot\,{\rm yr}^{-1}$")
PER_YR = ("yr^-1", r"${\rm yr}^{-1}$")
KM_S = ("km s^-1", r"${\rm km\,s}^{-1}$")
MPC_H = ("h^-1 Mpc", r"$h^{-1}\,{\rm Mpc}$")
GYR = ("Gyr", "Gyr")
KPC = ("kpc", "kpc")
RATE = ("SAGE units", "SAGE units")
# As the file holds them: discovered properties are not converted.
RAW_MASS = ("10^10 Msun h^-1", r"$10^{10}\,M_\odot\,h^{-1}$")
MSUN_GYR = ("Msun Gyr^-1", r"$M_\odot\,{\rm Gyr}^{-1}$")
MYR = ("Myr", "Myr")
MYR_H = ("h^-1 Myr", r"$h^{-1}\,{\rm Myr}$")
SPIN = ("Mpc km s^-1", r"${\rm Mpc\,km\,s}^{-1}$")

# key: (name, symbol for the page, symbol for a figure, unit)
PROPERTIES = {
    "mvir": ("Halo mass", "Mvir", r"M_{\rm vir}", MSUN),
    "rvir": ("Virial radius", "Rvir", r"R_{\rm vir}", MPC_H),
    "vvir": ("Virial velocity", "Vvir", r"V_{\rm vir}", KM_S),
    "vmax": ("Maximum circular velocity", "Vmax", r"V_{\rm max}", KM_S),
    "stellar_mass": ("Stellar mass", "M*", r"M_\star", MSUN),
    "sfr": ("Star formation rate", "SFR", r"{\rm SFR}", MSUN_YR),
    "ssfr": ("Specific star formation rate", "sSFR", r"s{\rm SFR}", PER_YR),
    "bt": ("Bulge-to-total ratio", "B/T", r"B/T", None),
    "age": ("Stellar age", "", "", GYR),
    "type": ("Galaxy type", "", "", None),
    "bh_mass": ("Black hole mass", "M_BH", r"M_{\rm BH}", MSUN),
    "bulge_mass": ("Bulge mass", "M_bulge", r"M_{\rm bulge}", MSUN),
    "bulge_radius": ("Bulge radius", "R_bulge", r"R_{\rm bulge}", MPC_H),
    "cgm_gas": ("CGM gas", "M_CGM", r"M_{\rm CGM}", MSUN),
    "cold_gas": ("Cold gas", "M_cold", r"M_{\rm cold}", MSUN),
    "cooling": ("Cooling rate", "", "", RATE),
    "disk_radius": ("Disk radius", "R_disk", r"R_{\rm disk}", MPC_H),
    "ejected_mass": ("Ejected gas", "M_ej", r"M_{\rm ej}", MSUN),
    "h1_gas": ("Atomic hydrogen", "H1", r"{\rm H}_1", MSUN),
    "h2_gas": ("Molecular hydrogen", "H2", r"{\rm H}_2", MSUN),
    "heating": ("Heating rate", "", "", RATE),
    "hot_gas": ("Hot gas", "M_hot", r"M_{\rm hot}", MSUN),
    "ics_mass": ("Intracluster stars", "M_ICS", r"M_{\rm ICS}", MSUN),
    "instability_bulge_mass": (
        "Instability bulge mass",
        "M_ib",
        r"M_{\rm ib}",
        MSUN,
    ),
    "instability_bulge_radius": (
        "Instability bulge radius",
        "R_ib",
        r"R_{\rm ib}",
        MPC_H,
    ),
    "mass_loading": ("Mass loading", "η", r"\eta", None),
    "merger_bulge_mass": ("Merger bulge mass", "M_mb", r"M_{\rm mb}", MSUN),
    "merger_bulge_radius": (
        "Merger bulge radius",
        "R_mb",
        r"R_{\rm mb}",
        MPC_H,
    ),
    "metals_bulge_mass": ("Metals in the bulge", "", "", MSUN),
    "metals_cgm_gas": ("Metals in CGM gas", "", "", MSUN),
    "metals_cold_gas": ("Metals in cold gas", "", "", MSUN),
    "metals_ejected_mass": ("Metals in ejected gas", "", "", MSUN),
    "metals_hot_gas": ("Metals in hot gas", "", "", MSUN),
    "metals_ics": ("Metals in intracluster stars", "", "", MSUN),
    "metals_stellar_mass": ("Metals in stars", "", "", MSUN),
    "outflow_rate": ("Outflow rate", "", "", MSUN_YR),
    "sfr_bulge": ("Bulge star formation rate", "", "", MSUN_YR),
    "sfr_bulge_z": ("Bulge star formation metallicity", "", "", None),
    "sfr_disk": ("Disk star formation rate", "", "", MSUN_YR),
    "sfr_disk_z": ("Disk star formation metallicity", "", "", None),
    "stellar_metallicity": ("Stellar metallicity", "", r"Z_\star", None),
    "metallicity": ("Metallicity", "", r"12 + \log_{10}({\rm O/H})", None),
    "baryon_mass": ("Baryonic mass", "M_bar", r"M_{\rm bar}", MSUN),
    "dust_mass": ("Dust mass", "M_dust", r"M_{\rm dust}", MSUN),
}

# Properties found in a model's own files, by dataset:
# (name, symbol for the page, unit).
DISCOVERED = {
    "CGMDust": ("Dust in CGM gas", "", RAW_MASS),
    "ColdDust": ("Dust in cold gas", "", RAW_MASS),
    "CoolingRate": ("CGM cooling rate", "", MSUN_GYR),
    "DustDestructionRate": ("Dust destruction rate", "", MSUN_YR),
    "DustFormationRate": ("Dust formation rate", "", MSUN_YR),
    "DustGrowthRate": ("Dust growth rate", "", MSUN_YR),
    "EjectedDust": ("Dust in ejected gas", "", RAW_MASS),
    "GasDiscHalfMassRadius": ("Gas disk half-mass radius", "", MPC_H),
    "GasDiscScaleRadius": ("Gas disk scale radius", "", MPC_H),
    "H2DepletionTime_Gyr": ("H2 depletion time", "", GYR),
    "HotDust": ("Dust in hot gas", "", RAW_MASS),
    "ICSMeanRadius": ("Intracluster stars mean radius", "", MPC_H),
    "ICS_accrete": ("Intracluster stars, accreted", "", RAW_MASS),
    "ICS_disrupt": ("Intracluster stars, stripped in situ", "", RAW_MASS),
    "ICS_sum_mt": ("Intracluster stars, mass times time", "", RATE),
    "QuasarModeBHaccretionMass": (
        "Quasar-mode black hole accretion",
        "",
        RAW_MASS,
    ),
    "RadioModeBHaccretionMass": (
        "Radio-mode black hole accretion",
        "",
        RAW_MASS,
    ),
    "RcoolToRvir": ("R_cool-to-Rvir", "", None),
    "Spinx": ("Halo spin, x", "", SPIN),
    "Spiny": ("Halo spin, y", "", SPIN),
    "Spinz": ("Halo spin, z", "", SPIN),
    "StellarDiscHalfMassRadius": ("Stellar disk half-mass radius", "", MPC_H),
    "StellarDiscScaleRadius": ("Stellar disk scale radius", "", MPC_H),
    "TimeOfLastMajorMerger": ("Lookback time to last major merger", "", MYR_H),
    "TimeOfLastMinorMerger": ("Lookback time to last minor merger", "", MYR_H),
    "TimeOfLastQuasarBurst": ("Lookback time to last quasar burst", "", MYR_H),
    "VelDisp": ("Halo velocity dispersion", "σ", KM_S),
    "VelDispBulge": ("Instability bulge velocity dispersion", "", KM_S),
    "VelDispMergerBulge": ("Merger bulge velocity dispersion", "", KM_S),
    "Velx": ("Galaxy velocity, x", "", KM_S),
    "Vely": ("Galaxy velocity, y", "", KM_S),
    "Velz": ("Galaxy velocity, z", "", KM_S),
    "Vvir": ("Virial velocity", "Vvir", KM_S),
    "g_max": ("Peak gravitational acceleration", "g_max", RATE),
    "infallMvir": ("Infall halo mass", "Mvir", RAW_MASS),
    "infallStellarMass": ("Infall stellar mass", "M*", RAW_MASS),
    "infallVmax": ("Infall maximum circular velocity", "Vmax", KM_S),
    "infallVvir": ("Infall virial velocity", "Vvir", KM_S),
    "mdot_cool": ("Cooling rate onto the disk", "", RATE),
    "mdot_stream": ("Cold stream inflow rate", "", RATE),
    "mergeType": ("Merger type", "", None),
    "r_heat": ("AGN heating radius", "R_heat", MPC_H),
    "tcool": ("Cooling time", "t_cool", GYR),
    "tff": ("Free-fall time", "t_ff", GYR),
}


def discovered(dataset: str, log: bool) -> tuple | None:
    """A found dataset's dropdown and slider labels, if it is a known one."""
    if dataset not in DISCOVERED:
        return None
    title, symbol, unit = DISCOVERED[dataset]
    text = unit[0] if unit else ""
    text = f"log10 {text}".strip() if log else text
    return (
        f"{title} ({symbol})" if symbol else title,
        f"{title} ({text})" if text else title,
    )


def name(key: str) -> str:
    """For a dropdown: "Stellar mass (M*)"."""
    title, symbol, _, _ = PROPERTIES[key]
    return f"{title} ({symbol})" if symbol else title


def slider(key: str, log: bool = True) -> str:
    """For a slider: "Stellar mass (log10 Msun)"."""
    title, _, _, unit = PROPERTIES[key]
    text = unit[0] if unit else ""
    text = f"log10 {text}".strip() if log else text
    return f"{title} ({text})" if text else title


def axis(key: str, unit: tuple | None = None) -> str:
    """For a figure: "Stellar mass $M_\\star$ ($M_\\odot$)"."""
    title, _, symbol, default = PROPERTIES[key]
    unit = unit or default
    text = f"{title} ${symbol}$" if symbol else title
    return f"{text} ({unit[1]})" if unit else text
