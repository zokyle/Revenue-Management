"""Geometry helpers shared by checks.py and drawings.py.

    section_polys(shape, axis, value)   true planar section (boolean common with a plane face) -> shapely geometry
    section_edges(shape, axis, value)   the same section as typed edges (line / circle / polyline) for DXF export
    hlr(shapes, view)                   hidden-line-removed projection (OCC HLRBRep) -> visible / hidden 2D polylines
    load_stl(path)                      binary STL -> (triangles Nx3x3 float64)
    RayCaster                           exact ray / solid intersection on the B-rep (OCC IntCurvesFace)

2D coordinates of a section on plane  x = c : (y, z);   y = c : (x, z);   z = c : (x, y).
"""
from __future__ import annotations
import math, struct
import numpy as np
import cadquery as cq
from shapely.geometry import Polygon
from shapely.ops import unary_union
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
from OCP.TopAbs import TopAbs_REVERSED

AXI = {"x": 0, "y": 1, "z": 2}
PLANE_2D = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}


def as_shape(obj):
    """cadquery Workplane / PartInfo / Shape -> Shape."""
    if hasattr(obj, "shape") and not isinstance(obj, cq.Shape):
        obj = obj.shape
    if isinstance(obj, cq.Workplane):
        return obj.val()
    return obj


def _plane_face(axis, value, size=600.0):
    n = [0.0, 0.0, 0.0]; n[AXI[axis]] = 1.0
    o = [0.0, 0.0, 0.0]; o[AXI[axis]] = value
    pl = cq.Plane(origin=tuple(o), normal=tuple(n))
    return cq.Face.makeFromWires(cq.Workplane(pl).rect(size, size).val())


def _edge_points(edge, chord_tol=0.002, reverse=False):
    """Sample an edge as a 3D polyline within chord_tol."""
    ad = BRepAdaptor_Curve(edge.wrapped)
    t0, t1 = ad.FirstParameter(), ad.LastParameter()
    typ = ad.GetType()
    if typ == GeomAbs_Line:
        n = 1
    elif typ == GeomAbs_Circle:
        r = ad.Circle().Radius()
        dth = 2 * math.acos(max(-1.0, min(1.0, 1 - chord_tol / max(r, chord_tol))))
        n = max(2, int(math.ceil(abs(t1 - t0) / max(dth, 1e-3))))
    else:
        n = 24
    ts = np.linspace(t0, t1, n + 1)
    pts = [(p.X(), p.Y(), p.Z()) for p in (ad.Value(float(t)) for t in ts)]
    return pts[::-1] if reverse else pts


def _wire_points(wire, chord_tol=0.002):
    exp = BRepTools_WireExplorer(wire.wrapped)
    pts = []
    while exp.More():
        e = cq.Edge(exp.Current())
        seg = _edge_points(e, chord_tol, reverse=(exp.Orientation() == TopAbs_REVERSED))
        pts.extend(seg if not pts else seg[1:])
        exp.Next()
    return pts


def section_faces(shape, axis, value):
    """List of cadquery Faces: the planar section of `shape` on the plane axis = value."""
    sec = as_shape(shape).intersect(_plane_face(axis, value))
    return list(sec.Faces())


def section_polys(shape, axis, value, chord_tol=0.002):
    """Section as a shapely (Multi)Polygon in the plane's 2D coordinates (see module docstring)."""
    i, j = PLANE_2D[axis]
    polys = []
    for f in section_faces(shape, axis, value):
        outer = [(p[i], p[j]) for p in _wire_points(f.outerWire(), chord_tol)]
        holes = [[(p[i], p[j]) for p in _wire_points(w, chord_tol)] for w in f.innerWires()]
        if len(outer) >= 3:
            pg = Polygon(outer, [h for h in holes if len(h) >= 3])
            if not pg.is_valid:
                pg = pg.buffer(0)
            if not pg.is_empty:
                polys.append(pg)
    return unary_union(polys) if polys else Polygon()


def section_edges(shape, axis, value, chord_tol=0.002):
    """Section boundary as typed 2D entities for DXF: ('line', p0, p1) | ('circle', c, r) |
    ('arc', c, r, a0_deg, a1_deg) (counter-clockwise) | ('poly', [pts])."""
    i, j = PLANE_2D[axis]
    out = []
    for f in section_faces(shape, axis, value):
        for e in f.Edges():
            ad = BRepAdaptor_Curve(e.wrapped)
            t0, t1 = ad.FirstParameter(), ad.LastParameter()
            p0, p1 = ad.Value(t0), ad.Value(t1)
            a = ((p0.X(), p0.Y(), p0.Z())[i], (p0.X(), p0.Y(), p0.Z())[j])
            b = ((p1.X(), p1.Y(), p1.Z())[i], (p1.X(), p1.Y(), p1.Z())[j])
            typ = ad.GetType()
            if typ == GeomAbs_Line:
                out.append(("line", a, b))
            elif typ == GeomAbs_Circle:
                c = ad.Circle(); cc = c.Location(); r = c.Radius()
                c2 = ((cc.X(), cc.Y(), cc.Z())[i], (cc.X(), cc.Y(), cc.Z())[j])
                if abs(abs(t1 - t0) - 2 * math.pi) < 1e-9:
                    out.append(("circle", c2, r))
                else:
                    pm = ad.Value(0.5 * (t0 + t1))
                    m = ((pm.X(), pm.Y(), pm.Z())[i], (pm.X(), pm.Y(), pm.Z())[j])
                    a0 = math.degrees(math.atan2(a[1] - c2[1], a[0] - c2[0]))
                    a1 = math.degrees(math.atan2(b[1] - c2[1], b[0] - c2[0]))
                    am = math.degrees(math.atan2(m[1] - c2[1], m[0] - c2[0]))
                    # order so that the arc runs counter-clockwise from a0 to a1 through am
                    if ((am - a0) % 360.0) > ((a1 - a0) % 360.0):
                        a0, a1 = a1, a0
                    out.append(("arc", c2, r, a0, a1))
            else:
                out.append(("poly", [(p[i], p[j]) for p in _edge_points(e, chord_tol)]))
    return out


