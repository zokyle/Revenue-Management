"""Review figures of the routed GL-1 main board, measured on the DRC'd board file.

Added after the layout review.  Nothing here is a pass / fail rule (KiCad's DRC
is the judge of the rules); these are the measurements the reviewers made by
hand, made by the build on every run so that the notes cannot drift from the
copper:

* fine track (narrower than the standard 0.15 mm): length per layer and how far
  from the camera ball fields it reaches;
* camera supply balls: copper path from each ball to the nearest capacitor of
  its net;
* crystal: every via inside the crystal's no-via box, the nearest foreign via
  and the nearest foreign top-layer track to the crystal nets (pads included);
* photodiode input PD_K: every LED line and clock net within 0.5 mm of its
  copper (pads and vias included) on the same layer, and what crosses it on the
  adjacent layer;
* layer 3 (In2.Cu): real fill coverage, and how much bottom-layer track has no
  fill above it;
* plane clearance: the smallest distance between each zone fill and foreign
  copper on its layer.

    import layout_review
    r = layout_review.review(design, pcb_path, G)      # dict
    text = layout_review.markdown(r)

Needs pcbnew (zone fills are read from the board file) and shapely.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from shapely.geometry import LineString, Point, Polygon, box            # noqa: E402
from shapely.ops import unary_union                                      # noqa: E402

from gleda import board, geometry                                        # noqa: E402
import layout_quality                                                    # noqa: E402

STD_WIDTH = 0.15


def _seg(t):
    if abs(t.x1 - t.x2) < 1e-9 and abs(t.y1 - t.y2) < 1e-9:
        return Point(t.x1, t.y1).buffer(t.width / 2.0)
    return LineString([(t.x1, t.y1), (t.x2, t.y2)]).buffer(t.width / 2.0)


def zone_fills(pcb):
    """[(net, layer name, shapely geometry of the fill)] read from the board file."""
    import pcbnew
    brd = pcbnew.LoadBoard(pcb)
    out = []
    for z in brd.Zones():
        if z.GetIsRuleArea():
            continue
        for lid in z.GetLayerSet().Seq():
            sps = z.GetFilledPolysList(lid)
            polys = []
            for i in range(sps.OutlineCount()):
                ol = sps.Outline(i)
                # design frame: x right, y up, origin at the board centre (KiCad page 100, 100)
                ext = [((ol.CPoint(k).x / 1e6) - 100.0, 100.0 - (ol.CPoint(k).y / 1e6))
                       for k in range(ol.PointCount())]
                holes = []
                for h in range(sps.HoleCount(i)):
                    hl = sps.Hole(i, h)
                    holes.append([((hl.CPoint(k).x / 1e6) - 100.0, 100.0 - (hl.CPoint(k).y / 1e6))
                                  for k in range(hl.PointCount())])
                if len(ext) >= 3:
                    p = Polygon(ext, [h for h in holes if len(h) >= 3])
                    polys.append(p if p.is_valid else p.buffer(0))
            if polys:
                out.append((str(z.GetNetname()), str(brd.GetLayerName(lid)), unary_union(polys)))
    return out


def review(design, pcb, G):
    tracks, vias = board.read_routing(pcb)
    pads = geometry.placed_pads(design)
    by_net_t, by_net_v = {}, {}
    for t in tracks:
        by_net_t.setdefault(t.net, []).append(t)
    for v in vias:
        by_net_v.setdefault(v.net, []).append(v)
    layers = list(design.copper_layers)
    r = {}

    # ---------------------------------------------------------------- fine track
    fields = {ref: box(*geometry.part_pads_bbox(design, ref)) for ref in ("U2", "U3")}
    fine = [t for t in tracks if t.width < STD_WIDTH - 1e-6]
    per_layer, nets, far = {}, set(), 0.0
    near = {1.0: 0.0, 2.0: 0.0}
    for t in fine:
        per_layer[t.layer] = per_layer.get(t.layer, 0.0) + t.length
        nets.add(t.net)
        d = max(min(f.distance(Point(x, y)) for f in fields.values())
                for x, y in ((t.x1, t.y1), (t.x2, t.y2)))
        far = max(far, d)
        for lim in near:
            if d <= lim:
                near[lim] += t.length
    fine_clear = 0.0
    r["fine"] = {"total_mm": round(sum(per_layer.values()), 1),
                 "per_layer_mm": {k: round(v, 1) for k, v in sorted(per_layer.items())},
                 "nets": len(nets), "farthest_from_ball_field_mm": round(far, 2),
                 "within_1mm_mm": round(near[1.0], 1), "within_2mm_mm": round(near[2.0], 1),
                 "fine_area_margin_mm": G.FINE_AREA_MARGIN,
                 "fine_area_mm2": round(sum(geometry.shape_polygon(a.shape).intersection(
                     geometry.outline_polygon(design.outline)).area for a in design.fine_areas), 1)}
    del fine_clear

    # ------------------------------------------------- camera supply balls to capacitors
    rows = []
    caps = {"V2V8_CAM": [p.ref for p in design.parts if p.ref.startswith("C")
                         and any(q.ref == p.ref and q.net == "V2V8_CAM" for q in pads)]}
    for ref, side in (("U2", "L"), ("U3", "R")):
        for ball, pin in (("D1", "DOVDD"), ("D5", "AVDD"), ("E3", "DVDD")):
            net = "V2V8_CAM" if pin != "DVDD" else "CAM_%s_DVDD" % side
            adj = layout_quality._net_graph(by_net_t.get(net, []), by_net_v.get(net, []), layers)
            src = next(q for q in pads if q.ref == ref and q.number == ball)
            best = None
            for q in pads:
                if q.net != net or not q.ref.startswith("C"):
                    continue
                try:
                    length = layout_quality.path_length(adj, src, q)
                except Exception:
                    length = None
                if length is None:
                    continue
                if best is None or length < best[1]:
                    best = (q.ref, length, math.hypot(q.x - src.x, q.y - src.y))
            rows.append({"ball": "%s.%s" % (ref, ball), "pin": pin, "net": net,
                         "capacitor": best[0] if best else None,
                         "path_mm": round(best[1], 2) if best else None,
                         "straight_mm": round(best[2], 2) if best else None})
    r["camera_supply"] = rows
    del caps

    # ---------------------------------------------------------------- crystal
    xt = {}
    cz = getattr(G, "CRYSTAL_ZONE", None)
    osc = ("OSC32_IN", "OSC32_OUT")
    osc_cu = unary_union([_seg(t) for n in osc for t in by_net_t.get(n, [])]
                         + [q.polygon for q in pads if q.net in osc])
    if cz:
        zb = box(*cz["no_via"])
        inside = [v for v in vias if zb.intersects(Point(v.x, v.y).buffer(v.diameter / 2.0))]
        xt["vias_in_box"] = sorted("%s (%.2f, %.2f)" % (v.net, v.x, v.y) for v in inside)
        xt["foreign_vias_in_box"] = sorted("%s (%.2f, %.2f)" % (v.net, v.x, v.y) for v in inside
                                           if v.net != "GND")
        xt["box"] = list(cz["no_via"])
    fv = [(osc_cu.distance(Point(v.x, v.y).buffer(v.diameter / 2.0)), v) for v in vias
          if v.net not in osc and v.net != "GND"]
    if fv:
        d, v = min(fv, key=lambda e: e[0])
        xt["nearest_foreign_via"] = {"mm": round(d, 3), "net": v.net, "at": [v.x, v.y]}
    ft = [(osc_cu.distance(_seg(t)), t) for t in tracks
          if t.layer == "F.Cu" and t.net not in osc and t.net != "GND"]
    if ft:
        d, t = min(ft, key=lambda e: e[0])
        xt["nearest_foreign_top_track"] = {"mm": round(d, 3), "net": t.net}
    y1 = next(p for p in design.parts if p.ref == "Y1")
    body = geometry.part_body_polygon(y1)
    under = {}
    for t in tracks:
        if t.layer != "F.Cu" and t.net not in osc and _seg(t).intersects(body):
            under.setdefault(t.layer, set()).add(t.net)
    xt["tracks_under_the_body_below_the_ground_plane"] = {k: sorted(v) for k, v in sorted(under.items())}
    for n in osc:
        xt[n + "_mm"] = round(sum(t.length for t in by_net_t.get(n, [])), 2)
    r["crystal"] = xt

    # ---------------------------------------------------------------- PD_K
    pd = {}
    pk_t = by_net_t.get("PD_K", [])
    pk_v = by_net_v.get("PD_K", [])
    pd["length_mm"] = round(sum(t.length for t in pk_t), 2)
    pd["length_per_layer_mm"] = {}
    for t in pk_t:
        pd["length_per_layer_mm"][t.layer] = round(pd["length_per_layer_mm"].get(t.layer, 0.0) + t.length, 2)
    pd["vias"] = len(pk_v)
    cu = {}
    for layer in layers:
        shapes = [_seg(t) for t in pk_t if t.layer == layer]
        shapes += [q.polygon for q in pads if q.net == "PD_K" and layer in q.layers]
        if shapes:                                   # layers where PD_K has tracks or pads; its vias with them
            shapes += [Point(v.x, v.y).buffer(v.diameter / 2.0) for v in pk_v]
            cu[layer] = unary_union(shapes)
    watch = sorted(n for n in design.nets if n.startswith("CP") or n in (
        "MCO", "CAM_XVCLK", "CAM_PCLK", "CAM_HREF", "CAM_VSYNC", "SPI1_SCK", "SPI2_SCK", "LCD_EXTCOMIN",
        "USB_DM", "USB_DP", "SWCLK", "NRST") or n.startswith("CAM_D"))
    close = []
    for n in watch:
        for layer, g in cu.items():
            segs = [t for t in by_net_t.get(n, []) if t.layer == layer]
            shapes = [(_seg(t), t.length) for t in segs]
            shapes += [(Point(v.x, v.y).buffer(v.diameter / 2.0), 0.0) for v in by_net_v.get(n, [])]
            shapes += [(q.polygon, 0.0) for q in pads if q.net == n and layer in q.layers]
            if not shapes:
                continue
            dmin = min(g.distance(s) for s, _l in shapes)
            if dmin <= 0.5:
                zone = g.buffer(0.5)
                length = sum(LineString([(t.x1, t.y1), (t.x2, t.y2)]).intersection(zone).length for t in segs)
                close.append({"net": n, "layer": layer, "min_mm": round(dmin, 3),
                              "length_within_0.5_mm": round(length, 2)})
    pd["switching_nets_within_0.5_mm_same_layer"] = close
    order = {"F.Cu": "In1.Cu", "In1.Cu": None, "In2.Cu": "B.Cu", "B.Cu": "In2.Cu"}
    cross = []
    for layer, g in cu.items():
        adj_layer = order.get(layer)
        if not adj_layer:
            continue
        acc = {}
        for t in tracks:
            if t.layer == adj_layer and t.net != "PD_K":
                length = LineString([(t.x1, t.y1), (t.x2, t.y2)]).intersection(g.buffer(t.width / 2.0)).length
                if length > 1e-6 or _seg(t).intersects(g):
                    acc[t.net] = acc.get(t.net, 0.0) + length
        for n, length in sorted(acc.items()):
            cross.append({"net": n, "pd_k_layer": layer, "on": adj_layer, "overlap_mm": round(length, 2)})
    pd["tracks_over_or_under_on_the_adjacent_layer"] = cross
    r["pd_k"] = pd

    # ---------------------------------------------------------------- zone fills
    fills = zone_fills(pcb)
    brd_poly = geometry.outline_polygon(design.outline)
    planes = []
    for net, layer, g in fills:
        dmin, what = None, ""
        for t in tracks:
            if t.layer == layer and t.net != net:
                d = g.distance(_seg(t))
                if dmin is None or d < dmin:
                    dmin, what = d, "track %s" % t.net
        for v in vias:
            if v.net != net:
                d = g.distance(Point(v.x, v.y).buffer(v.diameter / 2.0))
                if dmin is None or d < dmin:
                    dmin, what = d, "via %s (%.2f, %.2f)" % (v.net, v.x, v.y)
        pieces = len(g.geoms) if hasattr(g, "geoms") else 1
        planes.append({"net": net, "layer": layer, "area_mm2": round(g.area, 1),
                       "coverage_percent": round(100.0 * g.area / brd_poly.area, 1), "pieces": pieces,
                       "min_clearance_to_foreign_track_or_via_mm": None if dmin is None else round(dmin, 3),
                       "nearest": what})
    r["zones"] = planes
    in2 = [g for net, layer, g in fills if layer == "In2.Cu"]
    if in2:
        g = unary_union(in2)
        tot = bare = 0.0
        worst = {}
        for t in tracks:
            if t.layer != "B.Cu":
                continue
            line = LineString([(t.x1, t.y1), (t.x2, t.y2)])
            out = line.difference(g).length
            tot += t.length
            bare += out
            worst[t.net] = worst.get(t.net, 0.0) + out
        r["b_cu_reference"] = {"b_cu_track_mm": round(tot, 0), "without_in2_fill_above_mm": round(bare, 0),
                               "percent": round(100.0 * bare / tot, 0) if tot else 0.0,
                               "worst": [[n, round(v, 1)] for n, v in sorted(worst.items(),
                                                                              key=lambda e: -e[1])[:6]]}
        r["in2_track_mm"] = round(sum(t.length for t in tracks if t.layer == "In2.Cu"), 0)
    # ---------------------------------------------------------------- vias under the cell, at U4
    bb = G.BAT["body"]
    cell = box(bb["x"] - bb["dx"] / 2.0, bb["y"] - bb["dy"] / 2.0, bb["x"] + bb["dx"] / 2.0, bb["y"] + bb["dy"] / 2.0)
    r["vias"] = {"total": len(vias), "tenting": design.via_tenting,
                 "under_the_cell": sum(1 for v in vias if cell.intersects(Point(v.x, v.y).buffer(v.diameter / 2.0)))}
    u4 = next(p for p in design.parts if p.ref == "U4")
    u4b = geometry.part_body_polygon(u4)
    dv = [(u4b.distance(Point(v.x, v.y).buffer(v.diameter / 2.0)), v.net) for v in vias]
    r["imu"] = {"nearest_via_to_body_mm": round(min(dv)[0], 3), "net": min(dv)[1],
                "rotation_deg": u4.rotation}
    # ---------------------------------------------------------------- no-via areas
    go = G.VIA_KO["grain_opening"]
    c = Point(go["x"], go["y"])
    dg = min(c.distance(Point(v.x, v.y)) - v.diameter / 2.0 - go["dia"] / 2.0 for v in vias)
    ps = G.VIA_KO["pad_slot"]
    half = (ps["length"] - ps["width"]) / 2.0
    slot = LineString([(-half, ps["y"]), (half, ps["y"])]).buffer(ps["width"] / 2.0)
    dsl = min(slot.distance(Point(v.x, v.y).buffer(v.diameter / 2.0)) for v in vias)
    r["no_via_areas"] = {"nearest_via_pad_to_grain_opening_mm": round(dg, 3),
                         "nearest_via_pad_to_pad_slot_mm": round(dsl, 3), "margin_mm": G.NO_VIA_MARGIN}
    # fiducial mask openings against other mask openings on the top (vias are tented when "both")
    return r


def markdown(r):
    L = []
    f = r["fine"]
    L.append("- Fine track (narrower than 0.15 mm): %.1f mm on %d nets; per layer %s; %.1f mm of it within "
             "1 mm and %.1f mm within 2 mm of a camera ball field, the farthest %.2f mm away. Fine areas: "
             "pad field + %.1f mm, %.1f mm2 in all."
             % (f["total_mm"], f["nets"], ", ".join("%s %.1f" % kv for kv in f["per_layer_mm"].items()) or "-",
                f["within_1mm_mm"], f["within_2mm_mm"], f["farthest_from_ball_field_mm"],
                f["fine_area_margin_mm"], f["fine_area_mm2"]))
    L.append("- Camera supply balls, copper path to the nearest capacitor of the net: " + "; ".join(
        "%s (%s) -> %s %s mm (straight %s)" % (x["ball"], x["pin"], x["capacitor"], x["path_mm"], x["straight_mm"])
        for x in r["camera_supply"]) + ".")
    x = r["crystal"]
    L.append("- Crystal: OSC32_IN %.2f mm, OSC32_OUT %.2f mm; vias inside the no-via box: %s (foreign: %s); "
             "nearest foreign via to crystal copper (pads included) %s; nearest foreign top-layer track %s; "
             "below the ground plane under the body: %s."
             % (x.get("OSC32_IN_mm", 0), x.get("OSC32_OUT_mm", 0),
                ", ".join(x.get("vias_in_box", [])) or "none", ", ".join(x.get("foreign_vias_in_box", [])) or "none",
                "%.3f mm (%s)" % (x["nearest_foreign_via"]["mm"], x["nearest_foreign_via"]["net"])
                if "nearest_foreign_via" in x else "-",
                "%.3f mm (%s)" % (x["nearest_foreign_top_track"]["mm"], x["nearest_foreign_top_track"]["net"])
                if "nearest_foreign_top_track" in x else "-",
                "; ".join("%s: %s" % (k, ", ".join(v)) for k, v in
                          x["tracks_under_the_body_below_the_ground_plane"].items()) or "nothing"))
    p = r["pd_k"]
    L.append("- PD_K: %.2f mm (%s), %d via(s). LED / clock / bus nets within 0.5 mm on the same layer "
             "(pads and vias included): %s. On the adjacent layer over or under PD_K copper: %s."
             % (p["length_mm"], ", ".join("%s %.2f" % kv for kv in sorted(p["length_per_layer_mm"].items())),
                p["vias"],
                "; ".join("%s %s min %.3f mm, %.2f mm long" % (c["net"], c["layer"], c["min_mm"],
                                                              c["length_within_0.5_mm"])
                          for c in p["switching_nets_within_0.5_mm_same_layer"]) or "none",
                "; ".join("%s on %s (%.2f mm)" % (c["net"], c["on"], c["overlap_mm"])
                          for c in p["tracks_over_or_under_on_the_adjacent_layer"]) or "nothing"))
    for z in r["zones"]:
        L.append("- Fill %s on %s: %.1f mm2 (%.1f %% of the board), %d piece(s); smallest distance to foreign "
                 "track / via %s mm (%s)."
                 % (z["net"], z["layer"], z["area_mm2"], z["coverage_percent"], z["pieces"],
                    z["min_clearance_to_foreign_track_or_via_mm"], z["nearest"]))
    if "b_cu_reference" in r:
        b = r["b_cu_reference"]
        L.append("- Layer 3 (In2.Cu) carries %.0f mm of track; %.0f of %.0f mm of bottom-layer track (%.0f %%) "
                 "has no In2 fill above it (worst: %s)."
                 % (r["in2_track_mm"], b["without_in2_fill_above_mm"], b["b_cu_track_mm"], b["percent"],
                    ", ".join("%s %.1f" % (n, v) for n, v in b["worst"])))
    v = r["vias"]
    L.append("- Vias: %d, tenting '%s'; %d under the cell body. IMU: nearest via pad %.3f mm outside the body "
             "outline (%s); U4 rotation %g degrees."
             % (v["total"], v["tenting"], v["under_the_cell"], r["imu"]["nearest_via_to_body_mm"],
                r["imu"]["net"], r["imu"]["rotation_deg"]))
    n = r["no_via_areas"]
    L.append("- No-via areas: nearest via pad %.3f mm from the grain opening (dia 13) and %.3f mm from the pad "
             "slot (rule margin %.2f mm)."
             % (n["nearest_via_pad_to_grain_opening_mm"], n["nearest_via_pad_to_pad_slot_mm"], n["margin_mm"]))
    return "\n".join(L) + "\n"
