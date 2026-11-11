"""Plane-strain finite-element model of the cradle latch, meshed on a true section of the cradle solid.

Purpose: the beam formulas in holddown.py give the nominal outer-fibre strain; the largest strain actually sits in the
root fillets (or at the neck of the beam), a little above the nominal value.  This module measures that on the real
section: constant-strain triangles, graded Delaunay mesh (fine near the fillets), linear elasticity, plane strain.

    run(cradle_shape)  ->  dict with, for each load case, the hook travel per unit load, the peak principal strain per mm
                           of hook travel in the root zone and in the hook / tab zone, and the mesh size

Load cases (unit loads, results are per mm of hook travel so E drops out of the strains):
    F   horizontal force on the nose (hook pushed back: insertion, over-travel onto the stop ribs)
    M   vertical force on the thumb tab at the press point (release, tab pressed onto its stop)
    V   vertical force up on the nose (retention load)
Boundary: the cut edges of the body in front of and behind the latch are fixed.  The skin under the well spans the
PCB pocket; it is analysed twice, free and held in z by the cradle PCB that is screwed against it, and the larger strain
per mm is reported.
"""
from __future__ import annotations
import math
import numpy as np
import shapely
from shapely.geometry import Point, Polygon, box as sbox
from scipy.spatial import Delaunay, cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
import params as P
import geom as G

M = P.MECH
X_SECTION = 5.2            # between the USB pocket (|x| <= 4.77) and the drain tunnel (x >= 5.7); the tab is 14 mm wide
H_FINE, H_MID, H_COARSE = 0.025, 0.08, 0.22
R_FINE, R_MID = 1.9, 3.6


def _region(cradle_shape, x=X_SECTION):
    sec = G.section_polys(cradle_shape, "x", x, 0.004)
    clip = sbox(P.TAB_STOP_Y0 - 0.6, P.CPCB_Z1 - 0.5, P.WELL_Y1 + M["dam_t"] - 0.05, P.LATCH_TOP_Z + 1.0)
    g = sec.intersection(clip)
    pcs = [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and not p.is_empty]
    probe = Point(0.5 * (P.LATCH_Y_FACE + P.LATCH_Y_BACK1), 2.0)          # a point inside the beam
    for p in pcs:
        if p.contains(probe):
            return p, clip.bounds
    raise RuntimeError("latch section not found")


def _spacing(pts, hot):
    d = cKDTree(hot).query(pts)[0]
    return np.where(d < R_FINE, H_FINE, np.where(d < R_MID, H_MID, H_COARSE))


def _mesh(poly, hot):
    """Graded point cloud (boundary + interior) and its Delaunay triangulation clipped to the polygon."""
    hot = np.asarray(hot, float)
    bpts = []
    for ring in [poly.exterior] + list(poly.interiors):
        c = np.asarray(ring.coords)
        for a, b in zip(c[:-1], c[1:]):
            L = float(np.hypot(*(b - a)))
            if L < 1e-9:
                continue
            h = float(_spacing(np.array([0.5 * (a + b)]), hot)[0])
            n = max(1, int(math.ceil(L / h)))
            for i in range(n):
                bpts.append(a + (b - a) * i / n)
    bpts = np.array(bpts)
    # remove boundary points that crowd each other (fine fillet polylines)
    keep = np.ones(len(bpts), bool)
    tree = cKDTree(bpts)
    hb = _spacing(bpts, hot)
    for i in range(len(bpts)):
        if keep[i]:
            for j in tree.query_ball_point(bpts[i], 0.45 * hb[i]):
                if j > i:
                    keep[j] = False
    bpts = bpts[keep]
    x0, y0, x1, y1 = poly.bounds
    inner = []
    for h, sel in ((H_COARSE, lambda d: d >= R_MID), (H_MID, lambda d: (d >= R_FINE) & (d < R_MID)), (H_FINE, lambda d: d < R_FINE)):
        gx, gy = np.meshgrid(np.arange(x0 + 0.37 * h, x1, h), np.arange(y0 + 0.41 * h, y1, h * 0.866))
        gx[1::2] += 0.5 * h                                                   # staggered rows: near-equilateral triangles
        g = np.c_[gx.ravel(), gy.ravel()]
        d = cKDTree(hot).query(g)[0]
        g = g[sel(d)]
        g = g[shapely.contains_xy(poly, g[:, 0], g[:, 1])]
        if len(g):
            g = g[cKDTree(bpts).query(g)[0] > 0.62 * h]
        inner.append(g)
    pts = np.vstack([bpts] + inner)
    tri = Delaunay(pts, qhull_options="QJ Pp").simplices
    cen = pts[tri].mean(axis=1)
    tri = tri[shapely.contains_xy(poly, cen[:, 0], cen[:, 1])]
    a, b, c = pts[tri[:, 0]], pts[tri[:, 1]], pts[tri[:, 2]]
    area = 0.5 * ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
    flip = area < 0
    tri[flip] = tri[flip][:, [0, 2, 1]]
    area = np.abs(area)
    good = area > 1e-7
    return pts, tri[good], area[good]


