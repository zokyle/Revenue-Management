# GreenLine GL-1 mechanical design package (parameters rev C-EVT1, drawings rev C-EVT1)

**Status: PROVISIONAL, not released. Nothing in this folder has been built, printed or measured.**
Every number comes from the CAD model, which is driven by `../design/master_params.yaml` (rev C). Where the model
differs from the written specification the difference is a numbered deviation (section 11); where a shared number
should change it is in `PROPOSED_PARAM_CHANGES.md`. `master_params.yaml` was not edited.

The package is for two readers: a US 3D-printing bureau (tub, base plate, cradle) and the person who assembles the
first units. Read "Open mechanical issues" (section 12) before ordering anything. The three that matter most: the
upper edge of the camera field has almost no margin for print tolerance; the marker is not shown to survive a
footstep (estimates say it does not); and the seal, the adhesives and the cradle latch are calculated, not tested.

![assembled marker](renders/GL1_render_a_front_top.png)

## 1. One command

```
cd greenline-marker/mechanical
python3 cad/build.py              # about 5 minutes; exits non-zero on any failed check, drawing or render
python3 cad/build.py --selftest   # seeds fifteen defects and confirms each check catches its defect (about 7 minutes)
```

`build.py` regenerates the solids, STEP and STL files, the resolved parameters, the check report, the drawings
(PDF, SVG, DXF, PNG previews) and the renders. Options: `--no-export`, `--no-drawings`, `--no-renders`, `--summary`.
It needs python3 with cadquery 2.8, numpy, scipy, shapely, matplotlib, pyyaml and ezdxf; `pdftoppm` for the previews;
node with Playwright (headless Chromium) and three.js 0.160 for the renders (`npm install three@0.160.0` in
`tools/render` if three.js is not found; `node_modules` is not committed). Headless WebGL occasionally loses its
context, so every render is composed from the drawing buffer, checked for a non-empty frame and retried up to three
times; a blank picture fails the build.

| Path | Content |
|---|---|
| `cad/params.py` | loads the YAML, holds the mechanical-only choices (`MECH`), derives every dependent dimension once |
| `cad/parts.py` | one function per part, each returns a CadQuery solid in the assembly frame |
| `cad/assembly.py` | named, coloured parts; allow-list of intended contacts; STEP / STL export; print orientations |
| `cad/checks.py` | the fourteen checks; `cad/optics.py` the exact ray trace; `cad/geom.py` sections, projections, ray casting |
| `cad/holddown.py` | cradle hold-down: beam model of the latch (retention, strain, forces), poses of the insertion path |
| `cad/latchfe.py` | plane-strain finite-element model of the latch on a section of the cradle solid (strain at the fillets) |
| `cad/deviations.py` | the recorded deviations with their status (text is built from the parameters) |
| `cad/drawings.py`, `cad/drawlib.py` | dimensioned drawings from projections and true sections of the solids |
| `cad/renders.py`, `tools/render/render.js` | renders of the exported STL meshes |
| `cad/selftest.py` | negative tests of the checks |
| `export/step/` | `GL1_assembly.step` (43 named parts, marker seated in the cradle), `GL1_marker_only.step`, one STEP per part, and `tub_print.step`, `base_plate_print.step`, `cradle_print.step` in print orientation |
| `export/stl/print/` | `tub_print.stl`, `base_plate_print.stl`, `cradle_print.stl`: the printed parts in print orientation, resting on z = 0 |
| `export/stl/parts/` | every part in the assembly frame (used for the renders and for the mesh checks) |
| `export/params_resolved.json` | YAML + mechanical-only + derived numbers, and the support-post rectangles |
| `export/part_table.json` | every modelled part with material, group, volume, mass and bounding box |
| `export/check_report.md`, `.json` | full check results with every table; `export/selftest_report.json` |
| `drawings/` | GL1-001, -002, -010, -011, -020 as PDF and SVG; `dxf/` 2D profiles; `preview/` PNG of every sheet |
| `renders/` | six PNG renders |
| `PROPOSED_PARAM_CHANGES.md` | disposition of the rev B proposals and the changes proposed to the shared YAML |

Frame (same as the YAML): origin at the puck centre on the base plane, +x right, +y forward toward the hole (the flat
visor face), +z up, millimetres. The base plane is the underside of the base plate. The cradle is modelled in the same
frame with the marker seated.

### What revision C changed in this package

| Rev C decision | In the model |
|---|---|
| Base plate 0.87 + adhesive sheet 0.13 | sheet at z 0.87 to 1.00, PCB at 1.00 to 1.80, no modelling overlap; seal joint 0.33 |
| Ball feet in through holes | three dia 1.15 holes, balls potted (epoxy modelled), dia 2.0 holes in the adhesive sheet; conical seats removed |
| PCB radius 21.1, two locating holes | 0.25 mm to the ledge; spigots dia 1.0 x 0.6 under posts E in a round hole and a slot |
| Cameras at x = +-10.0, larger windows | windows 5.0 x 3.4 in 5.5 recesses, clear opening +-2.0 (straight, no bevel), section B-B on x = 10.0 |
| Tub keep-outs are a contract | posts and hoods are generated from `tub_keepouts`; check 12 proves the contract on the tub solid |
| Cradle is a dock only | one orientation, no reference plate; fixed lip + sprung latch hold the marker against the pins (section 8) |

### What the design review of the first rev C build changed

Three reviewers examined the first rev C build of this package (geometry audit, assembly walk-through, sealing and
loads). Every finding was reproduced; the real ones were fixed in the CAD or, where a fix needs a shared number, a
test or another discipline, recorded in section 12 and in `PROPOSED_PARAM_CHANGES.md`.

| Finding | What was done |
|---|---|
| The two key notches of the base plate crossed the seal land: a through path from the underside into each camera bay | key lugs and notches deleted; the base plate is registered to the PCB in a lamination jig (D07); new check 13 proves by an air-solid test that outside and cavity are separate |
| Latch retention formula ignored the rotation of the hook; 3 x only at nominal size | retaining face raked 14 deg, beam widened to 24 mm, numerical beam model with rotation and lever growth, tolerance rows; 6.0 x in the governing position, 3.4 x with 0.3 mm less overlap (section 8) |
| Over-travel stop did not limit a pressed thumb tab; fillet strain above 2.5 % | stop under the tab; necked beam; plane-strain FE of the latch section in check 7: 2.05 % peak at full deflection |
| Cradle print file with the latch beam along the build direction | `cradle_print` is turned so that the latch profile lies in the build plane; orientation locked (section 4) |
| Wet docking: the pin slot was the only drain of the nest | drained nest floor, rim round the pin slot, dam and drain tunnel for the latch well (D25) |
| Rim of the tub in the same plane as the base: feet only 0.10 proud of a four-part tolerance stack | rim relief 0.25 mm (D23) |
| Cell between cover glass and LCD sealed, not served by the vent | vent channel in the LCD adhesive frame (D26); check 13 confirms the cell is part of the vented cavity |
| Vent hole is a well on the stepped-on top face | two drain grooves through the vent hole, thicker pad (D24) |
| Ball feet held only by the shear strength of the potting | sheet holes backfilled with epoxy so the balls bear on the PCB (D27) |
| LCD could not be inserted flat as written (0.10 mm to the ledge, liner trapped) | tilt-in path, proven on the solids in check 14 (D11); frame applied to the LCD |
| Wet black silicone closed blind next to the prism | bead of black adhesive cured on the tub before the join, modelled as a part (D13) |
| PCB joined blind, cameras first to engage | 0.3 mm lead-in chamfers on the hoods, chamfered spigot tips, join fixture; both closing motions proven in check 14 |
| Pin height 5.785 in the model, 5.82 in the text; phantom drawing dimensions; STL chord error; thick cradle corners | cradle PCB set from the pad copper face (D28); drawings corrected; print files at 0.005 mm; blind cores under the cradle feet |
| No test before the irreversible close; seal bead too small; base closed blind | new assembly sequence with two test gates, bead dispensed into the tub by volume, base laminated outside the tub (section 7) |
| Footstep, hard-floor, thermal bow, turf, grain opening, tail to J1, flush glass | not curable in this package: open issues 3 to 12 and proposals B6, B11 to B21 |

## 2. Part list

### Printed parts

| Drawing | Part | Material, process, finish | Box (mm) | Volume | Mass | Surface |
|---|---|---|---|---|---|---|
| GL1-010 | Tub (top shell) | HP 3D High Reusability PA 12, Multi Jet Fusion, dyed black, chemical vapor smoothing | 46.0 x 41.4 x 7.35 | 2.453 cm3 | 2.48 g | 49.7 cm2 |
| GL1-011 | Base plate | same material, dyed black, NOT vapor smoothed (hidden part with three bonding faces) | 43.5 x 40.0 x 0.87 | 1.114 cm3 | 1.12 g | 28.0 cm2 |
| GL1-020 | Cradle body with lip and latch | HP PA 12, Multi Jet Fusion, any colour, not smoothed, not tumbled | 60.0 x 60.0 x 22.6 | 27.07 cm3 | 27.3 g | 161.8 cm2 |

