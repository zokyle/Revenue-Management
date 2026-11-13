"""GL-1 board import: the real circuit board against the mechanical model (rev D as amended, for the integration step).

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
  C  the fixed mechanical interfaces are where the YAML has them: both cameras, the LCD connector J1, the battery body;
  D  nothing on the bottom side lies outside the grain opening or the pad slot, and what is inside the grain opening
     clears the baffle ring and the wall and is covered by the potting;
  E  the contact pads line up with the cradle pins (YAML pad row and the modelled spring pins);
  F  the bottom-side keep-outs of the YAML (ball-foot zones, via keep-outs of the wetted areas) exist in the file
     (reported as warnings when they are not found: the file only lists keep-outs, not copper).

synthetic_board() builds a board file of the same format from the YAML part list (a conforming board); the self-test
uses it and seeds defects into it.  It is a test fixture, not a board.
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
DEMO_FILE = P.MECH_DIR.parent / "electrical" / "tools" / "demo" / "demo_out" / "greenline_demo-mechanical.json"
PART_CLR = 0.2            # required clearance of a top-side part body to the tub solid
POST_CLR = 0.2            # and to a post-foot keep-out square (design/check_layout.py uses the same number)
BOTTOM_CLR = 0.2          # bottom-side part to the baffle ring and to the wall of the grain opening
TOL_XY = 0.02             # position / size agreement with the YAML
OUTLINE_TOL_MAX = 0.05    # the polygon tolerance a board file may state for itself is capped at this
FLEX_CLR = 0.2            # top-side part to the (representative) LCD flex tail; the connector J1 is exempt
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
def _comp(ref, side, x, y, length, width, height, footprint, rot=0.0, value=""):
    a = math.radians(rot)
    ca, sa = math.cos(a), math.sin(a)
    cs = [[round(x + u * ca - v * sa, 4), round(y + u * sa + v * ca, 4)] for u, v in ((-length / 2, -width / 2), (length / 2, -width / 2), (length / 2, width / 2), (-length / 2, width / 2))]
    xs, ys = [p[0] for p in cs], [p[1] for p in cs]
    t = P.PCB_T
    z0, z1 = (t, t + height) if side == "top" else (-height, 0.0)
    return dict(ref=ref, value=value, footprint=footprint, mpn="", x=x, y=y, rot=rot, side=side,
                body=dict(length=length, width=width, height=height, cx=x, cy=y, corners=cs), z_min=round(z0, 4), z_max=round(z1, 4),
                courtyard_bbox=[min(xs), min(ys), max(xs), max(ys)], height_known=True, dnp=False, in_bom=True)


def _ring(poly):
    return [[round(x, 4), round(y, 4)] for x, y in list(poly.exterior.coords)[:-1]]


def synthetic_board():
    """A board file of the toolchain's format that follows the rev D YAML exactly: outline, hole and slot, the YAML
    top-side parts (the battery body is a keep-out, its two lead pads are components), the LED ring, the photodiode and
    the contact row on the bottom side, and the keep-outs of the contract."""
    xc = math.sqrt(P.PCB_R ** 2 - P.PCB_FLAT ** 2)
    outline = _dshape(P.PCB_R, P.PCB_FLAT, 1024)
    sx, sy, sd, sl = P.LOC_SLOT
    h = (sl - sd) / 2
    comps = []
    for p in P.TOP_PARTS:
        if p["ref"] == "BT1":
            continue
        comps.append(_comp(p["ref"], "top", p["x"], p["y"], p["dx"], p["dy"], p["h"], "yaml:" + p["name"], value=p["name"]))
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
    keep.append(dict(name="battery_body", layers=["F.Cu"], no_tracks=False, no_vias=False, no_copper=False, no_footprints=True,
                     polygon=_ring(sbox(b["x"] - b["dx"] / 2, b["y"] - b["dy"] / 2, b["x"] + b["dx"] / 2, b["y"] + b["dy"] / 2))))
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
                keepouts=keep, height_limits=hl,
                max_height=dict(top=max(c["body"]["height"] for c in comps if c["side"] == "top"), bottom=max(c["body"]["height"] for c in comps if c["side"] == "bottom")),
                components=comps)


def seeded(defect):
    """synthetic_board() with one defect, for the self-test: 'tall_under_hood', 'part_on_post_foot', 'part_over_foot_zone',
    'hole_moved', 'pads_shifted', 'bottom_part_outside', 'part_near_foot_zone' (N7), 'tall_in_tail_zone' (N10), and the
    malformed or edge-case boards 'outline_rectangle' (same bounds, no arc, stated tolerance 10), 'bad_side',
    'polygon_hole_only', 'part_in_tail_path', 'dnp_tall_under_hood' (the last one must PASS with a warning)."""
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
        j1 = next(q for q in P.TOP_PARTS if q["ref"] == "J1")
        d["components"].append(_comp("C905", "top", 0.0, j1["y"] - j1["dy"] / 2 - 0.7, 1.0, 0.5, 2.5, "seeded:tall"))
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
                               "states its own tolerance, a part on an unknown side, an opening listed only as a polygon hole and a part in the path of the LCD tail are each caught"])
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
    flex = S.get("lcd_flex")
    tabs = [(c["ref"], body_polygon(c)) for c in comps if c.get("side") == "top" and _is_battery_tab(c)]
    for c in comps:
        if c.get("side") != "top":
            continue
        why = []
        ref = c["ref"]
        dnp = bool(c.get("dnp"))
        n_top += 0 if dnp else 1
        pg = body_polygon(c)
        hgt = c["body"].get("height")
        tab = _is_battery_tab(c)
        is_cam = ref in cams.values()
        if hgt is None or not c.get("height_known", True):
            why.append("height unknown: cannot be verified")
            hgt = P.PCB_FREE_H
        hgt = float(hgt)
        h_eff = P.BAT_JOINT_H if tab else hgt                 # a lead pad carries a joint up to the YAML joint height
        solid = _prism(pg, P.PCB_Z1, P.PCB_Z1 + max(h_eff, 0.01))
        d_tub = _min_distance(solid, tub)
        if d_tub < d_tub_min[0] and not dnp:
            d_tub_min = (d_tub, ref)
        d_flex = None
        if flex is not None and c is not j1c and not tab:
            d_flex = _min_distance(solid, flex)
            if d_flex < FLEX_CLR - 2e-3:
                why.append(f"{d_flex:.3f} mm to the LCD flex tail (< {FLEX_CLR}; representative tail shape, PROVISIONAL)")
        if not tab:
            for tref, tpg in tabs:
                if tpg.intersection(pg).area > 1e-6:
                    why.append(f"on battery lead pad {tref}")
        if not d_tub >= PART_CLR - 2e-3:
            why.append(f"{d_tub:.3f} mm to the tub (< {PART_CLR})")
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
    j1y = next(p for p in P.TOP_PARTS if p["ref"] == "J1")
    j1 = j1c
    fixed("LCD connector J1: x, y", (j1["x"], j1["y"]) if j1 else None, (j1y["x"], j1y["y"]))
    bk = next((k for k in data.get("keepouts", []) if "battery" in k.get("name", "").lower()), None)
    fixed("battery body keep-out: x min, y min, x max, y max", Polygon(bk["polygon"]).bounds if bk else None, bat_poly.bounds, required=False)

    # ---------------- D, E: bottom side and contact pads
    grain = Point(P.GRAIN_X, P.GRAIN_Y).buffer(P.GRAIN_R, 256)
    slot = _stadium(P.PAD_SLOT_L, P.PAD_HOLE_D, 0.5 * (P.PAD_XS[0] + P.PAD_XS[-1]), P.PAD_Y, 128)
    ring = Point(P.GRAIN_X, P.GRAIN_Y).buffer(P.BAFFLE_RO, 256).difference(Point(P.GRAIN_X, P.GRAIN_Y).buffer(P.BAFFLE_RI, 256))
    drow, prow_, pads = [], [], []
    for c in comps:
        if c.get("side") != "bottom" or c.get("dnp"):
            continue
        why = []
        hgt = float(c["body"].get("height") or 0.0)
        row_ = _contact_row(c)
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
            match = "battery body" + ("" if pg.symmetric_difference(bat_poly).area < 0.05 else ": DIFFERS from the YAML")
        for i, z in zones:
            if pg.buffer(0.03).contains(z):
                match = f"ball-foot zone {i}"
        if "DIFFERS" in match:
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
    vk = P.VIA_KEEPOUTS
    need(f"grain opening: no via inside dia {vk['grain_opening']['dia']} at ({vk['grain_opening']['x']}, {vk['grain_opening']['y']})",
         Point(vk["grain_opening"]["x"], vk["grain_opening"]["y"]).buffer(vk["grain_opening"]["dia"] / 2, 128), ("no_vias",))
    need(f"pad slot: no via inside {vk['pad_slot']['length']} x {vk['pad_slot']['width']} at y {vk['pad_slot']['y']}",
         _stadium(vk["pad_slot"]["length"], vk["pad_slot"]["width"], 0.0, vk["pad_slot"]["y"]), ("no_vias",))

    n_bot = len(drow)
    notes += [f"board file: {source}; design {data.get('design')!r}, revision {data.get('revision')!r}, {len(comps)} components ({n_top} fitted on the top side, {n_bot} on the bottom side)",
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
               f"post feet, hood zones, free height and foot zones; {n_bot} bottom-side parts inside the grain opening or the pad slot; {len(prow_)} contact pads on the cradle pin axes"
               if passed else f"FAILED ({len(fails)}): " + "; ".join(fails[:12]) + (" ..." if len(fails) > 12 else ""))
    return dict(passed=passed, skipped=False, summary=summary, notes=notes, warnings=warns, fails=fails,
                tables=[dict(title="A. Board outline, thickness, hole and slot against the YAML", rows=arow),
                        dict(title="B. Top-side parts against the tub solid and the keep-out contract", rows=trow),
                        dict(title="C. Fixed mechanical interfaces", rows=crow),
                        dict(title="D. Bottom-side parts against the grain opening and the pad slot", rows=drow),
                        dict(title="E. Contact pads against the cradle pins", rows=prow_),
                        dict(title="F. Bottom-side keep-outs the YAML asks for", rows=frow),
                        dict(title="Keep-outs listed in the board file", rows=krow)])


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
    ps = A.build_parts(alt=False)
    r = check_board(ps, path=sys.argv[1] if len(sys.argv) > 1 else None)
    print(("PASS" if r["passed"] else "FAIL"), r["summary"])
    for w in r["warnings"]:
        print("  warning:", w)
    sys.exit(0 if r["passed"] else 1)
