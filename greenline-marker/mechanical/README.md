# GreenLine GL-1 mechanical design package (parameters rev B-EVT1, drawings rev A-EVT1)

**Status: PROVISIONAL, not released. Nothing in this folder has been built, printed or measured.**
Every number comes from the CAD model, which is driven by `../design/master_params.yaml` (rev B). Where the
model could not meet the written specification the difference is recorded as a numbered deviation (D01 to D18)
and is listed in this file, in `export/check_report.md` and, when a shared number would have to change, in
`PROPOSED_PARAM_CHANGES.md`. `master_params.yaml` was not edited.

The package is for two readers: a US 3D-printing bureau (tub, base plate, cradle) and the person who assembles the
first units. Read "Open mechanical issues" before ordering anything: the cradle cannot hold the marker down against
its own spring pins, and the camera openings have almost no margin for print tolerance.

![assembled marker](renders/GL1_render_a_front_top.png)

## 1. One command

```
cd greenline-marker/mechanical
python3 cad/build.py              # about 2 minutes; exits non-zero on any failed check, drawing or render
python3 cad/build.py --selftest   # seeds ten defects and confirms each check catches its defect (about 2 minutes)
```

`build.py` regenerates the solids, STEP and STL files, the resolved parameters, the check report, the drawings
(PDF, SVG, DXF, PNG previews) and the renders. Options: `--no-export`, `--no-drawings`, `--no-renders`, `--summary`.
It needs python3 with cadquery 2.8, numpy, scipy, shapely, matplotlib, pyyaml and ezdxf; `pdftoppm` for the previews;
node with Playwright (headless Chromium) and three.js 0.160 for the renders (`npm install three@0.160.0` in
`tools/render` if three.js is not found; `node_modules` is not committed).

| Path | Content |
|---|---|
| `cad/params.py` | loads the YAML, holds the mechanical-only choices (`MECH`), derives every dependent dimension once |
| `cad/parts.py` | one function per part, each returns a CadQuery solid in the assembly frame |
| `cad/assembly.py` | named, coloured parts; allow-lists of intended contacts; STEP / STL export |
| `cad/checks.py` | the eleven checks; `cad/optics.py` the exact ray trace; `cad/geom.py` sections, projections, ray casting |
| `cad/deviations.py` | the recorded deviations (text is built from the parameters) |
| `cad/drawings.py`, `cad/drawlib.py` | dimensioned drawings from projections and true sections of the solids |
| `cad/renders.py`, `tools/render/render.js` | renders of the exported STL meshes |
| `cad/selftest.py` | negative tests of the checks |
| `export/step/` | `GL1_assembly.step` (37 named parts, marker seated in the cradle), `GL1_marker_only.step`, one STEP per part |
| `export/stl/print/` | `tub_print.stl` (roof down), `base_plate_print.stl`, `cradle_print.stl`: the files to send to the bureau |
| `export/stl/parts/` | every part in the assembly frame (used for the renders and for the mesh checks) |
| `export/params_resolved.json` | YAML + mechanical-only + derived numbers, and the support-post rectangles |
| `export/check_report.md`, `.json` | full check results with every table; `export/selftest_report.json` |
| `drawings/` | GL1-001, -002, -010, -011, -020 as PDF and SVG; `dxf/` 2D profiles; `preview/` PNG of every sheet |
| `renders/` | six PNG renders |
| `PROPOSED_PARAM_CHANGES.md` | changes proposed to the shared YAML and to the spec text |

Frame (same as the YAML): origin at the puck centre on the base plane (the plane that rests on the turf), +x right,
+y forward toward the hole (the flat visor face), +z up, millimetres.

## 2. Part list

### Printed parts

| Drawing | Part | Material, process, finish | Box (mm) | Volume | Mass |
|---|---|---|---|---|---|
| GL1-010 | Tub (top shell) | HP 3D High Reusability PA 12, Multi Jet Fusion, dyed black, chemical vapor smoothing | 46.0 x 41.4 x 7.6 | 2.495 cm3 | 2.52 g |
| GL1-011 | Base plate | same | 43.5 x 40.0 x 1.0 | 1.276 cm3 | 1.29 g |
| GL1-020 | Cradle body | PA12 MJF (any colour, smoothing optional) or SLA resin | 60.0 x 60.0 x 14.0 | 28.66 cm3 | 29.0 g |

Surface areas for quoting: tub 50.3 cm2, base plate 28.4 cm2, cradle 135.4 cm2. The STL files are watertight single
shells (tub 4,828 triangles, base 2,620, cradle 3,820; 0.02 mm chord tolerance).

### Purchased and custom parts (mechanical bill of materials)

