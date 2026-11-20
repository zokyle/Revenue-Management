"""GL-1 board import: the real circuit boards against the mechanical model (rev E).

The board toolchain (electrical/tools/gleda/outputs.py, mechanical_data) writes <design>-mechanical.json: board outline
(exact contours and a polygon), NPTH holes, slots / cut-outs, keep-outs, height limits and every placed component with
reference, side, anchor position, rotation, body (length x width x height, corner points), courtyard box and z range.
Frame of that file: origin = board centre, +x right, +y up seen from the top, z = 0 at the bottom surface of the board.
That is the marker frame of params.py in x and y; z_marker = z_board + pcb.z_bottom.

    check_board(parts, path=None, data=None)  ->  dict(passed, skipped, summary, tables, notes, warnings)

When the board file does not exist the result is "skipped: no board file" and passes: the check must not fail a build
before the board exists.  When it exists, the check verifies on the solids of this build:

  A  outline, thickness, NPTH hole and slot equal the YAML (pcb.radius, flat_y, locating_holes).  The outer contour must
     be exactly one arc and one line (the D); the polygon tolerance the file states for itself is capped; an opening that
     appears only in the polygon holes or in the contours counts as an extra opening;
  B  every component must be on side "top" or "bottom".  Every top-side part: body clear of the tub solid by at least
     PART_CLR, clear of the post-foot keep-out squares, not taller than tub_keepouts.camera_hoods.max_part_height inside a
     hood zone (the camera itself is exempt), not taller than tub_keepouts.free_height_above_pcb anywhere (cameras exempt),
     not over a ball-foot zone and at least tub_keepouts.foot_zones.part_margin from it (N7), inside the board keep-in, not
     inside the battery body, not on a battery-lead pad, not taller than tub_keepouts.lcd_tail.max_part_height inside the
     LCD-tail zone (N10) and clear of the modelled LCD flex tail (J1 exempt); the two battery-lead pads inside
     battery.pads.zone (they are checked against the tub as joints battery.pads.joint_max_height tall).  Parts marked DNP
     are tested too: what they would violate is a warning;
  C  the fixed mechanical interfaces are where the YAML has them: both cameras; the LCD connector J1 by its BODY BOX and
     height (rev E: the YAML gives the body, mouth at its rear face) and, separately, by its footprint anchor (YAML
     `anchor`); the battery keep-out = battery.body less battery.board_keepout_notch (the courtyard strip of J1);
  D  no part BODY on the bottom side lies outside the grain opening or the pad slot, and what is inside the grain opening
     clears the baffle ring and the wall and is covered by the potting.  COPPER-ONLY footprints (the file says so itself:
     body height 0 and not in the BOM - fiducials, test pads, ball-foot lands, battery tabs, the contact row) are not
     bodies: they have their own rules (table "Copper-only footprints"): a ball-foot land must sit on a YAML foot zone
     with the YAML land diameter; any other bare copper on the bottom must lie under the adhesive sheet, outside both
     openings and outside the ball-foot zones; on the top side bare copper keeps every plan-view rule of a part (post
     feet, foot zones, keep-in, battery body) and skips only the tests against the tub solid and the tail, which need a
     body.  The "not fitted" mark does not exempt copper (it is on the board whatever the mark says), and a component
     with a body height of 0 that IS in the BOM fails: a part without a body cannot be verified;
  E  the contact pads line up with the cradle pins (YAML pad row and the modelled spring pins);
  F  the bottom-side keep-outs of the YAML (ball-foot zones, via keep-outs of the wetted areas) exist in the file
     (reported as warnings when they are not found: the file only lists keep-outs, not copper).

synthetic_board() builds a board file of the same format from the YAML part list (a conforming board); the self-test
uses it and seeds defects into it.  It is a test fixture, not a board.

    check_cradle_board(parts, path=None, data=None)   (check 19)

does the same for the cradle board (electrical/gl1_cradle/out/gl1_cradle-mechanical.json; frame of that file: origin at
the centre of the 30 x 22 board, so marker x, y = board x, y + (0, centre of cradle.pcb.y); the TOP face of the board is
the datum in z, cradle.pcb.top_z): thickness, outline, the four screw holes, the row of seven spring pins against the
YAML pad row and the modelled pins, which pins are fitted, the USB-C receptacle against the modelled receptacle and its
pocket, nothing else on the top side (the board lies against the pocket ceiling), bottom-side parts clear of the screw
heads and above the feet.  synthetic_cradle_board() / seeded_cradle() are its self-test fixtures.

    python3 cad/board_import.py [main-board file]            exit 0 pass / 1 fail
    python3 cad/board_import.py --cradle [cradle-board file]
"""
from __future__ import annotations
import copy, json, math, pathlib, re
import cadquery as cq
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from shapely.geometry import Point, Polygon, box as sbox
import params as P
import parts as PT
import assembly as A

M = P.MECH
BOARD_FILE = P.MECH_DIR.parent / "electrical" / "gl1_main" / "out" / "gl1_main-mechanical.json"
CRADLE_BOARD_FILE = P.MECH_DIR.parent / "electrical" / "gl1_cradle" / "out" / "gl1_cradle-mechanical.json"
DEMO_FILE = P.MECH_DIR.parent / "electrical" / "tools" / "demo" / "demo_out" / "greenline_demo-mechanical.json"
PART_CLR = 0.2            # required clearance of a top-side part body to the tub solid
POST_CLR = 0.2            # and to a post-foot keep-out square (design/check_layout.py uses the same number)
BOTTOM_CLR = 0.2          # bottom-side part to the baffle ring and to the wall of the grain opening
TOL_XY = 0.02             # position / size agreement with the YAML
OUTLINE_TOL_MAX = 0.05    # the polygon tolerance a board file may state for itself is capped at this
FLEX_CLR = M["flex_part_clr"]   # top-side part to the (representative) LCD flex tail; the connector J1 is exempt
LAND_TOL = 0.05           # ball-foot land: position and diameter against the YAML foot zone
PIN_TOL = 0.05            # cradle board: spring-pin position against the YAML pad row and the modelled pin axis
# copper-only footprint families of the board toolchain (matched in the footprint name, case-insensitive)
BARE_KINDS = (("contact row", "contactrow"), ("ball-foot land", "ballfootland"), ("battery tab", "batterytab"), ("fiducial", "fiducial"),
              ("test pad", "testpad"), ("service pads", "servicepads"))
ROUND_KINDS = ("ball-foot land", "fiducial", "test pad")
R3 = lambda v: None if v is None else round(float(v), 3)


# ----------------------------------------------------------------------------------------------
# geometry helpers
# ----------------------------------------------------------------------------------------------
def _dshape(r, flat_y, n=720):
    return Point(0, 0).buffer(r, n).intersection(sbox(-r - 1, -r - 1, r + 1, flat_y))


def _stadium(length, width, cx, cy, n=64):
    h = (length - width) / 2
    return sbox(cx - h, cy - width / 2, cx + h, cy + width / 2).union(Point(cx - h, cy).buffer(width / 2, n)).union(Point(cx + h, cy).buffer(width / 2, n))


def _min_distance(a, b):
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    d.Perform()
    return d.Value() if d.IsDone() else float("nan")


def body_polygon(c):
    """Body outline of a component in board x, y (the corner points of the file; the courtyard box when they are missing)."""
    cs = (c.get("body") or {}).get("corners")
    if cs and len(cs) >= 3:
        pg = Polygon(cs)
        if pg.is_valid and pg.area > 1e-9:
            return pg
    x0, y0, x1, y1 = c["courtyard_bbox"]
    return sbox(x0, y0, x1, y1)


def _prism(poly, z0, z1):
    pts = list(poly.exterior.coords)[:-1]
    return cq.Workplane("XY").workplane(offset=z0).polyline(pts).close().extrude(z1 - z0).val()


def copper_only(c):
    """True for a board-only footprint: bare copper, no body.  The board file says so itself: a body height of exactly 0
    (known, not missing) and no BOM line.  A zero-height component that is in the BOM is NOT copper-only (it fails)."""
    bd = c.get("body") or {}
    h = bd.get("height")
    return h is not None and float(h) == 0.0 and bool(c.get("height_known", True)) and not bool(c.get("in_bom", False))


def bare_kind(c):
    """Family of a copper-only footprint ('contact row', 'ball-foot land', 'battery tab', 'fiducial', 'test pad', 'service pads') or 'other'."""
    name = c.get("footprint", "").lower().replace("_", "").replace("-", "")
    return next((k for k, key in BARE_KINDS if key in name), "other")


def bare_shape(c):
    """Plan shape of a copper-only footprint: a disc on the body size for the round families, else the body polygon."""
    bd = c.get("body") or {}
    if bare_kind(c) in ROUND_KINDS and bd.get("length"):
        return Point(bd.get("cx", c["x"]), bd.get("cy", c["y"])).buffer(float(bd["length"]) / 2, 64)
    return body_polygon(c)


def _is_battery_tab(c):
    return "batterytab" in c.get("footprint", "").lower() or (c["ref"].upper().startswith("BT") and float((c.get("body") or {}).get("height") or 0.0) == 0.0)


