#!/usr/bin/env python3
"""Negative tests for the checks: seed one defect at a time into a copy of the model and confirm that the
corresponding check FAILS.  A check that cannot fail proves nothing.

    python3 cad/build.py --selftest      (or: python3 cad/selftest.py)

Nothing is written to export/; meshes are tessellated in memory from the modified solids.
"""
from __future__ import annotations
import dataclasses, pathlib, sys, time
from collections import OrderedDict
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cadquery as cq
import params as P
import parts as PT
import assembly as A
import checks as C


def _with(parts, **new):
    out = OrderedDict(parts)
    for n, shape in new.items():
        out[n] = dataclasses.replace(parts[n], shape=cq.Workplane("XY").newObject([shape]))
    return out


def _s(parts, n):
    return A.solid_of(parts[n])


def _u8_over_the_front_foot(parts):
    """YAML-level defect: U8 back at its rev C position (0, 15.3), directly over the front ball foot."""
    old = P.TOP_PARTS
    P.TOP_PARTS = [dict(q, x=0.0, y=15.3) if q["ref"] == "U8" else q for q in old]
    try:
        return C.check_posts(parts)
    finally:
        P.TOP_PARTS = old


def _u10_at_its_old_position(parts):
    """YAML-level defect: U10 back at (-14.2, -12.2), 0.19 mm from ball-foot zone 2 (N7 asks for 0.3)."""
    old = P.TOP_PARTS
    P.TOP_PARTS = [dict(q, x=-14.2) if q["ref"] == "U10" else q for q in old]
    try:
        return C.check_posts(parts)
    finally:
        P.TOP_PARTS = old


def _legend_unmirrored(parts):
    """Defect of the legend DATA: the bottom layer written un-mirrored (legend.to_model made the identity), so that every
    word would read backwards on the outer face.  The block layout is symmetric: no keep-clear distance changes."""
    import legend as L
    old = L.to_model
    L.to_model = lambda pl: [(u, v) for u, v in pl]
    try:
        return C.check_fr4_plate(parts)
    finally:
        L.to_model = old


def _legend_tight_pitch(parts):
    """Defect of the legend FONT: the letter pitch of the previous issue (5.2 units), which leaves 0.05 mm between letters
    at the 1.0 mm text height."""
    import legend as L
    old = L.advance
    L.advance = lambda h, stroke=None: L.GLYPH_ADV * h / L.GLYPH_H
    try:
        return C.check_fr4_plate(parts)
    finally:
        L.advance = old


