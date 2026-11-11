#!/usr/bin/env python3
"""GL-1 dimensioned drawings (PDF + SVG per sheet, DXF of the 2D profiles), generated from the CAD solids.

    python3 cad/drawings.py           # writes drawings/GL1-001 ... GL1-020 (.pdf, _sheetN.svg) and drawings/dxf/*.dxf
    python3 cad/drawings.py GL1-011   # only the drawings whose number is named (no DXF), for a quick look

Views are hidden-line projections (OCC HLR) and true boolean sections of the same solids that are exported to STEP.
Every dimension value is computed from params (the YAML and its derived numbers); nothing is typed in as a number.
"""
from __future__ import annotations
import math, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from shapely.geometry import box as sbox
import params as P
import parts as PT
import assembly as A
import geom as G
import optics as O
import holddown as H
import drawlib as D
from drawlib import Sheet, fmt, co, C_DIM

M = P.MECH
DRAW_DIR = P.MECH_DIR / "drawings"
DXF_DIR = DRAW_DIR / "dxf"
TOL_PRINT = "printed: +-0.3 or +-0.3 % (bureau MJF), as printed"
TOL_REF = "nominal CAD dimensions, reference only"

STYLE = {            # section fill: face colour, hatch
    "tub": ("#c5c9d1", "////"), "base_plate": ("#a9b7d3", "\\\\\\\\"), "main_pcb": ("#86c493", None), "pcb_adhesive": ("#f2d24f", None),
    "seal_bead": ("#f08a24", None), "lcd_glass": ("#c9d8c5", None), "lcd_flex": ("#e09a2a", None), "lcd_adhesive": ("#f2d24f", None),
    "cover_glass": ("#d3eaf8", None), "cover_tape": ("#4a4a4a", None), "battery": ("#dadbe0", "...."), "foam_pad": ("#b89acb", None),
    "vent": ("#ffffff", None), "cradle": ("#cfd4dc", "////"), "cradle_pcb": ("#74b6d2", None),
    "usb_receptacle": ("#dcdce2", None), "grain_potting": ("#d8f1f4", None), "baffle_ring": ("#3a3a40", None), "baffle_adhesive": ("#f2d24f", None),
}
PREFIX_STYLE = {"camera_": ("#9494aa", None), "prism_": ("#bfe3f7", None), "visor_window_": ("#cdeaf8", None), "ball_epoxy_": ("#7fb4dc", None),
                "window_bond_": ("#f2d24f", None), "hood_seal_": ("#2b2b2b", None),
                "ball_": ("#f2f2f6", None), "battery_lead_": ("#d8a070", None),
                "spring_pin_": ("#e3bb4b", None), "cradle_foot_": ("#5a5a5a", None)}


def style(name):
    if name in STYLE:
        return STYLE[name]
    for k, v in PREFIX_STYLE.items():
        if name.startswith(k):
            return v
    return ("#cccccc", None)


def draw_section(view, parts, names, axis, value, clip=None, lw=0.45):
    """Fill the true section of every named part. Returns {name: shapely geometry} (2D section coordinates)."""
    out = {}
    order = sorted(names, key=lambda n: 0 if n in ("tub", "base_plate", "cradle") else 1)
    for n in order:
        if n not in parts or parts[n].group == "alt":
            continue
        g = G.section_polys(A.solid_of(parts[n]), axis, value)
        if clip is not None:
            g = g.intersection(sbox(*clip))
        if g.is_empty:
            continue
        fc, hatch = style(n)
        if n == "base_plate" and not P.BASE["printed"]:
            fc, hatch = "#9fb89a", "xxxx"                      # FR-4 plate: laminate hatch
        view.fill(g, fc=fc, hatch=hatch, lw=lw)
        out[n] = g
    return out


def _save(name, sheets):
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
    pdf = DRAW_DIR / f"{name}.pdf"
    with PdfPages(pdf) as pp:
        for i, sh in enumerate(sheets):
            pp.savefig(sh.fig)
            sh.fig.savefig(DRAW_DIR / (f"{name}_sheet{i + 1}.svg" if len(sheets) > 1 else f"{name}.svg"))
            plt.close(sh.fig)
    return pdf


def _triad(sh, x, y, hx, hy, lx="+x", ly="+y", size=9.0):
    """Coordinate triad in page space: hx, hy = page directions of the two model axes."""
    ax = sh.ax
    for d, lab in ((hx, lx), (hy, ly)):
        d = np.asarray(d, float)
        ax.annotate("", xy=(x + d[0] * size, y + d[1] * size), xytext=(x, y), arrowprops=dict(arrowstyle="-|>", lw=0.7, color="k", mutation_scale=7))
        ax.text(x + d[0] * (size + 2.6), y + d[1] * (size + 2.6), lab, fontsize=6.5, ha="center", va="center")


PUCK_OUTSIDE = ["tub", "base_plate", "cover_glass", "visor_window_L", "visor_window_R", "ball_1", "ball_2", "ball_3", "seal_bead"]


# ==============================================================================================
# GL1-001 assembly outline
# ==============================================================================================
def gl1_001(parts):
    sh = Sheet("GL1-001", "Marker assembly - outline", 1, 1, part="marker assembly", material="see parts list in README.md",
               process="assembly (bonded)", tolerance=TOL_REF, scale="3:1 / 4:1", params_rev=P.REV)
    S = {n: parts[n] for n in PUCK_OUTSIDE}
    R, T, yv = P.R_OUT, P.T, P.Y_VISOR
    hx = P.HORN_X_OUT
    cxr = P.CAM_XY["R"][0]
    zax = P.AXIS_Z
    # ---------------- plan view 3:1
    v = sh.view((90, 174), 3.0, "TOP VIEW   3:1", (16, 268))
    v.hlr([S[n] for n in ("tub", "cover_glass", "visor_window_L", "visor_window_R")], "top")
    v.circle((0, 0), P.APERTURE_D / 2, lw=0.3, color="#666", ls=(0, (4, 2.5)))
    v.centerline((-R - 2, 0), (R + 2, 0)); v.centerline((0, -R - 2), (0, yv + 2))
    for cx in (-cxr, cxr):
        v.centerline((cx, yv - 4.5), (cx, yv + 1.5), ext=0)
    v.dim_h(-R, R, 0, 0, 0, at=v.Y(-R) - 8, prefix="Ø")
    v.dim_v(-R, yv, 0, 0, 0, at=v.X(-R) - 6)
    v.dim_h(-hx, hx, yv, yv, 6, suffix="  flat")
    v.dim_h(-cxr, cxr, yv, yv, 12.5, suffix="  camera baseline")
    v.dim_v(0, yv, hx, hx, 0, at=v.X(hx) + 5)
    vx, vy = P.VENT_XY
    a40 = math.radians(-35)
    lab = [((cxr, yv - 0.25), f"visor window (x2)\n{fmt(P.WIN_W)} x {fmt(P.WIN_H)} x {fmt(P.WIN_T)}"),
           ((0.5, 16.4), f"nose index groove\n{fmt(M['nose_w'])} wide x {fmt(M['nose_depth'])} deep"),
           ((P.RECESS_D / 2 * math.cos(math.radians(28)), P.RECESS_D / 2 * math.sin(math.radians(28))), f"glass recess Ø{fmt(P.RECESS_D)}\nx {fmt(P.RECESS_DEPTH)} deep"),
           ((P.CG_D / 2 * math.cos(math.radians(8)), P.CG_D / 2 * math.sin(math.radians(8))), f"cover glass\nØ{fmt(P.CG_D)} x {fmt(P.CG_T)}"),
           ((vx, vy), f"vent hole Ø{fmt(P.VENT_HOLE_D)} at x {co(vx)}, y {co(vy)},\ndrain grooves {fmt(M['vent_groove_w'])} x {fmt(M['vent_groove_d'])} deep"),
           ((P.APERTURE_D / 2 * math.cos(a40), P.APERTURE_D / 2 * math.sin(a40)), f"display aperture\nØ{fmt(P.APERTURE_D)} (under glass)"),
           ((R * math.cos(math.radians(-48)), R * math.sin(math.radians(-48))), f"outline R{fmt(R)},\nflat at y = {co(yv)}")]
    v.label_column(lab, 167, side="right", fs=6.2, min_gap=8.0, y_min=124, y_max=236)
    v.view_arrow((0, yv + 14.0), (0, -1), "F")
    v.view_arrow((R + 3.0, -21.0), (-1, 0), "S")
    _triad(sh, 178, 88, (1, 0), (0, 1))
    # ---------------- front view (on the visor, from +y) 4:1 ; page x = -x
    sf = 4.0
    f = sh.view((306, 226), sf, "VIEW F - on the visor face, from +y   4:1   (+x is to the LEFT in this view)", (212, 277))
    f.hlr([S[n] for n in PUCK_OUTSIDE], "front")
    f.centerline((-R - 1.5, zax), (R + 1.5, zax))
    f.centerline((0, -1.2), (0, T + 1.2))
    for u in (-cxr, cxr):
        f.centerline((u, P.WIN_Z0 - 0.8), (u, T + 0.8), ext=0)
    f.dim_v(0, T, -R, -R, 0, at=f.X(-R) - 5)
    f.dim_v(0, zax, R, R, 0, at=f.X(R) + 5)
    f.dim_h(-cxr, 0, T, T, 5); f.dim_h(0, cxr, T, T, 5)
    f.dim_h(-cxr - P.WIN_RECESS_W / 2, -cxr + P.WIN_RECESS_W / 2, T, T, 11, suffix=" recess", text_side="right")
    f.dim_h(cxr - P.OPEN_HALF_W, cxr + P.OPEN_HALF_W, P.OPEN_Z0, P.OPEN_Z0, 0, at=f.Y(0) - 6, suffix=" clear opening", text_side="left")
    f.dim_v(P.WIN_Z0, P.WIN_Z1, -cxr + P.WIN_RECESS_W / 2, -cxr + P.WIN_RECESS_W / 2, 5, suffix=" recess", text_side="right")
    f.dim_v(P.OPEN_Z0, P.OPEN_Z1, cxr - P.OPEN_HALF_W, cxr - P.OPEN_HALF_W, -5, suffix=" opening", text_side="left")
    f.leader((-6.0, P.LEDGE_Z0), f"visor wall underside z = {fmt(P.LEDGE_Z0)}; base plate edge below", -30, -15, ha="right", color=C_DIM)
    f.leader((-P.BALL_XY[0][0], -P.BALL_PROT), f"ball feet Ø{fmt(P.BALL_D)}, {fmt(P.BALL_PROT)} below the base plane (x3)", 10, -13, color=C_DIM)
    f.leader((6.0, 0.5 * P.RIM_Z), f"base plate edge; tub rim {fmt(P.RIM_Z)} above the base plane", 8, -19, color=C_DIM)
    f.ax.text(f.X(-18.4), f.Y(zax) + 1.5, "optical axis", fontsize=5.8, color="#b02020", ha="center")
    f.ax.text(f.X(-cxr), f.Y(T) + 17, "camera R", fontsize=6.5, ha="center"); f.ax.text(f.X(cxr), f.Y(T) + 17, "camera L", fontsize=6.5, ha="center")
    # ---------------- side view (from +x) 4:1 ; page x = +y
    s = sh.view((306, 148), sf, "VIEW S - from +x   4:1", (212, 192))
    s.hlr([S[n] for n in PUCK_OUTSIDE], "right")
    s.centerline((0, -1.5), (0, T + 1.5)); s.centerline((-R - 1.5, zax), (yv + 1.5, zax))
    (b1x, b1y), (b2x, b2y), _ = P.BALL_XY
    s.dim_h(b2y, 0, -P.BALL_PROT, -P.BALL_PROT, 0, at=s.Y(0) - 5, suffix=" ball feet 2, 3")
    s.dim_h(0, b1y, -P.BALL_PROT, -P.BALL_PROT, 0, at=s.Y(0) - 5, suffix=" ball foot 1")
    s.dim_h(-R, 0, 0, 0, 0, at=s.Y(0) - 11); s.dim_h(0, yv, 0, 0, 0, at=s.Y(0) - 11)
    s.dim_h(-R, yv, 0, 0, 0, at=s.Y(0) - 17)
    s.dim_v(0, T, -R, -R, 0, at=s.X(-R) - 5)
    s.dim_v(0, zax, yv, yv, 0, at=s.X(yv) + 5)
    s.leader((-R + 0.18, T - 0.18), f"top edge R{fmt(M['top_fillet'])} (arc only)", 8, 9, color=C_DIM)
    s.leader((-R + 0.15, P.RIM_Z + 0.15), f"rim {fmt(P.RIM_Z)} above the base plane (rim relief),\nbottom chamfer {fmt(M['bottom_chamfer'])} x 45° (arc only)", -3, -27, ha="left", color=C_DIM)
    s.leader((7.0, P.CG_Z1), f"cover glass {fmt(P.CG_BELOW_FLUSH)} below flush", 6, 8, color=C_DIM)
    s.leader((yv, 2.5), "visor (flat) face", 4, -22, ha="left", color=C_DIM)
    # ---------------- notes
    sh.note(16, 76, [
        "1. Outline of the assembled marker. Datum: the base plane z = 0 = underside of the base plate; the three ball feet protrude",
        f"   {fmt(P.BALL_PROT)} mm below it and the rim of the tub wall stays {fmt(P.RIM_Z)} mm above it (rim relief). Visor (flat) face at y = {co(yv)}.",
        f"2. Envelope Ø{fmt(2 * R)} x {fmt(T)} mm. Rev D stack: base plate {fmt(P.BASE_T)} (FR-4) + adhesive sheet {fmt(P.PSA_T)}, PCB at z {fmt(P.PCB_Z0)} to {fmt(P.PCB_Z1)}; optical axis",
        f"   {fmt(zax)} above the base plane. Camera baseline {fmt(2 * cxr)} (x = +-{fmt(cxr)}). Cover glass {fmt(P.CG_BELOW_FLUSH)} below the top face.",
        f"3. Camera windows {fmt(P.WIN_W)} x {fmt(P.WIN_H)} x {fmt(P.WIN_T)} mm borosilicate, centred on x = +-{fmt(cxr)}, in recesses {fmt(P.WIN_RECESS_W)} wide x {fmt(P.WIN_RECESS_DEPTH)} deep from z = {fmt(P.WIN_Z0)}",
        f"   to the top face: glass {fmt(P.WIN_SUBFLUSH)} below the visor face, its top edge {fmt(P.WIN_TOP_BELOW)} below the tub top. Clear opening {fmt(2 * P.OPEN_HALF_W)} wide, z = {fmt(P.OPEN_Z0)} to {fmt(P.OPEN_Z1)}.",
        "4. Sections A-A and B-B: GL1-002. Parts: GL1-010 tub, GL1-011 base plate (FR-4), GL1-012 base plate (PA12 alternative), GL1-013 baffle ring, GL1-020 cradle.",
        "5. Nothing has been built. All purchased-part envelopes are provisional until checked against manufacturer drawings.",
    ], fs=6.2, title="NOTES")
    sh.table(212, 112, [["Item", "Value", "Source"],
                        ["Envelope", f"Ø{fmt(2 * R)} x {fmt(T)}", "YAML envelope"],
                        ["Visor flat", f"y = {co(yv)}, {fmt(2 * hx)} wide", "YAML / derived"],
                        ["Camera baseline", f"{fmt(2 * cxr)} (x = +-{fmt(cxr)})", "YAML cameras"],
                        ["Optical axis height", f"{fmt(zax)}", "YAML prisms"],
                        ["Field required", f"+-{fmt(P.FOV_H)}° h, +{fmt(P.FOV_UP)}° ({fmt(P.FOV_UP_GUAR)}° guaranteed) / -{fmt(P.FOV_DOWN)}° v", "YAML cameras"],
                        ["Ball feet", f"Ø{fmt(P.BALL_D)}, {fmt(P.BALL_PROT)} proud, at (0, {co(b1y)}), (+-{fmt(abs(b2x))}, {co(b2y)})", "YAML feet"],
                        ["Rim relief", f"tub wall from z = {fmt(P.RIM_Z)}", "YAML envelope"]],
             [32, 62, 34], fs=5.8)
    return _save("GL1-001_assembly_outline", [sh])


# ==============================================================================================
# GL1-002 sections
# ==============================================================================================
def _stack_levels_centre():
    return [(0.0, ""), (P.BASE_T, ""), (P.PCB_Z0, ""), (P.PCB_Z1, ""), (P.BAT["z1"], ""), (P.BAT["z1"] + P.BAT_SWELL, ""), (P.FOAM_Z0, ""), (P.LCD_Z0, ""),
            (P.LCD_Z1, ""), (P.BOND_Z, ""), (P.RECESS_FLOOR_Z, ""), (P.CG_Z0, ""), (P.CG_Z1, ""), (P.T, ""), (P.ROOF_Z, ""),
            (P.LEDGE_Z0, ""), (P.LEDGE_Z1, "")]


