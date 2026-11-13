"""Quality figures of a routed GL-1 board, measured on the copper.

Nothing here is a pass / fail rule (KiCad's DRC is the judge of the rules);
these are the numbers a layout review asks for:

* camera bus: track length against the spanning tree, vias, net by net;
* the electrical length from each camera ball through its 220 ohm element to
  the MCU pad, for the eleven camera outputs, and the spread against PCLK;
* via count; the smallest gap between a via and a top-side pad (own net and
  foreign net); the smallest solder-mask web; the smallest copper-to-edge
  distance; what comes how close to the IMU.

    from layout_quality import quality
    q = quality(design, tracks, vias)        # tracks / vias as read back from the board file

``tracks`` / ``vias`` are ``gleda.model.Track`` / ``Via`` (or anything with the
same attributes).  Pure geometry (shapely); no pcbnew.
"""
import heapq
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, "..", "tools"))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from shapely.geometry import LineString, Point                          # noqa: E402
from shapely.strtree import STRtree                                      # noqa: E402

from gleda import geometry, router                                       # noqa: E402

#: propagation delay used for the skew figures: outer-layer FR-4 microstrip is
#: about 6 ps/mm, inner stripline about 7 ps/mm; 7 is the pessimistic one
PS_PER_MM = 7.0
EPS = 2e-3


def _node(x, y, layer):
    return (round(x, 3), round(y, 3), layer)


def _net_graph(tracks, vias, layers):
    """node -> [(node, length)] of one net.  Track ends that lie on the inside
    of another track of the same layer are joined to it (T junctions)."""
    adj = {}

    def link(a, b, w):
        adj.setdefault(a, []).append((b, w))
        adj.setdefault(b, []).append((a, w))

    by_layer = {}
    for t in tracks:
        by_layer.setdefault(t.layer, []).append(t)
    for layer, ts in by_layer.items():
        for t in ts:
            link(_node(t.x1, t.y1, layer), _node(t.x2, t.y2, layer), t.length)
        ends = {_node(t.x1, t.y1, layer) for t in ts} | {_node(t.x2, t.y2, layer) for t in ts}
        for t in ts:
            if t.length < EPS:
                continue
            a, b = _node(t.x1, t.y1, layer), _node(t.x2, t.y2, layer)
            dx, dy = t.x2 - t.x1, t.y2 - t.y1
            for e in ends:
                if e == a or e == b:
                    continue
                s = ((e[0] - t.x1) * dx + (e[1] - t.y1) * dy) / (t.length ** 2)
                if not EPS / t.length < s < 1.0 - EPS / t.length:
                    continue
                px, py = t.x1 + s * dx, t.y1 + s * dy
                if math.hypot(px - e[0], py - e[1]) < EPS:
                    link(e, a, s * t.length)
                    link(e, b, (1.0 - s) * t.length)
    for v in vias:
        nodes = [_node(v.x, v.y, layer) for layer in layers]
        for i in range(len(nodes) - 1):
            link(nodes[i], nodes[i + 1], 0.0)             # barrel length not counted
        # a track may end anywhere inside the via pad
        for layer in layers:
            for n in list(adj):
                if n[2] == layer and n != _node(v.x, v.y, layer) \
                        and math.hypot(n[0] - v.x, n[1] - v.y) <= v.diameter / 2.0 + EPS:
                    link(n, _node(v.x, v.y, layer), math.hypot(n[0] - v.x, n[1] - v.y))
    return adj


def _pad_nodes(adj, pad):
    out = []
    for n in adj:
        if n[2] in pad.layers and pad.polygon.buffer(0.02).contains(Point(n[0], n[1])):
            out.append((n, math.hypot(n[0] - pad.x, n[1] - pad.y)))
    return out


def path_length(adj, pad_a, pad_b):
    """Shortest copper path between two pads of one net (mm), None if the
    copper does not join them."""
    src = _pad_nodes(adj, pad_a)
    dst = dict(_pad_nodes(adj, pad_b))
    if not src or not dst:
        return None
    best = {}
    heap = []
    for n, d in src:
        best[n] = d
        heapq.heappush(heap, (d, n))
    while heap:
        d, n = heapq.heappop(heap)
        if d > best.get(n, 1e99) + 1e-12:
            continue
        if n in dst:
            return d + dst[n]
        for m, w in adj.get(n, ()):
            nd = d + w
            if nd < best.get(m, 1e99) - 1e-12:
                best[m] = nd
                heapq.heappush(heap, (nd, m))
    return None


