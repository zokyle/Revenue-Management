# GL-1 electrical package

Nothing in this directory has been built or measured. The boards exist as design scripts,
KiCad 7 files generated from them and fabrication data that passed KiCad's DRC. Several
land patterns and pin tables are PROVISIONAL (list below): **do not order boards before
those are checked against the manufacturers' drawings.**

Revised on 2026-11-18 after three independent reviews of the first layout. What changed is
in `gl1_main/LAYOUT_LOG.md` (first section) and in the design files under "REVIEW FIX".

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
| `gl1_cradle/` | the cradle board, same structure (`gl1_cradle_design.py`, `build_gl1_cradle.py`, `build_netlist.py`, `check_cradle_rules.py`, `CRADLE_NOTES.md`, `make_usb_footprint.py`, `gl1_cradle_fp.pretty/`) |

In each `out/`: `<name>.kicad_pcb / .kicad_pro / .kicad_dru`, `fab/` (Gerber X2, Excellon,
`README.txt` with stack-up, finish, via tenting and plugging) and `<name>-fab.zip`,
`assembly/` (position file, BOM, `<name>-bom-status.csv` with a Status column and the
sourcing risk and approved alternates of every line, README), `schematic/` (PDF, PNG,
netlist round trip), `<name>-mechanical.json`, `<name>-netlist.json`, `<name>-board.step`,
`renders/` and `review/` (PNG of every copper layer and both assembly sides), `drc.json`,
`layout_quality.md`, `build_summary.json`; for the main board also `pinmap.json`,
`pinmap_check.txt`, `spec_rules.md`, `mechanical_import.txt`.

## Rebuild

Use the system interpreter (it has KiCad's `pcbnew`). Run from the `greenline-marker`
directory. `PINDATA` is a directory outside the repository holding ST's two open pin data
files (`STM32U585RITx.xml`, `GPIO-STM32U5x_gpio_v1_0_Modes.xml`); without `--pindata` the
pin-map check is PARTIAL.

```
/usr/bin/python3 -B electrical/gl1_main/build_netlist.py --pindata PINDATA      # exit 0, about 25 s
/usr/bin/python3 -B electrical/gl1_main/build_gl1_main.py --pindata PINDATA     # exit 2 (see below), about 45 s with the stored routing
/usr/bin/python3 -B electrical/gl1_main/build_gl1_main.py --pindata PINDATA --reroute   # exit 2; routes from nothing: about 5.5 min (router 327 s)
/usr/bin/python3 -B electrical/gl1_cradle/build_netlist.py                      # exit 0, about 5 s
/usr/bin/python3 -B electrical/gl1_cradle/build_gl1_cradle.py                   # exit 0, about 10 s
/usr/bin/python3 -B electrical/gl1_main/update_notes.py --check                 # exit 0
(cd mechanical && python3 -B cad/board_import.py ../electrical/gl1_main/out/gl1_main-mechanical.json)   # exit 1 (J1, see below)
```

Exit status of `build_gl1_main.py`: **0** only if every stage passed; **2** when every stage
passed except the mechanical import and that check fails on exactly one row, J1's position
(spec amendment E24); **1** for anything else. Today it is 2. The cradle build exits 0 only
if every stage passed. Times are from a 4-core machine. The router is deterministic.

## Result (2026-11-18, after the review)

| | Main board `gl1_main` | Cradle `gl1_cradle` |
|---|---|---|
| Size, layers | D shape R 21.1 mm, flat at y 17.3; 4 layers, 0.8 mm, ENIG | 30 x 22 mm, 2 layers, 1.6 mm |
| Parts | 121 (104 on the BOM: 103 fitted + R14 not fitted; 11 bare-copper footprints; 6 fiducials) | 20 (13 on the BOM: 10 fitted + 3 spring pins not fitted; 1 bare; 6 fiducials) |
| Nets | 95 | 10 |
| Toolchain checks | 0 errors, 2 warnings (`plane_partial` twice: the GND pours round the crystal and over the photodiode, intended) | 0 errors, 0 warnings |
| Routed | 306 of 306 connections, audit clean; 278 vias, 2570 segments, 2297.4 mm | 29 of 29; 9 vias, 126.8 mm |
| KiCad DRC | 0 errors, 0 unconnected; 2 warnings, both cosmetic silkscreen (`silk_over_copper`, `silk_overlap`); nothing excluded, no rule relaxed. One rule ADDED by the build (zone clearance, see toolchain limits) | 0 errors, 0 unconnected; 1 `silk_overlap` warning |
| Rules | default 0.15 / 0.127 mm; Power 0.30 mm (neck 0.15); Fine 0.10 / 0.10 and CamPower 0.15 / 0.10 confined to two fine areas round the cameras (175 mm2, 13 % of the board); via 0.50 / 0.25 mm through; copper to edge 0.30; layer 2 solid GND; vias tented on BOTH sides, plugging from the bottom in the fab notes | default 0.15 / 0.127 mm (toolchain standard set), via 0.50 / 0.25; spring-pin holes 0.80 mm finished |
| Fine track | 218.3 mm narrower than 0.15 mm on 28 nets: F.Cu 133.7, In2.Cu 31.8, B.Cu 52.8 mm; all inside the fine areas, farthest 5.3 mm from a ball field | none |
| Outputs | 34 files verified against the model; BOM 37 lines (31 PROVISIONAL, 6 RESEARCH); 103 position rows; schematic 8 sheets, round trip equal (95 nets, 400 pads) | 28 files; BOM 7 lines (6 PROVISIONAL, 1 RESEARCH); schematic 3 sheets, round trip equal |
| Mechanical import | **FAILS, exit 1**, on one row: J1's anchor (0, -12.9) against the YAML point (0, -13.9). One warning: the battery keep-out differs from the YAML (0.3 mm notch for J1's courtyard). See "Departures" | not covered by `board_import.py`; never checked against the mechanical model |

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
* Copper to edge: 0.321 mm routed, 0.355 mm pads (rule 0.30).
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