def _assemble(pts, tri, area, E, nu):
    """Plane-strain CST stiffness (unit thickness)."""
    x, y = pts[:, 0], pts[:, 1]
    i, j, k = tri[:, 0], tri[:, 1], tri[:, 2]
    bb = np.stack([y[j] - y[k], y[k] - y[i], y[i] - y[j]], axis=1) / (2 * area[:, None])
    cc = np.stack([x[k] - x[j], x[i] - x[k], x[j] - x[i]], axis=1) / (2 * area[:, None])
    B = np.zeros((len(tri), 3, 6))
    B[:, 0, 0::2] = bb; B[:, 1, 1::2] = cc; B[:, 2, 0::2] = cc; B[:, 2, 1::2] = bb
    f = E / ((1 + nu) * (1 - 2 * nu))
    D = f * np.array([[1 - nu, nu, 0], [nu, 1 - nu, 0], [0, 0, (1 - 2 * nu) / 2]])
    Ke = np.einsum("eki,kl,elj->eij", B, D, B) * area[:, None, None]
    dof = np.stack([2 * i, 2 * i + 1, 2 * j, 2 * j + 1, 2 * k, 2 * k + 1], axis=1)
    rows = np.repeat(dof, 6, axis=1).ravel(); cols = np.tile(dof, (1, 6)).ravel()
    K = coo_matrix((Ke.ravel(), (rows, cols)), shape=(2 * len(pts), 2 * len(pts))).tocsr()
    return K, B, dof


def _nodal_principal(B, dof, u, tri, area, n_nodes):
    """Largest principal strain (absolute) at every node: element strains (constant per triangle) averaged onto the
    nodes with the element areas as weights.  The average over the elements round a boundary node is a smoothed surface
    value - it removes the scatter of single sliver elements at the cost of a slightly low peak (a few per cent at the
    mesh size used; see the convergence row in the check report)."""
    e = np.einsum("eki,ei->ek", B, u[dof])                    # exx, eyy, gxy per element
    acc = np.zeros((n_nodes, 3)); wsum = np.zeros(n_nodes)
    for k in range(3):
        np.add.at(acc, tri[:, k], e * area[:, None]); np.add.at(wsum, tri[:, k], area)
    en = acc / np.maximum(wsum, 1e-30)[:, None]
    c = 0.5 * (en[:, 0] + en[:, 1]); r = np.hypot(0.5 * (en[:, 0] - en[:, 1]), 0.5 * en[:, 2])
    return np.maximum(np.abs(c + r), np.abs(c - r))