def _contact_row(c):
    """(n, pad dia, pitch) parsed from a contact-row footprint name such as gleda:ContactRow_7x1.8mm_P2.54, or None."""
    m = re.search(r"ContactRow_(\d+)x([0-9.]+)mm_P([0-9.]+)", c.get("footprint", ""))
    return (int(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def _pad_centres(c):
    n, dia, pitch = _contact_row(c)
    a = math.radians(c.get("rot", 0.0))
    return [(c["x"] + (i - (n - 1) / 2) * pitch * math.cos(a), c["y"] + (i - (n - 1) / 2) * pitch * math.sin(a)) for i in range(n)], dia


def load(path=None):
    path = pathlib.Path(path or BOARD_FILE)
    return json.loads(path.read_text())


# ----------------------------------------------------------------------------------------------
# a conforming board in the toolchain's format, built from the YAML (self-test fixture)
# ----------------------------------------------------------------------------------------------
def _comp(ref, side, x, y, length, width, height, footprint, rot=0.0, value="", in_bom=None, anchor=None, t=None):
    """A component in the toolchain's format.  x, y = centre of the BODY; `anchor` = footprint origin where it differs (the
    file then carries the anchor as x, y and the body centre as body.cx, body.cy, as the toolchain does for J1).  A body of
    height 0 is a copper-only footprint and gets no BOM line unless in_bom says otherwise."""
    c = _comp0(ref, side, x, y, length, width, height, footprint, rot, value, t)
    c["in_bom"] = (height > 0) if in_bom is None else in_bom
    if anchor is not None:
        c["x"], c["y"] = anchor
    return c


def _comp0(ref, side, x, y, length, width, height, footprint, rot=0.0, value="", t=None):
    a = math.radians(rot)
    ca, sa = math.cos(a), math.sin(a)
    cs = [[round(x + u * ca - v * sa, 4), round(y + u * sa + v * ca, 4)] for u, v in ((-length / 2, -width / 2), (length / 2, -width / 2), (length / 2, width / 2), (-length / 2, width / 2))]
    xs, ys = [p[0] for p in cs], [p[1] for p in cs]
    t = P.PCB_T if t is None else t
    z0, z1 = (t, t + height) if side == "top" else (-height, 0.0)
    return dict(ref=ref, value=value, footprint=footprint, mpn="", x=x, y=y, rot=rot, side=side,
                body=dict(length=length, width=width, height=height, cx=x, cy=y, corners=cs), z_min=round(z0, 4), z_max=round(z1, 4),
                courtyard_bbox=[min(xs), min(ys), max(xs), max(ys)], height_known=True, dnp=False, in_bom=True)


def battery_keepout():
    """The battery placement keep-out a rev E board must carry: battery.body less battery.board_keepout_notch (the strip of
    J1's courtyard that reaches into the cell box; no copper, solder or body of J1 lies in it)."""
    b, n = P.BAT, P.BAT_NOTCH
    return sbox(b["x"] - b["dx"] / 2, b["y"] - b["dy"] / 2, b["x"] + b["dx"] / 2, b["y"] + b["dy"] / 2).difference(sbox(n["x"][0], n["y"][0], n["x"][1], n["y"][1]))


def _ring(poly):
    return [[round(x, 4), round(y, 4)] for x, y in list(poly.exterior.coords)[:-1]]


def synthetic_board():
    """A board file of the toolchain's format that follows the rev E YAML exactly: outline, hole and slot, the YAML
    top-side parts (fitted and not fitted; J1 with its footprint anchor as x, y and its body centre in the body, as the
    toolchain writes it; the battery body less the J1 courtyard notch is a keep-out, its two lead pads are components),
    the LED ring, the photodiode and the contact row on the bottom side, the copper-only footprints of the YAML (test
    points, fiducials on both sides, the three ball-foot lands), and the keep-outs of the contract."""
    xc = math.sqrt(P.PCB_R ** 2 - P.PCB_FLAT ** 2)
    outline = _dshape(P.PCB_R, P.PCB_FLAT, 1024)
    sx, sy, sd, sl = P.LOC_SLOT
    h = (sl - sd) / 2
    comps = []
    for p in P.TOP_PARTS:
        if p["ref"] == "BT1":
            continue
        c = _comp(p["ref"], "top", p["x"], p["y"], p["dx"], p["dy"], p["h"], ("yaml:FPC_" if p["ref"] == "J1" else "yaml:") + p["name"], value=p["name"], anchor=p.get("anchor"))
        c["dnp"] = bool(p.get("dnp"))
        comps.append(c)
    for q in P.Y.get("top_side_test_points") or []:
        comps.append(_comp(q["ref"], "top", q["x"], q["y"], q["dia"], q["dia"], 0.0, "gleda:TestPad_D%gmm" % q["dia"], value=q.get("net", "")))
    for i, (fx_, fy_) in enumerate(P.Y.get("top_side_fiducials") or []):
        comps.append(_comp(f"FID{i + 1}", "top", fx_, fy_, 2.0, 2.0, 0.0, "gleda:Fiducial_1mm_Mask2mm"))
    n_tf = len(P.Y.get("top_side_fiducials") or [])
    for i, (fx_, fy_) in enumerate(P.Y["bottom_side_parts"].get("fiducials") or []):
        comps.append(_comp(f"FID{n_tf + i + 1}", "bottom", fx_, fy_, 2.0, 2.0, 0.0, "gleda:Fiducial_1mm_Mask2mm"))
    for i, (fx_, fy_) in enumerate(P.FOOT_ZONES):
        comps.append(_comp(f"FL{i + 1}", "bottom", fx_, fy_, P.FOOT_ZONE_LAND_D, P.FOOT_ZONE_LAND_D, 0.0, "gleda:BallFootLand_D%gmm" % P.FOOT_ZONE_LAND_D))
    for i, (x0, y0, x1, y1) in enumerate(P.battery_pad_rects()):
        comps.append(_comp(f"BT{i + 1}", "top", 0.5 * (x0 + x1), 0.5 * (y0 + y1), x1 - x0, y1 - y0, 0.0, "gleda:BatteryTab_%.1fx%.1fmm" % (x1 - x0, y1 - y0), value="BAT+" if i == 0 else "BAT-"))
    lr, lt = M["led_body"]
    k = 0
    for i in range(P.LED_RING["count_pairs"]):
        ang = P.LED_RING["first_azimuth_deg"] + P.LED_RING["step_deg"] * i
        a = math.radians(ang)
        for off in (-M["led_pair_offset"], M["led_pair_offset"]):
            k += 1
            x = P.LED_RING["x"] + P.LED_RING["radius"] * math.cos(a) - off * math.sin(a)
            y = P.LED_RING["y"] + P.LED_RING["radius"] * math.sin(a) + off * math.cos(a)
            comps.append(_comp(f"D{k}", "bottom", round(x, 4), round(y, 4), lr, lt, P.LED_RING["led_height"], "LED_SMD:LED_0402_1005Metric", rot=ang))
    pd = P.PD
    comps.append(_comp("PD1", "bottom", pd["x"], pd["y"], pd["dx"], pd["dy"], pd["h"], "gleda:Photodiode_%.1fx%.1fmm" % (pd["dx"], pd["dy"])))
    pitch = P.PAD_XS[1] - P.PAD_XS[0]
    comps.append(_comp("J2", "bottom", 0.5 * (P.PAD_XS[0] + P.PAD_XS[-1]), P.PAD_Y, P.PAD_XS[-1] - P.PAD_XS[0] + M["pad_dia"], M["pad_dia"], 0.0,
                       "gleda:ContactRow_%dx%.1fmm_P%.2f" % (len(P.PAD_XS), M["pad_dia"], pitch)))
    keep = []
    for name, x0, x1, y0, y1 in P.ko_post_squares():
        keep.append(dict(name=f"post_foot_{name}", layers=["F.Cu"], no_tracks=False, no_vias=False, no_copper=False, no_footprints=True, polygon=_ring(sbox(x0, y0, x1, y1))))
    b = P.BAT
    keep.append(dict(name="battery_body", layers=["F.Cu"], no_tracks=False, no_vias=False, no_copper=False, no_footprints=True, polygon=_ring(battery_keepout())))
    for i, (fx, fy) in enumerate(P.FOOT_ZONES):
        keep.append(dict(name=f"foot_zone_{i + 1}", layers=["B.Cu"], no_tracks=True, no_vias=True, no_copper=False, no_footprints=True,
                         polygon=_ring(Point(fx, fy).buffer(P.FOOT_ZONE_D / 2 / math.cos(math.pi / 64), 16))))
    vk = P.VIA_KEEPOUTS
    keep.append(dict(name="grain_opening_no_via", layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], no_tracks=False, no_vias=True, no_copper=False, no_footprints=False,
                     polygon=_ring(Point(vk["grain_opening"]["x"], vk["grain_opening"]["y"]).buffer(vk["grain_opening"]["dia"] / 2 / math.cos(math.pi / 128), 32))))
    keep.append(dict(name="pad_slot_no_via", layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], no_tracks=False, no_vias=True, no_copper=False, no_footprints=False,
                     polygon=_ring(sbox(-vk["pad_slot"]["length"] / 2, vk["pad_slot"]["y"] - vk["pad_slot"]["width"] / 2, vk["pad_slot"]["length"] / 2,
                                        vk["pad_slot"]["y"] + vk["pad_slot"]["width"] / 2))))
    hl = []
    for ref, side in (("U2", "L"), ("U3", "R")):
        cx = P.CAM_XY[side][0]
        hl.append(dict(name=f"camera_hood_{ref}", side="top", max_height=P.KO_HOOD_MAX_H, exempt=[ref],
                       polygon=_ring(sbox(cx - P.KO_HOOD_HW, P.KO_HOOD_Y0, cx + P.KO_HOOD_HW, P.KO_HOOD_Y1))))
    return dict(design="gl1_synthetic_from_yaml", revision=str(P.REV), units="mm",
                frame="origin = board centre; +x right, +y up seen from the top; rot = degrees counter-clockwise seen from the top (also for bottom-side parts); "
                      "z = 0 bottom surface, z = thickness top surface",
                board=dict(thickness=P.PCB_T, copper_layers=4, bounds=[-P.PCB_R, -P.PCB_R, P.PCB_R, P.PCB_FLAT],
                           edge_contours=[[dict(type="arc", ccw=True, center=[0.0, 0.0], radius=P.PCB_R, start=[round(-xc, 6), P.PCB_FLAT], mid=[0.0, -P.PCB_R], end=[round(xc, 6), P.PCB_FLAT]),
                                           dict(type="line", start=[round(xc, 6), P.PCB_FLAT], end=[round(-xc, 6), P.PCB_FLAT])],
                                          [dict(type="line", start=[sx - h, sy - sd / 2], end=[sx + h, sy - sd / 2]),
                                           dict(type="arc", ccw=True, center=[sx + h, sy], radius=sd / 2, start=[sx + h, sy - sd / 2], mid=[sx + h + sd / 2, sy], end=[sx + h, sy + sd / 2]),
                                           dict(type="line", start=[sx + h, sy + sd / 2], end=[sx - h, sy + sd / 2]),
                                           dict(type="arc", ccw=True, center=[sx - h, sy], radius=sd / 2, start=[sx - h, sy + sd / 2], mid=[sx - h - sd / 2, sy], end=[sx - h, sy - sd / 2])]],
                           outline_polygon=_ring(outline), outline_polygon_holes=[_ring(_stadium(sl, sd, sx, sy, 16))], outline_tolerance=0.01,
                           cutouts=[dict(type="Slot", width=sd, x1=sx - h, x2=sx + h, y1=sy, y2=sy, polygon=_ring(_stadium(sl, sd, sx, sy)))],
                           npth_holes=[dict(name="H1", x=P.LOC_ROUND[0], y=P.LOC_ROUND[1], diameter=P.LOC_ROUND[2])]),
                keepouts=keep, height_limits=hl + [dict(name="lcd_tail", side="top", max_height=P.KO_TAIL["max_part_height"], exempt=["J1"],
                                                       polygon=_ring(sbox(-P.KO_TAIL["half_w"], P.KO_TAIL["y"][0], P.KO_TAIL["half_w"], P.KO_TAIL["y"][1])))],
                max_height=dict(top=max(c["body"]["height"] for c in comps if c["side"] == "top"), bottom=max(c["body"]["height"] for c in comps if c["side"] == "bottom")),
                components=comps)


