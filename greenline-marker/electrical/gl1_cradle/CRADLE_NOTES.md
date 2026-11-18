# GL-1 cradle board - netlist and layout notes

Stage: **layout**. Nothing has been built. The board is routed by the toolchain's router and
judged by KiCad's DRC (`build_gl1_cradle.py`, section 9); sections 1 to 8 are the netlist
stage (`build_netlist.py`, the board WITHOUT tracks) and still hold, with the two changes the
layout made marked "LAYOUT".

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
| `build_gl1_cradle.py`, `out/` | LAYOUT: one command - checks, rules, board with silkscreen legend, routing, KiCad DRC, fabrication and assembly outputs, schematic, quality figures (section 9) |

    /usr/bin/python3 -B electrical/gl1_cradle/build_netlist.py
    /usr/bin/python3 -B electrical/gl1_cradle/build_gl1_cradle.py      # about 15 s

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
| USB-C land | (KiCad DRC, rule set) 0.20 mm between a hole wall and foreign copper | J1 uses the project copy of KiCad's USB4105 land pattern: the four outer ground pads are 0.04 mm shorter; smallest distance from a locating-peg hole to a pad of J1 0.236 mm (library footprint: 0.194); one pad object per wide land instead of two coincident ones (B1 on A12, B12 on A1, B4 on A9, B9 on A4); the stored file equals the library file with exactly these changes *(DEVIATION from the maker's land pattern, PROVISIONAL; no design rule is relaxed. The merged pad objects are a workaround for the toolchain's router, which cannot join coincident pads; the copper is unchanged)* | **departure** |
| CC | 5.1 kohm from CC1 and from CC2 to ground | R1: CC1 (A5) - GND, R2: CC2 (B5) - GND, one resistor each | pass |
| fuse | a resettable fuse in VBUS (E6); E25: chosen for no more than 1.5 ohm after a trip (hold current 0.2 to 0.5 A) | F1 between VBUS_IN (J1 lands A4 / B9 and A9 / B4) and VBUS (SP1): hold 350 mA, trip 750 mA, 1.0 ohm at most after a trip (PROVISIONAL part 0603L035YR, ratings from the listing data in docs/SOURCING.md A5; trip 0.75 A departs from E6's 'about 0.5 A') | pass |
| ESD | USBLC6-2SC6 on VBUS / D+ / D- | U1: D- through pins 1 + 6, D+ through pins 3 + 4, pin 5 on VBUS_IN (C1 100n), pin 2 GND *(ADDED: C1 100 nF at the VBUS pin of U1; the clamp sits on the connector side of the fuse)* | pass |
| top side | nothing on the top side may reach the pocket ceiling (YAML note) | height limit 0.0 mm on the whole top side, J1 and SP1-SP7 exempt; every other part is on the bottom | pass |
| pin tables | (task) the pin -> pad table of every library-backed part agrees with a second source | U1 against the installed KiCad symbol USBLC6-2SC6, J1 against USB_C_Receptacle_USB2.0_16P (pad numbers and pin names): all agree *(the spring pins and the fuse have one or two interchangeable pads)* | pass |
| fiducials | (task) at least three global fiducials per side | FID1-FID3 top, FID4-FID6 bottom | pass |
| status | (task) every BOM part carries an evidence status | Part.fields['Status'] is RESEARCH or PROVISIONAL on all 13 BOM parts | pass |
<!-- END GENERATED: RULES -->

## 3. The circuit

    J1 USB-C  VBUS (A4/B9 A9/B4) --+-- F1 (PTC 0.35 A) ---- VBUS ---- SP1   pin 1  x = -7.62
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
| F1 | PTC, hold 0.35 A, no more than 1.5 ohm after a trip | spec E6 as amended by E25. See below |
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
| hold current | E25: 0.2 to 0.5 A. The example part holds 0.35 A at 23 C; a polymer PTC holds about 60 % of that at 60 C (PROVISIONAL): 0.21 A, seven times the load. It never trips in normal use |
| trip current | 0.75 A for the example part (E6 proposed "about 0.5 A"; E25 widened the hold window to get the resistance down). A hard short across the pins (a coin, a key) trips it on any source that delivers more than that; a USB 2.0 port limited to 0.5 A is protected by its own limiter instead. On a 1.5 A or 3 A charger it trips within a second or so (PROVISIONAL) |
| **resistance (E25)** | no more than 1.5 ohm after a trip. At 30 mA that is 0.045 V. With the marker's ideal-diode switch (E25, in place of the Schottky) the charger's input is 4.68 to 4.71 V from a 4.75 V source, 0.23 to 0.26 V above the 4.45 V minimum the research records (main-board notes, 4.1; every number PROVISIONAL) |
| voltage | 6 V or more. A sink with Rd only never sees more than 5.5 V |
| what it does not do | protect against a wet slot: water between the pins draws milliamperes and corrodes; no fuse sees that (spec). The marker must be dry before docking |

Part (changed after the layout review, per `docs/SOURCING.md` action A5): Littelfuse
0603L035YR (0603, 6 V, hold 0.35 A, trip 0.75 A, 1.0 ohm at most after a trip), which leaves
0.5 ohm under E25's limit. **PROVISIONAL**: the ratings are a distributor listing seen by the
sourcing report, not the data sheet. Second source on the same pads: Bourns MF-FSMF035X-2
(1.4 ohm from memory, 0.1 ohm of margin only). **Deviation**: the trip current is 0.75 A where
E6 proposed "about 0.5 A"; E25 widened only the hold range, and the sourcing report saw no
0603 part with a 0.5 A trip that meets 1.5 ohm. The REQUIREMENT is E25's: any 0603 PTC with a
hold current of 0.2 to 0.5 A, 6 V or more and no more than 1.5 ohm after a trip fits the
footprint. The ratings sit in the table `PTC` of the design file. `docs/sourcing.csv` row
cradle-02 still names MF-FSMF020X-2 (3.5 ohm, fails E25): for the sourcing owner.

## 5. PROVISIONAL items

| Table / item | What is not known |
|---|---|
| `MILLMAX_0914` | tail 0.635 mm and minimum mounting hole 0.737 mm are search extracts of Mill-Max data recorded in `docs/SOURCING.md` (cradle-05, action A6), not the drawing; the finished hole is 0.80 mm (it was 0.90 for an assumed 0.76 mm tail); pad 1.60, barrel and plunger diameters are still the mechanical model's assumptions. **OPEN: the tail is about 1.34 mm long (8.3 mm overall less 6.96 mm above the board, a subtraction of two extracts) in a 1.6 mm board**, so it would end about 0.26 mm inside the hole. To decide outside this package: the long-tail variant 0914-1-15-20-77-14-11-0 (about 2.8 mm stands out below the board: check the pocket) or a thinner board (YAML `cradle.pcb.thickness`, `top_z`). Do not order the board before that |
| `PTC` | the ratings of the part are a distributor listing, not the data sheet; height from memory |
| USB-C land | the four outer ground pads are 1.07 mm long, 0.04 mm shorter than KiCad's GCT USB4105 pattern, to keep 0.20 mm from the peg holes: to be confirmed against the GCT drawing |
| `SCREW_HOLE_DIA`, `SCREW_HEAD_DIA` | 2.2 mm hole (what the mechanical model drills), 4.0 mm head: an M2 thread-forming screw that has not been selected |
| J1 | body envelope 8.94 x 7.35 x 3.26 mm (mechanical model); that the KiCad land pattern's front (3.675 mm before its anchor) is the mouth of the shell; the four shortened ground pads of the project copy (section 6) against GCT's drawing |
| R1, R2, C1 | MPNs from memory |
| USB-C behaviour | Rd range, default current of a source, 4.75 V lower limit: from memory of the USB specifications |
| placement | final for this revision (section 9); nothing has been built |

`netlist_out/gl1_cradle-bom-status.csv` carries the status of every BOM line.

## 6. Departures and additions

| Spec / task | Netlist | Why |
|---|---|---|
| (not in the spec) | C1 100 nF at U1 | the clamp's supply pin |
| "three service positions for the factory fixture" | the three pin footprints stay on the board, not fitted, and are also taken to four bare pads (with GND) | the task asks for a header or test pads; the fixture can use either |
| 2 layers | no plane is declared; LAYOUT: ground is routed as 0.40 mm tracks, there is no pour | 29 connections on a 30 x 22 mm board; a pour would need thermal modelling the router does not have |
| KiCad's land pattern for the USB4105 | a project copy with the four outer ground pads (A1 / B12, A12 / B1) 0.04 mm shorter: 1.11 instead of 1.15 mm | see below |
| KiCad's land pattern for the USB4105 (LAYOUT) | the project copy has ONE pad object per wide land: A1, A4, A9, A12; the library's coincident duplicates B12, B9, B4, B1 are dropped. Copper, mask and paste are unchanged | workaround for a toolchain bug: the router cannot join two coincident pads of one net and then leaves the whole net open (section 9) |

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

- **Charger headroom is a system matter** (the fuse row of section 4 and the main-board notes, 4.1 and 8.1): the first fuse of this board and the Schottky the marker then had together took more than a compliant USB source at its low limit leaves; amendment E25 (ideal-diode switch on the marker, fuse of no more than 1.5 ohm) answers it. Raised with the spec owner; nothing in this netlist was changed for it.
- **No reference voltage for a debug probe.** The marker's 2.8 V rail is not on the seven pads, so the factory fixture's probe gets no VTref from J2; it has to be set to 2.8 V levels by itself.
- **The pins are live.** VBUS is on SP1 whenever a cable is plugged in (the spec decided against gating it); the fuse limits a short, nothing limits a slow leak.
- **Shield to ground.** The receptacle shell is tied straight to ground; a resistor-capacitor pair would be the alternative if the emissions test asks for it.
- **Where the board edge is under the receptacle.** KiCad's footprint draws its "PCB Edge" line at the front of the shell (3.675 mm before the anchor). The YAML puts the mouth 1.3 mm beyond the board edge (usb_mouth_y -35.5, board edge -34.2), so the shell overhangs by 1.3 mm. Copper is still legal (the rear shield pads end 0.40 mm from the edge); whether GCT allows that overhang is for the mechanical owner to confirm.

## 8. Not done

No datasheet was read. `mechanical/cad/board_import.py` checks the main board only; nothing in
the mechanical package checks this board's file (`out/gl1_cradle-mechanical.json`).

## 9. Layout (LAYOUT stage)

`/usr/bin/python3 -B electrical/gl1_cradle/build_gl1_cradle.py` builds everything into `out/`
and exits 0 only if every stage passed: toolchain checks, the rule table with its self-test,
board, routing, KiCad DRC, outputs verified against the model, schematic round trip.

| | |
|---|---|
| board | 30 x 22 x 1.6 mm, 2 layers, rule set `US_2L_STD` (tracks 0.20 mm, supply 0.40 mm, clearance 0.15 mm, vias 0.50 / 0.25 mm) |
| placement | J1 and the seven spring pins on the top side at their YAML positions; F1, U1, C1, R1, R2 and the four service pads J2 on the bottom; three fiducials per side |
| routing | 29 of 29 connections, 9 vias, 127 mm of track (x1.10 of the spanning trees), router run time about 2 s |
| KiCad DRC | 0 errors, 0 unconnected; 1 cosmetic warning (`silk_overlap`: the "GND" label touches the pin-1 dot of J2). Nothing is excluded |
| outputs | Gerbers (2 copper layers, mask, paste, silkscreen, outline), drill (9 vias 0.25, 4 slots 0.60 for the shell, 7 holes 0.80 for the spring pins, NPTH 2 x 0.65 and 4 x 2.20), position file (10 rows), BOM 7 lines and the same BOM with a status column (`out/assembly/gl1_cradle-bom-status.csv`: 6 PROVISIONAL, 1 RESEARCH), netlist and mechanical JSON, STEP, renders, fab README |

**The mirror, checked.** The YAML lists the marker's pads seen from above: VBUS at x = -7.62 ...
NRST at x = +7.62. This board is drawn in the same frame, also seen from above, and its pins
stand on the top side and press upward on the marker's underside. A pin at board x meets the
pad at marker x: there is no mirror. SP1 (x = -7.62) is VBUS; rule row "pin row" measures the
pad centres and the self-test catches a mirrored row. The only mirrored view is the one from
below: on the bottom silkscreen VBUS is on the right, as the spec says of the marker's
underside ("seen from below, with the visor away from you, VBUS is on the right").

**Silkscreen.** Top side: "1 VBUS", "2 D-", "3 D+", "4 GND", "5 SWDIO", "6 SWCLK", "7 NRST"
under the pins and the board name. Bottom side: the pin name above every pin, the name beside
every service pad, the board name and revision. The toolchain has no board-level text; the
legend is written into the board file by `../gl1_main/silk_text.py` before the routing is
applied and before KiCad's DRC runs, so it is on the judged board and in the Gerbers
(`gl1_cradle_design.silk_legend()` is the list).

**Toolchain findings (reported, nothing in `electrical/tools/` was edited).**

- The router cannot join two pads of one net that lie on top of each other (KiCad's USB4105
  footprint has four such pairs). It reports the connection between the twins as "not routed"
  and then leaves the whole net open: the first run of this board made 22 of 33 connections
  with VBUS_IN and GND open. Worked around in the project copy of the footprint (one pad
  object per land); a reproduction with one footprint of three pads is in the layout report.
- `gleda.checks` skips the pad-to-hole test for a part with `allow_overhang=True` (found at
  the netlist stage, section 6).
- No board-level silkscreen text (above).

**Figures measured on the copper** (`out/layout_quality.md`): smallest gap from a via to a
top-side pad 0.269 mm (own net) and 0.170 mm (other net); smallest solder-mask web 0.200 mm
(between the receptacle's lands A9 and A12); routed copper 0.348 mm from the edge at least,
pads 0.236 mm from the locating-peg holes of the receptacle.

**Open for the mechanical owner**: the 1.3 mm overhang of the receptacle (section 7); the
Mill-Max pin dimensions (`MILLMAX_0914`): the holes are now 0.80 mm for the 0.635 mm tail of
the sourcing data, where `mechanical/cad/params.py` still assumes a 0.76 mm tail in a 0.90 mm
hole; the tail length against the 1.6 mm board (section 5); the M2 x 5 screw that bottoms
0.4 mm before its head seats (`docs/SOURCING.md` A20).

**Service pads (review)**: SP5 to SP7 and J2 carry SWDIO, SWCLK and NRST with no clamp and no
series resistor, like the marker's own pads (the specification names VBUS, D+ and D- only);
they are fitted in the factory fixture only. J2 has no reference-voltage pad and the seven
pads carry no always-on rail: a debug probe must be set to a fixed 2.8 V target level (that
PA13 / PA14 tolerate a 3.3 V drive is from memory, PROVISIONAL). A marker without its cell is
fed through the 20 mA charger in the cradle: enough for SWD programming, not for a camera
read; what the charger does with no battery connected has not been read.

**Reproducibility (review)**: the silkscreen legend group now gets its identifier from the
seeded generator (`gl1_main/silk_text.py`); two builds give byte-identical `.kicad_pcb` files.
