"""GreenLine GL-1 parts.  One function per part, each returning a CadQuery Workplane holding one
solid (or a compound for multi-body reference parts) in the assembly frame (see params.py).

Printed parts: tub(), cradle() (with its fixed lip and sprung latch), baffle_ring() and - in the alternative build - the
PA12 base_plate().  Rev D: the primary base plate is routed FR-4.  base_plate(), pcb_adhesive(), seal_bead(), ball_epoxy()
and grain_potting() follow the ACTIVE base variant of params (params.base_variant).  Everything else is a purchased /
reference part modelled as a simple envelope solid for fit, clearance and optical checks.
"""
from __future__ import annotations
import math
import cadquery as cq
from shapely.geometry import LineString
import params as P

M = P.MECH
EPS = 0.2          # overlap used when a positive feature is fused into a wall / roof


# ----------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------
def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cyl(x, y, r, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)


def dprism(r, flat_y, z0, z1):
    """D-shaped prism: circle of radius r clipped at y <= flat_y."""
    return cyl(0, 0, r, z0, z1).intersect(box(-r - 1, r + 1, -r - 1, flat_y, z0 - 1, z1 + 1))


def poly_prism(pts, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).polyline(pts).close().extrude(z1 - z0)


def union(items):
    out = items[0]
    for it in items[1:]:
        out = out.union(it)
    return out


def mirror_x(wp):
    return wp.mirror("YZ")


def prism_x(pts_yz, x0, x1):
    """Prism along x with the cross-section pts_yz (list of (y, z))."""
    return cq.Workplane("YZ").polyline(pts_yz).close().extrude(x1 - x0).translate((x0, 0, 0))


def prism_y(pts_xz, y0, y1):
    """Prism along y with the cross-section pts_xz (list of (x, z))."""
    return cq.Workplane("ZX").polyline([(z, x) for x, z in pts_xz]).close().extrude(y1 - y0).translate((0, y0, 0))


def _xbar(y, z, r, x0, x1):
    """Cylinder of radius r along x through (y, z)."""
    return cq.Workplane("YZ").center(y, z).circle(r).extrude(x1 - x0).translate((x0, 0, 0))


def _fillet_x(corner, u1, u2, r, x0, x1):
    """Concave fillet of radius r in the corner `corner` (y, z) between two faces that leave it along the unit
    directions u1 and u2 (the air wedge lies between them): material to ADD, as a prism along x."""
    c = (u1[0] * u2[0] + u1[1] * u2[1])
    half = 0.5 * math.acos(max(-1.0, min(1.0, c)))
    t = r / math.tan(half)                               # tangent length along each face
    bis = (u1[0] + u2[0], u1[1] + u2[1]); n = math.hypot(*bis)
    cen = (corner[0] + bis[0] / n * r / math.sin(half), corner[1] + bis[1] / n * r / math.sin(half))
    e = 0.02                                             # the filler reaches a little into both faces so that the fuse is clean
    b1 = (-u1[1], u1[0]); b2 = (-u2[1], u2[0])
    if b1[0] * u2[0] + b1[1] * u2[1] > 0:                # make b1, b2 point away from the air wedge (into the material)
        b1 = (-b1[0], -b1[1])
    if b2[0] * u1[0] + b2[1] * u1[1] > 0:
        b2 = (-b2[0], -b2[1])
    p1 = (corner[0] + u1[0] * t, corner[1] + u1[1] * t); p2 = (corner[0] + u2[0] * t, corner[1] + u2[1] * t)
    pts = [(p1[0] + b1[0] * e, p1[1] + b1[1] * e), p1, p2, (p2[0] + b2[0] * e, p2[1] + b2[1] * e),
           (corner[0] + (b1[0] + b2[0]) * e, corner[1] + (b1[1] + b2[1]) * e)]
    return prism_x(pts, x0, x1).cut(_xbar(cen[0], cen[1], r, x0 - 1, x1 + 1))


# ----------------------------------------------------------------------------------------------
# 1. TUB (top shell) - printed, MJF PA12
# ----------------------------------------------------------------------------------------------
def _tub_outer():
    """Outer body of the tub.  The side wall starts at RIM_Z (rim relief): the base plate and the ball feet are the
    lowest surfaces of the marker."""
    f, c = M["top_fillet"], M["bottom_chamfer"]
    R, T, z0 = P.R_OUT, P.T, P.RIM_Z
    k = f * (1 - math.sqrt(0.5))
    prof = (cq.Workplane("XZ").moveTo(0, z0).lineTo(R - c, z0).lineTo(R, z0 + c).lineTo(R, T - f)
            .threePointArc((R - k, T - k), (R - f, T)).lineTo(0, T).close())
    body = prof.revolve(360, (0, 0, 0), (0, 1, 0))
    return body.intersect(box(-R - 1, R + 1, -R - 1, P.Y_VISOR, -1, T + 1))   # flat visor face, sharp edges


def marker_envelope():
    """Outer envelope of the assembled marker (tub body + base plate), for outline drawings."""
    return _tub_outer().union(dprism(P.BASE_R, P.BASE_FLAT, 0.0, P.RIM_Z + EPS))


def _horn_cuts(z0, z1):
    """Wall ends below the visor: cut on the radial plane through the outer D corner (removes the feather edge; the
    wall end face is a full 1.0 mm wide)."""
    out = []
    k = (P.R_OUT + 3.0) / P.R_OUT
    for sx in (1, -1):
        pts = [(sx * P.HORN_X_IN, P.HORN_Y_IN), (sx * P.HORN_X_OUT * k, P.Y_VISOR * k),
               (sx * (P.HORN_X_IN - 3.0), P.Y_VISOR * k), (sx * (P.HORN_X_IN - 3.0), P.HORN_Y_IN)]
        out.append(poly_prism(pts, z0, z1))
    return out


def _hood_positive(cx):
    """Prism bay / light baffle for the camera at x = cx (solid before the bay is hollowed)."""
    s = 1 if cx > 0 else -1
    xo0, xo1 = cx - P.HOOD_OUT_HW, cx + P.HOOD_OUT_HW
    xi0, xi1 = cx - P.HOOD_IN_HW, cx + P.HOOD_IN_HW
    zs, zc, zr = M["hood_skirt_z0"], P.HOOD_Z_OVER_CUBE, P.ROOF_Z + EPS
    yw = P.Y_VISOR_IN + EPS
    items = [
        box(xo0, xo1, P.HOOD_REAR_Y0, yw, zc, zr),                 # block over the cube (hollowed later)
        box(xo0, xi0, P.HOOD_REAR_Y0, yw, zs, zc + EPS),           # skirt walls beside the cube
        box(xi1, xo1, P.HOOD_REAR_Y0, yw, zs, zc + EPS),
        box(xi0 - EPS, xi1 + EPS, P.HOOD_PAD_Y, yw, zs, zc + EPS), # pad in front of the cube
    ]
    # corner fill between the outer skirt and the tub wall (avoids a tapering crevice)
    xa, xb = sorted((s * (abs(cx) + P.HOOD_OUT_HW - EPS), s * (P.R_IN + 0.5)))
    fill = box(xa, xb, P.HOOD_FILL_Y0, yw, zs, zr).intersect(cyl(0, 0, P.R_IN + 0.5, zs - 1, zr + 1))
    items.append(fill)
    return union(items)


