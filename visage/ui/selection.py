"""The selection: one selected galaxy, everything about it, and moving on.

Whatever sets the Galaxy index -- a double-click in the view, the Target
tab, the Console, Story mode, a click in the group list -- selects that
galaxy, and with it, from the catalogue itself:

* its FOF group (central first, then by stellar mass) and the group's
  host halo: the halo the central sits on (an exact match in SAGE), never
  just the nearest visible one;
* a ring on it and smaller rings on the other members (fixed size on
  screen), and a card in the view with its properties, the group list and
  Go / Isolate / HD / Track.

The selection is the galaxy, not its row in this snapshot: changing
snapshot finds the same galaxy again by its persistent GalaxyIndex (and,
with Track on, moves the camera with it), or says it isn't there.
Typing a halo index selects that halo's central.
"""

from __future__ import annotations

import time

import numpy as np
from trame.widgets import html
from trame.widgets import vuetify3 as v3

# Members listed on the card (the rest are counted).
MAX_LISTED = 30
_DOUBLE_CLICK = 0.45  # s
_PICK_PX = 28.0  # how close (pixels) a double-click must be to a galaxy


def _init_state(state) -> None:
    for k, v in {
        "sel_show": False,
        "sel_title": "",
        "sel_sub": "",
        "sel_props": [],
        "sel_members": [],
        "sel_more": 0,
        "sel_note": "",
        "sel_track": False,
        "sel_info_open": False,
        "sel_info_items": [],
    }.items():
        if not state.has(k):
            state[k] = v


def selection_card(server) -> None:
    """The card (built in the render area's layout)."""
    state, ctrl = server.state, server.controller
    _init_state(state)
    with v3.VCard(
        v_show=("sel_show",),
        classes="sage-popout",
        style=(
            "position:absolute;top:32px;left:24px;"
            "width:300px;max-height:calc(100% - 56px);"
            "display:flex;flex-direction:column;"
            "background:rgba(17,24,39,0.88);backdrop-filter:blur(6px);"
            "border:1px solid #0e7490;color:#e2e8f0;z-index:5;"
        ),
        elevation=8,
    ):
        with html.Div(
            classes="sage-popout-handle",
            style=(
                "display:flex;align-items:flex-start;padding:10px 12px 6px;"
                "cursor:move;user-select:none;flex-shrink:0;"
                "border-bottom:1px solid #1f2937;"
            ),
        ):
            with html.Div(style="flex:1;min-width:0;"):
                html.Div(
                    "{{ sel_title }}",
                    style="font-size:0.95rem;font-weight:700;color:#22d3ee;",
                )
                html.Div(
                    "{{ sel_sub }}",
                    style="font-size:0.75rem;color:#9ca3af;margin-top:2px;",
                )
            v3.VBtn(
                icon="mdi-close",
                size="x-small",
                variant="text",
                click=ctrl.sel_close,
                title="Deselect",
            )
        html.Div(
            "{{ sel_note }}",
            v_show=("sel_note",),
            style=("font-size:0.75rem;color:#fbbf24;padding:6px 12px 0;"),
        )
        # Actions.
        with html.Div(
            style="display:flex;gap:6px;padding:8px 12px;flex-shrink:0;"
        ):
            v3.VBtn(
                "Go",
                size="small",
                variant="outlined",
                color="#FFD700",
                click=ctrl.sel_go,
                title="Fly to it (10 Mpc/h; in HD, to it in close-up)",
            )
            v3.VBtn(
                "Isolate",
                size="small",
                variant=("isolate_active ? 'flat' : 'outlined'",),
                color="cyan",
                click=ctrl.toggle_isolate,
            )
            v3.VBtn(
                "HD",
                size="small",
                variant=("hd_active ? 'flat' : 'outlined'",),
                color=("hd_active ? 'cyan' : '#FFD700'",),
                loading=("hd_building",),
                click=ctrl.toggle_hd,
            )
            v3.VBtn(
                "Track",
                size="small",
                variant=("sel_track ? 'flat' : 'outlined'",),
                color="#a78bfa",
                click="sel_track = !sel_track",
                title="Keep the camera on it as the snapshot changes",
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
                "GROUP",
                v_show=("sel_members.length > 1",),
                style=(
                    "font-size:0.7rem;letter-spacing:0.08em;color:#c084fc;"
                    "margin:10px 0 4px;font-weight:700;"
                ),
            )
            with html.Div(v_show=("sel_members.length > 1",)):
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
                html.Div(
                    "+ {{ sel_more }} more",
                    v_show=("sel_more > 0",),
                    style="font-size:0.72rem;color:#6b7280;padding:2px 6px;",
                )