Status is copied from `../design/DESIGN_SPEC.md` (VERIFIED or PROVISIONAL as defined there). Where the spec gives no
status the item is PROVISIONAL here, with what `../docs/research/bom-verification-opto.md` reports in brackets. Every
envelope in the CAD is a simple solid for fit checks, not a manufacturer model.

| # | Item | Qty | Part / source | Envelope modelled (mm) | Status |
|---|---|---|---|---|---|
| 1 | Camera cube | 2 | OmniVision OVM7692-RYAA, DigiKey 884-1027-1-ND | 3.47 x 2.95 x 2.76 | Dimensions VERIFIED (product brief via search); ball map, pitch, image orientation PROVISIONAL |
| 2 | Fold prism | 2 | Edmund Optics 32-526, 2.00 mm legs, N-BK7, aluminised hypotenuse | 2 x 2 x 2 right-angle | VERIFIED (dimensions, coating, $105 at 1-5); production source to be quoted |
| 3 | Memory LCD | 1 | Sharp LS013B7DH03, DigiKey 425-2903-ND | glass 26.6 x 30.3 x 0.75 | Outline VERIFIED (Sharp brochure via search); active-area offset, flex tail geometry and pin-1 side PROVISIONAL |
| 4 | Battery | 1 | PowerStream GM201030-PCB, 2 x 10 x 30 mm cell with protection board | 34 x 10 x 2.0 (+0.4 swell) | Listing VERIFIED; protection-board length, capacity and certificates PROVISIONAL |
| 5 | Cover glass | 1 | Flat mineral-glass watch crystal 28.0 x 1.0 (EVT); chemically strengthened glass with black border for production | dia 28.0 x 1.0 | PROVISIONAL (research: Esslinger flat round crystal, partly verified, diameter tolerance not stated) |
| 6 | Cover-glass tape ring | 1 | 3M VHB 5907, 0.20 mm, die-cut dia 28 / dia 23 (`dxf/GL1-030`) | 0.2 thick | PROVISIONAL (research: thickness confirmed; converter not found) |
| 7 | Visor window | 2 | EVT: 0.5 mm clear cast acrylic or cover glass, cut 4.3 x 3.4; production: AR-coated borosilicate or sapphire, custom | 4.3 x 3.4 x 0.5 | PROVISIONAL (custom part, no source) |
| 8 | Vent | 1 | W. L. Gore VE80205 adhesive ePTFE vent, 5.0 outer, 2.0 vent area, 0.26 thick | dia 5.0 x 0.26 | PROVISIONAL (YAML basis: provisional; water-entry pressure and US source not found) |
| 9 | Ball feet | 3 | 1.0 mm stainless balls | dia 1.0 | PROVISIONAL (research: McMaster 1598K16 inferred, 440C grade 25) |
| 10 | LCD adhesive frame | 1 | 0.15 mm PSA frame 26.6 x 30.3 with a dia 23 window (`dxf/GL1-030`), for example 3M VHB 5906 | 0.15 thick | PROVISIONAL |
| 11 | PCB-to-base adhesive sheet | 1 | 0.13 mm transfer adhesive, die-cut with the grain opening and the pad slot (`dxf/GL1-030`), for example 3M 468MP | 0.13 thick | PROVISIONAL (see section 6: zero thickness in the YAML) |
| 12 | Foam pad | 1 | 0.3 mm PU foam, 26.6 x 10, adhesive one side | 0.3 thick | PROVISIONAL |
| 13 | Perimeter seal adhesive | - | dispensed liquid adhesive, bead about 0.2 x 0.4 mm plus the 0.25 mm radial gap | 0.2 ring | PROVISIONAL: adhesive not selected (must bond vapor-smoothed PA12; primer or plasma likely) |
| 14 | Window and prism adhesive | - | light-cure acrylic (windows, cured through the window); UV-cure adhesive at the four prism corners | - | PROVISIONAL (class named in the research note; no part number confirmed) |
| 15 | Main PCB assembly | 1 | 4-layer 0.8 mm, D outline R 21.2, flat y 17.3 (electrical package) | board + the 13 YAML part boxes | Part boxes from the YAML; passives not modelled |
| 16 | Cradle spring pin | 7 | Mill-Max 0914-series long stroke (0914-0-15-20-77-14-11-0) | plunger dia 1.07, body dia 1.83 | PROVISIONAL (overall 8.3, working height 5.82, 60 gf from the research note; diameters not confirmed) |
| 17 | Cradle USB-C receptacle | 1 | GCT USB4105-GF-A, DigiKey 2073-USB4105-GF-ACT-ND | 8.94 x 7.35 x 3.26 | Part number: research note says verified; not named in the spec. Envelope PROVISIONAL |
| 18 | Cradle reference plate (GL1-021) | 1 | 304 stainless 1.5 mm, laser cut to `dxf/GL1-021_cradle_plate.dxf`, deburred, flat within 0.05 | 46.0 x 41.4 x 1.5 | Custom; 0.54 mm webs between the seven dia 2.0 holes to be confirmed by the cutter |
| 19 | Cradle PCB | 1 | 2-layer 1.6 mm, 22 x 30 (electrical package) | 22 x 30 x 1.6 | Outline is a mechanical proposal |
| 20 | Cradle feet | 4 | self-adhesive bumpers dia 8 x 3 | dia 8 x 3 | PROVISIONAL (generic) |
| 21 | Cradle PCB screws | 4 | M2 x 5 thread-forming screws for plastic | not modelled | PROVISIONAL (generic) |

