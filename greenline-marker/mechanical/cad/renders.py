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
    "tub": (0.17, 0.18, 0.21, 1), "base_plate": (0.20, 0.27, 0.24, 1), "main_pcb": (0.10, 0.46, 0.24, 1),
    "grain_potting": (0.70, 0.90, 0.96, 0.38), "baffle_ring": (0.07, 0.07, 0.08, 1), "baffle_adhesive": (0.26, 0.26, 0.29, 1),
    "pcb_adhesive": (0.95, 0.84, 0.36, 1), "seal_bead": (0.96, 0.50, 0.12, 1), "lcd_glass": (0.70, 0.78, 0.70, 1),
    "lcd_flex": (0.88, 0.55, 0.10, 1), "lcd_adhesive": (0.96, 0.86, 0.40, 1), "cover_glass": (0.72, 0.88, 0.98, 0.32),
    "cover_tape": (0.10, 0.10, 0.11, 1), "battery": (0.76, 0.77, 0.81, 1), "foam_pad": (0.42, 0.34, 0.50, 1),
    "vent": (0.97, 0.97, 0.97, 1), "cradle": (0.56, 0.60, 0.67, 1),
    "cradle_pcb": (0.06, 0.36, 0.52, 1), "usb_receptacle": (0.82, 0.82, 0.84, 1),
}
PREFIX_COLORS = {"ball_epoxy_": (0.40, 0.66, 0.90, 1), "camera_": (0.33, 0.33, 0.40, 1), "prism_": (0.50, 0.78, 0.96, 0.62), "visor_window_": (0.62, 0.86, 0.96, 0.42),
                 "window_bond_": (0.84, 0.80, 0.62, 1), "hood_seal_": (0.05, 0.05, 0.06, 1),
                 "ball_": (0.88, 0.89, 0.92, 1), "spring_pin_": (0.86, 0.70, 0.22, 1), "cradle_foot_": (0.08, 0.08, 0.09, 1),
                 "battery_lead_": (0.82, 0.50, 0.28, 1)}
LIGHT_EDGES = ("tub", "base_plate", "cradle_foot_", "camera_", "foam_pad", "hood_seal_", "baffle_ring")
CAP_COLORS = {"tub": (0.80, 0.80, 0.83), "base_plate": (0.60, 0.74, 0.60), "cradle": (0.74, 0.77, 0.83), "main_pcb": (0.45, 0.78, 0.52),
              "battery": (0.90, 0.90, 0.93), "grain_potting": (0.80, 0.93, 0.97), "baffle_ring": (0.30, 0.30, 0.33)}