def _hood_negative(cx):
    xi0, xi1 = cx - P.HOOD_IN_HW, cx + P.HOOD_IN_HW
    zs = M["hood_skirt_z0"]
    # prism bay: from the rear wall straight to the floor of the window recess (no bevel: the light bundle is narrower
    # inside the wall than at the aperture, and a wider bay would leave the hood keep-out zone of the YAML)
    bay = box(xi0, xi1, P.HOOD_REAR_Y1, P.WIN_RECESS_FLOOR_Y + 0.05, P.HOOD_Z_OVER_CUBE, P.ROOF_Z)
    a = P.OPEN_HALF_W                 # below the bay roof line the opening continues down to the sill, over the front pad
    sill = box(cx - a, cx + a, P.HOOD_PAD_Y - 0.05, P.WIN_RECESS_FLOOR_Y + 0.05, P.OPEN_Z0, P.HOOD_Z_OVER_CUBE + 0.05)
    recess = box(cx - P.WIN_RECESS_W / 2, cx + P.WIN_RECESS_W / 2, P.WIN_RECESS_FLOOR_Y, P.Y_VISOR + 1,
                 P.WIN_Z0, P.T + 1)
    out = bay.union(sill).union(recess)
    c = P.HOOD_REAR_CHAMFER           # 45 deg chamfer on the rear wall's bottom front edge (parallel to the hypotenuse)
    if c > 0:
        y1, zc, e = P.HOOD_REAR_Y1, P.HOOD_Z_OVER_CUBE, 0.05
        out = out.union(prism_x([(y1 - c - e, zc - e), (y1 + e, zc - e), (y1 + e, zc + c + e)], xi0, xi1))
    c, e = M["hood_leadin"], 0.05     # lead-in chamfers at the mouth of the hood (the cube and the prism enter here blind)
    if c > 0:
        out = out.union(prism_y([(xi0 - c - e, zs - e), (xi0 + e, zs - e), (xi0 + e, zs + c + e)], P.HOOD_REAR_Y0 - e, P.HOOD_PAD_Y + e))
        out = out.union(prism_y([(xi1 + c + e, zs - e), (xi1 - e, zs - e), (xi1 - e, zs + c + e)], P.HOOD_REAR_Y0 - e, P.HOOD_PAD_Y + e))
        cp = P.HOOD_PAD_LEADIN
        pad = prism_x([(P.HOOD_PAD_Y - e, zs - e), (P.HOOD_PAD_Y + cp + e, zs - e), (P.HOOD_PAD_Y - e, zs + cp + e)], xi0 - c, xi1 + c)
        out = out.union(pad.intersect(box(xi0 - c - 1, xi1 + c + 1, P.HOOD_PAD_Y - 1, P.Y_VISOR_IN, zs - 1, zs + 1)))
    return out


def tub():
    R, T = P.R_OUT, P.T
    shell = _tub_outer()
    # main cavity above the seal plane (D profile) and the lower cavity that lets the base pass
    shell = shell.cut(dprism(P.R_IN, P.Y_VISOR_IN, P.LEDGE_Z0, P.ROOF_Z))
    shell = shell.cut(cyl(0, 0, P.R_IN, -1, P.LEDGE_Z0))             # open to the front below the visor wall
    for n in _horn_cuts(-1, P.LEDGE_Z0):
        shell = shell.cut(n)

    pos = []
    # seating ledge on the arc
    pos.append(cyl(0, 0, P.R_IN + EPS, P.LEDGE_Z0, P.LEDGE_Z1).cut(cyl(0, 0, P.LEDGE_RI, 0, T))
               .intersect(box(-R, R, -R, P.Y_VISOR_IN + EPS, 0, T)))
    # thick roof: cover-glass ring + LCD bonding plane over the whole glass footprint (runs to the rear wall)
    zt = P.ROOF_Z + EPS
    pos.append(cyl(0, 0, P.THICK_RING_R, P.BOND_Z, zt))
    pos.append(box(-P.LCD_POCKET_X, P.LCD_POCKET_X, -R, P.LCD_POCKET_Y1, P.BOND_Z, zt)
               .intersect(cyl(0, 0, P.R_IN + EPS, 0, T)))
    # LCD locating ribs (sides and rear; the front is located by posts E and the hood rear walls, the sides also by posts B).
    # The two rear ribs reach down to the free height above the PCB: the tilted glass is pushed back against them (step 9)
    rz0, rt = M["lcd_rib_z0"], M["lcd_rib_t"]
    for (ya, yb) in M["lcd_side_ribs_y"]:
        for sx in (1, -1):
            xa, xb = sorted((sx * P.LCD_POCKET_X, sx * (P.LCD_POCKET_X + rt)))
            pos.append(box(xa, xb, ya, yb, rz0, zt))
    xa, xb = M["lcd_rear_ribs_x"]
    for sx in (1, -1):
        x0, x1 = sorted((sx * xa, sx * xb))
        pos.append(box(x0, x1, P.LCD_POCKET_Y0 - rt, P.LCD_POCKET_Y0, P.LCD_REAR_RIB_Z0, P.BOND_Z + EPS))
    # support posts roof -> PCB top
    for _, x0, x1, y0, y1 in P.post_rects():
        pos.append(box(x0, x1, y0, y1, P.PCB_Z1, zt))
    # PCB locating spigots under the two posts B (they enter the non-plated PCB holes; the post foot seats round them).
    # Rev D: the pair is 28.7 mm apart, outboard of the cameras
    for (sx_, sy_) in (P.LOC_ROUND[:2], P.LOC_SLOT[:2]):
        sp = cyl(sx_, sy_, P.SPIGOT_D / 2, P.SPIGOT_Z0, P.PCB_Z1 + EPS)
        if M["spigot_tip_chamfer"] > 0:
            sp = sp.faces("<Z").chamfer(M["spigot_tip_chamfer"])
        pos.append(sp)
    # camera hoods
    for cx, _cy in P.CAM_XY.values():
        pos.append(_hood_positive(cx))
    # vent pad (runs out to the side wall so that 0.8 mm stays under the drain groove) and the pad under the nose groove
    vx, vy = P.VENT_XY; hp = M["vent_pad"] / 2
    pos.append(box(vx - hp - 0.6, R, vy - hp, vy + hp, P.VENT_PAD_Z, zt).intersect(cyl(0, 0, P.R_IN + EPS, 0, T)))
    nw = M["nose_w"] / 2 + P.MIN_WALL
    pos.append(box(-nw, nw, P.THICK_RING_R - 0.3, P.Y_VISOR_IN + EPS, P.ROOF_Z - M["nose_depth"], zt))
    body = shell
    for p in pos:
        body = body.union(p)

    gw, gd = M["vent_groove_w"] / 2, M["vent_groove_d"]
    neg = [
        cyl(0, 0, P.RECESS_D / 2, P.RECESS_FLOOR_Z, T + 1),                      # cover-glass recess
        cyl(0, 0, P.APERTURE_D / 2, P.BOND_Z - 1, T + 1),                        # display aperture
        cyl(vx, vy, P.VENT_HOLE_D / 2, P.VENT_PAD_Z - 1, T + 1),                 # vent hole
        box(vx, R + 1, vy - gw, vy + gw, T - gd, T + 1),                         # drain groove from the vent hole over the edge
        box(vx - gw, vx + gw, vy - M["vent_cross_half"], vy + M["vent_cross_half"], T - gd, T + 1),   # cross groove
        box(-M["nose_w"] / 2, M["nose_w"] / 2, P.RECESS_D / 2 - 0.3, P.Y_VISOR + 1, T - M["nose_depth"], T + 1),
    ]
    for cx, _cy in P.CAM_XY.values():
        neg.append(_hood_negative(cx))
    for n in neg:
        body = body.cut(n)
    return body.clean()


