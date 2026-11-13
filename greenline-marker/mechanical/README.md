# GreenLine GL-1 mechanical design package (parameters rev D-EVT1 as amended, drawings rev D-EVT1.2)

**Status: PROVISIONAL, not released. Nothing in this folder has been built, printed, fabricated or measured.**
Every number comes from the CAD model, which is driven by `../design/master_params.yaml` (rev D, amended in place by
the decisions N1 to N10 and the spec amendments E1 to E16). "Computed" below means
a boolean, ray or sampling computation on the solids of this build; "estimate" means arithmetic on assumed inputs;
nothing is "tested". Where the model differs from the specification the difference is a numbered deviation
(section 11); where a shared number should change it is in `PROPOSED_PARAM_CHANGES.md`. `master_params.yaml` was not edited.

The package is for three readers: a PCB fabricator (the routed FR-4 base plate, drawing GL1-011), a US 3D-printing
bureau (tub, cradle, baffle ring and the alternative PA12 base plate) and the person who assembles the first units.
Read "Open issues, release gates and test items" (section 12) before ordering anything. The four that matter most:
the EVT units are **not step-proof**; the seal, every adhesive and the cradle latch are calculated or chosen by class,
not tested; the upper edge of the camera field has almost no tolerance margin (accepted: the YAML guarantees 14.5
degrees with the optics 0.2 mm high and the spigot play against it, and the model gives 14.61 there for the nominal
spigot fit; the hole tolerance of the board alone uses that margin up, section 5); and the tilt
drift of the PCB / base laminate with temperature and humidity has to be **measured** on both base-plate variants at EVT.

![assembled marker](renders/GL1_render_a_front_top.png)

## 1. One command

```
cd greenline-marker/mechanical
python3 cad/build.py              # about 7 minutes; exits non-zero on any failed check, drawing, render or stale README number
python3 cad/build.py --selftest   # seeds 62 defects and confirms that each check catches its defect (about 20 minutes)
```

`build.py` regenerates the solids, STEP and STL files, the resolved parameters, the check report, the drawings
(PDF, SVG, DXF, Gerber / Excellon data of the FR-4 plate, PNG previews) and the renders, and then reads the fabrication
files, the PCB outline DXF and two die cuts back from disk and compares them with the model. Last, it compares the
numbers this README states in words (masses, the guaranteed field, legend capacity, film size, the standing deviations
and others: `readme_facts` in `cad/build.py`) with the build and fails if one is stale. Options: `--no-export`, `--no-drawings`, `--no-renders`, `--summary`.
It needs python3 with cadquery 2.8, numpy, scipy, shapely, matplotlib, pyyaml and ezdxf; `pdftoppm` for the previews;
node with Playwright (headless Chromium) and three.js 0.160 for the renders (`npm install three@0.160.0` in
`tools/render` if three.js is not found; `node_modules` is not committed). Headless WebGL occasionally loses its
context, so every render is composed from the drawing buffer, checked for a non-empty frame and retried up to three
times; a blank picture fails the build.

| Path | Content |
|---|---|
| `cad/params.py` | loads the YAML, holds the mechanical-only choices (`MECH`), derives every dependent dimension once; the base-plate material is a parameter (`BASE_VARIANTS`, `base_variant()`); asserts that the YAML and the model agree (among them every decision N1 to N10) |
| `cad/parts.py` | one function per part, each returns a CadQuery solid in the assembly frame; base plate, adhesive sheet, seal joint, pottings follow the active base variant |
| `cad/assembly.py` | named, coloured parts of the primary build and of the alternative build (suffix `_pa12`); allow-list of intended contacts; STEP / STL export; print orientations |
| `cad/checks.py` | the eighteen checks; `cad/optics.py` the exact ray trace and its closed-form cross-check; `cad/geom.py` sections, projections, ray casting |
| `cad/legend.py` | the legend of the outer face of the FR-4 base plate (E10): placeholder blocks, a small stroke font with its letter-spacing rule, the keep-clear zones, the footprints of the fixtures that bear on the face |
| `cad/fabdata.py` | Gerber and Excellon files of the FR-4 base plate (profile, two mask layers, the legend layer of the outer face, drill), written from the plate solid and from `legend.py`, and the readers check 15 uses to read them back |
| `cad/board_import.py` | check 17: reads the board toolchain's `*-mechanical.json` and checks the real circuit board against the YAML and the tub |
| `cad/holddown.py`, `cad/latchfe.py` | cradle hold-down: beam model of the latch and plane-strain finite-element model of its section |
| `cad/deviations.py` | the recorded deviations with their status (text is built from the parameters) |
| `cad/drawings.py`, `cad/drawlib.py` | dimensioned drawings from projections and true sections of the solids; DXF profiles |
| `cad/renders.py`, `tools/render/render.js` | renders of the exported STL meshes |
| `cad/selftest.py` | negative tests of the checks |
| `export/step/` | `GL1_assembly.step` (48 named parts, marker with the FR-4 plate seated in the cradle), `GL1_marker_only.step`, `GL1_marker_only_pa12_base.step` (the alternative build), one STEP per part (59: both base-plate sets, the optional `retarder_film`, the fixtures `cal_seat_plate`, `cal_plain_plate` and `gauge_plate`), and `tub_print`, `cradle_print`, `baffle_ring_print`, `base_plate_pa12_print` in print orientation |
| `export/stl/print/` | the four print files in print orientation, resting on z = 0; `baffle_ring_print` is a sprued set of six rings with a lapping allowance, not the single ring |
| `export/stl/parts/` | every part in the assembly frame (renders and mesh checks) |
| `export/params_resolved.json` | YAML + mechanical-only + derived numbers, both base variants, post rectangles, camera play |
| `export/part_table.json` | every modelled part with material, group, volume, mass and bounding box |
| `export/check_report.md`, `.json` | full check results with every table; `export/selftest_report.json` |
| `drawings/` | GL1-001, -002, -010, -011, -012, -013, -020, -050 as PDF and SVG; `dxf/` 2D profiles; `fab/` Gerber profile, two mask layers, legend layer and Excellon drill of the FR-4 plate; `preview/` PNG of every sheet |
| `renders/` | six PNG renders |
| `PROPOSED_PARAM_CHANGES.md` | disposition of the rev C proposals under rev D (part A), of the proposals N1 to N10 (part B), and the new changes proposed to the YAML (part C) |

Frame (same as the YAML): origin at the puck centre on the base plane, +x right, +y forward toward the hole (the flat
visor face), +z up, millimetres. The base plane is the underside of the base plate. The cradle is modelled in the same
frame with the marker seated.

### What revision D changed in this package

| Rev D decision | In the model |
|---|---|
| Base plate, primary: routed FR-4 0.80 with a 0.20 sheet | plate z 0 to 0.80, sheet 0.80 to 1.00, PCB unchanged at 1.00 to 1.80; plain dia 13 grain opening, slot 17.44 x 2.2, three drilled dia 1.10 holes; seal joint 0.40; fabrication drawing GL1-011, Gerber / Excellon data and check 15 (corner radii, webs, drill table, data read back) |
| Base plate, alternative: MJF PA12 0.87 with a 0.13 sheet | built, exported and checked in the same build (check 16); integral baffle on three spokes, dia 1.15 holes, seal joint 0.33; drawing GL1-012 |
| Grain baffle (FR-4 build): separate black PA12 ring | dia 8.2 / 6.6 x 0.82 on a black adhesive annulus (tape 0.10 to 0.145 mm as available, drawn 0.13), crest at z 0.05; printed 1.10 high as a sprued set and lapped by us to the plate lot and the tape (E16); drawing GL1-013 |
| Grain opening potted clear | solid from the PCB down to z 0.05 (99.1 mm3, the level that must never be passed) in the interference, seal and mass checks; accepted surface z 0.05 to 0.15 for the nominal ring crest, fill target z 0.10 (93.4 mm3); potting step 12 (the YAML states these levels since the amendment, N4) |
| Ball feet on copper lands, foot zones | holes 1.10 / 1.15; check 10 proves that no post foot and no soldered part other than the battery lies over a foot zone |
| PCB locating moved to posts B | spigots at (+-14.35, 10.8), 28.7 apart; posts E plain; new camera-position table (section 5) |
| Visor windows 5.0 x 3.25 x 0.40 | seated on the recess floor, 0.15 below the visor face, top 0.15 below the tub top; sealed by a frame of thixotropic adhesive round the edge of the glass (side gaps, top bead, sill fillet), which check 13 proves with the glass drawn off its seats; field of view re-checked (the YAML states this bond since the amendment, N2) |
| Cover glass on a 0.13 tape ring 28 / 25 | crystal 0.12 below flush; EVT crystal declared not step-proof |
| U8, U10 moved; battery lead pads | part boxes from the YAML; two lead-and-joint solids checked against the tub |
| Board import check | `cad/board_import.py`, check 17; "skipped: no board file" until the board exists; proven by the self-test |
| B4, B5, B7, B9, B10, B22, B1, B2 adopted | the numbers are read from the YAML (cradle block, rim relief, pad plane, float, free height, field requirement); the former `MECH` overrides are gone and the deviations D05, D07, D13, D20 to D28 are closed |

### What the amendment changed in this package (decisions N1 to N10, spec amendments E8 to E16)

The YAML was amended in place after the last issue of this package. The model overrides that the proposals N1 to N10
had needed are gone: the numbers are read from the YAML and `params.py` asserts them.

| Decision / amendment | In the model, the checks and the drawings |
|---|---|
| N1 feet of posts B as built | 1.9 x 2.2 with the inner faces at x = +-13.55, asserted against `post_feet.locating.foot`; D29 closed |
| N2 window seated bare, edge frame | `sub_flush` 0.15 and `bond_line` 0 read from the YAML, top bead 0.10 and sill fillet 0.12 asserted against its text; D30 closed |
| N3 upper field 14.5 deg guaranteed, DEFINED with the optics 0.2 high and the spigot play against it | check 4 compares that case strictly, on both cameras: 14.61 deg, margin 0.11 deg at the nominal fit; no recorded shortfall is left; D31 closed |
| N4 potting levels, separate ring; E16 tape 0.10 to 0.145 mm | levels, ring height 0.82, tolerance and crest window read from the YAML. Ring height = plate thickness + 0.15 - tape thickness: 0.85 for a 0.10 tape, 0.82 for 0.13 (drawn), 0.805 for 0.145 on the 0.80 plate; crest z 0.00 to 0.13 in every case; the print file is 1.10 high (was 0.97); D32 closed |
| N5 tape-ring bore, N6 plate tolerances / accepted thickness / mask relief | read from the YAML (`bond_id`, `tolerances`, `thickness_accepted`, `mask_relief_dia`) |
| N7 0.3 mm between a part and a ball-foot zone, U10 moved | check 10 requires it (nearest part U11 at 0.312 mm); check 17 applies it to the real board |
| N9 slot 2.2 long | PCB solid, DXF `GL1-040`, synthetic board. Check 14 measures the slot on the solid: +-0.60 against 0.38 to 0.48 needed, margin 0.12 to 0.22 mm. Post B- now seats on two strips 0.525 wide: 2.15 mm2 (was 2.44); total post seat 20.6 mm2 |
| N10 keep-out under the LCD tail | check 12 proves the modelled tail inside the zone; check 17 fails a part taller than 0.7 mm in it |
| U9 is the BQ25101, 1.6 x 0.9 x 0.5 | part box from the YAML: marker 12.23 g (was 12.25), cavity 4218 mm3 (was 4205) |
| E8 ball feet 316 stainless (grade 100 or better) or silicon nitride, never 440C | part list, drawing notes, renders; a grade 100 ball may be 0.0127 mm oversize (as remembered), which uses up the epoxy under it at the lower plate limit: new deviation D33 with an incoming rule |
| E9 quarter-wave film under the cover glass (EVT trial) | optional part `retarder_film`, dia 23.4 x 0.10 with a clocking flat: 0.98 to the display, 0.80 inside the bore of the tape ring, 0.03 above the roof ledge outside the aperture (check 2); die cut `GL1-035`; shown in the stack, on GL1-002 and in the exploded render; D35 |
| E10 legend on the outer face of the base plate | `cad/legend.py`: placeholder blocks (maker, GL-1, PRACTICE DEVICE, two statement blocks, serial box 14.0 x 2.8); Gerber layer `-B_Legend.gbr`, read back by check 15, which measures 1.2 mm or more to holes, reliefs, opening and slot (1.0 required), proves the file mirrored and the letters 0.15 mm apart; GL1-011 sheet 2; PA12 plate: laser-marked (GL1-012 note 7) |
| E11 level zero on two seats | fixtures `cal_seat_plate` (base-face seat: three seat pads with ball pockets per nest) and `cal_plain_plate` (ball seat), drawing GL1-050, check 18; the six-face fixture is stated as a requirement, NOT designed; D34. Because the legend is ink on the same face, the ball gauge plate (`gauge_plate`, GL1-050 item 3) and the bridge gauge bear on bare mask too |
| E12 display rotation | check 14: the glass can turn 1.19 deg free in its pocket; squaring pusher in step 9; the residual angle is measured at the factory (fixture requirement) |
| Assembly-sequence defects of the manufacturing review | test gate 2 target at +13.5 deg (guaranteed 14.5 less 1.0), thermal-adhesive dabs on the two cell thermistors (step 13, part list), flux cleaning of the PCB underside (step 11a), second leak test after the temperature cycle (step 19), calibration fixtures (E11) |

The four deviations of the last issue against the YAML (D29 to D32) are closed. Three new ones are recorded, each with a
proposal (section 11 and `PROPOSED_PARAM_CHANGES.md` part C): the epoxy under an oversize grade 100 ball (D33), no
fixture on printed legend: seat pads, gauge-plate bosses and bridge-gauge feet on bare mask in legend-free zones round
the feet (D34), and the retarder film in the tape gap over the roof ledge (D35).

### What the review of drawings rev D-EVT1.1 changed (drawings rev D-EVT1.2, same parameters)

| Finding of the review | Change |
|---|---|
| Legend ink lay between the base plate and the flat ball gauge plate, and under depth gauges | the gauge plate has three bosses dia 7.0 with the gauge holes in them and is relieved 0.30 elsewhere (new fixture solid `gauge_plate`, GL1-050 item 3, detail on GL1-011, check 18); every depth reading on the underside is taken with a bridge gauge on three annular feet round the balls (requirement; check 15 keeps the legend 0.15 mm or more from each footprint); steps 2, 11, 12, 14, 15; D34 extended |
| Check 4 compared the guaranteed upper field on camera R only | the upper field is traced on both cameras in every case and the smaller value is compared; gate 2 rows for both cameras; a roof seed over camera L in the self-test |
| The 0.11 deg margin holds only at the nominal fit and the assumed pupil | new table in check 4 (what uses up the margin), a warning, section 5, proposal N18 |
| Nothing proved the legend file mirrored | check 15 mirrors the file it read and compares it with the legend as read, and tests the glyph order of "GL-1"; the build does the same on the Gerber and the DXF on disk; self-test seed |
| Legend letters 0.05 mm apart at 1.0 mm text | letter pitch widened so that the space is at least the line width (0.15); check 15 measures the smallest space between pieces of ink; the statement blocks hold 88 characters (was 96) |
| Retarder film: no clocking feature, bore margin smaller than its centring chain | film dia 23.4 (was 24.0) with a clocking flat toward the visor; check 2 rows for the chain; step 5 rewritten |
| Step 11a, 13, 19 and the serial number | dark-offset reading before the ring goes on, solvent limited by the optical parts; step 13 order, tack-free dabs, both thermistors read at gate 1, serial number marked after gate 1; soak before the second leak test and before the zeros |
| Check 14 did not test the slot across its width | slot and round hole are measured on the PCB solid in length, width and both centre coordinates; the two spigot-fit rows of check 2 use the PCB solid of the build; three self-test seeds |
| Stale values and labels | slot text in section 9, ring text above, DXF layer of `GL1-034` named by the tape range, docstring of `deviations.py`, ball grade and "never 440C" on GL1-011 and GL1-012; the build now fails on a stale README number |
| GL1-050: pad trim not dimensioned; 0 and 180 degrees only | R 21.0 and 0.9 dimensioned on both sheets and in the table; note 9 and section 2 say that a four-position zero needs another location |

Changes made after the design review of this revision (same parameters, rev D-EVT1): the two rear glass ribs of the tub
reach down to z 4.35 so that they are a real stop for the tilted LCD; the hood gasket bead is 0.5 x 0.33 astride the
rear edge of the cube and modelled at constant volume; the window adhesive is a closed frame with a sill fillet; the
tolerance chains were corrected (the seal joint does not depend on the plate thickness); the assembly sequence was
reordered (cell and prisms after lamination and potting, a dry trial close before the seal bead).

## 2. Part list

### Printed parts (HP Multi Jet Fusion PA12) and the fabricated base plate

| Drawing | Part | Material, process, finish | Box (mm) | Volume | Mass | Surface |
|---|---|---|---|---|---|---|
| GL1-010 | Tub (top shell) | HP 3D High Reusability PA 12, Multi Jet Fusion, dyed black, chemical vapor smoothing | 46.0 x 41.4 x 7.35 | 2.471 cm3 | 2.50 g | 49.9 cm2 |
| GL1-011 | Base plate, **primary** | FR-4 0.80 mm, matte black solder mask both sides, no copper; routed and drilled by the PCB fabricator; white legend on the outer face (E10, sheet 2) | 43.5 x 40.0 x 0.80 | 1.006 cm3 (12.57 cm2) | 1.86 g | - |
| GL1-012 | Base plate, **alternative** | HP PA 12, Multi Jet Fusion, dyed black, NOT vapor smoothed | 43.5 x 40.0 x 0.87 | 1.115 cm3 | 1.13 g | 28.1 cm2 |
| GL1-013 | Grain baffle ring (FR-4 build only) | HP PA 12, Multi Jet Fusion, dyed black, not smoothed; lapped to height by us | dia 8.2 / 6.6 x 0.82 finished (0.735 to 0.95 by plate lot and tape); print file: sprued set of six, 20.4 x 30.2 x 2.0, rings 1.10 high | 0.0153 cm3 (set 0.247 cm3) | 0.015 g | 0.75 cm2 |
| GL1-020 | Cradle body with lip and latch | HP PA 12, Multi Jet Fusion, any colour, not smoothed, not tumbled | 60.0 x 60.0 x 22.6 | 27.07 cm3 | 27.3 g | 161.8 cm2 |

The print files are watertight single shells (tub 23,046 triangles, cradle 13,492, baffle-ring set 7,038, PA12 plate
4,496) tessellated at 0.005 mm chord error and resting on z = 0; check 9 measures the largest facet sag on the main
radius of each (0.005 mm or less). The baffle ring is printed as a sprued set of six rings, each 1.10 high (GL1-013). The same parts are exported as STEP in print orientation: send the STEP when the bureau accepts
it. The cradle latch is sized for PA12; do not substitute SLA resin without redoing the latch numbers.

### Purchased and custom parts (mechanical bill of materials)

Status is copied from `../design/DESIGN_SPEC.md` (VERIFIED or PROVISIONAL as defined there). Where the spec gives no
status the item is PROVISIONAL here. Every envelope in the CAD is a simple solid for fit checks, not a manufacturer model.
"FR-4 build" is the primary build; "PA12 build" the alternative for the all-printed comparison at EVT.

