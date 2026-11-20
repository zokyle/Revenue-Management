#!/usr/bin/env python3
"""master_params.yaml part lists against the routed main board (rev E).

    python3 check_parts_vs_board.py [path to gl1_main-mechanical.json]

Exit 0: every part body (fitted or not) of the board file is in the YAML with the same centre, size and height, and the YAML
lists nothing the board does not have (the cell, YAML ref BT1, is not a board part).  Exit 1: a difference.  Exit 2: no
board file.  The YAML is regenerated from the board, so after any new placement this must be run again.
"""
import json, pathlib, sys, yaml
HERE = pathlib.Path(__file__).resolve().parent
path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "electrical" / "gl1_main" / "out" / "gl1_main-mechanical.json"
if not path.exists():
    print(f"no board file at {path}"); sys.exit(2)
Y = yaml.safe_load(open(HERE / "master_params.yaml")); J = json.load(open(path))
TOL = 1e-3
errs, notes = [], []
def body(c):
    b = c["body"]; xs = [p[0] for p in b["corners"]]; ys = [p[1] for p in b["corners"]]
    return dict(x=b["cx"], y=b["cy"], dx=max(xs) - min(xs), dy=max(ys) - min(ys), h=b["height"])
def same(ref, got, want, keys):
    bad = [f"{k}: board {got[k]:g}, YAML {want[k]:g}" for k in keys if abs(got[k] - want[k]) > TOL]
    if bad: errs.append(f"{ref}: " + "; ".join(bad))
comps = {(c["side"], c["ref"]): c for c in J["components"]}
top = {r: c for (s, r), c in comps.items() if s == "top"}; bot = {r: c for (s, r), c in comps.items() if s == "bottom"}
ytop = {p["ref"]: p for p in Y["top_side_parts"] if p["ref"] != "BT1"}
fitted = {r: c for r, c in top.items() if c["body"]["height"] > 0}
for r in sorted(set(fitted) - set(ytop)): errs.append(f"{r}: on the board, not in top_side_parts")
for r in sorted(set(ytop) - set(fitted)): errs.append(f"{r}: in top_side_parts, not a top-side part body of the board")
for r in sorted(set(fitted) & set(ytop)):
    c, p = fitted[r], ytop[r]
    same(r, body(c), p, ("x", "y", "dx", "dy", "h"))
    ax, ay = p.get("anchor", (p["x"], p["y"]))
    if abs(ax - c["x"]) > TOL or abs(ay - c["y"]) > TOL: errs.append(f"{r}: anchor: board ({c['x']:g}, {c['y']:g}), YAML ({ax:g}, {ay:g})")
    if bool(p.get("dnp", False)) != bool(c["dnp"]): errs.append(f"{r}: dnp differs")
    if "courtyard" in p and any(abs(a - b) > TOL for a, b in zip(p["courtyard"], c["courtyard_bbox"])): errs.append(f"{r}: courtyard differs")
    if "mpn" in p and p["mpn"] != c["mpn"]: errs.append(f"{r}: mpn: board {c['mpn']}, YAML {p['mpn']}")
j1c = fitted.get("J1"); j1 = ytop.get("J1")
if j1c and j1:
    ys = [q[1] for q in j1c["body"]["corners"]]
    if abs(min(ys) - j1["mouth_y"]) > TOL or abs(max(ys) - j1["body_y"][1]) > TOL: errs.append("J1: mouth_y / body_y differ from the board body")
ytp = {t["ref"]: t for t in Y["top_side_test_points"]}; btp = {r: c for r, c in top.items() if r.startswith("TP")}
if set(ytp) != set(btp): errs.append(f"test points: board {sorted(btp)}, YAML {sorted(ytp)}")
for r in set(ytp) & set(btp):
    if abs(ytp[r]["x"] - btp[r]["x"]) > TOL or abs(ytp[r]["y"] - btp[r]["y"]) > TOL or ytp[r]["net"] != btp[r]["value"]: errs.append(f"{r}: position or net differs")
for name, ref in (("BAT+", "BT1"), ("BAT-", "BT2")):
    c = top.get(ref); w = Y["battery"]["pads"]["centres"][name]
    if c is None or c["value"] != name or abs(c["x"] - w[0]) > TOL or abs(c["y"] - w[1]) > TOL: errs.append(f"battery pad {name} ({ref}) differs from battery.pads.centres")
fid = sorted((c["x"], c["y"]) for r, c in top.items() if r.startswith("FID"))
if fid != sorted(map(tuple, Y["top_side_fiducials"])): errs.append("top-side fiducials differ")
ybot = {p["ref"]: p for p in Y["bottom_side_parts"]["board_parts"]}
bfit = {r: c for r, c in bot.items() if c["body"]["height"] > 0}
if set(ybot) != set(bfit): errs.append(f"bottom side: board {sorted(bfit)}, YAML {sorted(ybot)}")
for r in set(ybot) & set(bfit):
    c = bfit[r]; got = dict(x=c["x"], y=c["y"], rot=c["rot"], dx=c["body"]["length"], dy=c["body"]["width"], h=c["body"]["height"])
    same(r, got, ybot[r], ("x", "y", "rot", "dx", "dy", "h"))
if sorted((c["x"], c["y"]) for r, c in bot.items() if r.startswith("FID")) != sorted(map(tuple, Y["bottom_side_parts"]["fiducials"])): errs.append("bottom-side fiducials differ")
# keep-outs the YAML states: battery body less the recorded notch; LCD-tail zone (reported, the board is rebuilt after the YAML)
from shapely.geometry import Polygon, box
b = Y["battery"]["body"]; n = Y["battery"]["board_keepout_notch"]
want = box(b["x"] - b["dx"] / 2, b["y"] - b["dy"] / 2, b["x"] + b["dx"] / 2, b["y"] + b["dy"] / 2).difference(box(n["x"][0], n["y"][0], n["x"][1], n["y"][1]))
bk = next((k for k in J.get("keepouts", []) if k["name"] == "battery_body"), None)
if bk is None or Polygon(bk["polygon"]).symmetric_difference(want).area > 1e-6: errs.append("battery_body keep-out of the board is not battery.body less battery.board_keepout_notch")
lt = Y["tub_keepouts"]["lcd_tail"]; bl = next((k for k in J.get("height_limits", []) if k["name"] == "lcd_tail"), None)
if bl is None or Polygon(bl["polygon"]).symmetric_difference(box(-lt["half_w"], lt["y"][0], lt["half_w"], lt["y"][1])).area > 1e-6:
    notes.append("the board file's lcd_tail height limit is not the YAML zone (expected until the board is rebuilt on the rev E YAML)")
if str(J.get("revision")) != str(Y["rev"]): notes.append(f"board file is stamped {J.get('revision')}, YAML is {Y['rev']}")
ndnp = sum(1 for c in fitted.values() if c.get("dnp")); ydnp = sum(1 for p in ytop.values() if p.get("dnp"))
print(f"{len(fitted)} top-side part bodies ({len(fitted) - ndnp} fitted, {ndnp} not fitted) and {len(bfit)} bottom-side bodies on the board; {len(ytop)} ({len(ytop) - ydnp} fitted, {ydnp} not fitted) + {len(ybot)} in the YAML")
print("\n".join("NOTE  " + n_ for n_ in notes)); print("\n".join("ERROR " + e for e in errs) or "OK: the YAML part lists match the board")
sys.exit(1 if errs else 0)
