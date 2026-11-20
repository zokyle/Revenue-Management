#!/usr/bin/env python3
"""Plan-view and z-stack sanity checks for design/master_params.yaml, rev E (run: python3 check_layout.py).
Nothing was removed at rev E; the block "rev E additions" checks the keys that the amendments E17 to E36 added."""
import math, sys, itertools, yaml, pathlib
from shapely.geometry import Point, box, Polygon
P = yaml.safe_load(open(pathlib.Path(__file__).with_name("master_params.yaml")))
errs, notes = [], []
def dshape(r, flat_y):
    return Point(0, 0).buffer(r, 256).intersection(box(-r - 1, -r - 1, r + 1, flat_y))
def rect(c): return box(c["x"] - c["dx"] / 2, c["y"] - c["dy"] / 2, c["x"] + c["dx"] / 2, c["y"] + c["dy"] / 2)
env, pcb, lcd = P["envelope"], P["pcb"], P["lcd"]
R, W = env["outer_radius"], env["wall"]
inner = dshape(R - W, env["front_flat_y_outer"] - env["front_flat_wall"])
pcb_poly = dshape(pcb["radius"], pcb["flat_y"])
keep = pcb_poly.buffer(-pcb["component_edge_clearance"])
z_pcb_top = pcb["z_bottom"] + pcb["thickness"]
glass = rect(lcd["glass"])
if not inner.buffer(-0.25).contains(glass): errs.append("LCD glass does not fit inside the tub wall with 0.25 clearance")
else: notes.append(f"LCD glass corner margin to inner wall: {inner.exterior.distance(glass):.2f} mm")
parts = P["top_side_parts"]
for p in parts:
    r = rect(p)
    if not keep.contains(r): errs.append(f"{p['ref']} outside PCB keep-in by {r.difference(keep).area:.2f} mm^2")
    top = z_pcb_top + p["h"]
    if r.intersects(glass):
        lim = lcd["glass"]["z0"] - P["battery"]["foam_above"]
        extra = P["battery"]["swell_allowance"] if p["ref"] == "BT1" else 0.0
        if p["ref"] == "BT1": top = P["battery"]["body"]["z1"] + extra
        if top > lim + 1e-9: errs.append(f"{p['ref']} top z={top:.2f} exceeds under-LCD limit {lim:.2f}")
    elif p["h"] > P["tub_keepouts"]["free_height_above_pcb"] + 1e-9 and p["ref"] not in ("U2", "U3"):
        errs.append(f"{p['ref']} height {p['h']} exceeds the free height above the PCB ({P['tub_keepouts']['free_height_above_pcb']})")
for a, b in itertools.combinations(parts, 2):
    if rect(a).buffer(0.1).intersects(rect(b).buffer(0.1)):
        errs.append(f"{a['ref']} overlaps/too close to {b['ref']}")
cam, pr = P["cameras"], P["prisms"]
prism_top = z_pcb_top + cam["height"] + pr["bond_line"] + pr["leg"]
if prism_top > P["roof"]["prism_pocket_underside_z"] - 0.05: errs.append(f"prism top {prism_top:.2f} hits pocket roof")
if P["roof"]["prism_pocket_underside_z"] > env["thickness"] - env["min_printed_wall"] + 1e-9: errs.append("roof over prism thinner than the printed-wall minimum")
for side in ("left", "right"):
    c = cam[side]; pz = box(c["x"] - 1.2, c["y"] - 1.2, c["x"] + 1.2, c["y"] + 1.2)
    if pz.intersects(glass.buffer(0.5)): errs.append(f"prism pocket {side} too close to LCD glass")
    if pz.distance(Point(0, 0)) < P["cover_glass"]["recess_dia"] / 2 + 0.8: errs.append(f"prism pocket {side} too close to cover-glass recess")
ledge = env["thickness"] - P["cover_glass"]["recess_depth"] - (lcd["glass"]["z1"] + lcd["psa_thickness"])
if ledge < env['min_printed_wall'] - 1e-9: errs.append(f"cover-glass ledge only {ledge:.2f} mm thick")
notes.append(f"cover-glass ledge thickness: {ledge:.2f} mm")
notes.append(f"prism top z = {prism_top:.2f}; optical axis z = {z_pcb_top + cam['height'] + pr['bond_line'] + pr['leg']/2:.2f}")
notes.append(f"PCB area {pcb_poly.area:.0f} mm^2; top-side parts {sum(rect(p).area for p in parts):.0f} mm^2 "
             f"({100*sum(rect(p).area for p in parts)/pcb_poly.area:.0f} %)")