| # | Item | Qty | Part / source | Envelope modelled (mm) | Status |
|---|---|---|---|---|---|
| 1 | Camera cube | 2 | OmniVision OVM7692-RYAA, DigiKey 884-1027-1-ND | 3.47 x 2.95 x 2.76 | Dimensions VERIFIED (product brief via search); ball map, pitch, image orientation PROVISIONAL |
| 2 | Fold prism | 2 | Edmund Optics 32-526, 2.00 mm legs, N-BK7, aluminised hypotenuse | 2 x 2 x 2 right-angle | VERIFIED (dimensions, coating, $105 at 1-5); production source to be quoted |
| 3 | Memory LCD | 1 | Sharp LS013B7DH03, DigiKey 425-2903-ND | glass 26.6 x 30.3 x 0.75 | Outline VERIFIED (Sharp brochure via search); active-area offset, flex tail geometry and pin-1 side PROVISIONAL |
| 4 | Battery | 1 | PowerStream GM201030-PCB, 2 x 10 x 30 mm cell with protection board | 34 x 10 x 2.0 (+0.4 swell); two leads to pads in the zone x -19.3 to -17.5, y -7.0 to -1.5 | Listing VERIFIED; protection-board length, capacity, maximum delivered thickness, swelling and certificates PROVISIONAL |
| 5 | Cover glass | 1 | EVT: flat mineral-glass watch crystal 28.0 x 1.0, **not step-proof**. Production: chemically strengthened glass or sapphire specified by strength (ring-on-ring 600 MPa or more), printed black border | dia 28.0 x 1.0 | PROVISIONAL. EVT crystal: a US source is listed (docs/SOURCING.md), tolerances not stated. Production: 1.0 mm is reported as not stocked for strengthened glass (0.8 and 1.1 mm are): recess or tape are re-fitted at DVT |
| 6 | Cover-glass tape ring | 1 | 3M 9472LE transfer tape 0.13 mm, die-cut dia 28.0 / 25.0 (`dxf/GL1-033`) | 0.13 thick, 1.5 wide | tape and its 0.13 mm thickness found (docs/SOURCING.md); converter PROVISIONAL |
| 6a | Retarder film, **OPTIONAL** (EVT trial, E9) | 1 | quarter-wave retarder film with its laminating adhesive, about 0.10 mm (0.11 at most), die cut dia 23.4 with one clocking flat 4.3 long (`dxf/GL1-035`; the converter cuts the flat at the stated angle to the film axis), laminated to the underside of the cover glass with its axis at 45 deg to the LCD polariser | dia 23.4 x 0.10, flat at 11.5 from the centre | PROVISIONAL (no part number; the angle of the axis to the flat follows from the polariser direction of the LCD, which is not known: display trial). Not in the primary build: a trial against the display going dark through polarised sunglasses |
| 7 | Visor window | 2 | 0.40 mm borosilicate (SCHOTT D 263 T eco class), custom cut 5.0 x 3.25; AR coating optional at EVT | 5.0 x 3.25 x 0.40 | PROVISIONAL (custom part, no source) |
| 8 | Window adhesive | - | THIXOTROPIC (non-wicking, gel) light-cure adhesive: a closed frame round the edge of the glass, i.e. the fill of the two 0.25 mm side gaps, a 0.10 mm bead along the top edge and a 0.12 x 0.12 fillet on the shelf in front of the bottom edge. Nothing behind the glass | 0.91 mm3 per window | PROVISIONAL (class only) |
| 9 | Vent | 1 | W. L. Gore VE80205 adhesive ePTFE vent, 5.0 outer, 2.0 vent area, 0.26 thick | dia 5.0 x 0.26 | PROVISIONAL (YAML basis: provisional). No US distributor was found and the water-entry pressure is unconfirmed; a Porex disc of the same size is the alternative named in docs/SOURCING.md |
| 10 | Ball feet | 3 | 1.0 mm balls of **316 stainless, grade 100 or better, or silicon nitride; never 440C** (E8: 440C rusts in wet fertilised turf) | dia 1.0 | PROVISIONAL. 316 balls of 1 mm are listed in the US without a stated grade; the only grade 25 ball found is 440C, which is excluded (docs/SOURCING.md). The diameter of each lot is measured at incoming inspection (D33) |
| 11 | Ball potting | - | stage 1 (in the hole, open to light from above): dual-cure or two-part epoxy. Stage 2 (between two opaque boards): a TWO-PART room-temperature epoxy. Per foot, FR-4 build: stage 1 0.27 mm3, stage 2 0.61 mm3 to fill the sheet hole, dispense 85 % (0.52); PA12 build: 0.40 and 0.41 (dispense 0.35) | plug in the hole + fill of the dia 2.0 sheet hole | PROVISIONAL (no part number); a UV-only grade does not cure in the shadow of the ball |
| 12 | LCD adhesive frame | 1 | 0.15 mm foam-type PSA frame 26.6 x 30.3 with a dia 23 window and a 0.8 mm vent channel (`dxf/GL1-032`) | 0.15 thick | PROVISIONAL |
| 13a | PCB-to-base adhesive sheet, FR-4 build | 1 | 3M 93020LE (300LSE) double-coated tape 0.20 mm, die cut: plain dia 13 opening, pad slot, three dia 2.0 foot holes (`dxf/GL1-030`) | 0.20 thick | thickness 0.20 found in docs/SOURCING.md (YAML basis still "provisional"); converter PROVISIONAL |
| 13b | PCB-to-base adhesive sheet, PA12 build | 1 | 3M 9472LE (300LSE) transfer tape 0.13 mm, die cut with the baffle pattern (`dxf/GL1-031`) | 0.13 thick | PROVISIONAL |
| 14 | Baffle adhesive annulus (FR-4 build) | 1 | OPAQUE BLACK double-coated tape, **0.10 to 0.145 mm as available** (E16; no black tape of exactly 0.13 mm was found: candidates in docs/SOURCING.md are 0.10 and 0.145 mm), die cut dia 8.2 / 6.6 (`dxf/GL1-034`, its layer named by the tape range) | drawn 0.13 thick, 0.8 wide | PROVISIONAL. The ring is lapped to the tape actually used (section 4.2). A clear tape would be a light slot between LEDs and photodiode; a 0.8 mm ring of tape is delicate: black liquid adhesive is the fallback |
| 15 | Clear potting of the grain opening | 0.10 ml | clear, low-fluorescence optical epoxy, mixed viscosity 0.1 to 2 Pa.s, low shrinkage, modulus to be chosen (section 12). FR-4 build: 93.4 mm3 to the fill target (25.0 inside the ring, 68.3 outside); 99.1 mm3 would reach the limit z 0.05. PA12 build: 90.9 mm3 in four compartments to its target (93.6 to the limit) | PCB underside down to z 0.05 at most | PROVISIONAL: not selected (YAML fill_basis: provisional) |
| 16 | Foam pad | 1 | 0.3 mm soft PU foam (Poron 4790 class), 26.6 x 10, adhesive one side | 0.3 thick | PROVISIONAL (whether this grade exists at 0.3 mm is disputed: docs/SOURCING.md) |
| 16a | Thermal adhesive for the two cell thermistors | 2 dabs | thermally conductive, electrically insulating, silicone-free adhesive that cures at room temperature (45 C at most); one dab joins each of the two NTCs (charger and MCU, 0402, within 1 mm of the cell edge) to the cell (DESIGN_SPEC section 4, E2) | not modelled: about 1 mm3 each, below the cell top (2.0 mm above the PCB) | PROVISIONAL (class only) |
| 17 | Perimeter seal adhesive | 70 mm3 (PA12 build 65) | opaque BLACK, thixotropic, work life of an hour or more, cures at room temperature or at 45 C at most (the cell is on the board), rated for sustained peel at 70 C on primed PA12 and on FR-4 solder mask (structural acrylic or epoxy, not RTV) | 49.8 mm3 at nominal gaps in the FR-4 build (0.40 x 0.4 joint on the land + the 0.25 mm radial groove); 45.6 mm3 in the PA12 build (0.33 joint) | PROVISIONAL: adhesive not selected |
| 18 | Hood gasket | 2 beads | black, soft (about Shore A 40), silicone-free form-in-place gasket material (UV-cure urethane-acrylate class), 0.43 mm3 per hood | bead 0.5 wide x 0.33 high x 3.9 long as dispensed; squeezed 24 % over a 0.17 mm land on the cube top | PROVISIONAL (class only) |
| 19 | Main PCB assembly | 1 | 4-layer 0.8 mm, D outline R 21.1, flat y 17.3, round locating hole dia 1.15 at (14.35, 10.8) and slot 1.15 x 2.2 at (-14.35, 10.8) (`dxf/GL1-040`, re-issued: the slot was 1.8 long) | board + the 13 YAML part boxes + two battery-lead envelopes | Part boxes from the YAML (nominal); passives not modelled: the real board is checked by check 17 |
| 20 | Cradle spring pin | 4 or 7 | Mill-Max 0914-series long stroke; consumer cradle 4 (VBUS, D-, D+, GND), factory fixture 7 | plunger dia 1.07, barrel dia 1.83 | PROVISIONAL (working height 5.82, 0.59 N, stroke 2.29; diameters and barrel length not confirmed) |
| 21 | Cradle USB-C receptacle | 1 | GCT USB4105 | 8.94 x 7.35 x 3.26 | Envelope PROVISIONAL |
| 22 | Cradle PCB | 1 | 2-layer 1.6 mm, 30 x 22 (YAML cradle.pcb), seven pin positions, resettable fuse on VBUS | 30 x 22 x 1.6 | position and top face from the YAML |
| 23 | Cradle feet | 4 | self-adhesive bumpers dia 8 x 3 | dia 8 x 3 | PROVISIONAL (generic) |
| 24 | Cradle PCB screws | 4 | M2 x 5 thread-forming screws for plastic | not modelled | PROVISIONAL (generic) |

Fixtures and gauges the build needs (not product parts; in this CAD only where a solid is named). **Rule for every
fixture that takes the outer face of the base plate as its reference: it bears on BARE MASK inside the legend-free
zones round the three ball feet, never on printed legend** (ink 0.02 mm typical, 0.03 at most; D34; checks 15 and 18).

- **Ball gauge plate** (step 2; solid `gauge_plate`, drawing GL1-050 item 3, detail on GL1-011 sheet 1, check 18):
  a ground plate 52 x 50 x 10 with three bosses dia 7.0, 0.30 proud, their tops ground in one plane within 0.005, at
  (0, 15.0), (-16.5, -9.5), (16.5, -9.5); in the centre of each boss a reamed hole dia 0.60 +0.005 / 0, 0.5 deep, with
  a sharp burr-free rim. A 1.0 mm ball seated on the rim of a dia 0.60 hole stands exactly 0.10 mm below the boss top,
  and the boss face seals the epoxy. The base plate lies on it outer face down and **rests on the three bosses only**,
  on bare mask: the legend, 0.27 mm clear of the relieved plate face and 0.99 mm from a boss, never touches the plate.
  (On a flat plate the base plate would lie on its legend: the protrusion would come out 0.10 to 0.13 against
  +-0.02, and the ball top would come 0.03 nearer its land, where only 0.02 mm of epoxy is budgeted at the lower plate
  limit.) Clamp: a weight with three annular feet over the bosses (dia 7 / dia 3, open above each hole), so that the
  load goes straight through the plate into the bosses; a flat weight would bend the 0.8 mm plate between its three
  supports. **The three balls locate the plate: no hard edge stops, only loose guides** (the holes sit +-0.10 from
  the outline; a ball forced 0.05 off its gauge hole stands only 0.067 proud, design-review figure). Release: a
  non-transferring, silicone-free dry film (PTFE) baked onto the boss tops, nothing that can reach the bonding faces
  of the plate. A micrometer for the ball lot: an oversize ball stands just as proud but reaches higher into the
  laminate (D33).
- **Bridge gauge** (steps 11, 12, 14, 15; a requirement, not drawn; its footprint is checked in checks 15 and 18): a
  small bridge on three annular feet dia 6.0 / 1.6 at the ball-foot positions, 1.0 proud and lapped in one plane
  within 0.002, carrying a dial indicator (0.001 mm) that can be set over the grain opening (centre, and four points at
  r 5 outside the baffle ring) and at four rim stations at r 22.35, azimuth 45, 135, -135 and -45 degrees from +x (the
  flat of the tub rim runs from r 22.0 to 22.7). Each foot bore centres on its ball cap within 0.53 and clears the
  mask relief; the feet stay 1.06 mm or more from the legend. Zeroed on a flat plate. Contact tip dia 2 on potting and
  rim, dia 1 on the 0.8 mm crest of the ring. **Every depth reading on the underside is taken with this gauge**, from
  the same three areas of bare mask as the calibration seat: an ordinary depth gauge laid across the grain opening
  would rest on legend 1.2 mm from the opening and read the ring crest and the potting level up to 0.03 mm deep
  against a never-below limit of 0.05.
- **Lamination jig** (steps 3 and 11): a support nest for the component side of the PCB that carries it on bare board
  areas, with pockets for every part; two SPRUNG dia 1.10 pins for the locating hole and slot (28.7 apart) that stand
  2 mm above the PCB underside for the ring tool and are pressed down flush by the base plate (they stay inside the
  0.8 mm board, so the PCB stays located); a ring tool on those pins that places the baffle ring round the photodiode;
  three sprung fingers that centre the D outline of the base plate about the pins (no fixed frame); two dia 3.0 posts
  at (+-27, 0) for the tooling holes of the adhesive sheet's carrier liner (`dxf/GL1-030`, `-031`); a flat press plate
  with three relief holes for the ball feet, faced with a compliant pad about 1 mm thick (the outer face it presses on
  carries the legend: a hard plate would press on ink islands 0.02 to 0.03 mm high instead of on the sheet).
- **Ring lapping gauge**: a plate with a pocket of adjustable depth (shims) and a flat stone; the ring is lapped until
  flush with the pocket. Pocket depth = measured plate thickness + 0.15 - measured tape thickness.
- **Film lamination nest** (step 5, retarder-film trial only; a requirement, not drawn): a pocket dia 28.1 for the
  crystal, a loose ring dia 28.0 / 23.5 that centres the film on it within 0.25 mm and a straight stop for the
  clocking flat of the film; a scribed line continues the flat to the edge of the pocket, where the crystal edge is
  marked.
- **LCD squaring pusher** (step 9; a requirement, not drawn): a sprung slide on the tub nest, guided on the centre line
  of the tub (x = 0 within 0.5 mm), with a soft pad 5 mm wide and about 1 mm high that bears on the middle of the front
  edge of the tilted glass and pushes it rearward with 0.5 to 1 N. The pad passes between posts E (6.8 mm clear: 0.4 mm
  each side at the worst guidance) and acts 5.0 mm inside the inner corners of the two rear glass ribs (x = +-8.0), so
  the glass beds on BOTH ribs and is square
  to them; the slide follows the glass while its rear edge is raised to the roof and lets go when the front hinges up.
- **Potting nest** (step 12): carries the unit underside up on bare areas of the component side (camera pockets) and
  is levelled ON THE BASE UNDERSIDE to 0.25 degrees or better (0.06 mm across the opening); positive-displacement
  dispenser for 0.10 ml good to +-3 %; vacuum bell; a low-tack mask that is an ANNULUS dia 15 to dia 24 centred on the
  grain opening (inside, the edge of the opening must stay a free edge that pins the meniscus; outside, the three seat
  zones must stay bare: the feet of the bridge gauge are 1.9 mm clear of a dia 24 mask); the bridge gauge, or an
  optical height sensor referred to the same three zones.
- **Prism jig** (step 13), referenced to the two locating features of the PCB.
- **Window stop** (step 6): a plate on the tub top with a 0.15 mm step that enters the open end of each window recess.
- **Needle guide** (step 8): a fork that registers on the rear face of the hood rear wall and guides the needle
  0.35 mm in front of it.
- **Join fixture** (steps 14 to 17): a nest for the upturned tub with a window (or a mirror) under the LCD and an open
  front for the two cameras; a hinged carrier for the PCB / base unit, hinge axis parallel to x at y = -30, z = 0
  (7 mm behind the tub at the base plane), lateral guidance +-0.1 mm; a press plate with relief holes over the ball
  feet, a compliant facing (legend) and openings for the three feet and four rim stations of the bridge gauge, and a
  pogo block that reaches the seven pads through it. Check 14 proves both the hinged motion and a straight descent.
- **Go gauges**: disc dia 42.6 x 1 (ledge radius 21.30 or more); disc dia 43.7 x 1 (the bore below the ledge must take
  a base plate at its largest, R 21.85); block 4.90 high for the bay roof above the post feet; ring dia 1.10 for the
  two spigots; height gauge for the prism tops (4.85 maximum above the PCB); a **dummy unit**: a plate with the PCB
  outline, the hole and the slot at their smallest, and two stepped blocks at the camera positions (3.77 x 3.25 x 2.81
  for the cube, 2.3 x 2.3 on top of it up to 4.85 for the prism: nominal sizes plus the 0.10 play and 0.05 placement),
  which must seat on all eight posts with the blocks inside the hoods.
- **Vacuum pen** for the LCD; dispensers for the epoxies, the hood gaskets, the window adhesive and the seal bead.
- **Pogo test fixture** for the seven pads; **leak-test chamber** with a soft pad that occludes the vent hole and its
  grooves; a gasketed plate that closes the open underside of a tub for the tub leak test (step 10).
- **Gate 2 target** (step 16): two evenly lit horizontal bars on the open front of the join fixture, at +13.5 and
  -13.5 degrees from the optical axis of the seated unit (120 mm above and below the axis at 500 mm from the visor).
- **Calibration seat plates** (step 19, drawing **GL1-050**, check 18), for the level zero on two seats (E11). Item 1,
  the BASE-FACE seat plate (the turf seat): hardened, stabilised tool steel 70 x 112 x 12; per nest three annular seat
  pads dia 7.0, 0.30 proud of the plate face and lapped into one plane within 0.001 mm, each round a clearance pocket
  dia 3.0 x 0.50 deep at a ball-foot position of the YAML. The marker rests on its FR-4 face next to its three feet and
  the balls hang free (0.40 under a ball, 1.18 to the pocket wall). Item 2, the BALL seat plate: the same blank with a
  plain face lapped flat within 0.001 mm per nest. Both carry a double-faced datum fence across the middle (the visor
  flat lies against it between z 1.6 and 4.0, above an undercut that clears the seal joint) and a dia 3.0 stop pin per
  nest: fence and pin fix the marker in x, y and rotation. Two nests, 180 degrees apart, lie in the one lapped plane:
  a read in nest A and a read in nest B after turning the marker cancel the tilt of the plate and of the table, so the
  plate needs no parallelism. **No contacts on either plate**: a spring pin pushes five times harder than the marker
  weighs, so the zero is read with the marker lying free (started from the menu, or armed through the pogo fixture and
  run once the marker is at rest: a firmware requirement). Why pads and not the whole face: a legend print stands about
  0.02 mm proud of the mask (0.8 mrad across the feet) and the rim is only 0.25 above the base plane (D34). The pads
  end 0.75 inside the base-plate outline: pads 2 and 3 on R 21.0 about the nest centre, pad 1 on a line 0.9 from its
  datum face (dimensioned on GL1-050). **These plates give the 0 / 180 degree reversal only**: the fence takes the
  visor flat. The four-position zero (0, 90, 180, 270 degrees) that `docs/MANUFACTURING_PLAN.md` 6.2 and 6.7 plan for
  production needs a location on the round wall (three pins) instead of the fence: not designed; for EVT the two-nest
  reversal is what E11 asks for.
- **Six-face calibration fixture: NOT YET DESIGNED.** The six-face procedure is started over USB, so the marker must
  be held still in six orientations (+x, -x, +y, -y, +z, -z up) with spring pins on its pads. What drives its
  dimensions: marker envelope dia 46.0 x 7.6 with the flat at y = 18.4; seven pads dia 1.8 on a 2.54 pitch at y = -17.0,
  x = -7.62 to +7.62, their copper faces 0.965 above the base plane at the bottom of a 17.44 x 2.2 slot (the four pins
  VBUS, D-, D+, GND are enough for USB); pin force 0.59 N each at 5.82 mm working height, so 2.4 N (four pins) or
  4.1 N (seven) against a marker weight of 0.12 N: the clamp must hold at least three times that in every
  orientation without loading the cover glass (not step-proof) or the two windows, and without bending the marker;
  the clamp may bear on the tub top outside the dia 28.5 recess and on the base plate away from the dia 8.5 zones of
  the feet, the potted opening and the pad slot; six mutually square outer faces (ordinary toolroom squareness is
  enough, because errors largely cancel between opposite faces) of a cube of about 60 mm, and a cable exit that does
  not tip it. A candidate, not verified: the seven-pin factory cradle (GL1-020), whose lip and latch are calculated
  to hold the seven-pin force 6.0 times over, screwed into a square frame; against it: the marker floats up to 0.25 mm
  against lip and hook, the latch is printed PA12 (creep), and with USB attached the charger warms the unit.
- **Display-rotation measurement** (step 19; a requirement, not designed): the marker on a seat plate with its visor
  flat against the fence, a camera looking straight down, the display showing a test line (a firmware command that
  does not exist yet). The angle of the line against the fence is measured and stored (E12). Needed: 0.1 degree, i.e.
  0.035 mm over a 20 mm line, so about 20 micrometres per pixel over the dia 22 aperture; the camera axes are referred
  to the fence with a master plate that carries an engraved line.
- Zeroing in the field is done by the user on any hard flat surface. No calibration step uses the charging cradle.

Estimated mass (typical densities, envelope solids, no solder or passives; check 8 and check 16): marker with the FR-4
plate **12.23 g**, centre of gravity at (0.00, -1.28, 3.48) mm, 8.2 mm inside the triangle of the ball feet; with the
PA12 plate **11.39 g**, centre of gravity (-0.01, -1.38, 3.71), 8.1 mm inside; cradle assembly with seven pins 31.2 g.
(The optional retarder film would add 0.05 g.)

## 3. What the parts look like

| | |
|---|---|
| ![underside](renders/GL1_render_b_underside.png) | ![exploded](renders/GL1_render_c_exploded.png) |
| ![cut-away](renders/GL1_render_d_cutaway.png) | ![in cradle](renders/GL1_render_e_in_cradle.png) |
| ![cradle section](renders/GL1_render_f_cradle_section.png) | |

Renders of the primary build (2000 x 1500; the exploded view is 1800 x 2400). The tub is drawn dark grey so that its
shape reads; the real part is black, and so is the solder mask of the FR-4 plate.

- `GL1_render_a_front_top.png`: assembled marker from the front and above: visor windows (set back 0.15), cover glass, nose groove, vent hole with its drain grooves, rim relief.
- `GL1_render_b_underside.png`: from below: FR-4 base plate with its legend (the placeholder blocks of GL1-011 sheet 2, a render-only mesh of the legend strokes), grain opening potted clear over the LED pairs, the photodiode and the separate baffle ring, pad slot with the seven pads, the three potted ball feet, the seal adhesive in the groove at the rim.
- `GL1_render_c_exploded.png`: every marker part separated along z and labelled, including the adhesive sheet, the baffle ring and its black annulus, the clear potting, the battery leads, the window adhesive frames, the hood gaskets and the ball pottings; the OPTIONAL retarder film (E9, dia 23.4 with its clocking flat) is shown between the cover glass and its tape ring.
- `GL1_render_d_cutaway.png`: boolean cut on x = 0 behind y = 13.0 and on x = 10.0 through camera R in front of it, labelled (stack FR-4 0.80 / sheet 0.20 / PCB 0.80, potting, baffle ring).
- `GL1_render_e_in_cradle.png`: marker in the cradle from the rear right: latch with thumb tab, guard wall, tab stop, lip, finger scallop, USB-C receptacle and the drain outlet beside it.
- `GL1_render_f_cradle_section.png`: marker in the cradle cut on x = 0: centre spring pin compressed on its pad, lip over the front edge, raked latch hook over the rear edge, tab stop, drained floor.

Drawings (A3, PDF and SVG; PNG previews in `drawings/preview/`; title block with part, material, process, general tolerance,
drawing revision D-EVT1.2 and "PROVISIONAL - not released"):

