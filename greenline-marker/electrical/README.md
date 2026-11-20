# GL-1 electrical package

Nothing in this directory has been built or measured. The boards exist as design scripts,
KiCad 7 files generated from them and fabrication data that passed KiCad's DRC. Several
land patterns and pin tables are PROVISIONAL (list below): **do not order boards before
those are checked against the manufacturers' drawings.**

**Revision E (E-EVT1), 2026-11-18.** Both boards are rebuilt on revision E of
`design/master_params.yaml` and `design/DESIGN_SPEC.md` (amendments E24 to E28, E35, E36). No
part moved and no net changed on the main board: it was routed again from nothing because the
stored routing's fingerprint covers the revision stamp, and the copper came out identical to
revision D (2570 segments, 278 vias, compared item by item; `gl1_main/LAYOUT_LOG.md`, section
"Revision E"). The cradle board is 1.0 mm thick instead of 1.6 mm (E36). Both builds end with
the mechanical package's import check and both exit 0.

Revised before that on 2026-11-18 after three independent reviews of the first layout. What
changed then is in `gl1_main/LAYOUT_LOG.md` and in the design files under "REVIEW FIX".

## What is here

| Path | What |
|---|---|
| `tools/` | the in-house toolchain "gleda" 0.4.0: netlist as code, KiCad 7 board, router, KiCad DRC as the judge, outputs. Read `tools/README.md`, at least "Limitations" |
| `gl1_main/gl1_main_design.py` | main board: parts, nets, pin map, mechanical contract (from `design/master_params.yaml`), placement, router options |
| `gl1_main/build_gl1_main.py` | one command: checks, spec-rule table, pin-map check, board, route, KiCad DRC, outputs, schematic, mechanical import, quality figures, review renders -> `gl1_main/out/` |
| `gl1_main/build_netlist.py` | the earlier stage without copper -> `gl1_main/netlist_out/` |
| `gl1_main/check_netlist_rules.py`, `check_pinmap.py`, `pinmap.json` | specification -> netlist table with seeded-defect self-test; pin map against ST's open pin data; the exported pin map (a copy is in `out/`) |
| `gl1_main/routing.json` | the stored routing (reused when the design fingerprint matches; audited again on every build) |
| `gl1_main/NETLIST_NOTES.md`, `LAYOUT_LOG.md` | every value with its calculation, departures, PROVISIONAL list; every routing attempt |
| `gl1_main/layout_quality.py`, `layout_review.py`, `silk_text.py` | figures measured on the copper (the second file: the measurements the reviewers made, repeated by every build); silkscreen legend helper |
| `gl1_cradle/` | the cradle board, same structure (`gl1_cradle_design.py`, `build_gl1_cradle.py`, `build_netlist.py`, `check_cradle_rules.py`, `CRADLE_NOTES.md`, `make_usb_footprint.py`, `gl1_cradle_fp.pretty/`); its build also ends with the mechanical import (`board_import.py --cradle`) |

In each `out/`: `<name>.kicad_pcb / .kicad_pro / .kicad_dru`, `fab/` (Gerber X2, Excellon,
`README.txt` with stack-up, finish, via tenting and plugging) and `<name>-fab.zip`,
`assembly/` (position file, BOM, `<name>-bom-status.csv`, README) and `<name>-assembly.zip`,
`schematic/` (PDF, PNG,
netlist round trip), `<name>-mechanical.json`, `<name>-netlist.json`, `<name>-board.step`,
`renders/` and `review/` (PNG of every copper layer and both assembly sides), `drc.json`,
`layout_quality.md`, `build_summary.json`, `spec_rules.md`, `mechanical_import.txt`,
`outputs.json` (every output file with size and SHA-256; the build completes it with the status
BOM, the extended assembly README and the final assembly zip and then compares every entry
with the file on disk); for the main board also `pinmap.json`, `pinmap_check.txt`.