def gl1_002(parts):
    puck = [n for n, i in parts.items() if i.group == "puck"]
    sheets = []
    R, T, yv = P.R_OUT, P.T, P.Y_VISOR
    # ------------------------------------------------------------------ sheet 1: A-A on x = 0
    sh = Sheet("GL1-002", "Marker sections A-A and B-B", 1, 2, part="marker assembly", material="see parts list in README.md",
               process="assembly (bonded)", tolerance=TOL_REF, scale="7:1 / 18:1", params_rev=P.REV)
    sc = 7.0
    v = sh.view((20 + R * sc, 212), sc, "SECTION A-A   on x = 0, seen from +x (visor at the right)   7:1", (20, 278))
    g = draw_section(v, parts, puck, "x", 0.0)
    v.centerline((-R - 1, 0), (yv + 1, 0), color="#888")
    v.dim_h(-R, yv, 0, 0, 0, at=v.Y(0) - 20)
    v.dim_h(-P.BASE_R, P.BASE_FLAT, 0, 0, 0, at=v.Y(0) - 13, suffix=" base plate")
    v.dim_h(P.GRAIN_Y - P.GRAIN_R, P.GRAIN_Y + P.GRAIN_R, 0, 0, 0, at=v.Y(0) - 6, prefix="Ø", suffix=" grain opening")
    v.dim_v(0, T, -R, -R, 0, at=v.X(-R) - 6)
    j1 = next(p for p in P.TOP_PARTS if p["ref"] == "J1"); u1 = next(p for p in P.TOP_PARTS if p["ref"] == "U1")
    top = [((-18.5, 0.5 * (P.BOND_Z + T)), f"thick roof {fmt(T - P.BOND_Z)}"), ((-9.0, 0.5 * (P.CG_Z0 + P.CG_Z1)), "cover glass"),
           ((-0.5 * (P.CG_D + M["cover_tape_id"]) / 2, 0.5 * (P.RECESS_FLOOR_Z + P.CG_Z0)), f"tape ring {fmt(P.CG_TAPE_T)}"),
           ((-15.5, 0.5 * (P.LCD_Z0 + P.LCD_Z1)), "LCD glass"), ((3.0, P.LCD_Z1 + 0.07), "LCD adhesive frame"),
           ((-17.3, 4.4), "LCD flex tail (representative)"), ((-3.0, P.FOAM_Z0 + 0.15), "foam pad"), ((11.2, 0.5 * (P.BOND_Z + P.RECESS_FLOOR_Z)), "roof ledge"),
           ((16.2, P.T - 0.5), "nose groove"), ((yv - 0.4, 3.5), "visor wall 0.8")]
    bot = [((-21.6, 1.0), "seal adhesive"), ((-22.5, P.RIM_Z), f"rim z {fmt(P.RIM_Z)}"), ((P.PAD_Y, 0.5), "pad slot"), ((j1["y"], 2.8), "connector J1"), ((-7.0, 2.8), "battery"),
           ((P.GRAIN_Y - 0.5 * (P.BAFFLE_RI + P.BAFFLE_RO), 0.45), "baffle ring"), ((P.GRAIN_Y, 0.76), "photodiode"),
           ((P.GRAIN_Y + 5.3, 0.4), "clear potting"), ((u1["y"], 2.6), "MCU U1"),
           ((6.0, 1.4), f"PCB {fmt(P.PCB_T, 2)}"), ((10.0, 0.5 * (P.PSA_Z0 + P.PSA_Z1)), f"sheet {fmt(P.PSA_T, 2)}"), ((12.0, 0.4), f"FR-4 base {fmt(P.BASE_T, 2)}"),
           ((P.BALL_XY[0][1], 0.2), "ball foot 1")]
    v.label_row(top, v.Y(T) + 9, 24, 316, above=True)
    v.label_row(bot, v.Y(0) - 28, 24, 316, above=False)
    ya, yb = -15.2, -8.2
    v.frame(ya, -0.25, yb, T + 0.15, "C")
    # detail C
    sd = 18.0
    d = sh.view((60 - ya * sd, 24 + 0.25 * sd), sd, f"DETAIL C - z stack at the centre (x = 0, y = {co(ya)} to {co(yb)})   18:1", (16, 171))
    clip = (ya, -0.25, yb, T + 0.15)
    gd = draw_section(d, parts, puck, "x", 0.0, clip=clip, lw=0.55)
    d.frame(*clip)
    lev = [(0.0, "base plane"), (P.GRAIN_FILL_Z, "potting"), (P.BASE_T, ""), (P.PCB_Z0, ""), (P.PCB_Z1, ""), (P.BAT["z1"], ""), (P.FOAM_Z0, ""), (P.LCD_Z0, ""), (P.LCD_Z1, ""), (P.BOND_Z, ""),
           (P.RECESS_FLOOR_Z, ""), (P.CG_Z0, ""), (P.CG_Z1, ""), (P.T, "top"),
           (P.BAT["z1"] + P.BAT_SWELL, "")]
    d.levels(lev, ya, side="left", x_text=d.X(ya) - 9, fs=6.2)
    bat = P.BAT
    lab = [((-9.2, 0.5 * (bat["z0"] + bat["z1"])), f"battery {fmt(bat['z1'] - bat['z0'])}  (z {fmt(bat['z0'])} to {fmt(bat['z1'])})"),
           ((-9.2, bat["z1"] + P.BAT_SWELL / 2), f"swelling allowance {fmt(P.BAT_SWELL)}  (to z {fmt(bat['z1'] + P.BAT_SWELL)}), then {fmt(P.FOAM_Z0 - bat['z1'] - P.BAT_SWELL)} air"),
           ((-9.2, 0.5 * (P.FOAM_Z0 + P.FOAM_Z1)), f"foam pad {fmt(P.FOAM_T)}  (z {fmt(P.FOAM_Z0)} to {fmt(P.FOAM_Z1)})"),
           ((-8.6, 0.5 * (P.LCD_Z0 + P.LCD_Z1)), f"LCD glass {fmt(P.LCD_Z1 - P.LCD_Z0)}  (z {fmt(P.LCD_Z0)} to {fmt(P.LCD_Z1)})"),
           ((-12.2, 0.5 * (P.LCD_Z1 + P.BOND_Z)), f"LCD adhesive frame {fmt(P.LCD_PSA_T)}  (to z {fmt(P.BOND_Z)}, window Ø{fmt(M['lcd_psa_window_dia'])})"),
           ((-11.4, 0.5 * (P.BOND_Z + P.RECESS_FLOOR_Z)), f"roof ledge {fmt(P.ROOF_LEDGE_T)}  (z {fmt(P.BOND_Z)} to {fmt(P.RECESS_FLOOR_Z)}), aperture Ø{fmt(P.APERTURE_D)}"),
           ((-13.2, 0.5 * (P.RECESS_FLOOR_Z + P.CG_Z0)), f"transfer-tape ring {fmt(P.CG_TAPE_T)}  (Ø{fmt(P.CG_D)} / Ø{fmt(M['cover_tape_id'])})"),
           ((-9.5, 0.5 * (P.CG_Z0 + P.CG_Z1)), f"cover glass {fmt(P.CG_T)}  (top at z {fmt(P.CG_Z1)}, {fmt(P.CG_BELOW_FLUSH)} below flush)"),
           ((-14.7, 0.5 * (P.BOND_Z + P.T)), f"thick roof ring {fmt(P.T - P.BOND_Z)}  (z {fmt(P.BOND_Z)} to {fmt(P.T)}) round the recess Ø{fmt(P.RECESS_D)} x {fmt(P.RECESS_DEPTH)}"),
           ((-9.0, 0.5 * (P.PCB_Z0 + P.PCB_Z1)), f"main PCB {fmt(P.PCB_T)}  (z {fmt(P.PCB_Z0)} to {fmt(P.PCB_Z1)})"),
           ((-10.4, 0.5 * (P.PSA_Z0 + P.PSA_Z1)), f"adhesive sheet {fmt(P.PSA_T)}  (z {fmt(P.PSA_Z0)} to {fmt(P.PSA_Z1)}), die cut"),
           ((-12.5, 0.5 * P.BASE_T), f"base plate {fmt(P.BASE_T)}, routed FR-4  (z 0 to {fmt(P.BASE_T)})"),
           ((-9.6, 0.5), f"clear potting of the grain opening, down to z {fmt(P.GRAIN_FILL_Z)}"),
           ((-12.5, 0.5 * (P.PCB_Z1 + P.PCB_Z1 + j1["h"])), f"FPC connector J1, {fmt(j1['h'])} high (to z {fmt(P.PCB_Z1 + j1['h'])})")]
    d.label_column(lab, d.X(yb) + 9, side="right", fs=6.1, min_gap=4.1, y_min=28, y_max=164)
    sh.note(268, 164, [
        "1. Section on the plane x = 0 (the y axis through the centre).",
        "   No single vertical line crosses every layer: the battery ends at",
        f"   y = {co(bat['y'] - bat['dy'] / 2)}, the ledge and tape lie outside r = {fmt(P.APERTURE_D / 2)}.",
        "   Detail C therefore spans both.",
        f"2. Rev D stack: FR-4 base plate {P.BASE_T:.2f} / adhesive sheet {P.PSA_T:.2f} /",
        f"   PCB {P.PCB_T:.2f} (underside at z {fmt(P.PCB_Z0)}). The posts hold the PCB",
        f"   top at z = {fmt(P.PCB_Z1)}; the perimeter seal joint (base top to",
        f"   the seal face at z {fmt(P.LEDGE_Z0)}) is {fmt(P.BEAD_T)} mm high. Alternative",
        f"   build (GL1-012): PA12 plate {fmt(P.BASE_VARIANTS['pa12']['thickness'])} + sheet {fmt(P.BASE_VARIANTS['pa12']['psa_t'])}, joint {fmt(P.LEDGE_Z0 - P.BASE_VARIANTS['pa12']['thickness'])}.",
        "3. z values are heights above the base plane.",
        "4. Purchased parts are envelope solids.",
        f"5. On x = 0 the roof is the thick roof ({fmt(T - P.BOND_Z)}, underside",
        f"   z {fmt(P.BOND_Z)}) or the nose pad; the plain {fmt(P.ROOF_T)} roof",
        f"   (underside z {fmt(P.ROOF_Z)}) is on section B-B.",
        f"6. The tub wall ends at z = {fmt(P.RIM_Z)} (rim relief): base",
        "   plate and ball feet are the lowest surfaces.",
        f"7. Grain opening: clear potting from the PCB down to z {fmt(P.GRAIN_FILL_Z)}",
        f"   at most (shown); accepted z {fmt(P.potting_window()[0])} to {fmt(P.potting_window()[1])}. The crest of the",
        "   baffle ring GL1-013 is never covered by the potting.",
    ], fs=6.0, title="NOTES")
    sheets.append(sh)
    # ------------------------------------------------------------------ sheet 2: B-B on x = camera R
    cx, cy = P.CAM_XY["R"]
    sh = Sheet("GL1-002", "Marker sections A-A and B-B", 2, 2, part="marker assembly", material="see parts list in README.md",
               process="assembly (bonded)", tolerance=TOL_REF, scale="7:1 / 18:1", params_rev=P.REV)
    v = sh.view((20 + R * sc, 212), sc, f"SECTION B-B   on x = {fmt(cx)} through camera R, seen from +x (visor at the right)   7:1", (20, 278))
    g = draw_section(v, parts, puck, "x", cx)
    yb0 = -math.sqrt(R ** 2 - cx ** 2)
    v.centerline((yb0 - 1, P.AXIS_Z), (yv + 4, P.AXIS_Z))
    v.dim_h(yb0, yv, 0, 0, 0, at=v.Y(0) - 13, suffix=f"  (chord at x = {fmt(cx)})")
    v.dim_h(0, cy, P.CAM_Z0, P.CAM_Z0, 0, at=v.Y(0) - 6, suffix=" camera centre")
    v.dim_v(0, T, yb0, yb0, 0, at=v.X(yb0) - 6)
    u6 = next(p for p in P.TOP_PARTS if p["ref"] == "U6"); u7 = next(p for p in P.TOP_PARTS if p["ref"] == "U7")
    top = [((yb0 + 0.5, 4.0), "side wall 1.0"), ((15.6, P.T - 0.4), f"roof {fmt(P.ROOF_T)} over the prism bay"), ((-6.0, 0.5 * (P.CG_Z0 + P.CG_Z1)), "cover glass"),
           ((-12.0, 0.5 * (P.BOND_Z + P.ROOF_Z)), "thick roof (LCD bonding plane)"), ((2.0, 0.5 * (P.LCD_Z0 + P.LCD_Z1)), "LCD glass"),
           ((P.HOOD_REAR_Y0 + 0.4, 6.0), "hood rear wall"), ((15.9, 5.3), "fold prism"), ((yv - 0.25, 6.9), "visor window")]
    bot = [((yb0 + 1.2, 1.0), "seal adhesive"), ((u7["y"], 2.4), "LDO U7"), ((-5.2, 2.8), "battery"), ((-5.2, P.FOAM_Z0 + 0.15), "foam pad"),
           ((u6["y"], 2.2), "flash U6"), ((12.2, 2.2), "crystal Y1"), ((cy, 3.2), "camera cube"), ((2.0, 1.4), "PCB"), ((-12.0, 0.5), "base plate"),
           ((yb0 + 1.0, 1.7), "seating ledge")]
    v.label_row(top, v.Y(T) + 9, 24, 316, above=True)
    v.label_row(bot, v.Y(0) - 21, 24, 316, above=False)
    ya, yb = 12.6, 18.9
    v.frame(ya, -0.25, yb, T + 0.15, "D")
    d = sh.view((64 - ya * sd, 24 + 0.25 * sd), sd, f"DETAIL D - camera, prism and visor opening (x = {fmt(cx)})   18:1", (16, 176.5))
    clip = (ya, -0.25, yb, T + 0.15)
    gd = draw_section(d, parts, puck, "x", cx, clip=clip, lw=0.55)
    d.frame(*clip)
    # optical axis and the chief rays of the vertical field edges (exact trace, optics.py)
    d.centerline((cy - 0.6, P.AXIS_Z), (yb + 0.9, P.AXIS_Z))
    yr = yb + 0.25
    for tv, txt in ((0.0, f"axis z {fmt(P.AXIS_Z)}"), (math.tan(math.radians(M["fov_up_deg"])), f"+{fmt(M['fov_up_deg'])}°"),
                    (-math.tan(math.radians(M["fov_down_deg"])), f"-{fmt(M['fov_down_deg'])}°")):
        tr = O.trace("R", 0.0, tv)
        end = O.at_plane_y(tr, yr)
        pts = [tr["p0"], tr["p_entrance"], tr["p_hypotenuse"], tr["p_exit"], end]
        d.lines([np.array([(p[1], p[2]) for p in pts])], lw=0.4, color="#d01818", zorder=15)
        d.ax.text(d.X(yr) + 0.8, d.Y(end[2]), txt, fontsize=5.8, color="#d01818", va="center", ha="left",
                  bbox=dict(fc="white", ec="none", pad=0.4), zorder=31)
    lev = [(0.0, "base plane"), (P.BASE_T, "base top (FR-4)"), (P.PCB_Z0, "PCB bottom"), (P.PCB_Z1, "PCB top"), (P.CAM_Z1, "cube top"), (P.PRISM_Z0, "prism bottom"),
           (P.AXIS_Z, "optical axis"), (P.PRISM_Z1, "prism top"), (P.ROOF_Z, "roof underside"), (P.T, "top"),
           (P.WIN_Z0, "window recess"), (P.OPEN_Z0, "opening sill"), (P.LCD_Z0, "LCD"), (P.LCD_Z1, "")]
    d.levels(lev, ya, side="left", x_text=d.X(ya) - 9, fs=6.0)
    # horizontal chain above the detail: wall build-up in y
    yt = d.Y(T) + 4.5
    chain = [(P.HOOD_REAR_Y0, P.HOOD_REAR_Y1), (P.PRISM_Y0, P.PRISM_EXIT_Y), (P.PRISM_EXIT_Y, P.WIN_RECESS_FLOOR_Y), (P.WIN_RECESS_FLOOR_Y, yv)]
    d.dim_h(P.WIN_Y1, yv, T, T, 0, at=yt + 5.5, fs=5.8, text_side="right", suffix=" glass below the face")
    for a, b in chain:
        d.dim_h(a, b, T, T, 0, at=yt, fs=5.8, text_side="left" if a < 15 else "right")
    d.dim_h(P.LCD_Y1, cy - P.CAM_DY / 2, P.CAM_Z1 - 0.3, P.CAM_Z1 - 0.3, 0, at=d.Y(3.0), fs=5.8, text_side="left")
    d.dim_h(cy + P.CAM_DY / 2, P.HOOD_PAD_Y, 3.4, 3.4, 0, at=d.Y(2.35), fs=5.8, text_side="right")
    d.dim_h(P.HOOD_PAD_Y, P.WIN_RECESS_FLOOR_Y, P.WIN_Z0 + 0.2, P.WIN_Z0 + 0.2, 0, at=d.Y(3.75), fs=5.8, text_side="right")
    d.dim_h(P.Y_VISOR_IN, yv, 2.0, 2.0, 0, at=d.Y(1.55), fs=5.8, text_side="right")
    lab = [((cy + 0.4, 0.5 * (P.CAM_Z0 + P.CAM_Z1)), f"camera cube {fmt(P.CAM_DX)} x {fmt(P.CAM_DY)} x {fmt(P.CAM_H)}, centre y {fmt(cy)}"),
           ((P.PRISM_EXIT_Y - 0.5, P.PRISM_Z0 + 0.6), f"prism {fmt(P.PRISM_LEG)} legs, bond gap {fmt(P.PRISM_BOND)}, exit face y {fmt(P.PRISM_EXIT_Y)}"),
           ((P.PRISM_EXIT_Y - 0.3, P.PRISM_Z1 + P.PRISM_ROOF_CLR / 2), f"prism to roof {fmt(P.PRISM_ROOF_CLR)}"),
           ((0.5 * (P.WIN_Y0 + P.WIN_Y1), 7.2), f"window {fmt(P.WIN_T)} seated on the floor of the {fmt(P.WIN_RECESS_DEPTH)} recess, z {fmt(P.WIN_Z0)} to {fmt(P.WIN_TOP_Z)} ({fmt(P.WIN_TOP_BELOW)} below the top)"),
           ((P.WIN_Y1 + 0.3 * P.WIN_SILL_FILLET, P.WIN_Z0 + 0.3 * P.WIN_SILL_FILLET), f"adhesive fillet {fmt(P.WIN_SILL_FILLET)} on the shelf in front of the glass (part of the seal frame)"),
           ((P.WIN_RECESS_FLOOR_Y - 0.25, P.OPEN_Z0 + 0.25), f"opening z {fmt(P.OPEN_Z0)} to {fmt(P.OPEN_Z1)}, +-{fmt(P.OPEN_HALF_W)} wide, straight (no bevel)"),
           ((0.5 * (P.HOOD_PAD_Y + P.WIN_RECESS_FLOOR_Y), P.WIN_Z0 + 0.2), f"wall behind the recess {fmt(P.THIN_STRIP_T, 3)} (accepted, D04)"),
           ((P.HOOD_REAR_Y1 - 0.06, P.HOOD_Z_OVER_CUBE + 0.06), f"rear-wall edge chamfer {fmt(P.HOOD_REAR_CHAMFER, 2)}: {fmt(P.PRISM_HOOD_CLR, 2)} to the hypotenuse"),
           ((P.CAM_REAR_Y + 0.05, P.CAM_Z1 + 0.5 * P.HOOD_SLIT[0]), f"black gasket bead {fmt(M['hood_seal_w'])} x {fmt(M['hood_seal_free_h'])} astride the rear edge of the cube (slit {fmt(P.HOOD_SLIT[0], 2)})"),
           ((P.HOOD_PAD_Y + 0.1, M["hood_skirt_z0"] + 0.1), f"lead-in chamfer {fmt(P.HOOD_PAD_LEADIN, 3)} on the pad ({fmt(M['hood_leadin'])} on the skirts)"),
           ((P.Y_VISOR_IN + 0.4, 2.6), f"visor wall {fmt(P.VISOR_WALL)}, sits on the base at z {fmt(P.LEDGE_Z0)}"),
           ((P.BASE_FLAT - 0.4, 0.5), f"base plate under the wall to y {fmt(P.BASE_FLAT)}, plain edge"),
           ((P.PCB_FLAT - 0.5, 1.4), f"PCB flat edge y {fmt(P.PCB_FLAT)}"),
           ((P.LCD_Y1 - 0.3, 5.0), f"LCD glass edge y {fmt(P.LCD_Y1)}"),
           ((P.Y_VISOR_IN + 0.3, 1.03), f"front seal: {fmt(P.BEAD_T)} joint, {fmt(P.BASE_FLAT - P.LAND_FLAT_IN)} wide, under the visor wall")]
    d.label_column(lab, d.X(yb) + 24, side="right", fs=6.0, min_gap=6.2, y_min=30, y_max=166)
    sh.note(300, 166, [
        f"1. Stack: base {fmt(P.BASE_T)} + adhesive {fmt(P.PSA_T)} + PCB {fmt(P.PCB_T)} + cube",
        f"   {fmt(P.CAM_H)} + bond {fmt(P.PRISM_BOND)} + prism {fmt(P.PRISM_LEG)} = {fmt(P.PRISM_Z1)};",
        f"   clearance {fmt(P.PRISM_ROOF_CLR)}; roof {fmt(P.ROOF_T)}; top {fmt(P.T)}.",
        "2. Red: chief rays on axis and at the vertical",
        f"   field edges required (+{fmt(M['fov_up_deg'])}° / -{fmt(M['fov_down_deg'])}°), traced",
        f"   exactly through the prism (n = {M['n_prism']}). The lens",
        "   pupil position is ASSUMED (optics.py).",
        "3. The wall behind the window recess in front",
        f"   of the cube is {fmt(P.THIN_STRIP_T)} mm (accepted, D04).",
        f"   The {fmt(P.HOOD_SLIT[0], 2)}-{fmt(P.HOOD_SLIT[1], 2)} slit above the cube at the rear is",
        f"   closed by a black gasket bead ({fmt(M['hood_seal_w'])} x {fmt(M['hood_seal_free_h'])}, cured",
        f"   on the tub first; squeezed {100 * P.HOOD_SEAL_COMPRESSION:.0f} % by the cube).",
        "4. z = height above the base plane.",
        f"5. Rev D window: {fmt(P.WIN_W)} x {fmt(P.WIN_H)} x {fmt(P.WIN_T)} borosilicate, seated",
        f"   on the recess floor, {fmt(P.WIN_SUBFLUSH)} below the visor face;",
        f"   seats {fmt(P.WIN_LANDS[0], 2)} (sides) / {fmt(P.WIN_LANDS[1], 2)} (sill) / {fmt(P.WIN_LANDS[2], 2)} (top).",
        "   Sealed by a frame of thixotropic adhesive round",
        "   its edge: side gaps, top bead, sill fillet. Nothing",
        "   is wicked behind the glass (D30).",
    ], fs=6.0, title="NOTES")
    sheets.append(sh)
    return _save("GL1-002_sections", sheets)


