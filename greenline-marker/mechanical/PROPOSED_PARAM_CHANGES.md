# GL-1 mechanical: proposals and their disposition (rev D as amended)

`design/master_params.yaml` (rev D-EVT1, amended in place by the decisions N1 to N10 and the spec amendments E1 to E16) was
NOT edited by this package. Part A records what revision D did with every proposal (B1 to B22) and every decision (C) of
the rev C list. Part B records the decisions on the proposals N1 to N10 of the rev D mechanical review and where the model
stands on each. Part C lists only the NEW changes the mechanical model asks for after the amendment (N11 to N17 from
the first issue on the amended YAML; N12 and N13 revised and N18, N19 added after the review of that issue). Numbers
are from `export/check_report.md`; deviation IDs from `cad/deviations.py`. Nothing has been built.

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

## C. New changes proposed after the amendment

| # | YAML key / text | Now | Proposed | Why (numbers) | Dev. |
|---|---|---|---|---|---|
| N11 | `base_plate.thickness_accepted` (both plates); `base_plate.feet` | [0.76, 0.90] / [0.83, 0.92], "the lower limit keeps 0.02 mm of epoxy between each ball and its PCB land"; balls "grade 100 or better" | add `feet.dia_tol: 0.0127` (grade 100, to be confirmed on the supplier's certificate) and the rule "lower plate limit = 0.76 (0.83) + oversize of the measured ball lot"; or fix the lower limits at 0.78 / 0.84; or ask for grade 25 (+-0.0025) | a ball set to its protrusion on the gauge plate carries its diameter error at its top. Grade 100 at its upper limit (+0.0127 mm, ABMA figure AS REMEMBERED): 0.007 mm of epoxy at the lower FR-4 limit, 0.014 at the PA12 limit, against 0.02 required; grade 25: 0.018 / 0.025. No grade 25 ball in 316 was found at 1 mm (docs/SOURCING.md). Radial clearance of the largest ball in its dia 1.10 hole: 0.044 | D33 |
| N12 | `base_plate.legend`; `base_plate.feet` ("set on a gauge plate"); DESIGN_SPEC section 6 (E11) "a plate with three clearance pockets for the balls so that the base face seats" | `clear_of_features: 1.0` from holes, reliefs, opening and slot | add `seat_zones_clear_dia: 8.5` (no legend inside dia 8.5 round each ball foot), `edge_margin: 0.75`, `registration: 0.15`, `thickness_max: 0.03`, and the rule "every fixture or gauge that takes the outer face as its reference bears on bare mask inside the seat zones"; `feet`: "set on a gauge plate with three bosses"; spec text: "the base face seats on three pads round the pockets" | a legend print stands about 0.02 mm proud of the mask (0.03 allowed): 0.02 mm across the 24.5 mm foot triangle is 0.8 mrad, half of the 1.6 mrad the two-seat zero is there to find; under a flat ball gauge plate it would turn the protrusion of 0.10 +-0.02 into 0.10 to 0.13 and take 0.03 from the 0.02 mm of epoxy under the ball; under a depth gauge 1.2 mm from the grain opening it would shift the potting reading by 0.03 against a never-below limit of 0.05. Built: seat pads dia 7.0 (GL1-050 item 1), gauge-plate bosses dia 7.0 with the dia 0.60 gauge holes (item 3; legend 0.27 clear of the plate, 0.99 from a boss), bridge-gauge feet dia 6.0 / 1.6 (requirement). Zone = pad 7.0 + 2 x (0.6 location + 0.15 registration). The legend keeps 0.34 mm outside the zones and 0.49 mm or more from every footprint with its play. Alternative that needs none of this: a laser-marked legend | D34 |
| N13 | `cover_glass.retarder`; DESIGN_SPEC section 5 item 4 "there is 1.08 mm of air between the display and the glass, so nothing else moves" | type text only ("about 0.1 mm") | add `dia: 23.4`, `clocking_flat: {y: 11.5, length: 4.3}`, `thickness_max: 0.11` (film with its laminating adhesive), `placement: 0.25`; spec text: the air gap is 1.08 mm inside the dia 22 aperture only; the film axis is carried to the tub by the flat (edge mark on the crystal set to the nose groove) | modelled as an optional part: 0.98 mm to the display, 0.80 mm inside the bore of the tape ring, 0.70 mm beyond the aperture (0.50 at the flat). Centring chain: film on glass 0.25, glass in recess 0.25, tape ring in recess 0.25, so 0.75 against the bore and 0.50 against the aperture; left at the worst case 0.05 / 0.20 / 0.00 (flat), at RSS 0.37 / 0.35 / 0.15. (The dia 24.0 of the first issue had 0.50 to the bore, less than the chain, and no clocking feature on a round crystal in a round recess.) Outside the aperture the film lies over the roof ledge in the 0.13 mm tape gap: 0.03 mm nominal, 0.007 mm with the tape 10 % thin and the film 0.01 thick. A thicker film carries the glass off its tape: it is then cut to dia 21.5 and its edge is visible in the aperture | D35 |
| N14 | `top_side_parts` U11 (nominal) | (14.0, -12.2) | about 0.2 mm toward the centre when the layout is done, as was done for U10 | its corner is 0.312 mm from ball-foot zone 3 against the 0.3 mm of N7: 0.012 mm of margin | - |
| N15 | `base_plate.baffle.ring.matched_to`, `.adhesive` | "measured plate thickness + 0.02"; tape range only in text | `matched_to: "measured plate thickness + 0.15 - tape thickness"`, `tape: [0.10, 0.145]`, `print_height: 1.10` | E16: + 0.02 holds for a 0.13 tape only. Ring for the 0.80 plate: 0.85 with a 0.10 tape, 0.805 with 0.145 (0.82 with 0.13); over the accepted plates 0.735 to 0.95; crest z 0.00 to 0.13 in every case (window 0 to 0.15). The print file is now 1.10 high (was 0.97) so that the tallest ring still has 0.15 to lap | - |
| N16 | DESIGN_SPEC section 6 (E12) "up to about 1 degree" | text | "up to about 1.2 degrees left free; squared against the two rear ribs at assembly" | on the tub solid the glass can turn 1.19 deg (stops: a rear rib and the opposite hood rear wall; 0.95 deg would hold for continuous walls). Bedded on both rear ribs: 0 in the model, about 0.15 deg per 0.05 mm of step between the two rib faces (contact points 19 mm apart). Check 14 fails above 1.25 deg | - |
| N17 | `battery.fixing_adhesive_max` | 0.05 | 0.06, or name a tape of 0.05 or less | docs/SOURCING.md item 19: the transfer tapes named are about 0.058 mm. The air above a fully swollen cell is 0.15 mm before the adhesive: 0.10 left at 0.05, 0.09 at 0.06 | - |
| N18 | `cameras.field_required_deg.up_guaranteed` and its definition; `pcb.locating_holes` | 14.5, "the worst case with the optics 0.2 mm high AND the 0.075 mm spigot play against it"; no tolerance on the hole, the slot width or the spigot | EITHER `up_guaranteed: 14.0`, defined as "optics 0.2 mm high, the largest spigot fit (hole and slot width dia 1.15 +0.05, spigot dia 1.0 -0.05: 0.125) against it, roof at -10 C", with `locating_holes.dia_tol: 0.05` and `spigot_dia_min: 0.95` (a no-go ring gauge beside the dia 1.10 go gauge); OR keep 14.5 and hold the fit to 0.075 +0.02 (hole and slot width +0.02 / -0.03, spigots gauged 0.98 to 1.00) | the model meets the YAML as worded: 14.611 deg (closed form), margin +0.111 deg = 0.0063 mm of roof height = 0.024 mm of fore-aft play. That margin does not survive the tolerances the definition leaves out (check 4, table "what uses up the margin"): hole +0.05 on diameter 14.496; fit 0.125 14.38; roof 0.02 lower at -10 C 14.26; fit 0.125 and the cold roof 14.03; pupil dia 0.40 instead of the assumed 0.38 14.43; pupil 0.5 instead of 0.4 below the cube top 14.16. With 14.0 the stick top comes into view at about 8.4 m instead of 8.1 m on a worst-case unit, and the gate 2 target moves from +13.5 to +13.0 deg. The pupil numbers stay a release gate (lens data) under either choice | - |
| N19 | `base_plate.legend` | process text only | add `min_line: 0.15`, `min_text_height: 1.0`, `min_space: 0.15` (to be confirmed with the fabricator's quote) | at 1.0 mm text the font of the first issue left 0.05 mm between letters, which a 0.15 mm line fills in. The letter pitch is now glyph + line + 0.15 (0.967 mm at 1.0 mm text); check 15 measures the smallest clear space between two pieces of ink on the legend layer read back: 0.15. Cost: the two statement blocks hold 88 characters at 1.0 mm (four lines of eleven each), not 96 | - |

Requirements on other packages that follow from this pass (no YAML number):

- **Test gate 2** (docs/MANUFACTURING_PLAN.md station J3, docs/VALIDATION_PLAN.md O1): the target bar stands at +13.5 deg
  (guaranteed 14.5 less 1.0 for the placement of target and unit), with a reference bar at -13.5 deg. Both are fully
  clear on every in-tolerance unit, in both cameras (check 4). A bar at +17 deg passes only 66.8 % of the light on a
  unit at the tolerance limit and cannot be a pass / fail limit. (With N18 at 14.0: bars at +-13.0 deg.)
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