- `GL1-001_assembly_outline`: top view, view on the visor face and side view with overall size (dia 46.0, 41.4, 7.6), camera baseline 20.0, optical axis height 5.61, window and recess sizes, ball feet, rim relief.
- `GL1-002_sections` sheet 1: section A-A on x = 0 with every part labelled; detail C with the full z stack (FR-4 base 0.80, adhesive sheet 0.20, PCB 1.00 to 1.80, potting to z 0.05, ...) and the optional retarder film under the cover glass.
- `GL1-002_sections` sheet 2: section B-B on x = 10.0 through camera R; detail D with the camera stack, the wall build-up in y, the seated 0.40 window, the hood gasket and the traced chief rays (+17.6 / -8 deg).
- `GL1-010_tub` sheet 1: view into the cavity with posts, the spigots under posts B, hoods, ribs (the two rear ribs reach down to z 4.35), ledge; detail E of wall, ledge and plain roof on the arc; post table with the feet as built; the dimensions required to +-0.1 (seal face and rim from the post feet).
- `GL1-010_tub` sheet 2: top view, sections A-A and B-B of the tub alone, detail G of the camera opening in plan, view on the visor face with the window recesses.
- `GL1-011_base_plate_FR4` sheet 1: **fabrication drawing** for the PCB fabricator: outline, drill and rout table, slot, radii, webs and edge distances, tolerances, material, mask with its relief at the holes, no copper, tab rule, data files; for information, a section of a ball foot in use, standing on the boss of the gauge plate (the true section of the fixture solid); ball material with grade and "never 440C" (E8).
- `GL1-011_base_plate_FR4` sheet 2: the **legend of the outer face** as it is read (seen from below): the placeholder blocks, the keep-clear zones (1.0 mm round holes, reliefs, opening and slot; dia 8.5 seat zones round the feet; 0.75 from the outline), the footprints of the three fixtures that bear on the face (brown), block table, computed distances including the space between letters, notes on process, placeholders and the serial number.
- `GL1-012_base_plate_PA12_alternative`: the printed plate with its integral baffle, detail H of a ball foot as assembled, feature table; note 7: the legend is laser-marked.
- `GL1-013_baffle_ring`: the separate ring, its section with the lapped height, how it sits in the potted opening, the sprued print set (rings 1.10 high); clearance and level table; table of ring height by tape thickness (E16).
- `GL1-020_cradle` sheet 1: top view with the drained floor, section D-D with the marker seated, view from below.
- `GL1-020_cradle` sheet 2: detail J of the latch and detail K of the lip, section E-E through the pin row, insertion path, hold-down table, cradle PCB table.
- `GL1-050_calibration_seat_plates` sheet 1: the two fixtures of the two-seat level zero (E11): plan of the base-face seat plate (two nests, six seat pads with pockets and their trims R 21.0 and 0.9, datum fence, stop pins; the marker dash-dot), plan of the plain ball seat plate, requirement table (coplanarity, flatness, squareness, pocket, pad trim), notes (among them: 0 and 180 degrees only).
- `GL1-050_calibration_seat_plates` sheet 2: section A-A through pocket 1 and the fence with the marker seated on its base face, detail B of a ball foot hanging in its pocket, table of pocket and pin positions; **item 3, the ball gauge plate** of step 2: section through boss 1 with the base plate lying on it (boss dia 7.0, relief 0.3, gauge hole dia 0.6 x 0.5).
- `drawings/dxf/`: `GL1-011_base_plate_FR4_fab` (layers OUTLINE_ROUT, ROUT_OPENING_D13p0, ROUT_SLOT_17p44x2p2, DRILL_NPTH_D1p10, and three LEGEND_BOTTOM layers with the centre lines of the legend strokes by line width, mirrored as seen from the top face); the die cuts `GL1-030` (PCB sheet 0.20, FR-4 build) and `GL1-031` (PCB sheet 0.13, PA12 build), each with a second layer for the carrier liner 64 x 50 and its two dia 3.0 tooling holes at (+-27, 0), `GL1-032` (LCD frame with its vent channel), `GL1-033` (cover tape ring 28 / 25), `GL1-034` (baffle annulus; layer `BAFFLE_ANNULUS_BLACK_TAPE_0p10_TO_0p145_AS_AVAILABLE_...`), `GL1-035` (optional retarder film dia 23.4 with its clocking flat at y 11.5); `GL1-040` main PCB outline with the round hole and the 1.15 x 2.2 slot under posts B (**re-issued**: the last issue carried the 1.8 mm slot); `GL1-050` calibration seat plates and ball gauge plate (seat plane with pads and pockets, top face, fence band, blanks; bosses and gauge holes of item 3); `GL1-012` PA12 plate profile, `GL1-013` ring profile, tub and cradle profiles on named layers, sections A-A and B-B.
- `drawings/fab/`: `GL1-011_base_plate_FR4-Profile.gbr` (Gerber RS-274X: outline and routed cut-outs, true arcs), `-F_Mask.gbr` and `-B_Mask.gbr` (mask layers, negative: only the three dia 1.25 hole reliefs are open), `-B_Legend.gbr` (legend of the outer face, positive: 343 strokes with round apertures of 0.15, 0.20 and 0.25 mm; like every bottom layer it is given as seen from the top face, so the text is mirrored in the file), `-NPTH.drl` (Excellon: three dia 1.10 holes). Same origin as the drawing, millimetres. Check 15 reads them back and compares them with the plate solid and the legend blocks, and proves the legend layer mirrored without using the generator's own mirror function; after the drawings are written `build.py` compares the five files on disk with the text the check read and repeats the mirror test on the Gerber and on the legend layers of the DXF.

## 4. Ordering notes

### 4.1 FR-4 base plate (PCB fabricator), drawing GL1-011

1. **What it is.** A mechanical plate, not a circuit: FR-4 with **no copper** on any layer, matte black solder mask on
   both faces, a white legend on the underside only (item 9), no date code or fabricator marking.
2. **Thickness.** Finished thickness OVER THE MASK 0.80 +-0.10 mm (the usual tolerance below 1.0 mm). Ask the
   fabricator to choose the laminate for that finished thickness and to state the build-up: a nominal 0.8 mm
   copper-clad laminate ends near 0.75 mm once its copper is etched off (trade figure, not verified). We use plates
   from **0.76 to 0.90 mm**; the lower limit comes from the gap under the ball feet (check 2). The thickness does NOT
   set the seal joint (that is PCB - printed step + sheet); it sets the rim relief, the gap between each ball and its
   land and the depth of the grain opening, and the baffle rings are lapped to the plate lot (section 4.2).
3. **Data to send.** `drawings/GL1-011_base_plate_FR4.pdf` (two sheets); the five files in `drawings/fab/` (Gerber
   profile, two mask layers, legend of the underside, Excellon NPTH drill); `drawings/dxf/GL1-011_base_plate_FR4_fab.dxf` (one layer per operation);
   `export/step/base_plate.step`. Origin = centre of the R 21.75 arc, +y toward the flat, seen on the top face.
4. **Operations.** Routed outline R 21.75 with a flat at y = 18.25 (+-0.10); routed round opening dia 13.0 at (0, -4.0);
   routed slot 17.44 x 2.2 with full-radius ends at y = -17.0; three drilled non-plated holes dia 1.10 +-0.05 at
   (0, 15.0) and (+-16.5, -9.5), position +-0.05. No internal corner below R 0.5 (the smallest is R 1.1 at the slot
   ends), so no drilled relief; a dia 2.0 router bit makes everything. Smallest web 2.02 mm (slot to edge); holes 2.16
   and 2.70 mm from the edge (check 15 measures these on the solid; the 1.0 mm web rule it tests against is our
   assumption, confirm it with the fabricator).
5. **Mask at the holes.** A round relief dia 1.25 in the mask at each hole on both faces (or drill after mask): the
   ball has 0.05 mm radial clearance and 0.02 to 0.03 mm of mask on the hole wall would use it up.
6. **Edge and tabs.** The edge and a 0.4 mm rim of the top face are bonding faces of the perimeter seal, and the round
   part drops into a bore with 0.25 mm radial clearance: no V-score. Order individually routed pieces. If the fabricator
   panelises: break-off tabs ONLY on the flat (the land is 0.65 mm there and there is no bore), mouse bites recessed
   into the outline by at most 0.25 mm, no nub proud of the outline anywhere.
7. **Flatness** 0.5 % bow and twist maximum (0.2 mm over the part). Both faces are bonding faces: no release agent.
8. **To report with the first articles:** thickness over the mask, hole diameters (a dia 1.0 ball must drop through
   with 0.05 radial clearance), outline.
9. **Legend (E10, sheet 2).** White legend print on the black mask of the UNDERSIDE (the face that rests on the turf),
   or laser marking of the same artwork: line 0.15 mm or more, text 1.0 mm or more (to be confirmed with the quote),
   clear space between letters and between any two pieces of ink 0.15 mm or more (the letters are pitched for it:
   0.15 mm between letters at 1.0 mm text, pitch 0.967 mm), print 0.03 mm thick at most, registration +-0.15 to the
   outline. The artwork holds PLACEHOLDERS: "MAKER NAME", "GL-1", "PRACTICE DEVICE", two framed blocks 11.5 x 7.8 mm
   reserved for the statements of `docs/COMPLIANCE.md` (the two blocks hold 88 characters at 1.0 mm, four lines of
   eleven each: the short FCC sentence fits, the full two-condition statement does not) and a serial-number box
   14.0 x 2.8 mm inside its frame, in which we mark the number per unit (assembly step 13). It keeps 1.2 mm or more
   from the three holes with their mask reliefs, the round opening and the slot (1.0 required), 1.57 mm from the
   outline, and stays out of a dia 8.5 zone round each hole: the bosses of the ball gauge plate, the seat pads of the
   calibration plate and the feet of the bridge gauge bear on bare mask there (0.49 mm or more between the legend and
   any of these footprints with its play; 0.15 required). The file is a bottom layer: the text is mirrored in it and
   check 15 proves that. **Do not order plates for sale with the placeholder artwork**: the wording is not frozen.

### 4.2 Printed parts (bureau)

1. **Process.** HP Multi Jet Fusion, PA 12. Tub: dyed black and chemically vapor smoothed. Baffle-ring set and the
   alternative PA12 base plate: dyed black, not smoothed. Cradle: any colour, not smoothed and **not tumbled** (the
   latch is a 1 mm beam with a heavy head).
2. **Orientation.** `export/stl/print/` and `export/step/*_print.step` hold the parts in build orientation (z up):
   - tub roof-down, so that the cosmetic top face and the cover-glass recess face the bed and the cavity is open upward;
   - baffle-ring set and PA12 base plate flat;
   - **cradle with its x axis (one of the 60 mm sides) as the build direction. This orientation is LOCKED**: the side
     profile of the latch beam and of the lip then lies in the build plane, so that their bending stress runs along
     the layers and not across them. Please confirm it on the order.
   The functional planes of the tub must stay parallel to each other: LCD bonding plane z 5.55, recess floor z 6.35,
   seal face z 1.2 and the eight post feet at z 1.8.
3. **Walls.** Designed to 0.8 mm minimum (side wall 1.0). The wall audit (check 5) lists every place below 0.8 mm,
   ten regions in all: the 0.525 mm strip behind each window recess in front of the camera (D04, accepted,
   4.0 x 0.4 mm), the feet of chamfered edges (side wall 0.70 at the rim, hood rear walls 0.68, hood skirts 0.50 at
   their 0.3 mm lead-in chamfer), a sliver at the rounded top corner of the land beside each window recess (0.76 over
   0.01 to 0.02 mm2) and the nose of the cradle hook (a solid wedge ending in a 0.4 mm flat: an edge, not a wall). The
   two locating spigots are dia 1.0 pins with chamfered tips. The baffle ring is 0.8 radial; the PA12 base plate has
   no wall below 0.8 mm (check 16). Please confirm that 0.8 mm walls survive your vapor smoothing.
4. **Powder.** No closed void and no cavity without a 2 mm escape path (check 6, which lists eight open recesses
   narrower than 2 mm in the tub: the gaps between posts C and the side wall, the two corners where the thick roof
   meets the side wall and the two corners between a rear glass rib and the side wall; check 16 for the PA12 plate).
   Other open narrow places that need attention: the two camera bays and visor openings, the dia 1.0 vent hole (it
   may fuse shut: clear it with a 1.0 mm drill) and its two 0.6 mm grooves, the three dia 1.15 ball-foot holes of the
   PA12 plate, and in the cradle the pin slot (2.33 mm wide, through), the latch well (gaps 2.2 / 2.7 / 1.2 mm round
   the beam, open at the top, 6.8 mm deep), its 2.4 x 2.4 mm drain tunnel to the rear face and the four dia 5 blind
   cores behind the foot pockets.
5. **Baffle ring.** The print file is a sprued set: six rings on a 2 x 2 mm runner, each joined by a 0.8 mm gate on
   its outside and printed 1.10 high (0.15 mm of lapping allowance on the tallest ring that can be needed). Order two
   sets. We cut the rings off, trim the gate flush and lap the bonding face in a pocket gauge. Finished height =
   measured plate thickness + 0.15 - thickness of the black tape actually used (E16: 0.10 to 0.145 mm as available),
   +0.00 / -0.03: for a 0.80 mm plate 0.85 with a 0.10 tape, 0.82 with 0.13 (the model), 0.805 with 0.145; over the
   accepted plate lots (0.76 to 0.90) 0.735 to 0.95. The crest of the ring then ends 0.00 to 0.13 mm inside the base
   plane whatever lot and tape (accepted 0.00 to 0.15); lapped to 0.82 regardless of the plate it could end 0.03 proud
   or 0.22 deep (check 2).
6. **Dimensions to report at first article.**
   - Tub: REQUIRED to +-0.1, measured from the post feet: seal face 0.60 below them (it sets the seal joint) and rim
     1.55 below them (it sets the rim relief). The bureau's general tolerance is wider, so these two are the first
     things to measure. Ledge radius 21.35 (a dia 42.6 disc must pass); bore below the ledge (a dia 43.7 disc must
     enter); bay roof 5.0 above the post feet (4.90 minimum); the two spigots under posts B (dia 1.0 x 0.6, 28.7
     apart): diameter and spacing, a dia 1.10 ring gauge must go over each; the dummy unit must seat. The faces of the
     two rear glass ribs (the datum the LCD is squared against): step between them, 0.05 mm or less wanted.
   - PA12 base plate: as printed the bureau's tolerance applies. WE sort and finish: thickness 0.83 to 0.92 is used
     (below 0.83 the ball would touch its land through the 0.13 sheet); order about twice the quantity needed.
     Free-state flatness 0.3 mm is OUR target after flattening between plates under a weight, warm (time and
     temperature to be found on first articles), not a bureau requirement. The three foot holes are reamed to dia
     1.15 by us.
   - Cradle: front nest wall to hook nose 39.95 +-0.15; beam thickness 1.03 above the root fillets, 0.95 half way up,
     0.89 at the neck; beam to stop ribs 1.30; top of the tab stop 3.46 below the tab; nose 0.25 above a seated marker.
7. **Post-processing by us, not the bureau.** Four dia 1.6 x 3 pilot holes in the cradle at the printed spot marks;
   gauging of the spigots; lapping of the baffle rings; sorting, flattening and reaming of the PA12 plates.
8. **Tolerance.** Quoted general tolerance +-0.3 mm or +-0.3 %. Every drop-in fit has 0.25 mm nominal clearance; the
   only fit below it is the spigot fit (section 5).

## 5. Tolerances and fits

Nominal values from check 2 (all computed on the solids of the primary build; check 16 repeats the base-plate rows for
the PA12 plate). "Rule" is the 0.25 mm drop-in clearance of the specification.

| Fit | Nominal gap (mm) | Against the rule | Comment |
|---|---|---|---|
| Base plate in the tub, radial | 0.25 | meets | groove filled with seal adhesive down to the rim; plain edge, no key |
| Tub rim above the base plane (rim relief) | 0.25 | - | rim 0.35 above the plane of the ball feet (YAML envelope.rim_relief) |
| Base plate top to tub seal face | FR-4: 0.40 nominal, 0.27 to 0.53; PA12: 0.33, 0.20 to 0.46 | adhesive joint | = PCB 0.80 - printed step 0.60 + sheet; the plate thickness is not in this chain. Range = +-0.13 RSS with the printed step at the +-0.10 the drawing requires; 0.18 to 0.62 (PA12 0.11 to 0.55) at the bureau's general +-0.2 (table below) |
| PCB edge to the seating ledge, radial | 0.25 | meets | PCB radius 21.1 |
| PCB locating spigots in the round hole / across the slot | 0.075 | **below (D19), by specification** | the locating fit that positions the cameras; measured on the PCB solid of the build and compared with the nominal 0.075 (a hole or a slot 0.01 off its position fails checks 2 and 14); +-0.60 along the 2.2 mm slot (N9; 0.38 to 0.48 needed). Go gauge dia 1.10 |
| Spigot tip above the adhesive sheet | 0.20 | - | spigot is 0.6 long in a 0.8 board; tip chamfer 0.15 captures +-0.225 |
| PCB flat edge to visor wall | 0.30 | meets | |
| LCD glass in its pocket (ribs, posts B and E, hood rear walls) | 0.25 | meets | the feet of posts B have their inner faces at x = +-13.55 for this (YAML, N1). Left free the glass can turn 1.19 deg in this pocket (E12, below) |
| LCD glass as assembled in step 9 | 0.15 behind the nominal position: 0.10 to the rear ribs, 0.40 to posts E and the hood rear walls | inside the pocket | the tilted glass is pushed back against the rear ribs (they reach down to z 4.35); hinged flat it clears them by 0.10 (check 14) |
| LCD glass past the seating ledge during assembly | 0.28, glass tilted 6 deg and shifted 0.55 forward | meets (D11) | check 14; a flat glass shifted 0.25 would have 0.10 |
| LCD glass to roof bonding plane | 0.15 | adhesive frame | |
| Cover glass in its recess, radial | 0.25 | meets | on a 0.13 tape ring; top face 0.12 below flush |
| OPTIONAL retarder film (E9) under the cover glass: to the display / to the bore of the tape ring / to the roof ledge | 0.98 / 0.80 / 0.03 | 0.25 / 0.25 / 0.023 | dia 23.4 x 0.10 on the glass underside; it overlaps the dia 22 aperture by 0.70 (0.50 at its clocking flat). Over the ledge it lies in the 0.13 tape gap: 0.007 left with the tape 10 % thin and the film 0.01 thick. A film thicker than 0.11 is cut to dia 21.5 instead (D35) |
| The same after its centring chain at the worst case: to the tape bore / beyond the aperture / at the flat | 0.05 to the tape bore / 0.20 / 0.00 | 0 or more | chain: film on the glass 0.25 (lamination nest), glass in its recess 0.25, tape ring in the recess 0.25 (0.75 against the bore, 0.50 against the aperture); at RSS 0.37 / 0.35 / 0.15. The dia 24.0 film of the last issue had 0.50 to the bore: less than its chain |
| Visor window in its recess, per side | 0.25 | meets | gaps filled with the window adhesive |
| Visor window below the visor face / top edge below the tub top | 0.15 / 0.15 | YAML values | glass seated on the recess floor: no adhesive line behind it (YAML `bond_line: 0`, N2) |
| Visor window seats on the recess floor: sides / sill / top | 0.50 / 0.40 / 0.65 | - | seats, not seals; measured on the sections in check 13 |
| Window adhesive frame: sill fillet behind the visor face / top bead below the tub top | 0.03 / 0.05 | must not be proud | fillet 0.12 x 0.12 on the shelf, bead 0.10 on the top edge; bonded width on the glass 0.40 (sides, top) and 0.12 (front face at the sill) |
| Camera cube to hood (sides, top, front pad) | 0.25 (sides 0.265) | meets | 0.3 mm lead-in chamfers at the mouth of the hood |
| Prism to roof | 0.19 | YAML stack value | go gauge 4.90 for the bay, 4.85 for the prism top |
| Prism hypotenuse to hood rear wall | 0.26 | meets | |
| Hood gasket bead to the prism (bead as squeezed, at constant volume) | 0.30 | 0.10 required | bead 0.5 x 0.33 as dispensed, 0.43 mm3, centred 0.35 in front of the rear face of the hood rear wall |
| Hood gasket bead: squeezed land on the cube top / peak squeeze / standing load | 0.17 mm / 24 % / about 0.11 N per hood | 0.10 mm and 30 % | the half behind the cube hangs 0.08 below the cube top like a curtain; load estimated at E = 1.5 MPa |
| Hood gasket bead: placement window of its centre line | -0.10 / +0.08 | needle guide good to +-0.075 | rear edge on the wall underside, front edge behind the chamfer (0.31 mm of flat over the cube) |
| LCD glass to camera cube | 0.63 | meets | |
| Battery to foam pad | 0.55 | 0.40 swell + 0.15 | battery to LCD glass 0.85; the fixing adhesive (0.05 max) comes out of the 0.15 |
| Battery leads and joints (envelope to 2.4 above the PCB) to the tub | 0.96 | meets | to the foam pad / LCD glass 3.70 / 3.73; joint top 0.15 below the free height |
| Ball in its hole, radial | FR-4: 0.05; PA12: 0.075 | potting gap | drilled dia 1.10 / reamed dia 1.15 |
| Ball top to PCB underside | 0.10, filled with epoxy | - | the ball bears on a dia 1.6 copper land inside a dia 2.5 zone without vias or tracks |
| Ball top to its land with the plate at its lower incoming limit, the sheet at its thinnest and the ball set high | 0.02 (ball of exactly dia 1.0) | 0.02 required | this sets the incoming limits of the plate: FR-4 0.76 to 0.90, PA12 0.83 to 0.92 (YAML, N6) |
| The same with a grade 100 ball at its upper diameter limit (+0.0127, as remembered) | 0.007 (PA12 0.014) | **below 0.02 (D33)** | the ball lot is measured; the lower plate limit is raised by the oversize of the lot (0.773 at the grade limit). Grade 25: 0.018 |
| Ball feet below the base plane | 0.10 | - | set on the gauge plate, not by the plate |
| Photodiode to baffle ring | 0.594 | meets | ring dia 6.6 / 8.2 (both builds) |
| Grain LEDs to the baffle ring / to the opening wall | 0.604 / 0.757 | meets | FR-4 build; PA12 build 0.604 to ring, wall and spokes |
| Baffle ring to the wall of the grain opening (FR-4 build) | 2.40 | meets | placed by the ring tool on the two sprung pins of the lamination jig, before lamination |
| Baffle ring crest above the base plane (z) | 0.05 nominal; 0.00 to 0.13 worst case | accepted 0.00 to 0.15, never proud | ring lapped to plate thickness + 0.15 - tape thickness, +0.00 / -0.03 (E16): 0.85 / 0.82 / 0.805 for a 0.10 / 0.13 / 0.145 tape on the 0.80 plate; lapped to 0.82 regardless of the plate it would be -0.03 to 0.22 |
| Potting surface (z, centre of each compartment) | never nearer the base plane than 0.05 (the modelled solid); accepted from the ring crest to 0.10 inside it, at most 0.20 | - | nominal crest: 0.05 to 0.15, fill target 0.10; a wall meniscus may reach, not pass, the base plane. PA12 build (crest on the base plane): 0.05 to 0.10, target 0.075 |
| Potting over the photodiode | 0.47 at z 0.05; 0.32 at z 0.20 | 0.30 required | LEDs 0.45, photodiode 0.48 high |
| Support posts on the PCB | 0 (contact) | datum | posts set the PCB height; nearest listed part 0.45 mm (U1 to posts E), 0.60 (U6 to post B+) |
| Ball-foot zones (dia 2.5) to the nearest soldered part / post foot | 0.312 (U11; U10 0.378, U1 0.45) / 2.15 | 0.3 to a part (N7), no overlap | check 10; the battery lies over the two rear zones by decision |
| LCD flex tail (representative) in its keep-out: in x / at the rear / underside over a part of the allowed 0.7 mm | 0.25 / 0.088 / 0.225 | inside; 0.2 over the part | YAML `tub_keepouts.lcd_tail` (N10), check 12; PROVISIONAL tail |
| Marker in the cradle nest, radial | 0.25 | meets | |
| Base plate above the nest strip and pads / tub rim above them | 0.10 / 0.35 | - | the three balls carry the marker |
| Lip and latch nose above the tub top | 0.25 | meets | the marker floats up to 0.25 against them when pins are fitted (YAML cradle.float) |
| Lip to the visor windows / cover glass / vent hole | 1.55 / 3.22 / 22.9 | clear | the lip is 12 mm wide, the window recesses start at x = +-7.25 |
| Latch to the cover glass / vent hole | 7.31 / 18.7 | clear | |
| Latch to the walls of its well | 1.2 (sides), 1.30 (stop ribs), 2.2 (front) | printable gaps | |
| Spring-pin plunger in the base and adhesive slot | 0.565 | meets | pin diameters PROVISIONAL |
| Spring-pin barrel in the printed slot; cradle PCB in its pocket; USB shell | 0.25 | meets | |
| Light bundle to the visor opening: sides / sill / top | 0.377 / 0.397 / 0.054 | **top has no margin** | accepted, see below |
| Marker on the base-face seat plate (GL1-050): ball to its pocket floor / to the pocket wall / rim to the plate | 0.40 / 1.18 / 0.55 | 0.25 / 0.25 after 0.6 of location / 0.30 | check 18; the base face rests on three pads of 24.7 to 28.0 mm2 |
| Base plate on the ball gauge plate (step 2): legend to the relieved plate face / legend to a boss, less the location on the balls | 0.27 / 0.99 | 0.05 / 0.15 | check 18; three bosses dia 7.0 of 35.0 mm2 each; the gauge holes measured on the solid are dia 0.60 and set 0.100 of protrusion (an oversize grade 100 ball: 0.098) |
| Legend ink to the footprints of the fixtures on the outer face (gauge-plate boss + 0.1, seat pad + 0.6, bridge-gauge foot + 0.53) | 0.99 / 0.49 / 1.06 | 0.15 (print registration) | check 15, measured on the legend layer read back; no fixture rests on legend (D34) |
| Legend: smallest clear space between two pieces of ink | 0.15 | 0.15 (assumed = least line width) | check 15; 0.05 with the letter pitch of the last issue |