def main():
    import board_import as B
    import legend as L
    C.USE_EXPORTED = False
    t0 = time.time()
    parts = A.build_parts()
    cxr = P.CAM_XY["R"][0]
    tub, base, cradle = _s(parts, "tub"), _s(parts, "base_plate"), _s(parts, "cradle")
    alt = "base_plate" + A.ALT_SUFFIX
    bar = PT.box(cxr - 3, cxr + 3, P.WIN_RECESS_FLOOR_Y - 0.6, P.WIN_RECESS_FLOOR_Y - 0.2, P.AXIS_Z - 0.2, P.AXIS_Z + 0.2).val()
    low_roof = PT.box(cxr - P.OPEN_HALF_W, cxr + P.OPEN_HALF_W, P.HOOD_PAD_Y, P.WIN_RECESS_FLOOR_Y, P.OPEN_Z1 - 0.1, P.OPEN_Z1 + 0.05).val()
    groove = PT.box(-18.0, -16.0, -6.0, -4.0, P.ROOF_Z - 0.01, P.T - 0.3).val()
    void = PT.box(16.2, 20.2, -35.0, -31.0, -9.0, -5.0).val()
    channel = PT.cyl(18.2, -33.0, 0.5, -5.5, 5.0).val()
    lw = P.MECH["lip_half_w"]
    low_lip = PT.box(-lw, lw, P.LIP_Y0, P.NEST_FLAT, P.LIP_Z0 - 0.4, P.LIP_Z0 + 0.1).val()
    short_hook = PT.box(-30, 30, P.HOOK_Y - 0.6, P.HOOK_Y + 1.0, P.HOOK_Z0 - 0.1, P.LATCH_TOP_Z + 0.1).val()
    rib = PT.box(-1.0, 1.0, -3.0, -1.0, 3.0, P.ROOF_Z + 0.1).val()
    notch = PT.box(8.4, 10.1, P.Y_VISOR_IN - P.CLR, P.BASE_FLAT + 1.0, -1.0, 2.0).val()          # the key notch of the first rev C model
    small_ledge = (PT.cyl(0, 0, P.LEDGE_RI + 0.05, P.LEDGE_Z0, P.LEDGE_Z1).cut(PT.cyl(0, 0, P.LEDGE_RI - 0.3, 0, P.T))
                   .intersect(PT.box(-30, 30, -30, P.Y_VISOR_IN, 0, P.T))).val()
    fx, fy = P.FOOT_ZONES[0]
    foot_post = PT.box(fx - 0.8, fx + 0.8, fy - 0.8, fy + 0.8, P.PCB_Z1, P.ROOF_Z + 0.1).val()
    proud_pot = PT.cyl(P.GRAIN_X + 5.3, P.GRAIN_Y, 0.8, -0.05, P.GRAIN_FILL_Z + 0.01).val()        # a blob of potting 0.05 proud of the base plane
    sq_notch = PT.box(-0.5, 0.5, -22.0, -20.9, -1.0, 2.0).val()
    edge_hole = PT.cyl(0.0, -20.8, 0.55, -1.0, 2.0).val()
    bx, by = P.BALL_XY[0]
    with P.base_variant(P.BASE_ALT):
        tight_hole = PT.cyl(bx, by, P.BALL_HOLE_D / 2 + 0.01, 0.0, P.BASE_T).cut(PT.cyl(bx, by, 0.45, -1, 2)).val()   # foot hole 1 printed at dia 0.9
    bead_gap = PT.box(-1.5, 1.5, -23.0, -20.5, -1.0, 2.0).val()
    roof_001 = PT.box(cxr - P.OPEN_HALF_W, cxr + P.OPEN_HALF_W, P.HOOD_PAD_Y, P.WIN_RECESS_FLOOR_Y, P.OPEN_Z1 - 0.01, P.OPEN_Z1 + 0.05).val()
    wb = _s(parts, "window_bond_R")
    # (the cuts start 0.002 mm inside the neighbouring faces, so that no skin of adhesive is left to close the gap)
    sill = PT.box(cxr - P.WIN_W / 2 + 0.05, cxr + P.WIN_W / 2 - 0.05, P.WIN_Y1 - 0.002, P.Y_VISOR + 1, P.WIN_Z0 - 0.1, P.WIN_Z0 + 1.0).val()   # the fillet on the shelf in front of the glass
    top_bead = PT.box(cxr - P.WIN_W / 2 + 0.05, cxr + P.WIN_W / 2 - 0.05, 17.0, 19.0, P.WIN_TOP_Z - 0.002, P.T + 1).val()   # the bead on the top edge
    short_ribs = PT.box(-12.0, 12.0, P.LCD_POCKET_Y0 - 1.0, P.LCD_POCKET_Y0 + 1e-3, P.KO_FREE_Z - 0.1, P.KO_FREE_Z + 0.6).val()   # rear ribs ending 0.6 higher
    # ---- defects for what the amendments added (E9, E10, E11, E12, N9)
    lg_hole = L.blocks(); lg_hole[0] = dict(lg_hole[0], centre=(0.0, 13.0))          # 'MAKER NAME' 0.6 mm from the mask relief of ball-foot hole 1
    lg_seat = L.blocks(); lg_seat[0] = dict(lg_seat[0], centre=(0.0, 10.6))          # the same line 3 mm from the hole, but inside the calibration seat zone
    sx, sy, sd, sl = P.LOC_SLOT
    stadium = lambda length: (PT.box(sx - (length - sd) / 2, sx + (length - sd) / 2, sy - sd / 2, sy + sd / 2, P.PCB_Z0, P.PCB_Z1)
                              .union(PT.cyl(sx - (length - sd) / 2, sy, sd / 2, P.PCB_Z0, P.PCB_Z1)).union(PT.cyl(sx + (length - sd) / 2, sy, sd / 2, P.PCB_Z0, P.PCB_Z1))).val()
    short_slot_pcb = _s(parts, "main_pcb").fuse(stadium(sl)).cut(stadium(1.8))       # the slot of the unamended YAML: 1.8 long
    thick_film = PT.cyl(0, 0, P.RETARDER_D / 2, P.RETARDER_Z1 - 0.15, P.RETARDER_Z1).val()
    wide_film = PT.cyl(0, 0, P.MECH["cover_tape_id"] / 2 + 0.3, P.RETARDER_Z0, P.RETARDER_Z1).val()
    # the LCD pocket grown in both directions: front stops 0.15 mm further forward, side stops (side ribs, posts B) 0.10 mm
    # further out on each side.  (One direction alone is not a defect of the rotation: the other pair of stops still holds
    # the glass to 1.19 or 1.24 degrees, inside the limit.)
    big_pocket = PT.box(-14.0, 14.0, P.LCD_POCKET_Y1 - 0.01, P.LCD_POCKET_Y1 + 0.15, P.KO_FREE_Z + 0.05, P.BOND_Z).val()
    for sgn in (-1, 1):
        x0, x1 = sorted((sgn * (P.LCD_POCKET_X - 0.01), sgn * (P.LCD_POCKET_X + 0.10)))
        big_pocket = big_pocket.fuse(PT.box(x0, x1, P.LCD_POCKET_Y0 - 0.5, P.LCD_POCKET_Y1 + 0.5, P.KO_FREE_Z + 0.05, P.BOND_Z).val())
    # ---- defects for what the review of this issue found untested
    cxl = P.CAM_XY["L"][0]
    roof_001_L = PT.box(cxl - P.OPEN_HALF_W, cxl + P.OPEN_HALF_W, P.HOOD_PAD_Y, P.WIN_RECESS_FLOOR_Y, P.OPEN_Z1 - 0.01, P.OPEN_Z1 + 0.05).val()
    pcb0 = _s(parts, "main_pcb")
    slot_at = lambda dy_: (PT.box(sx - (sl - sd) / 2, sx + (sl - sd) / 2, sy + dy_ - sd / 2, sy + dy_ + sd / 2, P.PCB_Z0, P.PCB_Z1)
                           .union(PT.cyl(sx - (sl - sd) / 2, sy + dy_, sd / 2, P.PCB_Z0, P.PCB_Z1)).union(PT.cyl(sx + (sl - sd) / 2, sy + dy_, sd / 2, P.PCB_Z0, P.PCB_Z1))).val()
    slot_off_pcb = pcb0.fuse(slot_at(0.0)).cut(slot_at(0.05))                       # the 2.2 x 1.15 slot 0.05 mm off its centre line (two thirds of the 0.075 fit)
    rx, ry, rd = P.LOC_ROUND
    hole_off_pcb = pcb0.fuse(PT.cyl(rx, ry, rd / 2, P.PCB_Z0, P.PCB_Z1).val()).cut(PT.cyl(rx, ry + 0.05, rd / 2, P.PCB_Z0, P.PCB_Z1).val())   # the round hole 0.05 mm off in y
    old_film = PT.cyl(0, 0, 12.0, P.RETARDER_Z0, P.RETARDER_Z1).val()                # the dia 24.0 film of the previous issue: 0.5 inside the tape bore, less than its centring chain
    cases = [
        ("roof 0.01 mm low over the camera L opening ONLY (camera R untouched): the guaranteed case of camera L falls below 14.5 deg", C.check_fold, _with(parts, tub=tub.fuse(roof_001_L)),
         "camera L in the guaranteed case"),
        ("legend layer written un-mirrored (every word would read backwards on the outer face)", _legend_unmirrored, parts, "MIRRORED"),
        ("legend text at the letter pitch of the previous issue (0.05 mm between letters at 1.0 mm text)", _legend_tight_pitch, parts, "smallest clear space"),
        ("PCB locating slot 0.05 mm off its centre line in y (check 14 measures the slot on the PCB solid)", C.check_assembly_paths, _with(parts, main_pcb=slot_off_pcb), "PCB locating slot"),
        ("PCB locating slot 0.05 mm off its centre line in y (check 2: across-slot fit 0.025 instead of 0.075)", C.check_clearances, _with(parts, main_pcb=slot_off_pcb), "spigot in the slot"),
        ("PCB round locating hole 0.05 mm off in y", C.check_assembly_paths, _with(parts, main_pcb=hole_off_pcb), "PCB locating hole (round)"),
        ("retarder film dia 24.0 without a flat (the previous issue): its 0.5 mm to the tape bore is less than the 0.75 mm centring chain", C.check_clearances, _with(parts, retarder_film=old_film),
         "AFTER THE CENTRING CHAIN"),
        ("ball gauge plate without bosses (a flat plate: the base plate would lie on its legend ink)", C.check_cal_plates, _with(parts, gauge_plate=PT.ball_gauge_plate(boss=False).val()), "gauge plate"),
        ("ball gauge plate with dia 0.70 gauge holes (the balls would stand 0.14 proud)", C.check_cal_plates, _with(parts, gauge_plate=PT.ball_gauge_plate(hole_dia=0.70).val()), "gauge plate"),
        ("legend: 'MAKER NAME' moved to 0.6 mm from the mask relief of ball-foot hole 1 (keep-clear 1.0)", lambda q: C.check_fr4_plate(q, legend_blocks=lg_hole), parts, "legend keep-clear"),
        ("legend: 'MAKER NAME' inside the calibration seat zone of ball foot 1 (3 mm from the hole)", lambda q: C.check_fr4_plate(q, legend_blocks=lg_seat), parts, "legend keep-clear"),
        ("PCB locating slot only 1.8 mm long (the slot before decision N9)", C.check_assembly_paths, _with(parts, main_pcb=short_slot_pcb), "PCB locating slot"),
        ("retarder film 0.15 mm thick: thicker than the tape gap, it sits on the roof ledge", C.check_clearances, _with(parts, retarder_film=thick_film), "retarder film"),
        ("retarder film dia 25.6: it reaches under the tape ring", C.check_clearances, _with(parts, retarder_film=wide_film), "retarder film"),
        ("LCD pocket 0.15 mm longer and 0.2 mm wider (front and side stops cut back): the glass can turn 1.5 deg", C.check_assembly_paths, _with(parts, tub=tub.cut(big_pocket)), "display rotation"),
        ("calibration seat plate with pockets only 0.08 mm deep (a ball foot stands on the pocket floor)", C.check_cal_plates,
         _with(parts, cal_seat_plate=PT.cal_seat_plate(pocket_depth=0.08).val()), "ball foot to its pocket"),
        ("U10 back at x -14.2: 0.19 mm from ball-foot zone 2 (N7 asks for 0.3)", _u10_at_its_old_position, parts, "foot zone 2"),
        ("prism R raised 0.30 mm into the roof", C.check_interference, _with(parts, prism_R=_s(parts, "prism_R").translate((0, 0, 0.30)))),
        ("LCD glass shifted 0.20 mm toward the cameras", C.check_clearances, _with(parts, lcd_glass=_s(parts, "lcd_glass").translate((0, 0.20, 0)))),
        ("battery raised 0.25 mm (eats the swell allowance)", C.check_clearances, _with(parts, battery=_s(parts, "battery").translate((0, 0, 0.25)))),
        ("visor window R 0.20 mm proud of its seat (stands above the visor face)", C.check_clearances,
         _with(parts, visor_window_R=_s(parts, "visor_window_R").translate((0, 0.20, 0)))),
        ("clear potting 0.05 mm proud of the base plane", C.check_clearances, _with(parts, grain_potting=_s(parts, "grain_potting").fuse(proud_pot))),
        ("baffle ring bonded 0.5 mm off centre", C.check_clearances, _with(parts, baffle_ring=_s(parts, "baffle_ring").translate((0.5, 0, 0)))),
        ("0.4 mm bar across the camera R opening", C.check_fov, _with(parts, tub=tub.fuse(bar))),
        ("0.4 mm bar across the camera R opening", C.check_fold, _with(parts, tub=tub.fuse(bar))),
        ("roof 0.1 mm low over the camera R opening (upper field far below the guaranteed 14.5 deg)", C.check_fold, _with(parts, tub=tub.fuse(low_roof)), "BELOW"),
        ("roof 0.01 mm low over the camera R opening (the guaranteed case loses 0.18 deg: more than its 0.11 deg margin to 14.5)", C.check_fold,
         _with(parts, tub=tub.fuse(roof_001)), "BELOW"),
        ("hood gasket bead R dispensed 0.2 mm too far forward (over the chamfer of the rear wall)", C.check_clearances,
         _with(parts, hood_seal_R=_s(parts, "hood_seal_R").translate((0, 0.20, 0)))),
        ("2 x 2 mm pocket leaving a 0.30 mm roof", C.check_walls, _with(parts, tub=tub.cut(groove))),
        ("closed 4 mm void inside the cradle body", C.check_trapped, _with(parts, cradle=cradle.cut(void))),
        ("4 mm cavity in the cradle with only a dia 1.0 exit", C.check_trapped, _with(parts, cradle=cradle.cut(void).cut(channel))),
        ("lip 0.4 mm too low (no clearance over the tub)", C.check_cradle, _with(parts, cradle=cradle.fuse(low_lip))),
        ("latch hook cut back by 0.6 mm (overlap 0.25 forward)", C.check_cradle, _with(parts, cradle=cradle.cut(short_hook))),
        ("stop under the thumb tab left out", C.check_cradle, _with(parts, cradle=PT.cradle(with_tab_stop=False).val())),
        ("2 mm rib from the roof down to z 3.0 over the PCB, outside the keep-outs", C.check_keepouts, _with(parts, tub=tub.fuse(rib))),
        ("support post A+ shortened by 0.5 mm", C.check_posts, _with(parts, tub=tub.cut(PT.box(14.0, 17.0, 0.5, 3.0, P.PCB_Z1 - 0.01, P.PCB_Z1 + 0.5).val()))),
        ("a tub post standing on the front ball-foot zone", C.check_posts, _with(parts, tub=tub.fuse(foot_post))),
        ("U8 back over the front ball foot (rev C position in the YAML part list)", _u8_over_the_front_foot, parts),
        ("key notch through base plate and bead at the seal land (first rev C model)", C.check_seal,
         _with(parts, base_plate=base.cut(notch), seal_bead=_s(parts, "seal_bead").cut(notch))),
        ("visor window R: adhesive frame without the fillet along the bottom edge (bare glass on its shelf)", C.check_seal, _with(parts, window_bond_R=wb.cut(sill)), "connected"),
        ("visor window R: adhesive frame without the bead along the top edge", C.check_seal, _with(parts, window_bond_R=wb.cut(top_bead)), "connected"),
        ("visor window L: no adhesive at all (glass only seated)", C.check_seal,
         _with(parts, window_bond_L=PT.box(-0.05, 0.05, -0.05, 0.05, P.PCB_Z0 + 0.3, P.PCB_Z0 + 0.4).val()), "connected"),
        ("1 mm gap in the tape ring under the cover glass", C.check_seal,
         _with(parts, cover_tape=_s(parts, "cover_tape").cut(PT.box(-0.5, 0.5, -15.0, -11.0, P.RECESS_FLOOR_Z - 0.1, P.CG_Z0 + 0.1).val())), "connected"),
        ("seating ledge 0.3 mm too small on radius", C.check_assembly_paths, _with(parts, tub=tub.fuse(small_ledge))),
        ("rear glass ribs ending 0.6 mm higher (no stop for the LCD at the push-back height)", C.check_assembly_paths, _with(parts, tub=tub.cut(short_ribs))),
        ("FR-4 plate with a square 1 x 1 mm notch in its edge (sharp internal corners)", C.check_fr4_plate, _with(parts, base_plate=base.cut(sq_notch))),
        ("FR-4 plate with a drilled hole 0.4 mm from the edge", C.check_fr4_plate, _with(parts, base_plate=base.cut(edge_hole))),
        ("PA12 plate: foot hole 1 printed at dia 0.9 (the ball does not enter)", C.check_alt_base, _with(parts, **{alt: _s(parts, alt).fuse(tight_hole)})),
        ("PA12 build: 3 mm gap in the perimeter seal bead", C.check_alt_base,
         _with(parts, **{"seal_bead" + A.ALT_SUFFIX: _s(parts, "seal_bead" + A.ALT_SUFFIX).cut(bead_gap)})),
    ]
    rows, ok = [], True

    def record(label, r, expect_caught=True, must_mention=None):
        nonlocal ok
        caught = not r["passed"]
        good = caught == expect_caught
        if good and must_mention and must_mention not in r["summary"]:
            good = False                                          # caught, but not for the seeded reason
        ok &= good
        rows.append(dict(defect=label, check=f"{r['id']} {r['name']}", expected=("fail" if expect_caught else "pass"), result=("fail" if caught else "pass"),
                         as_expected=good, message=r["summary"][:220]))
        tag = ("caught" if caught else "MISSED") if expect_caught else ("passes" if not caught else "FALSE ALARM")
        print(f"[{tag if good else tag + ' (WRONG)'}] {label[:78]:78s} -> check {r['id']} {r['name']}", flush=True)

    for label, fn, mod, *word in cases:
        record(label, fn(mod), must_mention=(word[0] if word else None))
    # ---- board import (check 17): a board built from the YAML must pass; each seeded defect must be caught for its own reason;
    #      the demonstration board of the toolchain (older positions) must show its mismatches
    record("board import: board built from the amended rev D YAML (conforming, synthetic)", C.check_board_import(parts, data=B.synthetic_board()), expect_caught=False)
    for defect, label, word in (("tall_under_hood", "a 1.5 mm part under camera hood R", "under camera hood"),
                                ("part_on_post_foot", "an 0402 resistor on post foot A+", "post foot A+"),
                                ("part_over_foot_zone", "an 0402 capacitor over the front ball-foot zone", "over ball-foot zone 1"),
                                ("hole_moved", "the round locating hole 0.3 mm off", "locating hole"),
                                ("pads_shifted", "the contact-pad row shifted 0.4 mm", "cradle pin axis"),
                                ("bottom_part_outside", "a bottom-side capacitor outside the grain opening", "outside the grain opening"),
                                ("outline_rectangle", "a rectangular outline with the bounds of the D that states a tolerance of 10 mm for itself", "outline"),
                                ("bad_side", "a 2.5 mm part whose side is neither top nor bottom", "neither 'top' nor 'bottom'"),
                                ("polygon_hole_only", "an opening listed only in the polygon holes of the outline", "openings listed only"),
                                ("part_in_tail_path", "a 2.5 mm part in the path of the LCD tail behind J1", "LCD flex tail"),
                                ("part_near_foot_zone", "an 0402 capacitor 0.15 mm from ball-foot zone 3 (N7: 0.3 required)", "to ball-foot zone 3"),
                                ("tall_in_tail_zone", "a part 0.02 mm taller than the LCD-tail keep-out allows (N10)", "LCD-tail keep-out")):
        record(f"board import: {label}", C.check_board_import(parts, data=B.seeded(defect)), must_mention=word)
    r = C.check_board_import(parts, data=B.seeded("dnp_tall_under_hood"))
    r = dict(r, summary=r["summary"] + " | warnings: " + "; ".join(r["warnings"]))
    record("board import: a 2.5 mm part under hood R that is marked not fitted (DNP): passes, with a warning", r, expect_caught=False, must_mention="marked not fitted")
    if B.DEMO_FILE.exists():
        record("board import: demonstration board of the toolchain (rev C positions: holes under posts E, U8 over the front foot)",
               C.check_board_import(parts, path=B.DEMO_FILE), must_mention="locating hole")
    record("board import: no board file", C.check_board_import(parts, path=P.EXPORT_DIR / "no_such_board-mechanical.json"), expect_caught=False, must_mention="skipped: no board file")
    # and the unmodified model must pass the same checks
    for fn in (C.check_clearances, C.check_fold, C.check_posts, C.check_keepouts, C.check_seal, C.check_assembly_paths, C.check_fr4_plate, C.check_alt_base, C.check_cal_plates):
        r = fn(parts)
        record("unmodified model", r, expect_caught=False)
    n_def = sum(r["expected"] == "fail" for r in rows)
    readme = P.MECH_DIR / "README.md"                      # the README states how many defects are seeded: keep it true
    if readme.exists() and f"seeds {n_def} defects" not in " ".join(readme.read_text().split()):
        print(f"[README] README.md does not say 'seeds {n_def} defects'", flush=True)
        ok = False
    (P.EXPORT_DIR / "selftest_report.json").write_text(__import__("json").dumps(dict(all_defects_caught=ok, seeded_defects=n_def, cases=rows), indent=1))
    print(f"{f'SELFTEST PASSED: all {n_def} seeded defects were caught and the unmodified cases pass' if ok else 'SELFTEST FAILED'} ({time.time() - t0:.1f} s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
