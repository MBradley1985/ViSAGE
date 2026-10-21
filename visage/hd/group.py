"""HD mode for a whole halo: a pair, group or cluster.

Every member of the FOF group is drawn at its own position and spin, with
its surroundings: the most massive neighbours outside the group in HD too,
and every other galaxy out to R_WEB as glows, so the group sits at its
node of the cosmic web.  Close pairs raise tidal bridges and tails.  The
most massive ones get the full HD model (at a texture resolution that
falls with rank, as each is small on screen); any long tail of a big
cluster is drawn as soft glows.  All members share one exposure, so their
relative brightness follows stellar mass as in the offline grids
(brightness ~ M^0.35), anchored so the central looks as it does on its
own.  Every member carries its own halo gas (on the Gas button) out to
its own Rvir; only the central carries the intracluster light, and its
Rvir is the group's.

The CPU side of the builds runs in a process pool (many small numpy
operations, which threads can't spread across cores).
"""

from __future__ import annotations

import os

import numpy as np

from visage.hd.layer import HDGalaxyLayer, magnification
from visage.hd.model import (
    CGM_RGB,
    HOT_GAS_RGB,
    OLD_LIGHT,
    SageGalaxy,
    display_sizes,
)

# Light scale for a shared exposure (as scripts/hd_galaxy/grid.py).
M_REF = 3e10
LUM_POWER = 0.35
# Members by stellar-mass rank: the first N_TOP in full quality (all of a
# group of up to N_FULL), then "group" quality up to N_GROUP, "lite" up to
# N_HD; the rest of a big cluster as glows.  Quality over build time (a few
# seconds is fine); GPU memory per full model (~150 MB) sets the limits.
N_FULL = 5
N_TOP = 4
N_GROUP = 16
N_HD = 40
# Surroundings: HD for the N_NEIGH most massive neighbours (M* > M_NEIGH)
# within R_NEIGH; glows for everything within R_WEB (Mpc/h).
R_WEB = 12.0
R_NEIGH = 1.5
N_NEIGH = 16
M_NEIGH = 1e9
# Tidal features: neighbours closer than R_TIDAL (kpc) and at least
# TIDAL_RATIO of the galaxy's mass.
R_TIDAL = 100.0
TIDAL_RATIO = 0.1


def _orbit_sense(entry_a, entry_b, d) -> float:
    """+1 if b orbits a the way a's disk turns (prograde: strong tidal
    tails), -1 if against it (retrograde), from their relative velocity."""
    va = np.asarray(entry_a["gal"].vel, float)
    vb = np.asarray(entry_b["gal"].vel, float)
    spin = entry_a.get("spin")
    if spin is None or not np.any(vb - va):
        return 1.0
    L = np.cross(d, vb - va)
    return 1.0 if float(np.dot(L, spin)) >= 0 else -1.0


# Galaxies flagged to merge before the next snapshot (SAGE mergeType):
# (strength on the merging galaxy, strength on the one it merges into).
MERGE_STRENGTH = {1: (0.75, 0.2), 2: (0.9, 0.9), 4: (1.0, 0.0)}


