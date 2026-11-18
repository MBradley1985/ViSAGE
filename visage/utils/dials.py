"""The Filters tab's two dials, one for haloes and one for galaxies: the
filter each property drives, its unit, and where the haloes or galaxies sit
on it (the ring's histogram).

A dial sets the same filter_* state a slider did, so filters.py applies it
unchanged.  Log properties are shown as 10^x and their unit.
"""

from __future__ import annotations

import re

import numpy as np

from visage.utils import labels

# Solar metallicity, as HD uses it (the star-formation metallicities are
# shown in solar units).
Z_SUN = 0.02
NBINS = 60


def _lg(x, floor=1.0):
    return np.log10(np.maximum(np.asarray(x, np.float64), floor))


def _lnz(x):
    """log10 of the positive values only (zero means absent: it passes)."""
    x = np.asarray(x, np.float64)
    return np.log10(x[x > 0])


# (filter state key, side, labels key or title, unit or None to take it
# from labels, log, min, max, step, model field it needs, values)
# values(halos, galaxies): the property as its filter reads it.
_H, _G = "halo", "gal"
DIALS = [
    (
        "filter_halo_mvir",
        _H,
        "mvir",
        None,
        True,
        10.0,
        15.0,
        0.1,
        None,
        lambda h, g: _lg(h.masses),
    ),
    (
        "filter_halo_rvir",
        _H,
        "rvir",
        None,
        False,
        0.0,
        3.0,
        0.05,
        None,
        lambda h, g: h.rvir,
    ),
    (
        "filter_halo_vmax",
        _H,
        "vmax",
        None,
        False,
        0.0,
        1000.0,
        10.0,
        "vmax",
        lambda h, g: h.vmax,
    ),
    (
        "filter_halo_vvir",
        _H,
        "vvir",
        None,
        False,
        0.0,
        1000.0,
        10.0,
        None,
        lambda h, g: h.vvir,
    ),
    (
        "filter_halo_conc",
        _H,
        "Concentration",
        "",
        False,
        0.0,
        50.0,
        0.5,
        "concentration",
        lambda h, g: g.concentration,
    ),
    (
        "filter_halo_len",
        _H,
        "Particles",
        "",
        False,
        0,
        10000,
        100,
        "len_particles",
        lambda h, g: g.len_particles,
    ),
    (
        "filter_halo_spin",
        _H,
        "Spin",
        "",
        False,
        0.0,
        0.2,
        0.002,
        "spin",
        lambda h, g: g.spin,
    ),
    (
        "filter_gal_smass",
        _G,
        "stellar_mass",
        None,
        True,
        0.0,
        14.0,
        0.1,
        None,
        lambda h, g: _lg(g.stellar_mass),
    ),
    (
        "filter_gal_sfr",
        _G,
        "sfr",
        None,
        True,
        -6.0,
        5.0,
        0.1,
        None,
        lambda h, g: _lg(g.sfr, 1e-6),
    ),
    (
        "filter_gal_ssfr",
        _G,
        "ssfr",
        None,
        True,
        -14.0,
        0.0,
        0.1,
        None,
        lambda h, g: _lg(g.ssfr, 1e-14),
    ),
    (
        "filter_gal_coldgas",
        _G,
        "cold_gas",
        None,
        True,
        0.0,
        14.0,
        0.1,
        None,
        lambda h, g: _lg(g.cold_gas),
    ),
    (
        "filter_gal_bulge",
        _G,
        "bulge_mass",
        None,
        True,
        0.0,
        14.0,
        0.1,
        None,
        lambda h, g: _lg(g.bulge_mass),
    ),
    (
        "filter_gal_bt",
        _G,
        "Bulge-to-total (B/T)",
        "",
        False,
        0.0,
        1.0,
        0.02,
        None,
        lambda h, g: np.clip(
            g.bulge_mass / np.maximum(g.stellar_mass, 1.0), 0.0, 1.0
        ),
    ),
    (
        "filter_gal_bhmass",
        _G,
        "bh_mass",
        None,
        True,
        0.0,
        14.0,
        0.1,
        "bh_mass",
        lambda h, g: _lg(g.bh_mass),
    ),
    (
        "filter_gal_ics",
        _G,
        "ics_mass",
        None,
        True,
        0.0,
        14.0,
        0.1,
        "ics_mass",
        lambda h, g: _lg(g.ics_mass),
    ),
    (
        "filter_gal_h2",
        _G,
        "h2_gas",
        None,
        True,
        0.0,
        14.0,
        0.1,
        "h2_mass",
        lambda h, g: _lg(g.h2_mass),
    ),
    (
        "filter_gal_h1gas",
        _G,
        "h1_gas",
        None,
        True,
        0.0,
        14.0,
        0.1,
        "h1_gas",
        lambda h, g: _lg(g.h1_gas),
    ),
    (
        "filter_gal_cgmgas",
        _G,
        "cgm_gas",
        None,
        True,
        0.0,
        14.0,
        0.1,
        "cgm_gas",
        lambda h, g: _lg(g.cgm_gas),
    ),
    (
        "filter_gal_hotgas",
        _G,
        "hot_gas",
        None,
        True,
        0.0,
        14.0,
        0.1,
        "hot_gas",
        lambda h, g: _lg(g.hot_gas),
    ),
    (
        "filter_gal_ejected",
        _G,
        "ejected_mass",
        None,
        True,
        0.0,
        14.0,
        0.1,
        "ejected_mass",
        lambda h, g: _lg(g.ejected_mass),
    ),
    (
        "filter_gal_outflow",
        _G,
        "outflow_rate",
        None,
        True,
        -6.0,
        5.0,
        0.1,
        "outflow_rate",
        lambda h, g: _lnz(g.outflow_rate),
    ),
    (
        "filter_gal_massload",
        _G,
        "Mass loading",
        "",
        True,
        -3.0,
        5.0,
        0.05,
        "mass_loading",
        lambda h, g: _lnz(g.mass_loading),
    ),
    (
        "filter_gal_cooling",
        _G,
        "cooling",
        "erg s^-1",
        True,
        34.0,
        46.0,
        0.1,
        "cooling",
        lambda h, g: np.asarray(g.cooling)[np.asarray(g.cooling) > 0],
    ),
    (
        "filter_gal_heating",
        _G,
        "heating",
        "erg s^-1",
        True,
        34.0,
        46.0,
        0.1,
        "heating",
        lambda h, g: np.asarray(g.heating)[np.asarray(g.heating) > 0],
    ),
    (
        "filter_gal_diskrad",
        _G,
        "disk_radius",
        None,
        True,
        -4.0,
        1.0,
        0.05,
        "disk_radius",
        lambda h, g: _lnz(g.disk_radius),
    ),
    (
        "filter_gal_bulgerad",
        _G,
        "bulge_radius",
        None,
        True,
        -4.0,
        1.0,
        0.05,
        "bulge_radius",
        lambda h, g: _lnz(g.bulge_radius),
    ),
    (
        "filter_gal_mb_mass",
        _G,
        "merger_bulge_mass",
        None,
        True,
        0.0,
        14.0,
        0.1,
        "merger_bulge_mass",
        lambda h, g: _lg(g.merger_bulge_mass),
    ),
    (
        "filter_gal_mb_rad",
        _G,
        "merger_bulge_radius",
        None,
        True,
        -4.0,
        1.0,
        0.05,
        "merger_bulge_radius",
        lambda h, g: _lnz(g.merger_bulge_radius),
    ),
    (
        "filter_gal_ib_mass",
        _G,
        "instability_bulge_mass",
        None,
        True,
        0.0,
        14.0,
        0.1,
        "instability_bulge_mass",
        lambda h, g: _lg(g.instability_bulge_mass),
    ),
    (
        "filter_gal_ib_rad",
        _G,
        "instability_bulge_radius",
        None,
        True,
        -4.0,
        1.0,
        0.05,
        "instability_bulge_radius",
        lambda h, g: _lnz(g.instability_bulge_radius),
    ),
    (
        "filter_gal_sfr_bulge",
        _G,
        "sfr_bulge",
        None,
        True,
        -6.0,
        5.0,
        0.1,
        "sfr_bulge",
        lambda h, g: _lg(g.sfr_bulge, 1e-6),
    ),
    (
        "filter_gal_sfr_disk",
        _G,
        "sfr_disk",
        None,
        True,
        -6.0,
        5.0,
        0.1,
        "sfr_disk",
        lambda h, g: _lg(g.sfr_disk, 1e-6),
    ),
    (
        "filter_gal_sfr_blg_z",
        _G,
        "sfr_bulge_z",
        "Zsun",
        True,
        -6.0,
        1.0,
        0.1,
        "sfr_bulge_z",
        lambda h, g: _lg(g.sfr_bulge_z, 1e-6),
    ),
    (
        "filter_gal_sfr_dsk_z",
        _G,
        "sfr_disk_z",
        "Zsun",
        True,
        -6.0,
        1.0,
        0.1,
        "sfr_disk_z",
        lambda h, g: _lg(g.sfr_disk_z, 1e-6),
    ),
    (
        "filter_gal_met_cg",
        _G,
        "metals_cold_gas",
        None,
        True,
        -2.0,
        12.0,
        0.1,
        "metals_cold_gas",
        lambda h, g: _lg(g.metals_cold_gas),
    ),
    (
        "filter_gal_met_sm",
        _G,
        "metals_stellar_mass",
        None,
        True,
        -2.0,
        12.0,
        0.1,
        "metals_stellar_mass",
        lambda h, g: _lg(g.metals_stellar_mass),
    ),
    (
        "filter_gal_met_bm",
        _G,
        "metals_bulge_mass",
        None,
        True,
        -2.0,
        12.0,
        0.1,
        "metals_bulge_mass",
        lambda h, g: _lg(g.metals_bulge_mass),
    ),
    (
        "filter_gal_met_hg",
        _G,
        "metals_hot_gas",
        None,
        True,
        -2.0,
        12.0,
        0.1,
        "metals_hot_gas",
        lambda h, g: _lg(g.metals_hot_gas),
    ),
    (
        "filter_gal_met_em",
        _G,
        "metals_ejected_mass",
        None,
        True,
        -2.0,
        12.0,
        0.1,
        "metals_ejected_mass",
        lambda h, g: _lg(g.metals_ejected_mass),
    ),
    (
        "filter_gal_met_ics",
        _G,
        "metals_ics",
        None,
        True,
        -2.0,
        12.0,
        0.1,
        "metals_ics",
        lambda h, g: _lg(g.metals_ics),
    ),
    (
        "filter_gal_met_cgm",
        _G,
        "metals_cgm_gas",
        None,
        True,
        -2.0,
        12.0,
        0.1,
        "metals_cgm_gas",
        lambda h, g: _lg(g.metals_cgm_gas),
    ),
    (
        "filter_gal_age",
        _G,
        "age",
        None,
        False,
        0.0,
        14.0,
        0.1,
        "mean_age",
        lambda h, g: np.asarray(g.mean_age)[np.asarray(g.mean_age) > 0],
    ),
]


