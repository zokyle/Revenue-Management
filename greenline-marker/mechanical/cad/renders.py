#!/usr/bin/env python3
"""GL-1 renders: PNG images of the exported STL meshes (headless Chromium + three.js, tools/render/render.js).

    python3 cad/renders.py            # needs export/stl/parts/*.stl (written by cad/build.py)

Writes renders/GL1_render_a_front_top.png ... _f_cradle_section.png.  The cut-away views are true boolean cuts of the
solids (cut faces are drawn in a lighter tint of the part colour).
"""
from __future__ import annotations
import json, math, pathlib, shutil, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np
import params as P
import parts as PT
import assembly as A

RENDER_DIR = P.MECH_DIR / "renders"
RENDER_JS = P.MECH_DIR / "tools" / "render" / "render.js"
M = P.MECH

COLORS = {            # r, g, b, opacity (render colours; black PA12 is drawn dark grey so that its shape reads)
    "tub": (0.17, 0.18, 0.21, 1), "base_plate": (0.30, 0.32, 0.38, 1), "main_pcb": (0.10, 0.46, 0.24, 1),
    "pcb_adhesive": (0.95, 0.84, 0.36, 1), "seal_bead": (0.96, 0.50, 0.12, 1), "lcd_glass": (0.70, 0.78, 0.70, 1),
    "lcd_flex": (0.88, 0.55, 0.10, 1), "lcd_adhesive": (0.96, 0.86, 0.40, 1), "cover_glass": (0.72, 0.88, 0.98, 0.32),
    "cover_tape": (0.10, 0.10, 0.11, 1), "battery": (0.76, 0.77, 0.81, 1), "foam_pad": (0.42, 0.34, 0.50, 1),
    "vent": (0.97, 0.97, 0.97, 1), "cradle": (0.56, 0.60, 0.67, 1), "cradle_plate": (0.80, 0.82, 0.85, 1),
    "cradle_pcb": (0.06, 0.36, 0.52, 1), "usb_receptacle": (0.82, 0.82, 0.84, 1),
}
PREFIX_COLORS = {"camera_": (0.33, 0.33, 0.40, 1), "prism_": (0.50, 0.78, 0.96, 0.62), "visor_window_": (0.62, 0.86, 0.96, 0.42),
                 "ball_": (0.88, 0.89, 0.92, 1), "spring_pin_": (0.86, 0.70, 0.22, 1), "cradle_foot_": (0.08, 0.08, 0.09, 1)}
LIGHT_EDGES = ("tub", "base_plate", "cover_tape", "cradle_foot_", "camera_", "foam_pad")
CAP_COLORS = {"tub": (0.80, 0.80, 0.83), "base_plate": (0.58, 0.65, 0.80), "cradle": (0.74, 0.77, 0.83), "main_pcb": (0.45, 0.78, 0.52),
              "battery": (0.90, 0.90, 0.93), "cradle_plate": (0.93, 0.94, 0.96)}
NAMES = {            # label text per part
    "tub": "Tub (top shell), MJF PA12", "base_plate": "Base plate, MJF PA12", "main_pcb": "Main PCB assembly (0.8 mm)",
    "pcb_adhesive": "PSA sheet PCB-to-base (0.13 mm)", "seal_bead": "Perimeter seal bead (dispensed adhesive)",
    "lcd_glass": "Memory LCD LS013B7DH03", "lcd_flex": "LCD flex tail (representative)", "lcd_adhesive": "LCD adhesive frame (0.15 mm)",
    "cover_glass": "Cover glass dia 28 x 1.0", "cover_tape": "VHB 5907 tape ring (0.2 mm)", "battery": "LiPo cell GM201030-PCB",
    "foam_pad": "Foam pad (0.3 mm)", "vent": "ePTFE vent (Gore VE80205)", "cradle": "Cradle body (printed)",
    "cradle_plate": "Reference plate, 304 stainless 1.5 mm", "cradle_pcb": "Cradle PCB 30 x 22 x 1.6", "usb_receptacle": "USB-C receptacle (USB4105)",
}


def _color(name):
    if name in COLORS:
        return COLORS[name]
    for k, v in PREFIX_COLORS.items():
        if name.startswith(k):
            return v
    return (0.6, 0.6, 0.6, 1)