# ----------------------------------------------------------------------------------------------
# 2. BASE PLATE - primary: routed FR-4 from the PCB fabricator; alternative: printed MJF PA12 (params.base_variant)
# ----------------------------------------------------------------------------------------------
def _pad_slot(z0, z1):
    """One slot through all seven pad positions (the 0.34 mm webs between 2.2 mm holes cannot be made)."""
    r = P.PAD_HOLE_D / 2
    xa, xb = min(P.PAD_XS), max(P.PAD_XS)
    return box(xa, xb, P.PAD_Y - r, P.PAD_Y + r, z0, z1).union(cyl(xa, P.PAD_Y, r, z0, z1)).union(cyl(xb, P.PAD_Y, r, z0, z1))


def _grain_negative(z0, z1):
    """Grain opening.  FR-4 plate: a plain round hole (the baffle is a separate ring bonded to the PCB).  PA12 plate: the
    opening minus the integral baffle ring and its three spokes (all from the YAML)."""
    gx, gy = P.GRAIN_X, P.GRAIN_Y
    opening = cyl(gx, gy, P.GRAIN_R, z0, z1)
    if not P.BAFFLE_INTEGRAL:
        return opening
    ring = cyl(gx, gy, P.BAFFLE_RO, z0 - 1, z1 + 1).cut(cyl(gx, gy, P.BAFFLE_RI, z0 - 2, z1 + 2))
    keep = ring
    w = P.SPOKE_W / 2
    for a in P.SPOKE_ANGLES:
        sp = box(P.BAFFLE_RO - 0.2, P.GRAIN_R + 0.5, -w, w, z0 - 1, z1 + 1)
        keep = keep.union(sp.rotate((0, 0, 0), (0, 0, 1), a).translate((gx, gy, 0)))
    return opening.cut(keep)


def base_plate():
    """Base plate of the active variant (z 0 .. BASE_T): D outline, grain opening, one slot over the seven pads and three
    THROUGH holes for the ball feet (drilled dia 1.10 in FR-4, printed and reamed dia 1.15 in PA12; the balls are set on
    a gauge plate and potted from the inside).  The edge is plain: no notch crosses the seal land (the plate is
    registered to the PCB in the lamination jig, the PCB to the tub by the two spigots)."""
    z0, z1 = 0.0, P.BASE_T
    body = dprism(P.BASE_R, P.BASE_FLAT, z0, z1)
    body = body.cut(_grain_negative(z0 - 1, z1 + 1)).cut(_pad_slot(z0 - 1, z1 + 1))
    for (x, y) in P.BALL_XY:
        body = body.cut(cyl(x, y, P.BALL_HOLE_D / 2, z0 - 1, z1 + 1))
    return body.clean()


def baffle_ring():
    """FR-4 build: separate printed black PA12 light baffle round the photodiode, bonded to the PCB underside on a die-cut
    adhesive annulus.  Its lower face is flush with the surface of the clear potting (z = GRAIN_FILL_Z)."""
    gx, gy = P.GRAIN_X, P.GRAIN_Y
    return cyl(gx, gy, P.BAFFLE_RO, P.BAFFLE_RING_Z0, P.BAFFLE_RING_Z1).cut(cyl(gx, gy, P.BAFFLE_RI, -1, P.PCB_Z0 + 1))


def baffle_adhesive():
    """Die-cut adhesive annulus between the baffle ring and the PCB underside (same diameters as the ring)."""
    gx, gy = P.GRAIN_X, P.GRAIN_Y
    return cyl(gx, gy, P.BAFFLE_RO, P.BAFFLE_RING_Z1, P.PCB_Z0).cut(cyl(gx, gy, P.BAFFLE_RI, -1, P.PCB_Z0 + 1))


def baffle_ring_sprue():
    """PRINT FILE of the baffle ring (not an assembly part): a sprued set of MECH['ring_sprue']['n'] rings, each printed
    BAFFLE_RING_PRINT_H high (the lapping allowance is on top) and joined by a gate on its outside to a runner bar, so that the
    bureau handles one piece instead of loose 0.015 g rings.  Rings in two rows along the runner (the y axis), resting on z = 0."""
    sp = M["ring_sprue"]
    n, pitch, rw, gw, gl = sp["n"], sp["pitch"], sp["runner"], sp["gate_w"], sp["gate_len"]
    per_row = (n + 1) // 2
    h = P.BAFFLE_RING_PRINT_H
    cx = rw / 2 + gl + P.BAFFLE_RO                           # ring centres this far from the runner axis
    ylen = (per_row - 1) * pitch + 2 * P.BAFFLE_RO
    body = box(-rw / 2, rw / 2, -ylen / 2, ylen / 2, 0.0, rw)
    k = 0
    for sx in (1, -1):
        for j in range(per_row):
            if k >= n:
                break
            k += 1
            y = (j - (per_row - 1) / 2) * pitch
            ring = cyl(sx * cx, y, P.BAFFLE_RO, 0.0, h).cut(cyl(sx * cx, y, P.BAFFLE_RI, -1, h + 1))
            xa, xb = sorted((sx * (rw / 2 - EPS), sx * (rw / 2 + gl + 0.5 * P.BAFFLE_WALL)))
            gate = box(xa, xb, y - gw / 2, y + gw / 2, 0.0, min(h, P.MIN_WALL)).cut(cyl(sx * cx, y, P.BAFFLE_RI, -1, h + 1))
            body = body.union(ring).union(gate)
    return body.clean()


def photodiode_box():
    pd = P.PD
    return box(pd["x"] - pd["dx"] / 2, pd["x"] + pd["dx"] / 2, pd["y"] - pd["dy"] / 2, pd["y"] + pd["dy"] / 2, P.PCB_Z0 - pd["h"], P.PCB_Z0)


def grain_potting():
    """Clear potting of the grain opening as cured: from the PCB underside down to z = GRAIN_FILL_Z (0.05 inside the
    opening, so that it never stands proud of the base plane), embedding the LEDs and the photodiode outside and inside
    the baffle ring.  It is everything inside the opening cylinder that is not plate, adhesive, baffle or a part."""
    gx, gy = P.GRAIN_X, P.GRAIN_Y
    body = cyl(gx, gy, P.GRAIN_R, P.GRAIN_FILL_Z, P.PCB_Z0)
    body = body.cut(base_plate()).cut(pcb_adhesive())                     # integral baffle and spokes, sheet on them (PA12 build)
    if not P.BAFFLE_INTEGRAL:
        body = body.cut(cyl(gx, gy, P.BAFFLE_RO, P.BAFFLE_RING_Z0 - 1, P.PCB_Z0 + 1).cut(cyl(gx, gy, P.BAFFLE_RI, -2, P.PCB_Z0 + 2)))
    body = body.cut(photodiode_box())
    for b in led_boxes():
        body = body.cut(b)
    return body.clean()