bp = P["base_plate"]
for x in bp["pad_holes"]["xs"]:
    if not pcb_poly.buffer(-1.0).contains(Point(x, bp["pad_holes"]["y"]).buffer(bp["pad_holes"]["dia"] / 2)):
        errs.append(f"pad hole at x={x} too close to PCB edge")
for fx, fy in bp["feet"]["positions"]:
    if not dshape(bp["radius"], bp["flat_y"]).buffer(-1.5).contains(Point(fx, fy)): errs.append(f"foot at {fx},{fy} too close to base edge")
cav = Point(bp["grain_cavity"]["x"], bp["grain_cavity"]["y"]).buffer(bp["grain_cavity"]["dia"] / 2)
for x in bp["pad_holes"]["xs"]:
    if cav.distance(Point(x, bp["pad_holes"]["y"])) < 3: errs.append("pad hole too close to grain cavity")
# --- rev C additions -------------------------------------------------------------------------
# base plate + adhesive sheet must end exactly at the PCB underside
if abs(bp["thickness"] + bp["psa"]["thickness"] - pcb["z_bottom"]) > 1e-6:
    errs.append(f"base {bp['thickness']} + adhesive {bp['psa']['thickness']} != PCB bottom z {pcb['z_bottom']}")
# PCB edge to the tub seating ledge
gap = P["tub_ledge"]["r_inner"] - pcb["radius"]
if gap < env["fit_clearance"] - 1e-9: errs.append(f"PCB edge to tub ledge only {gap:.2f} mm")
notes.append(f"PCB edge to tub ledge: {gap:.2f} mm")
# pad slot: webs to the PCB edge and the base edge
ph = bp["pad_holes"]
slot = box(-ph["slot_length"] / 2, ph["y"] - ph["dia"] / 2, ph["slot_length"] / 2, ph["y"] + ph["dia"] / 2)
base_poly = dshape(bp["radius"], bp["flat_y"])
web = base_poly.exterior.distance(slot)
if web < 1.5: errs.append(f"pad slot only {web:.2f} mm from the base edge")
notes.append(f"pad slot to base edge: {web:.2f} mm; slot covers pads to x = +-{max(ph['xs']) + 0.9:.2f} of +-{ph['slot_length']/2:.2f}")
if ph["slot_length"] / 2 < max(ph["xs"]) + 0.9: errs.append("pad slot shorter than the pad row")
# ball feet: through holes clear of the slot, the grain opening and each other's webs
for fx, fy in bp["feet"]["positions"]:
    hole = Point(fx, fy).buffer(bp["feet"]["hole_dia"] / 2)
    for name, other in (("pad slot", slot), ("grain opening", cav)):
        if hole.distance(other) < 2.0: errs.append(f"foot hole at {fx},{fy} within 2 mm of the {name}")
    if bp["feet"]["ball_dia"] - bp["feet"]["protrusion"] > pcb["z_bottom"] - 0.05:
        errs.append("ball top reaches the PCB underside")
# grain baffle against the LED ring (0402 LEDs, long side radial: +-0.5 mm)
led = P["bottom_side_parts"]["grain_led_ring"]; baf = bp["baffle"]
if led["radius"] - 0.5 - baf["outer_dia"] / 2 < 0.5: errs.append("grain baffle within 0.5 mm of the LED ring")
if led["radius"] + 0.5 > bp["grain_cavity"]["dia"] / 2 - 0.5: errs.append("LED ring within 0.5 mm of the grain-opening wall")
for a in baf["spokes_deg"]:
    d = min(abs(((a - (led["first_azimuth_deg"] + led["step_deg"] * k)) + 180) % 360 - 180) for k in range(led["count_pairs"]))
    if d < 15: errs.append(f"baffle spoke at {a} deg is only {d:.1f} deg from an LED")