def _entry(name, stl, offset=None, **kw):
    r, g, b, a = _color(name)
    e = dict(stl=str(stl), color=[r, g, b], opacity=a)
    if any(name.startswith(k) for k in LIGHT_EDGES):
        e["edgeColor"] = [0.62, 0.64, 0.68]; e["edgeOpacity"] = 0.55
    if name.startswith(("ball_", "spring_pin_", "cradle_plate", "usb_")):
        e["metalness"] = 0.55; e["roughness"] = 0.35
    if name.startswith("ball_"):
        e["edges"] = False
    if offset:
        e["offset"] = list(offset)
    if name in CAP_COLORS:
        e["capColor"] = list(CAP_COLORS[name])
    e.update(kw)
    return e


def _bbox(parts, name):
    return np.array(A.bbox_of(parts[name]))


def _screen_right(eye, target, up=(0, 0, 1)):
    v = np.array(eye, float) - np.array(target, float); v /= np.linalg.norm(v)
    r = np.cross(np.array(up, float), v)
    return r / np.linalg.norm(r)


def _rim_anchor(parts, name, side, right, offset=(0, 0, 0), frac=0.82, z="mid"):
    """A point near the rim of a part on the screen side where its label goes."""
    b = _bbox(parts, name)
    c = 0.5 * (b[:3] + b[3:]); h = 0.5 * (b[3:] - b[:3])
    s = 1.0 if side == "R" else -1.0
    p = c + s * frac * np.array([right[0] * h[0], right[1] * h[1], 0.0])
    if z == "top":
        p[2] = b[5]
    return list(p + np.array(offset, float))


def _eye(direction, target, visible_width_mm, W, H, fov):
    """Eye position for a perspective camera so that `visible_width_mm` spans the image width at the target."""
    d = np.array(direction, float); d /= np.linalg.norm(d)
    dist = 0.5 * visible_width_mm * (H / W) / math.tan(math.radians(fov / 2))
    return [float(v) for v in (np.array(target, float) + dist * d)]


def _pcb_detail_stls(tmp):
    """Render-only solids for the bottom-side features of the main PCB (they are part of main_pcb.stl): pads, LEDs, photodiode."""
    out = {}
    pads = PT.union([PT.cyl(x, P.PAD_Y, M["pad_dia"] / 2, P.PAD_Z0 - 0.01, P.PCB_Z0) for x in P.PAD_XS])
    leds = PT.union([b.translate((0, 0, -0.01)) for b in PT.led_boxes()])
    pd = P.PD
    pdb = PT.box(pd["x"] - pd["dx"] / 2, pd["x"] + pd["dx"] / 2, pd["y"] - pd["dy"] / 2, pd["y"] + pd["dy"] / 2, P.PCB_Z0 - pd["h"] - 0.01, P.PCB_Z0)
    for n, wp, col in (("pads", pads, (0.90, 0.72, 0.20)), ("leds", leds, (0.95, 0.93, 0.80)), ("photodiode", pdb, (0.12, 0.12, 0.16))):
        f = pathlib.Path(tmp) / f"detail_{n}.stl"
        wp.val().exportStl(str(f), A.STL_TOL, A.STL_ANG)
        out[n] = dict(stl=str(f), color=list(col), opacity=1, front=True, metalness=0.5 if n == "pads" else 0.05, roughness=0.4)
    return out


def _run(cfg, tmp):
    f = pathlib.Path(tmp) / (pathlib.Path(cfg["out"]).stem + ".json")
    f.write_text(json.dumps(cfg))
    r = subprocess.run(["node", str(RENDER_JS), str(f)], capture_output=True, text=True)
    if r.returncode != 0 or not pathlib.Path(cfg["out"]).exists():
        raise RuntimeError(f"render failed for {cfg['out']}:\n{r.stdout}\n{r.stderr}")
    return r.stdout.strip()


def _cut_stls(parts, names, cutter, tmp, tag):
    """Boolean-cut the named parts with `cutter` and write STLs; returns {name: path} for parts that still exist."""
    out = {}
    for n in names:
        try:
            s = A.solid_of(parts[n]).cut(cutter)
            if sum(x.Volume() for x in s.Solids()) < 1e-4:
                continue
            f = pathlib.Path(tmp) / f"{tag}_{n}.stl"
            s.exportStl(str(f), A.STL_TOL, A.STL_ANG)
            out[n] = f
        except Exception as e:
            print(f"  cut failed for {n}: {e}")
    return out