# ----------------------------------------------------------------------------------------------
# 3. CRADLE (charging / data dock, one orientation, lip + latch hold-down; numbers from the YAML cradle block) with its pins and PCB
# ----------------------------------------------------------------------------------------------
def _pin_slot(w, z0, z1):
    xa, xb = min(P.PAD_XS), max(P.PAD_XS)
    return box(xa, xb, P.PAD_Y - w / 2, P.PAD_Y + w / 2, z0, z1).union(cyl(xa, P.PAD_Y, w / 2, z0, z1)).union(cyl(xb, P.PAD_Y, w / 2, z0, z1))


def latch_profile():
    """Section of beam + hook in the y-z plane (the same at every x): front face vertical at the nest radius; back face
    tapering in from the root to the neck and flaring out again to the nose level; straight nose; retaining face raked
    back from the nose up to the heel (the nose is its lowest point); lead-in above the nose flat."""
    zr = M["latch_root_z"]
    yf, yn = P.LATCH_Y_FACE, P.HOOK_Y
    return [(yf, zr - EPS), (yf, P.HOOK_HEEL_Z), (yn, P.HOOK_Z0), (yn, P.HOOK_LEAD_Z0), (yf, P.LATCH_TOP_Z),
            (P.LATCH_Y_BACK1, P.LATCH_TOP_Z), (P.LATCH_Y_BACK1, P.HOOK_Z0), (P.LATCH_Y_BACKN, P.LATCH_NECK_Z),
            (P.LATCH_Y_BACK0, zr), (P.LATCH_Y_BACK0, zr - EPS)]


def latch():
    """Rear hold-down latch as one solid: rectangular cantilever (latch_w wide; thickness latch_h_root at the root,
    latch_h_neck at the neck, latch_h_tip where it runs into the hook) rooted on the floor of the latch well, full-width
    hook with a straight nose and a raked retaining face one fit clearance above the tub top, 30 deg lead-in, and a
    thumb tab that projects rearward from the top (press it down to release).  Fillets at the root (both faces), at the
    heel of the hook and under the tab."""
    hw, tw, zr = M["latch_w"] / 2, M["tab_w"] / 2, M["latch_root_z"]
    out = prism_x(latch_profile(), -hw, hw)
    out = out.union(box(-tw, tw, P.TAB_Y0, P.LATCH_Y_BACK1 + EPS, P.TAB_Z0, P.LATCH_TOP_Z))          # thumb tab
    rf = M["latch_root_fillet"]
    out = out.union(_fillet_x((P.LATCH_Y_FACE, zr), (0, 1), (1, 0), rf, -hw, hw))                    # root, front face
    tb = (P.LATCH_Y_BACKN - P.LATCH_Y_BACK0, P.LATCH_S1); n = math.hypot(*tb)                        # direction of the back face
    out = out.union(_fillet_x((P.LATCH_Y_BACK0, zr), (tb[0] / n, tb[1] / n), (-1, 0), rf, -hw, hw))  # root, back face
    ca, sa = math.cos(math.radians(M["hook_rake_deg"])), math.sin(math.radians(M["hook_rake_deg"]))
    out = out.union(_fillet_x((P.LATCH_Y_FACE, P.HOOK_HEEL_Z), (0, -1), (ca, -sa), M["hook_heel_fillet"], -hw, hw))   # heel
    out = out.union(_fillet_x((P.LATCH_Y_BACK1, P.TAB_Z0), (0, -1), (-1, 0), M["tab_root_fillet"], -tw, tw))          # under the tab
    fl = (P.LATCH_Y_BACK1 - P.LATCH_Y_BACKN, P.LATCH_L - P.LATCH_S1); nf = math.hypot(*fl)           # smooth blend at the neck
    out = out.union(_fillet_x((P.LATCH_Y_BACKN, P.LATCH_NECK_Z), (-tb[0] / n, -tb[1] / n), (fl[0] / nf, fl[1] / nf), M["latch_neck_blend"], -hw, hw))
    return out.clean()


def lip():
    """Fixed front hold-down: tower in front of the visor between the camera windows and the lip over the tub top."""
    lw = M["lip_half_w"]
    tower = box(-lw, lw, P.LIP_POCKET_Y, P.CRADLE_Y1 - 0.8, P.CRADLE_TOP_Z - EPS, P.LIP_Z1)
    plate = box(-lw, lw, P.LIP_Y0, P.LIP_POCKET_Y + EPS, P.LIP_Z0, P.LIP_Z1)
    return tower.union(plate)


def _scallops(z0, z1):
    """Finger scallops: two sectors of the nest wall (radial end faces)."""
    X = P.CRADLE_X
    a0, a1 = (math.radians(a) for a in M["scallop_deg"])
    r1, r2 = P.NEST_R - M["scallop_inset"], 3 * X
    out = []
    for sx in (1, -1):
        pts = [(sx * r * math.cos(a), r * math.sin(a)) for r, a in ((r1, a0), (r2, a0), (r2, a1), (r1, a1))]
        out.append(poly_prism(pts, z0, z1))
    return out


def _basin():
    """Negative of the drained nest floor.  The marker stands on its ball feet on the front strip (y >= STRIP_Y0) and on
    two round pads; everywhere else the floor is lowered and falls from the centre line to both sides, out through the
    finger scallops.  A rim stays round the pin slot and a dam in front of the latch well, both at the level of the
    strip, so that water on the floor reaches neither the cradle PCB nor the well."""
    X, zt = P.CRADLE_X, P.CRADLE_TOP_Z
    zlo, zhi = P.BASIN_Z_AT_EDGE - 3.0, zt + 1
    foot = dprism(P.NEST_R, P.NEST_FLAT, zlo, zhi)
    for sc in _scallops(zlo, zhi):
        foot = foot.union(sc)
    foot = foot.cut(box(-2 * X, 2 * X, P.STRIP_Y0, 3 * X, zlo - 1, zhi + 1))                               # landing strip
    for (bx, by) in P.BALL_XY:
        if by < P.STRIP_Y0:
            foot = foot.cut(cyl(bx, by, M["ball_pad_dia"] / 2, zlo - 1, zhi + 1))                          # pads under the rear feet
    foot = foot.cut(_pin_slot(P.CRADLE_PIN_SLOT_W + 2 * M["slot_rim_t"], zlo - 1, zhi + 1))                # rim round the pin slot
    foot = foot.cut(box(-P.WELL_HX, P.WELL_HX, -3 * X, P.WELL_Y1 + M["dam_t"], zlo - 1, zhi + 1))          # dam + latch well
    xe = 2 * X
    tool = prism_y([(-xe, P.BASIN_RIDGE_Z - xe * P.BASIN_TAN), (0.0, P.BASIN_RIDGE_Z), (xe, P.BASIN_RIDGE_Z - xe * P.BASIN_TAN),
                    (xe, zhi), (-xe, zhi)], -3 * X, 3 * X)
    return foot.intersect(tool)