def seeded(defect):
    """synthetic_board() with one defect, for the self-test: 'tall_under_hood', 'part_on_post_foot', 'part_over_foot_zone',
    'hole_moved', 'pads_shifted', 'bottom_part_outside', 'part_near_foot_zone' (N7), 'tall_in_tail_zone' (N10), and the
    malformed or edge-case boards 'outline_rectangle' (same bounds, no arc, stated tolerance 10), 'bad_side',
    'polygon_hole_only', 'part_in_tail_path', 'dnp_tall_under_hood' (the last one must PASS with a warning).
    Rev E: 'j1_body_moved_anchor_kept' (the body of J1 at its rev D place, 0.5 mm forward, the footprint anchor where the YAML
    has it: only a comparison of the BODY sees it), 'j1_anchor_moved_body_kept', 'battery_keepout_full' (the keep-out without
    the notch), and for the copper-only footprints 'bare_copper_in_grain_opening', 'foot_land_moved',
    'zero_height_bom_part' (a part with a BOM line and a body height of 0 outside the openings: it may not pass as copper),
    'fiducial_on_post_foot', 'bare_copper_marked_dnp_in_opening' (the not-fitted mark must not hide copper)."""
    d = copy.deepcopy(synthetic_board())
    cx = P.CAM_XY["R"][0]
    if defect == "tall_under_hood":                 # a 1.5 mm part beside camera R, inside its hood zone but clear of the skirt wall in plan
        d["components"].append(_comp("C901", "top", cx - 2.3, P.KO_HOOD_Y0 + 0.0, 1.0, 0.5, 1.5, "seeded:tall_0402"))
    elif defect == "part_on_post_foot":
        n, x0, x1, y0, y1 = P.ko_post_squares()[1]   # post A+
        d["components"].append(_comp("R901", "top", 0.5 * (x0 + x1), 0.5 * (y0 + y1), 1.05, 0.54, 0.4, "seeded:R_0402"))
    elif defect == "part_over_foot_zone":
        fx, fy = P.FOOT_ZONES[0]
        d["components"].append(_comp("C902", "top", fx + 0.6, fy + 0.3, 1.0, 0.5, 0.55, "seeded:C_0402"))
    elif defect == "hole_moved":
        d["board"]["npth_holes"][0]["x"] -= 0.3
    elif defect == "pads_shifted":
        for c in d["components"]:
            if c["ref"] == "J2":
                c["x"] += 0.4
                for p in c["body"]["corners"]:
                    p[0] += 0.4
    elif defect == "bottom_part_outside":
        d["components"].append(_comp("C903", "bottom", 12.0, -6.0, 1.0, 0.5, 0.55, "seeded:C_0402"))
    elif defect == "outline_rectangle":              # a rectangular board with the bounds of the D, which states a tolerance of 10 for itself
        r, f = P.PCB_R, P.PCB_FLAT
        cs = [[-r, -r], [r, -r], [r, f], [-r, f]]
        d["board"].update(outline_polygon=cs, outline_tolerance=10,
                          edge_contours=[[dict(type="line", start=cs[i], end=cs[(i + 1) % 4]) for i in range(4)]] + d["board"]["edge_contours"][1:])
    elif defect == "bad_side":                       # a 2.5 mm part whose side is neither top nor bottom
        c = _comp("C904", "top", 6.0, -15.5, 1.0, 0.5, 2.5, "seeded:tall")
        c["side"] = "front"
        d["components"].append(c)
    elif defect == "polygon_hole_only":              # an opening listed only in outline_polygon_holes
        d["board"]["outline_polygon_holes"] = list(d["board"].get("outline_polygon_holes") or []) + [_ring(Point(5.0, 0.0).buffer(0.6, 8))]
    elif defect == "part_in_tail_path":              # a 2.5 mm part behind the mouth of J1, where the LCD tail folds
        d["components"].append(_comp("C905", "top", 0.0, P.J1_MOUTH_Y - 0.7, 1.0, 0.5, 2.5, "seeded:tall"))
    elif defect in ("j1_body_moved_anchor_kept", "j1_anchor_moved_body_kept"):
        c = next(q for q in d["components"] if q["ref"] == "J1")
        if defect.startswith("j1_body"):             # body 0.5 mm forward (mouth at -16.80, the rev D place); anchor untouched
            c["body"]["cy"] += 0.5
            for p in c["body"]["corners"]:
                p[1] += 0.5
        else:                                        # anchor 0.3 mm off; body untouched
            c["y"] += 0.3
    elif defect == "battery_keepout_full":           # the full rectangle of the cell: the rev E board must carry the J1 courtyard notch
        b = P.BAT
        k = next(q for q in d["keepouts"] if q["name"] == "battery_body")
        k["polygon"] = _ring(sbox(b["x"] - b["dx"] / 2, b["y"] - b["dy"] / 2, b["x"] + b["dx"] / 2, b["y"] + b["dy"] / 2))
    elif defect == "bare_copper_in_grain_opening":   # a bottom fiducial (bare copper, mask opening dia 2) inside the grain opening, clear of ring, LEDs and wall
        d["components"].append(_comp("FID901", "bottom", P.GRAIN_X + 2.0, P.GRAIN_Y + 3.0, 2.0, 2.0, 0.0, "gleda:Fiducial_1mm_Mask2mm"))
    elif defect == "bare_copper_marked_dnp_in_opening":
        c = _comp("FID902", "bottom", P.GRAIN_X + 2.0, P.GRAIN_Y + 3.0, 2.0, 2.0, 0.0, "gleda:Fiducial_1mm_Mask2mm")
        c["dnp"] = True
        d["components"].append(c)
    elif defect == "foot_land_moved":                # ball-foot land 1 0.5 mm off its foot
        c = next(q for q in d["components"] if q["ref"] == "FL1")
        c["x"] += 0.5; c["body"]["cx"] += 0.5
        for p in c["body"]["corners"]:
            p[0] += 0.5
    elif defect == "zero_height_bom_part":           # a BOM part on the bottom side, outside both openings, whose body height is given as 0
        d["components"].append(_comp("C909", "bottom", 12.0, -6.0, 1.0, 0.5, 0.0, "Capacitor_SMD:C_0402_1005Metric", in_bom=True))
    elif defect == "fiducial_on_post_foot":          # a top-side fiducial under post A+ (the post would seat on copper and bare laminate, not on mask)
        n, x0, x1, y0, y1 = P.ko_post_squares()[1]
        d["components"].append(_comp("FID903", "top", 0.5 * (x0 + x1), 0.5 * (y0 + y1), 2.0, 2.0, 0.0, "gleda:Fiducial_1mm_Mask2mm"))
    elif defect == "part_near_foot_zone":            # an 0402 0.15 mm behind ball-foot zone 3 (inside the 0.3 mm margin of N7, not over the zone, clear of the battery)
        fx, fy = P.FOOT_ZONES[2]
        d["components"].append(_comp("C907", "top", fx, fy - P.FOOT_ZONE_D / 2 - 0.15 - 0.25, 1.0, 0.5, 0.55, "seeded:C_0402"))
    elif defect == "tall_in_tail_zone":              # a part 0.02 mm taller than the LCD-tail keep-out allows, under the fold; it still clears the MODELLED tail by more than FLEX_CLR
        d["components"].append(_comp("C908", "top", 0.0, 0.5 * (P.KO_TAIL["y"][0] + P.KO_TAIL["y"][1]), 0.6, 0.3, P.KO_TAIL["max_part_height"] + 0.02, "seeded:tall_0201"))
    elif defect == "dnp_tall_under_hood":            # not fitted: must pass, with a warning
        c = _comp("C906", "top", cx - 2.3, P.KO_HOOD_Y0 + 0.0, 1.0, 0.5, 2.5, "seeded:tall")
        c["dnp"] = True
        d["components"].append(c)
    else:
        raise ValueError(defect)
    return d