The print files are watertight single shells (tub 23,046 triangles, base 4,496, cradle 13,492) tessellated at
0.005 mm chord error and resting on z = 0; check 9 measures the largest facet sag on the main radius of each
(0.005 mm). The same three parts are exported as STEP in print orientation: send the STEP when the bureau accepts it.
The cradle latch is sized for PA12; do not substitute SLA resin without redoing the latch numbers.

### Purchased and custom parts (mechanical bill of materials)

Status is copied from `../design/DESIGN_SPEC.md` (VERIFIED or PROVISIONAL as defined there). Where the spec gives no
status the item is PROVISIONAL here. Every envelope in the CAD is a simple solid for fit checks, not a manufacturer model.

| # | Item | Qty | Part / source | Envelope modelled (mm) | Status |
|---|---|---|---|---|---|
| 1 | Camera cube | 2 | OmniVision OVM7692-RYAA, DigiKey 884-1027-1-ND | 3.47 x 2.95 x 2.76 | Dimensions VERIFIED (product brief via search); ball map, pitch, image orientation PROVISIONAL |
| 2 | Fold prism | 2 | Edmund Optics 32-526, 2.00 mm legs, N-BK7, aluminised hypotenuse | 2 x 2 x 2 right-angle | VERIFIED (dimensions, coating, $105 at 1-5); production source to be quoted |
| 3 | Memory LCD | 1 | Sharp LS013B7DH03, DigiKey 425-2903-ND | glass 26.6 x 30.3 x 0.75 | Outline VERIFIED (Sharp brochure via search); active-area offset, flex tail geometry and pin-1 side PROVISIONAL |
| 4 | Battery | 1 | PowerStream GM201030-PCB, 2 x 10 x 30 mm cell with protection board | 34 x 10 x 2.0 (+0.4 swell) | Listing VERIFIED; protection-board length, capacity, maximum delivered thickness and certificates PROVISIONAL |
| 5 | Cover glass | 1 | Flat mineral-glass watch crystal 28.0 x 1.0 (EVT, not step-proof); chemically strengthened glass with black border for production | dia 28.0 x 1.0 | PROVISIONAL |
| 6 | Cover-glass tape ring | 1 | 3M VHB 5907, 0.20 mm, die-cut dia 28 / dia 23 (`dxf/GL1-030`) | 0.2 thick | PROVISIONAL (converter not found) |
| 7 | Visor window | 2 | EVT: 0.5 mm clear cast acrylic or cover glass, cut 5.0 x 3.4; production: AR-coated borosilicate or sapphire, custom | 5.0 x 3.4 x 0.5 | PROVISIONAL (custom part, no source) |
| 8 | Window adhesive | - | low-viscosity light-cure acrylic, wicked in; 0.05 mm bond line round the opening, side gaps filled | frame 5.0 x 3.4 x 0.05 | PROVISIONAL (class only) |
| 9 | Vent | 1 | W. L. Gore VE80205 adhesive ePTFE vent, 5.0 outer, 2.0 vent area, 0.26 thick | dia 5.0 x 0.26 | PROVISIONAL (YAML basis: provisional) |
| 10 | Ball feet | 3 | 1.0 mm stainless balls (grade 25 or better) | dia 1.0 | PROVISIONAL |
| 11 | Ball potting | - | dual-cure (UV + heat or moisture) or two-part epoxy; stage 1 about 0.45 microlitre per foot, stage 2 about 0.35 | plug dia 1.15 x 0.87 + fill of the dia 2.0 sheet hole | PROVISIONAL (no part number); a UV-only grade does not cure in the shadow of the ball |
| 12 | LCD adhesive frame | 1 | 0.15 mm foam-type PSA frame 26.6 x 30.3 with a dia 23 window and a 0.8 mm vent channel (`dxf/GL1-030`), for example 3M VHB 5906 | 0.15 thick | PROVISIONAL |
| 13 | PCB-to-base adhesive sheet | 1 | 3M 9472LE (300LSE) adhesive transfer tape 0.13 mm, die cut with the grain opening, the pad slot and three dia 2.0 foot holes (`dxf/GL1-030`) | 0.13 thick | PROVISIONAL (YAML basis: provisional) |
| 14 | Foam pad | 1 | 0.3 mm soft PU foam (Poron 4790 class), 26.6 x 10, adhesive one side | 0.3 thick | PROVISIONAL |
| 15 | Perimeter seal adhesive | about 60 mm3 | opaque BLACK, thixotropic, work life of an hour or more, rated for sustained peel at 70 C on primed PA12 (structural acrylic or epoxy, not RTV) | 45.6 mm3 at nominal gaps: 0.33 x 0.4 joint on the land + the 0.25 mm radial groove | PROVISIONAL: adhesive not selected |
| 16 | Hood gasket | 2 beads | black, soft, silicone-free form-in-place gasket material (UV-cure urethane-acrylate class), 0.6 mm3 per hood | 3.9 x 0.25 x 0.25 as compressed | PROVISIONAL (class only) |
| 17 | Main PCB assembly | 1 | 4-layer 0.8 mm, D outline R 21.1, flat y 17.3, two non-plated locating holes (`dxf/GL1-040`) | board + the 13 YAML part boxes | Part boxes from the YAML; passives, battery leads and pads not modelled |
| 18 | Cradle spring pin | 4 or 7 | Mill-Max 0914-series long stroke; consumer cradle 4 (VBUS, D-, D+, GND), factory fixture 7 | plunger dia 1.07, barrel dia 1.83 | PROVISIONAL (working height 5.82, 0.59 N, stroke 2.29; diameters and barrel length not confirmed) |
| 19 | Cradle USB-C receptacle | 1 | GCT USB4105 | 8.94 x 7.35 x 3.26 | Envelope PROVISIONAL |
| 20 | Cradle PCB | 1 | 2-layer 1.6 mm, 30 x 22 (YAML), seven pin positions | 30 x 22 x 1.6 | Position is a mechanical proposal (`PROPOSED_PARAM_CHANGES.md` B5) |
| 21 | Cradle feet | 4 | self-adhesive bumpers dia 8 x 3 | dia 8 x 3 | PROVISIONAL (generic) |
| 22 | Cradle PCB screws | 4 | M2 x 5 thread-forming screws for plastic | not modelled | PROVISIONAL (generic) |

Fixtures and gauges the build needs (not product parts, not in this CAD):

- **Ball gauge plate** (step 2): a flat ground plate with three reamed dia 0.60 holes at least 0.3 deep at (0, 15.0),
  (-16.5, -9.5), (16.5, -9.5), two edge stops and a windowed weight that clamps the base plate flat. A 1.0 mm ball
  seated on the rim of a dia 0.60 hole stands exactly 0.10 mm below the plate surface, and the rim seals the epoxy.
  (A 0.10 mm shim with clearance holes on a flat plate does the same job less precisely.) Mould release on the plate.
- **Lamination jig** (step 10): a support nest for the component side of the PCB with pockets for every part, two dia
  1.10 pins for the locating holes and a frame that locates the D outline of the base plate; a flat press plate with
  three relief holes for the ball feet.
- **Prism jig** (step 10), referenced to the two locating holes of the PCB.
- **Join fixture** (step 11): a nest for the upturned tub and a hinged carrier for the PCB / base unit, hinge axis
  parallel to x at y = -30, z = 0 (7 mm behind the tub at the base plane), lateral guidance +-0.1 mm. Check 14
  proves both this hinged motion and a straight descent (for which a guide collar on the tub rim, bore dia 43.7 with
  the flat, would serve instead).
- **Go gauges**: disc dia 42.6 x 1 (ledge radius 21.30 or more); block 4.90 high for the bay roof above the post feet;
  ring dia 1.10 for the spigots; height gauge for the prism tops (4.85 maximum above the PCB).
- **Vacuum pen** for the LCD; **positive-displacement dispenser** for the epoxy, the hood gaskets and the seal bead.
- **Pogo test fixture** for the seven pads; **leak-test chamber** with a soft pad that occludes the vent hole and its grooves.
- **Factory calibration fixture** (manufacturing plan): a flat with a three-point nest on a granite surface plate for
  the tilt calibration. Zeroing in the field is done by the user on any hard flat surface. Neither uses the cradle.

Estimated mass (typical densities, envelope solids, no solder or passives): marker 11.3 g, centre of gravity at
(0.05, -1.40, 3.75) mm, 8.1 mm inside the triangle of the ball feet; cradle assembly with seven pins 31.2 g.

## 3. What the parts look like