def tidal_partners(entries, hubble_h: float, max_partners: int = 2):
    """For each entry with an HD build, its tidal partners' (direction,
    distance in Mpc/h, strength, orbit sense).

    Close neighbours (within R_TIDAL) raise features stronger the closer
    and the more massive they are; a galaxy SAGE has merging before the
    next snapshot interacts with the galaxy it merges into (the nearest
    more massive one) at any distance, by merger type.  Prograde
    encounters (orbit turning with the disk) raise stronger tails."""
    hd = [k for k, e in enumerate(entries) if e.get("quality")]
    pos = {k: np.asarray(entries[k]["center"], float) for k in hd}
    found = {k: {} for k in hd}

    def add(ka, kb, strength):
        d = pos[kb] - pos[ka]
        sep = float(np.linalg.norm(d))
        u = d / max(sep, 1e-12)
        sense = _orbit_sense(entries[ka], entries[kb], d)
        strength *= 1.0 if sense > 0 else 0.6
        if strength > found[ka].get(kb, (0, 0, 0, 0))[2]:
            found[ka][kb] = (u, sep, float(strength), sense)

    for ka in hd:
        ma = entries[ka]["gal"].stellar_mass
        for kb in hd:
            if ka == kb:
                continue
            sep_kpc = (
                float(np.linalg.norm(pos[kb] - pos[ka])) * 1000.0 / hubble_h
            )
            ratio = entries[kb]["gal"].stellar_mass / max(ma, 1.0)
            if sep_kpc >= R_TIDAL or ratio < TIDAL_RATIO:
                continue
            strength = float(
                np.clip((R_TIDAL - sep_kpc) / 70.0, 0.0, 1.0)
                * np.clip(np.sqrt(ratio), 0.0, 1.0)
            )
            if strength > 0.1:
                add(ka, kb, strength)
        # A merger about to happen.
        mt = entries[ka]["gal"].merge_type
        if mt in MERGE_STRENGTH:
            heavier = [
                kb
                for kb in hd
                if kb != ka and entries[kb]["gal"].stellar_mass >= ma
            ]
            if heavier:
                kb = min(
                    heavier, key=lambda k: np.linalg.norm(pos[k] - pos[ka])
                )
                s_a, s_b = MERGE_STRENGTH[mt]
                add(ka, kb, s_a)
                if s_b > 0:
                    add(kb, ka, s_b)
    return {
        k: sorted(v.values(), key=lambda x: -x[2])[:max_partners]
        for k, v in found.items()
    }


# Ram pressure: log10(rho_ICM v^2 / (Sigma_* Sigma_gas)) in the units of
# `ram_pressure` -- calibrated on Millennium SAGE26 satellites in hot haloes
# (the strongest ~30 per cent get visible tails).
# log10(ram pressure / restoring force) mapped to a 0-1 tail strength:
# among SAGE26 satellites in hot haloes ~27% get a tail and ~1% a full one.
RAM_LO = -7.8
RAM_SPAN = 2.0


def ram_pressure(
    sat: SageGalaxy, host: SageGalaxy, r_kpc: float, v_kms: float
) -> float:
    """Ram pressure on a satellite's gas against what holds it, as a
    0-1 tail strength: the host's hot gas (an isothermal core profile)
    times the speed squared, over the disk's star x gas surface density."""
    if host.hot_gas <= 0 or sat.cold_gas <= 0 or v_kms <= 0:
        return 0.0
    rc = 0.1 * max(host.rvir_kpc, 20.0)
    rho = host.hot_gas / rc**3 / (1 + (r_kpc / rc) ** 2)
    rd, _, _ = display_sizes(sat)
    restore = sat.stellar_mass * sat.cold_gas / max(rd, 0.1) ** 4
    lam = np.log10(rho * v_kms**2 / max(restore, 1e-30))
    return float(np.clip((lam - RAM_LO) / RAM_SPAN, 0.0, 1.0))


# Cap on a jellyfish tail's exposure compensation.
TAIL_GAIN_MAX = 10.0


def tail_gains(entries, sat_ctx) -> dict:
    """Jellyfish tails dimmed by the group's shared exposure, and by how
    much: {entry index: gain}.  The group draws every member at the
    central's exposure scaled by brightness ~ M*^0.35, which can dim a
    satellite several times next to a bright central; its tail, faint to
    begin with, then vanishes.  The gain brings the tail back to how it
    looks at the satellite's own exposure (built preps needed: it is the
    exact ratio of the two exposures, as show() sets them)."""
    lead = entries[0]
    if not lead.get("prep"):
        return {}
    w_common = lead["prep"]["exposure"].base * display_luminosity(
        lead["gal"], lead["prep"]["rc"].kind
    )
    out = {}
    for k, ctx in sat_ctx.items():
        e = entries[k]
        if "ram" not in ctx or not e.get("prep"):
            continue
        lum = display_luminosity(e["gal"], e["prep"]["rc"].kind)
        f = (w_common / lum) / max(e["prep"]["exposure"].base, 1e-12)
        if f > 1.15:
            out[k] = float(min(f, TAIL_GAIN_MAX))
    return out