### Camera position (check 4; four directions on camera R, the upper field on both cameras)

Rev D: the PCB is located by the two spigots under posts B, 28.7 mm apart, with the cameras between them. With
+-0.075 mm of radial fit at each spigot:

| Quantity | Rev D (posts B, 28.7 apart) | Rev C (posts E, 8.4 apart) |
|---|---|---|
| Sideways play at a camera | +-0.100 mm | +-0.094 mm |
| Fore-aft play at a camera | +-0.075 mm | +-0.179 mm |
| Yaw of the board (a stereo-calibration item) | +-0.30 deg | +-1.02 deg |
| Upper field, full pupil, with the fore-aft play | 18.12 deg | 17.6 deg |

| Case | Shift of the optics (x, y, z) | Full pupil clear to (deg): left / right / up / down | Upper field against the required 17.6 | Worst field-point transmission |
|---|---|---|---|---|
| Nominal | 0, 0, 0 | 25.60 / 25.60 / 18.56 / 15.33 | +0.96 | 97.7 % |
| Spigot play sideways | 0.100, 0, 0 | 25.60 / 25.60 / 18.56 / 15.33 | +0.96 | 97.7 % |
| Spigot play plus 0.2 mm print tolerance sideways | 0.300, 0, 0 | 25.60 / 25.60 / 18.56 / 15.33 | +0.96 | 97.7 % |
| Fore-aft play, optics toward the visor | 0, 0.075, 0 | 25.60 / 25.60 / 19.02 / 15.71 | +1.42 | 97.7 % |
| Fore-aft play, optics away from the visor | 0, -0.075, 0 | 25.60 / 25.60 / 18.12 / 14.97 | +0.52 | 97.7 % |
| Fore-aft play plus 0.2 mm print tolerance | 0, -0.275, 0 | 25.60 / 25.60 / 17.05 / 14.07 | -0.55 | 93.5 % |
| Optics 0.2 mm low | 0, 0, -0.2 | 25.60 / 25.60 / 22.06 / 11.67 | +4.46 | 97.7 % |
| Optics 0.2 mm high, no play | 0, 0, 0.2 | 25.60 / 25.60 / 14.97 / 18.91 | -2.63 | 63.6 % |
| **Guaranteed case (YAML, N3): optics 0.2 mm high and 0.075 away from the visor** | 0, -0.075, 0.2 | 25.60 / 25.60 / **14.61** / 18.47 | -2.99 | 55.8 % |

Required field (YAML `cameras.field_required_deg`): +-26 deg horizontal, +17.6 / -8 deg vertical, with **14.5 deg of
upper field guaranteed**, defined as the worst case with the optics 0.2 mm high AND the 0.075 mm fore-aft play of the
spigot fit against it (decision N3). The horizontal limit of 25.60 deg is the 2.0 mm prism exit face, not the
opening (2.3 % of the assumed pupil is clipped at the field edge). The opening is wide enough sideways for the spigot
play plus the print tolerance, and the lower field has 3.7 deg in hand even with the optics 0.2 mm low.

