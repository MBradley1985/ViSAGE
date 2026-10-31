"""The galaxies the Filters tab and the Environment checkboxes keep."""

from __future__ import annotations

import numpy as np


def galaxy_mask(galaxies, fields: dict, state) -> np.ndarray:
    """Boolean mask over `galaxies` for the filter settings in `state`
    (anything with the filter_gal_* and env_show_* attributes)."""
    g_mask = np.ones(galaxies.count, dtype=bool)

    # Each range filter is only applied when the slider has been moved off its
    # full-range default — at default every slider is a pass-through.
    def _active(lo, hi, mn, mx):
        """True when the slider has been moved away from its default extent."""
        return float(lo) > mn + 1e-6 or float(hi) < mx - 1e-6

    def _lg(x):
        return np.log10(np.maximum(x, 1.0))

    def _lgr(x):
        return np.log10(np.maximum(x, 1e-6))

    def _apply(lo, hi, arr, mn, mx):
        if _active(lo, hi, mn, mx):
            g_mask.__iand__((arr >= float(lo)) & (arr <= float(hi)))

    def _apply_nz(lo, hi, raw, mn, mx):
        # Zero/negative raw values always pass (not "below range", just absent).
        if _active(lo, hi, mn, mx):
            log_v = np.log10(np.maximum(raw, 1e-30))
            g_mask.__iand__(
                (raw <= 0) | ((log_v >= float(lo)) & (log_v <= float(hi)))
            )

    # ── Unconditional filters ──────────────────────────────────────────
    sm_lo, sm_hi = state.filter_gal_smass
    if _active(sm_lo, sm_hi, 0.0, 14.0):
        sm_log = np.log10(np.maximum(galaxies.stellar_mass, 1.0))
        g_mask &= (sm_log >= float(sm_lo)) & (sm_log <= float(sm_hi))

    sfr_lo, sfr_hi = state.filter_gal_sfr
    if _active(sfr_lo, sfr_hi, -6.0, 5.0):
        sfr_log = np.log10(np.maximum(galaxies.sfr, 1e-6))
        g_mask &= (sfr_log >= float(sfr_lo)) & (sfr_log <= float(sfr_hi))

    ss_lo, ss_hi = state.filter_gal_ssfr
    if _active(ss_lo, ss_hi, -14.0, 0.0):
        ssfr_log = np.log10(np.maximum(galaxies.ssfr, 1e-14))
        g_mask &= (ssfr_log >= float(ss_lo)) & (ssfr_log <= float(ss_hi))

    cg_lo, cg_hi = state.filter_gal_coldgas
    if _active(cg_lo, cg_hi, 0.0, 14.0):
        cg_log = np.log10(np.maximum(galaxies.cold_gas, 1.0))
        g_mask &= (cg_log >= float(cg_lo)) & (cg_log <= float(cg_hi))

    bm_lo, bm_hi = state.filter_gal_bulge
    if _active(bm_lo, bm_hi, 0.0, 14.0):
        bm_log = np.log10(np.maximum(galaxies.bulge_mass, 1.0))
        g_mask &= (bm_log >= float(bm_lo)) & (bm_log <= float(bm_hi))

    bt_lo, bt_hi = state.filter_gal_bt
    if _active(bt_lo, bt_hi, 0.0, 1.0):
        sm_safe = np.maximum(galaxies.stellar_mass, 1.0)
        # Clamp: SAGE can produce BulgeMass > StellarMass numerically.
        bt_c = np.clip(galaxies.bulge_mass / sm_safe, 0.0, 1.0)
        g_mask &= (bt_c >= float(bt_lo)) & (bt_c <= float(bt_hi))

    t = str(state.filter_gal_type)
    if t == "central":
        g_mask &= galaxies.gal_type == 0
    elif t == "satellite":
        g_mask &= galaxies.gal_type > 0

    # ── Auto-discovered properties ─────────────────────────────────────
    # Values live on the galaxies either way — a halo-classified
    # field is a property of each galaxy's host halo — so both
    # groups narrow the galaxy mask.  Same pass-through rule as the
    # named filters: a slider left at its full extent filters
    # nothing.
    def _apply_extra(prefix: str, i: int, spec: dict) -> None:
        rng = getattr(state, f"{prefix}_{i}", None)
        if not rng or len(rng) != 2:
            return
        lo, hi = float(rng[0]), float(rng[1])
        if not _active(lo, hi, spec["min"], spec["max"]):
            return
        vals = galaxies.extra.get(spec["key"])
        if vals is None or len(vals) != galaxies.count:
            return
        vals = np.asarray(vals, dtype=np.float64)
        if spec["log"]:
            # Non-positive values have no log — treat them as absent
            # and let them pass, as the other log filters do.
            with np.errstate(divide="ignore", invalid="ignore"):
                log_v = np.log10(np.maximum(vals, 1e-30))
            g_mask.__iand__((vals <= 0) | ((log_v >= lo) & (log_v <= hi)))
        else:
            g_mask.__iand__((vals >= lo) & (vals <= hi))

    for _prefix, _specs in (
        ("extra_halo_filter", state.extra_halo_filters or []),
        ("extra_gal_filter", state.extra_gal_filters or []),
    ):
        for _i, _spec in enumerate(_specs):
            _apply_extra(_prefix, _i, _spec)

    # ── Host-halo properties, carried per galaxy ───────────────────────
    # Shown among the galaxy sliders because that is what they
    # filter: the halo snapshot has no Len / Concentration / Spin
    # of its own.
    if fields.get("len_particles", False):
        lo, hi = state.filter_halo_len
        if _active(lo, hi, 0, 10000):
            g_mask &= (galaxies.len_particles >= float(lo)) & (
                galaxies.len_particles <= float(hi)
            )

    if fields.get("concentration", False):
        lo, hi = state.filter_halo_conc
        if _active(lo, hi, 0.0, 50.0):
            g_mask &= (galaxies.concentration >= float(lo)) & (
                galaxies.concentration <= float(hi)
            )

    if fields.get("spin", False):
        lo, hi = state.filter_halo_spin
        if _active(lo, hi, 0.0, 0.2):
            g_mask &= (galaxies.spin >= float(lo)) & (
                galaxies.spin <= float(hi)
            )

    # ── Conditional filters ────────────────────────────────────────────
    if fields.get("bh_mass", False):
        lo, hi = state.filter_gal_bhmass
        _apply(lo, hi, _lg(galaxies.bh_mass), 0.0, 14.0)

    if fields.get("ics_mass", False):
        lo, hi = state.filter_gal_ics
        _apply(lo, hi, _lg(galaxies.ics_mass), 0.0, 14.0)

    if fields.get("h2_mass", False):
        lo, hi = state.filter_gal_h2
        _apply(lo, hi, _lg(galaxies.h2_mass), 0.0, 14.0)

    if fields.get("cgm_gas", False):
        lo, hi = state.filter_gal_cgmgas
        _apply(lo, hi, _lg(galaxies.cgm_gas), 0.0, 14.0)

    if fields.get("hot_gas", False):
        lo, hi = state.filter_gal_hotgas
        _apply(lo, hi, _lg(galaxies.hot_gas), 0.0, 14.0)

    if fields.get("h1_gas", False):
        lo, hi = state.filter_gal_h1gas
        _apply(lo, hi, _lg(galaxies.h1_gas), 0.0, 14.0)

    if fields.get("ejected_mass", False):
        lo, hi = state.filter_gal_ejected
        _apply(lo, hi, _lg(galaxies.ejected_mass), 0.0, 14.0)

    if fields.get("outflow_rate", False):
        lo, hi = state.filter_gal_outflow
        _apply_nz(lo, hi, galaxies.outflow_rate, -6.0, 5.0)

    if fields.get("mass_loading", False):
        lo, hi = state.filter_gal_massload
        _apply_nz(lo, hi, galaxies.mass_loading, -3.0, 5.0)

    if fields.get("cooling", False):
        lo, hi = state.filter_gal_cooling
        _apply_nz(lo, hi, galaxies.cooling, -7.0, 7.0)

    if fields.get("heating", False):
        lo, hi = state.filter_gal_heating
        _apply_nz(lo, hi, galaxies.heating, -7.0, 7.0)

    if fields.get("disk_radius", False):
        lo, hi = state.filter_gal_diskrad
        _apply_nz(lo, hi, galaxies.disk_radius, -4.0, 1.0)

    if fields.get("bulge_radius", False):
        lo, hi = state.filter_gal_bulgerad
        _apply_nz(lo, hi, galaxies.bulge_radius, -4.0, 1.0)

    if fields.get("merger_bulge_mass", False):
        lo, hi = state.filter_gal_mb_mass
        _apply(lo, hi, _lg(galaxies.merger_bulge_mass), 0.0, 14.0)

    if fields.get("merger_bulge_radius", False):
        lo, hi = state.filter_gal_mb_rad
        _apply_nz(lo, hi, galaxies.merger_bulge_radius, -4.0, 1.0)

    if fields.get("instability_bulge_mass", False):
        lo, hi = state.filter_gal_ib_mass
        _apply(lo, hi, _lg(galaxies.instability_bulge_mass), 0.0, 14.0)

    if fields.get("instability_bulge_radius", False):
        lo, hi = state.filter_gal_ib_rad
        _apply_nz(lo, hi, galaxies.instability_bulge_radius, -4.0, 1.0)

    if fields.get("sfr_bulge", False):
        lo, hi = state.filter_gal_sfr_bulge
        _apply(lo, hi, _lgr(galaxies.sfr_bulge), -6.0, 5.0)

    if fields.get("sfr_disk", False):
        lo, hi = state.filter_gal_sfr_disk
        _apply(lo, hi, _lgr(galaxies.sfr_disk), -6.0, 5.0)

    if fields.get("sfr_bulge_z", False):
        lo, hi = state.filter_gal_sfr_blg_z
        _apply(lo, hi, _lgr(galaxies.sfr_bulge_z), -6.0, 1.0)

    if fields.get("sfr_disk_z", False):
        lo, hi = state.filter_gal_sfr_dsk_z
        _apply(lo, hi, _lgr(galaxies.sfr_disk_z), -6.0, 1.0)

    if fields.get("metals_cold_gas", False):
        lo, hi = state.filter_gal_met_cg
        _apply(lo, hi, _lg(galaxies.metals_cold_gas), -2.0, 12.0)

    if fields.get("metals_stellar_mass", False):
        lo, hi = state.filter_gal_met_sm
        _apply(lo, hi, _lg(galaxies.metals_stellar_mass), -2.0, 12.0)

    if fields.get("metals_bulge_mass", False):
        lo, hi = state.filter_gal_met_bm
        _apply(lo, hi, _lg(galaxies.metals_bulge_mass), -2.0, 12.0)

    if fields.get("metals_hot_gas", False):
        lo, hi = state.filter_gal_met_hg
        _apply(lo, hi, _lg(galaxies.metals_hot_gas), -2.0, 12.0)

    if fields.get("metals_ejected_mass", False):
        lo, hi = state.filter_gal_met_em
        _apply(lo, hi, _lg(galaxies.metals_ejected_mass), -2.0, 12.0)

    if fields.get("metals_ics", False):
        lo, hi = state.filter_gal_met_ics
        _apply(lo, hi, _lg(galaxies.metals_ics), -2.0, 12.0)

    if fields.get("metals_cgm_gas", False):
        lo, hi = state.filter_gal_met_cgm
        _apply(lo, hi, _lg(galaxies.metals_cgm_gas), -2.0, 12.0)

    if fields.get("ffb_regime", False):
        ffb = str(state.filter_gal_ffb)
        if ffb == "yes":
            g_mask &= galaxies.ffb_regime != 0
        elif ffb == "no":
            g_mask &= galaxies.ffb_regime == 0

    if fields.get("cgm_regime", False):
        cgm = str(state.filter_gal_cgm)
        if cgm == "cold":
            g_mask &= galaxies.cgm_regime == 0
        elif cgm == "hot":
            g_mask &= galaxies.cgm_regime == 1

    if fields.get("mean_age", False):
        age_lo, age_hi = state.filter_gal_age
        ages = galaxies.mean_age
        # 0-age galaxies are those with no SFH data — keep them visible
        # only when the slider includes 0 to avoid hiding everything.
        age_mask = (ages >= float(age_lo)) & (ages <= float(age_hi))
        if float(age_lo) > 0.0:
            g_mask &= age_mask
        else:
            g_mask &= (ages == 0) | age_mask

    # Environment categories — checkbox-driven; subset → mask
    show_f = bool(state.env_show_field)
    show_i = bool(state.env_show_isolated)
    show_p = bool(state.env_show_pairs)
    show_g = bool(state.env_show_group)
    show_c = bool(state.env_show_cluster)
    all_on = show_f and show_i and show_p and show_g and show_c
    if not all_on and fields.get("central_mvir", False):
        cm = galaxies.central_mvir
        log_cm = np.log10(np.maximum(cm, 1.0))
        cat_mask = np.zeros(galaxies.count, dtype=bool)
        if show_f:
            cat_mask |= log_cm < 11.0
        if show_i:
            cat_mask |= (log_cm >= 11.0) & (log_cm < 12.5)
        if show_p and fields.get("central_id", False):
            # Use central_id (not central_mvir) for accurate FOF group count
            _, _inv, _grp_sizes = np.unique(
                galaxies.central_id,
                return_inverse=True,
                return_counts=True,
            )
            cat_mask |= _grp_sizes[_inv] == 2
        if show_g:
            cat_mask |= (log_cm >= 12.5) & (log_cm < 14.0)
        if show_c:
            cat_mask |= log_cm >= 14.0
        g_mask &= cat_mask
    return g_mask