| | |
|---|---|
| ![underside](renders/GL1_render_b_underside.png) | ![exploded](renders/GL1_render_c_exploded.png) |
| ![cut-away](renders/GL1_render_d_cutaway.png) | ![in cradle](renders/GL1_render_e_in_cradle.png) |
| ![cradle section](renders/GL1_render_f_cradle_section.png) | |

Renders (2000 x 1500; the exploded view is 1800 x 2400). The tub is drawn dark grey so that its shape reads; the real part is black.

- `GL1_render_a_front_top.png`: assembled marker from the front and above: visor windows, cover glass, nose groove, vent hole with its drain grooves, rim relief.
- `GL1_render_b_underside.png`: from below: grain opening with baffle ring, LED pairs and photodiode, pad slot with the seven pads, the three potted ball feet, the seal adhesive visible in the groove at the rim.
- `GL1_render_c_exploded.png`: every marker part separated along z and labelled, including the adhesive sheet, the window adhesive frames, the hood gaskets and the epoxy pottings.
- `GL1_render_d_cutaway.png`: boolean cut on x = 0 behind y = 13.0 and on x = 10.0 through camera R in front of it, labelled.
- `GL1_render_e_in_cradle.png`: marker in the cradle from the rear right: latch with thumb tab, guard wall, tab stop, lip, finger scallop, USB-C receptacle and the drain outlet beside it.
- `GL1_render_f_cradle_section.png`: marker in the cradle cut on x = 0: centre spring pin compressed on its pad, lip over the front edge, raked latch hook over the rear edge, tab stop, drained floor.

Drawings (A3, PDF and SVG; PNG previews in `drawings/preview/`; title block with part, material, process, general tolerance,
revision C-EVT1 and "PROVISIONAL - not released"):

- `GL1-001_assembly_outline`: top view, view on the visor face and side view with overall size (dia 46.0, 41.4, 7.6), camera baseline 20.0, optical axis height 5.61, window and recess sizes, ball feet, rim relief.
- `GL1-002_sections` sheet 1: section A-A on x = 0 with every part labelled; detail C with the full z stack (base 0.87, adhesive sheet 0.13, PCB 1.00 to 1.80, ...).
- `GL1-002_sections` sheet 2: section B-B on x = 10.0 through camera R; detail D with the camera stack, the wall build-up in y, the hood gasket and the traced chief rays (+17.6 / -8 deg).
- `GL1-010_tub` sheet 1: view into the cavity with posts, spigots, hoods, ribs, ledge; detail E of wall, ledge and plain roof on the arc (section y = 0); post table (the YAML keep-outs).
- `GL1-010_tub` sheet 2: top view, sections A-A and B-B of the tub alone, detail G of the camera opening in plan (straight, 4.0 wide), view on the visor face.
- `GL1-011_base_plate`: top view with every hole dimensioned (plain edge, no notch), detail H of a ball foot as assembled (ball, two-stage potting, adhesive-sheet hole, gauge plate), feature table.
- `GL1-020_cradle` sheet 1: top view with the drained floor, section D-D with the marker seated, view from below.
- `GL1-020_cradle` sheet 2: detail J of the latch (beam thicknesses, rake, stops) and detail K of the lip, section E-E through the pin row, insertion path, hold-down table, cradle PCB table.
- `drawings/dxf/`: tub, base plate and cradle profiles on named layers (GL1-010, -011, -020); the three adhesive die-cuts (GL1-030: PCB sheet with the three dia 2.0 foot holes, LCD frame with its vent channel, cover tape ring); the main PCB outline with its locating holes (GL1-040); sections A-A and B-B.

## 4. Print orientation and notes for the bureau

1. **Process.** HP Multi Jet Fusion, PA 12. Tub: dyed black and chemically vapor smoothed. Base plate: dyed black, not
   smoothed. Cradle: any colour, not smoothed and **not tumbled** (the latch is a 1 mm beam with a heavy head).
2. **Orientation.** `export/stl/print/` and `export/step/*_print.step` hold the parts in build orientation (z up):
   - tub roof-down, so that the cosmetic top face and the cover-glass recess face the bed and the cavity is open upward;
   - base plate flat;
   - **cradle with its x axis (one of the 60 mm sides) as the build direction. This orientation is LOCKED**: the side
     profile of the latch beam and of the lip then lies in the build plane, so that their bending stress runs along
     the layers and not across them. Please confirm it on the order.
   The functional planes of the tub must stay parallel to each other: LCD bonding plane z 5.55, recess floor z 6.35,
   seal face z 1.2 and the eight post feet at z 1.8.
3. **Walls.** Designed to 0.8 mm minimum (side wall 1.0). The wall audit (check 5) lists every place below 0.8 mm,
   eight regions in all: the 0.525 mm strip behind each window recess in front of the camera (D04, accepted,
   4.0 x 0.4 mm), the feet of chamfered edges (side wall 0.70 at the rim, hood rear walls 0.68, hood skirts 0.50 at
   their 0.3 mm lead-in chamfer), and the nose of the cradle hook (a solid wedge ending in a 0.4 mm flat: an edge, not a
   wall). The two locating spigots are dia 1.0 pins with chamfered tips. The base plate has no wall below 0.8 mm.
   Please confirm that 0.8 mm walls survive your vapor smoothing.
4. **Powder.** No closed void and no cavity without a 2 mm escape path (check 6, which lists six open recesses narrower
   than 2 mm in the tub: the gaps between posts C and the side wall and the two corners where the thick roof meets the
   side wall). Other open narrow places that need attention: the two camera bays and visor openings, the dia 1.0 vent hole (it may fuse
   shut: clear it with a 1.0 mm drill) and its two 0.6 mm grooves, the three dia 1.15 ball-foot holes, and in the cradle
   the pin slot (2.33 mm wide, through), the latch well (gaps 2.2 / 2.7 / 1.2 mm round the beam, open at the top,
   6.8 mm deep), its 2.4 x 2.4 mm drain tunnel to the rear face and the four dia 5 blind cores behind the foot pockets.
5. **Dimensions to report at first article.**
   - Tub: ledge radius 21.35 (a dia 42.6 disc must pass); bay roof 5.0 above the post feet (4.90 minimum); the two
     spigots (dia 1.0 x 0.6): diameter and position, they must enter a dia 1.15 hole.
   - Base plate: thickness 0.87 +-0.05 (0.82 to 0.92 accepted); flatness in the free state 0.3 mm maximum on a surface
     plate (flatten under weight in an oven if exceeded); the three foot holes are reamed to dia 1.15 by us.
   - Cradle: front nest wall to hook nose 39.95 +-0.15; beam thickness 1.03 above the root fillets, 0.95 half way up,
     0.89 at the neck; beam to stop ribs 1.30; top of the tab stop 3.46 below the tab; nose 0.25 above a seated marker.
6. **Post-processing by us, not the bureau.** Four dia 1.6 x 3 pilot holes in the cradle at the printed spot marks;
   gauging of the spigots; reaming of the foot holes.
7. **Tolerance.** Quoted general tolerance +-0.3 mm or +-0.3 %. Every drop-in fit has 0.25 mm nominal clearance; the
   only fit below it is the spigot fit (section 5).

## 5. Tolerances and fits

Nominal values from check 2 (all computed on the solids). "Rule" is the 0.25 mm drop-in clearance of the specification.