def cradle(with_latch=True, with_lip=True, with_tab_stop=True):
    """Printed dock body.  Nest = the marker D outline + fit clearance (the flat is the orientation key); the ball feet
    rest on the front strip and two pads, the rest of the floor is a drained basin.  with_latch / with_lip = False give
    the body without those features (used by the insertion check); with_tab_stop = False is used by the self-test."""
    X, y0, y1 = P.CRADLE_X, P.CRADLE_Y0, P.CRADLE_Y1
    zb, zt = P.CRADLE_BOT_Z, P.CRADLE_TOP_Z
    zr = M["latch_root_z"]
    body = box(-X, X, y0, y1, zb, zt).edges("|Z").fillet(M["cradle_corner_r"]).faces(">Z").edges().chamfer(0.8)
    body = body.cut(dprism(P.NEST_R, P.NEST_FLAT, P.NEST_FLOOR_Z, zt + 1))               # nest
    for sc in _scallops(P.NEST_FLOOR_Z, zt + 1):                                         # finger scallops
        body = body.cut(sc)
    body = body.cut(_basin())                                                            # drained floor
    # the nest wall is open over the width of the latch well (no sliver of wall between nest and well)
    body = body.cut(box(-P.WELL_HX, P.WELL_HX, P.WELL_Y1 - EPS, P.NEST_WINDOW_Y1, P.NEST_FLOOR_Z, zt + 1))
    # latch well: open pocket in which the cantilever stands free (front gap, side gaps, back cavity)
    body = body.cut(box(-P.WELL_HX, P.WELL_HX, P.WELL_Y0, P.WELL_Y1, zr, zt + 1))
    # guard wall behind the latch with two over-travel stop ribs
    body = body.union(box(-P.WELL_HX, P.WELL_HX, P.WELL_Y0 - M["guard_t"], P.WELL_Y0, zt - EPS, M["guard_top_z"]))
    for sx in (1, -1):
        xa, xb = sorted((sx * (M["stop_rib_x"] - M["stop_rib_w"] / 2), sx * (M["stop_rib_x"] + M["stop_rib_w"] / 2)))
        body = body.union(box(xa, xb, P.WELL_Y0 - EPS, P.STOP_RIB_Y1, zr - EPS, M["guard_top_z"]))
    if with_tab_stop:                                                                    # stop under the thumb tab
        hw = M["tab_stop_w"] / 2
        body = body.union(box(-hw, hw, P.TAB_STOP_Y0, P.TAB_STOP_Y1, zt - 1.0, P.TAB_STOP_Z))
    if with_lip:
        body = body.union(lip())
    if with_latch:
        body = body.union(latch())
    body = body.cut(_pin_slot(P.CRADLE_PIN_SLOT_W, P.CPCB_Z1 - 1, P.NEST_FLOOR_Z + 1))  # one slot for the spring pins
    # PCB pocket (open underneath) and the USB-C receptacle pocket / rear opening
    body = body.cut(box(-P.CPCB_HX - P.CLR, P.CPCB_HX + P.CLR, P.CPCB_Y0 - P.CLR, P.CPCB_Y1 + P.CLR, zb - 1, P.CPCB_Z1))
    uw = M["usb"][0] / 2 + 0.3
    body = body.cut(box(-uw, uw, y0 - 1, P.USB_Y1 + P.CLR, P.CPCB_Z1 - P.CLR, P.USB_Z1 + P.CLR))   # clear under the overhanging shell too
    # drain of the latch well: a tunnel from the back of the well to the rear face, beside the USB opening
    dx0, dx1 = M["well_drain_x"]
    body = body.cut(box(dx0, dx1, y0 - 1, P.WELL_Y0 + 0.5, P.WELL_DRAIN_Z0, P.WELL_DRAIN_Z1))
    for (sx, sy_) in P.CPCB_SCREWS:                                                     # spot marks for 4 screws
        for s in (1, -1):
            body = body.cut(cyl(s * sx, sy_, M["cradle_screw_pilot_dia"] / 2, P.CPCB_Z1 - 0.01,
                                P.CPCB_Z1 + M["cradle_screw_pilot_depth"]))
    # lightening pockets from below
    lx0, lx1 = M["lighten_x"]; ly0, ly1 = M["lighten_y"]; lz = M["lighten_ceiling_z"]
    for s in (1, -1):
        xa, xb = sorted((s * lx0, s * lx1))
        body = body.cut(box(xa, xb, ly0, ly1, zb - 1, lz).edges("|Z").fillet(2.0))
    fx_, fy0, fy1 = M["lighten_front"]
    body = body.cut(box(-fx_, fx_, fy0, fy1, zb - 1, lz).edges("|Z").fillet(2.0))
    fx, fy = M["foot_xy"]
    for sx in (1, -1):
        for s in (1, -1):
            body = body.cut(cyl(sx * fx, P.CRADLE_CY + s * fy, M["foot_pocket_dia"] / 2, zb - 1, zb + M["foot_pocket_depth"]))
            body = body.cut(cyl(sx * fx, P.CRADLE_CY + s * fy, M["core_dia"] / 2, zb, P.CORE_Z1))   # blind core in each corner
    return body.clean()


def cradle_pcb():
    hx = P.CPCB_HX
    body = box(-hx, hx, P.CPCB_Y0, P.CPCB_Y1, P.CPCB_Z0, P.CPCB_Z1)
    for x in P.PAD_XS:                                  # seven pin positions (consumer build fits four)
        body = body.cut(cyl(x, P.PAD_Y, M["pin_tail_dia"] / 2 + 0.07, P.CPCB_Z0 - 1, P.CPCB_Z1 + 1))
    for (sx, sy_) in P.CPCB_SCREWS:
        for s in (1, -1):
            body = body.cut(cyl(s * sx, sy_, 1.1, P.CPCB_Z0 - 1, P.CPCB_Z1 + 1))
    return body


def usb_receptacle():
    w, d, h = M["usb"]
    return box(-w / 2, w / 2, P.USB_Y0, P.USB_Y1, P.CPCB_Z1, P.USB_Z1)


def spring_pin(x):
    """Mill-Max 0914-series pin (PROVISIONAL envelope), drawn compressed to its working height on the pad face."""
    y = P.PAD_Y
    tail = cyl(x, y, M["pin_tail_dia"] / 2, P.CPCB_Z0 - M["pin_tail_below_pcb"], P.CPCB_Z1)
    body = cyl(x, y, M["pin_body_dia"] / 2, P.CPCB_Z1, P.PIN_BODY_Z1)
    plunger = cyl(x, y, M["pin_plunger_dia"] / 2, P.PIN_BODY_Z1, P.PAD_Z0)
    return tail.union(body).union(plunger)


