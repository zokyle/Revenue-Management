# GreenLine GL-1: release gates at revision E-EVT1

Written 2026-11-20 against `design/DESIGN_SPEC.md` rev E (EVT1, amendments E1 to E36) and
`design/master_params.yaml` rev E-EVT1.

Nothing in this project has been built, printed, assembled, measured or run on hardware. No
supplier has been asked for a quote, no document has been collected from a vendor, and nothing
has been ordered, certified or approved. This file lists what stands between the design package
and four orders. It adds no new engineering: every line is collected from a file of the package,
and that file is named in the last column. Where this file and its source differ, the source is
right and this file must be corrected.

## 1. Summary

A release gate is a question that must have a written answer before money is spent on something
that cannot be undone. The package is at the stage of a kitchen drawn on paper where the position
of the sink was sketched from memory: the drawing is complete and consistent with itself, but the
worktop must not be cut until someone has measured the real sink. Most gates below are of that
kind. A pin table, a land pattern (the copper pads a part is soldered to) or a part dimension was
written down from memory or from a search extract and is marked PROVISIONAL in the package. The
automatic checks of the package compare the design with itself. They cannot tell whether a pin
table copied from memory is the real one (`electrical/README.md`: "A wrong pin table passes every
check").

The four orders, in the sequence in which they would be placed:

```
 (a) prototype boards -> (b) enclosure and purchased parts -> (c) build the EVT units -> (d) sell
     43 gates                20 gates                             22 gates                   19 gates
```

| Group | Order blocked | What the order covers | Open gates | Of them, owner decisions |
|---|---|---|---|---|
| A | (a) ordering prototype boards | Main board, cradle board, board assembly | 43 | 13 |
| B | (b) ordering the printed enclosure and purchased parts | Printed tub and cradle, base plate, display, cell, glass, adhesives | 20 | 5 |
| C | (c) building EVT units | Assembly, firmware load, calibration, tests | 22 | 6 |
| D | (d) selling | Any sale, pre-order or public launch | 19 | 8 |
| | Total | | 104 | 32 |

A gate is listed once, in the group of the first order it blocks. The column "Blocks" names every
order it blocks. Groups are ordered from the most blocking to the least: nothing in group B can
be closed usefully while group A is open for the same part, and so on.

Gate numbers are names. They are not changed when a gate moves to another group or closes, so
the numbers inside a group are not consecutive. This file was first issued with 102 gates
(G-001 to G-102). On the same day three of them closed (G-069, G-070, G-082: section 10), six
were moved to the group of the first order they block (G-038, G-039, G-057 and G-059 to group A,
G-085 to group B, G-089 to group C), and five were added (G-103 to G-107). That gives 104 open
gates (102 less 3 plus 5).

What the counts mean in practice:

- Three decisions come before any hardware money is spent, and none of them needs hardware:
  whether to measure first how repeatably a dummy marker seats on turf, the number the device
  stands or falls on (G-103); whether to start the patent search now, as the compliance checklist
  advises (G-104); and whether to buy the long-lead parts at risk (G-105). The budget in the
  package is a size built from listings and assumptions, not a quote (G-059).
- Group A is mostly reading. 22 of its gates (G-001 to G-022) close when the owner obtains about
  twenty manufacturer documents (data sheets and outline drawings) and the design files are
  corrected from them. One of these, the camera data sheet, is called "the registered OmniVision
  datasheet" in the specification: it has to be requested from the maker or its distributor.
- The camera ball map is the gravest item (G-001). The ball map is the table that says which
  solder ball under the camera carries which signal. The table on the board is a stand-in: a
  plausible table put in so that the board could be routed, not the maker's table. If the real
  one differs, the two camera areas of the board, the tracks that lead out of them and the
  placement of their capacitors are redone.
- Group A also contains decisions that change the wiring of the board (its copper) and therefore
  cannot wait for the first boards: the ship-mode current (the model gives 12.9 microamps against
  a requirement of 5), the charge-temperature limit when no firmware runs, and a way out of the
  USB loader for a user without a PC (G-028 to G-030). The USB loader is the program that the
  processor's maker builds into the chip for loading new firmware over USB.
- Group B is mostly asking. No fabricator, assembler, print bureau or part seller has been asked
  anything. Three parts with one maker or one seller set the schedule: camera, display, cell.
- Group C is what must exist before a unit can be assembled and judged: fixtures that are not
  designed, and a firmware image that has never been linked for the processor (linking is the
  build step that produces the one file that can be loaded into the chip). The manufacturing and
  validation plans were re-issued against revision E on 2026-11-20; what is open about the
  documents is in G-106 and G-107.
- Group D is the compliance checklist, on which every line reads "Not started", and the measured
  evidence that only EVT units can give. EVT is the engineering validation test: the first
  hand-built units.

The status of the package is therefore: an EVT design package with 104 open gates, not a device
that is ready to manufacture. The phrase "US-sourceable" has its own gate (G-097). Of the 86
lines of the sourcing list, 64 are marked VERIFIED: 55 of the 72 purchased lines were seen
listed by a US distributor or seller (42 with a stock figure), and for 9 of the 14 custom parts
and outside services a US company was seen advertising that kind of work. No quote has been
requested. That says where a part can be bought, not where it is made.

Sources of the counts in this section: this file (the script check of the "Blocks" column is
described in section 10). Sources of the figures quoted: the firmware test log
`firmware/build/readme/test.log` (stamp 2026-11-20 19:31 UTC), `docs/SOURCING.md` sections 1.1
and 1.4, `docs/COMPLIANCE.md` "Read this first".

## 2. How to read the tables

Words used:

| Word | Meaning here |
|---|---|
| PROVISIONAL | From memory or from an unconfirmed search extract. The package's own word; kept wherever the source uses it. |
| PROPOSED | A requirement or limit that the specification states but that nobody has adopted or measured. |
| NOT MET | A requirement that the firmware or the supply model does not meet, pinned by a test that prints the figure. A model result, not a measurement. |
| Data sheet, drawing | The manufacturer's own document, read in full by a person, not a search extract. |
| EVT | Engineering validation test: the first hand-built units (ten are planned), built to find out what is wrong. |
| Ball map | The table that says which solder ball under a chip carries which signal. |
| Stand-in | A plausible value or table put in so that the design could go on; not the maker's. |
| Amendment | A numbered change to the specification (E1 to E36 at this revision). |
| USB loader | The program the processor's maker builds into the chip for loading firmware over USB. Also called ST's loader or the ROM loader in the sources. |
| Linked image | The one file that can be loaded into the processor. Compiling checks each source file; linking joins them into that file. |
| DECISION | The gate is a choice, not a missing fact. Only the owner can close it. |

Who acts:

| Name | Who |
|---|---|
| Owner | The owner of the project: obtains a document, sends a request, signs an order, or takes a decision. |
| Design | Whoever maintains the design files. Corrects the file once the evidence is in hand and re-runs the package checks. Design cannot close a gate without the evidence. |
| Board fabricator | The company that makes the bare boards and the FR-4 base plate. None is chosen. |
| Assembler | The company that solders the parts onto the boards. None is chosen. |
| Print bureau | The 3D-printing company for tub, cradle, baffle ring and the alternative base plate. None is chosen. |
| Part vendor | The maker or seller of a purchased part. |
| Test lab | An outside laboratory. |
| Attorney | A qualified lawyer. |

Blocks: a = ordering prototype boards, b = ordering the printed enclosure and purchased parts,
c = building EVT units, d = selling.

File names in the last column are relative to the package root. "elec" is `electrical/README.md`,
"mech" is `mechanical/README.md`, "fw" is `firmware/README.md`, "spec" is `design/DESIGN_SPEC.md`,
"SRC" is `docs/SOURCING.md`, "COMP" is `docs/COMPLIANCE.md`. "A3" and similar are the design
actions of SRC section 12; "issue 33" and similar are the open issues of fw. "COMP 4.1 item 4"
and similar name the subsection of COMP section 4 and the item number printed there (4.1 and 4.2
keep the item numbers of checklist revision 2; 4.3 has its own numbers 1 to 8).

## 3. Group A: before prototype boards are ordered (43 gates)

Figures in this group are from `electrical/README.md` (sections "Result", "Departures", "Known
weaknesses", "PROVISIONAL items that gate ordering boards"), `design/DESIGN_SPEC.md` (amendment
table and section 7), `design/master_params.yaml`, `electrical/gl1_cradle/gl1_cradle_design.py`,
`mechanical/cad/params.py`, `firmware/build/readme/test.log` and `firmware/README.md`; in section
3.5 also `docs/SOURCING.md`, `docs/VALIDATION_PLAN.md` and `docs/COMPLIANCE.md`.

### 3.1 Pin tables and land patterns taken from memory

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-001 | Camera OVM7692-RYAA: ball map, ball pitch (0.5 mm taken) and pad size (0.20 mm taken). The table on the board is a stand-in. If it is wrong both cameras are wired wrongly and the two arrays of pads, their fan-out (the tracks that lead out of them) and the placement of their capacitors are redone. | The registered OmniVision data sheet, read; `OVM7692_BALLS` corrected; main board rebuilt and its checks passed. | Owner obtains it from the part vendor; Design | a, c | spec section 7; elec gate table; mech part list item 1 |
| G-002 | Camera image orientation: which side of the package carries the 640-pixel axis. Both cameras stand at rotation 0 with the 3.47 mm side along x, which assumes it. If wrong, images are rotated by 90 degrees. | The same data sheet; placement of U2 and U3 confirmed or changed. | Owner; Design | a, c | spec section 7; elec gate table |
| G-003 | Charger BQ25101YFP: ball map and the 0.23 mm lands. | TI data sheet, read; `BQ25101_BALLS` confirmed. | Owner; Design | a | spec section 7 (E1); elec gate table |
| G-004 | Charger temperature thresholds against the chosen thermistor (Murata NCU15XH103F60RC). The firmware model uses 0 / 10 / 45 / 60 C and a one-constant curve; no resistance-temperature table of the part was read. | TI data sheet table and Murata's resistance-temperature table, compared at each threshold. | Owner; Design | a, c | spec section 4 (E1, E2); fw "PROVISIONAL constants" and issue 5 (charge temperature: guard band and limits, which also waits for the cell data sheet of G-039) |
| G-005 | Ideal-diode switch LM66100DCKR (E25): pin table, polarity of the enable pin, and whether it blocks reverse current with the enable pin tied to its output. From memory. | TI data sheet, read; `LM66100_PINS` and the wiring confirmed. | Owner; Design | a | spec E25 and section 7; elec gate table; A7 |
| G-006 | Display tail: pin order and which edge of the tail is pin 1 (E28). A wrong guess mirrors all ten display pins. | Sharp LS013B7DH03 outline drawing, read; `LCD_TAIL` and `LCD_TAIL_PIN1_EDGE` confirmed. | Owner; Design | a, c | spec E28 and section 7; elec gate table; fw "PROVISIONAL constants" |
| G-007 | Display connector J1: the top-contact part FH12A-10S-0.5SH(55) stands on the land pattern of the bottom-contact FH12; that it fits, its pin numbering and its 2.0 mm height are unchecked. | Hirose FH12A drawing, read. | Owner; Design | a | elec gate table; A15 |
| G-008 | Display tail geometry behind J1 (E24): free length, permitted bend radius, where the fold lies. The keep-out `tub_keepouts.lcd_tail` (y from -21.1 to -17.3, parts at most 0.7 mm tall) is `basis: provisional`. If the fold does not fit, the fallback is a different connector (a 1.0 mm high back-flip part), which was not searched for at any seller. | Sharp drawing giving at least a free tail of 10 mm plus the insertion depth of J1 and a bend radius of 1 mm or less; then the mock-up trial of G-066. If the fallback is taken: a new footprint and a source. | Owner; Design | a, b, c | spec E24; mech section 12 (B16) and open issue 9; SRC section 11 item 21 |
| G-009 | Photodiode VEMD8080: land pattern. | Vishay drawing, read; `VEMD8080_PADS` confirmed. | Owner; Design | a | elec gate table |
| G-010 | The 16 grain LEDs (VLMS1500-GS08 and SFH 4053B) stand on KiCad's generic 0402 LED pattern with pad 1 taken as the cathode. If wrong, all 16 are reversed. For the SFH 4053B no extract states the 0402 package, and its wavelength is 850 nm in some extracts and 860 nm in others. | Both data sheets, read: package, pad layout, polarity mark, wavelength. | Owner; Design | a | elec gate table; spec section 4 (E3); A9 |
| G-011 | Crystal ABS07 on the Epson FC-135 land pattern. | Abracon drawing against the pattern. | Owner; Design | a | elec gate table |
| G-012 | Axis map of the tilt sensor U4 (turned 90 degrees on the board). The map assumes that ST's axis drawing matches KiCad's LGA-14 pattern at rotation 0, which was not read. If wrong, the slope direction is wrong by 90 degrees. | ST data sheet axis drawing, read; later a tilt reading on a board (G-067). | Owner; Design | a, c | elec "What the firmware must take from this board"; fw issue 62 |
| G-013 | Cell leads: BT1 = VBAT at (-18.4, -2.7), BT2 = GND at (-18.4, -5.8). No source says which lead of the cell GM201030-PCB is where, or where the leads leave the cell. | The seller's data sheet or drawing of the cell with its protection board (see G-039). | Owner asks the part vendor; Design | a, c | elec gate table; mech section 12 (B15) |
| G-014 | Cradle spring pin Mill-Max 0914. Tail length: about 1.34 mm is a subtraction of two search extracts (8.3 overall less 6.96 above the board); amendment E36 made the cradle board 1.0 mm so that the tail comes 0.34 mm through; if the real tail is shorter than 1.2 mm the joint has no fillet. Tail and hole diameter: the cradle board is built for a 0.635 mm tail in a 0.80 mm finished hole, the mechanical model draws a 0.76 mm tail in a 0.90 mm hole, the YAML has no key for either and no check compares them. Barrel and plunger diameters are also unconfirmed. | Mill-Max drawing, read. Then one pair of keys in `design/master_params.yaml` (tail diameter, hole diameter) that both `electrical/gl1_cradle/gl1_cradle_design.py` and `mechanical/cad/params.py` read, and both packages rebuilt. See section 8 for why the keys were not added with this file. | Owner obtains the drawing; Design | a, b | spec E36 and section 7; YAML `cradle.pins`; elec gate table and "Changes needed in other packages"; mech section 11 and section 12; `mechanical/PROPOSED_PARAM_CHANGES.md` part D row 4; A6 |
| G-015 | Cradle USB-C receptacle GCT USB4105: the four outer ground pads are 1.11 mm long, 0.04 mm shorter than the 1.15 mm of KiCad's pattern (a recorded departure); the part envelope is PROVISIONAL. Screw hole and head size for the cradle board are generic. | GCT drawing, read; screw chosen (G-055). | Owner; Design | a, b | elec "Departures" and gate table; mech part list items 21 and 24 |
| G-016 | Cradle fuse Littelfuse 0603L035YR: hold 0.35 A, 1.0 ohm after a trip, trip 0.75 A are listing data, not a data sheet reading. | Littelfuse data sheet, read. | Owner; Design | a | elec gate table; A5 |

### 3.2 Facts about the processor and the passives

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-017 | Processor STM32U585: the data sheet paragraph on raising VDDUSB before VDD (the reason for E26) is from memory. | ST data sheet paragraph, read. | Owner; Design | a | spec E26 and section 7 |
| G-018 | Processor: the pins that ST's built-in loader drives (PB9 and PA6 are camera nets), the electrical limits, USB without a crystal, that PH1 is a 5 V-tolerant pin, the analog input on PC4. | ST data sheet, reference manual and loader application note, read. | Owner; Design | a, c | elec gate table (last row); fw issues 4, 10 and 36 |
| G-019 | Ship mode with PB5 and PB14 floating: a possible 27 microamps through R13 if the processor's dead-battery switch acts in Shutdown. PROVISIONAL; the reference manual RM0456 was not read. | RM0456, read; if the path exists, a board change. | Owner; Design | a | elec `open_items_for_firmware` |
| G-020 | Capacitance left under working voltage (DC bias) of every 1 uF, 2.2 uF and 4.7 uF 0402 capacitor. The figures in the package are from memory. A larger case would be a footprint change. | The makers' DC-bias curves of the fitted part numbers, checked against what the regulators U7, U8, U11 and the charger U9 need. | Owner; Design | a | spec E27 and section 7; A3 |
| G-021 | Enable-pin current of the LP5907 regulator U11 (2.8 microamps assumed in the supply model) and the order code of LP5907MFX-3.3/NOPB. | TI data sheet; the live US distributor page. | Owner; Design | a, b | fw issue 35; A8 |
| G-022 | Order codes of the passives and approved second sources. Every BOM line is VERIFIED as a listing only; the column "Design evidence" is PROVISIONAL on 31 of 37 main-board lines and 6 of 7 cradle lines. No alternate is approved. The status BOM also keeps availability doubts: medium for the processor STM32U585RIT6 and the flash memory MX25R6435FZNIL0, and a conflicting life-cycle flag for the 100 nF capacitor GRM155R71C104KA88D. | Each line read on a live page; the alternates column approved line by line; the life-cycle status of the three parts named read on the maker's page. | Owner; Design | a, b | elec "Result" (Outputs row), gate table and "Sourcing actions"; A4, A17, A18 |

### 3.3 Questions for the board fabricator and the assembler

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-023 | Whether a fabricator accepts 0.100 mm track and 0.100 mm gap on three layers (F.Cu, In2.Cu, B.Cu) inside the two fine areas: 218.3 mm of such track on 28 nets. 0.100 mm is 3.94 mil, just under the common "4 mil" (0.1016 mm) tier. | The fabricator's written acceptance; the quote request must name all three layers. | Owner asks; Board fabricator answers | a | spec E7, E35 and section 7; elec gate table |
| G-024 | Via hole: 0.25 mm is meant as the drill size on a 0.50 mm pad (finished about 0.20 mm). The fabrication notes call it "finished hole". Read as the finished hole, the ring falls to 0.075 to 0.10 mm. Plugging of vias is text in the notes, not geometry. | The fabricator's written reading of the drill table and of the plugging note. | Owner asks; Board fabricator | a | elec gate table and "Toolchain limits" |
| G-025 | No quote has been requested for the bare boards or for assembly. The companies named in the sourcing report were seen advertising such work; none was asked whether it takes this job. | Written quotes for both boards and for assembly. | Owner; Board fabricator; Assembler | a | SRC section 8 and section 11 item 20 |
| G-026 | Assembly questions with no answer: flash memory on tray or reel (A14); oven limits, number of reflow passes and lens protection for the camera cube, which is soldered with its lens on and needs X-ray; the workmanship standard. | The assembler's written answers; the camera data sheet's reflow section. | Owner; Assembler; Part vendor | a | A14; `docs/MANUFACTURING_PLAN.md` (plan revision 3) section 10 gaps 10 and 11 |
| G-027 | The board files come from an in-house toolchain. KiCad's geometric rule check passes with 0 errors, but KiCad's electrical rule check is not run and the schematic is a generated drawing. The limits are listed in `electrical/tools/README.md` section "Limitations". The package names no closing evidence for this item. | PROPOSED here: a person qualified in electronics reads the schematic sheets and the footprints against the data sheets of G-001 to G-016 and signs the review. | Owner commissions it | a | elec "Toolchain limits to know before trusting the files" |

### 3.4 Owner decisions that change the boards

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-028 | DECISION. Ship-mode current. The requirement (E23, PROPOSED) is 5 microamps at the cell. The supply model gives 12.9, of which the always-on parts of the board alone are 9.6 and the firmware controls 3.3. At 12.9 microamps 30 % of the cell lasts 42 days, not 3 months. Meeting 5 needs a board change; the other choice is to relax the requirement. | A written decision; then either a changed netlist or a changed E23. | Owner | a, d | `firmware/build/readme/test.log` line 444; fw "Status" and issue 33; spec section 6 (E23) |
| G-029 | DECISION. Charging when no firmware runs (the built-in USB loader, or a hung firmware). Three things are NOT MET in the model for hardware alone. (1) The charger then keeps its own window of 0 to 60 C, not the 0 to 45 C the firmware enforces: at 50 C it charges for the 33 s of a hang and for the whole time in the loader. (2) With the charger's thermistor open and no firmware there is no window at all. (3) While the USB loader runs the charge never ends: the loader is taken to draw 4.0 mA (a guess), more than the charger's end threshold of 1.98 mA, so after 9 h the charger still delivers 4.05 mA into a full cell. What would end it is the charger's own safety timer, taken as 10 h from memory of the chip family (PROVISIONAL: whether the part has one is not confirmed). All of this is the simulator's model of the chip, thresholds PROVISIONAL. | The TI data sheet (G-004), read for the temperature thresholds and for the safety timer; the cell data sheet (G-039) for what the cell allows; a written decision to accept the charger's behaviour in these states or to change the hardware. | Owner | a, d | test.log lines 294, 297, 383, 386; fw "Charger and cell temperature" (state table) and issue 2; COMP row 14, 4.1 item 4 and 4.3 item 3 |
| G-030 | DECISION. Once a unit is in ST's USB loader, only a PC with ST's update tool or a flat cell gets it out: the cell is sealed in and the cradle has no reset contact. For a user with a wall charger E34's "cannot strand a unit" is NOT MET. One of the two answers on record is a reset path in the cradle, which is a hardware change. | A written decision between a reset path in the cradle and a watchdog on the loader path. | Owner | a, c | fw "Boot stub" and issue 59; spec E34 |
| G-031 | DECISION. The three service pads SWDIO, SWCLK and NRST reach the processor with no clamp and no series resistor. The specification names a clamp only for VBUS, D+ and D-. Wanted amendment, not decided: a clamp, series resistors and an NRST capacitor at the pad. | An amendment to the specification, or a written acceptance as an EVT limitation. | Owner | a | elec "Known weaknesses" and "Changes needed in other packages" |
| G-032 | DECISION. Four things are on the board that no amendment covers: vias tented on the top side as well as the underside, a fifth test pad TP5, a second fine class "CamPower" (0.15 / 0.10 mm), and no rule for the distance from a camera supply ball to its capacitor. The electrical README also asks the mechanical package to consider a tolerance margin on the outer faces of the post-foot keep-outs; no decision is recorded. | Each adopted in the specification or removed from the board; the keep-out margin adopted or declined in writing. | Owner | a | elec "Departures" and "Changes needed in other packages" |
| G-033 | DECISION. The cradle fuse trips at 0.75 A where E6 says "about 0.5 A"; its 6 V rating has no margin over a 5.5 V bus; the 1206 fallback part was not adopted. | E6 reworded to 0.75 A, or the fallback part taken (a footprint change). | Owner | a | elec "Departures"; spec section 4 (cradle board); A5 |
| G-034 | DECISION. Camera supply decoupling. The reviewers asked for a 100 nF capacitor within about 2 mm of every supply ball; the routed paths are 4.2 to 9.9 mm. The electrical README says it is to be done again with the real ball map, by hand if the router cannot. | After G-001: a new layout and its `layout_quality.md`, or a written acceptance for EVT. | Owner; Design | a | elec "Result" and "Known weaknesses" |
| G-035 | DECISION. Known layout weaknesses that are not fixed: the photodiode net PD_K has no guard and four nets cross it on layer 3; layer 3 is not a plane and 46 % of the bottom-layer track has no copper above it; no stitching vias; the pixel clock of the left camera is 99.5 mm long; the USB lines D- 41.7 mm and D+ 41.2 mm run up to 13.6 mm apart and are not a coupled pair; no reference designators on the silkscreen. | A written acceptance as EVT limitations, or a hand layout. The emissions pre-scan of G-083 is the first measurement that would show the cost. | Owner | a, d | elec "Result" and "Known weaknesses" |
| G-036 | DECISION. First programming is by SWD through the factory fixture only: BOOT0 has no pad, the seven pads carry no always-on rail, and a board without its cell gets at most the charger's 20 mA in the cradle. | A written acceptance, or a pad added. | Owner | a, c | elec "Known weaknesses" (bring-up access) |

### 3.5 Supply, money and three decisions to take before any hardware money is spent

G-038, G-039, G-057 and G-059 stood in group B when this file was first issued. Their "Blocks"
cells have always named order (a), so by the rule of section 1 they belong here. G-103 to G-105
are new. They record three points on which other files of the package give advice that this
file's sequence did not carry.

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-103 | DECISION. Whether the seating test with a dummy marker is run, and its result accepted, before prototype boards are ordered. Test S0 of the validation plan measures how repeatably the puck seats on turf, using a printed shell loaded to the marker's mass. It needs no electronics (the plan: "can start now") and the plan puts it at a few printed shells and a week (a planning figure; nothing is timed and no price is given). The simulation ASSUMED a seating scatter of 2.5 mrad. In the simulation a Quick Read is level with a golfer who reads slope to 0.5 % at 2.5 mrad, about 5 points of holed putts behind that golfer at 5 mrad, and no better than a golfer who reads to 1 % at 7.4 mrad. The plan's PROPOSED bands: green at most 2.5 mrad, amber 2.5 to 5 mrad, red above 5 mrad ("no single-placement mode holds its simulated standing"). The specification's own estimate, 2 to 5 mrad, is unmeasured. | A written decision: either the S0 record, the band it falls in and the owner's go-ahead, or a decision to order boards without it. The few dummy shells and plates that S0 needs are not order (b). | Owner; Design prepares the dummy markers | a | `docs/VALIDATION_PLAN.md` sections 1.1 and 1.2, tests S0 and S1, section 4 (decision point 1); `sim/results/REPORT.md` sections 1 and 4.1; spec section 2 |
| G-104 | DECISION. Whether the patent search (G-096) and the choice of markets (G-098) are started before prototype boards are ordered. The compliance checklist puts "Book the patent attorney" in the first column of its order of work, headed "NOW (costs nothing)", and gives the reason: the patent search is the one item that can stop the product outright, and it does not depend on any hardware. The checklist's own PROVISIONAL reading of the EU battery rule is that the GL-1 as designed is unlikely to be sellable in the EU after 18 February 2027. The package holds no cost for the search or for the attorney. | A written decision; if yes, the attorney engaged and the search begun. G-096 and G-098 stay in group D, because their evidence is needed before a sale. | Owner; Attorney | a | COMP section 5, row 34 and section 3 |
| G-105 | DECISION. Whether long-lead parts are bought at risk, before groups A and B are closed. The sourcing report advises an early purchase (its sections 1.2 and 12.4 step 3: the display first, then the camera cubes), because the listings show a factory lead time of 28 weeks for the display and of 14 weeks for the camera on the distributor's page (20 on an aggregator). Those are listings, not quotes. The sequence of this file places purchased parts after groups A and B, and the manufacturing plan says that no order may be placed until the gates that apply to it are closed. Our reading of what is at risk: a wrong ball map (G-001) or tail pin order (G-006) changes the board, not the part bought; the money is lost if the project stops (G-103, G-104), if the lens data (G-041) or a life-cycle statement (G-038) leads to another camera, or if the display tail cannot be folded and the display itself has to change (G-008 names only a connector fallback). The cell is not part of any early purchase: it has no data sheet (G-039), and the checklist asks for its transport and safety papers before cells are ordered in quantity (G-040). | A written yes or no for the display and for the camera cubes, with quantities. Until it is taken, the sequence of this file holds and SRC sections 1.2 and 12.4 are advice subject to it. | Owner | a, b | SRC sections 1.2, 12.4, A10 and A11; `docs/MANUFACTURING_PLAN.md` section 2; COMP row 9 |
| G-059 | DECISION. The money, and in what stages it is released. The sourcing report's budget is built from listings and assumptions; none of it is a quote. One marker and one cradle at 10 units: about USD 896 (62 % of it rests on assumptions). The first-build (EVT) programme: parts and outside services about USD 17,000; fixtures and gauges USD 8,000 to 15,000 (assumed); together about USD 25,000 to 32,000 before test equipment and labour. About 36 % of the EVT figure rests on a price seen. Not in that figure, by the report's own list: the test equipment and lab time of the validation plan, the formal emissions test, labour, freight, tariffs and tax. The package holds no figure at all for: obtaining the documents of group A; the electronics review proposed in G-027; the attorney (G-096, G-104); labour (the manufacturing plan's estimate of about 410 minutes of hands-on work per unit is untimed, and it says that fixture making, trials, fault-finding and finishing the firmware are larger than the build and are not estimated); and any schedule. | A staged budget built from quotes, with a written go-ahead for each stage: the spend to close group A; the spend to first boards; the spend to ten units. It names the stop points: the result of G-103, and decision point 1 of the validation plan ("Red: stop field aim tests, review with the owner"). Quotes in hand (G-025, G-042, G-051). | Owner | a, b | SRC sections 1.1, 10 and 10.5; `docs/MANUFACTURING_PLAN.md` section 9; `docs/VALIDATION_PLAN.md` section 4 (schedule, decision point 1) |
| G-038 | Camera cube supply: one maker and one authorised US distributor, whose pages showed 1,814 and 2,497 in stock; no price between 1 and 2,500 pieces; no maker statement on its life cycle. | A written life-cycle statement and a quote; the action asks for both before the layout is frozen. | Owner; Part vendor | a, b | SRC section 1.2 and A10 |
| G-039 | Cell PowerStream GM201030-PCB: one US seller, no stock figure, no lead time, no data sheet seen. Unknown: length with the protection board, greatest delivered thickness, swelling at end of life (the bay has 0.15 mm in hand), storage and process temperature limits, protection thresholds, the cell maker. No second US seller of such a cell was found in three searches. It is on no purchasing list. | A dated quote and the data sheet from the seller; the cell entered on a purchasing list. | Owner asks; Part vendor | a, b, c | spec section 7; mech section 12 (B15) and open issue 13; SRC section 1.2, A12 and section 12.2 item 16 |
| G-057 | Every stock figure and price in the sourcing report is an undated search extract. Of 86 lines, 22 are PROVISIONAL, and 13 of the 64 VERIFIED lines were listed with no stock figure. For 17 of the 55 purchased lines marked VERIFIED, the `us_source` cell of `docs/sourcing.csv` says that one or more of its listings was seen on a distributor's page for another country, on an aggregator's copy or on a category page (counted for this file by a text search of that column). For one of them, main-34 (U11, LP5907MFX-3.3/NOPB), the cell reads "regional pages only: the US page was in no result". | A live US page read, or a quote, for each line on the day of the order. | Owner | a, b | spec section 7 ("every distributor stock check"); SRC sections 1.1, 2.1 and 11 |

## 4. Group B: before the printed enclosure and the purchased parts are ordered (20 gates)

Figures in this group are from `docs/SOURCING.md` (report revision 4; every listing, price and
stock figure is a snapshot of 2026-11-13 or 2026-11-11 from search extracts, not a quote),
`mechanical/README.md` sections 2, 4, 11 and 12, and `mechanical/export/check_report.md`.

### 4.1 The display and the cell papers

Three parts set the schedule: camera, display, cell. The camera supply (G-038) and the cell
data (G-039) also block the board order and are in section 3.5.

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-037 | Display Sharp LS013B7DH03: one maker, a 28-week factory lead time, shelf stock not established (undated copies of one distributor's page ran from 0 to 32,134). Its thickness is 0.741 mm in the extracts against 0.746 mm in the design. It is on no purchasing list. | A live stock reading or a phone call; the life-cycle status in writing; the thickness from the Sharp drawing; the display entered on a purchasing list. | Owner; Part vendor | b, c | SRC section 1.2 and A11; SRC section 12.2 item 6 |
| G-040 | Cell papers: no transport test summary and no safety certificate for the cell with its protection board has been seen. The compliance checklist asks for them before any cell is ordered in quantity. | The documents named in COMP rows 9 and 13, from the seller; if none exists, a lab test or another cell. | Owner asks; Part vendor; Test lab if the vendor has none | b, d | COMP rows 9 and 13 and 4.2 item 5; spec section 7 |

### 4.2 Enclosure

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-041 | Camera lens data: position and diameter of the entrance pupil are assumed. The guaranteed upward field is 14.0 degrees and the model gives 14.03, a margin of 0.03 degree. A pupil of diameter 0.40 mm gives 13.86 and a pupil 0.5 mm lower gives 13.61, both under the guarantee. The roof and the camera openings of the tub depend on it. The guaranteed case also rests on an estimated drop of the roof of 0.02 mm that the YAML does not carry: the mechanical package proposes a key `roof_drop: 0.02` in `cameras.up_guaranteed_case` ("the guaranteed figure depends on this number as much as on the fit"), not adopted. | The lens data from the camera data sheet (G-001); the roof-drop key adopted or declined; mechanical check 4 re-run. | Owner obtains it; Design | b, c | spec E17 and section 7; mech section 12 and open issue 1; `mechanical/PROPOSED_PARAM_CHANGES.md` part D item 3 |
| G-042 | Print bureau: whether 0.8 mm walls survive vapor smoothing; the print orientation; whether seal face and rim can be held within +-0.1 mm from the post feet when the quoted general tolerance is +-0.3 mm or +-0.3 %. No bureau has been asked. | The bureau's written confirmation on the order; then first articles (G-064). | Owner asks; Print bureau | b | mech section 4.2 and open issues 21 and 26 |
| G-043 | Alternative printed base plate (0.87 mm PA12), needed for 4 of the 10 EVT units: no bureau has been asked whether it can hold thickness and flatness on such a plate. | The bureau's answer. | Owner asks; Print bureau | b | SRC section 12.2 item 20 |
| G-044 | FR-4 base plate: the build-up for 0.80 mm over the mask, the thickness tolerance (plates are accepted from 0.78 to 0.90 mm) and the web rule are to be confirmed by the fabricator. | The fabricator's written confirmation; first-article thickness. | Owner asks; Board fabricator | b | mech section 4.1 and section 12 |
| G-045 | Legend on the base plate: the print rules (line 0.15 mm, text 1.0 mm, space 0.15 mm, registration 0.15 mm, ink 0.02 to 0.03 mm high) are assumptions until the quote. The five text blocks on drawing GL1-011 are placeholders. CONTRADICTED in the package: how much text the two statement blocks hold. `mechanical/README.md` section 4 item 9 says the two blocks (11.5 x 7.8 mm each) hold 88 characters at 1.0 mm, "four lines of eleven each", and its section 12 says 88 "between them", which is 44 a block. The specification (E18) and a comment in `design/master_params.yaml` say that each block holds 88. `firmware/README.md` speaks of "four statements of 88 characters". `mechanical/export/check_report.md` check 15 says only "statement blocks hold 88 characters". The difference is a factor of two in the room for the required statements. This file does not pick a value. | The character cells of each block counted on drawing GL1-011 and in mechanical check 15; then whichever of the specification, the YAML comment, the two READMEs and COMP is wrong corrected. The fabricator's legend rules in writing. The real text from the compliance work (G-085), fitted to the blocks, and mechanical check 15 re-run; or a written decision that the EVT plates are ordered with placeholder text. | Owner; Board fabricator; Design | b, d | spec E18 and section 7; YAML comment above `legend`; mech section 4 item 9, section 12 and open issue 27; fw "The regulatory and information screen"; COMP rows 5, 4.1 item 1 and 4.3 item 8 |
| G-085 | DECISION. Regulatory text: the text of the INFO screen is a placeholder (the release gate refuses on it as well), the legend blocks on the base plate are placeholders, and the label route is not chosen. The checklist says to copy the statements word for word from the current regulation on the day the manual is frozen, and that freezing the text is a gate before the base plates are ordered and before any release build. How much text the legend holds is contradicted in the package (G-045). | The route chosen; the final text in `firmware/app/gl_regulatory.h`, on drawing GL1-011 and in the manual; the release gate passing. | Owner; Design | b, d | spec E10, E18; `firmware/build/release-gate-text.log`; fw issue 57; COMP rows 5 and 6 and 4.3 item 2 |
| G-046 | DECISION. Standing deviations D04, D06, D09, D11, D14, D18, D19 and D36 and the 23 warnings of the mechanical check report. Two matter for the order: the spigot fit of 0.075 mm is below the print tolerance (D19), and 0.47 mm of material is left above the two front cradle screw holes (D36). | A written acceptance before the print order. | Owner | b | mech section 11; `mechanical/export/check_report.md` |
| G-047 | Gauges that first articles need and that do not exist: the diameter 0.95 no-go gauge for the spigots that E17 names, and the go gauges of the part list. | The gauges made or ordered with the prints. | Owner; Design | b, c | mech section 2 (fixtures) and open issue 1 |

### 4.3 Purchased parts and materials

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-048 | No adhesive is selected. Nine classes have no product: perimeter seal, ball-foot potting (two stages), visor-window adhesive, clear potting of the grain opening, hood gasket, cover-glass rim sealant, prism adhesive, primer for the nylon faces, thermal adhesive for the two thermistors. The sourcing report names candidates as starting points for trial bonds, not selections. | A part number and a data sheet for each class; then the coupon tests of G-065. | Owner; Design; Part vendor | b, c | mech section 12 and open issue 10; SRC section 7 |
| G-049 | DECISION. Three open adhesive choices: whether the clear potting may cure at 65 C when the limit in the assembly sequence is 60 C (no candidate has a maker's full cure at or below 60 C); which window adhesive; whether a silicone is allowed at the cover-glass rim. | A written decision for each. | Owner | b, c | SRC section 1.3 item 11; A30, A31, A32 |
| G-050 | DECISION. Ball feet. No US listing with a grade or a price was found for a 1.0 mm ball in 316 stainless, grade 100. The only priced US source found is a silicon nitride ball at USD 2.37 each (a listing, not a quote). The diameter tolerance taken (+-0.0127 mm, E20) is from memory of the ball standard; the lower plate limits depend on it. | A choice of material; a supplier's certificate with the diameter tolerance of the lot. | Owner; Part vendor | b | spec E8, E20 and section 7; mech section 12 and open issue 28; A19 |
| G-051 | Visor windows (5.0 x 3.25 x 0.40 mm borosilicate): a custom part with no source, price or lead time. | A quote with the size tolerance and the edge-chipping limit. | Owner asks; Part vendor | b | mech part list item 7; A29 |
| G-052 | DECISION. Vent Gore VE80205: no US listing with a price or stock was found, and its water-entry pressure has not been seen. To decide: which requirement governs, 50 kPa or the about 10 kPa of an IP67 test. | The vendor's price, lead time and water-entry pressure; a written decision. | Owner; Part vendor | b | mech part list item 9 and open issue 17; A22 |
| G-053 | Tapes, film and foam: the trial film has no adhesive and none is chosen (A23); for the black tape under the baffle ring only one candidate has US listings, as full rolls, and its adhesive layers are clear (A24); the foam exists at 0.30 mm in one grade only, with no price seen (A26); the display frame tape is not recorded as selected (A27). No converter for the die-cut parts has been asked. | Each item selected with a part number; a converter's quote for the die cuts (`dxf/GL1-030` to `GL1-035`). | Owner; Design; Part vendor | b | mech part list items 6, 6a, 12 to 16; A23, A24, A26, A27 |
| G-054 | EVT cover glass (mineral watch crystal 28.0 x 1.0 mm): a US source is listed, tolerances not stated. | The seller's tolerances, or measurement on receipt. | Owner; Part vendor | b | mech part list item 5 |
| G-055 | Cradle hardware: no part number has been seen for the M2 x 4 thread-forming screw the model calls for; no self-adhesive foot of diameter 8 x 3 mm was found (the candidate is 2.16 mm high). | A screw part number read on the seller's page; the foot adopted and the drawing corrected. | Owner; Design | b | mech part list items 23 and 24; A20, A21; SRC section 1.3 item 9 |
| G-056 | Prisms Edmund Optics 32-526: the listing (USD 105 each at 1 to 5) was seen on 2026-11-11 and not re-checked. | A live page or a quote. | Owner | b | mech part list item 2; SRC section 11 item 20 |
| G-058 | There is no purchasing list above the two board BOMs. The display and the cell are on no list, and the list has no file and no owner. | A purchasing list file that carries every off-board item. | Owner; Design | b | elec "Sourcing actions"; A11, A12, A17 |

## 5. Group C: before EVT units are built (22 gates)

Figures in this group are from `firmware/README.md`, `firmware/build/readme/test.log` (stamp
2026-11-20 19:31 UTC; a host test log, no hardware), `mechanical/README.md` sections 2, 9 and 12,
`sim/README.md`, `sim/results/REPORT.md`, and the two plans in `docs/` (both at plan revision 3
of 2026-11-20, written against rev E).

### 5.1 Things that do not exist yet

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-060 | Fixtures and gauges. Drawn so far, as solids only: the two calibration seat plates and the ball gauge plate (GL1-050). Every other fixture and gauge has no drawing and no making method. The mechanical README lists six as not designed: the six-face calibration fixture; the display-rotation measurement; the LCD squaring pusher; the bridge gauge (a requirement with a checked footprint, not a design); the film lamination nest; a location for the four-position zero. The manufacturing plan lists more that are stated as requirements and not drawn: the lamination jig, the potting nest, the prism jig, the join fixture, the pogo test fixture (the spring-pin nest for board test), the leak tester, the gate 2 target and the go gauges (see also G-047). None has been made. The sourcing report budgets fixtures and gauges at USD 8,000 to 15,000; that is an assumption, not a quote, and it is about as large as half the parts budget of G-059. | A drawing and a making method for each fixture and gauge the EVT build uses; a quote for those made outside. | Design; Owner orders them | c | mech section 2 (fixtures) and section 12; `docs/MANUFACTURING_PLAN.md` section 2.2 (G15), section 5.3 and section 10 gaps 16 and 46; SRC section 10.5 |
| G-061 | No firmware image for the processor exists. The portable code is built and tested on a PC against a simulator. The STM32 backend is compiled only, never linked; its USB file is compiled by no target because ST's USB device library is absent; start-up code and linker script for the application do not exist. The serial link of the PC tool `glctl` to a unit is not verified either: the tool has only talked to the simulator. | A linked application image, loaded and running on a board; `glctl` talking to it over the cradle. | Design; Owner supplies the vendor files | c | fw "Status", "PC tool" and "What is not done" |
| G-062 | The boot stub (1536 bytes of its 8192-byte page) links and has never run. Its six hardware release gates are open: entry into ST's loader, write protection and option bytes, vector relocation with a linked application, backup registers and watchdog across Shutdown and the loader, the time of the image check, what a USB host sees. | Each shown on a board. | Design | c | fw "Boot stub" and "What is not done"; issue 46 |
| G-063 | Every constant in `firmware/core/gl_provisional.h` is unverified (camera registers, image orientation and timing; display pins and timing; processor sleep and USB assumptions; tilt-sensor wake; flash timing; charger; thermistor; cell thresholds), and every register of the tilt sensor and the flash is marked "from memory - verify against datasheet". Named in the firmware README and waiting for the same documents or for a board: whether both cameras drive the shared image bus against each other at power-up, which depends on whether the camera's power-down pin releases its outputs (issue 3); the idle camera kept awake during a read, and the camera's output size after reset (issue 13); whether the charger's status line shows a recharge (issue 39); that a tap wakes the real tilt sensor, and how soon it then delivers samples (NOT VERIFIED); the flash endurance figure behind the wear estimate (PROVISIONAL). | The data sheets of G-001 to G-018 read against the header; then readings on a board. | Owner obtains documents; Design | c | fw "Status", "PROVISIONAL constants", "Device registers and commands" and issues 3, 13 and 39 |
| G-089 | Serial number and traceability. The firmware derives a serial number from the processor's unique number (issue 41); two units can share one. The serial format for a unit for sale and the lot records that a recall needs are not defined; whether a derived number serves a recall is an owner decision in the checklist. | A serial-number scheme and label, and the lot record. | Owner; Design | c, d | COMP row 18 and 4.1 item 7; fw issue 41; `docs/MANUFACTURING_PLAN.md` section 10 gap 27 |
| G-064 | Tub first articles: seal face 0.60 and rim 1.55 from the post feet within +-0.1; spigots (go gauge diameter 1.10, D19); bore; a dummy unit seated on all eight posts. This cannot close before the prints are ordered; it must close before any adhesive is opened. | Gauge and measurement record of every tub on arrival. | Owner; Design | c | spec section 7 ("mechanical first-article fit"); mech section 12; `docs/MANUFACTURING_PLAN.md` section 2.2 (station T1) |
| G-065 | The seal, every adhesive joint and the visor-window bond are chosen by class and calculated, not tested. | The coupon tests of mech section 9 (tests 1 to 4, 9 and 11) on the real materials, with the products of G-048. | Design; Owner | c | mech section 9, section 12 test items 5 and 6, open issues 10, 12 and 15 |
| G-066 | Assembly trials before the first sealed unit: display tilt-in against the rear ribs; the hood gasket bead from the needle guide; mating the display tail with the unit open (9.7 mm free at 35 degrees against 4.3 mm when closed); a dry trial close. Not demonstrated. | The trials done on a mock-up and recorded. | Design; Owner | c | mech section 12 test item 8 and open issues 9, 24 and 30 |
| G-067 | Factory procedures and commands that do not exist: the four-position level zero; the stereo calibration procedure and its PC fit; the tilt-sensor self-test; the flash identity read-out; a command that holds the camera rail on; dark frames with fixed exposure; a way to read the charger's thermistor; setting a state of charge for shipping; a PC-side updater. Also: tilt is logged per placement only, not on demand or at intervals, so a chamber run with an untouched marker logs nothing (issue 51); and running the grain amplifier on a bare board without a display, which the dark-offset step 11a needs, is PROVISIONAL. | Each written and run, or struck from the plan in writing. | Design; Owner decides which the EVT build needs | c | fw "Station tests that still cannot be run", "What is not done" and issue 51; spec section 6 |
| G-068 | Process limits that no document sets: leak-test pressure, time and limit; the dark-frame limit; cleaning of the board underside before lamination; the number of extra shells for destructive tests. Listed as open in the manufacturing plan, revision 3 (gap 13 is closed in part there: the cleaning is step 11a, the solvent is open). | The limits written into the manufacturing plan. | Design; Owner | c | `docs/MANUFACTURING_PLAN.md` section 10 gaps 9 and 13 to 17 |

### 5.2 Documents: unread, overtaken or still proposals

G-069 and G-070 stood here and are closed (section 10).

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-106 | The documents under `docs/` and the top-level `README.md` were written, re-issued and cross-checked on 2026-11-20 by software agents. No person has read them against the design files. The cross-references between them were checked by text search, not by reading each target. The five Mermaid diagrams (two in `README.md`, three in `docs/MANUFACTURING_PLAN.md`) have not been rendered by anyone: their syntax was checked by rule only. | PROPOSED here: a person reads the build documents (the manufacturing plan and the validation plan) against the specification and the YAML before building from them, and views each diagram once in a Markdown viewer that draws Mermaid. | Owner; Design | c | this file section 10; `docs/MANUFACTURING_PLAN.md` section 11 items 10 and 11 |
| G-107 | Statements in the design files that the package itself has overtaken. They are outside `docs/` and were not edited with this file. (1) `design/master_params.yaml` `requirements`: `ship_mode ... modelled: false` and `reads_per_charge ... model_to_empty: 600`; the specification, section 6: "Ship mode: ... Not modelled yet" and "about 600 to empty". The firmware test log now holds a ship-mode model (12.93 microamps, 42 days from 30 %) and 594 read cycles. The specification says the YAML wins where the two disagree, so the stale entries matter. (2) Specification E15: "4.1 to 4.8 s"; the log gives 4.15 to 4.84 s. (3) Specification E32: the firmware stops the charge "after 6 hours of continuous charging"; the firmware counts six hours docked, whatever the charger's status says (see G-076). (4) `mechanical/README.md` open issue 13 still gives the cell fixing adhesive as 0.05 mm (0.06 since E22, which leaves 0.09 mm of air over a swollen cell, not 0.15); its section 4.2 item 7 gives the cradle pilot holes as dia 1.6 x 3 where three other places say 3.2. (5) `electrical/README.md`, "Changes needed in other packages": says the two plans are still the rev D plans and that `docs/RELEASE_GATES.md` was never written. (6) fw issue 15: specification text still to correct (the register table's "INT pins pulsed"). | Each entry corrected in its own file by whoever maintains that file, and the package checks re-run. | Design | c | the files named; `firmware/build/readme/test.log` lines 316 to 318, 322, 443 and 444; fw "End to end", "What the backstop costs" and issue 15; `docs/POWER_BUDGET.md` section 4 |
| G-071 | The simulation is still the revision C run and has not been re-run for rev E. One input is known to differ: the usable upward field is 17.6 degrees in the simulation and is guaranteed only to 14.0 degrees by the specification. That the simulation's own tests pass says nothing about rev E performance. | The Monte-Carlo run repeated with rev E optics and `sim/results/REPORT.md` regenerated. | Design | c, d | `sim/README.md`; `sim/results/REPORT.md` "Which hardware"; fw issue 58 |
| G-072 | DECISION. The battery-life and drop requirements of E23 are PROPOSED: at least 150 reads per charge at 20 C and 100 at 0 C or after 300 cycles; at least 45 days asleep; ship mode no more than 5 microamps and 3 months from a 30 % charge; a 1.0 m drop in six attitudes. The board-test limits of E14 are also PROPOSED (rails within +-3 %, sleep current no more than 25 microamps with the underside dark). | A written adoption as EVT targets; then measurement on EVT units (G-081). | Owner | c, d | spec E14, E23, section 4 and section 6 |
| G-073 | DECISION. This file and the specification disagree on one sentence: section 7 of the specification says that no separate `docs/RELEASE_GATES.md` exists and that section 7 with the package lists is the list. The same statement stands in `docs/SOURCING.md` section 12.2 item 4 (noted there on 2026-11-20) and in `electrical/README.md`, "Changes needed in other packages" ("`docs/RELEASE_GATES.md` was never written; the spec no longer points to it"). | One sentence of the specification corrected to name this file as the collected index, or this file withdrawn; the two other files brought into step. | Owner; Design | c | spec introduction and section 7; SRC section 12.2 item 4; elec "Changes needed in other packages" |

### 5.3 Requirements the firmware model does not meet

The stored host test log contains 21 lines with the words NOT MET; one of them (line 456) reports
a requirement that is now met. Five of the other 20 are in group A because they need a hardware
decision: line 444 under G-028 and lines 294, 297, 383 and 386 under G-029. The remaining 15 are
below: line 477 under G-074, line 467 under G-075, lines 350, 419 and 952 under G-078, and lines
1090, 1094, 1099, 1117, 1119, 1121, 1123, 1189, 1195 and 1215 under G-079. G-030 is also marked
NOT MET, in `firmware/README.md` (issue 59), not in a line of the log. All are results of a
simulator on a PC. To record a result as NOT MET, the firmware writes a test that prints the
figure; the sources call this "pinning".

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-074 | Sleep current. E14 allows 25 microamps through the cell-lead pads. The model gives 20.68 with the underside dark and without the display, for which no figure is known: the limit is met only if the panel draws less than 4.32 microamps with its DISP line low. With the underside lit the model gives 25.88. | The Sharp data sheet for the panel current; then a measurement on a board. | Owner obtains it; Design | c, d | test.log line 477; fw issue 61 |
| G-075 | DECISION. A USB host that keeps the bus running but says nothing for 30 s loses the marker until it is docked again (E32 as specified). | A written decision to accept it or to change E32. | Owner | c | test.log line 467; fw issue 34 |
| G-076 | DECISION. The 6-hour charge backstop counts time docked, not time charging. Six hours after docking it holds the charger off, also on a marker whose charge ended by itself hours earlier; charging restarts when the cell has fallen to the restart voltage (4.00 V, PROVISIONAL). Over 30 docked days the model's cell cycles between 100 % and 79.3 % while the screen says FULL. | A written decision on the restart voltage or on what the backstop counts. | Owner | c | fw "Status" and issue 60 |
| G-077 | Read time is a model. The result comes 4.45 s after the marker is at rest at the nominal compute factor (4.15 to 4.84 s over the range of the factor), and the factor between a PC instruction and a processor cycle is an estimate (1.5 to 3). The longest read with several lines in view kept the camera rail on for 3.36 s against the specification's 2.8 s; a near stick at the high factor is not re-measured. | Timing measured on a board; then E15 restated. | Design | c, d | fw "Status", "What is not done" and issue 1; spec section 6 (E15) |
| G-078 | DECISION. Vision and Survey cases pinned as NOT MET: a second post 14 pixels from the stick defeats more than half the reads (26 of 64 give a disparity); the class of the stick's base 3 m from the hole flips with the frame noise; a drift that reverses inside a group of four strips is not noticed; a Survey placement behind the ball is not used for the result at the ball; short-range and low-contrast cases listed in the README. | A written decision for each: accept for EVT, or change the method. Field reads on EVT units show how often each occurs. | Owner; Design | c, d | test.log lines 350, 419, 952; fw "What is not done" and issues 18, 22, 23, 30 |
| G-079 | Solver differences between the firmware's single precision and the reference: fallback cases 62 and 77, fallback solver cases 12, 13, 25 and 28, one near-miss vector shown as a normal result, and the tolerance on putts of 15 m and more. | A written acceptance, or a tolerance that grows with the putt (issue 25); the solver's arithmetic compared on the processor (issue 26). | Owner; Design | c, d | test.log lines 1090 to 1123, 1189, 1195, 1215; fw issues 25 and 26 |
| G-080 | DECISION. Firmware items waiting for the owner: camera exposure and clocking (no exposure, gain or frame-rate register is written; the sensors run on their reset settings); what the unit shows of a missing calibration; whether the grain setting, which ships off, stays visible to the user before the sensor has passed its validation gates; the tuning constants of gestures, Recall and "TOO STEEP", none tuned on hardware. | A written decision for each; the camera values need the data sheet of G-001. | Owner; Design | c | fw "What is not done" (Not implemented) and issues 44, 49, 52, 53; spec section 2 (grain); COMP 4.2 item 12 |

## 6. Group D: before anything is sold (19 gates)

Figures and rule references in this group are from `docs/COMPLIANCE.md` (checklist revision 3,
2026-11-20, written against rev E). Revision 3 made no web search: every legal point in it is
still the reading of 2026-11-11. That file is an engineering checklist, not legal advice, and
marks many of its own statements PROVISIONAL. Rule names are quoted from it as its reading; none
was checked again for this file. The status of every row in it is "Not started".

G-082 stood here and is closed (section 10). G-085 is in section 4.2 and G-089 in section 5.1,
because each blocks an earlier order as well.

| ID | Unknown or undecided | Evidence that closes it | Who acts | Blocks | Recorded in |
|---|---|---|---|---|---|
| G-081 | Nothing has been measured. Every performance figure in the package is a model or a result on synthetic data. The validation plan's tests on EVT units are the evidence for every claim, among them the tilt drift of the board and base laminate with temperature and humidity on both base-plate variants, the footstep tests (the EVT units are not step-proof), the cradle latch cycles and the light-leak tests. | The test reports of the validation plan (revision 3), run on EVT units. | Owner; Design; Test lab where the plan asks | d | spec section 7 first sentence; mech section 12 test items 1 to 8; `docs/VALIDATION_PLAN.md` |
| G-083 | DECISION and test. Radio interference: which procedure is chosen, who the US responsible party is, which accredited lab, and the emissions test itself in two set-ups, preceded by a pre-scan on an EVT unit. | The written decisions; the lab's test report naming unit, firmware version, cradle and cable. | Owner; Test lab; Design supplies a test firmware | d | COMP rows 1 to 4 and 7 |
| G-084 | USB vendor and product ids: none is assigned. The firmware carries the placeholders 0xFFFF and 0x0000, and `make release-gate` refuses a release build while they stand. | An assigned vendor id or a sub-licensed product id, entered in `firmware/app/gl_usb_ids.h`; the release gate passing. | Owner | d | spec E34 and section 7; fw "Boot stub"; `firmware/build/release-gate.log`; COMP row 16 |
| G-086 | Shipping a product with a lithium cell: no shipping instruction exists; the checklist advises shipping at about 30 % charge, and no way exists to set a state of charge at the factory (G-067). A new marker does nothing until it is docked once, because it leaves the factory in ship mode; the quick-start card and the box must say so. | The one-page shipping instruction; each carrier's rules; the cell papers of G-040. | Owner | d | COMP rows 10 to 12 and 4.3 item 5 |
| G-087 | Charger energy rules: whether the product is in scope is not known. | A lab's written answer on scope, test and filings. | Owner; Test lab | d | COMP row 17 |
| G-088 | Consumer product safety: no written procedure for receiving complaints and reporting a hazard; the conclusion that no listed rule applies has not been checked by a qualified person; the question on the button-cell rule has not been put to the regulator; the warnings wait for the cell data sheet. | The procedure; the qualified person's answer on file; the regulator's written answer; the warning texts. | Owner; Attorney | d | COMP rows 18 to 21 |
| G-090 | State rules as the checklist reads them: supplier statements for the California warning law; the California law on products with a built-in battery; other states' battery laws; the fluoropolymer vent, which the checklist did not research. | The suppliers' statements on file; the readings confirmed before the first sale. | Owner; Part vendor | d | COMP rows 22 to 26 |
| G-091 | LED eye safety: no written assessment exists for the red and near-infrared LEDs of the grain sensor (drive about 6 mA and 10 mA). The infrared LED changed with E3 and its data sheet is unread. | The written assessment the checklist describes and each LED maker's statement. | Design; Part vendor | d | COMP row 27, 4.2 item 11 and 4.3 item 4; spec section 4 (E3) |
| G-092 | Material declarations: a hazardous-substances declaration was seen for the processor only. | A declaration for every line of the parts list, each adhesive included once chosen (G-048). | Owner; Part vendor | d | COMP row 28 |
| G-093 | DECISION. Origin wording. The checklist's reading: "Made in USA" and similar may not be claimed, and "US-sourced" should not be used in public at all, because a buyer reads it as US-made. A qualified statement is possible if true and documented. | The final wording approved by an attorney; an origin table for the parts. | Owner; Attorney | d | COMP row 29 |
| G-094 | DECISION. Performance, water and footstep claims: none may be made until the corresponding validation tests are passed on the production design. | The test reports of G-081; if a protection code is wanted, a lab test. | Owner; Test lab | d | COMP rows 30 and 31 |
| G-095 | DECISION. Rules of Golf: the checklist's reading is that the product is sold as a practice and training device and says so on the box, the quick-start card and the first screen. The wording is not frozen. | The current rule texts read on the official pages; the wording frozen. | Owner; Design for the first-screen text | d | COMP rows 32 and 33 |
| G-096 | DECISION. Patents, trademark, software licences. The checklist calls the patent search the one item that can stop the product outright and that depends on no hardware; it asks for it before any sale, pre-order or public launch, and it puts booking the attorney first in its order of work, before any hardware. Whether to start now is the separate decision G-104. The package holds no cost for the search. | A freedom-to-operate opinion; a trademark clearance search; a list of every third-party software piece and its licence. | Attorney; Owner; Design | d | COMP rows 34 to 36 and section 5 |
| G-097 | The owner asked for a US-sourceable device. What the package can show: 55 of the 72 purchased lines of the sourcing list were seen listed by a US distributor or seller (42 with a stock figure; some of the listings were seen only on pages for other countries or on aggregator copies, see G-057), and for 9 of the 14 custom parts and outside services a US company was seen advertising that kind of work. None has been quoted, and 17 purchased lines cannot be bought as they stand. A country of manufacture is recorded for 3 of the 86 lines, and none of the three is the US, and nothing yet shows where the product is assembled: the assembler and the print bureaus have not confirmed their build sites. | Country of origin per line; the build sites confirmed in writing. | Owner; Part vendor; Assembler; Print bureau | d | SRC sections 1.1 and 1.4 and section 11 item 22; COMP 4.2 item 14 |
| G-098 | DECISION. Sales outside the US. The checklist's own reading, PROVISIONAL: the sealed, soldered cell blocks sales in the European Union from February 2027. Canada and the United Kingdom have their own lists. | A decision on which markets are wanted; for the EU, a qualified reading of the battery rule or a design change. | Owner; Attorney | d | COMP section 3 and 4.2 item 8 |
| G-099 | DECISION. Production cover glass. The EVT crystal is declared not step-proof. For production the design asks for strengthened glass or sapphire by strength, and 1.0 mm is not a stocked thickness of strengthened glass at either US fabricator seen; the alternatives change the recess. | A decision on thickness and material; quotes with a strength figure; the footstep tests. | Owner; Part vendor | d | mech part list item 5 and section 12 test item 2; A28 |
| G-100 | Production items left open on purpose at EVT: hard-gold contact pads (ENIG at EVT); a volume source for the prisms (no volume price is known); the processor's price and lead time, on which the distributor pages disagree. | Quotes; the wet-docking and wear results for the pads. | Owner; Part vendor | d | mech section 12; SRC section 1.3 item 6 and A16; `docs/MANUFACTURING_PLAN.md` section 2.6 |
| G-101 | DECISION. Firmware production choices: write protection of the boot stub, the read-out protection level, signed images, and an update path other than ST's loader. The unlock word of the factory commands is the same for every unit and is not a secret. | A written decision for each. | Owner | d | fw issues 43 and 47 |
| G-102 | The phases after EVT are not defined: quantities, entry and exit criteria of the design and production validation builds; functional limits of the final test; cosmetic limits; box contents and packaging. Listed as open in the manufacturing plan, revision 3. | A manufacturing plan that defines them. | Owner; Design | d | `docs/MANUFACTURING_PLAN.md` section 2.4 and section 10 gaps 28 to 31 |

## 7. Owner decisions wanted and not taken

These are the gates marked DECISION, collected in one place. Each is a choice that no document
and no measurement makes for the owner. The wording of the question is in the gate.

| Order blocked first | Gates | Subject |
|---|---|---|
| (a) boards | G-103 | Run the dummy-marker seating test before ordering boards, yes or no |
| (a) boards | G-104 | Start the patent search and the market decision before ordering boards, yes or no |
| (a) boards | G-105 | Buy the display and the camera cubes at risk, yes or no |
| (a) boards | G-059 | Funding the first build, in stages |
| (a) boards | G-028 | Ship-mode current: change the board or relax the 5 microamp requirement |
| (a) boards | G-029 | Charge-temperature window when no firmware runs |
| (a) boards | G-030 | A way out of the USB loader for a user without a PC |
| (a) boards | G-031 | Protection of the three service pads |
| (a) boards | G-032 | Top-side tenting, TP5, the CamPower class, a capacitor-distance rule |
| (a) boards | G-033 | Cradle fuse trip current against E6 |
| (a) boards | G-034, G-035, G-036 | Accept the known layout weaknesses for EVT or have the layout redone |
| (b) parts | G-085 | Label route and regulatory text; ordering EVT base plates with placeholder text or not |
| (b) parts | G-046 | Accept the standing mechanical deviations and warnings |
| (b) parts | G-049 | Three adhesive choices |
| (b) parts | G-050 | Ball material |
| (b) parts | G-052 | Vent requirement: 50 kPa or about 10 kPa |
| (c) build | G-072 | Adopt the E23 and E14 figures as EVT targets |
| (c) build | G-073 | Whether this file or section 7 of the specification is the gate list |
| (c) build | G-075, G-076 | Cradle behaviour: silent USB host; the 6-hour backstop |
| (c) build | G-078 | Vision and Survey cases: accept for EVT or change the method |
| (c) build | G-080 | Camera exposure, calibration sign, grain setting, tuning constants |
| (d) selling | G-083 | Radio-interference procedure and responsible party |
| (d) selling | G-093, G-094, G-095 | What may be claimed: origin, performance, Rules of Golf wording |
| (d) selling | G-096 | Patent search, trademark, licences |
| (d) selling | G-098 | Markets outside the US |
| (d) selling | G-099, G-101 | Production cover glass; firmware protection choices |

Two further decisions are folded into gates that are not marked DECISION because a document must
come first: which of the missing factory procedures the EVT build needs (G-067), and whether the
solver differences are accepted (G-079). G-045 and G-048 each contain a selection that follows
from a vendor's answer. G-089 contains the checklist's question whether a derived serial number
serves a recall.

The firmware README lists further items tagged "[OWNER DECISION]" that do not block an order
(for example issues 8, 9, 11, 12, 15, 17, 19 to 21, 24, 27, 29, 38, 40, 42, 45, 50, 51, 54 to
56, 63, 64 and 66). Issue 5 (charge temperature) and issue 13 (idle camera kept awake) carry the
same tag and wait for a data sheet; they are cited in G-004 and G-063. Issue 24 (near the
critical slope the aim is not determined) is the reason for the "TOO STEEP" rule of E31; its
tuning constant is in G-080. They are not repeated here; `firmware/README.md` section "Open issues that need a
decision" is the list.

## 8. The Mill-Max diameters: why the YAML was not changed

The task that produced this file allowed a pair of keys for the Mill-Max 0914 tail and hole
diameters to be added to `design/master_params.yaml` if that broke nothing. A trial was made in a
scratch copy of `design/` and `mechanical/cad/`: with `tail_dia: 0.635, hole_dia: 0.80` added to
`cradle.pins`, `python3 -B cad/params.py` exits 0 and `design/check_layout.py` ends with "OK: no
layout errors". The keys were still not added to the package, for three reasons:

1. The two packages hold different PROVISIONAL numbers (0.635 / 0.80 mm in
   `electrical/gl1_cradle/gl1_cradle_design.py`, 0.76 / 0.90 mm in `mechanical/cad/params.py`) and
   neither is from the Mill-Max drawing. Writing one pair into the shared file would look like a
   decision that has not been taken.
2. Neither package would read the new keys, so they would compare nothing. The useful change is
   keys that both packages read, which means editing both design files and rebuilding both
   packages, outside the scope of this file.
3. `mechanical/export/params_resolved.json` stores a full copy of the YAML. Any edit of the YAML
   makes that stored export differ from a rebuild until the mechanical package is rebuilt.

The mismatch is therefore gate G-014, and no YAML file was edited.

## 9. What this list does not contain

- Test items that are run on EVT units and cannot block the build that produces them. They are in
  `mechanical/README.md` section 12 ("Test items for EVT") and in `docs/VALIDATION_PLAN.md`;
  G-081 points to them.
- Open mechanical issues that are observations rather than gates (`mechanical/README.md`
  section 12, "Open mechanical issues", 31 items). Those that block an order are cited in the
  gates above.
- Items the packages record as closed at revision E.

When a gate closes, record the evidence (document name and date, or measurement record) in the
source file named in its last column, then strike the gate here. A gate is not closed by a search
extract, by memory, or by a check of the package passing.

## 10. Changes to this list since its first issue on 2026-11-20

The first issue had 102 gates in groups of 36, 23, 21 and 22. The same day the other documents
under `docs/` were re-issued, and an independent check compared the files. This section records
what changed, so that a reference to an old count or an old group can be followed.

Closed, with the evidence:

| ID | What it said | Evidence that closed it |
|---|---|---|
| G-069 | The manufacturing plan and the validation plan were written against revision D and carried rev E notes only. Closing evidence asked for: "Both plans re-issued against rev E". | `docs/MANUFACTURING_PLAN.md` and `docs/VALIDATION_PLAN.md` are at plan revision 3 of 2026-11-20, written against rev E. The three wrong statements the gate named are gone: the cradle board is described as routed and 1.0 mm, the sleep model as 23.7 microamps and 76 days, the guaranteed field as 14.0 degrees. What is still open about the documents is G-106. |
| G-070 | `docs/SOURCING.md` section 12.1, cells A6 and A20, spoke of 0.90 mm drills, an M2 x 5 screw and a 1.6 mm board. | Both cells were rewritten on 2026-11-20 and begin "State at revision E": a 0.635 mm tail in a 0.80 mm hole, a 1.0 mm board, M2 x 4. The other rows of 12.1 are as written on 2026-11-13; that is covered by G-057. |
| G-082 | The compliance checklist was written against rev D with no rev E note. | `docs/COMPLIANCE.md` is at checklist revision 3 of 2026-11-20, written against rev E; its section 4.1 lists the old items 1, 2, 3, 4, 6, 7 and 13 as closed on paper. It made no new search: the legal content is the reading of 2026-11-11, and every row is still "Not started" (G-083 to G-098). |

Moved, because the "Blocks" cell named an earlier order than the group: G-038, G-039, G-057 and
G-059 from group B to group A (section 3.5); G-085 from group D to group B (section 4.2); G-089
from group D to group C (section 5.1).

Added: G-103, G-104 and G-105 (section 3.5); G-106 and G-107 (section 5.2).

Widened without a new number: G-029 (the charge that never ends in the USB loader, test log line
297), G-045 (the contradiction on the legend capacity), G-059 (the full budget of SRC 10.5 and
what has no figure), G-060 (the full fixture list), and the citations of items from the firmware
and electrical READMEs in G-004, G-022, G-032, G-041, G-061, G-063 and G-067.

How the counts were checked: a script read every table row of sections 3 to 6 that begins with a
gate number, counted the rows per section, counted the rows whose text begins with "DECISION",
and compared the first letter of each "Blocks" cell with the group. Result on 2026-11-20: 43, 20,
22 and 19 rows; 13, 5, 6 and 8 decisions; no row whose first blocked order differs from its
group. Orders blocked, counted from the "Blocks" column: (a) 43, (b) 30, (c) 38, (d) 32.
