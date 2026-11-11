# GL-1 mechanical: proposed changes to design/master_params.yaml and DESIGN_SPEC.md (rev B-EVT1)

`master_params.yaml` was NOT edited. Each item below is a shared number that the mechanical model could not honour,
honours only with a recorded deviation, or that a check showed to be too tight. Deviation IDs refer to
`cad/deviations.py` (printed at the end of `export/check_report.md`). All of this is PROVISIONAL: nothing has been built.

## A. Numbers in master_params.yaml

| # | YAML key | Now | Proposed | Why (numbers from export/check_report.md) | Dev. |
|---|---|---|---|---|---|
| 1 | `base_plate.pad_holes` | seven dia 2.2 holes, pitch 2.54 | describe the opening as one slot 17.44 x 2.2 (as modelled), or `dia: 1.7` | 2.2 mm holes on 2.54 pitch leave 0.34 mm webs, below the 0.8 mm print minimum. `check_layout.py` uses only the hole centres and diameter, so either form passes | D01 |
| 2 | `base_plate.feet` | 1.0 mm ball, 0.10 protrusion, 1.0 mm plate | `ball_dia: 0.8` with the same protrusion (0.30 mm skin), or a local 1.3 mm base thickness at the feet with PCB keep-outs, or press-fit 1.0 mm dowel pins; and state that the protrusion is set on a gauge plate, not by the print | the ball top is at z = 0.90, so a blind seat leaves 0.10 mm of skin. The modelled cone breaks through; about 2 mm2 per seat is thinner than 0.5 mm (check 5) | D02 |
| 3 | `pcb.z_bottom` and everything stacked on it | adhesive sheet between PCB and base at zero thickness | add `pcb.psa_thickness: 0.13` and either (a) `base_plate.thickness: 0.87` so that every other z stays, or (b) keep 1.0 and state that the tub rim sits 0.13 above the base plane (height 7.73, pads at 1.13, optical axis 5.74) | the posts hold the PCB top at tub z = 1.80, so a real 0.13 mm sheet pushes the base 0.13 mm down; the seal bead becomes 0.33 mm. (a) conflicts with item 2 unless the ball is smaller | D10 |
| 4 | `visor_window.z0`, `.h`, `.recess_depth` or `cameras.*.y` | z0 4.2, h 3.4, recess 0.55, camera y 15.6 | move both cameras and prisms 0.3 mm back (`y: 15.3`, `exit_face_y: 16.3`), or accept the thin strip | between the visor face (18.40) and the cube front (17.075) there is 1.325 mm; recess 0.55 + wall 0.8 + clearance 0.25 needs 1.60. The wall behind the recess in front of the cube is 0.525 mm over 3.5 mm2 per camera. Moving the cameras back costs LCD-to-cube clearance (0.63 now) | D04 |
| 5 | `visor_window.w` against the recess width (4.4, task statement) | 0.05 mm per side | recess = window + 0.5 (0.25 per side), or cut each window to its measured recess | below the 0.25 mm drop-in rule and below the MJF tolerance | D12 |
| 6 | `visor_window.opening.half_w` (and `visor_window.w`) | 1.65 (window 4.3) | `half_w: 2.0`, `w: 5.0`, recess 5.5 | exact ray trace: the full pupil bundle is +-1.622 wide at the aperture plane for the +-26 deg field, 0.028 mm inside the opening. With the PCB displaced by its own 0.15 mm play the field is clipped at 24.0 deg, with 0.35 mm at 20.5 deg and transmission at the worst field point falls to 12 % (check 4, sensitivity table) | - |
| 7 | `visor_window.opening.z0` (and `visor_window.z0`, `.h`) | sill 4.6 (window from 4.2, h 3.4) | sill 4.3, window from 3.9, h 3.7 | the bundle clears the sill by 0.019 mm at the -15 deg field edge; optics 0.2 mm low clip the lower field at 11.7 deg. The thin strip of item 4 moves down with the recess but stays in front of the cube | - |
| 8 | `roof.underside_z` / upper field | 6.8; upper field +17.6 deg | no change proposed; record that the upper field edge has 0.054 mm margin | the top of the opening is the roof underside. Optics 0.2 mm high clip the upper field at 15.0 deg. Curing this needs a thicker puck, a lower optical axis or a smaller upper field | - |
| 9 | `pcb.radius` or `tub_ledge.r_inner` / `base_plate.seal_land.r_inner` | 21.2 / 21.35 | `pcb.radius: 21.1` | PCB edge to seating ledge is 0.15 mm, below the 0.25 mm rule | D12 |
| 10 | new: PCB-to-tub locating features | none: the PCB is located in x, y only by the 0.15 mm gap of item 9 | add two locating features near the cameras, for example spigots on the two posts E (centres (+-4.2, 14.55)) entering PCB holes, and share them in the YAML | this play is what consumes the optical margin of items 6 to 8 | - |
| 11 | `tub_ledge.r_inner` against `lcd.glass` | ledge 21.35; glass rear corners at r = 21.43 | accept the biased insertion (0.12 mm nominal clearance), or relieve the ledge locally to r 21.7 over +-3 deg at the two rear glass corners (costs seal-land width there), or move the glass 0.3 mm forward if the Sharp drawing allows | the glass cannot drop straight through the ledge ring | D11 |
| 12 | `vent.location` | about x = 17, y = -3 | x = 17.9, y = -3.0 | a 5 mm disc at x = 17 overlaps the thick roof ring (r 15.05) that carries the cover-glass recess | D08 |
| 13 | `bottom_side_parts.photodiode` / baffle | ring "about 5.4" inner dia (task statement) | record baffle inner dia 5.91, wall 0.8, outer dia 7.51, spokes at 90 / 225 / 315 deg, so that `check_layout.py` can check the LED ring (r 5.2) against it | the 4.8 x 2.5 photodiode has a 5.41 mm diagonal | D03 |
| 14 | new: `tub_keepouts` for the PCB layout | not in the YAML | list the eight post feet (1.6 x 1.6 mm, centres (+-15.4, 1.8), (+-14.35, 10.8), (+-6.5, -18.6), (+-4.2, 14.55)) and the hood skirts (x = camera x +-1.985 to 2.785, y 13.75 to 17.6, parts below 0.95 mm; front pad y 17.325 to 17.6) and have `check_layout.py` test every part and passive against them | passives are not in the YAML, so the mechanical checks cannot see a clash with them | - |
| 15 | new: `cradle` block | cradle numbers exist only in `mechanical/cad/params.py` | add pad height above the base plane (1.13 with the sheet), pin working height 5.82, cradle PCB top z = -4.69, pin row y = -17.0, nest centre (0, -2.3) | the cradle PCB layout needs them | D15, D17 |

