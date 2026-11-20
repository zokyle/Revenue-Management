# GreenLine GL-1: validation plan for the EVT build

Plan revision 3, 2026-11-20. Written against `design/DESIGN_SPEC.md` rev E (EVT1, amendments E1 to
E36), `design/master_params.yaml` rev E-EVT1, `mechanical/README.md`, `firmware/README.md` with the
test log of its final build (`firmware/build/readme/test.log`, stamped 2026-11-20 19:31 UTC) and
`sim/results/REPORT.md`. Revision 2 of 2026-11-11 was written against rev D.

**What changed from revision 2.** The body is corrected for rev E; revision 2 only carried notes.

| Where | Change | Source |
|---|---|---|
| 2.1, 1.1 | Level zero on two seats: base face (turf) and ball feet (hard plate). New test A5 | `DESIGN_SPEC.md` E11, section 6 |
| 2.4, O1, O3 | Guaranteed upward field 14.0 degrees (was 14.5); stick top seen from about 8.4 m on a worst-case unit (was 8.1) | E17; `master_params.yaml` `cameras`; `mechanical/README.md` section 5 |
| 2.5, D0 | Display rotation is measured at the factory and stored | E12, E22 |
| 2.7 | Power figures replaced by the firmware supply model of the rev E board: 23.7 microamps asleep at the cell, 76 days (were 20.6 and 87). Requirements of E23 entered as limits. New test F8 (ship mode) | `firmware/README.md` "Sleep and the supply model (rev E)"; test log; `DESIGN_SPEC.md` section 6 |
| 2.8, H2 | Quarter-wave film is an EVT trial | E9, E19 |
| 2.9 | Charger with its own temperature input, two temperature sensors, no read above 60 C, cradle sleep and the 6-hour limit. New test J10 | E1, E2, E13, E32 |
| 2.11, K3 | Drop is a requirement (PROPOSED in the specification) | E23 |
| 2.13 | Boot stub for firmware update; ship mode replaces the shelf test from an ordinary sleep | E34, E13 |
| 3, 6 | The field log, the PC tool and the replay path now exist in the firmware package and run on its PC simulator only | `firmware/README.md` "Field log", "PC tool" |
| 5, 7 | Remedies and observations brought to rev E | - |

Not changed in this revision: the simulation. `sim/results/REPORT.md` still uses the optical and
inertial parameters of hardware revision C and has not been re-run on the rev E optics. Every SIM
figure in this plan is that older run. Section references into `docs/MANUFACTURING_PLAN.md` were
written against its revision 2. That plan is now at revision 3 (2026-11-20, rev E) and kept its
section, test, gate and gap numbers; the references used here (2.3, 4.1, 4.5 test 18, 6.2, 7.1,
gap 17, gate G3) were looked up in revision 3 on 2026-11-20 and each still exists under its
number. A companion,
`docs/POWER_BUDGET.md`, shows the power model of section 2.7 state by state with a chart.

**Read this first.** Nothing in this project has been built or tested. No board, printed part,
fixture or finished unit exists. Every "claimed value" below is a simulation result, a
calculation or an assumption, and the table says which. A figure "from the firmware's supply model"
is a calculation too: a PC program adds up currents taken from data sheets, mostly from memory. This plan says how each number will be
checked on the first ten prototypes (the EVT build), what counts as a pass, and what a failure
means. No test in this plan has been run.

This plan owns WHAT is tested and to WHAT limit. How the units are built and calibrated is in
`docs/MANUFACTURING_PLAN.md`. Who supplies the parts is in `docs/SOURCING.md`. What the law and
the Rules of Golf ask for is in `docs/COMPLIANCE.md`.

## How to read the labels

