# GL-1 mechanical: rev C proposals under revision D, and what the YAML still needs

`design/master_params.yaml` (rev D-EVT1) was NOT edited. Part A records what revision D did with every proposal
(B1 to B22) and every decision (C) of the rev C list, and where the model stands. Part B lists only the NEW changes
the mechanical model asks for after rev D. Numbers are from `export/check_report.md`; deviation IDs from
`cad/deviations.py`. Nothing has been built.

## A. Disposition of the rev C proposals and decisions

| # | Rev C proposal | Revision D | In the model now |
|---|---|---|---|
| B1 | free height above the PCB in `tub_keepouts` | adopted: `free_height_above_pcb: 2.55`, used by `check_layout.py` | check 12 proves the tub clear below z 4.35; D22 closed |
| B2 | `cameras.field_required_deg`; decide the upper field | adopted: h 26, up 17.6, up_guaranteed 15.0, down 8.0; the upper edge is accepted | checks 3 and 4 read the YAML. Upper field at the tolerance limit: 14.97 deg (closed form 14.967), 0.03 below the guaranteed 15.0. Check 4 compares strictly; a shortfall up to 0.05 deg is the recorded deviation D31 (a warning), more fails. See N3 |
| B3 | keep the 0.075 fit, move the spigots to posts B | adopted: round dia 1.15 at (14.35, 10.8), slot 1.15 x 1.8 at (-14.35, 10.8) | spigots under posts B, 28.7 apart: +-0.100 sideways, +-0.075 fore-aft, +-0.30 deg yaw at a camera (rev C: 0.094 / 0.179 / 1.02); D19 accepted. Slot travel: see N9 |
| B4 | straight camera openings | adopted (spec text, `visor_window.opening`) | unchanged; D05 closed |
| B5 | cradle numbers into the YAML | adopted as modelled (`cradle` block) | the model reads the block; derived values (overall height 22.63, PCB top -4.855, hook overlap 1.10) are asserted; D20, D25 closed |
| B6 | ball potting, PCB land and keep-out, no part over a foot | adopted: dual-cure or two-part epoxy, `epoxy_dome_max`, `backfill`, land dia 1.6 in a dia 2.5 zone, `foot_zones`, U8 moved to (-11.0, 11.6) | check 10: no post foot and no soldered part over a foot zone (nearest part U10, 0.19 mm); D27 closed |
| B7 | pad plane = copper face 0.965; float 0.25 | adopted | pins 5.82 on z 0.965, 6.07 floated; D21, D28 closed |
| B8 | hold-down proof depends on pin force, friction, modulus | no number; carried as test items | README section 12 (latch cycle, creep, pull) |
| B9 | rim relief 0.25 | adopted (`envelope.rim_relief`) | D23 closed |
| B10 | vent pad 0.3 with drain grooves | adopted (`vent.location`) | D24 closed |
| B11 | baffle ring dia 6.6 / 8.2 | adopted | 0.594 to the photodiode, 0.604 to the LEDs; D03 closed. Height and level of the separate ring: D32, N4 |
| B12 | larger feet under the locating posts | adopted: `post_feet.locating` 2.2 x 2.2 at posts B | built 1.9 x 2.2: the LCD glass must pass between the posts (D29, N1); seat 3.14 mm2 (round hole) and 2.44 mm2 (slot) |
| B13 | base plate FR-4, stainless or PA12 | FR-4 0.80 + 0.20 sheet is primary; PA12 0.87 + 0.13 stays as the alternative, compared at EVT. **Stainless: not adopted** (the spec gives the reasons for FR-4: same expansion as the PCB it is laminated to, flat, drilled holes to 0.05 mm, from the PCB fabricator) | both plates and both sheets are built, exported and checked in one build (checks 15 and 16); seal joint 0.40 / 0.33 (it does not depend on the plate thickness); Gerber / Excellon data for the FR-4 plate; plates sorted to 0.76 to 0.90 / 0.83 to 0.92 (N6) |
| B14 | windows and cover glass below flush | adopted: windows 5.0 x 3.25 x 0.40, 0.15 below face and top; crystal 0.12 below flush on a 0.13 tape | as specified; the window is seated bare on the recess floor and sealed by an adhesive frame round its edge, which check 13 proves (D30, N2) |
| B15 | battery pads, lead keep-out, cell thickness | pad zone, pad size, joint height 2.4 and fixing adhesive 0.05 adopted; delivered thickness and swelling stay **open** (release gate) | two lead-and-joint solids, 0.96 mm from the tub, 0.15 below the free height |
| B16 | LCD tail geometry before release | **open** (release gate) | tail still representative; the Sharp drawing must allow a free tail of 10 mm plus the insertion depth (check 14: 6.5 / 10.0 / 15.3 mm at 20 / 35 / 60 deg of opening; the closed fold needs 3.8). Keep-out for the tail: N10 |
| B17 | (no such number in the rev C list) | - | - |
| B18 | grain opening: pot or coat; via keep-outs | adopted: clear potting to 0.05 inside the opening; `via_keepouts` | potting solid to z 0.05 (99.1 mm3) in interference, seal and mass checks. z 0.05 is treated as the level never to be passed, the fill target is z 0.10 (93.4 mm3): D32, N4; potting step 12 of the assembly sequence |
| B19 | hard gold, VBUS gating, firmware | ENIG at EVT, hard gold for production (**open** item). **VBUS gating: not adopted**: the cradle board gets a resettable fuse instead. Dry marker before docking stays an instruction | nothing mechanical |
| B20 | pad row 0.5 mm inboard or slot 1.8 | **not adopted**: pad row stays at y -17.0, slot 2.2 wide (system owner's decision) | slot unchanged; sheet land to the PCB edge 1.37 mm, fillet round the PCB edge as second barrier |
| B21 | crystal by strength; tape ring 28 / 25 | adopted: 0.13 tape ring 28 / 25; EVT mineral crystal declared NOT step-proof; production glass by strength (600 MPa) | ring 1.5 mm wide; README states the EVT crystal is not step-proof |
| B22 | no key, vented LCD frame, pre-cured hood gasket, drained nest | adopted (a to d) | D07, D13, D25, D26 closed. No key: every unit is tried dry in its own tub before the seal bead (lateral chain 0.17 to 0.28 RSS against the 0.25 gap, check 14). Gasket bead re-dimensioned to 0.5 x 0.33 (mechanical-only) |
| C | 0.2 mm thicker puck | **not adopted**: reserved remedy if step tests fail at EVT | not modelled |
| C | step-proof claim | EVT units are not step-proof; footstep tests are **open** test items | README section 12 |
| C | base plate material | FR-4 primary, PA12 alternative; thermal and humidity tilt drift to be MEASURED on both at EVT | README section 12 with the owner's acceptance targets; potted and unpotted units of each variant |
| C | upper field of view | accepted: 17.6 nominal, 15 at the tolerance limit; spigots moved | see B2, B3, N3 |
| C | grain opening | potted clear | see B18 |
| C | cradle latch | stays; cycle, creep and pull tests are **open** test items | check 7 unchanged (6.0 x, 2.05 % by FE) |
| C | adhesives | **open**: perimeter seal, ball potting, hood gasket, window adhesive, LCD frame, clear potting | classes only in the README |
| C | OVM7692 lens data | **open** | pupil position and diameter still assumed |

## B. New changes proposed after revision D

| # | YAML key / text | Now | Proposed | Why (numbers) | Dev. |
|---|---|---|---|---|---|
| N1 | `tub_keepouts.post_feet.locating`; DESIGN_SPEC "two 2.2 mm post feet" | 2.2 x 2.2 squares centred on (+-14.35, 10.8) | keep the squares as keep-outs and state the foot as built: `foot: {dx: 1.9, dy: 2.2, x_inner: 13.55}` | feet centred on the spigots would be 26.5 mm apart; the LCD glass that passes between them is 26.6 mm wide. With 0.25 clearance the inner faces are at x = +-13.55. Seat on the PCB 3.14 mm2 (round hole) and 2.44 mm2 (slot; rev C posts E: 1.52 / 0.96); total post seat 20.9 mm2 | D29 |
| N2 | `visor_window` | `t: 0.4` with the comment "0.15 below the visor face"; spec: "bonded into a recess" | add `sub_flush: 0.15`, `bond_line: 0.0`, `bond: "frame of thixotropic adhesive round the edge of the glass: side gaps, top bead 0.10, sill fillet 0.12; nothing behind the glass"` | recess 0.55 - glass 0.40 - 0.15 leaves no adhesive line (rev C had 0.05). A film wicked onto the top seat ends at the roof edge of the opening, where the upper field has 0.054 mm. If an adhesive line of 0.05 is wanted instead, the glass is 0.10 below the face | D30 |
| N3 | `cameras.field_required_deg.up_guaranteed` | 15.0 | 14.9, defined as "optics 0.2 mm high, spigot play not included"; or 14.6 if the play is to be included | optics 0.2 mm high: 14.97 deg (closed form 14.967); with the spigot fore-aft play of 0.075 mm added: 14.61 deg (stick top then visible from about 8.0 m instead of 7.8 m). Nominal 18.56, with the play alone 18.12 | D31 |
| N4 | `base_plate.grain_cavity.fill`, `base_plate.baffle` | "surface 0.05 below the base plane"; ring height only in text ("top flush with the potting") | `fill_surface_z: {never_above: 0.05, max: 0.20, below_ring_crest: [0.0, 0.10]}`; separate ring `height: 0.82` (for the 0.80 plate; lapped to plate + 0.02, +0.00 / -0.03), `adhesive: "black double-coated tape 0.13"`, `crest_z: [0.0, 0.15]` | a fill aimed at exactly 0.05 stands proud on half the units: 93.4 mm3 +-3 % is +-0.03 mm of level, 0.08 mm of plate thickness another 0.08 mm. Nominal crest z 0.05: surface 0.05 to 0.15, target 0.10 (25.0 + 68.3 mm3). A ring lapped to 0.82 whatever the plate would end at z -0.03 to 0.22; matched to the plate lot, 0.00 to 0.13 | D32 |
| N5 | `cover_glass` | tape ring ID only in the text of `bond` | add `bond_id: 25.0` | the die cut and the seal-land check (1.5 mm) use it | - |
| N6 | `base_plate` (FR-4 and alternative) | material text only | add `tolerances: {outline: 0.10, holes: 0.05, thickness_over_mask: 0.10}`, `thickness_accepted: [0.76, 0.90]`, `mask_relief_dia: 1.25`; alternative `thickness_accepted: [0.83, 0.92]` | on the fabrication drawing GL1-011. The lower limits keep 0.02 mm of epoxy between each ball and its land with the sheet at its thinnest and the ball set 0.02 high. The plate thickness is not in the seal-joint chain (joint 0.40 +-0.13 RSS from PCB, printed step and sheet) | - |
| N7 | `top_side_parts` U10 (nominal) | (-14.2, -12.2) | when the layout is done, about 0.3 mm toward the centre | its corner is 0.06 mm inside the board keep-in and 0.19 mm from ball-foot zone 2; legal, but without margin | - |
| N8 | board file (`*-mechanical.json`), not the YAML | keep-outs of the demonstration board are top-side only | export the three foot zones (bottom side, no track, no via) and the two via keep-outs as keep-outs | check 17 looks for them and can only warn when they are missing; copper itself is not in the file | - |
| N9 | `pcb.locating_holes.slot.length_x` | 1.8 (the spigot may move +-0.40 along the slot) | 2.2 (+-0.60) | spigot spacing error 0.2 to 0.3 on 28.7 mm, hole position 0.05 and 0.13 mm of thermal movement at 70 C sum to 0.38 to 0.48 mm. Cost: the slot then crosses the whole foot of post B-, seat 2.44 -> about 2.0 mm2. Alternative without a YAML change: require 28.7 +-0.15 between the spigots on GL1-010 | - |
| N10 | `tub_keepouts` | no keep-out for the LCD tail | add `lcd_tail: {half_w: 3.25, y: [-18.3, -16.8], max_part_height: 0.7}` (PROVISIONAL until B16) | the tail folds behind the mouth of J1: x +-3.0, y -18.2 to -16.8, underside 0.93 mm above the PCB. Check 17 keeps parts 0.2 mm from the modelled tail, but the layout contract has no rule and `check_layout.py` cannot see it | - |

Drawing-only requirements that follow from the tolerance chains and need no YAML change: on GL1-010 the seal face
(0.60) and the rim (1.55) from the post feet at +-0.1 (the rim relief of 0.25 survives the worst case only with that;
at the bureau's general tolerance the remedy would be a larger `envelope.rim_relief`).
