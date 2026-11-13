# GreenLine GL-1: validation plan for the EVT build

Plan revision 2, 2026-11-11 (revised the same day after two independent reviews). Written
against `design/DESIGN_SPEC.md` rev D (EVT1), `design/master_params.yaml` rev D-EVT1,
`mechanical/README.md`, `sim/results/REPORT.md` and `firmware/README.md`.

**Read this first.** Nothing in this project has been built or tested. No board, printed part,
fixture or finished unit exists. Every "claimed value" below is a simulation result, a
calculation or an assumption, and the table says which. This plan says how each number will be
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
The seating test measures what really happens. It does not need to assume which part touches.
A consequence is listed in section 7, item 1.

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
| A2 | Tilt repeatability when re-seated on the plate | No number in the repository. `MANUFACTURING_PLAN.md` 6.2: a 10 micrometre grain under a foot is 0.3 to 0.4 mrad | none | CALC | Lift the unit and set it down on the same clean spot 30 times. One read each | All 10 units, 30 placements | Surface plate, lint-free wipes | PROPOSED: scatter at most 0.15 mrad per axis (1 sigma); no single reading more than 0.5 mrad from the mean |
| A3 | User zeroing on a hard surface that is not level | `firmware/README.md` "Tilt, range, grain, protocol": bias recovered to 0.1 mrad on synthetic data | 0.1 mrad | SIM (firmware test on a PC) | Zero the unit (menu "ZERO") on a plate tilted 10 mrad. Then check it on the level plate, 0 and 180 degree pair | All 10 units, 3 zeroings each | As A1 | PROPOSED: remaining bias at most 0.3 mrad per axis |
| A4 | Ball feet: height of each ball | `mechanical/README.md` step 2 | 0.10 +-0.02 mm, all three | TARGET | Height gauge or optical profiler on the underside, before lamination and again after the thermal cycle | All 10 units and all shells | Height gauge with 0.001 mm reading, surface plate | REPO: 0.10 +-0.02 mm. PROPOSED extra: the three balls of one unit equal within 0.02 mm (see section 7, item 1) |

Reference level example: Digi-Pas DWL-8500XY, 1 arcsecond resolution and accuracy, seen at US
distributors at about $3,970 to $5,840 (VERIFIED as listings [V1]; country of manufacture not
found). Any level of this class will do. A sine plate with gauge blocks needs no electronics
and is the better primary reference. Plate flatness figures are in `MANUFACTURING_PLAN.md` 6.2.

