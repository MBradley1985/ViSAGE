"""The selection: one selected galaxy, everything about it, and moving on.

Whatever sets the Galaxy index -- a double-click in the view, the Target
tab, the Console, Story mode, a click in the group list -- selects that
galaxy, and with it, from the catalogue itself:

* its FOF group (central first, then by stellar mass) and the group's
  host halo: the halo the central sits on (an exact match in SAGE), never
  just the nearest visible one;
* a ring on it and smaller rings on the other members (fixed size on
  screen), and a card in the view with its properties, the group list and
  Go / Isolate / HD / Gas.

The selection is the galaxy, not its row in this snapshot: changing
snapshot finds the same galaxy again by its persistent GalaxyIndex, or
says it isn't there.
Selecting a halo (Console `go to halo N`) selects that halo's central.
"""

from __future__ import annotations

import time

import numpy as np
from trame.widgets import html
from trame.widgets import vuetify3 as v3

_DOUBLE_CLICK = 0.45  # s
_PICK_PX = 28.0  # how close (pixels) a double-click must be to a galaxy


def _init_state(state) -> None:
    for k, v in {
        "sel_show": False,  # the card is open (Show info)
        "sel_active": False,  # something is selected
        "sel_title": "",
        "sel_sub": "",
        "sel_props": [],
        "sel_members": [],
        "sel_group_props": [],
        # HD's drawing of each member, by row: "HD" / "glow" / "extra".
        "hd_member_tags": {},
        "sel_note": "",
        "sel_info_open": False,
        "sel_info_items": [],
        "sel_rings": True,  # the indicator on (the card's Clear / Show)
        "sel_halo": "",
        "sel_badge": "",
        "sel_group": "",
        "sel_q_gal": "",
        "sel_q_halo": "",
        # What's selected: the galaxy, or its (host) halo with its group.
        "sel_kind": "galaxy",
        "sel_has_halo": False,
        "sel_can_back": False,
        "sel_can_fwd": False,
        "find_preset": None,
        "find_results": [],
        "find_id": "",
        "find_note": "",
        "hd_available": True,
        "hd_unavailable": "",
    }.items():
        if not state.has(k):
            state[k] = v


