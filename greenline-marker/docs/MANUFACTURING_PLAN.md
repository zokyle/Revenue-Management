# GreenLine GL-1: manufacturing plan

Plan revision 2, 2026-11-11 (revised the same day after two independent reviews). Written
against `design/DESIGN_SPEC.md` rev D (EVT1) and `design/master_params.yaml` rev D-EVT1.

**Read this first.** Nothing in this project has been built or tested. No circuit board, printed
part, fixture or finished unit exists. This plan says how the device is meant to be made and
proven. Every time, yield and limit in it is either copied from the design files (which are
themselves untested) or is an estimate, and is marked as such.

This document owns HOW the GL-1 is made and proven. Who supplies each part, at what price and
with what lead time, is in `docs/SOURCING.md`. This plan recommends no supplier and gives no price. Part
numbers that appear here are the ones written in the design specification. Section 12 names
only the publishers of the outside facts used.

The GL-1 is a practice and training device. The Rules of Golf do not allow it in a stipulated
round (`docs/research/rules-compliance.md`). That statement belongs on the box and on the
quick-start card (section 7.4).

## How to read the labels

| Label | Meaning |
|---|---|
| **REPO** | Taken from the design package; the file is named. The package is unbuilt, so a REPO fact is a design intent, not a test result. |
| **VERIFIED** | An outside fact seen today (2026-11-11) in a web search result. The source is in section 12. Vendor pages could not be opened from this session, so "seen" means the text the search returned. |
| **PROVISIONAL** | An outside fact from memory or from an unconfirmed extract. Confirm it before ordering parts or setting a process. |
| **PROPOSAL** | Suggested by this plan. It is not in the repository. The owner accepts it or changes it. |
| **Not yet defined** | The repository is silent. Every such item is listed again in section 10 (Gaps). |

## Words used

| Word | Plain meaning |
|---|---|
| PCB | Printed circuit board: the thin green (here 0.8 mm) board that carries the chips. |
| Reflow | Soldering in an oven. Solder paste is printed, parts are placed on it, and the whole board is heated until the paste melts. |
| BGA | Ball grid array: a chip whose contacts are small solder balls hidden under its body. They cannot be seen after soldering, only X-rayed. |
| MSL | Moisture sensitivity level. Some chips soak up water from the air. In the oven that water turns to steam and can crack them. The level says how long a part may sit in room air before soldering. |
| Camera cube | The OVM7692 camera: sensor and lens in one block about 3 mm on a side, soldered like a chip. |
| IMU | Inertial measurement unit: the chip that feels gravity and so measures tilt. |
| Pogo pin | A spring-loaded pin that presses on a pad to make contact without soldering. |
| SWD | Serial wire debug: the two-wire port used to load software into a blank processor. |
| DFU | Device firmware update over USB, using a small loader that the chip maker builds into the processor. |
| Firmware | The software that runs inside the device. |
| Fixture, jig | A tool made for this product that holds a part in the right place while a step is done. |
| Go gauge | A simple test piece: if it fits (or passes), the part is good. |
| Cure | The time and conditions an adhesive needs to harden. |
| Thixotropic | An adhesive that stays where it is put, like toothpaste. |
| Wicking | The opposite: a thin adhesive that runs into a narrow gap by itself, like water into a paper towel. |
| Potting | Filling a space with resin so that water and dirt cannot reach the parts inside. |
| mrad | Milliradian. 1 mrad is a slope of 1 mm in 1 m (0.1 %, about 0.06 degree). |
| px | Pixel: one dot of a camera image. |
| First article | The first part of a new kind from a supplier, measured before any more are used. |
| EVT, DVT, PVT | Three build phases: engineering, design and production validation tests (section 2). |

---

## 1. Overview

### The one analogy to keep

The GL-1 is built like a sealed wristwatch. The "movement" is the circuit board glued to its
base plate. The "case" is the printed tub with its glass. Each half is finished and tested by
itself. The two are tried together dry, then glued shut. After the glue has set, nobody can
open the watch again without destroying it. That is why almost every check in this plan sits
just before a point of no return.

### The whole chain

```
  BOARD MAKER             BOARD ASSEMBLER              OUR BENCH
 +--------------+      +-------------------+      +------------------------+
 | 1 Bare PCB   | ---> | 2 PCB assembly    | ---> | 3 Program the board    |
 |   + FR-4     |      |   parts soldered, |      |   and electrical test  |
 |   base plate |      |   cubes X-rayed   |      +-----------+------------+
 +--------------+      +-------------------+                  |
                                                              v
 +--------------+      +-------------------+      +------------------------+
 | 7 Pack       | <--- | 6 Final test      | <--- | 4 Mechanical assembly  |
 +--------------+      +---------+---------+      |   glue, pot, seal shut |
                                 ^                +-----------+------------+
                                 |                            |
                       +---------+---------+                  |
                       | 5 Calibration     | <----------------+
                       +-------------------+
```

| # | Stage | Done by | Goes in | Comes out | Main check | Section |
|---|---|---|---|---|---|---|
| 1 | Bare PCB and base plate | PCB fabricator | Fabrication files | Bare 4-layer board; FR-4 base plate with no copper | Thickness, hole sizes, outline | 3 |
| 2 | PCB assembly | Board assembler | Bare boards, parts kit | Board with all soldered parts. No display, no battery, no prisms | Optical inspection; X-ray of the two camera cubes | 3 |
| 3 | Programming and board test | Us | Assembled board | Board with firmware, electrically proven | Rails, currents, each chip answers | 4 |
| 4 | Mechanical assembly | Us | Tested board, tub, base plate, glass, display, battery, prisms, adhesives | Sealed marker | Two test gates and two leak tests | 5 |
| 5 | Calibration | Us | Sealed, cured, temperature-cycled marker | Marker with its own correction numbers stored | Level, cameras, grain sensor, display | 6 |
| 6 | Final test | Us | Calibrated marker | Accepted marker with a record | Function, cosmetics, record complete | 7 |
| 7 | Pack | Us | Marker, cradle, printed card | Boxed product | Contents and battery state | 7 |

The charging cradle is a second, simple product with its own small board. It is built and
tested beside this chain (section 7.5).

### Three points of no return

| Point | Step in `mechanical/README.md` section 7 | What can no longer be fixed afterwards |
|---|---|---|
| Clear potting has cured | 12 | The 16 grain LEDs and the photodiode under the potting |
| Prisms are bonded to the camera cubes | 13 | The camera cube under each prism |
| Seal adhesive has cured | 17 | Everything inside the marker |

### Where the project stands today

| Item | State on 2026-11-11 | Source |
|---|---|---|
| Main circuit board | Not laid out. The repository holds the layout toolchain and a demonstration board at older (rev C) positions. No schematic, netlist, parts list or fabrication files for the real board | REPO: `electrical/tools/README.md` (demo build); `mechanical/README.md` section 10, check 17 "skipped: no board file" |
| Camera footprint | Provisional. Ball map, ball pitch and image orientation are not confirmed | REPO: `DESIGN_SPEC.md` section 7 |
| Firmware | Runs on a simulator on a PC. Never run on hardware. The processor-specific part has been compiled against the chip maker's header files, but never linked or run; its USB part is still uncompiled | REPO: `firmware/README.md` "Status" (as that file stood late on 2026-11-11) |
| Printed parts, base plate | Modelled and drawn. None printed or measured | REPO: `mechanical/README.md` header |
| Adhesives | None chosen. Each is named by class only | REPO: `mechanical/README.md` section 12 |
| Fixtures and gauges | Described in words. Not drawn, not made | REPO: `mechanical/README.md` section 2 |
| Factory software (PC side) | Does not exist | REPO: `firmware/README.md` "What is not done" |
| `docs/RELEASE_GATES.md` | Named by the specification as the full gate list. The file is not in the repository | REPO: `DESIGN_SPEC.md` intro and section 7 |

---

## 2. Build phases and what each must prove

Hardware is proven in three builds. Think of a new recipe: first cook it once to see whether it
works at all (EVT), then cook it for many guests in bad conditions (DVT), then check that the
kitchen staff can make it the same way every evening (PVT).

**Status of this package: ready to order EVT prototypes once the release gates are closed. It
is not ready for volume production.** The reasons are in section 2.5.

### 2.1 The three phases at a glance

| | EVT | DVT | PVT |
|---|---|---|---|
| Question | Does the design work? | Does it survive, and does it meet the specification on every unit? | Can the line build it the same way again and again? |
| Quantity | **10 units** (given). PROPOSAL: buy parts for 15 builds, plus extra tubs, to finish 10 | Not yet defined. Planning assumption (PROPOSAL): 30 to 50 | Not yet defined. Planning assumption (PROPOSAL): 100 to 200 |
| Built by | The design team, by hand, at one bench | The design team with trained helpers, on second-generation fixtures | The people who will run production, from written instructions |
| Parts | EVT-grade: mineral-glass crystal (not step-proof), plain gold (ENIG) contact pads, prism from the catalogue source | Production-intent: strengthened glass or sapphire, hard-gold pads, chosen adhesives, volume prism source | Production parts from production lots |
| Design state | Rev D with open choices | Frozen after EVT (next revision) | Frozen. Only process changes |
| Main output | A list of what works, what does not, and the decisions in 2.6 | Test reports; design freeze for production | Yield per step, time per step, final work instructions |

### 2.2 EVT: entry criteria (the release gates)

Nothing is ordered until each line below is closed by a named person. The list combines
`DESIGN_SPEC.md` section 7, `mechanical/README.md` section 12 and `firmware/README.md` "Open
issues". The specification points to `docs/RELEASE_GATES.md` for the full list; that file does
not exist yet, so this table is a working copy, not the master.

| # | Gate | Why it blocks the order | Source |
|---|---|---|---|
| G1 | Camera cube ball map, ball pitch and image orientation read from the maker's registered datasheet. From the same datasheet: the lens data (where the lens opening sits and how wide it is) | The footprint on the board is a guess until then. A wrong footprint scraps every board. The field-of-view figures and the 2.3 % clipping at the prism rest on assumed lens values | `DESIGN_SPEC.md` section 7; `mechanical/README.md` section 12 ("OVM7692 lens data") |
| G2 | Display tail: length, exit position, which end is pin 1, which face carries the contacts | A wrong guess mirrors all ten pins. The tail must also be long enough to plug in with the unit open 35 degrees (10 mm free length plus insertion depth) | `DESIGN_SPEC.md` section 4; `mechanical/README.md` section 12 (B16) |
| G3 | Battery: size with its protection board, largest delivered thickness, swelling at end of life, highest allowed process and storage temperature, safety certificates. PROPOSAL, added here: the highest allowed discharge current | The battery bay has 0.15 mm in hand. The 45 C cure limit is a trade figure until the cell data sheet confirms it. The storage temperature decides whether the 70 C tests may be run on units with a cell. A read draws about 96 mA, about 2.2 times the cell's capacity per hour (an estimate in `firmware/README.md`, every current provisional; `VALIDATION_PLAN.md` 2.7) | `mechanical/README.md` section 12 (B15) |
| G4 | The real board exists: netlist, layout, design-rule check clean, `design/check_layout.py` passes, mechanical check 17 passes on the real board file | Today check 17 has only run on synthetic boards | `mechanical/README.md` section 10 |
| G5 | Processor pin facts confirmed against the maker's documents (pins the built-in loader drives, the charge-inhibit pin type, the analog input for the cell temperature, USB without a crystal) | They are from memory | `firmware/README.md` open issues 2, 4, 10 |
| G6 | Charger safety decision: add hardware that stops charging without the firmware, or accept the two cases the firmware cannot cover | In the built-in USB loader, and for up to 33 s after a firmware hang, nothing watches the cell temperature | `firmware/README.md` "Charger and cell temperature" (two rows marked NOT MET) |
| G7 | Every adhesive has a part number and data sheet (nine joints, section 5.4) | Cure times, primers and fixtures depend on the product | `mechanical/README.md` section 12 |
| G8 | FR-4 base plate: fabricator confirms the build-up for 0.80 mm over the mask, the thickness tolerance and the 1.0 mm web rule | The plate thickness sets the gap under the ball feet | `mechanical/README.md` section 4.1 |
| G9 | Print bureau confirms 0.8 mm walls survive vapor smoothing, and the locked print orientation of the cradle | Thin walls can distort in smoothing | `mechanical/README.md` section 4.2, open issue 21 |
| G10 | Mechanical package rebuilt against the amended parameter file, and drawings re-issued | The parameter file was amended after the last mechanical build (section 11, item 3) | `design/master_params.yaml` header; `mechanical/export/params_resolved.json` |
| G11 | Every stock check | See `docs/SOURCING.md` | `DESIGN_SPEC.md` section 7 |
| G12 | Firmware compiles for the real processor and a factory test path exists for cameras and display (section 4.4) | Without it the two test gates of the assembly sequence cannot be run | `firmware/README.md` "What is not done" |