def _title_unit(name: str, unit: str | None) -> tuple[str, str]:
    if name in labels.PROPERTIES:
        title, _, _, u = labels.PROPERTIES[name]
        return title, (u[0] if u else "") if unit is None else unit
    return name, unit or ""


def _hist(vals, lo: float, hi: float, step: float) -> dict:
    """Where they sit: the ring spans the data (0.1-99.9th percentiles, to
    the step) within the filter's range, and the bars are log counts, so a
    thin tail shows.  A handle at either end of the ring means no limit."""
    v = np.asarray(vals, np.float64)
    v = v[np.isfinite(v) & (v >= lo) & (v <= hi)]
    if v.size < 2:
        return {"hist": [], "lo": lo, "hi": hi}
    a, b = np.percentile(v, [0.1, 99.9])
    a = max(lo, np.floor(a / step) * step)
    b = min(hi, np.ceil(b / step) * step)
    if b <= a:
        a, b = lo, hi
    n, _ = np.histogram(v, bins=NBINS, range=(a, b))
    h = np.log1p(n) / np.log1p(max(n.max(), 1))
    return {
        "hist": [round(float(x), 3) for x in h],
        "lo": round(float(a), 6),
        "hi": round(float(b), 6),
    }


def _extra(spec: dict, state_key: str, vals) -> dict:
    """A property found in the model's own output (its slider label is
    "Title (log10 unit)" or "Title (unit)")."""
    m = re.match(r"^(.*?)\s*\((.*)\)$", spec["label"])
    title, unit = (m.group(1), m.group(2)) if m else (spec["label"], "")
    unit = re.sub(r"^log10\s*", "", unit)
    # A raw mass unit's 10^10 goes into the exponent (10^x Msun h^-1).
    shift = 0.0
    m10 = re.match(r"^10\^(\d+)\s+(.*)$", unit)
    if spec["log"] and m10:
        shift, unit = float(m10.group(1)), m10.group(2)
    v = np.asarray(vals, np.float64)
    if spec["log"]:
        v = np.log10(v[v > 0])
    return {
        "key": state_key,
        "title": title,
        "unit": unit,
        "log": bool(spec["log"]),
        "shift": shift,
        "min": spec["min"],
        "max": spec["max"],
        "step": spec["step"],
        **_hist(v, spec["min"], spec["max"], spec["step"]),
    }