| What | Numbers |
|---|---|
| J1 (E24 against the YAML) | anchor (0, -12.90), body y -17.30 to -11.70 (centre -14.50), signal pads to -10.40; the YAML has the body box centred on (0, -13.9). `mechanical/cad/board_import.py` exits 1 |
| battery-body keep-out | the YAML box less a notch 11.10 x 0.30 mm at y -10.2 to -9.9 for J1's courtyard; pads end 0.20 mm from the cell edge |
| fine class "used only to escape the camera BGAs" | not met: 0.10 mm track on three layers up to 5.3 mm from the ball fields (table above). Smaller fine areas did not complete (pad field + 4.0 mm: 303 of 306; + 3.5 and + 3.0 mm: 5 to 14 open). E7 therefore covers F.Cu, In2.Cu and B.Cu |
| CamPower | a second class, 0.15 / 0.10 mm, for the camera supply balls |
| vias tented on both sides | the specification asks for the underside only; the top is tented as well because the cell lies on it |
| TP5 | a fifth test pad (VDDUSB) beyond the four of E4 |
| cradle fuse trip current | 0.75 A against E6's "about 0.5 A" (hold 0.35 A and 1.0 ohm are inside E25) |
| cradle USB-C land | four ground pads 0.04 mm shorter than KiCad's pattern (hole clearance 0.20 mm) |
| carried from the netlist | rail VDDUSB, cam 2d, grain c, grain d, E1 b (`gl1_main/out/spec_rules.md`) |

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
`firmware/tools/gen_pins.py`. Its header and two notes changed, so **`make pins` must be run
in `firmware/`** (the hash in `gl_pins.h` follows). No pin assignment changed.

* `firmware_notes` (17): unchanged in number; notes 2 and 4 no longer claim outstanding work.
* `imu_mounting`: **U4 is at 90 degrees counter-clockwise seen from above.** Marker X =
  -sensor Y, marker Y = +sensor X, Z unchanged, i.e. `GL_PROV_IMU_MARKER_X_AXIS 1 / SIGN -1`,
  `Y_AXIS 0 / SIGN +1`. `firmware/core/gl_provisional.h` still has the identity placeholder:
  with it the two in-plane tilt axes are exchanged and one is inverted. PROVISIONAL: the map
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
| FH12A numbering equal to the FH12 land pattern; J1 position per E24 (YAML not yet corrected) | design file, section 1 | connector mirrored / tail fold does not fit |
| IMU axis map (above) | `pinmap.json` `imu_mounting` | slope direction wrong by 90 degrees |
| Cell lead polarity and position: BT1 = VBAT at (-18.4, -2.7), BT2 = GND at (-18.4, -5.8). No source says which lead of GM201030-PCB is where | `battery_pad_positions()` | cell connected reversed, or the leads cross |
| Generic KiCad 0402 LED land pattern and its polarity mark for VLMS1500 and SFH 4053B (pad 1 taken as the cathode) | `led_positions()` | all 16 LEDs reversed |
| ABS07 crystal on the Epson FC-135 land pattern | part Y1 | crystal does not seat |
| Mill-Max 0914: tail 0.635 mm, hole 0.80 mm (search extracts, not the drawing); **tail about 1.34 mm in a 1.6 mm board: OPEN** | cradle `MILLMAX_0914` | pins cannot be soldered properly |
| Cradle fuse (listing data), screw hole and head, USB-C land (four ground pads 1.07 mm) | cradle `PTC`, `make_usb_footprint.py` | charger input headroom; fit |
| 0.100 / 0.100 mm inside the fine areas on F.Cu, In2.Cu and B.Cu accepted by the fabricator in writing (spec E7); 0.25 mm as the DRILL size on a 0.50 mm pad (finished about 0.20 mm) | fab README | board cannot be made as drawn; ring 0.075 to 0.10 mm if 0.25 is read as the finished hole |
| Every passive order code, MCU electrical limits, ROM bootloader pin list, LP5907 enable current, MLCC bias derating (the 1 uF and 2.2 uF parts are new: sourcing A3) | `NETLIST_NOTES.md` section 7, BOM Status column | see notes |