pd = P["bottom_side_parts"]["photodiode"]
if math.hypot(pd["dx"], pd["dy"]) > baf["inner_dia"] - 0.4: errs.append("photodiode diagonal does not fit inside the baffle ring")
# tub posts and camera hoods against the top-side parts; PCB locating holes
ko = P["tub_keepouts"]; pf = ko["post_feet"]
post_list = [(c, pf["size"]) for c in pf["centres"]] + [(c, pf["locating"]["size"]) for c in pf["locating"]["centres"]]
post_boxes = []
for (cx, cy), size in post_list:
    half = size / 2
    foot = box(cx - half, cy - half, cx + half, cy + half); post_boxes.append(foot)
    if not pcb_poly.buffer(-0.1).contains(foot): errs.append(f"post foot at {cx},{cy} is not on the PCB")
    for p_ in parts:
        if foot.buffer(0.2).intersects(rect(p_)): errs.append(f"post foot at {cx},{cy} clashes with {p_['ref']}")
for a, b in itertools.combinations(post_boxes, 2):
    if a.intersects(b): errs.append("two post feet overlap")
# ball-foot zones: no soldered part above a foot (the battery may lie over the rear feet); consistent with base_plate.feet
fz = ko["foot_zones"]
if sorted(map(tuple, fz["positions"])) != sorted(map(tuple, bp["feet"]["positions"])): errs.append("tub_keepouts.foot_zones differ from base_plate.feet.positions")
if abs(fz["dia"] - bp["feet"]["pcb_keepout_dia"]) > 1e-9: errs.append("foot zone diameter differs from base_plate.feet.pcb_keepout_dia")
for fx, fy in fz["positions"]:
    zone = Point(fx, fy).buffer(fz["dia"] / 2, 64)
    if not pcb_poly.buffer(-0.3).contains(Point(fx, fy).buffer(fz["land_dia"] / 2)): errs.append(f"foot land at {fx},{fy} is not on the PCB")
    for p_ in parts:
        if p_["ref"] != "BT1" and zone.buffer(fz.get("part_margin", 0.0)).intersects(rect(p_)): errs.append(f"{p_['ref']} sits over (or within the margin of) the ball foot at {fx},{fy}")
    for b_ in post_boxes:
        if zone.intersects(b_): errs.append(f"a tub post stands on the foot zone at {fx},{fy}")
hd = ko["camera_hoods"]
for side, ref in (("left", "U2"), ("right", "U3")):
    c = cam[side]; zone = box(c["x"] - hd["half_w"], hd["y0"], c["x"] + hd["half_w"], hd["y1"])
    for p_ in parts:
        if p_["ref"] != ref and p_["h"] > hd["max_part_height"] and zone.intersects(rect(p_)):
            errs.append(f"{p_['ref']} (h {p_['h']}) is under the {side} camera hood")
lh = pcb["locating_holes"]
for name in ("round", "slot"):
    h_ = lh[name]; L = h_.get("length_x", h_["dia"])
    hole = box(h_["x"] - L / 2, h_["y"] - h_["dia"] / 2, h_["x"] + L / 2, h_["y"] + h_["dia"] / 2)
    if not pcb_poly.buffer(-0.5).contains(hole): errs.append(f"PCB locating {name} too close to the board edge")
    for p_ in parts:
        if hole.buffer(0.3).intersects(rect(p_)): errs.append(f"PCB locating {name} clashes with {p_['ref']}")
    if not any(abs(h_["x"] - cx) < 1e-6 and abs(h_["y"] - cy) < 1e-6 for cx, cy in pf["locating"]["centres"]):
        errs.append(f"PCB locating {name} is not under a locating post")
    # the slot may run the full width of the keep-out square (N9); the post seats on the strips either side of it in y
    if L > pf["locating"]["size"] + 1e-9 or h_["dia"] > pf["locating"]["size"] - 0.6: errs.append(f"locating post foot too small for the {name}")
if lh["round"]["x"] * lh["slot"]["x"] >= 0 or abs(lh["round"]["x"]) < abs(cam["right"]["x"]): errs.append("locating features must lie either side of the board, outboard of the cameras")
# LCD flex tail (provisional keep-out, N10): only low parts under the fold; the connector itself is exempt
lt = ko.get("lcd_tail")
if lt:
    tail = box(-lt["half_w"], lt["y"][0], lt["half_w"], lt["y"][1])
    for p_ in parts:
        if p_["ref"] != "J1" and p_["h"] > lt["max_part_height"] and tail.intersects(rect(p_)):
            errs.append(f"{p_['ref']} (h {p_['h']}) is under the LCD flex tail")