def spring_pin_free_plunger(x):
    """The plunger of a pin at its FREE length (tip at PIN_TIP_FREE_Z): what the marker meets while it is being inserted."""
    return cyl(x, P.PAD_Y, M["pin_plunger_dia"] / 2, P.PIN_BODY_Z1, P.PIN_TIP_FREE_Z)


def spring_pins():
    return {f"spring_pin_{i + 1}": spring_pin(x) for i, x in enumerate(P.PAD_XS)}


def cradle_feet():
    fx, fy = M["foot_xy"]; out = {}
    i = 0
    for sx in (1, -1):
        for sy in (1, -1):
            i += 1
            z1 = P.CRADLE_BOT_Z + M["foot_pocket_depth"]
            out[f"cradle_foot_{i}"] = cyl(sx * fx, P.CRADLE_CY + sy * fy, M["foot_dia"] / 2, z1 - M["foot_h"], z1)
    return out


# ----------------------------------------------------------------------------------------------
# 4. Main PCB with its parts
# ----------------------------------------------------------------------------------------------
PCB_SKIP = ("U2", "U3", "BT1")       # cameras and battery are separate solids


def pcb_board():
    """Bare board with the two non-plated locating holes (round + slot along x) for the tub spigots."""
    body = dprism(P.PCB_R, P.PCB_FLAT, P.PCB_Z0, P.PCB_Z1)
    z0, z1 = P.PCB_Z0 - 1, P.PCB_Z1 + 1
    rx, ry, rd = P.LOC_ROUND
    body = body.cut(cyl(rx, ry, rd / 2, z0, z1))
    sx, sy, sd, sl = P.LOC_SLOT
    h = (sl - sd) / 2
    return body.cut(box(sx - h, sx + h, sy - sd / 2, sy + sd / 2, z0, z1).union(cyl(sx - h, sy, sd / 2, z0, z1)).union(cyl(sx + h, sy, sd / 2, z0, z1)))


def led_boxes(z_overlap=0.0):
    """The sixteen 0402 LED bodies under the PCB (pairs on the YAML ring); z_overlap lets them reach into the board for a clean fuse."""
    out = []
    lr, lt = M["led_body"]; h = P.LED_RING["led_height"]
    for k in range(P.LED_RING["count_pairs"]):
        ang = P.LED_RING["first_azimuth_deg"] + P.LED_RING["step_deg"] * k
        for off in (-M["led_pair_offset"], M["led_pair_offset"]):
            b = box(P.LED_RING["radius"] - lr / 2, P.LED_RING["radius"] + lr / 2, off - lt / 2, off + lt / 2,
                    P.PCB_Z0 - h, P.PCB_Z0 + z_overlap)
            out.append(b.rotate((0, 0, 0), (0, 0, 1), ang).translate((P.LED_RING["x"], P.LED_RING["y"], 0)))
    return out


def main_pcb():
    """Board + every top-side part box (except cameras / battery) + bottom-side LEDs, photodiode and pads."""
    body = pcb_board()
    for p in P.TOP_PARTS:
        if p["ref"] in PCB_SKIP:
            continue
        body = body.union(box(p["x"] - p["dx"] / 2, p["x"] + p["dx"] / 2, p["y"] - p["dy"] / 2, p["y"] + p["dy"] / 2,
                              P.PCB_Z1 - 0.01, P.PCB_Z1 + p["h"]))
    for b in led_boxes(0.01):
        body = body.union(b)
    pd = P.PD
    body = body.union(box(pd["x"] - pd["dx"] / 2, pd["x"] + pd["dx"] / 2, pd["y"] - pd["dy"] / 2, pd["y"] + pd["dy"] / 2,
                          P.PCB_Z0 - pd["h"], P.PCB_Z0 + 0.01))
    for x in P.PAD_XS:
        body = body.union(cyl(x, P.PAD_Y, M["pad_dia"] / 2, P.PAD_Z0, P.PCB_Z0 + 0.01))
    return body.clean()


# ----------------------------------------------------------------------------------------------
# 5. Cameras and prisms
# ----------------------------------------------------------------------------------------------
def camera(side):
    x, y = P.CAM_XY[side]
    return box(x - P.CAM_DX / 2, x + P.CAM_DX / 2, y - P.CAM_DY / 2, y + P.CAM_DY / 2, P.CAM_Z0, P.CAM_Z1)


def prism(side):
    """2 mm right-angle prism: legs = bottom face (over the lens) and exit face (+y); hypotenuse up-and-back."""
    x, _ = P.CAM_XY[side]
    h = P.PRISM_LEG / 2
    pts = [(P.PRISM_EXIT_Y, P.PRISM_Z0), (P.PRISM_EXIT_Y, P.PRISM_Z1), (P.PRISM_Y0, P.PRISM_Z0)]
    return cq.Workplane("YZ").polyline(pts).close().extrude(P.PRISM_LEG).translate((x - h, 0, 0))


# ----------------------------------------------------------------------------------------------
# 6-9. Display stack, glass, battery, adhesives, small parts
# ----------------------------------------------------------------------------------------------
def lcd_glass():
    return box(P.LCD_X0, P.LCD_X1, P.LCD_Y0, P.LCD_Y1, P.LCD_Z0, P.LCD_Z1)


def lcd_flex():
    """Representative FPC tail (PROVISIONAL): leaves the rear edge of the glass, makes one U-fold (centre-line radius
    about 1 mm) and runs forward into the mouth of J1, which faces the rear.  Modelled up to the mouth face."""
    t, w = M["flex_t"], M["flex_w"]
    zt, zb = P.FLEX_ZT, P.FLEX_ZB
    r = P.FLEX_BEND_R
    ya = P.LCD_Y0 - M["flex_straight"]
    j1 = next(p for p in P.TOP_PARTS if p["ref"] == "J1")
    mouth = j1["y"] - j1["dy"] / 2
    pts = [(P.LCD_Y0, zt), (ya, zt)]
    for i in range(1, 24):
        a = math.pi / 2 + math.pi * i / 24
        pts.append((ya + r * math.cos(a), (zt + zb) / 2 + r * math.sin(a)))
    pts += [(ya, zb), (mouth, zb)]
    poly = LineString(pts).buffer(t / 2, cap_style=2, join_style=1, resolution=6)
    xy = list(poly.exterior.coords)[:-1]
    return cq.Workplane("YZ").polyline(xy).close().extrude(w).translate((-w / 2, 0, 0))


def lcd_adhesive():
    """Adhesive frame between LCD glass and the roof ledge, with a vent channel from the round window to the rear right
    corner: the air cell between cover glass and LCD breathes into the (vented) main cavity."""
    body = box(P.LCD_X0, P.LCD_X1, P.LCD_Y0, P.LCD_Y1, P.LCD_Z1, P.BOND_Z)
    body = body.cut(cyl(0, 0, M["lcd_psa_window_dia"] / 2, P.LCD_Z1 - 1, P.BOND_Z + 1))
    w = M["lcd_psa_vent_w"] / 2
    ch = box(M["lcd_psa_window_dia"] / 2 - 1.0, 40.0, -w, w, P.LCD_Z1 - 1, P.BOND_Z + 1).rotate((0, 0, 0), (0, 0, 1), P.LCD_VENT_ANGLE_DEG)
    return body.cut(ch).clean()