# ----------------------------------------------------------------------------------------------
# the check
# ----------------------------------------------------------------------------------------------
def check_board(parts, path=None, data=None):
    """See the module docstring.  `data` (a dict in the file format) takes precedence over `path`; path defaults to BOARD_FILE."""
    path = pathlib.Path(path or BOARD_FILE)
    if data is None:
        if not path.exists():
            return dict(passed=True, skipped=True, summary="skipped: no board file", tables=[], warnings=[],
                        notes=[f"looked for {path} (written by the board toolchain: electrical/tools/gleda/outputs.py, mechanical_data)",
                               "when the file exists this check verifies outline, hole and slot against the YAML, every top-side part against the tub solid "
                               f"({PART_CLR} mm), the post feet, the hood zones ({P.KO_HOOD_MAX_H} mm), the free height ({P.PCB_FREE_H} mm), the ball-foot zones with their "
                               f"{P.FOOT_PART_MARGIN} mm margin and the LCD-tail keep-out ({P.KO_TAIL['max_part_height']} mm), "
                               "the bottom side against the grain opening and the pad slot, and the contact pads against the cradle pins",
                               "the check itself is proven by the self-test (cad/selftest.py): a board built from the YAML passes; a tall part under a hood, a part "
                               "on a post foot, a part over a foot zone, a moved hole, a shifted pad row, a bottom-side part outside the openings, a rectangular outline that "
                               "states its own tolerance, a part on an unknown side, an opening listed only as a polygon hole, a part in the path of the LCD tail, a J1 body off its "
                               "place with the anchor kept (and the reverse), bare copper in the grain opening, a moved ball-foot land and a BOM part of height 0 are each caught"])
        try:
            data = load(path)
        except Exception as ex:
            return dict(passed=False, skipped=False, summary=f"FAILED: board file unreadable: {ex!r}", tables=[], notes=[str(path)], warnings=[])
        source = str(path)
    else:
        source = f"data passed in ({data.get('design', '?')})"
    fails, warns, notes = [], [], []
    S = {n: A.solid_of(i) for n, i in parts.items() if i.group not in A.EXTRA_GROUPS}
    tub = S["tub"]
    brd = data["board"]
    comps = [c for c in data.get("components", [])]
    tol_file = float(brd.get("outline_tolerance", 0.01))
    tol_o = min(tol_file, OUTLINE_TOL_MAX)                  # the file under test does not set its own pass mark
    if tol_file > OUTLINE_TOL_MAX:
        warns.append(f"the board file states an outline tolerance of {tol_file} mm; the check uses {OUTLINE_TOL_MAX} mm")

    # ---------------- A: outline, thickness, holes
    arow = []

    def cmp(item, got, want, tol=TOL_XY, note=""):
        ok = got is not None and all(abs(g - w) <= tol for g, w in zip(_tup(got), _tup(want)))
        if not ok:
            fails.append(f"{item}: board {got}, YAML {want}")
        arow.append(dict(item=item, board_file=_fmt(got), yaml=_fmt(want), tolerance_mm=tol, status="ok" if ok else "FAIL", note=note))
    cmp("board thickness", brd.get("thickness"), P.PCB_T, 1e-6)
    yaml_out = _dshape(P.PCB_R, P.PCB_FLAT, 2048)
    try:
        out = Polygon(brd["outline_polygon"])
        dev = max(out.exterior.hausdorff_distance(yaml_out.exterior), abs(out.area - yaml_out.area) / yaml_out.exterior.length)
        cmp("outline: largest deviation from the YAML D shape (R %.2f, flat y %.2f)" % (P.PCB_R, P.PCB_FLAT), dev, 0.0, tol_o + 0.01,
            note=f"polygon of the file; tolerance stated in the file {tol_file}, used {tol_o} (capped at {OUTLINE_TOL_MAX})")
    except Exception as ex:
        out = yaml_out
        fails.append(f"outline polygon unreadable: {ex!r}")
    cmp("outline bounds (x min, y min, x max, y max)", brd.get("bounds"), (-P.PCB_R, -P.PCB_R, P.PCB_R, P.PCB_FLAT))
    outer = (brd.get("edge_contours") or [[]])[0]
    arcs = [e for e in outer if e.get("type") == "arc"]
    lines = [e for e in outer if e.get("type") == "line"]
    cmp("outer contour: number of arcs, lines, other elements (the D is one arc and one line)", (len(arcs), len(lines), len(outer) - len(arcs) - len(lines)), (1, 1, 0), 0,
        note="exact contour of the board edge (edge_contours[0])")
    if arcs and lines:
        cmp("outline arc: centre x, y and radius (exact contour)", (arcs[0]["center"][0], arcs[0]["center"][1], arcs[0]["radius"]), (0.0, 0.0, P.PCB_R), 0.005)
        cmp("outline flat: y of the straight edge (exact contour)", (lines[0]["start"][1], lines[0]["end"][1]), (P.PCB_FLAT, P.PCB_FLAT), 0.005)
    holes = list(brd.get("npth_holes", []))
    slots = [c for c in brd.get("cutouts", []) if c.get("type") == "Slot"]
    other = [c for c in brd.get("cutouts", []) if c.get("type") != "Slot"]
    rx, ry, rd = P.LOC_ROUND
    sx, sy, sd, sl = P.LOC_SLOT
    hbest = min(holes, key=lambda h_: math.hypot(h_["x"] - rx, h_["y"] - ry)) if holes else None
    cmp("locating hole (round, NPTH): x, y, diameter", (hbest["x"], hbest["y"], hbest["diameter"]) if hbest else None, (rx, ry, rd), note=f"under post B+; {len(holes)} NPTH hole(s) in the file")
    sbest = min(slots, key=lambda c: math.hypot(0.5 * (c["x1"] + c["x2"]) - sx, 0.5 * (c["y1"] + c["y2"]) - sy)) if slots else None
    cmp("locating slot: centre x, y, width, overall length along x, y1 - y2",
        (0.5 * (sbest["x1"] + sbest["x2"]), 0.5 * (sbest["y1"] + sbest["y2"]), sbest["width"], abs(sbest["x2"] - sbest["x1"]) + sbest["width"], sbest["y2"] - sbest["y1"]) if sbest else None,
        (sx, sy, sd, sl, 0.0), note=f"under post B-; {len(slots)} slot(s) in the file")
    n_extra = max(0, len(holes) - 1) + max(0, len(slots) - 1) + len(other)
    # openings that appear only as a hole of the outline polygon or as an inner contour (not in cutouts / npth_holes)
    known = []
    for c_ in brd.get("cutouts", []):
        try:
            known.append(Polygon(c_["polygon"]).buffer(0.05))
        except Exception:
            if c_.get("type") == "Slot":
                known.append(_stadium(abs(c_["x2"] - c_["x1"]) + c_["width"], c_["width"], 0.5 * (c_["x1"] + c_["x2"]), 0.5 * (c_["y1"] + c_["y2"])).buffer(0.05))
    known += [Point(h_["x"], h_["y"]).buffer(h_["diameter"] / 2 + 0.05) for h_ in holes]
    n_only = 0
    for ring in (brd.get("outline_polygon_holes") or []):
        try:
            hp = Polygon(ring)
        except Exception:
            n_only += 1; continue
        if not any(k_.contains(hp) for k_ in known):
            n_only += 1
    for contour in (brd.get("edge_contours") or [[]])[1:]:
        pts_ = [q for el in contour for q in (el.get("start"), el.get("end"), el.get("mid")) if q]
        if len(pts_) < 2 or not any(all(k_.contains(Point(q)) for q in pts_) for k_ in known):
            n_only += 1
    cmp("holes, slots and cut-outs that the YAML does not have", n_extra, 0, 0, note="every opening in the board is a path under a post or into the cavity: none is expected")
    cmp("openings listed only in the polygon holes or the inner contours (not in cutouts / npth_holes)", n_only, 0, 0,
        note=f"{len(brd.get('outline_polygon_holes') or [])} polygon hole(s), {max(0, len(brd.get('edge_contours') or []) - 1)} inner contour(s) in the file")

    # ---------------- B: top-side parts
    squares = [(n, sbox(x0, y0, x1, y1)) for n, x0, x1, y0, y1 in P.ko_post_squares()]
    hoods = {s: sbox(cx - P.KO_HOOD_HW, P.KO_HOOD_Y0, cx + P.KO_HOOD_HW, P.KO_HOOD_Y1) for s, (cx, _) in P.CAM_XY.items()}
    zones = [(i + 1, Point(fx, fy).buffer(P.FOOT_ZONE_D / 2, 128)) for i, (fx, fy) in enumerate(P.FOOT_ZONES)]
    tail_zone = sbox(-P.KO_TAIL["half_w"], P.KO_TAIL["y"][0], P.KO_TAIL["half_w"], P.KO_TAIL["y"][1])
    keep_in = _dshape(P.PCB_R, P.PCB_FLAT, 720).buffer(-P.PCB_EDGE_CLR)
    b = P.BAT
    bat_poly = sbox(b["x"] - b["dx"] / 2, b["y"] - b["dy"] / 2, b["x"] + b["dx"] / 2, b["y"] + b["dy"] / 2)
    pad_zone = sbox(*P.BAT_PAD_ZONE)
    cams = {}
    for side, (cx, cy) in P.CAM_XY.items():
        for c in comps:
            if c.get("side") == "top" and math.hypot(c["x"] - cx, c["y"] - cy) < 0.25 and abs(float(c["body"].get("height") or 0) - P.CAM_H) < 0.3:
                cams[side] = c["ref"]
    trow, n_top, d_tub_min = [], 0, (float("inf"), None)
    bad_side = [c for c in comps if c.get("side") not in ("top", "bottom")]
    for c in bad_side:
        fails.append(f"{c.get('ref')}: side {c.get('side')!r} is neither 'top' nor 'bottom': the part cannot be checked")
        trow.append(dict(ref=c.get("ref"), footprint=c.get("footprint", ""), x=c.get("x"), y=c.get("y"), rot=c.get("rot", 0.0), body_mm="-", top_z=None, to_tub_mm=None,
                         nearest_post_foot_mm=None, to_lcd_flex_mm=None, status="FAIL", reasons=f"side {c.get('side')!r} is neither 'top' nor 'bottom'"))
    j1c = next((c for c in comps if c.get("side") == "top" and ("fh12" in c.get("footprint", "").lower() or "fpc" in c.get("footprint", "").lower() or c["ref"] == "J1")), None)
    brow = []                                               # copper-only footprints, both sides
    flex = S.get("lcd_flex")
    tabs = [(c["ref"], body_polygon(c)) for c in comps if c.get("side") == "top" and _is_battery_tab(c)]
    for c in comps:
        if c.get("side") != "top":
            continue
        why = []
        ref = c["ref"]
        tab = _is_battery_tab(c)
        bare = copper_only(c) and not tab                     # bare copper without a body (a lead pad carries a joint: it is tested as one)
        dnp = bool(c.get("dnp")) and not bare                 # copper is on the board whatever the "not fitted" mark says
        n_top += 0 if (dnp or bare or tab) else 1
        pg = bare_shape(c) if bare else body_polygon(c)
        hgt = c["body"].get("height")
        is_cam = ref in cams.values()
        if hgt is None or not c.get("height_known", True):
            why.append("height unknown: cannot be verified")
            hgt = P.PCB_FREE_H
        hgt = float(hgt)
        if hgt == 0.0 and not bare and not tab:
            why.append("in the BOM with a body height of 0: a part without a body cannot be verified (a copper-only footprint has no BOM line)")
        h_eff = P.BAT_JOINT_H if tab else hgt                 # a lead pad carries a joint up to the YAML joint height
        d_tub = d_flex = None
        if not bare:                                          # tests against the solids need a body
            solid = _prism(pg, P.PCB_Z1, P.PCB_Z1 + max(h_eff, 0.01))
            d_tub = _min_distance(solid, tub)
            if d_tub < d_tub_min[0] and not dnp:
                d_tub_min = (d_tub, ref)
            if flex is not None and c is not j1c and not tab:
                d_flex = _min_distance(solid, flex)
                if d_flex < FLEX_CLR - 2e-3:
                    why.append(f"{d_flex:.3f} mm to the LCD flex tail (< {FLEX_CLR}; representative tail shape, PROVISIONAL)")
            if not d_tub >= PART_CLR - 2e-3:
                why.append(f"{d_tub:.3f} mm to the tub (< {PART_CLR})")
        if not tab:
            for tref, tpg in tabs:
                if tpg.intersection(pg).area > 1e-6:
                    why.append(f"on battery lead pad {tref}")
        d_post, n_post = min((sq.distance(pg), n) for n, sq in squares)
        if d_post < POST_CLR - 2e-3:
            why.append(f"{d_post:.3f} mm to post foot {n_post} (< {POST_CLR})" if d_post > 0 else f"on post foot {n_post}")
        for s, hz in hoods.items():
            if hz.intersects(pg) and h_eff > P.KO_HOOD_MAX_H + 1e-9 and cams.get(s) != ref:
                why.append(f"{h_eff} mm tall under camera hood {s} (limit {P.KO_HOOD_MAX_H})")
        if h_eff > P.PCB_FREE_H + 1e-9 and not is_cam:
            why.append(f"{h_eff} mm tall: above the free height {P.PCB_FREE_H}")
        for i, z in zones:
            if z.intersects(pg):
                why.append(f"over ball-foot zone {i} ({z.intersection(pg).area:.2f} mm2)")
            elif z.distance(pg) < P.FOOT_PART_MARGIN - 2e-3:
                why.append(f"{z.distance(pg):.3f} mm to ball-foot zone {i} (< {P.FOOT_PART_MARGIN}, YAML foot_zones.part_margin)")
        if c is not j1c and not tab and tail_zone.intersection(pg).area > 1e-6 and h_eff > P.KO_TAIL["max_part_height"] + 1e-9:
            why.append(f"{h_eff} mm tall inside the LCD-tail keep-out (limit {P.KO_TAIL['max_part_height']}, YAML tub_keepouts.lcd_tail)")
        if not keep_in.buffer(1e-6).contains(pg):
            why.append(f"outside the board keep-in ({P.PCB_EDGE_CLR} mm from the edge) by {pg.difference(keep_in).area:.2f} mm2")
        if tab:
            if not pad_zone.buffer(1e-6).contains(pg):
                why.append("battery lead pad outside battery.pads.zone")
        elif bat_poly.intersection(pg).area > 1e-6:
            why.append(f"inside the battery body ({bat_poly.intersection(pg).area:.2f} mm2)")
        if why and dnp:
            warns.append(f"{ref} is marked not fitted (DNP); if it were fitted: " + "; ".join(why))
        elif why:
            fails.append(f"{ref}: " + "; ".join(why))
        bd = c["body"]
        status = ("not fitted (DNP): ok" if not why else "not fitted (DNP): WOULD FAIL if fitted (warning)") if dnp else ("ok" if not why else "FAIL")
        if bare:
            brow.append(dict(ref=ref, side="top", kind=bare_kind(c), footprint=c.get("footprint", ""), x=c["x"], y=c["y"], size_mm=f"{bd.get('length')} x {bd.get('width')}",
                             marked_not_fitted=bool(c.get("dnp")), rule="plan-view rules of a top-side part (post feet, ball-foot zones, keep-in, battery body, lead pads); no body: not tested against the tub or the tail",
                             measured=f"{d_post:.3f} mm to post foot {n_post}", status=status, reasons="; ".join(why)))
            continue
        trow.append(dict(ref=ref, footprint=c.get("footprint", ""), x=c["x"], y=c["y"], rot=c.get("rot", 0.0),
                         body_mm=f"{bd.get('length')} x {bd.get('width')} x {hgt}" + (f" (joint to {h_eff})" if tab else ""), top_z=R3(P.PCB_Z1 + h_eff),
                         to_tub_mm=R3(d_tub), nearest_post_foot_mm=R3(d_post), to_lcd_flex_mm=R3(d_flex), status=status, reasons="; ".join(why)))

    # ---------------- C: fixed interfaces
    crow = []

    def fixed(item, got, want, tol=TOL_XY, required=True):
        if got is None:
            ok = not required
            (fails if required else warns).append(f"{item}: not found in the board file")
        else:
            ok = all(abs(g - w) <= tol for g, w in zip(got, want))
            if not ok:
                fails.append(f"{item}: board {got}, YAML {want}")
        crow.append(dict(interface=item, board_file=_fmt(got) if got is not None else "not found", yaml=_fmt(want), status="ok" if ok else ("FAIL" if required or got is not None else "not found (warning)")))
    by_ref = {c["ref"]: c for c in comps}
    for side, ref_y in (("L", "U2"), ("R", "U3")):
        c = by_ref.get(cams.get(side, ""))
        cx, cy = P.CAM_XY[side]
        fixed(f"camera {side} ({cams.get(side, ref_y)}): x, y, body length, width, height",
              (c["x"], c["y"], *sorted((c["body"]["length"], c["body"]["width"]), reverse=True), c["body"]["height"]) if c else None, (cx, cy, P.CAM_DX, P.CAM_DY, P.CAM_H))
    # J1 (E24): the YAML entry is the BODY (x, y = body centre, dx, dy as placed, mouth = rear face); the footprint anchor is
    # the separate key `anchor`.  Both are compared: the body box from the corner points of the file, and the anchor
    j1 = j1c
    j1_body = None
    if j1 is not None:
        try:
            j1_body = (*Polygon(j1["body"]["corners"]).bounds, float(j1["body"]["height"]))
        except Exception:
            j1_body = None
    fixed("LCD connector J1 BODY box: x min, y min (the mouth), x max, y max, height", j1_body, (*P.J1_BOX, P.J1["h"]))
    fixed("LCD connector J1 body centre (body.cx, body.cy of the file)", (j1["body"].get("cx"), j1["body"].get("cy")) if j1 and j1["body"].get("cx") is not None else None, (P.J1["x"], P.J1["y"]))
    fixed("LCD connector J1 footprint anchor: x, y", (j1["x"], j1["y"]) if j1 else None, tuple(P.J1.get("anchor") or (P.J1["x"], P.J1["y"])))
    bk = next((k for k in data.get("keepouts", []) if "battery" in k.get("name", "").lower()), None)
    bat_keep = battery_keepout()                            # battery.body less battery.board_keepout_notch (E24)
    bk_poly = None
    if bk:
        try:
            bk_poly = Polygon(bk["polygon"])
        except Exception:
            bk_poly = None
    fixed("battery keep-out: x min, y min, x max, y max, and the area that differs from the YAML body less the J1 courtyard notch (mm2)",
          (*bk_poly.bounds, bk_poly.symmetric_difference(bat_keep).area) if bk_poly is not None else None, (*bat_keep.bounds, 0.0), required=False)

    # ---------------- D, E: bottom side and contact pads
    grain = Point(P.GRAIN_X, P.GRAIN_Y).buffer(P.GRAIN_R, 256)
    slot = _stadium(P.PAD_SLOT_L, P.PAD_HOLE_D, 0.5 * (P.PAD_XS[0] + P.PAD_XS[-1]), P.PAD_Y, 128)
    ring = Point(P.GRAIN_X, P.GRAIN_Y).buffer(P.BAFFLE_RO, 256).difference(Point(P.GRAIN_X, P.GRAIN_Y).buffer(P.BAFFLE_RI, 256))
    drow, prow_, pads = [], [], []
    lands = {}                                              # ball-foot zone index -> land found on it
    for c in comps:
        if c.get("side") != "bottom":
            continue
        bare = copper_only(c)
        if c.get("dnp") and not bare:                         # a part body that is not fitted is not on the board; copper is
            continue
        why = []
        hgt = float(c["body"].get("height") or 0.0)
        row_ = _contact_row(c)
        if bare and not row_:
            kind, shape, bd = bare_kind(c), bare_shape(c), c["body"]
            if kind == "ball-foot land":
                i_z, d_c = min(((i, math.hypot(bd.get("cx", c["x"]) - fx, bd.get("cy", c["y"]) - fy)) for i, (fx, fy) in enumerate(P.FOOT_ZONES)), key=lambda t_: t_[1])
                dia = float(bd.get("length") or 0.0)
                rule_ = f"centre on a YAML ball-foot zone within {LAND_TOL}, dia {P.FOOT_ZONE_LAND_D} +-{LAND_TOL}"
                meas_ = f"{d_c:.3f} mm from foot {i_z + 1}, dia {dia}"
                if d_c > LAND_TOL or abs(dia - P.FOOT_ZONE_LAND_D) > LAND_TOL or abs(float(bd.get("width") or 0.0) - dia) > 1e-6:
                    why.append(f"ball-foot land {d_c:.3f} mm from the nearest YAML foot (foot {i_z + 1}), dia {dia} (YAML land dia {P.FOOT_ZONE_LAND_D})")
                elif i_z in lands:
                    why.append(f"second land on ball foot {i_z + 1} (also {lands[i_z]})")
                else:
                    lands[i_z] = c["ref"]
            else:
                d_g, d_s = shape.distance(grain), shape.distance(slot)
                d_z = min(z.distance(shape) for _, z in zones)
                rule_ = "bare copper under the adhesive sheet: outside the grain opening, the pad slot and the ball-foot zones"
                meas_ = f"{d_g:.3f} to the grain opening, {d_s:.3f} to the pad slot, {d_z:.3f} to the nearest ball-foot zone"
                if shape.intersects(grain):
                    why.append("bare copper inside the grain opening (wetted, lit by the LEDs)" if grain.contains(shape) else "bare copper across the edge of the grain opening")
                if shape.intersects(slot):
                    why.append("bare copper in the pad slot (the spring pins land there)")
                if d_z <= 0:
                    why.append("bare copper inside a ball-foot zone (only the land may be there)")
            if why:
                fails.append(f"{c['ref']} (bottom, copper only): " + "; ".join(why))
            brow.append(dict(ref=c["ref"], side="bottom", kind=kind, footprint=c.get("footprint", ""), x=c["x"], y=c["y"], size_mm=f"{bd.get('length')} x {bd.get('width')}",
                             marked_not_fitted=bool(c.get("dnp")), rule=rule_, measured=meas_, status="ok" if not why else "FAIL", reasons="; ".join(why)))
            continue
        if hgt == 0.0 and not bare:
            why.append("in the BOM with a body height of 0: a part without a body cannot be verified (a copper-only footprint has no BOM line)")
        if row_:
            cen, dia = _pad_centres(c)
            pads += [(c["ref"], i + 1, x, y, dia) for i, (x, y) in enumerate(cen)]
            shape = None
            for x, y in cen:
                shape = Point(x, y).buffer(dia / 2, 64) if shape is None else shape.union(Point(x, y).buffer(dia / 2, 64))
            where = "pad slot" if slot.buffer(1e-6).contains(shape) else None
            margin = -shape.difference(slot).area if where is None else slot.exterior.distance(shape)
        else:
            shape = body_polygon(c)
            where = "grain opening" if grain.buffer(1e-6).contains(shape) else ("pad slot" if slot.buffer(1e-6).contains(shape) else None)
            margin = (grain.exterior.distance(shape) if where == "grain opening" else slot.exterior.distance(shape)) if where else -min(shape.difference(grain).area, shape.difference(slot).area)
        d_ring = cover = None
        if where is None:
            why.append("outside the grain opening and the pad slot")
        elif where == "grain opening":
            d_ring = ring.distance(shape)
            cover = P.GRAIN_FILL_DEPTH - hgt
            if d_ring < BOTTOM_CLR - 2e-3:
                why.append(f"{d_ring:.3f} mm to the baffle ring (< {BOTTOM_CLR})")
            if margin < BOTTOM_CLR - 2e-3:
                why.append(f"{margin:.3f} mm to the wall of the grain opening (< {BOTTOM_CLR})")
            if cover < M["grain_fill_min_cover"] - 1e-9:
                why.append(f"only {cover:.2f} mm of potting over a {hgt} mm part")
        elif hgt > P.PCB_Z0 - P.PAD_Z0 + 0.05:
            why.append(f"a {hgt} mm part in the pad slot (the spring pins land there)")
        if why:
            fails.append(f"{c['ref']} (bottom): " + "; ".join(why))
        drow.append(dict(ref=c["ref"], footprint=c.get("footprint", ""), x=c["x"], y=c["y"], height_mm=hgt, lies_in=where or "NEITHER OPENING",
                         margin_to_the_opening_edge_mm=R3(margin), to_baffle_ring_mm=R3(d_ring), potting_cover_mm=R3(cover), status="ok" if not why else "FAIL",
                         reasons="; ".join(why)))
    if lands and len(lands) != len(P.FOOT_ZONES):
        fails.append(f"ball-foot lands: found on {len(lands)} of {len(P.FOOT_ZONES)} feet ({', '.join(sorted(lands.values()))}); each foot bears on a land")
    pins = sorted((A.bbox_of(parts[n]) for n in parts if n.startswith("spring_pin_")), key=lambda bb: bb[0])
    pin_xy = [(0.5 * (bb[0] + bb[3]), 0.5 * (bb[1] + bb[4])) for bb in pins]
    pads.sort(key=lambda t: t[2])
    if len(pads) != len(P.PAD_XS):
        fails.append(f"{len(pads)} contact pads found in the board file, {len(P.PAD_XS)} expected (a contact-row footprint on the bottom side)")
    for k, (ref, i, x, y, dia) in enumerate(pads):
        yx = (P.PAD_XS[k], P.PIN_ROW_Y) if k < len(P.PAD_XS) else (float("nan"), float("nan"))
        px = pin_xy[k] if k < len(pin_xy) else (float("nan"), float("nan"))
        off_y, off_p = math.hypot(x - yx[0], y - yx[1]), math.hypot(x - px[0], y - px[1])
        ok = off_y <= 0.05 and off_p <= 0.05 and abs(dia - M["pad_dia"]) <= 0.05
        if not ok:
            fails.append(f"contact pad {k + 1}: {off_y:.3f} mm from its YAML position, {off_p:.3f} mm from the cradle pin axis")
        prow_.append(dict(pad=k + 1, ref=ref, x=R3(x), y=R3(y), dia_mm=dia, yaml_x=yx[0], yaml_y=yx[1], offset_from_yaml_mm=R3(off_y), cradle_pin_axis=(R3(px[0]), R3(px[1])),
                          offset_from_pin_axis_mm=R3(off_p), pin_tip_inside_the_pad_by_mm=R3(dia / 2 - M["pin_plunger_dia"] / 2 - off_p), status="ok" if ok else "FAIL"))

    # ---------------- F: keep-outs of the file against the YAML
    krow, frow = [], []
    kos = data.get("keepouts", [])
    for k in kos:
        try:
            pg = Polygon(k["polygon"])
        except Exception:
            continue
        match = "-"
        for n, sq in squares:
            if pg.symmetric_difference(sq).area < 0.02:
                match = f"post foot {n} (YAML square)"
            elif match == "-" and pg.intersection(sq).area > 0.5 * min(pg.area, sq.area):
                match = f"post foot {n}: DIFFERS from the YAML square by {pg.symmetric_difference(sq).area:.2f} mm2"
        if "battery" in k.get("name", "").lower():
            match = "battery body less the J1 courtyard notch (YAML battery.board_keepout_notch)" if pg.symmetric_difference(bat_keep).area < 0.05 else "battery body: DIFFERS from the YAML body less the notch (fails in table C)"
        for i, z in zones:
            if pg.buffer(0.03).contains(z):
                match = f"ball-foot zone {i}"
        if "DIFFERS" in match and "battery" not in match:
            warns.append(f"keep-out {k.get('name')} of the board file: {match}")
        krow.append(dict(name=k.get("name"), layers=", ".join(k.get("layers", [])), no_tracks=k.get("no_tracks"), no_vias=k.get("no_vias"), no_footprints=k.get("no_footprints"),
                         bounds=tuple(round(v, 2) for v in pg.bounds), corresponds_to=match))

    def need(item, shape, flags):
        found = [k.get("name") for k in kos if any(l.startswith("B.") for l in k.get("layers", [])) and all(k.get(f) for f in flags)
                 and Polygon(k["polygon"]).buffer(0.03).contains(shape)]
        if not found:
            warns.append(f"bottom-side keep-out not found in the board file: {item}")
        frow.append(dict(yaml_requirement=item, needs=" + ".join(flags), keep_out_in_the_board_file=", ".join(found) if found else "NOT FOUND (warning)"))
    for i, z in zones:
        need(f"ball-foot zone {i}: dia {P.FOOT_ZONE_D} at {P.FOOT_ZONES[i - 1]}, no via, no track (unmasked dia {P.FOOT_ZONE_LAND_D} land)", z, ("no_tracks", "no_vias"))
        frow[-1]["land_in_the_board_file"] = lands.get(i - 1, "NOT FOUND (warning)")
    if not lands:
        warns.append(f"no ball-foot land (copper-only footprint, dia {P.FOOT_ZONE_LAND_D}) found in the board file: that each ball bears on an unmasked land must be confirmed on the board itself")
    # ---------------- G: what the file states about itself (information for the layout tool; this check applies the YAML zones to every part whatever the file says)
    grow_ = []
    stamp = str(data.get("revision"))
    grow_.append(dict(item="revision stamp of the board file", board_file=stamp, yaml=str(P.REV), status="ok" if stamp == str(P.REV) else "DIFFERS (warning)"))
    if stamp != str(P.REV):
        warns.append(f"the board file is stamped {stamp}; master_params.yaml is {P.REV}: the board was built on an older YAML (rebuild it)")
    want_hl = {"lcd_tail": (sbox(-P.KO_TAIL["half_w"], P.KO_TAIL["y"][0], P.KO_TAIL["half_w"], P.KO_TAIL["y"][1]), P.KO_TAIL["max_part_height"])}
    for s_, hz in hoods.items():
        want_hl[f"camera_hood ({s_})"] = (hz, P.KO_HOOD_MAX_H)
    for nm, (shape, hmax) in want_hl.items():
        got = None
        for hl_ in data.get("height_limits", []) or []:
            try:
                pg_ = Polygon(hl_["polygon"])
            except Exception:
                continue
            if nm.split(" ")[0] in str(hl_.get("name", "")) and (got is None or pg_.symmetric_difference(shape).area < got[0].symmetric_difference(shape).area):
                got = (pg_, hl_.get("max_height"), hl_.get("name"))
        ok_ = got is not None and got[0].symmetric_difference(shape).area < 0.05 and abs(float(got[1]) - hmax) < 1e-6
        grow_.append(dict(item=f"height limit {nm}: bounds, limit", board_file=(f"{tuple(round(v, 2) for v in got[0].bounds)}, {got[1]} ({got[2]})" if got else "not in the file"),
                          yaml=f"{tuple(round(v, 2) for v in shape.bounds)}, {hmax}", status="ok" if ok_ else "DIFFERS (warning)"))
        if not ok_:
            warns.append(f"height limit '{nm}' stated in the board file " + (f"is {tuple(round(v, 2) for v in got[0].bounds)} / {got[1]} mm" if got else "is missing")
                         + f"; the YAML zone is {tuple(round(v, 2) for v in shape.bounds)} / {hmax} mm. This check applied the YAML zone to every part; the layout tool did not")
    vk = P.VIA_KEEPOUTS
    need(f"grain opening: no via inside dia {vk['grain_opening']['dia']} at ({vk['grain_opening']['x']}, {vk['grain_opening']['y']})",
         Point(vk["grain_opening"]["x"], vk["grain_opening"]["y"]).buffer(vk["grain_opening"]["dia"] / 2, 128), ("no_vias",))
    need(f"pad slot: no via inside {vk['pad_slot']['length']} x {vk['pad_slot']['width']} at y {vk['pad_slot']['y']}",
         _stadium(vk["pad_slot"]["length"], vk["pad_slot"]["width"], 0.0, vk["pad_slot"]["y"]), ("no_vias",))

    n_bot = len(drow)
    notes += [f"board file: {source}; design {data.get('design')!r}, revision {data.get('revision')!r}, {len(comps)} components ({n_top} fitted bodies on the top side, {n_bot} bodies or pad rows on the bottom side, "
              f"{len(brow)} copper-only footprints besides the contact row and the battery tabs)",
              "copper-only footprints (body height 0 and no BOM line in the file: fiducials, test pads, ball-foot lands) are not part bodies. Bottom side: a ball-foot land must sit on a YAML foot "
              f"zone (+-{LAND_TOL}) with the YAML land diameter, one per foot; other bare copper must lie under the adhesive sheet, outside the grain opening, the pad slot and the ball-foot zones. Top "
              "side: every plan-view rule of a part applies; only the distance to the tub solid and to the tail, which need a body, is not taken. The 'not fitted' mark does not exempt copper. A "
              "component with a body height of 0 that has a BOM line fails on either side",
              f"J1 (E24) is compared by its body box (corner points of the file) and height with the YAML body (x {P.J1_BOX[0]} to {P.J1_BOX[2]}, y {P.J1_BOX[1]} (mouth) to {P.J1_BOX[3]}, {P.J1['h']} high), by "
              f"body.cx / cy, and by its footprint anchor with YAML `anchor` {P.J1.get('anchor')}; the battery keep-out must be battery.body less battery.board_keepout_notch "
              f"(x {P.BAT_NOTCH['x']}, y {P.BAT_NOTCH['y']}: J1's courtyard strip)",
              "frame: board x, y = marker x, y (origin at the board centre); board z = 0 is the PCB underside, marker z = board z + %.2f" % P.PCB_Z0,
              f"top-side bodies are prisms on the corner points of the file from the PCB top (z {P.PCB_Z1}) to their height; distance to the tub solid by exact "
              f"B-rep minimum distance, required {PART_CLR} mm. Battery-lead pads are checked as joints {P.BAT_JOINT_H} mm tall",
              f"post feet: the YAML keep-out squares ({P.KO_POST_SIZE} mm, posts B {P.KO_LOC_SIZE} mm) with {POST_CLR} mm; hood zones: camera x +-{P.KO_HOOD_HW}, y {P.KO_HOOD_Y0} to "
              f"{P.KO_HOOD_Y1}, parts to {P.KO_HOOD_MAX_H} mm (camera exempt); free height {P.PCB_FREE_H} mm; ball-foot zones dia {P.FOOT_ZONE_D}",
              f"LCD flex tail: YAML tub_keepouts.lcd_tail (N10): no part taller than {P.KO_TAIL['max_part_height']} mm inside x +-{P.KO_TAIL['half_w']}, y {P.KO_TAIL['y'][0]} to {P.KO_TAIL['y'][1]} "
              f"(J1 exempt); in addition every top-side part except J1 must stay {FLEX_CLR} mm from the modelled tail (one U-fold behind the mouth of J1). The tail geometry is PROVISIONAL",
              f"ball-foot zones: no soldered part over a zone and none within {P.FOOT_PART_MARGIN} mm of it (YAML foot_zones.part_margin, N7); the battery body is exempt",
              "a component whose side is neither 'top' nor 'bottom' fails; parts marked DNP are tested like fitted parts and what they would violate is reported as a warning",
              f"bottom side: bodies must lie inside the grain opening (dia {P.GRAIN_D} at ({P.GRAIN_X}, {P.GRAIN_Y})) or the pad slot ({P.PAD_SLOT_L} x {P.PAD_HOLE_D} at y {P.PAD_Y}); "
              "a contact-row footprint is tested by its round pads, not by its body rectangle",
              "the file lists keep-outs but no copper: that the foot zones are free of tracks and vias and carry an unmasked land must be confirmed on the board itself"]
    passed = not fails
    summary = (f"board {data.get('design')} agrees with the YAML outline, hole and slot; {n_top} top-side parts clear the tub by {d_tub_min[0]:.2f} mm or more ({d_tub_min[1]}) and respect "
               f"post feet, hood zones, free height and foot zones; J1 body box and anchor on the YAML (mouth y {P.J1_MOUTH_Y}); {n_bot} bottom-side parts inside the grain opening or the pad slot; "
               f"{len(brow)} copper-only footprints by their own rules ({len(lands)} ball-foot lands on their feet); {len(prow_)} contact pads on the cradle pin axes"
               if passed else f"FAILED ({len(fails)}): " + "; ".join(fails[:12]) + (" ..." if len(fails) > 12 else ""))
    return dict(passed=passed, skipped=False, summary=summary, notes=notes, warnings=warns, fails=fails,
                tables=[dict(title="A. Board outline, thickness, hole and slot against the YAML", rows=arow),
                        dict(title="B. Top-side parts against the tub solid and the keep-out contract", rows=trow),
                        dict(title="C. Fixed mechanical interfaces", rows=crow),
                        dict(title="D. Bottom-side parts against the grain opening and the pad slot", rows=drow),
                        dict(title="Copper-only footprints (no body; both sides)", rows=brow),
                        dict(title="G. What the board file states about itself (differences are warnings)", rows=grow_),
                        dict(title="E. Contact pads against the cradle pins", rows=prow_),
                        dict(title="F. Bottom-side keep-outs the YAML asks for", rows=frow),
                        dict(title="Keep-outs listed in the board file", rows=krow)])


