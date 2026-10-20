"""The selection marker: one ring style for everything selected.

A ring of fixed size on screen around the selected galaxy, with a short
label beside it, and smaller rings around the other members of its group.
Drawn as a 2D overlay re-projected as each frame starts, so it stays the
same size at any zoom, is never hidden inside a galaxy's glow and never
clipped by the scene's depth range.
"""

from __future__ import annotations

import numpy as np

_TARGET_RGB = (0.13, 0.83, 0.93)  # cyan
_MEMBER_RGB = (0.85, 0.90, 1.00)


def _rings(centers: np.ndarray, radius: float, n: int = 48):
    """Polylines of circles (display coordinates) as vtkPolyData."""
    import vtk

    pts = vtk.vtkPoints()
    lines = vtk.vtkCellArray()
    t = np.linspace(0.0, 2.0 * np.pi, n + 1)
    for cx, cy in centers:
        ids = []
        for a in t:
            ids.append(
                pts.InsertNextPoint(
                    cx + radius * np.cos(a), cy + radius * np.sin(a), 0.0
                )
            )
        line = vtk.vtkPolyLine()
        line.GetPointIds().SetNumberOfIds(len(ids))
        for k, pid in enumerate(ids):
            line.GetPointIds().SetId(k, pid)
        lines.InsertNextCell(line)
    poly = vtk.vtkPolyData()
    poly.SetPoints(pts)
    poly.SetLines(lines)
    return poly


class SelectionMarker:
    """Target ring + label + member rings, kept in screen space."""

    def __init__(self, plotter):
        self._pl = plotter
        self.target: np.ndarray | None = None
        self.members = np.zeros((0, 3))
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

    def clear(self) -> None:
        self.target = None
        self.label = ""
        self.members = np.zeros((0, 3))
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
        cam = ren.GetActiveCamera()
        pos = np.array(cam.GetPosition())
        fwd = np.array(cam.GetFocalPoint()) - pos
        fwd /= max(np.linalg.norm(fwd), 1e-12)
        out, ok = [], []
        for w in world:
            ren.SetWorldPoint(float(w[0]), float(w[1]), float(w[2]), 1.0)
            ren.WorldToDisplay()
            x, y, _ = ren.GetDisplayPoint()
            out.append((x, y))
            ok.append(float(np.dot(np.asarray(w) - pos, fwd)) > 0)
        return np.array(out).reshape(-1, 2), np.array(ok, bool)

    def update(self, *_) -> None:
        if self.target is None or not self._actors:
            return
        h = max(int(self._pl.renderer.GetSize()[1]), 1)
        r_target = max(12.0, h / 45.0)
        xy, ok = self._project(self.target[None, :])
        if ok[0]:
            self._actors["target"].GetMapper().SetInputData(
                _rings(xy, r_target)
            )
        else:
            self._actors["target"].GetMapper().SetInputData(
                _rings(np.zeros((0, 2)), r_target)
            )
        label = self._actors["label"]
        label.SetInput(self.label if ok[0] else "")
        label.SetPosition(xy[0, 0] + 1.2 * r_target, xy[0, 1] + 0.4 * r_target)
        label.GetTextProperty().SetFontSize(int(max(13, h / 60)))
        if len(self.members):
            mxy, mok = self._project(self.members)
            self._actors["members"].GetMapper().SetInputData(
                _rings(mxy[mok], 0.45 * r_target)
            )
        else:
            self._actors["members"].GetMapper().SetInputData(
                _rings(np.zeros((0, 2)), 1.0)
            )
