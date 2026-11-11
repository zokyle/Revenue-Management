# GL-1 mechanical: proposed changes to design/master_params.yaml and DESIGN_SPEC.md (after rev C-EVT1)

`master_params.yaml` was NOT edited. Part A records what happened to each proposal of the rev B list under
revision C. Part B lists the NEW changes the mechanical model asks for after rev C, with numbers from
`export/check_report.md`. Deviation IDs refer to `cad/deviations.py`. All of this is PROVISIONAL: nothing has been built.

## A. Disposition of the rev B proposals under revision C

| # | Rev B proposal | Rev C decision | In the model now | Dev. |
|---|---|---|---|---|
| 1 | `base_plate.pad_holes`: one slot 17.44 x 2.2 instead of seven dia 2.2 holes | adopted (`form: slot`) | one slot in base plate and adhesive sheet; plunger 0.565 mm clear | D01 closed |
| 2 | `base_plate.feet`: smaller ball, local thickening or dowel pins; protrusion set on a gauge plate | adopted differently: dia 1.15 through holes, balls set on a gauge plate and potted, dia 2.0 holes in the sheet | through holes modelled, conical seats removed, epoxy modelled as a solid (plug + 0.08 dome); ball top 0.10 under the PCB. Residual process point: B6 | D02 closed |
| 3 | `pcb.z_bottom` / adhesive sheet at zero thickness: (a) base 0.87 or (b) 7.73 mm stack | (a) adopted: base 0.87 + sheet 0.13 | sheet at z 0.87 to 1.00, no overlap with the PCB (check 1: zero modelling overlaps); seal bead 0.33; overall height 7.60 | D10 closed |
| 4 | thin strip behind the window recess: move the cameras back 0.3 mm, or accept | accepted as a recorded deviation (`min_wall_behind_recess: 0.525`) | 0.525 mm over 4.0 x 0.4 mm per camera, listed by the wall audit | D04 accepted |
| 5 | window-to-recess clearance 0.05 per side | adopted: recess 5.5 for a 5.0 window | 0.25 per side | D12 closed |
| 6 | opening half-width 1.65 to 2.0, window 5.0, recess 5.5 | adopted, with the cameras moved to x = +-10.0 so that 1.05 mm of visor face remains outboard of each recess | side margin of the pupil bundle 0.028 to 0.378 mm; the full pupil stays clear to 25.6 deg with the optics 0.294 mm sideways (spigot play + 0.2 print) | - |
| 7 | sill 4.6 to 4.3 | not adopted; instead the required lower field is reduced to about -8 deg | sill margin 0.397 mm at -8 deg; full pupil clear to -15.35 deg nominally and to -11.7 deg with the optics 0.2 mm low | - |
| 8 | roof / upper field: no change proposed, record the 0.054 mm margin | unchanged | still 0.054 mm; see B2 | - |
| 9 | `pcb.radius: 21.1` | adopted | PCB edge to ledge 0.25 mm | D12 closed |
| 10 | PCB-to-tub locating features on posts E | adopted: round hole + slot, spigots dia 1.0 x 0.6 | spigots modelled; posts E still seat on the PCB (1.53 and 0.96 mm2); fit 0.075 mm: see B3 | D19 (new) |
| 11 | LCD past the ledge: accept the biased insertion, relieve the ledge, or move the glass | accepted (assembly step) | README assembly step 8; 0.12 mm clearance | D11 accepted |
| 12 | `vent` at (17.9, -3.0) | adopted | as modelled | D08 closed |
| 13 | baffle ring numbers in the YAML | adopted (`base_plate.baffle`) | the model reads them; photodiode clearance 0.249 mm because the ring is rounded to 5.91 | D03 closed |
| 14 | `tub_keepouts` block | adopted: eight 1.6 mm post feet, hood zones camera x +-2.85, y 13.7 to 17.3, parts to 0.95 mm | posts and hoods are generated from the block; check 12 proves it on the tub solid (0.000000 mm3 of tub in the layout space below z 4.35). Hood is +-2.80 from y 13.75; skirts 1.20 above the PCB. See B1 for what the block does not cover | D22 (new) |
| 15 | `cradle` block | adopted, and the cradle redefined as a dock | redesigned: one orientation, no plate, lip + latch (README section 8). See B5 for the numbers that should go back into the block | D15, D16, D17 closed; D20, D21 new |

Rev B text items: the "180 degrees touches no pins" sentence is gone from the rev C spec; the hold-down is now in the
spec and designed; the hood slit is accepted and closed with black adhesive (D13); pad slot, through holes and the
adhesive sheet are in the spec text and the stack table.

Rev B decisions for the system owner: hold-down concept: decided (lip + latch) and implemented; flip calibration in the
cradle: dropped; adhesive selection for vapor-smoothed PA12: **still open**; OVM7692 lens data (pupil position and size):
**still open** (the 2.0 mm prism clips 2.3 % of the assumed pupil at the horizontal field edge).

## B. New changes proposed after revision C