Estimated mass (typical densities, envelope solids, no solder or passives): marker 11.4 g, centre of gravity at
(0.05, -1.36, 3.71) mm, 8.1 mm inside the triangle of the ball feet; cradle assembly 52.7 g.

## 3. What the parts look like

| | |
|---|---|
| ![underside](renders/GL1_render_b_underside.png) | ![exploded](renders/GL1_render_c_exploded.png) |
| ![cut-away](renders/GL1_render_d_cutaway.png) | ![in cradle](renders/GL1_render_e_in_cradle.png) |

Renders (all 2000 x 1500 except the exploded view, 1800 x 2400). The tub is drawn dark grey so that its shape reads; the real part is black.

- `GL1_render_a_front_top.png`: assembled marker from the front and above: visor windows, cover glass, nose groove, vent hole.
- `GL1_render_b_underside.png`: from below: grain opening with baffle ring, LED pairs and photodiode, pad slot with the seven pads, ball feet, key lugs.
- `GL1_render_c_exploded.png`: every marker part separated along z and labelled.
- `GL1_render_d_cutaway.png`: boolean cut on x = 0 behind y = 13.0 and on x = 10.2 through camera R in front of it, labelled.
- `GL1_render_e_in_cradle.png`: marker in the cradle from the rear right, USB-C receptacle visible.
- `GL1_render_f_cradle_section.png`: marker in the cradle cut on x = 0: centre spring pin on its pad, ball foot on the plate.

Drawings (A3, PDF and SVG; PNG previews in `drawings/preview/`; title block with part, material, process, general tolerance,
revision A-EVT1 and "PROVISIONAL - not released"):

- `GL1-001_assembly_outline`: top view, view on the visor face and side view with overall size (dia 46.0, 41.4, 7.6), optical axis height 5.61, window positions and sizes, ball feet.
- `GL1-002_sections` sheet 1: section A-A on x = 0 with every part labelled; detail C with the full z stack, each level and each layer thickness.
- `GL1-002_sections` sheet 2: section B-B on x = 10.2 through camera R; detail D with the camera stack, the wall build-up in y and the traced chief rays.
- `GL1-010_tub` sheet 1: view into the cavity with posts, hoods, ribs, ledge; detail E of wall, ledge and roof; post table.
- `GL1-010_tub` sheet 2: top view, sections A-A and B-B of the tub alone, detail G of the camera opening in plan, view on the visor face.
- `GL1-011_base_plate`: top view with every hole dimensioned, detail H of a ball seat, feature table.
- `GL1-020_cradle` sheet 1: top view, section D-D with plate, PCB, receptacle and pin, view from below.
- `GL1-020_cradle` sheet 2: reference plate GL1-021, section E-E through the pin row, plan of the 0 and 180 degree positions, cradle PCB table.
- `drawings/dxf/`: tub, base plate and cradle section profiles on named layers; the laser-cut reference plate; the three adhesive die-cuts; sections A-A and B-B.

## 4. Print orientation and notes for the bureau

1. **Process.** HP Multi Jet Fusion, PA 12, dyed black, chemical vapor smoothing for tub and base plate. The cradle may be MJF or SLA, unsmoothed.
2. **Orientation.** `export/stl/print/` holds the parts in the proposed build orientation (z up): the tub roof-down so that the
   cosmetic top face and the cover-glass recess face the bed and the cavity is open upward for depowdering; base plate and cradle
   as modelled. The bureau may tilt parts for warp control. The functional planes of the tub must stay parallel to each other
   whatever the orientation: LCD bonding plane z 5.55, recess floor z 6.35, seal face z 1.2 and the eight post feet at z 1.8.
3. **Walls.** Designed to 0.8 mm minimum (side wall 1.0). The wall audit (check 5) lists every place below 0.8 mm: the 0.525 mm
   strip behind each window recess (D04), the 0.5 mm aperture land with its 30 degree bevel (D05), the feet of two chamfered
   edges (0.70 and 0.68 mm) and the three conical ball seats, which run out to a pin-hole (D02). Please confirm that 0.8 mm
   walls survive your vapor smoothing: the research note reports stated minimums of 0.76 mm (Protolabs) to 1.0 mm (Xometry), unverified.