def quality(design, tracks, vias, *, cam_arrays=None, cam_map=None, bus=None):
    """The figures listed in the module text, as one JSON-able dict."""
    tracks = list(tracks)
    vias = list(vias)
    layers = list(design.copper_layers)
    pads = [p for p in geometry.placed_pads(design) if p.polygon is not None]
    pad_of = {(p.ref, p.number): p for p in pads}
    by_net_t, by_net_v = {}, {}
    for t in tracks:
        by_net_t.setdefault(t.net, []).append(t)
    for v in vias:
        by_net_v.setdefault(v.net, []).append(v)
    out = {}

    # ---- net quality of the camera nets ---------------------------------------------------
    nq = router.net_quality(design, tracks, vias)
    per_net = dict(nq.get("nets", {}))                 # net -> {length_mm, tree_mm, ratio, vias, pads, sides}
    cam_nets = sorted(n for n in design.nets if n.startswith("CAM_") or n == "MCO")
    out["camera_nets"] = {n: {k: per_net[n][k] for k in ("length_mm", "tree_mm", "ratio", "vias", "pads")}
                          for n in cam_nets if n in per_net}
    bus_nets = ["CAM_%s" % s for s in (bus or ())]
    if bus_nets:
        ln = sum(per_net[n]["length_mm"] for n in bus_nets if n in per_net)
        tr = sum(per_net[n]["tree_mm"] for n in bus_nets if n in per_net)
        out["camera_bus"] = {"nets": len(bus_nets), "length_mm": round(ln, 2), "tree_mm": round(tr, 2),
                             "ratio": round(ln / tr, 3) if tr else None,
                             "vias": sum(per_net[n]["vias"] for n in bus_nets if n in per_net)}
    out["all_signal_nets"] = {k: nq.get(k) for k in ("signal_length_mm", "signal_tree_mm", "signal_ratio",
                                                       "nets_over_1_5")}
    out["router_warnings"] = list(nq.get("warnings", []))

    # ---- ball -> array -> MCU pad lengths and the spread against PCLK ---------------------
    if cam_arrays and cam_map and bus:
        graphs = {}

        def graph(net):
            if net not in graphs:
                graphs[net] = _net_graph(by_net_t.get(net, []), by_net_v.get(net, []), layers)
            return graphs[net]

        mcu_pad = {}
        for p in pads:
            if p.ref == "U1" and p.net in bus_nets:
                mcu_pad[p.net] = p
        skew = {}
        for cam, side in (("U2", "L"), ("U3", "R")):
            rows = {}
            for sig in bus:
                a, e = cam_map[cam][sig]
                rn = cam_arrays[cam][a]
                ball = next(p for p in pads if p.ref == cam and p.net == "CAM_%s_%s" % (side, sig))
                pa, pb = pad_of[(rn, str(e))], pad_of[(rn, str(9 - e))]
                l1 = path_length(graph("CAM_%s_%s" % (side, sig)), ball, pa)
                l2 = path_length(graph("CAM_%s" % sig), pb, mcu_pad["CAM_%s" % sig])
                rows[sig] = {"ball_to_array_mm": None if l1 is None else round(l1, 2),
                             "array_to_mcu_mm": None if l2 is None else round(l2, 2),
                             "total_mm": None if None in (l1, l2) else round(l1 + l2, 2)}
            ref = rows.get("PCLK", {}).get("total_mm")
            tot = [r["total_mm"] for r in rows.values() if r["total_mm"] is not None]
            for sig, r in rows.items():
                r["minus_pclk_mm"] = None if None in (ref, r["total_mm"]) else round(r["total_mm"] - ref, 2)
            d = [r["minus_pclk_mm"] for s, r in rows.items() if s != "PCLK" and r["minus_pclk_mm"] is not None]
            skew[cam] = {"lines": rows, "pclk_mm": ref,
                         "shortest_mm": min(tot) if tot else None, "longest_mm": max(tot) if tot else None,
                         "spread_against_pclk_mm": [min(d), max(d)] if d else None,
                         "spread_against_pclk_ps": [round(min(d) * PS_PER_MM, 1), round(max(d) * PS_PER_MM, 1)]
                         if d else None}
        out["camera_skew"] = skew
        out["camera_skew_note"] = (
            "lengths along the copper, ball to array pad plus array pad to MCU pad (the resistor body is "
            "the same for every line); %.0f ps/mm assumed.  At a 12 MHz pixel clock the period is 83.3 ns: "
            "a spread of 40 mm is 0.28 ns, 0.3 %% of the period, and small against the RC of the 220 ohm "
            "series element with the bus capacitance (220 ohm x about 15 pF = 3.3 ns, the same for every "
            "line)" % PS_PER_MM)

    # ---- vias --------------------------------------------------------------------------------
    plane_nets = set(design.full_plane_layers().values())
    out["vias"] = {"total": len(vias),
                   "on_plane_nets": sum(1 for v in vias if v.net in plane_nets),
                   "by_net_class": {}}
    for v in vias:
        cls = design.nets[v.net].netclass if v.net in design.nets else "?"
        out["vias"]["by_net_class"][cls] = out["vias"]["by_net_class"].get(cls, 0) + 1

    # ---- via to top-side pads -------------------------------------------------------------------
    top_pads = [p for p in pads if "F.Cu" in p.layers and p.kind != "th"]
    tree = STRtree([p.polygon for p in top_pads])
    own = foreign = None
    for v in vias:
        pt = Point(v.x, v.y)
        for i in tree.query(pt.buffer(v.diameter / 2.0 + 1.0)):
            p = top_pads[int(i)]
            gap = p.polygon.distance(pt) - v.diameter / 2.0
            rec = (round(gap, 4), p.key, v.net, round(v.x, 3), round(v.y, 3))
            if p.net == v.net:
                if own is None or rec < own:
                    own = rec
            elif foreign is None or rec < foreign:
                foreign = rec
    keys = ("gap_mm", "pad", "via_net", "via_x", "via_y")
    out["via_to_top_pad"] = {"own_net": dict(zip(keys, own)) if own else None,
                             "other_net": dict(zip(keys, foreign)) if foreign else None}

    # ---- solder-mask web --------------------------------------------------------------------------
    exp = design.rules.mask_expansion
    webs = {}
    for side, mask, cu in (("top", "F.Mask", "F.Cu"), ("bottom", "B.Mask", "B.Cu")):
        shapes = []
        for p in pads:
            if mask in p.tech:
                shapes.append((p.polygon.buffer(exp) if exp else p.polygon, p.key, p.net))
        open_side = {"top": design.via_tenting in ("bottom", "none"),
                     "bottom": design.via_tenting in ("top", "none")}[side]
        if open_side:
            for v in vias:
                shapes.append((Point(v.x, v.y).buffer(v.diameter / 2.0, 16), "via(%.2f,%.2f)" % (v.x, v.y), v.net))
        st = STRtree([s[0] for s in shapes])
        best = None
        bridges = 0
        for i, (g, key, net) in enumerate(shapes):
            for j in st.query(g.buffer(0.5)):
                j = int(j)
                if j <= i:
                    continue
                d = g.distance(shapes[j][0])
                if d <= 1e-6:
                    if net != shapes[j][2]:
                        bridges += 1
                    continue
                if best is None or d < best[0]:
                    best = (round(d, 4), key, shapes[j][1])
        webs[side] = {"smallest_web_mm": best[0] if best else None,
                      "between": list(best[1:]) if best else None,
                      "openings": len(shapes), "touching_openings_of_different_nets": bridges}
    out["solder_mask"] = webs
    out["solder_mask_note"] = ("mask openings are drawn 1:1 on the pads (board expansion %.3f mm); an open "
                               "via on the top side counts as an opening of its pad size" % exp)

    # ---- copper to edge ---------------------------------------------------------------------------------
    outline = geometry.outline_polygon(design.outline)
    edges = [outline.exterior] + list(outline.interiors)
    for h in geometry.npth_holes(design):
        (x1, y1, x2, y2), w = h[0], h[1]
        g = Point(x1, y1) if (x1, y1) == (x2, y2) else LineString([(x1, y1), (x2, y2)])
        edges.append(g.buffer(w / 2.0, 32).exterior)

    def edge_dist(g):
        return min(g.distance(e) for e in edges)

    best = None
    for t in tracks:
        d = edge_dist(LineString([(t.x1, t.y1), (t.x2, t.y2)])) - t.width / 2.0
        rec = (round(d, 4), "track %s %s" % (t.net, t.layer))
        best = rec if best is None or rec < best else best
    for v in vias:
        d = edge_dist(Point(v.x, v.y)) - v.diameter / 2.0
        rec = (round(d, 4), "via %s" % v.net)
        best = rec if best is None or rec < best else best
    pad_best = None
    for p in pads:
        if p.kind == "npth":
            continue
        rec = (round(edge_dist(p.polygon), 4), "pad %s" % p.key)
        pad_best = rec if pad_best is None or rec < pad_best else pad_best
    out["copper_to_edge"] = {"routed_copper_mm": best[0] if best else None, "routed_item": best[1] if best else None,
                             "pad_mm": pad_best[0], "pad": pad_best[1],
                             "note": "edge = board outline, the locating slot and the NPTH hole wall; rule %.2f mm"
                                     % design.rules.copper_to_edge}

    # ---- the IMU -----------------------------------------------------------------------------------------
    if "U4" in design.parts_by_ref:
        u4 = design.part("U4")
        body = geometry.part_body_polygon(u4)
        own_nets = {p.net for p in pads if p.ref == "U4" and p.net}
        near_via = None
        for v in vias:
            d = body.distance(Point(v.x, v.y)) - v.diameter / 2.0
            rec = (round(d, 3), v.net)
            near_via = rec if near_via is None or rec < near_via else near_via
        near_trk = None                      # top-layer copper of nets that do not end on the IMU
        under = {}
        for t in tracks:
            line = LineString([(t.x1, t.y1), (t.x2, t.y2)])
            d = body.distance(line) - t.width / 2.0
            if t.layer == "F.Cu" and t.net not in own_nets:
                rec = (round(d, 3), t.net)
                near_trk = rec if near_trk is None or rec < near_trk else near_trk
            if d < 0:
                under.setdefault(t.layer, set()).add(t.net)
        near_part = None
        for p in design.parts:
            if p.ref == "U4" or not p.placed or p.side != u4.side:
                continue
            rec = (round(body.distance(geometry.part_body_polygon(p)), 3), p.ref)
            near_part = rec if near_part is None or rec < near_part else near_part
        ko = next((k for k in design.keepouts if k.name == "under_U4"), None)
        in_ko = []
        if ko is not None:
            kp = geometry.keepout_polygon(ko)
            for t in tracks:
                if t.layer == "F.Cu" and kp.distance(LineString([(t.x1, t.y1), (t.x2, t.y2)])) < t.width / 2.0 - 1e-6:
                    in_ko.append(t.net)
            for v in vias:
                if kp.distance(Point(v.x, v.y)) < v.diameter / 2.0 - 1e-6:
                    in_ko.append("via " + v.net)
        out["imu"] = {
            "nearest_via_mm": near_via[0] if near_via else None, "nearest_via_net": near_via[1] if near_via else None,
            "nearest_foreign_top_track_mm": near_trk[0] if near_trk else None,
            "nearest_foreign_top_track_net": near_trk[1] if near_trk else None,
            "nearest_part_mm": near_part[0], "nearest_part": near_part[1],
            "distance_to_regulators_and_charger_mm": {
                r: round(body.distance(geometry.part_body_polygon(design.part(r))), 2)
                for r in ("U7", "U8", "U9", "U11") if r in design.parts_by_ref},
            "nets_with_tracks_under_the_body": {k: sorted(v) for k, v in sorted(under.items())},
            "copper_in_the_F_Cu_keepout_under_the_body": sorted(set(in_ko)),
            "note": "distances from the body outline (3.0 x 2.5 mm); tracks under the body on F.Cu can only "
                    "be the stubs of its own pads outside the rule area under_U4; inner and bottom layers "
                    "are not restricted by the spec"}
    # ---- sensitive nets: crystal, photodiode input, USB pair ---------------------------------------
    def net_lines(names):
        return [(t, LineString([(t.x1, t.y1), (t.x2, t.y2)])) for t in tracks if t.net in names]

    def nearest_foreign(names, same_layer_only):
        """(gap, foreign net, layer of the foreign track) of the copper nearest to the tracks of ``names``."""
        mine = net_lines(names)
        best = None
        if not mine:
            return None
        others = [(t, LineString([(t.x1, t.y1), (t.x2, t.y2)])) for t in tracks if t.net not in names]
        tree2 = STRtree([g for _t, g in others])
        for t, g in mine:
            for j in tree2.query(g.buffer(2.0)):
                o, og = others[int(j)]
                if same_layer_only and o.layer != t.layer:
                    continue
                d = g.distance(og) - t.width / 2.0 - o.width / 2.0
                rec = (round(d, 3), o.net, o.layer)
                best = rec if best is None or rec < best else best
        return best

    sens = {}
    for label, names in (("crystal", ("OSC32_IN", "OSC32_OUT")), ("photodiode_input", ("PD_K",))):
        if not any(n in design.nets for n in names):
            continue
        row = {"nets": {n: {"length_mm": per_net.get(n, {}).get("length_mm"), "vias": per_net.get(n, {}).get("vias")}
                        for n in names if n in per_net}}
        nf = nearest_foreign(set(names), True)
        if nf:
            row["nearest_foreign_track_same_layer"] = {"gap_mm": nf[0], "net": nf[1], "layer": nf[2]}
        sens[label] = row
    if "PD_K" in design.nets:
        clock = {"MCO", "CAM_XVCLK"}
        pk = net_lines({"PD_K", "OPAMP_OUT", "VBIAS"})
        ck = net_lines(clock)
        if pk and ck:
            d = min((g.distance(h), t.layer, o.layer) for t, g in pk for o, h in ck)
            sens["photodiode_input"]["to_camera_clock_copper_mm"] = {"distance": round(d[0], 2),
                                                                      "layers": [d[1], d[2]]}
        fb = [r for r in ("R28", "C33") if r in design.parts_by_ref]
        if fb and "U1" in design.parts_by_ref:
            pin = {p.net: p for p in pads if p.ref == "U1" and p.net in ("PD_K", "OPAMP_OUT")}
            sens["photodiode_input"]["feedback_parts_to_their_mcu_pads_mm"] = {
                r: round(min(geometry.part_body_polygon(design.part(r)).distance(q.polygon) for q in pin.values()), 2)
                for r in fb} if pin else {}
            for other, key in (("U9", "feedback_parts_to_charger_mm"), ("R9", "feedback_parts_to_clock_resistor_mm")):
                if other in design.parts_by_ref:
                    ob = geometry.part_body_polygon(design.part(other))
                    sens["photodiode_input"][key] = round(min(
                        geometry.part_body_polygon(design.part(r)).distance(ob) for r in fb), 1)
    if "USB_DM" in design.nets and "USB_DP" in design.nets:
        usb = {n: per_net.get(n, {}) for n in ("USB_DM", "USB_DP")}
        dm, dp = net_lines({"USB_DM"}), net_lines({"USB_DP"})
        far = None
        if dm and dp:
            # how far apart the two lines run: for points along D-, the distance to D+ copper (any layer)
            far = max(min(g.interpolate(f, normalized=True).distance(h) for _o, h in dp)
                      for _t, g in dm for f in (0.0, 0.5, 1.0))
        sens["usb_pair"] = {"USB_DM_mm": usb["USB_DM"].get("length_mm"), "USB_DP_mm": usb["USB_DP"].get("length_mm"),
                            "vias": {n: usb[n].get("vias") for n in usb},
                            "largest_separation_mm": None if far is None else round(far, 2),
                            "note": "full-speed USB (12 Mbit/s): the router has no differential-pair mode; the two "
                                    "nets are ordinary tracks"}
    out["sensitive_nets"] = sens
    return out


