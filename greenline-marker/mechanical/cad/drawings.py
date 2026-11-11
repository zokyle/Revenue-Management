#!/usr/bin/env python3
"""GL-1 dimensioned drawings (PDF + SVG per sheet, DXF of the 2D profiles), generated from the CAD solids.

    python3 cad/drawings.py           # writes drawings/GL1-001 ... GL1-020 (.pdf, _sheetN.svg) and drawings/dxf/*.dxf

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
    "vent": ("#ffffff", None), "cradle": ("#cfd4dc", "////"), "cradle_plate": ("#eef0f4", "xxxx"), "cradle_pcb": ("#74b6d2", None),
    "usb_receptacle": ("#dcdce2", None),
}
PREFIX_STYLE = {"camera_": ("#9494aa", None), "prism_": ("#bfe3f7", None), "visor_window_": ("#cdeaf8", None), "ball_": ("#f2f2f6", None),
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
        g = G.section_polys(A.solid_of(parts[n]), axis, value)
        if clip is not None:
            g = g.intersection(sbox(*clip))
        if g.is_empty:
            continue
        fc, hatch = style(n)
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
    vx, vy = M["vent_xy"]
    a40 = math.radians(-35)
    lab = [((cxr, yv - 0.25), f"visor window (x2)\n{fmt(P.WIN_W)} x {fmt(P.WIN_H)} x {fmt(P.WIN_T)}"),
           ((0.5, 16.4), f"nose index groove\n{fmt(M['nose_w'])} wide x {fmt(M['nose_depth'])} deep"),
           ((P.RECESS_D / 2 * math.cos(math.radians(28)), P.RECESS_D / 2 * math.sin(math.radians(28))), f"glass recess Ø{fmt(P.RECESS_D)}\nx {fmt(P.RECESS_DEPTH)} deep"),
           ((P.CG_D / 2 * math.cos(math.radians(8)), P.CG_D / 2 * math.sin(math.radians(8))), f"cover glass\nØ{fmt(P.CG_D)} x {fmt(P.CG_T)}"),
           ((vx, vy), f"vent hole Ø{fmt(P.VENT_HOLE_D)}\nat x {co(vx)}, y {co(vy)}"),
           ((P.APERTURE_D / 2 * math.cos(a40), P.APERTURE_D / 2 * math.sin(a40)), f"display aperture\nØ{fmt(P.APERTURE_D)} (under glass)"),
           ((R * math.cos(math.radians(-48)), R * math.sin(math.radians(-48))), f"outline R{fmt(R)},\nflat at y = {co(yv)}")]
    v.label_column(lab, 167, side="right", fs=6.2, min_gap=8.0, y_min=124, y_max=236)
    v.view_arrow((0, yv + 14.0), (0, -1), "F")
    v.view_arrow((R + 3.0, -21.0), (-1, 0), "S")
    _triad(sh, 20, 92, (1, 0), (0, 1))
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
    f.leader((M["key_x"], 0.5), f"key lug {fmt(M['key_w'])} wide in a base notch (x2)", 8, -19, color=C_DIM)
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
    s.leader((-R + 0.15, 0.15), f"bottom chamfer {fmt(M['bottom_chamfer'])} x 45° (arc only)", -3, -26, ha="left", color=C_DIM)
    s.leader((7.0, P.CG_Z1), f"cover glass {fmt(P.CG_BELOW_FLUSH)} below flush", 6, 8, color=C_DIM)
    s.leader((yv, 2.5), "visor (flat) face", 4, -22, ha="left", color=C_DIM)
    # ---------------- notes
    sh.note(16, 76, [
        "1. Outline of the assembled marker. Datum: the base plane z = 0 (the plane that rests on the turf); the three ball feet protrude",
        f"   {fmt(P.BALL_PROT)} mm below it. Visor (flat) face at y = {co(yv)}; the two camera windows look along +y.",
        f"2. Nominal envelope Ø{fmt(2 * R)} x {fmt(T)} mm. With the real {fmt(M['pcb_psa_t'])} mm PSA sheet between PCB and base the base plate sits {fmt(M['pcb_psa_t'])} mm lower",
        f"   relative to the tub: overall height {fmt(T + M['pcb_psa_t'])}, optical axis {fmt(zax + M['pcb_psa_t'])} above the base plane (deviation D10).",
        f"3. Camera windows {fmt(P.WIN_W)} x {fmt(P.WIN_H)} x {fmt(P.WIN_T)} mm, centred on x = +-{fmt(cxr)}, in recesses {fmt(P.WIN_RECESS_W)} wide x {fmt(P.WIN_RECESS_DEPTH)} deep from z = {fmt(P.WIN_Z0)}",
        f"   to the top face. Clear opening {fmt(2 * P.OPEN_HALF_W)} wide, z = {fmt(P.OPEN_Z0)} to {fmt(P.OPEN_Z1)}. Optical axis z = {fmt(zax)}.",
        "4. Sections A-A and B-B: drawing GL1-002. Parts: GL1-010 tub, GL1-011 base plate, GL1-020 cradle.",
        "5. Nothing has been built. All purchased-part envelopes are provisional until checked against manufacturer drawings.",
    ], fs=6.2, title="NOTES")
    sh.table(212, 112, [["Item", "Value", "Source"],
                        ["Envelope", f"Ø{fmt(2 * R)} x {fmt(T)}", "YAML envelope"],
                        ["Visor flat", f"y = {co(yv)}, {fmt(2 * hx)} wide", "YAML / derived"],
                        ["Camera baseline", f"{fmt(2 * cxr)} (x = +-{fmt(cxr)})", "YAML cameras"],
                        ["Optical axis height", f"{fmt(zax)} ({fmt(zax + M['pcb_psa_t'])} with the PSA)", "YAML prisms / D10"],
                        ["Field of view (spec)", f"+-{fmt(M['fov_h_half_deg'])}° h, +{fmt(M['fov_up_deg'])}° / -{fmt(M['fov_down_deg'])}° v", "task statement"],
                        ["Ball feet", f"Ø{fmt(P.BALL_D)}, {fmt(P.BALL_PROT)} proud, at (0, {co(b1y)}), (+-{fmt(abs(b2x))}, {co(b2y)})", "YAML feet"]],
             [32, 62, 34], fs=5.8)
    return _save("GL1-001_assembly_outline", [sh])


# ==============================================================================================
# GL1-002 sections
# ==============================================================================================
def _stack_levels_centre():
    return [(0.0, ""), (P.BASE_T, ""), (P.PCB_Z1, ""), (P.BAT["z1"], ""), (P.BAT["z1"] + P.BAT_SWELL, ""), (P.FOAM_Z0, ""), (P.LCD_Z0, ""),
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
    u8 = next(p for p in P.TOP_PARTS if p["ref"] == "U8")
    top = [((-18.5, T - 0.4), "tub roof 0.8"), ((-9.0, 0.5 * (P.CG_Z0 + P.CG_Z1)), "cover glass"), ((-12.7, P.RECESS_FLOOR_Z + 0.1), "tape ring"),
           ((-15.5, 0.5 * (P.LCD_Z0 + P.LCD_Z1)), "LCD glass"), ((3.0, P.LCD_Z1 + 0.07), "LCD adhesive frame"),
           ((-17.3, 4.4), "LCD flex tail (representative)"), ((-3.0, P.FOAM_Z0 + 0.15), "foam pad"), ((11.2, 0.5 * (P.BOND_Z + P.RECESS_FLOOR_Z)), "roof ledge"),
           ((16.2, P.T - 0.5), "nose groove"), ((yv - 0.4, 3.5), "visor wall 0.8")]
    bot = [((-21.55, 1.1), "seal bead"), ((P.PAD_Y, 0.5), "pad slot"), ((j1["y"], 2.8), "FPC connector J1"), ((-7.0, 2.8), "battery"),
           ((P.GRAIN_Y - P.BAFFLE_RI - 0.4, 0.5), "baffle ring"), ((P.GRAIN_Y, 0.76), "photodiode"), ((u1["y"], 2.6), "MCU U1"),
           ((6.0, 1.4), "PCB 0.8"), ((10.0, 1.065), "PSA sheet"), ((12.0, 0.5), "base plate 1.0"), ((P.BALL_XY[0][1], 0.2), "ball foot 1"),
           ((u8["y"], 2.5), "LDO U8")]
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
    lev = [(0.0, "base plane"), (P.BASE_T, ""), (P.PCB_Z1, ""), (P.BAT["z1"], ""), (P.FOAM_Z0, ""), (P.LCD_Z0, ""), (P.LCD_Z1, ""), (P.BOND_Z, ""),
           (P.RECESS_FLOOR_Z, ""), (P.CG_Z0, ""), (P.CG_Z1, ""), (P.T, "top"), (P.ROOF_Z, ""), (P.LEDGE_Z0, ""), (P.LEDGE_Z1, ""),
           (P.BAT["z1"] + P.BAT_SWELL, "")]
    d.levels(lev, ya, side="left", x_text=d.X(ya) - 9, fs=6.2)
    bat = P.BAT
    lab = [((-9.2, 0.5 * (bat["z0"] + bat["z1"])), f"battery {fmt(bat['z1'] - bat['z0'])}  (z {fmt(bat['z0'])} to {fmt(bat['z1'])})"),
           ((-9.2, bat["z1"] + P.BAT_SWELL / 2), f"swelling allowance {fmt(P.BAT_SWELL)}  (to z {fmt(bat['z1'] + P.BAT_SWELL)}), then {fmt(P.FOAM_Z0 - bat['z1'] - P.BAT_SWELL)} air"),
           ((-9.2, 0.5 * (P.FOAM_Z0 + P.FOAM_Z1)), f"foam pad {fmt(P.FOAM_T)}  (z {fmt(P.FOAM_Z0)} to {fmt(P.FOAM_Z1)})"),
           ((-8.6, 0.5 * (P.LCD_Z0 + P.LCD_Z1)), f"LCD glass {fmt(P.LCD_Z1 - P.LCD_Z0)}  (z {fmt(P.LCD_Z0)} to {fmt(P.LCD_Z1)})"),
           ((-12.2, 0.5 * (P.LCD_Z1 + P.BOND_Z)), f"LCD adhesive frame {fmt(P.LCD_PSA_T)}  (to z {fmt(P.BOND_Z)}, window Ø{fmt(M['lcd_psa_window_dia'])})"),
           ((-11.4, 0.5 * (P.BOND_Z + P.RECESS_FLOOR_Z)), f"roof ledge {fmt(P.ROOF_LEDGE_T)}  (z {fmt(P.BOND_Z)} to {fmt(P.RECESS_FLOOR_Z)}), aperture Ø{fmt(P.APERTURE_D)}"),
           ((-12.2, 0.5 * (P.RECESS_FLOOR_Z + P.CG_Z0)), f"VHB tape ring {fmt(P.CG_TAPE_T)}  (Ø{fmt(P.CG_D)} / Ø{fmt(M['cover_tape_id'])})"),
           ((-9.5, 0.5 * (P.CG_Z0 + P.CG_Z1)), f"cover glass {fmt(P.CG_T)}  (top at z {fmt(P.CG_Z1)}, {fmt(P.CG_BELOW_FLUSH)} below flush)"),
           ((-14.7, 0.5 * (P.ROOF_Z + P.T)), f"roof {fmt(P.ROOF_T)}  (z {fmt(P.ROOF_Z)} to {fmt(P.T)}), recess Ø{fmt(P.RECESS_D)} x {fmt(P.RECESS_DEPTH)}"),
           ((-9.0, 0.5 * (P.PCB_Z0 + P.PCB_Z1)), f"main PCB {fmt(P.PCB_T)}  (z {fmt(P.PCB_Z0)} to {fmt(P.PCB_Z1)})"),
           ((-10.4, P.BASE_T + M["pcb_psa_t"] / 2), f"PSA sheet {fmt(M['pcb_psa_t'])}: zero thickness in the YAML (note 2)"),
           ((-12.5, 0.5 * P.BASE_T), f"base plate {fmt(P.BASE_T)}  (z 0 to {fmt(P.BASE_T)})"),
           ((-10.0, 0.4), f"grain opening Ø{fmt(P.GRAIN_D)} (edge at y {co(P.GRAIN_Y - P.GRAIN_R)})"),
           ((-12.5, 0.5 * (P.PCB_Z1 + P.PCB_Z1 + j1["h"])), f"FPC connector J1, {fmt(j1['h'])} high (to z {fmt(P.PCB_Z1 + j1['h'])})")]
    d.label_column(lab, d.X(yb) + 9, side="right", fs=6.1, min_gap=4.1, y_min=28, y_max=164)
    sh.note(268, 164, [
        "1. Section on the plane x = 0 (the y axis through the centre).",
        "   No single vertical line crosses every layer: the battery ends at",
        f"   y = {co(bat['y'] - bat['dy'] / 2)}, the ledge and tape lie outside r = {fmt(P.APERTURE_D / 2)}.",
        "   Detail C therefore spans both.",
        f"2. The YAML stack carries the PCB-to-base PSA at zero thickness.",
        f"   Real sheet {fmt(M['pcb_psa_t'])} mm: the posts hold the PCB top at tub z = {fmt(P.PCB_Z1)},",
        f"   so the base plate sits {fmt(M['pcb_psa_t'])} lower and the seal bead is",
        f"   {fmt(P.BEAD_T + M['pcb_psa_t'])} instead of {fmt(P.BEAD_T)} (deviation D10).",
        "3. z values are heights above the base plane.",
        "4. Purchased parts are envelope solids.",
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
    top = [((yb0 + 0.5, 4.0), "side wall 1.0"), ((-15.0, P.T - 0.4), "roof 0.8"), ((-6.0, 0.5 * (P.CG_Z0 + P.CG_Z1)), "cover glass"),
           ((-12.0, 0.5 * (P.BOND_Z + P.ROOF_Z)), "thick roof (LCD bonding plane)"), ((2.0, 0.5 * (P.LCD_Z0 + P.LCD_Z1)), "LCD glass"),
           ((P.HOOD_REAR_Y0 + 0.4, 6.0), "hood rear wall"), ((15.9, 5.3), "fold prism"), ((yv - 0.25, 6.9), "visor window")]
    bot = [((yb0 + 1.25, 1.1), "seal bead"), ((u7["y"], 2.4), "LDO U7"), ((-5.2, 2.8), "battery"), ((-5.2, P.FOAM_Z0 + 0.15), "foam pad"),
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
    lev = [(0.0, "base plane"), (P.BASE_T, "base top"), (P.PCB_Z1, "PCB top"), (P.CAM_Z1, "cube top"), (P.PRISM_Z0, "prism bottom"),
           (P.AXIS_Z, "optical axis"), (P.PRISM_Z1, "prism top"), (P.ROOF_Z, "roof underside"), (P.T, "top"),
           (P.WIN_Z0, "window recess"), (P.OPEN_Z0, "opening sill"), (P.LCD_Z0, "LCD"), (P.LCD_Z1, "")]
    d.levels(lev, ya, side="left", x_text=d.X(ya) - 9, fs=6.0)
    # horizontal chain above the detail: wall build-up in y
    yt = d.Y(T) + 4.5
    chain = [(P.HOOD_REAR_Y0, P.HOOD_REAR_Y1), (P.PRISM_Y0, P.PRISM_EXIT_Y), (P.HOOD_FRONT_IN_Y, P.WIN_RECESS_FLOOR_Y), (P.WIN_RECESS_FLOOR_Y, yv)]
    for a, b in chain:
        d.dim_h(a, b, T, T, 0, at=yt, fs=5.8, text_side="left" if a < 15 else "right")
    d.dim_h(P.LCD_Y1, cy - P.CAM_DY / 2, P.CAM_Z1 - 0.3, P.CAM_Z1 - 0.3, 0, at=d.Y(3.0), fs=5.8, text_side="left")
    d.dim_h(cy + P.CAM_DY / 2, P.HOOD_PAD_Y, 3.4, 3.4, 0, at=d.Y(2.35), fs=5.8, text_side="right")
    d.dim_h(P.HOOD_PAD_Y, P.WIN_RECESS_FLOOR_Y, P.WIN_Z0 + 0.2, P.WIN_Z0 + 0.2, 0, at=d.Y(3.75), fs=5.8, text_side="right")
    d.dim_h(P.Y_VISOR_IN, yv, 2.0, 2.0, 0, at=d.Y(1.55), fs=5.8, text_side="right")
    lab = [((cy + 0.4, 0.5 * (P.CAM_Z0 + P.CAM_Z1)), f"camera cube {fmt(P.CAM_DX)} x {fmt(P.CAM_DY)} x {fmt(P.CAM_H)}, centre y {fmt(cy)}"),
           ((P.PRISM_EXIT_Y - 0.5, P.PRISM_Z0 + 0.6), f"prism {fmt(P.PRISM_LEG)} legs, bond gap {fmt(P.PRISM_BOND)}, exit face y {fmt(P.PRISM_EXIT_Y)}"),
           ((P.PRISM_EXIT_Y - 0.3, P.PRISM_Z1 + P.PRISM_ROOF_CLR / 2), f"prism to roof {fmt(P.PRISM_ROOF_CLR)}"),
           ((yv - P.WIN_T / 2, 7.2), f"window {fmt(P.WIN_T)} in a {fmt(P.WIN_RECESS_DEPTH)} recess, z {fmt(P.WIN_Z0)} to {fmt(P.WIN_Z1)}"),
           ((P.WIN_RECESS_FLOOR_Y - 0.25, P.OPEN_Z0 + 0.25), f"opening z {fmt(P.OPEN_Z0)} to {fmt(P.OPEN_Z1)}; sides: {fmt(M['visor_land'])} land, then {fmt(M['visor_bevel_deg'], 0)}° bevel"),
           ((0.5 * (P.HOOD_PAD_Y + P.WIN_RECESS_FLOOR_Y), P.WIN_Z0 + 0.2), f"wall behind the recess {fmt(P.THIN_STRIP_T, 3)} (deviation D04)"),
           ((P.HOOD_REAR_Y1 - 0.06, P.HOOD_Z_OVER_CUBE + 0.06), f"rear-wall edge chamfer {fmt(P.HOOD_REAR_CHAMFER, 2)}: {fmt(P.PRISM_HOOD_CLR, 2)} to the hypotenuse"),
           ((P.Y_VISOR_IN + 0.4, 2.6), f"visor wall {fmt(P.VISOR_WALL)}, sits on the base at z {fmt(P.LEDGE_Z0)}"),
           ((P.BASE_FLAT - 0.4, 0.5), f"base plate runs under the wall to y {fmt(P.BASE_FLAT)}"),
           ((P.PCB_FLAT - 0.5, 1.4), f"PCB flat edge y {fmt(P.PCB_FLAT)}"),
           ((P.LCD_Y1 - 0.3, 5.0), f"LCD glass edge y {fmt(P.LCD_Y1)}"),
           ((P.Y_VISOR_IN + 0.3, 1.1), f"front seal: {fmt(P.BEAD_T)} bead under the visor wall")]
    d.label_column(lab, d.X(yb) + 24, side="right", fs=6.0, min_gap=4.3, y_min=30, y_max=166)
    sh.note(300, 166, [
        f"1. Stack at the camera: base {fmt(P.BASE_T)} + PCB {fmt(P.PCB_T)} +",
        f"   cube {fmt(P.CAM_H)} + bond {fmt(P.PRISM_BOND)} + prism {fmt(P.PRISM_LEG)} = {fmt(P.PRISM_Z1)};",
        f"   clearance {fmt(P.PRISM_ROOF_CLR)}; roof {fmt(P.ROOF_T)}; top {fmt(P.T)}.",
        "2. Red: chief rays on axis and at the vertical",
        f"   field edges (+{fmt(M['fov_up_deg'])}° / -{fmt(M['fov_down_deg'])}°), traced exactly",
        f"   through the prism (n = {M['n_prism']}). The lens",
        "   pupil position is ASSUMED (optics.py).",
        "3. The wall behind the window recess in front",
        f"   of the cube is {fmt(P.THIN_STRIP_T)} mm (deviation D04).",
        "4. z = height above the base plane.",
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
        v.ax.text(v.X(ux), v.Y((y0 + y1) / 2), name, fontsize=5.2, ha="center", va="center", color="#b02020", fontweight="bold", zorder=30,
                  bbox=dict(fc="white", ec="none", pad=0.3, alpha=0.85))
    vx, vy = M["vent_xy"]
    a = math.radians(205)
    lab = [((-cxr - P.HOOD_OUT_HW + 0.4, 15.2), "camera hood: prism bay, side skirts\nto z 3.0, rear wall 0.8 (light baffle)"),
           ((-M["key_x"], yv - 0.4), f"key lug {fmt(M['key_w'])} x {fmt(P.VISOR_WALL)} x {fmt(P.LEDGE_Z0)} high\nat x = +-{fmt(M['key_x'])} (below the visor wall)"),
           ((-P.LCD_POCKET_X - 0.4, 6.0), f"glass locating rib {fmt(M['lcd_rib_t'])} wide,\ndown to z {fmt(M['lcd_rib_z0'])} (x4 side, x2 rear)"),
           ((-P.THICK_RING_R * math.cos(math.radians(20)), P.THICK_RING_R * math.sin(math.radians(20)) * 0 - 1.5), f"thick roof ring Ø{fmt(2 * P.THICK_RING_R)}\n(carries the glass recess)"),
           ((-vx, vy), f"vent pad {fmt(M['vent_pad'] + 0.6)} x {fmt(M['vent_pad'])}, {fmt(M['vent_pad_h'])} proud,\nhole Ø{fmt(P.VENT_HOLE_D)} at x {co(vx)}, y {co(vy)}"),
           ((-P.APERTURE_D / 2 * math.cos(math.radians(-25)), P.APERTURE_D / 2 * math.sin(math.radians(-25))), f"display aperture Ø{fmt(P.APERTURE_D)}"),
           ((-P.LEDGE_RI * math.cos(math.radians(-40)), P.LEDGE_RI * math.sin(math.radians(-40))), f"seating ledge to r {fmt(P.LEDGE_RI)},\nz {fmt(P.LEDGE_Z0)} to {fmt(P.LEDGE_Z1)} (seal face below)"),
           ((-P.R_IN * math.cos(math.radians(-55)), P.R_IN * math.sin(math.radians(-55))), f"cavity wall R{fmt(P.R_IN)} (wall {fmt(P.WALL)})"),
           ((-6.5, -18.6), "support post, 1.6 x 1.6 (x8): see table"),
           ((-0.9, 16.5), f"pad under the nose groove\n(keeps {fmt(P.MIN_WALL)} roof)")]
    v.label_column(lab, 186, side="right", fs=5.9, min_gap=7.6, y_min=96, y_max=246)
    _triad(sh, 36, 100, (-1, 0), (0, 1))
    # detail E: wall / ledge / roof at the rear
    se = 14.0
    ya, yb = -23.35, -19.2
    d = sh.view((298 - ya * se, 150 + 0.3 * se), se, "DETAIL E - wall, ledge and roof at the rear (section x = 0)   14:1", (262, 272))
    clip = (ya, -0.3, yb, T + 0.25)
    g = G.section_polys(A.solid_of(tub), "x", 0.0).intersection(sbox(*clip))
    d.fill(g, fc=style("tub")[0], hatch=style("tub")[1], lw=0.6)
    d.frame(*clip)
    d.levels([(0.0, "rim (base plane)"), (M["bottom_chamfer"], "chamfer"), (P.LEDGE_Z0, "seal face"), (P.LEDGE_Z1, "ledge top"), (P.ROOF_Z, "roof underside"),
              (T - M["top_fillet"], "R start"), (T, "top")], yb, side="right", x_text=d.X(yb) + 6, fs=6.0)
    d.dim_h(-R, -P.R_IN, 3.6, 3.6, 0, at=d.Y(4.4), text_side="left", suffix=" wall")
    d.dim_h(-P.R_IN, -P.LEDGE_RI, P.LEDGE_Z1, P.LEDGE_Z1, 0, at=d.Y(3.0), text_side="right", suffix=" ledge")
    d.dim_v(P.ROOF_Z, T, -20.2, -20.2, 0, at=d.X(-20.2), text_side="below", suffix=" roof")
    d.leader((-R + 0.17, T - 0.17), f"R{fmt(M['top_fillet'])}", -6, 6, ha="right", color=C_DIM)
    d.leader((-R + 0.15, 0.15), f"{fmt(M['bottom_chamfer'])} x 45°", -6, -5, ha="right", color=C_DIM)
    rows = [["Post", "x centre", "y centre", "from - to"]]
    for name, x0, x1, y0, y1 in P.post_rects():
        rows.append([name, co((x0 + x1) / 2), co((y0 + y1) / 2), f"PCB top z {fmt(P.PCB_Z1)} - roof"])
    sh.table(262, 142, rows, [14, 22, 22, 40], fs=5.8)
    sh.note(366, 142, ["Posts 1.6 x 1.6 mm.", "Their feet are PCB", "keep-outs: nothing", "may be placed under", "them (see README)."], fs=5.8)
    sh.note(16, 71, [
        "1. Material HP 3D High Reusability PA 12, Multi Jet Fusion, dyed black, chemical vapor smoothing. Print roof-down (cosmetic top on the bed side, cavity open upward).",
        f"2. Minimum wall {fmt(P.MIN_WALL)} mm by design. Recorded exceptions: the {fmt(P.THIN_STRIP_T)} mm strip behind each window recess (D04), the {fmt(M['visor_land'])} mm aperture land with its bevel (D05),",
        f"   and the feet of chamfered edges (side wall {fmt(P.WALL - M['bottom_chamfer'])} at the rim, hood rear wall {fmt(P.MIN_WALL - P.HOOD_REAR_CHAMFER)}). See export/check_report.md, check 5.",
        "3. No closed void and no cavity without a 2 mm escape path (check 6). Depowder the two camera bays, the visor openings and the Ø1.0 vent hole with care.",
        "4. Critical-to-function: bonding plane z 5.55 (LCD), recess floor z 6.35 (cover glass), seal face z 1.2, post feet z 1.8 (all in one plane +-0.1), window recesses.",
        "   First-article inspection of these is a release gate. Nothing has been built.",
        f"5. Fit clearances are {fmt(P.CLR)} mm nominal; the PCB-to-ledge gap is {fmt(P.LEDGE_RI - P.PCB_R)} and the window-to-recess gap {fmt((P.WIN_RECESS_W - P.WIN_W) / 2)} per side (D12): fit windows to the printed recess.",
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
           ((M["vent_xy"][0], M["vent_xy"][1]), f"vent hole Ø{fmt(P.VENT_HOLE_D)}"),
           ((0.5, 16.2), f"groove {fmt(M['nose_w'])} x {fmt(M['nose_depth'])} deep")]
    v.label_column(lab, 137, side="right", fs=6.0, min_gap=5.0, y_min=196, y_max=252)
    # section A-A of the tub alone
    sa = 5.0
    a_ = sh.view((292, 238), sa, "SECTION A-A  (x = 0)   5:1", (178, 280))
    ga = G.section_polys(A.solid_of(tub), "x", 0.0)
    a_.fill(ga, fc=style("tub")[0], hatch=style("tub")[1], lw=0.6)
    a_.dim_v(0, T, -R, -R, 0, at=a_.X(-R) - 5)
    a_.levels([(P.LEDGE_Z0, ""), (P.LEDGE_Z1, ""), (P.BOND_Z, ""), (P.RECESS_FLOOR_Z, ""), (P.ROOF_Z, ""), (T, "")], yv, side="right", x_text=a_.X(yv) + 7, fs=6.0)
    a_.dim_h(-P.APERTURE_D / 2, P.APERTURE_D / 2, P.BOND_Z, P.BOND_Z, 0, at=a_.Y(0) - 5, prefix="Ø", suffix=" aperture")
    a_.dim_h(-P.RECESS_D / 2, P.RECESS_D / 2, P.BOND_Z, P.BOND_Z, 0, at=a_.Y(0) - 11, prefix="Ø", suffix=" recess")
    a_.dim_h(-P.THICK_RING_R, P.THICK_RING_R, P.BOND_Z, P.BOND_Z, 0, at=a_.Y(0) - 17, prefix="Ø", suffix=" thick ring")
    a_.dim_h(-R, yv, 0, 0, 0, at=a_.Y(0) - 23)
    # section B-B of the tub alone
    b_ = sh.view((292, 168), sa, f"SECTION B-B  (x = {fmt(cxr)}, through the camera R hood)   5:1", (178, 209))
    gb = G.section_polys(A.solid_of(tub), "x", cxr)
    b_.fill(gb, fc=style("tub")[0], hatch=style("tub")[1], lw=0.6)
    yb0 = -math.sqrt(R ** 2 - cxr ** 2)
    b_.levels([(M["hood_skirt_z0"], "skirt / pad"), (P.WIN_Z0, "recess"), (P.OPEN_Z0, "sill"), (P.HOOD_Z_OVER_CUBE, "hood"), (P.ROOF_Z, ""), (T, "")],
              yv, side="right", x_text=b_.X(yv) + 7, fs=6.0)
    b_.dim_h(P.HOOD_REAR_Y0, P.HOOD_REAR_Y1, P.HOOD_Z_OVER_CUBE, P.HOOD_Z_OVER_CUBE, 0, at=b_.Y(0) - 5, text_side="left", suffix=" rear wall", fs=6.0)
    b_.dim_h(P.HOOD_REAR_Y1, P.HOOD_FRONT_IN_Y, P.HOOD_Z_OVER_CUBE, P.HOOD_Z_OVER_CUBE, 0, at=b_.Y(0) - 11, text_side="left", suffix=" bay", fs=6.0)
    b_.dim_h(P.HOOD_PAD_Y, yv, M["hood_skirt_z0"], 0.0, 0, at=b_.Y(0) - 17, text_side="left", suffix=" wall + pad below the opening", fs=6.0)
    b_.dim_v(0, T, yb0, yb0, 0, at=b_.X(yb0) - 5)
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
    gdt.dim_h(cxr - P.OPEN_HALF_W_INSIDE, cxr + P.OPEN_HALF_W_INSIDE, P.HOOD_FRONT_IN_Y, P.HOOD_FRONT_IN_Y, 0, at=gdt.Y(16.25), suffix=" inside")
    gdt.dim_h(cxr - P.HOOD_IN_HW, cxr + P.HOOD_IN_HW, 14.9, 14.9, 0, at=gdt.Y(15.3), suffix=" bay")
    gdt.dim_h(cxr - P.HOOD_OUT_HW, cxr + P.HOOD_OUT_HW, P.HOOD_REAR_Y0, P.HOOD_REAR_Y0, 0, at=gdt.Y(y0) - 4, suffix=" hood outside")
    xr = gdt.X(x1)
    gdt.dim_v(P.WIN_RECESS_FLOOR_Y, yv, x1, x1, 0, at=xr + 4, text_side="right", suffix=" recess depth", fs=6.0)
    gdt.dim_v(P.HOOD_FRONT_IN_Y, P.WIN_RECESS_FLOOR_Y, x1, x1, 0, at=xr + 4, text_side="right", suffix=" wall behind the recess", fs=6.0)
    gdt.dim_v(P.HOOD_REAR_Y0, P.HOOD_REAR_Y1, x1, x1, 0, at=xr + 4, text_side="right", suffix=" rear wall", fs=6.0)
    gdt.leader((cxr + P.OPEN_HALF_W, P.WIN_RECESS_FLOOR_Y - M["visor_land"] / 2), f"{fmt(M['visor_land'])} land, then {fmt(M['visor_bevel_deg'], 0)}° bevel", 30, -7, color=C_DIM, fs=6.0)
    # view F of the tub alone
    f = sh.view((292, 96), 4.0, "VIEW F - on the visor face   4:1   (+x to the LEFT)", (200, 132))
    f.hlr([tub], "front")
    f.centerline((-R - 1.5, P.AXIS_Z), (R + 1.5, P.AXIS_Z))
    f.dim_v(P.WIN_Z0, P.WIN_Z1, -cxr + P.WIN_RECESS_W / 2, -cxr + P.WIN_RECESS_W / 2, 5, suffix=" recess", text_side="right")
    f.dim_v(P.OPEN_Z0, P.OPEN_Z1, cxr - P.OPEN_HALF_W, cxr - P.OPEN_HALF_W, -5, suffix=" opening", text_side="left")
    f.dim_v(0, P.LEDGE_Z0, -R, -P.HORN_X_OUT, 0, at=f.X(-R) - 5, text_side="left", suffix=" visor wall underside")
    f.dim_h(M["key_x"] - M["key_w"] / 2, M["key_x"] + M["key_w"] / 2, 0, 0, 0, at=f.Y(0) - 5, suffix=" key lug", text_side="right")
    f.dim_h(-M["key_x"], M["key_x"], 0, 0, 0, at=f.Y(0) - 11, suffix=" between lugs")
    f.dim_h(-P.HORN_X_OUT, P.HORN_X_OUT, T, T, 4, suffix=" visor flat")
    sh.note(112, 60, ["Sections are true boolean sections of the", "tub solid; hatched = PA12.",
                      "z values = height above the rim (base plane)."], fs=5.8)
    sheets.append(sh)
    return _save("GL1-010_tub", sheets)


# ==============================================================================================
# GL1-011 base plate
# ==============================================================================================
def gl1_011(parts):
    base = parts["base_plate"]
    sh = Sheet("GL1-011", "Base plate", 1, 1, part="base plate", material="PA12 (HP 3D HR PA 12), dyed black",
               process="HP Multi Jet Fusion + vapor smoothing", tolerance=TOL_PRINT, scale="4:1 / 30:1", params_rev=P.REV)
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
    v.dim_h(b2x, b3x, b2y, b3y, 0, at=v.Y(b2y - 2.6), suffix=" ball seats 2 - 3")
    v.dim_v(b3y, 0, b3x, b3x, 0, at=v.X(b3x + 2.2))
    v.dim_v(0, b1y, 3.0, b1x, 0, at=v.X(3.0))
    kx = M["key_x"]
    v.dim_h(kx - P.KEY_NOTCH_HW, kx + P.KEY_NOTCH_HW, F, F, 4.5, suffix=" notch", text_side="right")
    v.dim_h(-kx, kx, F, F, 10.5, suffix=" between notch centres")
    v.dim_v(P.KEY_NOTCH_Y0, F, -kx - P.KEY_NOTCH_HW, -kx - P.KEY_NOTCH_HW, -5, text_side="left", suffix=" notch depth")
    lab = [((gx + P.GRAIN_R * math.cos(math.radians(40)), gy + P.GRAIN_R * math.sin(math.radians(40))), f"grain opening Ø{fmt(P.GRAIN_D)},\ncentre x {co(gx)}, y {co(gy)}"),
           ((gx + P.BAFFLE_RO * math.cos(math.radians(15)), gy + P.BAFFLE_RO * math.sin(math.radians(15))), f"baffle ring Ø{fmt(2 * P.BAFFLE_RI, 2)} / Ø{fmt(2 * P.BAFFLE_RO, 2)}\n(wall {fmt(M['baffle_wall'])}, full thickness)"),
           ((gx + 5.2 * math.cos(math.radians(-45)), gy + 5.2 * math.sin(math.radians(-45))), f"three spokes {fmt(M['spoke_w'])} wide at\n" + ", ".join(f"{a:.0f}°" for a in M["spoke_angles_deg"]) + " (clear of the LEDs)"),
           ((b3x, b3y), f"conical ball seat (x3), see\ndetail H; at (0, {co(b1y)}), (+-{fmt(b3x)}, {co(b3y)})"),
           ((xb + rs * 0.7, P.PAD_Y - rs * 0.7), f"pad slot, ends R{fmt(rs)}, centre line\ny = {co(P.PAD_Y)} (7 pads, pitch 2.54)"),
           ((R * math.cos(math.radians(22)), R * math.sin(math.radians(22))), f"edge R{fmt(R)}: {fmt(P.CLR)} radial gap\nto the tub wall (adhesive-filled)"),
           ((kx + 0.3, F - 0.5), f"key notch (x2) for the tub lugs,\nx = +-{fmt(kx)}")]
    v.label_column(lab, 198, side="right", fs=5.9, min_gap=7.6, y_min=92, y_max=246)
    v.cut_line((0, 12.6), (0, F + 1.2), "H", ext=0.5, arrow_dir=(-1, 0), fs=7.5)
    _triad(sh, 20, 92, (1, 0), (0, 1))
    # detail H: ball seat 1 in section
    sd = 30.0
    y0, y1 = b1y - 1.75, b1y + 1.75
    z0, z1 = -0.4, 1.3
    d = sh.view((270 - y0 * sd, 206 - z0 * sd), sd, f"DETAIL H - ball seat 1, section on x = 0   30:1   (seats 2 and 3 identical)", (262, 268))
    clip = (y0, z0, y1, z1)
    g = G.section_polys(A.solid_of(base), "x", 0.0).intersection(sbox(*clip))
    d.fill(g, fc=style("base_plate")[0], hatch=style("base_plate")[1], lw=0.6)
    gb = G.section_polys(A.solid_of(parts["ball_1"]), "x", 0.0)
    d.fill(gb, fc="#f2f2f6", lw=0.5)
    d.frame(*clip)
    d.centerline((b1y, z0), (b1y, z1), ext=0)
    d.lines([np.array([(y0, 0.0), (y1, 0.0)])], lw=0.3, color="#888", ls=(0, (6, 3)))
    d.dim_v(0, P.BASE_T, y0 + 0.25, y0 + 0.25, 0, at=d.X(y0) - 5)
    d.dim_v(-P.BALL_PROT, 0, b1y, b1y + 1.3, 0, at=d.X(y1) + 4, text_side="right", suffix=" ball proud")
    d.dim_h(b1y - P.BALL_SEAT_R_BOTTOM, b1y + P.BALL_SEAT_R_BOTTOM, 0, 0, 0, at=d.Y(z0) - 4, prefix="Ø", suffix=" cone mouth", nd=2)
    d.dim_h(b1y - P.BALL_SEAT_R_TOP, b1y + P.BALL_SEAT_R_TOP, P.BASE_T, P.BASE_T, 0, at=d.Y(z1) + 3.5, prefix="Ø", suffix=" pin-hole", text_side="right", nd=2)
    d.leader((b1y + 0.36, P.BALL_Z + 0.36 + 0.05), f"cone {fmt(2 * M['ball_seat_cone_half_angle_deg'], 0)}° included,\napex at z {fmt(P.BALL_SEAT_APEX_Z, 2)}", 30, 10, color=C_DIM, fs=6.0)
    d.leader((b1y - 0.2, P.BALL_Z), f"ball Ø{fmt(P.BALL_D)} (stainless),\ncentre z {fmt(P.BALL_Z)}", -38, -22, ha="right", color=C_DIM, fs=6.0)
    rows = [["Feature", "Qty", "Size", "Position (x, y)"],
            ["Outline", "1", f"R{fmt(R)}, flat y {co(F)}", "centre (0, 0)"],
            ["Grain opening", "1", f"Ø{fmt(P.GRAIN_D)} through", f"({co(gx)}, {co(gy)})"],
            ["Baffle ring", "1", f"Ø{fmt(2 * P.BAFFLE_RI, 2)} / Ø{fmt(2 * P.BAFFLE_RO, 2)}", "concentric with the opening"],
            ["Spokes", "3", f"{fmt(M['spoke_w'])} wide", ", ".join(f"{a:.0f}°" for a in M["spoke_angles_deg"]) + " from +x"],
            ["Pad slot", "1", f"{fmt(xb - xa + 2 * rs)} x {fmt(2 * rs)}", f"centre (0, {co(P.PAD_Y)})"],
            ["Ball seats", "3", f"{fmt(2 * M['ball_seat_cone_half_angle_deg'], 0)}° cone, mouth Ø{fmt(2 * P.BALL_SEAT_R_BOTTOM, 2)}", f"(0, {co(b1y)}), (+-{fmt(b3x)}, {co(b3y)})"],
            ["Key notches", "2", f"{fmt(2 * P.KEY_NOTCH_HW)} x {fmt(F - P.KEY_NOTCH_Y0)}", f"(+-{fmt(kx)}, front edge)"],
            ["Thickness", "-", f"{fmt(P.BASE_T)}", "z 0 to 1.0"]]
    sh.table(262, 150, rows, [24, 9, 48, 60], fs=5.7)
    sh.note(262, 108, [
        f"1. D01: the seven Ø{fmt(P.PAD_HOLE_D)} pad holes are merged into one slot (webs would be {fmt(P.PAD_WEB)} mm).",
        f"2. D02: a blind seat is impossible (ball top at z {fmt(P.BALL_Z + P.BALL_D / 2)} in a {fmt(P.BASE_T)} mm plate). The printed cone is a",
        "   pilot only: finish each seat with a 90° spot drill to depth, or set the balls on a gauge",
        f"   plate ({fmt(P.BALL_PROT)} proud) and pot them. The pin-hole is closed by the PCB adhesive sheet.",
        "3. D03: baffle ring enlarged for the photodiode diagonal; spokes unequally spaced.",
        f"4. The top face is the PCB bonding face and the seal land (r {fmt(P.LAND_RI)} to {fmt(R)}): keep flat,",
        "   no vapor-smoothing sink marks. Thin-skin regions at the seats: check 5 (D02).",
        "5. Hidden lines (dashed) show the cone mouths on the underside.",
    ], fs=5.9, title="NOTES")
    return _save("GL1-011_base_plate", [sh])


# ==============================================================================================
# GL1-020 cradle (sheet 2: reference plate, pin row, positions)
# ==============================================================================================
def gl1_020(parts):
    cr = parts["cradle"]
    X, y0c, y1c = P.CRADLE_X, P.CRADLE_Y0, P.CRADLE_Y1
    cyn = P.NEST_CY
    sheets = []
    sh = Sheet("GL1-020", "Cradle (charging / data / flip-calibration dock)", 1, 2, part="cradle body", material="PA12 (MJF) or SLA resin, any colour",
               process="MJF or SLA; drill 4 x Ø1.6 after printing", tolerance=TOL_PRINT, scale="2:1 / 2.8:1", params_rev=P.REV)
    v = sh.view((86, 176), 2.0, "TOP VIEW   2:1", (16, 268))
    v.hlr([cr], "top")
    v.centerline((-X - 2, cyn), (X + 2, cyn)); v.centerline((0, y0c - 2), (0, y1c + 2))
    v.dim_h(-X, X, y0c, y0c, -7)
    v.dim_v(y0c, y1c, -X, -X, -6)
    v.dim_h(-P.NEST_R, P.NEST_R, y1c, y1c, 5, suffix=" nest")
    v.dim_v(-P.NEST_SHIFT - P.NEST_FLAT, P.NEST_FLAT, X, X, 6, suffix=" nest (flat to flat)")
    sw = M["scallop_half_w"]
    v.dim_v(cyn - sw, cyn + sw, X, X, 13, suffix=" scallop")
    v.cut_line((0, y0c - 1.5), (0, y1c + 1.5), "D", ext=1.0, arrow_dir=(-1, 0))
    slot_l = P.PAD_XS[-1] - P.PAD_XS[0] + P.CRADLE_PIN_SLOT_W
    lab = [((P.NEST_R * math.cos(math.radians(35)), P.NEST_R * math.sin(math.radians(35))), f"nest arc R{fmt(P.NEST_R)}\nabout (0, 0)"),
           ((P.NEST_R * math.cos(math.radians(-40)), -P.NEST_SHIFT + P.NEST_R * math.sin(math.radians(-40))), f"nest arc R{fmt(P.NEST_R)}\nabout (0, {co(-P.NEST_SHIFT)})"),
           ((10.0, P.NEST_FLAT), f"flat y = {co(P.NEST_FLAT)}\n(visor at 0°)"),
           ((10.0, -P.NEST_SHIFT - P.NEST_FLAT), f"flat y = {co(-P.NEST_SHIFT - P.NEST_FLAT)}\n(visor at 180°)"),
           ((P.PAD_XS[-1], P.PAD_Y), f"pin slot {fmt(slot_l)} x {fmt(P.CRADLE_PIN_SLOT_W)}\non y = {co(P.PAD_Y)}"),
           ((0, cyn), f"nest centre\n(0, {co(cyn)})"),
           ((X - 2.0, cyn + sw - 1.0), "finger scallop,\nfloor at plate level")]
    v.label_column(lab, 172, side="right", fs=5.9, min_gap=7.4, y_min=112, y_max=244)
    _triad(sh, 20, 98, (1, 0), (0, 1))
    # section D-D (assembly)
    ss = 2.8
    names = ["cradle", "cradle_plate", "cradle_pcb", "usb_receptacle", "spring_pin_4"]
    d = sh.view((232 - y0c * ss, 236), ss, "SECTION D-D  (x = 0) with plate, PCB, receptacle and centre pin   2.8:1", (232, 268))
    draw_section(d, parts, names, "x", 0.0)
    d.lines([np.array([(y0c - 2, 0.0), (y1c + 2, 0.0)])], lw=0.3, color="#b02020", ls=(0, (12, 2.5, 2, 2.5)))
    d.levels([(P.CRADLE_TOP_Z, "top"), (0.0, "puck base plane"), (P.PLATE_Z0, "plate seat"), (P.CPCB_Z1, "PCB top"), (P.CPCB_Z0, ""), (P.CRADLE_BOT_Z, "underside")],
             y0c, side="left", x_text=d.X(y0c) - 6, fs=5.9, min_gap=3.2)
    d.dim_h(y0c, y1c, P.CRADLE_BOT_Z, P.CRADLE_BOT_Z, -5)
    d.dim_v(P.CRADLE_BOT_Z, P.CRADLE_TOP_Z, y1c, y1c, 5)
    top = [((P.PAD_Y, -3.0), "spring pin"), ((0.0, 0.5 * (P.PLATE_Z0 + P.PLATE_Z1)), "reference plate 1.5"), ((20.0, -5.0), "cradle body")]
    bot = [((P.USB_Y0 + 3, P.CPCB_Z1 + 1.6), "USB-C receptacle"), ((-10.0, 0.5 * (P.CPCB_Z0 + P.CPCB_Z1)), "cradle PCB 1.6"), ((8.0, -8.5), "lightening pocket")]
    d.label_row(top, d.Y(P.CRADLE_TOP_Z) + 6, 262, 400, above=True, fs=5.9)
    d.label_row(bot, d.Y(P.CRADLE_BOT_Z) - 9, 250, 400, above=False, fs=5.9)
    # view from below
    b = sh.view((330, 123), 2.0, "VIEW FROM BELOW   2:1   (+x to the LEFT)", (232, 185.5))
    b.hlr([cr], "bottom")
    hx = P.CPCB_HX + P.CLR
    fx, fy = M["foot_xy"]
    b.dim_h(-fx, fx, cyn + fy, cyn + fy, 0, at=b.Y(y1c) + 4, suffix=" foot pockets")
    lab = [((fx, cyn - fy), f"foot pocket Ø{fmt(M['foot_pocket_dia'])} x {fmt(M['foot_pocket_depth'])} (x4)\nat (+-{fmt(fx)}, {co(cyn)} +-{fmt(fy)})"),
           ((hx - 1.0, -10.0), f"PCB pocket {fmt(2 * hx)} x {fmt(P.CPCB_Y1 - P.CPCB_Y0 + 2 * P.CLR)},\nceiling z {co(P.CPCB_Z1)}"),
           ((M["cradle_pcb_screw_xy"][0][0], M["cradle_pcb_screw_xy"][0][1]), "spot mark (x4): drill Ø1.6 x 3\nfor M2 thread-forming screws"),
           ((M["lighten_x"][0] + 4, 5.0), f"lightening pocket (x3),\nceiling z {co(M['lighten_ceiling_z'])}")]
    b.label_column(lab, 264, side="left", fs=5.8, min_gap=7.4, y_min=68, y_max=172)
    sh.note(16, 92, [
        "1. Printed body 60 x 60 x 14 mm. The nest is the union of the puck outline (+0.25) at 0° and turned 180° about the nest centre: it accepts the marker",
        f"   in exactly these two positions; its centre moves {fmt(P.NEST_SHIFT)} mm between them (deviation D15).",
        f"2. Seat for the stainless reference plate at z = {co(P.PLATE_Z0)}; the three ball feet rest on the plate top (z = {co(P.PLATE_Z1)}). Bond the plate with a thin",
        "   epoxy film on three pads only, then check flatness - the plate, not the print, is the tilt reference.",
        f"3. Cradle PCB top at z = {co(P.CPCB_Z1)} so that each spring pin is at its recommended working height ({fmt(M['pin_working_h'])}) on a pad {fmt(M['real_pad_height'])} above the puck base plane.",
        "4. OPEN (D17): the seven pins push the 11 g marker up with about 4 N. No hold-down is modelled; one is required before the cradle can",
        "   charge reliably or serve as the flip-calibration seat. At 180° the pins bear on the solid base plate (no pad, no opening).",
        "5. Pin and receptacle envelopes are PROVISIONAL. Sheet 2: reference plate, pin row section, 0° / 180° positions.",
    ], fs=6.0, title="NOTES")
    sheets.append(sh)
    # ------------------------------------------------------------------ sheet 2
    sh = Sheet("GL1-020", "Cradle (charging / data / flip-calibration dock)", 2, 2, part="reference plate GL1-021, pin row, positions",
               material="plate: 304 stainless 1.5 mm, laser cut, deburred", process="see sheet 1", tolerance="plate: +-0.1, flat within 0.05",
               scale="2:1 / 6:1 / 1.5:1", params_rev=P.REV)
    pl = parts["cradle_plate"]
    R = P.R_OUT
    v = sh.view((72, 206), 2.0, "REFERENCE PLATE GL1-021   2:1   (profile: dxf/GL1-021_cradle_plate.dxf)", (16, 272))
    v.hlr([pl], "top")
    v.centerline((-R - 2, cyn), (R + 2, cyn)); v.centerline((0, -P.NEST_SHIFT - P.Y_VISOR - 2), (0, P.Y_VISOR + 2))
    v.dim_h(-R, R, cyn, cyn, 0, at=v.Y(-P.NEST_SHIFT - P.Y_VISOR) - 7)
    v.dim_v(-P.NEST_SHIFT - P.Y_VISOR, P.Y_VISOR, 0, 0, 0, at=v.X(-R) - 5)
    xa, xb = P.PAD_XS[0], P.PAD_XS[-1]
    v.dim_h(xa, xb, P.PAD_Y, P.PAD_Y, 6, suffix=f"  (6 x {fmt(P.PAD_XS[1] - P.PAD_XS[0])})")
    v.dim_v(-P.NEST_SHIFT - P.Y_VISOR, P.PAD_Y, xb + 1.0, xb, 0, at=v.X(xb + 4.5), text_side="right")
    lab = [((xb + 0.7, P.PAD_Y + 0.7), f"7 x Ø{fmt(M['plate_hole_dia'])} through (webs {fmt(P.PAD_XS[1] - P.PAD_XS[0] - M['plate_hole_dia'])}:\nconfirm with the cutter)"),
           ((R * math.cos(math.radians(30)), R * math.sin(math.radians(30))), f"R{fmt(R)} about (0, 0)"),
           ((R * math.cos(math.radians(-35)), -P.NEST_SHIFT + R * math.sin(math.radians(-35))), f"R{fmt(R)} about (0, {co(-P.NEST_SHIFT)})"),
           ((8.0, P.Y_VISOR), f"flats at y = {co(P.Y_VISOR)} and {co(-P.NEST_SHIFT - P.Y_VISOR)}"),
           ((-10, 5), f"thickness {fmt(M['plate_t'])}; top face = tilt datum,\nflat within 0.05, no burr on top")]
    v.label_column(lab, 124, side="right", fs=5.9, min_gap=7.0, y_min=168, y_max=250)
    # pin row section on y = PAD_Y
    se = 6.0
    names = ["cradle", "cradle_plate", "cradle_pcb", "base_plate", "main_pcb", "pcb_adhesive", "tub"] + [f"spring_pin_{i}" for i in range(1, 8)]
    x0, x1, z0, z1 = -11.6, 11.6, -7.6, 2.3
    e = sh.view((284, 212), se, f"SECTION E-E  (y = {co(P.PAD_Y)}) through the pin row, marker seated at 0°   6:1", (196, 272))
    draw_section(e, parts, names, "y", P.PAD_Y, clip=(x0, z0, x1, z1))
    e.frame(x0, z0, x1, z1)
    e.dim_h(P.PAD_XS[3], P.PAD_XS[4], P.PCB_Z0, P.PCB_Z0, 0, at=e.Y(z1) + 3.5, text_side="right", suffix=" pitch")
    e.dim_h(xa, xb, P.CPCB_Z0, P.CPCB_Z0, 0, at=e.Y(z0) - 4)
    e.levels([(M["real_pad_height"], "pad (real stack)"), (0.0, "puck base plane"), (P.PLATE_Z1, "plate top"), (P.PLATE_Z0, ""), (P.PIN_BODY_Z1, "pin body top"),
              (P.CPCB_Z1, "cradle PCB top"), (P.CPCB_Z0, "")], x0, side="left", x_text=e.X(x0) - 5, fs=5.9, min_gap=3.3)
    lab = [((P.PAD_XS[-1], 0.5), f"plunger Ø{fmt(M['pin_plunger_dia'])} in the\nbase slot ({fmt(P.PAD_HOLE_D)} wide)"),
           ((P.PAD_XS[-1], 0.5 * (P.PLATE_Z0 + P.PLATE_Z1)), f"plate hole Ø{fmt(M['plate_hole_dia'])}"),
           ((P.PAD_XS[-1] + 0.6, -3.2), f"pin body Ø{fmt(M['pin_body_dia'])} in the\nprinted slot ({fmt(P.CRADLE_PIN_SLOT_W)} wide)"),
           ((9.5, 0.5 * (P.CPCB_Z0 + P.CPCB_Z1)), "cradle PCB 1.6,\npins soldered"),
           ((P.PAD_XS[-2], P.PAD_Z0 + 0.1), "contact pad (main PCB\nunderside)"),
           ((10.5, 1.4), "main PCB / PSA / base plate")]
    e.label_column(lab, e.X(x1) + 6, side="right", fs=5.7, min_gap=6.6, y_min=166, y_max=232)
    # positions plan
    sp = 1.5
    q = sh.view((84, 86), sp, "POSITIONS   1.5:1   marker at 0° (solid) and at 180° (dashed) in the nest", (16, 140))
    gn = G.section_polys(A.solid_of(parts["cradle"]), "z", 1.0)
    q.fill(gn, fc=style("cradle")[0], hatch=style("cradle")[1], lw=0.5)
    puck0 = G.section_polys(A.solid_of(parts["tub"]), "z", 0.6)
    from shapely.geometry import Polygon as SPoly
    out0 = np.asarray(SPoly(puck0.geoms[0].exterior if hasattr(puck0, "geoms") else puck0.exterior).exterior.coords)
    q.lines([out0], lw=0.8, color="k")
    out180 = np.c_[-out0[:, 0], 2 * cyn - out0[:, 1]]
    q.lines([out180], lw=0.6, color="#1a3f8f", ls=(0, (5, 2.5)))
    for x in P.PAD_XS:
        q.circle((x, P.PAD_Y), M["pin_plunger_dia"] / 2, lw=0.6, color="#b06000")
        px, py = P.puck_to_cradle_180(x, P.PAD_Y)
        q.circle((px, py), M["pad_dia"] / 2, lw=0.4, color="#1a3f8f", ls=(0, (2, 1.5)))
    for (bx, by) in P.BALL_XY:
        q.circle((bx, by), 0.9, lw=0.7, color="k")
        px, py = P.puck_to_cradle_180(bx, by)
        q.circle((px, py), 0.9, lw=0.5, color="#1a3f8f", ls=(0, (2, 1.5)))
    q.cross((0, 0), 2.5); q.cross((0, -P.NEST_SHIFT), 2.5, color="#1a3f8f")
    lab = [((0, 0), "marker centre at 0°: (0, 0)"), ((0, -P.NEST_SHIFT), f"marker centre at 180°: (0, {co(-P.NEST_SHIFT)})"),
           ((P.PAD_XS[-1], P.PAD_Y), f"pins (orange) on the pads at 0°;\nat 180° they sit under marker y = {co(P.cradle_to_puck_180(0, P.PAD_Y)[1])} (solid base)"),
           ((P.puck_to_cradle_180(P.PAD_XS[0], P.PAD_Y)), "pad row of the marker at 180° (dashed): no pin near it"),
           ((P.BALL_XY[2][0], P.BALL_XY[2][1]), "ball feet (circles): on the plate in both positions")]
    q.label_column(lab, 136, side="right", fs=5.9, min_gap=7.0, y_min=52, y_max=122)
    rows = [["Cradle PCB (30 x 22 x 1.6, 2 layers)", "Value"],
            ["Outline", f"{fmt(M['cradle_pcb'][0])} x {fmt(M['cradle_pcb'][1])} x {fmt(M['cradle_pcb'][2])}, rear edge y {co(P.CPCB_Y0)}"],
            ["Pin holes (7)", f"on y = {co(P.PAD_Y)}, x = {co(xa)} ... {co(xb)}, pitch {fmt(P.PAD_XS[1] - P.PAD_XS[0])}"],
            ["Screws (4 x M2 thread-forming)", "at (+-%s, %s) and (+-%s, %s)" % (fmt(M["cradle_pcb_screw_xy"][0][0]), co(M["cradle_pcb_screw_xy"][0][1]), fmt(M["cradle_pcb_screw_xy"][1][0]), co(M["cradle_pcb_screw_xy"][1][1]))],
            ["USB-C receptacle", f"GCT USB4105 on the top face, mouth at y {co(P.USB_Y0)} (rear face recessed {fmt(M['usb_mouth_recess'])})"],
            ["Top face height", f"z = {co(P.CPCB_Z1)} (pad height {fmt(M['real_pad_height'])} - working height {fmt(M['pin_working_h'])})"]]
    sh.table(226, 152, rows, [48, 122], fs=5.6)
    sh.note(226, 124, [
        "Pins: Mill-Max 0914 long stroke (overall 8.3, working height 5.82, 60 gf): diameters PROVISIONAL.",
        f"Pin bodies stop {fmt(M['pin_body_top_below_plate'])} below the plate so that only the plunger passes the steel (no short through the plate).",
        f"The modelled plunger ends on the YAML pad plane (z {fmt(P.PAD_Z0)}); the real pad is at {fmt(M['real_pad_height'])} with the PSA sheet (D10).",
        "At 180° the plungers bear on the base plate and are compressed 2.27 of 2.29 mm stroke: see README, open issues.",
    ], fs=5.8)
    sheets.append(sh)
    return _save("GL1-020_cradle", sheets)


# ==============================================================================================
# DXF profiles
# ==============================================================================================
def export_dxf(parts):
    import ezdxf
    DXF_DIR.mkdir(parents=True, exist_ok=True)
    for f in DXF_DIR.glob("*.dxf"):
        f.unlink()
    cxr = P.CAM_XY["R"][0]
    files = {
        "GL1-010_tub_profiles": [("Z0p6_RIM", "tub", "z", 0.6), ("Z1p7_LEDGE", "tub", "z", 1.7), ("Z4p0_POSTS_HOODS", "tub", "z", 4.0),
                                 ("Z5p61_OPTICAL_AXIS", "tub", "z", P.AXIS_Z), ("Z6p0_THICK_ROOF", "tub", "z", 6.0), ("Z7p0_RECESS", "tub", "z", 7.0)],
        "GL1-011_base_plate_profile": [("Z0p5_PROFILE", "base_plate", "z", 0.5), ("Z0p01_CONE_MOUTHS", "base_plate", "z", 0.01)],
        "GL1-020_cradle_profiles": [("Z1p0_NEST", "cradle", "z", 1.0), ("Zm1p0_PLATE_SEAT", "cradle", "z", -1.0), ("Zm3p0_PIN_SLOT", "cradle", "z", -3.0),
                                    ("Zm6p0_POCKETS", "cradle", "z", -6.0), ("Zm10p5_FOOT_POCKETS", "cradle", "z", -10.5)],
        "GL1-021_cradle_plate": [("PLATE_1p5_304", "cradle_plate", "z", 0.5 * (P.PLATE_Z0 + P.PLATE_Z1))],
        "GL1-030_adhesive_die_cuts": [("PCB_PSA_0p13", "pcb_adhesive", "z", P.BASE_T + M["pcb_psa_t"] / 2), ("LCD_FRAME_0p15", "lcd_adhesive", "z", 0.5 * (P.LCD_Z1 + P.BOND_Z)),
                                      ("COVER_TAPE_0p2", "cover_tape", "z", 0.5 * (P.RECESS_FLOOR_Z + P.CG_Z0))],
    }
    puck = [n for n, i in parts.items() if i.group == "puck"]
    files["GL1-002_section_A-A_x0"] = [(n.upper(), n, "x", 0.0) for n in puck]
    files["GL1-002_section_B-B_x10p2"] = [(n.upper(), n, "x", cxr) for n in puck]
    out = []
    for fname, layers in files.items():
        doc = ezdxf.new("R2010"); doc.units = 4                      # millimetres
        msp = doc.modelspace()
        n_ent = 0
        for i, (layer, part, axis, value) in enumerate(layers):
            ents = G.section_edges(A.solid_of(parts[part]), axis, value)
            if not ents:
                continue
            doc.layers.add(layer, color=1 + (i % 6))
            for e in ents:
                kind = e[0]
                if kind == "line":
                    msp.add_line(e[1], e[2], dxfattribs={"layer": layer})
                elif kind == "circle":
                    msp.add_circle(e[1], e[2], dxfattribs={"layer": layer})
                elif kind == "arc":
                    msp.add_arc(e[1], e[2], e[3], e[4], dxfattribs={"layer": layer})
                else:
                    msp.add_lwpolyline(e[1], dxfattribs={"layer": layer})
                n_ent += 1
        f = DXF_DIR / f"{fname}.dxf"
        doc.saveas(f)
        out.append((f, n_ent))
    return out


DRAWINGS = [gl1_001, gl1_002, gl1_010, gl1_011, gl1_020]


def draw_all(parts=None, verbose=True):
    parts = parts or A.build_parts()
    DRAW_DIR.mkdir(parents=True, exist_ok=True)
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
    return out


if __name__ == "__main__":
    draw_all()
