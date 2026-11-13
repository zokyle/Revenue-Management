# GL-1 cradle board - netlist notes

Stage: **netlist, no copper**. Nothing has been built and nothing is routed. KiCad's DRC has
seen only the board WITHOUT tracks (land patterns, courtyards, keep-outs, edge distances:
0 errors, every connection still open); that is not the DRC of a routed board. The positions
of the free parts in `gl1_cradle_design.py` are nominal.

The board implements DESIGN_SPEC section 4, "Cradle board (E6)", on the mechanical interfaces
of the `cradle` block of `design/master_params.yaml`: 30 x 22 mm, 1.6 mm, 2 layers, four screw
holes, seven spring-pin positions on 2.54 mm under the marker's seven pads, the USB-C mouth
1.3 mm beyond the rear edge.

Evidence levels: **RESEARCH** (seen in `docs/research/*.md` as "confirmed"; not a datasheet),
**PROVISIONAL** (engineering memory; to be checked before boards are ordered).

## 1. What is here and how to run it

| File | What it is |
|---|---|
| `gl1_cradle_design.py` | the netlist as code: parts, nets, footprints, outline and holes from the YAML, nominal placement |
| `check_cradle_rules.py` | the spec's cradle sentence and the YAML block, row by row, tested against the netlist, and the pin tables of U1 and J1 against the installed KiCad symbols; `--selftest` seeds 14 defects |
| `make_usb_footprint.py`, `gl1_cradle_fp.pretty/` | the project copy of the receptacle's land pattern and the script that derives it from the installed KiCad library (section 6) |
| `build_netlist.py` | runner (the stages of `../gl1_main/netlist_stage.py`): toolchain checks, rule table, schematic with netlist round trip, KiCad DRC of the board without tracks, exports |
| `netlist_out/` | results of the last run |

    /usr/bin/python3 -B electrical/gl1_cradle/build_netlist.py

Exit status 0 only if every stage passed. Content of the netlist:

<!-- BEGIN GENERATED: SUMMARY -->
20 parts: 13 on the BOM (10 fitted, 3 not fitted), 1 bare-copper footprint (J2), 6 fiducials; 10 nets
<!-- END GENERATED: SUMMARY -->

Two pins are unconnected on purpose: SBU1 and SBU2 of the receptacle.

## 2. Rule -> where it is in the netlist

A row is **pass** (as written), **departure** (the test passes, but the thing is done
differently from the letter of its source; section 6) or **FAIL**.

<!-- BEGIN GENERATED: RULE_COUNTS -->
**14 rows: 13 as specified; 1 departures from the letter of the spec (section 6): USB-C land; 0 open - NOT met (section none); 0 workaround (section none); 0 failed.**
<!-- END GENERATED: RULE_COUNTS -->