# battery lead pads and the alternative base plate
bz = P["battery"]["pads"]["zone"]; padzone = box(bz["x"][0], bz["y"][0], bz["x"][1], bz["y"][1])
if not keep.contains(padzone): errs.append("battery pad zone is not inside the PCB keep-in")
for p_ in parts:
    if padzone.intersects(rect(p_)): errs.append(f"battery pad zone clashes with {p_['ref']}")
alt = bp["alternative"]
if abs(alt["thickness"] + alt["psa_thickness"] - pcb["z_bottom"]) > 1e-6: errs.append("alternative base plate + adhesive != PCB bottom z")
# glass parts below flush
cg = P["cover_glass"]
sub = cg["recess_depth"] - cg["bond_thickness"] - cg["thickness"]
if abs(sub - cg["sub_flush"]) > 1e-6: errs.append(f"cover glass sub-flush is {sub:.2f}, YAML says {cg['sub_flush']}")
vwp = P["visor_window"]
notes.append(f"cover glass {sub:.2f} below flush; visor windows {vwp['recess_depth'] - vwp['t']:.2f} below the visor face")
# visor windows: recess inside the flat face with a full wall outboard, and clear of each other
vw = P["visor_window"]; chord = math.sqrt(R ** 2 - env["front_flat_y_outer"] ** 2)
out = chord - (abs(cam["right"]["x"]) + vw["recess_w"] / 2)
if out < env["min_printed_wall"]: errs.append(f"only {out:.2f} mm of visor face outboard of the window recess")
notes.append(f"visor face outboard of each window recess: {out:.2f} mm (flat half-chord {chord:.2f})")
if vw["recess_w"] < vw["w"] + 2 * env["fit_clearance"] - 1e-9: errs.append("window recess gives less than the fit clearance per side")
if vw["w"] < 2 * vw["opening"]["half_w"] + 1.0 - 1e-9: errs.append("window overlaps the opening by less than 0.5 mm per side (bond land)")
if abs(cam["right"]["x"] - cam["left"]["x"] - cam["baseline"]) > 1e-6: errs.append("camera baseline does not match the camera positions")
for side, ref in (("left", "U2"), ("right", "U3")):
    p_ = next(q for q in parts if q["ref"] == ref)
    if abs(p_["x"] - cam[side]["x"]) > 1e-6 or abs(p_["y"] - cam[side]["y"]) > 1e-6: errs.append(f"{ref} position differs from cameras.{side}")
# --- rev E additions (amendments E17 to E24, E36) ------------------------------------------------
j1 = next(q for q in parts if q["ref"] == "J1"); bb = P["battery"]["body"]; cell_y0 = bb["y"] - bb["dy"] / 2
# E24: J1 as stated in words equals J1 as a box; the pads keep 0.20 mm from the cell; the tail zone starts at the mouth
if abs(j1["mouth_y"] - (j1["y"] - j1["dy"] / 2)) > 1e-6 or abs(j1["body_y"][0] - j1["mouth_y"]) > 1e-6 or abs(j1["body_y"][1] - (j1["y"] + j1["dy"] / 2)) > 1e-6:
    errs.append("J1: mouth_y / body_y do not agree with its box (y -+ dy / 2)")
if abs(j1["mouth_y"] - (-17.30)) > 1e-6 or abs(j1["body_y"][1] - (-11.70)) > 1e-6 or abs(j1["pads_end_y"] - (-10.40)) > 1e-6:
    errs.append("J1 is not where amendment E24 puts it (mouth -17.30, body to -11.70, pads to -10.40)")
if abs((j1["pads_end_y"] - j1["mouth_y"]) - 6.90) > 1e-6: errs.append("J1: mouth to pad ends is not the 6.90 mm of the FH12 land pattern")
gap = cell_y0 - j1["pads_end_y"]
if gap < 0.20 - 1e-9: errs.append(f"J1 signal pads end only {gap:.2f} mm from the cell (0.20 required, E24)")
notes.append(f"J1 pads to the cell: {gap:.2f} mm; mouth at y = {j1['mouth_y']}")
if lt and (abs(lt["y"][1] - j1["mouth_y"]) > 1e-6 or lt["y"][0] >= lt["y"][1] or lt["y"][0] < -pcb["radius"] - 1e-9 or lt["half_w"] > j1["dx"] / 2):
    errs.append("tub_keepouts.lcd_tail must run from the mouth of J1 rearward, not beyond the board edge, and not wider than J1")
