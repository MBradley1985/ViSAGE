"""The selection marker: one ring style for everything selected.

A ring of fixed size on screen around the selected galaxy, with a short
label beside it, and smaller rings around the other members of its group
(merged where they would pile up on screen).
Drawn as a 2D overlay re-projected as each frame starts, so it stays the
same size at any zoom, is never hidden inside a galaxy's glow and never
clipped by the scene's depth range.
"""

from __future__ import annotations

import numpy as np

_TARGET_RGB = (0.13, 0.83, 0.93)  # cyan
_MEMBER_RGB = (0.85, 0.90, 1.00)
_NEAR_RGB = (1.00, 0.75, 0.20)  # amber: where the nearest-galaxy hop goes


def _rings(centers: np.ndarray, radius, n: int = 48):
    """Polylines of circles (display coordinates) as vtkPolyData.
    `radius`: one for all, or one per circle."""
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

    centers = np.asarray(centers, float).reshape(-1, 2)
    k = len(centers)
    poly = vtk.vtkPolyData()
    if k == 0:
        return poly
    r = np.broadcast_to(np.asarray(radius, float), (k,))
    t = np.linspace(0.0, 2.0 * np.pi, n + 1)
    xyz = np.zeros((k, n + 1, 3))
    xyz[..., 0] = centers[:, :1] + r[:, None] * np.cos(t)
    xyz[..., 1] = centers[:, 1:] + r[:, None] * np.sin(t)
    pts = vtk.vtkPoints()
    pts.SetData(numpy_to_vtk(xyz.reshape(-1, 3), deep=True))
    ids = np.arange(k * (n + 1)).reshape(k, n + 1)
    conn = np.hstack([np.full((k, 1), n + 1), ids]).ravel()
    lines = vtk.vtkCellArray()
    lines.SetCells(
        k, numpy_to_vtkIdTypeArray(conn.astype(np.int64), deep=True)
    )
    poly.SetPoints(pts)
    poly.SetLines(lines)
    return poly


def merge_rings(xy: np.ndarray, r: float, avoid=None, avoid_r: float = 0.0):
    """Member rings that would overlap on screen, merged.

    `xy`: ring centres (display pixels), most important first.  Rings
    closer than `r` join into one ring around them all (at most 3r);
    rings inside the `avoid` ring (the selected galaxy's, radius
    `avoid_r`) are left out.  Returns (centres, radii)."""
    xy = np.asarray(xy, float).reshape(-1, 2)
    if avoid is not None and len(xy):
        xy = xy[np.hypot(*(xy - np.asarray(avoid)).T) > avoid_r]
    if len(xy) == 0:
        return np.zeros((0, 2)), np.zeros(0)
    # Cells of size r first (a big cluster has hundreds of members), then
    # the cells' centroids greedily, most important first.
    cell = np.floor(xy / r).astype(np.int64)
    _, first, inv = np.unique(
        cell, axis=0, return_index=True, return_inverse=True
    )
    inv = inv.ravel()
    order = np.argsort(first)  # cells in order of their first member
    groups = [np.flatnonzero(inv == c) for c in order]
    kept: list[list[int]] = []
    kc = np.zeros((0, 2))
    for g in groups:
        c = xy[g].mean(axis=0)
        if len(kc):
            d = np.hypot(*(kc - c).T)
            j = int(np.argmin(d))
            if d[j] < r:
                kept[j].extend(g.tolist())
                kc[j] = xy[kept[j]].mean(axis=0)
                continue
        kept.append(g.tolist())
        kc = np.vstack([kc, c])
    radii = np.array(
        [
            min(r + float(np.hypot(*(xy[m] - kc[j]).T).max()), 3.0 * r)
            for j, m in enumerate(kept)
        ]
    )
    return kc, radii