def _classify(host_mvir: float, n: int) -> str:
    from visage.utils.group_info import _classify

    return _classify(host_mvir, n)


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
        sel.update(
            gid=int(galaxies.galaxy_id[i]) if galaxies.galaxy_id[i] else None,
            idx=i,
            pos=pos,
        )
        if host is not None and host != _int(state.nav_halo_idx):
            sel["halo_echo"] = host
            state.nav_halo_idx = host
        ms = float(galaxies.stellar_mass[i])
        lm = np.log10(max(ms, 1.0))
        is_cen = galaxies.gal_type[i] == 0
        role = "central" if is_cen else "satellite"
        mvir_host = float(halos.masses[host]) if host is not None else 0.0
        kind = _classify(mvir_host, len(mem)) if len(mem) > 1 else "Isolated"
        state.sel_title = f"Galaxy {i}"
        state.sel_sub = f"{role} · log M* {lm:.2f} · {kind}" + (
            f" of {len(mem)}" if len(mem) > 1 else ""
        )
        sfr = float(galaxies.sfr[i])
        props = [
            ("Stellar mass", _fmt(ms, " M☉")),
            ("SFR", f"{sfr:.2f} M☉/yr"),
            ("sSFR", _fmt(float(galaxies.ssfr[i]), " /yr")),
            ("B/T", f"{galaxies.bulge_mass[i] / max(ms, 1.0):.2f}"),
            ("Cold gas", _fmt(float(galaxies.cold_gas[i]), " M☉")),
        ]
        if host is not None:
            props.append(("Host halo", f"{host}  ({_fmt(mvir_host, ' M☉')})"))
        else:
            props.append(("Host halo", "below the halo mass cut"))
        if not is_cen:
            d_kpc = np.linalg.norm(pos - cpos) * 1000.0 / h
            props.append(("From central", f"{d_kpc:.0f} kpc"))
        if sel["gid"] is not None:
            props.append(("GalaxyIndex", str(sel["gid"])))
        state.sel_props = [{"label": a, "value": b} for a, b in props]
        listed = mem[:MAX_LISTED]
        state.sel_members = [
            {
                "idx": int(k),
                "text": (
                    f"{'★ central' if galaxies.gal_type[k] == 0 else 'sat.'}"
                    f" · log M* {np.log10(max(galaxies.stellar_mass[k], 1)):.1f}"
                    f" · {int(k)}"
                ),
                "current": bool(k == i),
            }
            for k in listed
        ]
        state.sel_more = int(max(len(mem) - MAX_LISTED, 0))
        state.sel_note = note
        state.sel_show = True
        if state.sel_info_open:
            _fill_info(i, snap)
        others = [_unwrap(galaxies, int(k), lead) for k in mem if k != i]
        marker = scene.camera.marker
        marker.set_target(pos)
        marker.set_details(f"{i} · {lm:.1f}", others)
        _push()

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
        i = _int(nav_gal_idx)
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
            state.nav_gal_idx = k

    @state.change("snap_num")
    def _on_snap(snap_num=None, **_):
        """Find the same galaxy in the new snapshot."""
        gid = sel.get("gid")
        if gid is None or snap_num is None or not state.sel_show:
            return
        _, galaxies = _snap(int(snap_num))
        hit = np.flatnonzero(galaxies.galaxy_id == gid)
        if len(hit) == 0:
            scene.camera.marker.clear()
            state.sel_note = (
                "Not in this snapshot (not formed yet, or merged into "
                "another galaxy)."
            )
            _push()
            return
        old = sel.get("pos")
        i = int(hit[0])
        _select(i, snap=int(snap_num))
        # (Its row number may differ in this snapshot.)
        if _int(state.nav_gal_idx) != i:
            state.nav_gal_idx = i
        if state.sel_track and old is not None and sel["pos"] is not None:
            cam = scene.plotter.camera
            shift = sel["pos"] - old
            cam.focal_point = tuple(np.asarray(cam.focal_point) + shift)
            cam.position = tuple(np.asarray(cam.position) + shift)
            scene.plotter.renderer.ResetCameraClippingRange()
            _push()

    @ctrl.set("sel_select")
    def _sel_select(idx):
        state.nav_gal_idx = int(idx)
        state.flush()

    @ctrl.set("sel_go")
    def _sel_go():
        if hasattr(ctrl, "go_to_galaxy_enter"):
            ctrl.go_to_galaxy_enter()

    @ctrl.set("sel_close")
    def _sel_close():
        state.sel_show = False
        scene.camera.marker.clear()
        _push()

    @ctrl.set("sel_toggle_info")
    def _sel_toggle_info():
        state.sel_info_open = not bool(state.sel_info_open)
        if state.sel_info_open and sel.get("idx") is not None:
            _fill_info(sel["idx"])

    # -- picking inside HD ---------------------------------------------
    # The catalogue is hidden in HD and the models aren't pickable, so a
    # double-click there picks among the galaxies HD draws (members,
    # neighbours, the web), by their position on screen.
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