def cover_glass():
    return cyl(0, 0, P.CG_D / 2, P.CG_Z0, P.CG_Z1)


def cover_tape():
    """Transfer-tape ring under the cover glass (rev D: 0.13 mm, OD = the glass, ID 25.0)."""
    return cyl(0, 0, P.CG_D / 2, P.RECESS_FLOOR_Z, P.CG_Z0).cut(cyl(0, 0, M["cover_tape_id"] / 2, 0, P.T))


def visor_window(side):
    """0.40 mm borosilicate window seated on the floor of its recess: front face WIN_SUBFLUSH below the visor face, top
    edge WIN_TOP_BELOW below the tub top (rev D)."""
    x, _ = P.CAM_XY[side]
    return box(x - P.WIN_W / 2, x + P.WIN_W / 2, P.WIN_Y0, P.WIN_Y1, P.WIN_Z0, P.WIN_TOP_Z)


def battery():
    b = P.BAT
    return box(b["x"] - b["dx"] / 2, b["x"] + b["dx"] / 2, b["y"] - b["dy"] / 2, b["y"] + b["dy"] / 2, b["z0"], b["z1"])


def battery_lead(i):
    """Envelope of one cell lead and its solder joint: the pad footprint (nominal position inside the YAML pad zone)
    extended to the protection-board end of the cell, up to the joint height the YAML allows above the PCB top."""
    x0, y0, x1, y1 = P.battery_pad_rects()[i]
    b = P.BAT
    cell_end = b["x"] - b["dx"] / 2
    return box(min(x0, cell_end), max(x1, cell_end), y0, y1, P.PCB_Z1, P.PCB_Z1 + P.BAT_JOINT_H)


def foam_pad():
    b = P.BAT; hx = M["foam_dx"] / 2
    return box(b["x"] - hx, b["x"] + hx, b["y"] - b["dy"] / 2, b["y"] + b["dy"] / 2, P.FOAM_Z0, P.FOAM_Z1)


def pcb_adhesive():
    """Die-cut adhesive sheet between base plate and PCB (z BASE_T .. 1.00; 0.20 mm in the FR-4 build, 0.13 mm in the
    PA12 build): grain opening (plain, or with the baffle pattern of the PA12 plate), pad slot and three 2.0 mm holes
    round the potted ball feet."""
    z0, z1 = P.PSA_Z0, P.PSA_Z1
    body = dprism(P.PCB_R, P.PCB_FLAT, z0, z1)
    body = body.cut(_grain_negative(z0 - 1, z1 + 1)).cut(_pad_slot(z0 - 1, z1 + 1))
    for (x, y) in P.BALL_XY:
        body = body.cut(cyl(x, y, P.PSA_FOOT_HOLE_D / 2, z0 - 1, z1 + 1))
    return body.clean()


def seal_bead():
    """Perimeter seal adhesive as cured: the joint between the base seal land and the tub seal face (BEAD_T high: 0.40 mm
    on the FR-4 plate, 0.33 mm on the PA12 plate; 0.4 mm wide on the arc, 0.65 mm under the visor wall) plus the fill of
    the 0.25 mm radial groove between the base edge and the side wall, down to the rim.  One closed ring: nothing
    crosses the land."""
    z0, z1 = P.BASE_T, P.LEDGE_Z0
    land = dprism(P.BASE_R, P.BASE_FLAT, z0, z1).cut(dprism(P.LAND_RI, P.LAND_FLAT_IN, z0 - 1, z1 + 1))
    groove = cyl(0, 0, P.R_IN, P.RIM_Z, z1).cut(cyl(0, 0, P.BASE_R, P.RIM_Z - 1, z1 + 1))
    k = 3.0                                             # the groove exists only where the side wall does: behind the wall ends
    groove = groove.cut(poly_prism([(0, 0), (P.HORN_X_OUT * k, P.Y_VISOR * k), (-P.HORN_X_OUT * k, P.Y_VISOR * k)], P.RIM_Z - 1, z1 + 1))
    return land.union(groove).clean()


def window_bond(side):
    """Adhesive round a visor window.  Rev D: the glass sits on the recess floor and on its shelf, so there is no adhesive
    line behind it.  The seal is a closed FRAME of thixotropic (non-wicking) adhesive round the edge of the glass, all of it
    outside the clear opening: the fill of the two side gaps of the recess, a bead along the top edge of the glass (it stays
    below the tub top) and a fillet on the shelf along the bottom edge in front of the glass (it stays behind the visor
    face).  Check 13 proves that this frame, and not the bare seat of the glass, closes the opening."""
    x, _ = P.CAM_XY[side]
    hw, hr = P.WIN_W / 2, P.WIN_RECESS_W / 2
    y0, y1 = P.WIN_RECESS_FLOOR_Y, P.WIN_Y1
    zt = min(P.T, P.WIN_TOP_Z + M["window_top_bead"])
    f = P.WIN_SILL_FILLET
    body = box(x - hr, x - hw, y0, y1, P.WIN_Z0, zt).union(box(x + hw, x + hr, y0, y1, P.WIN_Z0, zt))
    body = body.union(box(x - hw - 0.01, x + hw + 0.01, y0, y1, P.WIN_TOP_Z, zt))
    if f > 0:                                             # sill fillet: triangle on the shelf against the front face of the glass
        body = body.union(prism_x([(y1, P.WIN_Z0), (y1 + f, P.WIN_Z0), (y1, P.WIN_Z0 + f)], x - hr, x + hr))
    if M["window_bond"] > 0:                              # adhesive line behind the glass, round the clear opening
        film = box(x - hw, x + hw, y0, P.WIN_Y0, P.WIN_Z0, P.WIN_TOP_Z)
        body = body.union(film.cut(box(x - P.OPEN_HALF_W, x + P.OPEN_HALF_W, y0 - 1, y1 + 1, P.OPEN_Z0, P.OPEN_Z1)))
    return body.clean()


def hood_seal(side):
    """Black form-in-place gasket bead that closes the slit above the camera cube at the rear of its hood, shown as
    squeezed at constant volume (params.hood_seal_section): a low bead on the underside of the rear wall, astride the rear
    edge of the cube top - the part behind the cube hangs free like a curtain, the part over the cube is flattened to the
    slit height."""
    x, _ = P.CAM_XY[side]
    return prism_x(P.hood_seal_section()["pts"], x - P.HOOD_SEAL_HW, x + P.HOOD_SEAL_HW).clean()


def ball_epoxy(i):
    """Epoxy that pots ball i: stage 1 fills the through hole round the ball (flush with the base plane, where the gauge
    plate was); stage 2, at lamination, fills the 2.0 mm hole of the adhesive sheet up to the PCB, so that the ball
    bears on its copper land on the board through epoxy in compression.  Follows the active base variant."""
    x, y = P.BALL_XY[i]
    plug = cyl(x, y, P.BALL_HOLE_D / 2, 0.0, P.BASE_T).union(cyl(x, y, P.PSA_FOOT_HOLE_D / 2, P.PSA_Z0, P.PSA_Z1))
    return plug.cut(cq.Workplane("XY").sphere(P.BALL_D / 2).translate((x, y, P.BALL_Z)))