FOOT = f"GreenLine GL-1  |  parameters rev {P.REV}  |  PROVISIONAL - not released  |  rendered from the exported STL meshes"


def render_all(parts=None, verbose=True):
    parts = parts or A.build_parts()
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    for f in RENDER_DIR.glob("GL1_render_*.png"):
        f.unlink()
    stl = {n: A.STL_PARTS_DIR / f"{n}.stl" for n in parts}
    missing = [n for n, f in stl.items() if not f.exists()]
    if missing:
        raise RuntimeError(f"STL files missing (run cad/build.py first): {missing[:5]}")
    puck = [n for n, i in parts.items() if i.group == "puck"]
    cradle = [n for n, i in parts.items() if i.group == "cradle"]
    outs = []
    tmp = tempfile.mkdtemp(prefix="gl1_render_")
    try:
        W, H = 2000, 1500
        detail = _pcb_detail_stls(tmp)
        cxl, cxr = P.CAM_XY["L"][0], P.CAM_XY["R"][0]
        # ---------------- (a) assembled marker, front-top
        tgt, fov = (0, 0.5, 3.0), 22
        eye = _eye((0.36, 0.80, 0.48), tgt, 88, W, H, fov)
        cfg = dict(out=str(RENDER_DIR / "GL1_render_a_front_top.png"), width=W, height=H, eye=eye, target=tgt, fov=fov,
                   title="GL-1 marker, assembled - front / top",
                   subtitle="flat visor face with the two camera windows toward the hole (+y); 46.0 mm across, 7.6 mm thick",
                   footer=FOOT, parts=[_entry(n, stl[n]) for n in puck],
                   labels=[dict(text="Visor window R", anchor=[cxr, P.Y_VISOR, 6.3], side="L"),
                           dict(text="Camera opening behind the window", anchor=[cxr, P.Y_VISOR, 5.3], side="L"),
                           dict(text="Tub: top edge R0.6", anchor=[21.6, 6.0, P.T - 0.15], side="L"),
                           dict(text="Vent hole dia 1.0", anchor=[M["vent_xy"][0], M["vent_xy"][1], P.T], side="L"),
                           dict(text="Base plate under the visor wall", anchor=[4.0, P.BASE_FLAT, 0.5], side="L"),
                           dict(text="Cover glass dia 28 x 1.0", anchor=[-9.5, -8.5, P.CG_Z1], side="R"),
                           dict(text="LCD behind the dia 22 aperture", anchor=[-4, 1, P.CG_Z1], side="R"),
                           dict(text="Nose index groove 1.0 x 0.3", anchor=[0, 16.3, P.T], side="R"),
                           dict(text="Visor window L", anchor=[cxl, P.Y_VISOR, 6.3], side="R"),
                           dict(text="Tub key lug in a base notch", anchor=[-M["key_x"], P.Y_VISOR, 0.6], side="R")])
        outs.append(_run(cfg, tmp))
        # ---------------- (b) from below
        tgt = (0, 0, 1.5)
        eye = _eye((0.30, 0.62, -0.72), tgt, 90, W, H, fov)
        gx, gy = P.GRAIN_X, P.GRAIN_Y
        cfg = dict(out=str(RENDER_DIR / "GL1_render_b_underside.png"), width=W, height=H, eye=eye, target=tgt, fov=fov,
                   title="GL-1 marker - underside",
                   subtitle="grain-sensor opening with baffle ring, pad slot with the seven contact pads, three 1.0 mm ball feet (0.10 mm proud)",
                   footer=FOOT, parts=[_entry(n, stl[n]) for n in puck] + list(detail.values()),
                   labels=[dict(text="Ball foot 3", anchor=[P.BALL_XY[2][0], P.BALL_XY[2][1], -0.1], side="L"),
                           dict(text="Grain opening dia 13", anchor=[gx + 5.9, gy + 2.2, 0.0], side="L"),
                           dict(text="LED pairs on r 5.2 (PCB underside)", anchor=[gx + 5.2 * math.cos(math.radians(247.5)), gy + 5.2 * math.sin(math.radians(247.5)), 0.6], side="L"),
                           dict(text="Pad slot 17.44 x 2.2", anchor=[P.PAD_XS[-1] + 0.6, P.PAD_Y, 0.0], side="L"),
                           dict(text="Contact pads x7 (gold)", anchor=[P.PAD_XS[4], P.PAD_Y, 0.95], side="L"),
                           dict(text="Visor wall sits on the base", anchor=[-3.0, P.Y_VISOR, 2.6], side="R"),
                           dict(text="Key notch / tub lug", anchor=[-M["key_x"], P.BASE_FLAT - 0.3, 0.0], side="R"),
                           dict(text="Ball foot 1 (front)", anchor=[P.BALL_XY[0][0], P.BALL_XY[0][1], -0.1], side="R"),
                           dict(text="Photodiode inside the baffle ring", anchor=[gx - 1.0, gy, 0.55], side="R"),
                           dict(text="Baffle ring on three spokes", anchor=[gx - P.BAFFLE_RO + 0.35, gy - 0.5, 0.0], side="R"),
                           dict(text="Base plate, 0.25 radial gap", anchor=[-17.5, 3.0, 0.0], side="R"),
                           dict(text="Ball foot 2", anchor=[P.BALL_XY[1][0], P.BALL_XY[1][1], -0.1], side="R")])
        outs.append(_run(cfg, tmp))
        # ---------------- (c) exploded, every part separated along z
        dz = {"ball_": -34, "base_plate": -24, "seal_bead": -12, "pcb_adhesive": -2, "main_pcb": 10, "camera_": 21, "battery": 21, "prism_": 29,
              "foam_pad": 32, "lcd_flex": 38, "lcd_glass": 46, "lcd_adhesive": 58, "vent": 69, "tub": 74, "visor_window_": 74,
              "cover_tape": 95, "cover_glass": 106}

        def off(n):
            for k, v in dz.items():
                if n == k or (k.endswith("_") and n.startswith(k)):
                    return (0, 9.0 if n.startswith("visor_window_") else 0, v)
            return (0, 0, 0)
        eye_dir = np.array([0.62, 0.72, 0.30]); eye_dir /= np.linalg.norm(eye_dir)
        tgt = np.array([0.0, 0.0, 39.0]); eye = tgt + 500 * eye_dir
        r = _screen_right(eye, tgt)
        order = [("cover_glass", "R"), ("cover_tape", "L"), ("tub", "R"), ("visor_window_L", "R"), ("vent", "L"), ("lcd_adhesive", "L"),
                 ("lcd_glass", "R"), ("lcd_flex", "L"), ("foam_pad", "L"), ("prism_L", "R"), ("battery", "L"), ("camera_L", "R"), ("main_pcb", "L"),
                 ("pcb_adhesive", "R"), ("seal_bead", "L"), ("base_plate", "R"), ("ball_3", "L")]
        extra = {"visor_window_L": "Visor windows x2", "prism_L": "Fold prisms x2 (2 mm, N-BK7)",
                 "camera_L": "Camera cubes x2 (OVM7692)", "ball_3": "Ball feet x3 (dia 1.0)", "lcd_flex": "LCD flex tail (representative)",
                 "seal_bead": "Seal bead (dispensed)", "pcb_adhesive": "PSA sheet 0.13", "lcd_adhesive": "LCD adhesive frame 0.15",
                 "cover_tape": "VHB 5907 ring 0.2", "main_pcb": "Main PCB assembly", "tub": "Tub (top shell)", "base_plate": "Base plate",
                 "cover_glass": "Cover glass dia 28 x 1.0", "lcd_glass": "Memory LCD (glass 0.75)", "battery": "LiPo cell 34 x 10 x 2",
                 "foam_pad": "Foam pad 0.3", "vent": "ePTFE vent (inside the roof)"}
        labels = []
        for n, side in order:
            small = n.startswith(("visor_window_", "prism_", "camera_", "ball_", "vent", "lcd_flex"))
            a = _rim_anchor(parts, n, side, r, off(n), frac=0.0 if small else 0.88)
            labels.append(dict(text=extra.get(n, NAMES.get(n, n)), anchor=a, side=side))
        cfg = dict(out=str(RENDER_DIR / "GL1_render_c_exploded.png"), width=1800, height=2400, eye=list(eye), target=list(tgt), ortho=84,
                   title="GL-1 marker - exploded along z",
                   subtitle="every part of the marker, separated along z (windows also moved forward); assembly sequence in README.md",
                   footer=FOOT, labels=labels, labelTop=150, fontSize=30,
                   parts=[_entry(n, stl[n], off(n)) for n in puck] + [dict(v, offset=[0, 0, dz["main_pcb"]]) for v in detail.values()])
        outs.append(_run(cfg, tmp))
        # ---------------- (d) cut-away: x = 0 behind y_step, x = camera R in front of it
        ystep = P.LCD_Y1 - 0.5
        big = 200.0
        cutter = PT.box(cxr, big, ystep, big, -big, big).union(PT.box(0, big, -big, ystep, -big, big)).val()
        cut = _cut_stls(parts, puck, cutter, tmp, "cut")
        tgt, fovd = (2.0, -1.5, 3.2), 18
        eye = _eye((0.80, -0.42, 0.42), tgt, 76, W, H, fovd)
        labels = [dict(text="Roof 0.8", anchor=[0, -19.5, P.T - 0.4], side="L"),
                  dict(text="Cover glass 1.0", anchor=[0, -11.5, 0.5 * (P.CG_Z0 + P.CG_Z1)], side="L"),
                  dict(text="VHB tape ring 0.2", anchor=[0, -13.2, P.RECESS_FLOOR_Z + 0.1], side="L"),
                  dict(text="Roof ledge 0.8", anchor=[0, -12.2, 0.5 * (P.BOND_Z + P.RECESS_FLOOR_Z)], side="L"),
                  dict(text="LCD glass 0.75 under adhesive 0.15", anchor=[0, -15.0, 0.5 * (P.LCD_Z0 + P.LCD_Z1)], side="L"),
                  dict(text="Foam pad 0.3", anchor=[0, -9.6, P.FOAM_Z0 + 0.15], side="L"),
                  dict(text="Battery 2.0 (swell gap above)", anchor=[0, -8.6, 2.8], side="L"),
                  dict(text="FPC connector J1", anchor=[0, -14.0, 2.9], side="L"),
                  dict(text="PCB 0.8 on PSA sheet", anchor=[0, -20.3, 1.4], side="L"),
                  dict(text="Seal bead under the ledge", anchor=[0, -P.LAND_RI - 0.2, 1.1], side="L"),
                  dict(text="Base plate 1.0", anchor=[0, -19.3, 0.5], side="L"),
                  dict(text="Section step at y = %.1f" % ystep, anchor=[5.5, ystep, 7.0], side="R"),
                  dict(text="Visor window", anchor=[cxr, P.Y_VISOR - 0.25, 7.0], side="R"),
                  dict(text="Fold prism", anchor=[cxr, 16.1, 5.2], side="R"),
                  dict(text="Camera opening (sill z 4.6)", anchor=[cxr, P.WIN_RECESS_FLOOR_Y - 0.4, P.OPEN_Z0 - 0.3], side="R"),
                  dict(text="Camera cube 2.76", anchor=[cxr, 15.6, 3.2], side="R"),
                  dict(text="MCU (U1) under the LCD", anchor=[0, 7.2, 2.6], side="R"),
                  dict(text="Photodiode in the baffle ring", anchor=[0, P.GRAIN_Y + 0.3, 0.75], side="R"),
                  dict(text="Grain opening dia 13", anchor=[0, P.GRAIN_Y + P.GRAIN_R - 1.2, 0.3], side="R")]
        cfg = dict(out=str(RENDER_DIR / "GL1_render_d_cutaway.png"), width=W, height=H, eye=eye, target=tgt, fov=fovd,
                   title="GL-1 marker - cut-away",
                   subtitle=f"true boolean cut on x = 0 (centre stack) behind y = {ystep:.1f} and on x = {cxr} (through camera R) in front of it; cut faces in a lighter tint",
                   footer=FOOT, labels=labels, capPlanes=[dict(axis="x", value=0.0), dict(axis="x", value=cxr), dict(axis="y", value=ystep)],
                   parts=[_entry(n, f) for n, f in cut.items()])
        outs.append(_run(cfg, tmp))
        # ---------------- (e) marker in the cradle
        tgt, fove = (0, -2.5, -2.5), 20
        eye = _eye((0.52, -0.66, 0.54), tgt, 120, W, H, fove)
        cfg = dict(out=str(RENDER_DIR / "GL1_render_e_in_cradle.png"), width=W, height=H, eye=eye, target=tgt, fov=fove,
                   title="GL-1 marker in its cradle (0 deg: charging / data position)",
                   subtitle="seen from the rear right; the USB-C receptacle exits the rear face; no hold-down is modelled (open issue D17)",
                   footer=FOOT, parts=[_entry(n, stl[n]) for n in puck + cradle],
                   labels=[dict(text="Marker, visor toward +y", anchor=[-8, 6, P.T], side="L"),
                           dict(text="Nest wall (0 and 180 deg only)", anchor=[-16.5, -19.0, P.CRADLE_TOP_Z], side="L"),
                           dict(text="Cradle body 60 x 60 x 14", anchor=[-P.CRADLE_X + 8, P.CRADLE_Y0, -5.0], side="L"),
                           dict(text="USB-C receptacle", anchor=[0, P.CRADLE_Y0, P.CPCB_Z1 + 1.6], side="L"),
                           dict(text="Finger scallop (both sides)", anchor=[P.CRADLE_X - 3.0, P.NEST_CY + 2.0, 0.5], side="R"),
                           dict(text="Reference plate, 304 stainless", anchor=[24.5, P.NEST_CY - 5.5, P.PLATE_Z1], side="R"),
                           dict(text="Bumper feet x4 underneath", anchor=[M["foot_xy"][0] + 2.0, P.NEST_CY - M["foot_xy"][1] - 2.0, P.CRADLE_BOT_Z + 0.3], side="R")])
        outs.append(_run(cfg, tmp))
        # ---------------- (f) section through the pin row (x = 0), marker in the cradle
        cutter = PT.box(0, big, -big, big, -big, big).val()
        cut = _cut_stls(parts, puck + cradle, cutter, tmp, "cutc")
        tgt = (0, -2.5, -2.0)
        eye = _eye((0.86, -0.36, 0.30), tgt, 100, W, H, fove)
        cfg = dict(out=str(RENDER_DIR / "GL1_render_f_cradle_section.png"), width=W, height=H, eye=eye, target=tgt, fov=fove,
                   title="GL-1 marker in its cradle - section on x = 0",
                   subtitle="centre spring pin compressed onto its contact pad; ball feet on the reference plate; no hold-down is modelled (open issue D17)",
                   footer=FOOT, capPlanes=[dict(axis="x", value=0.0)], parts=[_entry(n, f) for n, f in cut.items()],
                   labels=[dict(text="USB-C receptacle", anchor=[0, P.USB_Y0 + 2.5, P.CPCB_Z1 + 1.6], side="L"),
                           dict(text="Pad slot in the base plate", anchor=[0, P.PAD_Y - 1.0, 0.5], side="L"),
                           dict(text="Spring pin on contact pad 4", anchor=[0, P.PAD_Y, -2.8], side="L"),
                           dict(text="Cradle PCB, top at z = %.2f" % P.CPCB_Z1, anchor=[0, -24.0, 0.5 * (P.CPCB_Z0 + P.CPCB_Z1)], side="L"),
                           dict(text="Marker (section A-A)", anchor=[0, 2.0, 5.0], side="R"),
                           dict(text="Front ball foot on the plate", anchor=[0, P.BALL_XY[0][1], -0.05], side="R"),
                           dict(text="Reference plate 1.5", anchor=[0, 9.0, 0.5 * (P.PLATE_Z0 + P.PLATE_Z1)], side="R"),
                           dict(text="Cradle body", anchor=[0, 23.0, -5.0], side="R"),
                           dict(text="Lightening pocket", anchor=[0, 8.0, -8.5], side="R")])
        outs.append(_run(cfg, tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if verbose:
        for o in outs:
            print("  rendered", o)
    return sorted(str(p) for p in RENDER_DIR.glob("GL1_render_*.png"))


if __name__ == "__main__":
    render_all()