def markdown(q):
    """The figures as a short Markdown text (for LAYOUT_LOG.md / the README)."""
    L = []
    cb = q.get("camera_bus")
    if cb:
        L.append("- Camera bus (%d nets after the series arrays): %.1f mm of track for %.1f mm of spanning "
                 "trees (x%.2f), %d vias." % (cb["nets"], cb["length_mm"], cb["tree_mm"], cb["ratio"], cb["vias"]))
    a = q.get("all_signal_nets", {})
    if a.get("signal_tree_mm"):
        L.append("- All routed signal nets: %.0f mm of track for %.0f mm of spanning trees (x%.2f), %s nets "
                 "over x1.5." % (a["signal_length_mm"], a["signal_tree_mm"], a["signal_ratio"], a["nets_over_1_5"]))
    for cam, s in sorted(q.get("camera_skew", {}).items()):
        if s.get("spread_against_pclk_mm"):
            L.append("- %s: ball-to-MCU lengths %.1f to %.1f mm, PCLK %.1f mm; the other ten lines are %+.1f to "
                     "%+.1f mm against PCLK (%+.0f to %+.0f ps)."
                     % (cam, s["shortest_mm"], s["longest_mm"], s["pclk_mm"], s["spread_against_pclk_mm"][0],
                        s["spread_against_pclk_mm"][1], s["spread_against_pclk_ps"][0],
                        s["spread_against_pclk_ps"][1]))
    v = q.get("vias", {})
    L.append("- Vias: %d (%d of them plane connections); by class %s."
             % (v.get("total", 0), v.get("on_plane_nets", 0),
                ", ".join("%s %d" % kv for kv in sorted(v.get("by_net_class", {}).items()))))
    vp = q.get("via_to_top_pad", {})
    if vp.get("own_net"):
        L.append("- Smallest via-to-pad gap on the top side: %.3f mm to a pad of its own net (%s), %s to a "
                 "pad of another net%s."
                 % (vp["own_net"]["gap_mm"], vp["own_net"]["pad"],
                    "%.3f mm" % vp["other_net"]["gap_mm"] if vp.get("other_net") else "n/a",
                    " (%s)" % vp["other_net"]["pad"] if vp.get("other_net") else ""))
    for side, w in sorted(q.get("solder_mask", {}).items()):
        if w.get("smallest_web_mm") is not None:
            L.append("- Smallest solder-mask web, %s: %.3f mm (%s / %s); %d touching openings of different nets."
                     % (side, w["smallest_web_mm"], w["between"][0], w["between"][1],
                        w["touching_openings_of_different_nets"]))
    ce = q.get("copper_to_edge", {})
    if ce:
        L.append("- Copper to edge: routed copper %.3f mm (%s), pads %.3f mm (%s)."
                 % (ce["routed_copper_mm"], ce["routed_item"], ce["pad_mm"], ce["pad"]))
    imu = q.get("imu")
    if imu:
        L.append("- IMU: nearest via %.2f mm (%s), nearest top-layer track of a foreign net %.2f mm (%s), "
                 "nearest part %.2f mm (%s); to U7 / U8 / U9 / U11: %s mm; tracks under the body: %s; copper "
                 "in the F.Cu rule area: %s."
                 % (imu["nearest_via_mm"], imu["nearest_via_net"], imu["nearest_foreign_top_track_mm"],
                    imu["nearest_foreign_top_track_net"], imu["nearest_part_mm"], imu["nearest_part"],
                    " / ".join("%.1f" % imu["distance_to_regulators_and_charger_mm"].get(r, float("nan"))
                               for r in ("U7", "U8", "U9", "U11")),
                    "; ".join("%s: %s" % (k, ", ".join(v)) for k, v in imu["nets_with_tracks_under_the_body"].items())
                    or "none",
                    ", ".join(imu["copper_in_the_F_Cu_keepout_under_the_body"]) or "none"))
    sn = q.get("sensitive_nets", {})
    c = sn.get("crystal")
    if c:
        nf = c.get("nearest_foreign_track_same_layer")
        L.append("- Crystal: %s; nearest foreign track on the same layer %s."
                 % (", ".join("%s %.1f mm, %d via(s)" % (n, v["length_mm"] or 0.0, v["vias"] or 0)
                              for n, v in sorted(c["nets"].items())),
                    "%.2f mm (%s, %s)" % (nf["gap_mm"], nf["net"], nf["layer"]) if nf else "n/a"))
    pd = sn.get("photodiode_input")
    if pd:
        nf = pd.get("nearest_foreign_track_same_layer")
        L.append("- Photodiode input PD_K: %s; nearest foreign track on the same layer %s; nearest camera-clock "
                 "copper (MCO / CAM_XVCLK) to the amplifier nets %s; feedback parts R28 / C33 %s from their MCU "
                 "pads, %s mm from the charger, %s mm from R9."
                 % (", ".join("%.1f mm, %d via(s)" % (v["length_mm"] or 0.0, v["vias"] or 0) for v in pd["nets"].values()),
                    "%.2f mm (%s, %s)" % (nf["gap_mm"], nf["net"], nf["layer"]) if nf else "n/a",
                    "%.1f mm (%s / %s)" % (pd["to_camera_clock_copper_mm"]["distance"],
                                           pd["to_camera_clock_copper_mm"]["layers"][0],
                                           pd["to_camera_clock_copper_mm"]["layers"][1])
                    if pd.get("to_camera_clock_copper_mm") else "n/a",
                    " / ".join("%.2f mm" % v for v in pd.get("feedback_parts_to_their_mcu_pads_mm", {}).values()) or "n/a",
                    pd.get("feedback_parts_to_charger_mm"), pd.get("feedback_parts_to_clock_resistor_mm")))
    u = sn.get("usb_pair")
    if u:
        L.append("- USB pair: D- %.1f mm, D+ %.1f mm, vias %s / %s, largest distance between the two lines %s mm."
                 % (u["USB_DM_mm"] or 0.0, u["USB_DP_mm"] or 0.0, u["vias"].get("USB_DM"), u["vias"].get("USB_DP"),
                    u["largest_separation_mm"]))
    return "\n".join(L) + "\n"