def ball(i):
    x, y = P.BALL_XY[i]
    return cq.Workplane("XY").sphere(P.BALL_D / 2).translate((x, y, P.BALL_Z))


def vent():
    vx, vy = P.VENT_XY
    return cyl(vx, vy, M["vent_od"] / 2, P.VENT_Z0, P.VENT_PAD_Z)


# ----------------------------------------------------------------------------------------------
# 10. Optional part: quarter-wave retarder film under the cover glass (spec amendment E9, EVT trial)
# ----------------------------------------------------------------------------------------------
def retarder_film(dia=None):
    """Quarter-wave retarder film (with its laminating adhesive, RETARDER_T thick) on the underside of the cover glass: a
    disc that covers the display aperture and ends inside the bore of the tape ring, so that the tape still seats on glass.
    Outside the aperture it lies in the gap that the tape leaves between glass and roof ledge.  One CLOCKING FLAT (the chord
    y = RETARDER_FLAT_Y, toward the visor) carries the direction of the film axis from the die cut to the tub: the film is
    laminated to the crystal against a straight stop, the crystal edge is marked at the flat and the mark is set to the nose
    groove of the tub.  Not part of the primary build: an EVT trial part (group "option")."""
    d = P.RETARDER_D if dia is None else dia
    return cyl(0, 0, d / 2, P.RETARDER_Z0, P.RETARDER_Z1).cut(box(-d, d, P.RETARDER_FLAT_Y, d, P.RETARDER_Z0 - 1, P.RETARDER_Z1 + 1))


# ----------------------------------------------------------------------------------------------
# 11. Fixtures: the two calibration seat plates of the two-seat level zero (spec amendment E11, drawing GL1-050)
# ----------------------------------------------------------------------------------------------
def _cal_locators(z_top_face):
    """Double-faced datum fence across the middle of the plate and one side stop pin per nest, standing on the top face of
    the plate (z_top_face).  Plate frame = the marker frame of nest A; nest B is nest A turned 180 deg about CAL_CENTRE."""
    c = P.CAL
    hl = c["fence_len"] / 2
    fence = box(-hl, hl, P.CAL_FENCE_Y0, P.CAL_FENCE_Y1, z_top_face - EPS, c["fence_h"])
    rd, rh = c["fence_relief"]                           # undercut at the foot of both datum faces
    fence = fence.cut(box(-hl - 1, hl + 1, P.CAL_FENCE_Y0 - 1, P.CAL_FENCE_Y0 + rd, z_top_face - 1, rh))
    fence = fence.cut(box(-hl - 1, hl + 1, P.CAL_FENCE_Y1 - rd, P.CAL_FENCE_Y1 + 1, z_top_face - 1, rh))
    out = fence
    for (px, py) in (P.CAL_PIN_XY, P.cal_nest_b(*P.CAL_PIN_XY)):
        out = out.union(cyl(px, py, c["pin_dia"] / 2, z_top_face - EPS, c["pin_h"]))
    return out


def _cal_blank(z_top):
    c = P.CAL
    hx, hy = c["plate"][0] / 2, c["plate"][1] / 2
    cx, cy = P.CAL_CENTRE
    return box(cx - hx, cx + hx, cy - hy, cy + hy, -c["plate"][2], z_top)


def cal_seat_pad_outline(nest="A"):
    """The limit of the seat pads of one nest: the base plate outline less a margin, so that no pad reaches under the tub
    rim or the seal fillet at the plate edge.  A prism (-1 .. 1 in z) in the plate frame."""
    m = P.MECH["legend_edge_margin"]
    d = dprism(P.BASE_R - m, P.BASE_FLAT - m, -1.0, 1.0)
    if nest == "B":
        d = d.rotate((P.CAL_CENTRE[0], P.CAL_CENTRE[1], 0), (P.CAL_CENTRE[0], P.CAL_CENTRE[1], 1), 180)
    return d


def cal_seat_plate(pocket_depth=None):
    """BASE-FACE seat plate (the 'turf seat' of E11).  Per nest three annular seat pads, each round a clearance pocket for
    a ball foot (positions = YAML base_plate.feet.positions); the pad tops are the seat plane z = 0 = the marker base
    plane, the rest of the top face lies CAL['relief'] lower.  The marker therefore rests on the FR-4 face next to its
    three feet and the balls hang free in the pockets.  Two nests, 180 deg apart, either side of the datum fence."""
    c = P.CAL
    zr = -c["relief"]
    depth = c["pocket_depth"] if pocket_depth is None else pocket_depth
    body = _cal_blank(zr)
    for nest in ("A", "B"):
        lim = cal_seat_pad_outline(nest)
        for (bx, by) in P.BALL_XY:
            x, y = (bx, by) if nest == "A" else P.cal_nest_b(bx, by)
            body = body.union(cyl(x, y, c["pad_od"] / 2, zr - EPS, P.CAL_SEAT_Z).intersect(lim))
    for nest in ("A", "B"):
        for (bx, by) in P.BALL_XY:
            x, y = (bx, by) if nest == "A" else P.cal_nest_b(bx, by)
            body = body.cut(cyl(x, y, c["pocket_dia"] / 2, P.CAL_SEAT_Z - depth, P.CAL_SEAT_Z + 1))
    return body.union(_cal_locators(zr)).clean()


def cal_plain_plate():
    """BALL seat plate: the same blank, fence and side stops with a plain lapped top face (z = 0 in ITS frame = the plane of
    the ball feet: in the marker frame the plate sits BALL_PROT lower)."""
    return _cal_blank(0.0).union(_cal_locators(0.0)).clean()


# ----------------------------------------------------------------------------------------------
# 12. Fixture: ball gauge plate of assembly step 2 (sets the three ball feet 0.10 proud of the outer face)
# ----------------------------------------------------------------------------------------------
def ball_gauge_plate(boss=True, hole_dia=None):
    """Ball gauge plate, in the marker frame with the base plate lying on it, OUTER FACE DOWN (boss tops at z = 0 = the
    marker base plane; the plate body below).  Three raised bosses at the ball-foot positions, each with a reamed gauge
    hole in its centre: a ball seated on the rim of its hole stands BALL_PROT below the boss top, and the base plate rests
    on the three boss tops only, i.e. on bare solder mask inside the legend-free zones.  Everything else of the plate face
    lies GAUGE['relief'] lower, so that the legend print (0.03 mm at most) never carries the base plate.
    boss=False builds the plain flat plate of the earlier issue (used by the self-test: it bears on the legend)."""
    g = P.GAUGE
    hx, hy, th = g["blank"][0] / 2, g["blank"][1] / 2, g["blank"][2]
    zr = -g["relief"] if boss else 0.0
    body = box(-hx, hx, -hy, hy, -th, zr)
    if boss:
        for (x, y) in P.BALL_XY:
            body = body.union(cyl(x, y, g["boss_od"] / 2, zr - EPS, 0.0))
    d = P.GAUGE_HOLE_D if hole_dia is None else hole_dia
    for (x, y) in P.BALL_XY:
        body = body.cut(cyl(x, y, d / 2, -g["hole_depth"], 1.0))
    return body.clean()