**The status BOM has two status columns.** "Status" follows `docs/SOURCING.md`: VERIFIED = a US
source listing this exact part number was seen on the date in the last column (listed for
sale; not a stock promise), PROVISIONAL = everything else; it is copied from the numbered row of
`docs/sourcing.csv` (main-NN / cradle-NN) that has the line's references, and it is PROVISIONAL
when that row names another part number or does not exist (the build then prints a WARNING and
counts the line under "sourcing rows out of step with the BOM"; today 0 on both boards).
"Design evidence" is RESEARCH or PROVISIONAL: how well the pin table, land pattern and values
of the line are known (with a note). Today every part number on both boards is VERIFIED as a
listing, while 31 of 37 main-board lines and 6 of 7 cradle lines are PROVISIONAL in their
design data. A line can be ordered only when both allow it. The remaining columns are the
sourcing risk, the alternates the sourcing report names (actions A4 and A18) and the sourcing
row. The alternates are CANDIDATES: the column is headed "candidates, NOT approved", each cell
says VERIFIED or PROVISIONAL for itself, and no alternate has been approved by anybody (the
microcontroller's cell, for instance, names a different MCU whose pin compatibility is from memory).

## Rebuild

Use the system interpreter (it has KiCad's `pcbnew`). Run from the `greenline-marker`
directory. `PINDATA` is a directory outside the repository holding ST's two open pin data
files (`STM32U585RITx.xml`, `GPIO-STM32U5x_gpio_v1_0_Modes.xml`); without `--pindata` the
pin-map check is PARTIAL.

```
/usr/bin/python3 -B electrical/gl1_main/build_netlist.py --pindata PINDATA      # exit 0, about 25 s
/usr/bin/python3 -B electrical/gl1_main/build_gl1_main.py --pindata PINDATA     # exit 0, about 60 s with the stored routing
/usr/bin/python3 -B electrical/gl1_main/build_gl1_main.py --pindata PINDATA --reroute   # exit 0; routes from nothing: about 6.5 min (router 328 s)
/usr/bin/python3 -B electrical/gl1_cradle/build_netlist.py                      # exit 0, about 5 s
/usr/bin/python3 -B electrical/gl1_cradle/build_gl1_cradle.py                   # exit 0, about 30 s
/usr/bin/python3 -B electrical/gl1_main/update_notes.py --check                 # exit 0
/usr/bin/python3 -I -B electrical/gl1_main/check_pinmap.py --selftest --pindata PINDATA   # exit 0
/usr/bin/python3 -B electrical/gl1_main/check_netlist_rules.py --selftest       # exit 0 (49 seeded defects)
/usr/bin/python3 -B electrical/gl1_cradle/check_cradle_rules.py --selftest      # exit 0 (18 seeded defects)
(cd mechanical && python3 -B cad/board_import.py ../electrical/gl1_main/out/gl1_main-mechanical.json)             # exit 0
(cd mechanical && python3 -B cad/board_import.py --cradle ../electrical/gl1_cradle/out/gl1_cradle-mechanical.json)   # exit 0
(cd design && python3 check_parts_vs_board.py)                                  # exit 0: the YAML part lists match the board
```

Exit status of both board builds: **0** only if every stage passed, the mechanical import
included; **1** for anything else. (At revision D the main build exited 2 because the import
failed on J1; that special status is gone with its cause.) The mechanical stage also fails if
the import warns that the board file is stamped with another revision than the YAML or states
another height-limit zone. The stored routing is reused only when its fingerprint matches the
design and the router options; the fingerprint covers the whole design dictionary, so ANY edit
of a design file, a status note or fab note included, makes the next build route again (about
5.5 min; the router is deterministic, so unchanged geometry gives the same copper). Times are
from a 4-core machine.

## Result (2026-11-18, revision E-EVT1)

| | Main board `gl1_main` | Cradle `gl1_cradle` |
|---|---|---|
| Size, layers | D shape R 21.1 mm, flat at y 17.3; 4 layers, 0.8 mm, ENIG | 30 x 22 mm, 2 layers, **1.0 mm** (E36; 0.91 mm core), ENIG |
| Parts | 121 (104 on the BOM: 103 fitted + R14 not fitted; 11 bare-copper footprints; 6 fiducials) | 20 (13 on the BOM: 10 fitted + 3 spring pins not fitted; 1 bare; 6 fiducials) |
| Nets | 95 | 10 |
| Toolchain checks | 0 errors, 2 warnings (`plane_partial` twice: the GND pours round the crystal and over the photodiode, intended) | 0 errors, 0 warnings |
| Rule table | 66 rows: 62 as specified, 4 departures, 0 open, 0 workarounds, 0 failed; self-test 49 of 49 seeded defects | 15 rows: 14 as specified, 1 departure (USB-C land), 0 failed; self-test 18 of 18 |
| Routed | 306 of 306 connections, audit clean; 278 vias, 2570 segments, 2297.4 mm; identical to the revision D copper | 29 of 29; 9 vias, 126.8 mm |
| KiCad DRC | 0 errors, 0 unconnected; 2 warnings, both cosmetic silkscreen (`silk_over_copper`, `silk_overlap`); nothing excluded, no rule relaxed. One rule ADDED by the build (zone clearance, see toolchain limits) | 0 errors, 0 unconnected; 1 `silk_overlap` warning |
| Rules | board minimum 0.100 / 0.100 mm (track / clearance); classes Default 0.15 / 0.127 mm, Power 0.30 / 0.127 mm (neck 0.15), Fine 0.10 / 0.10 mm and CamPower 0.15 / 0.10 mm, the last two fine only inside the two fine areas (pad field + 5 mm, 175 mm2, 13 % of the board; E35); via 0.50 / 0.25 mm through; copper to edge 0.30, hole to copper 0.20; layer 2 solid GND; vias tented on BOTH sides, plugging from the bottom in the fab notes | board minimum 0.127 / 0.127 mm; classes Default 0.20 / 0.15 mm and Power 0.40 / 0.15 mm; via 0.50 / 0.25 mm; copper to edge 0.30, hole to copper 0.20; spring-pin holes 0.80 mm finished |
| Fine track | 218.3 mm of 0.100 mm track on 28 nets: F.Cu 133.7, In2.Cu 31.8, B.Cu 52.8 mm; all inside the fine areas, farthest 5.3 mm from a ball field. As E35 allows; the fab README names F.Cu, In2.Cu and B.Cu for 0.100 / 0.100 mm | none |
| Outputs | 35 files in `outputs.json`, each equal to the file on disk; plotted data verified against the model; BOM 37 lines (Status 37 VERIFIED; design evidence 31 PROVISIONAL, 6 RESEARCH); 103 position rows; schematic 8 sheets, round trip equal (95 nets, 400 pads) | 29 files; BOM 7 lines (Status 7 VERIFIED; design evidence 6 PROVISIONAL, 1 RESEARCH); schematic 3 sheets, round trip equal |
| Mechanical import | **passes, exit 0, no warning**: outline, hole and slot; 86 top-side parts 0.25 mm or more from the tub; J1 body box and anchor on the YAML (mouth y -17.3); the battery keep-out equals `battery.body` less the YAML notch; 18 bottom-side parts in the openings; 14 copper-only footprints by their own rules; 7 pads on the pin axes | **passes, exit 0** (`--cradle`, new at revision E): thickness 1.0, outline, four screw holes, seven pins on the pad row and on the modelled axes (4 fitted), receptacle on the modelled one, nothing else on the top face |

Main-board figures (`gl1_main/out/layout_quality.md`, measured by the build on the DRC'd board):

* Camera bus after the series arrays: 577 mm of track for 293 mm of spanning trees (x1.97),
  48 vias. This is WORSE than the first layout (449 mm).
* Camera data against PCLK, ball to MCU pad: left camera PCLK is the longest line (99.5 mm)
  and the data lines are 27 to 84 mm shorter (-589 to -188 ps at 7 ps/mm); right camera
  -9.7 to +77.5 mm (-68 to +542 ps); the longest line is 105 mm. The pixel clock is 12 MHz
  (period 83 ns), so the skew is under 1 % of a period; the copper is long all the same.
* Camera supply balls to the nearest capacitor of the net, along the copper: U2 DOVDD 9.9 mm,
  U2 AVDD 5.9 mm, U2 DVDD 4.2 mm, U3 DOVDD 5.0 mm, U3 AVDD 7.7 mm, U3 DVDD 7.1 mm.
* Smallest via-to-pad gap on the top side 0.100 mm (own net, vias tented), 0.134 mm to a pad
  of another net (rule 0.127). Smallest solder-mask web: top 0.150 mm (two IMU pads),
  bottom 0.360 mm. No via opening in either mask.
* Copper to the board edge (outline and the routed locating slot; rule 0.30): 0.325 mm routed
  (CAM_D3, at the slot), 0.355 mm pads (R4, at the slot). Copper to the wall of the drilled
  locating hole H1 (a separate rule, 0.20): 0.321 mm routed (CAM_D4), 0.795 mm pads. Earlier
  issues gave the 0.321 mm as an edge distance; the figures are now reported separately by
  `layout_quality.py`.
* Plane clearance: 0.200 mm to every foreign track and via on all four filled layers.
* Layer 3 (In2.Cu): V2V8 fill on 59.0 % of the board in 4 pieces, 461 mm of signal track;
  408 of 888 mm of bottom-layer track (46 %) has no In2 copper above it. It is a supply fill
  and a routing layer, not a plane. Layer 2: GND fill 86.0 %, one piece, no track.
* IMU: no copper in the top-layer rule area under the body, no via within 0.35 mm of the
  body outline; a CP1_MCU track clips the corner of the body outline by 0.03 mm; 12.3 mm or
  more from every regulator, 26 mm from the charger. U4 stands at 90 degrees (see "What the
  firmware must take from this board").
* Crystal: 7.6 and 4.8 mm, top layer only, no via; in its no-via box only a GND via and
  R1's V2V8 via; nearest foreign via 0.275 mm (CAM_EN, static); nearest foreign top-layer
  track 0.168 mm (VBUS_SENSE at the neighbouring MCU pad, static); layer 2 unbroken under
  it; tracks of other nets run below that plane on layers 3 and 4.
* PD_K: 33.6 mm (28.2 on the bottom layer, links between the seven cathode pads included),
  1 via; no LED, clock or bus track within 0.5 mm on its layer; on layer 3 CAM_HREF, CP3,
  CP4 and LCD_DISP cross over it (2.0 / 2.2 / 0.3 / 1.2 mm).
* Vias: 278, 37 of them under the cell, all tented on both sides.
* USB pair: D- 41.7 mm, D+ 41.2 mm, 6 and 2 vias, up to 13.6 mm apart. NOT a coupled pair.

## Departures from the specification and from the YAML

Closed at revision E, and therefore gone from this table: J1's position (E24 is in the YAML),
the notch in the battery keep-out (YAML `battery.board_keepout_notch`), the fine class on three
layers (E35), the cradle pin tail against the board thickness (E36).

| What | Numbers |
|---|---|
| CamPower | a second class, 0.15 / 0.10 mm, for the camera supply balls, inside the same fine areas (in no amendment) |
| vias tented on both sides | the specification asks for the underside only; the top is tented as well because the cell lies on it |
| TP5 | a fifth test pad (VDDUSB) beyond the four of E4 (the YAML lists it because it is on the board, flagged open) |
| cradle fuse trip current | 0.75 A against E6's "about 0.5 A" (hold 0.35 A and 1.0 ohm are inside E25) |
| cradle USB-C land | the four outer ground pads (two lands) are 1.11 mm long, 0.04 mm shorter than the 1.15 mm of KiCad's pattern (hole clearance 0.20 mm) |
| carried from the netlist | cam 2d, grain c, grain d (`gl1_main/out/spec_rules.md`). Rows "rail VDDUSB" and "E1 b" were counted here until the final audit: their 2.2 uF capacitors are the letter of the rev E spec (E27), and the rows now quote that text and test for 2.2 uF |

## Known weaknesses of this layout (review findings that are NOT fixed)

* **Camera supply decoupling.** The reviewers asked for a 100 nF within about 2 mm of every
  supply ball. Twenty-three routing variants with capacitors 1.45 mm beside the balls ended
  at 97.4 to 99.3 %. The paths are 4.2 to 9.9 mm (above). The left camera's DOVDD ball, the
  worst case of the first layout (15.6 mm), is at 9.9 mm. To be done again with the real
  ball map, by hand if the router cannot.
* **PD_K** has a ground pour beside it, not a VBIAS guard, and four nets cross it on layer 3.
* **Layer 3 is not a plane**; nearly half of the bottom-layer track has no reference on the
  adjacent layer. No ground stitching vias at layer changes (the router has none).
* **Long camera lines** (above). PCLK of the left camera is 99.5 mm.
* **SWDIO, SWCLK and NRST** go from the underside pads to the MCU with no clamp and no series
  resistor; NRST's 100 nF is at the MCU. The specification names only VBUS, D+ and D- for
  the clamp: a specification gap, recorded as an EVT limitation (the three pads belong in the
  ESD test plan).
* **Bring-up access**: BOOT0 has no pad (first programming is SWD through the factory
  fixture); the seven pads carry no always-on rail and the cradle's J2 no reference voltage;
  a board without its cell gets at most the charger's 20 mA in the cradle.
* No reference designators on the silkscreen; use the assembly renders and position file.
* The router does no length matching, no guard traces and no differential pairs.

## What the firmware must take from this board

`gl1_main/pinmap.json` (copy in `gl1_main/out/`) is the single input of
`firmware/tools/gen_pins.py`. **Revision E changed no pin.** The board build left the file
byte-identical (SHA-256 d33ff53f...3972e4); the final audit of rev E then corrected two TEXTS in it
and nothing else: the `spec` string ("DESIGN_SPEC rev E (EVT1) with amendments E1 to E36 (in the
netlist and on the board: E1 to E4, E24 to E28 and E35)"; it said rev D, E1 to E34) and the first
open item for the firmware (the IMU axis map is generated now; see below). The file is now SHA-256
30505550677ba2dca446e0d2cf8f66e4ea720316e02fde1aa317bb97d4d0371f; `make pins` was run in
`firmware/` in the same step and `make pins-check` passes (the generated header changed in its
hash and comment lines only). A key-by-key comparison of the two JSON files shows no other difference.

* `firmware_notes` (17): unchanged in number; notes 2 and 4 no longer claim outstanding work.
* `imu_mounting`: **U4 is at 90 degrees counter-clockwise seen from above.** Marker X =
  -sensor Y, marker Y = +sensor X, Z unchanged, i.e. `GL_PROV_IMU_MARKER_X_AXIS 1 / SIGN -1`,
  `Y_AXIS 0 / SIGN +1` (the key names in the pin map are historical). The firmware took this up
  in its phase 3: the identity placeholder of `firmware/core/gl_provisional.h` is gone and
  `gen_pins.py` writes the map into `gl_pins.h` as `GL_PINS_IMU_MARKER_*`. PROVISIONAL: the map
  assumes ST's axis drawing matches KiCad's LGA-14 pattern at rotation 0 (not read).
* `open_items_for_firmware` (4): the IMU axes; ship mode with PB5 / PB14 floating (possible
  27 uA through R13 if the UCPD dead-battery switch acts in Shutdown, PROVISIONAL, RM0456 not
  read); first programming by SWD only; no ESD parts on the three service pads. These are
  not `firmware_notes` because `gen_pins.py` accepts only notes it has a rule for.

## PROVISIONAL items that gate ordering boards

Each is isolated in one marked table of its design file.

| Item | Where | Risk if wrong |
|---|---|---|
| OVM7692 ball map, pitch 0.5 mm, pad 0.20 mm (stand-in) | `OVM7692_BALLS` | both cameras mis-wired; array order, fan-out and capacitor placement must be redone |
| Camera image orientation: which package side carries the 640-pixel axis (spec section 7 gate). Both cameras stand at rotation 0 with the 3.47 mm side along x, which assumes it | placement of U2 / U3 | images rotated by 90 degrees; the horizontal field is the short one |
| BQ25101YFP ball map and 0.23 mm lands | `BQ25101_BALLS` | charger mis-wired |
| LCD tail pin order and which tail edge is pin 1 | `LCD_TAIL`, `LCD_TAIL_PIN1_EDGE` | all ten display pins mirrored |
| LM66100DCKR pin table and CE polarity (from memory, E25) | `LM66100_PINS` | VBUS switch mis-wired |
| VEMD8080 land pattern | `VEMD8080_PADS` | photodiode does not fit |
| FH12A numbering equal to the FH12 land pattern and its 2.0 mm height (sourcing A15); the tail fold behind J1's mouth (Sharp drawing; the YAML zone is `basis: provisional`) | design file, section 1; YAML `tub_keepouts.lcd_tail` | connector mirrored / tail fold does not fit |
| IMU axis map (above) | `pinmap.json` `imu_mounting` | slope direction wrong by 90 degrees |
| Cell lead polarity and position: BT1 = VBAT at (-18.4, -2.7), BT2 = GND at (-18.4, -5.8). No source says which lead of GM201030-PCB is where | `battery_pad_positions()` | cell connected reversed, or the leads cross |
| Generic KiCad 0402 LED land pattern and its polarity mark for VLMS1500 and SFH 4053B (pad 1 taken as the cathode) | `led_positions()` | all 16 LEDs reversed |
| ABS07 crystal on the Epson FC-135 land pattern | part Y1 | crystal does not seat |
| Mill-Max 0914: tail 0.635 mm, hole 0.80 mm, **tail length about 1.34 mm** (search extracts and a subtraction, not the drawing). E36 made the board 1.0 mm so that this tail comes 0.34 mm through; if the real tail is shorter than 1.2 mm the joint has no fillet again | cradle `MILLMAX_0914`, YAML `cradle.pins.tail_length` | pins cannot be soldered properly |
| Cradle fuse (listing data), screw hole and head, USB-C land (four outer ground pads 1.11 mm, 0.04 mm shorter than KiCad's) | cradle `PTC`, `make_usb_footprint.py` | charger input headroom; fit |
| 0.100 / 0.100 mm inside the fine areas on F.Cu, In2.Cu and B.Cu accepted by the fabricator in writing (spec E7 as widened by E35: the quote request must name all three layers); 0.25 mm as the DRILL size on a 0.50 mm pad (finished about 0.20 mm) | fab README | board cannot be made as drawn; ring 0.075 to 0.10 mm if 0.25 is read as the finished hole |
| Every passive order code, MCU electrical limits, ROM bootloader pin list, LP5907 enable current, MLCC bias derating (the 1 uF and 2.2 uF parts are new: sourcing A3) | `NETLIST_NOTES.md` sections 6 and 7, BOM column "Design evidence" | see notes |

**Sourcing actions of `docs/SOURCING.md` section 12** (the full table, action by action, is in
`gl1_main/NETLIST_NOTES.md` section 12):

* **Applied in the design files and BOMs** (same footprint, same value): A1 (1 uF: Samsung
  CL05A105KP5NNNC for the obsolete GRM155R61A105KE15D), A2 (2.2 uF: GRM155R61A225KE01D, second
  source CL05A225KP5NSNC), A4 (alternate CL05B104KO5NNNC for the 100 nF line, both BOMs), A5
  (cradle fuse 0603L035YR), A6 (spring-pin tail and hole diameter; the tail length is answered
  by E36), A7 (U12 LM66100DCKR, Digi-Key 296-53541-1-ND), A8 (U11 LP5907MFX-3.3/NOPB), A9
  (SFH 4053B kept, IN-S42CTQIR named), A13 (U4 from Newark at 5.75), A17 (order codes and
  prices; the cradle's R1 / R2 and C1 codes were entered at this revision), A18 (the
  alternates column: candidates, none approved).
* **Open, needs an owner decision or a document this session could not read:** A3 (DC-bias
  curves of the 1 uF, 2.2 uF and 4.7 uF parts; a larger case would be a footprint change), A8's
  order code (the live US distributor page), A9 (SFH 4053B data sheet: wavelength, package,
  polarity mark), A11 / A12 (the display LS013B7DH03 and the cell GM201030-PCB are not board
  parts; the main assembly README names them as off-board items, but the purchasing list above
  the BOMs has no file and no owner here), A14 (flash on tray or reel: with the assembler), A15
  (FH12A against the FH12 land pattern: Hirose drawing), A5's 1206 fallback fuse and E6's trip
  current (spec owner).
* **Not design-file changes:** A10 (camera life cycle and quotes), A16 (MCU price and lead
  time). **Not electrical:** A19 to A35.
* The availability doubts stay visible on the status BOM (OVM7692-RYAA high; SFH 4053B medium
  to high; STM32U585RIT6 and MX25R6435FZNIL0 medium; GRM155R71C104KA88D conflicting life-cycle
  flag).

## Changes needed in other packages (not made here)

Done by the other packages at revision E and no longer asked: J1, the tail zone, the part list
and the cradle thickness in the YAML; the spec's E24 to E28, E35, E36 text; `board_import.py`
comparing J1 by its body and handling copper-only footprints; the cradle import check.

| Package | Change |
|---|---|
| `design/DESIGN_SPEC.md` | wanted amendments, none decided: a clamp and series resistors on SWDIO / SWCLK / NRST and an NRST capacitor at the pad; whether tenting on the top side, TP5 and the CamPower class are adopted; E6's trip current (0.75 A on the board); a capacitor-distance rule for the camera supplies |
| `design/master_params.yaml` | the Mill-Max tail and hole diameters (electrical 0.635 / 0.80 mm, mechanical model 0.76 / 0.90 mm): no key, so no check compares them. If a part moves on the board, `top_side_parts` must be regenerated (`design/check_parts_vs_board.py` says so) |
| `mechanical/` | the Mill-Max diameters (above); consider a tolerance margin on the outer faces of the post-foot keep-outs |
| `firmware/` | nothing new from this revision (no pin changed; two texts of `pinmap.json` corrected, `make pins` run). Carried: the IMU axis map (generated into `gl_pins.h` now, PROVISIONAL in itself), the ship-mode item, the simulator's IMU placeholder |
| `docs/sourcing.csv`, `docs/SOURCING.md` | done in the final audit (report revision 4): the numbered rows are the rev E BOM lines with the BOM's item numbers; the parts that left are history rows. Open there: no part number for the M2 x 4 cradle screw, the LP5907-3.3 order code |
| `docs/` in general | VALIDATION_PLAN and MANUFACTURING_PLAN are still the rev D plans (each carries a rev E note since the final audit; not re-issued). `docs/RELEASE_GATES.md` was never written; the spec no longer points to it |
| `electrical/tools` (toolchain owner) | see the first three limits below; `outputs.json` should be written after everything else, or offer a hook |

## Toolchain limits to know before trusting the files

* **Defect, worked around in `build_gl1_main.py`:** the generated rule "fine class ... outside
  the fine areas" carries `clearance min 0.127 mm`, and KiCad's zone filler lets it override
  the zones' 0.20 mm clearance for those nets (29 items at 0.1275 mm on the first layout,
  while the fab README said 0.200). The build appends one rule (`A.Type == 'Zone' ||
  B.Type == 'Zone'` -> clearance 0.2 mm) to the `.kicad_dru`. The toolchain's own rule should
  not apply to zones.
* **Defect, not worked around:** the assembly README prints "no paste" for every part that
  is not on the BOM without looking at the pads, and `verify_outputs` cannot catch it. It is
  true on this board now (BT1 / BT2 are made without paste).
* **Wording:** the fab README calls the 0.25 mm via hole "finished hole"; a fab note in the
  design asks the fabricator the question (drill size intended).
* The mechanical JSON gives a part's footprint anchor as its x, y; for J1 the anchor is
  1.6 mm from the body centre (see `anchor_offsets` in `out/outputs.json`).
* Fine areas have no layer: a fine class cannot be confined to the escape layer.
* KiCad's DRC is geometric. The electrical checks are ERC-style rules on the model;
  KiCad's ERC is not run. A wrong pin table passes every check.
* The schematic is a generated netlist drawing (boxes and labels), proven equal to the
  model by a netlist round trip; it is not a hand-drawn schematic.
* Maze router: 0 / 45 / 90 degree segments, through vias only, no shove, no length or skew
  matching, no differential pairs, no guard traces, no stitching vias. More vias and longer
  tracks than a hand layout. Routing is reproducible but not stable against small design
  changes: 39 attempts after the review, one complete placement (attempt 61, repeated
  identically by build 63 and again by the revision E build; `gl1_main/LAYOUT_LOG.md`). A part
  inside the escape window of a fine-pitch array usually leaves connections open.
* Thermal reliefs, teardrops, impedance control: none. Plugging of vias is text in the fab
  README, not geometry.
* Mask and paste are verified for presence and position, not aperture size; mask is drawn
  1:1 on the lands.
* The toolchain BOM has no status column: the build writes `<name>-bom-status.csv` beside it,
  appends a section to the assembly README and zips the assembly folder again. The toolchain
  writes `outputs.json` before that, so the build re-enters those three files and then checks
  every entry of the manifest against the disk (at revision D the manifest held a stale hash
  for the assembly zip and did not list the status BOM).
* `gleda.checks` skips the pad-to-hole test for parts with `allow_overhang` (found on the
  cradle's USB-C land pattern; worked around in `make_usb_footprint.py`).
* The mechanical JSON lists copper-only footprints as components. Since revision E
  `mechanical/cad/board_import.py` recognises them (zero height, no BOM line) and tests them by
  their own rules; the "not fitted" mark the six bottom ones carried at revision D is removed.
* The routing fingerprint covers texts that the router never reads (revision, notes): a
  revision stamp alone forces a new routing run. It was not changed here; the copper is
  compared with the previous one instead.