# ==============================================================================================
# GL1-010 tub
# ==============================================================================================
def gl1_010(parts):
    tub = parts["tub"]
    R, T, yv = P.R_OUT, P.T, P.Y_VISOR
    cxr = P.CAM_XY["R"][0]
    mat, proc = "PA12 (HP 3D HR PA 12), dyed black", "HP Multi Jet Fusion + vapor smoothing"
    sheets = []
    # ------------------------------------------------------------------ sheet 1
    sh = Sheet("GL1-010", "Tub (top shell)", 1, 2, part="tub", material=mat, process=proc, tolerance=TOL_PRINT, scale="3.5:1 / 14:1", params_rev=P.REV)
    sc = 3.5
    v = sh.view((100, 172), sc, "VIEW FROM BELOW - into the cavity   3.5:1   (+x is to the LEFT, visor at the top)", (16, 268))
    v.hlr([tub], "bottom")
    v.centerline((-R - 2, 0), (R + 2, 0)); v.centerline((0, -R - 2), (0, yv + 2))
    v.dim_h(-R, R, 0, 0, 0, at=v.Y(-R) - 7, prefix="Ø")
    v.dim_h(-P.LCD_POCKET_X, P.LCD_POCKET_X, -17.6, -17.6, 0, at=v.Y(-R) - 13, suffix="  thick roof (LCD bonding plane z 5.55)")
    v.dim_h(-cxr, 0, yv, yv, 5); v.dim_h(0, cxr, yv, yv, 5)
    v.dim_h(-cxr - P.HOOD_OUT_HW, -cxr + P.HOOD_OUT_HW, yv, yv, 11, suffix=" hood", text_side="left")
    v.dim_h(cxr - P.HOOD_IN_HW, cxr + P.HOOD_IN_HW, yv, yv, 11, suffix=" bay", text_side="right")
    v.dim_v(0, P.LCD_POCKET_Y1, R, P.LCD_POCKET_X, 0, at=v.X(-R) - 5)
    v.dim_v(P.LCD_POCKET_Y0, 0, R, 8.0, 0, at=v.X(-R) - 5)
    for name, x0, x1, y0, y1 in P.post_rects():
        ux = -(x0 + x1) / 2
        loc = name[0] == M["locating_posts"]                   # keep the spigot visible: the name goes above the foot
        v.ax.text(v.X(ux), v.Y((y0 + y1) / 2) + (6.2 if loc else 0.0), name, fontsize=5.2, ha="center", va="center", color="#b02020", fontweight="bold", zorder=30,
                  bbox=dict(fc="white", ec="none", pad=0.3, alpha=0.85))
    vx, vy = P.VENT_XY
    a = math.radians(205)
    lab = [((-cxr - P.HOOD_OUT_HW + 0.4, 15.2), "camera hood: prism bay, side skirts\nto z 3.0, rear wall 0.8 (light baffle)"),
           ((-cxr + P.HOOD_IN_HW, 15.9), f"lead-in chamfers {fmt(M['hood_leadin'])} at the mouth of the hood\n(skirts and front pad, z {fmt(M['hood_skirt_z0'])})"),
           ((-P.LCD_POCKET_X - 0.4, 6.0), f"glass locating rib {fmt(M['lcd_rib_t'])} wide, x4 at the sides down to z {fmt(M['lcd_rib_z0'])};\nx2 at the rear down to z {fmt(P.LCD_REAR_RIB_Z0)} (stop for the tilted glass)"),
           ((-P.THICK_RING_R * math.cos(math.radians(20)), P.THICK_RING_R * math.sin(math.radians(20)) * 0 - 1.5), f"thick roof ring Ø{fmt(2 * P.THICK_RING_R)}\n(carries the glass recess)"),
           ((-vx, vy), f"vent pad {fmt(M['vent_pad'])} wide, out to the side wall, {fmt(M['vent_pad_h'])} proud,\nhole Ø{fmt(P.VENT_HOLE_D)} at x {co(vx)}, y {co(vy)}"),
           ((-P.APERTURE_D / 2 * math.cos(math.radians(-25)), P.APERTURE_D / 2 * math.sin(math.radians(-25))), f"display aperture Ø{fmt(P.APERTURE_D)}"),
           ((-P.LEDGE_RI * math.cos(math.radians(-40)), P.LEDGE_RI * math.sin(math.radians(-40))), f"seating ledge to r {fmt(P.LEDGE_RI)},\nz {fmt(P.LEDGE_Z0)} to {fmt(P.LEDGE_Z1)} (seal face below)"),
           ((-P.R_IN * math.cos(math.radians(-55)), P.R_IN * math.sin(math.radians(-55))), f"cavity wall R{fmt(P.R_IN)} (wall {fmt(P.WALL)})"),
           ((-6.5, -18.6), f"support post {fmt(P.KO_POST_SIZE)} x {fmt(P.KO_POST_SIZE)} (x6: A, C, E): see table"),
           ((-P.LOC_ROUND[0], P.LOC_ROUND[1]), f"post B (x2), foot {fmt(P.LOC_FOOT[0])} x {fmt(P.LOC_FOOT[1])}, with the PCB locating spigot\nØ{fmt(P.SPIGOT_D)} x {fmt(P.SPIGOT_H)}, tip chamfer {fmt(M['spigot_tip_chamfer'])} (tip at z {fmt(P.SPIGOT_Z0)})"),
           ((-0.9, 16.5), f"pad under the nose groove\n(keeps {fmt(P.MIN_WALL)} roof)")]
    v.label_column(lab, 186, side="right", fs=5.9, min_gap=7.6, y_min=96, y_max=246)
    _triad(sh, 36, 100, (-1, 0), (0, 1))
    # detail E: wall / ledge / roof on the arc, cut where the plain roof exists (section y = 0, the -x side)
    se = 14.0
    xa_, xb_ = -R - 0.35, -19.2
    d = sh.view((298 - xa_ * se, 150 + 0.3 * se), se, f"DETAIL E - wall, ledge and roof on the arc (section y = 0 at x = {co(-R)})   14:1", (262, 272))
    clip = (xa_, -0.3, xb_, T + 0.25)
    g = G.section_polys(A.solid_of(tub), "y", 0.0).intersection(sbox(*clip))
    d.fill(g, fc=style("tub")[0], hatch=style("tub")[1], lw=0.6)
    d.frame(*clip)
    d.levels([(0.0, "base plane (base plate underside)"), (P.RIM_Z, "rim of the wall"), (P.RIM_Z + M["bottom_chamfer"], "chamfer"), (P.LEDGE_Z0, "seal face"),
              (P.LEDGE_Z1, "ledge top"), (P.ROOF_Z, "roof underside"), (T - M["top_fillet"], "R start"), (T, "top")], xb_, side="right", x_text=d.X(xb_) + 6, fs=6.0)
    d.dim_h(-R, -P.R_IN, 3.6, 3.6, 0, at=d.Y(4.4), text_side="left", suffix=" wall")
    d.dim_h(-P.R_IN, -P.LEDGE_RI, P.LEDGE_Z1, P.LEDGE_Z1, 0, at=d.Y(3.0), text_side="right", suffix=" ledge")
    d.dim_v(P.ROOF_Z, T, -20.2, -20.2, 0, at=d.X(-20.2), text_side="below", suffix=" roof")
    d.leader((-R + 0.17, T - 0.17), f"R{fmt(M['top_fillet'])}", -6, 6, ha="right", color=C_DIM)
    d.leader((-R + 0.15, P.RIM_Z + 0.15), f"{fmt(M['bottom_chamfer'])} x 45°", -6, -5, ha="right", color=C_DIM)
    rows = [["Post", "x from", "x to", "y from", "y to", "foot", "spigot centre"]]
    for name, x0, x1, y0, y1 in P.post_rects():
        loc = name[0] == M["locating_posts"]
        sx_ = (P.LOC_ROUND if x0 > 0 else P.LOC_SLOT)[0]
        rows.append([name, co(x0), co(x1), co(y0), co(y1), f"{fmt(x1 - x0)} x {fmt(y1 - y0)}", f"({co(sx_)}, {co(P.LOC_ROUND[1])})" if loc else "-"])
    sh.table(262, 142, rows, [11, 16, 16, 16, 16, 19, 28], fs=5.6)
    sh.note(388, 142, ["All posts: PCB top", f"(z {fmt(P.PCB_Z1)}) to the roof.", "Feet lie inside the", "YAML keep-out", "squares (check 12);", f"posts B: {fmt(P.KO_LOC_SIZE)} square,", f"foot cut back to", f"|x| >= {fmt(P.LCD_POCKET_X)} for", "the LCD glass (D29)."], fs=5.2)
    sh.note(16, 71, [
        "1. Material HP 3D High Reusability PA 12, Multi Jet Fusion, dyed black, chemical vapor smoothing. Print roof-down (cosmetic top on the bed side, cavity open upward).",
        f"2. Minimum wall {fmt(P.MIN_WALL)} mm by design. Recorded exceptions: the {fmt(P.THIN_STRIP_T)} mm strip behind each window recess (D04, accepted), the feet of chamfered",
        f"   edges (side wall {fmt(P.WALL - M['bottom_chamfer'])} at the rim, hood rear wall {fmt(P.MIN_WALL - P.HOOD_REAR_CHAMFER, 2)}, hood skirts {fmt(P.MIN_WALL - M['hood_leadin'])} at their lead-in chamfer). See export/check_report.md, check 5.",
        "3. No closed void and no cavity without a 2 mm escape path (check 6). Depowder the two camera bays, the visor openings and the Ø1.0 vent hole with care.",
        "4. Critical-to-function: bonding plane z 5.55 (LCD), recess floor z 6.35 (cover glass), seal face z 1.2, post feet z 1.8 (all in one plane +-0.1), window recesses,",
        f"   ledge radius {fmt(P.LEDGE_RI)} (go gauge), bay roof {fmt(P.ROOF_Z - P.PCB_Z1)} above the post feet (go gauge). REQUIRED +-{fmt(M['tol_printed'])}, measured from the post feet: seal face {fmt(P.PCB_Z1 - P.LEDGE_Z0)} below",
        f"   them (it sets the seal joint), rim {fmt(P.PCB_Z1 - P.RIM_Z)} below them (it sets the rim relief). The bureau's general tolerance is wider: first-article inspection of these is a release gate.",
        f"5. Drop-in fits are {fmt(P.CLR)} mm nominal. The two spigots under posts B ({fmt(P.SPIGOT_SPAN)} apart; Ø{fmt(P.SPIGOT_D)} in a Ø{fmt(P.LOC_ROUND[2])} PCB hole at x = {co(P.LOC_ROUND[0])} and in a {fmt(P.LOC_SLOT[2])} x {fmt(P.LOC_SLOT[3])} slot at x = {co(P.LOC_SLOT[0])}) locate the PCB: go gauge Ø1.10 at first article (D19).",
        f"6. Camera hoods stay inside the YAML keep-out zones (camera x +-{fmt(P.KO_HOOD_HW)}, y {fmt(P.KO_HOOD_Y0)} to {fmt(P.KO_HOOD_Y1)}); skirts end at z {fmt(M['hood_skirt_z0'])} ({fmt(M['hood_skirt_z0'] - P.PCB_Z1)} above the PCB).",
        f"7. The side wall ends {fmt(P.RIM_Z)} mm above the base plane (rim relief): z values on this drawing are heights above the base plane, the tub itself is {fmt(T - P.RIM_Z)} tall.",
        f"   No key lug: the base plate has a plain edge and the seal face runs unbroken round the D. Vent: pad {fmt(M['vent_pad_h'])} proud, drain grooves {fmt(M['vent_groove_w'])} x {fmt(M['vent_groove_d'])} on the top face.",
        f"8. Rev D: spigots moved from posts E to posts B; posts E are plain. Window recesses unchanged ({fmt(P.WIN_RECESS_W)} x {fmt(P.WIN_RECESS_DEPTH)} deep, z {fmt(P.WIN_Z0)} to the top) for {fmt(P.WIN_W)} x {fmt(P.WIN_H)} x {fmt(P.WIN_T)} glass windows seated on the recess floor.",
        f"   The two rear glass ribs reach down to z {fmt(P.LCD_REAR_RIB_Z0)} (the free height above the PCB): the tilted LCD glass is pushed back against them. Nothing has been built.",
    ], fs=6.0, title="NOTES")
    sheets.append(sh)
    # ------------------------------------------------------------------ sheet 2
    sh = Sheet("GL1-010", "Tub (top shell)", 2, 2, part="tub", material=mat, process=proc, tolerance=TOL_PRINT, scale="2.5:1 / 5:1 / 12:1", params_rev=P.REV)
    v = sh.view((74, 212), 2.5, "TOP VIEW   2.5:1   (section planes A-A and B-B)", (16, 272))
    v.hlr([tub], "top")
    v.centerline((-R - 2, 0), (R + 2, 0))
    v.cut_line((0, -R - 1.5), (0, yv + 1.5), "A", ext=1.5, arrow_dir=(-1, 0))
    v.cut_line((cxr, -R + 2.5), (cxr, yv + 1.5), "B", ext=1.5, arrow_dir=(-1, 0))
    lab = [((P.RECESS_D / 2 * math.cos(math.radians(35)), P.RECESS_D / 2 * math.sin(math.radians(35))), f"recess Ø{fmt(P.RECESS_D)} x {fmt(P.RECESS_DEPTH)}"),
           ((P.APERTURE_D / 2 * math.cos(math.radians(10)), P.APERTURE_D / 2 * math.sin(math.radians(10))), f"aperture Ø{fmt(P.APERTURE_D)}"),
           ((P.VENT_XY[0], P.VENT_XY[1]), f"vent hole Ø{fmt(P.VENT_HOLE_D)}"),
           ((0.5, 16.2), f"groove {fmt(M['nose_w'])} x {fmt(M['nose_depth'])} deep")]
    v.label_column(lab, 137, side="right", fs=6.0, min_gap=5.0, y_min=196, y_max=252)
    # section A-A of the tub alone
    sa = 5.0
    a_ = sh.view((292, 238), sa, "SECTION A-A  (x = 0)   5:1", (178, 280))
    ga = G.section_polys(A.solid_of(tub), "x", 0.0)
    a_.fill(ga, fc=style("tub")[0], hatch=style("tub")[1], lw=0.6)
    a_.dim_v(P.RIM_Z, T, -R, -R, 0, at=a_.X(-R) - 5)
    a_.levels([(P.RIM_Z, "rim"), (P.LEDGE_Z0, ""), (P.LEDGE_Z1, ""), (P.BOND_Z, "thick roof"), (P.RECESS_FLOOR_Z, ""), (P.ROOF_Z - M["nose_depth"], "nose pad"), (T, "")],
              yv, side="right", x_text=a_.X(yv) + 7, fs=6.0)
    a_.dim_h(-P.APERTURE_D / 2, P.APERTURE_D / 2, P.BOND_Z, P.BOND_Z, 0, at=a_.Y(0) - 5, prefix="Ø", suffix=" aperture")
    a_.dim_h(-P.RECESS_D / 2, P.RECESS_D / 2, P.BOND_Z, P.BOND_Z, 0, at=a_.Y(0) - 11, prefix="Ø", suffix=" recess")
    a_.dim_h(-P.THICK_RING_R, P.THICK_RING_R, P.BOND_Z, P.BOND_Z, 0, at=a_.Y(0) - 17, prefix="Ø", suffix=" thick ring")
    a_.dim_h(-R, yv, P.RIM_Z, P.LEDGE_Z0, 0, at=a_.Y(0) - 23)
    # section B-B of the tub alone
    b_ = sh.view((292, 168), sa, f"SECTION B-B  (x = {fmt(cxr)}, through the camera R hood)   5:1", (178, 209))
    gb = G.section_polys(A.solid_of(tub), "x", cxr)
    b_.fill(gb, fc=style("tub")[0], hatch=style("tub")[1], lw=0.6)
    yb0 = -math.sqrt(R ** 2 - cxr ** 2)
    b_.levels([(M["hood_skirt_z0"], "skirt / pad"), (P.WIN_Z0, "recess"), (P.OPEN_Z0, "sill"), (P.HOOD_Z_OVER_CUBE, "hood"), (P.ROOF_Z, ""), (T, "")],
              yv, side="right", x_text=b_.X(yv) + 7, fs=6.0)
    b_.dim_h(P.HOOD_REAR_Y0, P.HOOD_REAR_Y1, P.HOOD_Z_OVER_CUBE, P.HOOD_Z_OVER_CUBE, 0, at=b_.Y(0) - 5, text_side="left", suffix=" rear wall", fs=6.0)
    b_.dim_h(P.HOOD_REAR_Y1, P.WIN_RECESS_FLOOR_Y, P.HOOD_Z_OVER_CUBE, P.OPEN_Z0, 0, at=b_.Y(0) - 11, text_side="left", suffix=" bay, rear wall to recess floor", fs=6.0)
    b_.dim_h(P.HOOD_PAD_Y, yv, M["hood_skirt_z0"], P.LEDGE_Z0, 0, at=b_.Y(0) - 17, text_side="left", suffix=" wall + pad below the recess", fs=6.0)
    b_.dim_h(P.HOOD_PAD_Y, P.WIN_RECESS_FLOOR_Y, P.OPEN_Z0, P.OPEN_Z0, 0, at=b_.Y(T) + 4, text_side="right", suffix=" sill (D04)", fs=6.0)
    b_.dim_v(P.RIM_Z, T, yb0, yb0, 0, at=b_.X(yb0) - 5)
    # detail G: plan section through the opening at the optical axis height
    sg = 12.0
    x0, x1, y0, y1 = cxr - 3.3, cxr + 3.3, 13.3, 18.65
    gdt = sh.view((22 - x0 * sg, 58 - y0 * sg), sg, f"DETAIL G - camera R opening, section at z = {fmt(P.AXIS_Z)} (seen from above)   12:1", (16, 141))
    clip = (x0, y0, x1, y1)
    gg = G.section_polys(A.solid_of(tub), "z", P.AXIS_Z).intersection(sbox(*clip))
    gdt.fill(gg, fc=style("tub")[0], hatch=style("tub")[1], lw=0.6)
    gdt.frame(*clip)
    gdt.centerline((cxr, y0), (cxr, y1 + 0.2), ext=0)
    yt = gdt.Y(y1)
    gdt.dim_h(cxr - P.OPEN_HALF_W, cxr + P.OPEN_HALF_W, P.WIN_RECESS_FLOOR_Y, P.WIN_RECESS_FLOOR_Y, 0, at=yt + 4, suffix=" clear opening")
    gdt.dim_h(cxr - P.WIN_RECESS_W / 2, cxr + P.WIN_RECESS_W / 2, yv, yv, 0, at=yt + 9.5, suffix=" window recess")
    gdt.dim_h(cxr - P.HOOD_IN_HW, cxr + P.HOOD_IN_HW, 14.9, 14.9, 0, at=gdt.Y(15.3), suffix=" bay = opening")
    gdt.dim_h(cxr - P.HOOD_OUT_HW, cxr + P.HOOD_OUT_HW, P.HOOD_REAR_Y0, P.HOOD_REAR_Y0, 0, at=gdt.Y(y0) - 4, suffix=" hood outside")
    xr = gdt.X(x1)
    gdt.dim_v(P.WIN_RECESS_FLOOR_Y, yv, x1, x1, 0, at=xr + 4, text_side="right", suffix=" recess depth", fs=6.0)
    gdt.dim_v(P.HOOD_REAR_Y1, P.WIN_RECESS_FLOOR_Y, x1, x1, 0, at=xr + 4, text_side="right", suffix=" bay and opening", fs=6.0)
    gdt.dim_v(P.HOOD_REAR_Y0, P.HOOD_REAR_Y1, x1, x1, 0, at=xr + 4, text_side="right", suffix=" rear wall", fs=6.0)
    gdt.leader((cxr + P.OPEN_HALF_W, P.WIN_RECESS_FLOOR_Y - 0.4), f"straight opening, flush with the bay wall;\nbelow the sill (z < {fmt(P.OPEN_Z0)}) the wall behind\nthe recess is {fmt(P.THIN_STRIP_T, 3)} thick (D04)", 30, -9, color=C_DIM, fs=6.0)
    # view F of the tub alone
    f = sh.view((292, 96), 4.0, "VIEW F - on the visor face   4:1   (+x to the LEFT)", (200, 132))
    f.hlr([tub], "front")
    f.centerline((-R - 1.5, P.AXIS_Z), (R + 1.5, P.AXIS_Z))
    f.dim_v(P.WIN_Z0, P.WIN_Z1, -cxr + P.WIN_RECESS_W / 2, -cxr + P.WIN_RECESS_W / 2, 5, suffix=" recess", text_side="right")
    f.dim_v(P.OPEN_Z0, P.OPEN_Z1, cxr - P.OPEN_HALF_W, cxr - P.OPEN_HALF_W, -5, suffix=" opening", text_side="left")
    f.dim_v(P.RIM_Z, P.LEDGE_Z0, -R, -P.HORN_X_OUT, 0, at=f.X(-R) - 5, text_side="below")
    f.dim_h(-P.HORN_X_OUT, P.HORN_X_OUT, T, T, 4, suffix=" visor flat")
    f.leader((-3.0, P.LEDGE_Z0), f"visor-wall underside z {fmt(P.LEDGE_Z0)}, {fmt(P.LEDGE_Z0 - P.RIM_Z)} above the rim: plain seal face (no key lug)", -30, -16, ha="right", color=C_DIM, fs=6.0)
    f.leader((-cxr + 1.2, P.WIN_Z0 + 0.25), f"window recess (x2): glass {fmt(P.WIN_W)} x {fmt(P.WIN_H)} x {fmt(P.WIN_T)} sits on this shelf (z {fmt(P.WIN_Z0)})\nand on the recess floor (seats {fmt(P.WIN_LANDS[0], 2)} / {fmt(P.WIN_LANDS[1], 2)} / {fmt(P.WIN_LANDS[2], 2)}); sealed by an adhesive frame round its edge",
             6, -32, ha="left", color=C_DIM, fs=5.8)
    sh.note(112, 60, ["Sections are true boolean sections of the", "tub solid; hatched = PA12.",
                      f"z values = height above the base plane (rim at z {fmt(P.RIM_Z)})."], fs=5.8)
    sheets.append(sh)
    return _save("GL1-010_tub", sheets)