4. **Powder.** No closed void and no cavity without a 2 mm escape path (check 6). Open narrow places that need attention: the
   two camera bays and visor openings, the gaps between posts C and the side wall (about 1.4 mm wide), the dia 1.0 vent hole
   (it may fuse shut: clear it with a 1.0 mm drill), the three ball-seat cones, the cradle pin slot (2.33 mm wide, through).
5. **Flatness.** The base plate is a 1.0 mm disc 43.5 mm across and will not come out flat. It is laminated to the rigid PCB;
   request best flatness and report it. The cradle is not a datum: the stainless plate is.
6. **Post-processing by us, not the bureau.** Ball seats (section 7, step 2), four dia 1.6 x 3 pilot holes in the cradle at the printed spot marks.
7. **Tolerance.** Quoted general tolerance +-0.3 mm or +-0.3 %. Every drop-in fit has 0.25 mm nominal clearance except the three listed in section 5.

## 5. Tolerances and fits

Nominal values from check 2 (all computed on the solids). "Rule" is the 0.25 mm drop-in clearance of the specification.

| Fit | Nominal gap (mm) | Against the rule | Comment |
|---|---|---|---|
| Base plate in the tub, radial (and key lugs in their notches) | 0.25 | meets | gap is filled with seal adhesive |
| Base plate top to tub seal face | 0.20 (0.33 real) | bead | liquid bead; absorbs post-height and flatness errors |
| PCB edge to the seating ledge, radial | 0.15 | **below (D12)** | also the only thing that locates the PCB, and so the cameras, in the tub: see open issue 3 |
| PCB flat edge to visor wall | 0.30 | meets | |
| LCD glass in its pocket (ribs, posts E, hood rear walls) | 0.25 | meets | |
| LCD glass past the seating ledge during assembly | 0.12, glass biased 0.25 forward | **below (D11)** | rear glass corners are at r 21.43, ledge at r 21.35 |
| LCD glass to roof bonding plane | 0.15 | adhesive frame | |
| Cover glass in its recess, radial | 0.25 | meets | top face 0.05 below flush |
| Visor window in its recess, per side | 0.05 | **below (D12)** | cut windows to the measured recess |
| Camera cube to hood (sides, top, front pad) | 0.25 | meets | |
| Prism to roof | 0.19 | YAML stack value | |
| Prism hypotenuse to hood rear wall | 0.26 | meets | 0.18 before the wall edge was chamfered |
| LCD glass to camera cube | 0.63 | meets | |
| Battery to foam pad | 0.55 | 0.40 swell + 0.15 | battery to LCD glass 0.85 |
| Photodiode to baffle ring | 0.25 | meets | LEDs 0.75 from the nearest plastic |
| Support posts on the PCB | 0 (contact) | datum | posts set the PCB height; nearest listed part 0.45 mm (U1 to posts E) |
| Ball feet below the base plane | 0.10 | - | cannot be held by printing: set on a gauge plate (D02) |
| Marker in the cradle nest; plate in its seat; cradle PCB in its pocket | 0.25 | meets | |
| Spring-pin plunger in the plate hole / in the base slot | 0.465 / 0.565 | meets | pin diameters PROVISIONAL |
| Spring-pin body in the printed slot | 0.25 | meets | the 2.0 mm slot first modelled left 0.085 |
| Light bundle to the visor opening (sides / sill / top) | 0.028 / 0.019 / 0.054 | **no margin** | see open issue 2 |

Thermal note (estimate): PA12 expands about 100 ppm/K against about 14 ppm/K for FR-4. Over 30 K the PCB-to-ledge gap changes
by about 0.06 mm; nothing closes, but every bond between PCB, base and tub is sheared by that amount. Not analysed further.

## 6. The 0.13 mm adhesive sheet under the PCB

The YAML puts the PCB bottom on the base top (`pcb.z_bottom` = `base_plate.thickness` = 1.0), so the die-cut adhesive sheet
between them has zero thickness in the shared numbers. The model keeps the YAML heights and draws the sheet at its true
0.13 mm, which makes it overlap the PCB by exactly its own volume (156.05 mm3, the one allow-listed overlap in check 1).

In the real stack the eight posts hold the PCB top at tub z = 1.80. A 0.13 mm sheet therefore pushes the base plate
0.13 mm down relative to the tub, and the stack absorbs it in the seal: the liquid bead between the base land and the tub seal
face becomes 0.33 mm instead of 0.20 mm. Consequences: the tub rim stands 0.13 mm above the base plane, the overall height is
7.73 mm, the optical axis is 5.74 mm and the contact pads 1.13 mm above the base plane. The cradle PCB is placed for 1.13.
Nothing inside the tub changes. `PROPOSED_PARAM_CHANGES.md` item 3 offers two ways to carry this in the YAML (deviation D10).