# ----------------------------------------------------------------------------------------------
# cradle board (check 19)
# ----------------------------------------------------------------------------------------------
CRADLE_ORIGIN = (0.0, 0.5 * (P.CPCB_Y0 + P.CPCB_Y1))       # centre of the cradle board in the marker frame (board frame: origin at its centre)


def synthetic_cradle_board():
    """A cradle board file of the toolchain's format that follows the YAML cradle block and the model exactly (self-test fixture)."""
    hx, hy, t = P.CPCB_SIZE[0] / 2, P.CPCB_SIZE[1] / 2, P.CPCB_SIZE[2]
    oy = CRADLE_ORIGIN[1]
    cs = [[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]]
    comps = []
    uw, ud, uh = M["usb"]
    comps.append(_comp("J1", "top", 0.0, P.USB_Y0 + ud / 2 - oy, uw, ud, uh, "yaml:USB_C_Receptacle", t=t))
    for i, x in enumerate(P.PAD_XS):
        c = _comp(f"SP{i + 1}", "top", x, P.PAD_Y - oy, M["pin_body_dia"], M["pin_body_dia"], M["pin_max_working_h"], "gleda:MillMax_0914_TH_PROVISIONAL", t=t)
        c["dnp"] = i >= len(P.PINS_CONSUMER)
        comps.append(c)
    comps.append(_comp("U1", "bottom", -2.0, 0.6, 1.6, 2.9, 1.45, "Package_TO_SOT_SMD:SOT-23-6", t=t))
    comps.append(_comp("FID1", "top", -11.0, 1.5, 2.0, 2.0, 0.0, "gleda:Fiducial_1mm_Mask2mm", t=t))
    holes = [dict(name=f"MH{k + 1}", x=sg * sx, y=sy - oy, diameter=M["cradle_screw_hole_dia"]) for k, (sg, (sx, sy)) in enumerate((sg, q) for q in P.CPCB_SCREWS for sg in (-1, 1))]
    return dict(design="gl1_cradle_synthetic_from_yaml", revision=str(P.REV), units="mm", frame="origin = board centre; +x right, +y up seen from the top; z = 0 bottom surface",
                board=dict(thickness=t, copper_layers=2, bounds=[-hx, -hy, hx, hy],
                           edge_contours=[[dict(type="line", start=cs[i], end=cs[(i + 1) % 4]) for i in range(4)]], outline_polygon=cs, outline_polygon_holes=[],
                           outline_tolerance=0.01, cutouts=[], npth_holes=holes),
                keepouts=[], height_limits=[], max_height=dict(top=M["pin_max_working_h"], bottom=1.45), components=comps)


