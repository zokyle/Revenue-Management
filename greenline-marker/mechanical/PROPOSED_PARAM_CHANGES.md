# GL-1 mechanical: proposals and their disposition (rev E)

`design/master_params.yaml` is at rev E-EVT1. It was NOT edited by this package. Part A records what revision D did
with every proposal (B1 to B22) and every decision (C) of the rev C list. Part B records the decisions on the
proposals N1 to N10 of the rev D mechanical review. Part C records the disposition of the proposals N11 to N19, which
were decided as the spec amendments E17 to E22 and entered in the YAML at revision letter E: **all nine are closed**,
and so are the deviations D33, D34 and D35 that carried them. Part D lists what this package asks for after rev E
(nothing that blocks the model; no standing deviation needs a YAML change). Numbers are from `export/check_report.md`;
deviation IDs from `cad/deviations.py`. Nothing has been built.

Parts A and B are the record of rev D and of the amendment: figures in them that rev E moved are restated in part C
(guaranteed field 14.0, plate limits 0.78 / 0.84, marker mass, nearest part to a foot zone, tail fold).

## A. Disposition of the rev C proposals and decisions

Unchanged in substance from the previous issue; figures that the amendment moved are given as they stand now.

| # | Rev C proposal | Revision D | In the model now |
|---|---|---|---|
| B1 | free height above the PCB in `tub_keepouts` | adopted: `free_height_above_pcb: 2.55`, used by `check_layout.py` | check 12 proves the tub clear below z 4.35; D22 closed |
| B2 | `cameras.field_required_deg`; decide the upper field | adopted: h 26, up 17.6, down 8.0; the upper edge is accepted. `up_guaranteed` was 15.0 and is 14.5 since N3 | checks 3 and 4 read the YAML. Guaranteed case (optics 0.2 high and spigot play against it): 14.61 deg against 14.5, strict comparison (N3) |
| B3 | keep the 0.075 fit, move the spigots to posts B | adopted: round dia 1.15 at (14.35, 10.8), slot at (-14.35, 10.8), 1.15 x 1.8, lengthened to 2.2 by N9 | spigots under posts B, 28.7 apart: +-0.100 sideways, +-0.075 fore-aft, +-0.30 deg yaw at a camera (rev C: 0.094 / 0.179 / 1.02); D19 accepted |
| B4 | straight camera openings | adopted (spec text, `visor_window.opening`) | unchanged; D05 closed |
| B5 | cradle numbers into the YAML | adopted as modelled (`cradle` block) | the model reads the block; derived values (overall height 22.63, PCB top -4.855, hook overlap 1.10) are asserted; D20, D25 closed |
| B6 | ball potting, PCB land and keep-out, no part over a foot | adopted: dual-cure or two-part epoxy, `epoxy_dome_max`, `backfill`, land dia 1.6 in a dia 2.5 zone, `foot_zones`, U8 moved to (-11.0, 11.6) | check 10: no post foot and no soldered part over a foot zone; nearest part now U11 at 0.312 mm (0.3 required since N7); D27 closed |
| B7 | pad plane = copper face 0.965; float 0.25 | adopted | pins 5.82 on z 0.965, 6.07 floated; D21, D28 closed |
| B8 | hold-down proof depends on pin force, friction, modulus | no number; carried as test items | README section 12 (latch cycle, creep, pull) |
| B9 | rim relief 0.25 | adopted (`envelope.rim_relief`) | D23 closed |
| B10 | vent pad 0.3 with drain grooves | adopted (`vent.location`) | D24 closed |
| B11 | baffle ring dia 6.6 / 8.2 | adopted | 0.594 to the photodiode, 0.604 to the LEDs; D03 closed. Height and level of the separate ring: N4, E16 (D32 closed) |
| B12 | larger feet under the locating posts | adopted: `post_feet.locating` 2.2 x 2.2 at posts B; the foot as built is stated since N1 | built 1.9 x 2.2 (D29 closed); seat 3.14 mm2 (round hole) and 2.15 mm2 (over the 2.2 mm slot) |
| B13 | base plate FR-4, stainless or PA12 | FR-4 0.80 + 0.20 sheet is primary; PA12 0.87 + 0.13 stays as the alternative, compared at EVT. **Stainless: not adopted** (the spec gives the reasons for FR-4: same expansion as the PCB it is laminated to, flat, drilled holes to 0.05 mm, from the PCB fabricator) | both plates and both sheets are built, exported and checked in one build (checks 15 and 16); seal joint 0.40 / 0.33 (it does not depend on the plate thickness); Gerber / Excellon data for the FR-4 plate, now with a legend layer (E10); plates sorted to 0.76 to 0.90 / 0.83 to 0.92 (N6) |
| B14 | windows and cover glass below flush | adopted: windows 5.0 x 3.25 x 0.40, 0.15 below face and top; crystal 0.12 below flush on a 0.13 tape | as specified; the window is seated bare on the recess floor and sealed by an adhesive frame round its edge, which check 13 proves (N2; D30 closed) |
| B15 | battery pads, lead keep-out, cell thickness | pad zone, pad size, joint height 2.4 and fixing adhesive 0.05 adopted; delivered thickness and swelling stay **open** (release gate) | two lead-and-joint solids, 0.96 mm from the tub, 0.15 below the free height |
| B16 | LCD tail geometry before release | **open** (release gate) | tail still representative; the Sharp drawing must allow a free tail of 10 mm plus the insertion depth (check 14: 6.5 / 10.0 / 15.3 mm at 20 / 35 / 60 deg of opening; the closed fold needs 3.8). Keep-out for the tail: in the YAML since N10 |
| B17 | (no such number in the rev C list) | - | - |
| B18 | grain opening: pot or coat; via keep-outs | adopted: clear potting; `via_keepouts` | potting solid to z 0.05 (99.1 mm3) in interference, seal and mass checks; target z 0.10 (model 93.36 mm3, YAML 93.4); the levels are YAML numbers since N4; potting step 12 of the assembly sequence |
| B19 | hard gold, VBUS gating, firmware | ENIG at EVT, hard gold for production (**open** item). **VBUS gating: not adopted**: the cradle board gets a resettable fuse instead. Dry marker before docking stays an instruction | nothing mechanical |
| B20 | pad row 0.5 mm inboard or slot 1.8 | **not adopted**: pad row stays at y -17.0, slot 2.2 wide (system owner's decision) | slot unchanged; sheet land to the PCB edge 1.37 mm, fillet round the PCB edge as second barrier |
| B21 | crystal by strength; tape ring 28 / 25 | adopted: 0.13 tape ring 28 / 25; EVT mineral crystal declared NOT step-proof; production glass by strength (600 MPa) | ring 1.5 mm wide (`bond_id` in the YAML since N5); README states the EVT crystal is not step-proof |
| B22 | no key, vented LCD frame, pre-cured hood gasket, drained nest | adopted (a to d) | D07, D13, D25, D26 closed. No key: every unit is tried dry in its own tub before the seal bead (lateral chain 0.17 to 0.28 RSS against the 0.25 gap, check 14). Gasket bead 0.5 x 0.33 (mechanical-only) |
| C | 0.2 mm thicker puck | **not adopted**: reserved remedy if step tests fail at EVT | not modelled |
| C | step-proof claim | EVT units are not step-proof; footstep tests are **open** test items | README section 12 |
| C | base plate material | FR-4 primary, PA12 alternative; thermal and humidity tilt drift to be MEASURED on both at EVT | README section 12 with the owner's acceptance targets; potted and unpotted units of each variant |
| C | upper field of view | accepted: 17.6 nominal; guaranteed figure 14.5 with its definition since N3; spigots moved | see B2, B3 |
| C | grain opening | potted clear | see B18 |
| C | cradle latch | stays; cycle, creep and pull tests are **open** test items | check 7 unchanged (6.0 x, 2.05 % by FE) |
| C | adhesives | **open**: perimeter seal, ball potting, hood gasket, window adhesive, LCD frame, clear potting | classes only in the README |
| C | OVM7692 lens data | **open** | pupil position and diameter still assumed |

## B. Disposition of the proposals N1 to N10 (decided as in the amended YAML)

"Override removed" means the number no longer lives in `cad/params.py` (`MECH`): the model reads the YAML and `params.py`
asserts that the two agree; the build stops if they do not.

| # | Proposal of the rev D review | Decision in the YAML | In the model now | Dev. |
|---|---|---|---|---|
| N1 | state the feet of posts B as built | `tub_keepouts.post_feet.locating.foot: {dx: 1.9, dy: 2.2, x_inner: 13.55}`; the 2.2 squares stay the layout keep-outs | asserted (feet 1.9 x 2.2, inner faces at x = +-13.55); check 12: feet inside their squares, 4.18 of 4.84 mm2 | D29 closed |
| N2 | window seated bare, sealed round its edge | `visor_window.sub_flush: 0.15`, `bond_line: 0.0`, `bond: "frame of thixotropic adhesive ... top bead 0.10, sill fillet 0.12 x 0.12; nothing behind the glass"` | override removed (`bond_line`); sub-flush, top bead and sill fillet asserted against the YAML (the two bead numbers are read from its text); check 13 proves the frame closes the opening | D30 closed |
| N3 | guaranteed upper field 14.9 (no play) or 14.6 (with play) | `up_guaranteed: 14.5`, DEFINED as the worst case with the optics 0.2 mm high AND the 0.075 mm spigot play against it | check 4 compares the with-play figure strictly, on both cameras (camera L 14.61, camera R 14.61; closed form 14.611), margin +0.11 deg = 0.006 mm of roof or optics height; without the play 14.97; nominal 18.56. No recorded shortfall is left: below 14.5 on either camera the check fails (self-test: a roof 0.01 mm low over either opening is caught). The figure is that of the NOMINAL fit, as the YAML words it: see N18 | D31 closed |
| N4 | potting levels and separate ring as numbers | `fill_surface_z: {never_below: 0.05, target: 0.10, max: 0.20, below_ring_crest: [0.0, 0.10]}`; `baffle.ring: {height: 0.82, height_tol: [-0.03, 0.0], matched_to, adhesive, crest_z: [0.0, 0.15]}` | overrides removed; asserted: target = middle of the window for the nominal crest (0.10), ring 0.82, crest window, tape inside its range; potting volume to the target 93.36 mm3 against the YAML 93.4 (check 2 row); crest z 0.00 to 0.13 | D32 closed |
| N5 | tape-ring bore as a number | `cover_glass.bond_id: 25.0` | override removed; die cut GL1-033 and the seal-land check (1.50 mm) use it | - |
| N6 | plate tolerances, accepted thickness, mask relief | `tolerances: {outline: 0.10, holes: 0.05, thickness_over_mask: 0.10}`, `thickness_accepted: [0.76, 0.90]`, `mask_relief_dia: 1.25`; alternative `thickness_accepted: [0.83, 0.92]` | overrides removed; drawing GL1-011, mask layers (dia 1.25 read back) and the stack arithmetic read them. The lower limits keep 0.02 mm of epoxy under a ball of exactly dia 1.0; with a grade 100 ball at its upper diameter limit they do not: see N11 | D33 (new) |
| N7 | U10 0.3 mm inboard | `foot_zones.part_margin: 0.3`; U10 at (-13.9, -12.2) | check 10 now REQUIRES 0.3 mm between a soldered part and a foot zone (battery exempt): U10 0.378, U1 0.45, U11 0.312 (see N14); check 17 applies the same margin to the real board | - |
| N8 | foot zones and via keep-outs in the board file | for the board (not the YAML) | unchanged: check 17 looks for them in the board file and warns when they are missing; no board file exists yet | - |
| N9 | slot 2.2 long | `pcb.locating_holes.slot.length_x: 2.2` | PCB solid, DXF GL1-040 (read back from disk: 2.20 x 1.15 at x -14.35) and the synthetic board follow. Check 14 measures the slot on the PCB solid: +-0.60 along the slot against 0.378 to 0.478 needed, margin 0.12 to 0.22 mm; a shorter slot now FAILS the check. Cost as predicted: the slot crosses the whole foot of post B-, which seats on two strips 0.525 mm wide, 2.15 mm2 (was 2.44); total post seat 20.6 mm2 (was 20.9) | - |
| N10 | keep-out for the LCD tail | `tub_keepouts.lcd_tail: {half_w: 3.25, y: [-18.3, -16.8], max_part_height: 0.7, basis: provisional}` | check 12: the representative tail lies inside the zone (0.25 in x, 0.088 at the rear) and its underside (0.925 above the PCB) is 0.225 over a part of the allowed height (0.2 needed); check 17 fails a part taller than 0.7 in the zone (J1 exempt) and still keeps 0.2 mm to the modelled tail | - |

Also amended: `top_side_parts` U9 is the BQ25101 (1.6 x 0.9 x 0.5 mm, was a 3 x 3 x 1.45 box): the part box follows; marker
12.23 g (was 12.25), cavity 4218 mm3 (was 4205). E8 (ball material), E9 (retarder film), E10 (legend), E11 (two-seat zero),
E12 (display rotation) and E16 (baffle tape) are worked into the model, the checks, the drawings and the README.

## C. Disposition of the proposals N11 to N19 (decided as E17 to E22, entered at rev E): all closed

"Asserted" means `cad/params.py` reads the number from the YAML and the build stops if the model disagrees; the former
`MECH` copies of these numbers are gone.

| # | Proposal of the review of the amended rev D | Decision (amendment; YAML rev E) | In the model now | Status |
|---|---|---|---|---|
| N11 | ball diameter tolerance against the lower plate limit | **E20**: `base_plate.thickness_accepted: [0.78, 0.90]`, alternative `[0.84, 0.92]`; `feet.dia_tol: 0.0127` (`dia_tol_basis: provisional`, as remembered from the ball standard) | asserted: the YAML limit must be the least one that keeps 0.02 mm of epoxy under a ball at the UPPER diameter limit (computed 0.78 / 0.84; for a nominal ball 0.76 / 0.83). Check 2 now REQUIRES the oversize-ball row: 0.027 mm (PA12 0.024) against 0.02; it was a recorded shortfall of 0.007 / 0.014 | closed; D33 closed. Open with it: the tolerance itself (release gate) |
| N12 | legend-free seat zones; fixtures on bare mask | **E18**: `base_plate.legend`: `seat_zones_clear_dia: 8.5`, `edge_margin: 0.75`, `registration: 0.15`, `thickness_max: 0.03`, `fixture_rule`; `feet`: gauge plate on three bosses; spec section 6: seat plate on three pads | asserted (zone = pad 7.0 + 2 x (0.6 + 0.15) = 8.5; boss and bridge foot fit in it). Checks 15 and 18: legend 0.34 outside the zones, 0.49 or more from every fixture footprint, 0.27 clear of the gauge plate | closed; D34 closed |
| N13 | retarder film size, flat, thickness | **E19**: `cover_glass.retarder`: `dia: 23.4`, `clocking_flat: {y: 11.5, length: 4.3}`, `thickness_max: 0.11`, `placement: 0.25` | asserted (flat y 11.5, length 4.31 computed against 4.3, film 0.10 + 0.01). Check 2: 0.05 / 0.20 / 0.00 left after the centring chain at its worst case (bore / aperture / flat) | closed; D35 closed |
| N14 | U11 about 0.2 mm inboard | settled by the layout: U11 (now the 5-pin LP5907MFX-3.3, E26) stands at (13.33, -12.60) | part list regenerated from the routed board (88 entries). Check 10: nearest soldered part to a ball-foot zone is C23 at 0.888 mm (zone 3), R2 at 0.93 (zone 1); 0.3 required. The self-test now seeds U11 0.20 mm from zone 3 | closed |
| N15 | ring-height rule with the tape | **E21**: `baffle.ring`: `matched_to: "measured plate thickness + 0.15 - tape thickness"`, `rule_offset: 0.15`, `tape: [0.10, 0.145]`, `nominal_tape: 0.13`, `print_height: 1.10` | asserted, all five (the rule offset is sheet thickness - never_below; the print height is the tallest finished ring + 0.15 to lap). Finished rings over the accepted plates: **0.755 to 0.95** (the 0.735 of the proposal belonged to the 0.76 plate limit, see part D item 1) | closed |
| N16 | display rotation "about 1.2 degrees" | **E22**: `lcd.rotation_in_pocket_max_deg: 1.2` | check 14 computes 1.19 deg on the tub solid, requires agreement with the YAML within 0.05 deg and still fails above 1.25 | closed |
| N17 | cell fixing adhesive 0.06 | **E22**: `battery.fixing_adhesive_max: 0.06` | read from the YAML; 0.09 mm of air left above a fully swollen cell (0.15 before the adhesive) | closed |
| N18 | guaranteed upper field restated on the loosest fit | **E17**: `up_guaranteed: 14.0`; `cameras.up_guaranteed_case: {optics_high: 0.2, locating_fit: 0.125, roof_temperature_C: -10, model_deg: 14.03}`; `pcb.locating_holes`: `dia_tol: [0, 0.05]`, `spigot_dia_tol: [-0.05, 0]`, `spigot_dia_min: 0.95`, `fit_nominal: 0.075`, `fit_max: 0.125`; `gate2_bars_deg: [13.0, -13.0]` | asserted (fits, no-go size, the case, the bars). Check 4 now traces THAT case on both cameras and compares strictly: camera L 14.03, camera R 14.03, closed form 14.033 (must reproduce `model_deg` within 0.01), margin +0.03 deg = 0.002 mm of roof height. At the nominal fit and 20 C: 14.611. The roof drop at -10 C (0.02 mm) is this package's estimate: the YAML names the temperature, not the drop (part D item 3). With another pupil the defined case gives 13.86 (dia 0.40) or 13.61 (0.5 below the cube top): release gate, check 4 warning | closed; D31 re-closed on E17 |
| N19 | legend print rules | **E18**: `legend`: `min_line: 0.15`, `min_space: 0.15`, `min_text_height: 1.0`, `statement_block_chars: 88`, `print_rules_basis: provisional` | asserted / measured: check 15 reads the legend layer back: least space 0.15, least text 1.0, capacity 88 characters (compared with the YAML figure) | closed; the rules stay PROVISIONAL until the fabricator's quote |

Also entered at rev E and worked into this package (not proposals of this package):

| Amendment | YAML | In the model now |
|---|---|---|
| E24 J1 0.5 mm to the rear; tail zone from the mouth | `top_side_parts` J1: body centre (0, -14.5), 8.1 x 5.6 x 2.0, `anchor` (0, -12.9), `mouth_y` -17.3; `tub_keepouts.lcd_tail.y: [-21.1, -17.3]`; `battery.board_keepout_notch` | the mouth is 0.50 BEHIND the rear edge of the glass (-16.80). The representative tail is re-modelled: 0.85 back from the glass edge at z 4.775 (over the rear of the connector, 0.90 above its top), one fold of radius 0.99 wholly behind the mouth, 0.35 forward into it; rearmost point y -18.71; free length 4.30 mm (was 3.80). Check 2: 0.70 to the tub (0.25 now required; rev D required only no contact). Check 12: fold inside the zone (0.25 in x, 2.39 at the rear), 0.225 over a 0.7 mm part, upper run over J1 only. Check 17 compares J1 by its body box and, separately, by its anchor |
| E36 cradle board 1.0 mm | `cradle.pcb.thickness: 1.0`; `cradle.pins.tail_length: 1.34` (PROVISIONAL) | top face unchanged at z -4.855 (measured on the solid and on the pocket ceiling), underside z -5.855; pins 5.82 working / 6.07 floated as before; tail 0.34 through the board (0.2 required for a fillet; rev D: 0.26 inside the hole). Screws restated: 4 x M2 x 4 (was M2 x 5), drill dia 1.6 x 3.2, 3.0 mm of thread; 0.47 mm of material left above the two front holes: new recorded deviation D36 |
| E25 / E26 parts | U12 LM66100DCKR SC-70-6 at (-7.25, -12.85), 1.1 high; U11 LP5907MFX-3.3 SOT-23-5 1.6 x 2.9 x 1.45 (the task text names the diode "D17": on the board and in the YAML it is U12, D17 is retired) | bodies in the PCB solid with the other 85 fitted top-side bodies of the routed board (R14, not fitted, is left out of the solid and still tested in checks 10 and 17) |

## D. After rev E: what this package asks for (none blocks the model)

| # | Item | Now | Asked | Why |
|---|---|---|---|---|
| 1 | YAML comment at `base_plate.baffle.ring` (and DESIGN_SPEC section 5 item 3 if it repeats it): "0.735 to 0.95 over the accepted plates" | comment text | "0.755 to 0.95" | 0.735 = 0.76 + 0.15 - 0.145 - 0.03 was computed on the old lower plate limit; with 0.78 (E20) the least finished ring is 0.755. **DONE (final audit of rev E, 2026-11-18): the YAML comment says 0.755 to 0.95** |
| 2 | `tub_keepouts.lcd_tail.y[0]` | -21.1 (the whole strip to the board edge) | may be shortened to about -19.2 once the Sharp tail drawing is in hand | the modelled fold reaches y -18.71 (1.41 of the 3.8 mm zone); nothing on the routed board is in the zone, so there is no cost in keeping it |
| 3 | `cameras.up_guaranteed_case` | names the roof temperature (-10 C) | add `roof_drop: 0.02` (mm, estimate) or state that the drop is the mechanical package's | the guaranteed figure depends on this number as much as on the fit: 14.26 instead of 14.61 at the nominal fit |
| 4 | `cradle.pins` | `tail_length: 1.34` only | tail diameter and hole diameter (model 0.76 in 0.90; the electrical footprint uses 0.635 in 0.80) | the two packages hold different PROVISIONAL numbers; neither is from the Mill-Max drawing. Check 19 cannot compare them: the board file does not list plated holes |
| 5 | cradle screws (spec / sourcing) | "four screws" | M2 x 4 thread-forming, drill dia 1.6 x 3.2 | follows from the 1.0 mm board (D36: skin above the two front holes 0.47 mm; remedy if the pull test fails: move the two front screws 2 mm outboard of the basin, a cradle change). `docs/sourcing.csv` names M2 x 4 since its revision 4; no part number for a 4 mm screw has been seen |

Requirements on other packages that follow from this pass (no YAML number):

- **Test gate 2** (docs/MANUFACTURING_PLAN.md station J3, docs/VALIDATION_PLAN.md O1): since E17 the target bar stands at
  +13.0 deg (guaranteed 14.0 less 1.0 for the placement of target and unit), with a reference bar at -13.0 deg (rev D:
  +-13.5). Both are fully clear on every in-tolerance unit, in both cameras (check 4). A bar at +17 deg is vignetted on
  in-tolerance units (55.8 % of the light on a unit at the tolerance limit) and cannot be a pass / fail limit.
- **Firmware**: the level zero must be readable with no pin on the pads (a spring pin pushes with 0.59 N, the marker
  weighs about 0.12 N): either from the menu, or armed through the pogo fixture and run after the marker has come to
  rest on the seat plate. A display test line is needed for the rotation measurement of E12. Test gate 1 reads both
  cell thermistors; the dark offset of the photodiode amplifier is read on the bare board in step 11a.
- **Compliance** (docs/COMPLIANCE.md row 5): the two reserved statement blocks hold 88 characters at 1.0 mm text
  height with 0.15 mm between letters. The short FCC sentence fits; the full two-condition statement (about 240
  characters) does not.
- **Manufacturing plan** (docs/MANUFACTURING_PLAN.md 5.2, 5.3, 6.2, 7.3): fixture 1 is a gauge plate with three bosses,
  not a flat plate, and its clamp a weight with three feet; fixture 16 ("depth gauge") is the bridge gauge on three
  feet round the balls for stations B3, B4, J1 and J2; the potting mask is an annulus dia 15 to 24; station B3 reads
  the photodiode dark offset before the ring goes on; station B5 cleans before the thermistor dabs, waits for them to
  gel and marks the serial number after gate 1; station J6 soaks the unit before the second leak test and before the
  zeros; the calibration seat plates give 0 and 180 degrees only, so the four-position zero of 6.2 and 6.7 needs
  another fixture.
- **Six-face fixture**, **bridge gauge**, **film lamination nest**, **four-position location**: not designed (README
  section 2, fixtures).

Drawing-only requirements that follow from the tolerance chains and need no YAML change: on GL1-010 the seal face
(0.60) and the rim (1.55) from the post feet at +-0.1 (the rim relief of 0.25 survives the worst case only with that;
at the bureau's general tolerance the remedy would be a larger `envelope.rim_relief`).