| Fit | Nominal gap (mm) | Against the rule | Comment |
|---|---|---|---|
| Base plate in the tub, radial | 0.25 | meets | groove filled with seal adhesive down to the rim; plain edge, no key (D07) |
| Tub rim above the base plane (rim relief) | 0.25 | - | rim 0.35 above the plane of the ball feet (D23) |
| Base plate top to tub seal face | 0.33 nominal, 0.17 to 0.49 with the stack tolerance | adhesive joint | set by post foot to seal face (printed), PCB, sheet and plate: +-0.16 RSS |
| PCB edge to the seating ledge, radial | 0.25 | meets | rev C: PCB radius 21.1 |
| PCB locating spigots in the round hole / across the slot | 0.075 | **below (D19), by specification** | this is the locating fit that positions the cameras; +-0.325 along the slot. Gauge the spigots |
| Spigot tip above the adhesive sheet | 0.20 | - | spigot is 0.6 long in a 0.8 board; tip chamfer 0.15 captures +-0.225 |
| PCB flat edge to visor wall | 0.30 | meets | |
| LCD glass in its pocket (ribs, posts E, hood rear walls) | 0.25 | meets | |
| LCD glass past the seating ledge during assembly | 0.28, glass tilted 6 deg and shifted 0.55 forward | meets (D11) | check 14; a flat glass shifted 0.25 would have 0.10 |
| LCD glass to roof bonding plane | 0.15 | adhesive frame | |
| Cover glass in its recess, radial | 0.25 | meets | top face 0.05 below flush: about one unit in four will be proud (open issue 11) |
| Visor window in its recess, per side | 0.25 | meets | 0.05 bond line behind it; flush with face and top by design (open issue 11) |
| Camera cube to hood (sides, top, front pad) | 0.25 (sides 0.265) | meets | 0.3 mm lead-in chamfers at the mouth of the hood |
| Prism to roof | 0.19 | YAML stack value | go gauge 4.90 for the bay, 4.85 for the prism top |
| Prism hypotenuse to hood rear wall | 0.26 | meets | hood gasket 0.20 from the prism |
| LCD glass to camera cube | 0.63 | meets | |
| Battery to foam pad | 0.55 | 0.40 swell + 0.15 | battery to LCD glass 0.85 |
| Photodiode to baffle ring | 0.249 | meets (YAML rounds the ring to 5.91) | registration by the lamination jig; a rebalanced ring is proposed (B11). LEDs 0.75 from the nearest plastic |
| Support posts on the PCB | 0 (contact) | datum | posts set the PCB height; nearest listed part 0.45 mm (U1 to posts E) |
| Ball top to PCB underside | 0.10, filled with epoxy | - | ball stands 0.03 above the plate inside the dia 2.0 hole of the sheet (D27) |
| Ball feet below the base plane | 0.10 | - | set on the gauge plate, not by the print |
| Marker in the cradle nest, radial | 0.25 | meets | |
| Base plate above the nest strip and pads / tub rim above them | 0.10 / 0.35 | - | the three balls carry the marker |
| Lip and latch nose above the tub top | 0.25 | meets | the marker floats up to 0.25 against them when pins are fitted (D21) |
| Lip to the visor windows / cover glass / vent hole | 1.52 / 3.21 / 22.9 | clear | the lip is 12 mm wide, the window recesses start at x = +-7.25 |
| Latch to the cover glass / vent hole | 7.31 / 18.7 | clear | |
| Latch to the walls of its well | 1.2 (sides), 1.30 (stop ribs), 2.2 (front) | printable gaps | |
| Spring-pin plunger in the base and adhesive slot | 0.565 | meets | pin diameters PROVISIONAL |
| Spring-pin barrel in the printed slot; cradle PCB in its pocket; USB shell | 0.25 | meets | |
| Light bundle to the visor opening: sides / sill / top | 0.378 / 0.397 / 0.054 | **top has no margin** | see open issue 1 |

Camera position tolerance (check 4, camera R). The PCB is located by the two spigots, 8.4 mm apart; +-0.075 mm at each
gives +-0.094 mm sideways and +-0.179 mm fore-aft at a camera and +-1.02 deg of yaw (a stereo-calibration item).

| Case | Full pupil clear to (deg): left / right / up / down | Worst field-point transmission |
|---|---|---|
| Nominal | 25.6 / 25.6 / 18.6 / 15.4 | 97.7 % |
| PCB at the end of its spigot play, 0.094 mm sideways | 25.6 / 25.6 / 18.6 / 15.4 | 97.7 % |
| Spigot play plus 0.2 mm print tolerance, 0.294 mm sideways | 25.6 / 25.6 / 18.6 / 15.4 | 97.7 % |
| Yaw play, optics 0.179 mm toward the visor | 25.6 / 25.6 / 19.7 / 16.3 | 97.7 % |
| Yaw play, optics 0.179 mm away from the visor | 25.6 / 25.6 / 17.6 / 14.5 | 97.7 % |
| Optics 0.2 mm low | 25.6 / 25.6 / 22.1 / 11.7 | 97.7 % |
| Optics 0.2 mm high | 25.6 / 25.6 / 15.0 / 18.9 | 63.6 % |

Required field: +-26 deg horizontal, +17.6 / -8 deg vertical (rev C). The horizontal limit of 25.6 deg is the 2.0 mm
prism exit face, not the opening (2.3 % of the assumed pupil is clipped at the field edge). The opening is wide
enough sideways for the spigot play plus the print tolerance; the lower field has 3.7 deg in hand even with the optics
0.2 mm low; **the upper field does not survive 0.2 mm of height error**. The entrance-pupil position (0.4 mm below the
cube top) and diameter (0.38 mm) are assumptions; the lens data is not published.

Stack tolerances (arithmetic on assumed part tolerances: printed features +-0.10, PCB +-0.08, sheet +-0.02):

| Chain | Nominal | Tolerance | Consequence |
|---|---|---|---|
| Tub rim to base plane: post foot, PCB, sheet, plate | rim 0.25 above the base plane | +-0.16 RSS, +-0.29 worst case | with the rim relief the ball feet stay the lowest points (0.35 nominal to the rim) |
| Seal joint: same chain to the seal face | 0.33 | +-0.16 RSS | the bead is dispensed by volume into the tub, not as a 0.5 mm bead on the land |
| Prism top to bay roof | 0.19 | +-0.21 RSS (cube and bond tolerances assumed) | go gauges in step 1 and step 10 |
| Cover glass below flush | 0.05 | +-0.15 RSS | proud on roughly one unit in four (open issue 11) |

Thermal estimate over -10 to 70 C from a 23 C assembly (PA12 about 110 ppm/K, FR-4 15, soda-lime glass 9, LCD glass 4;
handbook values, not measured): the edge of the cover glass moves 0.06 mm against the tub (30 % shear of the 0.20 mm
tape), a corner of the LCD glass 0.10 mm (67 % of its 0.15 mm frame), the PCB edge 0.09 mm against the base plate
(72 % of the 0.13 mm sheet). The two spigots move 0.04 mm apart (the slot allows +-0.325). The diametral clearance of
cover glass and LCD glass shrinks from 0.50 to about 0.40 mm at -10 C. The bimetal effect of the PCB / base laminate
is open issue 6.

## 6. The z stack in revision C

| From | To | Item |
|---|---|---|
| -0.10 | 0.90 | ball feet (dia 1.0), potted in the dia 1.15 through holes of the base plate |
| 0.00 | 0.87 | base plate |
| 0.25 | 7.60 | tub (the side wall ends 0.25 above the base plane) |
| 0.87 | 1.00 | die-cut adhesive sheet (0.13), with the grain opening, the pad slot and three dia 2.0 holes round the feet (filled with epoxy) |
| 0.87 | 1.20 | perimeter seal joint (0.33) between the base land and the tub seal face; the adhesive also fills the radial groove down to z 0.25 |
| 1.00 | 1.80 | main PCB; spigots reach from 1.80 down to 1.20 inside the two locating holes |
| 1.80 | 3.80 | battery; 3.80 to 4.20 swelling allowance |
| 4.35 | 4.65 | foam pad |
| 4.65 | 5.40 | LCD glass; 5.40 to 5.55 adhesive frame |
| 5.55 | 6.35 | roof ledge; 6.35 to 6.55 tape ring; 6.55 to 7.55 cover glass |
| 7.60 | | top of the tub |

At the cameras: base 0.87, adhesive 0.13, PCB 0.80, cube 2.76, bond 0.05, prism 2.00 (top at 6.61), 0.19 clearance,
roof 0.80. Optical axis 5.61 mm above the base plane. Check 1 finds no volume overlap anywhere in the assembly.

## 7. Assembly sequence

Adhesive types are classes, not released part numbers; cure times are to be taken from the chosen product's data sheet.
Work on the tub upside-down in a nest that supports the roof ring unless a step says otherwise. The last column says
until when the result of a step can still be seen and corrected. **After step 13 nothing inside can be reworked.**

| Step | Operation | Check or gauge | Inspectable / reworkable until |
|---|---|---|---|
| 1 | Incoming inspection | see below | - |
| 2 | Ball feet, stage 1, on the gauge plate | protrusion 0.10 +-0.02, all three | step 10 (re-pot) |
| 3 | Adhesive sheet onto the base plate | holes over the feet, slot and opening aligned | step 10 |
| 4 | Surface preparation of every PA12 bonding face | - | - |
| 5 | Cover glass, then the rim-gap fillet | crystal not proud of the top face | always (outside) |
| 6 | Visor windows | inner face clean, no adhesive in the opening | step 11 (through the bays) |
| 7 | Vent disc | centred on the hole | step 11 |
| 8 | Hood gaskets, cured | bead on the flat of the rear wall, not past its chamfer | step 11 |
| 9 | LCD, tilted in; foam pad | glass against the rear ribs, bonded all round the aperture | step 11 |
| 10 | PCB sub-assembly: battery, prisms, base plate laminated, edge fillet | prism height; wet-out at pad slot and grain opening; **test gate 1** | step 11 |
| 11 | Seal bead into the tub; tail into J1; close in the join fixture | LCD test pattern; base 0.25 +-0.10 proud of the rim at four points | step 13 (open time of the adhesive) |
| 12 | **Test gate 2** with the adhesive still wet; top-up fillet from outside | continuous visible fillet all round | step 13 |
| 13 | Cure under the press weight | - | no rework after this |
| 14 | Leak test, functional test, dark frames | - | - |
| 15 | Tilt calibration on the granite plate | - | - |