# the recorded notch of the board's battery keep-out is J1's courtyard and nothing more; body and pads stay outside the cell
nt = P["battery"]["board_keepout_notch"]; cy = j1["courtyard"]
if abs(nt["x"][0] - cy[0]) > 1e-6 or abs(nt["x"][1] - cy[2]) > 1e-6 or abs(nt["y"][0] - cell_y0) > 1e-6 or abs(nt["y"][1] - cy[3]) > 1e-6:
    errs.append("battery.board_keepout_notch is not J1's courtyard inside the cell box")
if abs(nt["pad_to_cell_gap"] - gap) > 1e-6: errs.append("battery.board_keepout_notch.pad_to_cell_gap differs from the geometry")
for name, c in P["battery"]["pads"]["centres"].items():
    sx, sy = P["battery"]["pads"]["size"]
    if not padzone.buffer(1e-9).contains(box(c[0] - sx / 2, c[1] - sy / 2, c[0] + sx / 2, c[1] + sy / 2)): errs.append(f"battery pad {name} is outside battery.pads.zone")
# E17: the fit numbers are those of the hole and spigot tolerances; guaranteed field below the required one; gate bars 1.0 inside it
fr = cam["field_required_deg"]
fit_nom = (lh["round"]["dia"] - lh["spigot_dia"]) / 2
fit_max = (lh["round"]["dia"] + lh["dia_tol"][1] - (lh["spigot_dia"] + lh["spigot_dia_tol"][0])) / 2
if abs(fit_nom - lh["fit_nominal"]) > 1e-9 or abs(fit_max - lh["fit_max"]) > 1e-9 or abs(lh["spigot_dia"] + lh["spigot_dia_tol"][0] - lh["spigot_dia_min"]) > 1e-9:
    errs.append(f"pcb.locating_holes: fit_nominal / fit_max / spigot_dia_min do not follow from the diameters and tolerances ({fit_nom:.3f}, {fit_max:.3f})")
ug = cam["up_guaranteed_case"]
if abs(ug["locating_fit"] - lh["fit_max"]) > 1e-9: errs.append("cameras.up_guaranteed_case is not defined on pcb.locating_holes.fit_max")
if not (fr["up_guaranteed"] <= ug["model_deg"] <= fr["up"]): errs.append("cameras: up_guaranteed must not exceed the model figure of its own case, nor that the required field")
if abs(cam["gate2_bars_deg"][0] - (fr["up_guaranteed"] - 1.0)) > 1e-9 or abs(cam["gate2_bars_deg"][0] + cam["gate2_bars_deg"][1]) > 1e-9:
    errs.append("cameras.gate2_bars_deg must be +-(up_guaranteed - 1.0)")
# E20: the lower plate limits keep 0.02 mm of epoxy under a ball at its upper diameter limit. Chain as in the mechanical
# package: thinnest plate + adhesive sheet 10 % thin - (largest ball - protrusion + 0.02 mm setting tolerance)
ft = bp["feet"]
for name, t_lo, psa_t in (("FR-4", bp["thickness_accepted"][0], bp["psa"]["thickness"]), ("PA12", alt["thickness_accepted"][0], alt["psa_thickness"])):
    epoxy = t_lo + 0.9 * psa_t - (ft["ball_dia"] + ft["dia_tol"] - ft["protrusion"] + 0.02)
    if epoxy < 0.02 - 1e-9: errs.append(f"{name} plate at its lower limit {t_lo} leaves {epoxy:.3f} mm of epoxy under an oversize ball (0.02 required, E20)")
    notes.append(f"epoxy under an oversize ball, {name} plate at {t_lo}: {epoxy:.3f} mm")