# ----------------------------------------------------------------------------------------------
# hidden-line projection
# ----------------------------------------------------------------------------------------------
VIEWS = {            # name: (direction from the object TOWARD the viewer, page-x direction); page-y = n x xdir
    "top": ((0, 0, 1), (1, 0, 0)),          # page x = +x, page y = +y
    "bottom": ((0, 0, -1), (-1, 0, 0)),     # seen from below: page x = -x, page y = +y (visor stays up)
    "front": ((0, 1, 0), (-1, 0, 0)),       # seen from the visor side (+y): page x = -x, page y = +z
    "rear": ((0, -1, 0), (1, 0, 0)),        # seen from behind (-y): page x = +x, page y = +z
    "right": ((1, 0, 0), (0, 1, 0)),        # seen from +x: page x = +y, page y = +z
    "left": ((-1, 0, 0), (0, -1, 0)),       # seen from -x: page x = -y, page y = +z
}


def view_xy(view, pts):
    """Project 3D points (N x 3) into the 2D page coordinates of a named view."""
    n, xd = (np.array(v, float) for v in VIEWS[view])
    yd = np.cross(n, xd)
    pts = np.atleast_2d(np.asarray(pts, float))
    return np.stack([pts @ xd, pts @ yd], axis=1)


def hlr(shapes, view, chord_tol=0.01, hidden=True):
    """Exact hidden-line removal. Returns dict(visible=[Nx2 arrays], hidden=[Nx2 arrays]) in page coordinates."""
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
    from OCP.BRepLib import BRepLib
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    n, xd = VIEWS[view]
    algo = HLRBRep_Algo()
    for s in shapes:
        algo.Add(as_shape(s).wrapped)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*n), gp_Dir(*xd))))
    algo.Update(); algo.Hide()
    hs = HLRBRep_HLRToShape(algo)

    def collect(comps):
        lines = []
        for comp in comps:
            if comp is None or comp.IsNull():
                continue
            BRepLib.BuildCurves3d_s(comp)
            ex = TopExp_Explorer(comp, TopAbs_EDGE)
            while ex.More():
                e = cq.Edge(TopoDS.Edge_s(ex.Current()))
                try:
                    p = np.array(_edge_points(e, chord_tol))[:, :2]
                    if len(p) >= 2:
                        lines.append(p)
                except Exception:
                    pass
                ex.Next()
        return lines
    vis = collect([hs.VCompound(), hs.Rg1LineVCompound(), hs.OutLineVCompound()])
    hid = collect([hs.HCompound(), hs.Rg1LineHCompound(), hs.OutLineHCompound()]) if hidden else []
    return dict(visible=vis, hidden=hid)


# ----------------------------------------------------------------------------------------------
# meshes and rays
# ----------------------------------------------------------------------------------------------
def load_stl(path):
    """Binary STL -> triangles (N, 3, 3) float64."""
    data = open(path, "rb").read()
    n = struct.unpack_from("<I", data, 80)[0]
    rec = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n, offset=84)
    return rec["v"].astype(np.float64)


def mesh_volume_area(tris):
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    vol = float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)
    area = float(0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1).sum())
    return vol, area


def mesh_is_closed(tris, decimals=5):
    """True if every edge is shared by exactly two triangles with opposite direction (watertight, consistently oriented)."""
    v = np.round(tris.reshape(-1, 3), decimals)
    _, idx = np.unique(v, axis=0, return_inverse=True)
    f = idx.reshape(-1, 3)
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 2] != f[:, 0])]     # drop degenerate facets (sphere poles)
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    key_fwd = e[:, 0].astype(np.int64) * (idx.max() + 1) + e[:, 1]
    key_rev = e[:, 1].astype(np.int64) * (idx.max() + 1) + e[:, 0]
    return bool(np.array_equal(np.sort(key_fwd), np.sort(key_rev)) and len(np.unique(key_fwd)) == len(key_fwd))


class RayCaster:
    """Exact ray casting against a B-rep solid (OCC IntCurvesFace_ShapeIntersector)."""

    def __init__(self, shape, tol=1e-7):
        from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
        self._i = IntCurvesFace_ShapeIntersector()
        self._i.Load(as_shape(shape).wrapped, tol)

    def first_hit(self, origin, direction, t_min=1e-6, t_max=1e6):
        """Smallest ray parameter t in [t_min, t_max] where the ray meets the shape, or None."""
        from OCP.gp import gp_Lin, gp_Pnt, gp_Dir
        d = np.asarray(direction, float); d = d / np.linalg.norm(d)
        self._i.Perform(gp_Lin(gp_Pnt(*map(float, origin)), gp_Dir(*map(float, d))), float(t_min), float(t_max))
        if not self._i.IsDone() or self._i.NbPnt() == 0:
            return None
        return min(self._i.WParameter(k) for k in range(1, self._i.NbPnt() + 1))

    def blocked(self, origin, direction, t_min=1e-6, t_max=1e6):
        return self.first_hit(origin, direction, t_min, t_max) is not None