<!-- BEGIN GENERATED: RULES -->
| Rule | What the specification says | Where it is in the netlist | Result |
|---|---|---|---|
| board | cradle.pcb: 30.0 x 22.0, thickness 1.6; 2 layers (task) | outline rectangle about the board centre = marker (0, -23.2); layers 2 | pass |
| screws | four screw holes at cradle.pcb.screws [[-12.5, -31.5], [12.5, -31.5], [-12.5, -14.5], [12.5, -14.5]] | NPTH holes MH1-MH4 dia 2.2 (diameter PROVISIONAL) | pass |
| pin row | seven spring-pin positions on 2.54 mm pitch at pin_row_y -17.0, in the YAML order (VBUS, D-, D+, GND, SWDIO, SWCLK, NRST from x = -7.62 to +7.62 seen from above) | SP1-SP7 (through hole, top side): pad centres measured at marker x = [-7.62, -5.08, -2.54, 0.0, 2.54, 5.08, 7.62], y = [-17.0] | pass |
| fitted | four spring pins fitted (VBUS, D-, D+, GND) and three service positions (SWDIO, SWCLK, NRST) for the factory fixture | SP1-SP4 fitted, SP5-SP7 not fitted (same footprint, fitted in the factory fixture) | pass |
| service | (task) the three service positions taken to a small unpopulated header or test pads | J2: four bare pads on the bottom (GND, SWDIO, SWCLK, NRST) | pass |
| USB-C | USB-C receptacle (USB 2.0; YAML: GCT USB4105, rear exit), the USB mouth at the YAML edge (usb_mouth_y -35.5) | J1 USB4105-GF-A, top side, body front at marker y -35.50 (1.3 mm beyond the board edge); SBU1 / SBU2 not connected | pass |
| USB-C land | (KiCad DRC, rule set) 0.20 mm between a hole wall and foreign copper | J1 uses the project copy of KiCad's USB4105 land pattern: the four outer ground pads are 0.04 mm shorter; smallest distance from a locating-peg hole to a pad of J1 0.236 mm (library footprint: 0.194); the stored file equals the library file with exactly that change *(DEVIATION from the maker's land pattern, PROVISIONAL; no design rule is relaxed)* | **departure** |
| CC | 5.1 kohm from CC1 and from CC2 to ground | R1: CC1 (A5) - GND, R2: CC2 (B5) - GND, one resistor each | pass |
| fuse | a resettable fuse in VBUS (hold about 0.2 A, trip about 0.5 A, PROPOSED) | F1 between VBUS_IN (J1 A4, A9, B4, B9) and VBUS (SP1): hold 200 mA, trip 500 mA (PROVISIONAL part MF-FSMF020X-2) | pass |
| ESD | USBLC6-2SC6 on VBUS / D+ / D- | U1: D- through pins 1 + 6, D+ through pins 3 + 4, pin 5 on VBUS_IN (C1 100n), pin 2 GND *(ADDED: C1 100 nF at the VBUS pin of U1; the clamp sits on the connector side of the fuse)* | pass |
| top side | nothing on the top side may reach the pocket ceiling (YAML note) | height limit 0.0 mm on the whole top side, J1 and SP1-SP7 exempt; every other part is on the bottom | pass |
| pin tables | (task) the pin -> pad table of every library-backed part agrees with a second source | U1 against the installed KiCad symbol USBLC6-2SC6, J1 against USB_C_Receptacle_USB2.0_16P (pad numbers and pin names): all agree *(the spring pins and the fuse have one or two interchangeable pads)* | pass |
| fiducials | (task) at least three global fiducials per side | FID1-FID3 top, FID4-FID6 bottom | pass |
| status | (task) every BOM part carries an evidence status | Part.fields['Status'] is RESEARCH or PROVISIONAL on all 13 BOM parts | pass |
<!-- END GENERATED: RULES -->

## 3. The circuit

    J1 USB-C  VBUS (A4 A9 B4 B9) --+-- F1 (PTC 0.2 A) ---- VBUS ---- SP1   pin 1  x = -7.62
                                   +-- U1 pin 5, C1 100 nF
              D- (A7 B7) ---------- U1 pins 1 + 6 -------- USB_DM -- SP2   pin 2
              D+ (A6 B6) ---------- U1 pins 3 + 4 -------- USB_DP -- SP3   pin 3
              GND, shield --------- U1 pin 2 ------------- GND ----- SP4   pin 4, J2 pad 1
              CC1 (A5) -- R1 5.1 kohm -- GND               SWDIO --- SP5 (not fitted) -- J2 pad 2
              CC2 (B5) -- R2 5.1 kohm -- GND               SWCLK --- SP6 (not fitted) -- J2 pad 3
              SBU1, SBU2: not connected                    NRST ---- SP7 (not fitted) -- J2 pad 4