## 7. Assembly sequence

Adhesive types are classes, not released part numbers; cure times are to be taken from the chosen product's data sheet.
Work on the tub upside-down in a nest that supports the roof ring unless a step says otherwise.

1. **Incoming inspection.** Measure on the tub: z of the bonding plane, recess floor, seal face and post feet (one plane each,
   +-0.1), recess dia 28.5, window recesses, ledge radius 21.35. Check that the vent hole and both camera openings are clear
   of powder. Clean all printed parts with isopropanol and dry them.
2. **Ball feet.** Finish the three seats in the base plate (90 degree spot drill to depth), or place the base plate on a gauge
   plate with 0.10 mm shims under it, drop the three 1.0 mm balls into the cones so that they rest on the gauge plate, and pot
   them from above through the pin-holes with low-viscosity epoxy. Cure fully. Check the protrusion: 0.10 +-0.02 mm, all three.
3. **Surface preparation.** Prime or plasma-treat every PA12 bonding face according to the adhesive maker: recess floor, LCD
   bonding plane, seal face and visor-wall underside, window recesses, vent pad, base-plate land and top face.
4. **Cover glass.** Tub top-up on a mandrel that supports the roof ledge from inside. Apply the VHB 5907 ring to the recess
   floor, remove the liner, centre the crystal (0.25 mm radial gap) and press with the load the tape maker specifies. Allow the
   stated dwell (typically 72 h to full strength) before the leak test.
5. **Visor windows.** From outside, a thin bead of light-cure acrylic on the recess side lands (0.55 mm), the bottom shelf
   (0.4 mm) and the roof edge (0.8 mm). Set the window flush with the visor face, check that no adhesive has entered the
   opening, cure through the window.
6. **Vent.** Tub upside-down. Apply the vent disc to the pad inside the roof, centred on the 1.0 mm hole; press evenly.
7. **LCD.** Apply the 0.15 mm adhesive frame to the bonding plane (liner on). Offer the LCD glass face-down, biased 0.25 mm
   toward the visor so that its rear corners pass the seating ledge (D11), lower it, slide it back against the rear ribs,
   remove the liner and press it onto the frame around the aperture. Leave the flex tail standing. Stick the foam pad to the
   underside of the glass over the battery zone.
8. **PCB sub-assembly** (outside the tub). Cameras are soldered. Bond each prism on its cube with UV adhesive at the four
   corners only (air gap over the lens), exit face toward +y at y = 16.6, in a jig referenced to the PCB edge; cure. Fix the
   cell to the PCB with a transfer adhesive of 0.05 mm or less and connect it.
9. **Join.** Hold the PCB component-side down over the tub, make the one U-fold in the LCD tail and latch it into J1
   (top contact). Lower the PCB through the ledge ring (0.15 mm radial) until it rests on the eight posts. Check through the
   visor windows that both prisms sit centred in their openings. This is the step that sets the optical margins of open issue 2.
10. **Base plate.** Laminate the 0.13 mm adhesive sheet to the base-plate top (openings aligned), remove the liner. Dispense
    the seal adhesive as a continuous bead on the land of the base (r 21.35 to 21.75 on the arc, the front strip under the
    visor wall), with extra in the two key notches and at the two front corners. Lower the base onto the PCB with the key
    notches on the tub lugs. Press on the base over the post positions with a flat fixture until the sheet has wetted the
    PCB; the bead must squeeze into the 0.25 mm radial gap all round. Wipe the squeeze-out at the rim and at the visor.
11. **Cure** the seal adhesive under light pressure for the full time on its data sheet. Do not move the unit before handling strength.
12. **Leak test** with the vent hole occluded in the fixture (pressure decay). Then functional test.
13. **Tilt calibration** only after full cure: on the reference plate, at 0 and 180 degrees. See open issue 1 before relying on the cradle for this.

Cradle: bond the stainless plate into its seat with a thin epoxy film on three pads (the plate top is the tilt datum; check
flatness after cure); drill the four dia 1.6 x 3 pilots at the spot marks; solder the seven pins into the cradle PCB square to
the board (use the plate as a drilling and soldering jig: the pins must pass its seven holes); screw the PCB against the pocket
ceiling with four M2 thread-forming screws; fit the four bumpers.

## 8. Sealing concept and what must be tested

The marker is bonded, with no O-ring. There are four seal lines and one vent:

| Seal | Geometry | Concern |
|---|---|---|
| Cover glass | VHB 5907 ring dia 28 / 23 (2.5 mm wide) on the recess floor | foam tape on vapor-smoothed PA12: primer, dwell |
| Visor windows (2) | light-cure adhesive on lands of 0.55 mm (sides), 0.4 mm (bottom) and 0.8 mm (top); 0.05 mm bond line behind the window | very narrow lands; adhesive must not creep into the 3.3 x 2.2 opening |
| Base perimeter | liquid bead 0.2 mm (0.33 real) on a 0.4 mm land under the tub ledge, continued under the visor wall (0.65 mm overlap); the 0.25 x 1.0 mm radial gap is filled as well | no glue channel is possible (D06); the two key lugs interrupt the front land and the two front corners have open notches about 2 mm wide that the adhesive must bridge (D07, D14) |
| PCB underside | the 0.13 mm adhesive sheet closes the grain opening and the pad slot around the wetted PCB areas; it also closes the three ball-seat pin-holes | PCB vias must be tented and plugged (spec); the sheet is the only barrier at the pad slot |
| Vent | Gore VE80205 on a flat pad inside the roof, 1.0 mm hole to the top face | water-entry pressure not confirmed |

Tests required before any water claim (loads from `../docs/research/enclosure-manufacturing.md`, itself unverified):

1. Pressure-decay leak test of every unit with the vent occluded.
2. 25 kPa inward (hot unit into cold water at 1 m) and 40 kPa outward (blocked vent, altitude plus heat) on sealed samples.
3. Dunk test including the hot-unit-into-cold-water case on the first units; vent water-entry pressure of at least 50 kPa.
4. Lap-shear and peel coupons of each adhesive on vapor-smoothed black PA12, with and without primer, before and after
   thermal cycling (-10 to 70 C), UV and sunscreen / fertiliser exposure.
5. Light-leak coupon: black MJF PA12 at 0.8 mm in direct sun, and the hood slit above the cube (D13).
6. Footstep: 800 N on the cover glass and on the roof, with the LCD powered. Not analysed (open issue 8).

## 9. Check report summary

Full tables: `export/check_report.md`. All eleven checks pass on the build of 2026-11-11 with 21 warnings. A check fails when a
requirement is violated and the violation is not a recorded deviation; recorded deviations stay visible as warnings.
`python3 cad/build.py --selftest` seeded ten defects (a prism raised 0.3 mm, an LCD shifted 0.2 mm, a bar across a camera
opening, a 0.3 mm roof pocket, a closed void, a cavity with a 1 mm exit, a hole under a pin, a shortened post and others)
and every one was caught.

| # | Check | Result | Numbers |
|---|---|---|---|
| 1 | Interference, all 666 pairs of 37 solids | pass | 121 pairs with overlapping boxes tested by boolean common (limit 0.01 mm3): no unintended interference; 41 intended zero-volume contacts; one allow-listed modelling overlap (PCB / adhesive sheet, 156.05 mm3, section 6) |
| 2 | Clearances | pass, 3 warnings | 45 key gaps and 12 PCB parts; below the 0.25 rule and recorded: PCB to ledge 0.15, window to recess 0.05 per side (both D12) |
| 3 | Field of view | pass, 4 warnings | field frusta from the prism exit face to 200 mm (chief rays and full pupil, both cameras) have zero intersection with tub, base, seal bead and the other camera's parts. Chief rays clear to 29.5 deg left and right, 21.9 up, 18.7 down (specified 26 / 17.6 / 15). The full 0.38 mm pupil is clear to 25.65 deg horizontally (prism exit face), 18.6 up, 15.35 down |
| 4 | Fold ray trace | pass, 9 warnings | chief rays of all nine field points pass prism and opening. Pupil transmission 97.7 % at the horizontal field edges and 98.6 % at the lower corners (clipped by the prism exit face by 0.013 mm), 100 % elsewhere. Smallest margin of the bundle to the visor opening 0.019 mm (sill), 0.028 (sides), 0.054 (top) |
| 5 | Wall thickness | pass, 3 warnings | tub minimum 0.501 mm, cradle 0.95 mm; base plate runs to zero at the three ball-seat pin-holes (D02; about 2 mm2 each below 0.5 mm). Ten recorded regions below 0.8 mm, none unrecorded |
| 6 | Trapped volume | pass | no closed void, no cavity without a 2 mm exit (voxel 0.1 / 0.1 / 0.2 mm); six small open recesses listed (posts C to wall, pocket corners) |
| 7 | Cradle pins | pass, 2 warnings | 0 deg: seven pins on pad centres at the 5.82 mm working height, 0.565 mm clear in the base slot. 180 deg: every pin on solid base at marker y = 12.4, at least 1.44 mm from any opening, 27.97 mm from the nearest pad. Nest accepts 0 and 180 deg, blocks 90 and 270. Warnings: pin force 4.1 N against 0.11 N weight; 2.27 of 2.29 mm stroke at 180 deg |
| 8 | Mass, centre of gravity | pass | marker 11.4 g, cradle assembly 52.7 g (densities stated in the report) |
| 9 | Quoting data, export integrity | pass | boxes and volumes as in section 2; all 37 STEP files re-imported and all 37 STL files re-read: volumes match, meshes closed |
| 10 | Support posts | pass | eight posts 1.6 x 1.6 mm, solid from PCB top to roof, 0.45 mm or more from listed parts, 0.25 mm from the LCD glass |
| 11 | `design/check_layout.py` | pass | "OK: no layout errors" (LCD corner margin 0.57 mm, ledge 0.80 mm, prism top 6.61, axis 5.61) |