class SelectionMarker:
    """Target ring + label + member rings, kept in screen space."""

    def __init__(self, plotter):
        self._pl = plotter
        self.target: np.ndarray | None = None
        self.members = np.zeros((0, 3))
        self.near = np.zeros((0, 3))  # the next hops, nearest first
        self.label = ""
        self._actors: dict = {}
        self._observer = None

    # -- public --------------------------------------------------------

    def set_target(self, position) -> None:
        """Ring around world `position` (Mpc/h); label and members kept if
        it is the same place, dropped otherwise."""
        p = np.asarray(position, float)
        if self.target is None or not np.allclose(p, self.target, atol=1e-6):
            self.label = ""
            self.members = np.zeros((0, 3))
            self.near = np.zeros((0, 3))
        self.target = p
        self._ensure()
        self.update()

    def set_details(self, label: str, members=None) -> None:
        self.label = label or ""
        self.members = (
            np.zeros((0, 3))
            if members is None or len(members) == 0
            else np.asarray(members, float)
        )
        self.update()

    def set_near(self, positions=None) -> None:
        """Amber rings on the nearest galaxies (the first, the next hop,
        drawn larger)."""
        self.near = (
            np.zeros((0, 3))
            if positions is None or len(positions) == 0
            else np.asarray(positions, float).reshape(-1, 3)
        )
        self.update()

    def clear(self) -> None:
        self.target = None
        self.label = ""
        self.members = np.zeros((0, 3))
        self.near = np.zeros((0, 3))
        for a in self._actors.values():
            self._pl.renderer.RemoveViewProp(a)
        self._actors = {}
        if self._observer is not None:
            try:
                self._pl.renderer.RemoveObserver(self._observer)
            except Exception:
                pass
            self._observer = None

    @property
    def active(self) -> bool:
        return self.target is not None

    # -- drawing -------------------------------------------------------

    def _ensure(self) -> None:
        import vtk

        if self._actors:
            return
        ren = self._pl.renderer
        for name, rgb, width, opacity in (
            ("target", _TARGET_RGB, 2.5, 1.0),
            ("members", _MEMBER_RGB, 1.5, 0.7),
            ("near", _NEAR_RGB, 1.5, 0.9),
        ):
            mapper = vtk.vtkPolyDataMapper2D()
            mapper.SetInputData(vtk.vtkPolyData())
            actor = vtk.vtkActor2D()
            actor.SetMapper(mapper)
            prop = actor.GetProperty()
            prop.SetColor(*rgb)
            prop.SetLineWidth(width)
            prop.SetOpacity(opacity)
            actor.PickableOff()
            ren.AddViewProp(actor)
            self._actors[name] = actor
        text = vtk.vtkTextActor()
        tp = text.GetTextProperty()
        tp.SetColor(*_TARGET_RGB)
        tp.SetFontSize(15)
        tp.SetBold(True)
        tp.SetShadow(True)
        text.PickableOff()
        ren.AddViewProp(text)
        self._actors["label"] = text
        self._observer = ren.AddObserver("StartEvent", self.update)

    def _project(self, world: np.ndarray):
        """Display (x, y) of world points, and which are in front."""
        ren = self._pl.renderer
        w, h = (max(int(v), 1) for v in ren.GetSize())
        M = ren.GetActiveCamera().GetCompositeProjectionTransformMatrix(
            w / h, -1.0, 1.0
        )
        m = np.array(
            [[M.GetElement(i, j) for j in range(4)] for i in range(4)]
        )
        world = np.asarray(world, float).reshape(-1, 3)
        hom = np.c_[world, np.ones(len(world))] @ m.T
        ok = hom[:, 3] > 0
        ndc = hom[:, :2] / np.where(ok, hom[:, 3], 1.0)[:, None]
        ox, oy = ren.GetOrigin()
        xy = np.c_[
            ox + (ndc[:, 0] + 1) * 0.5 * w, oy + (ndc[:, 1] + 1) * 0.5 * h
        ]
        return xy, ok

    def update(self, *_) -> None:
        if self.target is None or not self._actors:
            return
        h = max(int(self._pl.renderer.GetSize()[1]), 1)
        r_target = max(12.0, h / 45.0)
        xy, ok = self._project(self.target[None, :])
        self._actors["target"].GetMapper().SetInputData(
            _rings(xy[ok], r_target)
        )
        label = self._actors["label"]
        label.SetInput(self.label if ok[0] else "")
        label.SetPosition(xy[0, 0] + 1.2 * r_target, xy[0, 1] + 0.4 * r_target)
        label.GetTextProperty().SetFontSize(int(max(13, h / 60)))
        if len(self.members):
            mxy, mok = self._project(self.members)
            # Rings that would pile up on screen (a group seen from afar)
            # merge; none inside the selected galaxy's own ring.
            centres, radii = merge_rings(
                mxy[mok],
                0.45 * r_target,
                avoid=xy[0] if ok[0] else None,
                avoid_r=0.8 * r_target,
            )
            self._actors["members"].GetMapper().SetInputData(
                _rings(centres, radii)
            )
        else:
            self._actors["members"].GetMapper().SetInputData(
                _rings(np.zeros((0, 2)), 1.0)
            )
        if len(self.near):
            nxy, nok = self._project(self.near)
            r = np.full(len(nxy), 0.55 * r_target)
            r[0] = 0.75 * r_target  # the next hop
            self._actors["near"].GetMapper().SetInputData(
                _rings(nxy[nok], r[nok])
            )
        else:
            self._actors["near"].GetMapper().SetInputData(
                _rings(np.zeros((0, 2)), 1.0)
            )