# ==============================================================================================
# GL1-011 base plate, routed FR-4 (fabrication drawing); GL1-012 printed PA12 alternative; GL1-013 baffle ring
# ==============================================================================================
def _ball_foot_detail(sh, parts, origin_xy, title, title_xy, label_y=(192, 246), sd=20.0):
    """Section through ball foot 1 as assembled (ball, two-stage potting, adhesive-sheet hole, PCB) with the gauge plate
    dashed.  Uses the ACTIVE base variant; `parts` must hold that variant under the plain names."""
    (b1x, b1y) = P.BALL_XY[0]
    y0, y1 = b1y - 1.75, b1y + 1.75
    z0, z1 = -0.45, 1.95
    d = sh.view((origin_xy[0] - y0 * sd, origin_xy[1] - z0 * sd), sd, title, title_xy)
    clip = (y0, z0, y1, z1)
    draw_section(d, parts, ["base_plate", "pcb_adhesive", "main_pcb", "ball_epoxy_1", "ball_1"], "x", 0.0, clip=clip, lw=0.55)
    d.frame(*clip)
    d.centerline((b1y, z0), (b1y, z1), ext=0)
    pk = math.sqrt((P.BALL_D / 2) ** 2 - (P.BALL_D / 2 - P.BALL_PROT) ** 2)   # the ball sits on the rim of a hole of this radius
    gp = np.array([(y0, 0.0), (b1y - pk, 0.0), (b1y - pk, -0.3), (b1y + pk, -0.3), (b1y + pk, 0.0), (y1, 0.0)])
    d.lines([gp], lw=0.5, color="#b06000", ls=(0, (5, 2.5)), zorder=16)
    d.levels([(-P.BALL_PROT, "ball lowest point"), (0.0, "base plane"), (P.BASE_T, "plate top"), (P.BALL_TOP_Z, "ball top"),
              (P.PCB_Z0, "PCB underside"), (P.PCB_Z1, "PCB top")], y0, side="left", x_text=d.X(y0) - 7, fs=6.0, min_gap=3.6)
    d.dim_h(b1y - P.BALL_HOLE_D / 2, b1y + P.BALL_HOLE_D / 2, 0, 0, 0, at=d.Y(z0) - 4, prefix="Ø", suffix=" through hole", text_side="left", nd=2)
    d.dim_h(b1y - P.PSA_FOOT_HOLE_D / 2, b1y + P.PSA_FOOT_HOLE_D / 2, P.PSA_Z1, P.PSA_Z1, 0, at=d.Y(z1) + 3.5, prefix="Ø", suffix=" hole in the adhesive sheet")
    s1, s2 = P.epoxy_volumes()
    labs = [((b1y + 0.2, P.BALL_Z - 0.1), f"ball Ø{fmt(P.BALL_D)} stainless,\n{fmt(P.BALL_PROT)} below the base plane"),
            ((b1y + 0.5 * (P.BALL_D + P.BALL_HOLE_D) / 2, 0.45), f"stage 1 epoxy ({s1:.2f} mm3): fills the\nhole, flush with the base plane"),
            ((b1y + 0.8, P.BASE_T + 0.5 * P.PSA_T), f"stage 2 epoxy ({s2:.2f} mm3) in the sheet\nhole: ball bears on its Ø{fmt(P.FOOT_LAND_D)} land"),
            ((b1y + 1.4, 0.5 * (P.PSA_Z0 + P.PSA_Z1)), f"adhesive sheet {fmt(P.PSA_T)}"),
            ((b1y + 1.5, 0.3), f"base plate {fmt(P.BASE_T)}"),
            ((b1y + 1.5, 1.4), "main PCB"),
            ((b1y + 1.1, -0.0), f"dashed: gauge plate (fixture),\nreamed Ø{fmt(2 * pk, 2)} hole, ball on its rim")]
    d.label_column(labs, d.X(y1) + 6, side="right", fs=5.7, min_gap=6.4, y_min=label_y[0], y_max=label_y[1])
    return pk


def _plate_profile(parts):
    """(polygon, [(name, ring polygon)]) of the base plate of `parts` at mid thickness, from the solid."""
    from shapely.geometry import Polygon as SPoly
    g = G.section_polys(A.solid_of(parts["base_plate"]), "z", 0.5 * P.BASE_T, 2e-4)
    pg = max(getattr(g, "geoms", [g]), key=lambda q: q.area)
    return pg, [SPoly(r) for r in pg.interiors]