Tolerance sensitivity of the camera openings (check 4, camera R; the optics moved relative to the printed tub):

| Case | Full pupil clear to (deg): left / right / up / down | Worst field-point transmission |
|---|---|---|
| Nominal | 25.6 / 25.6 / 18.6 / 15.4 | 97.4 % |
| PCB shifted 0.15 mm sideways (the PCB-to-ledge gap) | 25.6 / 24.0 / 18.6 / 15.4 | 70 % |
| 0.35 mm sideways (gap plus 0.2 print tolerance) | 25.6 / 20.5 / 18.6 / 15.4 | 12 % |
| Optics 0.2 mm low | 25.6 / 25.6 / 22.1 / 11.7 | 53 % |
| Optics 0.2 mm high | 25.6 / 25.6 / 15.0 / 18.9 | 64 % |

The entrance-pupil position (0.4 mm below the cube top) and diameter (0.38 mm) are assumptions; the lens data is not published.

## 10. Deviations from the specification

Full text with numbers: `export/check_report.md` (end) and `cad/deviations.py`.

| ID | Requirement | What is modelled | Why |
|---|---|---|---|
| D01 | seven dia 2.2 pad holes | one slot 17.44 x 2.2 in base and adhesive sheet | webs would be 0.34 mm |
| D02 | blind seats for 1.0 mm balls, 0.10 mm proud | 90 degree cones that break through as a dia 0.24 pin-hole | ball top is at z 0.90 in a 1.00 plate; printing cannot hold 0.10 mm |
| D03 | baffle ring about dia 5.4, wall 0.6 | dia 5.91 / 7.51, wall 0.8, spokes at 90, 225, 315 deg | photodiode diagonal is 5.41; three equal spokes cannot all miss the LEDs |
| D04 | every wall 0.8 mm | 0.525 mm behind each window recess in front of the cube | 1.325 mm available for recess 0.55 + wall 0.8 + clearance 0.25 |
| D05 | opening bevelled toward the inside | sides only: 0.5 mm land, then 30 deg to +-1.82 | cube below the sill, roof above; land raised from 0.3 to 0.5 after the wall audit |
| D06 | glue channel if possible | none | any relief in the 0.65 mm ledge or the 0.8 mm visor wall goes below the wall minimum; a 0.2 mm chamfer was removed after the audit |
| D07 | 1.2 mm locating pins or keys | two tub lugs under the visor wall in base notches | no room for pins inside the seal line; the lugs interrupt the front seal |
| D08 | vent pad near (17, -3) | at (17.9, -3.0) | the disc would overlap the thick roof ring |
| D09 | nose groove from the aperture edge | from the cover-glass recess edge | the aperture edge is under the glass |
| D10 | adhesive sheet 0.13 mm | true thickness, overlapping the YAML-nominal PCB | zero thickness in the YAML (section 6) |
| D11 | LCD drops in from below | biased insertion with 0.12 mm clearance | rear glass corners are outside the ledge radius |
| D12 | 0.25 mm on every drop-in fit | PCB to ledge 0.15; window to recess 0.05 per side | YAML and task numbers kept |
| D13 | light baffle from visor wall to prism | hood with skirts and front pad; rear wall stops above the cube | LCD glass is 0.63 mm behind the cube; a slit remains at the rear |
| D14 | top radius and bottom chamfer all round; lower cavity clipped at the visor face | radius and chamfer on the arc only; wall ends cut on a radial plane | windows are flush with the top; the clipped cavity would leave feather edges |
| D15 | nest accepts 0 and 180 deg | union of the outline at 0 deg and turned about the nest centre (0, -2.3) | a D with one flat cannot be located at both angles about its own centre; the marker centre moves 4.6 mm |
| D16 | seven 2.0 mm pin holes | one 2.33 mm slot in the print, seven dia 2.0 holes in the steel plate | printed webs would be 0.54 mm; pin body needs 0.25 mm |
| D17 | pins at working height; marker at 180 deg touches no pins | geometry correct, but no hold-down; at 180 deg the pins bear on the base | open issue 1 |
| D18 | four 3 mm feet pockets | pockets dia 8.4 x 1.0 for dia 8 x 3 bumpers; PCB held by four screws | "3 mm feet" read as 3 mm high |

