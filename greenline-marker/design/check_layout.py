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
print("\n".join("NOTE  " + n for n in notes)); print("\n".join("ERROR " + e for e in errs) or "OK: no layout errors")
sys.exit(1 if errs else 0)