def selection_card(server) -> None:
    """The card (built in the render area's layout)."""
    state, ctrl = server.state, server.controller
    _init_state(state)
    # Browsing keys (visage.js clicks these): [ ] members, C central,
    # N nearest neighbour, B back, Shift+B forward.
    with html.Div(style="display:none;"):
        for name, fn in (
            ("prev", (ctrl.sel_step, "[-1]")),
            ("next", (ctrl.sel_step, "[1]")),
            ("central", ctrl.sel_central),
            ("nearest", ctrl.sel_nearest),
            ("back", (ctrl.sel_history, "[-1]")),
            ("fwd", (ctrl.sel_history, "[1]")),
        ):
            v3.VBtn("", id=f"sel-key-{name}", click=fn)
    with v3.VCard(
        v_show=("sel_show",),
        id="sel-card",
        classes="sage-popout",
        style=(
            "position:absolute;top:32px;left:24px;"
            "width:330px;max-height:calc(100% - 56px);"
            "display:flex;flex-direction:column;"
            "color:#e2e8f0;z-index:5;"
        ),
        elevation=0,
    ):
        with html.Div(
            classes="sage-popout-handle sel-hero",
            style=(
                "display:flex;align-items:flex-start;padding:16px 12px 8px 16px;"
                "cursor:move;user-select:none;flex-shrink:0;"
            ),
        ):
            with html.Div(style="flex:1;min-width:0;"):
                html.Div(
                    "{{ sel_title }}",
                    style=(
                        "font-size:1.3rem;font-weight:700;color:#fff;"
                        "letter-spacing:-0.01em;overflow-wrap:anywhere;"
                    ),
                )
                html.Div(
                    "{{ sel_sub }}",
                    style="font-size:0.78rem;color:#9ca3af;margin-top:2px;",
                )
                html.Span(
                    "{{ sel_badge }}",
                    v_show=("sel_badge",),
                    classes="sel-badge",
                )
            v3.VBtn(
                icon="mdi-close",
                size="x-small",
                variant="text",
                click=ctrl.sel_close,
                title="Hide (Show info brings it back)",
            )
        html.Div(
            "{{ sel_note }}",
            v_show=("sel_note",),
            style=("font-size:0.75rem;color:#fbbf24;padding:6px 12px 0;"),
        )
        # Galaxy or its halo: what Go, Isolate and Focus act on.
        with html.Div(
            classes="sel-pills", style="padding:6px 16px 0;flex-shrink:0;"
        ):
            with v3.VBtnToggle(
                v_model=("sel_kind",),
                mandatory=True,
                density="compact",
                divided=True,
                variant="outlined",
                color="cyan",
                style="height:26px;",
            ):
                v3.VBtn(
                    "Galaxy",
                    value="galaxy",
                    size="small",
                    style="text-transform:none;",
                )
                v3.VBtn(
                    "Halo + group",
                    value="halo",
                    size="small",
                    disabled=("!sel_has_halo",),
                    style="text-transform:none;",
                )
        # Actions.
        with html.Div(
            classes="sel-actions",
            style=(
                "display:flex;flex-wrap:wrap;gap:6px;padding:8px 16px;"
                "flex-shrink:0;"
            ),
        ):
            v3.VBtn(
                "Go",
                size="small",
                variant="tonal",
                color="cyan",
                click=ctrl.sel_go,
                title="Fly to it (10 Mpc/h; in HD, to it in close-up)",
            )
            v3.VBtn(
                "Isolate",
                size="small",
                variant=("isolate_active ? 'flat' : 'outlined'",),
                color=("isolate_active ? 'cyan' : '#cbd5e1'",),
                click=ctrl.toggle_isolate,
            )
            v3.VBtn(
                "HD",
                size="small",
                variant=("hd_active ? 'flat' : 'outlined'",),
                color=("hd_active ? 'cyan' : '#cbd5e1'",),
                loading=("hd_building",),
                disabled=("!hd_available",),
                click=ctrl.toggle_hd,
                title=("hd_available ? 'HD close-up' : hd_unavailable",),
            )
            v3.VBtn(
                "Gas",
                size="small",
                variant=("hd_gas ? 'flat' : 'outlined'",),
                color=("hd_gas ? '#a3e635' : '#cbd5e1'",),
                click="hd_gas = !hd_gas",
                title="HD halo gas: CGM, hot gas, winds and jets",
            )

        # Moving on: history, the group's members, its central, the nearest
        # galaxy.
        with html.Div(
            style=(
                "display:flex;align-items:center;gap:2px;padding:0 12px 6px;"
                "flex-shrink:0;"
            ),
        ):
            for icon, fn, tip, dis in (
                (
                    "mdi-arrow-left",
                    (ctrl.sel_history, "[-1]"),
                    "Back (B)",
                    "!sel_can_back",
                ),
                (
                    "mdi-arrow-right",
                    (ctrl.sel_history, "[1]"),
                    "Forward (Shift+B)",
                    "!sel_can_fwd",
                ),
                (
                    "mdi-chevron-left",
                    (ctrl.sel_step, "[-1]"),
                    "Previous member of the group ([)",
                    "sel_members.length < 2",
                ),
                (
                    "mdi-chevron-right",
                    (ctrl.sel_step, "[1]"),
                    "Next member of the group (])",
                    "sel_members.length < 2",
                ),
                (
                    "mdi-star-outline",
                    ctrl.sel_central,
                    "Up to the group's central (C)",
                    "sel_members.length < 2",
                ),
                (
                    "mdi-near-me",
                    ctrl.sel_nearest,
                    "Hop to the nearest galaxy (N)",
                    "false",
                ),
            ):
                v3.VBtn(
                    icon=icon,
                    size="x-small",
                    variant="text",
                    color="cyan",
                    click=fn,
                    title=tip,
                    disabled=(dis,),
                )
            # Components: label the HD galaxy's parts (Galaxy context).
            v3.VBtn(
                icon="mdi-help-circle-outline",
                v_show=("hd_active && sel_kind !== 'halo'",),
                size="x-small",
                variant="text",
                color="cyan",
                click="hd_labels_on = !hd_labels_on",
                title="Components: label the parts of this galaxy",
            )
        # Closer zooms (Mpc/h), and the host halo.
        with html.Div(
            style=(
                "display:flex;align-items:center;gap:4px;padding:0 12px 6px;"
                "font-size:0.72rem;color:#9ca3af;flex-shrink:0;"
            ),
        ):
            html.Span("Zoom (Mpc/h)", style="margin-right:4px;")
            for label, fn in (
                ("3", ctrl.go_to_galaxy_1),
                ("5", ctrl.go_to_galaxy_3),
                ("10", ctrl.go_to_galaxy_5),
            ):
                v3.VBtn(
                    label,
                    size="x-small",
                    variant="outlined",
                    color="#cbd5e1",
                    click=fn,
                    style="min-width:0;",
                )
            html.Div(style="flex:1;")
            v3.VBtn(
                "{{ sel_rings ? 'Clear indicator' : 'Show indicator' }}",
                size="x-small",
                variant="text",
                color="#9ca3af",
                click=ctrl.sel_clear_marker,
                title=(
                    "Rings off or on (the galaxy stays selected; stays as "
                    "set through HD, Gas and new selections)"
                ),
            )
        with html.Div(
            v_show=("sel_halo",),
            style=(
                "display:flex;align-items:center;gap:6px;padding:0 12px 8px;"
                "font-size:0.75rem;flex-shrink:0;"
            ),
        ):
            html.Span("{{ sel_halo }}", style="flex:1;color:#c084fc;")
            v3.VBtn(
                "Go to halo",
                size="x-small",
                variant="outlined",
                color="#c084fc",
                click=ctrl.sel_go_halo,
                title="Fly to the host halo (10 Mpc/h standoff)",
            )
        with html.Div(style="overflow-y:auto;padding:0 12px 10px;"):
            # Key properties.
            with html.Div(
                v_for="(p, i) in sel_props",
                key="i",
                style=(
                    "display:flex;justify-content:space-between;"
                    "font-size:0.78rem;padding:2px 0;"
                    "border-bottom:1px solid rgba(55,65,81,0.5);"
                ),
            ):
                html.Span("{{ p.label }}", style="color:#9ca3af;")
                html.Span("{{ p.value }}", style="font-family:monospace;")
            # Every property, on demand.
            v3.VBtn(
                "{{ sel_info_open ? 'Fewer properties' : 'All properties' }}",
                size="x-small",
                variant="text",
                color="cyan",
                click=ctrl.sel_toggle_info,
                style="margin:4px 0;",
            )
            v3.VBtn(
                "Radial profile",
                v_show=("radial_ok",),
                size="x-small",
                variant="text",
                color="cyan",
                click=ctrl.radial_profile,
                style="margin:4px 0;",
            )
            v3.VBtn(
                "Rotation",
                v_show=("rotation_ok",),
                size="x-small",
                variant="text",
                color="cyan",
                click=ctrl.rotation_view,
                title="Stars and gas as line-of-sight velocity maps",
                style="margin:4px 0;",
            )
            with html.Div(v_show=("sel_info_open",)):
                with html.Div(
                    v_for="(p, i) in sel_info_items",
                    key="i",
                    style=(
                        "display:flex;justify-content:space-between;"
                        "font-size:0.72rem;padding:1px 0;gap:8px;"
                    ),
                ):
                    html.Span("{{ p.label }}", style="color:#9ca3af;")
                    html.Span(
                        "{{ p.value }}",
                        style="font-family:monospace;text-align:right;",
                    )
            # The group.
            html.Div(
                "GROUP · {{ sel_group }}",
                v_show=("sel_members.length > 1",),
                style=(
                    "font-size:0.7rem;letter-spacing:0.08em;color:#c084fc;"
                    "margin:10px 0 4px;font-weight:700;"
                ),
            )
            with html.Div(
                v_for="(p, i) in sel_group_props",
                key="i",
                v_show=("sel_members.length > 1 && sel_kind === 'halo'",),
                style=(
                    "display:flex;justify-content:space-between;gap:8px;"
                    "font-size:0.74rem;padding:1px 0;"
                ),
            ):
                html.Span("{{ p.label }}", style="color:#c4b5fd;")
                html.Span(
                    "{{ p.value }}",
                    style="font-family:monospace;text-align:right;",
                )
            # Every member (the card scrolls).
            with html.Div(
                v_show=("sel_members.length > 1",),
                style="margin-top:6px;",
            ):
                with html.Div(
                    v_for="m in sel_members",
                    key="m.idx",
                    click=(ctrl.sel_select, "[m.idx]"),
                    style=(
                        "'font-size:0.76rem;padding:3px 6px;cursor:pointer;"
                        "border-radius:4px;' + (m.current ? "
                        "'background:rgba(34,211,238,0.18);color:#22d3ee;'"
                        " : 'color:#e2e8f0;')",
                    ),
                ):
                    html.Span("{{ m.text }}")
                    html.Span(
                        "{{ hd_member_tags[m.idx] }}",
                        v_show=("hd_active && hd_member_tags[m.idx]",),
                        style=(
                            "float:right;font-size:0.66rem;color:#94a3b8;"
                            "margin-left:6px;"
                        ),
                    )