### 2.2 Seating and level on turf (the first question)

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| S0 | Seating scatter on turf, **before electronics exist** | `DESIGN_SPEC.md` section 2: "Measuring seating repeatability is the first task for a prototype" | 2 to 5 mrad per placement; simulation uses 2.5 mrad per axis | ASSUMED | Dummy marker: a printed tub and FR-4 base with three ball feet, loaded to the real mass and balance (12.25 g, CALC from `mechanical/README.md` section 2). Tilt is read by a small breakout board of the same level sensor on hair-thin wires, or by a mirror on top and a laser spot on a screen 5 m away (1 mrad of tilt moves the spot 10 mm). 20 placements on each of 10 spots | 2 dummies, 200 placements per green, 2 greens with different grass | Dummy markers, sensor breakout and laptop (or laser, mirror, screen, dusk light), spot markers | Same decision bands as S1. PROPOSED |
| S1 | Seating scatter on turf, real units | Same; `sim/results/REPORT.md` section 4.1 | 2.5 mrad per axis assumed. Break-even points in the simulation: 2.5 mrad (Quick Read equals the 0.5 % golfer), 5.4 mrad (Survey equals them), 7.4 mrad (Quick Read equals the 1 % golfer) | ASSUMED; SIM | At 10 marked spots per green: 20 placements each, same heading, lifted fully between placements. Scatter is computed inside each spot and pooled. Repeat on a dewy morning | U1, U2, U3, U7: 200 placements each per green; at least 2 greens (PROPOSED: one bentgrass, one bermudagrass) and one wet session | Units with logging, practice green, spot markers, log dump tool | PROPOSED decision bands, per axis, 1 sigma, upper 95 % confidence bound: **Green** at most 2.5 mrad. **Amber** 2.5 to 5 mrad: the Quick Read is behind a good reader; the product must lead with the Precision Read and Survey. **Red** above 5 mrad: no single-placement mode holds its simulated standing |
| S2 | Are two seatings on one spot independent? | `sim/results/REPORT.md` section 11 ("Precision Read when the two seatings are correlated") | Independent (correlation 0) | ASSUMED | From S1 plus half-turn pairs: 10 placements at 0 degrees and 10 at 180 degrees on each spot. Compare the scatter between spots with the scatter inside a spot | Same sessions as S1 | Same | Report the correlation. No pass limit. PROPOSED note: above 0.5 the Precision Read gains about half of what the simulation shows |
| S3 | Rare bad seatings (outliers) | `sim/results/REPORT.md` section 11 ("Seating outliers") | None in the main run; a sweep tried 10 % and 25 % of seatings with an extra 11 mrad | ASSUMED | Count placements in S1 that lie more than 3 sigma from their spot mean | S1 data (at least 1600 placements) | - | PROPOSED: at most 5 % of placements. More than 10 % costs about 1.4 points in the simulation |
| S4 | Bias on turf: does the marker read the same slope at 0 and at 180 degrees? | `sim/results/REPORT.md` section 13: device bias 1 mrad per axis; a 2.5 mrad bias costs 1.0 +- 1.4 points | 1 mrad | ASSUMED | From the half-turn pairs of S2: half the difference between the 0 and 180 degree means is the device's bias as it sits on grass | S2 data | - | PROPOSED: at most 1.0 mrad per axis, mean over 10 spots |
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
| O1 | Upper edge of the camera view | `master_params.yaml` `cameras.field_required_deg`; `mechanical/README.md` section 5 | 17.6 degrees required nominally. The model keeps the **full** light bundle clear up to 18.56 degrees on a nominal unit and up to 14.97 degrees at the tolerance limit (14.61 with the spigot play): hence "14.5 degrees guaranteed". The bundle clears the roof by 0.054 mm. Above that angle the picture dims slowly, it does not go dark: at +17.6 degrees a unit at the tolerance limit still passes 56 to 64 % of the light | CALC (ray trace on assumed lens data; the README says the lens data "is not published") | Marker on a flat, 2.000 m from an evenly lit vertical strip with marks every 0.5 degree from -20 to +20 degrees (14.5 degrees is 523 mm above the flat, 17.6 degrees is 640 mm). Plot the brightness along the strip. Find the **onset**: the lowest upward angle at which the picture is more than 5 % darker than at the mirrored downward angle (PROPOSED threshold). The lower half is the reference because the roof cuts only the upper bundle; on the units that matter (optics sitting high) the model keeps the lower bundle clear to about 18 degrees. Turn the strip end for end and repeat, to cancel uneven lighting. If a picture of the same board without its tub exists, use that as the reference instead | All 10 units, both cameras | Target wall with an even light strip, tape, raw-strip logging (level FIRST) | REPO: onset at 14.5 degrees or higher on every unit. The YAML figure is the angle up to which the full bundle is clear, so the limit applies to the onset, **not** to the half-brightness point. A unit at the tolerance limit still shows more than half brightness at 17.6 degrees, so a half-brightness test with a 14.5 degree limit would pass units far outside tolerance. Report the onset, the half-brightness angle, and how many units show no onset up to 17.6 degrees. The 5 % threshold must be tuned on the first units |
| O2 | Sideways and downward view | Same | +-26 degrees required. The model gives 25.60 degrees for the full bundle, limited by the 2 mm prism and the same on both sides in every tolerance case; 2.3 % of the assumed bundle is clipped at the field edge. 8 degrees down required; the model keeps it clear to 11.7 degrees even with the optics 0.2 mm low. The picture itself ends at about +-26 degrees (640 pixels at a focal length of 657 px) | CALC | Same strip turned sideways; marker raised on a block for the downward marks | All 10 | Same | PROPOSED: the left and the right edge of each picture are equally bright within 10 % (the model clips both sides alike, so a difference means a shifted prism or adhesive in the opening); the outermost marks inside the picture show on both sides; no onset (as in O1, with the upper half as the reference) down to 8 degrees. The predicted 2.3 % loss at the edge is too small to check without lens data: record the edge brightness against the centre, with no limit. A limit in "% of centre brightness" would mix clipping by the enclosure with the lens's own fall-off, which nobody knows |
| O3 | Distance from which the top of the stick is seen | `DESIGN_SPEC.md` sections 2 and 5 | From about 6.6 to 6.7 m on a nominal unit; about 8.1 m on a worst-case unit (2.13 m stick) | CALC | Walk the marker back from 5 m in 0.25 m steps until the log shows the stick top as valid. Measure the real stick | U1, U2, U7, U8 | Tape, flagstick of measured height | PROPOSED: at most 8.3 m for a 2.13 m stick (scale by stick height) |
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
| D0 | Does the drawn line point where the unit thinks it points? | `firmware/README.md` "Display" (line direction 0.05 degree RMS, 0.28 worst, on a PC model); `MANUFACTURING_PLAN.md` section 11, item 10 (the display glass can sit turned by up to about 1 degree; nothing calibrates it) | 0.05 degree (drawing only). The simulation assumes 0.94 degree steps (0.27 degree RMS) plus 0.5 degree for the golfer | SIM; CALC | Level floor, flagstick at 3 m, a taut string from the stick over the centre of the marker. Photograph the marker from straight above. Measure the angle between the drawn line and the string in the picture | All 10 units, 5 reads each | Camera on a boom, string, flagstick | PROPOSED: mean error per unit at most 5 mrad (0.3 degree, 1.5 cm at 3 m). There is no remedy today if a display is turned (section 5) |
| D1 | Quick Read: how far from the true aim point | `sim/results/REPORT.md` sections 1 and 3 | Median miss at the hole 2.3 cm at 1.5 m, 5.1 cm at 3 m, 9.2 cm at 4.5 m, 13.2 cm at 6 m, 23.6 cm at 9 m. Aiming straight at the flag: 6.9, 13.9, 24.0, 28.5, 47.7 cm | SIM (perfect stroke, 2.5 mrad seating, no grain) | Steps 1 to 7 above. Device error = device aim point minus true aim point | U1, U2, U7. PROPOSED: 30 putts at each of 1.5, 3, 4.5 and 6 m and 20 at 9 m, spread over at least 3 greens with slopes from 0.5 to 3 % | Ramp, 10 identical balls, Stimpmeter, tapes, ruler, hole cover, flagstick, level, phone camera, field sheets | PROPOSED, both must hold at each length: (a) median device error at most 1.5 times the simulated median: 3.5, 7.7, 13.8, 19.8, 35 cm; (b) median device error at most 0.6 times the "aim straight" error measured on the same putts (the simulation gives 0.33 to 0.50) |
| D2 | Precision Read and Survey | Same | Median miss, Precision: 1.8, 4.8, 8.2, 12.2 cm at 1.5 to 6 m. Survey with three placements: 1.9, 4.3, 6.8, 8.5 cm | SIM | Same putts, extra reads in step 3 | Same | Same | PROPOSED: no worse than the Quick Read on the same putts; report the gain. The simulation's gains are small (2 and 5 points), so 140 putts may not resolve them |
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
- `firmware/README.md` carries an estimate for rev D ("End to end", table "Time and charge of
  this read", and "Battery life under the supply model"; as that file stood late on
  2026-11-11). The firmware's PC simulator multiplies its simulated times by assumed currents.
  The file itself says that **every current is provisional**. Nothing is measured.