Sourcing actions of `docs/SOURCING.md`: A1, A2, A5, A6 (hole and tail diameter), A13 and A17
are taken into the design files. Still open: A3 (bias curves), A6 (tail length), A11 / A12
(the display LS013B7DH03 and the cell GM201030-PCB are on no board BOM: they are not board
parts; they belong on a purchasing list above the BOMs), the availability doubts now shown
on the status BOM (OVM7692-RYAA high; SFH 4053B medium to high; STM32U585RIT6 and
MX25R6435FZNIL0 medium; GRM155R71C104KA88D conflicting life-cycle flag).

## Changes needed in other packages (not made here)

| Package | Change |
|---|---|
| `design/master_params.yaml` | J1 per E24: `top_side_parts` J1 body centre y -14.5 (not -13.9) with dy 5.6 (not 5.8); `tub_keepouts.lcd_tail` from y -17.30 rearward; regenerate the part list from the board (U11 is a SOT-23-5 LP5907-3.3, U12 added, TP5 added, the moved parts); `cradle.pcb`: spring-pin hole and, if the long-tail pin is not chosen, the thickness |
| `design/DESIGN_SPEC.md` | the note under the amendment table says the netlist "still carries the Schottky (D17), the three-pin 3.3 V regulator (U11) and J1 on its first position": the netlist and the board carry E24 to E26. Wanted amendments: a clamp and series resistors on SWDIO / SWCLK / NRST and an NRST capacitor at the pad; whether tenting on the top side and TP5 are adopted; the fine-class sentence (three layers, 5 mm) or a hand-routed escape; E6's trip current; a capacitor-distance rule for the camera supplies |
| `mechanical/cad/board_import.py` | check C: compare J1's BODY centre (`body.cx / cy` of the JSON) with the YAML, not the footprint anchor - with the YAML corrected to -14.5 the present comparison would still fail by 1.6 mm; build the LCD-tail model from the E24 position; check D: ignore zero-height board-only copper (then `BARE_BOTTOM_COPPER_NOT_FITTED` can go); accept or model the 0.3 mm courtyard notch; consider a tolerance margin on the outer faces of the post-foot keep-outs |
| `mechanical/cad/params.py`, `mechanical/README.md` | Mill-Max tail 0.635 mm / hole 0.80 mm (the model assumes 0.76 / 0.90); tail length against the cradle board; the M2 x 5 screw (sourcing A20) |
| `firmware/` | `make pins`; `GL_PROV_IMU_MARKER_*`; the ship-mode item; the simulator's IMU placeholder |
| `docs/sourcing.csv`, `docs/SOURCING.md` | drop rows main-10 (D17) and main-35 (MCP1700-3302); renumber main-11 to main-35; row cradle-02 (fuse) |
| `electrical/tools` (toolchain owner) | see the first three limits below |

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
  changes: 39 attempts after the review, one complete (`gl1_main/LAYOUT_LOG.md`). A part
  inside the escape window of a fine-pitch array usually leaves connections open.
* Thermal reliefs, teardrops, impedance control: none. Plugging of vias is text in the fab
  README, not geometry.
* Mask and paste are verified for presence and position, not aperture size; mask is drawn
  1:1 on the lands.
* The toolchain BOM has no status column: the build writes `<name>-bom-status.csv` beside it.
* `gleda.checks` skips the pad-to-hole test for parts with `allow_overhang` (found on the
  cradle's USB-C land pattern; worked around in `make_usb_footprint.py`).
* The mechanical JSON lists copper-only footprints as components; six bare-copper
  footprints on the main board's underside carry a "not fitted" mark so that
  `mechanical/cad/board_import.py` does not reject them (workaround, bounded by rule row
  "bare copper"; it means those six are not tested by that check).
