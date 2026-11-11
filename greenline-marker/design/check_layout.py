#!/usr/bin/env python3
"""Plan-view and z-stack sanity checks for design/master_params.yaml (run: python3 check_layout.py)."""
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
    elif top > P["roof"]["underside_z"] - 0.1 and p["ref"] not in ("U2", "U3"):
        errs.append(f"{p['ref']} top z={top:.2f} hits the roof")
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
ko = P["tub_keepouts"]; half = ko["post_feet"]["size"] / 2
for cx, cy in ko["post_feet"]["centres"]:
    foot = box(cx - half, cy - half, cx + half, cy + half)
    if not pcb_poly.buffer(-0.1).contains(foot): errs.append(f"post foot at {cx},{cy} is not on the PCB")
    for p_ in parts:
        if foot.buffer(0.2).intersects(rect(p_)): errs.append(f"post foot at {cx},{cy} clashes with {p_['ref']}")
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
    if not any(abs(h_["x"] - cx) < 1e-6 and abs(h_["y"] - cy) < 1e-6 for cx, cy in ko["post_feet"]["centres"]):
        errs.append(f"PCB locating {name} is not under a tub post")
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
print("\n".join("NOTE  " + n for n in notes)); print("\n".join("ERROR " + e for e in errs) or "OK: no layout errors")
sys.exit(1 if errs else 0)