def gl1_011(parts):
    """FABRICATION drawing of the routed FR-4 base plate for a PCB fabricator's quote."""
    base = parts["base_plate"]
    v = P.BASE
    tol_o, tol_h, tol_t = M["fr4_tol_outline"], M["fr4_tol_hole"], M["fr4_tol_thickness"]
    acc = v["accept"]
    d_mask = P.BALL_HOLE_D + M["fr4_mask_relief"]
    import fabdata as FD
    sh = Sheet("GL1-011", "Base plate, FR-4 - FABRICATION DRAWING", 1, 1, part="base plate (primary build)", material="FR-4 0.80 mm, matte black solder mask both sides, NO COPPER",
               process="PCB fabricator: routed outline + cut-outs, drilled NPTH", tolerance=f"routed +-{tol_o}, drilled +-{tol_h}, thickness +-{tol_t}",
               scale="4:1 / 20:1", params_rev=P.REV)
    R, F = P.BASE_R, P.BASE_FLAT
    sc = 4.0
    v_ = sh.view((104, 166), sc, "VIEW ON THE TOP FACE (PCB side), z = 0.80   4:1   datum: centre of the R 21.75 arc, +y toward the flat", (16, 268))
    v_.hlr([base], "top")
    v_.centerline((-R - 2, 0), (R + 2, 0)); v_.centerline((0, -R - 2), (0, F + 2))
    gx, gy = P.GRAIN_X, P.GRAIN_Y
    v_.cross((gx, gy), 4.0)
    xa, xb = P.PAD_XS[0], P.PAD_XS[-1]
    rs = P.PAD_HOLE_D / 2
    pg, holes = _plate_profile(parts)
    v_.dim_h(-R, R, 0, 0, 0, at=v_.Y(-R) - 6, prefix="Ø", suffix=f" +-{tol_o}  (R {fmt(R)})")
    v_.dim_v(-R, F, 0, 0, 0, at=v_.X(-R) - 5)
    v_.dim_v(0, F, R, math.sqrt(R ** 2 - F ** 2), 0, at=v_.X(R) + 5, suffix=" flat")
    v_.dim_h(xa - rs, xb + rs, P.PAD_Y - rs, P.PAD_Y - rs, -4.5, suffix=" slot")
    v_.dim_v(P.PAD_Y - rs, P.PAD_Y + rs, xb + rs, xb + rs, 5, text_side="right", suffix=" slot")
    v_.dim_v(P.PAD_Y, 0, xa - rs, -14.0, 0, at=v_.X(-14.0))
    v_.dim_v(gy, 0, gx - P.GRAIN_R, -9.0, 0, at=v_.X(-9.0), text_side="left")
    (b1x, b1y), (b2x, b2y), (b3x, b3y) = P.BALL_XY
    for i, (bx_, by_) in enumerate(P.BALL_XY):
        v_.cross((bx_, by_), 2.2)
        v_.ax.text(v_.X(bx_) + 2.6, v_.Y(by_) + 2.2, f"T1.{i + 1}", fontsize=5.6, color="#b02020", fontweight="bold", zorder=30)
    v_.dim_h(b2x, b3x, b2y, b3y, 0, at=v_.Y(b2y - 2.6), suffix=" holes T1.2 - T1.3")
    v_.dim_v(b3y, 0, b3x, b3x, 0, at=v_.X(b3x + 2.2))
    v_.dim_v(0, b1y, 3.0, b1x, 0, at=v_.X(3.0))
    cxb = P.BASE_CORNER_X
    v_.dim_h(-cxb, cxb, F, F, 10.0, suffix=" flat", nd=2)
    # webs measured on the solid
    web_slot = holes and min(h.distance(pg.exterior) for h in holes if abs(h.centroid.y - P.PAD_Y) < 0.5)
    web_ball = min(h.distance(pg.exterior) for h in holes if h.area < 2.0)
    lab = [((gx + P.GRAIN_R * math.cos(math.radians(40)), gy + P.GRAIN_R * math.sin(math.radians(40))), f"ROUTED round opening Ø{fmt(P.GRAIN_D)} +-{tol_o},\ncentre x {co(gx)}, y {co(gy)}; plain hole, edge deburred"),
           ((b3x + P.BALL_HOLE_D / 2 * 0.7, b3y + P.BALL_HOLE_D / 2 * 0.7), f"T1: 3 x Ø{fmt(P.BALL_HOLE_D, 2)} +-{tol_h} DRILLED, non-plated,\nat (0, {co(b1y)}), (+-{fmt(b3x)}, {co(b3y)}), position +-{tol_h}"),
           ((xb + rs * 0.7, P.PAD_Y - rs * 0.7), f"ROUTED slot {fmt(P.PAD_SLOT_L)} x {fmt(P.PAD_HOLE_D)} +-{tol_o}, full-radius ends R{fmt(rs)},\ncentre line y = {co(P.PAD_Y)}, centres of the ends x = +-{fmt(xb)}"),
           ((R * math.cos(math.radians(22)), R * math.sin(math.radians(22))), f"ROUTED outline R{fmt(R)} +-{tol_o}: this edge and a {fmt(P.BASE_R - P.LAND_RI)} rim\nof the top face are bonding faces (seal land)"),
           ((cxb, F), f"external corner (x2) at x = +-{fmt(cxb, 2)}: sharp,\nbreak edge 0.1 max"),
           ((0.5 * (xb + rs + R * 0.9), P.PAD_Y - 0.9), f"smallest web: slot to edge {fmt(web_slot, 2)};\nhole T1 to edge {fmt(web_ball, 2)}"),
           ((6.0, F - 0.3), f"top face: {fmt(P.BASE_FLAT - P.LAND_FLAT_IN)} strip along the flat is a\nbonding face too (no notch, no tab here)")]
    v_.label_column(lab, 198, side="right", fs=5.9, min_gap=8.4, y_min=96, y_max=246)
    _triad(sh, 20, 92, (1, 0), (0, 1))
    # edge view: thickness and build-up
    e = sh.view((300, 240), 20.0, "EDGE VIEW (section y = 0 at the +x edge)   20:1", (262, 272))
    xe0, xe1 = R - 3.2, R + 0.6
    ge = G.section_polys(A.solid_of(base), "y", 0.0).intersection(sbox(xe0, -0.4, xe1, 1.2))
    e2 = sh.view((300 - xe0 * 20.0, 238), 20.0)
    e2.fill(ge, fc="#9fb89a", hatch="xxxx", lw=0.6)
    e2.dim_v(0, P.BASE_T, R, R, 6, text_side="right", text=f"{P.BASE_T:.2f}", suffix=f" +-{tol_t} over the mask")
    e2.leader((R - 2.4, P.BASE_T), "top face (PCB side): matte black mask", 4, 6, ha="left", color=C_DIM, fs=5.8)
    e2.leader((R - 2.4, 0.0), "underside (rests on the turf): matte black mask", 4, -7, ha="left", color=C_DIM, fs=5.8)
    e2.leader((R, 0.3), f"routed edge, deburred", 6, -16, ha="left", color=C_DIM, fs=5.8)
    rows = [["Tool / feature", "Qty", "Size", "Tolerance", "Position (x, y)", "Plating"],
            ["T1 drill", "3", f"Ø{fmt(P.BALL_HOLE_D, 2)}", f"+-{tol_h} dia, +-{tol_h} pos.", f"(0, {co(b1y)}), (+-{fmt(b3x)}, {co(b3y)})", "none (NPTH)"],
            ["Rout: round opening", "1", f"Ø{fmt(P.GRAIN_D)}", f"+-{tol_o}", f"({co(gx)}, {co(gy)})", "-"],
            ["Rout: slot", "1", f"{fmt(P.PAD_SLOT_L)} x {fmt(P.PAD_HOLE_D)}, ends R{fmt(rs)}", f"+-{tol_o}", f"centre (0, {co(P.PAD_Y)})", "-"],
            ["Rout: outline", "1", f"R{fmt(R)}, flat at y = {co(F)}", f"+-{tol_o}", "arc centre (0, 0)", "-"],
            ["Mask relief at T1", "3 + 3", f"Ø{fmt(d_mask, 2)} opening, both faces", "+-0.05", "on the T1 holes", "-"],
            ["Thickness over mask", "-", f"{fmt(P.BASE_T)}", f"+-{tol_t}", "-", "no copper"]]
    sh.table(262, 214, rows, [27, 7, 37, 29, 33, 15], fs=5.3)
    rows = [["Web / edge distance (measured on the model)", "mm"]]
    names = {}
    for h in holes:
        c0 = h.centroid
        if h.area > 50:
            nm = "round opening"
        elif abs(c0.y - P.PAD_Y) < 0.5:
            nm = "slot"
        else:
            nm = "hole T1.%d" % (1 + min(range(3), key=lambda i_: math.hypot(c0.x - P.BALL_XY[i_][0], c0.y - P.BALL_XY[i_][1])))
        names[nm] = h
    for nm in sorted(names):
        rows.append([f"{nm} to the outline", fmt(names[nm].distance(pg.exterior), 2)])
    rows.append(["slot to the round opening", fmt(names["slot"].distance(names["round opening"]), 2)])
    sh.table(262, 180, rows, [62, 14], fs=5.4, row_h=3.6)
    sh.note(344, 180, [f"Smallest internal radius: R{fmt(rs)} (slot ends).", "No internal corner below R0.5; no drilled",
                       "relief needed. A router bit of Ø2.0 or", "smaller makes every feature.",
                       f"Smallest web {fmt(min(h.distance(pg.exterior) for h in holes), 2)} mm."], fs=5.5)
    pk = _ball_foot_detail(sh, parts, (292, 92), "FOR INFORMATION (not a fabrication detail): hole T1.1 in use   16:1", (262, 149), label_y=(90, 136), sd=16.0)
    sh.note(16, 68, [
        f"1. MATERIAL: FR-4 glass-epoxy laminate, NO COPPER on any layer (unclad or fully etched): a mechanical plate, not a circuit. FINISHED THICKNESS OVER THE SOLDER MASK {fmt(P.BASE_T)} +-{tol_t} mm.",
        f"   Choose the laminate for that finished thickness and state the build-up in the quote (a 0.8 mm copper-clad laminate ends near 0.75 without its copper). We use plates from {acc[0]:.2f} to {acc[1]:.2f} mm.",
        f"2. SOLDER MASK: matte black, both faces, full coverage EXCEPT a round relief Ø{fmt(d_mask, 2)} at each hole T1 on both faces: no mask on the hole wall or rim (or drill after mask). NO legend, date code or marking.",
        f"3. OUTLINE AND CUT-OUTS: routed, +-{tol_o}. No V-score. Supply individually routed pieces. If panelised: break-off tabs ONLY on the flat (y = {co(F)}), mouse bites recessed into the outline by at most",
        f"   {fmt(M['fr4_tab_recess_max'])} mm, no nub proud of the outline anywhere. NO tab on the round part: it drops into a bore with {fmt(P.CLR)} mm radial clearance and carries a {fmt(P.BASE_R - P.LAND_RI)} mm seal land.",
        f"4. HOLES T1: 3 x Ø{fmt(P.BALL_HOLE_D, 2)} +-{tol_h}, drilled, non-plated, free of mask; position +-{tol_h} to each other, +-{tol_o} to the outline. They take Ø{fmt(P.BALL_D)} steel balls (detail, for information).",
        f"5. CORNERS: slot ends full radius R{fmt(rs)}; no internal corner below R0.5. The two external corners at the ends of the flat are sharp (break edge 0.1 max).",
        "6. FLATNESS: bow and twist 0.5 % maximum (0.2 mm over the part). Edges free of burrs and loose fibres. Both faces are bonding faces: no release agent, mask fully cured, parts clean.",
        f"7. DATA (mm, same origin): drawings/fab/{FD.FILES['profile']} (Gerber: outline + routed cut-outs), {FD.FILES['mask_top'].split('-')[-1]} / {FD.FILES['mask_bottom'].split('-')[-1]} (mask layers), {FD.FILES['drill'].split('-')[-1]} (Excellon, NPTH);",
        "   drawings/dxf/GL1-011_base_plate_FR4_fab.dxf (layers OUTLINE_ROUT, ROUT_OPENING_D13p0, ROUT_SLOT_17p44x2p2, DRILL_NPTH_D1p10); export/step/base_plate.step.",
        f"8. Datum: origin = centre of the R{fmt(R)} arc; +x to the right and +y toward the flat in this view (seen on the top face). The part is symmetric about the y axis.",
        "9. To report with the first articles: thickness over the mask, hole diameters, outline. PROVISIONAL - not released. Nominal CAD dimensions (design/master_params.yaml rev D); checked by check 15 of the build.",
    ], fs=5.7, title="NOTES FOR THE FABRICATOR")
    return _save("GL1-011_base_plate_FR4", [sh])


def gl1_012(parts):
    """The printed PA12 base plate of the ALTERNATIVE build (all-printed build, EVT comparison)."""
    with P.base_variant(P.BASE_ALT):
        vp = A.variant_view(parts)
        base = vp["base_plate"]
        sh = Sheet("GL1-012", "Base plate, printed PA12 - ALTERNATIVE build", 1, 1, part="base plate (alternative build, EVT comparison)", material="PA12 (HP 3D HR PA 12), dyed black",
                   process="HP Multi Jet Fusion, dyed, NOT vapor smoothed", tolerance=TOL_PRINT, scale="4:1 / 20:1", params_rev=P.REV)
        R, F = P.BASE_R, P.BASE_FLAT
        sc = 4.0
        v = sh.view((104, 166), sc, "TOP VIEW (PCB side)   4:1", (16, 268))
        v.hlr([base], "top", hidden=True)
        v.centerline((-R - 2, 0), (R + 2, 0)); v.centerline((0, -R - 2), (0, F + 2))
        gx, gy = P.GRAIN_X, P.GRAIN_Y
        v.cross((gx, gy), 4.0)
        xa, xb = P.PAD_XS[0], P.PAD_XS[-1]
        rs = P.PAD_HOLE_D / 2
        v.dim_h(-R, R, 0, 0, 0, at=v.Y(-R) - 6, prefix="Ø")
        v.dim_v(-R, F, 0, 0, 0, at=v.X(-R) - 5)
        v.dim_v(0, F, R, math.sqrt(R ** 2 - F ** 2), 0, at=v.X(R) + 5)
        v.dim_h(xa - rs, xb + rs, P.PAD_Y - rs, P.PAD_Y - rs, -4.5, suffix=" slot")
        v.dim_v(P.PAD_Y - rs, P.PAD_Y + rs, xb + rs, xb + rs, 5, text_side="right", suffix=" slot")
        v.dim_v(P.PAD_Y, 0, xa - rs, -14.0, 0, at=v.X(-14.0))
        (b1x, b1y), (b2x, b2y), (b3x, b3y) = P.BALL_XY
        for bx_, by_ in P.BALL_XY:
            v.cross((bx_, by_), 2.2)
        v.dim_h(b2x, b3x, b2y, b3y, 0, at=v.Y(b2y - 2.6), suffix=" ball-foot holes 2 - 3")
        v.dim_v(b3y, 0, b3x, b3x, 0, at=v.X(b3x + 2.2))
        v.dim_v(0, b1y, 3.0, b1x, 0, at=v.X(3.0))
        cxb = P.BASE_CORNER_X
        v.dim_h(-cxb, cxb, F, F, 10.0, suffix=" flat (plain edge)", nd=2)
        lab = [((gx + P.GRAIN_R * math.cos(math.radians(40)), gy + P.GRAIN_R * math.sin(math.radians(40))), f"grain opening Ø{fmt(P.GRAIN_D)},\ncentre x {co(gx)}, y {co(gy)}"),
               ((gx + P.BAFFLE_RO * math.cos(math.radians(15)), gy + P.BAFFLE_RO * math.sin(math.radians(15))), f"integral baffle ring Ø{fmt(2 * P.BAFFLE_RI, 2)} / Ø{fmt(2 * P.BAFFLE_RO, 2)}\n(wall {fmt(P.BAFFLE_WALL)}, full thickness)"),
               ((gx + 5.2 * math.cos(math.radians(-45)), gy + 5.2 * math.sin(math.radians(-45))), f"three spokes {fmt(P.SPOKE_W)} wide at\n" + ", ".join(f"{a:.0f}°" for a in P.SPOKE_ANGLES) + " (clear of the LEDs)"),
               ((b3x + P.BALL_HOLE_D / 2 * 0.7, b3y + P.BALL_HOLE_D / 2 * 0.7), f"through hole Ø{fmt(P.BALL_HOLE_D)} for a Ø{fmt(P.BALL_D)} ball foot (x3),\ndetail H; at (0, {co(b1y)}), (+-{fmt(b3x)}, {co(b3y)})"),
               ((xb + rs * 0.7, P.PAD_Y - rs * 0.7), f"pad slot {fmt(P.PAD_SLOT_L)} x {fmt(P.PAD_HOLE_D)}, ends R{fmt(rs)}, centre line\ny = {co(P.PAD_Y)} (7 pads, pitch 2.54)"),
               ((R * math.cos(math.radians(22)), R * math.sin(math.radians(22))), f"edge R{fmt(R)}: {fmt(P.CLR)} radial gap\nto the tub wall (adhesive-filled)"),
               ((6.0, F - 0.3), f"seal land: {fmt(P.BASE_FLAT - P.LAND_FLAT_IN)} strip under the visor wall,\n{fmt(P.BASE_R - P.LAND_RI)} ring on the arc (no notch)")]
        v.label_column(lab, 198, side="right", fs=5.9, min_gap=7.6, y_min=92, y_max=246)
        v.cut_line((0, 12.6), (0, F + 1.2), "H", ext=0.5, arrow_dir=(-1, 0), fs=7.5)
        _triad(sh, 20, 92, (1, 0), (0, 1))
        pk = _ball_foot_detail(sh, vp, (290, 204), "DETAIL H - ball foot 1 as assembled (x = 0), PA12 build   20:1", (262, 272))
        rows = [["Feature", "Qty", "Size", "Position (x, y)"],
                ["Outline", "1", f"R{fmt(R)}, flat y {co(F)}", "centre (0, 0)"],
                ["Grain opening", "1", f"Ø{fmt(P.GRAIN_D)} through", f"({co(gx)}, {co(gy)})"],
                ["Baffle ring (integral)", "1", f"Ø{fmt(2 * P.BAFFLE_RI, 2)} / Ø{fmt(2 * P.BAFFLE_RO, 2)}", "concentric with the opening"],
                ["Spokes", "3", f"{fmt(P.SPOKE_W)} wide", ", ".join(f"{a:.0f}°" for a in P.SPOKE_ANGLES) + " from +x"],
                ["Pad slot", "1", f"{fmt(P.PAD_SLOT_L)} x {fmt(2 * rs)}", f"centre (0, {co(P.PAD_Y)})"],
                ["Ball-foot holes", "3", f"Ø{fmt(P.BALL_HOLE_D)} through", f"(0, {co(b1y)}), (+-{fmt(b3x)}, {co(b3y)})"],
                ["Thickness", "-", f"{fmt(P.BASE_T)}", f"z 0 to {fmt(P.BASE_T)}"]]
        sh.table(262, 152, rows, [28, 9, 46, 58], fs=5.7)
        sh.note(262, 114, [
            f"1. ALTERNATIVE to GL1-011 (routed FR-4, the primary plate): for an all-printed build and for the EVT comparison of thermal and humidity",
            f"   tilt drift. Plate {fmt(P.BASE_T)} mm with a {fmt(P.PSA_T)} mm adhesive sheet: the PCB underside stays at z = {fmt(P.PCB_Z0)}; seal joint {fmt(P.BEAD_T)} mm.",
            f"2. Ball feet: the print cannot hold a {fmt(P.BALL_PROT)} mm protrusion. Clamp the plate flat on a gauge plate with three reamed",
            f"   Ø{fmt(2 * pk, 2)} holes, drop the balls in (each seats on the rim of its hole, {fmt(P.BALL_PROT)} proud), pot them from this",
            "   side, cure. At lamination the sheet holes are filled with epoxy as well (README assembly sequence).",
            f"3. The baffle ring is part of the plate here (the FR-4 build uses the separate ring GL1-013). The grain opening is potted clear",
            f"   after lamination, in four compartments: surface z {P.potting_window()[0]:.2f} to {P.potting_window()[1]:.2f} (target {P.potting_window()[2]:.3f}), never nearer the base plane than z {fmt(P.GRAIN_FILL_Z)}.",
            f"4. The top face is the bonding face for the adhesive sheet and the seal land (r {fmt(P.LAND_RI)} to {fmt(R)}). Plain edge: no notch.",
            "5. No wall below 0.8 mm, no trapped powder (check 16). Dyed, NOT vapor smoothed (hidden part, three bonding faces).",
            f"6. As printed the bureau's tolerance applies (title block). WE sort and finish the plates: thickness {P.BASE['accept'][0]:.2f} to {P.BASE['accept'][1]:.2f} used",
            f"   (below {P.BASE['accept'][0]:.2f} the ball would touch its land through the {fmt(P.PSA_T)} sheet); order about twice the quantity needed. Flatness",
            f"   0.3 mm free state is OUR target after flattening (between plates under a weight, warm; time and temperature to be found on",
            f"   first articles), not a bureau requirement. We ream the three foot holes to Ø{fmt(P.BALL_HOLE_D)}.",
        ], fs=5.9, title="NOTES")
        return _save("GL1-012_base_plate_PA12_alternative", [sh])