def items(halos, galaxies, fields: dict, extra_halo=(), extra_gal=()) -> dict:
    """{"halo": [...], "gal": [...]}: each property this model has, with its
    filter key, title, unit, range and histogram."""
    out = {_H: [], _G: []}
    for key, side, name, unit, log, lo, hi, step, field, values in DIALS:
        if field and not fields.get(field, False):
            continue
        title, unit = _title_unit(name, unit)
        try:
            # Haloes from the halo snapshot; the rest from the galaxies.
            src_ok = (
                halos.count
                if key
                in (
                    "filter_halo_mvir",
                    "filter_halo_rvir",
                    "filter_halo_vmax",
                    "filter_halo_vvir",
                )
                else galaxies.count
            )
            ring = (
                _hist(values(halos, galaxies), lo, hi, step) if src_ok else {}
            )
        except (AttributeError, ValueError, TypeError):
            ring = {}
        out[side].append(
            {
                "key": key,
                "title": title,
                "unit": unit,
                "log": log,
                # Metallicities: shown in solar units.
                "shift": -float(np.log10(Z_SUN)) if unit == "Zsun" else 0.0,
                "min": lo,
                "max": hi,
                "step": step,
                **{"hist": [], "lo": lo, "hi": hi, **ring},
            }
        )
    for side, specs, prefix in (
        (_H, extra_halo, "extra_halo_filter"),
        (_G, extra_gal, "extra_gal_filter"),
    ):
        for i, spec in enumerate(specs or ()):
            vals = galaxies.extra.get(spec["key"]) if galaxies.count else None
            if vals is None:
                continue
            out[side].append(_extra(spec, f"{prefix}_{i}", vals))
    for side in out:
        out[side].sort(key=lambda d: d["title"].lower())
    return out