## B. Text in DESIGN_SPEC.md

- Section 3, charging contacts: "a puck placed 180 degrees round in the cradle for flip calibration touches no pins" is not
  achievable with spring pins that stand 1.13 mm above the seat: at 180 degrees every pin bears on the solid base plate
  (check 7: no pin over a pad, the pad slot, the grain opening or a ball seat; nearest opening 1.44 mm). Reword to "touches
  no pad", or specify retracting pins.
- Section 5, part 5 (cradle): add the hold-down. Seven pins at about 0.59 N give about 4.1 N against a marker weight of
  about 0.11 N; about 9 N at the marker centre is needed to keep the three ball feet on the plate (check 7).
- Section 5, part 1 (tub): "light-tight snouts" is not met: the hood rear wall cannot pass the camera cube, so a slit of
  about 0.25 to 0.35 mm remains above the cube at the rear (D13).
- Section 5, part 2 (base plate): "seven 2.2 mm pad holes" becomes one slot (item 1); "three ball seats" need a finishing
  operation (item 2).
- Section 5, stack table: add the adhesive sheet (item 3).

## C. Decisions for the system owner (not YAML numbers)

- Cradle hold-down concept (README open issue 1).
- Whether the flip calibration may displace the marker centre by 4.6 mm between 0 and 180 degrees (D15); if it must turn
  about its own centre a different locating scheme, for example a removable stop, is required.
- Adhesive selection and surface preparation for vapor-smoothed PA12 (README section 8).
- Lens data for the OVM7692 (entrance-pupil position and diameter): the optical checks assume 0.4 mm below the cube top
  and 0.38 mm; with these values the 2.0 mm prism clips 2.3 % of the pupil at the horizontal field edge.