The upper field is 18.56 deg nominally, 14.97 deg with the optics 0.2 mm high and **14.61 deg in the guaranteed case
(camera L 14.61, camera R 14.61), 0.11 deg above the 14.5 the YAML guarantees**. Check 4 traces the upper field on
both cameras in every case and compares the smaller value, so a change of the tub over one opening only is caught (the
self-test lowers the roof by 0.01 mm over camera L alone). The limit angles are found by bisection to 0.002 deg with pupil samples
that include the extreme rim points, and they agree with the closed form (1.70 tan(t) + 2.00 tan(t') = 0.80,
sin(t) = 1.517 sin(t') gives 14.967 deg without the play; with the play 14.611). Check 4 compares the with-play figure
with the YAML strictly and fails below it: there is no recorded shortfall any more. The margin is small: the upper
field loses 0.18 deg per 0.01 mm of roof or optics height, so 0.11 deg is 0.006 mm (the self-test lowers the roof by
0.01 mm and the check fails). The entrance-pupil position (0.4 mm below the cube top) and diameter (0.38 mm) are
assumptions; the lens data is not published.

**What uses up that margin** (check 4, table of the same name; closed form, one change per row). The YAML defines the
guaranteed case on the nominal fit of 0.075 mm, and that is the case the check compares. It does not cover:

| Change | Upper field in the guaranteed case | Against 14.5 |
|---|---|---|
| none (the case the YAML defines) | 14.611 deg | +0.111 |
| PCB locating hole at +0.05 on diameter (ordinary non-plated hole tolerance, assumed; a spigot 0.05 undersize does the same) | 14.496 deg | -0.004 |
| pupil dia 0.40 instead of the assumed 0.38 | 14.43 deg | -0.07 |
| pupil 0.5 instead of 0.4 mm below the cube top | 14.16 deg | -0.34 |
| roof 0.02 mm lower over the opening at -10 C | 14.26 deg | -0.24 |
| hole +0.05 and spigot -0.05 (fit 0.125) | 14.38 deg | -0.12 |
| fit 0.125 and the roof 0.02 mm lower | 14.03 deg | -0.47 |

The margin of 0.111 deg is worth 0.0063 mm of roof or optics height or 0.024 mm of extra fore-aft play. So the 14.5
degrees is a guarantee for the nominal fit and the assumed lens, as the YAML words it, not for a board whose locating
hole is at the top of its tolerance; the spigots have a go gauge (dia 1.10) but no gauge for their lower size. Proposal
N18 (`PROPOSED_PARAM_CHANGES.md`): either tolerance the two fits or restate the guarantee as 14.0 degrees on the
largest fit and the cold roof (the model gives 14.03 there).

**Test gate 2 follows from the guarantee, not from the nominal field** (assembly step 16; check 4, last table). A
target bar at +13.5 deg (the guaranteed 14.5 less 1.0 deg for the placement of target and unit in the join fixture) is
100 % clear on a nominal unit and on a unit in the guaranteed case, and so is its mirror image at -13.5 deg (the lower
field is clear to 18.5 deg when the optics sit high). A bar at +17 deg, the former gate, passes 100 % on a nominal
unit but only 66.8 % on a unit at the tolerance limit (55.8 % at +17.6 deg): it would have failed good units with the
adhesive wet.

### Display rotation (check 14, E12)

The LCD glass (26.6 x 30.3) sits in a pocket with 0.25 mm all round, defined by ribs, posts and the hood rear walls.
Left free it can turn **1.19 deg** either way (computed on the tub sections at the height of the glass and its frame as
a configuration-space obstacle, by bisection to 0.002 deg, and confirmed by a boolean on the solids: no interference at
1.17 deg, interference at 1.24 deg). The stops at the limit are one rear rib and the hood rear wall on the opposite
side, with a side rib and a post B; a pocket with continuous walls would give 0.95 deg (the manufacturing review's
"about 1 degree"). That is more than the 0.5 deg the aim-line budget allows for transfer, so (a) in step 9 the tilted
glass is pushed back by the squaring pusher on the centre of its front edge and beds on BOTH rear ribs (their faces
are coplanar in the model; the residual angle is about 0.15 deg per 0.05 mm of step between the two printed faces,
whose contact points are 19 mm apart), and (b) the residual angle of the drawn line against the visor flat is measured
at the factory and stored (fixture requirement in section 2). The check fails if a tub change lets the glass turn
more than 1.25 deg or removes one of the two ribs.

### Tolerance chains and thermal estimates

Arithmetic on **assumed** part tolerances, computed in check 2 (table "Tolerance chains"). The posts of the tub seat
on the PCB top, so the three chains through the laminate are different:

- seal joint = PCB thickness - printed step (post foot to seal face, 0.60) + adhesive sheet. **The plate thickness is
  not in this chain.**
- rim relief (tub rim above the base plane) = plate + sheet + PCB - printed distance post foot to rim (1.55).
- gap between each ball and its copper land = plate + sheet - ball top (0.90, set on the gauge plate).

Tolerances used: PCB +-0.08; sheet +-10 % (0.02 / 0.013); FR-4 plate +-0.10 (fabricator standard), PA12 plate +-0.10;
ball protrusion +-0.02. For the printed tub dimension two values are carried: +-0.10, which drawing GL1-010 REQUIRES of
the seal face and the rim measured from the post feet and which is a first-article gate, not a bureau capability; and
+-0.2, the bureau's general figure used elsewhere in this package.

| Chain | FR-4 build | PA12 build | Consequence |
|---|---|---|---|
| Seal joint, printed step +-0.10 | 0.40 +-0.13 RSS (0.27 to 0.53), +-0.20 worst case | 0.33 +-0.13 RSS (0.20 to 0.46), +-0.19 worst case | 61 mm3 (57) of adhesive at the upper RSS limit |
| Seal joint, printed step +-0.2 | 0.18 to 0.62 RSS, 0.10 to 0.70 worst case | 0.11 to 0.55 RSS, 0.04 to 0.62 worst case | 68.6 mm3 (64.4) at the upper RSS limit: **dispense 70 mm3 (PA12 build 65)**; nominal 49.8 (45.6) |
| Rim relief, printed +-0.10 | 0.25 +-0.16 RSS (0.09 to 0.41), +-0.30 worst case | 0.25 +-0.16 RSS, +-0.29 worst case | the rim stays 0.05 (0.06) above the plane of the ball feet at the worst case |
| Rim relief, printed +-0.2 | 0.01 to 0.49 RSS, -0.15 to 0.65 worst case | 0.01 to 0.49 RSS, -0.14 to 0.64 worst case | at the worst case the rim would touch 0.05 (0.04) BEFORE the balls: the rim height is a required dimension and is measured on every tub lot |
| Ball to land | 0.10 +-0.10 RSS | 0.10 +-0.10 RSS | with unsorted plates the ball could hold the laminate open: plates are sorted to 0.76 to 0.90 (PA12 0.83 to 0.92), which keeps at least 0.02 mm of epoxy under the ball |
| Prism top to bay roof (carried from the rev C review, not recomputed) | 0.19 +-0.21 RSS (cube and bond tolerances assumed) | same | go gauges in steps 1 and 13 |
| Cover glass below flush (tolerance carried from the rev C review) | 0.12 +-0.15 RSS (recess, tape, crystal) | same | still at or above flush on a minority of units; 0.2 mm more puck is the reserved remedy |

The base-plate edge reaches the tub bore through a lateral chain as well (check 14, fourth table): plate outline
+-0.10, jig pin in the PCB hole 0.025, spigot fit 0.075, spigot to bore axis and bore radius (printed). Against the
0.25 mm radial gap that is 0.17 RSS and 0.35 worst case with the plate centred by sprung fingers and the tub at
+-0.10 (0.26 and 0.50 at +-0.2; with a fixed frame round the plate 0.20 / 0.45 and 0.28 / 0.60). The gap is used up at
the worst case, which is why every laminated unit is tried dry in its own tub before the seal bead (step 14). Along
the PCB slot (2.2 long since N9; measured on the PCB solid in check 14) the spigot may move +-0.60; spacing error (0.2
to 0.3), hole position (0.05) and thermal movement at 70 C (0.13) sum to 0.38 to 0.48: a margin of 0.12 to 0.22 mm.

Thermal estimate over -10 to 70 C from a 23 C assembly (PA12 about 110 ppm/K, FR-4 15, soda-lime glass 9, LCD glass 4;
handbook values, not measured; check 2): the edge of the cover glass moves 0.07 mm against the tub (51 % shear of the
0.13 mm tape), a corner of the LCD glass 0.10 mm (67 % of its 0.15 mm frame). The PCB edge does not move against the
FR-4 base plate (same material); against the PA12 plate it moves 0.09 mm (72 % of the 0.13 mm sheet). The two spigots
move 0.13 mm apart against the PCB holes (the slot allows +-0.60). What the laminate, and the clear potting bonded
into it, do to the tilt reading is not computed here: it is to be measured (section 12, test item 1).

## 6. The z stack in revision D

| From | To | Item |
|---|---|---|
| -0.10 | 0.90 | ball feet (dia 1.0; 316 stainless grade 100 or better, or silicon nitride), potted in the dia 1.10 drilled holes of the base plate |
| 0.00 | 0.80 | base plate, routed FR-4 (alternative: PA12, 0.00 to 0.87) |
| 0.05 | 1.00 | clear potting in the dia 13 grain opening, shown at the level it must never pass (accepted surface z 0.05 to 0.15 for the nominal ring, target 0.10); baffle ring 0.05 to 0.87 and its black tape annulus 0.87 to 1.00 as drawn (tape 0.10 to 0.145 as available: the ring is lapped so that its crest stays at z 0.05) |
| 0.25 | 7.60 | tub (the side wall ends 0.25 above the base plane) |
| 0.80 | 1.00 | die-cut adhesive sheet 0.20 (alternative 0.87 to 1.00, 0.13), with the grain opening, the pad slot and three dia 2.0 holes round the feet (filled with epoxy) |
| 0.80 | 1.20 | perimeter seal joint 0.40 between the base land and the tub seal face (alternative 0.33); the adhesive also fills the radial groove down to z 0.25 |
| 1.00 | 1.80 | main PCB; the spigots of posts B reach from 1.80 down to 1.20 inside the hole and the slot |
| 1.80 | 3.80 | battery; 3.80 to 4.20 swelling allowance; lead joints to 4.20 |
| 4.35 | 4.65 | foam pad (4.35 is also the free height for parts, and the foot of the two rear glass ribs) |
| 4.65 | 5.40 | LCD glass; 5.40 to 5.55 adhesive frame |
| 5.55 | 6.35 | roof ledge; 6.35 to 6.48 tape ring (dia 28 / 25); 6.48 to 7.48 cover glass |
| 6.38 | 6.48 | OPTIONAL (E9, EVT trial): quarter-wave retarder film dia 23.4 x 0.10 with a clocking flat on the underside of the cover glass, inside the bore of the tape ring; 0.98 above the LCD glass (1.08 without the film), 0.03 above the roof ledge outside the dia 22 aperture |
| 7.60 | | top of the tub |

At the cameras: base 0.80, adhesive 0.20, PCB 0.80, cube 2.76, bond 0.05, prism 2.00 (top at 6.61), 0.19 clearance,
roof 0.80. Optical axis 5.61 mm above the base plane. Windows: z 4.20 to 7.45, y 17.85 to 18.25; their adhesive frame
reaches z 7.55 at the top and y 18.37 at the sill. Check 1 finds no volume overlap anywhere in the assembly, and check 16
none in the alternative build; the optional film is checked against every marker part by its own rows in check 2.
The outer face of the base plate (z 0) carries the legend (E10): a print about 0.02 mm thick, 0.03 at most, standing
below the base plane; the ball feet stand 0.10 below it. That 0.10 is set from the bare mask round each foot (the
bosses of the gauge plate), not from the ink, and every later reading from this face uses the same three areas.

## 7. Assembly sequence

Adhesive types are classes, not released part numbers; cure times are to be taken from the chosen product's data sheet.
Work on the tub upside-down in a nest that supports the roof ring unless a step says otherwise. The last column says
until when the result of a step can still be seen and corrected. **After step 17 nothing inside can be reworked.**
The sequence is written for the FR-4 build; what differs in the PA12 build is marked. Order of the board work: the
base plate is laminated to a board that carries the cameras only; the cell and the prisms go on after lamination,
potting and their cures, so that no press load passes through bonded prisms and no heat or vacuum reaches the cell.
Step numbers 1 to 19 are those of the last issue (`docs/MANUFACTURING_PLAN.md` refers to them); what the manufacturing
review found missing is worked in as step 11a and as new parts of steps 1, 9, 13, 16 and 19. **The outer face of the
base plate carries the legend: wherever a step takes that face as a reference (steps 2, 11, 12, 14, 15, 19) the
fixture or gauge bears on the bare mask round the three ball feet, never on the print** (section 2, D34).

| Step | Operation | Check or gauge | Inspectable / reworkable until |
|---|---|---|---|
| 1 | Incoming inspection; ball lot measured; baffle rings lapped to the plate lot and the tape | gauges below | - |
| 2 | Ball feet, stage 1, on the three bosses of the gauge plate | protrusion 0.10 +-0.02, all three; epoxy ring complete from below | step 11 (re-pot) |
| 3 | Adhesive sheet onto the base plate, in the lamination jig | sheet clear of the seal land all round | step 11 |
| 4 | Surface preparation of the bonding faces | - | - |
| 5 | Cover glass on its tape ring, then the rim-gap seal (trial units: film laminated and clocked first) | crystal below the top face (0.12 nominal), never proud; trial units: edge mark at the nose groove | always (outside) |
| 6 | Visor windows: seated, adhesive frame round the edge | glass below the visor face; frame closed on four sides; nothing in the opening | step 15 (through the bays) |
| 7 | Vent disc | centred on the hole | step 15 |
| 8 | Hood gaskets along the needle guide, cured | bead on the flat of the rear wall, not on its chamfer | step 15 |
| 9 | LCD, tilted in, squared against the two rear ribs with the pusher; foam pad | on both ribs when the rear strip tacks; bonded all round the aperture | step 15 |
| 10 | Tub leak test (windows, cover glass, vent) | pressure decay on the gasketed plate | step 15 |
| 11a | **Board underside cleaned of flux, then the photodiode dark offset read on the bare board** (before the ring, the sheet and the potting go on) | no residue at 10x and under UV; dark offset in limit BEFORE the ring is taped on | within 11a only (clean again); not after the ring or the plate is on |
| 11 | Board, cameras only: baffle ring, base plate laminated, stage 2 cured | ring gaps; ring crest 0.00 to 0.15 inside the base plane (bridge gauge); wet-out at pad slot and opening; grain LEDs and photodiode tested | step 12 |
| 12 | **Clear potting of the grain opening** | level checked WET, then bubbles and surface after cure | wet: yes; after cure: none |
| 13 | Cell and leads soldered, joints cleaned, THEN thermal-adhesive dabs on the two cell thermistors, prisms, edge fillet; test gate 1; serial number marked | both dabs bridge thermistor and cell and are tack-free; prism height; **test gate 1** including both thermistor readings; serial number in its box | step 15 |
| 14 | **Dry trial close** of the unit in its own tub | seats on all posts without force; rim relief at the four rim stations of the bridge gauge | - (pair and mark) |
| 15 | Seal bead into the tub; tail into J1; close in the join fixture | LCD test pattern; rim relief 0.25 +-0.15, four readings equal within 0.05 (bridge gauge) | step 17 (open time of the adhesive) |
| 16 | **Test gate 2** with the adhesive still wet; top-up fillet from outside | bar at +13.5 deg not darker than the bar at -13.5 deg; continuous visible fillet all round | step 17 |
| 17 | Cure under the press weight, 45 C at most | - | no rework after this |
| 18 | Leak test, functional test, dark frames | pressure decay | - |
| 19 | Thermal cycle; soak at room temperature; **second leak test**; six-face calibration; rest; level zero on two seats; display rotation | unit within 1 K of the chamber before the leak test and before the zeros; pressure decay as in step 18; both zeros and the rotation stored | - |

1. **Incoming inspection.**
   - Tub: bonding plane, recess floor, seal face and post feet (one plane each, +-0.1); REQUIRED +-0.1 from the post
     feet: seal face 0.60 below them, rim 1.55 below them (a tub outside these is not used: they set the seal joint
     and the rim relief). Recess dia 28.5; window recesses 5.5 wide; the dia 42.6 disc must pass the ledge ring and the
     dia 43.7 disc must enter the bore below it; the 4.90 block must stand on the post feet under each bay roof; the
     dia 1.10 ring gauge must go over both spigots (posts B); a bare PCB and then the **dummy unit** must drop over the
     spigots and seat on all eight posts without force, its two blocks inside the hoods (dress an oversize spigot with
     a hollow punch or a fine file, never by enlarging the PCB hole). Vent hole, grooves, camera openings clear of
     powder.
   - FR-4 base plate: thickness over the mask, measured on bare mask and not on the legend (use 0.76 to 0.90, note the
     value of the lot), a dia 1.0 ball drops through each hole, holes free of mask, no nub on the edge, flat; legend on
     the underside only, reading correctly seen from below (not mirrored), none inside dia 8.5 round a foot hole,
     letters not filled in. (PA12 plate: sort to 0.83 to 0.92, flatten to 0.3 mm or better, ream the three foot holes
     to dia 1.15; legend laser-marked.)
   - Ball feet (E8): 316 stainless of grade 100 or better, or silicon nitride; never 440C. The certificate decides;
     a magnet is only a rough sorter (it picks up 440C strongly, 316 weakly or not at all, silicon nitride not at
     all). Measure the diameter of a sample of the lot with a micrometer: a lot that
     is oversize by d raises the lower limit of the plate thickness by d (0.76 + d; a grade 100 lot may be 0.013 over,
     D33), because the gauge plate sets the protrusion, not the top of the ball.
   - Baffle rings (FR-4 build): cut from the sprue, trim the gate flush, lap the bonding face in the pocket gauge to
     the measured plate thickness + 0.15 - the measured thickness of the black tape (0.82 for a 0.80 plate and a 0.13
     tape, 0.85 for a 0.10 tape, 0.805 for 0.145), +0.00 / -0.03.
   - Clean all parts with isopropanol and dry them.
2. **Ball feet, stage 1 (gauge plate).** Lay the base plate, PCB side up (legend down), on the three bosses of the
   gauge plate between its loose guides and drop one 1.0 mm ball into each hole: the three balls, each seating on the
   rim of its dia 0.60 gauge hole, locate the plate. The plate rests on the boss tops only, on bare mask; look from the
   side that no legend lies on a boss (it cannot on a plate to drawing: 0.99 mm). Clamp it with the weight whose three
   annular feet stand over the bosses. Feed about 0.27 mm3 of epoxy into each dia 1.10 hole
   FROM ONE SIDE of the ball, so that it runs round and under the ball and pushes the air out on the other side, until
   the annulus is full (PA12 plate, dia 1.15: 0.40 mm3); the dome over the plate must not exceed 0.08 mm. Cure
   completely before unclamping (two-part, or UV from above followed by the secondary cure: the lower half of the
   joint is in the ball's shadow). After demoulding look at each foot FROM THE UNDERSIDE: a complete ring of epoxy
   round the ball, flush with the base plane, no void (the half below the ball's equator is the only mechanical lock
   against pull-out; fill a void from below). Check the protrusion, 0.10 +-0.02 mm on all three: plate outer face up
   on a flat support, an indicator with a flat tip zeroed on the bare mask beside the foot (inside its dia 8.5
   zone, never on a legend block) and then moved onto the ball.
3. **Adhesive sheet.** In the lamination jig: the base plate, PCB side up, centred by the three sprung fingers; the
   die-cut sheet (0.20 mm; PA12 build 0.13 mm) on its carrier liner, located by the liner's two tooling holes on the
   jig posts. Laminate it to the plate; grain opening, pad slot and the three foot holes aligned, the sheet (r 21.1)
   clear of the seal land (from r 21.35) all round. Leave the top liner on. Do not place the sheet by eye: 0.25 mm of
   error puts adhesive on the 0.4 mm seal land.
4. **Surface preparation.** Prime or plasma-treat every PA12 bonding face according to the adhesive maker: recess
   floor, LCD bonding plane, seal face with the corner to the side wall, visor-wall underside, window recesses, vent
   pad, hood rear-wall undersides. FR-4 plate: land and edge wiped clean, abraded only if the adhesive maker asks for
   it on solder mask. (PA12 plate: land and edge primed like the tub.)
5. **Cover glass.** Tub top-up on a mandrel that supports the roof ledge from inside. Apply the 0.13 mm transfer-tape
   ring (dia 28 / 25) to the recess floor, remove the liner, centre the crystal (0.25 mm radial gap) and press with the
   load the tape maker specifies. After the dwell, seal the gap round the crystal (0.25 wide, 1.13 deep, about 25 mm3)
   with a WICKING-grade black sealant run in from a needle resting on the edge of the crystal: a 30-gauge needle does
   not enter a 0.25 mm gap, and a paste would bridge it. The sealant must not flood onto the crystal, which lies only
   0.12 mm below the top face. The EVT crystal is not step-proof: label the units.
   *Units of the retarder-film trial only (E9, optional):* before the tape ring, laminate the die-cut quarter-wave
   film (dia 23.4 with one clocking flat, `dxf/GL1-035`) to the underside of the crystal in the film lamination nest:
   crystal in the pocket, film centred by the loose ring within 0.25 mm, its flat against the straight stop, no
   bubbles. The flat is what carries the direction of the film axis: the converter cuts it at the angle to the axis
   that the display trial fixes. Before the unit leaves the nest, **mark the ground edge of the crystal** at the middle
   of the flat (the scribed line of the nest; a paint dot on the edge, not on a face). Measure film plus adhesive:
   more than 0.11 mm does not fit over the roof ledge (D35); such a film is cut to dia 21.5 instead. Then apply the
   tape ring to the recess floor as above and set the crystal down **with its edge mark at the nose groove** of the
   tub (the groove on the centre line toward the visor), within 0.7 mm on the rim, which is 3 degrees; the rim sealant
   afterwards hides the mark. The film must end inside the dia 25.0 bore of the tape ring, because a film under the
   tape would lift the glass off its seal: with film, crystal and tape ring each 0.25 mm off in the same direction
   0.05 mm is still left (check 2), and the round edge of the film stays 0.20 mm outside the aperture; only the flat can
   then just reach the aperture edge. Check through the glass that the flat lies toward the visor and parallel to it.
6. **Visor windows.** Tub with the VISOR FACE UP, so that each glass lies on its recess floor by its own weight, and
   with the window stop on the tub top (its 0.15 mm step closes the open end of each recess). Lay each 5.0 x 3.25 x
   0.40 window in its recess, bottom edge against the shelf (z 4.2), top edge against the stop, centred between the
   side walls (0.25 mm each side). With a THIXOTROPIC (non-wicking) light-cure adhesive: fill the two side gaps, run
   a fillet about 0.12 mm along the shelf in front of the bottom edge and tack-cure; remove the stop and run a bead
   about 0.1 mm high along the top edge, below the tub top; cure through the window. The four runs must join into a
   closed frame. **Nothing is to be wicked behind the glass**: a film on the top seat would end as a fillet at the roof
   edge of the opening, where the upper field has 0.054 mm (0.055 mm of fillet costs the required 17.6 degrees). The
   side and sill edges of the opening have 0.38 and 0.40 mm in hand. The glass is then 0.15 mm below the visor face
   and its top edge 0.15 below the tub top. Inspect the inner face through the open bay and swab it if needed; the
   bay stays reachable until step 15.
7. **Vent.** Tub upside-down. Apply the vent disc to the pad inside the roof, centred on the 1.0 mm hole; press evenly.
8. **Hood gaskets.** Hook the needle guide on the rear face of each hood rear wall and dispense a bead of the black
   gasket material on the flat underside of the wall: 0.5 mm wide, 0.33 mm high, 3.9 mm long (0.43 mm3), its centre
   0.35 mm in front of the rear face (window -0.10 / +0.08: the bead must stay on the flat, behind the chamfer). Cure
   it now. Half of the bead will hang behind the cube like a curtain, the other half is squeezed by the cube top to
   the 0.25 mm slit (24 %, a land of about 0.17 mm, about 0.1 N per hood); nothing is wet when the PCB goes in.
9. **LCD (tilted in, D11; squared, E12).** Apply the 0.15 mm adhesive frame to the top face of the LCD glass, vent channel at the
   rear right corner, and remove its liner. Pick the glass up with the vacuum pen on its underside. Enter rear edge
   first, tilted about 6 deg and shifted 0.5 to 0.6 mm toward the visor, until the rear corners have passed the
   seating ledge (0.28 mm clearance). Still shifted, raise the rear edge to about 0.7 mm below the roof (z 4.8): the
   front edge is then just below the feet of posts E and the rear face of the glass is level with the two rear ribs,
   which reach down to z 4.35. Push the glass back against these ribs **with the squaring pusher** (0.75 mm; the ribs
   are the stop and the datum): the pusher bears on the middle of the front edge, so the glass beds on BOTH ribs and
   is square to them (E12: pushed at one corner by hand it can sit up to 1.19 degrees turned in its pocket). With the
   pusher still on, raise the rear edge to the roof until the rear strip of the adhesive frame tacks: from then on the
   rotation is fixed. Hinge the front up (the pusher lets go; the glass passes between posts B with 0.25 mm on each
   side) and press the glass onto the bonding plane all round the aperture. It ends 0.15 mm behind its nominal
   position, 0.10 mm in front of the ribs, inside the 0.25 mm pocket clearance. Leave the flex tail standing. Stick
   the foam pad to the underside of the glass over the battery zone.
10. **Tub leak test.** Close the open underside of the tub on the gasketed plate (seal on the seal face and the
    visor-wall underside), occlude the vent, and run a pressure-decay test of cover glass, windows and vent pad. A
    leak found here can still be reworked; after step 17 it cannot. Recommended on every EVT tub.
11. **Board, cameras only: cleaning, baffle ring, lamination.** No cell and no prisms yet.
    - *Step 11a, clean the underside.* The board comes from lead-free reflow with flux residue on it, and the
      underside is about to be sealed for good: under the black annulus, the adhesive sheet (the only barrier at the
      pad slot) and the clear potting, round a photodiode input of high impedance. Clean it with a solvent that the
      assembler names for the flux used AND that the data sheets of the sixteen LEDs and of the photodiode permit on
      their clear encapsulants (these are the parts being scrubbed; if the two lists do not meet, the flux is changed,
      not the rule), locally with swab and brush (no immersion: the camera cubes are on the other side and their
      washing rules are an open item), most carefully round the photodiode and its tracks, on the lands
      the sheet will seal (round the grain opening, round the pad slot, the three foot lands) and on the seven pads;
      rinse with fresh isopropanol, blow dry, then bake dry at 60 C at most for about 30 minutes (provisional figures;
      there is no cell on the board yet). Check at 10x and under a UV lamp (rosin fluoresces): no residue. Handle the
      cleaned face by the edge only. **Then, still in 11a and before the ring or the plate goes on,** put the bare
      board on the pogo fixture (powered through the cell-lead pads, E4) and read the dark offset of the photodiode
      amplifier in the dark: it must be inside its limit (not yet defined). A leaky input is found here, while the
      underside is still open and can be cleaned again. After the ring is taped on and the plate is laminated nothing
      is cleaned any more: no solvent on the black annulus, on the cut edge of the adhesive sheet or inside the 6.6 mm
      bore of the ring. A board that shows a leaky input after lamination is not re-cleaned; it is set aside.
    - PCB component-side down in the support nest of the lamination jig, on its two sprung pins (they stand 2 mm
      above the PCB underside).
    - Baffle ring (FR-4 build): apply the black adhesive annulus to the lapped face of the ring; place the ring round
      the photodiode with the ring tool, which registers on the two pins; press. The gap to the photodiode corners
      is 0.59 mm nominal and must be visible at all four.
    - Lamination: remove the liner of the adhesive sheet; put 0.52 mm3 of two-part room-temperature epoxy ON EACH
      COPPER LAND of the PCB (stage 2: 85 % of the 0.61 mm3 sheet hole, so that it cannot flood the sheet; PA12 build
      0.35 of 0.41 mm3); lower the base plate, centred by the sprung fingers; it presses the two pins down flush.
      Press with the press plate (compliant facing: the face under it carries the legend) at the pressure the tape
      maker specifies (about 116 N for 0.10 MPa on 1157 mm2);
      the load passes through the nest into bare board areas, not through the cameras. Inspect the edge of the sheet
      at the pad slot and round the grain opening from the base side: no gap, no lifted edge. Cure stage 2 (room
      temperature; it lies between two opaque boards, so light cannot reach it).
    - Ring crest: with the BRIDGE GAUGE on its three feet round the balls (bare mask; not a depth gauge laid across
      the opening, which would rest on legend), the crest of the ring must lie between the base plane and 0.15 mm
      inside it (0.05 nominal). A crest proud of the base plane is pared flush with a flat blade guided on
      the base underside. Note the crest depth and the depth of the opening (plate + sheet) for step 12.
    - Test the sixteen grain LEDs and the photodiode on the pogo fixture now (the dark offset again, against the value
      of 11a): after potting they cannot be reworked.
12. **Clear potting of the grain opening** (YAML `fill_surface_z`: never nearer the base plane than z 0.05, aimed at
    z 0.10, accepted to z 0.20 and from the ring crest to 0.10 inside it).
    - *Nest and level.* Unit underside up in the potting nest, levelled on the base underside to 0.25 degrees or
      better. (Laid on a plain plate the board would rest on its camera cubes and connector, tilted.)
    - *Dam.* The wall of the dia 13 opening (0.80 of plate and 0.20 of sheet) is the dam. Stick the low-tack mask, an
      annulus dia 15 to dia 24, on the underside with its hole clear of the edge of the opening: the edge must stay a
      free, sharp edge that pins the meniscus; a mask flush with the opening would let the potting climb it and leave
      a lip proud of the base plane. The mask must not reach the three seat zones round the balls: the bridge gauge
      stands there for the wet level check.
    - *Fill.* Degas the mixed potting. Dispense by volume, inside the baffle ring first, then outside it, to the fill
      target = the middle of the accepted window. For the nominal unit (crest at z 0.05, opening 1.00 deep) that is
      z 0.10: **25.0 mm3 inside the ring and 68.3 mm3 outside** (93.4 in all; the 26.7 + 72.3 = 99.1 mm3 of the model
      would reach z 0.05, the level that must never be passed). Correct per unit: +3.4 mm3 inside and +8.0 mm3 outside
      for each 0.1 mm of extra opening depth, and the same amounts less for each 0.1 mm that the target lies deeper.
      (PA12 build, crest on the base plane: target z 0.075, 25.9 mm3 inside the ring and 24.6, 24.6 and 15.8 mm3
      between the spokes, 90.9 in all.) Degas again under the vacuum bell (air is trapped under the 0402 bodies) and
      let it level.
    - *Level check, wet.* Before cure, measure the surface in the middle of each compartment with the bridge gauge
      (optical height sensor, or the indicator lowered until it just wets): it must lie between
      the ring crest and 0.10 mm inside it, never nearer the base plane than z 0.05 and never deeper than z 0.20
      (nominal crest: z 0.05 to 0.15; a dispenser good to +-3 % places it within +-0.03). The crest of the ring must
      stay uncovered. A wall meniscus may reach the edge of the opening but not pass the base plane. Add with a
      needle or wick off with a swab now; nothing can be corrected after cure.
    - *Cure* completely, by the data sheet, at 60 C at most (adhesive sheet, PA12 ring), before the mask comes off.
    - *Inspect.* Under a magnifier: no bubble over the photodiode or over an LED, none larger than 0.3 mm elsewhere
      (provisional criterion). Surface as above and **nowhere proud of z 0.05**, not tacky; the ball feet are then at
      least 0.15 mm below it. Reject a unit with a proud or tacky surface.
13. **Cell, thermistor dabs, prisms, test gate 1, serial number.** The order of the first two items matters:
    cleaning comes before the dabs, because a solvent would wash a wet dab.
    - Fix the cell with transfer adhesive of 0.05 mm or less; dress its two leads to the pads in the strip beyond the
      protection-board end of the cell (x -19.3 to -17.5, y -7.0 to -1.5) and solder them; lead and joint must stay
      below 2.4 mm above the PCB. Clean the two joints, let the solvent dry, inspect. From here on nothing may be cured
      above 45 C.
    - Thermistors, after the cleaning (DESIGN_SPEC section 4, E2): put a dab of thermal adhesive, about 1 mm3, between EACH of the two
      cell thermistors (NTC1 of the charger and NTC2 of the MCU, 0402 parts within 1 mm of the cell edge) and the side
      of the cell, so that each dab bridges its thermistor to the cell. The dab stays below the top of the cell (2.0 mm
      above the PCB), off the post-foot keep-outs and off the lead pads; it cures at room temperature. Check by eye
      that both dabs bridge: without them the charger and the firmware read the board, not the cell. **Both dabs must
      be tack-free (gelled, by the data sheet) before step 14**, where the unit is turned component-side down over the
      LCD, and fully set before step 15 seals them in.
    - Bond each prism on its cube with UV adhesive at the four corners only (air gap over the lens), exit face toward
      +y at y = 16.6, in the prism jig; cure. Prism top 4.85 mm or less above the PCB on the height gauge.
    - Run a fine fillet (0.2 mm) of the seal adhesive round the edge of the PCB onto the base plate, inside r 21.3,
      and let it gel: a second barrier behind the 1.06 to 1.37 mm lands of the sheet.
    - **Test gate 1** on the pogo fixture: supply through the pads, both camera IDs, one frame per camera on a target
      (prism centring), IMU, charge current, grain LEDs and photodiode through the potting, and **both cell
      thermistors**: the MCU's reading (NTC2) within 2 K of the room, and the charger's (NTC1) shown plausible by a
      charge that starts at room temperature and stops when the firmware pulls TS low (proposed limits; a thermistor
      without its dab still reads the room here: the dab itself is the visual check above).
    - **Serial number.** The unit now has an identity (the processor's unique number, read at gate 1). Mark the short
      serial derived from it inside the serial-number box of the legend (14.0 x 2.8 mm; unit underside up in the
      potting nest): by laser on the black mask (preferred: no height), or by ink-jet with a mark 0.03 mm thick at
      most, cured. The box lies outside the three seat zones and 5 mm from the nearest fixture footprint (check 15), so
      a mark has no effect on any later reading. On the PA12 plate: laser.
14. **Dry trial close.** Before any seal adhesive: put the unit on the hinged carrier of the join fixture and close it
    into ITS tub, dry (the LCD tail is not mated). It must turn onto the two spigots and seat on the eight posts
    without force, the cube tops bedding into the hood gaskets; with the bridge gauge on its three feet (bare mask
    round the balls) the tub rim must lie 0.25 +-0.15 mm below the base face at its four rim stations (r 22.35 at 45,
    135, -135 and -45 degrees from +x), the four readings equal within 0.05. A unit that binds at
    the bore (the plate edge has 0.25 mm; the lateral chain is 0.17 to 0.28 RSS and 0.35 to 0.60 worst case) or at
    the hoods is tried in another tub. Mark the pair; open again.
15. **Seal bead, tail, close.** Tub upside-down in the join fixture. Dispense 70 mm3 of the black seal adhesive
    (PA12 build 65) as one continuous bead into the corner between the seal face and the side wall all round the
    arc (both faces look up) and along the underside of the visor wall, without a gap at the two D corners. Put the
    PCB / base unit on the hinged carrier, open; make the one U-fold in the LCD tail, insert it into J1 and close
    the actuator under a magnifier (open issue 9: tail length and where the surplus loop goes). Power the unit
    through the pogo block and check an LCD test pattern through the window of the nest. Close the carrier: the
    unit turns about the fixture hinge onto the two spigots and the eight posts. Press with the press plate. With
    the bridge gauge through the openings of the press plate, at the same four rim stations, the base plate must stand
    0.25 +-0.15 mm proud of the tub rim, the four readings equal within 0.05 and equal to those of the dry close (an
    unseated or tilted unit shows as unequal readings). Both sets of readings come from the same three areas of bare
    mask, so the legend is not in the comparison.
16. **Test gate 2 and fillet**, within the open time of the adhesive, in the join fixture (pogo block through the press
    plate, LCD seen through the nest window, cameras through the open front): frames from both cameras through the
    windows (prisms centred in their openings, no gasket in the field, **the upper edge of the field free of
    adhesive**), dark frames under strong side light, LCD, IMU. The test for the upper edge is set from what the YAML
    guarantees, not from the nominal field: the gate 2 target shows an evenly lit bar at +13.5 degrees (the guaranteed
    14.5 less 1.0 for the placement of target and unit) and one at -13.5 degrees, and in each camera the upper bar
    must not be darker than the lower one (proposed limit: not more than 10 % darker; to be set on the first units).
    Both bars are fully clear on every in-tolerance unit (check 4), so the gate cannot fail a good unit with the
    adhesive wet; on a unit whose optics sit low the lower bar is the dimmer one and the unit passes. What the gate
    finds is adhesive or gasket at the roof edge of the opening: from about 0.06 mm on a unit at the tolerance limit,
    from about 0.28 mm on a nominal unit (0.18 degrees per 0.01 mm). The finer question, where the dimming starts, is
    validation test O1, measured dry. A bar at +17 degrees, the former gate, passes only 67 % of the light on a unit
    at the tolerance limit and is not used.
    If anything fails, open the carrier, wipe the adhesive off and correct. Then top up from outside into the
    0.25 mm groove between base plate and wall until a continuous fillet is visible all round the rim, across the
    visor front and at both D corners; wipe the excess.
17. **Cure** the seal adhesive under the press weight for the full time on its data sheet, at room temperature or at
    45 C at most (the cell is inside).
18. **Leak test** in the chamber with the vent hole and its grooves occluded by the soft pad (pressure decay; the free
    air volume of the unit is 4.2 cm3, check 13). Then functional test, including a dark-frame light-leak test of
    both cameras under strong side light.
19. **Thermal cycle, second leak test, calibration.**
    - After full cure run each unit through one cycle of -10 to 50 C so that the cure stresses of the potting and of
      the seal relax.
    - **Soak.** Leave the unit at room temperature, beside the leak-test chamber, for at least 60 minutes after it
      leaves the temperature chamber (provisional: to be set from the settling of the pressure reading on first units)
      and until its cell thermistor reads within 1 K of the room. A pressure-decay reading on a 4.2 cm3 unit follows
      temperature: 1 K is 0.34 % of the absolute pressure, about 340 Pa, enough for a false pass or a false fail.
    - **Second leak test**, as in step 18 (same chamber, vent occluded, same limit): a leak that the cycle opens
      would otherwise leave unseen. A unit that fails here cannot be reworked; it goes to the seal investigation.
    - **Six-face calibration** (started over USB): in the six-face fixture, which holds the marker still in six
      orientations with spring pins on its pads. That fixture is NOT designed yet (section 2).
    - **Rest.** The six-face step runs over USB with the charger on and the processor awake: the unit is warmer than
      in use. Disconnect it and let it rest free for at least 30 minutes (provisional) and until the cell thermistor
      is within 1 K of the room before the zeros (`docs/MANUFACTURING_PLAN.md` 6.7: "unit at room temperature first").
    - **Level zero on two seats** (E11), on the calibration seat plates GL1-050 on a surface plate, with nothing on
      the pads. Wipe plate and base before every placement (10 micrometres of dust under a foot is 0.4 mrad). Ball
      seat: marker on the plain plate in nest A, visor flat against the fence and round wall against the stop pin,
      read; lift, turn 180 degrees, nest B, read. Base-face seat (the turf seat, the default for a read): the same on
      the plate with the seat pads; the balls hang in their pockets. Both zeros are stored. (The plates give the
      0 / 180 degree reversal; a four-position zero needs another fixture, section 2.)
    - **Display rotation** (E12): marker on a seat plate against the fence, test line on the display; the angle of
      the line against the fence is measured from above and stored (fixture requirement in section 2).
    - Temperature compensation, stereo and grain reference: `docs/MANUFACTURING_PLAN.md` section 6.
    None of this uses the charging cradle.

Cradle: drill the four dia 1.6 x 3 pilots at the spot marks; solder the pins into the cradle PCB square to the board in a
soldering jig (four pins at x = -7.62, -5.08, -2.54, 0.0 for the consumer cradle, all seven for the factory fixture) and the
USB-C receptacle; screw the PCB against the pocket ceiling with four M2 thread-forming screws (the pins come up through the
slot in the nest floor); fit the four bumpers. First articles from two builds: 3000 insert / release cycles with the
hook position measured before and after, and a pull test of 12.4 N at the pin row (3 x the seven-pin force).

Using the cradle: dry the marker first. Tilt it nose-down, slide its top front edge under the lip, press the rear down
until the latch clicks (about 11 N). To remove: press the thumb tab down (9 to 12 N; it stops on its rest), the pins
lift the rear about 1.3 mm, lift the marker at the two finger scallops and draw it back from under the lip. Do not
pull the marker out without pressing the tab.

## 8. Cradle hold-down: design and calculation

Rev D carries the cradle numbers in the YAML (`cradle` block): the model reads them and asserts its derived values
(overall height 22.63, PCB top -4.855, hook overlap 1.10). The geometry is unchanged from the reviewed rev C design.

Seven pins at 0.59 N push up with 4.13 N at y = -17 (four pins: 2.36 N); the marker weighs 0.12 N.

- **Fixed lip** at the front: 12 mm wide (|x| <= 6, between the window recesses, which start at |x| = 7.25), 1.6 mm thick,
  reaching 1.2 mm over the top front edge of the tub with 0.25 mm clearance. It stands on a tower in front of the visor;
  under it a nose pocket 1.0 mm deep lets the top front corner of the tilted marker swing in. Nearest window 1.55 mm,
  cover glass 3.22 mm, vent hole 22.9 mm away.
- **Sprung latch** at the rear: a rectangular cantilever 24 mm wide and 11.65 mm long (root at z = -3.8, 1.055 mm above
  the PCB pocket, R1.0 root fillets) standing in an open well. Its front face is vertical; its back face makes it
  1.05 mm thick at the root, 0.85 mm nominal at a neck 2.5 mm below the hook (0.89 mm on the solid, because the two
  tapers are blended with R8) and 1.30 mm where it runs into the hook. The hook is as wide as the beam and has a
  **straight nose** at y = -21.30, 0.25 mm above the tub top, and a **retaining face raked back 14 deg** (the nose is
  its lowest point), with a 30 deg lead-in above. The nose lies 1.10 mm on the flat top of the tub with the marker
  centred and 0.85 mm with the marker against the front nest wall. A thumb tab 14 mm wide and 7.9 mm long projects
  rearward from the top: pressing it down bends the beam back.
- **Two over-travel stops.** Two ribs on the guard wall, 1.30 mm behind the beam at z 5.5, stop a hook that is pushed
  or pulled back at 1.9 mm of travel. A rest under the end of the thumb tab (10 x 2 mm, top at z 6.57, 3.46 mm below
  the tab) stops a pressed tab at 2.0 mm of hook travel; any further thumb force goes into the rest, not into the beam.
  The ribs sit below the hook at the height where a pressed tab would reach them only at 2.11 mm, so they never block
  a release.
- The marker rests on its three ball feet on a front strip and two pads of the nest (z = -0.10); the D flat (front
  nest wall at y = 18.65) is the key, so it seats one way round only (check 7: at 90, 180 and 270 deg the solids collide).
- **Drained floor:** outside the strip and the pads the nest floor is 0.65 mm lower on the centre line and falls
  2 deg to both sides, out through the finger scallops. A rim round the pin slot and a dam in front of the latch well
  stay at the level of the strip; the well drains to the rear face through a tunnel beside the USB opening.

Numbers (check 7; method in `cad/holddown.py`; E = 1700 MPa, HP PA 12 data sheet, dry, 23 C; I(s) = b h(s)^3 / 12).
The beam is integrated numerically, curvature = M / (E I(s)). "Hook travel" is the backward travel of the beam axis at
the nose level.

| Quantity | How | Value |
|---|---|---|
| Hold-down reactions with seven pins | moments about lip (y 17.80) and hook contact (y -22.15) | hook 3.54 N, lip 0.47 N (four pins: 2.00 / 0.24 N) |
| Retention, no friction, marker centred | largest upward force on the hook before the nose leaves the flat top; moment about the deflected axis | 31.65 N at the hook = 36.34 N at the pin row = 8.8 x the seven-pin force |
| **Retention, governing position** (marker against the front wall, where the lead-in leaves it) | same, overlap 0.85 | 21.65 N = 24.85 N at the pin row = **6.0 x** (required 3 x); 3 x needs E of 848 MPa or more |
| Same with 0.2 / 0.3 mm less overlap (print tolerance) | overlap 0.65 / 0.55 | 15.19 N = 4.2 x / 12.36 N = **3.4 x**; 3 x at -0.3 mm needs E of 1485 MPa or more |
| Same at E = 1200 MPa (conditioned PA12, assumed) | | 4.2 x |
| Same with friction 0.2 | friction pulls the hook forward | above 30 x: self-locking in practice |
| Hook rotation at release | tip slope of the beam | 8.6 deg (11.3 deg centred) against the 14 deg rake |
| Root stress at 3 x the seven-pin force | 6 F e / (b h^2) + F / (b h) | 6.5 MPa, safety factor 7.4 to yield (48 MPa) |
| Hook travel needed | posed solids | insertion 1.42 mm; release 1.37 / 1.59 / 1.86 mm (marker forward / centred / rearmost) |
| Full deflection | the two stops, verified on the solids | 1.90 mm (stop ribs), 2.00 mm (tab rest) |
| **Strain at full deflection**, beam formula eps = M h / (2 E I) | tip force: largest at the root; tab moment: largest at the neck | 1.81 % / 1.78 % (limit 2.5 %) |
| Same, peak by plane-strain FE of the section | root fillet / neck | **2.05 % / 1.99 %** |
| Strain at insertion and at release | formula (FE peak) | 1.35 (1.53) % and 1.22 to 1.65 (1.36 to 1.85) % |
| Beam stiffness at the hook | tip force | 6.1 N/mm by the beam model, 7.0 to 7.5 N/mm by FE (plane strain) |
| Insertion force at the thumb | W = P (mu + tan 30 deg) / (1 - mu tan 30 deg), P = 8.7 N | 9.5 / 11.4 / 13.7 N for mu = 0.2 / 0.3 / 0.4; 8.0 N to finish seating against seven pins |
| Release force on the thumb tab | M0 = E b d / cw_M, lever 7.05 mm | 8.8 / 10.2 / 11.9 N; the tab lands on its rest at 12.9 N |
| Over-press of 40 N on the tab | excess goes into the rest | 27 N on the rest, 1.4 MPa; the beam stays at its full-deflection strain |
| Straight pull without pressing the tab | root yields when friction has locked the hook | 80 N at the hook, about 125 N of pull at the scallops |
| Lip | plate bending with the whole 3 x force on it | 4.5 MPa, safety factor 10.7 |
| Hook travel under the continuous seven-pin load | beam model | 0.18 mm elastic, 0.54 mm with a creep factor of 3, against 0.85 mm overlap |

Why the retaining face is raked: an upward force on the hook bends the beam back and turns the hook nose-up. A
90 deg face then becomes a ramp that cams the latch open. With the face raked more than the hook turns, the nose corner
bears on the flat top of the marker, the frictionless reaction stays vertical and the hook lets go only when the nose
has travelled the whole overlap. The figures above are frictionless lower bounds; with any friction above about 0.2
the hook is self-locking.

Insertion path (check 7, drawing GL1-020 sheet 2): the marker solids (tub, base plate, balls) were posed at 19 tilts from
17 deg to 0, resting on the front strip and as far forward as the front wall, the nose pocket and the lip tip allow. At
every pose the intersection with the cradle (latch removed) is zero, the free-length plungers (tip at z = 2.105) enter
the pad slot without touching base plate or adhesive sheet, and the latch needs at most 1.42 mm of travel. The pads
meet the plungers at about 1.9 deg; seated, the pins stand 5.82 mm high on the copper face of the pads (z 0.965) and are
compressed 1.14 of 2.29 mm. With pins fitted the marker is pushed up against lip and hook: it floats up to 0.25 mm above
its feet and the pins then stand 6.07 mm high (0.89 mm of stroke).

Finger access: the nest wall is removed over two sectors beside the marker (from -42 deg to 0 deg on each side, 16.5 mm of
the marker's side, full height); 42 of 42 test rays from each side reach the marker.

Printability: no wall of the cradle below 0.8 mm (latch root 1.05 mm, neck 0.85 mm; the hook nose is a solid wedge
ending in a 0.4 mm flat), no trapped powder (checks 5 and 6).

## 9. Sealing concept and what must be tested

The marker is bonded, with no O-ring. Check 13 proves on the solids that the modelled seals close the cavity: a box
minus all marker solids leaves the outside and the inner cavity (4218 mm3) as two separate bodies of air. Check 16
proves the same for the PA12 build. A bare contact is not counted as a seal: for this test each visor window is drawn
0.02 mm off the recess floor and off its shelf, so the cavity stays closed only if adhesive SOLIDS close all four
edges of each glass. The self-test removes the sill fillet of one window, then its top bead, then all the adhesive of
the other window, and each time the cavity opens to the outside and check 13 fails; it fails in the same way with a gap
in the cover-glass tape ring or in the perimeter bead. This shows that no modelled opening by-passes
a seal; it does not show that an adhesive wets, fills or lasts.

| Seal | Geometry | Concern |
|---|---|---|
| Cover glass | 0.13 mm transfer-tape ring dia 28 / 25 (1.5 mm wide) on the recess floor; the cell under it is vented into the cavity through the LCD frame; rim gap 0.25 x 1.13 sealed with a wicking-grade black sealant (about 25 mm3); the optional retarder film (dia 23.4) lies inside the bore of the ring, never under the tape, also with film, crystal and tape ring each 0.25 off (check 2) | a thin unsupported tape on vapor-smoothed PA12: primer, dwell; the 1.5 mm ring halves the lever on the roof ledge but also the bond area |
| Visor windows (2) | glass seated bare on the recess floor (seats 0.50 sides, 0.40 sill, 0.65 top) and on its shelf; sealed by a closed frame of thixotropic adhesive round its edge: two side-gap fills 0.25 x 0.40, a bead 0.10 high on the top edge, a fillet 0.12 x 0.12 on the shelf in front of the bottom edge (0.91 mm3 per window) | no adhesive line behind the glass (YAML `visor_window.bond`, N2); the frame bonds to the 0.40 mm edge of the glass and, at the sill, to 0.12 mm of its front face: a coupon test; adhesive must not reach the roof edge of the 4.0 x 2.2 opening; the 0.525 mm sill (D04) relies on the bonded window |
| Base perimeter | one closed ring: joint 0.40 mm high on a 0.4 mm land under the tub ledge, 0.65 mm under the visor wall, plus the fill of the 0.25 mm radial groove down to the rim: 49.8 mm3 nominal, dispense 70 (PA12 build: 0.33 mm, 45.6 mm3, dispense 65) | the joint height follows PCB, printed step and sheet (0.27 to 0.53 with the step at the required +-0.10, 0.18 to 0.62 at the bureau's +-0.2), not the plate; black, thixotropic adhesive dispensed into the tub by volume; no glue channel is possible (D06); the land is well under the 1.5 mm that the project's research note asks for; it must bond to PA12 on one side and to solder mask and a routed FR-4 edge on the other |
| PCB underside | the adhesive sheet (0.20 mm) closes the pad slot and the grain opening and bonds the plate; lands to the PCB edge 1.37 mm (pad slot), 1.30 and 1.06 mm (foot holes); fillet round the PCB edge as second barrier | the sheet is the only barrier at the pad slot; no via inside the pad slot or the grain opening (YAML via_keepouts) |
| Grain opening | clear potting from the PCB down to z 0.05 at most (target z 0.10, YAML `fill_surface_z`), bonded to the wall of the opening over 0.75 mm, round the baffle ring, LEDs and photodiode | optical clarity, fluorescence, bubbles, yellowing, adhesion to solder mask after thermal cycling; surface must stay inside the opening; its stiffness and shrinkage act on the board that carries the IMU (section 12) |
| Ball feet (3) | epoxy plug 0.80 mm long round each ball (annulus 0.05 mm), then the back-filled sheet hole | each potting is a seal and carries a foot; the half below the ball's equator must be free of voids |
| Vent | Gore VE80205 on a pad inside the roof, 1.0 mm hole with two drain grooves on the top face | water-entry pressure not confirmed; the hole is on the face that is stepped on |

The round PCB locating hole is closed by the foot of post B+ (0.39 mm3 of trapped air); the slot under post B- reaches
0.30 mm past the cut-back foot (slot end at x -13.25, inner face of the foot at -13.55; it was 0.10 with the 1.8 mm
slot) and is open to the cavity. Both are inside the sealed volume. The two pockets under the
ends of the visor wall (D14) are outside the seal ring; they hold about 1.7 mm3 of water each unless the outside
fillet fills them.

Tests required before any water claim (loads from `../docs/research/enclosure-manufacturing.md`, itself unverified):

1. Pressure-decay leak test of every tub (step 10) and of every unit with the vent occluded, **twice**: after the
   cure (step 18) and again after the temperature cycle (step 19), with the same chamber and limit, so that a seal
   opened by the cycle is found at the factory; the unit at the temperature of the chamber within 1 K each time (after
   the cycle: a soak of at least 60 minutes, provisional), because 1 K is about 340 Pa on the reading; sectioned
   samples to confirm that the perimeter joint and groove are filled.
2. 25 kPa inward (hot unit into cold water at 1 m) and 40 kPa outward for 24 h at 70 C (blocked vent, altitude plus
   heat) on sealed samples. With a blocked vent 40 kPa pushes the base out with about 55 N, carried by the perimeter
   joint alone (design-review estimate: about 0.4 N/mm of peel).
3. Dunk test including the hot-unit-into-cold-water case on the first units; vent water-entry pressure of at least
   50 kPa; a step on a wet unit followed by a leak test (does a sole pump water through the vent?).
4. Lap-shear and peel coupons of each adhesive on its real substrates (smoothed PA12, unsmoothed PA12, solder mask,
   routed FR-4 edge, glass), with and without primer, before and after thermal cycling (-10 to 70 C, 100 cycles), UV
   and sunscreen / fertiliser exposure; push-in and pull-out test of a potted ball (target 100 N); a window coupon:
   0.40 mm glass in a printed recess with the adhesive frame only, 25 kPa from inside and from outside.
5. Light-leak coupon: black MJF PA12 at 0.8 mm in direct sun; dark frames of assembled units, with and without the
   gaps beside the cubes masked.
6. Footstep: 800 N on a 20 mm indenter on the cover glass and on the roof, with the LCD powered, on turf and on a
   hard floor, at 23 and 60 C (open issues 3 to 5).
7. Fogging of the cover glass: hot-humid soak, then a cold plate on the glass.
8. Wet docking: 100 dockings of a marker wetted with 0.3 S/m solution, then inspection of the pads (open issue 8).
9. Thermal cycling of complete bonded units, -10 to 70 C, 100 cycles: then leak test, LCD position and display
   inspection, tilt offset before and after.
10. Swollen cell: a 2.4 mm dummy cell in a unit quenched at 25 kPa with the LCD powered (open issue 13).
11. Potted grain opening: mud and fertiliser soak, abrasion on sand, then photodiode signal, insulation and surface
    inspection; yellowing after UV.

## 10. Check report summary

Full tables: `export/check_report.md`. All eighteen checks pass on the build of 2026-11-13 with 25 warnings. A check
fails when a requirement is violated and the violation is not a recorded deviation; recorded deviations stay visible as
warnings. Checks 1 to 15 run on the primary build (FR-4 base plate); check 16 runs the base-specific checks on the
alternative build; check 17 is the board import; check 18 covers the fixtures that bear on the outer face (the two
calibration plates, the ball gauge plate and the footprint of the bridge gauge). The optional retarder
film and the fixtures are not part of the assembly of checks 1, 8 and 13; they have their own rows (checks 2 and 18).
After the drawings are written the build reads the five fabrication files, the DXF of the PCB outline (`GL1-040`),
the legend layers of the `GL1-011` DXF and the die cuts `GL1-034` and `GL1-035` back from disk and compares them with
the checked data (the legend in the Gerber and in the DXF must be the mirror image of the legend as read; the film
must carry its flat); a difference fails the build. So does a number in this README that the build no longer gives.

`python3 cad/build.py --selftest` seeds 62 defects and each is caught by its check, most of them for a stated
reason (the word the failure message must contain). New after the review of this issue (nine): a roof 0.01 mm low over
the camera L opening only; the legend layer written un-mirrored; legend text at the letter pitch of the last issue
(0.05 mm between letters); the PCB slot 0.05 mm off its centre line (caught by check 14 and by check 2); the round
locating hole 0.05 mm off; the dia 24.0 retarder film of the last issue (0.5 mm to the tape bore, less than its
centring chain); a ball gauge plate without bosses; one with dia 0.70 gauge holes. New with the amendment: a legend line moved to 0.6 mm from a mask
relief, and one 3 mm from a foot hole but inside its seat zone; a PCB slot 1.8 long; a retarder film 0.15 thick and
one of dia 25.6; an LCD pocket grown by 0.15 mm in length and 0.2 mm in width (the glass could turn 1.5 degrees; a
pocket grown in one direction only is held by the other pair of stops to 1.24 degrees and is rightly not a failure);
a calibration seat plate with pockets 0.08 deep; U10 back at its old position 0.19 mm from a foot zone; on the board:
an 0402 part 0.15 mm from a foot zone and a part 0.02 mm too tall under the LCD tail. As before: a prism raised
0.3 mm, an LCD shifted 0.2 mm, a raised battery, a visor window standing 0.2 mm proud, potting 0.05 mm proud of the
base plane, a baffle ring 0.5 mm off centre, a hood gasket bead 0.2 mm too far forward, a bar across a camera opening
(two checks), a roof 0.1 mm and a roof 0.01 mm low over an opening (the guaranteed case falls below 14.5 degrees: the
0.01 mm case costs 0.18 degrees against a margin of 0.11), a 0.3 mm roof pocket, a closed void, a cavity with a 1 mm
exit, a lip 0.4 mm too low, a hook cut back by 0.6 mm, a missing tab stop, a rib over the PCB outside the keep-outs, a
shortened post, a post standing on a ball-foot zone, U8 back over the front foot, the key notch of the first rev C
model, a window adhesive frame without its sill fillet, one without its top bead and a window with no adhesive at all
(each opens the cavity in the air test), a gap in the cover-glass tape ring, a seating ledge 0.3 mm too small, rear
glass ribs 0.6 mm short (no stop for the LCD), an FR-4 plate with a square notch and one with a hole 0.4 mm from its
edge, a PA12 plate with a foot hole too small and a gap in its seal bead, ten further defects of a circuit board
(below) and the toolchain's demonstration board. A board built from the amended YAML, a board with a tall part marked
not fitted (warning only), a missing board file and the unmodified model (nine checks) pass.

| # | Check | Result | Numbers |
|---|---|---|---|
| 1 | Interference, all 1128 pairs of 48 solids | pass | 188 pairs with overlapping boxes tested by boolean common (limit 0.01 mm3): no interference; 72 intended zero-volume contacts, each on the allow-list (a lost or an unlisted contact fails the check); no modelling overlap |
| 2 | Clearances | pass, 3 warnings | 106 key gaps and 12 PCB parts. Below the rule and recorded: the two spigot fits, 0.075 by specification (D19; measured on the PCB solid of the build and compared with that nominal), and the epoxy under a ball at the upper diameter limit of grade 100, 0.007 against 0.02 at the lower plate limit (D33). Retarder film (dia 23.4 with its flat): 0.98 to the display, 0.80 inside the bore of the tape ring, 0.03 above the roof ledge against 0.023 needed, 0.70 beyond the aperture (0.50 at the flat), no interference with any part; after its centring chain at the worst case 0.05 to the tape bore, 0.20 beyond the aperture, 0.00 at the flat; ring height by tape (E16 table: 0.85 / 0.82 / 0.805 on the 0.80 plate, crest z 0.00 to 0.13 in every case, window 0.00 to 0.15); ring print file 1.10 high, 0.15 above the tallest finished ring; potting volume against the YAML. Tolerance chains for both base plates, potting volumes and levels, thermal table |
| 3 | Field of view | pass, 4 warnings | field frusta from the prism exit face to 200 mm (chief rays and full pupil, both cameras) have zero intersection with tub, base, seal adhesive, window adhesive and the other camera's parts. Chief rays clear to 31.22 deg left and right, 21.89 up, 18.74 down (required 26 / 17.6 / 8). The full 0.38 mm pupil is clear to 25.60 deg horizontally (prism exit face), 18.56 up, 15.33 down |
| 4 | Fold ray trace | pass, 10 warnings | chief rays of all nine field points pass prism and opening. Pupil transmission 97.7 % at the horizontal field edges, 100 % elsewhere. Bundle margin to the opening: sides 0.377, sill 0.397, top 0.054 mm. Upper field 18.56 deg nominal, 14.97 with the optics 0.2 mm high, **14.61 deg in the guaranteed case of the YAML (optics high and the spigot play against it), traced on both cameras (camera L 14.61, camera R 14.61) and compared strictly on the smaller: 14.5 guaranteed, margin +0.11 deg at the nominal fit (N3)**; 0.18 deg per 0.01 mm of roof height. New table "what uses up the margin": 14.496 deg with the PCB hole 0.05 oversize, 14.43 with a pupil of dia 0.40, 14.26 with the roof 0.02 lower at -10 C, 14.03 with the largest fit and the cold roof (warning; proposal N18). Gate 2 target at +13.5 deg: 100 % clear in the guaranteed case in both cameras (a target at +17 deg: 67 %). Camera-position and sensitivity tables in section 5 |
| 5 | Wall thickness (tub, cradle, baffle ring) | pass, 1 warning | tub minimum 0.500 mm (feet of the hood skirts; D04 strip 0.525), cradle 0.391 mm (hook nose, an edge), baffle ring 0.800 mm. Ten recorded regions below 0.8 mm, none unrecorded |
| 6 | Trapped volume (tub, cradle, baffle ring) | pass | no closed void, no cavity without a 2 mm exit (voxel 0.1 / 0.2 / 0.041 mm); eight small open recesses listed in the tub |
| 7 | Cradle: pins, key, hold-down, insertion | pass, 4 warnings | seven pin positions on pad centres, 0.565 mm clear in the slots, 5.82 mm high; seats at 0 deg only; retention without friction 6.0 x in the governing position (21.65 N at the hook), 8.8 x centred, 3.4 x with 0.3 mm less overlap (required 3 x); strain at full deflection 1.81 % / 1.78 % by the beam formula, 2.05 % peak by FE (limit 2.5 %); both stops verified on the solids; insertion 1.42 mm, about 11 N; release 1.37 to 1.86 mm, 9 to 12 N; 19 posed tilts without interference; finger access 42 of 42 rays on each side; drained floor measured |
| 8 | Mass, centre of gravity | pass | marker 12.23 g, CoG (0.00, -1.28, 3.48), 8.2 mm inside the foot triangle; cradle assembly 31.2 g (densities stated in the report; balls taken as steel, 8.0 g/cm3) |
| 9 | Quoting data, export integrity | pass | boxes and volumes as in section 2 for the four print files (the baffle ring as its sprued set of six, each 1.10 high, 20.4 x 30.2 x 2.0, 0.247 cm3) and the fabricated FR-4 plate; print files rest on z = 0 with 0.005 mm facet sag or less; all 59 STEP files re-imported and all 59 STL files re-read: volumes match, meshes closed |
| 10 | Support posts and ball-foot zones | pass | eight posts solid from PCB top to roof, 0.45 mm or more from listed parts, 0.25 mm from the LCD glass; spigots under posts B, 28.7 apart; feet 1.6 x 1.6 and 1.9 x 2.2 (posts B, as the YAML now states); seat area 20.6 mm2 (post B+ 3.14, post B- over its 2.2 mm slot 2.15). No tub material and no soldered part other than the battery over the three dia 2.5 foot zones; **nearest part U11 at 0.312 mm against the 0.3 the YAML now requires** (U10 0.378), nearest post 2.15 mm |
| 11 | `design/check_layout.py` | pass | "OK: no layout errors" |
| 12 | Tub keep-out contract | pass | tub INTERSECT layout space (PCB outline x z 1.80 to 4.35, minus the eight post squares, minus the hood zones above z 2.75) = 0.000000 mm3; feet inside their YAML squares (posts B built 1.9 x 2.2 in a 2.2 square); the modelled LCD tail lies inside the YAML `lcd_tail` zone and 0.225 mm above a 0.7 mm part under it (N10); hoods span +-2.80 of +-2.85 from y 13.75, skirts 1.20 mm above the PCB (parts to 0.95 allowed); lowest tub feature elsewhere 2.55 mm above the PCB (the foot of the two rear glass ribs, exactly the free height) |
| 13 | Seal continuity | pass | air-solid test with each visor window drawn 0.02 mm off its seats: outside and cavity are separate bodies of air (cavity 4218 mm3 including the cell under the cover glass); potting, window adhesive frames, the test gaps behind and under the glass and the space in front of the windows probed; perimeter bead one closed ring, 0.40 mm high, narrowest 0.40 mm, 49.8 mm3 nominal, dispense 70; sheet lands 1.06 to 1.37 mm; window seats 0.50 / 0.40 / 0.65 and adhesive frames in one piece each; tape ring 1.50; one known closed pocket of 0.39 mm3 (round locating hole under post B+) |
| 14 | Assembly paths | pass, 2 warnings | LCD tilt-in: 14 poses, 0.28 mm to the ledge, 0.25 mm between the glass and each post B; the two rear ribs are proven to be the stop at the push-back height, the glass ends 0.15 mm behind nominal; PCB / base unit: straight descent at 10 heights with +-0.1 mm lateral error and hinged close at 14 angles, no interference. **Slot (N9): 2.20 x 1.15 at (-14.35, 10.8) and round hole dia 1.15 at (14.35, 10.8), measured on the PCB solid and compared with the YAML to 0.01 in length, width and both centre coordinates; travel +-0.60 against 0.378 to 0.478 needed, margin 0.122 to 0.222; a shorter slot, a slot or hole off its position or a negative margin fails.** **Display rotation (E12): the glass can turn 1.187 deg in its pocket (0.952 with continuous walls at the fit clearance), stopped by a rear rib, a hood rear wall, a side rib and a post B; limit 1.25; the pose is confirmed on the solids (0 mm3 at 1.17 deg). Bedded on the two rear ribs (x 8 to 11 on each side) the rotation is 0; 0.05 mm of step between the ribs is 0.15 deg; the squaring pusher (pad 5.0 wide, guided +-0.5) acts between the ribs and passes 0.4 mm clear between posts E.** Warnings: the lateral chain base edge to bore (0.17 to 0.28 RSS, up to 0.60 worst case against 0.25) and the free rotation against the 0.5 deg line budget |
| 15 | FR-4 base plate: fabrication rules | pass | 0.80 mm, constant section; one routed dia 13.0 opening, one routed slot, three drilled dia 1.10 holes; smallest internal radius 1.10 mm (rule 0.5), no sharp internal corner; smallest web 2.02 mm (slot to edge; rule 1.0, assumed); Gerber profile, mask layers and Excellon file generated from the solid, read back and equal to it. **Legend (E10): the layer `-B_Legend.gbr` is read back (55.30 mm2 of ink in 343 strokes, equal to the blocks within 0.0001 mm2) and proven MIRRORED, as a bottom layer must be (the file mirrored about x = 0 equals the legend as read; the first glyph of "GL-1" lies at larger x than the last); ink to the grain opening and to the pad slot 1.2 mm, to the three holes with their mask reliefs 3.97 to 3.98 (required 1.0), to the outline 1.57 (0.75), 0.342 outside the seat zones dia 8.5, 0.49 or more to the footprints of gauge-plate bosses, seat pads and bridge-gauge feet with their play (0.15); smallest clear space between two pieces of ink 0.15 (rule 0.15; 0.15 mm between letters at 1.0 mm text); six placeholder blocks present, text heights 1.0 to 2.2 (rule 1.0), line widths 0.15 to 0.25 (rule 0.15); the two statement blocks hold 88 characters at 1.0 mm; 940 of 1257 mm2 of the face stay open** |
| 16 | Alternative base plate (printed PA12) | pass, 1 warning | 294 pairs with a base-specific part, 69 tested: no interference; 18 base-specific clearances met (ball in its dia 1.15 hole 0.075, photodiode to the integral ring 0.594, LEDs 0.604; gap under the balls 0.02 or more with plates sorted to 0.83 to 0.92, 0.014 with an oversize grade 100 ball, D33); plate minimum wall 0.800 mm, no trapped powder; air-solid test passes; seal joint 0.33 mm, 45.6 mm3, dispense 65, one closed ring; marker 11.39 g |
| 17 | Board import | pass (skipped) | "skipped: no board file": `../electrical/gl1_main/out/gl1_main-mechanical.json` did not exist at build time (2026-11-13) |
| 18 | Fixtures on the outer face: calibration seat plates (E11), ball gauge plate, bridge gauge | pass | base-face seat plate: in both nests the FR-4 plate rests on three pads (contact 24.7 to 28.0 mm2 each), the balls hang 0.40 above the pocket floors and 1.18 from the pocket walls (0.575 left when the marker sits 0.6 off, the placement allowance), the pads end 0.75 inside the plate outline; the legend-free zones of check 15 (dia 8.5) cover the pads (dia 7.0) with that allowance and 0.15 to spare; the visor flat bears on the fence over 27.6 mm above its undercut, the round wall touches the stop pin, the tub rim is 0.55 above the relieved face; ball seat plate: the three balls stand on the plain face, the base 0.10 above it; no interference in either nest. **Ball gauge plate (step 2): the base plate rests on three bosses dia 7.0 and on nothing else (35.0 mm2 each); every piece of legend ink is 0.27 clear of the relieved plate face and 0.99 from a boss after the location on the balls; the three gauge holes measured on the solid are dia 0.60 and set 0.100 of protrusion. Bridge gauge: annular feet dia 6.0 / 1.6, 1.06 from the legend with their play, bore 0.175 clear of the mask relief; its four rim stations lie on the rim flat of the tub solid (z 0.250); feet 1.86 clear of the potting mask** |

### Check 17: the board import

`cad/board_import.py` reads the file the board toolchain writes (`electrical/tools/gleda/outputs.py`, `mechanical_data`):
board thickness, exact outline contours and polygon, NPTH holes, slots, keep-outs, and every placed component with
reference, side, position, rotation, body corners and height. When the file exists the check verifies:

- A. thickness, outline (largest deviation from the YAML D shape; the polygon tolerance the file states for itself is
  capped at 0.05 mm), the outer contour (it must be exactly one arc and one line: the D), the round hole and the slot
  equal the YAML, and there is no other hole or cut-out, including one that appears only as a hole of the outline
  polygon or as an inner contour;
- B. every component is on side "top" or "bottom" (anything else fails); every top-side part: body (a prism on its
  corner points) at least 0.2 mm from the tub solid, 0.2 mm from the post-foot keep-out squares, not taller than
  0.95 mm inside a hood zone (camera exempt), not taller than the free height 2.55 mm (cameras exempt), **at least
  0.3 mm from every ball-foot zone (YAML `part_margin`, N7; the battery exempt)**, inside the board keep-in, not inside
  the battery body, not on a battery-lead pad, **not taller than 0.7 mm inside the LCD-tail zone (YAML
  `tub_keepouts.lcd_tail`, N10; J1 exempt)** and at least 0.2 mm from the modelled LCD flex tail (the tail shape is
  provisional); battery-lead pads inside
  `battery.pads.zone` and checked as joints 2.4 mm tall. Parts marked DNP are tested like fitted parts and what they
  would violate is reported as a warning;
- C. the fixed interfaces: both cameras and J1 at their YAML positions, the battery keep-out equal to the YAML body;
- D. every bottom-side part inside the grain opening or the pad slot; in the grain opening also 0.2 mm from the baffle
  ring and the wall, and under at least 0.30 mm of potting;
- E. the seven contact pads within 0.05 mm of the YAML pad row and of the modelled cradle pin axes;
- F. (warnings only) the bottom-side keep-outs of the three foot zones and the two via keep-outs are present in the file.

Proof (self-test): a board file built from the amended rev D YAML passes (slot 2.2 long, U10 at its new position, U9
1.6 x 0.9 x 0.5). Each of these is caught, and for the seeded reason: a
1.5 mm part under hood R, an 0402 on post foot A+, an 0402 over the front foot zone, a locating hole moved 0.3 mm, a
pad row shifted 0.4 mm, a bottom-side part outside the openings, a rectangular outline with the bounds of the D that
states a tolerance of 10 mm for itself, a part whose side is "front", an opening listed only in the polygon holes, a
2.5 mm part in the path of the LCD tail behind J1, an 0402 capacitor 0.15 mm from foot zone 3 (N7) and a part 0.72 mm
tall inside the LCD-tail zone (N10). A 2.5 mm part under a hood that is marked not fitted passes with a
warning. The demonstration board of the toolchain (`electrical/tools/demo/demo_out/greenline_demo-mechanical.json`, rev
C positions) fails as it should: hole and slot still under posts E, U8 over the front ball foot, one battery pad
outside the pad zone; it also has no bottom-side keep-outs. The requirement N8 (what the board file must contain) is
for the board package; this check is its acceptance test. To run the check on any file:
`python3 cad/board_import.py path/to/board-mechanical.json` (exit status 1 when the board fails). The check has never
run on a real board: only on the synthetic board, its seeded variants and the demonstration board. At the build of
2026-11-13 the folder `../electrical/gl1_main/out/` did not exist, so check 17 reports "skipped: no board file".

## 11. Deviations from the specification

Full text with numbers: `export/check_report.md` (end) and `cad/deviations.py`.

Standing deviations: D04, D06, D09, D11, D14, D18, D19, D33, D34, D35 (seven of them unchanged; D34 and D35 revised
after the review of drawings rev D-EVT1.1; nothing new, nothing closed since the first issue on the amended YAML).

| ID | Status | Requirement | What is modelled | Why |
|---|---|---|---|---|
| D04 | accepted (rev C) | every wall 0.8 mm | 0.525 mm behind each window recess in front of the cube, 4.0 x 0.4 mm | 1.325 mm available for recess 0.55 + wall 0.8 + clearance 0.25; the bonded window backs it |
| D06 | recorded | glue channel if possible | none | any relief in the 0.65 mm ledge or the 0.8 mm visor wall goes below the wall minimum; the radial groove is the reservoir |
| D09 | recorded | nose groove from the aperture edge | from the cover-glass recess edge | the aperture edge is under the glass |
| D11 | accepted (rev C) | LCD drops in from below | tilted in: rear edge first at 6 deg, shifted 0.55 forward, 0.28 mm to the ledge, then pushed back against the two rear glass ribs, which reach down to z 4.35 (step 9, check 14) | rear glass corners are outside the ledge radius |
| D14 | recorded | top radius and bottom chamfer all round; lower cavity clipped at the visor face | radius and chamfer on the arc only; wall ends cut on a radial plane; a 2 mm pocket under each end of the visor wall, outside the seal ring | a rounded visor edge would cut into the window recesses; the clipped cavity would leave feather edges |
| D18 | recorded | four 3 mm feet pockets | pockets dia 8.4 x 1.0 for dia 8 x 3 bumpers with a blind core dia 5 behind each; PCB held by four screws | "3 mm feet" read as 3 mm high; the corners would be 13 mm solid |
| D19 | accepted (rev D) | 0.25 mm on every drop-in fit | spigot fit 0.075 mm radial, as the YAML specifies, now under posts B | a locating fit below the print tolerance: gauged at first article (go gauge dia 1.10) |
| D33 | recorded (new) | plates accepted from 0.76 mm (PA12 from 0.83): 0.02 mm of epoxy between each ball and its land (YAML `thickness_accepted`, N6); balls of grade 100 or better (E8) | with a ball at the upper diameter limit of grade 100 (+0.0127 mm, as remembered from the ball standard: to be confirmed on the supplier's certificate) the gap at the lower plate limit is 0.007 mm (PA12 0.014); check 2 carries the row | the plate limits were fixed for grade 25 balls (+-0.0025); E8 widened the grade. Incoming rule (step 1): measure the ball lot, raise the lower plate limit by the oversize. Proposal N11 |
| D34 | recorded (new; extended after the review) | E11: turf-seat zero on a plate with three clearance pockets so that "the base face seats"; E10: legend 1.0 mm from the foot holes; balls set on a gauge plate | no fixture bears on printed legend: the base face seats on three annular pads dia 7.0 round the pockets (contact 24.7 to 28.0 mm2 each, plate relieved 0.3 elsewhere), not on the whole face; the ball gauge plate carries the base plate on three bosses dia 7.0 round its gauge holes (relieved 0.30); every depth reading on the underside is taken with a bridge gauge on three annular feet dia 6.0 / 1.6 round the balls; the legend keeps out of dia 8.5 round each foot hole (3.7 mm from the hole edge instead of 1.0) and 0.15 or more from each footprint | printed legend stands about 0.02 mm proud of the mask (0.03 at most) and the rim is only 0.25 above the base plane: on a full-face seat the marker would rest on ink, on a bowed plate or on the rim (0.02 mm across the foot triangle is 0.8 mrad); on a flat gauge plate the ink would add itself to the protrusion (0.10 +-0.02) and take the same from the 0.02 mm of epoxy between ball and land; a depth gauge on legend 1.2 mm from the grain opening would read 0.03 deep against a never-below limit of 0.05. A laser-marked legend would not need this. Proposal N12 |
| D35 | recorded (new; film changed after the review) | E9: quarter-wave film of about 0.1 mm on the underside of the cover glass, axis 45 deg to the LCD polariser; "1.08 mm of air, so nothing else moves" | film dia 23.4 x 0.10 with a clocking flat 4.3 long toward the visor, inside the bore of the tape ring (dia 25.0): 0.80 to the bore, 0.05 left after the centring chain at its worst case; 0.03 mm above the roof ledge at nominal; a film thicker than 0.11 mm with its adhesive must be cut to dia 21.5 and hang inside the aperture | the 1.08 mm of air exists only inside the aperture dia 22; outside it the glass lies 0.13 mm (the tape) above the roof ledge, and the film must not carry the glass off its tape; crystal and recess are round, so the flat (edge mark on the crystal, set to the nose groove) carries the film axis to the tub. Proposal N13 |

Closed by the amendment of revision D (the YAML now says what the model does, and `cad/params.py` asserts it): **D29**
feet of posts B 1.9 x 2.2 (N1); **D30** visor window seated bare with an adhesive frame, `bond_line` 0 (N2); **D31**
guaranteed upper field, now 14.5 degrees including the spigot play, compared strictly: 14.61, margin 0.11 (N3);
**D32** potting level never nearer than z 0.05, target 0.10, and the ring height rule (N4, E16).

Closed by revision D (the YAML or the spec now says what the model does): D03 baffle ring 6.6 / 8.2, D05 straight
openings, D07 no key between base and tub, D13 pre-cured hood gasket, D20 cradle body and height, D21 float, D22 free
height, D23 rim relief, D24 vent pad and grooves, D25 drained nest, D26 vented LCD frame, D27 ball back-fill on a copper
land, D28 pad plane. Closed by revision C: D01, D02, D08, D10, D12, D15, D16, D17.

Mechanical-only choices that are not in the YAML: baffle rings printed as a sprued set 1.10 high (lapped to 0.735 to
0.95; N15); black tape of the annulus modelled 0.13 thick; battery pads centred in x in their zone with a 0.7 mm gap;
hood gasket bead 0.5 x 0.33 centred 0.35 in front of the rear face of the hood rear wall; rear glass ribs down to
z 4.35; tabs of the FR-4 plate on the flat only and the web rule 1.0; carrier liner 64 x 50 with two dia 3.0 tooling
holes for the sheet die cuts; the tolerances of the chains in section 5; corner fill between hood and side wall from
y = 16.79; pin barrel top assumed 0.285 mm below the nest strip; LCD tail modelled with a 1 mm fold radius entering J1
at 1.0 mm above the PCB. New in this pass: everything about the legend except its 1.0 mm keep-clear (block positions
and sizes, strokes 0.15 to 0.25, text heights 1.0 to 2.2, letter spacing 0.15 or the line width, edge margin 0.75, seat
zones dia 8.5, registration 0.15, print thickness 0.03 at most; N12, N19); the ball gauge plate (bosses dia 7.0, relief
0.30, holes dia 0.60 x 0.5, blank 52 x 50 x 10) and the bridge gauge (feet dia 6.0 / 1.6, rim stations at r 22.35,
potting mask dia 15 / 24); retarder film dia 23.4 with a flat 0.5 outside the aperture radius, placed within 0.25 and
clocked within 3 degrees, and its thickness limit 0.11 (N13); the rows of check 4 that show what uses up the margin (PCB
hole +0.05, pupil 0.40 or 0.5 deep, roof 0.02 lower at -10 C, spigot 0.05 undersize; N18); calibration plates (70 x 112 x 12, fence 8 x 60 x 4, pin dia 3, pads dia 7.0,
pockets dia 3.0 x 0.5, relief 0.3, coplanarity 0.001); the limit 1.25 degrees for the free rotation of the glass and
the squaring pusher (pad 5 mm wide, guided to +-0.5); the gate 2 margin of 1.0 degree; the ball diameter tolerance
taken for grade 100 (0.0127).

## 12. Open issues, release gates and test items

Numbers marked "review estimate" are plate, strip, capillary or ideal-gas estimates from the design reviews (rev C and
rev D); they were checked for plausibility but are not computed by this package and none is tested.

### Release gates (data or decisions needed before parts are ordered)

- **Adhesive selection**, none is chosen. Each needs a part number and its data sheet:
  - perimeter seal: opaque black, thixotropic, sustained peel at 70 C on primed PA12 and on solder mask; **cures at
    room temperature or at 45 C at most** (the cell is in the unit; trade figure for Li-polymer cells, to be
    confirmed against the cell data sheet);
  - ball potting: stage 1 dual-cure or two-part; **stage 2 a two-part room-temperature system** (it lies between two
    opaque boards);
  - hood gasket: black, soft (about Shore A 40), silicone-free, form-in-place, holds a 0.5 x 0.33 bead without slumping flat;
  - window adhesive: light-cure, **thixotropic** (it must not wick behind the glass), bonds glass to PA12;
  - cover-glass rim seal: black, wicking grade; LCD frame tape; black tape for the baffle annulus;
  - clear potting: low fluorescence, non-yellowing, mixed viscosity about 0.1 to 2 Pa.s (review estimate: at 1 Pa.s
    it levels in about 1.5 minutes and a 0.05 mm bubble rises 0.95 mm in about 10 minutes; at 5 Pa.s in 53), pot
    life for degassing, cure at 60 C at most, and **low cure shrinkage and a chosen modulus**: a hard potting
    resists abrasion but loads the board that carries the IMU (open issue 15); state both on the selection sheet.
- **OVM7692 lens data** (entrance-pupil position and diameter): the field-of-view numbers and the 2.3 % clipping at the
  prism rest on assumed values.
- **LCD tail geometry (B16)**: tail length, exit position, pin-1 side and the actuator side of J1 from the Sharp
  outline drawing. The drawing must give at least: **a free tail of 10 mm plus the insertion depth of J1** (the join
  fixture mates the tail with the unit open 35 degrees: check 14 gives 6.5 mm at 20 deg, 10.0 mm at 35 deg, 15.3 mm at
  60 deg, while the closed U-fold needs only 3.8 mm), a permitted bend radius of 1 mm or less starting within 0.35 mm
  of the glass edge, and where the surplus loop of 6 mm or more may lie when the unit is closed (the pocket behind
  the glass, between the rear ribs and the side wall, is 5 mm deep and 4 mm high above the J1 mouth).
- **Battery (B15)**: maximum delivered thickness and end-of-life swelling from the PowerStream drawing; protection-board
  length (it decides where the leads leave the cell); maximum storage and process temperature.
- **FR-4 plate**: build-up for 0.80 mm over the mask, thickness tolerance and web rule to be confirmed by the
  fabricator; first-article thickness. **Legend text**: the five blocks on GL1-011 are placeholders; maker's name and
  address, the regulatory statements and the serial format come from `docs/COMPLIANCE.md` and must fit the blocks (the
  two statement blocks hold 88 characters of 1.0 mm text between them, with 0.15 mm between letters; more text goes to
  the packaging and the manual, or the blocks are re-laid and check 15 run again). The fabricator's legend rules (line
  0.15, text 1.0, space 0.15, registration 0.15, ink height 0.02 to 0.03) are assumptions until the quote; the ink
  height decides whether the seat zones and the bosses, pads and feet that use them are needed (D34): a laser-marked
  legend would make them unnecessary.
- **Ball feet**: a supplier's certificate for dia 1.000 balls in 316 stainless, grade 100 or better, or in silicon
  nitride, with the diameter tolerance of the lot (D33); never 440C.
- **Tub first articles**: seal face 0.60 and rim 1.55 from the post feet within +-0.1; spigots; bore; dummy unit.
- **Proposals N11 to N19** in `PROPOSED_PARAM_CHANGES.md` (ball diameter against the lower plate limit; legend seat
  zones, fixtures on bare mask and the wording of E11; retarder film diameter, flat and thickness limit; U11 0.2 mm
  inboard; ring height text and print height; the rotation figure of E12; fixing-adhesive thickness of the cell; the
  guaranteed upper field against the tolerance of the spigot fit; legend print rules). N1 to N10 are decided and built.
- **Fixtures not designed**: the six-face calibration fixture (section 2 lists what its dimensions must come from),
  the display-rotation measurement, the LCD squaring pusher as a detail of the tilt-in fixture, the bridge gauge
  (stated as a requirement with its footprint, stations and tolerances; its footprint is checked), the film
  lamination nest, a location for a four-position zero. Drawn: the two calibration seat plates and the ball gauge
  plate (GL1-050). **Firmware**: the level zero on the seat plates is taken without
  anything on the pads, so the firmware must start and store it without a wired contact (the marker has no radio:
  from its own menu, or armed through the pogo fixture and run after the marker has come to rest on the seat plate):
  a requirement on the firmware and on `docs/MANUFACTURING_PLAN.md` section 6.
- **Hard-gold contact pads** for production (ENIG at EVT).

### Decided in revision D and not adopted (recorded with the reason given)

- **B20**, pad row 0.5 mm inboard or a 1.8 mm slot: not adopted; the pad row stays at y -17.0 and the slot 2.2 wide
  (system owner's decision; the sheet land to the PCB edge stays 1.37 mm with the fillet round the PCB edge behind it).
- **0.2 mm thicker puck**: not adopted; it is the reserved remedy if the step tests fail at EVT.
- **VBUS gating in the cradle**: not adopted; the cradle board gets a resettable fuse instead.
- **B13, stainless base plate**: not adopted; the plate is FR-4 (same expansion as the PCB it is laminated to, flat,
  drilled holes to 0.05 mm, from the PCB fabricator), with the printed PA12 plate as the alternative.

### Test items for EVT (targets set by the system owner where stated)

1. **Thermal and humidity tilt drift of the PCB / base laminate, to be MEASURED for both base-plate variants.**
   Acceptance (system owner): under 0.05 mrad per kelvin after per-unit compensation, and repeatable within 0.3 mrad
   after a -10 to 50 C cycle. Build both variants, **each with the grain opening potted and left unpotted**: the clear
   potting is a 13 mm disc of epoxy bonded to the board that carries the IMU, both variants carry it, and without the
   unpotted units the comparison cannot separate plate from potting. Measure the tilt reading against a reference on
   a temperature-controlled flat, dry and after humid conditioning, and **again some weeks after cure** (cure
   shrinkage relaxes with time). Nothing in this package predicts the result (review estimates: 0.04 to 0.3 mrad/K
   for the PA12 plate; for the potting alone 0.03 to 0.08 mrad/K at the IMU with a 2.5 GPa epoxy, half that at
   0.5 GPa, and 1.5 to 8.6 mrad of built-in tilt from 0.2 to 0.5 % of cure shrinkage).
2. **Footstep tests and the step-proof claim**: 800 N on a 20 mm indenter on the cover glass and on the roof, on turf
   and on a hard floor, at 23 and 60 C, LCD powered. The EVT mineral crystal is declared not step-proof. If the tests
   fail with the production glass, 0.2 mm more puck thickness above the LCD is the reserved remedy (not adopted now).
3. **Cradle latch**: 3000 insert / release cycles at 23 C and 0 C, 1000 h at 50 C with seven pins (creep), pull test
   of 12.4 N at the pin row; hook position before and after.
4. **Light leaks**: dark frames under strong side light; translucency of 0.8 mm black PA12, of the baffle ring and of
   its black annulus; the hood gasket (a squeezed land of 0.17 mm and a curtain behind the cube).
5. **Seal and adhesives**: section 9, tests 1 to 4 and 9, including the window coupon.
6. **Potted grain opening**: section 9, test 11; optical function through the potting; level and meniscus on first
   articles (does a fill by volume hold the 0.10 mm window; does the meniscus pin at the edge of the opening).
7. **Ball feet**: push-in and pull-out strength of a potted ball on its copper land (target 100 N); protrusion after
   thermal cycling; sections of stage 1 to look for the void under the ball's equator.
8. **Assembly trials before the first sealed unit**: LCD tilt-in against the rear ribs; hood gasket bead from the
   needle guide (shape after cure); mating of the LCD tail with the unit open, on a mock-up; dry trial close.

### Open mechanical issues

1. **The upper edge of the camera field has no tolerance margin (accepted in rev D).** The +17.6 deg field edge clears
   the roof underside by 0.054 mm. Optics 0.2 mm high: 14.97 deg; with the spigot play added (the guaranteed case of
   the amended YAML): 14.61 deg against 14.5 on both cameras, a margin of 0.11 deg, which is 0.006 mm of roof height
   (0.18 deg per 0.01 mm) or 0.024 mm of fore-aft play. **The margin belongs to the nominal fit and the assumed pupil
   only**: a locating hole 0.05 over on diameter gives 14.496 deg, a pupil of dia 0.40 gives 14.43, a pupil 0.5 below
   the cube top 14.16, the roof 0.02 mm lower at -10 C 14.26 (section 5, check 4). The YAML defines the guarantee on
   the nominal fit, so the check passes; a real lot is not covered. Proposal N18. Any change to roof, opening, prism
   height or spigot fit must be followed by check 4.
2. **Spigot fit (D19).** 0.075 mm radial on printed dia 1.0 spigots is tighter than the print tolerance. Gauge and dress
   at first article; measure the achieved camera position through the windows. Along the slot the spigot now has
   +-0.60 (slot 2.2 long, N9, measured on the PCB solid and on the written DXF); spacing error, hole position and
   thermal movement sum to 0.38 to 0.48, which leaves 0.12 to 0.22.
3. **Footstep on the cover glass (review estimate).** 800 N on a 20 mm patch: about 400 MPa in a 1.0 mm crystal simply
   supported on its tape (the EVT crystal breaks at roughly 100 to 200 N); the roof ledge under the tape hands load to
   the LCD glass bonded under it; the posts take the rest: 800 N on their 20.6 mm2 of feet is 39 MPa (PA12 yields near
   48 MPa). Needs a test and a 3-D FE run.
4. **Footstep on turf (review estimate for the PA12 plate).** Inside the ring of posts the PCB / base laminate spans
   30 mm with only the battery, 0.55 mm of air, the foam and the LCD above it; with the PA12 plate it was estimated to
   close that gap at 250 to 500 N. The FR-4 plate makes the laminate about as stiff as a 1.8 mm board (spec) only if
   the 0.20 mm adhesive sheet transfers shear, which a pressure-sensitive adhesive does poorly at slow rates (review
   estimate); the number is not computed here.
5. **Hard floor.** With the rim relief a step on a hard floor is carried by the three balls and then by the base plate
   through PCB and posts. Each ball bears on its copper land through epoxy; the front foot zone is now free of parts,
   the rear zones lie under the battery by decision. A hard-floor step requires re-zeroing in any case. With a tub at
   the bureau's general tolerance the rim could touch before the balls (section 5): the rim height is a required
   dimension.
6. **Posts B.** Their feet are 1.9 x 2.2 (YAML, N1); post B+ seats on 3.14 mm2 round its hole, post B- on 2.15 mm2
   beside its slot, which is 0.4 mm longer than before (N9): the smallest seat of the eight.
7. **The cradle latch is calculated, not tested** (section 8): retention depends on the modulus (3 x in the governing
   position down to 848 MPa, at -0.3 mm overlap only down to 1485 MPa), on the pin force (provisional) and on the
   distance front nest wall to hook nose (39.95 mm). Strain at full deflection 2.05 % by FE against 2.5 %; 0.2 mm on
   the rib gap is about 0.3 mm of hook travel. Small-deflection beam theory is used up to 20 deg of rotation.
8. **Wet docking.** The cradle drains, but the marker's pad slot (37 mm3) holds water by
   capillarity across 5 V contacts (review estimate: 0.1 to 0.6 mA through the film). VBUS gating was not adopted: the
   cradle board gets a resettable fuse instead. The grain opening no longer holds water. Dry the marker before docking.
9. **LCD flex tail and J1**: release gate above. The mouth of J1 must face the rear because the battery is 0.8 mm in
   front of it. Mating with the unit open needs a tail several millimetres longer than the closed fold (10 mm free at
   35 degrees against 3.8 mm), J1 faces down into the upturned tub while its actuator is closed, and the surplus has
   to stow behind the glass: not demonstrated; to be tried on a mock-up before any seal adhesive is involved. The
   YAML now has a keep-out for the tail (`tub_keepouts.lcd_tail`, N10: parts under it at most 0.7 mm tall); check 12
   finds the modelled tail 0.225 mm above such a part, and the board import applies the rule to every placed part.
   The tail shape itself stays provisional.
10. **Seal** not tested and adhesive not chosen: 0.4 mm land, joint height 0.27 to 0.53 mm (0.18 to 0.62 with a tub at
    the bureau's general tolerance), bonding PA12 to solder mask, sustained peel when the vent is blocked (section 9).
    The fill is proven only as geometry (check 13).
11. **Glass near flush.** Windows 0.15 below the visor face and the tub top, cover glass 0.12 below flush: the stack
    of recess depth, tape and glass is +-0.15 mm RSS, so some crystals will still be at or above flush. The window
    adhesive frame is designed 0.03 behind the visor face and 0.05 below the tub top: both must be checked with a
    straightedge.
12. **Visor window bond (YAML `visor_window.bond`, N2)**: no adhesive line behind the glass; the seal is the frame
    round its edge, bonded to 0.40 mm of glass edge and, at the sill, to 0.12 mm of the front face. Whether it seals
    and holds is a coupon test. Adhesive at the roof edge of the opening costs upper field (0.18 degrees per
    0.01 mm): thixotropic adhesive, no wicking. Test gate 2 (bars at +-13.5 degrees) finds 0.06 mm of it on a unit at
    the tolerance limit and 0.28 mm on a nominal unit, not less: a thinner film at the roof edge passes the gate and
    is only seen in validation test O1 or by inspection of the opening at 10x before the join.
13. **Battery**: the last 0.15 mm above a fully swollen cell is also claimed by the fixing adhesive (0.05), PCB
    deflection and thermal bow; delivered thickness is a release gate. Lead pads are nominal until the board is laid out.
14. **Ball potting.** The epoxy below the ball's equator is shadowed and is fed only through the 0.05 mm annulus,
    with the gauge rim sealing the bottom: air can be trapped there (0.13 of the 0.27 mm3 lies below the equator).
    Fed from one side and inspected from below after demoulding (step 2); dispensing 0.27 mm3 repeatably is unproven.
    Stage 2 is dispensed at 85 % so that it cannot flood the sheet.
15. **Clear potting**: product not selected. A fill by volume has to hold a window of 0.10 mm (93.4 mm3 +-3 % is
    +-0.03 mm; 0.08 mm of plate thickness is another 0.08 mm, hence the per-unit correction and the wet level check);
    the meniscus (review estimate: a wetting liquid would climb 1.9 mm on a free wall) must pin at the edge of the
    opening; bubbles, cure shrinkage (a sink over 13 mm), adhesion and abrasion are untested; the baffle ring must
    not be floated off its annulus. **The potting is a bimetal disc on the board that carries the IMU** (test item 1):
    its effect on the tilt reading is not computed.
16. **Light leaks**: the hood gasket closes the slit above the cube with a 0.17 mm land and a curtain behind the
    cube; its bead must be placed within -0.10 / +0.08 mm and its cured shape (0.5 x 0.33) is an assumption. The
    0.265 mm gaps beside each cube and 0.25 mm in front of it stay open (a labyrinth, not a seal). Translucency of
    0.8 mm black PA12 is untested.
17. **Vent**: part data unverified; the printed dia 1.0 hole may need drilling; whether the grooves keep a sole from
    pumping the membrane is untested.
18. **Prism slightly undersized for the assumed pupil**: 2.3 % of the pupil is clipped at the horizontal field edge.
19. **Thin wall behind the window recess (D04, accepted)**, 0.525 mm over 1.6 mm2 per camera.
20. **Passives and the real board**: the YAML lists 13 top-side parts; everything else is checked only when the board
    file exists (check 17, never yet run on a real board). The amended YAML asks for 0.3 mm between any part and a
    foot zone (N7): U10, moved by the YAML, has 0.378; **U11 has 0.312**, a margin of 0.012 mm (N14 proposes 0.2 mm
    more).
21. **Vapor smoothing of 0.8 mm walls**: bureau confirmation and coupons.
22. **Cradle details**: pin diameters, barrel length and stroke are provisional (the barrel top is assumed at z -0.385);
    the thumb tab and its rest are directly above the USB plug; no cable strain relief.
23. **Purchased-part envelopes** are simple solids; every PROVISIONAL item in section 2 must be checked against a
    manufacturer drawing before parts are ordered.
24. **No key between base plate and tub: the dry trial close (step 14) is the control.** The plate edge reaches the
    bore through a lateral chain of 0.17 to 0.28 mm RSS and 0.35 to 0.60 mm worst case against a 0.25 mm gap (check
    14). The plate top passes the rim 0.55 mm before the seat, after the spigots have engaged at 0.60 mm, so an
    offset plate would fight two dia 1.0 PA12 spigots with the bead wet. Units and tubs are paired dry.
25. **Baffle ring**: its height is lapped to the plate lot and the tape (plate thickness + 0.15 - tape thickness,
    E16: 0.735 to 0.95 over the accepted plates and tapes of 0.10 to 0.145); if the lots vary more than expected, or
    lapping a 0.015 g ring proves impractical, the alternative is a ring 0.07 mm lower that is always covered (with
    the optical penalty of a clear bridge). The gate stub must be trimmed flush (0.60 mm to the LEDs).
26. **Tub dimensions required tighter than the bureau quotes**: seal face and rim from the post feet at +-0.1. If
    first articles do not hold them, the seal volume (70 mm3 covers the bureau's +-0.2) still fills the joint, but
    the rim relief does not survive the worst case; the remedy would be a larger rim relief (a YAML number).
27. **Legend against every reference on the outer face (D34, N12).** The legend is ink on the face the marker rests
    on in the turf seat, and on the face that the ball gauge plate, the calibration seat plate and every depth
    reading take as their reference. It is kept out of dia 8.5 round each foot hole, and the gauge-plate bosses, the
    seat pads and the feet of the bridge gauge bear only there; the press plates that touch the rest of the face have
    a compliant facing. The ink height (0.02 mm assumed, 0.03 allowed), its wear on sand, whether a PCB fabricator
    registers a legend to 0.15 mm on a 43 mm part and holds 0.15 mm between letters of 1.0 mm text are not known. The
    bridge gauge is a requirement, not a design. The placeholder blocks leave 940 of 1257 mm2 of the face
    unprinted. On turf itself the marker lies on ink and mask alike: 0.02 mm of print is far below the seating
    scatter of 2 to 5 mrad the specification expects.
28. **Ball grade against plate limit (D33, N11).** With a grade 100 ball at its upper diameter limit the epoxy under
    the ball is 0.007 mm at the lower plate limit, not 0.02. The limit itself (0.02) is a judgement, not a measured
    need; the diameter tolerance used is from memory of the ball standard and must be read from the certificate.
29. **Retarder film (D35, N13)**, optional: laminated to the glass before the tape ring, inside its bore. The film's
    thickness with adhesive, the direction of the LCD polariser (and so the angle at which the converter cuts the
    clocking flat to the film axis) and bubbles under the film are open. The film is dia 23.4 so that the centring
    chain (0.25 each for film, crystal and tape ring) still leaves 0.05 mm to the tape bore at its worst case; its
    flat can then just reach the aperture edge (0.00), which would show as a short straight line at the visor side of
    the aperture. Clocking by an edge mark set to the nose groove is good to about 3 degrees; whether that is enough
    for the purpose is part of the trial. The lamination nest is a requirement, not a design.
30. **Display rotation (E12).** Left to itself the glass can turn 1.19 degrees in its pocket (check 14). The squaring
    pusher of step 9 is a requirement, not a design; with it the residual is set by the step between the two rear
    ribs (0.15 degrees per 0.05 mm over their 19 mm spacing) and by the squareness of the pocket to the visor flat.
    Whether a printed rib pair is flat to 0.05 mm, and whether the glass stays bedded while the rear strip tacks, is
    a first-article question; the factory measurement and the stored correction (E12) are the safety net.
31. **Calibration seat plates and ball gauge plate (GL1-050)**: designed and checked as solids only. The reversal
    method cancels the tilt of the surface plate but not dirt under a foot or a pad; the 0.001 mm coplanarity of
    three pads over 30 mm asks for a lapped part and a measurement report; whether the fence and pin locate the
    marker repeatably enough (0.6 mm of placement is allowed by the pockets) is untested. **The plates support the
    0 / 180 degree reversal only**: the four-position zero planned for production (`docs/MANUFACTURING_PLAN.md` 6.2,
    6.7) needs a location on the round wall, which is not designed. Gauge plate: a ball on a dia 0.60 rim gains
    0.0038 mm of protrusion per 0.01 mm of hole diameter, so the reamed holes and their rims decide the +-0.02; the
    0.8 mm plate lies on three bosses only and is flat there by the clamp, not elsewhere (it does not need to be).