def build_selection(server, scene) -> None:
    """Selection logic: react to the Galaxy / Halo index and the snapshot."""
    state, ctrl = server.state, server.controller
    _init_state(state)
    sel: dict = {"gid": None, "idx": None, "halo_echo": None, "pos": None}

    def _push():
        if hasattr(ctrl, "view_update"):
            ctrl.view_update()

    def _snap(snap=None):
        model = scene.active_model
        return model.loader.get(model.current_snap if snap is None else snap)

    def _members(galaxies, i: int) -> np.ndarray:
        from visage.utils.group_info import member_indices

        if not np.any(galaxies.central_id):
            return np.array([i], dtype=np.int64)
        idx = member_indices(galaxies, i)
        idx = idx[galaxies.stellar_mass[idx] > 0]
        if i not in idx:
            idx = np.append(idx, i)
        order = np.lexsort(
            (-galaxies.stellar_mass[idx], galaxies.gal_type[idx] != 0)
        )
        return idx[order]

    def _drawn(galaxies, i: int, ref: int) -> np.ndarray:
        """Where galaxy `i` is drawn: its catalogue position in the normal
        view; in HD, its periodic image nearest `ref` (HD lays a group
        straddling the box edge out together)."""
        if state.has("hd_active") and bool(state.hd_active):
            return _unwrap(galaxies, i, ref)
        return (
            np.asarray(galaxies.positions[i], float)
            + scene.active_model.offset
        )

    def _unwrap(galaxies, i: int, ref: int) -> np.ndarray:
        p = np.asarray(galaxies.positions[i], float)
        if not scene.is_lightcone:
            box = float(scene.active_model.box_size)
            c = np.asarray(galaxies.positions[ref], float)
            d = p - c
            p = c + d - box * np.round(d / box)
        return p + scene.active_model.offset

    trees: dict = {}

    def _halo_tree(halos, snap):
        from scipy.spatial import cKDTree

        key = (scene.active_model.name, snap, halos.count)
        if trees.get("key") != key:
            trees["key"] = key
            trees["tree"] = cKDTree(halos.positions)
        return trees["tree"]

    def _host_halo(halos, pos_world, snap):
        """The halo the central sits on (exact in SAGE), or None (e.g.
        below the halo mass cut)."""
        if halos.count == 0:
            return None
        p = np.asarray(pos_world, float) - scene.active_model.offset
        d, h = _halo_tree(halos, snap).query(p)
        return int(h) if d < 2e-3 else None

    def _fmt(x, unit=""):
        return f"{x:.2e}{unit}" if x else "0"

    def _cone_props(galaxies, i: int, props: list) -> list:
        """A lightcone galaxy: where it is, then (with synthetic
        photometry) how it looks and its dust, after its SAGE basics."""
        from visage.utils.galaxy_info import cone_summary

        head = cone_summary(galaxies, i)
        # (Where it is first, its look and dust after the basics.)
        return head[:2] + props + head[2:]

    def _select(i: int, note: str = "", snap=None) -> None:
        snap = scene.active_model.current_snap if snap is None else snap
        halos, galaxies = _snap(snap)
        if not 0 <= i < galaxies.count:
            return
        h = float(scene._cfg.hubble_h)
        mem = _members(galaxies, i)
        lead = int(mem[0])
        pos = _unwrap(galaxies, i, lead)
        cpos = _unwrap(galaxies, lead, lead)
        host = _host_halo(halos, cpos, snap)
        cone = bool(scene.is_lightcone)
        sel.update(
            # (A lightcone repeats galaxies -- the same GalaxyIndex in
            # several tiles -- and is one static catalogue: its rows are
            # the identity.)
            gid=(
                int(galaxies.galaxy_id[i])
                if galaxies.galaxy_id[i] and not cone
                else None
            ),
            idx=i,
            pos=pos,
            mem=mem,
        )
        _remember(sel["gid"], i)
        if host is not None and host != _int(state.nav_halo_idx):
            sel["halo_echo"] = host
            state.nav_halo_idx = host
        ms = float(galaxies.stellar_mass[i])
        lm = np.log10(max(ms, 1.0))
        is_cen = galaxies.gal_type[i] == 0
        role = "central" if is_cen else "satellite"
        from visage.utils.group_info import (
            classify_members,
            galaxy_label,
            halo_label,
            group_summary,
            host_mass,
        )

        mvir_host = (
            float(halos.masses[host])
            if host is not None
            else host_mass(galaxies, mem, h)
        )
        kind = classify_members(galaxies, mem, host_mass(galaxies, mem, h))
        state.sel_badge = kind + (f" of {len(mem)}" if len(mem) > 1 else "")
        halo_name = "" if host is None else halo_label(galaxies, lead, host)
        state.sel_has_halo = host is not None
        halo_ctx = state.sel_kind == "halo" and host is not None
        if state.sel_kind == "halo" and host is None:
            state.sel_kind = "galaxy"
        sel["host"] = host
        if halo_ctx:
            state.sel_title = f"Halo {halo_name}"
            state.sel_sub = f"Central galaxy {galaxy_label(galaxies, lead)}"
        else:
            state.sel_title = f"Galaxy {galaxy_label(galaxies, i)}"
            state.sel_sub = f"{role.title()} · log M* {lm:.2f}"
        sfr = float(galaxies.sfr[i])
        props = [
            ("Stellar mass", _fmt(ms, " M☉")),
            ("SFR", f"{sfr:.2f} M☉/yr"),
            ("sSFR", _fmt(float(galaxies.ssfr[i]), " /yr")),
            ("B/T", f"{galaxies.bulge_mass[i] / max(ms, 1.0):.2f}"),
            ("Cold gas", _fmt(float(galaxies.cold_gas[i]), " M☉")),
            ("ICS", _fmt(float(galaxies.ics_mass[i]), " M☉")),
        ]
        state.sel_halo = (
            f"Host halo {halo_name} · {_fmt(mvir_host, ' M☉')}"
            if host is not None
            else "Host halo below the halo mass cut"
        )
        total = float(galaxies.stellar_mass[mem].sum())
        state.sel_group = (
            f"{kind}, {len(mem)} members · ΣM* {_fmt(total, ' M☉')}"
        )
        if not is_cen:
            d_kpc = np.linalg.norm(pos - cpos) * 1000.0 / h
            props.append(("From central", f"{d_kpc:.0f} kpc"))
        if cone:
            props = _cone_props(galaxies, i, props)
        state.sel_props = [{"label": a, "value": b} for a, b in props]
        state.sel_group_props = [
            {"label": a, "value": b}
            for a, b in (
                group_summary(galaxies, mem, h) if len(mem) > 1 else []
            )
        ]
        listed = mem
        state.sel_members = [
            {
                "idx": int(k),
                "text": (
                    f"{'★ central' if galaxies.gal_type[k] == 0 else 'sat.'}"
                    f" · log M* {np.log10(max(galaxies.stellar_mass[k], 1)):.1f}"
                    f" · {galaxy_label(galaxies, int(k))}"
                ),
                "current": bool(k == i),
            }
            for k in listed
        ]
        if (
            not note
            and cone
            and galaxies.snap_nums is not None
            and galaxies.snap_nums[i] > scene.active_model.current_snap
        ):
            note = "Hidden by the redshift slider's cut."
        state.sel_note = note
        state.sel_active = True  # (the card opens on Show info)
        if state.sel_info_open:
            _fill_info(i, snap)
        marker = scene.camera.marker
        marker.enabled = bool(state.sel_rings)
        if halo_ctx:
            # The halo and its group: every member ringed alike.
            marker.set_target(_drawn(galaxies, lead, lead))
            marker.set_details(
                "",
                [_drawn(galaxies, int(k), lead) for k in mem if k != lead],
                style="full",
            )
        else:
            # The galaxy alone.
            marker.set_target(_drawn(galaxies, i, lead))
            marker.set_details("", [])
        _push()

    # Back / forward through what was selected: (GalaxyIndex, row).
    hist: dict = {"items": [], "pos": -1, "nav": False}

    def _remember(gid, i) -> None:
        here = (gid, i)
        items, pos = hist["items"], hist["pos"]
        same = 0 <= pos < len(items) and (
            items[pos][0] == gid if gid is not None else items[pos] == here
        )
        if same:
            items[pos] = here  # (its row in this snapshot)
        if hist["nav"] or same:
            hist["nav"] = False
            _hist_state()
            return
        del items[pos + 1 :]
        items.append(here)
        del items[: max(len(items) - 50, 0)]
        hist["pos"] = len(items) - 1
        _hist_state()

    def _hist_state() -> None:
        state.sel_can_back = hist["pos"] > 0
        state.sel_can_fwd = hist["pos"] < len(hist["items"]) - 1

    def _go_row(i: int, keep_kind: bool = False) -> None:
        """Select row `i`: as a galaxy, or (`keep_kind`: moving within the
        group) in the card's current Galaxy / Halo + group context."""
        kind = str(state.sel_kind) if keep_kind else "galaxy"
        if _int(state.nav_gal_idx) == i:
            state.sel_kind = kind
            _select(i)
        else:
            sel["kind_next"] = kind
            state.nav_gal_idx = int(i)
        state.flush()

    @ctrl.set("sel_history")
    def _sel_history(step):
        pos = hist["pos"] + int(step)
        if not 0 <= pos < len(hist["items"]):
            return
        gid, i = hist["items"][pos]
        _, galaxies = _snap()
        if gid is not None:
            hit = np.flatnonzero(galaxies.galaxy_id == gid)
            if len(hit) == 0:
                state.sel_note = "That galaxy isn't in this snapshot."
                return
            i = int(hit[0])
        hist["pos"] = pos
        hist["nav"] = True
        _go_row(i)

    @ctrl.set("sel_step")
    def _sel_step(step):
        """The next / previous member of the group."""
        mem, i = sel.get("mem"), sel.get("idx")
        if mem is None or len(mem) < 2 or not state.sel_active:
            return
        k = int(np.flatnonzero(mem == i)[0]) if i in mem else 0
        _go_row(int(mem[(k + int(step)) % len(mem)]), keep_kind=True)
        ctrl.sel_go()  # and fly there

    @ctrl.set("sel_central")
    def _sel_central():
        mem = sel.get("mem")
        if mem is None or not state.sel_active or mem[0] == sel.get("idx"):
            return
        _go_row(int(mem[0]), keep_kind=True)
        ctrl.sel_go()

    near_trees: dict = {}

    def _nearest(i: int, n: int, skip=()) -> list[int]:
        """Rows of the `n` galaxies nearest row `i` (periodic in a box),
        nearest first: visible ones only (the filters and environment
        checkboxes), not `i` nor any in `skip`."""
        from scipy.spatial import cKDTree

        _, galaxies = _snap()
        ok = galaxies.stellar_mass > 0
        mask = getattr(scene.galaxy_layer, "_filter_mask", None)
        if mask is not None and len(mask) == galaxies.count:
            ok = ok & mask
        key = (
            scene.active_model.name,
            scene.active_model.current_snap,
            hash(ok.tobytes()),
        )
        if near_trees.get("key") != key:
            rows = np.flatnonzero(ok)
            p = np.asarray(galaxies.positions[rows], float)
            box = None
            if not scene.is_lightcone:
                box = float(scene.active_model.box_size)
                p = np.mod(p, box)
            near_trees.update(
                key=key,
                rows=rows,
                tree=cKDTree(p, boxsize=box) if len(rows) else None,
                box=box,
            )
        t = near_trees
        if t["tree"] is None:
            return []
        q = np.asarray(galaxies.positions[i], float)
        if t["box"]:
            q = np.mod(q, t["box"])
        want = min(n + len(skip) + 1, len(t["rows"]))
        _, hits = t["tree"].query(q, k=want)
        out = []
        for h in np.atleast_1d(hits):
            if h >= len(t["rows"]):
                continue
            r = int(t["rows"][h])
            if r != i and r not in skip:
                out.append(r)
            if len(out) == n:
                break
        return out

    @ctrl.set("sel_nearest")
    def _sel_nearest():
        """Hop to the nearest galaxy, fly there, and ring the next few
        nearest (amber; the next hop larger).  Hopping again carries on to
        the nearest one not yet visited on this run, so it never just
        bounces back to where it came from."""
        i = sel.get("idx")
        if i is None or not state.sel_active:
            return
        seen = sel.get("hop_seen") if sel.get("hop_at") == i else None
        seen = set(seen or ()) | {i}
        nxt = _nearest(i, 1, seen)
        if not nxt:
            return
        j = nxt[0]
        _go_row(j)
        seen.add(j)
        sel["hop_seen"], sel["hop_at"] = seen, j
        if hasattr(ctrl, "sel_go"):
            ctrl.sel_go()
        _, galaxies = _snap()
        near = _nearest(j, 5, seen)
        scene.camera.marker.set_near([_drawn(galaxies, k, j) for k in near])
        _push()

    # -- Find -----------------------------------------------------------

    def _find(preset=None) -> None:
        from visage.utils.find import find

        preset = preset or state.find_preset
        if not preset or preset == "id":
            state.find_results = []
            state.find_note = ""
            return
        _, galaxies = _snap()
        box = (
            None if scene.is_lightcone else float(scene.active_model.box_size)
        )
        res = find(galaxies, preset, box=box)
        state.find_results = res
        state.find_note = (
            ""
            if res
            else (
                "None in this lightcone."
                if scene.is_lightcone
                else "None in this snapshot."
            )
        )

    @state.change("find_preset")
    def _on_find_preset(find_preset=None, **_):
        _find(find_preset)

    @ctrl.set("find_id_go")
    def _find_id_go():
        """Fly to the galaxy with the GalaxyIndex in Find's box."""
        typed = str(state.find_id or "").strip()
        row = _row_for_id(typed) if typed.isdigit() else None
        if row is None:
            state.find_note = f"No galaxy with ID {typed} here."
            return
        state.find_note = ""
        _find_select(row)

    @ctrl.set("find_select")
    def _find_select(idx):
        """A Find result clicked: select it and fly there."""
        _go_row(int(idx))
        if hasattr(ctrl, "sel_go"):
            ctrl.sel_go()

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def _fill_info(i: int, snap=None) -> None:
        from visage.utils.galaxy_info import build_galaxy_info

        _, galaxies = _snap(snap)
        info = build_galaxy_info(
            galaxies=galaxies,
            fields_available=scene.active_model.fields_available,
            idx=i,
            snap_table=scene._snap_table,
            hubble_h=scene._cfg.hubble_h,
        )
        state.sel_info_items = [
            {"label": k, "value": v} for k, v in info.items()
        ]

    @state.change("nav_gal_idx")
    def _on_gal(nav_gal_idx=None, **_):
        # A galaxy picked (double-click, the group list...) is a galaxy
        # selection, unless it came from selecting a halo.
        state.sel_kind = sel.pop("kind_next", "galaxy")
        i = _int(nav_gal_idx)
        if sel.pop("echo", None) == i:
            return  # set by the snapshot follow, already selected
        if i is not None and i >= 0:
            _select(i)

    @state.change("nav_halo_idx")
    def _on_halo(nav_halo_idx=None, **_):
        """A halo index typed or picked: select the galaxy at its centre."""
        h = _int(nav_halo_idx)
        if h is None or h < 0 or h == sel.get("halo_echo"):
            return
        halos, galaxies = _snap()
        if not h < halos.count or galaxies.count == 0:
            return
        hp = np.asarray(halos.positions[h], float)
        d = np.linalg.norm(galaxies.positions - hp, axis=1)
        k = int(np.argmin(d))
        if d[k] < 2e-3:
            sel["halo_echo"] = h
            if _int(state.nav_gal_idx) == k:
                state.sel_kind = "halo"
                _select(k)
            else:
                sel["kind_next"] = "halo"
                state.nav_gal_idx = k

    @state.change("snap_num")
    def _on_snap(snap_num=None, **_):
        """Find the same galaxy in the new snapshot."""
        if state.find_preset:
            _find()
        gid = sel.get("gid")
        if snap_num is None or not state.sel_active:
            return
        if scene.is_lightcone:
            # The slider only cuts the (static) cone: the selection stays.
            if sel.get("idx") is not None:
                _select(sel["idx"])
            return
        if gid is None:
            # No GalaxyIndex in the catalogue: rows mean nothing across
            # snapshots, so the selection ends here.
            _sel_reset()
            return
        _, galaxies = _snap(int(snap_num))
        hit = np.flatnonzero(galaxies.galaxy_id == gid)
        if len(hit) == 0:
            # Kept (by GalaxyIndex) for a snapshot it is in, but nothing
            # here acts on a row that is now another galaxy.
            scene.camera.marker.clear()
            sel.update(idx=None, mem=None)
            if state.nav_gal_idx is not None:
                sel["echo"] = None
                state.nav_gal_idx = None
            state.sel_note = (
                "Not in this snapshot (not formed yet, or merged into "
                "another galaxy)."
            )
            _push()
            return
        i = int(hit[0])
        _select(i, snap=int(snap_num))
        # (Its row number may differ in this snapshot; the galaxy / halo
        # context carries over.)
        if _int(state.nav_gal_idx) != i:
            sel["kind_next"] = state.sel_kind
            sel["echo"] = i
            state.nav_gal_idx = i

    @ctrl.set("sel_reset")
    def _sel_reset(*_):
        """Nothing selected (the model or box changed: rows and indices
        refer to another catalogue)."""
        scene.camera.marker.clear()
        sel.update(gid=None, idx=None, mem=None, pos=None, host=None)
        sel.pop("hop_seen", None)
        hist.update(items=[], pos=-1, nav=False)
        _hist_state()
        state.sel_active = False
        state.sel_show = False
        state.sel_note = ""
        if state.nav_gal_idx is not None:
            sel["echo"] = None
            state.nav_gal_idx = None
        if state.find_preset:
            _find()
        _push()

    scene.register_model_change_callback(_sel_reset)

    @state.change("hd_active")
    def _on_hd(**_):
        # HD lays a group out round its central: the rings follow.
        if state.sel_active and sel.get("idx") is not None:
            _select(sel["idx"])

    @ctrl.set("sel_refresh")
    def _sel_refresh():
        i = _int(state.nav_gal_idx)
        if i is not None and i >= 0:
            _select(i)

    @ctrl.set("show_galaxy_info")
    def _show_galaxy_info():
        """The card, with every property open."""
        state.sel_info_open = True
        _sel_refresh()
        state.sel_show = bool(state.sel_active)

    @ctrl.set("show_group_info")
    def _show_group_info():
        _sel_refresh()
        state.sel_show = bool(state.sel_active)

    @ctrl.set("sel_query")
    def _sel_query(kind):
        """Select by a typed Galaxy or Halo index."""
        key = "sel_q_gal" if kind == "galaxy" else "sel_q_halo"
        k = _int(str(state[key]).strip())
        if k is None or k < 0:
            return
        if kind == "galaxy":
            # (Typed as SAGE's GalaxyIndex.)
            k = _row_for_id(k)
            if k is None:
                state.sel_note = "No galaxy with that GalaxyIndex here."
                return
            if _int(state.nav_gal_idx) == k:
                _sel_refresh()
            state.nav_gal_idx = k
        else:
            # (Typed as SimulationHaloIndex.)
            k = _halo_row_for_id(k)
            if k is None:
                state.sel_note = "No halo with that number here."
                return
            sel["halo_echo"] = None
            if _int(state.nav_halo_idx) == k:
                _on_halo(nav_halo_idx=k)
            state.nav_halo_idx = k
        state.flush()

    @ctrl.set("halo_row_for_id")
    def _halo_row_for_id(number):
        """The loaded row of halo `number` (None if not here), or `number`
        itself for a catalogue without SimulationHaloIndex."""
        from visage.utils.group_info import central_of_halo, halo_ids

        halos, galaxies = _snap()
        if halo_ids(galaxies) is None:
            return number
        row = central_of_halo(galaxies, number)
        if row is None:
            return None
        pos = galaxies.positions[row] + scene.active_model.offset
        return _host_halo(halos, pos, scene.active_model.current_snap)

    def _row_for_id(gid):
        from visage.utils.group_info import row_for_galaxy_index

        _, galaxies = _snap()
        return row_for_galaxy_index(galaxies, int(gid))

    @ctrl.set("galaxy_row_for_id")
    def _galaxy_row_for_id(gid):
        """The loaded row of GalaxyIndex `gid` (None if not here)."""
        return _row_for_id(gid)

    @ctrl.set("sel_select")
    def _sel_select(idx):
        """A member clicked in the card's group list: select it and fly
        there."""
        _go_row(int(idx), keep_kind=True)
        ctrl.sel_go()

    @ctrl.set("sel_go")
    def _sel_go():
        """Fly to what's selected: the galaxy (+-10 kpc), or its halo with
        the whole group -- framed as Isolate frames it."""
        ctrl.go_to_galaxy_enter()

    @ctrl.set("sel_go_halo")
    def _sel_go_halo():
        """Select the halo (with its group) and fly to it."""
        state.sel_kind = "halo"
        state.flush()
        _sel_refresh()
        ctrl.go_to_galaxy_enter()

    @state.change("sel_kind")
    def _on_kind(**_):
        i = sel.get("idx")
        if i is not None and state.sel_active:
            _select(i)

    @ctrl.set("sel_close")
    def _sel_close():
        """Hide the card (the selection stays)."""
        state.sel_show = False
        _push()

    @ctrl.set("sel_toggle_card")
    def _sel_toggle_card():
        """Show info / Hide info (the header's i button and the
        Structure tab's button)."""
        if not state.sel_active:
            state.notice_text = "Double-click a galaxy to select it first."
            state.notice_color = "info"
            state.notice_show = True
            return
        state.sel_show = not bool(state.sel_show)
        _push()

    @ctrl.set("sel_clear_marker")
    def _sel_clear_marker():
        """Rings off (or back on); the selection and its card stay, and
        the choice holds through HD, Gas and new selections."""
        state.sel_rings = not bool(state.sel_rings)
        scene.camera.marker.set_enabled(state.sel_rings)
        _push()

    @ctrl.set("sel_toggle_info")
    def _sel_toggle_info():
        state.sel_info_open = not bool(state.sel_info_open)
        if state.sel_info_open and sel.get("idx") is not None:
            _fill_info(sel["idx"])

    # -- picking inside HD ---------------------------------------------
    # The catalogue is hidden in HD and the models aren't pickable, so a
    # double-click there picks among the galaxies HD draws (members,
    # the group's members), by their position on screen.
    clicks = {"t": 0.0, "xy": (0, 0)}

    def _hd_pick(obj, _ev):
        if not bool(state.hd_active):
            return
        x, y = obj.GetEventPosition()
        now = time.monotonic()
        first = (
            now - clicks["t"] > _DOUBLE_CLICK
            or abs(x - clicks["xy"][0]) + abs(y - clicks["xy"][1]) > 6
        )
        clicks.update(t=0.0 if not first else now, xy=(x, y))
        if first:
            return
        hd = getattr(ctrl, "hd_pick_candidates", None)
        cand = hd() if hd else None
        if not cand:
            return
        idx, pos = cand
        ren = scene.plotter.renderer
        cam = ren.GetActiveCamera()
        cpos = np.array(cam.GetPosition())
        fwd = np.array(cam.GetFocalPoint()) - cpos
        _, galaxies = _snap()
        best, best_d, close = None, _PICK_PX**2, []
        for k, w in zip(idx, pos, strict=True):
            if np.dot(w - cpos, fwd) <= 0:
                continue
            ren.SetWorldPoint(float(w[0]), float(w[1]), float(w[2]), 1.0)
            ren.WorldToDisplay()
            dx, dy, _ = ren.GetDisplayPoint()
            d2 = (dx - x) ** 2 + (dy - y) ** 2
            if d2 < 12.0**2:
                close.append(k)
            if d2 < best_d:
                best, best_d = k, d2
        # Under the cursor, the most massive wins (not a dwarf in front).
        if close:
            best = max(close, key=lambda k: galaxies.stellar_mass[k])
        if best is not None:
            state.nav_gal_idx = int(best)
            state.flush()

    iren = getattr(scene.plotter, "iren", None)
    if iren is not None and getattr(iren, "interactor", None) is not None:
        iren.interactor.AddObserver("LeftButtonPressEvent", _hd_pick)