1. **Incoming inspection.** Tub: z of the bonding plane, recess floor, seal face and post feet (one plane each, +-0.1);
   recess dia 28.5; window recesses 5.5 wide; the dia 42.6 disc gauge must pass the ledge ring; the 4.90 block must
   stand on the post feet under each bay roof; the dia 1.10 ring gauge must go over both spigots and a bare PCB must
   drop over them and seat on all eight posts without force (dress an oversize spigot with a hollow punch or a fine
   file, never by enlarging the PCB hole). Vent hole, grooves, camera openings clear of powder. Base plate: thickness
   0.82 to 0.92, free-state flatness 0.3 mm or better, ream the three foot holes to dia 1.15. Clean all printed parts
   with isopropanol and dry them.
2. **Ball feet, stage 1 (gauge plate).** Lay the base plate, PCB side up, on the gauge plate against its edge stops and
   clamp it flat with the windowed weight. Drop one 1.0 mm ball into each dia 1.15 hole: it seats on the rim of its
   dia 0.60 gauge hole. Dispense about 0.45 microlitre of epoxy into each hole from above until it is full round the
   ball; the dome over the plate must not exceed 0.08 mm. Cure completely before unclamping (UV from above, then the
   secondary cure: the lower half of the joint is in the ball's shadow). Check the protrusion on a surface plate:
   0.10 +-0.02 mm, all three; reject and re-pot otherwise.
3. **Adhesive sheet.** Laminate the die-cut 0.13 mm sheet to the base-plate top (grain opening, pad slot and the three
   foot holes aligned). Leave the liner on.
4. **Surface preparation.** Prime or plasma-treat every PA12 bonding face according to the adhesive maker: recess floor,
   LCD bonding plane, seal face with the corner to the side wall, visor-wall underside, window recesses, vent pad,
   hood rear-wall undersides, base-plate land and edge.
5. **Cover glass.** Tub top-up on a mandrel that supports the roof ledge from inside. Apply the VHB 5907 ring to the
   recess floor, remove the liner, centre the crystal (0.25 mm radial gap) and press with the load the tape maker
   specifies. After the dwell, fill the 0.25 mm gap round the crystal with a fillet of black sealant so that it cannot
   hold water against the edge of the tape.
6. **Visor windows.** Hold each 5.0 x 3.4 window in a positioning clip: bottom edge on the shelf, front face flush
   with the visor face (0.05 mm off the recess floor). Wick low-viscosity light-cure acrylic into the two 0.25 mm side
   gaps and along the top edge; it is drawn into the 0.05 mm bond line round the opening (0.5 mm at the sides, 0.4 mm
   at the sill, 0.8 mm at the top). Cure through the window. Inspect the inner face through the open bay and swab it
   if needed; the bay stays reachable until step 11.
7. **Vent.** Tub upside-down. Apply the vent disc to the pad inside the roof, centred on the 1.0 mm hole; press evenly.
8. **Hood gaskets (D13).** Dispense a bead of the black gasket material, 0.25 mm wide, 0.6 mm high and 3.9 mm long
   (0.6 mm3), on the flat underside of each hood rear wall, its front edge 0.15 mm behind the front face of the wall
   (just behind the chamfer; the prism will stand 0.2 mm in front of it). Cure it now. The cube top will later
   compress it to the 0.25 mm slit; nothing is wet when the PCB goes in.
9. **LCD (tilted in, D11).** Apply the 0.15 mm adhesive frame to the top face of the LCD glass, vent channel at the
   rear right corner, and remove its liner. Pick the glass up with the vacuum pen on its underside. Enter rear edge
   first, tilted about 6 deg and shifted 0.5 to 0.6 mm toward the visor, until the rear corners have passed the
   seating ledge (0.28 mm clearance); the front edge is then still outside the spigots and post feet. Push the glass
   back against the two rear ribs, hinge the front up (it clears posts E and the hood rear walls by 0.25 mm) and
   press it onto the bonding plane all round the aperture. Leave the flex tail standing. Stick the foam pad to the
   underside of the glass over the battery zone.
10. **PCB sub-assembly** (outside the tub, cameras soldered).
    - Fix the cell with transfer adhesive of 0.05 mm or less, dress and solder its leads, clean, inspect (pads and lead
      route are not in the YAML yet: open issue 13). Soldering comes before the optics.
    - Bond each prism on its cube with UV adhesive at the four corners only (air gap over the lens), exit face toward
      +y at y = 16.6, in the prism jig; cure. Prism top 4.85 mm or less above the PCB on the height gauge.
    - Lamination: PCB component-side down in the support nest of the lamination jig, on its two pins. Remove the liner
      of the adhesive sheet, put about 0.35 microlitre of epoxy into each of the three sheet holes (stage 2: the ball
      then bears on the PCB), lower the base plate in the jig frame and press with the press plate at the pressure the
      tape maker specifies (about 120 N for 0.1 MPa). Inspect the edge of the sheet at the pad slot and round the grain
      opening from the base side: no gap, no lifted edge. Cure the epoxy.
    - Run a fine fillet (0.2 mm) of the seal adhesive round the edge of the PCB onto the base plate, inside r 21.3, and
      let it gel: a second barrier behind the 1.06 to 1.37 mm lands of the sheet.
    - **Test gate 1** on the pogo fixture: supply through the pads, both camera IDs, one frame per camera on a target
      (prism centring), IMU, charge current, grain LEDs and photodiode.
11. **Seal bead, tail, close.** Tub upside-down in the join fixture. Dispense about 60 mm3 of the black seal adhesive
    as one continuous bead into the corner between the seal face and the side wall all round the arc (both faces look
    up) and along the underside of the visor wall, without a gap at the two D corners. Put the PCB / base unit on the
    hinged carrier, open; make the one U-fold in the LCD tail, insert it into J1 and close the actuator under a
    magnifier (see open issue 9 for the tail length this needs). Power the unit through the pads and check an LCD
    test pattern. Close the carrier: the unit turns about the fixture hinge onto the two spigots and the eight posts,
    the cube tops bed into the hood gaskets. Press with the press plate (relief holes over the ball feet). With a
    depth gauge at four points the base plate must stand 0.25 +-0.10 mm proud of the tub rim.
12. **Test gate 2 and fillet**, within the open time of the adhesive: frames from both cameras through the windows
    (prisms centred in their openings, no gasket in the field), dark frames under strong side light, LCD, IMU. If
    anything fails, open the carrier, wipe the adhesive off and correct. Then top up from outside into the 0.25 mm
    groove between base plate and wall until a continuous fillet is visible all round the rim, across the visor front
    and at both D corners; wipe the excess.
13. **Cure** the seal adhesive under the press weight for the full time on its data sheet.
14. **Leak test** in the chamber with the vent hole and its grooves occluded by the soft pad (pressure decay; the free
    air volume of the unit is 4.27 cm3, check 13). Then functional test, including a dark-frame light-leak test of
    both cameras under strong side light.
15. **Tilt calibration** only after full cure, in the factory calibration fixture on the granite plate (not in the cradle).

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

Seven pins at 0.59 N push up with 4.13 N at y = -17 (four pins: 2.36 N); the marker weighs 0.11 N.

- **Fixed lip** at the front: 12 mm wide (|x| <= 6, between the window recesses, which start at |x| = 7.25), 1.6 mm thick,
  reaching 1.2 mm over the top front edge of the tub with 0.25 mm clearance. It stands on a tower in front of the visor;
  under it a nose pocket 1.0 mm deep lets the top front corner of the tilted marker swing in. Nearest window 1.52 mm,
  cover glass 3.21 mm, vent hole 22.9 mm away.
- **Sprung latch** at the rear: a rectangular cantilever 24 mm wide and 11.65 mm long (root at z = -3.8, 1.055 mm above
  the PCB pocket, R1.0 root fillets) standing in an open well. Its front face is vertical; its back face makes it
  1.05 mm thick at the root, 0.85 mm nominal at a neck 2.5 mm below the hook (0.89 mm on the solid, because the two
  tapers are blended with R8) and 1.30 mm where it runs into the hook. The hook is as wide as the beam and has a **straight nose** at y = -21.30, 0.25 mm above the tub top, and a
  **retaining face raked back 14 deg** (the nose is its lowest point), with a 30 deg lead-in above. The nose lies
  1.10 mm on the flat top of the tub with the marker centred and 0.85 mm with the marker against the front nest wall.
  A thumb tab 14 mm wide and 7.9 mm long projects rearward from the top: pressing it down bends the beam back.
- **Two over-travel stops.** Two ribs on the guard wall, 1.30 mm behind the beam at z 5.5, stop a hook that is pushed
  or pulled back at 1.9 mm of travel. A rest under the end of the thumb tab (10 x 2 mm, top at z 6.57, 3.46 mm below
  the tab) stops a pressed tab at 2.0 mm of hook travel; any further thumb force goes into the rest, not into the beam.
  The ribs sit below the hook at the height where a pressed tab would reach them only at 2.11 mm, so they never block
  a release.
- The marker rests on its three ball feet on a front strip and two pads of the nest; the D flat (front nest wall at
  y = 18.65) is the key, so it seats one way round only (check 7: at 90, 180 and 270 deg the solids collide).
- **Drained floor** (D25): outside the strip and the pads the nest floor is 0.65 mm lower on the centre line and
  falls 2 deg to both sides, out through the finger scallops. A rim round the pin slot and a dam in front of the
  latch well stay at the level of the strip; the well drains to the rear face through a tunnel beside the USB opening.

Numbers (check 7; method in `cad/holddown.py`; E = 1700 MPa, HP PA 12 data sheet, dry, 23 C; I(s) = b h(s)^3 / 12).
The beam is integrated numerically, curvature = M / (E I(s)). "Hook travel" is the backward travel of the beam axis at
the nose level.

| Quantity | How | Value |
|---|---|---|
| Hold-down reactions with seven pins | moments about lip (y 17.80) and hook contact (y -22.15) | hook 3.54 N, lip 0.48 N (four pins: 2.00 / 0.25 N) |
| Retention, no friction, marker centred | largest upward force on the hook before the nose leaves the flat top; moment about the deflected axis | 31.7 N at the hook = 36.3 N at the pin row = 8.8 x the seven-pin force |
| **Retention, governing position** (marker against the front wall, where the lead-in leaves it) | same, overlap 0.85 | 21.7 N = 24.9 N at the pin row = **6.0 x** (required 3 x); 3 x needs E of 848 MPa or more |
| Same with 0.2 / 0.3 mm less overlap (print tolerance) | overlap 0.65 / 0.55 | 4.2 x / **3.4 x**; 3 x at -0.3 mm needs E of 1485 MPa or more |
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
90 deg face then becomes a ramp that cams the latch open (for the first rev C latch, 14 mm wide with a 90 deg face, the
design review corrected the 4.0 x of its closed formula to about 3.2 x in the governing position). With the face raked more than
the hook turns, the nose corner bears on the flat top of the marker, the frictionless reaction stays vertical and the
hook lets go only when the nose has travelled the whole overlap. The figures above are frictionless lower bounds;
with any friction above about 0.2 the hook is self-locking.

Insertion path (check 7, drawing GL1-020 sheet 2): the marker solids (tub, base plate, balls) were posed at 19 tilts from
17 deg to 0, resting on the front strip and as far forward as the front wall, the nose pocket and the lip tip allow. At
every pose the intersection with the cradle (latch removed) is zero, the free-length plungers (tip at z = 2.105) enter
the pad slot without touching base plate or adhesive sheet, and the latch needs at most 1.42 mm of travel. The pads
meet the plungers at about 1.9 deg; seated, the pins stand 5.82 mm high and are compressed 1.14 of 2.29 mm. With pins
fitted the marker is pushed up against lip and hook: it floats up to 0.25 mm above its feet and the pins then stand
6.07 mm high (0.89 mm of stroke, D21).

Finger access: the nest wall is removed over two sectors beside the marker (from -42 deg to 0 deg on each side, 16.5 mm of
the marker's side, full height); 42 of 42 test rays from each side reach the marker.

Printability: no wall of the cradle below 0.8 mm (latch root 1.05 mm, neck 0.85 mm; the hook nose is a solid wedge
ending in a 0.4 mm flat), no trapped powder (checks 5 and 6).

## 9. Sealing concept and what must be tested

The marker is bonded, with no O-ring. Check 13 proves on the solids that the modelled seals close the cavity: a box
minus all marker solids leaves the outside and the inner cavity as two separate bodies of air.

| Seal | Geometry | Concern |
|---|---|---|
| Cover glass | VHB 5907 ring dia 28 / 23 (2.5 mm wide) on the recess floor; the cell under it is vented into the cavity through the LCD frame | foam tape on vapor-smoothed PA12: primer, dwell; rim gap filled with sealant |
| Visor windows (2) | light-cure adhesive: 0.05 mm bond line round the opening (0.5 mm at the sides, 0.4 mm sill, 0.8 mm top), side gaps filled | narrow lands; adhesive must not creep into the 4.0 x 2.2 opening; the 0.525 mm sill (D04) relies on the bonded window |
| Base perimeter | one closed ring: joint 0.33 mm high on a 0.4 mm land under the tub ledge, 0.65 mm under the visor wall, plus the fill of the 0.25 mm radial groove down to the rim (45.6 mm3 nominal, dispense 60) | the joint height follows a tolerance stack (0.17 to 0.49); black, thixotropic adhesive dispensed into the tub by volume; no glue channel is possible (D06); land well under the 1.5 mm that the project's research note asks for |
| PCB underside | the 0.13 mm adhesive sheet closes the grain opening and the pad slot; lands to the PCB edge 1.37 mm (pad slot), 1.30 and 1.06 mm (foot holes); fillet round the PCB edge as second barrier | PCB vias must be tented and plugged (spec); the sheet is the only barrier at the pad slot |
| Ball feet (3) | epoxy plug 0.87 mm long round each ball, then the backfilled sheet hole | each potting is a seal and carries a foot |
| Vent | Gore VE80205 on a pad inside the roof, 1.0 mm hole with two drain grooves on the top face | water-entry pressure not confirmed; the hole is on the face that is stepped on |

The two PCB locating holes are inside the sealed volume. The two pockets under the ends of the visor wall (D14) are
outside the seal ring; they hold about 1.7 mm3 of water each unless the outside fillet fills them.

Tests required before any water claim (loads from `../docs/research/enclosure-manufacturing.md`, itself unverified):

1. Pressure-decay leak test of every unit with the vent occluded (step 14); sectioned samples to confirm that the
   perimeter joint and groove are filled.
2. 25 kPa inward (hot unit into cold water at 1 m) and 40 kPa outward for 24 h at 70 C (blocked vent, altitude plus
   heat) on sealed samples. With a blocked vent 40 kPa pushes the base out with about 55 N, carried by the perimeter
   joint alone (design-review estimate: about 0.4 N/mm of peel).
3. Dunk test including the hot-unit-into-cold-water case on the first units; vent water-entry pressure of at least
   50 kPa; a step on a wet unit followed by a leak test (does a sole pump water through the vent?).
4. Lap-shear and peel coupons of each adhesive on PA12 as finished (smoothed tub, unsmoothed base), with and without
   primer, before and after thermal cycling (-10 to 70 C, 100 cycles), UV and sunscreen / fertiliser exposure;
   push-in test of a potted ball (target 100 N).
5. Light-leak coupon: black MJF PA12 at 0.8 mm in direct sun; dark frames of assembled units, with and without the
   gaps beside the cubes masked (D13).
6. Footstep: 800 N on a 20 mm indenter on the cover glass and on the roof, with the LCD powered, on turf and on a
   hard floor, at 23 and 60 C (open issues 3 to 5).
7. Fogging of the cover glass: hot-humid soak, then a cold plate on the glass.
8. Wet docking: 100 dockings of a marker wetted with 0.3 S/m solution, then inspection of the pads (open issue 8).
9. Thermal cycling of complete bonded units, -10 to 70 C, 100 cycles: then leak test, LCD position and display
   inspection, tilt offset before and after (open issue 6).
10. Swollen cell: a 2.4 mm dummy cell in a unit quenched at 25 kPa with the LCD powered (open issue 13).
11. Grain opening: mud and fertiliser soak, then function and insulation check (open issue 12).

## 10. Check report summary

Full tables: `export/check_report.md`. All fourteen checks pass on the build of 2026-11-11 with 21 warnings. A check fails
when a requirement is violated and the violation is not a recorded deviation; recorded deviations stay visible as warnings.
`python3 cad/build.py --selftest` seeded fifteen defects (a prism raised 0.3 mm, an LCD shifted 0.2 mm, a raised battery,
a bar across a camera opening, a 0.3 mm roof pocket, a closed void, a cavity with a 1 mm exit, a lip 0.4 mm too low, a hook
cut back by 0.6 mm, a missing tab stop, a rib over the PCB outside the keep-outs, a shortened post, the key notch of the
first rev C model, a seating ledge 0.3 mm too small) and every one was caught.

| # | Check | Result | Numbers |
|---|---|---|---|
| 1 | Interference, all 903 pairs of 43 solids | pass | 160 pairs with overlapping boxes tested by boolean common (limit 0.01 mm3): no interference; 61 intended zero-volume contacts; no modelling overlap |
| 2 | Clearances | pass, 2 warnings | 61 key gaps and 12 PCB parts; the only gaps below the 0.25 rule are the two spigot fits, 0.075 by specification (D19) |
| 3 | Field of view | pass, 4 warnings | field frusta from the prism exit face to 200 mm (chief rays and full pupil, both cameras) have zero intersection with tub, base, seal adhesive and the other camera's parts. Chief rays clear to 31.2 deg left and right, 21.9 up, 18.7 down (required 26 / 17.6 / 8). The full 0.38 mm pupil is clear to 25.65 deg horizontally (prism exit face), 18.6 up, 15.35 down |
| 4 | Fold ray trace | pass, 9 warnings | chief rays of all nine field points pass prism and opening. Pupil transmission 97.7 % at the horizontal field edges (prism exit face, clipped by 0.013 mm), 100 % elsewhere. Bundle margin to the opening: sides 0.378, sill 0.397, top 0.054 mm. Sensitivity table in section 5 |
| 5 | Wall thickness | pass, 1 warning | tub minimum 0.500 mm (feet of the hood skirts; D04 strip 0.525), base plate 0.800 mm, cradle 0.389 mm (hook nose, an edge). Eight recorded regions below 0.8 mm, none unrecorded |
| 6 | Trapped volume | pass | no closed void, no cavity without a 2 mm exit (voxel 0.1 / 0.087 / 0.2 mm); six small open recesses listed in the tub, none in base plate or cradle |
| 7 | Cradle: pins, key, hold-down, insertion | pass, 4 warnings | seven pin positions on pad centres, 0.565 mm clear in the slots, 5.82 mm high; seats at 0 deg only; retention without friction 6.0 x in the governing position, 8.8 x centred, 3.4 x with 0.3 mm less overlap (required 3 x); strain at full deflection 1.81 % / 1.78 % by the beam formula, 2.05 % peak by FE (limit 2.5 %); both stops verified on the solids; insertion 1.42 mm, about 11 N; release 1.37 to 1.86 mm, 9 to 12 N; 19 posed tilts without interference; finger access 42 of 42 rays on each side; drained floor measured |
| 8 | Mass, centre of gravity | pass | marker 11.25 g, CoG (0.05, -1.40, 3.75), 8.1 mm inside the foot triangle; cradle assembly 31.2 g (densities stated in the report) |
| 9 | Quoting data, export integrity | pass | boxes and volumes as in section 2; print files rest on z = 0 with 0.005 mm facet sag; all 43 STEP files re-imported and all 43 STL files re-read: volumes match, meshes closed |
| 10 | Support posts | pass | eight posts 1.6 x 1.6 mm on the YAML keep-out squares, solid from PCB top to roof, 0.45 mm or more from listed parts, 0.25 mm from the LCD glass; spigots under posts E; seat area 17.9 mm2 (post E+ beside its slot: 0.96 mm2) |
| 11 | `design/check_layout.py` | pass | "OK: no layout errors" (PCB edge to ledge 0.25, visor face outboard of each recess 1.05) |
| 12 | Tub keep-out contract | pass, 1 warning | proven **below z 4.35 only**: tub INTERSECT layout space (PCB outline x z 1.80 to 4.35, minus the eight post squares, minus the hood zones above z 2.75) = 0.000000 mm3; hoods span +-2.80 of +-2.85 from y 13.75 (zone from 13.7), skirts 1.20 mm above the PCB (parts to 0.95 allowed); lowest tub feature elsewhere 2.95 mm above the PCB (glass rib). Above z 4.35 the tub overhangs the board outside the keep-outs (D22) |
| 13 | Seal continuity | pass | air-solid test: outside and cavity are separate bodies of air (cavity 4265 mm3 including the cell under the cover glass); perimeter bead is one closed ring, narrowest joint 0.40 mm; adhesive-sheet lands 1.06 to 1.37 mm; one known closed pocket of 0.39 mm3 (round locating hole under post E-) |
| 14 | Assembly paths | pass | LCD tilt-in: 13 poses, 0.28 mm to the ledge; PCB / base unit: straight descent at 10 heights with +-0.1 mm lateral error and hinged close at 14 angles, no interference (smallest gaps 0.15 mm between cameras / prisms and the tub, 0.05 mm between the board and the tub just before it seats) |

How check 12 reads the contract: "touches or overhangs the PCB top side" is evaluated up to the free height
`pcb.max_top_height_under_lcd` = 2.55 mm above the PCB top (z 4.35), the height the layout may use anywhere on the board.
Below it, tub material exists over the PCB only inside the post-foot squares and inside the hood zones from 0.95 mm upward.
Above it the roof structure begins (glass ribs at z 4.75, thick roof at z 5.55, nose pad 6.5, vent pad 6.5); that part
of the contract is not in the YAML yet (D22, `PROPOSED_PARAM_CHANGES.md` B1).

## 11. Deviations from the specification

Full text with numbers: `export/check_report.md` (end) and `cad/deviations.py`.

| ID | Status | Requirement | What is modelled | Why |
|---|---|---|---|---|
| D04 | accepted (rev C) | every wall 0.8 mm | 0.525 mm behind each window recess in front of the cube, 4.0 x 0.4 mm | 1.325 mm available for recess 0.55 + wall 0.8 + clearance 0.25; the bonded window backs it |
| D05 | recorded | opening bevelled toward the inside | straight opening +-2.0, as wide as the bay | the light bundle is narrower inside the wall than at the aperture; a wider bay would leave the 2.85 mm keep-out |
| D06 | recorded | glue channel if possible | none | any relief in the 0.65 mm ledge or the 0.8 mm visor wall goes below the wall minimum; the radial groove is the reservoir |
| D07 | recorded | 1.2 mm locating pins or keys between base and tub | none; plain base edge; base registered to the PCB in the lamination jig, PCB to the tub by the spigots | a key under the visor wall cuts the seal land (the first rev C lugs left a through path into the camera bays) |
| D09 | recorded | nose groove from the aperture edge | from the cover-glass recess edge | the aperture edge is under the glass |
| D11 | accepted (rev C) | LCD drops in from below | tilted in: rear edge first at 6 deg, shifted 0.55 forward, 0.28 mm to the ledge (step 9, check 14) | rear glass corners are outside the ledge radius; flat and shifted 0.25 it has 0.10 mm and cannot go further because of posts E |
| D13 | accepted (rev C) | light-tight hood | slit of 0.25 to 0.37 mm above the cube at the rear, closed by a bead of black adhesive cured on the tub before the join (step 8) | the hood rear wall cannot pass the cube; a wet bead closed blind would squeeze out beside the prism |
| D14 | recorded | top radius and bottom chamfer all round; lower cavity clipped at the visor face | radius and chamfer on the arc only; wall ends cut on a radial plane; a 2 mm pocket under each end of the visor wall, outside the seal ring | windows are flush with the top; the clipped cavity would leave feather edges |
| D18 | recorded | four 3 mm feet pockets | pockets dia 8.4 x 1.0 for dia 8 x 3 bumpers with a blind core dia 5 behind each; PCB held by four screws | "3 mm feet" read as 3 mm high; the corners would be 13 mm solid |
| D19 | **open** | PCB located by two spigots (YAML) | as specified: 0.075 mm radial fit, tip chamfer 0.15 | below the print tolerance: spigots must be gauged; they sit inboard of the cameras and only locate until the adhesives cure (B3) |
| D20 | recorded | cradle body 60 x 60 x 14 | body 60 x 60 x 14, lip to z 9.45, latch to z 11.63 (22.6 mm overall), body from y -36 to 24 | hook above the marker top on an 11.65 mm cantilever; room for latch well, tab stop and USB-C behind the marker |
| D21 | recorded | marker rests on its feet, pins at working height | marker floats up to 0.25 mm against lip and hook; pins 5.82 to 6.07 mm | a retaining face with drop-in clearance cannot preload; inside the pin stroke |
| D22 | **open** | `tub_keepouts` is the complete contract | complete below z 4.35; above it ribs, thick roof and pads hang over the PCB outside the keep-outs | `check_layout.py` allows parts to z 6.7 outside the LCD; a free height must be added |
| D23 | recorded | tub side wall from z = 0 | wall ends 0.25 above the base plane (rim relief); tub 7.35 tall, marker 7.60 | the feet stood 0.10 proud of a rim positioned by a +-0.16 to 0.29 mm stack |
| D24 | recorded | vent pad raised 0.2 mm, plain top face | pad 0.3 mm and out to the side wall; two drain grooves 0.6 x 0.3 through the vent hole | the vent well ponds water and a sole can seal it |
| D25 | recorded | marker rests on the nest floor | on a front strip and two pads; the rest of the floor is a drained basin; rim round the pin slot, dam and drain for the latch well | a flat floor drained only through the pin slot onto the cradle PCB |
| D26 | recorded | closed LCD adhesive frame | 0.8 mm vent channel to the rear right corner | the cell under the cover glass was sealed and not served by the vent |
| D27 | recorded | balls potted in through holes | plus backfill of the sheet holes: the balls bear on the PCB | potting shear alone does not carry a step on a hard floor |
| D28 | recorded | pins at working height on the pad plane z 1.00 | cradle PCB top 5.82 below the copper face of the pads (z 0.965): z -4.855 | the first model had 5.785 mm pins and 5.82 in the text |

Closed by revision C (kept in `cad/deviations.py` as pointers): D01 pad slot, D02 ball seats, D03 baffle ring, D08 vent
position, D10 adhesive-sheet thickness, D12 PCB and window clearances, D15 two-orientation nest, D16 pin holes and
reference plate, D17 missing hold-down.

Geometry decisions of this pass that are not in the YAML: opening without bevel and bay 4.0 wide (hood 5.6 of 5.7
allowed); corner fill between hood and side wall starts at y = 16.79 so that it does not hang over the PCB outside the hood
zone; lip overlap 1.2; finger scallops as sectors with radial ends; pin barrel top assumed 0.285 mm below the nest strip;
latch 24 mm wide with the nest wall open over the width of its well (the marker can sit 0.30 mm back instead of 0.25);
LCD tail modelled with a 1 mm fold radius entering J1 at 1.0 mm above the PCB.

## 12. Open mechanical issues

Numbers marked "review estimate" are plate, strip or ideal-gas estimates from the design review; they were checked for
plausibility but are not computed by this package and none is tested.

1. **The upper edge of the camera field has no tolerance margin.** The +17.6 deg field edge clears the top of the opening
   (the roof underside, z 6.8) by 0.054 mm. Optics 0.2 mm high clip the upper field at 15.0 deg (64 % transmission at the worst
   field point); the fore-aft spigot play alone brings the limit to 17.6 deg; at -10 C the roof comes 0.02 mm lower.
   Curing this needs a thicker puck, a lower optical axis or a smaller required upper field (`PROPOSED_PARAM_CHANGES.md` B2).
2. **Spigot fit (D19).** 0.075 mm radial on printed dia 1.0 spigots is tighter than the print tolerance. Gauge and dress at
   first article; measure the achieved camera position through the windows. The spigots are 8.4 mm apart, the cameras
   20 mm: moving the pair to posts B would cut the fore-aft play at a camera from +-0.179 to +-0.075 mm (B3).
3. **Footstep on the cover glass (review estimate).** 800 N on a 20 mm patch: about 400 MPa in a 1.0 mm crystal simply
   supported on its tape (the EVT mineral crystal breaks at roughly 100 to 200 N); the 0.8 mm roof ledge under the tape is
   overloaded and hands the load to the LCD glass bonded under it, contrary to the stated load path; the posts take almost
   everything else at 45 MPa on 17.9 mm2 of feet (yield 48 MPa), and post E+ seats on two 0.225 mm strips beside its slot.
   Needs a test and a 3-D FE run; likely changes: crystal specified by strength, larger feet for posts E (B12),
   narrower tape ring (B21). Until then the marker is not step-proof on the glass.
4. **Footstep on turf (review estimate).** Inside the ring of posts (r 15 to 20) the PCB / base laminate spans 30 mm
   with only the battery, 0.55 mm of air, the foam and the LCD above it. Under turf pressure it closes that gap at about
   250 to 500 N of footstep, after which battery and LCD carry load, and the board strain under U1 exceeds the usual
   assembly limits. A stiffer base (routed FR-4 or stainless, B13) is the candidate cure.
5. **Hard floor.** With the rim relief (D23) a step on a hard floor is carried by the three balls and then by the base
   plate through PCB and posts; the side wall joins only after another 0.25 mm. The balls now bear on the PCB through
   epoxy (D27), which protects the potting but bends the board locally: the front foot is directly under U8, the rear
   feet under the ends of the battery (review estimate: 36 to 75 N per ball before the base lands). Needs the PCB
   keep-outs of B6 and a push-in test; a hard-floor step requires re-zeroing in any case.
6. **Thermal and moisture bow of the PCB / base laminate (review estimate).** FR-4 on PA12 through a 0.13 mm adhesive
   sheet is a bimetal: between 0.04 and 0.3 mrad/K of tilt at the IMU relative to the plane of the feet, depending on
   how far the adhesive relaxes, against a 0.5 to 1 mrad target; moisture swelling of PA12 acts like a further 10 to
   20 K. Measure laminated coupons and units over -10 to 70 C before deciding (B13). Until then: zero again after a
   large temperature change.
7. **The cradle latch is calculated, not tested.** Retention depends on the modulus (1700 MPa dry; 3 x in the governing
   position down to 848 MPa, at -0.3 mm overlap only down to 1485 MPa), on the pin force (provisional) and on the
   distance front nest wall to hook nose (39.95 mm, a first-article dimension). Strain at full deflection is 2.05 % by FE
   against 2.5 %; 0.2 mm of error on the rib gap is about 0.3 mm of hook travel, so the stop positions are first-article
   dimensions too. Friction (0.3 assumed), creep under the continuous pin load (0.18 mm elastic of 0.85 mm overlap) and
   fatigue are unverified: 3000-cycle test at 23 C and 0 C, 1000 h at 50 C with seven pins, pull test of 12.4 N.
   The root stands on a 1.055 mm skin above the PCB pocket. Small-deflection beam theory is used up to 20 deg of rotation.
8. **Wet docking.** The cradle now drains (D25), but the marker's own pad slot (37 mm3) and grain opening (100 mm3) hold
   water by capillarity, the seven pads share that water and VBUS is live whenever the cradle is plugged in (review
   estimate: 0.1 to 0.6 mA through the film, enough to strip the nickel under an ENIG pad within the hour). Needs hard
   gold pads, VBUS gated by marker detection and firmware that ignores NRST when not docked (B19). The drain outlet
   of the latch well is beside the USB opening.
9. **LCD flex tail and J1.** The tail is modelled with one U-fold of 1 mm radius entering the mouth of J1, which must face
   the rear because the battery is 0.8 mm in front of it. Mating is not demonstrated: check 14 gives the free tail
   length needed at each opening of the join fixture (6.5 mm at 20 deg, 10 mm at 35 deg, 15 mm at 60 deg), and the
   real tail length, the actuator side of J1 and pin 1 are PROVISIONAL. Get the Sharp outline drawing before the
   boards are ordered; if the tail does not reach, J1 must move or change (B16).
10. **Seal** not tested and adhesive not chosen: 0.4 mm land, joint height 0.17 to 0.49 mm, PA12 bonding, sustained
    peel when the vent is blocked (section 9). The fill is proven only as geometry (check 13).
11. **Glass flush with printed faces.** The windows are flush with the visor face and the tub top, the cover glass 0.05 mm
    below flush, all tighter than the print tolerance: some will be proud, at edges that get stepped on (B14).
12. **Grain opening** is an open cup 1.0 mm deep on the underside with sixteen LEDs and the photodiode exposed, split by
    the baffle into four compartments with 0.25 mm crevices at the photodiode corners; mud cannot be brushed out and dew
    reaches a 470 kohm node. Potting it clear or conformal coating is a system decision (B18).
13. **Battery**: retention and leads not designed (adhesive thickness comes out of the 0.15 mm swell margin, which is also
    claimed by PCB deflection and thermal bow); pads, lead route and maximum delivered thickness are not in the YAML (B15).
14. **Ball potting.** The epoxy below the ball's equator is shadowed: a dual-cure grade or a two-part epoxy is needed.
    Stage 2 must not flood the sheet (0.35 microlitre per hole). Push-in strength untested.
15. **Light leaks**: the hood gasket closes the slit above the cube; the 0.265 mm gaps beside each cube and 0.25 mm in
    front of it stay open (a labyrinth, not a seal). Translucency of 0.8 mm black PA12 is untested. Dark-frame test.
16. **Vent**: part data unverified; the printed dia 1.0 hole may need drilling; whether the grooves keep a sole from
    pumping the membrane is untested.
17. **Prism slightly undersized for the assumed pupil**: 2.3 % of the pupil is clipped at the horizontal field edge by the
    2.0 mm exit face. Confirm with the OVM7692 lens data.
18. **Thin wall behind the window recess (D04, accepted)**, 0.525 mm over 1.6 mm2 per camera, and window lands of 0.4 to 0.8 mm.
19. **Keep-out contract above z 4.35 (D22)** and passives: passives are not in the YAML, so no check can see a clash with them.
20. **Vapor smoothing of 0.8 mm walls**: bureau confirmation and coupons.
21. **Cradle details**: pin diameters, barrel length and stroke are provisional (the barrel top is assumed at z -0.385);
    the marker floats 0.25 mm (D21); the thumb tab and its rest are directly above the USB plug; no cable strain relief.
22. **Purchased-part envelopes** are simple solids; every PROVISIONAL item in section 2 must be checked against a
    manufacturer drawing before parts are ordered.