def seeded_cradle(defect):
    """synthetic_cradle_board() with one defect: 'thick_board' (1.6 mm, the rev D board), 'pin_row_shifted', 'screw_hole_moved',
    'usb_moved', 'part_on_top' (a part on the face that lies against the pocket ceiling), 'wrong_pins_fitted', 'outline_wide',
    'bottom_part_under_screw_head'."""
    d = copy.deepcopy(synthetic_cradle_board())

    def shift(c, dx=0.0, dy=0.0):
        c["x"] += dx; c["y"] += dy; c["body"]["cx"] += dx; c["body"]["cy"] += dy
        for p in c["body"]["corners"]:
            p[0] += dx; p[1] += dy
    if defect == "thick_board":
        d["board"]["thickness"] = 1.6
    elif defect == "pin_row_shifted":
        for c in d["components"]:
            if c["ref"].startswith("SP"):
                shift(c, dy=0.3)
    elif defect == "screw_hole_moved":
        d["board"]["npth_holes"][0]["x"] += 0.5
    elif defect == "usb_moved":
        shift(next(c for c in d["components"] if c["ref"] == "J1"), dy=0.5)
    elif defect == "part_on_top":
        d["components"].append(_comp("C901", "top", 5.0, -2.0, 1.0, 0.5, 0.55, "seeded:C_0402", t=d["board"]["thickness"]))
    elif defect == "wrong_pins_fitted":
        for c in d["components"]:
            if c["ref"] in ("SP1", "SP7"):
                c["dnp"] = not c["dnp"]
    elif defect == "outline_wide":
        hx, hy = P.CPCB_SIZE[0] / 2 + 0.4, P.CPCB_SIZE[1] / 2
        cs = [[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]]
        d["board"].update(bounds=[-hx, -hy, hx, hy], outline_polygon=cs, edge_contours=[[dict(type="line", start=cs[i], end=cs[(i + 1) % 4]) for i in range(4)]])
    elif defect == "bottom_part_under_screw_head":
        sx, sy = P.CPCB_SCREWS[0]
        d["components"].append(_comp("C902", "bottom", sx - 1.2, sy - CRADLE_ORIGIN[1], 1.0, 0.5, 0.55, "seeded:C_0402", t=d["board"]["thickness"]))
    else:
        raise ValueError(defect)
    return d