| Label | Meaning |
|---|---|
| **REPO** | Taken from the design package. The file is named. The package is unbuilt, so a REPO number is a design intent, not a test result. |
| **SIM** | A result of the computer simulation in `sim/results/REPORT.md`. Synthetic greens, perfect conditions. Not a measurement. |
| **CALC** | A calculation or estimate on assumed inputs (a beam formula, an energy budget, a reviewer's estimate). |
| **ASSUMED** | An input that somebody chose because nobody has measured it. |
| **TARGET** | A goal set by the specification or by the owner. |
| **PROPOSED** | Suggested by this plan. It is NOT in the repository. The owner accepts it or changes it. Every pass limit that is ours carries this word. |
| **VENDOR** | A figure from a seller's listing or a maker's data sheet, not yet confirmed on a delivered part. |
| **VERIFIED** / **PROVISIONAL** | For outside facts only (a price, a standard, a product). VERIFIED = seen in a web search result on 2026-11-11, source in section 8. PROVISIONAL = from memory or an unconfirmed extract; confirm before relying on it. |

## Words used

| Word | Plain meaning |
|---|---|
| EVT | Engineering validation test: the first hand-built units, made to learn whether the design works. |
| Read | One measurement by the marker: it feels its own tilt, looks at the flagstick, and draws the aim line. |
| mrad | Milliradian. 1 mrad is a slope of 1 mm in 1 m (0.1 %, about 0.06 degree). A hair under one edge of the marker is roughly 1.5 mrad. |
| Seating | How the marker comes to rest when it is put down. Put it down twice and it never lies at exactly the same angle. |
| Scatter (or noise) | How much repeated measurements of the same thing differ from each other. Given as "1 sigma" (standard deviation) or as RMS. |
| Bias (or offset) | An error that is the same every time. Averaging does not remove it. |
| Median | The middle value: half the results are better, half are worse. |
| px | Pixel: one dot of a camera picture. |
| Disparity | How far the flagstick shifts between the left and the right camera picture, in pixels. Near things shift more. Distance is worked out from it. |
| Stimp | Green speed. The number of feet a ball rolls on a level green when released from a standard ramp (a Stimpmeter). |
| Cup | The hole. It is 108 mm across, so the "hole radius" is 5.4 cm. |
| Aim point | The spot beside the hole that the ball must be started toward so that the slope carries it into the hole. |
| Quick Read, Precision Read, Survey | The three reading modes (`DESIGN_SPEC.md` section 2): one placement; one placement plus a half-turn re-read; two to four placements along the line. |
| Potted / unpotted | Whether the opening for the grain sensor under the marker is filled with clear resin. |
| Chamber | A cabinet that holds a set temperature (and humidity). |
| Surface plate | A thick slab of granite ground very flat. The reference for "level" tests. |

---

## 1. Orientation: what is being proven, and in what order

### 1.1 The one question that comes first

The marker reads the slope of the green by feeling its own tilt. So the first question is not
about electronics at all:

> **If the same marker is put down on the same spot of turf twenty times, how much do the
> twenty tilt readings differ?**

Think of a bathroom scale on a thick carpet. Step on it three times and it shows three
different weights. Until that is fixed, it does not matter how many decimals the scale has.
The marker on grass is that scale. Every slope number, and therefore every aim line, rests on
how repeatably it seats.

Why this matters so much (all SIM, `sim/results/REPORT.md` sections 1 and 4.1):

| If the seating scatter is... | ...then a Quick Read is |
|---|---|
| 1 mrad | ahead of a golfer who reads slope to 0.5 % (by about 3 points of holed putts) |
| 2.5 mrad (the value the simulation ASSUMED) | level with that golfer |
| 5 mrad | behind that golfer (by about 5 points) |
| 7.4 mrad | no better than a golfer who reads slope to 1 % |

The specification's own estimate is "2 to 5 mrad per placement (estimate, unmeasured)"
(`DESIGN_SPEC.md` section 2). The whole range between "good product" and "weak product" lies
inside that estimate. Nobody knows where the real number is.

One point about the wording "on its three ball feet". On a hard, flat plate the three steel
balls are the seat: they stand 0.10 mm proud of the base (REPO). On turf the grass blades are
far rougher than 0.10 mm, so the whole underside rests on the grass tips, not only the balls.
Rev E accepts this (amendment E11): the factory measures the level zero twice, once on the ball
feet and once on the base face, stores both, and a read on turf uses the base-face zero. The two
planes can differ by up to 1.6 mrad (REPO: `DESIGN_SPEC.md` section 6). The seating test measures
what really happens on grass. It does not need to assume which part touches. Test A5 checks the
two stored zeros.

### 1.2 The order of everything else

```
 BEFORE ANY ELECTRONICS EXISTS
   Step 0   Seating on turf with a dummy marker (cheap, days)      <-- can start now
            Adhesive coupons, assembly trials (MANUFACTURING_PLAN 2.3)

 BARE BOARDS (before anything is sealed: some things can never be measured later)
   Step 1   Currents, sleep current, charger, temperature-sensor faults

 SEALED, CALIBRATED UNITS - on the bench
   Step 2   Is the level sensor good on a flat plate?
   Step 3   Does the level reading drift with temperature and humidity?
            (both base plates, potted and unpotted)
   Step 4   Do the cameras see what they should? (field of view, light leaks,
            distance against a tape measure)

 ON GRASS
   Step 5   Seating on turf with real units             ---- DECISION POINT 1
   Step 6   Aim line against rolled balls on a measured green
            Grain sensor data collection (in parallel)  ---- DECISION POINT 2

 BENCH AGAIN, GENTLE FIRST
   Step 7   Read time, battery life, display in sun, charging limits, USB, cradle
   Step 8   Heat, cold, rain, wet grass, wet docking

 LAST: TESTS THAT CAN KILL A UNIT
   Step 9   Hot-into-cold dunk, immersion, drop, footstep, cut sections
```

Why the order matters:

1. **Foundations first.** A field test of the aim line means nothing if the level sensor
   drifts, and the level sensor means nothing if the marker does not seat repeatably. Each
   step stands on the one before it.
2. **Cheap answers before expensive ones.** Step 0 costs a few printed shells and a week. If
   seating scatter on turf is 8 mrad, the project should know before ten units are built.
   Whether Step 0 is run before the prototype boards are ordered is an owner decision
   (`docs/RELEASE_GATES.md` G-103).
3. **Some things can only be measured before sealing.** The marker has no battery contact on
   the outside. Once the cell is soldered in and the unit is glued shut, nobody can measure
   sleep current or the current of one read (REPO: `MANUFACTURING_PLAN.md` 4.1).
4. **Calibration before use, and bench before field.** A unit that goes to the grass must
   have passed the plate tests, or a field error cannot be traced.
5. **Destructive tests last.** After the seal has cured a unit cannot be opened (REPO:
   `mechanical/README.md` section 7, "after step 17 nothing inside can be reworked"). A unit
   that leaks or cracks is finished. Ten units do not allow waste.

### 1.3 What ten units can and cannot prove

Ten units are enough to find design faults. They are not enough to prove that failures are
rare. A simple rule: if n units are tested and none fails, the true failure rate could still
be as high as about 3 divided by n. Five units through a rain test with no failure only show
that fewer than about 60 % would fail. A claim on the box ("rain-proof", "step-proof") needs
the larger DVT build (30 or more units for "fewer than 10 %"). EVT answers "does it work at
all, and where is it weak".

---

## 2. Requirements with a number: source, claimed value, test, pass limit

Columns: **Kind** says whether the claimed value is a simulation result, a calculation, an
assumption, a target or a vendor figure (labels above). "none" or "-" in the Kind or value column means the repository gives no number.
**Units** are the EVT units of section
4 (U1 to U10); "shells" are extra marker shells without electronics; "boards" are assembled
circuit boards before sealing.

### 2.1 Level (tilt) on a surface plate

Foot geometry used in the arithmetic below (REPO: `master_params.yaml`, `base_plate.feet`):
three balls at (0, 15.0) and (+-16.5, -9.5) mm. The triangle is 33 mm wide and 24.5 mm deep.
So 0.01 mm of height at one foot is 0.3 to 0.4 mrad of tilt.

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| A1 | Tilt accuracy against known angles | `DESIGN_SPEC.md` section 3 ("Tilt sensing"); `sim/results/REPORT.md` section 13 | Target 0.5 to 1 mrad. The simulation assumes 1 mrad of device bias per axis after zeroing | TARGET; ASSUMED | Plate set to known tilts with a sine plate or gauge blocks: 0, +-5, +-10, +-20, +-35 mrad on each axis and on one diagonal. Three readings per point | All 10 units, 13 points x 3 | Granite surface plate, sine plate or tilt table with gauge blocks, two-axis reference level of about 1 arcsecond (0.005 mrad) | Error at every point at most 1.0 mrad (REPO upper target). Goal 0.5 mrad. PROPOSED extra: scale error at most 1 % of the reading |
| A2 | Tilt repeatability when re-seated on the plate | No number in the repository. `MANUFACTURING_PLAN.md` 6.2: dust of 10 micrometres under a foot is 0.4 mrad | none | CALC | Lift the unit and set it down on the same clean spot 30 times. One read each | All 10 units, 30 placements | Surface plate, lint-free wipes | PROPOSED: scatter at most 0.15 mrad per axis (1 sigma); no single reading more than 0.5 mrad from the mean |
| A3 | User zeroing on a hard surface that is not level | `firmware/README.md` "Tilt, range, grain, protocol": bias recovered to 0.1 mrad on synthetic data | 0.1 mrad | SIM (firmware test on a PC) | Zero the unit (menu "ZERO") on a plate tilted 10 mrad. Then check it on the level plate, 0 and 180 degree pair | All 10 units, 3 zeroings each | As A1 | PROPOSED: remaining bias at most 0.3 mrad per axis |
| A4 | Ball feet: height of each ball | `mechanical/README.md` step 2 | 0.10 +-0.02 mm, all three | TARGET | Height gauge or optical profiler on the underside, before lamination and again after the thermal cycle | All 10 units and all shells | Height gauge with 0.001 mm reading, surface plate | REPO: 0.10 +-0.02 mm. PROPOSED extra: the three balls of one unit equal within 0.02 mm (see section 7, item 1) |
| A5 | The two stored level zeros (E11): ball seat and base-face seat | `DESIGN_SPEC.md` section 6 ("Level zero on two seats"); `firmware/README.md` (calibration records of version 2) | The two planes differ by up to 1.6 mrad (+-0.02 mm of ball height over a 24.5 mm triangle) | CALC | Read each unit on the plain granite plate (ball seat) and on the seat plate with three clearance pockets (base face on three pads of bare mask). Read back the two stored zeros. Compare their difference with the difference computed from the unit's own ball heights (A4) | All 10 units, 0 and 180 degree pair on each plate | Surface plate, seat plate (a fixture that is not designed yet: section 6, item 7), PC tool | PROPOSED: on each plate the reading with its own zero is within 0.3 mrad of level; the difference between the two stored zeros is at most 1.6 mrad and agrees with the A4 heights within 0.3 mrad. A unit without a base-face zero marks its result `Z?` (REPO: `firmware/README.md`, review finding A4): none may show that mark |

Reference level example: Digi-Pas DWL-8500XY, 1 arcsecond resolution and accuracy, seen at US
distributors at about $3,970 to $5,840 (VERIFIED as listings [V1]; country of manufacture not
found). Any level of this class will do. A sine plate with gauge blocks needs no electronics
and is the better primary reference. Plate flatness figures are in `MANUFACTURING_PLAN.md` 6.2.

### 2.2 Seating and level on turf (the first question)

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| S0 | Seating scatter on turf, **before electronics exist** | `DESIGN_SPEC.md` section 2: "Measuring seating repeatability is the first task for a prototype" | 2 to 5 mrad per placement; simulation uses 2.5 mrad per axis | ASSUMED | Dummy marker: a printed tub and FR-4 base with three ball feet, loaded to the real mass and balance (12.11 g with the FR-4 plate, 11.27 g with the PA12 plate: CALC, `mechanical/README.md`, "Estimated mass"). Tilt is read by a small breakout board of the same level sensor on hair-thin wires, or by a mirror on top and a laser spot on a screen 5 m away (1 mrad of tilt moves the spot 10 mm). 20 placements on each of 10 spots | 2 dummies, 200 placements per green, 2 greens with different grass | Dummy markers, sensor breakout and laptop (or laser, mirror, screen, dusk light), spot markers | Same decision bands as S1. PROPOSED |
| S1 | Seating scatter on turf, real units | Same; `sim/results/REPORT.md` section 4.1 | 2.5 mrad per axis assumed. Break-even points in the simulation: 2.5 mrad (Quick Read equals the 0.5 % golfer), 5.4 mrad (Survey equals them), 7.4 mrad (Quick Read equals the 1 % golfer) | ASSUMED; SIM | At 10 marked spots per green: 20 placements each, same heading, lifted fully between placements. Scatter is computed inside each spot and pooled. Repeat on a dewy morning | U1, U2, U3, U7: 200 placements each per green; at least 2 greens (PROPOSED: one bentgrass, one bermudagrass) and one wet session | Units with logging, practice green, spot markers, log dump tool | PROPOSED decision bands, per axis, 1 sigma, upper 95 % confidence bound: **Green** at most 2.5 mrad. **Amber** 2.5 to 5 mrad: the Quick Read is behind a good reader; the product must lead with the Precision Read and Survey. **Red** above 5 mrad: no single-placement mode holds its simulated standing |
| S2 | Are two seatings on one spot independent? | `sim/results/REPORT.md` section 11 ("Precision Read when the two seatings are correlated") | Independent (correlation 0) | ASSUMED | From S1 plus half-turn pairs: 10 placements at 0 degrees and 10 at 180 degrees on each spot. Compare the scatter between spots with the scatter inside a spot | Same sessions as S1 | Same | Report the correlation. No pass limit. PROPOSED note: above 0.5 the Precision Read gains about half of what the simulation shows |
| S3 | Rare bad seatings (outliers) | `sim/results/REPORT.md` section 11 ("Seating outliers") | None in the main run; a sweep tried 10 % and 25 % of seatings with an extra 11 mrad | ASSUMED | Count placements in S1 that lie more than 3 sigma from their spot mean | S1 data (at least 1600 placements) | - | PROPOSED: at most 5 % of placements. More than 10 % costs about 1.4 points in the simulation |
| S4 | Bias on turf: does the marker read the same slope at 0 and at 180 degrees? | `sim/results/REPORT.md` section 13: device bias 1 mrad per axis; a 2.5 mrad bias costs 1.0 +- 1.4 points | 1 mrad | ASSUMED | From the half-turn pairs of S2: half the difference between the 0 and 180 degree means is the device's bias as it sits on grass. The units read with their base-face zero (E11); the same pairs evaluated with the ball-seat zero show what E11 is worth | S2 data | - | PROPOSED: at most 1.0 mrad per axis, mean over 10 spots, with the base-face zero |
| S5 | Tilt accuracy on turf against a reference | `DESIGN_SPEC.md` section 2: "Local slope ... sensor about 0.5 mrad; seating 2-5 mrad" | none for the mean of many placements | - | Reference: a stiff flat disc 300 mm across laid on the same spot, with the reference level on it, read at four headings 90 degrees apart and averaged. Compare with the mean of 20 marker placements (10 at 0, 10 at 180 degrees) | U1, U7; 10 spots on each of 2 greens | Reference level, 300 mm disc, units | PROPOSED: mean difference at most 1.5 mrad per axis. Treat as a guide on first use: the disc averages 300 mm of turf and the marker 46 mm, and the disc has seating scatter of its own (measure it: 10 placements) |
| S6 | How much the slope changes over one metre of real green | `sim/results/REPORT.md` section 4.3 | The synthetic greens have almost none. A sweep added 0.5, 1 and 2 mm of metre-scale relief (1.3, 2.6, 5.2 mrad per axis); at 2 mm the Quick Read loses about 5 points | ASSUMED | Mean of 5 placements at each of 5 spots 0.25 m apart along a 1 m line; 10 lines per green | U1; at least 3 greens | Unit, tape | Report the RMS difference between neighbouring spots. No pass limit: it is a property of greens, not of the marker. PROPOSED flag: above 5 mrad the single-placement modes are in doubt |

How many placements are enough: with 200 placements on one green the scatter is known to
about +-10 %. That is enough to tell 2.5 mrad from 3.3 mrad, the edge of the band the
simulation cannot tell apart.

### 2.3 Tilt drift with temperature and humidity (both base plates, potted and unpotted)

Why it is tested: the level sensor sits on a circuit board that is glued to a base plate and,
on potted units, carries a 13 mm disc of resin. Materials that grow by different amounts when
warmed bend each other, like a door that sticks in summer. A bend of a few thousandths of a
millimetre tilts the sensor. Nothing in the package predicts the size (REPO:
`mechanical/README.md` section 12, test item 1).

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| B1 | Tilt drift per degree, after per-unit correction | `mechanical/README.md` section 12, test item 1 (owner's target) | Under 0.05 mrad per kelvin. Reviewer estimates before correction: 0.04 to 0.3 mrad/K for the PA12 plate; 0.03 to 0.08 mrad/K from a hard potting alone | TARGET; CALC | Chamber run -10 to 50 C with stops at -10, 0, 10, 23, 35, 50 C, up and down. At each stop a 0 and 180 degree pair on a flat inside the chamber. The correction is fitted on one run and judged on a second run | All 10 units: 4 FR-4 potted, 2 FR-4 unpotted, 2 PA12 potted, 2 PA12 unpotted | Chamber, lapped flat with a thermometer on it, turntable or glove port, log dump | REPO: residual slope under 0.05 mrad/K for each variant. PROPOSED extra: residual stays within +-0.5 mrad from 5 to 40 C (0.05 mrad/K over 20 K would use the whole 1 mrad budget by itself) |
| B2 | Does the zero come back after a temperature cycle? | Same (owner's target) | Within 0.3 mrad after a -10 to 50 C cycle | TARGET | Zero at 23 C before and after the B1 run | All 10 | Same | REPO: change at most 0.3 mrad per axis |
| B3 | Up-ramp against down-ramp (hysteresis) | `docs/research/inertial-sensors.md` section 2 (judge the up/down difference) | none | - | From B1: difference between the warming and the cooling reading at the same temperature | All 10 | Same | PROPOSED: at most 0.3 mrad |
| B4 | Humidity | `mechanical/README.md` section 12, test item 1 ("dry and after humid conditioning") | none. PA12 swells with moisture; FR-4 much less | - | Zero at 23 C dry. Condition 48 h at 40 C and 90 % relative humidity (PROPOSED). Re-measure within 1 h and again after 24 h in room air | All 10 (the unpotted units are sealed everywhere except the open grain cavity; keep them out of liquid water) | Humidity chamber | PROPOSED: change at most 0.3 mrad per axis |
| B5 | Slow change after cure | Same ("again some weeks after cure"). Reviewer estimate: 1.5 to 8.6 mrad of built-in tilt from cure shrinkage, relaxing with time | none | CALC | Repeat the 23 C zero check at about 2, 6 and 12 weeks after cure | All units still alive; at least one of each variant | Surface plate | PROPOSED: change between week 2 and week 12 at most 0.3 mrad |
| B6 | Which variant wins | `DESIGN_SPEC.md` section 5, item 2 ("compared at EVT") | - | - | Compare B1 to B5 across the four variants. Potted against unpotted separates the resin from the plate | All 10 | - | Decision, not a limit: the variant that passes B1 and B2 with the most margin |

Two gaps affect this test: there is no tilt logger (section 6, item 1), and no tool computes the
per-unit correction that B1 judges (section 6, item 9).

### 2.4 Cameras: distance, direction, field of view, light leaks

Stereo arithmetic used below (REPO: 20.0 mm between the cameras, 657 px focal length): the
flagstick shifts by 13.14 px divided by the distance in metres. That is 4.4 px at 3 m, 2.2 px
at 6 m and 1.1 px at 12 m. So an error of 0.1 px is 2.3 % of the distance at 3 m, 4.6 % at
6 m and 9.1 % at 12 m when the two cameras are the only source.

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| C1 | Stereo distance against a tape, **scatter** | `sim/results/REPORT.md` section 6; `DESIGN_SPEC.md` section 2 | Cameras alone, RMS: 1.0 % at 1.5 m, 1.9 % at 3 m, 2.7 % at 4.5 m, 3.5 % at 6 m, 5.3 % at 9 m, 7.3 % at 12 m (random part only; assumes 0.08 px of disparity noise) | SIM | Flagstick in a cup on short grass. Marker at the six distances, measured from the front of the camera windows to the stick. 20 reads per distance. Overcast and sunny | U1, U2, U3, U4, U7, U8 (the six potted units); 6 distances x 20 reads x 2 light conditions | Steel tape or laser distance meter, standard flagstick (measure its diameter and height), log dump | PROPOSED: RMS scatter at most 1.5 times the simulated value: 1.5, 2.9, 4.1, 5.3, 8.0, 11.0 % |
| C2 | Stereo distance, **bias** (a constant error) | `sim/results/REPORT.md` section 6: +0.1 px reads 3 to 4 % short and 30 % of putts stop short (22 % normally). `firmware/README.md` open issue 6: 0.05 px assumed | 0 in the main simulation; firmware assumes 0.05 px | ASSUMED | Mean error of the C1 reads at each distance, converted to pixels | Same reads | Same | PROPOSED: mean disparity error at most 0.05 px at every distance (1.1 % at 3 m, 2.3 % at 6 m, 4.6 % at 12 m). Hard ceiling from the spec: no distance wrong by more than 10 % ("10 % is enough for the line") |
| C3 | Does the stereo calibration hold? | `sim/results/REPORT.md` section 6: a board bow of 0.38 micrometres across the 20 mm is 0.1 px | none | CALC | Repeat C2 at 6 m: after re-seating, at 10 and 40 C, after the thermal cycles of test N3, after a 1 m drop (K3), and after 4 and 12 weeks | U2, U4, U7, U8 | Same, chamber with a window or an outdoor cold and warm day | PROPOSED: change at most 0.05 px (2.3 % at 6 m) from the first calibration |
| C4 | Fused distance with the flagstick's height | `DESIGN_SPEC.md` section 2; `sim/results/REPORT.md` section 6 | Fused RMS 3.4 % at 6 m, 3.6 % at 9 m, 5.1 % at 12 m once the stick height is learned; the stick top is usable on 52 to 59 % of long reads | SIM | From the C1 reads at 6, 9 and 12 m after the unit has "learned" the stick over about 18 reads | Same | Same | PROPOSED: fused RMS at most 1.5 times the simulated value (5.1, 5.4, 7.7 %) |
| C5 | Direction to the flag (bearing) | `DESIGN_SPEC.md` section 2 | "about 1 mrad" | ASSUMED | Marker on a turntable with a fixed stick at 6 m. Turn by known steps of 5 degrees out to +-25 degrees. The logged bearing must change by the same steps | U1, U7; 11 angles x 5 reads | Turntable good to 0.1 mrad (or a dividing head), flagstick | PROPOSED: error of each step at most 1 mrad plus 0.5 % of the angle |
| C6 | Flag found, and no false flags | `sim/results/REPORT.md` section 7 (detection model "an engineering guess"); `firmware/README.md` "Vision" (0 false flags in 88 synthetic reads) | Found on 96.5 % of reads at 1.5 m falling to 91.3 % at 12 m. A 20 % miss rate costs 2 points | ASSUMED; SIM | Count reads with and without a flag in view, against varied backgrounds: trees, people, a second flag, low sun | All field reads of section 2.5 (at least 300 with a flag) plus 200 reads with no flag in view | Log dump | PROPOSED: found on at least 90 % of reads to 6 m and 80 % at 9 to 12 m; a flag reported when none is in view on at most 1 % of reads |
| C7 | Height of the hole against the ball (from the lowest visible point of the stick) | `DESIGN_SPEC.md` section 2; `sim/results/REPORT.md` section 7 | 1 to 3 mrad when the base is visible; base hidden on 11 % of putts at 3 m, 28 % at 6 m, 48 % at 12 m | ASSUMED; SIM | Survey the height difference ball to hole with a builder's level. Compare with the slope the unit logs | Field putts of section 2.5 (at least 30 with the base visible) | Builder's optical level or rotating laser and staff (1 mm) | PROPOSED: RMS error at most 3 mrad with the base visible. Report how often the base was hidden at each distance |
| O1 | Upper edge of the camera view | `master_params.yaml` `cameras.field_required_deg`, `up_guaranteed_case`, `gate2_bars_deg`; `mechanical/README.md` section 5; `DESIGN_SPEC.md` E17 | 17.6 degrees required nominally. Guaranteed: **14.0 degrees** (E17; rev D said 14.5). The model keeps the **full** light bundle clear up to 18.56 degrees on a nominal unit, 14.97 with the optics 0.2 mm high, and 14.03 in the guaranteed case (optics 0.2 mm high, the loosest locating fit of 0.125 mm against it, roof at -10 C). The margin to 14.0 is 0.03 degree. It rests on an assumed lens pupil: with a pupil of 0.40 mm instead of 0.38 the model gives 13.86, with the pupil 0.5 mm instead of 0.4 mm below the cube top 13.61 (release gate: OmniVision lens data). The bundle clears the roof by 0.054 mm. Above the limit the picture dims slowly, it does not go dark: a unit in the guaranteed case still passes 55.8 % of the light at +17 degrees and 44.2 % at +17.6 | CALC (ray trace on assumed lens data, PROVISIONAL) | Marker on a flat, 2.000 m from an evenly lit vertical strip with marks every 0.5 degree from -20 to +20 degrees (with the optical axis 5.6 mm above the base plane, 14.0 degrees is 504 mm above the flat and 17.6 degrees is 640 mm: our arithmetic). Plot the brightness along the strip. Find the **onset**: the lowest upward angle at which the picture is more than 5 % darker than at the mirrored downward angle (PROPOSED threshold). The lower half is the reference because the roof cuts only the upper bundle; when the optics sit high the model keeps the lower bundle clear to about 18.5 degrees. Turn the strip end for end and repeat, to cancel uneven lighting. If a picture of the same board without its tub exists, use that as the reference instead. Also record each unit's result at factory test gate 2 (bar at +13.0 degrees not darker than the bar at -13.0) | All 10 units, both cameras | Target wall with an even light strip, tape, raw-strip logging (level FIRST) or the capture command | REPO: onset at 14.0 degrees or higher on every unit. The YAML figure is the angle up to which the full bundle is clear, so the limit applies to the onset, **not** to the half-brightness point. Report the onset, the half-brightness angle, and how many units show no onset up to 17.6 degrees. With 0.03 degree of model margin and marks every 0.5 degree, this test cannot confirm the margin; it can find a unit that is clearly short. The 5 % threshold must be tuned on the first units |
| O2 | Sideways and downward view | Same | +-26 degrees required. The model gives 25.60 degrees for the full bundle, limited by the 2 mm prism and the same on both sides in every tolerance case; 2.3 % of the assumed bundle is clipped at the field edge. 8 degrees down required; the model keeps it clear to 11.7 degrees even with the optics 0.2 mm low. The picture itself ends at about +-26 degrees (640 pixels at a focal length of 657 px) | CALC | Same strip turned sideways; marker raised on a block for the downward marks | All 10 | Same | PROPOSED: the left and the right edge of each picture are equally bright within 10 % (the model clips both sides alike, so a difference means a shifted prism or adhesive in the opening); the outermost marks inside the picture show on both sides; no onset (as in O1, with the upper half as the reference) down to 8 degrees. The predicted 2.3 % loss at the edge is too small to check without lens data: record the edge brightness against the centre, with no limit. A limit in "% of centre brightness" would mix clipping by the enclosure with the lens's own fall-off, which nobody knows |
| O3 | Distance from which the top of the stick is seen | `DESIGN_SPEC.md` sections 2 and 5 | From about 6.6 m on a nominal unit; about 8.4 m on a worst-case unit (E17; 8.1 m at rev D) | CALC | Walk the marker back from 5 m in 0.25 m steps until the log shows the stick top as valid. Measure the real stick | U1, U2, U7, U8 | Tape, flagstick of measured height | PROPOSED: at most 8.6 m (the 8.4 m of E17 plus the 0.2 m this plan allowed before). The specification does not state the stick height behind its figure; revision 2 of this plan used 2.13 m. Measure the stick and scale by its height |
| L1 | Light leaking into the cameras | `mechanical/README.md` section 12, test item 4 and open issue 16 | No number. 0.8 mm black PA12 "untested"; gaps beside the cubes are "a labyrinth, not a seal" | none | Cap both windows. Take dark frames in the dark, then with a strong lamp or direct sun from six directions, including low from behind | All 10 | Lamp of about 100,000 lux at the unit or clear midday sun, lux meter, window caps, picture capture (section 6, item 2) | PROPOSED: mean picture level rises by at most 1 grey level of 255, and no patch by more than 2 (the firmware's synthetic tests lose accuracy at 2 grey levels of fixed pattern) |
| L2 | Stray light into the grain sensor on turf in sun | `DESIGN_SPEC.md` section 4 ("Grain LEDs"): 470 kilohm amplifier at mid-rail | none | none | Marker on turf in full sun, grain LEDs off. Read the photodiode level through the grain data stream | U1 to U4, U7, U8 | Sun, lux meter | PROPOSED: level with the LEDs off at most half of full scale. Our arithmetic says the amplifier has only about 3 microamps of headroom, which a little sunlight through the grass could use up (section 7, item 9) |

A calibration gap affects C1 to C4 and O3: no stereo calibration procedure or tool exists yet.
Section 6, item 8 says what these tests mean on a unit that runs on nominal values.

### 2.5 Aim line on a measured practice green

This is the test of the whole instrument. It needs a careful reference, so the method comes
before the table.

**What "true" means here.** For one putt (ball position, hole, green speed) the true aim point
is the spot beside the hole toward which a ball must be started so that it crosses the middle
of the hole at the chosen pace. The chosen pace is the device's default: the ball would stop
0.30 m past the hole if the hole were covered (REPO: setting PAST, default 30 cm).

**The reference: rolled balls from a ramp.** A putting robot would be ideal. None was found
today as a catalogue item that can be bought and shipped inside the US (**not found**). A ramp
does the same job: a short inclined rail that releases the ball at the same speed and in the
same direction every time, like a robot that never has a bad stroke. One such product was
seen on sale at about $300 to $340 (VERIFIED as listings [V2]; country of manufacture not
found). A home-made ramp of the Stimpmeter kind works too.

Step list for one putt:

1. Mark the ball position B with a tee beside it. Measure B to the hole with a steel tape.
2. Measure the green speed that session with a Stimpmeter, both directions (REPO formulas:
   `docs/research/putting-physics.md` findings 4 and 5).
3. Put the flagstick in. Set the marker behind B. Take the read (Quick, then Precision; Survey
   on putts of 4.5 m and more). Note the read numbers. Lift the marker.
4. Take the flagstick out. Cover the hole with a thin flush cover so that balls roll over it.
   Lay a ruler across the line through the middle of the hole, at right angles to B-to-hole.
5. **Find the true aim point.** Aim the ramp at B toward a trial point. Set its release height
   so that balls stop 0.30 m (+-0.15 m) past the hole line. Roll 5 balls and note where each
   crosses the ruler. Shift the trial point and repeat until the crossings straddle the hole
   centre. Interpolate. The trial point with zero mean miss is the true aim point.
6. **Roll the device's own answer.** The log holds, for each read, the aim offset at the hole
   in metres and the launch speed (REPO: `firmware/core/gl_log.h`, fields `aim_offset_m` and
   `v0_mps`). Aim the ramp at that offset, set that speed, roll 5 balls, note crossings and
   stopping points.
7. Dump the log that evening. Join it to the field sheet (section 3.3).

Three things in rev E change what is written on the field sheet (REPO: `DESIGN_SPEC.md` E29, E31,
E33; `firmware/README.md` "Phase 3, builder 3"):

- **Display state.** A solid line with a confidence bar is a normal solution. A dashed line marked
  APPROX is a fallback solution. A message without a line is no solution. "TOO STEEP" draws only a
  dashed line. Note the state of every read. D1 to D4 are judged on normal solutions; fallback and
  no-line reads are counted and reported separately.
- **Survey order.** A Survey now finishes at the ball: the placement the marker stands on is
  treated as the ball, and a line is shown after every placement from the second on.
- **Recall.** A tap on a marker that has not been lifted shows the last result again with its age.
  It takes no new read and writes nothing to the log.

**The error of the reference itself (PROPOSED budget, to be measured, not assumed):**

| Source | Size | How it is kept small |
|---|---|---|
| Ball-to-ball scatter of the ramp on real turf | unknown: measure it first (10 rolls, same setting) | Average 5 to 10 rolls. If the scatter is 2 cm at 3 m, the mean of 10 rolls is good to 0.6 cm |
| Pointing the ramp | about 1 mrad (3 mm at 3 m) | Laser pointer on the ramp, read on the ruler |
| Reading the crossing point | about 3 mm | Phone camera on a low tripod over the ruler, slow motion |
| Pace: the break changes with speed | about 5 % of the break for +-0.15 m of stopping distance | Hold the stopping distance inside +-0.15 m |
| Green speed drifting during a session | - | Measure the Stimp at start and end; PROPOSED: discard the session if it moves by more than 0.5 ft |
| Balls wearing a track in dew | - | Shift B by a few centimetres between repeats; work on dry greens |

PROPOSED requirement on the reference: its uncertainty (1 sigma) is at most 1 cm at 3 m and
2 cm at 6 m. That is about one fifth of the error the simulation predicts for the device. If
the ramp cannot reach it on a given green, roll more balls or do not use that green.

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| D0 | Does the drawn line point where the unit thinks it points? | `firmware/README.md` "Display" (line direction 0.05 degree RMS, 0.28 worst, on a PC model); `DESIGN_SPEC.md` section 6 (E12, E22: the display glass can sit up to about 1.2 degrees rotated in its pocket, computed 1.19; the factory measures the drawn line against the visor flat and stores the angle; the firmware rotates the line by it) | 0.05 degree (drawing only). The aim-line budget allows 0.5 degree for transfer. The simulation (rev C run) assumes 0.94 degree steps (0.27 degree RMS) plus 0.5 degree for the golfer | SIM; CALC | Level floor, flagstick at 3 m, a taut string from the stick over the centre of the marker. Photograph the marker from straight above. Measure the angle between the drawn line and the string in the picture. Read back the stored rotation of each unit | All 10 units, 5 reads each | Camera on a boom, string, flagstick, PC tool | PROPOSED: mean error per unit at most 5 mrad (0.3 degree, 1.5 cm at 3 m) with the stored rotation applied. Report the stored rotation of every unit: it shows how far the glass really sits turned. The fixture that measures the rotation at the factory is not designed yet (`mechanical/README.md` section 12) |
| D1 | Quick Read: how far from the true aim point | `sim/results/REPORT.md` sections 1 and 3 | Median miss at the hole 2.3 cm at 1.5 m, 5.1 cm at 3 m, 9.2 cm at 4.5 m, 13.2 cm at 6 m, 23.6 cm at 9 m. Aiming straight at the flag: 6.9, 13.9, 24.0, 28.5, 47.7 cm | SIM (perfect stroke, 2.5 mrad seating, no grain) | Steps 1 to 7 above. Device error = device aim point minus true aim point | U1, U2, U7. PROPOSED: 30 putts at each of 1.5, 3, 4.5 and 6 m and 20 at 9 m, spread over at least 3 greens with slopes from 0.5 to 3 % | Ramp, 10 identical balls, Stimpmeter, tapes, ruler, hole cover, flagstick, level, phone camera, field sheets | PROPOSED, both must hold at each length: (a) median device error at most 1.5 times the simulated median: 3.5, 7.7, 13.8, 19.8, 35 cm; (b) median device error at most 0.6 times the "aim straight" error measured on the same putts (the simulation gives 0.33 to 0.50) |
| D2 | Precision Read and Survey | Same | Median miss, Precision: 1.8, 4.8, 8.2, 12.2 cm at 1.5 to 6 m. Survey with three placements: 1.9, 4.3, 6.8, 8.5 cm | SIM | Same putts, extra reads in step 3. Survey placements in the E29 order, ending at the ball | Same | Same | PROPOSED: no worse than the Quick Read on the same putts; report the gain. The simulation's gains are small (2 and 5 points), so 140 putts may not resolve them |
| D3 | Pace: where the ball stops | `sim/results/REPORT.md` section 8 | Median pace error with the true green speed: 16 cm over all lengths ("Stimp error 0" row). With a golfer's 7 % speed estimate: 10, 20, 30, 40 cm at 1.5 to 6 m | SIM | Step 6: stopping distance past the hole line against the 0.30 m target, with the measured Stimp entered | Same putts | Same | PROPOSED: median pace error at most 25 cm over all lengths with the measured Stimp entered |
| D4 | Putts holed when the device's answer is rolled | `sim/results/REPORT.md` section 3 | 85 % at 1.5 m, 44 % at 3 m, 26 % at 4.5 m, 13 % at 6 m (perfect stroke) | SIM | Step 6 with the hole open: count balls holed out of 5 | Same putts | Same | Report only. With 30 putts per length the count is good to about +-9 points. The simulation calls its own figures upper bounds (no bumps, no wind) |
| D5 | Device against real golfers on the same putts | `sim/results/REPORT.md` sections 1 and 13 (human readers are simulated, "generous to the human") | Quick Read level with a 0.5 % reader | SIM | Before the device reads, 3 to 5 golfers each mark their own aim point with a tee. Compare their errors with the device's on the same putts | Same putts; golfers of mixed skill | Tees | Report only. PROPOSED goal: device median error at most the median golfer's |
| D6 | How well a golfer copies the line from the display | `sim/results/REPORT.md` section 4.2 | 0.5 degree (1 sigma). At 1 degree the Quick Read falls behind the 0.5 % reader | ASSUMED ("no data") | Level surface, 3 m. Golfer sets the ball or putter to the displayed line; start direction measured from slow-motion video from above | PROPOSED: 10 golfers x 20 putts | Phone or camera at 240 frames per second on a boom, scale marks | Report. PROPOSED decision line: above 1.0 degree the "break in cups" way of using the device should become the main instruction (the simulation's other use model) |
| D7 | Is the confidence bar honest? | `sim/results/REPORT.md` section 12 | Calibrated on average; says little beyond putt length | SIM | Pool D1: for each confidence band, the share of reads whose true aim point lies within the hole radius of the device's | All D1 reads | - | Report. PROPOSED flag: a band whose real share is less than half of what the bar claims |

Effort: about 15 minutes per putt with two people. 140 putts is roughly six field days.

### 2.6 Grain sensor (ships switched off until this passes)

REPO: the grain reading is experimental; reviewer's estimate is a 15 to 25 % chance that it
improves the line; it "ships disabled until it passes the validation gates in
`docs/research/grain-sensing.md`" (`DESIGN_SPEC.md` section 2). The gates are that note's
section 2.3. The numeric limits below are ours unless marked REPO.

| ID | Gate | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| GR0 | Noise floor: what does the sensor say on turf with no grain? | `grain-sensing.md` 2.3 gate 0; firmware default threshold 0.30 | A model predicts a false signal of 0.10 to 0.23 on grainless turf | CALC | At least 50 readings at spots 2 to 3 cm apart inside one mowing stripe, on upright turf and on brushed turf | U1 to U4, U7, U8 (potted only) | Grain data stream through the cradle contacts, or new logging (section 6, item 3) | REPO: sets the acceptance threshold. PROPOSED: with that threshold, at most 10 % of grainless readings are accepted as "grain present" |
| GR1 | Bench: white tile and tilted tile | Gate 1 | White-tile spread under 1 % after correction; tilt response about 2.5 to 4.8 % per degree | TARGET; CALC | White reference procedure, then tilt the tile by known angles | Same 6 units | White tile, sine plate | REPO: spread under 1 %. Tilt response reported |
| GR2 | Rotation: the reading must turn with the turf, not with the device | Gate 2 | - | - | On grainy turf, read at 8 headings 45 degrees apart on the same spot, 5 spots | Same | Practice green with visible grain | PROPOSED: the reported direction stays within +-30 degrees of its mean (in ground coordinates) at 7 of 8 headings |
| GR3 | Stripe test | Gate 3 | - | - | Readings in neighbouring mowing stripes against ball-roll difference along and against each stripe | U1, U7 | Ramp | PROPOSED: direction flips between stripes in at least 8 of 10 stripe pairs |
| GR4 | Ball-roll ground truth | Gate 4; `sim/results/REPORT.md` section 11 (the simulated sensor: direction to 20 degrees, strength to 30 %) | Worth 5.1 +- 1.9 points if it works as specified. Worth nothing if the direction is wrong by 180 degrees half the time, or with a false floor of 0.04 | SIM | Short-ramp rolls in 8 directions on a spot levelled to 0.02 degree; record distance and sideways drift; compare with the sensor's direction | U1, U7; at least 10 spots on 2 grass types | Ramp, reference level, tape | PROPOSED: direction within +-30 degrees of the ball-roll direction on 80 % of accepted readings; wrong by more than 90 degrees on at most 10 % |
| GR5 | Closed loop | Gate 5 | Must cut the miss on bermudagrass and not worsen it on bentgrass | TARGET | Replay the D1 putts with the grain reading on and off (section 3) | D1 data | - | REPO, as stated. This gate belongs to DVT; EVT collects the data |

If gates 0, 2 or 3 fail: REPO remedy, section 5.

### 2.7 Read time and battery life

**Where the power numbers come from.** There are two sources, and they must not be mixed up.

- `docs/research/power.md` was written for an **older architecture**: a Bluetooth module,
  another regulator and charger, LEDs fed from the cell, cameras budgeted at about 10.7 mA.
  Think of a fuel figure measured on last year's engine. Its figures are marked "older
  architecture" below.
- `firmware/README.md` carries the supply model of the **rev E board** ("Sleep and the supply
  model (rev E)", "Cradle, ship mode and the hot cell", "End to end"). The firmware runs on a PC
  simulator; the simulator multiplies the time spent in each state by a current for each part.
  The file says of those currents: each is a data-sheet figure from memory, a figure of the
  research notes, a provisional figure of the netlist notes, or a plain guess. None is measured.
  The lines quoted below are in the test log of the final build
  (`firmware/build/readme/test.log`).

`docs/POWER_BUDGET.md` shows the same model state by state, with a chart.

| Item | Rev E MODEL (REPO: the firmware simulator's supply model; not a measurement) |
|---|---|
| Time the camera supply is on in one Quick Read | 2.42 s at the nominal estimate of computing speed (2.16 to 2.76 s over the estimated range). 3.82 s if the fast clock fails. 1.56 s only if computing took no time. Since firmware phase 3 a read with several lines in view is bounded: the longest such read keeps the supply on for 2.59 s |
| Current while it is on | 86 mA for the two camera cubes (about 120 mW each, unverified; both stay awake for the whole read) plus 9.5 mA for the processor at 160 MHz: about 96 mA, which is about 2.2 times the cell's listed capacity per hour |
| Charge of one read, from wake-up to result | 226.7 mAs = 0.063 mAh (201.4 to 259.3 mAs = 0.056 to 0.072 mAh; 342.9 mAs = 0.095 mAh if the fast clock fails). The cameras are 92 % of it |
| Charge of one whole cycle: read, 45 s of display, asleep again | 260.5 mAs = 0.072 mAh (235.2 to 293.1 mAs; 376.7 mAs if the fast clock fails). The 45 s of display are 33.8 mAs of it, a mean of about 0.75 mA (our arithmetic on the two log columns) |
| Read cycles from the listed 43 mAh | 594 (528 to 658). This counts the whole listed capacity down to empty, nothing else drawing, and no self-discharge |
| Asleep, underside dark | 23.68 microamps at the cell: processor asleep 9.0, tilt sensor waiting for motion 5.0, memory 0.1, 2.8 V regulator 1.6, battery-voltage divider 1.90, the cell's protection circuit 3.0, charger leakage 0.075, disabled camera regulator 0.2, enable pin of the USB regulator 2.8 (NOT CONFIRMED), housekeeping 0.01. That is 0.57 mAh a day: 76 days from a full cell, 23 days from a cell at 30 % (12.9 mAh). The display with its DISP line low stays on the always-on supply and is counted as 0, because **no figure is known for it** |
| Asleep, underside lit | 28.88 microamps at the cell: light on the grain photodiode adds 5.2 through the 150 kilohm wake pull-up (E27) |
| The same, seen from the cell-lead pads | 20.68 microamps dark, 25.88 lit, both plus the display. A bench supply on the pads replaces the cell and its protection circuit (3.0 of the 23.68) |
| Ship mode (E13) | 12.93 microamps at the cell at 3.9 V: processor in Shutdown 0.20, tilt sensor powered down 3.0, memory 0.1, always-on parts 9.62. Plus the display, as above. 30 % of the cell lasts 42 days |
| In the cradle | Awake with USB: 3.35 mA. Asleep in the cradle (E32): 98.6 microamps while charging; 179.4 with the USB bus suspended. The charger delivers 19.8 mA and ends the charge when its output falls below 1.98 mA |
| Revision 2 of this plan (rev D, firmware phase 2) | 20.6 microamps asleep at the cell, 87 days, about 17.6 at the pads, 600 read cycles. The 3.1 microamps of difference are parts of the rev E board: charger leakage, the disabled camera regulator and the enable pin of the new USB regulator |

**What the specification now requires (E23, E14).** The first four rows are the E23 requirements,
PROPOSED in `DESIGN_SPEC.md` section 6 and in `master_params.yaml` `requirements` until measured
on EVT units. The last row is the board-test limit of E14, also PROPOSED there. Those two files
give the limits only. The column "The model says" is from the firmware test log: the
specification (section 6: "Ship mode ... Not modelled yet", "about 600 to empty") and the YAML
(`requirements.ship_mode ... modelled: false`, `model_to_empty: 600`) pre-date the firmware's
ship-mode model and still carry the older entries (`docs/RELEASE_GATES.md` G-107):

| Requirement (E23) | Limit | The model says | Standing of the model |
|---|---|---|---|
| Reads per charge, 20 C, new cell | at least 150, from full to the low-battery symbol | 594 cycles to empty (528 to 658). To the symbol, by our arithmetic, if 80 % of a 34 to 41 mAh cell lies above the symbol's 3.5 V (an assumption): about 380 to 450 at the nominal cycle of 260.5 mAs; 260 if the fast clock fails on every read (376.7 mAs) with the smaller cell, 500 at the low computing cost (235.2 mAs) with the larger | Meets it. The point of the low-battery symbol is not modelled |
| Reads per charge at 0 C, or after 300 charge cycles | at least 100 | nothing: the model has no temperature and no ageing | Not modelled |
| Standby, 20 C | at least 45 days asleep, from full to the low-battery symbol | 76 days to empty at 23.7 microamps, underside dark, display counted as 0 | Meets it on the listed capacity. The margin is unknown: the symbol point, the display's draw, self-discharge and a lit underside are outside the figure |
| Ship mode | at most 5 microamps at the cell, protection circuit included; at least 3 months from 30 % charge without falling below 3.0 V | 12.9 microamps; 42 days from 30 % | **NOT MET** (stated so in the firmware test log). The firmware controls 3.3 of the 12.9; the rest is the board |
| Sleep current at the pads (E14, a board-test limit) | at most 25 microamps at 3.8 V, underside dark | 20.68 without the display | Met only if the display draws less than 4.32 microamps with DISP low. With a lit underside 25.88: over the limit, a case E27 excludes |

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| F1 | Time from "marker at rest" to "result on the screen" | `DESIGN_SPEC.md` section 1 and E15 ("about four to five seconds", "4.1 to 4.8 s"); `firmware/README.md` "End to end" | 4.45 s on the PC simulator with computing charged at its estimated cost (4.15 to 4.84 s over the estimated range; 6.03 s if the fast clock fails; 3.47 s only if computing took no time). The firmware notes state that the low end now reads 4.2 at one decimal, against the 4.1 of E15 | TARGET; SIM; CALC | Video at 60 frames per second: hands leave the marker, result appears. 30 reads each: flag at 3 m, flag at 9 m, a person in view, no flag. The read record of the field log also carries stage times in milliseconds | U1, U3, U7 | Phone camera, log dump | PROPOSED: median at most 6.5 s and 95 % of reads under 8 s with a flag in view. The E15 range of 4.1 to 4.8 s is reported as met or not met |
| F2 | Energy of one read | The rev E model above. (`docs/research/power.md` section 4 gives 0.011 mAh nominal and 0.039 mAh worst case: older architecture) | 0.063 mAh from wake-up to result (0.056 to 0.072); 0.072 mAh for a whole cycle with its 45 s of display | CALC (simulator model on provisional currents, unmeasured) | Current against time during a read, with a bench supply on the cell-lead pads in place of the cell (E4). Record the time the camera supply is on and the current in each phase, and the current during the 45 s of display | 3 boards **before sealing** | Source-measure unit or current probe and oscilloscope | Report only at EVT. PROPOSED flag: above 0.10 mAh from wake-up to result with the stick at 6 m (the model's figure for a read whose fast clock failed is 0.095 mAh), find the cause before F6 is run. A limit of 0.05 mAh, taken from the older figure, would fail a board that works as designed |
| F3 | Peak current and voltage dip in the cold | The rev E model above. (`power.md` section 4, finding 5, gives about 47 mA, 1.1 times the cell's capacity per hour, with the cameras at 10.7 mA: older architecture) | About 96 mA (cameras 86, processor 9.5), about 2.2 times the cell's capacity per hour. With the 1 to 5 ohm that `power.md` assumed for the pack, the dip is about 0.1 to 0.5 V, more in the cold. The cell's highest allowed discharge current is not known; data for the thin-cell family show about 90 % of capacity at 100 mA (`bom-verification-opto.md` 3.4) | CALC | Read at 0 and 5 C with the cell resting at 3.5 V (the firmware's low-battery threshold) and at 3.35 V (below it the firmware refuses a read). Watch the cell voltage, the always-on 2.8 V supply and the camera supply | 2 boards with a real cell, before sealing | Chamber, oscilloscope | REPO (E14, PROPOSED there): both 2.8 V supplies within +-3 %, the camera supply under camera load. PROPOSED: no reset and no camera fault; the always-on supply never below 2.7 V (the display's lower limit, PROVISIONAL in the specification); the lowest cell voltage recorded. If the cell dips below 3.1 V from 3.5 V, the low-battery threshold has to rise. The cell's rated discharge current must come with the data sheet (battery release gate) |
| F4 | Sleep current | `DESIGN_SPEC.md` section 4 (E14, E27); the rev E model above; `MANUFACTURING_PLAN.md` 4.5 test 18. (`power.md` section 2 gives 4.7 to 12 mAh per month, about 7 to 17 microamps, with the motion wake-up left on: older architecture, protection circuit included) | Limit of E14: 25 microamps at the cell-lead pads at 3.8 V with the underside dark. Model: 20.68 at the pads without the display (23.68 at the cell); 25.88 at the pads with a lit underside | TARGET; CALC | Bench supply on the cell-lead pads at 3.8 V, no VBUS, after the board has gone to sleep, display connected, grain opening covered. Repeat with the opening lit by room light and by a lamp. Repeat with the display unplugged: the difference is the display's draw with DISP low, the figure nobody has. Repeat at 3.2 V, where the firmware's storage mode switches the motion wake-up off | All boards **before sealing** | Supply with a microamp range, opaque cover, lamp | REPO (E14, PROPOSED there): at most 25 microamps at 23 C and 3.8 V, dark, display connected. Report the lit value, the display's share and the 3.2 V value (the rev E model was not run for storage mode). Each board's value goes on its record: F7, F8 and Q1 are judged against it |
| F5 | Cell capacity | `DESIGN_SPEC.md` section 3 ("about 43 mAh ... still to be obtained"); `power.md` finding 8 suspects about 34 mAh | 43 mAh | VENDOR (listing, unconfirmed) | Discharge loose cells at 8.6 mA from 4.2 V to 3.0 V at 23 C. Note the capacity delivered down to 3.5 V as well: it is what the low-battery symbol leaves usable. Two of the cells then go through 300 charge and discharge cycles (PROPOSED: this may run past week 12) and are measured again | 5 loose cells | Battery tester | PROPOSED: at least 40 mAh. Report the share above 3.5 V and the capacity after 300 cycles |
| F6 | Reads per charge | `DESIGN_SPEC.md` section 6 (E23); `master_params.yaml` `requirements.reads_per_charge` | Requirement: at least 150 reads from full to the low-battery symbol at 20 C with a new cell; at least 100 at 0 C or after 300 charge cycles. Model: 594 read cycles from the listed 43 mAh down to empty (528 to 658). To the symbol about 380 to 450 at the nominal cycle, 260 to 500 over the cases named above (our arithmetic, assumption above). (`power.md`: 0.7 to 3.0 mAh per 4.5-hour round: older architecture) | TARGET; CALC | Fully charged unit on a rocking table that wakes it every 60 s until the low-battery symbol. Once at 20 C and once at 0 C. The 300-cycle case is not run on a unit at EVT: it is computed from the aged cells of F5 and the measured energy of F2, and labelled as computed | U3, U8 | Rocking table or motor cam, counter, chamber | REPO (E23, PROPOSED there): at least 150 at 20 C; at least 100 at 0 C. PROPOSED check: the count agrees within 30 % with the measured capacity above 3.5 V (F5) divided by the measured energy of one cycle (F2) |
| F7 | Standby time | `DESIGN_SPEC.md` section 6 (E23); `master_params.yaml` `requirements.standby_days` | Requirement: at least 45 days asleep from a full charge to the low-battery symbol at 20 C. Model: 76 days to empty at 23.7 microamps at the cell, underside dark, display counted as 0, no self-discharge; about 2.3 months with 41 mAh usable and 2 % a month of self-discharge (the specification's arithmetic). With a lit underside the model draws 28.9 | TARGET; CALC | Charge fully, leave at rest at 23 C in the dark. Every two weeks read the cell voltage at the cell pads with a high-impedance voltmeter. At the end measure what capacity is left | Long-term boards LB1 and LB2 (section 4.1), 12 weeks, then extrapolate. Not sealed units: no unit can be left alone for 12 weeks (U5 and U9, the only candidates, are needed for the drift checks and are destroyed in week 12) | Voltmeter, battery tester | REPO (E23, PROPOSED there): at least 45 days from full to 3.5 V, measured or by extrapolation. This limit and the F4 limit fit together only if enough of the capacity lies above 3.5 V: a board at 25 microamps at the pads draws about 28 at the cell, 0.67 mAh a day, so 45 days need about 30 mAh above the symbol before self-discharge (our arithmetic), which is 70 % of the listed 43 mAh. F5 measures that share. Also report the drain beyond the board's own F4 value: it is the protection circuit plus self-discharge |
| F8 | Ship-mode current | `DESIGN_SPEC.md` section 6 (E13, E23) and `master_params.yaml` `requirements.ship_mode` for the limit (both still say "not modelled"); `firmware/README.md` "Ship mode (E13)" and the test log for the model | Requirement: at most 5 microamps at the cell, protection circuit included. Model: 12.93 microamps at the cell at 3.9 V (9.93 at the pads by our arithmetic: the model counts 3.0 for the protection circuit), plus the display. **NOT MET in the model** | TARGET; CALC | Arm ship mode by its command through the pin nest, remove VBUS, wait 2 s (the firmware enters the state 1 s after VBUS has gone). Measure the current at the cell-lead pads at 3.9 V. A meter in the cell lead cannot see the protection circuit, which is inside the pack: its draw comes from the cell data sheet or from the voltage decay in Q1. Then check that motion does not wake the board and that VBUS does | All boards **before sealing** | Supply with a microamp range, pin nest | REPO (E23, PROPOSED there): pad current plus the protection circuit's draw at most 5 microamps. **Expected to fail** on the model's figures. The record decides between the two remedies the firmware notes name: change the board (the 2 megohm battery divider is 1.95 microamps, the regulator 1.6, the unconfirmed enable pin 2.8) or change the requirement. REPO: motion does not wake it; VBUS does |

### 2.8 Display in sunlight

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| H1 | Can a standing golfer read it in full sun? | `DESIGN_SPEC.md` section 3 ("Sunlight readable"), 22 mm window | No number | VENDOR class claim | Marker on turf in direct sun. Five observers standing (eye about 1.6 m above it) call out the distance, the break text and the side of the line. 20 trials each, with the sun in front, behind and at the side | U1, U7; 5 observers x 20 trials x 3 sun positions | Lux meter | PROPOSED: at least 95 % correct at 80,000 lux or more; also at 1,000 lux (shade) and 50 lux (dusk) |
| H2 | Polarised sunglasses | `docs/research/display.md` section 2, item 4: a quarter-wave film is "required, not optional, if polarised sunglasses are in scope". `DESIGN_SPEC.md` E9, E19: a quarter-wave film under the cover glass is an **EVT trial** (dia 23.4 mm with a clocking flat, at most 0.11 mm with its adhesive, axis at 45 degrees to the display polariser; `basis: provisional` in the YAML) | - | - | H1 repeated with polarised sunglasses, marker turned to 0, 45 and 90 degrees. PROPOSED: one field unit is built with the film and one without, so that the trial has a comparison (the build split is the manufacturing plan's to fix) | Same | Polarised sunglasses | PROPOSED: readable at every heading with the film. Report the unit without the film beside it. If the film does not help or costs contrast in H1: a recorded limitation (section 5) |
| H3 | Fogging under the glass | `mechanical/README.md` section 9, test 7 | - | - | Soak warm and humid (40 C, 90 %, 24 h), then put a cold plate (5 C) on the glass | U4, U8 | Humidity chamber, cold plate | PROPOSED: no mist visible in the window after 60 s |

### 2.9 Charging, temperature limits and the cell temperature cut-offs

NTC means a small temperature sensor glued beside the cell. Rev E has two (E2): NTC1 belongs to
the charger and NTC2 to the processor. The charger (E1: TI BQ25101) starts by itself whenever 5 V
is present and keeps to a temperature window of its own through NTC1, with no firmware running.
The firmware can only stop it, and does so on a narrower window read from NTC2 (REPO:
`DESIGN_SPEC.md` section 4; `firmware/README.md` "Charger and cell temperature"). No data sheet of
the BQ25101 was read: its thresholds, ball map and behaviour are PROVISIONAL, and every statement
below about what the charger does alone is a statement about the firmware package's model of it.
Since E13 the firmware also refuses a camera read when NTC2 reads above 60 C.

**Hot tests with a cell inside (J7, J8, N3, Q3, and the 60 C footstep in K1).** The only cell
temperature data in the repository is for the cell *family*: charge at 0 to 45 C, discharge at
-20 to +60 C (`bom-verification-opto.md` 3.4). The highest storage temperature of this cell is
not known. It is an open release gate (`mechanical/README.md` section 12, "Battery (B15)";
gate G3 of `MANUFACTURING_PLAN.md`). The repository's own qualification figure of 70 C is
therefore above the only cell limit it holds. Until the cell data sheet is in hand:

1. **No unit with a real cell goes above 60 C.** The 70 C part of a test is run on shells that
   carry a dummy cell (a 2.0 mm block), not on units.
2. **Each hot test states the charge level.** PROPOSED: about half charge for J8 and N3 (3.7 to
   3.85 V at rest, read over USB; an exact level cannot be set, section 6, item 6). Full charge
   for Q3, on purpose: it is the swelling test.
3. **Fire-safe set-up.** A chamber or oven that may be lost, units on a metal tray with sand,
   nothing flammable near, never left running in an unattended office.
4. **Swelling check** before and after every hot step: height of the cover glass against the
   top face, a straightedge across the base plate, and the weight. A unit that has swollen is
   not charged again.
5. **Shells ride along.** Two shells with a dummy cell go through J8, and two through N3,
   beside the units.
   If the shells pass and the units fail, the cell is the suspect. If both fail, it is the
   enclosure. Without them a failure could not be told apart.

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| J1 | Charge current and end voltage | `DESIGN_SPEC.md` section 4 ("Charger (E1)"); `firmware/README.md` "Charger and cell temperature" | 19.8 mA (6.81 kilohm on ISET); 4.20 V end voltage; the charger ends the charge when its output falls below 1.98 mA | TARGET | Meter in the cell line on a board; voltmeter at the end of charge | 3 boards before sealing; then charge time on U3, U8 | Meters, test cell | PROPOSED: 20 mA +-10 %; 4.20 V +-1 %; full charge from empty within 3.5 h (43 mAh at 19.8 mA is 2.2 h before the current tapers: our arithmetic; no model of a whole charge exists) |
| J2 | Charging starts with a dead processor | Same: "charging is ON BY DEFAULT ... a cell at its protection cut-off must be rechargeable" | - | TARGET | Hold reset low, apply 5 V. Then repeat with a cell drained to its cut-off | 3 boards; then the long-term boards LB3 and LB4 when their cells are at the cut-off (Q2) | Meter | REPO: charge current flows in both cases |
| J3 | Charging stops outside the allowed temperature | `DESIGN_SPEC.md` section 4 (E1: the charger's own window; firmware window 0 to 45 C); `firmware/README.md` "Charger and cell temperature" | Firmware (NTC2): stops below 1.5 C and above 43.5 C; resumes above 3.5 C and below 41.5 C; checks every 5 s. Charger alone (NTC1, MODEL, PROVISIONAL): off below 0 C and above 60 C, half current below 10 C, 4.06 V above 45 C | TARGET; SIM | Unit in its cradle in the chamber. Ramp -5 to 50 C and back at 0.5 K per minute. Log charge current and a reference thermometer taped to the marker. On boards: the same ramp with the processor held in reset, so that the charger's own window is seen, up to 50 C only with a real cell | U4, U8; on 2 boards with a thermocouple on the cell itself | Chamber, current logger, thermocouple | REPO: with firmware running, no charging with the cell below 0 C or above 45 C. PROPOSED: stop and resume points within +-1.5 K of the firmware's values; charging stops within 10 s of a sudden crossing. With the processor in reset: no charging below 0 C, and the end voltage recorded between 45 and 50 C. Whether the cell may be charged at 4.06 V above 45 C is the cell data sheet's answer (release gate) |
| J4 | Sensor faults | `firmware/README.md`: an open, shorted or stuck NTC2 stops the charge; an open NTC1 lets the charger (MODEL) charge with no temperature window, no timer and no termination while no firmware runs | - | SIM | Open, short and tie the NTC2 line on a board with firmware running. Then open NTC1 with the processor held in reset, at room temperature only, on a supply that can absorb current in place of the cell | 2 boards before sealing | Jumpers, sink supply | REPO: with firmware running the charge stops in each NTC2 case, and an open NTC1 is flagged (`ntc1_suspect`). The open-NTC1 case without firmware is **expected to charge**: the firmware log marks it NOT MET in hardware alone. The record says whether the real part behaves as the model does; board test must prove NTC1 on every board |
| J5 | Is the sensor at the cell's temperature? | `firmware/README.md` open issue 5a: the 1.5 K guard band "does not cover" a difference between the cell and the sensor | Unknown | - | Thermocouple on the cell centre against the firmware's reading, during charging and in sun | 2 boards before sealing (open tub) | Thermocouples | PROPOSED: difference at most 2 K. If more, the guard band must grow |
| J6 | The cases no firmware watches | `firmware/README.md` "Charger and cell temperature", state table: firmware hung (unwatched for 33 s; the watchdog period is 32 s) and the processor's built-in USB loader running. At rev D nothing limited the charge in these cases. At rev E the charger's own window does (MODEL): at 65 C it does not charge; at 50 C it charges in its warm zone to 4.06 V, for 33 s and for 600 s of 600 s. Both are marked NOT MET for the firmware's 45 C limit. In the loader the charge also never ends by itself | Charger window 0 to 60 C (PROVISIONAL) | SIM | Show both on a board at 50 C and at 65 C. A supply that can absorb current stands in for the cell: no real cell is charged above 45 C | 1 board | Chamber, sink supply | PROPOSED: no charge current at 65 C in either case; at 50 C the end voltage is the charger's reduced one. The record feeds the owner's decision whether the charger's window is accepted where the firmware's 45 C limit is not enforced |
| J7 | Sun soak, and the "too hot" rule (E13) | `docs/research/enclosure-manufacturing.md` section 2 (reviewer's energy balance): 55 to 77 C in a light breeze, 85 to 92 C in still air on an insulating surface. Cell family limits (`bom-verification-opto.md` 3.4): discharge up to 60 C. `firmware/README.md`: no read while NTC2 reads above 60.0 C, and none until it has fallen 3.0 K below | 55 to 92 C; read refused above 60 C | CALC; SIM | Two hours at midday on dry turf and on a black insulating board, air at 30 C or more. A placement every 10 minutes: the log records the temperature and, when the read is refused, the "too hot" event. Hot-test rules above: watch the surface thermocouple and end the run if it passes 60 C before the cell data sheet is in hand. The refusal itself is shown on a board in the chamber at 62 C and 56 C with a dummy cell | U2, U7; 1 board | Thermocouple on the surface, weather record, chamber | REPO: no camera read with NTC2 above 60 C; the marker shows its "too hot" screen and reads again after cooling. PROPOSED: unit works afterwards; zero moves by at most 0.3 mrad; glass still below flush; no swelling; internal peak recorded |
| J8 | Hot and cold storage | `mechanical/README.md` section 9 (70 C loads) | - | - | 24 h hot and 24 h at -20 C, unpowered, at about half charge, then 4 h at room temperature. Hot part: 60 C for units with a cell; 70 C only when the cell data sheet allows it (gate G3). Two shells with a dummy cell take 70 C in any case (hot-test rules above) | U4, U8; 2 shells with a dummy cell | Chamber, fire-safe tray | PROPOSED: works; zero within 0.3 mrad; leak test passes; no swelling |
| J9 | Cradle on different USB sources | `DESIGN_SPEC.md` section 4 (E6, E25, E36): USB-C socket, 5.1 kilohm from each CC pin to ground, a resettable fuse (on the routed cradle: holds 0.35 A at 1.0 ohm, trips at 0.75 A, PROVISIONAL), a 1.0 mm board; in the marker an ideal-diode switch in place of the series diode (wiring PROVISIONAL) | 5 V only. Worst-case charger input about 4.5 V from a 4.75 V source (CALC in the specification) | TARGET; CALC | Cradle on: a PC port, a plain 5 V charger with an A-to-C cable, and a USB-C charger with a C-to-C cable. Measure the voltage at the charger input of a docked board at a source set to 4.75 V. Then short VBUS to ground at the pins for 10 minutes. Then check with a voltmeter that the VBUS pad of an undocked board with a cell does not carry the cell voltage (E25: the switch must block reverse current) | 3 cradles; 1 board | Three sources, bench supply, meter, thermocouple | PROPOSED: 5 V appears on every source; never more than 5.5 V; charger input at least 4.45 V (the minimum the specification records for the charger) from a 4.75 V source; under a short the fuse limits the current, nothing exceeds 60 C, and it recovers; no cell voltage on the VBUS pad of an undocked marker |
| J10 | The charge ends in the cradle (E32) | `DESIGN_SPEC.md` E32; `firmware/README.md` "Cradle, ship mode and the hot cell" | MODEL: an awake docked marker draws 3.35 mA, above the charger's 1.98 mA end threshold, so the charge never ends. Asleep in the cradle it draws 98.6 microamps and the charge ends. The firmware stops any charge 6 hours after docking. Left docked for 30 days the model's cell cycles down to 79.3 % and is recharged 4 times (an open owner decision in the firmware notes) | SIM | (a) Dock on a wall charger: the marker must show the static charging picture within about 30 s and later "FULL". (b) Dock on a PC that keeps talking to it: record when the charge stops. (c) Leave a unit docked on a wall charger for 7 days and log the cell voltage through the PC tool at the end | U3, U8 | Wall charger, PC, current logger on the cradle supply | REPO: (a) asleep 30 s after docking with no host, and the charge ends; (b) stopped by the firmware 6 h after docking. PROPOSED for (c): cell voltage at the end not more than 0.05 V below the firmware's restart voltage of 4.00 V. Known and NOT MET in the firmware log: after 30 s of silence on a running USB bus the marker leaves the bus and a PC reaches it again only after re-docking |

### 2.10 Water

**What is honest to claim.** The marker is glued shut and has a small breathing vent. Think
of a rain jacket, not a diving suit. The vent's resistance to water pressure is not confirmed
(REPO: `mechanical/README.md` section 9, "Vent"). The slot over the charging contacts is open
to the outside by design. So the claim to earn at EVT is **rain and wet grass**. Immersion is
tested last, on units already given up, to see whether more can honestly be said later. Even
a clean pass on five units supports no promise on the box (section 1.3).

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| W1 | Factory leak test, every tub and every unit | `mechanical/README.md` steps 10 and 18; air inside 4.2 cm3 | No limit defined ("limit not yet defined", `MANUFACTURING_PLAN.md` 7.1) | - | Pressure-decay test with the vent covered | All tubs, all units, all shells; repeated after every test below | Leak tester with a small chamber | PROPOSED starting point: leak of at most 0.1 cm3 per minute at 10 kPa. To be tightened or loosened once W3 to W6 show which leak rates let water in |
| W2 | Seal strength under pressure | `mechanical/README.md` section 9, test 2 (loads from the enclosure research, "itself unverified") | 25 kPa inward; 40 kPa outward for 24 h at 70 C with the vent blocked (about 55 N pushing the base out) | CALC | Pressure pot (inward) and internal pressure through a drilled port (outward) | 6 shells: 3 FR-4, 3 PA12 | Pressure pot, regulator, oven | REPO loads. PROPOSED pass: no leak in W1 afterwards and the base plate has not moved by more than 0.02 mm |
| W3 | Wet grass and dew | `mechanical/README.md` section 12, open issue 8 (the contact slot holds 37 mm3 of water) | - | - | Eight hours on soaked turf or a wet sponge, a read every 30 minutes | U2, U3, U4, U7, U8 (potted units only; U1 is kept out of the water tests) | Sponge tray | PROPOSED: works throughout; no mist behind any glass; W1 passes; weight gain after wiping and one hour of drying at most 5 mg |
| W4 | Rain | - | - | - | Spray from every side, underside included, 10 minutes, about 1 litre per minute through a shower head held 0.5 m away (PROPOSED in-house method). A lab test to the splash level of the international standard IEC 60529 ("IPX4") is the formal version; its exact parameters were not confirmed today (PROVISIONAL) | Same five units | Shower head, flow meter, scale good to 1 mg | PROPOSED: as W3 |
| W5 | A step on a wet unit | `mechanical/README.md` section 9, test 3 ("does a sole pump water through the vent?") | - | - | Water film on the roof; press a 20 mm rubber pad on the vent area with 400 N, ten times. Not on the glass (the EVT glass is not step-proof) | U4, U8, 3 shells | Press with a load cell | PROPOSED: as W3 |
| W6 | Hot marker into cold water | `enclosure-manufacturing.md` section 1: a wet vent passes no air, so the seals see about 23.5 kPa inward | 23.5 to 26 kPa | CALC | Heat to 60 C, drop into 20 C water 0.15 m deep for one minute | 3 shells first; then U3, U4, U8 | Oven, basin | Exploratory. PROPOSED: no water inside (weight, mist). The result decides the wording of the user warning |
| W7 | Immersion, 1 m for 30 minutes | The international code for this is "IPX7" (VERIFIED: test conditions as summarised in [V3]) | No claim is made | - | As stated | 3 shells; then U4, U8 as their last test before sectioning | Water column or pressure pot at 10 kPa | Exploratory. No pass or fail at EVT |
| W8 | Vent: water entry pressure | `enclosure-manufacturing.md` section 2 (specify at least 50 kPa); vendor figure not found (`bom-verification-opto.md` 3.13) | 50 kPa wanted | TARGET | Vent on a printed coupon over a 1 mm hole; water pressure raised to 50 kPa for 10 minutes | 5 coupons | Pressure pot | REPO target: no drop passes at 50 kPa |
| W9 | Adhesive coupons | `mechanical/README.md` section 9, test 4 | Ball push-out target 100 N; window coupon 25 kPa both ways; 100 cycles of -10 to 70 C | TARGET | As listed there: lap-shear and peel on the real materials, before and after cycling, sunlight, sunscreen and fertiliser | Coupons, not units | Tensile tester, chamber | REPO where given. Strength limits come from each adhesive's data sheet once chosen |
| W10 | Grain window after mud, fertiliser and sand | `mechanical/README.md` section 9, test 11 | - | - | Soak and rub; then check the sensor signal and the surface | U4, U8, coupons | - | PROPOSED: sensor signal on the white tile changes by at most 5 %; no pit proud of the base plane |
| W11 | Cuts through the seal | `mechanical/README.md` section 9, test 1 | Joint and groove filled | TARGET | Saw units through the rim at four places | U4, U8 at the very end; 2 shells early | Saw, microscope | REPO: perimeter joint and groove filled, no channel |

### 2.11 Footstep, drop and the ball feet

**EVT units are declared NOT step-proof** (REPO: `DESIGN_SPEC.md` section 5, item 4). The
flat mineral crystal is expected to break at 100 to 200 N on a 20 mm patch (reviewer's
estimate). No EVT result can earn a step-proof claim.

The test that would earn it, on the production glass, is defined now so that EVT can try the
rest of the structure:

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| K0 | **The step-proof test (for DVT, production glass)** | `mechanical/README.md` section 12, test item 2 and open issues 3 to 5 | 800 N on a 20 mm indenter, on the glass and on the roof, on turf and on a hard floor, at 23 and 60 C, display powered. Estimates: about 400 MPa in a 1 mm crystal; 39 MPa under the post feet (800 N on 20.6 mm2) against 48 MPa yield for PA12 | TARGET; CALC | Eight conditions (2 places x 2 supports x 2 temperatures). 800 N held 5 s, ten times per condition. "Turf" is real turf or a 20 mm rubber pad; "hard floor" is a steel plate. Indenter with a 2 mm rubber face | DVT: at least 5 units per condition, glass specified at 600 MPa ring-on-ring or more (REPO) | Test press with a load cell, oven | PROPOSED: no crack; display undamaged; W1 passes; ball heights still 0.10 +-0.02 mm; after the user's re-zeroing the zero is within 0.3 mrad (REPO: a hard-floor step "requires re-zeroing in any case"); one further press to 1200 N without a crack |
| K1 | EVT footstep on the roof and structure | Same | Same loads | Same | K0 on the roof beside the glass, and on shells whose crystal is replaced by a steel disc, so that posts, board and base are loaded | 4 shells; then U6, U10 (at 60 C, weeks 10 to 12) and U5, U9 (at 23 C, week 12, after the last drift check), each as its last test | Same | Same limits, glass excluded. Units are treated as destroyed |
| K2 | What the EVT crystal really takes | Reviewer's estimate | 100 to 200 N | CALC | Ramp the load on the glass until it breaks | 3 shells | Same | Report only |
| K3 | Drop | `DESIGN_SPEC.md` section 6 (E23); `master_params.yaml` `requirements.drop`. PROPOSED there until measured | 1.0 m onto paving, six attitudes. 1.5 m is recorded and is not a requirement at EVT | TARGET | Free fall of 1.0 m onto paving, once on each of six attitudes: glass down, base down, visor flat, rear edge, left, right. Then 1.5 m, same six | U2, U7 (after their field work); 3 shells first | Drop guide, paving slab | REPO (E23) after the six 1.0 m drops: the marker works; it passes the leak test (W1); its ball-seat level zero has moved by at most 0.5 mrad; its stereo calibration is still within its acceptance limit; cosmetic marks are allowed. No stereo acceptance limit exists yet (section 6, item 8), so PROPOSED until it does: distance at 6 m changed by at most 0.1 px (4.6 %). PROPOSED extras: no crack; three ball feet present; after the user's re-zeroing the zero is within 0.3 mrad. The 1.5 m drops are report-only |
| K4 | Ball feet: push-in and pull-out | `mechanical/README.md` section 12, test item 7 | 100 N | TARGET | Push each ball inward and outward with a pin | 3 shells; then the units destroyed in K1 | Press with a load cell | REPO: 100 N without movement |
| K5 | Ball height after thermal cycling | Same | 0.10 +-0.02 mm | TARGET | A4 repeated after test N3 | U4, U6, U8, U10 | Height gauge | REPO |

### 2.12 Cradle: latch, contacts, wet docking

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| M1 | Latch life | `mechanical/README.md` section 12, test item 3; section 8 | 3000 insert and release cycles at 23 C and at 0 C. Calculated strain 2.05 % against a 2.5 % limit | TARGET; CALC | Cycle by hand with a counter or on a small rig. Measure the hook position before and after | PROPOSED: 2 cradles per temperature from each of 2 print builds (8 cradles) | Chamber at 0 C, calipers, force gauge | REPO: 3000 cycles without a crack. PROPOSED: wall-to-hook distance still 39.95 +-0.15 mm; insert force 8 to 15 N; release force 7 to 14 N (calculated: about 11 N and 9 to 12 N) |
| M2 | Latch creep | Same | 1000 h at 50 C with seven pins fitted. Calculated hook movement 0.54 mm against 0.85 mm of overlap | TARGET; CALC | A marker (or a shell) latched in, in an oven | PROPOSED: 2 cradles from each build (4) | Oven | REPO: still latched. PROPOSED: passes M3 afterwards; hook returns to within 0.3 mm of its start once unloaded |
| M3 | Pull-out | Same | 12.4 N at the pin row (three times the force of seven pins). Calculated margin 6.0 times, 3.4 times at the worst print tolerance | TARGET; CALC | Pull the rear of the marker upward at the pin row without pressing the tab | Every cradle, before and after M1 and M2 | Force gauge with a hook | REPO: holds 12.4 N |
| M4 | Contact pad wear | `DESIGN_SPEC.md` section 5, item 6 (plain gold at EVT, hard gold in production) | No cycle number for the pads | - | The M1 cycles, with a real board underside in the shell. Contact resistance every 500 cycles; microscope at the end | 2 boards in shells (or U6, U10) | Milliohm meter, microscope | PROPOSED: each contact at most 100 milliohms through 3000 cycles; report the cycle count at which the gold is worn through |
| M5 | Wet docking | `mechanical/README.md` section 9, test 8 and open issue 8 | 100 dockings of a marker wetted with a 0.3 S/m solution (roughly hard tap water with fertiliser). Estimated leakage through the water film: 0.1 to 0.6 mA | TARGET; CALC | Wet the slot, dock with 5 V on for 5 minutes, undock; 100 times | U3, U8 | Salt solution and conductivity meter, current meter, microscope | PROPOSED: leakage at most 1 mA; the fuse does not trip; the PC still sees the unit; contacts at most 100 milliohms; no green or black deposit at 10 times magnification |

### 2.13 USB, firmware update, storage, long cycling

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| P1 | The PC sees the marker | `DESIGN_SPEC.md` section 3 (USB through the cradle; no crystal: PROVISIONAL there) and E34 (USB vendor and product IDs: none assigned, a release gate) | - | TARGET | Dock 50 times on each of three kinds of PC. EVT units need some pair of IDs to be seen at all; which pair is the owner's decision and is written on the test record | All 10 units, 3 PCs | PCs with Windows, macOS, Linux | PROPOSED: recognised within 5 s every time |
| P2 | Data link | `firmware/README.md` "Protocol" (tested on a PC only) | Every corrupted frame rejected | SIM | 10,000 echo frames; a full dump of a filled log while the marker is rocked in the cradle | U1, U7 | PC tool (section 6, item 4) | PROPOSED: no undetected error; dump identical twice |
| P3 | Firmware update | `DESIGN_SPEC.md` E34; `firmware/README.md` "Boot stub (E34)" and "Station tests that still cannot be run": a write-protected boot stub checks the application image (length and CRC) and starts the processor's built-in USB loader when the image is invalid or an update was requested. The stub is compiled and linked and has never run; no application image has been linked; no PC-side updater exists (the PC tool only enters the loader) | - | - | 20 updates in a row. Calibration read back before and after | All 10 units | PC update tool (does not exist: section 6, item 10) | PROPOSED: 20 of 20 succeed; calibration unchanged (REPO: it is stored outside the processor). Cannot be run until an image and an updater exist |
| P4 | Interrupted update | Same. REPO intent (E34): an update cannot strand a unit; factory recovery is by the three service pins of the factory cradle. Known and NOT MET in the firmware notes (open issue 59): once in the built-in loader, only a PC with a DFU program gets the unit out | - | - | Lift the marker out of the cradle during the update, 10 times. Dock again each time and update | U5 only, in week 12 after its last drift check | Consumer cradle, PC; factory fixture with 7 pins in reserve | REPO (E34): 10 of 10 recover through the 4-pin consumer cradle without the factory fixture. Cannot be run until an image and an updater exist |
| Q1 | Shelf life in ship mode from the shipping charge | `DESIGN_SPEC.md` section 6 (E13, E23): units are shipped and stored in ship mode; at least 3 months from a 30 % charge without the cell falling below 3.0 V; stock older than 3 months is recharged before sale. PROPOSED there | MODEL: 42 days from 30 % (12.9 mAh at 12.93 microamps). **NOT MET in the model.** In an ordinary sleep the same cell lasts 23 days in the model | TARGET; CALC | Two boards with cells, set to about 30 % charge with the battery tester (70 % of the measured capacity taken out), put into ship mode, 23 C, cell voltage every two weeks with a high-impedance voltmeter at the cell pads | Long-term boards LB3 and LB4 (section 4.1), 13 weeks | Battery tester, voltmeter, pin nest | REPO (E23, PROPOSED there): cell at or above 3.0 V after 3 months. **Expected to fail** on the model's figures unless F8 shows a lower current than the model. Report the time to 3.25 V and to 3.0 V, and the drain against the board's F8 value: the difference is the protection circuit plus self-discharge. The result, with F8, decides the shipping charge and the recharge interval for stock |
| Q2 | Recovery of a flat cell | `DESIGN_SPEC.md` section 4 (charger on by default for this case) | - | TARGET | Drain to the cut-off, leave 4 weeks, then apply 5 V through the pin nest of the bring-up station | LB3 and LB4 after Q1 (drained the rest of the way with a load) | Battery tester | PROPOSED: charges again without help; capacity at least 90 % of the first measurement |
| Q3 | Hot storage at full charge | `master_params.yaml` `battery.swell_allowance` 0.4 mm; `mechanical/README.md` section 5 and open issue 13: 0.09 mm left above a fully swollen cell once the 0.06 mm fixing adhesive of E22 is counted (0.15 mm before it; open issue 13 still gives the adhesive as 0.05 mm, `docs/RELEASE_GATES.md` G-107) | 0.4 mm | TARGET | 10 days at 60 C, fully charged. 60 C is the cell family's discharge limit, not a known storage limit: run this only when the cell data sheet (gate G3) allows 60 C storage at full charge, or at the data-sheet limit if that is lower. Swelling check every two days (hot-test rules, section 2.9) | U6, U10 | Oven, fire-safe tray | PROPOSED: glass still below flush; display unmarked; capacity loss at most 20 % |
| Q4 | Swollen cell | `mechanical/README.md` section 9, test 10 | - | - | A 2.4 mm dummy cell in a shell, 25 kPa quench, display powered | 2 shells with displays | - | PROPOSED: display unmarked |
| N3 | Long thermal cycling of sealed units | `mechanical/README.md` section 9, test 9 | 100 cycles of -10 to 70 C; then leak test, display position, tilt offset | TARGET | As stated, unpowered, at about half charge. The README asks for 70 C on complete units. Units with a real cell go to 70 C only when the cell data sheet allows that storage temperature (gate G3). Until then their upper temperature is 60 C, recorded as a deviation from the README's test, and two shells with a dummy cell take the full -10 to 70 C (hot-test rules, section 2.9) | U4, U6, U8, U10; 2 shells with a dummy cell | Chamber (about 9 days), fire-safe tray | PROPOSED: W1 passes; display still centred; zero moved by at most 0.5 mrad before re-zeroing; ball heights in tolerance; no swelling; C3 passes on U4 and U8 |
| R1 | Radio emissions pre-scan | `docs/COMPLIANCE.md` row 2 | - | - | A quick scan at a test lab: marker reading in a loop, and marker in the cradle talking to a PC | U3 with a consumer cradle | Lab | Report against the Class B limits. Not a formal test at EVT |

---

## 3. Checking the simulator itself

The simulation is the only source of performance figures today. It is honest about what it
assumed (`sim/results/REPORT.md` section 13). It is also one hardware revision behind in its
optics: the report says it takes the optical and inertial parameters as they stood at hardware
revision C, and it has not been run again for rev E. The stereo numbers (20.0 mm, 657 px) are
the same in rev E; the upward field is not (the simulation used the nominal field, rev E
guarantees 14.0 degrees). EVT must replace those assumptions with
measurements, then run the simulation again with the measured values. Only that second run is
a prediction worth quoting.

### 3.1 Assumptions the field data must confirm

| # | Assumption in the simulator | Where | Field measurement that checks it | What changes if it is wrong |
|---|---|---|---|---|
| 1 | **Speed model.** The ball slows at a constant rate set by the Stimp: a ball released at 1.83 m/s rolls "Stimp" feet | `sim/greenline_sim/physics.py`; `putting-physics.md` findings 4 and 6 (real slowing rises at low speed by about 10 % over a 4 m putt) | Ramp on a level patch: roll-out distance at four release speeds, speed measured over a 0.3 m gate with slow-motion video | Pace advice ("PLAYS") and the break both scale with it. PROPOSED limit: predicted roll-out within +-5 % from 1.5 to 9 m |
| 2 | **Slope and friction.** Break follows `(5/7) x gravity x slope`; on a plane the aim angle is `(5/14) x gravity x cross slope / slowing rate`, the same at every distance. Reference point: 3.05 m, 1 % cross slope, Stimp 10, 0.43 m past: aim 13.7 cm outside | `REPORT.md` section 14.2 | D1 putts on areas that are plane within +-0.2 % (level every 0.5 m): measured true aim point against the model with the measured slope and Stimp | A gain error on every read. PROPOSED limit: within +-15 % or +-1.5 cm at 3 m. The research allows a correction gain of 0.90 to 1.10 |
| 3 | **Seating noise** 2.5 mrad per axis, independent between placements, no outliers | `REPORT.md` section 4.1 | S1, S2, S3 | Section 1.1 |
| 4 | **Device bias** 1 mrad per axis | `REPORT.md` section 13 | A3, S4 | 2.5 mrad costs about 1 point |
| 5 | **Greens are smooth at the metre scale** | `REPORT.md` section 4.3 | S6 | 2 mm RMS of relief costs about 5 points |
| 6 | **Patch fit, method B1.** The green is one smooth curved patch fitted to the tilt and to the height of the flag base. The fit is assumed to know whether the base is hidden | `REPORT.md` sections 3, 7; `sim/README.md` | C7 (hole height), the hidden-base counts, and replay of the D1 logs with B0 (tilt only) against B1 | In the simulation B1 improves pace, not line (median pace error 40 cm against 51 cm at 6 m). If the field shows no pace gain, the flag-base channel is not earning its place |
| 7 | **Distance noise** 0.08 px random, no bias | `REPORT.md` section 6 | C1, C2, C3 | Section 2.4 |
| 8 | **Flag detection**: 2 % miss floor, perfect rejection of other objects | `REPORT.md` section 7 | C6 | A 20 % miss rate costs 2 points |
| 9 | **The golfer** copies the line to 0.5 degree; the screen draws the line in 0.94 degree steps | `REPORT.md` section 4.2 | D0, D6 | 1 degree costs about 3 points. Note: the firmware's own display test claims 0.05 degree (section 7, item 4) |
| 10 | **Green speed entered by the golfer** is right to 7 % | `REPORT.md` section 11 | Ask each D5 golfer to estimate the Stimp; compare with the Stimpmeter | 15 % costs about 4 points and doubles the pace error |
| 11 | **Human readers** err by 0.5 % or 1 % of slope and know everything else exactly | `REPORT.md` section 13 | D5 | Changes what the device is compared with, not the device |
| 12 | **Hole capture rule**: holed if the ball crosses within the hole radius below a speed limit; no lip-outs | `REPORT.md` section 13 | D4 counts against the crossing positions and speeds | About 3 points on every method alike |
| 13 | **Heat shimmer** (mirage) is small | `REPORT.md` section 13 | Scatter of the flag-base height on a hot sunny afternoon against an overcast day (C7) | Degrades the hole-height channel at long range |
| 14 | **Survey placements** are within 0.15 m of the line; **hand pointing** is good to 1.5 degrees | `REPORT.md` section 11 | Measure where golfers put the marker in D2 Survey reads; D6 set-up for pointing | Survey gain shrinks from 5 to 3 points at 0.3 m |
| 15 | **The lens is at the ball.** The real lenses are 16 mm ahead and 10 mm either side of the marker centre; the firmware takes the ball centre 44.3 mm ahead of the marker centre | `REPORT.md` section 13; `firmware/README.md` "PROVISIONAL constants" | Photograph how golfers really place the marker behind a ball; measure the gap | A fixed offset of a few millimetres in distance and a small bearing correction |
| 16 | **Grain** is a constant push; the sensor is ideal | `REPORT.md` sections 11, 13 | GR0 to GR4 | The grain function ships off until proven |
| 17 | **Synthetic greens** in four classes stand for real greens | `REPORT.md` section 2 | Record the slopes of every test green; say which class it resembles | The pooled numbers shift with the mix of greens |

### 3.2 What the firmware log holds today

REPO: `firmware/README.md` "Field log" and "PC tool"; `firmware/core/gl_log.h`,
`firmware/core/gl_fieldlog.h`. All of it has run on the firmware's PC simulator only.

- A ring log on the 8 MB memory chip: 2044 blocks of 4 kB. Old records are overwritten when
  it is full.
- **A solved read writes four records with one read number:**
  - a placement record for each placement handed to the estimator (the complete measurement,
    with the turf-horizon profile);
  - the 72-byte summary of firmware phase 2: clock time (1 s steps), read number, flags,
    temperature, battery voltage, slope, bearing, disparity, distance, aim, launch speed, Stimp
    entered, confidence, solver status, picture quality figures;
  - the estimator event (where the aim came from, solver status, flags, method, read tier);
  - a read record of 684 bytes: firmware, solver and calibration versions, the settings in
    force, the seat used, both tilt readings of a Precision Read, three temperatures, cell
    voltage, the grain values when the grain reader ran, stage times in milliseconds, what was
    shown on the screen, the whole estimate and the whole fit record.
- **Tilt records without a camera read:** with the setting TILT LOG = ON every placement writes
  one; with TILT LOG = ONLY the cameras stay off. Not done: logging at intervals while the
  marker lies untouched.
- **Other events:** start-up, faults, zeroing, calibrations, storage mode, ship mode, "too hot",
  charger decisions with the cell temperature.
- **Raw pictures, if switched on:** as before, about 94 kB per read at level FIRST.
- **Capacity (REPO, simulator):** one Quick Read takes 1156 bytes; 6129 Quick Reads are retained
  before the oldest is overwritten. Our arithmetic on those two figures and the 94 kB: with
  level FIRST on, about 85 reads, so in the field the log must then be dumped at least once a
  day.
- **Getting it out:** the PC tool `firmware/tools/glctl` downloads the log over USB in the
  cradle, resumes a broken download and decodes it. Its serial transport has never been
  exercised (the firmware notes say the serial library is not installed where it was built);
  every run so far was against the simulator.

### 3.3 Capture and replay (the software path exists on the simulator; nothing has run on a unit)

```
  ON THE GREEN                          THAT EVENING                 AT THE DESK
 +--------------------+            +---------------------+      +---------------------------+
 | marker log         |--cradle--->| log dump (binary)   |----->| converter: log record ->  |
 | (read 1234, ...)   |            +---------------------+      | simulator "Measurements"  |
 +--------------------+                                         +-------------+-------------+
 +--------------------+            +---------------------+                    |
 | field sheet        |--typed---->| truth table (CSV)   |----->  join on read number
 | (putt 17, true aim)|            +---------------------+                    v
 +--------------------+                                         +---------------------------+
                                                                | 1 same answer as the unit?|
                                                                | 2 other methods, same data|
                                                                | 3 re-fit the noise numbers|
                                                                | 4 re-run the Monte Carlo  |
                                                                +---------------------------+
```

1. **Field sheet, one line per putt:** putt number; date and time; green; grass and mowing
   height; wet or dry; tape distance; Stimp both ways, start and end of session; slope at the
   ball, the midpoint and the hole (level, two axes); surveyed height difference; true aim
   point with its number of rolls and scatter; stopping distances; the read numbers shown by
   the units; wind; anything odd.
2. **Converter.** The simulator's estimator takes a `Measurements` record
   (`sim/greenline_sim/measurements.py`) and nothing else. REPO: `firmware/tools/glctl/logdec.py`
   turns a read record with its placement records into that form, and
   `sim/greenline_sim/replay.py` runs the reference estimator on it. On seven reads made by the
   firmware simulator all seven agree (largest aim difference 0.023 mrad). No log from a real
   unit exists. The join with the field sheet (the truth table) is still to be written.
3. **Check 1: same answer.** The Python estimator, fed the logged inputs, must give the aim
   the unit logged. PROPOSED limit: within 0.5 mrad, the tolerance the firmware's own
   comparison test uses (`firmware/README.md`, "make appdiff").
4. **Check 2: other methods on the same data.** Tilt-only (B0) against the Quick Read (B1)
   against the measured true aim. This is how assumption 6 is tested without more field days.
5. **Check 3: re-fit.** Replace the assumed noise values in the simulator (`SensorParams`)
   with the measured ones from sections 2.2 and 2.4.
6. **Check 4: run the Monte Carlo again** and compare its new prediction with D1. If the two
   agree inside the D1 limits, the simulator is validated for this design. If not, the
   difference points at a missing effect.

What revision 2 of this plan listed as missing from the log is now in it (REPO:
`firmware/README.md` "Field log"): the grain values, the turf-horizon profile, the two tilt
readings of a Precision Read, the settings in force, the fit record with its step count, and a
time stamp in milliseconds. Still missing: a tilt record at intervals without a placement
(section 6, item 1).

---

## 4. Test matrix and schedule for the ten EVT units

### 4.1 The units

Build variants follow `MANUFACTURING_PLAN.md` 2.3.

| Unit | Base plate | Grain opening | Role | End state |
|---|---|---|---|---|
| U1 | FR-4 | potted | Field reference. Never abused | **Kept** as the reference for DVT |
| U2 | FR-4 | potted | Field, then sun soak and drop | At risk (drop) |
| U3 | FR-4 | potted | Field, power, wet docking, hot-into-cold dunk | At risk (dunk) |
| U4 | FR-4 | potted | Environment: charging chamber, 100 cycles, water tests to immersion | **Destroyed** (sectioned) |
| U5 | FR-4 | unpotted | Bench: drift up to week 12, then interrupted update | **Destroyed** (footstep, 23 C, after the week-12 drift check) |
| U6 | FR-4 | unpotted | Bench: drift, 100 cycles, hot storage | **Destroyed** (footstep, 60 C; ball push-out) |
| U7 | PA12 | potted | Field (second variant), then sun soak and drop | At risk (drop) |
| U8 | PA12 | potted | Environment, as U4 | **Destroyed** (sectioned) |
| U9 | PA12 | unpotted | Bench: drift up to week 12 | **Destroyed** (footstep, 23 C, after the week-12 drift check) |
| U10 | PA12 | unpotted | Bench, as U6 | **Destroyed** (footstep, 60 C; ball push-out) |

Six of ten are destroyed by plan. Three more are at risk. One is kept untouched.

**Extra shells (PROPOSED, not in the repository; `MANUFACTURING_PLAN.md` gap 17 asks for the
number):** 20 marker shells without working electronics, 10 with each base plate. A shell is a
tub with glass, windows, vent and a base plate laminated to a bare or scrap board. They take
the first hit in every destructive test so that a real unit is spent only on a test the
shells have already survived. Four of them carry a dummy cell and ride along in the hot tests
(section 2.9). Also: 2 dummy markers for S0, 12 cradles (4 of them with seven pins, for M2),
8 to 10 spare assembled boards for the before-sealing tests, 8 loose cells (5 are measured in
F5).

**Long-term boards LB1 to LB4 (PROPOSED).** Four of the spare assembled boards get a cell
soldered on and are never sealed. They carry the slow battery tests: LB1 and LB2 standby from
full charge (F7); LB3 and LB4 shelf life in ship mode from 30 % charge (Q1), then flat-cell recovery (Q2 and
the second half of J2). Reasons: a sealed unit cannot do these tests and the others it is
booked for; on an open board the cell voltage can be read at the cell pads, and a battery
tester can set the charge level, which no command can do on a sealed unit (section 6, item 6).
`docs/SOURCING.md` section 10.5 prices all the hardware of this section.

### 4.2 Unit by test

`X` = test is run on this unit. `(X)` = only if the unit is still alive and the shells
passed. `D` = this test ends the unit. `-` = not run.

| Test (section 2 ID) | U1 | U2 | U3 | U4 | U5 | U6 | U7 | U8 | U9 | U10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Plate level A1 to A5 | X | X | X | X | X | X | X | X | X | X |
| Drift B1 to B4 | X | X | X | X | X | X | X | X | X | X |
| Drift again at 6 and 12 weeks, B5 | X | - | - | - | X | - | X | - | X | - |
| Field of view O1, O2; light leak L1 | X | X | X | X | X | X | X | X | X | X |
| Line direction on the screen D0 | X | X | X | X | X | X | X | X | X | X |
| USB and update P1, P3 | X | X | X | X | X | X | X | X | X | X |
| Distance and bearing C1 to C5, O3 | X | X | X | X | - | - | X | X | - | - |
| Turf seating S1 to S6 | X | X | X | - | - | - | X | - | - | - |
| Aim on the green D1 to D7, C6, C7 | X | X | - | - | - | - | X | - | - | - |
| Grain GR0 to GR4, stray light L2 | X | X | X | X | - | - | X | X | - | - |
| Read time F1 | X | - | X | - | - | - | X | - | - | - |
| Display in sun H1, H2 | X | - | - | - | - | - | X | - | - | - |
| Reads per charge F6 (20 C and 0 C); charge end in the cradle J10 | - | - | X | - | - | - | - | X | - | - |
| Emissions pre-scan R1 | - | - | X | - | - | - | - | - | - | - |
| Charging in the chamber J3; hot and cold storage J8 | - | - | - | X | - | - | - | X | - | - |
| Sun soak J7 | - | X | - | - | - | - | X | - | - | - |
| Wet grass and rain W3, W4 | - | X | X | X | - | - | X | X | - | - |
| 100 thermal cycles N3; ball height K5 (and calibration hold C3 on U4, U8) | - | - | - | X | - | X | - | X | - | X |
| Hot storage at full charge Q3 | - | - | - | - | - | X | - | - | - | X |
| Fogging H3; wet step W5; grain window W10 | - | - | - | X | - | - | - | X | - | - |
| Wet docking M5 | - | - | X | - | - | - | - | X | - | - |
| Pad wear M4 (as the "marker" in the latch rig) | - | - | - | - | - | X | - | - | - | X |
| Interrupted update P4 (week 12, after the last drift check) | - | - | - | - | X | - | - | - | - | - |
| Drop K3 | - | (X) | - | - | - | - | (X) | - | - | - |
| Hot-into-cold dunk W6 | - | - | (X) | (X) | - | - | - | (X) | - | - |
| Immersion W7 | - | - | - | (X) | - | - | - | (X) | - | - |
| Footstep K1, then ball push-out K4 | - | - | - | - | D | D | - | - | D | D |
| Sectioned W11 | - | - | - | D | - | - | - | D | - | - |

Not on the ten units: S0 (dummies); F2 to F5, F8, J1, J2, J4 to J6 (boards before sealing, loose
cells); F7, Q1, Q2 (long-term boards LB1 to LB4); W2, W8, W9, K2, Q4 and the first pass of W6,
W7, K1, K3, K4 (shells and coupons); the 70 C part of J8 and N3 (shells with a dummy cell);
M1 to M3, J9 (cradles).

U5 and U9 are the only unpotted units left for the week-12 drift check (B5 needs one unit of
each variant), so they are kept whole until then and take the footstep test last.

### 4.3 Schedule order

Week 0 is the week the first sealed units finish their cure and first temperature cycle.
Durations are PROPOSED planning figures. Nothing has been timed.

| When | What | Why here |
|---|---|---|
| Before week 0 | S0 dummy seating on turf. Coupons W9, vent W8. Assembly trials. Cell capacity F5 | Needs no electronics. Answers the first question early |
| Board bring-up (before sealing) | F2, F3, F4, F8, J1, J2, J4, J5, J6. Solder cells to the long-term boards LB1 to LB4 and start F7 and Q1 on them | Cannot be measured after the cell is soldered and the unit is sealed. The 12-week clocks start as early as possible |
| Week 0 | Start the cradle creep test M2 (it runs 1000 h, six weeks). Start M1 | Longest clock in the plan |
| Weeks 1 to 2 | Bench, all ten units: A1 to A5, O1, O2, L1, D0, P1, P3. Drift round one: B1 to B4. Distance baseline C1 to C5 | Nothing goes to the grass uncalibrated or unchecked |
| Week 3 | Turf seating S1 to S6 | **Decision point 1.** Green or amber: go on. Red: stop field aim tests, review with the owner (section 5) |
| Weeks 3 to 6 | Field: D1 to D7, C6, C7, O3, grain data GR0 to GR4, L2, H1, H2, F1. Log dumps daily. Replay (section 3.3) as data arrives | **Decision point 2** at the end: does the measured aim error match the re-run simulation? |
| Weeks 5 to 7 | Shell tests: W2, K1, K2, K3, K4, W6, W7, Q4 | Shells first. Their results decide which `(X)` tests are worth a real unit |
| Week 6 | Drift round two (B5) on U1, U5, U7, U9. Cradle M1 finished, M3 | "Some weeks after cure" |
| Weeks 6 to 8 | Gentle bench on units: F6, J3, J7, J8, J9, J10, H3, W3, W4, M5, P2 | Field units are free now |
| Weeks 7 to 9 | N3 (100 cycles, about nine days in the chamber), then K5, C3, W1. Q3 (only if the cell data sheet allows it) | Ageing before the hard water tests |
| Weeks 9 to 10 | W5, W6, W7 on units. K3 drop on U2, U7 | Units that may die |
| Weeks 10 to 12 | K1 footstep and K4 on U6, U10. W11 sections of U4, U8 | Destruction last |
| Week 12 | Drift round three (B5) on U1, U5, U7, U9. Then P4 on U5. Then K1 footstep and K4 on U5, U9 | B5 needs one unit of each variant at week 12, so the two unpotted units are destroyed only after it |
| Week 12 on | Last readings of F7 on the long-term boards, twelve weeks after they were started, and of Q1 after thirteen. Q2 follows on LB3 and LB4 (four weeks flat, then recharge). EVT report | - |

---

## 5. What a failure means

For each major test: what the repository has already reserved as a remedy, or "no remedy
defined". "Reserved" means the design package names the change. "Named, not adopted" means
the package mentions it and decided against it or left it open. Our own ideas are marked
PROPOSED and are not part of the design.

| Test | A failure looks like | Remedy already in the repository | Status |
|---|---|---|---|
| S1 seating on turf | Scatter above 5 mrad | The two modes that average seatings: the Precision Read (half-turn and re-read) and the Survey (`DESIGN_SPEC.md` section 2). In the simulation the Survey still equals a 0.5 % reader at 5.4 mrad. No hardware change is named | **No hardware remedy defined** |
| S4 bias on turf | The marker reads differently at 0 and 180 degrees on grass | The Precision Read cancels a fixed bias | Mode exists; no hardware remedy |
| A1 plate accuracy | Error above 1 mrad after calibration | A precision inclinometer chip (ST IIS2ICLX): "a documented option for a later revision" (`DESIGN_SPEC.md` section 3). Its pin map is unverified | Named, not adopted |
| B1 to B5 drift | Above 0.05 mrad/K or 0.3 mrad after a cycle | The test is itself the choice between the two base plates. For the potting: "low cure shrinkage and a chosen modulus" (`mechanical/README.md` section 12); a softer resin halves the reviewer's estimate | Reserved (choice of plate and resin). If both plates fail: **no remedy defined** |
| C1 to C3 distance | Scatter or bias above the limits | The stick-height channel helps beyond about 7 m; the dialled distance is the fallback; "10 % is enough for the line" | Fallback exists. For calibration drift: **no remedy defined** |
| O1 upper view | Dimming starts below 14.0 degrees | None. The risk is accepted in the specification (E17) because a low upper edge only delays stick-top ranging to about 8.4 m. The lens pupil data behind the figure is a release gate | **No remedy defined** |
| L1 light leak | Dark frames brighten | The README test compares "with and without the gaps beside the cubes masked" (section 9, test 5); the hood gasket is the designed barrier | Diagnosis named; **no design change reserved** |
| D0 line on the screen | The drawn line is turned against the cameras | The factory measures the rotation and the firmware turns the drawn line by the stored angle (E12, E22). The measuring fixture is not designed | **Reserved** in firmware (simulator only); fixture open |
| D1 aim on the green | Error above 1.5 times the simulation | Depends on the cause found by replay: seating (see S1); real greens rougher than assumed (Survey mode); golfer cannot copy the line (the "break in cups" display is already on the screen) | Partly: modes exist |
| GR0 to GR5 grain | Any of gates 0, 2, 3 fails | "Ship the prior-based estimate only and keep the optical hardware for data collection" (`grain-sensing.md` 2.3 and 2.4) | **Reserved** |
| L2 grain stray light | Sensor saturates in sun | None | **No remedy defined** |
| F1 read time | Above the limit | Fast clock during the read is already in. "An optimisation pass on the vision is still wanted" (`firmware/README.md` open issue 1) | Named, not done |
| F2, F3 read energy and peak current | Energy far above the estimate; reset or camera fault in the cold | None in the specification. The firmware notes still want "an optimisation pass on the vision" (shorter camera time), and the idle camera could be put to sleep between strips (`firmware/README.md` open issues 1 and 13). A cell with a known discharge rating is a gate item (G3) | Named, not done |
| F4 to F7 battery | Short standby or few reads; sleep current over 25 microamps | None in the specification beyond the limits themselves. The firmware notes name the parts that carry the always-on current. If the unconfirmed 2.8 microamps of the USB regulator's enable pin is not real, every sleep figure is that much lower | Named, not adopted |
| F8, Q1 ship mode | More than 5 microamps; a cell at 30 % below 3.0 V before 3 months (the model already says so: 12.9 microamps, 42 days) | Two remedies named in `firmware/README.md` "Ship mode (E13)": change the hardware (battery divider 1.95 microamps, regulator 1.6, enable pin 2.8 unconfirmed) or change the requirement. A higher shipping charge and a shorter recharge interval for stock follow from the arithmetic and are not in the repository (PROPOSED) | **Open decision**; NOT MET in the model |
| H2 polarised sunglasses | Screen goes dark at some headings | A quarter-wave film under the cover glass, an EVT trial at rev E (E9, E19) | **On trial** |
| J3, J5 charge temperature | Charging outside 0 to 45 C | Widen the firmware guard band (`firmware/README.md` open issue 5a) | Reserved (a constant) |
| J6 cases no firmware watches | The charger charges outside its own window, or the owner does not accept charging to 4.06 V between 45 and 60 C | The charger with its own temperature input is in (E1). Beyond it: none. The open-NTC1 case is covered by board test only | **Reserved** (E1) for the window; for the 45 C limit without firmware: **no remedy defined** |
| J7 sun soak | Cell or glue damaged by heat; a read taken above 60 C | The firmware refuses a read above 60 C (E13). Nothing protects the cell or the adhesives from the heat itself | Rule **in** (simulator only); for heat damage: **no remedy defined** |
| J9 cradle on a USB-C charger | No power, or the charger input below 4.45 V | The two 5.1 kilohm resistors and the fuse are in the specification and on the routed cradle (E6); the ideal-diode switch replaces the series diode (E25). Fuse data and switch wiring are PROVISIONAL | **Reserved** (in the design) |
| J10 charge end in the cradle | The charge never ends, or a docked marker is found well below full | Cradle sleep and the 6-hour limit (E32). The restart voltage is a firmware constant; the firmware notes leave its value to the owner (open issue 60) | **Reserved** (a constant) |
| W3, W4 rain and wet grass | Water inside | Adhesive choice and primer (open). A second barrier exists at the board edge. Conformal coating is recommended by the enclosure research and is not in the specification. No larger seal land is possible (0.4 mm; deviation D06) | **No design remedy defined**; the fallback is a weaker claim |
| W6, W7 dunk and immersion | Water inside | None. No immersion claim is made | Not a failure at EVT |
| W8 vent | Leaks below 50 kPa | None. "Vent part data unverified" | **No remedy defined** |
| K0, K1 footstep | Glass or structure fails | Production glass specified by strength (600 MPa ring-on-ring or more), and "0.2 mm more puck thickness above the LCD is the reserved remedy" (`DESIGN_SPEC.md` section 5, item 4) | **Reserved** for the glass. For yielding posts: **no remedy defined** |
| K3 drop | Crack, lost foot, shifted cameras, zero moved by more than 0.5 mrad | None. The requirement exists since E23; no design change is named for a failure | **No remedy defined** |
| K4 ball feet | Moves below 100 N | Re-potting from below is allowed until lamination (step 2). No design change | Process only |
| M1 to M3 latch | Cracks, creeps open, or releases below 12.4 N | None beyond the rules "PA12 only" and "print orientation locked". The calculation lists what it is sensitive to | **No remedy defined** |
| M4 pad wear | Gold worn through | "Selective hard gold in production" | **Reserved** |
| M5 wet docking | Corrosion, fuse trips | Resettable fuse (in). Switching VBUS in the cradle was considered and "not adopted" | Named, not adopted |
| P4 interrupted update | Unit will not start | The boot stub starts the built-in USB loader when the image is invalid (E34); factory recovery by the service pins. Never run | **Reserved** (never run) |
| Q2 flat cell | Will not recover | Charger on by default, working with no firmware (E1). "Charge before first use" on the packaging (`power.md` risk 4) | Reserved (charger, packaging text) |
| J8, N3, Q3 hot tests | A unit swells or fails and the shells beside it pass | None. The cell's storage temperature limit is an open gate (B15, G3) | **No remedy defined** |
| Potting level (assembly) | Surface proud or too deep | Per-unit volume correction; a ring 0.07 mm lower as the alternative (`mechanical/README.md` open issue 25) | Reserved |
| Cover glass at or above flush | Glass proud | The same reserved 0.2 mm of thickness | **Reserved** |

---

## 6. What this plan needs that does not exist yet

Each is a gap in firmware or tooling. Without them the test named cannot be run as written.

Status at rev E. "Exists on the simulator" means the firmware package contains it and its tests
pass on a PC; it has never run on a board (REPO: `firmware/README.md`, "Field log", "PC tool",
"Station tests that still cannot be run").

1. **A tilt logger.** Partly there. A setting writes a tilt record at every placement, with
   the cameras off if wanted. **Still missing:** a record at intervals while the marker lies
   untouched. In the chamber (B1 to B5) the marker must be lifted and replaced at each stop, or
   its tilt streamed over USB in the cradle, where the spring pins push on it and the charger
   warms it.
2. **A picture capture command.** Exists on the simulator (a capture command and a field
   command in the factory protocol). **Still missing:** a fixed exposure and a limit for the
   dark-frame light-leak test (L1).
3. **Grain values in the log.** In the read record. A live grain stream is in the PC tool.
4. **A PC program** that dumps and decodes the log, and the converter to the simulator's
   input record. Exists on the simulator (`firmware/tools/glctl`; section 3.3). Its serial
   transport has never been exercised.
5. **A fine time stamp.** In the read record (milliseconds since start-up, and stage times).
6. **A way to set a chosen state of charge** on a sealed unit (shipping, and the charge level
   of the hot tests). **Still missing.** The firmware notes say the PC must watch the voltage
   and stop the charge. Q1 does not need it: it runs on open boards, where a battery tester
   sets the level.
7. **Fixtures.** None is designed (REPO: `mechanical/README.md` section 12): the six-face
   calibration fixture, the seat plate for the base-face zero (A5), the display-rotation
   measurement (D0), and of this plan the chamber flat with a turntable, the camera target
   wall, the ramp with a laser pointer, the dummy markers, the shells.
8. **A stereo calibration procedure and its PC tool. Still missing.** C2 and C3 set limits of
   0.05 px, C3 speaks of "the first calibration" and the drop requirement of E23 of "its
   acceptance limit". The firmware can store calibration values; no procedure and no fit
   exist. Until they do every unit runs on nominal values (focal length 657 px, picture
   centred, cameras parallel). What the tests then mean:
   - C1 (scatter) is still valid. Scatter does not depend on calibration.
   - C2 (bias) measures the unit's built-in misalignment, not a calibration error. Report it
     in pixels for each unit. It is the number the calibration will have to remove. The
     0.05 px limit applies only once a calibration exists.
   - C3 and K3 can run as "change from the first measurement" instead of "from the first
     calibration".
   - C4 and O3 use the same distance and inherit the same bias.
9. **A temperature-fit tool.** Exists on the simulator: a command stores the temperature
   terms from at least 5 points over 30 K and refuses an ill-conditioned fit. B1 can be judged
   "after per-unit correction" once it has run on a unit.
10. **A linked application image and a PC-side updater. Missing.** P3 and P4 cannot be run
    without them.
11. **USB vendor and product IDs. None assigned** (release gate, E34). The firmware's release
    build refuses for that reason and for the placeholder regulatory text. P1 needs IDs of
    some kind.
12. **Board checks the firmware cannot do yet** (same README section): reading NTC1, the tilt
    sensor's self-test, the memory chip's identity, holding the camera supply on for a meter.
    F2 measures the camera current during a read instead.

---

## 7. Design observations raised while writing this plan

Revision 2 of this plan raised sixteen observations against rev D. Rev E answered most of them
in the specification. The table gives the standing of each; "answered" means the design package
now states it, not that anything was built or tested. New observations follow the table.

| # | Observation at rev D | Standing at rev E | Where |
|---|---|---|---|
| 1 | Calibration is done on the ball feet; use is on the grass. The two planes can differ by about 1.6 mrad | Answered: two stored zeros, base face and ball feet. Tests A5 and S4. The seat plate is not designed | E11, E18 |
| 2 | No battery-life requirement and no power budget | Answered in part: requirements for reads, standby and ship mode exist, all PROPOSED. The power model is the firmware's; `docs/POWER_BUDGET.md` lays it out. The cell's rated discharge current is still unknown | E23, E14 |
| 3 | Read time: the specification said "about three seconds", the firmware 4.1 to 4.8 s | Answered: the specification now takes the firmware's model, "about four to five seconds". The current build gives 4.15 to 4.84 s | E15 |
| 4 | Line direction: the simulation assumes 0.94 degree steps, the firmware draws to 0.05 degree | **Open.** The simulation has not been re-run | `sim/results/REPORT.md` section 4.2 |
| 5 | No drop requirement | Answered: 1.0 m, six attitudes, PROPOSED. Test K3 | E23 |
| 6 | No "too hot" rule for reading | Answered: no read above 60 C at the cell sensor. Test J7 | E13 |
| 7 | The log cannot support its own validation | Answered on the simulator; a tilt record at intervals is still missing | section 6 |
| 8 | No replay path from a field log into the simulator | Answered on the simulator: seven simulated reads replayed | section 3.3 |
| 9 | Grain amplifier headroom: about 3 microamps of photocurrent before it saturates; LED currents about 6 and 10 mA, not 20 | Accepted and written down. The feedback resistor is an ordinary 0402 part so that it can be lowered if test L2 shows saturation | E3; `DESIGN_SPEC.md` section 4 |
| 10 | Cradle electrical details missing | Answered: resistors, fuse, protection part written down and routed. Fuse data PROVISIONAL | E6, E25, E36 |
| 11 | No film for polarised sunglasses | On trial at EVT. Test H2 | E9, E19 |
| 12 | An interrupted update may leave a unit only the factory can revive | Answered in design: boot stub. Never run; no image, no updater. Tests P3, P4 | E34 |
| 13 | The simulation report is headed "hardware revision C" | **Open, and wider now:** the design is at rev E and the simulation still uses the rev C optics | `sim/results/REPORT.md` line 5 |
| 14 | The repository's hot tests are above the only cell limit it holds | **Open.** No cell data sheet. Section 2.9 keeps units with a real cell at 60 C or below | `mechanical/README.md` section 12, "Battery (B15)" |
| 15 | Shipping at 30 % charge with an always-on motion wake-up: empty in about a month | Answered in part: ship mode exists. **Its requirement is NOT MET in the model:** 12.9 microamps against 5, and 42 days from 30 % against 3 months. Tests F8, Q1 | E13, E23; `firmware/README.md` "Ship mode (E13)" |
| 16 | The upper-view guarantee and the factory gate measure different things | Answered: guarantee 14.0 degrees, gate bars at +13.0 and -13.0 degrees, both fully clear on a unit in the guaranteed case | E17 |

Observations new at rev E:

17. **The sleep-current limit has no known margin.** E14 allows 25 microamps at the pads. The
    model gives 20.68 without the display, and the display stays powered on the always-on
    supply when asleep and in ship mode. No figure is known for it. The limit holds only if
    the display draws less than 4.32 microamps. The model also uses typical values only: no
    maximum, no temperature. Test F4 measures the display's share. Files:
    `firmware/README.md` "Sleep and the supply model (rev E)"; `firmware/hal/host/gl_sim.h`.
18. **The standby requirement and the sleep-current limit fit together only on an assumption
    about the cell.** A board at the 25 microamp limit needs about 30 mAh above the
    low-battery symbol to last 45 days (our arithmetic, test F7). The listed capacity is
    43 mAh, unconfirmed; the research suspects about 34 mAh. Test F5 measures the share above
    3.5 V. Files: `DESIGN_SPEC.md` sections 4 and 6.
19. **The low-battery symbol is the end point of two requirements and is not in the power
    model.** E23 counts reads and standby "to the low-battery symbol". The model counts to
    empty. The threshold is 3.5 V in the firmware's provisional constants; how much charge
    lies above it is unknown until F5.
20. **A lit underside is outside the sleep limit by definition (E27) but inside real use.** A
    marker asleep face-up, or on a glass shelf, draws 28.9 microamps at the cell in the model,
    not 23.7. Standby then falls from 76 to 62 days on the listed capacity (our arithmetic:
    43 mAh at 28.88 microamps).
21. **The ship-mode requirement is not met by the design as modelled** (item 15). It is the
    one E23 requirement on which the package's own model says "no" before anything is built.
22. **The 0.03 degree of margin on the upward field cannot be checked by test O1.** It is
    smaller than any optical bench in this plan can resolve, and it rests on assumed lens
    data. The lens data is the check; O1 only finds units that are clearly short.
23. **The drop requirement refers to a stereo acceptance limit that does not exist** (section
    6, item 8).
24. **A marker left in its cradle is not kept full.** By the model the cell cycles down to
    79.3 % before it is recharged. The firmware notes leave the restart voltage to the owner.
    Test J10.
25. **Several firmware limits in the cradle are marked NOT MET in the firmware test log** and
    are owner decisions, not test failures of this plan: a silent USB host loses the marker
    until it is re-docked; the 45 C charge limit is not enforced when no firmware runs (the
    charger's own window to 60 C is); an open charger sensor removes every limit while no
    firmware runs. Tests J4, J6, J10 show them on a board. The log has 21 lines marked
    NOT MET in all; the others concern the solver and the vision code and are not power or
    safety items.

---

## 8. Sources for outside facts

Seen on 2026-11-11 as text returned by a web search. Vendor and regulator pages could not be
opened directly from this session, so "VERIFIED" means the search extract, not the full page.

| Ref | Source | Used for | Status |
|---|---|---|---|
| V1 | Transcat, JB Tools, Zoro and Higher Precision listings for the Digi-Pas DWL-8500XY. https://transcat.com/dwl8500xy-215881 ; https://www.transcat.com/media/pdf/DWL8500XY.pdf | A two-axis level with 1 arcsecond resolution and accuracy exists and is sold by US distributors at about $3,970 to $5,840 | VERIFIED as listings. Prices change; country of manufacture not found |
| V2 | Golf.com and Plugged In Golf reviews of "The Perfect Putter"; reseller listings. https://golf.com/instruction/putting/perfect-putter-golf-com-rerview/ ; https://pluggedingolf.com/the-perfect-putter-training-aid-review/ | A putting ramp of the Stimpmeter kind is sold for about $300 to $340 | VERIFIED as reviews and listings. Country of manufacture not found. Its repeatability is not stated anywhere seen: measure it |
| V3 | Wikipedia "IP code" as mirrored in the search results; test-lab summaries. https://www.wikipedia.org/wiki/IP67 | IPX7 means immersion at 1 m for 30 minutes | VERIFIED as a summary. The standard itself (IEC 60529) was not read. The splash level (IPX4) parameters were **not confirmed** |

Not found today: a putting robot that can be bought and shipped within the US; any published
figure for how repeatably a small puck seats on turf; the water entry pressure of the vent.

From memory, not checked today (PROVISIONAL): the "3 divided by n" rule for zero failures in n
trials is standard statistics; typical leak-test limits for small sealed electronics are of
the order of 0.1 to 0.5 cm3 per minute at tens of kPa, which is where the W1 starting point
comes from.