Geometry changed in this pass because a check showed a problem: aperture land 0.3 to 0.5 mm; visor-wall glue chamfer removed;
side-wall ends below the visor cut on a radial plane (full 1.0 mm end face instead of a 0.65 mm one); hood rear-wall edge
chamfered (prism clearance 0.18 to 0.26 mm); cradle pin slot 2.0 to 2.33 mm (0.085 to 0.25 mm round the pin body); clearance
under the overhanging USB shell 0.01 to 0.25 mm.

## 11. Open mechanical issues

1. **The cradle has no hold-down (D17).** Seven spring pins at about 0.59 N each push up with about 4.1 N; the marker weighs
   about 0.11 N. Without a hold-down the marker lifts off the reference plate, so the cradle as modelled can neither charge
   reliably nor act as the flip-calibration seat. About 9 N at the marker centre would keep all three ball feet seated at
   0 degrees. At 180 degrees the pins bear on the solid base plate, compressed 2.27 mm of a 2.29 mm stroke. The DESIGN_SPEC
   sentence "a puck placed 180 degrees round touches no pins" is not achievable with pins that stand above the seat; the
   check confirms only that no pin touches a pad or an opening. Options: a hinged or sliding lid, magnetic retention, or
   pins that retract for calibration. A system decision is needed.
2. **The camera openings have no tolerance margin.** Nominal margins of the light bundle are 0.019 to 0.054 mm; the bureau
   tolerance is +-0.2 to 0.3 mm. With the PCB displaced by its own 0.15 mm play the right-hand field is clipped at 24 degrees,
   with 0.35 mm at 20.5 degrees; 0.2 mm in height clips the lower field at 11.7 degrees or the upper at 15.0. Proposed: opening
   half-width 1.65 to 2.0 and sill 4.6 to 4.3 with a correspondingly larger window (`PROPOSED_PARAM_CHANGES.md` items 6 and 7).
   The top of the opening is the roof underside and cannot move without a thicker puck.
3. **Nothing locates the PCB in the tub in x and y** except the 0.15 mm gap to the ledge. This sets issue 2. Proposed: two
   locating features between PCB and tub near the cameras.
4. **Ball feet (D02).** A 0.10 mm protrusion cannot be printed; seats must be machined or the balls jig-set and potted. The
   three seats are the tilt datum of the instrument.
5. **Prism slightly undersized for the assumed pupil**: 2.3 % of the pupil is clipped at the horizontal field edge by the
   2.0 mm exit face. The pupil position and size are assumptions; confirm with the OVM7692 lens data.
6. **Thin wall behind the window recess (D04)**, 0.525 mm over 3.5 mm2 per camera, and the visor window lands of 0.4 to 0.55 mm.
7. **Seal** not tested and adhesive not chosen: 0.4 mm land, lugs and corner notches in the front seal, PA12 bonding (section 8).
8. **Footstep load not analysed.** Post foot area is 20.5 mm2 (39 MPa if 800 N went through the posts alone, an upper bound).
   The cover glass loads a 0.8 mm ledge with the LCD bonded under it.
9. **LCD insertion (D11)** has 0.12 mm nominal clearance past the ledge, less than the print tolerance.
10. **Adhesive sheet thickness (D10)**: decide between a 0.87 mm base plate and a 7.73 mm stack.
11. **Vapor smoothing of 0.8 mm walls** and flatness of the 1.0 mm base plate: bureau confirmation and coupons.
12. **Light leaks**: the slit above the cube at the rear of each hood (D13) and the translucency of 0.8 mm black PA12 are untested.
13. **Battery**: retention not designed (adhesive thickness comes out of the 0.15 mm swell margin); protection-board size provisional.
14. **LCD flex tail** shape is representative; it clears J1 by 0.05 mm in the model.
15. **PCB keep-outs are not in the YAML**: eight post feet and the hood skirts (parts under them below 0.95 mm). Passives are
    not in the YAML, so the checks cannot see a clash with them.
16. **Cradle details**: 0.54 mm webs in the steel plate, provisional pin and receptacle envelopes, 4.6 mm shift of the marker
    centre between the two positions (D15), no cable strain relief.
17. **Vent**: part data unverified; printed dia 1.0 hole may need drilling; position moved 0.9 mm from the YAML note (D08).
18. **Purchased-part envelopes** are simple solids; every PROVISIONAL item in section 2 must be checked against a
    manufacturer drawing before parts are ordered.