def run(cradle_shape, E=None, nu=None):
    E = M["pa12_E_MPa"] if E is None else E
    nu = M["pa12_poisson"] if nu is None else nu
    zr = M["latch_root_z"]
    poly, (cy0, cz0, cy1, cz1) = _region(cradle_shape)
    hot = [(P.LATCH_Y_FACE, zr), (P.LATCH_Y_BACK0, zr), (P.LATCH_Y_FACE, P.HOOK_HEEL_Z), (P.LATCH_Y_BACK1, P.TAB_Z0)]
    pts, tri, area = _mesh(poly, hot)
    cen = pts[tri].mean(axis=1)
    tree = cKDTree(pts)
    K, B, dof = _assemble(pts, tri, area, E, nu)
    on = lambda v, t: np.abs(v - t) < 1e-6
    fixed_edges = on(pts[:, 0], cy0) | on(pts[:, 0], cy1)
    ceiling = on(pts[:, 1], P.CPCB_Z1)
    i_nose = int(tree.query([P.HOOK_Y, P.HOOK_Z0 + 0.5 * M["hook_nose_flat"]])[1])
    i_tab = int(tree.query([P.TAB_PRESS_Y, P.LATCH_TOP_Z])[1])
    cases = {"F": (i_nose, (-1.0, 0.0)), "M": (i_tab, (0.0, -1.0)), "V": (i_nose, (0.0, 1.0))}
    px, pz = pts[:, 0], pts[:, 1]
    root_zone = (pz < zr + 2.6) & (pz > zr - 0.6) & (px > P.LATCH_Y_BACK0 - 2.2) & (px < P.LATCH_Y_FACE + 2.2)
    near = lambda i, r: np.hypot(px - pts[i, 0], pz - pts[i, 1]) < r
    hook_zone = (pz > P.HOOK_Z0 - 1.2) & ~(near(i_nose, 0.7) | near(i_tab, 1.0))
    beam_zone = (pz >= zr + 2.6) & (pz <= P.HOOK_Z0 - 1.2) & (px > P.LATCH_Y_BACK1 - 0.05) & (px < P.LATCH_Y_FACE + 0.05)
    out = dict(x_section=X_SECTION, nodes=int(len(pts)), elements=int(len(tri)), h_fine=H_FINE, area_err=float(abs(area.sum() - poly.area) / poly.area))
    for support, extra in (("free", None), ("pcb", ceiling)):
        fix = np.zeros(2 * len(pts), bool)
        fix[0::2] = fixed_edges; fix[1::2] = fixed_edges
        if extra is not None:
            fix[1::2] |= extra
        free = ~fix
        Kff = K[free][:, free].tocsc()
        for name, (node, (fy, fz)) in cases.items():
            f = np.zeros(2 * len(pts)); f[2 * node] = fy; f[2 * node + 1] = fz
            u = np.zeros(2 * len(pts)); u[free] = spsolve(Kff, f[free])
            d = -u[2 * i_nose]                                 # hook travel (backward) per unit load per mm of width
            pm = _nodal_principal(B, dof, u, tri, area, len(pts))
            zr_, zh_, zb_ = np.where(root_zone)[0], np.where(hook_zone)[0], np.where(beam_zone)[0]
            ir, ih, ib = zr_[int(np.argmax(pm[zr_]))], zh_[int(np.argmax(pm[zh_]))], zb_[int(np.argmax(pm[zb_]))]
            out[f"{name}_{support}"] = dict(travel_per_N_mm=float(d), eps_root_per_mm=float(pm[ir] / abs(d)),
                                            eps_hook_per_mm=float(pm[ih] / abs(d)), eps_beam_per_mm=float(pm[ib] / abs(d)),
                                            at_root=tuple(float(v) for v in np.round(pts[ir], 2)), at_hook=tuple(float(v) for v in np.round(pts[ih], 2)),
                                            at_beam=tuple(float(v) for v in np.round(pts[ib], 2)))
    for name in cases:
        a, b = out[f"{name}_free"], out[f"{name}_pcb"]
        worst = a if max(a["eps_root_per_mm"], a["eps_hook_per_mm"], a["eps_beam_per_mm"]) >= max(b["eps_root_per_mm"], b["eps_hook_per_mm"], b["eps_beam_per_mm"]) else b
        peak = max((worst["eps_root_per_mm"], "root fillet", worst["at_root"]), (worst["eps_hook_per_mm"], "hook / tab", worst["at_hook"]),
                   (worst["eps_beam_per_mm"], "beam (neck)", worst["at_beam"]))
        out[name] = dict(eps_root_per_mm=max(a["eps_root_per_mm"], b["eps_root_per_mm"]), eps_hook_per_mm=max(a["eps_hook_per_mm"], b["eps_hook_per_mm"]),
                         eps_beam_per_mm=max(a["eps_beam_per_mm"], b["eps_beam_per_mm"]), eps_per_mm=peak[0], where=peak[1], at=peak[2],
                         stiffness_free_N_mm=float(M["latch_w"] / a["travel_per_N_mm"]) if name != "M" else None,
                         stiffness_pcb_N_mm=float(M["latch_w"] / b["travel_per_N_mm"]) if name != "M" else None)
    return out


if __name__ == "__main__":
    import sys, time, json
    import parts as PT
    t = time.time()
    r = run(PT.cradle().val())
    print(json.dumps(r, indent=1))
    print("beam formula: eps_F %.4f %%/mm, eps_M %.4f %%/mm (thin end), eps_M root %.4f %%/mm; k_F %.2f N/mm" %
          (100 * P.LATCH_BEAM["eps_F"], 100 * P.LATCH_BEAM["eps_M"], 100 * P.LATCH_BEAM["eps_M_root"], M["pa12_E_MPa"] * M["latch_w"] / P.LATCH_BEAM["cw_F"]))
    print(f"{time.time() - t:.1f} s")