| Item | Rev D estimate (REPO: the firmware simulator's supply model) |
|---|---|
| Time the camera supply is on in one Quick Read | 2.4 s (2.2 to 2.8 s over the estimated range of computing speed). 3.0 to 3.4 s for a stick nearer than about 4 m or with several lines in view. 3.8 s if the fast clock fails. 1.56 s only if computing took no time |
| Current while it is on | 86 mA for the two camera cubes (about 120 mW each, unverified; both stay awake for the whole read) plus 9.5 mA for the processor at 160 MHz: about 96 mA, which is about 2.2 times the cell's capacity per hour |
| Charge of one read, from wake-up to result | 0.063 mAh (0.056 to 0.072; 0.095 if the fast clock fails). The cameras are 92 % of it |
| Charge of one whole cycle: read, 45 s of display, asleep again | 0.072 mAh (0.065 to 0.081; 0.104 if the fast clock fails; about 0.09 for a near stick) |
| Read cycles from the listed 43 mAh | 600 (533 to 665; 414 if the fast clock fails). This counts the whole listed capacity down to empty and no self-discharge |
| Asleep | 20.6 microamps: processor asleep 9, tilt sensor waiting for motion 5, memory 0.1, and 6.5 for the always-on regulator, the battery-voltage divider and the cell's protection circuit. That is 0.49 mAh a day: 87 days from a full cell, and 26 days from a cell at 30 % (our arithmetic on 12.9 mAh) |
| The same, seen from the battery pads | About 17.6 microamps (our arithmetic). A bench supply on the pads replaces the cell and its protection circuit, which is about 3 of the 6.5 microamps (regulator 1.6 and divider about 1.9 from `DESIGN_SPEC.md`) |

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| F1 | Time from "marker at rest" to "result on the screen" | `DESIGN_SPEC.md` section 1 ("about three seconds"); `firmware/README.md` "End to end" and "Run time" | 4.4 s on the PC simulator with computing charged at its estimated cost (4.1 to 4.8 s over the estimated range; 6.0 s if the fast clock fails; 3.45 s only if computing took no time). The firmware notes mark the specification's "about three seconds" as NOT MET | TARGET; SIM; CALC | Video at 60 frames per second: hands leave the marker, result appears. 30 reads each: flag at 3 m, flag at 9 m, a person in view, no flag | U1, U3, U7 | Phone camera | PROPOSED: median at most 6.5 s and 95 % of reads under 8 s with a flag in view. The 3 s design intent is reported as met or not met |
| F2 | Energy of one read | The rev D estimate above. (`docs/research/power.md` section 4 gives 0.011 mAh nominal and 0.039 mAh worst case: older architecture, not rev D) | 0.063 mAh from wake-up to result (0.056 to 0.072); 0.072 mAh for a whole cycle with its 45 s of display | CALC (simulator estimate on provisional currents, unmeasured) | Current against time during a read, with a bench supply in place of the cell. Record the time the camera supply is on and the current in each phase | 3 boards **before sealing** | Source-measure unit or current probe and oscilloscope | Report only at EVT. PROPOSED flag: above 0.10 mAh from wake-up to result with the stick at 6 m (the estimate for a read whose fast clock failed is 0.095 mAh), find the cause before F6 is run. A limit of 0.05 mAh, taken from the older figure, would fail a board that works as designed |
| F3 | Peak current and voltage dip in the cold | The rev D estimate above. (`power.md` section 4, finding 5, gives about 47 mA, 1.1 times the cell's capacity per hour, with the cameras at 10.7 mA: older architecture) | About 96 mA (cameras 86, processor 9.5), about 2.2 times the cell's capacity per hour. With the 1 to 5 ohm that `power.md` assumed for the pack, the dip is about 0.1 to 0.5 V, more in the cold. The cell's highest allowed discharge current is not known; data for the thin-cell family show about 90 % of capacity at 100 mA (`bom-verification-opto.md` 3.4) | CALC | Read at 0 and 5 C with the cell resting at 3.5 V (the firmware's low-battery threshold) and at 3.35 V (below it the firmware refuses a read). Watch the cell voltage, the always-on 2.8 V supply and the camera supply | 2 boards with a real cell, before sealing | Chamber, oscilloscope | PROPOSED: no reset and no camera fault; the always-on supply never below 2.7 V (the display's lower limit, provisional in the specification); the lowest cell voltage recorded. If the cell dips below 3.1 V from 3.5 V, the low-battery threshold has to rise. The cell's rated discharge current must come with the data sheet (gate G3 of `MANUFACTURING_PLAN.md`) |
| F4 | Sleep current | The rev D estimate above; `MANUFACTURING_PLAN.md` 4.5 test 18. (`power.md` section 2 gives 4.7 to 12 mAh per month, about 7 to 17 microamps, with the motion wake-up left on: older architecture, and that figure **includes** the cell's protection circuit) | 20.6 microamps in the firmware's model, protection circuit included; about 17.6 microamps at the pads, where the protection circuit is not seen. If the tilt sensor's waiting current is anywhere in the 3 to 10 microamps that `power.md` assumed, the pads show about 16 to 23 | CALC | Bench supply on the battery pads at 3.8 V, no VBUS, after the unit has gone to sleep. Repeat at 3.2 V, where the firmware's storage mode switches the motion wake-up off | All boards **before sealing** | Supply with a microamp range | PROPOSED: at most 25 microamps at 23 C and 3.8 V (the model's pad figure plus about 40 %, because every current in the model is provisional; a limit of 10 microamps would fail a board that works as designed). Report the 3.2 V value (about 12.6 microamps expected with the motion wake-up off). Each board's value goes on its record: F7 and Q1 are judged against it |
| F5 | Cell capacity | `DESIGN_SPEC.md` section 3 ("about 43 mAh ... still to be obtained"); `power.md` finding 8 suspects about 34 mAh | 43 mAh | VENDOR (listing, unconfirmed) | Discharge loose cells at 8.6 mA from 4.2 V to 3.0 V at 23 C | 5 loose cells | Battery tester | PROPOSED: at least 40 mAh |
| F6 | Reads per charge | No requirement in the specification | The rev D estimate above: 600 read cycles from the listed 43 mAh down to empty (533 to 665; 414 if the fast clock fails). To the low-battery symbol expect fewer: roughly 260 to 500 by our arithmetic, if 80 % of a 34 to 41 mAh cell lies above the symbol's 3.5 V (an assumption). (`power.md`: 0.7 to 3.0 mAh per 4.5-hour round, which is 50 to 60 reads a round: older architecture) | CALC | Fully charged unit on a rocking table that wakes it every 60 s until the low-battery warning | U3, U8 | Rocking table or motor cam, counter | Report. PROPOSED check: the count agrees within 30 % with the measured capacity (F5) divided by the measured energy of one read and its 45 s of display (F2). PROPOSED floor: at least 200 reads from full to the low-battery symbol, about three to four rounds. A limit of 600 reads would equal the model's figure for the whole listed capacity, with no margin for the low-battery threshold, a smaller real capacity or near sticks. The owner should set the real requirement |
| F7 | Standby time | No requirement in the specification | 87 days from the listed 43 mAh in the firmware's model (20.6 microamps, no self-discharge counted). About 2.6 months by our arithmetic with 41 mAh usable and the 2 % a month of self-discharge that `power.md` used | CALC | Charge fully, leave at rest at 23 C. Every two weeks read the cell voltage at the cell pads with a high-impedance voltmeter. At the end measure what capacity is left | Long-term boards LB1 and LB2 (section 4.1), 12 weeks, then extrapolate. Not sealed units: no unit can be left alone for 12 weeks (U5 and U9, the only candidates, are needed for the drift checks and are destroyed in week 12) | Voltmeter, battery tester | PROPOSED: at least 8 weeks from full to the storage threshold of 3.25 V, by extrapolation. This agrees with F4: a board at the F4 limit of 25 microamps lasts about 8 weeks by the same arithmetic, so a limit of 3 months would contradict F4. Also report the drain beyond the board's own F4 value: it is the protection circuit plus self-discharge, about 4 microamps if the assumptions hold |

### 2.8 Display in sunlight

| ID | What is checked | Source | Claimed or target value | Kind | Test | Units, sample | Equipment | Pass limit |
|---|---|---|---|---|---|---|---|---|
| H1 | Can a standing golfer read it in full sun? | `DESIGN_SPEC.md` section 3 ("Sunlight readable"), 22 mm window | No number | VENDOR class claim | Marker on turf in direct sun. Five observers standing (eye about 1.6 m above it) call out the distance, the break text and the side of the line. 20 trials each, with the sun in front, behind and at the side | U1, U7; 5 observers x 20 trials x 3 sun positions | Lux meter | PROPOSED: at least 95 % correct at 80,000 lux or more; also at 1,000 lux (shade) and 50 lux (dusk) |
| H2 | Polarised sunglasses | `docs/research/display.md` section 2, item 4: a quarter-wave film is "required, not optional, if polarised sunglasses are in scope". The rev D stack has no such film | - | - | H1 repeated with polarised sunglasses, marker turned to 0, 45 and 90 degrees | Same | Polarised sunglasses | PROPOSED: readable at every heading. If not: a recorded limitation (section 5) |
| H3 | Fogging under the glass | `mechanical/README.md` section 9, test 7 | - | - | Soak warm and humid (40 C, 90 %, 24 h), then put a cold plate (5 C) on the glass | U4, U8 | Humidity chamber, cold plate | PROPOSED: no mist visible in the window after 60 s |

### 2.9 Charging, temperature limits and the cell temperature cut-offs

NTC means the small temperature sensor glued beside the cell. The charger starts by itself
whenever 5 V is present; the firmware can only stop it (REPO: `DESIGN_SPEC.md` section 4).

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
| J1 | Charge current and end voltage | `DESIGN_SPEC.md` section 4 ("Charger") | 20 mA; 4.20 V end voltage (charger option in `bom-verification-ics.md`) | TARGET | Meter in the cell line on a board; voltmeter at the end of charge | 3 boards before sealing; then charge time on U3, U8 | Meters, test cell | PROPOSED: 20 mA +-10 %; 4.20 V +-1 %; full charge from empty within 3.5 h |
| J2 | Charging starts with a dead processor | Same: "charging is ON BY DEFAULT ... a cell at its protection cut-off must be rechargeable" | - | TARGET | Hold reset low, apply 5 V. Then repeat with a cell drained to its cut-off | 3 boards; then the long-term boards LB3 and LB4 when their cells are at the cut-off (Q2) | Meter | REPO: charge current flows in both cases |
| J3 | Charging stops outside the allowed temperature | `DESIGN_SPEC.md` section 4 (0 to 45 C); `firmware/README.md` "Charger and cell temperature" | Firmware stops below 1.5 C and above 43.5 C; resumes above 3.5 C and below 41.5 C; checks every 5 s | TARGET; SIM | Unit in its cradle in the chamber. Ramp -5 to 50 C and back at 0.5 K per minute. Log charge current and a reference thermometer taped to the marker | U4, U8; on 2 boards with a thermocouple on the cell itself | Chamber, current logger, thermocouple | REPO: no charging with the cell below 0 C or above 45 C. PROPOSED: stop and resume points within +-1.5 K of the firmware's values; charging stops within 10 s of a sudden crossing |
| J4 | Sensor faults | `firmware/README.md`: open, shorted or stuck sensor stops the charge and shows `TEMP SENSOR` | - | SIM | Open, short and tie the sensor line on a board | 2 boards before sealing | Jumpers | REPO: charge stops in each case |
| J5 | Is the sensor at the cell's temperature? | `firmware/README.md` open issue 5a: the 1.5 K guard band "does not cover" a difference between the cell and the sensor | Unknown | - | Thermocouple on the cell centre against the firmware's reading, during charging and in sun | 2 boards before sealing (open tub) | Thermocouples | PROPOSED: difference at most 2 K. If more, the guard band must grow |
| J6 | The two known gaps | `firmware/README.md`: nothing watches the cell while the built-in USB loader runs; a hung firmware is unwatched for up to 33 s. Both marked NOT MET | - | SIM | Show both on a board at 50 C. A supply that can absorb current stands in for the cell: no real cell is charged at 50 C | 1 board | Chamber, sink supply | Expected to fail. The record feeds release gate G6 of `MANUFACTURING_PLAN.md` |
| J7 | Sun soak | `docs/research/enclosure-manufacturing.md` section 2 (reviewer's energy balance): 55 to 77 C in a light breeze, 85 to 92 C in still air on an insulating surface. Cell family limits (`bom-verification-opto.md` 3.4): discharge up to 60 C | 55 to 92 C | CALC | Two hours at midday on dry turf and on a black insulating board, air at 30 C or more. A read every 10 minutes records the internal temperature in the log. Hot-test rules above: watch the surface thermocouple and end the run if it passes 60 C before the cell data sheet is in hand | U2, U7 | Thermocouple on the surface, weather record | PROPOSED: unit works afterwards; zero moves by at most 0.3 mrad; glass still below flush; no swelling; internal peak recorded. Note: the firmware has no "too hot to read" rule (section 7, item 6) |
| J8 | Hot and cold storage | `mechanical/README.md` section 9 (70 C loads) | - | - | 24 h hot and 24 h at -20 C, unpowered, at about half charge, then 4 h at room temperature. Hot part: 60 C for units with a cell; 70 C only when the cell data sheet allows it (gate G3). Two shells with a dummy cell take 70 C in any case (hot-test rules above) | U4, U8; 2 shells with a dummy cell | Chamber, fire-safe tray | PROPOSED: works; zero within 0.3 mrad; leak test passes; no swelling |
| J9 | Cradle on different USB sources | `mechanical/README.md` section 2, row 22 (resettable fuse); `power.md` section 2 names two 5.1 kilohm resistors that the specification does not list | 5 V only | TARGET | Cradle on: a PC port, a plain 5 V charger with an A-to-C cable, and a USB-C charger with a C-to-C cable. Then short VBUS to ground at the pins for 10 minutes | 3 cradles | Three sources, meter, thermocouple | PROPOSED: 5 V appears on every source (a C-to-C charger gives no power unless the two resistors are fitted); never more than 5.5 V; under a short the fuse limits the current, nothing exceeds 60 C, and it recovers |

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
| K0 | **The step-proof test (for DVT, production glass)** | `mechanical/README.md` section 12, test item 2 and open issues 3 to 5 | 800 N on a 20 mm indenter, on the glass and on the roof, on turf and on a hard floor, at 23 and 60 C, display powered. Estimates: about 400 MPa in a 1 mm crystal; 38 MPa under the post feet against 48 MPa yield for PA12 | TARGET; CALC | Eight conditions (2 places x 2 supports x 2 temperatures). 800 N held 5 s, ten times per condition. "Turf" is real turf or a 20 mm rubber pad; "hard floor" is a steel plate. Indenter with a 2 mm rubber face | DVT: at least 5 units per condition, glass specified at 600 MPa ring-on-ring or more (REPO) | Test press with a load cell, oven | PROPOSED: no crack; display undamaged; W1 passes; ball heights still 0.10 +-0.02 mm; after the user's re-zeroing the zero is within 0.3 mrad (REPO: a hard-floor step "requires re-zeroing in any case"); one further press to 1200 N without a crack |
| K1 | EVT footstep on the roof and structure | Same | Same loads | Same | K0 on the roof beside the glass, and on shells whose crystal is replaced by a steel disc, so that posts, board and base are loaded | 4 shells; then U6, U10 (at 60 C, weeks 10 to 12) and U5, U9 (at 23 C, week 12, after the last drift check), each as its last test | Same | Same limits, glass excluded. Units are treated as destroyed |
| K2 | What the EVT crystal really takes | Reviewer's estimate | 100 to 200 N | CALC | Ramp the load on the glass until it breaks | 3 shells | Same | Report only |
| K3 | Drop | **No requirement anywhere in the repository** | - | - | Free fall of 1.0 m onto paving, once on each of six attitudes: glass down, base down, visor flat, rear edge, left, right. Then 1.5 m, same six | U2, U7 (after their field work); 3 shells first | Drop guide, paving slab | PROPOSED after the six 1.0 m drops: works; no crack; zero moved by at most 1.0 mrad before and 0.3 mrad after re-zeroing; distance at 6 m changed by at most 0.1 px (4.6 %); W1 passes; three ball feet present. The 1.5 m drops are report-only |
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
| P1 | The PC sees the marker | `DESIGN_SPEC.md` section 3 (USB through the cradle; no crystal: PROVISIONAL there) | - | TARGET | Dock 50 times on each of three kinds of PC | All 10 units, 3 PCs | PCs with Windows, macOS, Linux | PROPOSED: recognised within 5 s every time |
| P2 | Data link | `firmware/README.md` "Protocol" (tested on a PC only) | Every corrupted frame rejected | SIM | 10,000 echo frames; a full dump of a filled log while the marker is rocked in the cradle | U1, U7 | PC tool (section 6, item 4) | PROPOSED: no undetected error; dump identical twice |
| P3 | Firmware update | `firmware/README.md` "What is not done": only the processor's built-in USB loader; no check of the new image; no way back without a PC or a power cycle | - | - | 20 updates in a row. Calibration read back before and after | All 10 units | PC update tool | PROPOSED: 20 of 20 succeed; calibration unchanged (REPO: it is stored outside the processor) |
| P4 | Interrupted update | Same | - | - | Lift the marker out of the cradle during the update, 10 times | U5 only, in week 12 after its last drift check (it may need the factory fixture to recover) | Factory fixture with 7 pins | Exploratory. PROPOSED requirement for DVT: a unit can always be recovered through the 4-pin consumer cradle. Today no remedy exists (section 5) |
| Q1 | Shelf life from the shipping charge | `power.md` section 4, finding 2, read with the motion wake-up **on**, as the firmware leaves it (`firmware/README.md`: asleep, the wake-up stays on; it is switched off only below 3.25 V) | About 26 days from 30 % charge by the firmware's supply model (12.9 mAh at 0.49 mAh a day; section 2.7). The older research gives about 1 to 2.3 months with the wake-up on (our arithmetic on its numbers: 12.9 mAh against 5.6 to 12.9 mAh a month). Its 2.3 to 3.8 months assume **no** wake-up source | CALC | Two boards with cells, set to about 30 % charge with the battery tester (70 % of the measured capacity taken out), 23 C, cell voltage every two weeks | Long-term boards LB3 and LB4 (section 4.1), 12 weeks | Battery tester, voltmeter | Report only at EVT: the time to 3.25 V and to the cut-off, and the drain against the board's F4 value. A fixed limit would contradict F4: a board at the F4 limit of 25 microamps uses about 21 mAh a month with the protection circuit and self-discharge, more than the 12.9 mAh that a cell at 30 % holds. The test feeds two decisions: whether a ship mode is needed (`COMPLIANCE.md` row 12) and at what charge to ship |
| Q2 | Recovery of a flat cell | `DESIGN_SPEC.md` section 4 (charger on by default for this case) | - | TARGET | Drain to the cut-off, leave 4 weeks, then apply 5 V through the pin nest of the bring-up station | LB3 and LB4 after Q1 (drained the rest of the way with a load) | Battery tester | PROPOSED: charges again without help; capacity at least 90 % of the first measurement |
| Q3 | Hot storage at full charge | `master_params.yaml` `battery.swell_allowance` 0.4 mm; `mechanical/README.md` open issue 13 (0.15 mm left above a swollen cell) | 0.4 mm | TARGET | 10 days at 60 C, fully charged. 60 C is the cell family's discharge limit, not a known storage limit: run this only when the cell data sheet (gate G3) allows 60 C storage at full charge, or at the data-sheet limit if that is lower. Swelling check every two days (hot-test rules, section 2.9) | U6, U10 | Oven, fire-safe tray | PROPOSED: glass still below flush; display unmarked; capacity loss at most 20 % |
| Q4 | Swollen cell | `mechanical/README.md` section 9, test 10 | - | - | A 2.4 mm dummy cell in a shell, 25 kPa quench, display powered | 2 shells with displays | - | PROPOSED: display unmarked |
| N3 | Long thermal cycling of sealed units | `mechanical/README.md` section 9, test 9 | 100 cycles of -10 to 70 C; then leak test, display position, tilt offset | TARGET | As stated, unpowered, at about half charge. The README asks for 70 C on complete units. Units with a real cell go to 70 C only when the cell data sheet allows that storage temperature (gate G3). Until then their upper temperature is 60 C, recorded as a deviation from the README's test, and two shells with a dummy cell take the full -10 to 70 C (hot-test rules, section 2.9) | U4, U6, U8, U10; 2 shells with a dummy cell | Chamber (about 9 days), fire-safe tray | PROPOSED: W1 passes; display still centred; zero moved by at most 0.5 mrad before re-zeroing; ball heights in tolerance; no swelling; C3 passes on U4 and U8 |
| R1 | Radio emissions pre-scan | `docs/COMPLIANCE.md` row 2 | - | - | A quick scan at a test lab: marker reading in a loop, and marker in the cradle talking to a PC | U3 with a consumer cradle | Lab | Report against the Class B limits. Not a formal test at EVT |

---

## 3. Checking the simulator itself

The simulation is the only source of performance figures today. It is honest about what it
assumed (`sim/results/REPORT.md` section 13). EVT must replace those assumptions with
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

REPO: `firmware/core/gl_log.h`, `firmware/app/gl_app.c`, `firmware/README.md` "Storage".

- A ring log on the 8 MB memory chip: 2044 blocks of 4 kB. Old records are overwritten when
  it is full.
- **One 72-byte record per solved read:** clock time (1 s steps), read number, flags (stick
  found, base visible, top visible, distance entered by hand, Precision, Survey, grain valid,
  sun in picture), Survey placement number, temperature, battery voltage, slope in x and y,
  bearing, disparity and its claimed uncertainty, elevation of the base and of the top of the
  stick, distance and its uncertainty, learned stick height, displayed aim direction, launch
  speed, aim offset at the hole, Stimp entered, confidence, solver status, and five picture
  quality figures.
- **One event after each read record:** where the aim came from, solver status, flags (fit
  converged, base hidden, flag missing, distance missing, poor horizon), method, read tier,
  ambiguous, line drawn, number of trial rolls.
- **Other events:** start-up, faults, zeroing, calibrations, storage mode, charger decisions
  with the cell temperature.
- **Raw pictures, if switched on:** strips of 96 x 480 pixels in records of 978 bytes. Level
  FIRST stores the first left and right strip of a read (96 records, about 94 kB, and adds
  2.6 s to the read). Level ALL stores 1600 records (1.6 MB) and keeps the cameras on for
  about 41 s: a bench mode.
- **Capacity (our arithmetic):** tens of thousands of reads with no pictures; about 85 reads
  at level FIRST; about 5 reads at level ALL. In the field with level FIRST the log must be
  dumped at least once a day.
- **Getting it out:** the commands LOG_INFO, LOG_READ and LOG_ERASE over USB, in the cradle.
  No PC program for this exists yet.

### 3.3 Capture and replay (PROPOSED: none of this exists yet)

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
   (`sim/greenline_sim/measurements.py`) and nothing else. A small program must turn each log
   record into one. It does not exist.
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

What the log does **not** hold, and the replay needs (see also section 6):

| Missing from the 72-byte record | Needed for |
|---|---|
| The grain reading (only a "valid" flag is stored) | Gates GR0 to GR5 |
| The turf-horizon profile | Replay of method B2 |
| The two separate tilt readings of a Precision Read | S2 from field data |
| The settings in force (PAST distance, method) | Exact replay |
| The fit record and the step count (REPO: "still reach neither the log nor the USB protocol") | Diagnosing a bad read |
| A time stamp finer than 1 s | F1 from the log |

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
full charge (F7); LB3 and LB4 shelf life from 30 % charge (Q1), then flat-cell recovery (Q2 and
the second half of J2). Reasons: a sealed unit cannot do these tests and the others it is
booked for; on an open board the cell voltage can be read at the cell pads, and a battery
tester can set the charge level, which no command can do on a sealed unit (section 6, item 6).
`docs/SOURCING.md` section 10.5 prices all the hardware of this section.

### 4.2 Unit by test

`X` = test is run on this unit. `(X)` = only if the unit is still alive and the shells
passed. `D` = this test ends the unit. `-` = not run.

| Test (section 2 ID) | U1 | U2 | U3 | U4 | U5 | U6 | U7 | U8 | U9 | U10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Plate level A1 to A4 | X | X | X | X | X | X | X | X | X | X |
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
| Reads per charge F6 | - | - | X | - | - | - | - | X | - | - |
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

Not on the ten units: S0 (dummies); F2 to F5, J1, J2, J4 to J6 (boards before sealing, loose
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
| Board bring-up (before sealing) | F2, F3, F4, J1, J2, J4, J5, J6. Solder cells to the long-term boards LB1 to LB4 and start F7 and Q1 on them | Cannot be measured after the cell is soldered and the unit is sealed. The 12-week clocks start as early as possible |
| Week 0 | Start the cradle creep test M2 (it runs 1000 h, six weeks). Start M1 | Longest clock in the plan |
| Weeks 1 to 2 | Bench, all ten units: A1 to A4, O1, O2, L1, D0, P1, P3. Drift round one: B1 to B4. Distance baseline C1 to C5 | Nothing goes to the grass uncalibrated or unchecked |
| Week 3 | Turf seating S1 to S6 | **Decision point 1.** Green or amber: go on. Red: stop field aim tests, review with the owner (section 5) |
| Weeks 3 to 6 | Field: D1 to D7, C6, C7, O3, grain data GR0 to GR4, L2, H1, H2, F1. Log dumps daily. Replay (section 3.3) as data arrives | **Decision point 2** at the end: does the measured aim error match the re-run simulation? |
| Weeks 5 to 7 | Shell tests: W2, K1, K2, K3, K4, W6, W7, Q4 | Shells first. Their results decide which `(X)` tests are worth a real unit |
| Week 6 | Drift round two (B5) on U1, U5, U7, U9. Cradle M1 finished, M3 | "Some weeks after cure" |
| Weeks 6 to 8 | Gentle bench on units: F6, J3, J7, J8, J9, H3, W3, W4, M5, P2 | Field units are free now |
| Weeks 7 to 9 | N3 (100 cycles, about nine days in the chamber), then K5, C3, W1. Q3 (only if the cell data sheet allows it) | Ageing before the hard water tests |
| Weeks 9 to 10 | W5, W6, W7 on units. K3 drop on U2, U7 | Units that may die |
| Weeks 10 to 12 | K1 footstep and K4 on U6, U10. W11 sections of U4, U8 | Destruction last |
| Week 12 | Drift round three (B5) on U1, U5, U7, U9. Then P4 on U5. Then K1 footstep and K4 on U5, U9 | B5 needs one unit of each variant at week 12, so the two unpotted units are destroyed only after it |
| Week 12 on | Last readings of F7 and Q1 on the long-term boards, twelve weeks after they were started. Q2 follows on LB3 and LB4 (four weeks flat, then recharge). EVT report | - |

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
| O1 upper view | Dimming starts below 14.5 degrees | None. The risk was accepted in rev D because a low upper edge only delays stick-top ranging to about 8.1 m (`mechanical/README.md` open issue 1) | **No remedy defined** |
| L1 light leak | Dark frames brighten | The README test compares "with and without the gaps beside the cubes masked" (section 9, test 5); the hood gasket is the designed barrier | Diagnosis named; **no design change reserved** |
| D0 line on the screen | The drawn line is turned against the cameras | None. `firmware/core/gl_cal.h` has no field for it (`MANUFACTURING_PLAN.md` section 11, item 10) | **No remedy defined** |
| D1 aim on the green | Error above 1.5 times the simulation | Depends on the cause found by replay: seating (see S1); real greens rougher than assumed (Survey mode); golfer cannot copy the line (the "break in cups" display is already on the screen) | Partly: modes exist |
| GR0 to GR5 grain | Any of gates 0, 2, 3 fails | "Ship the prior-based estimate only and keep the optical hardware for data collection" (`grain-sensing.md` 2.3 and 2.4) | **Reserved** |
| L2 grain stray light | Sensor saturates in sun | None | **No remedy defined** |
| F1 read time | Above the limit | Fast clock during the read is already in. "An optimisation pass on the vision is still wanted" (`firmware/README.md` open issue 1) | Named, not done |
| F2, F3 read energy and peak current | Energy far above the estimate; reset or camera fault in the cold | None in the specification. The firmware notes still want "an optimisation pass on the vision" (shorter camera time), and the idle camera could be put to sleep between strips (`firmware/README.md` open issues 1 and 13). A cell with a known discharge rating is a gate item (G3) | Named, not done |
| F4 to F7 battery | Short standby or few reads | None in the specification. The power research asked for a wake-up source under 1 microamp and a low-drain protection circuit; neither was adopted | Named, not adopted |
| H2 polarised sunglasses | Screen goes dark at some headings | A quarter-wave film over the display (`display.md` section 2, item 4). Not in the rev D stack | Named, not adopted |
| J3, J5 charge temperature | Charging outside 0 to 45 C | Widen the firmware guard band (`firmware/README.md` open issue 5a) | Reserved (a constant) |
| J6 charger unwatched | As expected | "A charger with its own NTC input, or a comparator on the NTC" (`firmware/README.md` open issue 2) | Named, not adopted |
| J7 sun soak | Cell or glue damaged by heat | None. No over-temperature rule for reading exists | **No remedy defined** |
| J9 cradle on a USB-C charger | No power | Two 5.1 kilohm resistors (named in `power.md`; missing from the specification) | Named, not in the spec |
| W3, W4 rain and wet grass | Water inside | Adhesive choice and primer (open). A second barrier exists at the board edge. Conformal coating is recommended by the enclosure research and is not in the specification. No larger seal land is possible (0.4 mm; deviation D06) | **No design remedy defined**; the fallback is a weaker claim |
| W6, W7 dunk and immersion | Water inside | None. No immersion claim is made | Not a failure at EVT |
| W8 vent | Leaks below 50 kPa | None. "Vent part data unverified" | **No remedy defined** |
| K0, K1 footstep | Glass or structure fails | Production glass specified by strength (600 MPa ring-on-ring or more), and "0.2 mm more puck thickness above the LCD is the reserved remedy" (`DESIGN_SPEC.md` section 5, item 4) | **Reserved** for the glass. For yielding posts: **no remedy defined** |
| K3 drop | Crack, lost foot, shifted cameras | None. The repository has no drop requirement | **No remedy defined** |
| K4 ball feet | Moves below 100 N | Re-potting from below is allowed until lamination (step 2). No design change | Process only |
| M1 to M3 latch | Cracks, creeps open, or releases below 12.4 N | None beyond the rules "PA12 only" and "print orientation locked". The calculation lists what it is sensitive to | **No remedy defined** |
| M4 pad wear | Gold worn through | "Selective hard gold in production" | **Reserved** |
| M5 wet docking | Corrosion, fuse trips | Resettable fuse (in). Switching VBUS in the cradle was considered and "not adopted" | Named, not adopted |
| P4 interrupted update | Unit will not start | None: "no bootloader of our own, no image check" | **No remedy defined** |
| Q1, Q2 storage | Flat on arrival, or will not recover | Charger on by default (in). "Charge before first use" on the packaging (`power.md` risk 4). A ship mode that keeps the motion wake-up off until first docking is PROPOSED in `COMPLIANCE.md` row 12; it is not in the repository | Reserved (charger, packaging text). Ship mode: PROPOSED only |
| J8, N3, Q3 hot tests | A unit swells or fails and the shells beside it pass | None. The cell's storage temperature limit is an open gate (B15, G3) | **No remedy defined** |
| Potting level (assembly) | Surface proud or too deep | Per-unit volume correction; a ring 0.07 mm lower as the alternative (`mechanical/README.md` open issue 25) | Reserved |
| Cover glass at or above flush | Glass proud | The same reserved 0.2 mm of thickness | **Reserved** |

---

## 6. What this plan needs that does not exist yet

Each is a gap in firmware or tooling. Without them the test named cannot be run as written.

1. **A tilt logger.** Tilt can be read out only over USB, and USB exists only in the cradle,
   where spring pins push on the marker and the charger warms it. The drift tests (B1 to B5)
   and the turf tests (S1 to S6) need tilt and temperature written to the log on demand or at
   intervals, with the cameras off. Today the only way is a full read, which is logged only
   when it is solved (so a distance must be dialled in first when no flag is in view). REPO:
   `firmware/README.md` "USB", `firmware/app/gl_app.c` function `log_read_`.
2. **A picture capture command.** O1, O2 and L1 need pictures. The only path today is the
   raw-strip log (`MANUFACTURING_PLAN.md` 4.4 and gate G12).
3. **Grain values in the log.** Only a flag is stored (`firmware/core/gl_log.h`). The grain
   stream works over USB only, which is useless on a green.
4. **A PC program** that dumps and decodes the log, and the converter to the simulator's
   input record (section 3.3).
5. **A fine time stamp** in the read record, or F1 stays a video test.
6. **A way to set a chosen state of charge** on a sealed unit (shipping, and the charge level
   of the hot tests; `MANUFACTURING_PLAN.md` gap 26). Q1 no longer needs it: it runs on open
   boards, where a battery tester sets the level.
7. **Fixtures:** the chamber flat with a turntable, the camera target wall, the ramp with a
   laser pointer, the dummy markers, the shells.
8. **A stereo calibration procedure and its PC tool.** C2 and C3 set limits of 0.05 px and C3
   speaks of "the first calibration". No such calibration can be done today. No procedure is
   defined; no command captures a picture; `CAM_HORIZON` answers "unsupported"; the camera
   numbers can only be written by a PC tool, and none exists (REPO: `MANUFACTURING_PLAN.md`
   6.3 and 6.9; `firmware/README.md` "What is not done"). Until it exists every unit runs on
   nominal values (focal length 657 px, picture centred, cameras parallel). What the tests
   then mean:
   - C1 (scatter) is still valid. Scatter does not depend on calibration.
   - C2 (bias) measures the unit's built-in misalignment, not a calibration error. Report it
     in pixels for each unit. It is the number the calibration will have to remove. The
     0.05 px limit applies only once a calibration exists.
   - C3 can run as "change from the first measurement" instead of "from the first calibration".
   - C4 and O3 use the same distance and inherit the same bias.
9. **A temperature-fit tool.** B1 judges the drift "after per-unit correction". The correction
   numbers can be written to a unit and a fitting routine exists in the firmware's core code,
   but nothing calls it and no PC tool computes the fit (REPO: `MANUFACTURING_PLAN.md` 6.2
   step C and 6.9 item 3). Until it exists B1 reports the raw drift. The fit can be done by
   hand in a spreadsheet from the logged points of the first run, and judged on the second.

---

## 7. Design observations raised while writing this plan

Things in the design package that look wrong, missing or inconsistent. Items already listed
in `MANUFACTURING_PLAN.md` section 11 are not repeated unless a test depends on them.

1. **Calibration is done on the ball feet; use is on the grass.** `DESIGN_SPEC.md` section 5
   says the rim relief means "the three ball feet are always the seat". That holds on a hard
   plate. On turf the balls stand only 0.10 mm proud, so the base plate rests on the grass.
   The plane of the three balls can be tilted against the base plate by the ball height
   tolerance: +-0.02 mm over a 24.5 mm triangle is up to about 1.6 mrad in the worst case
   (our arithmetic). Factory and user zeroing both stand on the balls, so neither removes
   this. Only the Precision Read cancels it. It is in no error budget. Tests A4 and S4
   measure it. Files: `design/DESIGN_SPEC.md` sections 2 and 5; `mechanical/README.md` step 2.
2. **No battery-life requirement, and no power budget in the specification.**
   `DESIGN_SPEC.md` section 3 gives the cell and the regulators but no number for reads per
   charge or standby. `docs/research/power.md` was computed for an older architecture (a
   Bluetooth module, cameras at about 10.7 mA, a 47 mA peak). The only rev D figures are an
   estimate inside `firmware/README.md` (the simulator's supply model, every current
   provisional): about 96 mA during a read, which is twice that peak and about 2.2 times the
   cell's capacity per hour, on a cell whose rated discharge current nobody has seen; 0.063
   mAh per read against the older 0.011 to 0.039; 20.6 microamps asleep. The research also warned that
   with the motion wake-up left on between rounds, ten rounds in ten weeks could in the worst
   case need more than the cell holds; the firmware leaves it on. The specification should
   adopt a power budget and a battery-life requirement, and the cell's discharge rating
   should join the battery release gate.
3. **Read time: the specification and the firmware disagree.** `DESIGN_SPEC.md` section 1:
   "about three seconds". `firmware/README.md` "Run time" and open issue 1 (as the file stood
   late on 2026-11-11): 4.1 to 4.8 s on the simulator with computing charged at its estimated
   cost, marked NOT MET there, and unverified on hardware.
4. **Line direction: the simulator and the firmware disagree.** `sim/results/REPORT.md`
   section 4.2 says the 1-bit screen can draw the line only in 0.94 degree steps (0.27 degree
   RMS). `firmware/README.md` "Display" measures 0.05 degree RMS with dithered edges. One of
   the two is out of date.
5. **No drop requirement** in any file.
6. **No "too hot" rule for reading.** The firmware gates charging by temperature only. The
   cell family's discharge limit is 60 C and the enclosure research estimates 55 to 92 C for
   a black puck in the sun. Files: `firmware/README.md` "Power"; `DESIGN_SPEC.md` section 4.
7. **The log cannot support its own validation** (section 6, items 1, 3, 5): no tilt logger,
   no grain values, no horizon profile, 1 s time stamps. File: `firmware/core/gl_log.h`.
8. **No replay path** from a field log into the simulator. Files: `sim/README.md`,
   `firmware/README.md`.
9. **Grain amplifier headroom.** `DESIGN_SPEC.md` section 4: 470 kilohm feedback with the
   input at mid-rail on a 2.8 V supply. That leaves roughly 1.3 V, or about 3 microamps of
   photocurrent, before the amplifier saturates (our arithmetic). Sunlight scattered through
   the grass under the rim may reach that. Test L2. In the same line: five 68 ohm resistors,
   one per pin, put two in series with each LED, so the LED current is about 6 mA (red) and
   10 mA (infrared), not the 20 mA that `docs/research/grain-sensing.md` assumed. This is not
   a new finding: `firmware/README.md` ("Drivers", note "Grain LED current") already records
   it with these figures. The resistance of the processor pins, which that note leaves out,
   lowers both a little.
10. **Cradle electrical details are missing.** The specification and the mechanical parts
    list name a USB-C socket and a resettable fuse. They do not name the two 5.1 kilohm
    resistors a USB-C socket needs to be given power by a USB-C charger, nor the fuse rating.
    Files: `DESIGN_SPEC.md` section 5, item 6; `mechanical/README.md` section 2, row 22.
11. **The display stack has no film for polarised sunglasses**, which the display research
    called required if such glasses are in scope. Files: `DESIGN_SPEC.md` section 5;
    `docs/research/display.md` section 2.
12. **An interrupted firmware update may leave a unit that only the factory can revive.** The
    consumer cradle has four pins; recovery needs the three extra programming pins. File:
    `firmware/README.md` "What is not done".
13. **The simulation report is headed "hardware revision C"** while the specification is rev
    D. The stereo numbers are the same; the report should say which revision it stands for.
14. **The repository's hot tests are above the only cell limit it holds.**
    `mechanical/README.md` section 9 asks for 70 C on complete bonded units (tests 2 and 9).
    The only cell figure is the family's discharge limit of 60 C
    (`docs/research/bom-verification-opto.md` 3.4); the storage and process limit is an open
    gate (B15). Section 2.9 keeps units with a real cell at 60 C or below until the data sheet
    says otherwise.
15. **Shipping at 30 % charge and an always-on motion wake-up do not fit together.** With the
    wake-up on, as the firmware leaves it, a cell at 30 % may be empty in about a month:
    26 days by the firmware's own supply model, one to two months by the older research
    figures (test Q1). The 2.3 to 3.8 months in `docs/research/power.md` assume no wake-up
    source. Files: `firmware/README.md` "Architecture" and "Power"; `docs/COMPLIANCE.md` rows
    11 and 12; `docs/MANUFACTURING_PLAN.md` 7.4.
16. **The upper-view guarantee and the factory gate measure different things.** The 14.5
    degrees in `master_params.yaml` is the angle up to which the full light bundle is clear.
    A "target at +17 degrees seen by both cameras" (`mechanical/README.md` step 16) is still
    seen at more than half brightness by a unit at the tolerance limit, so it neither proves
    nor disproves the guarantee. Test O1 now measures where the dimming starts.

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