| # | YAML key / text | Now | Proposed | Why (numbers from export/check_report.md) | Dev. |
|---|---|---|---|---|---|
| B1 | `tub_keepouts` (and the "hits the roof" rule of `check_layout.py`) | post feet and hood zones only; `check_layout.py` lets a part outside the LCD footprint reach z = roof - 0.1 = 6.7 | add `free_height_above_pcb: 2.55` (z 4.35) as the height the layout may use anywhere outside the keep-outs, and make `check_layout.py` use it; or list the low-roof regions | above z 4.35 the tub hangs over the PCB outside the keep-outs: glass locating ribs to z 4.75 (x +-13.55 to 14.35, y -11 to -7 and 4 to 8; x +-8 to 11, y -17.85 to -17.05), thick roof at z 5.55 (|x| <= 13.55 back to the rear wall, and r <= 15.05), nose pad at z 6.5 (|x| <= 1.3, y 14.75 to 17.6), vent pad at z 6.6 (x 14.5 to 20.7, y -5.8 to -0.2). Check 12 height map: lowest tub outside the keep-outs is 2.95 mm above the PCB; 38 % of that area is below roof height. No listed part is affected (tallest outside the LCD: 1.45 mm) | D22 |
| B2 | new `cameras.field_required_deg` and the upper field | the required field (+-26, +17.6 / -8) exists only in the task text and in `mechanical/cad/params.py`; roof underside 6.8 | add `field_required_deg: {h: 26.0, up: 17.6, down: 8.0}` so that both packages check the same number, and decide the upper field: either accept about +15 deg or find 0.2 mm of height | the +17.6 deg field edge clears the roof underside by 0.054 mm. Optics 0.2 mm high: upper field clipped at 15.0 deg, 64 % transmission at the worst field point. Spigot fore-aft play (0.179 mm): upper limit 17.6 deg, zero margin. Sideways and downward the rev C numbers are adequate (0.378 and 0.397 mm) | - |
| B3 | `pcb.locating_holes` | round dia 1.15, slot 1.15 x 1.65, spigot dia 1.0: 0.075 mm radial | **keep**, but record that the spigots are a gauged feature (go gauge dia 1.10 at first article). Do not loosen the hole unless first articles force it | 0.075 mm is below the +-0.2 mm print tolerance, so some spigots will need dressing. A dia 1.25 hole (0.125 fit) was evaluated: sideways it is harmless (0.356 mm with print tolerance: full pupil still 25.6 deg), but its yaw play moves a camera 0.298 mm fore-aft and the upper field drops to 17.0 deg (required 17.6), worst-point transmission 91 %. Yaw play is +-1.02 deg now, +-1.71 deg with the looser hole: stereo calibration must absorb it either way | D19 |
| B4 | `DESIGN_SPEC.md` section 5, part 1 | "two bevelled camera openings" | "two straight camera openings, 4.0 mm wide" | the bundle is +-1.62 mm at the aperture and about +-1.23 mm at the inner face of the wall, so a bevel toward the inside clears nothing; the bay is 4.0 mm wide and the hood 5.6 mm of the 5.7 mm keep-out | D05 |
| B5 | `cradle` block | body 60 x 60 x 14, pad plane, pin row, pin data, one-line hold-down description | add what the cradle PCB layout and the manufacturing plan need: `body_y: [-36.0, 24.0]` (not centred on the marker), `overall_height: 22.3`, `nest_floor_z: -0.10`, `pcb: {x: [-15.0, 15.0], y: [-34.2, -12.2], top_z: -4.82, screws: [[+-12.5, -31.5], [+-12.5, -14.5]], usb_mouth_y: -35.5}`, `hold_down: {lip: {half_w: 6.0, overlap: 1.2, clearance: 0.25}, latch: {w: 14.0, t: 1.15, free_length: 11.65, hook_overlap: 0.90, clearance: 0.25, stop_travel: 1.9}, float: 0.25}` | these numbers exist only in `mechanical/cad/params.py`. The latch well (|x| <= 8.2, y -27.0 to -21.05) ends 1.02 mm above the cradle PCB top and does not break through, so the PCB needs no cut-out | D20 |
| B6 | `base_plate.feet` comment ("potted with UV epoxy") | UV epoxy | "dual-cure (UV + heat or moisture) or two-part epoxy"; add `epoxy_dome_max: 0.08` | the joint below the ball's equator is shadowed by the steel ball and by black PA12, so a UV-only adhesive stays liquid there. The dome over the ball must stay under the 0.13 mm sheet: the PCB underside is 0.10 mm above the ball top and 0.05 mm above a 0.08 mm dome. Each potting is also a seal (the sheet has a dia 2.0 hole there) | - |
| B7 | `cradle.pins` and `pad_plane_z` | working height 5.82 on the pad plane z 1.00 with the marker on its feet | either keep and accept, or raise the cradle PCB by half the float (top at z -4.695) | lip and hook have the 0.25 mm drop-in clearance, so with pins fitted the marker floats up to 0.25 mm and the pins work at 6.07 mm (0.89 of 2.29 mm stroke). Centring would give 5.695 to 5.945 mm. The pin barrel length is unknown: the model assumes its top 4.47 mm above the cradle PCB (z -0.35); a barrel taller than 4.72 mm would stand above the nest floor | D21 |
| B8 | `cradle.pins.force_working_N`, `friction`, PA12 modulus | 0.59 N per pin (provisional); friction and modulus are mechanical assumptions | no number to change; record in the release gates that the hold-down proof depends on them | retention is 5.9 x the seven-pin force without friction (4.0 x with the marker fully forward) for E = 1700 MPa; it scales with E and inversely with the pin force. At E = 1200 MPa (conditioned PA12, assumed) it would be 4.2 x and 2.8 x: below 3 x in the worst position without friction, although friction above 0.24 makes the hook self-locking | - |

## C. Decisions for the system owner (not YAML numbers)

- Upper field of view (B2): accept about +15 deg at the tolerance limit, or fund 0.2 mm (thicker puck, thinner roof is not
  possible at 0.8 mm, lower optical axis by a thinner prism bond is 0.05 mm at most).
- Cradle latch (README section 8, open issue 3): the design meets the retention, strain and path requirements on paper with
  0.09 % of strain margin at the over-travel stop; a first-article cycle and pull test decides whether the 1.15 mm beam stays.
- Ball potting adhesive and seal adhesive for vapor-smoothed PA12 (README sections 7 and 9).
- Lens data for the OVM7692 (entrance-pupil position and diameter).