Frames: the board frame is the marker frame of the YAML moved to the board centre
(marker (0, -23.2)); x is not mirrored. Seen from above, pin 1 (VBUS) is on the left at
x = -7.62, under pad 1 of the marker's row, which the spec puts at x = -7.62 seen from above.
The top face of the board lies against the ceiling of its pocket in the printed cradle; the
receptacle and the spring pins are the only parts on it, everything else is on the bottom
(a height limit of 0 mm on the top side enforces it in the toolchain's checks).

## 4. Values and the calculations behind them

| Item | Value | Calculation |
|---|---|---|
| R1, R2 | 5.1 kohm 1 %, one on each CC pin | spec E6. A USB-C source applies VBUS only when it sees Rd (5.1 kohm) on one CC line; the cable connects only one of the two, so each pin needs its own resistor (CC1 tied to CC2 with one shared resistor fails with electronically marked cables, whose 1 kohm on the second line then lies in parallel). The sink never asks for more than the default 5 V |
| F1 | PTC, hold 0.2 A, trip 0.5 A | spec E6 (PROPOSED there). See below |
| U1 | USBLC6-2SC6 | spec E6: VBUS, D+, D-. On the connector side of the fuse, so that a discharge from the cable does not pass through the PTC; the marker has its own array at its pads |
| C1 | 100 nF | **added**: at the VBUS pin of U1 |
| SP1-SP7 | Mill-Max 0914 spring pin, through hole | YAML. SP1-SP4 fitted (VBUS, D-, D+, GND); SP5-SP7 are the same footprint, fitted only in the factory fixture |
| J2 | four bare pads dia 1.5 on 2.54 mm, bottom side | task: GND, SWDIO, SWCLK, NRST for the factory fixture (probe them or solder a 1 x 4 header) |

### The fuse

What the marker draws from VBUS (main-board notes, 4.1): 19.8 mA of charge current, which
includes whatever the system takes from the cell node, up to 1 mA for the charger, up to 8 mA
for the VDDUSB regulator (USB transceiver; PROVISIONAL), 25 uA for the sense divider:
**about 30 mA**. A read started in the cradle does not add to it (the charger limits its
output to 19.8 mA whatever the system draws).

| Question | Answer |
|---|---|
| hold current | 0.2 A at 23 C. A polymer PTC holds about 60 % of that at 60 C (PROVISIONAL): 0.12 A, four times the load. It never trips in normal use, also not with a marker that has a fault drawing 100 mA |
| trip current | 0.5 A. That is what every USB 2.0 port must be able to deliver and what a USB-C source offers at least, so a hard short across the pins (a coin, a key) trips the fuse on the weakest standard source; on a 1.5 A or 3 A charger it trips within a second or so (PROVISIONAL), where the pins and the tracks would otherwise carry 3 A |
| why not smaller (0.1 A / 0.3 A) | its resistance. A 0603 part with 0.1 A hold has up to about 6.5 ohm, the 0.2 A part about 5 ohm or less (PROVISIONAL): 0.20 V against 0.15 V at 30 mA |
| **what its resistance costs** | at 30 mA the fuse drops 0.06 V (2 ohm, assumed typical) to 0.15 V (5 ohm). Together with the marker's series Schottky that puts the charger's input at 4.23 to 4.37 V from a 4.75 V source, **below the 4.45 V minimum operating input the research records for the charger** (unverified; main-board notes, 4.1), and only 0.03 to 0.17 V above it from a 5.0 V source. The fuse cannot repair this alone (4.75 V less the diode's 0.35 V is already 4.40 V), but every ohm counts: when the part is chosen, take the lowest guaranteed resistance that still has hold 0.2 A / trip 0.5 A, and give the spec owner the figure. A part with about 1 ohm needs a higher hold current, which is a change of the spec's (PROPOSED) rating |
| voltage | 6 V or more. A sink with Rd only never sees more than 5.5 V |
| what it does not do | protect against a wet slot: water between the pins draws milliamperes and corrodes; no fuse sees that (spec). The marker must be dry before docking |

Part: Bourns MF-FSMF020X-2 (0603) is named as an example, **PROVISIONAL**: order code,
voltage (9 V) and resistance are from memory. Any 0603 PTC with hold 0.2 A, trip 0.5 A or
less, 6 V or more and 5 ohm or less fits the footprint; the lower its resistance the better
(table above). The ratings sit
in the table `PTC` of the design file.

## 5. PROVISIONAL items

| Table / item | What is not known |
|---|---|
| `MILLMAX_0914` | tail, barrel and plunger diameters, the hole (0.90) and pad (1.60) of the pin: the numbers of the mechanical model; only series, stroke and working height are RESEARCH |
| `PTC` | the order code and every rating of the example part |
| `SCREW_HOLE_DIA`, `SCREW_HEAD_DIA` | 2.2 mm hole (what the mechanical model drills), 4.0 mm head: an M2 thread-forming screw that has not been selected |
| J1 | body envelope 8.94 x 7.35 x 3.26 mm (mechanical model); that the KiCad land pattern's front (3.675 mm before its anchor) is the mouth of the shell; the four shortened ground pads of the project copy (section 6) against GCT's drawing |
| R1, R2, C1 | MPNs from memory |
| USB-C behaviour | Rd range, default current of a source, 4.75 V lower limit: from memory of the USB specifications |
| placement | nominal |

`netlist_out/gl1_cradle-bom-status.csv` carries the status of every BOM line.

## 6. Departures and additions

| Spec / task | Netlist | Why |
|---|---|---|
| (not in the spec) | C1 100 nF at U1 | the clamp's supply pin |
| "three service positions for the factory fixture" | the three pin footprints stay on the board, not fitted, and are also taken to four bare pads (with GND) | the task asks for a header or test pads; the fixture can use either |
| 2 layers | no plane is declared | the layout step decides whether the bottom becomes a ground pour |
| KiCad's land pattern for the USB4105 | a project copy with the four outer ground pads (A1 / B12, A12 / B1) 0.04 mm shorter: 1.11 instead of 1.15 mm | see below |

**The receptacle's land pattern.** KiCad's library footprint has 0.194 mm between each of its
two locating-peg holes (non-plated, dia 0.65) and the corner of the neighbouring ground pad.
The rule set asks for 0.20 mm from a hole wall to foreign copper, and KiCad's DRC reported
four `hole_clearance` errors on the bare board (the toolchain's own check skips this test for
a part that overhangs the edge, so it had not shown before). The rule was not touched:
`make_usb_footprint.py` copies the library file and shortens those four pads by 0.04 mm at
the end that faces the pegs, which gives 0.233 mm; `check_cradle_rules.py` verifies that the
stored copy differs from the library file in nothing else. PROVISIONAL: 3.5 % less pad
length on four ground pads, not checked against GCT's drawing.

Nothing was relaxed, excluded or waived.

## 7. Observations

- **Charger headroom is a system matter** (the fuse row of section 4 and the main-board notes, 4.1 and 8.1): the fuse of this board and the Schottky of the marker together take more than a compliant USB source at its low limit leaves. Raised with the spec owner; nothing in this netlist was changed for it.
- **No reference voltage for a debug probe.** The marker's 2.8 V rail is not on the seven pads, so the factory fixture's probe gets no VTref from J2; it has to be set to 2.8 V levels by itself.
- **The pins are live.** VBUS is on SP1 whenever a cable is plugged in (the spec decided against gating it); the fuse limits a short, nothing limits a slow leak.
- **Shield to ground.** The receptacle shell is tied straight to ground; a resistor-capacitor pair would be the alternative if the emissions test asks for it.
- **Where the board edge is under the receptacle.** KiCad's footprint draws its "PCB Edge" line at the front of the shell (3.675 mm before the anchor). The YAML puts the mouth 1.3 mm beyond the board edge (usb_mouth_y -35.5, board edge -34.2), so the shell overhangs by 1.3 mm. Copper is still legal (the rear shield pads end 0.40 mm from the edge); whether GCT allows that overhang is for the mechanical owner to confirm.

## 8. Not done

No copper and no routed board (the layout step); KiCad's DRC ran on the board without tracks only (0 errors, 29 unconnected items). No datasheet was read.
`mechanical/cad/board_import.py` checks the main board only; nothing in the mechanical package
checks this board's file.