def gl1_013(parts):
    """Small drawing of the separate grain baffle ring (FR-4 build) with its adhesive annulus and how it sits in the opening."""
    ring = parts["baffle_ring"]
    gx, gy = P.GRAIN_X, P.GRAIN_Y
    ri, ro = P.BAFFLE_RI, P.BAFFLE_RO
    sh = Sheet("GL1-013", "Grain baffle ring (FR-4 build)", 1, 1, part="grain baffle ring + adhesive annulus", material="PA12 (HP 3D HR PA 12), dyed black, not smoothed",
               process="MJF, sprued set; height lapped by us; annulus: black tape", tolerance=TOL_PRINT,
               scale="12:1 / 40:1 / 11:1 / 2:1", params_rev=P.REV)
    plus, minus = M["baffle_ring_tol"]
    crr = P.baffle_crest_range()
    pw = P.potting_window()
    sc = 12.0
    v = sh.view((78 - gx * sc, 196 - gy * sc), sc, "RING, seen on the face that bonds to the PCB   12:1", (16, 268))
    v.hlr([ring], "top", chord_tol=0.0005)
    v.cross((gx, gy), 5.0)
    v.dim_h(gx - ro, gx + ro, gy, gy, 0, at=v.Y(gy - ro) - 7, prefix="Ø", suffix=" outside")
    v.dim_h(gx - ri, gx + ri, gy, gy, 0, at=v.Y(gy + ro) + 6, prefix="Ø", suffix=" inside")
    v.dim_h(gx + ri, gx + ro, gy, gy, 0, at=v.Y(gy), text_side="right", suffix=" wall")
    v.cut_line((gx - ro - 0.6, gy), (gx + ro + 0.6, gy), "K", ext=1.0, arrow_dir=(0, 1), fs=8)
    # section K-K of the ring alone
    s2 = 40.0
    xk0 = gx + ri - 0.5
    k = sh.view((170 - xk0 * s2, 214), s2, "SECTION K-K (ring wall)   40:1", (150, 268))
    gk = G.section_polys(A.solid_of(ring), "y", gy).intersection(sbox(xk0, -0.2, gx + ro + 0.5, 1.2))
    k.fill(gk, fc=style("baffle_ring")[0], lw=0.6)
    k.dim_v(P.BAFFLE_RING_Z0, P.BAFFLE_RING_Z1, gx + ro, gx + ro, 7, text_side="right", suffix=f" +{plus:.2f} / -{minus:.2f} lapped")
    k.dim_h(gx + ri, gx + ro, P.BAFFLE_RING_Z1, P.BAFFLE_RING_Z1, 6, text_side="right")
    k.leader((gx + ri + 0.15, P.BAFFLE_RING_Z1), "bonding face (to the adhesive annulus)", -16, 16, ha="left", color=C_DIM, fs=5.8)
    k.leader((gx + 0.5 * (ri + ro), P.BAFFLE_RING_Z0), "crest (free face, lapped): never covered by the potting", -6, -9, ha="left", color=C_DIM, fs=5.8)
    # as assembled: section y = gy through the grain opening
    sa = 11.0
    x0, x1, z0, z1 = gx - 7.6, gx + 7.6, -0.35, 2.0
    a_ = sh.view((178 - x0 * sa, 134 - z0 * sa), sa, f"AS ASSEMBLED - section y = {co(gy)} through the grain opening   11:1", (150, 178))
    names = ["base_plate", "pcb_adhesive", "main_pcb", "baffle_ring", "baffle_adhesive", "grain_potting"]
    draw_section(a_, parts, names, "y", gy, clip=(x0, z0, x1, z1), lw=0.5)
    a_.frame(x0, z0, x1, z1)
    a_.levels([(0.0, "base plane"), (P.GRAIN_FILL_Z, "ring crest = potting limit"), (P.BASE_T, "plate top"), (P.BAFFLE_RING_Z1, "ring top"), (P.PCB_Z0, "PCB underside"), (P.PCB_Z1, "PCB top")],
              x0, side="left", x_text=a_.X(x0) - 5, fs=5.6, min_gap=3.3)
    a_.dim_h(gx - P.GRAIN_R, gx + P.GRAIN_R, 0, 0, 0, at=a_.Y(z0) - 4, prefix="Ø", suffix=" grain opening in the base plate")
    a_.dim_h(gx - ro, gx + ro, P.GRAIN_FILL_Z, P.GRAIN_FILL_Z, 0, at=a_.Y(z0) - 10, prefix="Ø", suffix=" ring")
    pdx = P.PD["dx"] / 2
    labs = [((gx, P.PCB_Z0 - 0.25), f"photodiode {fmt(P.PD['dx'])} x {fmt(P.PD['dy'])} x {fmt(P.PD['h'])}"),
            ((gx + 0.5 * (ri + ro), 0.45), f"baffle ring Ø{fmt(2 * ro)} / Ø{fmt(2 * ri)} x {fmt(P.BAFFLE_RING_H, 2)}"),
            ((gx + 0.5 * (ri + ro), 0.5 * (P.BAFFLE_RING_Z1 + P.PCB_Z0)), f"adhesive annulus {fmt(P.BAFFLE_PSA_T)}"),
            ((gx + 0.5 * (ro + P.GRAIN_R), 0.3), f"clear potting, shown at its limit z {fmt(P.GRAIN_FILL_Z)}"),
            ((gx + P.GRAIN_R + 0.6, 0.4), f"base plate {fmt(P.BASE_T)} (FR-4)"),
            ((gx + P.GRAIN_R + 0.6, 0.5 * (P.PSA_Z0 + P.PSA_Z1)), f"adhesive sheet {fmt(P.PSA_T)}"),
            ((gx + 4.0, 1.4), "main PCB")]
    a_.label_column(labs, a_.X(x1) + 8, side="right", fs=5.7, min_gap=4.4, y_min=128, y_max=172)
    rows = [["Clearance (model, check 2)", "mm"],
            ["photodiode corner to the ring bore", fmt(ri - P.PD_HALF_DIAG, 3)],
            ["ring outside to the LED bodies (0402 on r %s)" % fmt(P.LED_RING["radius"]), fmt(P.LED_R_IN - ro, 3)],
            ["LED outer corner to the opening wall", fmt(P.GRAIN_R - P.LED_R_OUT, 3)],
            ["ring outside to the opening wall", fmt(P.GRAIN_R - ro, 3)],
            ["potting over the photodiode / over an LED", f"{fmt(P.GRAIN_FILL_DEPTH - P.PD['h'], 2)} / {fmt(P.GRAIN_FILL_DEPTH - P.LED_RING['led_height'], 2)}"],
            ["ring crest above the base plane, as assembled (z)", f"{fmt(P.BAFFLE_RING_Z0, 2)}; range {crr['matched'][0]:.2f} to {crr['matched'][1]:.2f}; accepted 0 to {fmt(P.BAFFLE_CREST_MAX_Z, 2)}"],
            ["potting surface (z), for the nominal crest", f"{pw[0]:.2f} to {pw[1]:.2f}, fill target {pw[2]:.2f}"]]
    sh.table(262, 266, rows, [66, 60], fs=5.6)
    rows = [["Item", "Qty", "Size", "Material"],
            ["Baffle ring", "1", f"Ø{fmt(2 * ro)} / Ø{fmt(2 * ri)} x {fmt(P.BAFFLE_RING_H, 2)} lapped", f"MJF PA12, dyed black; printed {fmt(P.BAFFLE_RING_PRINT_H, 2)} high"],
            ["Adhesive annulus", "1", f"Ø{fmt(2 * ro)} / Ø{fmt(2 * ri)} x {fmt(P.BAFFLE_PSA_T)}", "OPAQUE BLACK double-coated tape (dxf GL1-034)"]]
    sh.table(262, 226, rows, [26, 8, 40, 60], fs=5.6)
    # the print file: a sprued set
    sp = M["ring_sprue"]
    pv_ = sh.view((208, 70), 2.0, f"PRINT FILE (baffle_ring_print): sprued set of {sp['n']} rings, each {fmt(P.BAFFLE_RING_PRINT_H, 2)} high   2:1", (160, 112))
    spr = PT.baffle_ring_sprue()
    pv_.hlr([spr], "top", chord_tol=0.002)
    sb = spr.val().BoundingBox()
    pv_.dim_h(sb.xmin, sb.xmax, sb.ymin, sb.ymin, -5)
    pv_.dim_v(sb.ymin, sb.ymax, sb.xmax, sb.xmax, 5, text_side="right")
    pv_.leader((0.0, 0.0), f"runner {fmt(sp['runner'])} x {fmt(sp['runner'])}", -22, 28, ha="right", color=C_DIM, fs=5.6)
    pv_.leader((sp["runner"] / 2 + 0.5 * sp["gate_len"], (((sp["n"] + 1) // 2) - 1) / 2 * sp["pitch"]), f"gate {fmt(sp['gate_w'])} wide x {fmt(P.MIN_WALL)} high on the\noutside of each ring: trim flush", 34, 6, ha="left", color=C_DIM, fs=5.6)
    sh.note(16, 112, [
        "1. Light baffle between the grain LEDs and the photodiode of the FR-4 build. (The printed PA12 base",
        "   plate GL1-012 carries the same ring itself, on three spokes.)",
        f"2. PRINTED {fmt(P.BAFFLE_RING_PRINT_H, 2)} high as a sprued set (print file). WE cut the rings off, trim the gate",
        f"   flush and LAP the bonding face in a pocket gauge to the finished height {fmt(P.BAFFLE_RING_H, 2)} +{plus:.2f} / -{minus:.2f}",
        f"   for a base plate of {fmt(P.BASE_T)} mm. For a plate lot of measured thickness t (over the mask) the",
        f"   finished height is t + {P.baffle_ring_height(0.0):.2f}: the crest then ends z {crr['matched'][0]:.2f} to {crr['matched'][1]:.2f} above the base plane",
        f"   and can never stand proud of it. (Lapped to {fmt(P.BAFFLE_RING_H, 2)} regardless of the plate it could end at",
        f"   z {crr['unmatched'][0]:.2f} to {crr['unmatched'][1]:.2f}.) The crest is the as-printed face.",
        f"3. Wall {fmt(P.BAFFLE_WALL)} mm (the printing minimum). Order two sets.",
        "4. ASSEMBLY, before the base plate is laminated: PCB component-side down in the lamination jig on",
        "   its two sprung pins; annulus onto the ring; the ring tool, registered on the same two pins, places",
        f"   the ring round the photodiode ({fmt(min(ri - P.PD_HALF_DIAG, P.LED_R_IN - ro), 2)} mm to the photodiode corners and to the LEDs). After",
        f"   lamination: crest between the base plane and {fmt(P.BAFFLE_CREST_MAX_Z, 2)} mm inside it (depth gauge). Then the",
        f"   opening is potted clear: surface from the crest to {fmt(M['grain_fill_below_crest'], 2)} inside it, never nearer the base",
        f"   plane than z {fmt(P.GRAIN_FILL_Z)} (README, steps 11 and 12).",
        "5. Ring and annulus black and opaque at the LED wavelengths, low fluorescence: light-leak test",
        "   (0.8 mm dyed MJF PA12; a clear tape would be a light slot between LEDs and photodiode).",
        "6. PROVISIONAL - not released. Nothing has been built.",
    ], fs=5.7, title="NOTES")
    return _save("GL1-013_baffle_ring", [sh])


# ==============================================================================================
# GL1-020 cradle
# ==============================================================================================
def _holddown_results():
    """Hold-down numbers for the drawing: beam model from holddown.calc; travel and FE strain from the check report."""
    import json
    travel, release, mass, cog, fe = {}, None, 11.3, -1.4, {}
    f = P.EXPORT_DIR / "check_report.json"
    if f.exists():
        try:
            rep = json.loads(f.read_text())
            for r in rep["results"]:
                for t in r["tables"]:
                    if t["title"].startswith("Insertion path"):
                        travel = {float(q["tilt_deg"]): float(q["latch_travel_needed_mm"]) for q in t["rows"]}
                    if t["title"].startswith("Release"):
                        release = [float(q["hook_travel_to_free_the_marker_mm"]) for q in t["rows"]]
                    if t["title"].startswith("Latch strain"):
                        fe = {q["case"]: float(q["strain_FE_peak_pct"]) for q in t["rows"]}
                    if t["title"] == "Totals":
                        mass, cog = float(t["rows"][0]["mass_g"]), float(t["rows"][0]["cog_y"])
        except Exception:
            pass
    c = H.calc(mass, cog, d_insert=max(travel.values()) if travel else None, d_release=release)
    return c, travel, fe


def _xf_poly(poly, th, s_, h_):
    return np.array([H.xf(y, z, th, s_, h_) for y, z in np.asarray(poly.exterior.coords)])


def gl1_020(parts):
    cr = parts["cradle"]
    X, y0c, y1c = P.CRADLE_X, P.CRADLE_Y0, P.CRADLE_Y1
    zb, zt = P.CRADLE_BOT_Z, P.CRADLE_TOP_Z
    c, travel, fe = _holddown_results()
    lw, hw = M["lip_half_w"], M["latch_w"] / 2
    zr = M["latch_root_z"]
    mat = "PA12 (HP 3D HR PA 12), any colour, not smoothed, not tumbled"
    sheets = []
    sh = Sheet("GL1-020", "Cradle (charging / data dock with hold-down)", 1, 2, part="cradle body", material=mat,
               process="HP Multi Jet Fusion, orientation LOCKED (note 5); drill 4 x Ø1.6", tolerance=TOL_PRINT, scale="2:1 / 2.8:1 / 1.5:1", params_rev=P.REV)
    # ---------------- top view
    v = sh.view((84, 198), 2.0, "TOP VIEW   2:1", (16, 272))
    v.hlr([cr], "top")
    v.centerline((-X - 2, 0), (X + 2, 0)); v.centerline((0, y0c - 2), (0, y1c + 2))
    v.dim_h(-X, X, y0c, y0c, -7)
    v.dim_v(y0c, 0, -X, -X, 0, at=v.X(-X) - 6); v.dim_v(0, y1c, -X, -X, 0, at=v.X(-X) - 6)
    v.dim_v(y0c, y1c, -X, -X, 0, at=v.X(-X) - 12)
    v.dim_h(-lw, lw, y1c, y1c, 5, suffix=" lip")
    v.dim_h(-hw, hw, y0c, y0c, -13, suffix=" latch")
    v.cut_line((0, y0c - 1.5), (0, y1c + 1.5), "D", ext=1.0, arrow_dir=(-1, 0))
    a0, a1 = M["scallop_deg"]
    am = math.radians(0.5 * (a0 + a1))
    b2 = P.BALL_XY[2]
    lab = [((P.NEST_R * math.cos(math.radians(40)), P.NEST_R * math.sin(math.radians(40))), f"nest R{fmt(P.NEST_R)} about (0, 0); the D flat\ny = {co(P.NEST_FLAT)} is the key (one orientation)"),
           ((12.0, 0.5 * (P.STRIP_Y0 + P.NEST_FLAT)), f"front strip (y >= {fmt(P.STRIP_Y0)}) at z {co(P.NEST_FLOOR_Z)}:\nball foot 1 and the nose of the marker land here"),
           ((lw - 1.0, P.LIP_Y0 + 0.4), f"fixed lip, |x| <= {fmt(lw)}, {fmt(M['lip_overlap'])} over the\nmarker top (between the windows)"),
           ((8.0, 4.0), f"drained floor: {fmt(M['basin_depth'])} below the strip on the\ncentre line, falling {fmt(M['basin_fall_deg'], 0)}° to both sides"),
           ((26.0 * math.cos(am), 26.0 * math.sin(am)), f"finger scallop (x2), {a0:.0f}° to {a1:.0f}°: also\nthe drain of the floor"),
           ((b2[0] + 1.2, b2[1] - 1.2), f"pad Ø{fmt(M['ball_pad_dia'])} under each rear ball foot,\ntop at z {co(P.NEST_FLOOR_Z)}"),
           ((P.PAD_XS[-1] + 1.6, P.PAD_Y - 1.6), f"pin slot {fmt(P.PAD_XS[-1] - P.PAD_XS[0] + P.CRADLE_PIN_SLOT_W)} x {fmt(P.CRADLE_PIN_SLOT_W)} on y = {co(P.PAD_Y)},\nrim {fmt(M['slot_rim_t'])} wide; dam to the latch well"),
           ((hw - 0.5, P.LATCH_Y_FACE - 0.4), f"latch: beam {fmt(M['latch_w'])} wide, straight nose\nat y = {co(P.HOOK_Y)} (full width)"),
           ((P.WELL_HX - 0.4, P.WELL_Y0 - 1.0), f"guard wall with two stop ribs\n(hook travel {fmt(M['latch_stop_travel'])} mm)"),
           ((M["tab_w"] / 2 - 1.0, P.TAB_Y0 + 1.5), "thumb tab: press down to release;\nthe tab stop is under its end")]
    v.label_column(lab, 168, side="right", fs=5.6, min_gap=7.2, y_min=124, y_max=264)
    _triad(sh, 178, 110, (1, 0), (0, 1))
    # ---------------- section D-D with the marker seated
    ss = 2.8
    allp = list(parts)
    d = sh.view((238 - y0c * ss, 222), ss, "SECTION D-D  (x = 0), marker seated, centre pin on its pad   2.8:1", (232, 272))
    draw_section(d, parts, allp, "x", 0.0)
    d.lines([np.array([(y0c - 2, 0.0), (y1c + 2, 0.0)])], lw=0.3, color="#b02020", ls=(0, (12, 2.5, 2, 2.5)))
    d.levels([(P.LATCH_TOP_Z, "latch top"), (P.LIP_Z1, "lip top"), (P.T, "marker top"), (P.TAB_STOP_Z, "tab stop"), (zt, "body top"), (0.0, "marker base plane"),
              (P.CPCB_Z1, "PCB top"), (P.CPCB_Z0, ""), (zb, "underside")], y0c, side="left", x_text=d.X(y0c) - 4, fs=5.6, min_gap=3.2)
    d.ax.text(d.X(y0c) - 4, d.Y(P.LATCH_TOP_Z) + 4.5, "z above the marker base plane", fontsize=5.2, color=C_DIM, ha="right")
    d.dim_h(y0c, y1c, zb, zb, -5)
    d.dim_v(zb, P.LATCH_TOP_Z, y1c, y1c, 5, nd=2)
    top = [((P.TAB_Y0 + 2.0, P.LATCH_TOP_Z - 0.6), "thumb tab"), ((0.5 * (P.TAB_STOP_Y0 + P.TAB_STOP_Y1), P.TAB_STOP_Z - 1.0), "tab stop"),
           ((P.LATCH_Y_NA, 4.0), "latch"), ((-8.0, 6.9), "marker"), ((P.LIP_Y0 + 0.6, P.LIP_Z0 + 0.6), "lip"), ((22.0, 6.0), "lip tower")]
    bot = [((P.USB_Y0 + 3, P.CPCB_Z1 + 1.6), "USB-C receptacle"), ((-24.0, 0.5 * (P.CPCB_Z0 + P.CPCB_Z1)), "cradle PCB 1.6"), ((P.PAD_Y, -2.5), "spring pin 4"),
           ((-2.0, P.BASIN_RIDGE_Z - 0.05), "drained floor"), ((0.0, -3.0), "body"), ((8.0, -8.5), "lightening pocket"), ((15.0, P.NEST_FLOOR_Z - 0.05), "front strip")]
    d.label_row(top, d.Y(P.LATCH_TOP_Z) + 5, 250, 404, above=True, fs=5.8)
    d.label_row(bot, d.Y(zb) - 9, 244, 404, above=False, fs=5.8)
    # ---------------- view from below
    b = sh.view((336, 116), 1.5, "VIEW FROM BELOW   1.5:1   (+x to the LEFT)", (240, 167))
    b.hlr([cr], "bottom")
    hx = P.CPCB_HX + P.CLR
    fx, fy = M["foot_xy"]
    b.dim_h(-fx, fx, P.CRADLE_CY + fy, P.CRADLE_CY + fy, 0, at=b.Y(y1c) + 4, suffix=" foot pockets")
    (sx1, sy1), (sx2, sy2) = P.CPCB_SCREWS
    lab = [((fx, P.CRADLE_CY - fy), f"foot pocket Ø{fmt(M['foot_pocket_dia'])} x {fmt(M['foot_pocket_depth'])} (x4) at\n(+-{fmt(fx)}, {co(P.CRADLE_CY)} +-{fmt(fy)}), blind core Ø{fmt(M['core_dia'])} to z {co(P.CORE_Z1)}"),
           ((hx - 1.0, -22.0), f"PCB pocket {fmt(2 * hx)} x {fmt(P.CPCB_Y1 - P.CPCB_Y0 + 2 * P.CLR)},\nceiling z {co(P.CPCB_Z1)}"),
           ((sx1, sy2), f"spot mark (x4): drill Ø1.6 x 3 for M2\nscrews at (+-{fmt(sx1)}, {co(sy1)}), (+-{fmt(sx2)}, {co(sy2)})"),
           ((M["lighten_x"][0] + 4, 0.0), f"lightening pocket (x3),\nceiling z {co(M['lighten_ceiling_z'])}")]
    b.label_column(lab, 280, side="left", fs=5.7, min_gap=7.4, y_min=70, y_max=150)
    sh.note(16, 108, [
        f"1. Charging and data dock only (rev D: every number of the YAML cradle block). Printed body {fmt(2 * X)} x {fmt(P.CRADLE_SIZE[1])} x {fmt(P.CRADLE_SIZE[2])} mm (z {co(zb)} to {co(zt)}); lip and latch stand above it,",
        f"   overall height {fmt(P.LATCH_TOP_Z - zb, 2)} mm. Frame: the marker frame with the marker seated (origin at the marker centre on its base plane); body from y {co(y0c)} to {co(y1c)}.",
        f"2. The nest is the marker outline + {fmt(P.CLR)} mm; the D flat is the key, so the marker seats one way round only. Its three ball feet rest on the front strip",
        f"   and on two pads (z = {co(P.NEST_FLOOR_Z)}); the rest of the floor is a basin that drains through the scallops. A rim round the pin slot and a dam in front of",
        f"   the latch well keep water off the cradle PCB; the well drains through a tunnel ({fmt(M['well_drain_x'][1] - M['well_drain_x'][0])} x {fmt(M['well_drain_h'])}) to the rear face beside the USB opening.",
        f"3. Hold-down: fixed lip over the top front edge (|x| <= {fmt(lw)}, clear of windows, cover glass and vent) + sprung latch at the rear with a thumb tab.",
        "   The marker goes in nose first under the lip and is pressed down at the rear until the latch clicks. Details and numbers: sheet 2.",
        f"4. Cradle PCB top at z = {co(P.CPCB_Z1)}: the spring pins stand at their working height ({fmt(P.PIN_WORK_H)}) on the copper face of the pads (z {fmt(P.PAD_Z0, 3)}). Seven pin",
        "   positions, consumer build fits four (VBUS, D-, D+, GND at x = -7.62 ... 0.0), factory fixture seven. Pin and receptacle envelopes are PROVISIONAL.",
        "5. PRINT ORIENTATION LOCKED: the x axis of this drawing is the build direction (cradle_print.stl / .step), so that the profiles of latch and lip lie in",
        "   the build plane. No tumbling, no vapor smoothing. No wall below 0.8 mm, latch root 1.05 mm, no trapped powder (checks 5, 6).",
        f"6. First-article dimensions: front nest wall to hook nose {fmt(P.NEST_FLAT - P.HOOK_Y, 2)} +-0.15; beam to stop ribs {fmt(P.LATCH_STOP_GAP, 2)}; tab-stop top z {fmt(P.TAB_STOP_Z, 2)}.",
    ], fs=5.8, title="NOTES")
    sheets.append(sh)

    # ------------------------------------------------------------------ sheet 2: hold-down details
    sh = Sheet("GL1-020", "Cradle (charging / data dock with hold-down)", 2, 2, part="hold-down details, pin row, insertion", material=mat,
               process="see sheet 1", tolerance=TOL_PRINT, scale="8:1 / 5:1 / 1.8:1", params_rev=P.REV)
    puck = [n for n, i in parts.items() if i.group == "puck"]
    names = ["cradle", "cradle_pcb", "usb_receptacle"] + puck
    # ---- detail J: latch
    sj = 8.0
    ya, yb, za, zc_ = -35.6, -19.0, -6.6, 12.4
    j = sh.view((24 - ya * sj, 108 - za * sj), sj, "DETAIL J - rear latch, section x = 0   8:1", (16, 276))
    clip = (ya, za, yb, zc_)
    draw_section(j, parts, names, "x", 0.0, clip=clip, lw=0.55)
    j.frame(*clip)
    j.levels([(P.LATCH_TOP_Z, "latch top"), (P.HOOK_HEEL_Z, "heel"), (P.HOOK_Z0, "nose"), (P.T, "marker top"), (P.LATCH_NECK_Z, "neck"), (zt, "body top"),
              (P.NEST_FLOOR_Z, "strip / dam"), (zr, "latch root"), (P.CPCB_Z1, "PCB top")], yb, side="right", x_text=j.X(yb) + 5, fs=5.6, min_gap=3.3)
    hz = lambda z: float(P.latch_h(z - zr))
    z_r = zr + M["latch_root_fillet"] + 0.25
    j.dim_h(P.LATCH_Y_FACE - hz(z_r), P.LATCH_Y_FACE, z_r, z_r, 0, at=j.Y(z_r), text_side="left", text=fmt(hz(z_r), 2), suffix=f" ({fmt(P.LATCH_H0, 2)} at the root)", fs=5.8)
    j.dim_h(P.LATCH_Y_FACE - hz(P.LATCH_NECK_Z), P.LATCH_Y_FACE, P.LATCH_NECK_Z, P.LATCH_NECK_Z, 0, at=j.Y(P.LATCH_NECK_Z), text_side="left",
            text=fmt(hz(P.LATCH_NECK_Z), 2), suffix=f" neck ({fmt(P.LATCH_HN, 2)} + R{fmt(M['latch_neck_blend'], 0)} blend)", fs=5.8)
    j.dim_h(P.LATCH_Y_BACK1, P.LATCH_Y_FACE, P.HOOK_Z0 - 0.3, P.HOOK_Z0 - 0.3, 0, at=j.Y(P.HOOK_Z0 - 0.3), text_side="left", suffix=" at the hook", fs=5.8, nd=2)
    zg = M["guard_top_z"] - 0.25
    j.ax.text(j.X(P.WELL_Y0 - 1.6), j.Y(M["guard_top_z"]) + 3.0, f"stop ribs at x = +-{fmt(M['stop_rib_x'])}: {fmt(P.LATCH_STOP_GAP, 2)} behind the beam at\ntheir top (z {fmt(M['guard_top_z'])}); met at {fmt(M['latch_stop_travel'])} mm of hook travel",
              fontsize=5.6, color=C_DIM, ha="center", va="bottom", zorder=31, bbox=dict(fc="white", ec="none", pad=0.4, alpha=0.9))
    j.dim_h(P.LATCH_Y_FACE, -P.R_OUT, 3.6, 3.6, 0, at=j.Y(3.2), text_side="right", suffix=" gap", fs=5.8)
    j.dim_h(-P.TUB_TOP_FLAT_R, P.HOOK_Y, P.HOOK_Z0, P.HOOK_Z0, 0, at=j.Y(zc_) + 3.0, text_side="right", suffix=" nose on the flat top", fs=5.8, nd=2)
    j.dim_h(P.LATCH_Y_FACE, P.HOOK_Y, P.LATCH_TOP_Z, P.LATCH_TOP_Z, 0, at=j.Y(zc_) + 7.5, text_side="right", suffix=" nose overhang", fs=5.8)
    j.dim_v(P.T, P.HOOK_Z0, P.HOOK_Y + 0.5, P.HOOK_Y + 0.5, 0, at=j.X(-20.2), text_side="above", fs=5.8)
    j.dim_h(P.TAB_Y0, P.LATCH_Y_BACK1, P.LATCH_TOP_Z, P.LATCH_TOP_Z, 0, at=j.Y(zc_) + 3.0, suffix=" tab", fs=5.8)
    j.dim_v(zr, P.HOOK_Z0, P.LATCH_Y_BACK0 - 0.9, P.LATCH_Y_BACK1 - 0.3, 0, at=j.X(-26.3), suffix=" L", fs=5.8)
    j.dim_v(P.TAB_STOP_Z, P.TAB_Z0, P.TAB_STOP_Y0, P.TAB_Y0, 0, at=j.X(ya) + 3.5, suffix=" tab end to its stop", fs=5.6, nd=2)
    j.leader((P.HOOK_Y - 0.75, P.HOOK_LEAD_Z0 + 0.75 / math.tan(math.radians(M["hook_lead_deg"]))),
             f"lead-in {fmt(M['hook_lead_deg'], 0)}° from vertical, nose flat {fmt(M['hook_nose_flat'])}", 14, 4, ha="left", color=C_DIM, fs=5.6)
    j.leader((P.HOOK_Y - 0.9, P.HOOK_Z0 + 0.9 * P.HOOK_RAKE_TAN), f"retaining face raked {fmt(M['hook_rake_deg'], 0)}° (nose lowest),\nnose {fmt(P.CLR)} above the tub top; heel R{fmt(M['hook_heel_fillet'])}", 14, 9, ha="left", color=C_DIM, fs=5.6)
    j.leader((P.LATCH_Y_NA, zr + 0.2), f"root fillets R{fmt(M['latch_root_fillet'])}; {fmt(zr - P.CPCB_Z1, 3)} skin to the PCB pocket", -10, -13, ha="right", color=C_DIM, fs=5.6)
    j.leader((P.WELL_Y0 + 0.4, -1.5), f"latch well: gaps {fmt(M['latch_front_gap'])} front, {fmt(M['latch_back_gap'])} back, {fmt(M['latch_side_gap'])} sides;\nopen top, drain tunnel to the rear face at x {fmt(M['well_drain_x'][0])} to {fmt(M['well_drain_x'][1])}", -20, -42, ha="left", color=C_DIM, fs=5.6)
    j.leader((0.5 * (P.TAB_STOP_Y0 + P.TAB_STOP_Y1), P.TAB_STOP_Z - 0.6), f"tab stop {fmt(M['tab_stop_w'])} x {fmt(M['tab_stop_t'])}, top z {fmt(P.TAB_STOP_Z, 2)}:\nthe tab lands at {fmt(M['tab_stop_travel'])} mm of hook travel", 10, -52, ha="left", color=C_DIM, fs=5.6)
    # ---- detail K: lip
    ya, yb, za, zc_ = 15.4, 24.4, -1.4, 10.4
    k = sh.view((204 - ya * sj, 172 - za * sj), sj, "DETAIL K - front lip, section x = 0   8:1", (198, 276))
    clip = (ya, za, yb, zc_)
    draw_section(k, parts, names, "x", 0.0, clip=clip, lw=0.55)
    k.frame(*clip)
    k.levels([(P.LIP_Z1, "lip top"), (P.LIP_Z0, "lip underside"), (P.T, "marker top"), (zt, "body top"), (P.RIM_Z, "tub rim"), (P.NEST_FLOOR_Z, "front strip")], yb, side="right",
             x_text=k.X(yb) + 5, fs=5.8, min_gap=3.4)
    k.dim_h(P.LIP_Y0, P.Y_VISOR, P.LIP_Z1, P.LIP_Z1, 0, at=k.Y(zc_) + 3.0, text_side="right", suffix=" lip over the marker", fs=6.0)
    k.dim_v(P.T, P.LIP_Z0, P.LIP_Y0 + 0.4, P.LIP_Y0 + 0.4, 0, at=k.X(ya) + 6, text_side="above", fs=5.8)
    k.dim_v(P.LIP_Z0, P.LIP_Z1, P.LIP_Y0, P.LIP_Y0, 0, at=k.X(ya) + 13, text_side="above", fs=5.8)
    k.dim_h(P.NEST_FLAT, P.LIP_POCKET_Y, 5.0, 5.0, 0, at=k.Y(5.6), text_side="right", suffix=" nose pocket", fs=6.0)
    k.dim_h(P.Y_VISOR, P.NEST_FLAT, 1.9, 1.9, 0, at=k.Y(2.5), text_side="left", suffix=" gap", fs=6.0)
    k.leader((22.2, 8.6), f"lip {fmt(2 * lw)} wide (|x| <= {fmt(lw)})", 4, -40, ha="left", color=C_DIM, fs=5.8)
    k.leader((P.NEST_FLAT, 1.0), f"front nest wall y = {co(P.NEST_FLAT)} (the key flat)", 12, -17, color=C_DIM, fs=5.8)
    # ---- section E-E through the pin row
    se = 5.0
    en = ["cradle", "cradle_pcb", "base_plate", "main_pcb", "pcb_adhesive", "tub", "seal_bead"] + [f"spring_pin_{i}" for i in range(1, 8)]
    x0, x1, z0, z1 = -11.6, 11.6, -7.6, 2.3
    e = sh.view((346, 138), se, f"SECTION E-E  (y = {co(P.PAD_Y)}) pin row, marker seated   5:1", (262, 164))
    draw_section(e, parts, en, "y", P.PAD_Y, clip=(x0, z0, x1, z1))
    e.frame(x0, z0, x1, z1)
    xa, xb = P.PAD_XS[0], P.PAD_XS[-1]
    e.dim_h(P.PAD_XS[1], P.PAD_XS[2], P.PCB_Z0, P.PCB_Z0, 0, at=e.Y(z1) + 3.5, text_side="left", suffix=" pitch")
    e.dim_h(xa, xb, P.CPCB_Z0, P.CPCB_Z0, 0, at=e.Y(z0) - 4)
    e.levels([(P.PAD_Z0, "pad face"), (0.0, "marker base plane"), (P.NEST_FLOOR_Z, "slot rim"), (P.BASIN_RIDGE_Z, "basin (x = 0)"), (P.CPCB_Z1, "cradle PCB top"), (P.CPCB_Z0, "")],
             x0, side="left", x_text=e.X(x0) - 4, fs=5.6, min_gap=3.3)
    for i, x in enumerate(P.PAD_XS):
        e.ax.text(e.X(x), e.Y(z0) + 2.2, ["VBUS", "D-", "D+", "GND", "SWDIO", "SWCLK", "NRST"][i], fontsize=4.6, ha="center", va="center", zorder=30,
                  bbox=dict(fc="white", ec="none", pad=0.3, alpha=0.9))
    e.ax.text(e.X(0.5 * (xa + P.PAD_XS[3])), e.Y(z0) - 8.5, "consumer build: these four", fontsize=5.6, ha="center", color=C_DIM)
    e.ax.text(e.X(P.PAD_XS[5]), e.Y(z0) - 8.5, "factory fixture: all seven", fontsize=5.6, ha="center", color=C_DIM)
    e.leader((P.PAD_XS[-1] + M["pin_plunger_dia"] / 2, 0.45), f"plunger Ø{fmt(M['pin_plunger_dia'])} in the base slot ({fmt(P.PAD_HOLE_D)} wide)", 2, 9.5, ha="right", color=C_DIM, fs=5.6)
    e.leader((P.PAD_XS[0] - M["pin_body_dia"] / 2, -3.0), f"barrel Ø{fmt(M['pin_body_dia'])} in the printed slot ({fmt(P.CRADLE_PIN_SLOT_W)} wide)", -3, -34, ha="left", color=C_DIM, fs=5.6)
    # ---- insertion sequence
    sp = 1.8
    q = sh.view((83, 37), sp, "INSERTION PATH   1.8:1   section x = 0, marker outline at four tilts", (16, 92))
    gq = G.section_polys(A.solid_of(parts["cradle"]), "x", 0.0)
    q.fill(gq, fc=style("cradle")[0], hatch=style("cradle")[1], lw=0.45)
    env = G.section_polys(PT.marker_envelope().val(), "x", 0.0)
    env = max(getattr(env, "geoms", [env]), key=lambda g: g.area)
    lsec = G.section_polys(PT.latch().val(), "x", 0.0)
    lsec = max(getattr(lsec, "geoms", [lsec]), key=lambda g: g.area)
    th_peak = max(travel, key=travel.get) if travel else 1.5
    cols = {17.0: "#1a3f8f", 9.0: "#b06000", th_peak: "#b02020", 0.0: "k"}
    for th, col in cols.items():
        s_, h_ = H.path_pose(th)
        q.lines([_xf_poly(env, th, s_, h_)], lw=0.7 if th == 0 else 0.5, color=col, ls="-" if th == 0 else (0, (5, 2)), zorder=12)
        py, pz = H.xf(-P.R_OUT, P.T, th, s_, h_)
        q.ax.text(q.X(py) + (9.0 if th == 0 else -1.0), q.Y(pz) + (-3.6 if th == 0 else 1.2), f"{th:g}°" + (" (seated)" if th == 0 else ""), fontsize=5.8, color=col,
                  ha="left", va="bottom", zorder=31, bbox=dict(fc="white", ec="none", pad=0.3, alpha=0.85))
    if travel:
        dpk = travel[th_peak]
        pts = np.asarray(lsec.exterior.coords)
        defl = np.array([P.latch_pose(y, z, dpk, "F") for y, z in pts])
        q.lines([defl], lw=0.5, color="#b02020", ls=(0, (2, 1.5)), zorder=13)
    q.lines([np.array([(P.PAD_Y - 0.535, P.PIN_BODY_Z1), (P.PAD_Y - 0.535, P.PIN_TIP_FREE_Z), (P.PAD_Y + 0.535, P.PIN_TIP_FREE_Z), (P.PAD_Y + 0.535, P.PIN_BODY_Z1)])],
            lw=0.6, color="#b08000", zorder=14)
    sh.note(134, 50, [
        "1. Tilt the marker nose-down, slide the top front edge under the lip, lower",
        "   the rear: its bottom edge runs down the 30° lead-in, pushes the latch",
        f"   back by up to {fmt(c['d_ins'], 2)} mm (red, dotted) and the hook snaps over the top.",
        f"2. The pads meet the free plungers (tip z {fmt(P.PIN_TIP_FREE_Z, 2)}, orange) at about 1.9° of tilt;",
        f"   seated, the pins are compressed {fmt(P.PIN_COMPRESSION, 2)} of {fmt(M['pin_full_stroke'], 2)} mm.",
        "3. Release: press the thumb tab down until the hook lets go (the tab stop",
        f"   limits it); the pins lift the rear about {fmt(c['pop_up'], 1)} mm; lift at the finger scallops.",
        f"4. Check 7 poses the marker solids at {len(M['insertion_tilts_deg'])} tilts from {max(M['insertion_tilts_deg']):.0f}° to 0°: no",
        "   interference with lip, nest walls, floor or pins.",
    ], fs=5.3, title="NOTES")
    g_, n_, t_ = c["governing"], c["nominal"], c["worst_tol"]
    fe_stop = fe.get("FULL DEFLECTION 1: hook pushed or pulled back onto the stop ribs"); fe_tab = fe.get("FULL DEFLECTION 2: thumb tab pressed onto its stop")
    rows = [["Hold-down (PA12 MJF, E = %.0f MPa); check 7" % c["E"], "Value"],
            ["Latch beam: b; h root / neck / at the hook; L", f"{fmt(c['b'])}; {fmt(P.LATCH_H0, 2)} / {fmt(P.LATCH_HN, 2)} ({fmt(float(P.latch_h(P.LATCH_NECK_Z - M['latch_root_z'])), 2)} blended) / {fmt(P.LATCH_H1, 2)}; {fmt(c['L'], 2)} mm"],
            ["Pin force: 7 pins / 4 pins; marker weight", f"{c['Fp7']:.2f} N / {c['Fp4']:.2f} N; {c['weight']:.2f} N"],
            ["Retention, no friction, marker centred", f"{n_['F_hook']:.2f} N at the hook = {n_['factor']:.1f} x the 7-pin force"],
            ["  marker against the front wall (governing)", f"{g_['F_hook']:.2f} N = {g_['factor']:.1f} x (>= {M['retention_factor_required']:.0f} x); needs E >= {g_['E_min']:.0f} MPa"],
            ["  governing, overlap -%.1f mm (tolerance)" % max(M["overlap_tolerances"]), f"{t_['F_hook']:.2f} N = {t_['factor']:.1f} x; needs E >= {t_['E_min']:.0f} MPa"],
            ["Hook travel: insertion / release fwd, ctr, rear", f"{c['d_ins']:.2f} / {c['d_rel_fwd']:.2f}, {c['d_rel']:.2f}, {c['d_rel_max']:.2f} mm (posed solids)"],
            ["Full deflection: stop ribs / tab stop", f"{c['d_stop']:.2f} / {c['d_tab']:.2f} mm of hook travel"],
            ["Strain there: beam formula (FE peak); limit", f"{100 * c['eps_stop']:.2f} ({fe_stop if fe_stop is not None else '-'}) / {100 * c['eps_tab']:.2f} ({fe_tab if fe_tab is not None else '-'}) %; {100 * M['latch_strain_limit']:.1f} %"],
            ["Insertion force at the thumb (mu 0.2 / 0.3 / 0.4)", " / ".join(f"{v_:.1f}" for v_ in c["ins"].values()) + " N"],
            ["Release: thumb on the tab (fwd / ctr / rear)", f"{c['F_tab_fwd']:.1f} / {c['F_tab']:.1f} / {c['F_tab_max']:.1f} N; tab lands at {c['F_tab_stop']:.1f} N"],
            ["Marker float against lip and hook with pins fitted", f"up to {fmt(P.CLR)} mm (pins then {fmt(P.PIN_FLOAT_H)} mm high)"]]
    sh.table(134, 100, rows, [56, 70], fs=5.1, row_h=3.7)
    rows = [["Cradle PCB (2 layers)", "Value"],
            ["Outline", f"{fmt(P.CPCB_SIZE[0])} x {fmt(P.CPCB_SIZE[1])} x {fmt(P.CPCB_SIZE[2])}, x +-{fmt(P.CPCB_HX)}, y {co(P.CPCB_Y0)} to {co(P.CPCB_Y1)}"],
            ["Pin positions (7)", f"y = {co(P.PAD_Y)}, x = {co(xa)} ... {co(xb)}, pitch {fmt(P.PAD_XS[1] - P.PAD_XS[0])}"],
            ["Screws (4 x M2 thread-forming)", f"(+-{fmt(sx1)}, {co(sy1)}) and (+-{fmt(sx2)}, {co(sy2)})"],
            ["USB-C receptacle", f"GCT USB4105, top face, mouth at y {co(P.USB_Y0)}"],
            ["Top face", f"z = {co(P.CPCB_Z1)} (pad face {fmt(P.PAD_Z0, 3)} - working height {fmt(P.PIN_WORK_H)})"]]
    sh.table(312, 270, rows, [33, 62], fs=5.2, row_h=3.7)
    sheets.append(sh)
    return _save("GL1-020_cradle", sheets)


# ==============================================================================================
# DXF profiles
# ==============================================================================================
def _fr4_layer(e):
    """Layer of one profile entity of the FR-4 base plate, for the fabricator: drill, routed opening, routed slot or outline."""
    kind = e[0]
    if kind == "circle":
        c, r = e[1], e[2]
        if abs(2 * r - P.BALL_HOLE_D) < 1e-6:
            return "DRILL_NPTH_D%s" % f"{P.BALL_HOLE_D:.2f}".replace(".", "p")
        return "ROUT_OPENING_D%s" % f"{2 * r:.1f}".replace(".", "p")
    pts = [e[1], e[2]] if kind == "line" else ([e[1]] if kind == "arc" else list(e[1]))
    if all(abs(p_[1] - P.PAD_Y) <= P.PAD_HOLE_D / 2 + 1e-6 and abs(p_[0]) <= P.PAD_SLOT_L / 2 + 1e-6 for p_ in pts):
        return "ROUT_SLOT_%sx%s" % (f"{P.PAD_SLOT_L:.2f}".replace(".", "p"), f"{P.PAD_HOLE_D:.1f}".replace(".", "p"))
    return "OUTLINE_ROUT"


def export_dxf(parts):
    import ezdxf
    DXF_DIR.mkdir(parents=True, exist_ok=True)
    for f in DXF_DIR.glob("*.dxf"):
        f.unlink()
    cxr = P.CAM_XY["R"][0]
    alt = A.ALT_SUFFIX
    alt_t = P.BASE_VARIANTS[P.BASE_ALT]
    zs_alt = alt_t["thickness"] + 0.5 * alt_t["psa_t"]
    t = lambda v_: f"{v_:.2f}".replace(".", "p")
    files = {
        "GL1-010_tub_profiles": [("Z0p6_RIM", "tub", "z", 0.6), ("Z1p5_LEDGE_SPIGOTS_POSTS_B", "tub", "z", 1.5), ("Z4p0_POSTS_HOODS", "tub", "z", 4.0),
                                 ("Z5p61_OPTICAL_AXIS", "tub", "z", P.AXIS_Z), ("Z6p0_THICK_ROOF", "tub", "z", 6.0), ("Z7p0_RECESS", "tub", "z", 7.0)],
        "GL1-011_base_plate_FR4_fab": [(_fr4_layer, "base_plate", "z", 0.5 * P.BASE_T)],
        "GL1-012_base_plate_PA12_profile": [(f"PROFILE_{t(alt_t['thickness'])}_PA12", "base_plate" + alt, "z", 0.5 * alt_t["thickness"])],
        "GL1-013_baffle_ring_profile": [(f"RING_D{t(2 * P.BAFFLE_RO)}_D{t(2 * P.BAFFLE_RI)}_H{t(P.BAFFLE_RING_H)}", "baffle_ring", "z", 0.5 * (P.BAFFLE_RING_Z0 + P.BAFFLE_RING_Z1))],
        "GL1-020_cradle_profiles": [("Z8p6_LIP_HOOK", "cradle", "z", 8.6), ("Z5p0_LIP_LATCH_GUARD_TABSTOP", "cradle", "z", 5.0), ("Z1p0_NEST", "cradle", "z", 1.0),
                                    ("Zm0p4_STRIP_PADS_RIM_BASIN", "cradle", "z", -0.4),
                                    ("Zm2p0_LATCH_WELL_PIN_SLOT_DRAIN", "cradle", "z", -2.0), ("Zm6p0_POCKETS", "cradle", "z", -6.0),
                                    ("Zm10p5_FOOT_POCKETS", "cradle", "z", -10.5), ("X0_SECTION_D-D", "cradle", "x", 0.0)],
        # adhesive die cuts: one file per part, each on its own layer, all in the marker frame
        "GL1-030_die_cut_pcb_sheet_FR4_build": [(f"PCB_SHEET_{t(P.PSA_T)}_FR4_BUILD_PLAIN_OPENING", "pcb_adhesive", "z", 0.5 * (P.PSA_Z0 + P.PSA_Z1))],
        "GL1-031_die_cut_pcb_sheet_PA12_build": [(f"PCB_SHEET_{t(alt_t['psa_t'])}_PA12_BUILD_BAFFLE_PATTERN", "pcb_adhesive" + alt, "z", zs_alt)],
        "GL1-032_die_cut_lcd_frame": [("LCD_FRAME_0p15_WITH_VENT_CHANNEL", "lcd_adhesive", "z", 0.5 * (P.LCD_Z1 + P.BOND_Z))],
        "GL1-033_die_cut_cover_tape_ring": [(f"COVER_TAPE_{t(P.CG_TAPE_T)}_D{t(P.CG_D)}_D{t(M['cover_tape_id'])}", "cover_tape", "z", 0.5 * (P.RECESS_FLOOR_Z + P.CG_Z0))],
        "GL1-034_die_cut_baffle_annulus": [(f"BAFFLE_ANNULUS_{t(P.BAFFLE_PSA_T)}_D{t(2 * P.BAFFLE_RO)}_D{t(2 * P.BAFFLE_RI)}", "baffle_adhesive", "z", 0.5 * (P.BAFFLE_RING_Z1 + P.PCB_Z0))],
        "GL1-040_main_pcb_outline": [("BOARD_OUTLINE_LOCATING_HOLE_AND_SLOT_POSTS_B", None, "z", 0.5 * (P.PCB_Z0 + P.PCB_Z1))],
    }
    # carrier liner of the two PCB-sheet die cuts: outline and two tooling holes for the posts of the lamination jig (the sheet is
    # placed on the base plate by these, not by eye: a sheet 0.25 mm off would put adhesive on the seal land)
    lt = M["liner_tooling"]
    lw_, lh_ = lt["liner"][0] / 2, lt["liner"][1] / 2
    liner = [("circle", (sx_ * lt["x"], 0.0), lt["dia"] / 2) for sx_ in (-1, 1)] + [("poly", [(-lw_, -lh_), (lw_, -lh_), (lw_, lh_), (-lw_, lh_), (-lw_, -lh_)])]
    extras = {k: [("CARRIER_LINER_%sx%s_TOOLING_HOLES_D%s_AT_X%s" % (t(lt["liner"][0]), t(lt["liner"][1]), t(lt["dia"]), t(lt["x"])), e) for e in liner]
              for k in ("GL1-030_die_cut_pcb_sheet_FR4_build", "GL1-031_die_cut_pcb_sheet_PA12_build")}
    puck = [n for n, i in parts.items() if i.group == "puck"]
    files["GL1-002_section_A-A_x0"] = [(n.upper(), n, "x", 0.0) for n in puck]
    files["GL1-002_section_B-B_x%s" % f"{cxr:.1f}".replace(".", "p")] = [(n.upper(), n, "x", cxr) for n in puck]
    out = []
    for fname, layers in files.items():
        doc = ezdxf.new("R2010"); doc.units = 4                      # millimetres
        msp = doc.modelspace()
        n_ent = 0
        made = {}
        for i, (layer, part, axis, value) in enumerate(layers):
            shape = PT.pcb_board().val() if part is None else A.solid_of(parts[part])
            ents = G.section_edges(shape, axis, value)
            if not ents:
                continue
            for e in ents:
                ln = layer(e) if callable(layer) else layer
                if ln not in made:
                    made[ln] = True
                    doc.layers.add(ln, color=1 + ((len(made) - 1 + i) % 6))
                kind = e[0]
                if kind == "line":
                    msp.add_line(e[1], e[2], dxfattribs={"layer": ln})
                elif kind == "circle":
                    msp.add_circle(e[1], e[2], dxfattribs={"layer": ln})
                elif kind == "arc":
                    msp.add_arc(e[1], e[2], e[3], e[4], dxfattribs={"layer": ln})
                else:
                    msp.add_lwpolyline(e[1], dxfattribs={"layer": ln})
                n_ent += 1
        for ln, e in extras.get(fname, []):
            if ln not in made:
                made[ln] = True
                doc.layers.add(ln, color=5)
            if e[0] == "circle":
                msp.add_circle(e[1], e[2], dxfattribs={"layer": ln})
            else:
                msp.add_lwpolyline(e[1], dxfattribs={"layer": ln})
            n_ent += 1
        f = DXF_DIR / f"{fname}.dxf"
        doc.saveas(f)
        out.append((f, n_ent))
    return out


DRAWINGS = [gl1_001, gl1_002, gl1_010, gl1_011, gl1_012, gl1_013, gl1_020]


def draw_all(parts=None, verbose=True, only=None):
    parts = parts or A.build_parts()
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
    if only:                                                 # quick look at single drawings: nothing is deleted, no DXF
        out = []
        for fn in DRAWINGS:
            if any(o.replace("-", "_").lower() == fn.__name__ for o in only):
                out.append(str(fn(parts)))
                print("  drew", pathlib.Path(out[-1]).name, flush=True)
        return out
    for f in list(DRAW_DIR.glob("GL1-*.pdf")) + list(DRAW_DIR.glob("GL1-*.svg")):
        f.unlink()
    out = []
    for fn in DRAWINGS:
        f = fn(parts)
        out.append(str(f))
        if verbose:
            print("  drew", pathlib.Path(f).name, flush=True)
    for f, n in export_dxf(parts):
        out.append(str(f))
        if verbose:
            print(f"  wrote {f.name} ({n} entities)", flush=True)
    import fabdata as FD
    fab = DRAW_DIR / "fab"
    if fab.exists():
        for f in fab.glob("*"):
            f.unlink()
    for f in FD.write(A.solid_of(parts["base_plate"]), fab):     # Gerber profile, mask layers, Excellon drill of the FR-4 plate
        out.append(str(f))
        if verbose:
            print(f"  wrote fab/{f.name}", flush=True)
    return out


if __name__ == "__main__":
    draw_all(only=sys.argv[1:] or None)
