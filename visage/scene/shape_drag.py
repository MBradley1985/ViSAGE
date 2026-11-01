"""Drag a Regions shape in the view: a box, sphere or slice.

The move icon at the shape's centre carries the whole shape (a slice along
its direction only). Dragging a box's face moves that face, and dragging a
sphere's rim changes its radius. What is being dragged lights up. Everything
else goes on to the camera as usual.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pyvista as pv
import vtk

DRAG_COLOUR = "#f1ece2"
_ICON_PX = 18  # the move icon's radius
_RIM_PX = 12  # how near a sphere's rim a press must be
_START_PX = 4  # a press that moves less than this is a click
_MIN_SIZE = 0.1  # Mpc/h


def _icon() -> tuple:
    """The move icon in pixels about its centre: a disc and four arrows."""
    t = np.linspace(0.0, 2.0 * np.pi, 33)[:-1]
    disc = pv.PolyData(
        np.column_stack([_ICON_PX * np.cos(t), _ICON_PX * np.sin(t), 0 * t]),
        faces=np.r_[len(t), np.arange(len(t))],
    )
    pts, lines, tris = [], [], []
    for x, y in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        tip, base = np.array([x, y]) * 13.0, np.array([x, y]) * 8.0
        side = np.array([-y, x]) * 4.0
        n = len(pts)
        pts += [(0, 0), tuple(base), tuple(tip)]
        pts += [tuple(base + side), tuple(base - side)]
        lines += [2, n, n + 1]
        tris += [3, n + 2, n + 3, n + 4]
    arrows = pv.PolyData(
        np.column_stack([np.array(pts, float), np.zeros(len(pts))]),
        lines=np.array(lines),
        faces=np.array(tris),
    )
    return disc, arrows


class ShapeDrag:
    """`on_change(region)` is told each new shape during a drag."""

    def __init__(self, plotter: pv.Plotter, on_change: Callable, push) -> None:
        self._pl = plotter
        self._on_change = on_change
        self._push = push
        self._region: dict | None = None
        self._grab: dict | None = None
        self._tags: list = []
        self._style: tuple = ()
        self._line = None
        self._tint = None
        disc, arrows = _icon()
        self._disc = self._icon_actor(disc, (0.04, 0.05, 0.07), 0.85)
        self._arrows = self._icon_actor(arrows, (1.0, 1.0, 1.0), 1.0)

    def _icon_actor(self, poly, colour, opacity):
        mapper = vtk.vtkPolyDataMapper2D()
        mapper.SetInputData(poly)
        actor = vtk.vtkActor2D()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*colour)
        actor.GetProperty().SetOpacity(opacity)
        actor.GetPositionCoordinate().SetCoordinateSystemToWorld()
        return actor

    # -- The shape -------------------------------------------------------

    def show(self, region: dict) -> None:
        """Draw `region`, ready to drag."""
        if self._region is None:
            iren = self._pl.iren.interactor
            for event, handler in (
                ("LeftButtonPressEvent", self._press),
                ("MouseMoveEvent", self._move),
                ("LeftButtonReleaseEvent", self._release),
            ):
                tag = iren.AddObserver(event, handler, 10.0)
                self._tags.append((tag, iren.GetCommand(tag)))
            style = iren.GetInteractorStyle()
            self._style = (
                style,
                style.AddObserver("StartInteractionEvent", self._keep_mouse),
            )
            self._pl.renderer.AddActor2D(self._disc)
            self._pl.renderer.AddActor2D(self._arrows)
        self._region = region
        self._draw()

    def hide(self) -> None:
        if self._region is None:
            return
        iren = self._pl.iren.interactor
        for tag, _ in self._tags:
            iren.RemoveObserver(tag)
        self._tags.clear()
        self._style[0].RemoveObserver(self._style[1])
        self._region = self._grab = None
        self._pl.renderer.RemoveActor2D(self._disc)
        self._pl.renderer.RemoveActor2D(self._arrows)
        self._drop("_line")
        self._drop("_tint")

    def _drop(self, name: str) -> None:
        if getattr(self, name) is not None:
            self._pl.remove_actor(getattr(self, name), render=False)
            setattr(self, name, None)

    def _centre(self) -> np.ndarray:
        r = self._region
        if r["kind"] == "box":
            return 0.5 * (np.array(r["lo"]) + np.array(r["hi"]))
        return np.array(r["centre" if r["kind"] == "sphere" else "point"])

    def _body(self) -> pv.PolyData:
        """The shape as thin lines."""
        r = self._region
        if r["kind"] == "box":
            (x0, y0, z0), (x1, y1, z1) = r["lo"], r["hi"]
            return pv.Box((x0, x1, y0, y1, z0, z1)).extract_all_edges()
        if r["kind"] == "sphere":
            t = np.linspace(0.0, 2.0 * np.pi, 65)
            c, s = np.cos(t), np.sin(t)
            rings = [(c, s, 0 * t), (c, 0 * t, s), (0 * t, c, s)]
            body = pv.PolyData()
            for ring in rings:
                pts = self._centre() + r["radius"] * np.column_stack(ring)
                body = body.merge(pv.lines_from_points(pts))
            return body
        ring = self._slice_corners()
        return pv.lines_from_points(np.array(ring + ring[:1]))

    def _slice_corners(self) -> list:
        r = self._region
        n = np.array(r["normal"])
        u = np.cross(
            n, (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (1.0, 0.0, 0.0)
        )
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        reach = r["reach"]
        return [
            self._centre() + reach * (a * u + b * v)
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))
        ]

    def _lit(self) -> pv.PolyData | None:
        """The part being dragged, as a surface."""
        g, r = self._grab, self._region
        if g is None or not g["live"]:
            return None
        if r["kind"] == "sphere":
            return pv.Sphere(
                radius=r["radius"],
                center=self._centre(),
                theta_resolution=48,
                phi_resolution=48,
            )
        if r["kind"] == "slice":
            return pv.PolyData(
                np.array(self._slice_corners()), faces=[4, 0, 1, 2, 3]
            )
        lo, hi = np.array(r["lo"], float), np.array(r["hi"], float)
        if g["mode"] == "face":
            axis, side = g["axis"], g["side"]
            lo[axis] = hi[axis] = (hi if side > 0 else lo)[axis]
        (x0, y0, z0), (x1, y1, z1) = lo, hi
        return pv.Box((x0, x1, y0, y1, z0, z1))

    def _draw(self) -> None:
        self._drop("_line")
        self._drop("_tint")
        live = self._grab is not None and self._grab["live"]
        self._line = self._pl.add_mesh(
            self._body(),
            color=DRAG_COLOUR if live else "white",
            opacity=0.9 if live else 0.55,
            line_width=1,
            pickable=False,
            reset_camera=False,
            render=False,
        )
        lit = self._lit()
        if lit is not None:
            self._tint = self._pl.add_mesh(
                lit,
                color=DRAG_COLOUR,
                opacity=0.22,
                lighting=False,
                pickable=False,
                reset_camera=False,
                render=False,
            )
        moving = live and self._grab["mode"] == "move"
        self._arrows.GetProperty().SetColor(
            pv.Color(DRAG_COLOUR).float_rgb if moving else (1.0, 1.0, 1.0)
        )
        centre = self._centre()
        for actor in (self._disc, self._arrows):
            actor.GetPositionCoordinate().SetValue(*centre)

    # -- The view --------------------------------------------------------

    def _screen(self, point) -> np.ndarray:
        ren = self._pl.renderer
        ren.SetWorldPoint(*point, 1.0)
        ren.WorldToDisplay()
        return np.array(ren.GetDisplayPoint()[:2])

    def _ray(self, xy) -> tuple:
        ren = self._pl.renderer
        ends = []
        for depth in (0.0, 1.0):
            ren.SetDisplayPoint(float(xy[0]), float(xy[1]), depth)
            ren.DisplayToWorld()
            w = np.array(ren.GetWorldPoint())
            ends.append(w[:3] / w[3])
        d = ends[1] - ends[0]
        return ends[0], d / np.linalg.norm(d)

    def _on_view_plane(self, xy, through) -> np.ndarray:
        """Where the pointer is, on the view plane through `through`."""
        origin, ray = self._ray(xy)
        forward = np.array(self._pl.camera.direction)
        t = np.dot(through - origin, forward) / np.dot(ray, forward)
        return origin + t * ray

    def _face(self, xy) -> tuple | None:
        """The box face under the pointer, nearest first: (axis, side)."""
        r = self._region
        lo, hi = np.array(r["lo"], float), np.array(r["hi"], float)
        origin, ray = self._ray(xy)
        best, near, far = None, -np.inf, np.inf
        for axis in range(3):
            if abs(ray[axis]) < 1e-12:
                if not lo[axis] <= origin[axis] <= hi[axis]:
                    return None
                continue
            a = (lo[axis] - origin[axis]) / ray[axis]
            b = (hi[axis] - origin[axis]) / ray[axis]
            side = -1 if a < b else 1
            a, b = min(a, b), max(a, b)
            if a > near:
                near, best = a, (axis, side)
            far = min(far, b)
        return best if near <= far else None

    def _px_per_unit(self, point) -> float:
        """Pixels per Mpc/h across the view at `point`."""
        up = np.array(self._pl.camera.up, float)
        up /= np.linalg.norm(up)
        return float(
            np.linalg.norm(self._screen(point + up) - self._screen(point))
        )

    def _target(self, xy) -> dict | None:
        centre = self._centre()
        r = self._region
        if np.linalg.norm(self._screen(centre) - xy) <= _ICON_PX:
            return {"mode": "move", "live": False}
        if r["kind"] == "sphere":
            rim = r["radius"] * self._px_per_unit(centre)
            off = np.linalg.norm(self._screen(centre) - xy) - rim
            if abs(off) <= _RIM_PX:
                return {"mode": "radius", "live": False}
        if r["kind"] == "box":
            face = self._face(xy)
            if face is not None:
                axis, side = face
                return {
                    "mode": "face",
                    "axis": axis,
                    "side": side,
                    "live": False,
                }
        return None

    # -- The mouse -------------------------------------------------------

    def _press(self, iren, _event) -> None:
        xy = np.array(iren.GetEventPosition(), float)
        grab = self._target(xy)
        if grab is None:
            return
        grab["xy"] = xy
        grab["start"] = {
            k: (list(v) if isinstance(v, list) else v)
            for k, v in self._region.items()
        }
        grab["centre"] = self._centre()
        grab["on_plane"] = self._on_view_plane(xy, grab["centre"])
        self._grab = grab
        if grab["mode"] == "move":
            self._tags[0][1].SetAbortFlag(1)

    def _keep_mouse(self, style, _event) -> None:
        """A face or rim press also starts the camera, in case it is a
        click, and the camera would take every later mouse event."""
        if self._grab is not None:
            style.ReleaseFocus()

    def _move(self, iren, _event) -> None:
        g = self._grab
        if g is None:
            return
        self._tags[1][1].SetAbortFlag(1)
        xy = np.array(iren.GetEventPosition(), float)
        if not g["live"]:
            if np.linalg.norm(xy - g["xy"]) < _START_PX:
                return
            g["live"] = True
            # A face was pressed and went on to the camera in case it was
            # a click: take it back.
            if g["mode"] != "move":
                iren.GetInteractorStyle().OnLeftButtonUp()
        self._region = getattr(self, f"_drag_{g['mode']}")(g, xy)
        self._on_change(self._region)
        self._draw()
        self._push()

    def _release(self, _iren, _event) -> None:
        g, self._grab = self._grab, None
        if g is None or not g["live"]:
            return
        self._tags[2][1].SetAbortFlag(1)
        self._draw()
        self._push()

    def _drag_move(self, g, xy) -> dict:
        step = self._on_view_plane(xy, g["centre"]) - g["on_plane"]
        region = dict(g["start"])
        if region["kind"] == "box":
            region["lo"] = (np.array(region["lo"]) + step).tolist()
            region["hi"] = (np.array(region["hi"]) + step).tolist()
        elif region["kind"] == "sphere":
            region["centre"] = (g["centre"] + step).tolist()
        else:
            n = np.array(region["normal"])
            region["point"] = (g["centre"] + n * float(step @ n)).tolist()
        return region

    def _drag_radius(self, g, xy) -> dict:
        at = self._on_view_plane(xy, g["centre"])
        region = dict(g["start"])
        region["radius"] = max(
            _MIN_SIZE, float(np.linalg.norm(at - g["centre"]))
        )
        return region

    def _drag_face(self, g, xy) -> dict:
        axis, side = g["axis"], g["side"]
        lo, hi = np.array(g["start"]["lo"]), np.array(g["start"]["hi"])
        out = np.zeros(3)
        out[axis] = 1.0
        rate = self._px_per_unit(g["centre"])
        along = self._screen(g["centre"] + out) - self._screen(g["centre"])
        # Seen face on, a face has no direction on screen: up is outwards.
        if np.linalg.norm(along) < 0.3 * rate:
            along = np.array([0.0, side * rate])
        step = float((xy - g["xy"]) @ along) / float(along @ along)
        region = dict(g["start"])
        if side > 0:
            hi[axis] = max(hi[axis] + step, lo[axis] + _MIN_SIZE)
        else:
            lo[axis] = min(lo[axis] + step, hi[axis] - _MIN_SIZE)
        region["lo"], region["hi"] = lo.tolist(), hi.tolist()
        return region