PROPOSAL: G12 can be closed during the weeks the boards are being made. All others must be
closed before the order.

One gate that the source lists name is left out of this table on purpose: **tub first
articles** (`mechanical/README.md` section 12: seal face 0.60 and rim 1.55 from the post feet
within +-0.1; spigots; bore; dummy unit; `DESIGN_SPEC.md` section 7 calls it "the mechanical
first-article fit"). It cannot be closed before the order, because the tubs must be ordered
before they can be measured. This plan moves it to the first station of mechanical assembly:
station T1 (section 5.2) gauges every tub on arrival, before any adhesive is opened. The
README's other gate lines are covered by G2, G3, G7, G8 and G10. Its hard-gold contact pads
are a production item (section 2.6).

### 2.3 EVT: the build, and what it must prove

**Trials before the first sealed unit** (REPO: `mechanical/README.md` section 12, test item 8).
These use loose parts and scrap boards, not the ten units: display tilt-in against the rear
ribs; hood gasket bead from the needle guide and its shape after cure; plugging in the display
tail with the unit open, on a mock-up; the dry trial close; adhesive coupons on the real
materials; a potting trial on bare base plates.

**Build matrix for the ten units (PROPOSAL).** The tilt-drift test needs both base-plate
materials, each with the grain opening potted and unpotted, or it cannot separate the effect of
the plate from the effect of the potting (REPO: `mechanical/README.md` section 12, test item 1).

| Base plate | Grain opening | Units | Use |
|---|---|---|---|
| FR-4 (primary) | Potted | 4 | Full function, turf trials, seal tests |
| FR-4 | Unpotted | 2 | Tilt-drift comparison only (bench; not for wet turf) |
| Printed PA12 (alternative) | Potted | 2 | Tilt-drift comparison, seal comparison |
| Printed PA12 | Unpotted | 2 | Tilt-drift comparison only |

Destructive tests (footstep, sectioning, ball push-out) should use extra shells without
electronics or optics. Their number is not yet defined in the repository.
`VALIDATION_PLAN.md` 4.1 proposes 20 shells, 10 with each base plate, plus spare boards and
cells; `docs/SOURCING.md` section 10.5 prices that whole programme.

**What EVT must prove.** Pass figures are from the repository where one exists.

| # | Question | Pass figure | Source |
|---|---|---|---|
| E1 | Do all boards power up and does every chip answer? | Section 4.5 | - |
| E2 | Does the tilt reading of the board-and-base sandwich drift with temperature and humidity? | Under 0.05 mrad per kelvin after per-unit correction. Repeats within 0.3 mrad after a -10 to 50 C cycle. Measured again some weeks after cure | `mechanical/README.md` section 12, test item 1 |
| E3 | How repeatably does the marker seat on real turf? | No pass figure. The simulation assumed 2.5 mrad; at 5 mrad a Quick Read falls behind a good human reader. The specification calls this the first task for a prototype | `DESIGN_SPEC.md` section 2; `sim/results/REPORT.md` section 4.1 |
| E4 | Do both cameras give images, the right way up, with the bus behaving as assumed? | Both identify themselves. Register and pin behaviours marked provisional in the firmware are measured | `firmware/README.md` open issues 3, 13 |
| E5 | Is the upper edge of the camera view clear? | Nominal design 17.6 degrees; guaranteed 14.5 degrees at the tolerance limit. The assembly sequence asks for a target at +17 degrees to be seen by both cameras (these two figures conflict: section 11, item 9) | `master_params.yaml` `cameras.field_required_deg`; `mechanical/README.md` step 16 |
| E6 | How long does a read take on the real processor? | Design intent: a result about three seconds after the ball is lifted. The simulator gives 4.4 s with computing charged at its estimated cost (4.1 to 4.8 s over the estimated range; 3.45 s only with computing counted as zero). The firmware notes mark the three seconds as NOT MET. Unmeasured on hardware | `DESIGN_SPEC.md` section 1; `firmware/README.md` "End to end" and open issue 1 |
| E7 | How repeatable is the stereo camera calibration? | The firmware assumes 0.05 px. A drift of 0.1 px moves the distance by about 3 % | `firmware/README.md` open issue 6; `DESIGN_SPEC.md` section 2 |
| E8 | Do the seals hold? | Leak tests of every tub and every unit. Qualification loads: 25 kPa inward, and 40 kPa outward for 24 h at 70 C. Cut sections show the joint is filled | `mechanical/README.md` section 9 |
| E9 | Do the potted ball feet hold? | Push-in and pull-out target 100 N. Protrusion unchanged after temperature cycling | `mechanical/README.md` section 12, test item 7 |
| E10 | Does filling the grain opening by volume hold the level window? | Surface inside a 0.10 mm window, never closer than 0.05 mm to the base plane | `mechanical/README.md` step 12 |
| E11 | Does the cradle latch last? | 3000 insert and release cycles at 23 C and 0 C; 1000 h at 50 C under seven pins; pull test 12.4 N at the pin row | `mechanical/README.md` section 12, test item 3 |
| E12 | Does light leak into the cameras? | Dark frames under strong side light. No numeric limit yet | `mechanical/README.md` section 12, test item 4 |
| E13 | What happens under a footstep? | 800 N on a 20 mm indenter, on glass and on roof, on turf and hard floor, at 23 and 60 C, display powered. The EVT crystal is declared not step-proof, so this test is about the roof, the posts and the board | `mechanical/README.md` section 12, test item 2 |
| E14 | Is the grain sensor worth keeping? | Validation gates 0 to 2 of the grain research note. The sensor ships disabled until it passes | `docs/research/grain-sensing.md` section 2.3 |
| E15 | Does charging start with a dead processor and stop outside 0 to 45 C? | Section 4.5, tests 6 to 8 | `DESIGN_SPEC.md` section 4 |
| E16 | Wet docking | 100 dockings of a wetted marker, then pad inspection | `mechanical/README.md` section 9, test 8 |
| E17 | Do bonded units survive temperature cycling? | 100 cycles of -10 to 70 C, then leak test, display position and tilt offset compared with before | `mechanical/README.md` section 9, test 9 |

**EVT exit criteria (PROPOSAL).** EVT ends when: every item above has a measured answer; each
decision in 2.6 marked "EVT" is made and written into the specification; every failure has a
known cause and a design change or a recorded acceptance; and the changed design passes the
automatic checks again.

### 2.4 DVT and PVT

The repository says little about these phases. What it does give is listed. The rest is not yet
defined.

| | DVT | PVT |
|---|---|---|
| Entry (PROPOSAL) | EVT exit met. Design frozen. Production-intent glass, pads, adhesives and prism source in hand. Fixtures remade from EVT lessons. Factory software complete (sections 4 and 6) | DVT exit met. Work instructions written. Operators trained on DVT units. Record system running |
| Must prove (REPO) | The repository assigns no test to DVT by name. Two things it does say point here: the step-proof claim needs the production glass, which EVT units do not have; and the enclosure research asks for a dunk test, including a hot unit into cold water, on the first 100 units | Not stated in the repository |
| Must prove (PROPOSAL) | Repeat, on production-intent parts and on more units, the tests that `mechanical/README.md` section 9 lists (tests 2 to 11: pressure loads, dunk, adhesive coupons after ageing, light leak, footstep, fogging, wet docking, temperature cycling, swollen cell, potted opening after mud and sand) | - |
| Also (PROPOSAL) | The calibration holds on every unit over temperature. Field trials with golfers. Regulatory tests named in `docs/research/rules-compliance.md` section 2.2 that still apply to a device with no radio (status there: unverified) | Yield at every gate. Time at every station. Each gauge gives the same answer for different operators. Parts from a second lot of tubs and base plates still fit. Packaging survives shipping |
| Exit (PROPOSAL) | All tests passed or the failures fixed and re-tested. Specification limits confirmed as test limits | Agreed yield and time reached on consecutive lots. No open safety item |

### 2.5 Why this is not ready for volume production

1. Nothing has been built or tested. Every performance figure is a simulation.
2. The main board is not laid out, and the camera footprint is provisional.
3. The firmware has never run on the processor. The factory software does not exist. Several
   calibration steps are not implemented (section 6.9).
4. No adhesive is chosen for any of the nine joints.
5. The seal, the latch, the ball feet and the potting are calculated or chosen by class, not
   tested.
6. The EVT cover glass is not step-proof.
7. The upper edge of the camera view has 0.054 mm of margin to the roof. It is accepted in
   rev D, but it leaves no room for process drift.
8. Several hand steps have windows of a few hundredths of a millimetre (ball height, potting
   level, gasket bead). Nobody knows yet how often a person can hit them.
9. No fixture or gauge has been drawn or made.
10. Two charger safety cases are not covered (gate G6).
11. The product's value depends on numbers nobody has measured, first of all how repeatably
    the marker seats on turf.
12. No regulatory test has been run. The research on it is unverified.

### 2.6 Open design decisions and the phase that closes each

| Decision | Evidence needed | Closed in |
|---|---|---|
| Base plate: FR-4 or printed PA12 | Tilt-drift test E2 on both | EVT |
| Clear potting product and its stiffness | E2 (potted against unpotted), E10, optical function through the potting | EVT |
| Each adhesive, with primer and cure | Coupons, E8 | EVT (choice), DVT (proof after ageing) |
| Fit of the board on the two locating spigots (0.075 mm) | First-article gauging; measured camera position through the windows | EVT |
| Guaranteed upper view angle and the limit used at test gate 2 | E5 | EVT |
| Display tail routing and connector orientation | Mock-up trial | EVT |
| Camera register settings, bus sharing at power-up, image orientation | E4 | EVT |
| Processor pin assignment | Layout, then E1 | Before EVT order (G4, G5) |
| Charger supervision in hardware | G6 | Before EVT order |
| Read time; whether the vision code needs speeding up | E6 | EVT |
| Is the single IMU good enough, or is the precision inclinometer needed | E2, E3 | EVT |
| Grain sensor: keep, or ship the prior-only estimate | E14 | EVT (bench gates), DVT (turf gates) |
| 0.2 mm thicker marker above the display (the reserved remedy) | E13 on EVT; footstep with production glass | DVT |
| Production cover glass: strengthened glass or sapphire, by strength (600 MPa ring-on-ring or more) | Footstep test | DVT |
| Hard-gold contact pads | Wet-docking and wear | DVT |
| Volume source for the prism | Quote and sample measurement (see `docs/SOURCING.md`) | DVT |
| Rim relief, if tubs do not hold the +-0.1 mm asked for | Tub first articles from two lots | EVT, confirmed in PVT |
| Calibration temperature points and limits | Section 6 on EVT units | EVT (method), DVT (limits) |

---

## 3. PCB fabrication and assembly: notes for the fabricator and the assembler

Three things are ordered here. They are different animals.

| Item | What it is | Drawing or data |
|---|---|---|
| Main board | 4-layer circuit board, parts on both sides | Not yet produced (gate G4) |
| Base plate | A mechanical plate made of circuit-board material with **no copper at all**. Routed and drilled only. It is ordered from the PCB fabricator because they hold thickness and hole positions well | `mechanical/drawings/GL1-011_base_plate_FR4.pdf` and the four files in `mechanical/drawings/fab/`. Ordering notes: `mechanical/README.md` section 4.1 |
| Cradle board | Small 2-layer board, 30 x 22 x 1.6 mm, with a USB-C socket and spring pins | Not yet produced. Only its outline exists (`master_params.yaml`, `cradle.pcb`) |

### 3.1 Main board: stack-up and rules

All REPO unless marked. Sources: `DESIGN_SPEC.md` section 4 ("PCB" paragraph) and
`electrical/tools/README.md` ("Rule set", "Via tenting", "Demo build").

| Item | Value |
|---|---|
| Layers | 4 |
| Finished thickness | 0.80 mm. The mechanical tolerance chains assume +-0.08 mm: ask the fabricator to confirm and to report the measured value, because board thickness sets the height of the seal joint |
| Surface finish | ENIG (thin gold over nickel) for EVT. Selective hard gold on the seven contact pads for production |
| Layer use | Top: parts and signals. Layer 2: solid ground. Layer 3: 2.8 V plane that also carries tracks (as on the demonstration board). Bottom: grain LEDs, photodiode, seven contact pads |
| Copper weight, dielectric build, material grade, solder-mask colour | Not yet defined |
| Outline | D shape: radius 21.1 mm, flat edge at y = 17.3 mm |
| Locating features | One non-plated round hole 1.15 mm at (14.35, 10.8). One non-plated slot 1.15 x 2.2 mm along x at (-14.35, 10.8). The mechanical drawings still show the slot as 1.8 mm long (section 11, item 3) |
| Vias | Through vias only. 0.25 mm drill, 0.50 mm pad, 0.125 mm minimum ring |
| Via protection | Tented and plugged on the underside, because the underside is wet in use. **No via at all** inside the 13 mm grain opening at (0, -4) or inside the pad slot at y = -17 |
| Tracks | Default 0.15 mm track with 0.127 mm gap. Power 0.30 mm |
| Fine tracks | 0.10 mm track with 0.10 mm gap, used only to escape the camera footprints (specification). The toolchain's fine rule set is 0.09 / 0.09 mm, which the research found to be outside the standard tier of the fabricators it checked. One of the two must change (section 11, item 4) |
| Other clearances | Copper to board edge 0.30 mm. Hole to hole 0.25 mm. Hole wall to other copper 0.20 mm |
| Under each ball foot (3 places) | Bottom side: a 2.5 mm circle with no via and no track, and a bare 1.6 mm copper land that the steel ball bears on. At (0, 15.0), (-16.5, -9.5), (16.5, -9.5) |
| Under the IMU | No copper pour and no via on the top layer |
| Contact pads | Seven 1.8 mm pads on 2.54 mm pitch at y = -17.0. No solder paste on them |
| Fiducials (camera targets for the placement machine) | Three per side, as on the demonstration board. The toolchain warns when a side with fine-pitch parts has fewer |
| Controlled impedance | None specified |

Height rule for anyone who proposes a substitute part: nothing on the top side may stand more
than 2.55 mm above the board; nothing more than 0.95 mm under the two camera hoods except the
camera; nothing more than 0.7 mm under the display tail behind connector J1. A taller
"equivalent" part will not fit the tub (REPO: `master_params.yaml`, `tub_keepouts`).

### 3.2 Parts that need care

| Ref | Part | Package | Why it needs care | How to handle |
|---|---|---|---|---|
| U2, U3 | OVM7692-RYAA camera cube | 25 balls at 0.5 mm pitch (count from third-party listings; pitch PROVISIONAL). Body 2.95 x 3.47 mm, 2.76 mm tall | A tall block on a small ball field with a lens on top. Its rotation on the board sets which way up the image is. Hidden joints | See 3.3 |
| U1 | STM32U585RIT6 processor | 64 leads at 0.5 mm pitch | Fine leads; solder bridges | Standard. Optical inspection |
| U4 | LSM6DSV16X IMU | 14 lands, 2.5 x 3.0 x 0.83 mm, no leads | A tiny mechanical sensor. Stress from solder or board bending shifts its zero. Hidden joints | No solder on the sides of the package (VERIFIED extract of the maker's mounting note [S4]). No ultrasonic cleaning (PROVISIONAL: `docs/research/enclosure-manufacturing.md` records that makers of such sensors warn against it). Do not flex the board near it when breaking boards out of the panel |
| U6 | MX25R6435F flash memory | 8 lands, 6 x 5 mm, no leads | Hidden joints | X-ray sample |
| J1 | Display connector FH12A-10S-0.5SH(55) | 10 contacts at 0.5 mm pitch, top contact, 2.0 mm tall | Its pick point is not its centre: the footprint anchor is offset 1.6 mm on this connector family. Its flip latch is small and easy to damage (general experience) | Check the pick point with the placement programmer (REPO: `electrical/tools/README.md`, "Anchor and body centre") |
| - | Six 4-resistor arrays, 220 ohm | 0804 | Small | Standard |
| - | 16 grain LEDs (8 red, 8 infrared) | 0402, bottom side, on a 5.2 mm radius | Each red LED sits beside an infrared one, wired back to back. A reversed LED looks perfect to a camera inspection | Polarity is proven electrically at board test (section 4.5, test 14) |
| - | Photodiode | 4.8 x 2.5 x 0.48 mm, bottom side | Its pad layout came from public footprints, not the maker's drawing (`docs/research/bom-verification-opto.md`, item 5) | Confirm the footprint before layout |
| - | Cell temperature sensor (NTC) | 0402, top side, within 1 mm of the battery edge | Must end up right beside the cell | Standard placement. The thermal adhesive dab is applied later (section 5) |

### 3.3 The camera cubes

What is known, and how sure.

| Fact | Status |
|---|---|
| The maker describes the cube as built to withstand more than one reflow, for rework or two-sided assembly | VERIFIED (search extract of the maker's product page [S1]) |
| Moisture sensitivity level 3: 168 hours of floor life | VERIFIED as a distributor listing only [S2]. Not seen in a maker's document. Read the label on the sealed bag |
| What level 3 means: once the dry bag is opened the parts may sit at up to 30 C and 60 % humidity for 168 hours in total before soldering; past that they are baked dry first | VERIFIED [S3] |
| Highest oven temperature, largest number of reflows, any protective film on the lens, cleaning allowed or not | **Not found.** They are in the maker's registered datasheet and assembly guide, which gate G1 already requires |
| Ball pitch, ball map, which edge is parallel to the image rows | PROVISIONAL (gate G1) |

Process notes for the assembler (PROPOSAL, to be agreed with them once the maker's guide is in
hand):

1. Keep the cubes in their dry bag until the top side is ready to place. Log the time out of
   the bag. A moisture clock is like bread going stale once the bag is open: it only runs one
   way unless the part is baked.
2. Place the cubes last on the top side, so nothing else is placed across them.
3. Solder the cubes once only: build the bottom side first (3.5).
4. The top of the cube is an optical and a bonding surface. A prism is glued to its four
   corners later. No fingerprints, no flux, no marker ink, no label on it.
5. Do not wash a board that carries cubes unless the maker's guide allows it.
6. X-ray both cubes on every board (3.6).
7. Report the height of each cube top above the board. The mechanical gauge allows 2.81 mm
   (2.76 mm nominal plus 0.05 mm). A cube that sits high or tilted eats the 0.19 mm of roof
   clearance above the prism (REPO: `mechanical/README.md` section 2, dummy unit; section 5,
   tolerance chains).

### 3.4 Parts that are NOT soldered in the oven

| Part | Why not | Where it is fitted |
|---|---|---|
| Memory LCD (LS013B7DH03) | Glass with a flexible tail. Its storage limit is +80 C in most copies of the maker's specification (`docs/research/bom-verification-opto.md` 3.1, confirmed there from search extracts). An oven is at well over 200 C | Glued under the tub roof (step 9). Its tail is plugged into J1 at the final close (step 15) |
| Battery | A lithium cell must never see oven heat | Stuck to the board and its two leads soldered by hand (step 13). From then on nothing in the unit may be heated above 45 C |
| Two prisms | Glued optics | Bonded to the cube tops with UV adhesive (step 13) |
| Baffle ring, base plate, ball feet | Mechanical parts | Steps 2, 3 and 11 |

The assembler ships boards with J1 empty and its latch closed, and with the two battery pads
bare.

### 3.5 Two-sided assembly sequence (PROPOSAL)

1. Check moisture labels. Bake any part whose floor life has run out.
2. **Bottom side first.** Print paste, place the 16 LEDs and the photodiode, reflow. These are
   the only bottom-side parts and they are light, so they stay on when the board is turned
   over.
3. Clean the bottom side now, while no cube and no IMU is on the board. Reason: the underside
   is later bonded to the base plate with an adhesive sheet and covered with clear potting.
   Flux residue is a risk to both bonds and to the very sensitive photodiode input. The
   repository does not address this (section 11, item 14).
4. **Top side second.** Print paste, place everything, cubes last, reflow. No wash afterwards
   (no-clean flux).
5. Optical inspection of both sides. X-ray (3.6).
6. Break out of the panel with a router or a fixture, not by hand (3.7).

### 3.6 What is inspected

| Inspection | On | Looking for |
|---|---|---|
| Solder paste check | Camera footprints, IMU, processor | Paste volume on 0.20 mm pads |
| Automatic optical inspection | Both sides, every board | Missing, shifted or bridged parts |
| **X-ray** | Both camera cubes on **every** board. IMU and flash on the first boards, then by sample | Bridged balls, open balls, large voids. These joints cannot be seen any other way |
| Cube height and tilt | Both cubes, every board at EVT | Top no more than 2.81 mm above the board; no visible tilt |
| Cleanliness | Underside | No residue in the grain area, on the contact pads or on the three copper lands |
| First article | First assembled board | Photographs of both sides and the X-ray images returned to us before the rest are built |

Workmanship standard (IPC class) and X-ray void limits: not yet defined.

### 3.7 Panelisation with the D-shaped outline

The toolchain produces no panel (REPO: `electrical/tools/README.md`, "Limitations"). The
repository gives panel rules only for the base plate. For the main board the rules below are a
PROPOSAL built from the mechanical fits.

| Rule | Reason |
|---|---|
| Tab-routed panel. No V-score | A curved outline cannot be scored |
| Break-off tabs with their perforations set back inside the outline. No nub proud of the outline anywhere | The board drops into the tub with 0.25 mm of radial clearance and 0.30 mm at the flat edge |
| No tab on the flat edge between x = -12 and x = +12 | The camera cubes sit 0.2 mm from that edge |
| No tab within about 8 mm of the IMU (nominally at (-11, 6); the layout may move it) | Breaking a tab bends the board locally |
| Panel rails carry the fiducials and tooling holes | The round board has no straight edge to grip |
| Programming and test in the panel is possible through the seven pads | `docs/research/enclosure-manufacturing.md` section 2 suggests in-panel test |

For the **base plate** the rules are REPO (`mechanical/README.md` section 4.1): order
individually routed pieces; if panelised, tabs only on the flat edge, perforations recessed by
at most 0.25 mm, no V-score, no marking, no release agent, flatness 0.5 % or better.

### 3.8 The files the fabricator and assembler receive

For the main board the toolchain writes the set below (REPO: `electrical/tools/README.md`,
"Outputs"). **None of it exists yet for the GL-1** (gate G4).

| File | Content | Goes to |
|---|---|---|
| `<name>-fab.zip` | Gerber X2 for all copper, mask, paste, legend and outline layers; drill files for plated and non-plated holes; drill maps; `README.txt` with stack-up, finish, via protection, minimum track and gap, where the fine tracks are | Fabricator |
| `<name>-assembly.zip` | Pick-and-place file for both sides; grouped parts list with part numbers; `README.txt` with origin, axes, rotation convention, do-not-fit list, fiducial positions, parts whose anchor is not their centre | Assembler |
| `schematic.pdf` | A netlist drawing, complete but not drawn like a hand schematic | Assembler, for fault finding |
| `<name>-board.step`, renders | Bare-board 3-D model and pictures | Both |
| This section 3 | Handling notes | Assembler |

Not produced by the toolchain and still needed: an assembly drawing, a fabrication drawing with
dimensions and tolerances, a panel drawing.

What we ask back: measured board thickness; the X-ray images; cube heights; the moisture log
for the cubes; a list of any substituted part.

---

## 4. Board bring-up and programming station

"Bring-up" means powering a new board for the first time, carefully, and proving each part of
it in turn.

### 4.1 The seven pads

Everything goes through seven gold pads on the underside. The consumer cradle touches four of
them. The factory fixture touches all seven.

```
   Design frame, seen from ABOVE (x to the right). Pad row at y = -17.0 mm, pitch 2.54 mm.

   x =  -7.62   -5.08   -2.54    0.00   +2.54   +5.08   +7.62
        VBUS     D-      D+      GND    SWDIO   SWCLK   NRST
        |------ consumer cradle ------|
        |-------------------- factory fixture ---------------------|

   Seen from BELOW (the way the pads are looked at), left and right are swapped.
```

The order is taken from two statements read together (`DESIGN_SPEC.md` section 3: the list of
names and "the consumer cradle fits the first four pins only"; `mechanical/README.md` section
7: consumer pins at x = -7.62 to 0.0). No netlist exists to confirm it.

| Pad | Job |
|---|---|
| VBUS | 5 V in. Feeds the charger and the USB supply regulator |
| D-, D+ | USB data (full speed) |
| GND | Ground |
| SWDIO, SWCLK | Programming and debug port of the processor |
| NRST | Processor reset |

Three things the pad set does not offer, each a limit on the station (PROPOSAL items; section
11, item 6):

1. **No battery pad.** A board with no cell can only be powered through VBUS and the charger,
   which is set to 20 mA. That is enough for the processor, USB and the grain LEDs (estimate).
   It is not enough for a camera read: two cameras at about 120 mW each (research figure). The
   charger maker's datasheet also says the charger looks for a battery or load on its output
   (VERIFIED extract [S6]); how it behaves feeding a bare board has to be tried. So the
   bring-up station must also feed the two battery solder pads on the top side, from a bench
   supply, through two spring pins or clips.
2. **No 2.8 V pad.** Programming probes usually sense the board's logic voltage on a spare
   pin (PROVISIONAL: general practice). The fixture has to give the probe a fixed 2.8 V
   reference instead.
3. **No way to measure sleep current once the cell is soldered in.** It has to be measured at
   this station, with the bench supply standing in for the cell.

### 4.2 The station

| Item | Purpose | State |
|---|---|---|
| Board nest with seven spring pins on the underside pads and two on the battery pads | Contact without soldering | Not yet defined. The cradle's pin geometry can be reused |
| Bench supply with current limit and a microamp range, set near 3.8 V | Stands in for the battery; measures currents | Standard equipment |
| 5 V supply through a meter | VBUS; measures charge current | Standard equipment |
| Programming probe for SWD | Loads firmware into a blank processor | Standard equipment; model not chosen |
| PC with the factory program | Runs the test list and saves the record | **Does not exist** |
| Voltmeter probes | Rails | Test points for the rails are not yet defined on the board |
| White card | Grain LED and photodiode loop | Not yet defined |

### 4.3 Loading the firmware

| Situation | Method | Notes |
|---|---|---|
| Blank processor (first load) | **SWD** through SWDIO, SWCLK, NRST and GND | The built-in USB loader cannot be relied on for a blank part here: the boot-select pin is not on the pads, and the maker's forum reports that this processor family does not fall into its loader just because the memory is empty (VERIFIED as forum posts [S7]; check the maker's bootloader note) |
| Later update, also on a sealed unit | **USB DFU** through VBUS, D-, D+, GND. The PC sends the unlock command, then the "reboot to loader" command | REPO: `firmware/core/gl_proto.h`. The firmware refuses the jump unless VBUS is present and the cell temperature is inside the charge window. The loader has no time-out: a power cycle or the PC ends it. Nothing watches the cell temperature while the loader runs (gate G6) |
| Read-out protection of the processor, signed images | Not yet defined | |

Calibration data and settings are kept in the separate flash memory chip, not in the processor
(section 6.6). A firmware update by either method leaves them in place.

There is no firmware file to load today. The processor-specific layer has been compiled
against the chip maker's header files but never linked into a loadable file (REPO:
`firmware/README.md` "Status").

### 4.4 What the factory protocol can already test, and what it cannot

The firmware speaks a small command language over USB (REPO: `firmware/core/gl_proto.h`,
`firmware/app/gl_usb.c`). It was tested on the PC simulator only.

**Can do today:**

| Need | Command | What comes back |
|---|---|---|
| Is the unit alive and is the link good | PING | The same bytes |
| Identity | GET_INFO | Protocol version, hardware revision, firmware version and build, solver version, the processor's 96-bit unique number, uptime |
| State | GET_STATUS | Battery millivolts, IMU chip temperature, screen state, flags (VBUS present, charging, charge allowed, unlocked), last error code, number of reads, clock |
| Live IMU data | STREAM, source IMU | Raw acceleration and rotation on three axes, temperature |
| Live calibrated tilt | STREAM, source TILT | Slope in x and y, and whether the unit is still |
| Live battery and charger | STREAM, source POWER | Battery millivolts, VBUS, charging, percent |
| Grain LEDs and photodiode | STREAM, source GRAIN | For each of the 16 LEDs: dark, lit, dark readings |
| Settings | GET_SETTINGS, SET_SETTINGS | 12-byte record |
| Calibration records | GET_CAL, SET_CAL (after unlock) | Tilt, left camera, right camera, grain |
| Calibration procedures | START_CAL (after unlock) | Six-face tilt calibration; grain white reference |
| Field log | LOG_INFO, LOG_READ, LOG_ERASE | Read records and events |
| Clock | SET_TIME | - |
| Restart, or jump to the USB loader | REBOOT (loader needs unlock) | - |

**Cannot do yet:**

| Need | Why not | Consequence |
|---|---|---|
| Read each camera's identity number | The cameras are powered only during a read. A read does not run while USB is attached (the unit is in its "cradle" state). No command asks for it | Test gates 1 and 2 of the assembly sequence cannot be run as written |
| Get a camera picture out | Two picture streams are named in the protocol but not implemented. The only path is the raw-strip log of a normal read, dumped afterwards | Prism centring, the upper-view check, dark-frame light-leak test and camera calibration all need a capture command |
| Show a display test pattern | No command. The unit only draws its cradle screen | Dead rows or a mirrored panel can be missed |
| Report the flash chip's identity | Checked inside the firmware at start; only a failure shows, as an error code | Indirect |
| Run the IMU's built-in self-test | Not used. The firmware only checks the chip's identity byte | Indirect: use the live data instead |
| Report the cell temperature sensor reading | GET_STATUS reports the IMU temperature. The cell sensor appears only in charge events in the log | The sensor is proven only by the charger behaving correctly |
| Force the charger off for a test | No command | Tested at EVT by warming and cooling the sensor |
| Start the zeroing routine from the PC | Refused by design: it needs a half turn, and USB exists only in the one-way cradle | Factory zero must use the on-device menu, or new firmware |
| Camera horizon procedure, grain noise-floor procedure | Answer "unsupported" | Section 6 |
| Write a serial number | No field. The processor's unique number is the identity | Section 7.3 |
| Measure voltages and currents | Outside any firmware | Station instruments |

PROPOSAL: close gate G12 with either new commands in the product firmware or a separate
factory test firmware loaded by SWD, run, and then replaced by the product firmware. The
choice is not yet defined.

### 4.5 Electrical test list

Run in this order. A current limit on both supplies protects a faulty board.

| # | Test | How | Pass limit | Limit comes from |
|---|---|---|---|---|
| 1 | No short circuits | Ohmmeter, power off: VBUS, battery +, 2.8 V rail, each to ground | Not shorted | PROPOSAL (normal practice) |
| 2 | Always-on rail | Bench supply on battery pads at 3.8 V; meter on the 2.8 V rail | 2.8 V nominal. Tolerance not yet defined. It must not fall below 2.7 V, the display's lower limit | REPO: `DESIGN_SPEC.md` section 4; `bom-verification-opto.md` 3.1 |
| 3 | Idle current before programming | Bench supply meter | Not yet defined | - |
| 4 | Program and verify | SWD | Verify passes | - |
| 5 | USB supply rail | VBUS at 5 V; meter on the USB supply pin's rail | 3.3 V nominal; never below 3.0 V | REPO: `DESIGN_SPEC.md` section 4 (the 3.0 V figure is provisional there) |
| 6 | Charger starts by itself | VBUS at 5 V, hold NRST low so the processor is dead. A test cell, or a supply that can absorb current, on the battery pads (an ordinary bench supply cannot). Meter in the battery line | About 20 mA into the battery side. Tolerance not yet defined | REPO: `DESIGN_SPEC.md` section 4, "Charger" |
| 7 | Charger end voltage | Same set-up; let the test cell fill, or raise the load voltage | Charging ends at 4.20 V nominal (charger option named in `bom-verification-ics.md`). Tolerance not yet defined | REPO |
| 8 | Charger stops when told | EVT only: warm the cell sensor above 45 C and cool it below 0 C | "Charge allowed" flag clears and the current stops. Firmware thresholds on the simulator: stops above 43.5 C and below 1.5 C, resumes below 41.5 C and above 3.5 C | REPO: `firmware/README.md` "Charger and cell temperature" |
| 9 | USB link | Plug into the PC; PING, GET_INFO | Unit appears as a serial device; answers; versions as released | REPO |
| 10 | Battery reading | GET_STATUS against the bench meter | Agreement limit not yet defined | - |
| 11 | Flash memory | No error code after start; write a setting, restart, read it back. Expected chip identity C2 28 17 (from memory in the firmware notes: PROVISIONAL) | Setting survives | REPO: `firmware/README.md` register table |
| 12 | IMU | STREAM IMU with the board lying flat and still | Identity byte 0x70 accepted by the firmware (PROVISIONAL value). Total acceleration close to 1 g; band not yet defined. The maker's self-test limits for a sister part are 50 to 1700 mg [S5] (PROVISIONAL for this part; the self-test is not implemented) | REPO; [S5] |
| 13 | Camera rail | Meter on the camera rail, off and during a read | Off: near 0 V. On: 2.8 V nominal, inside the camera's 2.6 to 3.0 V range | REPO: `DESIGN_SPEC.md` section 4; `bom-verification-ics.md` section 2 |
| 14 | Grain loop | STREAM GRAIN over a white card, then in the dark | All 16 LEDs give a lit reading above the two dark readings. A reversed or missing LED shows as one dead channel or a wrong colour pair. Firmware defaults: signal at least 200 counts, dark drift at most 40 counts. Bench target from the research: white-tile spread under 1 % after gain correction | REPO: `firmware/core/gl_cal.c`; `docs/research/grain-sensing.md` 2.3 |
| 15 | Camera identities | Needs gate G12 | Both answer with product number 0x7692 at bus address 0x3C (PROVISIONAL value) | REPO: `firmware/README.md` "OVM7692 register sources" |
| 16 | Camera pictures | Needs gate G12 | A picture from each camera. Limits not yet defined | - |
| 17 | Display signals | The display is not fitted at this stage. With a test display plugged into J1 the cradle screen appears; a full test pattern needs gate G12. Display clock 59.9 Hz (32768 / 547) | Inside 54 to 65 Hz and 1 to 60 Hz, the two ranges the maker publishes | REPO: `DESIGN_SPEC.md` section 4, "LCD" |
| 18 | Sleep current | Remove VBUS; wait for sleep; bench supply microamp range | **Not yet defined in the repository.** PROPOSAL (`VALIDATION_PLAN.md` test F4): at most 25 microamps at the pads. The firmware simulator's supply model gives 20.6 microamps asleep with the cell's protection circuit, so about 17.6 at the pads: processor 9, IMU waiting for motion 5, regulator and battery divider about 3.5, memory 0.1 (every current provisional; nothing measured). The power research's 4.7 to 12 mAh per month (about 7 to 17 microamps) is for an **older architecture, not rev D**, and it includes the protection circuit, which a bench supply on the battery pads does not see | `firmware/README.md` "Battery life under the supply model"; `DESIGN_SPEC.md` sections 3 and 4; `VALIDATION_PLAN.md` 2.7; `docs/research/power.md` section 2 (older architecture) |
| 19 | Wake on motion | Tap or lift the nest | Unit wakes; current rises | REPO |

Tests 1 to 14 and 18 to 19 can be run with today's firmware once it runs on the processor.
The "on" half of test 13 needs a read, which the board starts by itself when it is moved and
then left flat and still with USB unplugged. Tests 15 to 17 wait for gate G12.

---

## 5. Mechanical assembly

The full step-by-step text, with every dimension, is `mechanical/README.md` section 7
(19 steps). This section does not repeat it. It groups the steps into stations and says what
each station needs.

### 5.1 Two lines that meet

```
 TUB LINE (the "case")                      BOARD LINE (the "movement")
 --------------------------------           -------------------------------------
 T1  inspect, gauge, clean, prime           B1  ball feet into base plate
 T2  cover glass on its tape ring           B2  adhesive sheet onto base plate
 T3  two visor windows                      B3  baffle ring; board onto base plate
 T4  vent disc                              B4  clear potting         <-- no return
 T5  two hood gaskets                       B5  battery, prisms, edge fillet
 T6  display and foam pad                   B6  TEST GATE 1
 T7  TUB LEAK TEST
              \                               /
               \                             /
                J1  dry trial close: pair this unit with this tub, mark both
                J2  seal bead, plug in display tail, close
                J3  TEST GATE 2 while the glue is still wet
                J4  cure under a weight            <-- no return
                J5  leak test, function test, dark frames
                J6  one temperature cycle, then calibration (section 6)
```

### 5.2 Station table

"Step" is the step number in `mechanical/README.md` section 7. Adhesives are classes, not
products: none is chosen. Cure times come from the chosen product's data sheet and are not yet
defined.

| Station | Steps | Fixture or gauge | Adhesive class | Cure | Check | Main risk |
|---|---|---|---|---|---|---|
| T1 Incoming and prep | 1, 4 | Bore discs, bay block, spigot ring gauge, dummy unit, ring lapping gauge, thickness gauge | Primer or plasma on every printed bonding face, as the adhesive maker says | Primer flash-off | Tub: seal face 0.60 and rim 1.55 below the post feet, each within +-0.1. Dummy unit seats on all eight posts. Plate thickness 0.76 to 0.90. Rings lapped to plate thickness + 0.02 | A tub outside the two required dimensions is not used. Bureaus quote +-0.2 to 0.3 |
| B1 Ball feet, stage 1 | 2 | Ball-setting gauge plate, clamp weight | Dual-cure or two-part epoxy, 0.27 mm3 per hole, fed from one side | Complete, before unclamping | Protrusion 0.10 +-0.02 on all three. Full ring of epoxy seen from below, no void | Air trapped under the ball. Tiny dose |
| B2 Sheet onto plate | 3 | Lamination jig | Die-cut double-coated adhesive sheet, 0.20 mm | Pressure only | Sheet clear of the seal land all round | 0.25 mm of error puts adhesive on the 0.4 mm seal land |
| T2 Cover glass | 5 | Mandrel that supports the roof from inside | Transfer-tape ring 0.13 mm; then a black wicking sealant in the 0.25 mm rim gap | Tape dwell; sealant cure | Crystal below the top face (0.12 nominal), never proud | Sealant flooding onto the crystal |
| T3 Visor windows | 6 | Window stop | Light-cure, thixotropic. A closed frame round the glass edge. Nothing behind the glass | Light, through the window | Glass 0.15 below the visor face. Frame closed on four sides. Nothing in the opening | Adhesive at the roof edge of the opening costs upper view: the margin is 0.054 mm |
| T4 Vent | 7 | - | Self-adhesive vent disc | Pressure | Centred on the 1.0 mm hole | Hole fused shut in printing: clear with a 1.0 mm drill |
| T5 Hood gaskets | 8 | Needle guide | Black, soft, silicone-free form-in-place gasket | Light, before the next step | Bead on the flat of the wall, not on its chamfer. Window -0.10 / +0.08 mm | A misplaced bead leaks light or enters the view |
| T6 Display | 9 | Vacuum pen | Adhesive frame 0.15 mm on the glass, with a vent channel; foam pad | Pressure | Bonded all round the 22 mm aperture | Glass cracked while tilting in. Position not squared (section 11, item 10) |
| T7 Tub leak test | 10 | Leak tester with gasketed plate | - | - | Pressure decay. Limit not yet defined | A leak found here can still be fixed |
| B3 Board onto plate | 11 | Lamination jig, ring tool, press plate, depth gauge, pogo fixture | Black tape ring under the baffle; two-part room-temperature epoxy on each copper land (0.52 mm3); the adhesive sheet | Epoxy cure at room temperature | Ring gap visible at all four photodiode corners. Ring crest 0.00 to 0.15 mm inside the base plane. Sheet edge sealed at pad slot and grain opening. All 16 LEDs and the photodiode tested | Last chance to repair LEDs. Plate offset makes the unit bind in the tub later |
| B4 Clear potting | 12 | Potting nest, volume dispenser, vacuum bell, mask, depth gauge | Clear, hard, low-fluorescence optical epoxy; 93.4 mm3 nominal, corrected per unit | Complete, at 60 C at most | Level checked wet. After cure: no bubble over photodiode or LED, none over 0.3 mm elsewhere (provisional figure), surface never closer than 0.05 mm to the base plane, not tacky | **No rework after cure.** A proud or tacky surface scraps the board |
| B5 Battery, prisms | 13 | Prism jig, prism height gauge | Transfer adhesive 0.05 mm under the cell; UV adhesive at four prism corners; a fine fillet of seal adhesive round the board edge | Light; gel | Lead joints under 2.4 mm. Prism top at most 4.85 mm above the board | Heat on the cell. Adhesive over the lens. From here on nothing above 45 C |
| B6 Test gate 1 | 13 | Pogo fixture | - | - | Supply, both camera identities, one picture per camera (prism centring), IMU, charge current, grain loop through the potting | Needs gate G12 |
| J1 Dry trial close | 14 | Join fixture, depth gauge | None | - | Seats on all posts without force. Base plate 0.25 +-0.15 mm proud of the tub rim at four points, the four readings equal within 0.05 | A unit that binds is tried in another tub. Spare tubs are needed |
| J2 Seal and close | 15 | Join fixture, volume dispenser, magnifier | Black, thixotropic structural adhesive, 70 mm3 as one unbroken bead | Open time of at least an hour | Display test pattern before closing. Same four rim readings as the dry close | Display tail mating with the unit open is not yet demonstrated |
| J3 Test gate 2 | 16 | Join fixture with pogo block | Top-up fillet from outside | - | Pictures from both cameras through the windows; target at the top of the view seen by both; dark frames under side light; display; IMU. Then a continuous fillet all round | Needs gate G12. Last chance to open and correct |
| J4 Cure | 17 | Press weight | - | Full data-sheet time, room temperature or 45 C at most | - | **No rework after this** |
| J5 Leak and function | 18 | Leak tester with the soft pad over the vent | - | - | Pressure decay (free air volume 4.2 cm3; limit not yet defined). Function. Dark frames | - |
| J6 Cycle and calibrate | 19 | Temperature chamber; calibration fixtures | - | One cycle -10 to 50 C | Section 6 | - |

One step is missing from the README sequence: the specification asks for a dab of thermal
adhesive joining the cell temperature sensor to the cell. It belongs in station B5 (section
11, item 5).

### 5.3 Fixtures and gauges

None of these is drawn or made. "How it is made" repeats the description in
`mechanical/README.md` section 2; where that is all there is, the making method is not yet
defined.

| # | Fixture or gauge | Used at | What it controls | How it is made |
|---|---|---|---|---|
| 1 | **Ball-setting gauge plate** | B1 | Ball protrusion of 0.10 mm. A 1.0 mm ball resting on the rim of a 0.60 mm hole stands exactly 0.10 mm below the plate face | A flat ground plate with three reamed 0.60 mm holes, at least 0.3 mm deep, at (0, 15.0), (-16.5, -9.5), (16.5, -9.5). A weight with windows clamps the base plate flat. Loose guides only: the three balls locate the plate. A baked dry PTFE release film, silicone-free |
| 2 | **Lamination jig** | B2, B3 | Position of the adhesive sheet on the plate, and of the plate on the board. Keeps the press load off the cameras | A nest for the component side with a pocket for every part. Two sprung 1.10 mm pins, 28.7 mm apart, that stand 2 mm above the board and are pushed flush by the plate. Three sprung fingers that centre the D outline. Two 3.0 mm posts at (+-27, 0) for the tooling holes of the sheet's liner. A flat press plate with three relief holes; about 116 N |
| 3 | **Ring tool** | B3 | Position of the baffle ring round the photodiode (0.59 mm gap) | Sits on the two sprung pins of the lamination jig |
| 4 | Ring lapping gauge | T1 | Ring height = plate thickness + 0.02 mm, +0.00 / -0.03 | A plate with a pocket whose depth is set by shims, and a flat stone |
| 5 | **Potting nest** | B4 | Level of the underside to 0.25 degree or better (0.06 mm across the opening) | Carries the unit underside-up on bare board areas. Used with a positive-displacement dispenser good to +-3 % on 0.10 ml, a vacuum bell, a low-tack mask with a hole of 15 mm or more, and a depth gauge with a 2 mm foot or an optical height sensor |
| 6 | Prism jig | B5 | Prism position on the cube: exit face at y = 16.6 | References the board's hole and slot. Otherwise not yet defined |
| 7 | Window stop | T3 | Window top edge 0.15 mm below the tub top | A plate on the tub top with a 0.15 mm step that enters each window recess |
| 8 | **Needle guide** | T5 | Gasket bead centre 0.35 mm in front of the hood rear wall, good to +-0.075 mm | A fork that hooks on the rear face of the hood wall and steers the needle |
| 9 | **Join fixture** | J1 to J4 | Brings board unit and tub together square, within +-0.1 mm sideways | A nest for the upturned tub with a window or mirror under the display and an open front for the cameras. A hinged carrier for the board unit, hinge parallel to x at y = -30, z = 0. A press plate with relief holes over the ball feet, and a seven-pin spring block that reaches the pads through it |
| 10 | **Bore discs** (two go gauges) | T1 | Tub ledge and bore are large enough | A 42.6 x 1 mm disc must pass the ledge ring. A 43.7 x 1 mm disc must enter the bore below it |
| 11 | Bay block, spigot ring gauge, prism height gauge | T1, B5 | Bay roof at least 4.90 mm above the post feet. Spigots no larger than 1.10 mm. Prism top at most 4.85 mm above the board | Simple ground gauges |
| 12 | **Dummy unit** | T1 | That a worst-case board with cameras and prisms fits this tub | A plate with the board outline, hole and slot at their smallest, and two stepped blocks at the camera positions (3.77 x 3.25 x 2.81 mm, then 2.3 x 2.3 mm up to 4.85 mm). It must seat on all eight posts with the blocks inside the hoods |
| 13 | **Leak tester** | T7, J5 | Finds a leaking tub or unit before it ships | A pressure-decay instrument. For a tub: a gasketed plate that closes the open underside. For a unit: a chamber with a soft pad that blocks the vent hole and its grooves. Test pressure and limit not yet defined |
| 14 | Pogo test fixture (seven pads) | B3, B6 | Electrical access | Same pin geometry as the factory cradle |
| 15 | Cover-glass mandrel; tub nest | T2 to T6 | Supports the roof while parts are pressed on | Not yet defined |
| 16 | Depth gauge; small surface plate | B1, B3, J1, J2 | Ball protrusion, ring crest, rim relief | Standard instruments |
| 17 | Calibration fixtures | J6 | Section 6 | Section 6 |
| 18 | Cradle pin soldering jig | Cradle | Pins square to the cradle board | Not yet defined |

Pressure decay in one sentence: the tester puts the unit in a small closed space at a set
pressure and watches the gauge; a leaking unit lets air in or out and the reading drifts.

### 5.4 The adhesives, by class

None is selected (gate G7). REPO: `mechanical/README.md` sections 2 and 12.

| # | Joint | Class | Limit that matters |
|---|---|---|---|
| 1 | Perimeter seal, tub to base | Opaque black, thixotropic, structural (acrylic or epoxy, not silicone rubber) | Cures at room temperature or 45 C at most. Holds peel at 70 C on primed PA12 and on solder mask. Work life an hour or more |
| 2 | Ball feet, stage 1 | Dual-cure or two-part epoxy | Must cure in the shadow of the ball: a UV-only adhesive stays liquid there |
| 3 | Ball feet, stage 2 | Two-part room-temperature epoxy | Sits between two opaque boards |
| 4 | Board to base plate | Double-coated tape sheet 0.20 mm (0.13 mm transfer tape in the PA12 build), die cut | Bond strength of this tape family builds with time and temperature (VERIFIED extract of the maker's data sheet [S10]). The press load of 0.10 MPa used in the README was not found in a source |
| 5 | Visor windows | Light-cure, thixotropic | Must not wick behind the glass |
| 6 | Cover glass | Transfer-tape ring 0.13 mm, plus black wicking rim sealant | Thin tape on smoothed PA12 needs primer and dwell |
| 7 | Hood gasket | Black, about Shore A 40, silicone-free, form-in-place | Holds a 0.5 x 0.33 mm bead without slumping |
| 8 | Clear potting | Clear, hard, low fluorescence, non-yellowing, thin enough to level | Cure at 60 C at most. Low shrinkage. Stiffness to be chosen: it pulls on the board that carries the IMU |
| 9 | Prisms | UV adhesive at four corners | Air gap over the lens |
| - | Also: display frame tape, black tape ring for the baffle, cell fixing tape, foam pad, thermal adhesive at the cell sensor | | |

### 5.5 Rules that hold at every station

- After the cell is on the board (station B5), nothing is heated above 45 C.
- No silicone anywhere near a bonding face: not in release agents, gloves or hand cream.
- The camera cube tops, prisms and window inner faces are optical surfaces. Inspect and swab
  before each is closed in.
- Each board unit is paired with one tub at the dry close and both are marked.
- Wear a grounded wrist strap when handling the bare board.
- The EVT units are labelled "not step-proof".

---

## 6. Calibration

Calibration means measuring each unit's own small errors once, and storing numbers that
correct them. It is done after the unit is sealed, the adhesive has fully cured, and the unit
has been through one temperature cycle of -10 to 50 C, so that the stresses frozen in by the
adhesives have relaxed (REPO: `mechanical/README.md` step 19). It is never done in the
charging cradle.

### 6.1 Overview

| Calibration | What it corrects | Firmware today |
|---|---|---|
| Level: six-face | The IMU's own zero, scale and axis alignment | **Implemented** as a USB procedure |
| Level: zero on the granite plate | The angle between the IMU and the plane of the three ball feet | Implemented only as the user's on-device zeroing. **No factory trigger** |
| Level: temperature | Drift of the zero with temperature | **Not implemented as a procedure.** The numbers can be written, but no tool computes them |
| Stereo cameras | Each camera's focal length, centre and distortion; where each camera points | **Not implemented.** The numbers can be written; no capture command, no procedure, no tool |
| Grain: white reference | Brightness differences between the 16 LEDs | **Implemented** as a USB procedure |
| Grain: noise floor | The threshold below which a grain reading is ignored | **Not implemented.** It is a turf experiment, not a per-unit step |
| Display | Nothing is stored | A check only. No test-pattern command |

### 6.2 Level calibration

The target for the whole tilt chain is 0.5 to 1 mrad (REPO: `DESIGN_SPEC.md` section 3).

**Step A: six-face.** Like checking a kitchen scale by weighing the same known weight on each
of its sides: gravity is the known weight, and the unit is held still with each of its six
faces up in turn.

- REPO (`firmware/core/gl_proto.h`, `firmware/app/gl_app.c`): the PC unlocks the unit, then
  for each face 0 to 5 (+x, -x, +y, -y, +z, -z up) sends "start"; the unit averages for about
  one second while still. A seventh command computes offset and a 3 x 3 correction matrix,
  stores them, records the temperature and sets the "factory calibrated" flag.
- The commands travel over USB, and USB exists only through the pads. So the fixture must hold
  the marker in six orientations **with spring pins on its pads**. That fixture is not yet
  defined. The README's calibration fixture is a flat nest with no contacts.
- PROPOSAL: a machined cube that clamps the marker and carries a seven-pin block. Ordinary
  squareness is enough, because errors of the cube largely cancel between opposite faces.
- While USB is attached the charger is on and the processor does not sleep. The unit is warmer
  than in use. The effect on the stored zero is unmeasured (section 11, item 8).

**Step B: zero on the granite plate.** A granite surface plate is a thick slab of stone ground
very flat. The marker stands on it on its own three ball feet. The plate does not have to be
level: the reading is taken, the marker is turned half a turn in place, and the reading is
taken again. Like checking a spirit level by turning it end for end, the plate's own slope
cancels and what is left is the marker's error.

- REPO: the firmware has this as the user routine (settings menu, "ZERO"): read, "TURN 180",
  the gyroscope measures the turn, read again, solve, store with temperature and time. It
  refuses if VBUS is present, if the turn is more than 30 degrees away from a half turn, or if
  the result is larger than 5 % slope. The PC cannot start it.
- For EVT this can be run by hand from the menu on the plate. For production a factory
  trigger and a four-position version (0, 90, 180, 270 degrees, as the tilt research
  recommends) are needed. Not yet defined.
- The plate. For a 12 x 18 inch plate the standard grades allow an overall flatness error of
  50, 100 and 200 millionths of an inch (about 1.3, 2.5 and 5 micrometres) for grades AA, A
  and B (VERIFIED extract of a metrology maker's bulletin [S8]). The feet are 33 mm apart, so
  even grade B is of the order of 0.1 mrad or better under the marker (our arithmetic). Dust
  is the larger risk: one 10 micrometre grain under a foot is about 0.3 to 0.4 mrad.
- The README's "three-point nest" that locates the marker on the flat for repeatable turns is
  not yet defined.

**Step C: temperature.** REPO: the specification asks for per-unit temperature compensation.
The record holds two drift numbers per axis (a straight-line term and a curve term). The tilt
research asks for at least five temperatures across about 0 to 55 C, or a slow ramp up and
down, with a 0 and 180 degree pair at each point, and for the result to be judged on points
that were not used for the fit (`docs/research/inertial-sensors.md` section 2).

- With today's firmware the raw data can be collected (STREAM IMU gives acceleration and
  temperature) and the result can be written (SET_CAL). The PC tool that fits the numbers,
  the chamber fixture with a flat reference and pad contact inside it, and the temperature
  list do not exist. Not yet defined.
- Acceptance from the system owner for the EVT drift test: under 0.05 mrad per kelvin after
  correction; repeat within 0.3 mrad after a -10 to 50 C cycle.

### 6.3 Stereo camera calibration

Two cameras judge distance the way two eyes do: by how far an object shifts between the left
and the right picture. If the two "eyes" are not exactly parallel and the device does not know
by how much, every distance is wrong by the same factor. The numbers are small: a shift error
of 0.1 px, which is 0.15 mrad between the cameras, moves the distance by about 3 % (REPO:
`sim/results/REPORT.md` section 6).

What is stored per camera (REPO: `firmware/core/gl_cal.h`): focal length in x and y, image
centre in x and y, one lens distortion term; three pointing angles (pitch, yaw, roll) relative
to the marker; the position of the lens in the marker; two flags (intrinsics present,
extrinsics present). An uncalibrated unit runs on the nominal design values (657 px focal
length, centred, no distortion, zero angles). A comment in that header file says the display
should show reduced confidence while a flag is missing. **The firmware does not do this**:
nothing lowers the confidence, or shows anything, when a camera or tilt calibration is
missing (section 6.9, item 8). The unit itself gives no warning.

**The procedure is not yet defined, and the firmware cannot support one today**: there is no
command that captures a picture and sends it out. The points below are a PROPOSAL for what the
procedure has to contain.

| Element | Proposal | Why |
|---|---|---|
| Pose | Marker on the granite plate nest, so gravity is known from step B | The cameras are referenced to gravity |
| Target | Thin vertical lines or lit slits at known positions, on a wall or frame | The device measures a flagstick, a vertical line; the line finder already exists |
| Distances | At least two, both known to about 1 %, for example near 2 m and near 6 m. Expected shift: 13.14 px divided by the distance in metres, so 6.6 px at 2 m and 2.2 px at 6 m | Two distances separate a pointing error from a scale error. The focus range of the fixed lens is not published, so the near distance must be confirmed on the first units |
| Height marks | Marks at known heights up to the top of the view | Checks the upper view angle on every unit |
| Result | Per-camera record written with SET_CAL, both flags set | - |
| Repeat check | Capture again after re-seating the unit; the shift must repeat within 0.05 px | 0.05 px is the uncertainty the firmware assumes (`GL_PROV_STEREO_CAL_SIGMA_PX`) |

Room, lighting, target size and tolerance, and whether lens parameters are measured per unit
or taken as fixed: not yet defined.

### 6.4 Grain sensor reference

- **White reference (implemented).** The marker sits on a white tile. The PC sends the
  procedure command. The unit lights each of the 16 LEDs in turn, measures, and stores one
  gain per LED (average 1.0) and a flag. This removes the false pattern that unequal LEDs
  would create. Bench target from the research: spread under 1 % afterwards. The tile grade
  and the standoff are not yet defined. It is done through the clear potting.
- **Noise floor (not implemented).** The acceptance threshold should come from at least 50
  readings on turf with no lean (research gate 0). Until then the default threshold of 0.30
  stays, and the grain sensor ships switched off.

### 6.5 Display check

Nothing is stored for the display. Its orientation and the offset of its active area are
fixed constants in the firmware and are provisional. The check is by eye or by a camera over
the unit: every row and column lights; the picture is the right way round; the round picture
is centred in the 22 mm window; a straight test line is parallel to the marker's forward axis.
The test pattern command does not exist (gate G12). The allowed rotation of the line is not
yet defined (section 11, item 10).

### 6.6 What is stored where

All calibration and settings live in the separate flash memory chip on the board, in a small
store that survives power cuts (REPO: `firmware/README.md` "Storage";
`firmware/app/gl_app_cfg.h`).

| Record | Size | Content | Written by |
|---|---|---|---|
| Tilt (`GL_CAL_ID_TILT`) | 94 bytes | Zero offset on three axes; two temperature terms per axis; reference temperature; 3 x 3 matrix; zeroing bias in x and y with its temperature and time; flags (factory, zeroed) | Six-face procedure; zeroing routine; SET_CAL |
| Left camera, right camera (`GL_CAL_ID_CAM_L`, `_R`) | 46 bytes each | Section 6.3 | SET_CAL only |
| Grain (`GL_CAL_ID_GRAIN`) | 78 bytes | 16 LED gains; acceptance threshold; measured noise floor; two reject limits; flags | White-reference procedure; SET_CAL |
| Settings (`gl_settings`) | 12 bytes | Green speed, units, stopping distance, grass type, grain on or off, logging level, method, dialled distance | Menu on the device; SET_SETTINGS |
| Learned flagstick height | small | Learned in use | The device |

Layout: the first 4 sectors of the 8 MB chip (16 kB) hold this store. The other 2044 sectors
hold the read log. Because the store is not in the processor, a firmware update does not erase
it. Because it is on the board, a replaced board loses it. The factory PC should read every
record back with GET_CAL and file a copy under the unit's identity (section 7.3).

### 6.7 Time per unit (estimate)

Assumptions: fixtures and PC tools exist and work; one operator; units handled in batches so
chamber time is shared. Nothing here has been timed.

| Step | Hands-on time | Waiting |
|---|---|---|
| Six-face | 5 min | - |
| Zero on the granite plate (four positions) | 5 min | Unit at room temperature first |
| Temperature points (five) | 10 min | 3 to 4 hours of chamber time per batch |
| Stereo cameras, two distances, with repeat | 10 to 15 min | - |
| Grain white reference | 2 min | - |
| Display check | 2 min | - |
| Read back, file, check flags | 5 min | - |
| **Total** | **about 40 to 45 min** | **about half a day per batch** |

### 6.8 Pass limits

| Item | Limit | Status |
|---|---|---|
| Six-face solve | Completes without error | REPO. A limit on the size of the offsets is not yet defined |
| Zeroing | Refused by the firmware above 5 % slope bias or with a turn more than 30 degrees off | REPO. A tighter factory limit is not yet defined |
| Tilt after temperature correction | Under 0.05 mrad per kelvin; repeat within 0.3 mrad after a cycle | REPO (owner's EVT acceptance). Not yet confirmed as the production limit |
| Tilt accuracy overall | 0.5 to 1 mrad target | REPO |
| Stereo repeatability | 0.05 px assumed by the firmware | REPO as an assumption. Not a set limit |
| Upper view angle | 14.5 degrees guaranteed by the parameter file; 17.6 nominal | REPO. The limit to test against is not yet decided |
| Grain white reference | Spread under 1 % after correction | Research target, unverified there |
| All flags set | Tilt "factory"; both cameras "intrinsics" and "extrinsics"; grain "white reference" | PROPOSAL |

### 6.9 Calibration steps the firmware does not yet implement

1. Any way to capture a camera picture on command and send it to the PC.
2. The camera calibration procedure itself (`CAM_HORIZON` answers "unsupported").
3. The temperature fit as a procedure (the fitting routine exists in the core code; nothing
   calls it; no PC tool).
4. A factory-started zero on the granite plate, and a four-position version of it.
5. The grain noise-floor procedure (`GRAIN_FLOOR` answers "unsupported").
6. A display test pattern.
7. The PC-side program for all of the above. None exists.
8. Any sign on the unit that a calibration is missing. The header comment in
   `firmware/core/gl_cal.h` ("The UI shows reduced confidence while a flag is missing") is
   not implemented. The function that computes the shown confidence (`shown_confidence_` in
   `firmware/app/gl_app.c`) has factors only for a one-camera read, a second line in view,
   the disparity uncertainty and a fit that did not converge. The two camera flags are
   defined but never read. So final test 4 ("all calibration flags set", section 7.1) is
   the only guard against shipping an uncalibrated unit.

---

## 7. Final test, cosmetics, traceability, packing, and the cradle

### 7.1 Final test

Run after calibration. Items marked (G12) wait for the factory test path.

| # | Test | Pass |
|---|---|---|
| 1 | Leak test repeated after the temperature cycle (PROPOSAL: the README tests only before the cycle) | Limit not yet defined |
| 2 | Dock in a **consumer** cradle: latches, charges, appears on USB | Charging flag set; PING answers |
| 3 | GET_INFO, GET_STATUS | Released firmware version; no error code; battery in range |
| 4 | All calibration flags | Set (6.8) |
| 5 | A complete read outside the cradle at a test target, repeated | Distance, bearing and slope inside limits. Limits not yet defined |
| 6 | Dark-frame light-leak test under strong side light (G12) | Limit not yet defined |
| 7 | Display check (G12) | 6.5 |
| 8 | Wake on pick-up; sleep after 45 s | Works |
| 9 | Set the clock; erase the log; write default settings; lock | Done and read back |
| 10 | Battery state for shipping | 7.4 |
| 11 | Cosmetic inspection | 7.2 |

### 7.2 Cosmetic criteria

From the repository:

| Feature | Accept | Source |
|---|---|---|
| Cover glass | At or below the top face (0.12 mm below, nominal). Never proud. No sealant on the glass | `mechanical/README.md` step 5, open issue 11 |
| Visor windows | Below the visor face and the tub top. Adhesive frame not proud: check with a straightedge. Nothing in the opening | Step 6, open issue 11 |
| Rim | One continuous fillet of black adhesive all round, across the visor front and at both D corners. Excess wiped | Step 16 |
| Grain window | Clear, hard, no bubble over a part, not proud | Step 12 |
| Vent | Hole and both grooves open | Step 1 |
| Ball feet | Three, equal, complete epoxy ring | Step 2 |

Not yet defined: scratch and blemish limits on the tub and glass, colour, markings, a place
and method for the product label and any regulatory marks.

### 7.3 Serialisation and traceability

The only identity the firmware knows is the processor's 96-bit unique number (GET_INFO).
There is no serial-number field and no label is specified. PROPOSAL: use the unique number as
the key of the record, and print a short serial derived from it on the box and the base.

What should be logged for each unit (PROPOSAL; none of it exists yet):

| Group | Logged |
|---|---|
| Identity | Unique number, short serial, hardware revision, firmware version and build, build date, operator |
| Lots | Board lot and panel position; tub lot; base plate lot and measured thickness; baffle ring height; lot of every adhesive and its expiry date; cube reel and time out of the dry bag |
| Board test | Every value from section 4.5; X-ray image reference |
| Assembly measurements | Ball protrusions (3); ring crest; potting level wet and after cure, and dispensed volume; prism heights (2); rim relief at four points, dry and sealed; which tub was paired |
| Gates | Test gate 1 and 2 results; tub and unit leak results, before and after the temperature cycle |
| Calibration | A copy of all four calibration records; residuals; the temperatures used; fixture identity |
| Final | Final test values; cosmetic result; battery state at packing |
| Build variant | For EVT: base plate material, potted or not, "not step-proof" |

### 7.4 Packing

Box contents, box design and inserts are not yet defined. What the repository and today's
checks say must be respected:

| Topic | Requirement | Status |
|---|---|---|
| Rules statement | "For practice and training. Not permitted during a round played under the Rules of Golf (Rule 4.3)." on the box and the quick-start card | REPO: `docs/research/rules-compliance.md` 2.1 (unverified there) |
| User instructions that affect reliability | Dry the marker before docking. Press the thumb tab to release; never pull the marker out. Zero the marker on a hard flat surface, never on turf and never in the cradle | REPO: `mechanical/README.md` section 7; `firmware/README.md` |
| Lithium cell in transport | The research classes the product as a lithium-ion cell contained in equipment (UN3481), shipped with a test summary available | PROVISIONAL (`rules-compliance.md` 2.2, unverified there) |
| State of charge for air transport | For cells contained in equipment, the air transport association (IATA) recommends no more than 30 % charge in 2026; it is a recommendation, not a rule, for this packing class. The rule that became mandatory on 1 January 2026 covers cells packed beside equipment above 2.7 Wh. The GL-1 cell is about 0.16 Wh (43 mAh x 3.7 V) | VERIFIED as a training provider's summary [S9]. Confirm against the regulation text before the first shipment |
| How the factory sets a state of charge | No command stops charging at a chosen level | Not yet defined |
| What shipping at 30 % does to shelf life | A cell at 30 % holds about 13 mAh. The marker's motion wake-up stays on while it sleeps, as the firmware is written. On those terms the cell may be empty in about a month: 26 days by the firmware's own supply model (20.6 microamps asleep), one to two months by the power research's older figures; the 2.3 to 3.8 months quoted there assume no wake-up source (`VALIDATION_PLAN.md` test Q1). The charger revives a flat cell by design, but the buyer would unpack a dead product. A ship mode that keeps the wake-up off until the first docking is proposed in `docs/COMPLIANCE.md` row 12. It is not in the repository, and even with it the always-on loads of rev D must be measured before any shelf-life figure is promised | Estimate, unmeasured. Not yet defined |
| EVT units | Labelled "not step-proof" | REPO |
| Origin wording | Never an unqualified "Made in USA". See `docs/SOURCING.md` for the origin of each part | REPO: `rules-compliance.md` 2.2 |

### 7.5 The charging cradle: build and test

REPO: `mechanical/README.md` sections 7 and 8, `master_params.yaml` `cradle`. The cradle board
has no schematic yet.

Build:

1. Printed body arrives. Drill the four 1.6 x 3 mm pilot holes at the printed spot marks.
2. Solder the spring pins into the cradle board, square to it, in a soldering jig. Consumer
   cradle: four pins (VBUS, D-, D+, GND). Factory fixture: all seven.
3. Solder the USB-C socket and the resettable fuse.
4. Screw the board against the pocket ceiling with four M2 thread-forming screws. The pins
   come up through the slot in the nest floor.
5. Fit the four self-adhesive feet.

Test:

| Test | Pass | Source |
|---|---|---|
| Measurements on first articles: front nest wall to hook nose; latch beam thickness at three heights | 39.95 +-0.15 mm; 1.03 / 0.95 / 0.89 mm | REPO |
| Pin height with a marker seated | 5.82 mm working height; 1.14 mm of 2.29 mm stroke used | REPO (pin data provisional) |
| Fit | Marker goes in one way round only. Clicks home at about 11 N. Releases at 9 to 12 N on the thumb tab | REPO (calculated) |
| Retention | Pull of 12.4 N at the pin row (three times the seven-pin force) does not release the marker | REPO |
| Life, on first articles from two print builds | 3000 insert and release cycles; hook position before and after | REPO |
| Electrical | 5 V on the VBUS pin with a USB-C source; data lines continuous; fuse resets. Limits not yet defined | PROPOSAL |
| USB-C detail | A USB-C socket needs two pull-down resistors to be given 5 V by a USB-C charger. The power research names two 5.1 kilohm parts; the specification does not mention them | PROVISIONAL |
| With a known-good marker | Charges; appears on USB | PROPOSAL |

The cradle latch is sized for printed PA12 in a locked print orientation. Do not change the
material or the orientation without redoing the latch numbers (REPO).

---

## 8. Yield and risk: the ten steps most likely to scrap a unit

No yield figure exists, because nothing has been built. The ranking is this plan's judgement.
Nine rows come from the open issues in `mechanical/README.md` section 12. Row 4 comes from the
release gate on the camera footprint in `DESIGN_SPEC.md` section 7; the added worry about
soldering a tall cube on hidden joints is this plan's.

| Rank | Step | Why it can scrap a unit | Control in place | Can be fixed until | Source |
|---|---|---|---|---|---|
| 1 | Clear potting of the grain opening (station B4) | The level window is 0.10 mm and a proud or tacky surface is a reject. Bubbles over an LED. The resin may climb the wall. Nothing can be reworked after cure | Dose by volume with a per-unit correction; level checked wet and trimmed; vacuum; free edge kept sharp by the mask; LEDs tested just before | Wet: yes. Cured: never | Open issue 15; deviation D32 |
| 2 | Seal and close (J2 to J4) | A 0.4 mm land, a joint whose height varies from 0.27 to 0.53 mm, an adhesive not yet chosen, and a one-way cure | Dry trial close first; dose 70 mm3; four rim readings must match the dry close; test gate 2 with the glue wet; leak test after cure | The adhesive's open time | Open issues 10, 24 |
| 3 | Plugging the display tail into J1 with the unit half open | The tail length and pin-1 side are unconfirmed. A mirrored connector kills every board of the lot. The mating itself is "not demonstrated" | Gate G2; mock-up trial before any sealed unit; display test pattern before closing | Step 15 | Open issue 9; `DESIGN_SPEC.md` section 7 |
| 4 | Soldering the camera cubes | Provisional footprint and orientation; tall part on hidden balls; unknown oven limits | Gate G1; X-ray of every cube; height check; board test before any mechanical work | Board level (rework station), before lamination | `DESIGN_SPEC.md` section 7 |
| 5 | Visor window bonding (T3) | Adhesive that reaches the roof edge of the opening removes upper view; the margin is 0.054 mm. The seal is a thin frame on the glass edge | Thixotropic adhesive, nothing wicked; window stop; inspection through the bay; top-of-view target at gate 2 | Step 15 | Open issues 1, 12; deviation D30 |
| 6 | Prism bonding (B5) | Prism top must stay under 4.85 mm with 0.19 mm of roof clearance and +-0.21 mm of stack tolerance. Adhesive over the lens ruins the camera | Prism jig; four corners only; height gauge; picture check at gate 1 | Before the UV cure; afterwards the cube is lost with it | `mechanical/README.md` section 5, tolerance chains; open issue 18 |
| 7 | Ball feet, stage 1 (B1) | A void under the ball is the foot's only mechanical lock. The dose is 0.27 mm3. Protrusion must be 0.10 +-0.02 | Gauge plate; feed from one side; inspect from below; protrusion check | Step 11 (re-pot) | Open issue 14 |
| 8 | Laminating the board to the base plate (B3) | Sheet on the seal land; epoxy flooding the sheet; ring crest proud; plate off-centre so the unit later binds in the tub | Lamination jig; liner tooling holes; 85 % dose; crest gauge; dry trial close | Step 12 | Open issues 24, 25 |
| 9 | Hood gasket bead (T5) | Placement window of -0.10 / +0.08 mm; cured shape is assumed. A bad bead is a light leak found only in the dark-frame test | Needle guide; cure and inspect before the display goes in; dark frames at gate 2 | Step 15 | Open issue 16 |
| 10 | Tub dimensions and the spigot fit (T1, J1) | The seal face and rim are asked for at +-0.1 where bureaus quote +-0.2 to 0.3. The two spigots have 0.075 mm of fit | Gauge every tub on arrival; dress an oversize spigot; dry trial close; order spare tubs | Before any adhesive. This scraps tubs, not units | Open issues 2, 26 |

Also watched, but lower: cover glass at or above flush (open issue 11) and cell thickness
(open issue 13). Two more are this plan's own additions, not the README's: cracking the
display glass while tilting it in, and heat on the cell while its leads are soldered.

PROPOSAL for planning: buy parts for 15 builds to finish 10 EVT units. The README already asks
for twice the needed number of printed PA12 plates and two sets of baffle rings.

---

## 9. Cycle time and labour for an EVT hand build

**This is an estimate. Nothing has been timed.**

Assumptions: one experienced technician; every fixture exists and has been proven on trial
parts; adhesives are chosen and behave like typical products of their class; units are worked
in a batch of five to ten so that cure waits overlap; no rework and no fault-finding; the
factory test path (gate G12) and the calibration tools exist. The first two or three units
will take two to three times longer.

| Stage | Hands-on, minutes per unit | Waiting |
|---|---|---|
| Board bring-up, programming, electrical test | 30 | - |
| Incoming gauging and cleaning of tub, plate, rings | 30 | - |
| Lapping the baffle ring | 10 | - |
| Ball feet, stage 1 | 15 | Full cure |
| Adhesive sheet onto base plate | 5 | - |
| Surface preparation, primer | 10 | Primer flash-off |
| Cover glass and rim seal | 15 | Tape dwell, sealant cure |
| Two visor windows | 25 | Light cure |
| Vent | 2 | - |
| Two hood gaskets | 10 | Light cure |
| Display and foam pad | 10 | - |
| Tub leak test | 5 | - |
| Board onto base plate, ring, crest check, LED test | 30 | Epoxy cure, room temperature |
| Clear potting | 30 | Degas, level, cure |
| Battery, leads, sensor dab, cleaning | 20 | - |
| Two prisms and height check | 20 | Light cure |
| Edge fillet and test gate 1 | 15 | Gel |
| Dry trial close | 10 | - |
| Seal bead, tail, close, test gate 2, top-up fillet | 35 | - |
| Cure under weight | 2 | Full cure, 45 C at most |
| Leak test, function, dark frames | 15 | - |
| Temperature cycle | 5 | Chamber, several hours |
| Calibration (section 6.7) | 40 | Chamber, half a day per batch |
| Final test, record, pack | 20 | - |
| **Total** | **about 410 minutes: roughly 7 hours per unit** | **Five cure waits and two chamber runs** |

Reading the estimate:

- Hands-on labour for ten units: about 70 hours, with a likely range of 50 to 100.
- Elapsed time for a batch of ten: about one to two working weeks, set by the cures and the
  chamber, not by the hands-on work.
- Not included: making and proving the fixtures, the trials before the first sealed unit, the
  coupon tests, fault-finding on the first boards, and writing the factory software. At EVT
  these are larger than the build itself.

---

## 10. Gaps: what is not yet defined

Grouped by who has to supply the answer.

**Design data**

1. `docs/RELEASE_GATES.md`, the master list of gates.
2. The main board: schematic, layout, parts list, fabrication and assembly files, test points.
3. The cradle board: schematic and layout.
4. Copper weights, dielectric build, material grade and mask colour of the main board.
5. The panel drawing for the main board.
6. Tolerances on every rail and on the charge current and end voltage.
7. A sleep-current limit.
8. The order of the seven pads, confirmed by a netlist.

**Process**

9. Every adhesive, primer and cure schedule.
10. Oven limits, reflow count, lens protection and cleaning rules for the camera cube.
11. Workmanship standard and X-ray acceptance limits for board assembly.
12. Whether the board is conformal-coated (the enclosure research recommends it; the
    specification and the assembly sequence do not mention it).
13. Cleaning of the board underside before lamination and potting.
14. Leak-test pressure, time and limit, for tubs and for units.
15. Dark-frame (light-leak) limit.
16. Drawings and making method for every fixture and gauge.
17. The number of extra shells for destructive tests.

**Factory software and firmware**

18. A compiled firmware for the real processor.
19. Commands, or a separate test firmware, for camera identity, camera pictures and a display
    pattern.
20. The PC-side factory program.
21. A factory-started zeroing and a four-position version.
22. The temperature calibration: points, chamber fixture, fitting tool, limits.
23. The stereo calibration: target, room, distances, tool, limits.
24. The grain white tile and standoff; the noise-floor procedure.
25. Programming security settings of the processor.
26. A way to set the battery's state of charge for shipping.
27. A serial-number scheme and label.

**Product and phases**

28. DVT and PVT quantities, entry and exit criteria.
29. Functional limits for the final read test.
30. Cosmetic limits, marking, label position.
31. Box contents and packaging.
32. Which regulatory tests apply to the version without a radio (the research was written for
    a version with one).
33. A ship mode (motion wake-up off until the first docking), or another answer to the short
    shelf life of a unit shipped at 30 % charge (section 7.4).
34. A power budget and a battery-life requirement in the specification. The research budget
    is for an older architecture; the only rev D figures are the firmware simulator's
    estimate, on provisional currents (`VALIDATION_PLAN.md` 2.7).

---

## 11. Design observations raised while writing this plan

Things in the design package that look wrong, missing or inconsistent. Each names the file.

1. **The gate list file is missing.** `design/DESIGN_SPEC.md` (intro and section 7) names
   `docs/RELEASE_GATES.md`. It is not in the repository.
2. **The real board is missing.** `mechanical/README.md` section 10 (check 17) expects
   `electrical/gl1_main/out/gl1_main-mechanical.json`. Only `electrical/tools/` (the toolchain
   and a demonstration board at rev C positions) exists.
3. **The mechanical package is older than the parameter file.** `design/master_params.yaml`
   was amended in place (items N1 to N10) after the last mechanical build.
   `mechanical/export/params_resolved.json` and `mechanical/README.md` (section 2 row 19,
   section 5, deviations D29 and D31) still show the locating slot as 1.8 mm long and the
   guaranteed upper view as 15.0 degrees; the parameter file now says 2.2 mm and 14.5
   degrees. Drawing `GL1-040` (main board outline) therefore still carries the old slot.
   Rebuild and re-issue before the outline is used.
4. **Fine-track rule disagrees.** `DESIGN_SPEC.md` section 4 says 0.10 / 0.10 mm with 0.20 mm
   pads. `electrical/tools/README.md` ("Rule set", "Demo build") uses 0.09 / 0.09 mm.
   `docs/research/bom-verification-opto.md` 3.14 found 0.09 mm outside the standard tier of
   the fabricators it checked. The same README's locating-hole example is at the rev C
   position.
5. **A step is missing from the assembly sequence.** `DESIGN_SPEC.md` section 4 ("Cell
   temperature") asks for a dab of thermal adhesive between the sensor and the cell.
   `mechanical/README.md` section 7 step 13 and its parts list do not include it.
6. **The pad set limits the factory.** `DESIGN_SPEC.md` section 4: seven pads with no battery
   pad and no 2.8 V pad. A board without its cell can only be powered through the 20 mA
   charger; the programming probe has no voltage reference; sleep current cannot be measured
   once the cell is soldered. (This plan's observation.)
7. **The assembly sequence asks for tests the firmware cannot run.** `mechanical/README.md`
   section 7, steps 13, 15, 16 and 18 call for camera identities, camera pictures, a display
   test pattern and dark frames through the pogo fixture. `firmware/core/gl_proto.h` has no
   such commands; `firmware/app/gl_usb.c` implements four of the six stream sources it
   declares; a read does not run with USB attached.
8. **Six-face calibration and the fixtures do not match.** The procedure needs USB
   (`firmware/app/gl_app.c`, `gl_app_start_cal`), so pad contact in six orientations. The
   calibration fixture in `mechanical/README.md` section 2 is a flat nest without contacts.
   With USB attached the charger runs and the processor stays awake, so the unit is warmer
   than in use. Nobody has estimated what that does to the stored zero (this plan's
   observation).
9. **Test gate 2 uses a limit the tolerances do not guarantee.** `mechanical/README.md` step
   16 requires a target at +17 degrees to be seen by both cameras. `master_params.yaml`
   guarantees only 14.5 degrees on an in-tolerance unit. Units inside tolerance could fail
   the gate with the adhesive wet and no way to correct them. Whether they do depends on
   what "seen" means, which the step does not say. The 14.5 degrees is the angle up to which
   the full light bundle is clear; above it the picture dims slowly. At +17.6 degrees a unit
   at the tolerance limit still passes 56 to 64 % of the light (`mechanical/README.md`
   section 5). A plain "visible or not" check at +17 degrees would therefore pass units far
   outside tolerance, and a strict brightness check would fail good ones. The gate needs a
   brightness criterion (`VALIDATION_PLAN.md` test O1 proposes one).
10. **The display is not squared to the cameras, and nothing calibrates it.** The glass sits
    in its pocket with 0.25 mm of clearance per side and ends 0.10 mm clear of the rear ribs
    (`mechanical/README.md` section 5 and step 9). Our arithmetic: up to about 1 degree of
    rotation in the worst case. `firmware/core/gl_cal.h` has no field for it. The simulation
    assumes the golfer copies the line to 0.5 degree.
11. **Charger safety is open at board level.** `firmware/README.md` open issue 2: two cases
    are marked NOT MET and need hardware. `DESIGN_SPEC.md` section 7 does not list this as a
    gate.
12. **Revision names disagree.** `firmware/app/gl_app_cfg.h` reports hardware revision 3
    ("C"); the specification is rev D; the firmware README calls the same board changes "rev
    C2".
13. **The leak test comes before the temperature cycle.** `mechanical/README.md` steps 18 and
    19. A leak opened by the cycle would not be found. This plan proposes a second leak test.
14. **Flux residue on the underside is not addressed.** The underside is bonded with a
    pressure-sensitive sheet (the only barrier at the pad slot) and covered by clear potting,
    and it carries a high-impedance photodiode input. No cleaning step is defined for it.
15. **Older research no longer matches the specification** on three parts: the always-on
    regulator voltage, the display connector (a bottom-contact part of another maker was
    verified; the specification now uses a top-contact FH12A part that the research did not
    verify), and the cradle pin series. See `docs/research/bom-verification-ics.md` and
    `bom-verification-opto.md`. `docs/SOURCING.md` should settle these.
16. **Ten units against four build variants.** `mechanical/README.md` section 12, test item 1,
    needs both base plates, each potted and unpotted. That leaves few full-function units,
    and none for destructive tests.
17. **An uncalibrated unit gives no warning.** The header comment of
    `firmware/core/gl_cal.h` says "The UI shows reduced confidence while a flag is missing".
    `firmware/app/gl_app.c` (`shown_confidence_`) and `firmware/README.md` ("Confidence
    shown") have no such factor, and the camera flags `GL_CAL_CAM_FLAG_INTRINSICS` and
    `_EXTRINSICS` are defined but read nowhere. Implement the comment or delete it. Until
    then a unit that skipped calibration looks exactly like a calibrated one (section 6.9,
    item 8).
18. **The power figures in the research are for another machine.** `docs/research/power.md`
    assumes a Bluetooth module, cameras at about 10.7 mA and a 47 mA peak. Rev D runs two
    camera cubes of about 120 mW each for the whole read: about 86 mA for the cameras alone
    (`docs/research/bom-verification-ics.md` section 2). The firmware notes now carry a rev D
    estimate from the simulator: about 96 mA in a read, 0.072 mAh per read cycle, 20.6
    microamps asleep, every current provisional (`firmware/README.md` "Battery life under
    the supply model"). The specification has no power budget and no battery-life
    requirement, and the cell's rated discharge current is unknown (gate G3).
19. **Shipping at 30 % charge and the always-on motion wake-up do not fit together**
    (section 7.4). `firmware/README.md` "Power" has a storage mode only below 3.25 V.
20. **The 70 C tests are above the only cell limit in the repository.**
    `mechanical/README.md` section 9 (tests 2 and 9) asks for 70 C on bonded units. The only
    cell figure is the family's 60 C discharge limit (`bom-verification-opto.md` 3.4); the
    storage limit is the open gate B15. `VALIDATION_PLAN.md` section 2.9 holds units with a
    cell at 60 C or below until the data sheet is in hand.

---

## 12. Sources for outside facts

All seen on 2026-11-11 as text returned by a web search. Three vendor sites that were tried
directly (the camera maker, the IMU maker, a tape converter) could not be opened from this
session, so no vendor page was read in full.

| Ref | Source | Used for | Status |
|---|---|---|---|
| S1 | OmniVision, OVM7692 product page. https://www.ovt.com/products/ovm7692/ | Cube is designed to withstand multiple reflows | VERIFIED (extract) |
| S2 | Distributor listing for OVM7692-RYAA. https://hotenda.com/product-detail/omnivision-technologies-inc-3430/ovm7692-ryaa | Moisture level 3, 168 hours | VERIFIED as a distributor listing; not a maker's document |
| S3 | Microsemi (Microchip) moisture sensitivity application note. https://www.microchip.com/content/dam/mchp/documents/FPGA/ApplicationNotes/ApplicationNotes/Microsemi_Moisture_Sensitivity_Application_Note_V5.pdf ; SMTnet library paper on handling moisture-sensitive devices. https://www.smtnet.com/library/files/upload/robertRoland.pdf | Level 3 floor life: 168 hours at up to 30 C and 60 % humidity | VERIFIED (extracts) |
| S4 | STMicroelectronics technical note TN0018, surface mounting guidelines for MEMS sensors in an LGA package (Rev 8, March 2025). https://www.st.com/web/en/resource/technical/document/technical_note/CD00134799.pdf | No solder on the sides of the package | VERIFIED (extract). The moisture level of the IMU itself was seen only on a third-party page: PROVISIONAL |
| S5 | LSM6DSV datasheet page (sister part of the IMU). https://www.alldatasheet.net/html-pdf/1447360/STMICROELECTRONICS/LSM6DSV/25007/11/LSM6DSV.html | Self-test limits 50 to 1700 mg | PROVISIONAL for the LSM6DSV16X |
| S6 | Microchip MCP73831 datasheet, hosted copy. https://www.farnell.com/datasheets/1784520.pdf | Charger needs a battery or load present; no-battery detection | VERIFIED (extract). Behaviour when feeding a bare board: not found |
| S7 | STMicroelectronics community thread on entering the ROM bootloader of the STM32U575/585 for the first time. https://community.st.com/t5/stm32-mcus-embedded-software/stm32u575-585-how-to-enter-rom-bootloader-to-flash-sw-at-very/m-p/74879 | Blank part does not reliably enter the USB loader; loader uses the USB pins | VERIFIED as forum posts; the maker's bootloader note itself was not seen |
| S8 | Mitutoyo bulletin 15004A, granite surface plates. https://www.mitutoyo.com/webfoo/wp-content/uploads/15004A.pdf | Flatness by grade for a 12 x 18 inch plate | VERIFIED (extract) |
| S9 | Lion Technology, "Cheat Sheet 012: Lithium SOC 2026". https://www.lion.com/getmedia/34a1639d-f193-4c04-90b2-acc50fb051af/Cheat-Sheet-012-Lithium_SOC_2026.pdf ; IATA lithium battery guidance document. https://www.iata.org/contentassets/05e6d8742b0047259bf3a700bc9d42b9/lithium-battery-guidance-document.pdf | 30 % state of charge: recommended for cells contained in equipment, mandatory from 1 January 2026 for cells above 2.7 Wh packed with equipment | VERIFIED as a summary; the regulation text was not seen |
| S10 | 3M, Double Coated Tape 93020LE product page and data sheet. https://3m.com/3M/en_US/p/d/b40072050 | Bond strength builds with time and temperature | VERIFIED (extract). Application pressure: not found |

Not found today, and therefore open: the camera cube's highest reflow temperature and reflow
count; the moisture level of the processor and of the flash memory from a maker's document;
the application pressure of the adhesive sheet; how the charger behaves with no cell attached.