def check_cradle_board(parts, path=None, data=None):
    """The cradle board file against the YAML cradle block and the cradle model: see the module docstring."""
    path = pathlib.Path(path or CRADLE_BOARD_FILE)
    if data is None:
        if not path.exists():
            return dict(passed=True, skipped=True, summary="skipped: no cradle board file", tables=[], warnings=[], fails=[],
                        notes=[f"looked for {path} (written by the board toolchain)"])
        try:
            data = load(path)
        except Exception as ex:
            return dict(passed=False, skipped=False, summary=f"FAILED: cradle board file unreadable: {ex!r}", tables=[], notes=[str(path)], warnings=[], fails=["unreadable"])
        source = str(path)
    else:
        source = f"data passed in ({data.get('design', '?')})"
    fails, warns, rows = [], [], []
    ox, oy = CRADLE_ORIGIN
    brd = data["board"]
    comps = list(data.get("components", []))
    cradle = A.solid_of(parts["cradle"])
    ycp = P.Y["cradle"]["pcb"]

    def cmp(item, got, want, tol=TOL_XY, note=""):
        ok = got is not None and len(_tup(got)) == len(_tup(want)) and all(abs(g - w) <= tol for g, w in zip(_tup(got), _tup(want)))
        if not ok:
            fails.append(f"{item}: board {_fmt(got)}, model / YAML {_fmt(want)}")
        rows.append(dict(item=item, board_file=_fmt(got), model_or_yaml=_fmt(want), tolerance_mm=tol, status="ok" if ok else "FAIL", note=note))
        return ok
    # ---- A: thickness and outline
    cmp("board thickness", brd.get("thickness"), ycp["thickness"], 1e-6,
        note=f"YAML cradle.pcb.thickness (E36: 1.0, so that the {P.PIN_TAIL_L} mm pin tail comes {P.PIN_TAIL_THROUGH} through); the TOP face stays at z {P.CPCB_Z1}, the underside is at z {P.CPCB_Z0:.3f}")
    b_ = brd.get("bounds")
    cmp("outline bounds in the marker frame (x min, y min, x max, y max)", (b_[0] + ox, b_[1] + oy, b_[2] + ox, b_[3] + oy) if b_ else None, (-P.CPCB_HX, P.CPCB_Y0, P.CPCB_HX, P.CPCB_Y1),
        note=f"board frame origin = board centre = marker ({ox}, {oy}); YAML cradle.pcb x, y")
    outer = (brd.get("edge_contours") or [[]])[0]
    try:
        op = Polygon(brd["outline_polygon"])
        want = sbox(-P.CPCB_SIZE[0] / 2, -P.CPCB_SIZE[1] / 2, P.CPCB_SIZE[0] / 2, P.CPCB_SIZE[1] / 2)
        cmp("outline: number of straight edges, other elements, area that differs from the YAML rectangle (mm2)",
            (sum(1 for e in outer if e.get("type") == "line"), sum(1 for e in outer if e.get("type") != "line"), op.symmetric_difference(want).area), (4, 0, 0.0), 0.05,
            note=f"rectangle {P.CPCB_SIZE[0]} x {P.CPCB_SIZE[1]} in a pocket {P.CPCB_SIZE[0] + 2 * P.CLR} x {P.CPCB_SIZE[1] + 2 * P.CLR}")
    except Exception as ex:
        fails.append(f"cradle outline polygon unreadable: {ex!r}")
    cmp("cut-outs and openings other than the screw holes", len(brd.get("cutouts") or []) + len(brd.get("outline_polygon_holes") or []), 0, 0)
    # ---- B: screw holes
    holes = list(brd.get("npth_holes") or [])
    want_s = sorted((sg * sx, sy) for sx, sy in P.CPCB_SCREWS for sg in (-1, 1))
    cmp("number of non-plated holes (four screw holes)", len(holes), len(want_s), 0)
    used = set()
    for k, (wx, wy) in enumerate(want_s):
        best = min(((math.hypot(h_["x"] + ox - wx, h_["y"] + oy - wy), j) for j, h_ in enumerate(holes) if j not in used), default=(None, None))
        h_ = holes[best[1]] if best[1] is not None else None
        if h_ is not None:
            used.add(best[1])
        cmp(f"screw hole {k + 1}: x, y in the marker frame, diameter", (h_["x"] + ox, h_["y"] + oy, h_["diameter"]) if h_ else None, (wx, wy, M["cradle_screw_hole_dia"]),
            note="YAML cradle.pcb.screws; spot marks of the cradle body at the same positions (drawing GL1-020); hole diameter as modelled (clearance for M2)")
    # ---- C: spring pins
    pins = sorted((c for c in comps if c.get("side") == "top" and ("millmax" in c.get("footprint", "").lower() or c["ref"].upper().startswith("SP"))), key=lambda c: c["x"])
    mpins = sorted((A.bbox_of(parts[n]) for n in parts if n.startswith("spring_pin_")), key=lambda bb: bb[0])
    cmp("number of spring-pin positions", len(pins), len(P.PAD_XS), 0, note="YAML cradle.pins.positions = the pad row of the marker")
    for k, c in enumerate(pins[:len(P.PAD_XS)]):
        bd = c["body"]
        mx, my = (0.5 * (mpins[k][0] + mpins[k][3]), 0.5 * (mpins[k][1] + mpins[k][4])) if k < len(mpins) else (float("nan"), float("nan"))
        cmp(f"spring pin {k + 1} ({c['ref']}): x, y in the marker frame; offset from the modelled pin axis", (c["x"] + ox, c["y"] + oy, math.hypot(c["x"] + ox - mx, c["y"] + oy - my)),
            (P.PAD_XS[k], P.PIN_ROW_Y, 0.0), PIN_TOL, note="YAML base_plate.pad_holes.xs / cradle.pin_row_y; the pad is dia %.1f, the plunger dia %.2f" % (M["pad_dia"], M["pin_plunger_dia"]))
        cmp(f"spring pin {k + 1} ({c['ref']}): barrel diameter, free height above the board", (max(bd.get("length") or 0, bd.get("width") or 0), bd.get("height")), (M["pin_body_dia"], M["pin_max_working_h"]),
            note="model envelope of the Mill-Max 0914 pin (PROVISIONAL): working height + compression")
    fitted = sorted(round(c["x"] + ox, 3) for c in pins if not c.get("dnp"))
    want_f = sorted(round(x, 3) for x in P.PAD_XS[:len(P.PINS_CONSUMER)])
    ok_f = fitted == want_f
    rows.append(dict(item="pins fitted on the consumer board (x of the fitted positions)", board_file=str(fitted), model_or_yaml=str(want_f) + " = " + ", ".join(P.PINS_CONSUMER), tolerance_mm=0,
                     status="ok" if ok_f else "FAIL", note="YAML cradle.pins.populated_consumer; the other three are fitted in the factory fixture only"))
    if not ok_f:
        fails.append(f"pins fitted at x {fitted}, YAML populated_consumer is x {want_f}")
    # ---- D: USB receptacle
    usb = next((c for c in comps if c.get("side") == "top" and "usb" in c.get("footprint", "").lower()), None)
    mu = A.bbox_of(parts["usb_receptacle"])
    ub = None
    if usb is not None:
        try:
            bx = Polygon(usb["body"]["corners"]).bounds
            ub = (bx[0] + ox, bx[1] + oy, bx[2] + ox, bx[3] + oy, float(usb["body"]["height"]))
        except Exception:
            ub = None
    cmp("USB-C receptacle body: x min, y min (the mouth), x max, y max in the marker frame, height", ub, (mu[0], mu[1], mu[3], mu[4], mu[5] - mu[2]),
        note=f"modelled receptacle (usb_receptacle solid; envelope {M['usb']} PROVISIONAL); mouth at YAML cradle.pcb.usb_mouth_y {P.USB_Y0}, {P.USB_Y0 - P.CRADLE_Y0:.1f} inside the rear face of the body")
    # ---- E: the top face lies against the pocket ceiling; bodies against the cradle solid
    prow = []
    for c in comps:
        if c.get("side") not in ("top", "bottom"):
            fails.append(f"{c.get('ref')}: side {c.get('side')!r} is neither 'top' nor 'bottom'")
            continue
        bd = c.get("body") or {}
        hgt = bd.get("height")
        bare = copper_only(c)
        why = []
        if hgt is None or not c.get("height_known", True):
            why.append("height unknown: cannot be verified"); hgt = 0.0
        hgt = float(hgt)
        if hgt == 0.0 and not bare:
            why.append("in the BOM with a body height of 0: a part without a body cannot be verified")
        pg = sbox(*Polygon(bd["corners"]).bounds) if bd.get("corners") else sbox(*c["courtyard_bbox"])
        pgm = sbox(pg.bounds[0] + ox, pg.bounds[1] + oy, pg.bounds[2] + ox, pg.bounds[3] + oy)
        d_body = None
        is_pin, is_usb = c in pins, c is usb
        if c["side"] == "top":
            if hgt > 0 and not (is_pin or is_usb):
                why.append(f"a {hgt} mm part on the top face: the board lies against the pocket ceiling (only the receptacle and the pins pass through it)")
            if hgt > 0 and (is_pin or is_usb):
                solid = (cq.Workplane("XY").workplane(offset=P.CPCB_Z1).center(c["x"] + ox, c["y"] + oy).circle(max(bd.get("length") or 0, bd.get("width") or 0) / 2).extrude(hgt).val() if is_pin
                         else _prism(pgm, P.CPCB_Z1 + 0.001, P.CPCB_Z1 + hgt))
                d_body = _min_distance(solid, cradle)
                if not d_body >= PART_CLR - 2e-3:
                    why.append(f"{d_body:.3f} mm to the cradle body (< {PART_CLR})")
            where = "top (against the pocket ceiling)"
        else:
            z_low = P.CPCB_Z0 - hgt
            for sx, sy in P.CPCB_SCREWS:
                for sg in (-1, 1):
                    d_h = Point(sg * sx, sy).buffer(M["cradle_screw_head_dia"] / 2, 64).distance(pgm)
                    if d_h <= 0 and not (bare and bare_kind(c) == "other"):
                        why.append(f"under the head of the screw at ({sg * sx}, {sy}) (head dia {M['cradle_screw_head_dia']}, PROVISIONAL)")
            if z_low < P.CRADLE_BOT_Z + 1e-9:
                why.append(f"reaches z {z_low:.2f}, below the underside of the cradle body ({P.CRADLE_BOT_Z})")
            where = f"bottom (lowest point z {z_low:.3f}; body underside {P.CRADLE_BOT_Z}, feet {M['foot_h'] - M['foot_pocket_depth']:.1f} lower)"
        inside = sbox(-P.CPCB_HX, P.CPCB_Y0, P.CPCB_HX, P.CPCB_Y1).buffer(1e-6).contains(pgm) or is_usb
        if not inside:
            why.append("body outside the board outline")
        dnp = bool(c.get("dnp")) and not bare
        if why and dnp and not (is_pin or is_usb):
            warns.append(f"{c['ref']} is marked not fitted; if it were fitted: " + "; ".join(why))
        elif why:
            fails.append(f"{c['ref']}: " + "; ".join(why))
        prow.append(dict(ref=c["ref"], footprint=c.get("footprint", ""), side=where, x_marker=R3(c["x"] + ox), y_marker=R3(c["y"] + oy), body_mm=f"{bd.get('length')} x {bd.get('width')} x {hgt}",
                         copper_only=bare, not_fitted=bool(c.get("dnp")), to_cradle_body_mm=R3(d_body), status=("ok" if not why else ("WOULD FAIL if fitted (warning)" if dnp and not (is_pin or is_usb) else "FAIL")),
                         reasons="; ".join(why)))
    stamp = str(data.get("revision"))
    if stamp != str(P.REV):
        warns.append(f"the cradle board file is stamped {stamp}; master_params.yaml is {P.REV}: the board was built on an older YAML (rebuild it)")
    notes = [f"cradle board file: {source}; design {data.get('design')!r}, revision {stamp!r}, {len(comps)} components",
             f"frame: marker x, y = board x, y + ({ox}, {oy}) (the board centre; YAML cradle.pcb.x / y); z datum = the TOP face of the board at z {P.CPCB_Z1} (YAML cradle.pcb.top_z), which sets the "
             f"pin height ({P.PIN_WORK_H} working on the pad face z {P.PAD_Z0}) and does not move with the board thickness (E36)",
             f"the board is screwed against the pocket ceiling from below (4 x M2 x {M['cradle_screw_len']:g}, {P.SCREW_ENGAGE:.1f} mm of thread in the body), so nothing but the receptacle and the pins may stand on the top face; "
             f"their bodies are tested against the cradle solid ({PART_CLR} mm; pins as cylinders at their FREE height {M['pin_max_working_h']})",
             "NOT in the board file and therefore not checked here: the plated hole and the tail diameter of the spring pins (model: tail dia %.2f in a dia %.2f hole; the electrical footprint is "
             "PROVISIONAL and uses other numbers), and the solder side of the receptacle. Both stay open until the Mill-Max and GCT drawings are read" % (M["pin_tail_dia"], M["pin_tail_dia"] + 0.14)]
    passed = not fails
    summary = (f"cradle board {data.get('design')}: thickness {brd.get('thickness')}, outline {P.CPCB_SIZE[0]} x {P.CPCB_SIZE[1]}, four screw holes, seven spring pins on the pad row and on the modelled pin axes "
               f"({len(fitted)} fitted), USB-C receptacle on the modelled receptacle, nothing else on the top face" if passed
               else f"FAILED ({len(fails)}): " + "; ".join(fails[:10]) + (" ..." if len(fails) > 10 else ""))
    return dict(passed=passed, skipped=False, summary=summary, notes=notes, warnings=warns, fails=fails,
                tables=[dict(title="Cradle board against the YAML cradle block and the cradle model", rows=rows), dict(title="Components of the cradle board", rows=prow)])


def _tup(v):
    return tuple(v) if isinstance(v, (list, tuple)) else (v,)


def _fmt(v):
    if v is None:
        return "missing"
    if isinstance(v, (list, tuple)):
        return "(" + ", ".join(f"{float(x):g}" if isinstance(x, (int, float)) else str(x) for x in (round(float(q), 4) for q in v)) + ")"
    return f"{round(float(v), 4):g}" if isinstance(v, (int, float)) else str(v)


if __name__ == "__main__":
    import sys
    args = [a_ for a_ in sys.argv[1:] if a_ != "--cradle"]
    ps = A.build_parts(alt=False)
    fn = check_cradle_board if "--cradle" in sys.argv[1:] else check_board
    r = fn(ps, path=args[0] if args else None)
    print(("PASS" if r["passed"] else "FAIL"), r["summary"])
    for f_ in r.get("fails", []):
        print("  FAIL:", f_)
    for w in r["warnings"]:
        print("  warning:", w)
    sys.exit(0 if r["passed"] else 1)