def satellite_context(entries, hubble_h: float) -> dict:
    """For satellites of the group's (hot) central: their ram-pressure
    tail and tidal streams, as (world direction, strength)."""
    out: dict = {}
    if not entries:
        return out
    host = entries[0]
    hg = host["gal"]
    hpos = np.asarray(host["center"], float)
    hvel = np.asarray(hg.vel, float)
    for k, e in enumerate(entries[1:], start=1):
        g = e["gal"]
        if not e.get("quality") or g.gtype == 0 or e.get("role") != "member":
            continue
        d = np.asarray(e["center"], float) - hpos
        r_kpc = float(np.linalg.norm(d)) * 1000.0 / hubble_h
        v = np.asarray(g.vel, float) - hvel
        speed = float(np.linalg.norm(v))
        if speed <= 0:
            continue
        vdir = v / speed
        ctx = {}
        if hg.regime == 1:
            st = ram_pressure(g, hg, r_kpc, speed)
            if st > 0.05:
                ctx["ram"] = (-vdir, st)  # the tail trails the motion
        if g.infall_mvir > 0 and g.mvir > 0:
            f_dm = g.mvir / g.infall_mvir
            if f_dm < 0.35:
                ctx["strip"] = (
                    vdir,
                    float(np.clip((0.35 - f_dm) / 0.3, 0.2, 1.0)),
                )
        if ctx:
            out[k] = ctx
    return out


def display_luminosity(gal: SageGalaxy, kind: str) -> float:
    """Relative brightness of a galaxy in a shared exposure."""
    if kind == "disk":
        ref = max(gal.stellar_mass - gal.bulge_mass, 1.0)
    else:
        ref = max(gal.stellar_mass * OLD_LIGHT, 1.0)
    return float((ref / M_REF) ** LUM_POWER)


def plan(gals: list[SageGalaxy]) -> list[str | None]:
    """Build quality for each member (None = drawn as a glow), in the
    order given (the caller sorts by stellar mass, central first)."""
    if len(gals) <= N_FULL:
        return ["full"] * len(gals)
    return [
        (
            "full"
            if i < N_TOP
            else "group" if i < N_GROUP else "lite" if i < N_HD else None
        )
        for i in range(len(gals))
    ]


def prepare_member(
    gal: SageGalaxy, quality: str, context: dict | None = None
) -> dict:
    """Pool worker: the CPU side of one member's build."""
    return HDGalaxyLayer.prepare(gal, quality, context)


_POOL: dict = {"pool": None}


def pool():
    """A lazily started process pool for member builds (spawned workers,
    kept for the session)."""
    if _POOL["pool"] is not None and getattr(_POOL["pool"], "_broken", False):
        _POOL["pool"] = None
    if _POOL["pool"] is None:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor

        n = max(2, min(8, (os.cpu_count() or 4) - 1))
        _POOL["pool"] = ProcessPoolExecutor(
            max_workers=n, mp_context=mp.get_context("spawn")
        )
    return _POOL["pool"]


def _warm_worker() -> int:
    """Pool worker: import the build code (the slow part of a cold start)."""
    import visage.hd.gpu  # noqa: F401
    import visage.hd.layer  # noqa: F401

    return os.getpid()


def warm_pool() -> None:
    """Start the pool's workers now (at app start, in the background), so
    the first HD build doesn't wait for them to spawn and import."""
    ex = pool()
    for _ in range(ex._max_workers):
        ex.submit(_warm_worker)