# E21: nominal ring = nominal plate + rule offset - nominal tape; tape inside its range; print leaves lapping stock on the tallest ring
rg = baf["ring"]
if abs(bp["thickness"] + rg["rule_offset"] - rg["nominal_tape"] - rg["height"]) > 1e-9: errs.append("baffle ring: height is not plate + rule_offset - nominal_tape")
if not (rg["tape"][0] <= rg["nominal_tape"] <= rg["tape"][1]): errs.append("baffle ring: nominal tape outside the tape range")
tallest = bp["thickness_accepted"][1] + rg["rule_offset"] - rg["tape"][0]
if rg["print_height"] < tallest + 0.15 - 1e-9: errs.append(f"baffle ring: print height {rg['print_height']} leaves less than 0.15 to lap on the tallest ring ({tallest:.3f})")
# E18 / E19: legend rules and retarder film against the features they refer to
lg = bp["legend"]
if min(lg["min_line"], lg["min_space"]) < 0.15 - 1e-9 or lg["min_text_height"] < 1.0 - 1e-9 or lg["thickness_max"] > 0.03 + 1e-9 or lg["seat_zones_clear_dia"] < 8.5 - 1e-9 or lg["edge_margin"] < 0.75 - 1e-9:
    errs.append("base_plate.legend: a print rule is looser than amendment E18")
rt = cg["retarder"]
if not (lcd["aperture_dia"] < rt["dia"] < cg["bond_id"]): errs.append("retarder film must cover the aperture and stay inside the bore of the tape ring")
if not (lcd["aperture_dia"] / 2 < rt["clocking_flat"]["y"] < rt["dia"] / 2) or abs(2 * math.sqrt((rt["dia"] / 2) ** 2 - rt["clocking_flat"]["y"] ** 2) - rt["clocking_flat"]["length"]) > 0.05:
    errs.append("retarder clocking flat: not between aperture and film edge, or its length is not the chord at that y")
if rt["thickness_max"] >= cg["bond_thickness"]: errs.append("retarder film does not fit in the tape gap")
# E36: cradle board 1.0 mm, top face unchanged; the pin tail comes through
cp = P["cradle"]["pcb"]; pins = P["cradle"]["pins"]
if abs(cp["thickness"] - 1.0) > 1e-9 or abs(cp["top_z"] - (-4.855)) > 1e-9: errs.append("cradle.pcb: thickness 1.0 with top_z -4.855 (E36)")
if pins["tail_length"] <= cp["thickness"]: errs.append("cradle spring-pin tail does not come through the cradle board")
# E35: the fine class is finer than the default and names its three layers
nc = pcb["net_classes"]
if not (nc["fine"]["track"] < nc["default"]["track"] and nc["fine"]["clearance"] < nc["default"]["clearance"] and len(nc["fine"]["layers"]) == 3): errs.append("pcb.net_classes: fine class (E35)")
# bottom-side board parts against the keys they must agree with: 16 LEDs in 8 pairs on the ring, photodiode at its place
bparts = P["bottom_side_parts"]["board_parts"]
leds = [q for q in bparts if q["ref"].startswith("D")]; pdb = [q for q in bparts if q["ref"] == "PD1"]
if len(leds) != 2 * led["count_pairs"] or len(pdb) != 1: errs.append("bottom_side_parts.board_parts: 16 LEDs and one photodiode expected")
for k in range(led["count_pairs"]):
    az = math.radians(led["first_azimuth_deg"] + k * led["step_deg"])
    px, py = led["x"] + led["radius"] * math.cos(az), led["y"] + led["radius"] * math.sin(az)
    near = [q for q in leds if math.hypot(q["x"] - px, q["y"] - py) < 0.6]
    if len(near) != 2 or abs(sum(q["x"] for q in near) / 2 - px) > 2e-3 or abs(sum(q["y"] for q in near) / 2 - py) > 2e-3: errs.append(f"LED pair {k + 1} is not centred on the ring at {led['first_azimuth_deg'] + k * led['step_deg']} deg")
if any(abs(q["h"] - led["led_height"]) > 1e-9 for q in leds): errs.append("LED height differs from grain_led_ring.led_height")
if pdb and any(abs(pdb[0][k_] - pd[k_]) > 1e-9 for k_ in ("x", "y", "dx", "dy", "h")): errs.append("board photodiode differs from bottom_side_parts.photodiode")
for tp in P["top_side_test_points"]:
    if not keep.contains(Point(tp["x"], tp["y"]).buffer(tp["dia"] / 2)): errs.append(f"{tp['ref']} outside the PCB keep-in")
    if rect(bb).intersects(Point(tp["x"], tp["y"]).buffer(tp["dia"] / 2)): errs.append(f"{tp['ref']} lies under the cell (not reachable by a probe)")
print("\n".join("NOTE  " + n for n in notes)); print("\n".join("ERROR " + e for e in errs) or "OK: no layout errors")
sys.exit(1 if errs else 0)