NAMES = {            # label text per part
    "tub": "Tub (top shell), MJF PA12", "base_plate": "Base plate, routed FR-4 0.80", "main_pcb": "Main PCB assembly (0.8 mm)",
    "pcb_adhesive": "Adhesive sheet PCB-to-base (0.20 mm)", "seal_bead": "Perimeter seal (dispensed adhesive)",
    "lcd_glass": "Memory LCD LS013B7DH03", "lcd_flex": "LCD flex tail (representative)", "lcd_adhesive": "LCD adhesive frame (0.15 mm)",
    "cover_glass": "Cover glass dia 28 x 1.0", "cover_tape": "Transfer-tape ring 0.13 (dia 28 / 25)", "battery": "LiPo cell GM201030-PCB",
    "foam_pad": "Foam pad (0.3 mm)", "vent": "ePTFE vent (Gore VE80205)", "cradle": "Cradle body (printed)",
    "cradle_pcb": "Cradle PCB 30 x 22 x 1.6", "usb_receptacle": "USB-C receptacle (USB4105)",
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
    if name.startswith(("ball_", "spring_pin_", "usb_")) and not name.startswith("ball_epoxy_"):
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


def _picture_ok(path, cfg):
    """True when the PNG really shows the model: right size, background colour at the corners, and a reasonable share of
    non-background pixels in the middle of the frame (a blank WebGL frame is all background or all white)."""
    from PIL import Image
    im = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
    h, w = im.shape[:2]
    if (w, h) != (cfg.get("width", 1600), cfg.get("height", 1200)):
        return False, f"size {w} x {h}"
    bg = im[h - 8, w - 8]                                    # bottom-right corner: background, no text
    if int(np.abs(bg - np.array([238, 240, 243])).sum()) > 24 and "background" not in cfg:
        return False, f"corner colour {tuple(int(v) for v in bg)} is not the background"
    mid = im[h // 5: 4 * h // 5, w // 5: 4 * w // 5]
    frac = float((np.abs(mid - bg).sum(axis=2) > 24).mean())
    return frac >= 0.03, f"model share of the centre {100 * frac:.1f} %"


def _run(cfg, tmp, tries=3):
    f = pathlib.Path(tmp) / (pathlib.Path(cfg["out"]).stem + ".json")
    f.write_text(json.dumps(cfg))
    out, why = pathlib.Path(cfg["out"]), ""
    for k in range(tries):                                   # headless WebGL can lose its context: verify and retry
        if out.exists():
            out.unlink()
        r = subprocess.run(["node", str(RENDER_JS), str(f)], capture_output=True, text=True)
        if r.returncode == 0 and out.exists():
            ok, why = _picture_ok(out, cfg)
            if ok:
                return r.stdout.strip() + f" ({why})" + (f" after {k + 1} tries" if k else "")
        else:
            why = (r.stdout + r.stderr).strip()[-600:]
    raise RuntimeError(f"render failed for {cfg['out']} after {tries} tries: {why}")


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
        eye = _eye((0.36, 0.80, 0.48), tgt, 98, W, H, fov)
        cfg = dict(out=str(RENDER_DIR / "GL1_render_a_front_top.png"), width=W, height=H, eye=eye, target=tgt, fov=fov,
                   title="GL-1 marker, assembled - front / top",
                   subtitle="flat visor face with the two camera windows toward the hole (+y); 46.0 mm across, 7.6 mm thick",
                   footer=FOOT, parts=[_entry(n, stl[n]) for n in puck],
                   labels=[dict(text="Visor window R, 0.15 below the face", anchor=[cxr, P.WIN_Y1, 6.3], side="L"),
                           dict(text="Camera opening behind the window", anchor=[cxr, P.Y_VISOR, 5.3], side="L"),
                           dict(text="Tub: top edge R0.6", anchor=[21.6, 6.0, P.T - 0.15], side="L"),
                           dict(text="Vent hole + drain grooves", anchor=[P.VENT_XY[0] + 1.5, P.VENT_XY[1], P.T], side="L"),
                           dict(text="Base plate under the visor wall", anchor=[4.0, P.BASE_FLAT, 0.5], side="L"),
                           dict(text="Cover glass dia 28 x 1.0, 0.12 below flush", anchor=[-9.5, -8.5, P.CG_Z1], side="R"),
                           dict(text="LCD behind the dia 22 aperture", anchor=[-4, 1, P.CG_Z1], side="R"),
                           dict(text="Nose index groove 1.0 x 0.3", anchor=[0, 16.3, P.T], side="R"),
                           dict(text="Visor window L (0.40 borosilicate)", anchor=[cxl, P.WIN_Y1, 6.3], side="R"),
                           dict(text="Rim 0.25 above the base plane", anchor=[-P.R_OUT * math.cos(math.radians(40)), P.R_OUT * math.sin(math.radians(40)), P.RIM_Z], side="R")])
        outs.append(_run(cfg, tmp))
        # ---------------- (b) from below
        tgt = (0, 0, 1.5)
        eye = _eye((0.30, 0.62, -0.72), tgt, 86, W, H, fov)
        gx, gy = P.GRAIN_X, P.GRAIN_Y
        rp = 0.5 * (P.BAFFLE_RO + P.GRAIN_R)
        cfg = dict(out=str(RENDER_DIR / "GL1_render_b_underside.png"), width=W, height=H, eye=eye, target=tgt, fov=fov,
                   title="GL-1 marker - underside",
                   subtitle=f"FR-4 base plate; grain opening potted clear to {P.GRAIN_FILL_Z} inside; pad slot with seven pads; three potted ball feet {P.BALL_PROT:.2f} proud; tub rim {P.RIM_Z} higher",
                   footer=FOOT, parts=[_entry(n, stl[n]) for n in puck] + list(detail.values()),
                   labels=[dict(text="Ball foot 3 (drilled dia 1.10)", anchor=[P.BALL_XY[2][0], P.BALL_XY[2][1], -0.1], side="L"),
                           dict(text="Clear potting, dia 13 opening", anchor=[gx + rp * math.cos(math.radians(-10)), gy + rp * math.sin(math.radians(-10)), P.GRAIN_FILL_Z], side="L"),
                           dict(text="LED pairs on r 5.2 (potted)", anchor=[gx + 5.2 * math.cos(math.radians(247.5)), gy + 5.2 * math.sin(math.radians(247.5)), 0.6], side="L"),
                           dict(text="Pad slot 17.44 x 2.2", anchor=[P.PAD_XS[-1] + 0.6, P.PAD_Y, 0.0], side="L"),
                           dict(text="Contact pads x7 (gold)", anchor=[P.PAD_XS[4], P.PAD_Y, 0.95], side="L"),
                           dict(text="Visor wall over the base plate", anchor=[-3.0, P.Y_VISOR, 2.6], side="R"),
                           dict(text="Seal adhesive at the rim", anchor=[-21.875 * math.cos(math.radians(25)), 21.875 * math.sin(math.radians(25)), P.RIM_Z], side="R"),
                           dict(text="Ball foot 1 (front)", anchor=[P.BALL_XY[0][0], P.BALL_XY[0][1], -0.1], side="R"),
                           dict(text="Photodiode in the baffle ring", anchor=[gx - 1.0, gy, 0.55], side="R"),
                           dict(text="Baffle ring (black PA12)", anchor=[gx - 0.5 * (P.BAFFLE_RI + P.BAFFLE_RO), gy - 0.5, P.BAFFLE_RING_Z0], side="R"),
                           dict(text="FR-4 base plate (black mask)", anchor=[-17.5, 3.0, 0.0], side="R"),
                           dict(text="Ball foot 2", anchor=[P.BALL_XY[1][0], P.BALL_XY[1][1], -0.1], side="R")])
        outs.append(_run(cfg, tmp))
        # ---------------- (c) exploded, every part separated along z
        dz = {"ball_epoxy_": -44, "ball_": -51, "base_plate": -37, "grain_potting": -30, "seal_bead": -23, "baffle_ring": -17, "baffle_adhesive": -11, "pcb_adhesive": -1,
              "main_pcb": 10, "camera_": 21, "battery_lead_": 21, "battery": 21, "prism_": 29,
              "foam_pad": 32, "lcd_flex": 38, "lcd_glass": 46, "lcd_adhesive": 58, "hood_seal_": 64, "vent": 69, "tub": 74, "visor_window_": 74, "window_bond_": 74,
              "cover_tape": 95, "cover_glass": 106}

        def off(n):
            for k, v in dz.items():
                if n == k or (k.endswith("_") and n.startswith(k)):
                    return (0, 9.0 if n.startswith("visor_window_") else (4.5 if n.startswith("window_bond_") else 0), v)
            return (0, 0, 0)
        eye_dir = np.array([0.62, 0.72, 0.30]); eye_dir /= np.linalg.norm(eye_dir)
        tgt = np.array([0.0, 0.0, 32.5]); eye = tgt + 500 * eye_dir
        r = _screen_right(eye, tgt)
        order = [("cover_glass", "R"), ("cover_tape", "L"), ("tub", "R"), ("visor_window_L", "R"), ("window_bond_R", "L"), ("vent", "L"), ("hood_seal_L", "R"),
                 ("lcd_adhesive", "L"),
                 ("lcd_glass", "R"), ("lcd_flex", "L"), ("foam_pad", "L"), ("prism_L", "R"), ("battery", "L"), ("battery_lead_1", "L"), ("camera_L", "R"), ("main_pcb", "L"),
                 ("pcb_adhesive", "R"), ("baffle_adhesive", "L"), ("baffle_ring", "R"), ("seal_bead", "L"), ("grain_potting", "R"), ("base_plate", "R"),
                 ("ball_epoxy_1", "R"), ("ball_3", "L")]
        extra = {"visor_window_L": "Visor windows x2 (0.40 glass)", "prism_L": "Fold prisms x2 (2 mm, N-BK7)",
                 "camera_L": "Camera cubes x2 (OVM7692)", "ball_3": "Ball feet x3 (dia 1.0)", "ball_epoxy_1": "Ball potting x3 (epoxy)", "lcd_flex": "LCD flex tail (representative)",
                 "window_bond_R": "Window adhesive frame x2", "hood_seal_L": "Black hood gaskets x2",
                 "seal_bead": "Perimeter seal (dispensed)", "pcb_adhesive": "Adhesive sheet 0.20 (die cut)", "lcd_adhesive": "LCD adhesive frame 0.15, vented",
                 "cover_tape": "Tape ring 0.13 (dia 28 / 25)", "main_pcb": "Main PCB assembly", "tub": "Tub (top shell)", "base_plate": "Base plate, FR-4 0.80",
                 "grain_potting": "Clear potting (grain opening)", "baffle_ring": "Baffle ring (black PA12)", "baffle_adhesive": "Baffle annulus 0.13 (black tape)",
                 "battery_lead_1": "Battery leads x2 (envelope)",
                 "cover_glass": "Cover glass dia 28 x 1.0", "lcd_glass": "Memory LCD (glass 0.75)", "battery": "LiPo cell 34 x 10 x 2",
                 "foam_pad": "Foam pad 0.3", "vent": "ePTFE vent (inside the roof)"}
        labels = []
        for n, side in order:
            small = n.startswith(("visor_window_", "window_bond_", "hood_seal_", "prism_", "camera_", "ball_", "vent", "lcd_flex", "battery_lead_", "baffle_"))
            a = _rim_anchor(parts, n, side, r, off(n), frac=0.0 if small else 0.88)
            labels.append(dict(text=extra.get(n, NAMES.get(n, n)), anchor=a, side=side))
        cfg = dict(out=str(RENDER_DIR / "GL1_render_c_exploded.png"), width=1800, height=2400, eye=list(eye), target=list(tgt), ortho=91,
                   title="GL-1 marker - exploded along z",
                   subtitle="every part of the marker (primary build: FR-4 base plate), separated along z (windows also moved forward); assembly sequence in README.md",
                   footer=FOOT, labels=labels, labelTop=150, fontSize=30,
                   parts=[_entry(n, stl[n], off(n)) for n in puck] + [dict(v, offset=[0, 0, dz["main_pcb"]]) for v in detail.values()])
        outs.append(_run(cfg, tmp))
        # ---------------- (d) cut-away: x = 0 behind y_step, x = camera R in front of it
        ystep = P.LCD_Y1 - 0.5
        big = 200.0
        cutter = PT.box(cxr, big, ystep, big, -big, big).union(PT.box(0, big, -big, ystep, -big, big)).val()
        cut = _cut_stls(parts, puck, cutter, tmp, "cut")
        tgt, fovd = (2.0, -1.5, 3.2), 18
        eye = _eye((0.80, -0.42, 0.42), tgt, 78, W, H, fovd)
        labels = [dict(text="Thick roof 2.05", anchor=[0, -19.5, P.T - 1.0], side="L"),
                  dict(text="Cover glass 1.0", anchor=[0, -11.5, 0.5 * (P.CG_Z0 + P.CG_Z1)], side="L"),
                  dict(text="Transfer-tape ring 0.13", anchor=[0, -13.2, P.RECESS_FLOOR_Z + 0.06], side="L"),
                  dict(text="Roof ledge 0.8", anchor=[0, -12.2, 0.5 * (P.BOND_Z + P.RECESS_FLOOR_Z)], side="L"),
                  dict(text="LCD glass 0.75 + frame 0.15", anchor=[0, -15.0, 0.5 * (P.LCD_Z0 + P.LCD_Z1)], side="L"),
                  dict(text="Foam pad 0.3", anchor=[0, -9.6, P.FOAM_Z0 + 0.15], side="L"),
                  dict(text="Battery 2.0 + swell gap", anchor=[0, -8.6, 2.8], side="L"),
                  dict(text="FPC connector J1", anchor=[0, -14.0, 2.9], side="L"),
                  dict(text="PCB 0.80 on sheet 0.20", anchor=[0, -20.3, 1.4], side="L"),
                  dict(text="Seal adhesive", anchor=[0, -P.LAND_RI - 0.2, 1.05], side="L"),
                  dict(text="FR-4 base plate 0.80", anchor=[0, -19.3, 0.40], side="L"),
                  dict(text="Section step at y = %.1f" % ystep, anchor=[5.5, ystep, 7.0], side="R"),
                  dict(text="Visor window 0.40", anchor=[cxr, 0.5 * (P.WIN_Y0 + P.WIN_Y1), 7.0], side="R"),
                  dict(text="Fold prism", anchor=[cxr, 16.1, 5.2], side="R"),
                  dict(text="Camera opening (sill z 4.6)", anchor=[cxr, P.WIN_RECESS_FLOOR_Y - 0.4, P.OPEN_Z0 - 0.3], side="R"),
                  dict(text="Camera cube 2.76", anchor=[cxr, 15.6, 3.2], side="R"),
                  dict(text="MCU (U1) under the LCD", anchor=[0, 7.2, 2.6], side="R"),
                  dict(text="Photodiode in the baffle ring", anchor=[0, P.GRAIN_Y + 0.3, 0.75], side="R"),
                  dict(text="Baffle ring (bonded to the PCB)", anchor=[0, P.GRAIN_Y + 0.5 * (P.BAFFLE_RI + P.BAFFLE_RO), 0.45], side="R"),
                  dict(text="Clear potting, grain opening dia 13", anchor=[0, P.GRAIN_Y + P.GRAIN_R - 1.2, 0.4], side="R")]
        cfg = dict(out=str(RENDER_DIR / "GL1_render_d_cutaway.png"), width=W, height=H, eye=eye, target=tgt, fov=fovd,
                   title="GL-1 marker - cut-away",
                   subtitle=f"true boolean cut on x = 0 (centre stack) behind y = {ystep:.1f} and on x = {cxr} (through camera R) in front of it; cut faces in a lighter tint",
                   footer=FOOT, labels=labels, capPlanes=[dict(axis="x", value=0.0), dict(axis="x", value=cxr), dict(axis="y", value=ystep)],
                   parts=[_entry(n, f) for n, f in cut.items()])
        outs.append(_run(cfg, tmp))
        # ---------------- (e) marker in the cradle
        tgt, fove = (0, -6.0, 0.5), 20
        eye = _eye((0.50, -0.68, 0.54), tgt, 152, W, H, fove)
        a0, a1 = M["scallop_deg"]
        am = math.radians(0.5 * (a0 + a1))
        cfg = dict(out=str(RENDER_DIR / "GL1_render_e_in_cradle.png"), width=W, height=H, eye=eye, target=tgt, fov=fove,
                   title="GL-1 marker in its cradle (charging / data dock, one orientation)",
                   subtitle="seen from the rear right: sprung latch with thumb tab at the rear, fixed lip over the front edge between the camera windows, USB-C in the rear face",
                   footer=FOOT, parts=[_entry(n, stl[n]) for n in puck + cradle],
                   labels=[dict(text="Marker, visor toward +y", anchor=[-8, 6, P.T], side="L"),
                           dict(text="Fixed lip on its tower", anchor=[-M["lip_half_w"] + 1.0, P.LIP_Y0 + 1.0, P.LIP_Z1], side="L"),
                           dict(text="Nest wall (D flat = key)", anchor=[-19.0, -13.4, P.CRADLE_TOP_Z], side="L"),
                           dict(text="Guard wall with stop ribs", anchor=[-P.WELL_HX + 1.0, P.WELL_Y0 - 1.0, M["guard_top_z"]], side="L"),
                           dict(text="Stop under the thumb tab", anchor=[-M["tab_stop_w"] / 2 + 0.8, P.TAB_STOP_Y0 + 0.8, P.TAB_STOP_Z], side="L"),
                           dict(text="Cradle body 60 x 60 x 14", anchor=[-P.CRADLE_X + 8, P.CRADLE_Y0, -5.0], side="L"),
                           dict(text="USB-C receptacle", anchor=[0, P.CRADLE_Y0, P.CPCB_Z1 + 1.6], side="L"),
                           dict(text="Latch hook, 24 mm wide", anchor=[5.0, P.HOOK_Y - 0.9, P.LATCH_TOP_Z - 1.6], side="R"),
                           dict(text="Thumb tab: press to release", anchor=[4.0, P.TAB_Y0 + 2.0, P.LATCH_TOP_Z], side="R"),
                           dict(text="Finger scallop = floor drain", anchor=[27.0 * math.cos(am), 27.0 * math.sin(am), P.BASIN_Z_AT_WALL], side="R"),
                           dict(text="Bumper feet x4 underneath", anchor=[M["foot_xy"][0] + 2.0, P.CRADLE_CY - M["foot_xy"][1] - 2.0, P.CRADLE_BOT_Z + 0.3], side="R")])
        outs.append(_run(cfg, tmp))
        # ---------------- (f) section on x = 0 through the centre pin, the lip and the latch
        cutter = PT.box(0, big, -big, big, -big, big).val()
        cut = _cut_stls(parts, puck + cradle, cutter, tmp, "cutc")
        tgt = (0, -6.0, 0.0)
        eye = _eye((0.88, -0.30, 0.26), tgt, 108, W, H, fove)
        cfg = dict(out=str(RENDER_DIR / "GL1_render_f_cradle_section.png"), width=W, height=H, eye=eye, target=tgt, fov=fove,
                   title="GL-1 marker in its cradle - section on x = 0: pin compression and hold-down",
                   subtitle=f"centre pin compressed {P.PIN_COMPRESSION:.2f} of {M['pin_full_stroke']} mm; hook nose {P.HOOK_OVERLAP:.2f} on the tub top, {P.CLR} clear; lip and latch hold the marker "
                            f"against {len(P.PAD_XS)} x {P.PIN_FORCE_N} N",
                   footer=FOOT, capPlanes=[dict(axis="x", value=0.0)], parts=[_entry(n, f) for n, f in cut.items()],
                   labels=[dict(text="Thumb tab", anchor=[0, P.TAB_Y0 + 2.5, P.LATCH_TOP_Z - 0.8], side="L"),
                           dict(text="Hook with raked nose", anchor=[0, P.HOOK_Y - 0.5, P.HOOK_Z0 + 0.9], side="L"),
                           dict(text="Stop under the tab", anchor=[0, P.TAB_STOP_Y0 + 1.0, P.TAB_STOP_Z - 1.0], side="L"),
                           dict(text="Guard wall", anchor=[0, P.WELL_Y0 - 1.0, M["guard_top_z"] - 1.0], side="L"),
                           dict(text="USB-C receptacle", anchor=[0, P.USB_Y0 + 2.5, P.CPCB_Z1 + 1.6], side="L"),
                           dict(text=f"Latch beam, neck {float(P.latch_h(P.LATCH_NECK_Z - M['latch_root_z'])):.2f}", anchor=[0, P.LATCH_Y_FACE - 0.5, 2.5], side="L"),
                           dict(text="Cradle PCB", anchor=[0, -28.0, 0.5 * (P.CPCB_Z0 + P.CPCB_Z1)], side="L"),
                           dict(text="Spring pin 4 on its pad", anchor=[0, P.PAD_Y, -2.4], side="L"),
                           dict(text="Marker (section A-A)", anchor=[0, 2.0, 5.0], side="R"),
                           dict(text="Fixed lip over the front edge", anchor=[0, P.LIP_Y0 + 0.7, P.LIP_Z0 + 0.8], side="R"),
                           dict(text="Nose pocket under the lip", anchor=[0, P.NEST_FLAT + 0.5, 5.0], side="R"),
                           dict(text="Front ball foot on the strip", anchor=[0, P.BALL_XY[0][1], -0.05], side="R"),
                           dict(text="Drained floor (basin)", anchor=[0, 4.0, P.BASIN_RIDGE_Z], side="R"),
                           dict(text="Cradle body", anchor=[0, 22.0, -5.0], side="R"),
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