def _nbytes(obj, seen=None) -> int:
    """Rough memory held by a build (its numpy arrays)."""
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return 0
    seen.add(id(obj))
    if isinstance(obj, np.ndarray):
        return int(obj.nbytes)
    if isinstance(obj, dict):
        return sum(_nbytes(v, seen) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return sum(_nbytes(v, seen) for v in obj)
    if hasattr(obj, "__dict__"):
        return _nbytes(vars(obj), seen)
    return 0


class BuildCache:
    """The last few HD builds' CPU side, so turning HD off and on again (or
    going back to a group seen a moment ago) skips the build.  Least
    recently used first out, within a memory budget; the newest build is
    always kept."""

    def __init__(self, budget_bytes: int):
        from collections import OrderedDict

        self.budget = int(budget_bytes)
        self._items: OrderedDict = OrderedDict()  # key -> (preps, bytes)

    def get(self, key):
        hit = self._items.get(key)
        if hit is None:
            return None
        self._items.move_to_end(key)
        return hit[0]

    def put(self, key, preps) -> None:
        self._items[key] = (preps, _nbytes(preps))
        self._items.move_to_end(key)
        while len(self._items) > 1 and self.nbytes > self.budget:
            self._items.popitem(last=False)

    @property
    def nbytes(self) -> int:
        return sum(b for _, b in self._items.values())

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


def default_cache_budget() -> int:
    """A tenth of the machine's memory, between 0.5 and 3 GB."""
    from visage import system

    total = system.total_memory_bytes() or 8 * 1024**3
    return int(np.clip(total / 10, 0.5 * 1024**3, 3 * 1024**3))


class HDGroupLayer:
    """All members of a group, as HD models plus glows for the tail."""

    def __init__(self, plotter):
        self._pl = plotter
        self.members: list[HDGalaxyLayer] = []  # the group's own
        self.neighbours: list[HDGalaxyLayer] = []  # around it
        self._glow = None
        self._glow_data = None
        self._observer = None
        self._fxaa = None
        self._near_tol = None
        self.center = np.zeros(3)
        self.picks = ([], np.zeros((0, 3)))

    @property
    def active(self) -> bool:
        return any(m.active for m in self.members)

    def show(self, entries, hubble_h: float, gas: bool = False):
        """Draw the group.  `entries`: dicts with gal, center, spin, prep
        (None for a glow), "role" ("member" / "neighbour") and "magnify"
        (bool); the central first."""
        self.clear()
        ren = self._pl.renderer
        self._fxaa = bool(ren.GetUseFXAA())
        ren.SetUseFXAA(False)
        # Let the camera close in on a few-kpc galaxy without the near
        # clipping plane (set by the Rvir-sized gas box) cutting it.
        self._near_tol = ren.GetNearClippingPlaneTolerance()
        ren.SetNearClippingPlaneTolerance(1e-5)
        lead = entries[0]
        k_lead = lead["prep"]["rc"].kind
        # Shared exposure, anchored on the central.
        w_common = lead["prep"]["exposure"].base * display_luminosity(
            lead["gal"], k_lead
        )
        for i, e in enumerate(entries):
            if e["prep"] is None:
                continue
            lay = HDGalaxyLayer(self._pl)
            member = e.get("role", "member") == "member"
            lum = display_luminosity(e["gal"], e["prep"]["rc"].kind)
            mag = (
                magnification(e["gal"], e["prep"]["rc"], hubble_h)
                if e.get("magnify", True)
                else 1.0
            )
            lay.show(
                e["gal"],
                e["center"],
                e["spin"],
                hubble_h,
                gas=gas and member,
                prep=e["prep"],
                white=w_common / lum,
                halo=member,
                icl=i == 0,
                manage_fxaa=False,
                magnify=mag,
            )
            if member:
                self.members.append(lay)
            else:
                self.neighbours.append(lay)
            e["layer"] = lay
        self.center = np.asarray(lead["center"], float)
        self.picks = (
            [e["idx"] for e in entries if e.get("idx") is not None],
            np.array(
                [e["center"] for e in entries if e.get("idx") is not None]
            ),
        )
        self._add_glows(
            entries, hubble_h, display_luminosity(lead["gal"], k_lead)
        )
        self._observer = ren.AddObserver("StartEvent", self._update_glows)
        self._update_glows()

    def _add_glows(self, entries, hubble_h, lum_lead):
        """Every member as a soft glow (size from the size-mass relation,
        colour from sSFR, brightness from mass).  A galaxy smaller than a
        pixel or two would otherwise vanish (its box covers no pixel); the
        glow keeps it in view and fades out as its HD model resolves.  The
        tail of a big cluster is only ever glows."""
        import pyvista as pv

        pos, rad, col, hd = [], [], [], []
        for e in entries:
            g = e["gal"]
            rd, r50e, _ = display_sizes(g)
            disky = g.bt < 0.6
            r_kpc = 1.5 * rd if disky else r50e
            pos.append(np.asarray(e["center"], float))
            rad.append(r_kpc * hubble_h / 1000.0)
            kind = "disk" if disky else "elliptical"
            b = float(
                np.clip(1.2 * display_luminosity(g, kind) / lum_lead, 0.3, 1.0)
            )
            rgb = (
                np.array([0.75, 0.85, 1.0])
                if g.ssfr > 1e-11
                else np.array([1.0, 0.82, 0.6])
            )
            col.append(b * rgb)
            hd.append(e.get("layer"))
        # The web fades out over its outer 30% (no hard edge to the sphere).
        r_lead = np.linalg.norm(np.array(pos) - np.array(pos[0]), axis=1)
        fade = np.clip((R_WEB - r_lead) / (0.3 * R_WEB), 0.0, 1.0)
        col = list(np.array(col) * fade[:, None])
        self._glow_data = {
            "pos": np.array(pos),
            "rad": np.array(rad),
            "rgb": np.array(col, np.float32),
            "hd": hd,
        }
        cloud = pv.PolyData(np.array(pos))
        cloud["rgb"] = np.array(col, np.float32)
        cloud["radius"] = np.array(rad, np.float32)
        a = self._pl.add_mesh(
            cloud,
            scalars="rgb",
            rgb=True,
            style="points_gaussian",
            emissive=True,
            show_scalar_bar=False,
            render=False,
            reset_camera=False,
            pickable=False,
        )
        a.mapper.SetScaleArray("radius")
        a.mapper.SetScaleFactor(1.0)
        self._glow = a
        self._cloud = cloud

    def _update_glows(self, *_):
        """Per frame: each glow at least ~2.5 px across, faded out once the
        member's HD model is ~8 px across."""
        d = self._glow_data
        if d is None or self._glow is None:
            return
        ren = self._pl.renderer
        cam = ren.GetActiveCamera()
        pos = np.array(cam.GetPosition(), float)
        tan_half = np.tan(np.deg2rad(cam.GetViewAngle()) / 2.0)
        pix = 2.0 * tan_half / max(int(ren.GetSize()[1]), 1)
        dist = np.maximum(np.linalg.norm(d["pos"] - pos, axis=1), 1e-6)
        px_world = dist * pix
        rad = np.maximum(d["rad"], 2.5 * px_world)
        w = np.ones(len(rad))
        for k, lay in enumerate(d["hd"]):
            if lay is not None:
                size_px = lay.radius_world / px_world[k]
                w[k] = float(np.clip(1.0 - (size_px - 3.0) / 5.0, 0.0, 1.0))
        self._cloud["radius"] = rad.astype(np.float32)
        self._cloud["rgb"] = (d["rgb"] * w[:, None]).astype(np.float32)

    def clear(self):
        for m in self.members + self.neighbours:
            m.clear()
        self.members = []
        self.neighbours = []
        if self._observer is not None:
            try:
                self._pl.renderer.RemoveObserver(self._observer)
            except Exception:
                pass
            self._observer = None
        if self._glow is not None:
            self._pl.remove_actor(self._glow, render=False)
            self._glow = None
            self._glow_data = None
        if self._fxaa is not None:
            self._pl.renderer.SetUseFXAA(self._fxaa)
            self._fxaa = None
        if self._near_tol is not None:
            self._pl.renderer.SetNearClippingPlaneTolerance(self._near_tol)
            self._near_tol = None

    def set_gas(self, on: bool):
        """Every member's halo gas on or off."""
        for m in self.members:
            m.set_gas(on)

    # -- geometry ------------------------------------------------------

    @property
    def radius_world(self) -> float:
        """Half-width that frames the group, Mpc/h: every member of a pair
        or small group; the central and the inner three quarters of a big
        one's members (outliers, often beyond Rvir, would shrink everything
        else to a few pixels)."""
        if not self.members:
            return 0.0
        r = [
            np.linalg.norm(m._center - self.center) + m.radius_world
            for m in self.members
        ]
        if len(r) <= 10:
            return float(max(r))
        return float(max(r[0], np.percentile(r, 75)))

    def member_at(self, center) -> HDGalaxyLayer | None:
        """The HD galaxy (member or neighbour) at world position `center`."""
        for m in self.members + self.neighbours:
            if np.allclose(m._center, center, atol=1e-6):
                return m
        return None

    @property
    def rvir_world(self) -> float:
        return self.members[0].rvir_world if self.members else 0.0

    @property
    def basis(self) -> np.ndarray:
        """The central's frame (for the 55-degree framing)."""
        return self.members[0]._R
