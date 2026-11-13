# GreenLine GL-1 firmware (phase 2)

Firmware for the GreenLine GL-1 electronic ball marker (`../design/DESIGN_SPEC.md` and
`../design/master_params.yaml` rev D-EVT1). The board changes this file calls **rev C2** are the
ones of section 4 of that specification (charger inhibit, cell NTC, EXTCOMIN divider, core
clock, chip-select pulls, PWDN pins); the specification's own header reads "rev D, EVT1".

## Status - read this first

* **Nothing here has run on hardware.** No board exists and no vendor SDK is available in the
  build environment. What exists is portable C99 that is built and unit-tested on the host
  against a simulator of the board, and cross-compiled (compile only, not linked) for the
  Cortex-M33 to check that it is clean and to measure its size.
* **`hal/stm32u5/gl_hal_stm32u5.c` has been compiled, and never linked or run** (phase 2,
  builder 3). `make cross-hal STM32_HEADERS=<dir>` compiles it - compile only - against ST's
  and Arm's header files, warning-free with the firmware's whole warning set; the first compile
  found two wrong identifiers and two that existed only as legacy aliases ("STM32U5 backend").
  That shows that the names and types fit. It shows nothing about behaviour: no HAL source was
  compiled, no image linked, and every sequence in the file is still from memory of the
  reference manual. `gl_hal_stm32u5_usb.c` is **still uncompiled** (it needs ST's USB device
  library). No vendor file is in this repository; without the header directory the target is
  skipped with a message.
* **The device models of the simulator encode this project's understanding of the parts**, the
  same understanding the drivers are written from. A passing driver test shows that driver and
  model agree and that the bus traffic is self-consistent and obeys the board rules; it does not
  show that the real part behaves that way. Every register and command of the IMU and the flash
  is in one table below, marked "from memory - verify against datasheet".
* **The putt solver is ported** (phase 2, builder 1). `core/gl_solver*.c` is a C99 port of the
  Python reference (`../sim/greenline_sim`: roll kernel, aim solver, range fusion, patch fit,
  estimate, fallbacks, confidence) behind `core/gl_solver.h`; `gl_solver_version()` is
  0x00020100 (0x00020000 before the phase-2 review, which added two options: `near_miss_m`
  and `max_steps`). One source builds in double precision (host, compared with the reference)
  and in single precision (the firmware). What was run and measured, and what is not met, is in
  "Solver" under Measured results. **None of it has run on the target**: its run time there is
  an estimate.
* **The application uses the estimator end to end, and the rev C2 board changes are in** (phase
  2, builder 2). What a read hands to the estimator is gated, never synthesised; the estimator's
  range fusion is the only one that feeds the aim; its result is mapped to the screen with a
  message for every fallback and a dashed line for every aim that is not a solution (which
  results look normal and which do not: the table under "Result on the display"). Read
  sequence, vision, estimator and rendering are tested together on
  the simulator against the reference, with the direction of the drawn line measured from the
  panel's pixels ("Putt on the display"), and `make appdiff` repeats the comparison with the
  Python reference itself. Charger inhibit, cell NTC, EXTCOMIN divider, core-clock switching,
  chip-select states and the moved pins are implemented and tested on the simulator ("Charger
  and cell temperature", "Board changes of rev C2"). **Two requirements are NOT MET and are
  pinned as such by tests: nothing supervises the charger while the ROM bootloader runs
  (in the test: charging at 50 C for the 600 s the test lasts), and a hung firmware leaves it
  unsupervised until the watchdog resets it (measured: 33 s).** DESIGN_SPEC has since answered
  both in hardware (amendment E1: a charger with its own temperature input). **This firmware
  is still written for the rev C2 charger**, as its brief said; the difference is pinned by a
  test as NOT MET and listed under "DESIGN_SPEC amendments E1 to E16".
* **A second review has been applied** (phase 2; three reviewers: numerical, safety, product;
  34 findings). Every finding that was fixed was first reproduced on the unchanged tree and
  has a regression test that failed there. The critical one: a second double tap on a Precision
  result gave a `2X` screen with zero slope and a straight line. The gravest for the cell: one
  lost VBUS edge left the charger unsupervised for as long as the marker slept. The table is
  "Phase-2 review: what was fixed"; what could not be fixed here is in "Open issues" (24 to
  32, and additions to 1, 2, 5, 12, 17, 18, 21 and 22).
* All accuracy figures below are **measured on synthetic data** (`tests/synth`). They say what
  the algorithms do on idealised images; they are not a prediction of field performance. In
  particular the renderer does not model the Bayer mosaic of the colour sensor.
* Hardware facts that DESIGN_SPEC marks PROVISIONAL, and the device facts the drivers had to
  assume, are named constants in `core/gl_provisional.h` and nowhere else (full list below).
* **A design review has been applied** (three reviewers: C safety, vision, hardware interface;
  32 findings). What was changed, what was handed to the hardware design and what remains open
  is in "Design review" below; the vision figures in this file are the ones measured after it,
  and several of them are worse - and truer - than the ones this file used to carry.
* **The vision's run time has been reduced from 145 to 58 million host instructions for the
  nominal read, with bit-identical results, and the simulator now charges computation its
  time** (phase 2, builder 3; "Run time"). With that, a Quick Read at 6 m shows its result
  **4.1 - 4.8 s after the marker comes to rest** (4.4 s at the nominal factor) and keeps the
  camera rail on for 2.2 - 2.8 s - not the 3.45 s and 1.56 s this file used to state, which
  charged no computation. DESIGN_SPEC said "about three seconds" then; its amendment E15 now
  states these figures, taken from this model. **They are a model and not a measurement**:
  the factor between a host instruction and an MCU clock cycle is an ESTIMATE (1.5 - 3,
  nominal 2), no board exists. A flagstick between 2.25 and 4.5 m used to take 0.6 s longer in
  a third of the reads (its own shoulder in the band was probed as a second line); the
  phase-2 review removed that (2.42 - 2.46 s of rail and at most 4.40 s to the result in a
  sweep of 21 reads). **Still outside the stated figures:** a read with a person behind the
  stick or with two real lines in the band (3.4 s of rail), and a near stick at the high
  factor (the review measured 2.99 s of rail and 5.0 s to the result at 1.5 m; not repeated
  here). A stick whose line is wider than 1.2 px (3 m and nearer in the bench scenes) costs
  72 to 87 million instructions instead of 58 to 60. Honest timing also changed three
  results, all pinned by tests as NOT MET: a second post 14 px from the stick defeats more
  than half the reads (26 of 64 give a disparity), a Survey fit hangs on a marginal
  classification of the stick's base, and a drift that reverses inside a group of four strips
  is not noticed ("End to end", "Vision").
* **Rev C and later.** `core/gl_config.h` is generated from `master_params.yaml`, which now
  reads rev D-EVT1 (`GL_CFG_PARAMS_REV`); the values this firmware takes from it are the ones
  rev C set (stereo baseline 20.0 mm, cameras at x = +-10.0 mm). Where this file says "the rev
  C YAML" it means that change. The user calibration is a **zeroing on any hard flat surface**
  (read, turn the marker 180 degrees in place, read again). It is never done in the cradle,
  which takes the marker one way round only: the UI state is `CAL_ZERO` (rev B: `CAL_FLIP`), it
  can be entered only from the settings dial, being put into the cradle abandons it, and the
  USB command that asks for it is answered with `GL_ERR_STATE`.

## Design review: what was done with the 32 findings

| Area | Findings | Outcome |
|---|---|---|
| Charge gate (2 findings, one critical) | fails open with a dead or silent IMU; trusts unvalidated bytes | **Fixed**: liveness-checked IMU temperature, MCU die sensor as second opinion, staleness limit, gate evaluated in every state; simulator rule "charger enabled at Stop entry". **Superseded in phase 2:** rev C2 gives the cell an NTC and turns the charger's default round; gate, rules and tests were rewritten ("Charger and cell temperature"). |
| IMU faults (3) | one bus error disables motion input until reset; lost interrupt latch stalls the loop (backend and application) | **Fixed** in the application (recovery with back-off, polling fallback, watchdog as last resort) and in the uncompiled backend (latch updated with interrupts masked). |
| Capture pipeline (1) | assumed the vision is faster than a frame | **Fixed** structurally (whole group captured, then analysed; frame-end times latched in the interrupt; progress-based time-out). **The run time itself is not fixed**: open issue 1. |
| Precision Read, SET_CAL, LOG_ERASE, store geometry, DFU gate, USB stop outside the cradle state, float-to-int conversions, integer drawing overflow (8) | as titled | **Fixed**, each with a regression test (`test_e2e_faults.c`, `test_log.c`, `test_proto.c`, `test_gfx.c`, `test_basics.c`). DFU has no way back without a host: stated, not fixable here. |
| Vision: trunk / post accepted, stronger object chosen (critical) | | **Fixed for the reviewers' cases**: 0 of 88 stick-free reads report a flagstick; the stick is read beside a stronger post 120 px away. **Not for every case**: a second thin pole 7 px from a 0.8 px stick is still taken in half the reads, with the ambiguity flag. |
| Vision: turf texture read as stick (critical) | | **Fixed**: only rows above the turf edge are fitted; below it the stick is followed only with significance against ghost lines. |
| Vision: sigma 3-20 times too small (major) | | **Fixed in kind**: static part estimated from the flanks, calibration term added; error within 1.2 claimed sigma rms on all but one scene (1.4). The calibration term is a guess. |
| Vision: faint sticks rejected, all-or-nothing read, lowest point and base class, flag over the tip, band false candidates with FPN, phase bias, accuracy table on an impossible scene (7) | | **Fixed or partly fixed**, see "Vision" for what is met and what is not; the reviewers' scenes are permanent tests. |
| Range fusion (1) | contradicting sources averaged; insignificant disparity | **Fixed** (`test_range.c`). |
| Camera bus at power-up (1) | depends on PWDN releasing the bus | **Not fixable in firmware**: measured, asserted, documented (open issue 3). |
| Backend: EXTCOMIN stop on an uninitialised handle (1) | | **Fixed by inspection only** (the file compiles since builder 3 and has never run); the rule "every stop is safe before its start" is in `gl_hal.h` and tested on the simulator. |
| Charger default-off with the MCU unpowered (1) | | **Escalated to hardware; answered by rev C2** (charger on by default, the MCU can only stop it: `CHG_INHIBIT`). |
| Register table says "pulsed"; register 0x0C bit 4; EXTCOMIN 546 ticks; bootloader pins (4) | | **Fixed** in driver, table and generator; two SPEC pins remain a release gate (open issue 4). |

No finding was rejected as false. Two were closed only as far as firmware can (camera bus,
charger default), one only as far as a file that has never run can (EXTCOMIN handle).

## Phase-2 review: what was fixed

Three reviewers (numerical, safety, product) read the tree the three builders left and returned
34 findings. Every finding that was fixed was reproduced first on an unchanged copy of that
tree ("before"); the ones that were not fixed were checked against the code, and where this
session did not measure them again their figures are quoted as the reviewer's. A fix has
a regression test that was run against the unchanged copy and FAILED there: 13 tests of
`tests/test_e2e_review.c` (13 of 13 failed, 68 failed checks), `tests/test_app_handover.c`
(8 failed checks), `test_backend_starts_the_watchdog_first` in `tests/test_board.c` (5 failed
checks), and the new tests of `tests/test_solver.c`, `test_ui.c`, `test_gfx.c`, whose "before"
figures are in the table. The fourteenth test of `test_e2e_review.c` and the rail-time bound of
`test_read.c` came with the two vision-timing fixes; their "before" figures are the same sweeps
run on the unchanged copy. **No finding was rejected as false.** 21 are fixed (2 of them only
by inspection of the backend, which has never run), 4 are fixed in part (3, 8, 24, 25) and 9
are not fixed (2, 9, 10, 19, 20, 27, 28, 32, 33): each of those is an open issue with its
reason in the table - a reference behaviour the brief said not to change, a data sheet that
is not here, or a decision that is the owner's.

| # | Finding (severity) | Outcome | Before -> after, and the test |
|---|---|---|---|
| 1 | The fallback order discards a near-solution of the patch and shows a secant-plane aim that misses the hole on the fitted patch (major) | **Fixed, additively in the reference too.** New `EstimatorConfig.near_miss_keep` (default 0: the old behaviour, and the old vectors are a byte-identical prefix of the regenerated file), ported as `gl_solver_options_t.near_miss_m` (default 0; the application sets 5 mm). A patch solve that ends without a solution but whose last iterate passes within that distance of the hole centre is kept (`aim_source` 0, its status), its confidence is scored like a fallback's and the screen says `APPROX` | 18 new reference cases (14 kept, 4 controls). In the 14 the kept aim passes at most 4.44 mm from the hole centre on the fitted patch; the aim it replaces misses by more than the hole's radius in 4 and does not reach the hole in 10; the aim moves by up to 159 mrad. `test_near_miss_cases`, `sim/tests/test_near_miss.py`, `make diff` |
| 2 | Near the critical slope a one-microradian input change flips the aim by more than a display step in about 3 % of reads; the best-effort direction is an arbitrary search iterate (major) | **Not a port error; the reference's search is not changed** (decision of the brief). The C double build follows the reference exactly there too (`make diff`: bit-identical aims on every random aim problem that ran). Stated in `gl_solver.h` and under "Solver"; on the screen a best-effort aim is dashed, `NOT SOLVED`, `BREAK ?`, one box at most | open issue 24 (the estimator's owner) |
| 3 | The single-precision tolerance margins hold only for the vectors' putts (minor) | **Statement corrected, the limit measured and pinned.** The roll noise between the precisions is 0.03 of `tol_miss` up to 6 m and 0.12 up to 15 m; **NOT MET beyond**: 1.08 x at 15-25 m, 13 x at 25-40 m | `test_single_precision_roll_noise_by_distance`; a tolerance that grows with the distance is open issue 25 |
| 4 | Single precision: a converged horizon fit is reported as not converged (60 iterations of a one-ulp flip-flop) (minor) | **Fixed** in the single build only: a step below the resolution of the parameters ends the fit as converged | the reviewer's case: not converged after 60 iterations -> converged after 10 (double: 9). `test_horizon_fit_converges_at_the_resolution_of_its_parameters`; the vectors are unchanged |
| 5 | The costliest estimate found is 628,940 RK4 steps, above this file's "worst case constructed" (minor) | **Figures corrected; one cause removed.** When the fitted patch IS a plane, its secant plane is the same problem and is no longer solved a second time | that case: 424 rolls / 619,822 steps -> 212 / 309,911. Costliest found now, with the reference's limits alone: 575,247 steps. `test_step_budget_and_the_plane_solved_once`, `make bench`. Not a proven maximum |
| 6 | The default pace of the double build is 0.30f (minor) | **Fixed**: the default is a double constant | 0.30000001192092896 -> 0.29999999999999999; asserted in the API test of `tests/solver/gl_solver_run.c` |
| 7 | Absurd inputs: `GL_OK` where the reference raises; silent overflow in single precision (minor) | **Fixed**: a square that overflows is `GL_ERR_RANGE` in both precisions, where the reference raises `OverflowError` | four probe calls `GL_OK` -> `GL_ERR_RANGE`. `test_absurd_inputs_are_refused`, the hostile-input table, `make diff` with inputs of 1e300, 1e20, 1e-20, 1e-200 |
| 8 | The target build is IEEE-exact only because `-std=c99` happens to switch contraction off; libm on the target not verified (minor) | **Fixed for the flag**: `-ffp-contract=off` is explicit in every build and `make cross` fails on any fused multiply-add instruction. **libm on the target: not verified** | `make cross`: "no fused instruction"; open issue 26 |
| 9 | The base-visible flag is a hard switch (aim moves by more than a display step in 1.6 % of nominal Quick Reads) (minor) | **Not changed in the estimator** (reference behaviour). The screen now marks the weaker case: `PLAYS n?` when the base was hidden | open issue 22 |
| 10 | Method B2 with untidy horizons: nominal reads fall back, jump and differ between precisions (minor) | **Not fixed in the estimator.** B2 stays OFF by default; a poor horizon now has a message on the screen (`POOR HORIZON`; it had none, and the estimator's 0.8 on the confidence did not change the number of boxes) | mapping test in `test_e2e_putt.c`; open issue 27 |
| 11 | A single lost VBUS edge leaves the charger unsupervised for good, or the marker awake until the cell is flat (major) | **Fixed**: the main loop acts on the LEVEL of VBUS in every pass and before every sleep; the edge only shortens the wait | lost rising edge, asleep, cradle at 50 C: unsupervised for the 600 s of the test -> at most 15.5 s (the next housekeeping wake-up). Lost falling edge: awake with USB for ever -> asleep within 1 s (1.58 -> 0.021 mAh in the hour after, supply model). `test_vbus_rising_edge_lost_while_asleep`, `test_vbus_falling_edge_lost_in_the_cradle` |
| 12 | STM32 backend: the watchdog is started last, and a clock start-up failure returns before it (major) | **Fixed by inspection** (the file compiles and has never run): the watchdog is the first thing `gl_hal_init()` starts, the function has one return, an LSE that does not start falls back to LSI | `test_backend_starts_the_watchdog_first` (a check of the source text: 5 failed checks before); `make cross-hal` |
| 13 | The costliest estimate blocks the main loop for seconds with no watchdog refresh, and only loop counters bound it (minor) | **Fixed**: `gl_solver_options_t.max_steps`, a budget on the RK4 steps of one estimate (firmware only; default none, as in the reference); the application sets 300,000 and refreshes the watchdog before the solve. A solve that runs out ends as a best-effort aim (dashed, `NOT SOLVED`) | costliest case: 421 rolls / 575,247 steps -> 223 / 300,514 with the budget. `test_step_budget_and_the_plane_solved_once` |
| 14 | `build_measurement_()` clamps the horizon count to the solver's 41 but copies from arrays of 32 (minor) | **Fixed**, and a compile-time assertion ties the two sizes | `tests/test_app_handover.c`: counts of 33..255 reached the solver as 33..41 samples -> 32 |
| 15 | Test audit: one phase-1 safety expectation reversed, the application-level staleness test gone (minor) | **Staleness test restored** end to end. "One die sensor is enough" stays as built: open issue 5 | `test_stalled_supervision_stops_the_charge`: the charge is stopped when the last cell reading is 12.0 s old (before: never) |
| 16 | The simulator's power rules fire in two thirds of random VBUS-bounce scenarios (minor) | **The firmware was at fault, not the rules**: it could go to sleep on a VBUS level it had not acted on. Fixed with 11 | 300 random scenarios (4857 edges, 105 resets): 211 scenarios with 422 violations -> 0. `test_vbus_bounce_stress` |
| 17 | Backend, by inspection: wrong DFU comment, `clock_slow_()` ignores a failed switch, clock re-initialisation with the HAL tick suspended (minor) | **Fixed by inspection.** The contract is in `gl_hal.h` (a failed switch back returns `GL_ERR_IO` and the clock is still FAST), the simulator can fail the switch, and the application no longer believes it | three failed switches during a read: 482 "Stop mode with the fast clock" violations -> 0, `clock_fails` 3. `test_failed_switch_to_the_slow_clock_is_not_believed`, `test_board.c` |
| 18 | `make cross` checks the objects, not an image (minor) | **Fixed as a check**: `tools/cross_link_check.py` links a probe image against the installed newlib and walks the calls from the firmware's functions | figures under "Building and testing". Still no real image |
| 19 | No firmware limit on charge duration or termination; awake with USB for as long as it sits in the cradle (minor) | **Not fixed**: needs the charger's data sheet and a product decision | open issue 28 |
| 20 | The 1.5 K guard band leaves 0.6 K at 0 C for the error of the one-B NTC equation (minor) | **Not verified**: no R-T table of the part here | open issue 5 |
| 21 | A second double tap after a Precision Read gives a `2X` result with zero slope and a straight line (**critical**) | **Fixed**: Precision once per placement; a double tap on a `2X` result goes on to the Survey like on any result | `test_double_tap_after_precision_starts_a_survey`, `test_ui.c` |
| 22 | The Precision result is drawn for a marker that faces away from the hole: text upside down, `<` / `>` mirrored for the golfer (major) | **Fixed**: with the ball behind the marker the whole result screen is drawn turned by 180 degrees. Turning the marker back is a new placement and a new read: as built, open issue 29 | the panel is pixel for pixel the upright picture turned round (0 of 16384 differ). `test_precision_result_is_upright_for_the_golfer`, `test_rotate_180` |
| 23 | A dialled distance never expires (major) | **Fixed**: it belongs to one hole. It is forgotten after a read that ranged a flagstick, when the marker goes to sleep and at start-up; a flag-out result is drawn dashed with an empty confidence bar | `test_dialled_distance_belongs_to_one_hole` |
| 24 | The confidence bar does not separate weak results from clean ones; several fallbacks look like a normal result (major) | **Fixed in part**: flag-out is tentative (23), a poor horizon and a kept near miss have messages, `PLAYS n?` marks a hidden base, and the table under "Result on the display" now says which results look normal. **Not done**: an indicator relative to what a clean read achieves at that distance | open issue 21 |
| 25 | Time to a line and camera-rail time exceed the specification's figures in a third of the reads between 2.25 and 4.5 m (major) | **Fixed for that cause, not in general.** The second "line" was the shoulder of the stick in the widest template: dropped. And a lone line that is not a flagstick is given up after its first group | 65 reads at 1.5-4.5 m: 23 with two candidates, rail up to 3.12 s, result up to 5.07 s -> 0, 2.42-2.46 s, at most 4.40 s. 88 stick-free reads: mean rail 1.65 s -> 1.02 s. `test_near_stick_is_one_candidate`, `test_no_flagstick`. Still slow: a person behind the stick, two real lines; the high compute factor; open issue 1 |
| 26 | The distance prompt after "no flagstick seen" is a dead end for 30 s (major) | **Fixed**: picking the marker up and putting it down again reads again; the prompt says so | `test_distance_prompt_re_placing_reads_again`, `test_ui.c` |
| 27 | DESIGN_SPEC has been amended (E1 to E16) since the builders' brief (major) | **Not fixed, by the brief's decision** (this firmware is rev C2). The generator now reads the charger sentence of the spec and a test pins the difference as NOT MET; the README's statements are corrected | `test_charger_of_the_specification_is_not_the_firmwares`; "DESIGN_SPEC amendments E1 to E16"; open issue 2 |
| 28 | Survey in the order the specification gives never shows a line until a fourth placement back at the ball (minor) | **Not fixed** (product decision). The wrong sentence of this file is corrected | open issue 18 |
| 29 | A solved aim more than 13.5 degrees off the visor axis is drawn like a tentative one, with an arrow pointing away from the aim (minor) | **Fixed**: the parallel substitute is drawn in the style of the result (solid if solved) and the arrow is gone | aim +258.8 mrad: 0.46 of the solid core inked and 63 pixels of arrow -> 0.73 and 0. `test_solved_aim_off_the_screen_keeps_its_style`, `test_gfx.c` |
| 30 | `PLAYS` is the roll-out distance including the PAST setting (minor) | **Fixed**: `PLAYS` is the estimator's plays-like distance minus PAST | 6 m, dead flat, PAST 0 / 30 / 90 cm: `PLAYS 6.0M` each (estimator 5.98 / 6.28 / 6.88 m). `test_plays_like_is_the_flat_putt` |
| 31 | The GRAIN and GRASS dial items do not change the line (minor) | **Fixed for what exists**: GRAIN ON hands the measured grain to the solver (`use_grain`) with the grass's coefficient; GRAIN OFF measures nothing. GRASS has an effect only with GRAIN ON. The physics behind the coefficients is unproven (`gl_provisional.h`) | aim 109.26 / 113.96 / 136.31 mrad for OFF / ON bentgrass / ON bermuda. `test_grain_setting_reaches_the_solver` |
| 32 | At 2 to 3 m the hole is read 3 to 5 mm low; at 0.6 m the flagstick is refused (minor) | **Not fixed** (vision) | open issue 30 |
| 33 | A result cannot be recalled (minor) | **Not fixed** (product decision) | open issue 31 |
| 34 | README statements that the code or the tests contradict (minor) | **Corrected**, all nine, from the final run; the stale comment in `gl_app.c` too. The band-only bearing is not logged: the claim is dropped | this file |

## DESIGN_SPEC amendments E1 to E16

`../design/DESIGN_SPEC.md` now reads "rev D, EVT1, with amendments E1 to E16". The builders'
brief and this firmware are older than the amendments ("rev C2"). Which document rules for the
next phase is the owner's decision; this is where the firmware stands against each amendment
that touches it (the others are mechanical or assembly matters):

| # | Specification now | Firmware | Status |
|---|---|---|---|
| E1 | Charger BQ25101 with its own temperature input; `CHG_INHIBIT` is a push-pull output, HIGH = stop (an N-MOSFET pulls the charger's TS pin low) | written for the MCP73831 of rev C2: `CHG_INHIBIT` open drain, LOW = stop, released = charge; the simulator counts a push-pull drive of that pin as a violation | **NOT MET, pinned** (`test_charger_of_the_specification_is_not_the_firmwares`: `GL_PINS_SPEC_CHG_INHIBIT_ACTIVE_HIGH` 1 against `GL_POWER_CHG_INHIBIT_ACTIVE_HIGH` 0). On an E1 board this firmware's "stop" stops nothing; the charger's own input protects the cell, and the two NOT MET rows of the charger table become hardware-covered. `tools/gen_pins.py` reads the sentence, so a further change is seen |
| E2 | Two cell thermistors (one for the charger, one for the MCU), Murata NCU15XH103F60RC | one NTC, 10 kohm, B 3380 as specified in rev C2 | the MCU's thermistor keeps its role; the part's B value and R-T table are **not verified** (open issue 5) |
| E3 | Grain LED parts and real drive currents (about 6 and 10 mA) | the driver's note said the same; nothing depends on the part | no change needed |
| E11 | Factory level calibration on two seats (base face, ball feet) | one zeroing bias | **not implemented** (open issue 32) |
| E12 | Display rotation measured at the factory and stored; the firmware rotates the drawn line by it (up to about 1 degree = 17 mrad) | no such calibration field; the largest drawn-line error measured here is 3.9 mrad | **not implemented** (open issue 32) |
| E13 | No read above 60 C cell temperature; ship mode | neither exists | **not implemented** (open issue 32) |
| E14 | Sleep current and rail limits | the supply model draws 20.6 uA asleep; every current is provisional | not verified |
| E15 | Read time restated from this firmware's timing model: 4.1 to 4.8 s, camera rail 2.2 to 2.8 s | the same model; the figures of this file | agrees for the nominal read. It is a model, not a measurement, and it is exceeded by a read with a person behind the stick or two real lines ("Run time") |

## Architecture

```
                 app/gl_main.c        for (;;) gl_app_run_once(&app);      no RTOS, no heap
                       |
  +--------------------+-----------------------------------------------------------------+
  | app/                                                                                  |
  |   gl_app.c     one loop iteration: interrupt sources -> work -> events -> UI          |
  |                transition table -> actions -> redraw -> sleep (Stop 2 / idle)         |
  |   gl_motion.c  IMU samples -> STILL / MOTION / UPRIGHT / FLAT / DOUBLE_TAP /          |
  |                DIAL_STEP / SPIN_DONE; owns the block averager of the tilt read        |
  |   gl_read.c    camera part of a read as a step machine: rail on, horizon band,        |
  |                L R R L x 8 strips, vision on each strip, rail off, combined result    |
  |   gl_usb.c     CDC bytes <-> gl_proto callbacks, live streams, log dump, reboot       |
  +---------+-------------------------------------------+---------------------------------+
            | pure computation                          | devices
  +---------v------------------------------+  +---------v---------------------------------+
  | core/     (no HAL, no stdio, no heap)  |  | drivers/   (hal/gl_hal.h + core only)      |
  |   gl_ui       states, screens          |  |   ov7692          two cameras, shared bus, |
  |   gl_vision   flagstick on strips      |  |                   rail rule                |
  |   gl_cam      camera model             |  |   ls013b7dh03     memory LCD               |
  |   gl_range    range fusion             |  |   lsm6dsv16x      IMU                      |
  |   gl_tilt     slope, zeroing, spin     |  |   mx25r           NOR flash                |
  |   gl_gesture  posture, dial, tap       |  |   grain_frontend  LED ring + photodiode    |
  |   gl_grain    grain maths              |  |   power           battery, charge gate     |
  |   gl_gfx      1-bpp graphics           |  +---------+---------------------------------+
  |   gl_proto    USB framing              |            |
  |   gl_log      ring log, blob store     |  +---------v---------------------------------+
  |   gl_settings gl_cal gl_event ...      |  | hal/gl_hal.h   the ONLY hardware interface |
  |   gl_solver   putt estimator + solver  |  +------+---------------------------+---------+
  +----------------------------------------+         |                           |
                                            +--------v---------+   +-------------v-----------+
                                            | hal/host         |   | hal/stm32u5             |
                                            | board simulator  |   | STM32Cube HAL backend   |
                                            | (the unit tests) |   | compiled, NEVER RUN     |
                                            +------------------+   +-------------------------+
```

Data flow of a Quick Read (DESIGN_SPEC section 6), as the end-to-end test runs it:

```
IMU INT1 (wake-on-motion) -> GL_EV_MOTION -> WAKE: display on, IMU 240 Hz
 -> flat and still for 0.5 s (4 blocks of 32 samples) -> GL_EV_STILL
 -> READ_TILT: 8 still blocks (1.07 s) -> temperature polynomial, 6-face matrix, slope,
    minus the zeroing bias -> GL_EV_TILT_DONE
 -> CAPTURE: core clock FAST (gl_hal_clock_set) -> camera rail on (pins handed over in the
    rule's order) -> 640 x 96 band of the
    left camera around its calibrated horizon row -> matched-line detector -> up to 4
    candidates, less the shoulders of a much stronger line (several: one L R R L group each,
    then the one that is a flagstick; one: given up after its first group if that group says
    it is not a flagstick)
    -> 96 x 480 strips L R R L x 8: each group captured into four buffers, then refined
    strip by strip (rows above the turf edge only) -> segment fits over the lowest 0.4 m,
    timing correction, disparity accumulation -> camera rail off -> is it a flagstick
    (width, height, disparity)? -> base class, lowest point, top, horizon over the left
    strips -> bearing and elevations relative to gravity -> stick-height learning (the
    application's own range is a diagnostic only) -> GL_EV_CAPTURE_DONE
 -> SOLVE: the read as gl_measurements_t, GATED (what was not measured is "not available")
    -> watchdog refreshed -> gl_solver_estimate() (method B1, or B2 by setting: range fusion,
    patch fit, aim solve within a budget of 300,000 RK4 steps, confidence) -> core clock SLOW
    -> view, log records -> GL_EV_SOLVE_DONE
 -> SHOW_RESULT: aim line through the ball position, distance, plays-like distance, slope
    with the fall line, break in cups, confidence, one message if anything is unusual; MCU in
    Stop 2 between IMU samples -> 45 s -> SLEEP: display off, IMU wake-on-motion, flash in
    deep power-down, CHG_INHIBIT released, Stop 2, a wake every 16 s for the watchdog
```

## Layout

| Path | Content |
|---|---|
| `core/` | Portable core: pure computation, no HAL, no stdio, no heap. |
| `drivers/` | Device drivers written against `hal/gl_hal.h`: `ov7692`, `ls013b7dh03`, `lsm6dsv16x`, `mx25r`, `grain_frontend`, `power`. |
| `hal/gl_hal.h` | The only hardware interface: GPIO, SPI, SCCB, DCMI strip capture, ADC / op-amp, LPTIM, tick / RTC, USB CDC, sleep. |
| `hal/host/` | Host simulator behind `gl_hal.h`: simulated time, pin and bus trace, models of the LCD, flash, IMU, two cameras, analog front end and USB; rule checkers. |
| `hal/host/gl_sim_cost.h` | The instruction counts of the vision stages, the estimate and a rendering (measured with callgrind, `make profile`) from which the simulator charges computation its time. |
| `hal/stm32u5/` | STM32U585 backend (`gl_hal_stm32u5.c`: **compiled against the vendor's headers by `make cross-hal`, never linked or run**; `gl_hal_stm32u5_usb.c`: **never compiled**), the project's own HAL configuration `stm32u5xx_hal_conf.h` and the generated pin map `gl_pins.h`. No vendor file. |
| `app/` | Main loop and glue: `gl_app`, `gl_motion`, `gl_read`, `gl_usb`, `gl_app_cfg.h` (tuning constants, flash layout), `gl_main.c` (`main()`). |
| `tests/` | Host unit tests, one executable per `test_*.c` (27), with the tiny runner `gl_test.h`; `test_drv_*.c` check bus traffic, `test_e2e.c` and `test_e2e_faults.c` run the whole firmware on the simulator (the second one with faults injected), `test_e2e_putt.c` runs whole reads on rendered scenes and compares the line on the panel and the numbers shown with the reference, `test_e2e_review.c` holds the regression tests of the phase-2 review that need the whole firmware (product behaviour, charger supervision with lost VBUS edges, 300 random VBUS-bounce scenarios), `test_app_handover.c` calls the application's hand-over to the solver directly, `test_board.c` checks the rev C2 board rules (chip selects through reset, core-clock calls, EXTCOMIN) and, as a check of the source text, the order of the backend's start-up, `test_read.c` runs the camera part of a read on hard scenes, `test_vision_equiv.c` compares the vision bit for bit with the frozen phase-1 version, `test_solver.c` runs the solver against the reference vectors in both precisions. |
| `tests/vision_ref/` | The vision of phase 1, frozen (`gl_vision_p1_body.inc`, verbatim; built with its symbols renamed `glp1_*`): the oracle of `test_vision_equiv.c`. Host only. |
| `tests/solver/` | `gl_solver_vectors.c` (**generated** from `../sim/results/reference_vectors.json`, 1.06 MB of C data, host only), its hand-written header, `gl_solver_run.c`, the harness that is compiled once per precision, and `gl_solver_ref.c`, the double-precision build of the solver behind a plain-C interface (`gl_ref_estimate`), which the end-to-end putt test uses as its reference. |
| `tests/synth/` | Synthetic strip renderer (`gl_synth`), the reviewers' independent, physically consistent scene generator (`gl_scene`, used by `test_read.c`) and simulated NOR flash with power cuts (`gl_simflash`). |
| `tools/` | `gen_config.py` (YAML -> `core/gl_config.h`), `gen_font.py` (-> `core/gl_font_data.c`), `gen_pins.py` (-> `hal/stm32u5/gl_pins.h`, cross-checked against DESIGN_SPEC), `gen_vectors.py` (reference vectors -> `tests/solver/gl_solver_vectors.c`), `cross_report.sh` and `cross_link_check.py` (`make cross`: sizes, stack frames, forbidden symbols, fused instructions, the link probe); host-only solver tools: `diff_solver.py` + `diff_solver_abi.c` (`make diff`), `solver_bench.c` (`make bench`), `app_diff.py` (`make appdiff`: the estimator inputs the application produced, run through the Python reference); run-time tools: `vision_bench.c` (`make bench-vision`), `vision_cost.sh` (`make profile`); `cross_hal.sh` and `cross_hal_report.sh` (`make cross-hal`). |

## Building and testing

```
make test     # gcc -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror, builds
              #   core + drivers + app + simulator and runs all 27 test executables
              #   (several minutes, most of them the 984 reads of tests/test_read.c)
make asan     # the same under -fsanitize=address,undefined,float-cast-overflow
              #   (test_read.c with 3 instead of 8 reads per scene: its yield and accuracy
              #   assertions need the full count and are skipped there)
make cross    # arm-none-eabi-gcc -mcpu=cortex-m33 -mfpu=fpv5-sp-d16 -mfloat-abi=hard -Os
              #   -ffunction-sections: compiles core, drivers and app (NOT hal/stm32u5);
              #   size table, largest stack frames, forbidden-symbol check, fused-instruction
              #   check, and a LINK PROBE: the objects linked against the installed newlib's
              #   libm and libc (no start-up code, no HAL: not an image), to see what a link
              #   pulls in and whether the firmware's own functions can reach any of it
              #   (tools/cross_link_check.py)
make cross-hal STM32_HEADERS=<dir>
              # compiles hal/stm32u5/gl_hal_stm32u5.c - COMPILE ONLY - against ST's and Arm's
              #   header files in <dir> (layout and versions: "STM32U5 backend"); size, stack
              #   frames, forbidden-symbol check, the HAL functions a link would need.
              #   Without STM32_HEADERS, or if the headers are not there: SKIPPED with a
              #   message, exit 0 - the backend has then NOT been compiled
make config   # regenerate core/gl_config.h, core/gl_font_data.c, hal/stm32u5/gl_pins.h and
              #   tests/solver/gl_solver_vectors.c
make bench-vision
              # NOT part of make test: whole reads of 8 scenes on the simulator with the
              #   compute-time model: strips, what the cost table charges, camera-rail time
make profile  # NOT part of make test: callgrind (valgrind) instruction counts per stage of
              #   the vision, of whole reads and of the estimate; the source of
              #   hal/host/gl_sim_cost.h (several minutes)
make diff     # NOT part of make test: the solver as shared libraries against the Python
              #   reference on 20000 random reads and 20000 random aim problems (about 4.5 min;
              #   needs the reference's Python environment: numpy, scipy, numba optional)
make bench    # NOT part of make test: rolls, RK4 steps and fit iterations of typical and
              #   worst-case estimates (tools/solver_bench.c)
make appdiff  # NOT part of make test: tests/test_e2e_putt.c dumps every gl_measurements_t the
              #   application handed to the estimator; tools/app_diff.py runs the Python
              #   reference on them and compares flags, numbers and the drawn line (a few
              #   seconds; needs the reference's Python environment)
make V=1 ...  # show full compiler command lines
```

`build/host/tests/test_read --cpi 0` runs the read tests with computation for nothing (the
timing every figure before builder 3 was measured with; until the phase-2 review changed which
band lines a read probes, its output was byte-identical to the output of phase 1);
`test_read <scene> <reads> <factor>` runs one scene at a compute factor.

Needs `gcc`, `make`, `arm-none-eabi-gcc` (with newlib headers) and, for the staleness check of
the generated files, `python3` with PyYAML (skipped with a note if absent); `make profile`
needs valgrind. `make test` fails
if a generated file is stale, which is how the rev C YAML change was caught.

Firmware code (core, drivers, app) is additionally compiled with `-Wdouble-promotion -Wvla
-Wmissing-prototypes -Wstrict-prototypes -Wundef`. `make cross` fails if any object references a
double-precision soft-float helper, a double-precision libm function, the heap or stdio, which is
how "single-precision float only, no dynamic allocation" is enforced rather than promised.
gcc reports different `-Wconversion` findings at `-O1` (asan) and `-O2` (test): both must be run.

**Floating-point contraction is off, explicitly** (`-ffp-contract=off` in the flags of every
build, host and target; phase-2 review). It used to be off only because `-std=c99` implies it
with gcc; with `-std=gnu99` or another compiler the Cortex-M33's fused multiply-add would
have changed the solver's results in the last bit against the host build that is compared
with the reference. `make cross` now also FAILS if a compiled object contains a fused
instruction (`vfma`, `vfms`, `vfnma`, `vfnms`). This session: none; 342 `vmla` / `vmls`, which
multiply, round, add and round - as written.

**The link probe** (phase-2 review: the object check says nothing about what the C library
brings into an image). `tools/cross_link_check.py` links the cross-compiled objects against
the installed toolchain's libm and libc - a probe, not an image: no start-up code, no linker
script, every `gl_hal_*` symbol unresolved, nothing run -, builds the graph of direct calls
and takes EVERY firmware function as a starting point. This session: probe text 107,244
bytes, 477 functions of which 394 are the firmware's; the firmware reaches 43 library
functions by direct calls (single-precision libm and its kernels, `memcpy` and friends,
`__aeabi_ldivmod`, `__errno`); **17 double-precision helpers are PRESENT in the probe and
none is reachable from firmware code** (newlib's `erff` shares an object with `erfcf`, and
its error helpers with their double twins: "called only from `__math_check_oflow`,
`__math_check_uflow`, `__math_divzero`, `__math_invalid`, `erfcf`, `xflow`"); no heap, no
stdio. The check fails if any of them becomes reachable. What it does not show: another C
library (newlib-nano, a vendor toolchain), calls through pointers inside the library, or
anything about the HAL sources, which are not here. `errno` IS reachable (`__errno`,
`with_errnof`): newlib's single-precision functions set it; the firmware never reads it.

`tools/gen_config.py` reads the YAML keys it needs by name and ignores every other key, so the
mechanical additions of rev C (`pcb.locating_holes`, `tub_keepouts`, `cradle`,
`base_plate.psa`) do not disturb it (checked by generating from a copy of the YAML with extra
keys and from one without the rev C keys: both give the identical header). From rev C it also
exports the grain LED azimuths
(`first_azimuth_deg`, `step_deg`) and the number of ways round the marker fits the cradle
(`GL_CFG_CRADLE_ORIENTATIONS` = 1).

## Conventions (all core modules)

* **Marker frame** (same as `master_params.yaml`): origin at the puck centre on the base plane,
  +x right, +y forward (out of the visor), +z up.
* **Camera frame**: +x right along columns, +y down along rows, +z along the optical axis. Pixel
  centres at integers; row 0 at the top of the upright image.
* **Solver ("device") frame**, identical to the Python reference: +x out of the visor, +y left.
* **Horizontal angles** are radians, counter-clockwise positive seen from above, measured from
  the forward axis: positive = left. **Elevations** are positive upward from the gravity-level
  plane. **Slopes** are rise/run as the uphill gradient vector.
* Units are in names or comments (`_m`, `_mm`, `_px`, `_rad`, `_ms`, `_g`, ...).
* Every fallible function returns `gl_status_t`; 0 is success.
* No function allocates or recurses. Large work areas are supplied by the caller.

## Core modules

| Module | What it does |
|---|---|
| `gl_types.h`, `gl_math.c` | Status codes, vectors / 3x3 matrices, median, little-endian packing. |
| `gl_config.h` | **Generated** from `master_params.yaml`: optics, baseline, display geometry, ball position. |
| `gl_provisional.h` | Every provisional hardware fact and every unmeasured estimate, as named constants. |
| `gl_vision` | Lines on 8-bit luminance strips: horizon-band analysis (per-column edge energy; edge-blind matched vertical-line detector for leans of +-3 degrees at 4 widths, normalised by the spread of each path shape across the band; turf-horizon samples); sub-pixel line fit on the tall strip using only the rows above the local turf edge (per-row centroid of 1, 4 or 16 rows averaged along the line, both polarities, reweighted least squares, outlier rows, significance of the line as a whole); top end with a clutter flag; lower end followed into the turf only as far as it is significant against ghost lines beside it; segment fit with the static (background / fixed-pattern) part of its error; stereo disparity over the L R R L repeats with noise and static uncertainty; quality metrics. It finds LINES; `app/gl_read.c` decides which one is a flagstick. |
| `gl_cam` | Camera model: intrinsics with one radial term, extrinsics to the marker frame, pixel <-> bearing / elevation relative to gravity, rectification, calibrated horizon row. |
| `gl_range` | Stereo + angular-height + manual range, inverse-variance fusion in inverse range, per-course learned stick height, camera-to-ball geometry. |
| `gl_tilt` | Exact integer block averaging with stillness gating, 6-face + cross-axis calibration, temperature polynomial, slope vector / fall line, gyro rotation integrator, the zeroing maths (180-degree reversal with the measured turn angle, `gl_tilt_flip_solve`), Precision Read combining, Survey store. |
| `gl_gesture` | Posture (flat / upright), roll-to-set dial, double tap, half-turn spin. |
| `gl_grain` | Grain front-end maths: dark / on / dark differencing with drift rejection, white-reference gains, first-harmonic vector per colour, validity against a *calibrated* threshold, running average, estimate handed to the solver (zero while grain is disabled, the default). |
| `gl_gfx`, `gl_font_data.c` | 1-bpp 128 x 128 framebuffer in LCD bit order, round clipping to 122 px, thick line from a real-valued angle and point, aim line through the off-screen ball position (also with the ball behind the marker after a Precision spin: `gl_gfx_aim_line_at`; solid or in long dashes for a tentative aim: `gl_gfx_aim_line_styled`; a line that would leave the aperture is replaced by its parallel through the centre IN THE SAME STYLE), `gl_gfx_rotate_180()` (the whole frame turned in place, for a result that is read from behind the marker), 5x7 font, seven-segment large digits, icons, battery, confidence bar, arrows. |
| `gl_ui` | Explicit transition table over the 14 states (SLEEP, WAKE, WAIT_STILL, READ_TILT, CAPTURE, SOLVE, SHOW_RESULT, PRECISION_WAIT_SPIN, SURVEY_NEXT_DROP, SETTINGS_DIAL, CRADLE_USB, CAL_ZERO, ERROR, LOW_BATT), guards, timeouts, one screen per state. The result screen is drawn from `gl_ui_view_t` (aim, ball position, distance, plays-like distance, slope and fall line, break, confidence, one `gl_ui_note_t` message, whether the aim is a solution and whether the marker lies at the ball); `gl_ui_result_text()` returns the strings it shows so that tests compare them glyph for glyph. When the ball lies behind the marker (after the half turn of a Precision Read) the whole result screen is drawn turned by 180 degrees, so that the golfer behind the ball reads it upright. Three rows of the table date from the phase-2 review: a double tap on a `2X` result goes on to the Survey (Precision once per placement), and from the distance prompt a marker that is picked up and put down again starts a new read. `CAL_ZERO` is the rev C zeroing (rev B: `CAL_FLIP`): entered only from the dial, never from the cradle state; a structural test checks that. |
| `gl_proto` | Framed binary USB protocol with CRC-16 and resynchronisation; command dispatch through callbacks. The jump to the ROM bootloader is refused (`GL_ERR_STATE`) unless the `dfu_allowed` callback agrees. |
| `gl_log` | Power-fail-safe ring log on NOR flash and a small blob store (settings, calibration) on the same code; record formats. |
| `gl_settings`, `gl_cal`, `gl_fmt`, `gl_event`, `gl_crc`, `gl_buf.h` | Settings (record **version 2**: units, Stimp, stopping distance past the hole in cm, dialled distance, grain, raw logging, estimator method; a version 1 record is converted, any other version is refused) and the dial item table, calibration records, number formatting, event queue, CRC-16/CCITT-FALSE, bounded serialisation cursors. |
| `gl_solver.h`, `gl_solver.c`, `gl_solver_fit.c`, `gl_solver_aim.c`, `gl_solver_roll.c`, `gl_solver_priv.h` | The putt estimator, a port of the Python reference (structures mirror `Measurements`, `Estimate`, `PatchFit`, `RangeEstimate`, `AimSolution`): range fusion, Levenberg-Marquardt / Huber MAP fit of the quadratic patch with the anchored horizon stage (method B2), RK4 roll kernel with the capture model, nested bracketing aim solver, fallbacks (a kept near miss of the patch if `near_miss_m` is set, secant plane, best iterate, straight), an optional budget on the RK4 steps of one estimate (`max_steps`, firmware only), confidence. Written against `gl_real_t`: `float` in the firmware, `double` with `-DGL_SOLVER_DOUBLE` on the host. See "Solver". |

Public functions are documented in the headers; the header comment of each module states its RAM
and stack use.

### Contracts between core and drivers

* **Framebuffer -> LCD.** `gl_gfx_t.px[y * 16 + (x >> 3)]`, bit `x & 7`, 1 = white. Bit 0 is the
  leftmost pixel, so a row is sent as-is on an LSB-first bus. `gl_gfx_changed_rows()` compares
  with the driver's shadow copy and returns the lines to send.
* **Strips.** `gl_strip_t` is a window of the sensor (`x0`, `y0` = sensor coordinates of its
  first pixel); all vision results are in sensor pixel coordinates.
* **Tilt.** The IMU driver hands raw counts already rotated into marker axes plus the scale
  factors of its range setting (`gl_tilt_cfg_t`); the core never assumes a sensitivity.
* **Flash.** `gl_log` / `gl_store` use `gl_flash_if_t` (read, program, erase-sector callbacks).
  Suggested regions on the 8 MB part: 4 sectors for `gl_store`, the rest for the read log.
* **Events.** While awake `GL_EV_MOTION` must mean sustained movement (about 0.4 s without
  stillness, or a posture change), not a tap, or the double-tap gestures cannot work.
* **Dialled distance.** It is handed to the estimator with every read (`user_distance_m`); the
  estimator uses it only when the cameras give no range (no flagstick, or a flagstick that
  could not be ranged), and the screen then shows it with a question mark. **It belongs to one
  hole**: the application sets it back to "not dialled" after a read that ranged a flagstick,
  and when the marker goes to sleep (the stored setting is cleared with it), and at start-up
  (the copy in RAM, in case a reset came before the sleep).
* **Range means horizontal distance, and there is one of it.** Stereo disparity measures depth
  along the forward axis; `build_measurement_()` hands the estimator `disparity x cos(bearing)`
  (the reference's disparity is f B / distance; 6 % difference at 20 degrees off axis). The
  number shown, logged and solved with is `gl_estimate_t.distance_m`. `gl_range_fuse()` still
  runs in `flag_measured_()`, for learning the stick height and as a diagnostic, and nothing on
  the way to the aim reads its result. A bearing measured by the left camera is referred to the
  ball with `gl_range_from_ball_at()` at the estimator's distance (the 10.0 mm camera offset is
  3.35 mrad at 3 m).
* **Over the repeats.** Each left strip gives its own lowest point, base class, top and horizon
  row. `gl_read` takes the base class most strips agree on (a tie goes to the less committal
  one), averages the lowest point over those strips and reports its uncertainty: the way it was
  found (0.5 row and more when it was placed at the turf edge; not reduced by averaging) plus
  the scatter of the mean. The top is offered for ranging only if it is in the frame and not in
  clutter (`gl_vis_angles_t.top_valid`).
* **What a disparity sigma contains.** `gl_read_result_t.disp.sigma_px` = frame noise (shrinks
  with the groups) + static part (does not) + `GL_PROV_STEREO_CAL_SIGMA_PX` (0.05 px, the same
  in every read of a unit). `gl_range` gets this figure; the estimator has no input for it (it
  assumes 0.08 px, as the reference does), so the application uses it for two things only: the
  3-sigma gate on the disparity and the confidence shown.

## Drivers

Every driver includes only `hal/gl_hal.h` and core headers, keeps its state in a caller-provided
structure, and is tested against the simulator for its exact bus traffic.

| Driver | What it does | What its test checks (`tests/test_drv_*.c`) |
|---|---|---|
| `ov7692` | The two OVM7692 cubes on the shared parallel bus. Power-up: rail enable, settle, PWDN asserted, XVCLK, buses to their peripherals, then one camera at a time: PWDN released, **register 0x0C written first** (pads off), software reset, 0x0C again (the reset re-enables the pads), product id, MIPI off, YUV422, sleep. With PWDN not assumed to tri-state the pads (`GL_PROV_OV7692_PWDN_TRISTATES_OUTPUTS` = 0, the honest default) both sensors' pads are enabled together for 14.4 ms of every power-up, 6.4 ms of it with one of them streaming: the simulator now models and measures this, the test asserts the figure, and firmware cannot remove it (open issue 3). Register 0x0C keeps bit 4 of the reset value (0x90 released / 0x96 driving). Power-down: capture and clock stopped, every camera-facing pin analog or driven low, then the rail. Break-before-make bus ownership; strip window on the sensor (default) or by DCMI crop; Y-only capture through the DCMI byte select. Any error during power-up ends with the rail off. | The pin and register sequence of power-up and power-down record by record; no camera-facing pin moves before the rail has settled; nothing but the rail enable moves after it; 21 power cycles without a rule violation; register values of both window modes; pixel-exact strip contents from both cameras in both modes; settle frames; L R R L timing with unsynchronised sensors; missing camera, wrong product id, reset that never completes, capture time-out: rail off and pins parked every time. |
| `ls013b7dh03` | Sharp memory LCD: SPI mode 0, chip select active HIGH, LSB first, 1 MHz; mode byte, per line address + 16 bytes + 8 dummy bits, 8 more dummy bits; only lines that differ from a shadow copy are sent; DISP and the LPTIM1 EXTCOMIN timer (on: clear, timer, DISP; off: DISP, timer). Both panel mountings (row / column order) selectable. | The exact bytes of a frame for a known image (hand-written expectation), frame length 1 + 18 k + 1, full frame 2306 bytes in 18.5 ms, only changed lines sent, all four mountings pixel by pixel on random images, a UI screen reaching the panel inside the round aperture, on / off order, and that the model catches MSB-first, a clock that is too fast, a bad frame length, DISP without EXTCOMIN and a missing chip-select set-up time. |
| `lsm6dsv16x` | IMU on SPI2, mode 3: WHO_AM_I probe, software reset, BDU + IF_INC; MEASURE mode (accel +-2 g high-performance and gyro +-1000 dps at 240 Hz, data-ready on INT2, LATCHED: CTRL4 is written explicitly); WAKE mode (accel low-power 15 Hz, gyro off, wake-up on INT1); samples mapped into marker axes; temperature only from a sensor that proves it is alive (WHO_AM_I, accelerometer running, raw value not 0x0000 / 0xFFFF); a burst of twelve 0xFF or 0x00 bytes is refused as "no device"; `gl_imu_verify()`. | The exact bytes of init; register values of both modes; scale factors; every axis mapping; 240 data-ready interrupts per second; wake-on-motion latency; absent device; the driver's samples through `gl_tilt` to a slope. |
| `mx25r` | SPI NOR: JEDEC id, read, page program split at 256-byte boundaries with WREN and status polling, 4 kB sector erase, deep power-down with automatic wake; `gl_flash_if_t` for `gl_log` / `gl_store`. | The exact command bytes; page splitting; WREN before every program and erase; deep power-down; the ring log and the blob store running on the driver (3237 page programs, 19 erases, no non-blank byte programmed). |
| `grain_frontend` | 16 LEDs charlieplexed on 5 pins (anode push-pull high, cathode push-pull low, the other three analog; all analog = off; break before make), OPAMP1 + ADC power sequence, dark / on / dark per LED, scan order alternating red / NIR and reversed on odd cycles. | **The pin states of all 16 LEDs** against a table written out independently in the test, the 9 pin operations of each switch in order, that exactly one LED of the model's netlist lights; a sneak-path analysis of the proposed wiring (30 two-LED paths, none NIR-only beside a lit red LED); the ADC sequence with the lit-LED mask of every conversion; values through `gl_grain` (modulation 0.400, azimuth -30.0 deg recovered); drift, motion, threshold from the calibration record. |
| `power` | Battery through the 2 x 1 Mohm divider (VDDA from VREFINT), percent, low / critical / storage; VBUS and charger STAT. **Cell temperature** from the NTC divider (`NTC_BIAS` - 10.0 kohm - `NTC_SENSE` - NTC 10 kohm, B 3380 - ground): one conversion with the bias released (must read near ground, else `STUCK`), bias driven push-pull high, 500 us to settle, 8 conversions, bias back to analog; ratiometric B-parameter conversion; open above 98 % and short below 2 % of full scale. **Charge gate** (`gl_power_charge_gate`): with VBUS, `CHG_INHIBIT` is pulled low (open drain) unless the NTC reading is fresh and passed its checks, at least one live die sensor (IMU, MCU) is within 10 K of it, and it is inside 0..45 C narrowed by a 1.5 K guard band, with 2 K of hysteresis; without VBUS the pin is released. `gl_power_init()` does not touch `CHG_INHIBIT` or `NTC_BIAS`. | That init leaves both pins as reset left them; conversion of battery counts; **the B-parameter conversion against a table computed in the test in double precision** (-40..85 C in 0.5 C steps: worst error 0.011 K; the simulator's NTC model agrees with the same table to 2e-12 counts); the tolerance budget (NTC 1 %, B 1 %, resistor 1 %, ADC 0.2 % of full scale: 0.90 K at 0 C, 1.09 K at 45 C, inside the 1.5 K guard); the exact pin and ADC sequence of a measurement (`NTC_BIAS` driven for 684 us); open, short and stuck-high detection; the gate over a sweep of -10..60 C and back (allowed 3.5..43.5 C rising, 1.5..41.5 C falling); unknown, stale, faulty and implausible temperatures; the simulator's charger model and its rules; status pins and interrupts. |

Notes for the hardware review that came out of writing the drivers:

* **Grain LED current.** With the 2.8 V rail and two 68 ohm resistors in the path the LED
  current is about (2.8 - 2.0) / 136 = 6 mA for red and about 10 mA for NIR, not the 20 mA that
  `docs/research/grain-sensing.md` assumes.
* **Charlieplex wiring is a proposal** (no netlist exists): pair k on the pin pairs (0,1) (0,2)
  (0,3) (0,4) (1,2) (1,3) (1,4) (2,3), red anode on the lower-numbered pin, NIR antiparallel.
  With that orientation rule no two-LED sneak path beside a lit red LED consists of NIR LEDs
  only (checked by the test), so the low-voltage NIR LEDs cannot ghost.
* **OVM7692 output size after reset.** The comments of the public driver give 0x180 (384 lines)
  as the reset value of the vertical output size. The driver therefore never relies on reset
  values for the frame size: in sensor-windowing mode it writes input and output size with every
  window, in DCMI-crop mode it writes the full 640 x 480 at power-up. The camera model resets to
  384 lines so that the test would catch a driver that forgot.
* **Idle camera during L R R L.** DESIGN_SPEC says the idle camera is tri-stated *and held in
  sleep*. The driver tri-states it (register 0x0C) but keeps it awake during the sequence,
  because the number of frames a sensor needs after waking is unknown and would be paid on every
  switch (`GL_PROV_CAM_SLEEP_IDLE_ON_EVERY_SWITCH` = 0; set to 1 for the literal behaviour).

## HAL: interface, simulator, STM32U5 backend

`hal/gl_hal.h` is plain blocking C functions on LOGICAL pins and buses. Chip selects, PWDN, DISP
and the charlieplex pins are ordinary GPIOs driven by the drivers, so that the simulator can see
the exact pin sequences. Interrupt sources only latch a bit in a pending mask that the main loop
collects.

### Host simulator (`hal/host`)

A model of the board as seen from the MCU pins, with **simulated time**: time passes in
delays, in sleep, for the duration of bus transfers and conversions, and - from builder 3 -
**for computation**. Every pin change, bus transfer, register access and sleep is recorded in
a trace (up to 262144 records, with the SPI bytes) that tests inspect.

**Compute-time model.** The firmware reports the end of each heavy stage to the HAL with what
it did (`gl_hal_trace(point, work)`: the band with its pixel count; a strip with which
refinements were tried - 1, 4, 16 rows binned -, whether a line was found, whether it was wide,
whether the strip statistics ran; a group; the estimate with its RK4 steps; a rendering). On
the target the call does nothing. The simulator looks the stage up in `gl_sim_cost.h` - host
instruction counts measured with callgrind, table under "Run time" - and lets

    time = instructions x cycles per instruction / core clock in effect (160 or 48 MHz)

pass before the firmware continues, so that frames go by, the IMU keeps sampling and the
camera rail stays on while the firmware "computes". **The cycles-per-instruction factor is an
estimate, not a measurement**: 1.5 (low), 2.0 (nominal, the default of every test), 3.0 (high);
what it stands for and why the range is this wide is under "Run time". `gl_sim_set_cpi(0)`
gives the old behaviour (computation for nothing). What is still free: everything between the
trace points - the main loop, the drivers, the IMU filtering (a few hundred instructions per
sample).

**Supply model.** The simulator also integrates a current for every state of the board (MCU
run / idle / Stop 2 at either clock, camera rail, IMU mode, LCD, flash, ADC, op-amp, grain
LED): `gl_sim_stats_t.charge_*`. **Every current is PROVISIONAL** - from memory of the data
sheets or from the unverified figures of `docs/research` (`GL_SIM_I_*` in `gl_sim.h`) - so
the charge figures of this file say how the measured TIMES translate into charge under those
assumptions; they are not measurements.

It models: the LCD (decodes frames into a panel memory), the flash (8 MB, NOR semantics, busy
times, deep power-down), the IMU (register map, sample generator driven by a motion function of
the test, wake-up and data-ready interrupts, mounting, noise, bias, temperature), two cameras on
the shared bus (registers, reset, sleep, output enables, windows, free-running frame timing with
a phase offset between the sensors, frames from a scene callback), the battery divider, the
photodiode stage driven by the charlieplex pin states, a USB host, and from rev C2: the cell
NTC and its divider (cell temperature set by the test, part tolerances, open / short / stuck
faults, a conversion sees the divider only while `NTC_BIAS` is driven and settled), the charger
(running whenever VBUS is present and `CHG_INHIBIT` is not pulled low, whatever the MCU does),
the board's pull resistors on the chip selects, DISP and the rail enable, an MCU reset
(`gl_sim_mcu_reset`: every pin back to analog, the charger back to its default), and the core
clock as a recorded state.

It **checks**, and counts as violations (all tests require zero):

* the camera rail rule: every camera-facing pin analog or driven low while V2V8_CAM is off and
  for 1 ms after it is switched on; SCCB to an unpowered, unclocked or powered-down camera;
  both cameras driving the shared bus; a capture with no camera driving;
* LCD protocol: active-high chip select, LSB first, mode 0, at most 1.1 MHz, frame length, line
  addresses, chip-select timing, DISP without EXTCOMIN;
* flash protocol: program or erase without WREN, commands while busy or in deep power-down,
  page overflow; IMU SPI mode; both SPI1 chip selects active, transfers with no device selected;
* Stop mode with the camera rail on, a capture running, USB started, the ADC or op-amp powered
  or a chip select asserted; more than one grain LED lit; ADC use while unpowered; the watchdog
  not refreshed for 32 s; a sleep that nothing could ever end;
* power rules: USB started without VBUS when the MCU goes to sleep; EXTCOMIN outside 1-60 Hz
  (547..606 LSE ticks accepted);
* charger rules (rev C2; the phase-1 rule "charger enabled at Stop entry" is gone, because the
  charger is now ON by default and must stay able to start by itself): Stop mode with
  `CHG_INHIBIT` held low and no VBUS (a sleeping marker would then refuse the next cradle);
  Stop mode in the cradle with no wake-up source due within 10 s (nobody would be watching the
  cell); the charger running for more than 10 s outside 0..45 C while the firmware runs;
  `CHG_INHIBIT` driven push-pull; an internal pull enabled against a board pull;
* NTC rules: a conversion of the NTC channel less than 300 us after the bias was driven;
  `NTC_BIAS` still driven at Stop entry;
* clock rules: Stop mode with the core clock fast; and it counts vision and solver trace points
  that ran at the slow clock (`heavy_while_slow`, asserted to be 0 by the end-to-end tests).

It also MEASURES what it cannot forbid: the time both cameras' pads are enabled during power-up
(`cam_powerup_overlap_us`), how long the charger ran in all, outside the temperature window
(total and longest stretch) and during reset, how long `CHG_INHIBIT` was held and `NTC_BIAS`
driven, the number of clock switches and the time at the fast clock, the computation charged per stage
and the charge drawn; and it can charge a FIXED time at a trace point instead of the model's
(`gl_sim_set_compute_us()`), drop interrupt latches (also the one of a VBUS edge), fail SPI
transfers, glitch the IMU's supply and let the switch back to the slow clock fail
(`gl_sim_clock_fail_slow()`: `gl_hal_clock_set()` then returns `GL_ERR_IO` and the clock stays
fast, the contract `gl_hal.h` states for a PLL that will not let go), which is what
`tests/test_e2e_faults.c` and `tests/test_e2e_review.c` use.

`tests/test_e2e.c` adds an **independent** check of the camera rail rule: it replays the
recorded pin trace with its own model and counts moments at which a camera-facing pin is neither
analog nor driven low while the rail is off, and bus accesses with the rail off.

### STM32U5 backend (`hal/stm32u5`) - compiled against the vendor's headers, never linked or run

| File | Content |
|---|---|
| `gl_pins.h` | **Generated** by `tools/gen_pins.py`: logical pin -> port, pin, LQFP-64 pad, function, AF number, source. 19 rows are SPEC (DESIGN_SPEC section 4: the eleven DCMI pins, MCO, SPI1 MISO, USB D-/D+, LPTIM1_CH1, the three OPAMP1 pins); the generator parses the spec text and refuses to generate if a SPEC row disagrees. **28 rows are PROPOSED** by this firmware because no netlist exists: SPI1 SCK / MOSI (PA5 / PA7), SPI2 (PB13 / PB14 / PB15), chip selects, IMU INT1 on PC13 (WKUP2) and INT2 on PC5, the camera rail enable, PWDN and SCCB lines, the five charlieplex pins, VBAT sense on PA2, VBUS and charger STAT, and the three rev C2 signals `CHG_INHIBIT` (PH1), `NTC_BIAS` (PH3-BOOT0) and `NTC_SENSE` (PC4, ADC1_IN13). Pads outside the verified list come from the LQFP-64 pinout as remembered; AF5 for the SPI pins, ADC1_IN7 for PA2 and ADC1_IN13 for PC4 are from memory. The generator carries the pins the ROM bootloader drives or samples (22 pins, **from memory of AN2606**, 6 of them driven) and refuses a PROPOSED camera-facing, charger or NTC pin on any of them; it reads the pins rev C2 forbids for PWDN (PA9, PA2, PC10) from the spec and refuses a PWDN row on them (PWDN is on PH0 and PC12); it reads the EXTCOMIN divider (547) from the spec and emits `GL_PINS_EXTCOMIN_LSE_TICKS`; it emits the levels the board's pulls give the chip selects, DISP and the rail enable during reset (`GL_PINS_RESET_TABLE`), which the simulator and `tests/test_board.c` use. **Pin budget:** the package has 46 usable I/O pads and rev C2 needs 47 signals, so one signal had to go on PH3-BOOT0: the generator checks the count, and `NTC_BIAS` was chosen because both its loads pull the pin low at reset (see "Board changes of rev C2"). The fourth charlieplex pin moved from PC4 to PC10 to free an ADC input for the NTC. Two SPEC rows remain on bootloader pins (PB9 = D7, PA6 = PIXCLK): a release gate for the netlist, see open issue 4. |
| `gl_hal_stm32u5.c` | Clocks (MSIS 48 MHz trimmed against LSE; **rev C2: `gl_hal_clock_set()` switches SYSCLK to PLL1 at 160 MHz and back** - PLL1 from MSIS / 3 x 20 / 2; up: voltage range 1 with the EPOD booster, PLL locked, then SYSCLK with flash latency 4; down: SYSCLK back to MSIS, PLL off, then the lower voltage range; a PLL that does not lock leaves the slow clock and is not an error; SPI1, SPI2 and the ADC take their kernel clock from MSIK so that their timing does not move; `gl_hal_delay_us()` scales with the clock; Stop mode is refused (idle sleep instead) while the clock is fast; XVCLK = MSI / 4 on MCO), tick on LPTIM3 from LSE (runs through Stop 2), RTC seconds and RTC wake-up timer, GPIO from the pin table, EXTI sources, Stop 2 / sleep that returns only for an enabled source and cannot lose a wake-up, SPI1 / SPI2, **bit-banged SCCB** (two clock lines for two sensors at one address: no I2C peripheral can do that), DCMI snapshot with crop + byte select through GPDMA, ADC1 14-bit, OPAMP1 standalone, LPTIM1 PWM for EXTCOMIN, independent watchdog (32 s), unique id, reboot, jump to the ROM DFU bootloader through a backup-register flag (taken only if VBUS is present, so a marker in a pocket cannot be parked in the ROM). After the review: the interrupt latch is updated with interrupts masked (a lost IMU data-ready used to be possible), `gl_hal_extcomin_stop()` and the op-amp stop are safe before their start, the DCMI frame-end time is latched in the interrupt, the die temperature sensor is read, ICACHE is enabled. Rev C2: the NTC channel (ADC1_IN13), `CHG_INHIBIT` and `NTC_BIAS` left analog by `gl_hal_init()`, the chip selects taken over at the level of their pulls (output latch written before the mode). **Phase-2 review, by inspection** (it compiles; a test checks the order in the source text; none of it has run): the independent watchdog is the FIRST thing `gl_hal_init()` starts, the function has ONE return, and a failure of a later step is remembered and returned at the end with the watchdog running (it used to return before the watchdog was started, and the application's error loop then ran for ever with the charger on); a crystal that does not start is survived on LSI (tick, RTC and EXTCOMIN about 2.4 % off and untrimmed MSIS: reported as `GL_ERR_TIMEOUT`); the way back from the fast clock returns a status (`GL_ERR_IO`, still fast, if SYSCLK will not switch); `gl_hal_delay_ms()` / `_us()` are bounded loops; the HAL tick is resumed BEFORE the clocks are re-initialised after Stop 2 (the HAL's time-outs need it); the comment about DFU and the charger says what the code does. The PLL / booster / latency sequence in particular is written from memory of the reference manual. |
| `gl_hal_stm32u5_usb.c` | CDC-ACM on ST's USB device library: HSI48 + clock recovery, VDDUSB supply-valid only after VBUS was seen, byte rings, flow control by NAK. |

**What was done (builder 3).** `gl_hal_stm32u5.c` is compiled - `arm-none-eabi-gcc -c`, nothing
linked, nothing run - against the header files of three public repositories, fetched from
`raw.githubusercontent.com` at fixed tags into a scratch directory **outside this repository**
(header and device-description files only; no HAL source, no start-up code, no example). The
headers are data: nothing in that directory is executed and nothing from it is copied here.

```
make cross-hal STM32_HEADERS=<dir>

<dir>/cmsis_device_u5/Include/        stm32u5xx.h stm32u585xx.h system_stm32u5xx.h
<dir>/stm32u5xx_hal_driver/Inc/       stm32u5xx_hal*.h stm32u5xx_ll_*.h Legacy/stm32_hal_legacy.h
<dir>/CMSIS_5/CMSIS/Core/Include/     core_cm33.h cmsis_version.h cmsis_compiler.h cmsis_gcc.h mpu_armv8.h
```

Flags: the firmware's warning set with `-Werror` (`-Wall -Wextra -Wpedantic -Wshadow
-Wconversion -Wdouble-promotion -Wvla -Wmissing-prototypes -Wstrict-prototypes -Wundef`),
`-mcpu=cortex-m33 -mthumb -mfpu=fpv5-sp-d16 -mfloat-abi=hard -Os -DSTM32U585xx
-DUSE_HAL_DRIVER`; the vendor headers are included with `-isystem`, so the warnings are
judged on this project's code. `stm32u5xx_hal_conf.h` is the project's own file (every Cube
project supplies one); it is written here, not copied from ST's template, and enables exactly
the modules the backend calls.

**The 41 files it was compiled against** (STM32CubeU5 HAL driver v1.6.1, CMSIS device
package v1.4.1, CMSIS 5.9.0):

| Repository (github.com) | Tag | File | Bytes | SHA-256 (first 16 hex digits) |
|---|---|---|---|---|
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_conf_template.h` | 19769 | `a761a1c98d22aa0d` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal.h` | 39344 | `be0aa206bbdbd4be` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_def.h` | 7638 | `73a911c835b4c7f7` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/Legacy/stm32_hal_legacy.h` | 240589 | `7fff96faed90c813` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_rcc.h` | 249026 | `1006c48ca927ada2` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_rcc_ex.h` | 122138 | `79e433bc3ff360f1` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_gpio.h` | 16246 | `6d9e6c1abe6303f3` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_gpio_ex.h` | 16959 | `40848fe334a9252b` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_icache.h` | 9541 | `18aa44e01f694413` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_dma.h` | 45368 | `0d4f824e30374332` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_dma_ex.h` | 38773 | `bfe6f1435f362fd4` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_cortex.h` | 16590 | `d839d550236888f6` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_adc.h` | 161245 | `72a33bd9bd42e6a6` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_ll_adc.h` | 533842 | `1538f159a0b4b15b` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_adc_ex.h` | 84028 | `b2acc7d3c97a248a` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_flash.h` | 56604 | `e59f8e71dee58b4b` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_flash_ex.h` | 8978 | `8943fc2f847e40a8` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_iwdg.h` | 9899 | `28f4133413f1c0a7` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_lptim.h` | 59662 | `4c024efe65c72aad` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_ll_lptim.h` | 94415 | `e94a56981606821a` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_opamp.h` | 16946 | `cb5a5ab367616e96` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_opamp_ex.h` | 2179 | `82cc8fd42201a9c8` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_pwr.h` | 49154 | `d1b3888b86f2c25b` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_pwr_ex.h` | 46635 | `dd70ff0d9345914c` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_rtc.h` | 46370 | `92a7b0baff657fa0` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_rtc_ex.h` | 92645 | `1f7014ba621c8ab7` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_spi.h` | 58360 | `786f1dd29f4b5020` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_spi_ex.h` | 11381 | `c15da1ec3dc4f092` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_exti.h` | 15753 | `271badb9ab523a4f` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_dcmi.h` | 28975 | `725046175e4eb495` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_pcd.h` | 26414 | `401e2ceb09a42bc5` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_ll_usb.h` | 46803 | `ef829dd79eced900` |
| `STMicroelectronics/stm32u5xx_hal_driver` | `v1.6.1` | `Inc/stm32u5xx_hal_pcd_ex.h` | 2858 | `57ca135317a8b122` |
| `STMicroelectronics/cmsis_device_u5` | `v1.4.1` | `Include/stm32u5xx.h` | 10767 | `9c6f99860a416806` |
| `STMicroelectronics/cmsis_device_u5` | `v1.4.1` | `Include/stm32u585xx.h` | 2065354 | `c7b606a2868c4c4e` |
| `STMicroelectronics/cmsis_device_u5` | `v1.4.1` | `Include/system_stm32u5xx.h` | 2713 | `73675e7a1dfd4a63` |
| `ARM-software/CMSIS_5` | `5.9.0` | `CMSIS/Core/Include/core_cm33.h` | 189524 | `225c47c36230edaa` |
| `ARM-software/CMSIS_5` | `5.9.0` | `CMSIS/Core/Include/cmsis_version.h` | 1680 | `184c19fd3ee73632` |
| `ARM-software/CMSIS_5` | `5.9.0` | `CMSIS/Core/Include/cmsis_compiler.h` | 9481 | `b51963d271c1571c` |
| `ARM-software/CMSIS_5` | `5.9.0` | `CMSIS/Core/Include/cmsis_gcc.h` | 63374 | `43bfd1fe69fbbc2c` |
| `ARM-software/CMSIS_5` | `5.9.0` | `CMSIS/Core/Include/mpu_armv8.h` | 11370 | `2c7d22a344cedcc1` |

(`stm32u5xx_hal_conf_template.h` was fetched to read, and is not included by anything.)

**Result of the compile** (`make cross-hal`, this session):

* The first compile stopped on **two identifiers that do not exist in this form**:
  `__HAL_ADC_CALC_VREFANALOG_VOLTAGE` takes the ADC instance as its first argument on the U5
  (3 arguments, 2 were given), and the op-amp power mode is
  `OPAMP_POWERMODE_NORMALPOWER_NORMALSPEED` (`OPAMP_POWERMODE_NORMAL` does not exist). Both
  are fixed. **Two more compiled only through ST's legacy alias header** and were replaced by
  the current names: `GPDMA1_REQUEST_DCMI` -> `GPDMA1_REQUEST_DCMI_PSSI`,
  `ADC_SAMPLETIME_391CYCLES_5` -> `ADC_SAMPLETIME_391CYCLES`. Everything else - about 70 HAL
  functions, the handle and init structures, the interrupt names, the RCC / PWR / LPTIM / RTC /
  DCMI / GPDMA constants - compiled as written from memory.
* It compiles **warning-free** (this session, after the phase-2 review's changes to the
  file): text 6660, data 5, bss 1011 bytes; largest frames `clocks_init_` 248,
  `gl_hal_clock_set` 144, `clocks_osc_` 112 bytes; no double-precision helper, no heap, no
  stdio. It references `__aeabi_ldivmod` / `__aeabi_uldivmod` (64-bit divisions in the tick
  arithmetic; from libgcc at link time) and `memset`.
* The MEANING of the entries of the identifier map was then compared with the comments of the
  headers: MSIS / MSIK range 0 = 48 MHz; PLL input range 1 = 8-16 MHz (the 16 MHz this file
  feeds it is at the edge of that range); `DCMI_BSM_OTHER` / `DCMI_OEBS_ODD` / `_EVEN`; the ADC
  sampling times; the RTC wake-up clock; the temperature and VREFINT calibration at 14 bits and
  3.0 V, with this file's formula identical to ST's macro. One inconsistency **inside ST's
  header** was seen and not resolved: the comment of `TEMPSENSOR_CAL2_ADDR` says 110 C, the
  constant `TEMPSENSOR_CAL2_TEMP` is 130 (the firmware uses the constant).
* The EXTI vectors and the ADC channels are now tied to the generated pin table at compile
  time: moving one of the four interrupt pins in `tools/gen_pins.py` stops the compile
  (checked with a scratch copy: "size of array 'glh_imu_int1_is_exti13_' is negative").
* The object needs 71 HAL functions (listed by `make cross-hal`; `HAL_GetTick` is new, for
  the bounded delay) and `SystemCoreClockUpdate` of the system file, and defines the handlers
  `DCMI_PSSI_IRQHandler`, `EXTI0/5/9/13_IRQHandler`, `GPDMA1_Channel0_IRQHandler`,
  `LPTIM3_IRQHandler`, `RTC_IRQHandler`, `SysTick_Handler` - names taken from memory that a
  link against the start-up file's vector table would confirm or refute. **Not confirmed.**

**`gl_hal_stm32u5_usb.c` was NOT compiled**: it includes `usbd_core.h` and `usbd_cdc.h` of ST's
USB device library, which is in none of the three repositories. It is as unverified as before.

**What a person needs to produce a flashable image** (none of it is here, and none of it was
downloaded):

1. **STM32CubeU5** (the HAL release above or a later one - recompile and re-read the warnings
   if later): the HAL sources `stm32u5xx_hal.c`, `_hal_cortex.c`, `_hal_rcc.c`, `_hal_rcc_ex.c`,
   `_hal_pwr.c`, `_hal_pwr_ex.c`, `_hal_flash.c`, `_hal_flash_ex.c`, `_hal_gpio.c`,
   `_hal_exti.c`, `_hal_icache.c`, `_hal_iwdg.c`, `_hal_lptim.c`, `_hal_rtc.c`, `_hal_rtc_ex.c`,
   `_hal_spi.c`, `_hal_spi_ex.c`, `_hal_dma.c`, `_hal_dma_ex.c`, `_hal_dcmi.c`, `_hal_adc.c`,
   `_hal_adc_ex.c`, `_hal_opamp.c`, `_hal_opamp_ex.c`, and for USB `_hal_pcd.c`, `_hal_pcd_ex.c`,
   `stm32u5xx_ll_usb.c` (the list follows the modules enabled in `stm32u5xx_hal_conf.h`; the
   exact file a function lives in was not checked, no HAL source was read).
2. **Start-up code and system file**: `startup_stm32u585xx.s` (GCC flavour: vector table,
   reset handler, data / bss initialisation) and `system_stm32u5xx.c` (`SystemInit`,
   `SystemCoreClock`) from the CMSIS device package.
3. **A linker script** for the STM32U585RIT6: 2 MB flash at 0x08000000; SRAM1 192 kB at
   0x20000000, SRAM2 64 kB at 0x20030000, SRAM3 512 kB at 0x20040000 (sizes and addresses as
   the device header states them). The firmware's static data is 0.32 MB (`gl_app_t` alone
   320904 bytes): it does NOT fit SRAM1 + SRAM2, so `.bss` must reach into SRAM3 (the three
   regions are contiguous). That SRAM3 is clocked after reset and retained in Stop 2 without
   further action is how the part is remembered - **not verified**, and the backend touches
   neither setting. A hard fault at the first access to `.bss`, or data lost over the first
   sleep, would be the symptom.
4. **ST's USB device library** (core + CDC class) and the board glue the backend's USB file
   expects: `usbd_conf.c` (PCD low-level callbacks, `HAL_PCD_MspInit`, `OTG_FS_IRQHandler`),
   `usbd_desc.c` exporting `GL_USBD_Desc`, and an assigned VID / PID.
5. **`main()`** is `app/gl_main.c`. The backend defines `SysTick_Handler` and the interrupt
   handlers listed above itself, and relies on the HAL's default `HAL_InitTick`; the
   interrupt and MSP files of a generated Cube project must not define the same handlers a
   second time. No stdio is used: nothing of the C library's formatted output is wanted.
6. Link with `-mcpu=cortex-m33 -mthumb -mfpu=fpv5-sp-d16 -mfloat-abi=hard`, newlib-nano and
   `-Wl,--gc-sections`; then flash over SWD, or over USB with the ROM bootloader (DFU).

**What remains unverified until it runs on a board** - everything about behaviour:

* that it links at all (the handler names against the vector table, the HAL functions against
  the HAL sources, the weak callbacks' signatures as the HAL calls them);
* the clock sequences: MSIS 48 MHz with LSE trimming; PLL1 at 160 MHz with voltage range 1,
  the EPOD booster and 4 flash wait states, and the way back; kernel clocks from MSIK;
* Stop 2: entry and wake-up by the RTC timer and the four EXTI lines, LPTIM3 counting through
  it (the tick), LPTIM1 PWM continuing through it (EXTCOMIN), the independent watchdog
  running through it, wake-up fast enough for a 240 Hz data-ready interrupt;
* DCMI crop and byte-select semantics, the sync polarities, GPDMA with 32-bit words, both
  strip sizes (61440 and 46080 bytes, below 64 kB and multiples of 4 by design; a compile-time
  check in `app/gl_read.c` keeps it that way);
* the bit-banged SCCB timing, SPI modes and rates, the ADC sampling times against the source
  impedances, the op-amp configuration, the calibration arithmetic on real calibration words;
* the ADC channel numbers of PA2 and PC4 and the system-memory address of the ROM bootloader
  (from memory; no header states them);
* the reboot into the ROM bootloader, the backup-register flags, the interrupt-latch scheme
  under real preemption;
* **the run time of everything** - the cycles-per-instruction factor of the compute-time model
  (`gl_hal_trace()` is an empty function on the target; a bench build can toggle a pin or
  read the cycle counter there to measure each stage) - and every supply current.

## Application (`app/`)

* **Main loop** (`gl_app.c`). One object (`gl_app_t`, static), one loop, no RTOS, no heap, no
  second context. Sleep policy: Stop 2 whenever nothing needs fast clocks - asleep, and also
  between IMU samples while a result is shown; idle sleep while the camera rail is on, USB is
  running or the core clock is fast (the simulator counts any other combination as a
  violation).
* **Core clock** (rev C2). `gl_hal_clock_set(GL_CLOCK_FAST)` when the capture starts,
  `GL_CLOCK_SLOW` when the solve is done, and on every way out in between (abort by motion,
  camera error, time-out; a last check in the main loop drops a fast clock that no read is
  using). The compute-heavy part of a read is exactly what lies between the two calls: the
  vision on the band and on every strip, and the putt solve. Measured on the simulator: fast
  for 2545 ms of a Quick Read (1602 ms with computation for nothing), 33 vision trace points and the solve inside, none outside;
  equally many switches up and down in every end-to-end test; never Stop mode in between. If
  the switch up fails, the read runs at the slow clock (counted in `clock_fails`). If the
  switch BACK fails (`GL_ERR_IO`: the backend reports that SYSCLK did not leave the PLL), the
  application does not believe that it happened: it counts the failure, goes on treating the
  clock as fast - so no Stop mode - and tries again in the next loop pass (three failed
  switches in a row during a Quick Read: `clock_fails` 3, clock slow afterwards, no
  violation; before the review the same run entered Stop mode with the fast clock 482 times).
* **Motion** (`gl_motion.c`). 240 Hz samples in 32-sample blocks. `GL_EV_STILL`: flat and 4
  still blocks. `GL_EV_MOTION` depends on the state: during a tilt read or a capture ANY moving
  block aborts the read; otherwise only real movement counts (posture left FLAT, gravity
  direction displaced by more than 0.05 g for 2 blocks, or 8 moving blocks), so that double taps
  remain gestures. Double tap, the roll-to-set dial and the 180-degree spin come from
  `core/gl_gesture`.
* **Read** (`gl_read.c`). A step machine that never waits for a frame. A whole L R R L group
  is captured into four strip buffers before any of it is analysed (the spacing of the four
  exposures is the sensors', however long the vision takes), then analysed one strip per loop
  pass; the UI's capture limit is a limit on time WITHOUT PROGRESS. The rail is switched off
  when the last strip is in memory and on every error or abort. **Timing of L R R L:** the
  sensors free-run (42 / 33 / 58 ms with a 9 ms phase offset); the frame-end time of every strip
  is latched in the DCMI interrupt and the left positions are moved to the mean time of the
  right pair along the left camera's own sway rate. **Which line:** a band "line" that is only
  the shoulder of a much stronger one is dropped first (`drop_shoulders_()`: a flagstick 2.6
  to 4.4 px wide also answers the widest line template 9 px beside itself, with a tenth of its
  score; dropped if a line at least `GL_APP_SHOULDER_SCORE_RATIO` = 4 times stronger lies
  within the candidate's own template width). With several candidates left, each gets one
  group and a verdict before one is read in full; a lone candidate is read at once, and given
  up after its first group if that group already says it is not a flagstick. **Is it a
  flagstick:** a line is accepted only if its width fits its disparity (a 12.7-19 mm stick is
  0.64-0.95 x its disparity wide at any range with the 20 mm baseline), its height fits its
  disparity (1.0-3.2 m when both ends are in the strip), it is at least 60 times as tall as
  wide, it is within 40 m, and the background beside it does not put more than 0.5 px on its
  position. **Tiers:** stereo read; left camera only (bearing and elevations; the estimator ranges
  it from the stick's angular height if top and base are visible, otherwise it is "flag found,
  range not available": the dialled distance along the measured bearing); band-only bearing
  (counted by the read tests; the application treats it as "no flagstick": it is neither
  aimed at nor logged - the read record carries a bearing only for a flagstick); nothing,
  with a reason.
* **Measurement hand-over** (`build_measurement_()`, the one place where firmware quantities
  become solver inputs). The rule is GATE, DO NOT SYNTHESISE:

  | Read | What the estimator gets | What it does |
  |---|---|---|
  | stereo pair, disparity at least 3 sigma above zero | bearing, disparity x cos(bearing), lowest point, base flag (strict), top if in the frame and not in clutter, horizon samples, dialled distance | ranges the flag itself (`gl_solver_fuse_range`) |
  | left camera only, or a disparity below 3 sigma | the same with the disparity "not available" | ranges from the stick's angular height if top and base are visible; else `range_missing`: the dialled distance, else its 3 m default, along the MEASURED bearing |
  | stick top in clutter or out of the frame | top "not visible" | no angular-height range |
  | no flagstick | `flag_found` false, dialled distance | `flag_missing`: tilt-only plane along the visor axis |

  Nothing is passed that the cameras did not measure; a left-camera-only read is no longer
  turned into "no flag" (its bearing is kept). The bearing is referred to the ball with the
  distance the estimator will use.
* **Result on the display** (`compose_view_()` -> `gl_ui_view_t` -> `gl_ui.c`). What is shown,
  top to bottom: distance in the selected unit (`?` appended when it was dialled or assumed,
  `--` when nobody measured or dialled it); `PLAYS n`: **the length of the putt on a flat
  green that needs the same stroke** - the estimator's roll-out distance minus the PAST
  setting, so a dead-flat 6 m putt shows `PLAYS 6.0M` at PAST 0, 30 and 90 cm (it used to show
  the roll-out, PAST included: 6.3 m at the default); only for a solved putt, and with a
  question mark (`PLAYS n?`) when the base of the flagstick was hidden, because the height of
  the hole is then a bound and not a measurement; one message; the fall-line arrow in a rose
  beside the line with the slope in percent under it; the break in cup widths with the side to
  aim at (`<2.7 CUP` = aim 2.7 cups LEFT of the hole, `2.3 CUP>` = right, `STRAIGHT`, or
  `BREAK ?`); five confidence boxes; `2X` for a Precision Read, `Dn` for the n-th Survey drop.
  **Sign chain, with numbers from `tests/test_e2e_putt.c`:** green rising 2 % to the golfer's
  left, 3 m: device tilt y +0.020, estimator aim azimuth +129.2 mrad (counter-clockwise from
  the visor axis = left), break +2.7 cups, label `<2.7 CUP`, line fitted from the panel's
  pixels at +129.1 mrad, crossing the screen RIGHT of its centre (the line is the backward
  extension of the start line through the ball, which lies 246 px above the centre of the
  screen), fall-line arrow pointing right; the mirror image for a green rising to the right
  (-103.5 mrad, `2.3 CUP>`, -103.0 mrad drawn). Uphill 1.5 % at 6 m: `19.6FT`, `PLAYS
  23.3FT?`; downhill 2 %: `PLAYS 14.5FT?`.

  **What an abnormal result looks like - and which ones look normal.** (This table used to be
  headed "never a normal-looking line for an abnormal result". That was not true: the rows
  marked "looks normal" differ from a clean result by one word of text only.)

  | Estimator says | Message | Line | Break | Confidence shown |
  |---|---|---|---|---|
  | aim from the patch, solved, fit converged | none | solid | quoted | estimator's x camera factors |
  | the same, base of the flagstick hidden (`base_hidden`) | none; `PLAYS n?` | solid | quoted | estimator's. **Looks normal** but for the question mark |
  | the same, read by the left camera only / second line in view | `1 CAMERA` / `2 LINES SEEN` | solid | quoted | x 0.6 each. **Looks normal** but for the message |
  | fit stopped on its iteration limit | `FIT NOT DONE` | solid | quoted | x 0.7. **Looks normal** but for the message |
  | poor horizon (method B2 only) | `POOR HORIZON` | solid | quoted | estimator's (its own factor is 0.8). **Looks normal** but for the message |
  | pace limited (`solve_status` 1) | `PACE LIMIT` | solid | quoted | estimator's. **Looks normal** but for the message |
  | aim from the secant plane (`aim_source` 1), or a near miss of the patch solve that was kept (`aim_source` 0 with a failing status, within 5 mm of the hole centre) | `APPROX` | solid | quoted | estimator's (scored as a fallback). **Looks normal** but for the message |
  | `range_missing`, distance dialled | `NO RANGE`, distance with `?` | solid | quoted | estimator's (which has its own factor for the missing range), x 0.6 if one camera read the stick |
  | `range_missing`, nothing dialled (solved for the estimator's 3 m default) | `NO RANGE`, distance `--` | **dashed** | `BREAK ?`, no plays-like | as above |
  | `flag_missing`, distance dialled (flag out) | `NO FLAG` and the no-flag icon, distance with `?` | **dashed**, from the visor axis | quoted | **at most 0.09: no box** |
  | no flagstick and nothing dialled | no result: the UI shows the distance item of the dial under `NO FLAG`, with `OR PLACE AGAIN` (picking the marker up and putting it down starts a new read; the prompt used to be a dead end for 30 s) | | | |
  | best effort (`aim_source` 2: no convergence, no bracket, step budget spent) | `NOT SOLVED` | **dashed** | `BREAK ?`, no plays-like | at most 0.2 (one box) |
  | straight for want of anything (`aim_source` 3) | `NO SOLUTION` | **dashed** | `BREAK ?`, no plays-like | 0 (no box) |
  | Survey, marker not at the ball | `PUT AT BALL` | **none** | quoted | as computed |
  | estimator refused (`GL_ERR_PARAM`, `GL_ERR_RANGE`) | error screen | none | | |

  The most serious condition gives the one message, in this order: `PUT AT BALL`, `NO
  SOLUTION`, `NOT SOLVED`, `NO FLAG`, `NO RANGE`, `APPROX`, `PACE LIMIT`, `FIT NOT DONE`,
  `POOR HORIZON`, `1 CAMERA`, `2 LINES SEEN`. A line more than about 13.5 degrees off the
  visor axis leaves the aperture: its parallel through the centre replaces it, **solid if the
  aim is a solution and dashed if it is not** (it used to be dashed whatever the result, with
  a large arrow on the side the line leaves the screen, which is the side opposite the aim;
  the arrow is gone).

  **Confidence shown** (`shown_confidence_()`): the estimator's confidence, x 0.6 if the
  flagstick was measured by the left camera only, x 0.6 if another line in view also passed as
  a flagstick, x clamp(0.08 px / the read's disparity sigma, 0.5, 1) (the estimator assumes
  0.08 px whatever the read claims), x 0.7 if the fit did not converge; capped at 0.2 for a
  best-effort aim and at 0.09 for a flag-out result; 0 for the straight fallback. Boxes =
  round(5 x confidence). Measured: 0.204 with both cameras against 0.076 with the left one
  only and 5 m dialled; 0.155 against 0.093 with a second flagstick in view; 0.24 with the
  flagstick at 4.5 m against 0.09 (no box) with the flag out and 4.5 m dialled. **What the
  bar does not do** (review, open issue 21): the estimator's confidence is essentially the
  chance of holing, so a CLEAN read shows 5 boxes at 1.5 m, 3 at 3 m, 1 at 4.5 and 6 m and
  none at 9 and 12 m (table under "Putt on the display") - the same 0 or 1 box as most
  fallbacks at those distances. Beyond about 4 m the bar does not separate a weak result
  from a clean one; only the message and the line style do.
* **Survey.** Each placement is stored as its own `gl_measurements_t`; the estimate uses them
  all. The estimator takes the drops "ball first", and the line on the screen means something
  only if the marker lies at the ball, so: the ball is the stored drop FARTHEST from the
  flagstick by the estimator's range; if the newest drop is that one, or within 0.85 of its
  range, the newest drop is taken as the ball and the line is drawn in its frame; at any
  other drop the numbers are shown with `PUT AT BALL` and no line. **So a line appears only
  on a placement at the ball that is not the first one**: walk from the hole side back to the
  ball, or start at the ball and come back to it for the last drop. In the order the
  specification describes (ball, midpoint, a metre short of the hole) the three placements end
  with `PUT AT BALL` and no line; a fourth placement back at the ball shows it (the review
  measured exactly that). **This rule is this firmware's decision, not the specification's:
  see open issue 18.**
* **Log.** A read record's `range_m` is the estimator's distance; every read record is followed
  by an event `GL_APP_LOGEV_ESTIMATE` carrying aim source, solve status, the flags
  (`fit_converged`, `base_hidden`, `flag_missing`, `range_missing`, `poor_horizon`), method,
  read tier, `ambiguous`, whether the line was drawn, and the number of trial rolls. Charge
  gate changes are logged as `GL_APP_LOGEV_CHARGE` (reason and cell temperature) while awake.
* **Precision Read.** After the spin the marker faces away from the hole; the line is drawn
  through the ball position behind the marker (`gl_gfx_aim_line_at()`, added for this), with the
  spin angle from the gyro. **The whole result screen is then drawn turned by 180 degrees**
  (`gl_ui_render()` when the ball's azimuth is more than 90 degrees off the visor axis): the
  golfer stands behind the ball, which is now behind the marker, and reads the numbers upright
  with `<` and `>` on his own left and right. **Once per placement:** a double tap on a `2X`
  result does not arm a second spin (it used to, and the result of that was a `2X` screen with
  zero slope and a straight line); it goes on to the Survey, as on any result. A
  spin that is abandoned part way does not end the gyro integration (it ends when the marker
  sleeps or reads again), so a half turn completed later still counts from the first read.
  Turning the marker back to face the hole is a new placement and starts a new Quick Read;
  the `2X` result is gone then (open issue 29).
* **Zeroing** (rev C). From the dial item "ZERO": first read at rest, "TURN 180", gyro-measured
  turn, second read, `gl_tilt_flip_solve()`, bias stored with temperature and time. Refused
  with VBUS present; a turn more than 30 degrees from 180, a bias above 5 % or a disturbed read
  fails without storing.
* **Settings** (dial and USB). Stimp, units (feet, metres, paces), **PAST** (how far past the
  hole a missed putt should stop: 0..90 cm in steps of 5, default 30; shown in inches or
  centimetres), grass, grain, dialled distance, raw logging, **METHOD** (`B1` default, `B2
  HORIZ` = the anchored horizon fit), zeroing. **GRAIN** (default OFF): OFF measures nothing
  and the solver gets no grain (`use_grain` false); ON measures the grain during the tilt read
  (192 ADC conversions, which lengthen it) and hands the estimate to the solver with the
  coefficient of the **GRASS** item (bent / poa / bermuda: `GL_PROV_GRAIN_KAPPA_*`, unproven
  physics); GRASS alone changes nothing. **DIST** (the dialled distance) is for one hole: see
  "Dialled distance" above. The stored record is version 2; a version 1
  record (which had a three-step pace where PAST is now) is converted on load (pace 0 / 1 / 2
  -> 0 / 30 / 45 cm, method B1) and a record of any other version is refused, so that an old
  layout is never read as the new one.
* **USB** (`gl_usb.c`). All `gl_proto` commands are bound: settings, the four calibration
  records, log information / dump / incremental erase, RTC, reboot and ROM DFU, streams (IMU,
  tilt, power, grain). Writing calibration, starting a factory calibration procedure and the
  jump to ROM DFU need `UNLOCK` first; `SET_CAL` is atomic (decode, store, then adopt); a
  running log erase blocks appends (`GL_ERR_BUSY`) instead of interleaving with them, and USB
  is stopped in the loop pass that sees VBUS go, whatever the UI state. Calibration procedures: six-face (one still average per face, then solve
  and store) and grain white reference are implemented; `GRAIN_FLOOR` and `CAM_HORIZON` answer
  `GL_ERR_UNSUPPORTED`; `ZERO` answers `GL_ERR_STATE` (never in the cradle).
* **Storage.** 4 sectors of blob store (settings, calibration, learned stick height) and 2044
  sectors of ring log on the 8 MB flash. One 72-byte record per read; raw strips as 978-byte
  records (18-byte header + 960 pixels) so that each fits one USB log response.
* **Power.** Battery measured at wake-up and every 30 s (not during a read); below the LOW
  threshold the battery symbol shows it, below CRITICAL the warning screen is shown and the
  device sleeps (no camera read from a cell that the camera rail could brown out). **Charge
  supervision** (rev C2; rules in `drivers/power.h`, state table under "Charger and cell
  temperature"): the charger starts by itself whenever VBUS appears; the firmware measures the
  cell NTC and both die sensors at once on the VBUS edge (also when that edge is what woke it,
  and at boot in the cradle), then every 5 s while VBUS is present, awake or asleep (a timed
  wake-up; one measurement is 1.1 ms of simulated bus and conversion time, `NTC_BIAS` driven
  for 0.68 ms of it), and pulls `CHG_INHIBIT` low when the gate says stop. **The LEVEL of
  VBUS decides, not its edge** (review): every loop pass compares the pin with the level the
  firmware last acted on (`vbus_acted`), and so does the last step before every sleep, which
  is abandoned if they differ. An edge whose interrupt latch is lost is therefore acted on at
  the next wake-up of any kind, at the latest the 16 s housekeeping wake-up: asleep and put
  into a cradle at 50 C with the edge lost, the charger ran unsupervised for 15.5 s at worst
  (for the whole 600 s of the test before the fix); lifted out with the falling edge lost,
  the marker is asleep a second later (it used to stay awake with USB started, 1.58 mAh per
  hour in the supply model against 0.021 asleep). The supervision runs whatever the UI state
  (it used to be inside the "awake" branch), and a cell temperature older than 12 s counts as
  unknown and stops the charge, also when it is the supervision itself that stalled. `CHG_INHIBIT` is released when VBUS goes and
  before every sleep without VBUS. The cradle screen says `TOO COLD`, `TOO HOT` or `TEMP
  SENSOR` when charging is stopped. The jump to the ROM bootloader is refused unless VBUS is
  present and the gate is satisfied at that moment. **IMU supervision:** a bus error or a stall (no sample for 100 ms) starts a
  recovery (re-probe, re-configure) with a back-off of 1..64 s; a lost data-ready latch is
  bridged by polling after 10 ms; after 8 failed recoveries in a row (and no USB session) the
  watchdog is deliberately left to expire. **Storage mode:** below `GL_PROV_BATT_STORAGE_MV` (3250 mV) the IMU is switched
  off and the device only wakes for the watchdog and for VBUS. Wake-up interrupts of the IMU are ignored for 300 ms after the device went to
  sleep, in case the sensor's slope detector trips on its own mode change (behaviour unknown;
  without the hold-off a spurious wake would repeat for ever).

## Measured results (host, synthetic data)

These are copied from `make test`; re-run it to reproduce them.

### End to end (`tests/test_e2e.c`, the whole firmware on the simulator)

Scene: green sloped (1.2, -2.0) %, flagstick 6.0 m away and 2.9 degrees to the left, 15 mm
wide (1.6 px), SNR 20, swaying +-0.3 px at 1.5 Hz; sensors 9 ms out of phase; marker put down
between t = 1.0 and 1.6 s. **Computation is charged its time at the nominal factor** (2.0
cycles per host instruction, 160 MHz during the read); the low and the high case follow.

| Quantity | Result |
|---|---|
| State sequence | SLEEP, WAKE (1.02 s), WAIT_STILL (1.82 s), READ_TILT (2.37 s), CAPTURE (3.45 s), SOLVE, SHOW_RESULT (5.99 s; on the screen at 6.03 s) |
| Result on the screen | **4.43 s after the marker came to rest** (0.77 s until stillness is established, 1.08 s tilt read, 2.58 s camera part including power-up, settling and 0.80 s of computation). DESIGN_SPEC said "about three seconds" when this test was written; its amendment E15 now restates the figure from this model (4.1 to 4.8 s). NOT MET: the 4.0 s bound this test had while computation was free (3.45 s then) |
| Camera rail | on once, for 2424 ms (1557 ms with computation for nothing); 33 captures, 87 SCCB writes; rail never on outside the CAPTURE state |
| Camera rail rule | simulator: 0 violations; independent replay of the 18286 trace records: 0 pin-rule violations, 0 bus accesses with the rail off |
| Slope | (1.202, -1.997) % against (1.200, -2.000) % |
| Disparity | 2.2036 px against 2.1985 px true; claimed sigma 0.053 px, of which 0.05 px is the (unmeasured) stereo calibration term |
| Range | 5.972 m +- 0.136 m against 5.984 m (stereo 5.970, angular height 5.987 with the prior stick height) |
| Bearing | 48.48 mrad against 48.46 mrad |
| Putt estimate (method B1, single precision) | aim 78.9 mrad right of the line to the hole (-4.37 cups), launch speed 2.277 m/s, distance 5.970 m, hole 122 mm below the ball, confidence 0.16; aim source 0, status OK; 6 trial rolls, 1267 RK4 steps, 2 fit iterations |
| Screen | panel memory identical to the framebuffer; the aim line (bearing from the ball + aim angle) passes through the predicted pixels |
| While the result is shown | MCU in Stop 2 for 99.5 % of the time (IMU at 240 Hz) |
| After 45 s | display off, IMU wake-on-motion, flash in deep power-down, Stop 2; at most 6 loop iterations in the next 60 s (watchdog refresh every 16 s) |
| Log | one boot event, one read record (range = the estimator's distance, solve status, launch speed, aim offset) and its estimate event (aim source, status, flags, method, tier, rolls), decoded and compared with the result |

(The measured values differ in the last digits from the ones this table carried before: the
frames are exposed at other moments, so the noise and the sway in them are other samples.)

**Time and charge of this read, with its computation**
(`test_quick_read_time_and_charge_with_computation`; the same scene at four compute factors
and with a PLL that does not lock). Times are measured on the simulator; the factor is an
estimate (see "Run time"); the charge comes from the simulator's supply model, whose currents
are all PROVISIONAL:

| Computation | Rest to result | CAPTURE state | Camera rail on | Computation: all = band + strips + estimate + rendering | Charge, wake-up to result (cameras + MCU + rest) | Charge of a whole cycle |
|---|---|---|---|---|---|---|
| for nothing (what this file stated before) | 3.45 s | 1.60 s | 1.56 s | 0 | 143 mAs (134 + 6 + 3) | 175 mAs |
| low, 1.5 cycles per instruction | 4.13 s | 2.25 s | 2.16 s | 598 ms = 134 + 428 + 4.6 + 31 | 201 mAs (186 + 12 + 3) | 233 mAs |
| **nominal, 2.0** | **4.43 s** | **2.54 s** | **2.42 s** | 797 ms = 178 + 571 + 6.1 + 42 | **226 mAs** (208 + 14 + 4) | **258 mAs** |
| high, 3.0 | 4.82 s | 2.91 s | 2.76 s | 1196 ms = 268 + 857 + 9.1 + 63 | 259 mAs (237 + 18 + 4) | 291 mAs |
| nominal, PLL does not lock: the read at 48 MHz | 6.00 s | 4.10 s | 3.82 s | 2567 ms = 595 + 1903 + 20 + 49 | 342 mAs (329 + 9 + 5) | 374 mAs |

* "Whole cycle": wake-up, read, the 45 s the result is shown, and falling asleep again.
* The rail time grows by more than the computation between the captures would suggest in
  some rows and by less in others, because a capture can only start with the next frame of the
  sensor (33 ms): computation is paid in whole frames.
* The cost table counts 60.4 million instructions for this read; callgrind on the same read
  counts 59.6 million in the camera part and 0.49 million in the estimate.
* The rendering (0.23 million instructions per frame; five frames up to the result, four of
  them at 48 MHz by design) is 5 % of the computation.
* The cameras are 92 % of the charge of a read: **what a read costs is the time the camera
  rail is on**, and computation between the captures is paid at the cameras' 86 mA, not at
  the MCU's 9.5 mA.

**Battery life under the supply model** (ESTIMATE: every current is provisional - 86 mA for
the two cameras from an unverified 120 mW each, 9.5 mA for the MCU at 160 MHz, 9 uA in Stop 2,
5 uA for the IMU's wake-on-motion mode, 6.5 uA for regulator, battery divider and protection
circuit; the cell's 43 mAh is the listed figure, unverified; self-discharge, the usable part of
the capacity above the cut-off voltage and the cell's low-temperature behaviour are not
modelled):

| | For nothing (before) | Low | Nominal | High | PLL not locked |
|---|---|---|---|---|---|
| Charge per read cycle | 0.049 mAh | 0.065 mAh | 0.072 mAh | 0.081 mAh | 0.104 mAh |
| Read cycles per 43 mAh | 885 | 665 | 600 | 533 | 414 |
| Read cycles per 43 mAh, in % of "for nothing" | 100 | 75 | 68 | 60 | 47 |

Asleep, the model draws 20.6 uA (Stop 2 with RTC 9, IMU 5, always-on parts 6.5, flash 0.1):
0.49 mAh per day, 87 days from a full cell with no read at all; a round of 40 read cycles is
2.9 mAh at the nominal factor, the equivalent of 6 days asleep. A read with several lines in
the band keeps the rail on longer (about 3.4 s with a person behind the stick, "Run time"):
by the same arithmetic about 0.09 mAh per cycle. The 3 m scene below, which used to be such a
read (2.96 s), is not one any more (2.43 s).

What the L R R L timing correction is worth (stick drifting steadily at 6 px/s = 0.2 px per
frame, 8 groups):

| Sensor phase offset | Disparity error, corrected | Uncorrected |
|---|---|---|
| 2 ms | +0.002 px | -0.008 px |
| 9 ms | -0.001 px | +0.047 px |
| 16 ms | +0.004 px | +0.010 px |
| 24 ms | +0.003 px | -0.040 px |
| 31 ms | +0.003 px | -0.081 px |

The same against the run time of the vision, worst of the five phase offsets
(`tests/test_e2e_faults.c`): computation for nothing, the cost model at its nominal factor, and
fixed times per strip (eight times that for the band) up to 300 ms. The exposures of a group
keep the sensors' spacing whatever the run time, so the correction keeps working; what grows is
the read:

| Run time per strip | Worst error, corrected | Capture state | Camera rail on |
|---|---|---|---|
| none (computation for nothing) | 0.007 px | 1.48 s | 1.56 s |
| the cost model (about 17 ms, band 178 ms) | 0.004 px | 2.43 s | 2.42 s |
| 30 ms | 0.005 px | 2.78 s | 2.72 s |
| 60 ms | 0.005 px | 4.07 s | 3.89 s |
| 100 ms | 0.006 px | 5.49 s | 5.16 s |
| 200 ms | 0.011 px | 9.49 s | 8.76 s |
| 300 ms | 0.006 px | 13.49 s | 12.36 s |
| **the cost model, the drift REVERSING inside a group: NOT MET** | **0.039 px** | 2.43 s | 2.42 s |

No time-out at any of them. The fixed rows let the drift reverse every 1.7 s so that the stick
stays in the strip; in them the reversal happens to fall between two groups. With the cost
model's timing it falls inside one (the last row): the correction assumes uniform motion over
the 0.13 s of a group, that group is wrong by a few tenths of a pixel, **and nothing in the
read notices** - the read reports 0.039 px of error under a claimed sigma of 0.05 px. This is
not a matter of compute time (the row above it, without a reversal inside the read, is as good
as any); it was hidden by the timing of the earlier rows. Pinned by the test as NOT MET. The
200 ms and 300 ms rows are what a read would look like at 48 MHz with the vision of phase 1;
with the present vision the cost model gives about 59 ms per strip at 48 MHz (table above:
3.82 s of rail time).

Other end-to-end scenarios, all with zero simulator violations:

* **DCMI-crop windowing** (the fallback if the sensor window registers do not mean what is
  assumed): stick at 3 m, range 2.980 m against 2.984 m; 1 line in the band, 33 captures,
  camera rail on for 2.43 s. Before the phase-2 review the band listed TWO lines for this
  3.3 px wide stick and each got a group of its own before one was chosen (41 captures, rail
  on for 2.96 s). The second "line" was the stick's own shoulder in the widest line template;
  the read now drops it (`drop_shoulders_()`; `test_near_stick_is_one_candidate`: 21 Quick
  Reads of a flagstick 2.25 to 3.75 m away, 13 shoulders dropped, every read 33 captures, rail
  on for 2.42 to 2.46 s, result at most 4.40 s after the marker came to rest; the review had
  measured 3.02 to 3.12 s and 4.94 to 5.07 s on the reads with a shoulder).
* **Raw-strip logging.** Level FIRST: the first left and right strips arrive in the log byte
  for byte (2 x 48 records); the read takes 7.0 s instead of 4.4 s. Level ALL: 1600 records,
  1.6 MB, **48.1 s per read with the camera rail on for 40.8 s** - a bench mode, see open issues.
* **No flagstick:** the rail is on for 335 ms (band only, of which 178 ms are its analysis),
  the UI asks for the distance; with a
  dialled distance of 4.5 m the estimator's flag-out fallback: a tilt-only plane along the visor
  axis, aim 82 mrad right of the axis, `flag_missing`, estimator's confidence 0.21; shown with
  `NO FLAG`, a DASHED line and an empty confidence bar (capped at 0.09). Without a dialled
  distance the prompt is left by putting the marker down again, which reads again
  (`test_distance_prompt_re_placing_reads_again`: prompt at 7.0 s, picked up at 8.0 s, down
  again at 9.5 s, a result on the screen by 14.0 s; two camera-rail cycles).
* **Bumped 0.4 s into the capture:** read aborted and rail off within one 133 ms block,
  re-read by itself.
* **Precision Read:** spin measured 176.10 degrees (true 176.00); a device bias of (0.4, -0.3) %
  cancels: combined slope (1.205, -1.997) % against (1.200, -2.000) %; no second camera read;
  the estimator is told `tilt_reads` = 2.
* **Survey:** second drop 3 m further along, both drops stored with their own range and slope;
  the Survey estimate uses both (stations 0 and 3.0 m, twist d = 0.0041 /m, solved on the
  patch). The second drop is nearer the flagstick than the first, so the first is the ball and
  the screen says `PUT AT BALL` without a line. **NOT MET in this run, pinned: the curvature.**
  The fit gets a curvature (c = 0.0008 /m, what the two tilts 3 m apart imply) only if the base
  of the stick is classed VISIBLE at the second drop. There the stick ends 1.24 rows below the
  turf horizon, inside the 1.5-row margin of that class, and the class flips with the noise of
  the frames: VISIBLE in 51 of 80 runs of this scenario with the read shifted in time (compute
  factor 0 to 3.95). While computation was free the test was one of the 51 and asserted the
  curvature; at the nominal factor it is one of the 29: base AT THE HORIZON, c = 0.00001, patch
  coefficient a = -0.0205 instead of -0.0229.
* **Zeroing** on a table sloped (0.6, -1.1) % with a turn of -171 degrees: stored bias
  (3.490, -2.519) mrad against (3.500, -2.500) true, present after a power cycle; a 120 degree
  turn is refused; being put into the cradle abandons it; it cannot be started in the cradle.
* **Cradle:** protocol over the simulated CDC port (ping, info, status, settings, calibration,
  log dump, streams), charging at 22 C, stopped at 47 C (the charger ran for 4.30 s of the 5 s
  supervision period before the firmware stopped it), released again at 30 C, never Stop mode
  on USB, reboot to ROM DFU requested (after `UNLOCK`) and refused while the cell is too hot,
  asleep after removal with `CHG_INHIBIT` released.
* **Missing IMU / missing camera:** shown as an error, not fatal; rail off.
* **Battery:** at 3.45 V (low) the read runs; at 3.30 V (critical) the warning is shown and the
  device sleeps without ever powering the cameras; in the cradle it charges.
* **Spurious wake-up interrupt 50 ms after going to sleep:** ignored; a later one wakes.

Fault scenarios (`tests/test_e2e_faults.c`, 18 tests; the IMU, Precision, USB, calibration and
storage ones each reproduce a review finding and failed before its fix; the charger ones were
rewritten for rev C2):

* **Charge gate.** One SPI error earlier, then 5 minutes in the cradle at a true 60 C: the
  charger ran for 1.1 ms before the firmware stopped it, and stayed stopped. IMU silent: the
  NTC reads 60 C and stops the charge by itself (the IMU is only a second opinion now); at a
  permitted temperature a dead IMU leaves the MCU die sensor to vouch for the NTC (driver
  test). NTC 22 C,
  IMU 22 C, MCU die 50 C: charging (one die sensor agrees). NTC 22 C with both die sensors at
  50 C: stopped as implausible. NTC open, shorted, stuck high: stopped, with the reason logged
  (13 charge events in that test: 2 too hot, 3 NTC faults). 12 NTC conversions in 60 s in the
  cradle, `NTC_BIAS` driven for 10.3 ms of them. A fault acknowledged by a double tap in the
  cradle returns to the cradle state and the gate keeps running (10 minutes at 60 C: stopped).
* **Charger states** (`test_charger_state_table`, `test_rom_dfu_and_the_charger`): the table
  under "Charger and cell temperature" is measured there.
* **IMU supervision.** One failed SPI2 transfer: recovered (1 recovery), the read completes and
  15 later pick-up / put-down cycles all wake the device (it used to stay deaf until a reset).
  IMU absent only during boot: found later, 6 of 6 wakes. IMU dead for good: 12 failed
  recoveries, then the watchdog is left to expire (a reset on the target). 20 data-ready latches
  dropped during a read: longest gap without a sample 19 ms, bridged by polling.
* **Precision Read disturbed during the re-read:** a turn of 176 + 40 degrees is not shown as
  "Precision" (the angle is re-checked when the second read is done); 170 + 12 degrees is.
* **Lifted out of the cradle while a fault is shown:** USB stopped in the next loop pass (it
  used to stay started for 47 s).
* **SET_CAL with trailing bytes:** refused and nothing changed in RAM or flash. **LOG_ERASE
  with an append in between, then a reset:** 0 erased records come back.
* **Storage mode** at 3190 mV: IMU off, motion ignored, Stop mode 100.00 % of the time.
* **L R R L with vision run time:** the table above.


### Putt on the display (`tests/test_e2e_putt.c`; `make appdiff`)

Whole reads on the simulator: a rendered scene (sloped or twisted green, flagstick, optionally a
second flagstick or a blind right camera) seen by the two camera models, the real read sequence,
the vision, `build_measurement_()`, the single-precision estimator, `compose_view_()`, the
renderer, the LCD driver and the panel model. From the panel's memory the test fits the aim
line blind (run centres, a voting stage, least squares) and reads back every label glyph for
glyph. The reference is the double-precision build of the same solver source
(`tests/solver/gl_solver_ref.c`, which `make diff` ties to the Python package) and, with `make
appdiff`, the Python package itself on the dumped inputs.

"Reference aim" is the launch direction in the frame of the marker at the ball, in mrad,
counter-clockwise (left) from the visor axis: first on the record the application handed to
the estimator, then on a record built from the TRUE scene (true slope, range, bearing; the
availability flags of the application's record). "Drawn" is the same angle measured from the
pixels. `make test` on the final sources:

| Scene | Reference aim: app record / true scene | Drawn | Drawn - reference | Shown |
|---|---|---|---|---|
| Quick 3 m, rises LEFT 2 %, level | +129.22 / +127.58 | +129.08 | -0.13 | 9.8FT, PLAYS 9.7FT, <2.7 CUP, 2.0%, 3/5 |
| Quick 3 m, rises RIGHT 2 %, uphill 1.5 % | -103.47 / -102.27 | -102.97 | +0.50 | 9.8FT, PLAYS 11.6FT, 2.3 CUP>, 2.5%, 3/5 |
| Quick 6 m, rises RIGHT 1.2 %, downhill 2 % | -28.65 / -28.71 | -28.15 | +0.50 | 19.6FT, PLAYS 14.5FT?, 4.4 CUP>, 2.3%, 1/5 |
| Quick 6 m, rises LEFT 1 %, uphill 1.5 % | +8.43 / +8.56 | +8.42 | -0.01 | 19.6FT, PLAYS 23.3FT?, <2.7 CUP, 1.8%, 1/5 |
| Quick 9 m, rises LEFT 0.8 %, downhill 1 % | +72.74 / +72.80 | +74.91 | +2.17 | 29.5FT, PLAYS 25.8FT?, <4.4 CUP, 1.3%, 0/5 |
| Quick 1.5 m, rises RIGHT 1.5 %, uphill 0.5 % | -59.73 / -58.56 | -59.32 | +0.41 | 4.9FT, PLAYS 5.1FT, 0.8 CUP>, 1.6%, 5/5 |
| Quick 12 m, rises RIGHT 0.6 %, uphill 1 % | -59.40 / -59.33 | -59.10 | +0.30 | 39.8FT, PLAYS 44.9FT?, 3.3 CUP>, 1.2%, 0/5 |
| Quick 4.5 m, level green | +10.02 / +10.10 | +9.60 | -0.42 | 14.7FT, PLAYS 14.7FT?, STRAIGHT, 0.0%, 1/5 |
| Precision 6 m, rises LEFT 1.2 %, uphill 1.6 %, spun 176 deg (screen turned by 180 degrees) | +103.01 / +101.00 | +103.18 | +0.18 | 19.6FT, PLAYS 23.0FT?, <2.9 CUP, 2.0%, 1/5, 2X |
| Survey 2 drops (3 m, then the ball at 6 m) | +54.26 / +54.03 | +54.42 | +0.16 | 19.6FT, PLAYS 14.5FT?, <1.3 CUP, 2.2%, 1/5, D2 |
| Survey 3 drops: at drop 2 (3 m), not at the ball | +50.46 / +50.53 | no line | - | 19.6FT, PLAYS 14.5FT?, <0.6 CUP, 2.3%, PUT AT BALL, 1/5, D2 |
| Survey 3 drops (ball 6 m, 3 m, ball again) | +39.46 / +39.64 | +38.97 | -0.48 | 19.6FT, PLAYS 14.6FT?, <0.5 CUP, 2.3%, 1/5, D3 |
| Survey 4 drops: at drop 3 (2 m), not at the ball | +49.52 / +49.57 | no line | - | 29.5FT, PLAYS 34.2FT?, <2.4 CUP, 1.6%, PUT AT BALL, 1/5, D3 |
| Survey 4 drops (ball 9 m, 6 m, 2 m, ball again) | +19.54 / +19.63 | +19.70 | +0.16 | 29.3FT, PLAYS 33.9FT?, <2.4 CUP, 1.6%, 1/5, D4 |
| Flag out, dialled 4.5 m, rises LEFT 1.5 %, uphill 1 % | +70.12 / +70.21 | +73.89 dashed | +3.77 | 14.8FT?, PLAYS 16.7FT, <2.9 CUP, 1.8%, NO FLAG, 0/5 |
| Left camera only, 5 m dialled, rises RIGHT 1.4 % | -11.28 / -11.20 | -11.51 | -0.23 | 5.0M?, PLAYS 5.3M, 3.3 CUP>, 1.5%, NO RANGE, 0/5 |
| Left camera only, nothing dialled (3 m assumed) | -4.04 / -5.48 | -3.96 dashed | +0.08 | --, no plays-like, BREAK ?, 1.5%, NO RANGE, 1/5 |
| Ambiguous: a second flagstick in view | -28.54 / -28.71 | -27.88 | +0.66 | 19.6FT, PLAYS 14.5FT?, 4.4 CUP>, 2.3%, 2 LINES SEEN, 0/5 |
| Best effort: 7 % cross slope at Stimp 14 (`aim_source` 2, status 2) | +847.02 / +797.72 | off the screen: dashed parallel | - | 13.1FT, no plays-like, BREAK ?, 7.0%, NOT SOLVED, 1/5 |
| Best effort: 6.5 % downhill at Stimp 14 (`aim_source` 2, status 3) | +975.19 / +976.82 | off the screen: dashed parallel | - | 9.7FT, no plays-like, BREAK ?, 6.5%, NOT SOLVED, 1/5 |
| Secant plane: twisted green, Survey of 3 drops, Stimp 8 (`aim_source` 1) | -417.48 / -415.37 | off the screen: SOLID parallel | - | 16.4FT, PLAYS 18.0FT?, 20.5 CUP>, 6.2%, APPROX, 1/5, D3 |
| Method B2 (setting), 45 cm past, paces | -23.29 / -23.35 | -22.76 | +0.53 | 6.5P, PLAYS 4.8P?, 4.1 CUP>, 2.3%, 1/5 |

* Largest |drawn - reference| of a line on the screen: **3.77 mrad (0.22 degree)**; the test
  allows 6.5 mrad. The free-line figure of the display is 0.28 degree worst ("Display"); the
  labels of the result screen cover parts of this line, which is what the larger rows show.
* Largest |firmware (single precision) - reference| of a solved aim: 0.062 mrad. Largest
  |firmware - reference on the true scene|: 2.01 mrad over the scenes where that comparison is
  asserted (it contains the vision's and the tilt read's errors).
* **What the phase-2 review changed in this table.** Every `PLAYS` figure is smaller by the
  PAST setting (30 cm = 1.0 ft; 45 cm in the B2 row), and has a question mark where the base
  of the flagstick was hidden. The flag-out line is dashed and has no box. The Precision row
  is measured on a screen that is drawn turned by 180 degrees (the test turns the panel
  memory back before it fits the line and reads the labels). The off-screen substitute of
  the secant-plane row is solid. The reads at 2 to 4 m no longer spend a group of strips on
  the stick's shoulder, so their frames fall at other moments and their numbers moved in the
  last digits (Quick 3 m LEFT: drawn +129.47 before, +129.08 now). The Quick 9 m row moved
  too (+74.58 before, +74.91 now); why that read's frames changed was not traced.
* This table is the run WITH the compute-time model (nominal factor). Against the run with
  computation for nothing the frames of every read fall at other moments: the aims on the
  application's record move by up to about 1 mrad and the distances shown by up to 0.5 ft
  (at 12 m the range rests on 1.1 px of disparity); every assertion of the test holds
  unchanged.
* Solid or dashed is decided from the pixels too: of the pixels that only a solid line inks
  (the gaps of the dashes), at least 0.61 are black for the lines that must be solid and at
  most 0.07 for the ones that must be dashed.
* `make appdiff`: 22 estimator calls of the application, 22 agree with the Python reference
  (flags and codes exactly; C double within 1e-4 relative, largest aim difference 1.6e-7 mrad;
  firmware within 0.5 mrad of aim, 0.1 % of launch speed, 0.01 cup, 1e-4 of confidence; drawn
  line within 6.5 mrad; solid / dashed as the reference's flags require - where a flag-out
  result now requires dashed: the tool's rule was changed with the firmware's, and the first
  run after the change caught that it had not been).
* Precision Read: with a device bias of (0.4, -0.3) % the single read aims 16.41 mrad from the
  true scene's reference, the combined read 2.01 mrad.
* The best-effort rows: of a failed solve only the class (`aim_source`, `solve_status`) is
  defined and compared. Neither number is an aim, and the screen says so: the 7 % row's best
  iterate on the application's record was +796.75 mrad in the run before the review and is
  +847.02 mrad now, only because the frames of that read fall at other moments (137 trial
  rolls, 55,471 RK4 steps).

**What these tests do not reach, and how it is covered instead.** `PACE_LIMITED`, the straight
fallback (`aim_source` 3), a kept near miss, a fit that stops on its iteration limit and a
poor horizon are not produced by any read the simulator's scenes could be made to give
(pace-limited and the near miss are knife edges in cross slope; the others need inputs the
vision does not deliver). Their MAPPING to the screen is tested by overwriting the estimate of
a real read and re-composing the view (`gl_app_recompose_view()`): message, solid or dashed
line, `BREAK ?`, confidence boxes (the seven "Mapping only" lines of the test's output:
`APPROX` for the secant plane and for the kept near miss, `PACE LIMIT`, `NOT SOLVED` dashed,
`NO SOLUTION` dashed with no box, `FIT NOT DONE` at 0.7 of the confidence, `POOR HORIZON`).
The best-effort and secant-plane results of real reads have aims far off the visor axis, so
what is on the screen there is the off-screen parallel; a tentative line ON the screen is seen
in the mapping test, in the "nothing dialled" read and in the flag-out read. The synthetic
green is a plane or a twisted plane. **Both branches of the base-of-the-stick logic are
exercised by whole reads**: the base is classed VISIBLE in the two 3 m scenes, the 1.5 m scene
and several Survey drops (their rows have no question mark after `PLAYS`) and at the horizon
from 4.5 m on (`base_hidden` true). An earlier version of this paragraph said that only
`tests/test_solver.c` reached the visible-base branch; the dumped records show otherwise.

### Charger and cell temperature (rev C2; `tests/test_drv_power.c`, `tests/test_e2e_faults.c`)

**Which hardware this is.** The hardware of the builders' brief ("rev C2"): the MCP73831
charges whenever VBUS is present; the MCU can only STOP it, by pulling `CHG_INHIBIT` low (open
drain). **DESIGN_SPEC as it stands now (amendment E1) describes another charger**: a BQ25101
with its own thermistor input, and `CHG_INHIBIT` as a push-pull output that is driven HIGH to
stop. This section, the driver and the simulator's charger model are the rev C2 circuit; on an
E1 board this firmware's "stop" would stop nothing, and the cradle screen's `TOO COLD` / `TOO
HOT` / `TEMP SENSOR` would not describe what the charger does. The difference is pinned as NOT
MET (`tests/test_pins.c`, `test_charger_of_the_specification_is_not_the_firmwares`:
`tools/gen_pins.py` reads the charger sentence of the specification into
`GL_PINS_SPEC_CHG_INHIBIT_ACTIVE_HIGH` = 1 and `GL_PINS_SPEC_CHARGER_HAS_NTC_INPUT` = 1;
`drivers/power.h` says 0 and 0). Porting is a driver, a simulator model and this table; it was
not done because the brief fixes rev C2 (open issue 2).

The firmware's rules: pull low only as the outcome of a temperature evaluation made with VBUS
present; release whenever it stops supervising.

| State | `CHG_INHIBIT` | `NTC_BIAS` | Charger with VBUS | Who watches the cell | Measured on the simulator |
|---|---|---|---|---|---|
| MCU unpowered (cell at its cut-off) | high-Z (no supply) | high-Z | **on** | nobody (the case the default exists for) | by construction of the model; the FT-pin requirement is **not verified** (below) |
| Reset held, or start-up before `gl_app_init()` has measured | analog (reset state; `gl_hal_init()` and `gl_power_init()` do not touch it) | analog | **on** | nobody, until the first measurement early in `gl_app_init()` | boot in the cradle at -5 C: the charger ran for 1.1 ms after `gl_hal_init()` before the firmware stopped it (`gl_app_init()` takes 88.2 ms in all; the simulator charges no time for computation or for the start-up code before `main()`) |
| Awake, VBUS present, temperature permitted | released | driven high for 0.68 ms per measurement, analog otherwise | on | firmware: NTC + die sensors every 5 s | allowed 3.5..43.5 C rising, 1.5..41.5 C falling |
| Awake, VBUS present, too cold / too hot / NTC fault / implausible / unknown | **low** | as above | **off** | firmware, every 5 s (releases when permitted again) | cradle at 47 C: stopped within the 5 s period (4.30 s); every NTC fault stops |
| In the cradle between loop passes (idle sleep with USB, Stop 2 without) | as last evaluated (low or released) | analog | on or off accordingly | firmware: timed wake-up every 5 s | asleep, put into the cradle at 50 C: charger ran 1.13 ms before it was stopped; simulator rule: Stop in the cradle with no wake-up due within 10 s is a violation |
| Asleep (Stop 2), no VBUS | **released** before the sleep | analog | nothing to charge; starts by itself at the next cradle, and the VBUS edge wakes the firmware | firmware from the VBUS edge on | simulator rule: Stop with the pin low and no VBUS is a violation (none in any scenario; a test of the rule itself makes it fire) |
| The same, **the VBUS edge's interrupt latch lost** (review) | released | analog | **on** | **nobody until the next wake-up of any kind**, at the latest the 16 s housekeeping wake-up; then the firmware, which acts on the level | cradle at 50 C, edge lost 0.5 / 4.5 / 8.5 / 12.5 s after a housekeeping wake-up: charger ran 15.5 / 11.5 / 7.5 / 3.5 s before it was stopped (before the fix: all 600 s of the test) |
| VBUS removed while awake | released in the same loop pass | analog | - | - | |
| The same, the edge lost (review) | released in the next loop pass: the level is compared in every pass | analog | - | - | lifted out of the cradle with the edge lost: `SLEEP` one second later, USB stopped; the hour after: Stop mode 3600.0 s, 0.0206 mAh (before the fix: awake with USB started for good, 1.58 mAh in that hour; supply model) |
| Supervision stalled (no measurement for more than 12 s while VBUS is present) | **low** | analog | **off** | the staleness limit: a reading older than 12 s is "unknown" | cradle at 22 C, measurements withheld: charge stopped when the last reading was 12.0 s old (before the fix: not stopped) |
| Watchdog reset (also the deliberate one after a dead IMU) | analog again from the reset | analog | **on** until the firmware has measured again | firmware, from its first measurement after the restart | reset while inhibited at -5 C: charger on for 3.0 ms of reset + 1.1 ms of boot, then stopped |
| Firmware hung (no reset yet) | whatever it was: low stays low, released stays released | analog, or stuck high if hung inside a measurement | on if it was released | **nobody, for up to one watchdog period** | hung at 50 C: charger ran unsupervised for 33 s (watchdog 32 s). **NOT MET** |
| ROM bootloader (DFU) | analog (the ROM does not drive PH1; table from memory of AN2606) | analog | **on** | **nobody, for as long as the bootloader runs** | charging at 50 C for all of the 600 s the test lasts. **NOT MET** |

What is done about the two NOT MET rows, and what is not:

* **ROM bootloader.** The firmware refuses the jump (`GL_ERR_STATE`) unless VBUS is present
  and the gate is satisfied at that moment, so DFU starts from a permitted temperature. It
  cannot stop a cell from warming past 45 C during a long session in the bootloader, and it
  cannot prevent entry by other means (BOOT0 strap, empty flash). Only hardware can (a
  charger with its own NTC input, or a comparator on the NTC).
* **Hung firmware.** Bounded by the independent watchdog (32 s), after which the reset row
  applies. Shortening the watchdog period costs more wake-ups from Stop mode (open issue 12).
  The bound holds only if the watchdog runs: the backend now starts it before anything that
  can fail (by inspection; "STM32U5 backend"), and the longest computation between two
  refreshes, the putt solve, is refreshed before and bounded by its step budget ("Solver").
  A hang BEFORE `gl_hal_init()` (start-up code, a clock that never comes) is covered only by
  the hardware-watchdog option bit, which is a production setting and not set here (open
  issue 12).
* **Both rows are answered in hardware by amendment E1** (a charger with its own temperature
  input), for a board this firmware does not drive yet.

**Random plugging and unplugging** (`test_vbus_bounce_stress`; no fault is injected): 300
scenarios of VBUS edges singly and in bursts, temperature jumps between -8 and 55 C, MCU
resets and reads in progress - 4857 edges, 105 resets, 55 completed reads. 0 simulator
violations, 0 inconsistent end states (UI state, USB, `CHG_INHIBIT` and the VBUS level all
agree), 0 left with the fast clock; the longest stretch of charging outside 0..45 C was
5.00 s (the supervision period; the rule allows 10 s). On the tree as the review found it,
211 of the 300 scenarios violated a rule (422 violations): the firmware could go to sleep on
a VBUS level it had not acted on.

Cell temperature, as built and as tested:

* **Conversion.** Ratiometric (bias from the ADC's reference rail): R = 10.0 kohm x x / (1 - x),
  T = 1 / (1/298.15 + ln(R / 10 kohm) / 3380) - 273.15. Against a table computed independently
  in the test in double precision, -40..85 C in 0.5 C steps: worst error 0.011 K (at -39.5 C;
  one ADC count is 0.006 K at 25 C and 0.025 K at -40 C).
* **Tolerances and the guard band.** NTC 1 %, B 1 %, series resistor 1 % in their worst
  combination: 0.67 K at 0 C, 0.81 K at 45 C; with an ADC error of 0.2 % of full scale 0.90 K
  and 1.09 K. The window is therefore narrowed by `GL_PROV_CHARGE_TEMP_GUARD_C` = 1.5 K on
  both sides, with 2 K of hysteresis: charging stops below 1.5 C and above 43.5 C and
  resumes above 3.5 C and below 41.5 C. **Not covered by the guard band:** a temperature
  difference between the cell and the NTC beside it, and the difference between the
  B-parameter equation and the real part's R-T table (no datasheet table here: not quantified,
  not verified).
* **Open, short, stuck.** Above 98 % of full scale: open (NTC missing, or a broken trace; the
  equation would say below -51 C). Below 2 %: short, or no bias (above 180 C). The sense pin
  not within 5 % of ground with the bias released: stuck (a leak or a short to a rail). Each is
  a reason of its own and stops the charge.
* **Plausibility.** The NTC must be within 10 K of at least one die sensor that is alive and
  fresh (IMU with the driver's liveness check; MCU die sensor). With neither available the
  temperature counts as unknown. "At least one" and not "both": the MCU's die may run warm
  during a USB session, and one disagreeing die sensor should not stop a healthy unit from
  charging (open issue 5).
* **Bias only while measuring.** `NTC_BIAS` is driven for 684 us per measurement (500 us to
  settle the node, 8 conversions) and is analog otherwise: 12 measurements and 10.3 ms of
  bias in 60 s in the cradle (measured), about 0.02 % duty. The simulator counts a conversion
  before the settling time and a driven bias at Stop entry as violations.

### Board changes of rev C2 (`tests/test_board.c`, `tests/test_pins.c`)

| Change | Firmware | How it is checked |
|---|---|---|
| `CHG_INHIBIT` polarity and safe states (rev C2: open drain, low = stop) | `drivers/power.c`, table above | simulator rules and the measured table above. **The specification's present circuit (amendment E1) is the opposite polarity with another charger: NOT MET, pinned** (`test_charger_of_the_specification_is_not_the_firmwares`) |
| Cell NTC | `GL_ADC_CH_CELL_NTC`, `GL_PIN_NTC_BIAS`, `GL_PIN_NTC_SENSE`, `drivers/power.c` | above |
| EXTCOMIN divider 547 | the generator reads the divider from the spec into `GL_PINS_EXTCOMIN_LSE_TICKS`; `GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS` must equal it (`test_pins.c`) | simulator: the LCD driver starts LPTIM1 with 547 ticks, 32768 / 547 = 59.905 Hz |
| Core clock slow / 160 MHz around the read | `gl_hal_clock_set()`, `clock_()` in `app/gl_app.c` | simulator: calls recorded, paired, compute only while fast, never Stop while fast. **STM32: by inspection only** |
| Chip-select states during reset | pulls on the board (LCD SCS and DISP low, flash and IMU chip selects high, rail enable low: `GL_PINS_RESET_TABLE`); `gl_hal_init()` takes each over at that level | simulator: 0 of the 22 trace records of reset + `gl_hal_init()` leave one of the five pins away from its pull level; an internal pull against a board pull is a violation |
| PWDN off PA9 / PA2 / PC10 | `tools/gen_pins.py`: PWDN on PH0 and PC12; the forbidden pins are parsed from the spec | generator refuses; `test_pins.c` |
| New signals | `NTC_BIAS` PH3-BOOT0 (pad 60), `NTC_SENSE` PC4 (pad 24, ADC1_IN13), `CHG_INHIBIT` PH1 (pad 6): PROPOSED rows | `test_pins.c`: 47 signals, 46 on the 46 I/O pads and one on BOOT0; none of the three on a ROM-bootloader pin |

Three things about those pins need the schematic owner, and none is verifiable here:

* **`CHG_INHIBIT` must be an FT pin** (no protection diode to VDD). With the MCU unpowered, a
  diode would clamp the MOSFET gate to one diode drop and switch the charger off: the very
  case the default-on circuit exists for. PH1 is an FT pin as remembered; check the pin
  definition table of the datasheet.
* **`NTC_BIAS` on PH3-BOOT0.** With all 46 other pads taken, one signal had to go there. The
  bias was chosen because its loads pull the pin LOW at every reset (the divider to ground,
  and the BOOT0 pull-down), so it cannot select the bootloader by accident, and because it is
  driven for 0.7 ms at a time. If the board straps BOOT0 differently, or another signal can be
  dropped, `tools/gen_pins.py` is the one place to change.
* **ADC1_IN13 on PC4** is from memory of the datasheet.

### Solver (`tests/test_solver.c`; `make diff`; `make bench`)

All figures here are from runs on the host. "Reference" = the Python package
`../sim/greenline_sim` and its exported vectors (`../sim/results/reference_vectors.json`, schema
2: 240 estimator and 120 solver cases from simulated reads, plus the groups appended for this
port: 82 fallback estimator cases, 32 fallback solver cases, 33 single rolls, and - phase-2
review - 18 near-miss estimator cases; see `REFERENCE_VECTORS.md`). The file was regenerated
for the near-miss group and **the old file is a byte-identical prefix of the new one** up to
its closing bracket (checked with the files of before and after; 0 lines removed or changed),
as is the old `REFERENCE_VECTORS.md`: the reference's behaviour for the existing vectors is
unchanged, and the reference's own test suite passes (`python -m pytest -q` in `../sim`: 235
passed, 4 of them new). The same C source is built twice: `gl_real_t` = `double`
(`-DGL_SOLVER_DOUBLE`, symbols `gl_solver64_*`, host only) and `gl_real_t` = `float` (the
firmware). `tests/test_solver.c` runs both builds inside `make test` and `make asan`.

**Double build against the reference** (tolerance of REFERENCE_VECTORS.md: relative 1e-4 with
absolute floors; flags and codes exact):

| Group | Cases | Outside the tolerance | Worst difference, in units of the allowed one | Notes |
|---|---|---|---|---|
| `estimator_cases` | 240 | 0 | 3.6e-6 (a curvature, 2.2e-13 /m, in a B2 case) | aim 5.5e-13 rad, launch speed 5.7e-13 m/s; B0 / B1 / Precision / Survey cases agree to the last bit |
| `fallback_estimator_cases` | 82 | 0 | 2.7e-12 (confidence, last bit) | every flag and code equal; the best iterates of the 12 failed solves also equal (not required) |
| `solver_cases` | 120 | 0 (status: 0 differ) | 2.1e-12 | 118 solved |
| `fallback_solver_cases` | 32 | 0 (status: 0 differ) | 0 | same number of trial rolls as the reference in 32 of 32 |
| `roll_cases` | 33 | 0 | 0 (limit 1e-9) | status, capture, side and RK4 step count exact |
| `near_miss_estimator_cases` (`make diff`; `test_near_miss_cases`) | 18 | 0 | 0 | each case with the rule on (`near_miss` 5 mm) and, in its `without_*` fields, with the rule off: 14 kept, 4 controls that the rule must leave alone |

Between them the vectors reach every `aim_source` with every solve status the reference can
attach to it (0: OK, PACE_LIMITED, and NO_CONVERGENCE for the 14 kept near misses; 1: OK,
PACE_LIMITED; 2: UNREACHABLE, NO_BRACKET, NO_CONVERGENCE; 3: OK for method STRAIGHT, INVALID
for a zero distance), 6 fits that did not
converge (5 stopped by an iteration limit of 0 to 2, 1 whose horizon stage cannot run), Survey
with 2, 3 and 4 drops, B0 / B1 / B2 / STRAIGHT, flag missing, flag not
ranged, base hidden, stick top visible and not, dialled distance, Precision Read; the test
asserts that list. The 69 Survey cases are also run with the ball's drop last in the array
(`ball_index` = n - 1): identical results.

**Single build: tolerances.** The reference's tolerances (1e-5 m, 1e-5 m, fit step 1e-9; the
vectors use 1e-9 m and 1e-10) are below what single precision resolves: with them 185 of 185
fits and 17 of 240 pace solves of the vectors end on their limits. The firmware defaults were
chosen from measurements and are asserted with their margins:

| Option | Single-precision default | Why |
|---|---|---|
| `tol_miss_m` | 2e-4 m | the same launch rolled in single and in double precision crosses the hole line up to 2.1e-5 m apart (8580 launches around the solutions of the vectors; median 7.7e-8 m, 99 % 2.5e-6 m): 9.5 x that maximum. **For the vectors' putts only** - by putt length below |
| `tol_pace_m` | 1e-3 m | the squared arrival speed of those launches differs by up to 1.12e-4 m^2/s^2 (99 %: 6.7e-5); the tolerance as an energy, 2 a_r tol_pace, is 6.9e-4 at Stimp 16 (6.1 x) and more on slower greens |
| `lm_tol` | 1e-5 | bounded on both sides: at 1e-6 single-precision fits begin to end on the iteration limit (5 of 5542 random nominal fits; 0 at 3e-6 and above), and from 3e-5 on a fit that converges linearly (a Huber outlier row) stops early in EITHER precision (scaled patch error of the double build 8e-7 at 1e-5, 6e-5 at 2e-5, 0.14 at 3e-5) |

Three resolutions of the reference that are written for double (1e-13, 4e-15, 1e-15) are the
same multiples of the single-precision epsilon in the single build (`gl_solver_priv.h`).

**The margin of `tol_miss_m` by putt length** (phase-2 review: the 9.5 x above is a property
of the vectors' putts, not of the tolerance). `test_single_precision_roll_noise_by_distance`
solves random putts in double at 1e-9 m and rolls each solution in both precisions:

| Putt length | Launches | \|single - double\| at the hole line: median / 99 % / max | Max in units of `tol_miss_m` | Above a fifth of it |
|---|---|---|---|---|
| 0.3 to 6 m | 700 | 8.2e-8 / 2.8e-6 / 7.0e-6 m | 0.03 | 0 |
| 6 to 15 m | 700 | 8.4e-7 / 1.2e-5 / 2.4e-5 m | 0.12 | 0 |
| 15 to 25 m | 699 | 2.3e-6 / 7.3e-5 / 2.2e-4 m | **1.08** | 13 |
| 25 to 40 m | 699 | 4.7e-6 / 8.0e-5 / 2.6e-3 m | **13** | 36 |

Up to 15 m the tolerance is 8 times the worst roll noise or more (asserted up to 6 m).
**NOT MET from 15 m on, pinned**: there the tolerance is inside the noise of the roll for the
worst launches, and a single-precision solve can end NO_CONVERGENCE for no other reason (the
read accepts a flagstick up to 40 m away). A tolerance that grows with the distance would be
a change of the solver's contract (open issue 25).

**A horizon fit that converged used to be reported as not converged** in single precision
(review): with a fitted parameter above 0.125 the step that the convergence test asks for is
below one unit in the last place, and the fit flipped between two neighbours of equal cost
until its iteration limit (60), after which the application showed `FIT NOT DONE` and
multiplied the confidence by 0.7. In the single build a step below the resolution of the parameters
(`GLS_LM_STEP_ULPS` x epsilon x |x|) now ends the fit as converged: the reviewer's case
converges after 10 iterations (the double build with the same tolerances after 9; patch
coefficients equal to 4e-8). The double build and the vectors are untouched.

**Single build against the reference** (the reference at 1e-9 m / 1e-10; the single build with
its defaults). 240 simulated reads: all `GL_OK`, every flag and code equal, every fit converged.

| Quantity, \|single - reference\| | Median | 99 % | Max | Asserted bound |
|---|---|---|---|---|
| Aim direction [mrad] | 0.0046 | 0.100 | 0.132 | 0.20 |
| Launch speed [%] | 0.0013 | 0.022 | 0.029 | 0.045 |
| Aim point at the hole, D tan(phi) [mm] | 0.026 | 0.29 | 0.46 | 0.70 |
| Where the single-precision putt crosses the hole line, rolled in double on the reference patch [mm] | 0.008 | 0.18 | 0.19 | 0.30 |
| Roll-out past the hole of that putt against the 300 mm target [mm] | 0.16 | 0.96 | 0.99 | 1.5 |
| Displayed distance [mm] | 0.0002 | 0.0013 | 0.0015 | 0.003 |
| Break [cup widths] | 0.0002 | 0.0027 | 0.0042 | 0.0065 |
| Confidence [0..1] | 1.4e-8 | 1.2e-7 | 1.3e-7 | 5e-7 |
| Slope at the ball [%] | 4.7e-8 | 2.7e-7 | 5.0e-7 | 2e-6 |
| Plays-like distance [mm] | 0.15 | 0.94 | 0.99 | 1.5 |
| Height of the hole [mm] | 2.5e-6 | 4.6e-5 | 9.0e-5 | 3e-4 |

**A yardstick used in this section: one "display step" = 0.94 degree = 16.4 mrad.** That is
the step in which the reference's Monte Carlo quantises the displayed aim (2 / 122 rad, one
pixel at the rim of the aperture; `sim/greenline_sim/montecarlo.py`). **It is not the
resolution of this firmware's line** - an earlier version of this paragraph said "the aim line
on the display moves in steps of 0.94 degree", which the display tests contradict: the
dithered line reproduces an aim to 0.05 degree (0.9 mrad) rms ("Display"), and with the
labels of the result screen over it the drawn line is within 3.8 mrad of the reference in
every scene of `test_e2e_putt.c`. The largest single-precision error of the aim direction on
the simulated reads is 0.132 mrad: 1/125 of that yardstick (median 1/3600), a seventh of the
renderer's own rms error, and 1/19 of the 2.5 mrad seating noise the estimator assumes per
tilt axis. Single precision is not what limits this instrument.

Other groups in single precision:

| Group | Result |
|---|---|
| 82 fallback cases | 82 `GL_OK`; flags and codes equal to the reference's in 80. **NOT MET in 2** (pinned): cases 62 and 77, patches on a knife edge, end PACE_LIMITED where the reference at 1e-9 m ends NO_BRACKET / NO_CONVERGENCE. The double build run with the single-precision tolerances ends exactly like the single build in both: a tolerance effect, not an arithmetic one. Values of the 66 cases with a defined aim: aim 0.099 mrad, speed 0.012 %, aim point 0.48 mm at most. Every aim source and every solve status is reached in single precision too. |
| 120 solver cases | status equal in 120. Solved cases: aim 99 % 0.096 mrad, **max 1.04 mrad** (0.064 display steps), speed max 0.079 %, aim point max 3.1 mm, all three on case 16 (a putt down a slope at 0.9 of critical, where a family of aim / speed pairs holes the putt within the tolerance); rolled in double the single-precision solutions cross within 0.19 mm of the hole centre in every case. |
| 32 fallback solver cases | status equal in 28. **NOT MET in 4** (pinned): cases 12, 13, 25, 28, whose tags say that the outcome depends on the tolerance (two putts that die at the hole, one knife edge, one roll budget that is only exhausted at 1e-9 m); again the double build with the single tolerances ends like the single build. |
| 18 near-miss cases (rule on, firmware tolerances) | 18 `GL_OK`. In the 14 that the reference keeps, the single build's aim is on the patch too (`aim_source` 0) in 14 of 14 and passes within 5.5 mm of the hole centre in 12 (worst 6.42 mm; one stops short); its status is the reference's NO_CONVERGENCE in 8, PACE_LIMITED in 4 and OK in 2 - the same tolerance effect on knife-edge putts as in the rows above. The 4 controls, which the reference at 1e-9 m does not keep, end on the patch in the single build as well. Aim against the reference: up to 2.95 mrad (`make diff`). |

**Differential test beyond the vectors** (`make diff`, seed 20261111, 30 % of the cases pushed
outside the nominal ranges: slopes beyond what the green holds, curvatures of 0.02 /m, distances
from 0 to 500 m, green speeds from 0 to 1e6 ft, not-a-number and infinities in every field,
missing flags, iteration limits of 1 to 5, roll budgets of 8 to 1000; since the phase-2 review
also the near-miss option at random and inputs of 1e300, 1e20, 1e-20 and 1e-200, so the
counts are not those of the run before it). This session, 3 min 37 s:

| Double build | Result |
|---|---|
| 20000 random reads against `estimate_batch` | 18367 both return an estimate; 872 both reject (the reference raises `ValueError` 660, `ZeroDivisionError` 124, `OverflowError` 9, or returns a not-a-number 79; C returns `GL_ERR_PARAM` / `GL_ERR_RANGE` and the flagged record); 735 refused by contract (C returns `GL_ERR_PARAM` for a focal length or baseline that is not positive, or a lens height or tilt that is not finite, where the reference would compute on); **0 disagreements**; 0 undefined results |
| - distribution of \|C - reference\| over the reads where both return an estimate (the 30 of the next row included, which is where every maximum comes from) | worst difference in units of the allowed one: median 0, 99 % 6.0e-8, 99.9 % 0.029. Aim: median 0, 99 % 1.8e-14 rad, 99.9 % 3.5e-7 rad; launch speed: 99 % 8.8e-15, 99.9 % 3.6e-7 m/s; patch coefficients: 99 % at most 1.4e-17, 99.9 % at most 3.0e-12; fit covariance (not in the vectors) within 2.9e-8 relative |
| - 30 of those reads differ by more than the tolerance and are accounted for | 26 "explained by last-bit rounding of the patch" (25 with a horizon, 1 Survey: the two fitted patches differ by 1e-19 to 3e-13 because two library functions of the reference differ from libm in the last bit - numpy's vectorised cos / sin / tan, CPython's `math.hypot` - and for each the C solve chain run on the REFERENCE's patch reproduces the reference's aim source, status, aim and speed exactly; they are failing, pace-limited, dying-putt or kept-near-miss solves, whose outcome a last-bit change of the patch flips); 4 "tolerance-limited": drawn with loose random tolerances they differ by more than the allowed difference, and they agree within it when both sides are run again with the vectors' tolerances (1e-9 m, 1e-10) |
| 20000 random aim problems against `solve_aim` | status equal in 20000 (OK 14852, PACE_LIMITED 523, UNREACHABLE 690, NO_BRACKET 473, NO_CONVERGENCE 3273, INVALID 189); of the 19811 that ran, the number of trial rolls is the same in 19811 and aim and speed are **bit-identical in 19811** |
| 5000 random rolls against `simulate_putt` | status, capture, side equal in 5000; every real identical |
| 20000 range fusions, 5000 horizon rays | largest relative difference 1.9e-16 |
| the 5 vector groups of the estimator and the solver, through the same shared library | worst difference 3.55e-6 of the allowed one (`estimator_cases`); `near_miss_estimator_cases`: 0 |

Two port bugs were found by this test and fixed by builder 1 (the covariance of an anchored fit
whose horizon stage failed; a zero stick height, which the reference rejects with a division by
zero and the port used to answer with the "not ranged" fallback). In the phase-2 review it
found two more things, both in what the fixer had just written: the overflow check of finding
7 refused inputs with a not-a-number or infinite sigma that the reference accepts (6
disagreements; the check now mirrors the reference's `**2`), and the tool's own replay of a
solve on the reference's patch did not know the near-miss rule (1 disagreement).

The single build on the same random cases, the reference run with the single build's
tolerances: 0 undefined results, 0 disagreements. Of 20000 aim problems the status is equal in
19806; the 194 others are, as before the review (the aim problems are the same ones),
distances within a rounding of the 1e-6 m limit (25), classes of failing or pace-limited
solves that change places (150), and putts solved in one precision only (12 solved by the
reference and not in single, 7 the other way round; builder 1 traced the 12 to roll budgets
of 8 or 40, a slope at 0.90 to 0.97 of critical and a dying putt). Deviation of the
17101 solved problems with equal status: aim median 0.0001, 99 % 0.077, 99.9 % 0.47, max 3.7
mrad; launch speed 99 % 0.0035 %, max 0.12 %. Random reads: 18353 both return an estimate,
865 both reject, 47 are rejected by one side only because the input is not representable in
single precision; 1.4 % end with a different solve status (256) or aim source (153), almost
all between failing classes (14 reads that the reference solves on the patch with status OK
end otherwise in single precision). For the 15110 reads with the same outcome and a solved
aim the aim differs by 0.0001 mrad median, 0.12 mrad at 99 %, 1.3 mrad at 99.9 % - and by up
to 123 mrad in single cases of this deliberately hostile mix (steep or dying putts whose
solution is not determined to the tolerance; the near-critical instability below).

**Near the critical slope the aim is not determined, in either precision** (phase-2 review,
finding 2; not a port error and not changed, because the brief fixes the reference's
numerical behaviour). The reviewer perturbed the inputs of nominal reads by one microradian
and found the reference's aim jumping by more than a display step in about 3 % of the reads
whose putt runs near the critical slope, and the best-effort direction (`aim_source` 2) to be
an arbitrary iterate of the search (those figures are the reviewer's; they were not measured
again here). What this session shows of the same thing: the C double build follows the
reference bit for bit through all of it (19811 of 19811 aim problems); in `test_e2e_putt.c`
the best iterate of the unsolvable 7 % scene is +797 mrad in the firmware and +847 mrad in the
reference on the same record; and the single build differs from the reference by up to 123
mrad on the hostile reads above. What the firmware does about it: a best-effort aim is never
drawn as a solution (dashed, `NOT SOLVED`, `BREAK ?`, one box at most), and a near miss of
the patch is kept in preference to a secant-plane aim that misses (finding 1). What it does
not do: stabilise the search. That is the estimator owner's (open issue 24).

**The base-visible flag is a hard switch** (finding 9; reference behaviour, not changed): the
same placement with `flag_base_visible` flipped moves the aim by more than a display step in
1.6 % of nominal Quick Reads (the reviewer's figure), because the height of the hole is a
measurement in one case and a one-sided bound in the other. The vision's class flips with
the noise when the base is within the 1.5-row margin (open issue 22). The screen now marks
the weaker case (`PLAYS n?`).

**Method B2 with untidy horizons** (finding 10; B2 is OFF by default): the reviewer found
nominal reads that fall back, jump and differ between the precisions when the horizon samples
are untidy; nothing in the estimator was changed. A poor horizon is now shown (`POOR
HORIZON`). Method B1 does not use the horizon.

**Hostile inputs** (`test_hostile_inputs_give_defined_results`, both precisions, also under
`-fsanitize=address,undefined,float-cast-overflow` in `make asan`): 28000 calls per precision of
`gl_solver_estimate`, `_estimate_survey`, `_solve_aim`, `_roll`, `_fuse_range`,
`_quad_horizon` with not-a-number, infinities, the largest and smallest numbers, zero distance,
absurd slopes, zero green speed, NULL pointers, drop counts 0 to 6, options out of range.
**0 violations**: every call returns `GL_OK`, `GL_ERR_PARAM` or `GL_ERR_RANGE`; with `GL_OK`
every real the header promises finite is finite and the codes are defined; with an error the
output is the flagged record. (Single: 11074 OK, 3796 PARAM, 1130 RANGE; double: 11136, 3796,
1068. The table of hostile values grew in the phase-2 review by numbers whose square
overflows or underflows, which is why the counts moved.) Builder 1 also ran 84000 calls per
precision outside the sanitisers; that longer run was not repeated in this session.

**Absurd inputs** (finding 7). Four probe calls returned `GL_OK` and a plausible-looking
record: in the double build a relative stick-height sigma or a stick height of 1e300, which
the reference refuses with an `OverflowError`; in the single build a stick height of 1e-20 m
("not ranged", 3 m shown) or a focal length of 1e20 px, whose squares leave the range of a
float. A square of a finite input that overflows is now `GL_ERR_RANGE` in both precisions,
in the double build exactly where the reference's `**2` raises (an infinite or not-a-number
sigma is still what the reference makes of it: `make diff` holds the two together, 9
`OverflowError` cases among the random reads). `test_absurd_inputs_are_refused`.

**The default pace** (finding 6): `GL_SOLVER_DEFAULT_PAST_M` was the float literal `0.30f`,
so the double build's default was 0.30000001192092896 and not the reference's 0.3. It is a
double constant now (0.29999999999999999 in the double build, the same float as before in
the firmware); the vectors always passed their pace explicitly and are unaffected.

**Run time, bounded.** No loop without a counter: one roll takes at most 6004 RK4 steps, one aim
solve at most `max_rolls` + 120 = 320 rolls, an estimate at most two aim solves (the patch,
then its secant plane; **one if the patch is a plane**, since the secant plane is then the
same problem - it used to be solved twice), a fit at most 60 iterations of at most 25 damping
trials for at most 6 starts. `gl_estimate_t.n_rolls` / `.n_steps` report what was spent.

**And since the phase-2 review, a budget on the steps themselves**:
`gl_solver_options_t.max_steps` (firmware only; the default is 0 = none, as in the reference,
and every vector is run without it). The budget is checked between trial rolls and counted
over the whole estimate, so an estimate integrates at most `max_steps` + 6004 steps; a solve
that runs out ends as the best iterate so far, NO_CONVERGENCE (`aim_source` 2, or a kept near
miss). The application sets `GL_APP_SOLVE_MAX_STEPS` = 300,000 and refreshes the watchdog
before the solve. Over all 340 estimator vectors, with and without that budget, no record
differs among those that stay inside it: in the single build with the firmware's tolerances
none exceeds it (costliest 208,952 steps, with a result); in the double build at the
reference's 1e-9 m two do (costliest 338,870).

`make bench` (`tools/solver_bench.c`; host, `-O2`, single precision, firmware defaults).
Instruction counts: builder 1's callgrind runs where marked (c); `make profile` of this
session for the typical read (p); otherwise the simulator's cost rule, 40,000 + 351 per RK4
step, which reproduces the callgrind count of the 20.7 m case to 0.03 %:

| Estimate | Trial rolls | RK4 steps | Fit iterations | Host instructions | At 160 MHz, if one host instruction costs 1.5-3 cycles (ESTIMATE) |
|---|---|---|---|---|---|
| Typical Quick Read, B1 (the median of the 24 B1 reads) | 5 | 730 | 3 | 295,603 (p) | 3-6 ms |
| Survey, 3 drops (median of 24) | 3 | 849 | 3 | 348,793 (c) | 3-7 ms |
| B2 with 41 horizon samples (median of 69; the horizon stage's 5 starts are most of it) | 5 | 875 | 3 | 1,424,989 (c) | 13-27 ms |
| W0: 20.7 m across a slope near the limit (this table's "worst case constructed" before the review) | 418 | 492,782 | 3 | 172,948,041 (c) | 1.6-3.2 s |
| W1 (review): 30 m dialled, down a slope at 0.90 of critical, a tilt-only plane | 212 (424 when the plane was solved twice) | 309,911 (619,822) | 0 | 109 million | 1.0-2.0 s |
| **W2: the costliest found with the reference's limits alone** - 26 m by stereo, method B1, neither patch nor secant plane solvable | 421 | 575,247 | 3 | 202 million | 1.9-3.8 s |
| **W2 with the application's budget** | 223 | 300,514 | 3 | 105 million | **1.0-2.0 s** |
| W1 with the application's budget | 206 | 300,911 | 0 | 106 million | 1.0-2.0 s |
| Bound that follows from the counters alone (640 rolls of 6004 steps) | 640 | 3,842,560 | - | about 1.35e9 (not run) | 13-25 s |
| Bound with the application's budget (300,000 + 6004 steps) | - | 306,004 | - | 107 million | 1.0-2.0 s |

Over the 240 simulated reads: 5.0 rolls and 1026 RK4 steps on average, at most 57 rolls and
25,144 steps. W0 came from builder 1's random searches with hill climbing (492,782 to 519,807
steps); W1 and W2 are the two costliest cases of the safety reviewer's search (its seeds 21
and 11), run here with the fixed code; the numerical reviewer's own search ended at 628,940
steps (that case was not run again here). **None of them is a proven maximum** - the hostile-input test, which also
draws roll budgets up to 1000, saw 864,765 steps in one call of the double build - which is
why the application's bound is the budget and not a search result. **The time on the target is
an estimate, not a measurement**: the cycles-per-instruction factor is the same guess as for
the vision (a Cortex-M33 needs 14 cycles for each of the 5 square roots and 8 divisions of an
RK4 step alone, 180 of the roughly 500-1000 cycles the factor implies per step); newlib's
`powf`, `sinf`, `cosf`, `logf`, `erff`, `hypotf`, `atan2f`, `tanf` are not the host's. A
typical solve is 0.5 % of the 58 million instructions of a read's vision; the budget is 1.8
whole reads. At 48 MHz (a PLL that did not lock) the budget is 3.3-6.6 s; the watchdog period
is 32 s.

**Stack and RAM** (`make cross`, `-Os`, `-fstack-usage`): `gls_fit_patch` 464, `gls_roll` 304,
`gls_solve_kernel` 272, `fit_lm_` 240, `estimate_` 224, `trial_` 112, `fit_residuals_` 112,
`solve_pace_` 104, `solve_patch_` 80, `accel_` 40, `gl_solver_estimate_survey` 40 bytes. Deepest
chain below the caller: estimate -> solve on the patch -> kernel -> pace solve -> trial -> roll
-> acceleration = 1176 bytes (the fit chain: 1080), libm frames not included (not compiled
here). Static RAM: none (`.data` and `.bss` of the four solver objects are 0); the caller
supplies `gl_solver_work_t`, 6160 bytes on the target (12248 in the double build), which the
application holds once. Code: 17,835 bytes (`gl_solver` 2623, `_aim` 4028, `_fit` 6942, `_roll`
4242; 17,149 before the phase-2 review). No double-precision helper, no double libm function, no heap, no stdio (the
forbidden-symbol check of `make cross`).

### Vision

Two sets of figures, from two independent scene generators. Neither models the Bayer mosaic,
rolling shutter or real scenery.

**A. The camera part of a read on hard scenes (`tests/test_read.c`).** The real sequence
(`gl_read` + camera driver + `gl_vision`) on the simulator, with the design reviewers' scene
generator (`tests/synth/gl_scene.c`), which is physically consistent: a 15 mm stick 1.96 m tall
has the width, the height and the disparity of ONE range, its base lies (lens height / range)
below the turf edge on a flat green, both cameras see the same world. Sky 120 grey, turf 80 with
3 grey of texture, noise 2 grey rms, lens blur 0.6 px, 8 x L R R L, sensors out of phase at
random. "A" = 1.5 px stick (6.6 m), "B" = 0.8 px (12.3 m), both 30 % brighter than the sky.
8 reads per scene, 6 per cell of the grid (920 reads, and 64 more of the one scene that eight reads cannot pin); the claimed sigma includes the 0.05 px calibration term,
which these perfectly calibrated synthetic cameras do not exercise, so "rms / claimed" below 1
is expected on clean scenes and says nothing about the calibration term itself.

**These tables are the run with the compute-time model at its nominal factor** (builder 3).
The vision itself computes bit for bit what it did in phase 1 ("Run time"): when builder 3
finished, the output of this test with computation for nothing (`test_read --cpi 0`) was
byte-identical to the one before the optimisation, and every threshold of the test held
unchanged. What charging the
computation changes is WHEN the frames are exposed: the first strip comes about 0.2 s after
the band (its analysis, 0.18 s, and the wait for the next frame) instead of one frame after
it, and the groups of four strips are further apart. Of the 106 lines the test prints, 36
differ, most of them in the last digits; the rows that moved are marked "(was ...)" below. One threshold is NOT MET with honest timing and is pinned
by the test (the post 14 px beside the stick).

**And they are the run after the phase-2 review**, which changed two things in the read
(`app/gl_read.c`), not in the vision: a band "line" that is the shoulder of a much stronger
one is dropped, and a lone line that its first group shows not to be a flagstick is given up
at once. Against builder 3's run 38 of the lines the test prints differ, nearly all in their
last digits (the frames of a read with a dropped shoulder fall at other moments) and one for
real (the post 14 px beside the stick); the second change moved nothing but the camera-rail
time of the stick-free reads. For the same reason `test_read --cpi 0` no longer prints the
phase-1 output byte for byte (37 lines differ from the unchanged tree's, run in this
session); that the VISION computes what it did in phase 1 is shown by
`tests/test_vision_equiv.c`, which is unchanged and passes.

Flat green, width x contrast (6 reads per cell; reads that gave a disparity | disparity rms px;
bright sticks, dark ones are the same within the scatter):

| Width (range) | 5 % (3 x noise) | 10 % | 20 % | 40 % | 60 % |
|---|---|---|---|---|---|
| 0.5 px (19.7 m) | 0 of 6 | 0 of 6 | 6: 0.026 | 6: 0.018 | 6: 0.014 |
| 0.7 px (14.1 m) | 1 of 6 | 6: 0.036 | 6: 0.017 | 6: 0.009 | 6: 0.004 |
| 1.0 px (9.9 m) | 6: 0.038 | 6: 0.021 | 6: 0.013 | 6: 0.004 | 6: 0.003 |
| 1.5 px (6.6 m) | 6: 0.023 | 6: 0.013 | 6: 0.004 | 6: 0.002 | 6: 0.003 |
| 2.0 px (4.9 m) | 6: 0.017 | 6: 0.007 | 6: 0.005 | 6: 0.002 | 6: 0.003 |
| 3.0 px (3.3 m) | 6: 0.021 | 6: 0.008 | 6: 0.003 | 6: 0.003 | 6: 0.001 |

The claimed sigma is 0.051-0.054 px wherever the stick is easy and rises to 0.06-0.22 px in the
faint cells; no cell has an error above 1.5 claimed sigma rms. **Not met:** sticks of 0.5-0.7 px
at 5-10 % contrast (14-20 m, 3-6 x noise) are mostly not read (the old code, in the reviewers' run of the same grid, read none of the 5 % and 10 % cells
at any width up to 1.5 px, none of 0.7 px at 20 % and almost none of 0.5 px below 60 %; the
matched significance test and averaging 4 or 16 rows along the line are what recover the cells
that now work).

Named scenes (reads of 8 that gave a disparity; disparity rms px / mean claimed sigma px):

| Scene | Stereo reads | rms / claimed | Notes |
|---|---|---|---|
| A, B nominal | 8, 8 | 0.004 / 0.052, 0.015 / 0.053 | |
| Lean 1, 2, 3 degrees (A), -3 (B) | 8 each | 0.004-0.015 / 0.050-0.053 | |
| Sway: drift 3 px/s; 0.5 px at 1.5 Hz; 1 px at 3 Hz (A); 2 px at 1 Hz (B) | 8 each | 0.004 / 0.051; 0.009 / 0.056; 0.056 / 0.176; 0.021 / 0.065 | fast sway shows up in the sigma through the scatter of the groups. **Worse with honest timing** (was 0.004; 0.008; 0.040; 0.014 with computation for nothing): the groups are spread over 2.4 s instead of 1.5 s; still within the claimed sigma (0.09 - 0.34 of it) |
| Flag over the tip, bright or dark cloth (A, B) | 8 each | 0.003-0.010 / 0.051-0.053 | top flagged "in clutter" in 32 of 32 reads and never offered for ranging (it used to be ranged with: 19-23 % long) |
| Person 0.6 m beside, 2 m beside and nearer (A) | 8, 8 | 0.004 / 0.051, 0.005 / 0.051 | |
| Person 2 m behind, a leg right behind the stick (A) | 8 | 0.035 / 0.345 | static sigma 0.34 px: the background says so; all 8 flagged ambiguous |
| The same at 12 m (B) | **0** | - | **not met**: 6 nothing, 2 band-only bearing (was 5, 3) |
| Second pole 7 px beside, half as wide, twice as far (A) | 8 | 0.019 / 0.256 | |
| The same beside the 0.8 px stick (B) | **4** | 0.009 / 0.251 | **not met**: 4 of 8 give a disparity, none of them the far pole; 1 the left camera only, 3 a band-only bearing. (Was: 8 with a disparity, in 4 of them the far pole taken, all 4 with the ambiguity flag) |
| Dark 4 px post 14 px beside (A / B) | **4** / **0** | 0.005 / 0.051 | **A NOT MET with honest timing, pinned on 64 reads** (the test demands half): 26 of 64 at the nominal factor, 34 with computation for nothing, 27 at the low factor, 0 at the high one. Before the phase-2 review: 11 of 64 at the nominal factor (each dropped shoulder had cost this scene another 0.3 s). B **not met** as before |
| Other line 120 px away: weaker stick; dark 3 px post (A, B) | 8 each | 0.005-0.012 / 0.051-0.054 | the post used to be chosen over the stick in 12 of 12 |
| Glare gradients, veiling glare, sun disc 25 px from the stick | 8 each | 0.005-0.011 / 0.051-0.054 | |
| Row gain 3 %; alternating-column gain 3 % | 8, 8 | 0.005 / 0.051; 0.005 / 0.121 | the column pattern is over-claimed 20-fold (it reads as background structure) |
| Column fixed pattern 0.5 / 1 / 2 grey rms (A) | 8 each | 0.031 / 0.058; 0.040 / 0.076; 0.079 / 0.126 | the error does not average out; the old code claimed 0.004-0.02 px here |
| PRNU 1 %; all sensor effects (A); FPN 1; all (B) | 8 each | 0.057 / 0.085; 0.063 / 0.083; 0.080 / 0.110; 0.128 / 0.116 | |
| Right window smeared: blur 1.2; 1.8 + veil; 2.5 + veil | 8 each | 0.007 / 0.052; 0.012 / 0.055; 0.037 / 0.077 | a smeared LEFT window fails the width test instead (not tested) |
| Tree line behind, white stick: mild trunks; strong trunks; isotropic foliage | 8 each | 0.037 / 0.071; **0.172 / 0.120**; 0.063 / 0.071 | strong trunks: worst read 0.31 px off, 1.4 claimed sigma rms |
| Tree line, stick only 36 grey brighter than trunks of 12 grey rms | **0** | - | **not met** |
| Everything at once (A / B) | 8 / 7 | 0.095 / 0.088; 0.142 / 0.199 | range error 5 % / 12 % rms = 1.1 / 0.7 of its claimed sigma |

No stick in the scene (88 reads: plain, tree line, a person, FPN 1 and 2 grey, glare, a 12 px
trunk at 40 m, a 3 px post at 25 m, column gain, PRNU, foliage + rough turf): **0 reads report a
flagstick**, in either tier; 1 read (glare) reports a band-only bearing. The trunk and the post
were ranged as flagsticks by the old code in most reads. **Mean camera-rail time 1.02 s**
(asserted below 1.25 s). It was 1.65 s before the phase-2 review, when a lone line was read in
full - eight groups - before it was judged; dropping the shoulders alone made that worse
(1.86 s: a trunk or a post, until then two "lines" that were probed with one group each,
became a lone line), which is why the verdict now falls after the first group for a lone line
too.

**Why the post 14 px beside the stick now defeats the read.** The first search for the stick
in each camera is widened by 3 px for every second that has passed since the band was exposed
(`GL_APP_SWAY_ALLOW_PX_PER_S`: the stick may have swayed). With computation for nothing that
is a few tenths of a pixel; with the band's analysis taking its 0.18 s and the frame waits it
is about a pixel, and at the high factor more. `test_read A_pole2_14px_post 64 <factor>`:

| Compute factor | Disparity | Left camera only | Band-only bearing | Nothing | Wrong object |
|---|---|---|---|---|---|
| 0 (computation for nothing) | 34 of 64 | 0 | 0 | 30 | 0 |
| 1.5 | 27 (14 before the phase-2 review) | 0 | 4 | 33 | 0 |
| 2.0 (nominal) | 26 (11 before) | 1 | 4 | 33 | 0 |
| 3.0 | 0 | 11 | 21 | 32 | 0 |
| 0, 2.0 and 3.0 with the allowance set to 0 (scratch build of builder 3, not in the repository, not repeated in this session) | 34 | 0 | 0 | 30 | 0 |

So the loss is the allowance meeting the compute time, not the compute time itself; no read
takes the post for the stick. Half of what was lost at the low and nominal factors came back
with the shoulder rule (the band of this scene lists the stick, the post and shoulders; each
shoulder used to cost a group of strips, 0.3 s, before the stick was searched for). Whether the allowance should grow with time at all, now that
the time is not zero, is open issue 1b. (Even with computation for nothing the long-run yield
of this scene is 53 %: the 7 of 8 this table used to show were a lucky eight.)

Lowest visible point and base class (truth: the scene's lowest visible stick row):

| Scene | Class (visible / at horizon / unknown) | Bias, rms (rows) | rms / claimed |
|---|---|---|---|
| Flat green (base 0.3-0.6 row below the turf edge), A / B | 0 / 8 / 0 each | -0.51, 0.52 / -0.29, 0.29 | 0.8 / 0.5 |
| Base 6 rows below the edge (a rise behind the hole), A / B | 8 / 0 / 0 each | +0.26, 0.33 / +0.26, 0.40 | 1.1 / 1.2 |
| Base 8 rows below, grass 1.5 / 3 rows tall in front | 8 / 0 / 0 | +0.36, 0.39 / +0.29, 0.37 | 1.3 / 1.2 |
| The same, ragged grass 6 rows tall | 7 / 1 / 0 | +0.65, 1.05 | **3.0** (not met) |
| Turf texture 10 grey rms, flat, A / B | 0 / 8 / 0 each | -0.52, 0.52 / -0.26, 0.27 | 0.9 / 0.5 |
| Turf texture 10, base 6 rows below, A | 8 / 0 / 0 | +0.29, 0.55 | 1.1 |
| The same, B (0.8 px stick) | 2 / 6 / 0 | **-4.6, 5.4** | 0.9 |
| Lowest 0.3 m / a band of the stick without contrast | 0 / 0 / 8 each | not claimed | |

On a flat green the stick's last 0.3-0.6 row cannot be told from the turf edge: the lowest point
is reported AT the edge with 0.5-0.6 row of uncertainty, which is where the -0.3 to -0.5 row
bias comes from. Turf rows are no longer fitted at all (the old code took turf texture for the
stick and returned base rows tens of rows off with status OK). **Not met:** a 0.8 px stick is
followed 6 rows into rough turf in only 2 of 8 reads; in the others it is reported at the edge
and the hint of a continuation only widens the uncertainty (to about 6 rows), which is why the
last column still reads 0.9.

**B. Single-strip and single-pair figures (`tests/test_vision.c`, generator `gl_synth`).**
SNR = |stick level - background level| / noise sigma. One row = one left/right pair, 120 trials
with random position, disparity and sub-pixel phase; the disparity is taken over the lowest 40
rows unless stated. The widths and disparities of these trials are drawn independently (not one
range), which the review rightly called a scene that cannot occur: read this table as a test of
the line fit, not of a read. "Claimed" = mean reported uncertainty of the pair (noise + static
part, no calibration term).

| Condition | RMS px | Bias px | Worst px | Claimed px | Refused |
|---|---|---|---|---|---|
| 1.5 px, SNR 20, vertical | 0.0154 | -0.0004 | 0.051 | 0.0212 | 0 |
| 1.5 px, SNR 20, leaning 2 deg | 0.0157 | -0.0015 | 0.039 | 0.0183 | 0 |
| 1.5 px, SNR 20, dark on bright | 0.0155 | +0.0027 | 0.041 | 0.0214 | 0 |
| 1.5 px, SNR 20, 26 rows (0.4 m at 10 m) | 0.0226 | +0.0033 | 0.082 | 0.0249 | 0 |
| 1.5 px, SNR 20, textured background | 0.0459 | -0.0053 | 0.180 | 0.0493 | 0 |
| 1.5 px, SNR 10 | 0.0309 | +0.0004 | 0.075 | 0.0370 | 0 |
| 1.5 px, SNR 20, lens blur 1.0 px | 0.0226 | -0.0022 | 0.053 | 0.0291 | 0 |
| 0.7 px, SNR 20, vertical | 0.0326 | -0.0011 | 0.081 | 0.0356 | 0 |
| 0.7 px, SNR 20, leaning 0.6 deg | 0.0286 | -0.0040 | 0.115 | 0.0356 | 0 |
| 0.7 px, SNR 20, 26 rows | 0.0378 | +0.0009 | 0.092 | 0.0440 | 0 |
| 0.7 px, SNR 20, textured background | 0.0979 | -0.0003 | 0.287 | 0.1023 | 0 |
| 0.7 px, SNR 20, lens blur 0.4 px | 0.0379 | +0.0040 | 0.102 | 0.0543 | 0 |
| 0.5 px, SNR 20, 26 rows | 0.0487 | -0.0058 | 0.152 | 0.0609 | 0 |
| 4 px (3 m), SNR 20, 100 rows | 0.0087 | +0.0008 | 0.025 | 0.0126 | 0 |
| 8 px (1.5 m), SNR 20, 200 rows | 0.0078 | -0.0009 | 0.026 | 0.0095 | 0 |

Against the targets:

| Target | Result |
|---|---|
| Disparity RMS <= 0.08 px, 1.5 px stick, SNR 20 | **Met on clean scenes**: 0.015-0.023 px per pair (0.046 px on a textured background); 0.004 px per read of 8 groups. **Not met behind strong tree trunks** (0.17 px per read) and with fixed-pattern noise of 2 grey (0.08 px). |
| Disparity RMS <= 0.15 px, 0.7 px stick, SNR 20 | **Met**: 0.029-0.038 px per pair, 0.098 px on a textured background (single pairs off by up to 0.29 px). |
| No bias across sub-pixel phase beyond 0.03 px | **Met at the design blur**: largest mean error over 20 phase combinations of exactly vertical sticks 0.005 px (1.5 px stick) and 0.010 px (0.7 px stick). **Not met for a sharper lens**: 0.042 px for a 0.7 px stick at blur 0.4 px; this bias is now part of the claimed uncertainty (0.009 px per camera at the design blur, up to 0.07 px for a sharper profile, when the line does not sweep a pixel). |
| Both polarities | Dark-on-bright as good as bright-on-dark; a stick whose polarity flips half way is fitted through both parts. |
| Graceful failure with no stick | 0 false sticks in 60 stick-free tall strips, 0 false candidates in 60 stick-free bands, 0 of 5 edges of a person / wall / tree trunk accepted; and section A: 0 of 88 stick-free reads. |
| The reported uncertainty is honest | **Mostly**: error within 1.2 claimed sigma rms in every scene of section A except strong tree trunks (1.4) - and over-claimed by a large factor wherever the 0.05 px calibration term or a harmless column pattern dominates. The calibration term itself is a guess. |

Other figures:

* **L R R L**: with the stick swaying 0.20 px per frame, 8 groups give a mean error of +0.001 px
  (rms 0.004 px); pairing each L only with the next R gives -0.209 px.
* **Outliers**: flag cloth, a person crossing behind and a parallel rail: worst axis error
  0.032 px over 30 scenes; the fraction of rows used drops to 0.72.
* **Lowest visible point without a horizon prior** (single strip, the fit's unit test): bias
  +0.00 / RMS 0.08 row when the base is 8 rows below the turf horizon (1.5 px stick), RMS 0.18
  row for a 0.7 px stick, +0.26 to +0.29 row when the stick ends at the turf horizon. The read
  path always supplies a horizon prior; its figures are in section A.
* **Top of the stick**: RMS 0.13 row; angular height RMS 0.25 mrad.
* **Band detection** (640 x 96, SNR 20, lean -3..+3 deg, widths 0.7-10 px): 24/24 detected at
  each width, column RMS 0.12-0.24 px, lean RMS 0.6-1.0 deg, 32 of 32 horizon bins valid with
  0.045 row RMS.
* **Full chain** through the camera models with a mis-mounted right camera (4-6 mrad): range
  error -0.04 % at 3 m, -0.04 % at 6 m, +0.09 % at 10 m (rev C baseline of 20.0 mm); bearing error
  below 0.03 mrad.
* **Sharpness match** between the cameras: 0.98 with clean windows, 0.47 with one window smeared.

Things the synthetic tests do **not** cover: Bayer / YUV artefacts on sub-pixel lines, lens
distortion inside the strip, rolling shutter, non-Gaussian blur, real scenery, striped sticks
(beyond one stripe), heat shimmer, a smeared left window, two real flagsticks in view.

### Display

Rasterised lines, direction recovered by a least-squares fit of the lit pixels:

| Case | RMS deg | Worst deg |
|---|---|---|
| 7 px wide, all 1800 angles (0.1 deg steps), plain edges | 0.032 | 0.58 |
| 7 px wide, all 1800 angles, dithered edges | 0.038 | 0.32 |
| 7 px wide, -1..+1 deg in 0.01 deg steps, plain edges | 0.205 | 0.60 |
| 7 px wide, -1..+1 deg in 0.01 deg steps, dithered edges | 0.034 | 0.15 |
| Aim line through the ball (246 px off-screen), -13..+13 deg, 2601 angles | 0.050 | 0.28 |
| Aim line with the ball behind the marker (Precision spin of 172..188 deg), 1005 lines | 0.030 | 0.20 |

The 0.15 degree RMS target is met. The plain rule ("pixel centre within half a width of the
line") has a dead zone: within about 0.5 degree of a pixel axis several angles render
identically, which is exactly where straight putts live. The aim line therefore uses a 4-phase
ordered dither of the edges (quarter-pixel edge resolution, slightly rough edges). The fitted
line misses the ball centre by 0.24 px RMS (0.04 mm). Beyond about 13.5 degrees of aim the true
line leaves the aperture; its parallel through the centre is drawn instead, solid or dashed as
the result is (`test_aim_line_off_screen_fallback`; the side arrow of earlier versions, which
pointed away from the aim, is gone). `gl_gfx_rotate_180()`, with which a result is turned for
a golfer behind the marker, maps pixel (x, y) to (127 - x, 127 - y) and is its own inverse
(`test_rotate_180`); the aim-line figures above therefore hold for the turned screen too
(`test_e2e_putt.c` measures the Precision row on it: 0.18 mrad from the reference).

### Storage

* Ring log: power cut at each of 7479 points (every programmed byte with a randomly torn byte,
  every stage of every erase, 2.5 laps of the ring): 0 failures; 3596 double cuts: 0 failures;
  4 kB sectors with 2 kB raw-strip chunks, 120 sampled cuts: 0 failures.
* Blob store: 8975 cut points during updates and 354157 nested cuts during the repair at
  mount: 0 failures (every id holds its last acknowledged value or the one in flight); 4000 runs
  with three power cuts in a row: 0 with a lost value. A put is refused (`GL_ERR_FULL`, nothing
  changed) if the whole set would not fit one sector - 6 x 100-byte items offered to 3 x 256-byte
  sectors: 2 accepted, 4 refused, 2805 cut points, 0 acknowledged values lost (such a geometry
  used to lose values). The application's layout is checked at compile time.
* Log erase: 105 of the 7479 cut points interrupt a sector erase; an erase now proceeds in
  absolute sector order from a snapshot, appends are refused while it runs, and records older
  than the erase cannot reappear after a reset (sequence floor).
* A first version that relied on CRC-16 alone accepted a torn record 13 times in 1.2 million
  randomly torn cuts, as a 16-bit check must; records now carry a commit word programmed last,
  so an interrupted append is rejected by construction.

### Tilt, range, grain, protocol

* 1 s average at 240 Hz with 1 mg rms noise: worst error 0.22 mg (0.22 mrad) over 200 trials.
* Six-face solve: residual 3e-7 g. Temperature polynomial: residual 1e-8 g over -5..50 C.
* Zeroing maths (180-degree reversal on a hard flat surface that need not be level), end to
  end with noise, 174 degree turn measured by the gyro: bias recovered to 0.1 mrad. Ignoring the
  measured turn angle on a 172 degree turn on a surface sloped 1 % would cost 0.70 mrad.
* Precision Read: device bias cancels exactly; the two seating errors average.
* Range fusion Monte Carlo (4000 trials, 2-12 m): normalised error mean -0.02, rms 1.00, i.e.
  the reported sigma is honest. Stick height learned from a 9 cm wrong prior to 2 cm in 18 holes.
* Grain: the white-reference step removes a false modulation of 0.098 caused by a +-30 % LED
  spread; the acceptance threshold is read from the calibration record in every code path.
* Protocol: every single-bit corruption of a frame is rejected; 500 of 500 valid frames found in
  1 MB of protocol-like noise with no false frame.

## Memory

Flash (`make cross`, `-Os`, bytes; compile only, so library code - libm, memcpy, the STM32 HAL
and the USB library - is not included):

| Group | Module | text | data | bss |
|---|---|---|---|---|
| core | gl_vision | 19640 | 0 | 0 |
| core | gl_gfx | 4762 | 0 | 0 |
| core | gl_ui | 5069 | 0 | 0 |
| core | gl_log | 4102 | 0 | 0 |
| core | gl_tilt | 3264 | 0 | 0 |
| core | gl_range | 2276 | 0 | 0 |
| core | gl_proto | 2244 | 0 | 0 |
| core | gl_cal | 2160 | 0 | 0 |
| core | gl_grain | 1888 | 0 | 0 |
| core | gl_cam | 1504 | 0 | 0 |
| core | gl_math | 1772 | 0 | 0 |
| core | gl_settings | 1443 | 0 | 0 |
| core | gl_gesture | 970 | 0 | 0 |
| core | gl_font_data | 632 | 0 | 0 |
| core | gl_fmt | 477 | 0 | 0 |
| core | gl_solver_fit | 6942 | 0 | 0 |
| core | gl_solver_roll | 4242 | 0 | 0 |
| core | gl_solver_aim | 4028 | 0 | 0 |
| core | gl_solver | 2623 | 0 | 0 |
| core | gl_event | 148 | 0 | 0 |
| core | gl_crc | 100 | 0 | 0 |
| core | **total** | **70286** | **0** | **0** |
| drivers | ov7692 | 1941 | 0 | 0 |
| drivers | lsm6dsv16x | 1254 | 0 | 0 |
| drivers | mx25r | 870 | 0 | 0 |
| drivers | ls013b7dh03 | 674 | 0 | 0 |
| drivers | power | 1306 | 0 | 0 |
| drivers | grain_frontend | 530 | 0 | 0 |
| drivers | **total** | **6575** | **0** | **0** |
| app | gl_app | 9792 | 0 | 1366 |
| app | gl_read | 5179 | 0 | 0 |
| app | gl_usb | 2046 | 0 | 388 |
| app | gl_motion | 868 | 0 | 0 |
| app | gl_main | 24 | 0 | 320920 |
| app | **total** | **17909** | **0** | **322674** |
| all | **total** | **94770** | **0** | **322674** |

RAM (ARM `sizeof`, from the same build; core and drivers have no `.data` / `.bss` of their own,
all state is in the application object):

| Object | Bytes | Note |
|---|---|---|
| `gl_app_t` (bss of `gl_main`) | 320920 | everything below is inside it (312840 before builder 3: the optimisation of the vision costs 8064 bytes of work area; the phase-2 review added 16 bytes: the solver's two new options and a few flags) |
| - strip buffers `gl_read_t.img` | 184320 | FOUR 96 x 480 strips, one L R R L group (was two: the review showed that analysing while capturing ties the exposure spacing to the vision's run time); the 640 x 96 band (61440) uses the same memory |
| - `gl_vis_band_work_t` | 47360 | band analysis; 5120 bytes are new: the path sums of the sampled columns are kept from the first pass for the second |
| - `gl_vis_stick_work_t` x 4 | 69520 | one per strip of a group (17380 each, of which 5760 are the stored flank pixels; 736 are new: the coarse column of every row and the amplitude weights) |
| - LCD: `gl_gfx_t` + driver shadow | 2305 + 2060 | |
| - `gl_proto_t` | 2096 | two 1032-byte frame buffers |
| - solver inputs `gl_measurements_t` x 5 | 2000 | the shown read + 4 Survey drops (400 bytes each) |
| - `gl_solver_work_t` | 6160 | work area of the patch fit and its record (`gl_patch_fit_t`, 224 bytes); the aim solve needs none |
| - `gl_store_t` | 1084 | settings and calibration blobs |
| - everything else (UI, motion, tilt, survey, drivers, log, read state) | about 5900 | |
| static scratch in `gl_app.c` / `gl_usb.c` | 1754 | one raw-strip log record (978), two raw grain measurements (388 each) |
| STM32 backend | 1016 + about 2200 | `gl_hal_stm32u5.o` as compiled by `make cross-hal`: data 5, bss 1011 (HAL handles, pin shadows); the USB file (not compiled, estimate): two 1 kB rings and a packet buffer. The HAL's own data is not counted |
| main stack (recommended) | 4096 | see below |
| **total** | **about 330 kB of 786 kB** | does not fit SRAM1 + SRAM2 (256 kB): see "STM32U5 backend", linker script |

Stack (`-fstack-usage`, `-Os`, bytes per frame): `gl_vis_band_analyse` 672, `gls_fit_patch` 464,
`centroid_row_` 328, `gl_app_run_once` 312, `gls_roll` 304, `gl_cam_model_init` 304,
`gl_vis_stick_refine` 296, `gls_solve_kernel` 272, `measure_all_` 248, `gl_read_step` 240,
`fit_lm_` 240, `estimate_` 224, `do_actions_` 216, `gl_usb_service` 208, `gl_lcd_update` 200,
`gl_store_mount` 200, `gl_vis_stick_segment` 168, `screen_result_` 128, `gl_ui_render` 104 (the
phase-2 review moved four of them: `gl_app_run_once` 296 -> 312, `gls_solve_kernel` 264 -> 272,
`estimate_` 208 -> 224, and the result screen is now a function of its own). Builder 3's changes to the
vision moved its frames: the row measurement is now `centroid_row_` (328; `measure_row_` was
352), `measure_all_` grew from 144 to 248 (the reuse of the first pass), `gl_vis_stick_refine`
from 248 to 296, `gl_vis_band_analyse` from 632 to 672; the selection that replaced the sort
needs 24 bytes (`gl_select_inplace`, no recursion; its fallback `shell_sort_` 28). Worst chains:

| Chain | Bytes |
|---|---|
| run_once -> read step -> stick refinement -> measure_all_ -> centroid_row_ (312 + 240 + 296 + 248 + 328) | about 1420 |
| run_once -> read step -> band analysis -> selection (312 + 240 + 672 + 24 + 28) | about 1280 |
| run_once -> read step -> raw-strip hook -> log append -> flash driver | about 890 |
| run_once -> actions -> estimate -> aim solve on the patch -> kernel -> pace solve -> trial -> roll -> acceleration (312 + 216 + 40 + 224 + 80 + 272 + 104 + 112 + 304 + 40) | 1704 (the deepest; libm frames not included; 1648 before the review) |
| run_once -> actions -> estimate -> patch fit -> Levenberg-Marquardt -> residuals (312 + 216 + 40 + 224 + 464 + 240 + 112) | 1608 |
| run_once -> actions -> solve -> log append -> flash driver | about 800 |
| run_once -> USB service -> protocol -> log read -> log iterator -> flash driver | about 810 |
| run_once -> charge supervision -> temperature measurement (312 + 24 + 24) and the HAL below | about 360 + HAL |
| init -> store mount -> log walk -> flash driver | about 500 |

Add the HAL's own frames below the drivers (not measured: the HAL's sources were not compiled) and interrupt frames
(104 bytes each with FPU state, handlers are short; the backend's own frames, as compiled:
`clocks_init_` 248 and below it `clocks_osc_` 112, at start-up and after every Stop 2;
`gl_hal_clock_set` 144; everything else 64 or less). A 4 kB main stack leaves a factor of 2.4
over the deepest measured chain (1704 bytes, the solver's), before libm and the HAL.
No function recurses.

### Run time

**No part of this firmware has been timed on the target.** What is measured is the number of
instructions the x86-64 host build (`-O2`) executes, counted with callgrind (`make profile`;
`valgrind --tool=callgrind build/host/tests/test_read A_nominal 1`, inclusive count of
`gl_read_step`, for the nominal read). Phase 1 counted 145 million for the camera part of the
nominal read. Builder 3 reduced it **without changing a single result bit**:

| Stage (nominal read: 1.5 px stick at 6.6 m, 32 strips) | Phase 1 | Now | What was done |
|---|---|---|---|
| **Band analysis** (640 x 96, once) | 35,215,021 | 14,230,610 | medians by selection instead of sorting (16.7 million -> 3.0 million); the ridge sums slide along the row instead of being re-summed; the second pass takes the sums of the sampled columns from the first |
| **Strip refinement** (32 x) | 108,077,724 (3.38 million each) | 42,544,539 (1.33 million each) | the rows below |
| - row measurement (`measure_all_`) | 56,244,114 | 18,833,778 | the second pass reuses the first pass's centroid of every row whose window and coarse column are provably the same; the coarse column search is integer arithmetic (one division per row instead of one per candidate column); rows that cannot pass the significance test are dropped before their centroid is computed; `exp()` from a table with precomputed slopes |
| - medians and percentiles | 20.5 million | 3.0 million | selection (Wirth, median-of-three pivot, bounded rounds with a sort as fallback) instead of a Shell sort of every array |
| - amplitude along the line (`row_amp_at_`) | 18.1 million | 10,071,380 | weights of the window computed once per sub-pixel offset; rows below the lowest row that can matter are not visited |
| - weighted line fit (`irls_step_`) | 6.9 million | 3,971,536 | weights of a step kept for the next one |
| Everything else in `gl_read_step` (strip statistics, grouping, driver calls) | 1,484,508 | 1,384,391 | strip statistics: the column pass only if a pixel is saturated |
| **Camera part of the nominal read** | **144,777,253** | **58,159,540** | **-60 %** |
| The putt estimate, typical (method B1, 730 RK4 steps) | 295,316 | 295,316 | not touched |
| **Nominal read: vision + estimate** | **145.1 million** | **58.5 million** | the aim was 60 million |

(Both columns are builder 3's measurements, with computation for nothing so that both see the
same frames: `test_read A_nominal 1 0`. The vision's code has not changed since
(`tests/test_vision_equiv.c`). With the frames at the moments of the nominal compute factor
`make profile` counts 58,241,057 for the same read in this session, after the phase-2 review;
58,242,672 before it.)

**That the results are the same** is tested, not argued (`tests/test_vision_equiv.c`, part of
`make test`): the vision of phase 1 is kept, verbatim, as an oracle with renamed symbols
(`tests/vision_ref`), and both versions run on the same strips with every float of every
result compared as a bit pattern: 160 bands, 2131 strip refinements, 5692 segment fits,
683,040 rows - 1,497,340 values, **0 differ**; 960 more refinements on strips of only 2 to 5
grey levels (ties in the integer search), 0 differ; the selection against the sort on 6008
arrays including its worst case, 0 differ. The check was itself checked: of 9 deliberate
errors planted one at a time in the optimised code (the reuse without one of its three
conditions, a row limit off by one, a percentile index off by one, an offset in the band, a
stale weight in the fit, the tie rule of the integer search), 8 were caught by this test with
141 to 209,416 differing values; the ninth changed nothing because a later statement
overrides it, and its two real variants were caught (2702 and 248,797 values). (Builder 3
also had `build/host/tests/test_read --cpi 0` print, byte for byte, what `test_read` printed
in phase 1. That no longer holds, and is not meant to: the phase-2 review changed which band
lines a read probes, in `app/gl_read.c`, not the vision.)

**The 60 million are met for the nominal read and NOT for near sticks or several lines.**
One read of each scene of `tools/vision_bench.c` (the scene generator of `test_read.c`),
`gl_read_step` inclusive; "now" is `make profile` of this session:

| Scene | Strips | Phase 1 | Builder 3 | Now | What the cost table charges; rail on (`make bench-vision`) |
|---|---|---|---|---|---|
| A: 1.5 px stick, 6.6 m | 32 | 147,435,467 | 59,847,299 | 59,846,021 | 59.95 million; 2.42 s |
| B: 0.8 px, 12.3 m | 32 | 138,102,377 | 59,364,010 | 59,362,733 | 59.95; 2.42 s |
| **3.3 px, 3 m** | 32 (was 40: the stick's shoulder got a group, and so did the stick, before the read) | 178,732,435 | 86,690,409 | **71,991,668** | 78.51; 2.66 s (was 3.29 s) |
| **6.6 px, 1.5 m** | 32 | 168,493,313 | 86,695,037 | **86,693,728** | 78.51; 2.66 s |
| faint: 0.7 px at 10 % contrast (read with rows binned) | 32 | 100,553,036 | 43,913,225 | 43,911,981 | 44.59; 2.22 s |
| faint: 0.5 px at 20 % | 32 | 108,158,334 | 48,245,489 | 48,244,292 | 48.78; 2.23 s |
| **a person behind the stick** (three lines probed) | 44 | 197,913,409 | 88,052,456 | **88,050,771** | 84.03; 3.36 s |
| no stick | 0 | 35,219,331 | 14,262,080 | 14,262,020 | 14.27; 0.34 s |
| the Quick Read of `test_e2e.c` (1.6 px, 6 m, swaying) | 32 | not measured | 59,573,080 + 489,728 for its estimate of 1267 RK4 steps | not measured again (the cost table charges 60.4 million, as before) | 2.42 s |

A line whose fitted profile is wider than 1.2 px costs 1.8 to 2.2 million instructions per
strip instead of 1.4 (measured: the 3.3 px stick at 3 m and the 6.6 px one at 1.5 m, not the
1.5 px stick at 6.6 m; where between 3 and 6.6 m the change lies was not measured): the second
pass uses a wider window than the first, so its rows cannot take over the first pass's
centroids. That, and the extra groups when the band lists several REAL lines, is **what
remains**: 72 to 87 million instructions for a near stick, 88 million with a person behind
the stick. What the phase-2 review removed is the group of four strips that a near stick's own
shoulder used to cost (3 m scene: 86.7 -> 72.0 million, 40 -> 32 strips). In the end-to-end
world the same stick distances give 2.42 to 2.46 s of rail time (`test_near_stick_is_one_candidate`,
`test_quick_read_with_dcmi_crop_windowing`: 2.43 s), less than the 2.66 s of this bench's 3 m
scene; the two worlds render their sticks differently and the difference was not traced. The
end-to-end Quick Read is at the limit: 60.06 million with its estimate (about 0.4 million of
that are the simulator's own HAL functions inside `gl_read_step`; builder 3's figure).

**From instructions to seconds: an estimate with a stated range.** The simulator charges

    time = instructions x cycles per instruction / core clock

with the instruction counts of `hal/host/gl_sim_cost.h` (rounded from `make profile`):

| Stage | Host instructions | At 160 MHz: low 1.5 / nominal 2.0 / high 3.0 cycles per instruction | At 48 MHz, nominal |
|---|---|---|---|
| Band analysis, 640 x 96 | 14.27 million | 134 / 178 / 268 ms | 595 ms |
| One strip, line found unbinned (narrow line) | 1.39 million | 13 / 17 / 26 ms | 58 ms |
| One strip, wide line (> 1.2 px) | 1.97 million | 18 / 25 / 37 ms | 82 ms |
| One strip, found with 4 / 16 rows binned (after the failed tries before it) | 1.61 / 1.71 million | 15 / 20 / 30 and 16 / 21 / 32 ms | 67 / 71 ms |
| One strip, nothing found at any binning | 1.13 million | 11 / 14 / 21 ms | 47 ms |
| Strip statistics (first strip of each camera) | 0.44 million | 4 / 6 / 8 ms | 18 ms |
| One L R R L group (disparity, bookkeeping) | 0.04 million | 0.4 / 0.5 / 0.8 ms | 1.7 ms |
| The estimate | 0.04 million + 351 per RK4 step (typical 0.3 million) | 3 / 4 / 6 ms typical | 12 ms |
| One rendering of the screen | 0.234 million | (runs at 48 MHz) | 9.8 ms |

The table reproduces the measured whole reads of the eight scenes above within +9 % (the
3 m scene), -9 % (the 1.5 m scene) and -5 % (the person), the others within +2 % (`make
profile`, this session). What the cycles-per-
instruction factor stands for, and why its range is wide:

* the count is of **x86-64** instructions. A Cortex-M33 runs a comparable number of Thumb-2
  instructions for this code (no memory operands, so more loads and stores; fewer for
  conversions and rounding), most of them in 1 cycle, loads in 2, taken branches in 2-3, and
  **14 cycles for every single-precision division or square root**, of which the row
  measurement has about 15 per row;
* **low (1.5)**: the code behaves like plain integer code and the instruction cache (enabled
  by the backend) always hits;
* **high (3.0)**: flash wait states behind cache misses at 160 MHz (4 wait states), `-Os`
  code that is longer than the host's `-O2` code, newlib's `sqrtf` (it sets `errno`) and
  `memset`, data cache absent;
* **nominal (2.0)** is where the tests run. It is a judgement, not a measurement. **The factor
  is NOT VERIFIED** and cannot be here: there is no board, and the cross-compiled code was
  not run in an instruction-set simulator either (none was used; that would give instruction
  counts for the real code and narrow the range, and is the first thing to do).

What it means, with the tables under "End to end":

* **a Quick Read shows its result 4.1 - 4.8 s after the marker comes to rest** (4.4 s nominal),
  with the camera rail on for 2.2 - 2.8 s. These are the figures DESIGN_SPEC now states
  (amendment E15, taken from this model; "about three seconds" before). Of
  the 4.4 s, 1.85 s are stillness and the tilt read, 1.6 s the cameras' power-up, settling
  and 33 frames, and 1.0 s the computation (0.8 s) with the frame periods the captures wait
  for it. The vision of phase 1 would have needed 1.4 - 2.7 s of computation for the same read
  by the same arithmetic instead of 0.5 - 1.1 s (not simulated);
* a near stick: rail on for 2.4 - 2.7 s at the nominal factor (2.66 s in `make bench-vision`
  for the 3 m and the 1.5 m scene; 2.42 - 2.46 s in the end-to-end sweep of 2.25 to 3.75 m),
  where it was 3.0 - 3.3 s before the stick's shoulder stopped being probed; **several real
  lines still cost a group each**: 3.36 s with a person behind the stick, which is outside
  the 2.2 - 2.8 s the specification states;
* without the PLL (it failed to lock, or the backend's clock code does not work as written:
  **not verified**) the same read takes 6.0 s with the rail on for 3.8 s;
* the putt estimate is 0.5 % of a read, but a slope near the limit of what the green holds can
  cost seconds. The application now gives the solve a budget of 300,000 RK4 steps (plus the
  roll in progress): 105 million instructions by the cost table, **1.3 s at 160 MHz and the
  nominal factor, 1.0 - 2.0 s over the range** (4.4 s at 48 MHz), after which the result is a
  best-effort aim, shown as such. Without the budget the costliest estimate found needs
  575,247 steps (202 million instructions, 1.9 - 3.8 s) and the loop counters bound it only at
  1.35e9 instructions ("Solver"). In `tests/test_e2e_putt.c` the 7 % cross slope at Stimp 14
  took 137 trial rolls and 55,471 RK4 steps: 19.5 million instructions by the cost table,
  0.24 s.

The firmware's own code is 94.8 kB of the 2 MB flash before libraries (phase 2, builder 2 added 2.2 kB: result screen, charge gate and NTC, settings, hand-over; builder 3 added 3.5 kB: the faster vision is 3.0 kB larger, the selection 0.3 kB; the phase-2 review added 1.5 kB: 0.7 kB in the solver, 0.4 kB in the UI and graphics, 0.5 kB in the application), plus 6.7 kB for the STM32 backend as compiled by `make cross-hal` and the vendor's HAL and USB library, which were not compiled. The link probe of `make cross` (firmware objects + newlib's libm and libc, no HAL, no start-up code) has 107,244 bytes of text.

## Device registers and commands: "from memory - verify against datasheet"

Everything the drivers and the simulator models assume about the LSM6DSV16X and the MX25R6435F,
in one place. **Every row is from memory of the datasheet** (ST DS13510; Macronix MX25R6435F)
**and must be verified against it** before the driver is trusted. The drivers use nothing
that is not in this table.

| Device | Item | Value assumed | Used for | Status |
|---|---|---|---|---|
| LSM6DSV16X | SPI | 4-wire, mode 3, MSB first; first byte bit 7 = read, bits 6..0 = address; up to 10 MHz (5 MHz used) | all access | from memory - verify against datasheet |
| LSM6DSV16X | INT2_CTRL 0x0E | bit 0 = accelerometer data ready on INT2 | sample interrupt | from memory - verify against datasheet |
| LSM6DSV16X | WHO_AM_I 0x0F | reads 0x70 | probe | from memory - verify against datasheet |
| LSM6DSV16X | CTRL1 0x10 | [3:0] accel ODR: 0 = off, 3 = 15 Hz, 7 = 240 Hz; [6:4] mode: 0 = high performance, 4 = low-power 1 | 0x07 measure, 0x43 wake | from memory - verify against datasheet |
| LSM6DSV16X | CTRL2 0x11 | [3:0] gyro ODR (7 = 240 Hz), [6:4] mode (0 = high performance) | 0x07 measure, 0x00 off | from memory - verify against datasheet |
| LSM6DSV16X | CTRL4 0x13 | bit 1 DRDY_PULSED: 0 = data-ready stays high until the data is read (LATCHED, what the application's "level = work to do" loop needs), 1 = 65 us pulse | 0x00, written explicitly (`GL_PROV_IMU_DRDY_PULSED`) | from memory - verify against datasheet |
| LSM6DSV16X | CTRL3 0x12 | bit 6 BDU, bit 2 IF_INC (address auto-increment), bit 0 SW_RESET; reset value 0x44 | reset, 0x44 | from memory - verify against datasheet |
| LSM6DSV16X | CTRL6 0x15 | [3:0] gyro full scale: 3 = +-1000 dps | 0x03 | from memory - verify against datasheet |
| LSM6DSV16X | CTRL8 0x17 | [1:0] accel full scale: 0 = +-2 g | 0x00 | from memory - verify against datasheet |
| LSM6DSV16X | STATUS_REG 0x1E | bit 0 XLDA, bit 1 GDA, bit 2 TDA | data-ready poll | from memory - verify against datasheet |
| LSM6DSV16X | OUT_TEMP 0x20-0x21 | int16 little-endian, 256 LSB per K, 0 = 25 C; absolute accuracy unknown (a die sensor: typically several K) | charge gate (with the MCU die sensor as second opinion; a raw 0x0000 = exactly 25.000 C is refused as "not a measurement"), tilt compensation | from memory - verify against datasheet |
| LSM6DSV16X | OUTX_L_G 0x22 .. OUTZ_H_A 0x2D | gyro X Y Z then accel X Y Z, int16 little-endian, one 12-byte burst | samples | from memory - verify against datasheet |
| LSM6DSV16X | Sensitivities | 0.061 mg/LSB at +-2 g; 35 mdps/LSB at +-1000 dps | scale factors handed to `gl_tilt` | from memory - verify against datasheet |
| LSM6DSV16X | WAKE_UP_SRC 0x45 | bit 3 WU_IA; reading clears the latch | wake cause | from memory - verify against datasheet |
| LSM6DSV16X | FUNCTIONS_ENABLE 0x50 | bit 7 INTERRUPTS_ENABLE | wake-on-motion | from memory - verify against datasheet |
| LSM6DSV16X | TAP_CFG0 0x56 | 0x00: slope filter (bit 4 SLOPE_FDS = 0), interrupts not latched | wake-on-motion | from memory - verify against datasheet |
| LSM6DSV16X | WAKE_UP_THS 0x5B | [5:0] threshold, 7.8125 mg per LSB at the reset threshold weight | 62 mg -> code 8 | from memory - verify against datasheet |
| LSM6DSV16X | WAKE_UP_DUR 0x5C | 0x00: one sample over threshold wakes | wake-on-motion | from memory - verify against datasheet |
| LSM6DSV16X | MD1_CFG 0x5E | bit 5 = wake-up event on INT1 | 0x20 | from memory - verify against datasheet |
| LSM6DSV16X | Behaviour | temperature output valid while the accelerometer runs; software reset completes within 1 ms; INT pins push-pull, active high; data-ready on INT2 latched until the output registers are read (the earlier text said "pulsed", which the driver never selected) | driver sequences | from memory - verify against datasheet |
| MX25R6435F | SPI | mode 0 (mode 3 also accepted), MSB first; 8 MHz used | all access | from memory - verify against datasheet |
| MX25R6435F | RDID 9Fh | returns C2h 28h 17h | probe | from memory - verify against datasheet |
| MX25R6435F | RDSR 05h | status: bit 0 WIP, bit 1 WEL | busy polling | from memory - verify against datasheet |
| MX25R6435F | WREN 06h | sets WEL; needed before every PP and SE; cleared when they finish | program, erase | from memory - verify against datasheet |
| MX25R6435F | READ 03h | + 3 address bytes, then data, no dummy byte | read | from memory - verify against datasheet |
| MX25R6435F | PP 02h | + 3 address bytes + 1..256 bytes inside one 256-byte page; bits can only be cleared | program | from memory - verify against datasheet |
| MX25R6435F | SE 20h | + 3 address bytes: erases one 4 kB sector | erase | from memory - verify against datasheet |
| MX25R6435F | DP B9h / RDP ABh | deep power-down / release; about 30-35 us before the next command (100 us used) | sleep current | from memory - verify against datasheet |
| MX25R6435F | Timing | page program 3 ms typical / 10 ms max, sector erase 60 ms typical / 300 ms max in low-power mode (time-outs 100 ms and 2 s) | time-outs | from memory - verify against datasheet |

The LS013B7DH03 protocol (mode byte bits, line format, active-high chip select, LSB first) is
taken from `docs/research/display.md`, which confirmed it from four open-source drivers, not from
the Sharp datasheet; its chip-select set-up / hold / low times (6 / 2 / 2 us as remembered, 10 / 5
/ 5 us used) are `GL_PROV_LCD_SCS_*`.

## OVM7692 register sources

Register ADDRESSES and the bit masks below were read in the public Apache-2.0 Analog Devices
msdk driver (`Libraries/MiscDrivers/Camera/ov7692_regs.h` and `ov7692.c` at
raw.githubusercontent.com/analogdevicesinc/msdk/main/...), re-read for this work package; no
code was copied. The driver writes only these registers and leaves clock tree, exposure and
image processing at the sensor's reset values, for which this project has no verified numbers.

| Register | In the public driver | What this firmware assumes beyond it |
|---|---|---|
| SCCB address 0x3C | yes | |
| 0x0A / 0x0B PIDH / PIDL | addresses | the VALUE 0x7692 (`GL_PROV_OV7692_PID`; enforcement can be switched off) |
| 0x0C | bit 7 vertical flip, bit 6 horizontal mirror, bit 4 YU/YV swap, reset value 0x16 | **bits 2 and 1 = output drive, 1 = driven** (`GL_PROV_OV7692_REG0C_BIT_SET_MEANS_DRIVEN`; meaning from the OV7690 datasheet, polarity inferred from the reset value). Bit 4 is KEPT as in the reset value and the public driver (`GL_PROV_OV7692_REG0C_KEEP_BITS` = 0x10; the driver used to clear it, which would have swapped the byte order that `GL_PROV_OV7692_Y_IS_FIRST_BYTE` assumes): 0x90 released, 0x96 driving |
| 0x0E | bit 3 sleep | |
| 0x12 | bit 7 software reset, 0x00 = YUV422 | the reset bit clears itself when the reset is done |
| 0x17-0x1A HSTART, HSIZE, VSTART, VSIZE | addresses | **units, origin and border** (`GL_PROV_OV7692_HSTART_FULL` ..), inferred from OV7690 reset values; the reason the DCMI-crop fallback exists |
| 0xC8-0xCB input size, 0xCC-0xCF output size | yes (high bits / low byte) | |
| 0xFF bank select, bank 1 0xB5 = 0x30 | yes: MIPI and low-power transmitter powered down | |
| - | | Y is the first byte of each YUV pair, sync polarities, PCLK edge, frame period at 12 MHz, PWDN polarity, image orientation behind the prism: all `GL_PROV_*` |

## PROVISIONAL constants (`core/gl_provisional.h`)

Every one is a named constant with a comment saying where the value comes from and what to
check. Changing one is the whole firmware change if the fact turns out different.

| Group | Constants | What is uncertain |
|---|---|---|
| OVM7692 bus | `GL_PROV_OV7692_REG0C_BIT_SET_MEANS_DRIVEN`, `_REG0C_KEEP_BITS`, `_PWDN_ACTIVE_HIGH`, `_PWDN_TRISTATES_OUTPUTS` (0: NOT assumed), `GL_PROV_CAM_SLEEP_IDLE_ON_EVERY_SWITCH`, `GL_PROV_OV7692_SCCB_ACKS` | tri-state bit polarity (DESIGN_SPEC PROVISIONAL), PWDN polarity, whether PWDN frees the bus (assumed NOT to; then both sensors' pads overlap for 14.4 ms at every power-up, see open issue 3), idle-camera policy, the 9th SCCB bit |
| OVM7692 image | `GL_PROV_CAM_SENSOR_VFLIP`, `_HMIRROR`, `GL_PROV_OV7692_Y_IS_FIRST_BYTE`, `_VSYNC_ACTIVE_HIGH`, `_HREF_ACTIVE_HIGH`, `_PCLK_RISING`, `_PID`, `_ENFORCE_PID` | orientation behind the prism, byte order, sync polarities, product id value |
| OVM7692 window | `GL_PROV_OV7692_SENSOR_WINDOWING`, `_HSTART_FULL`, `_VSTART_FULL`, `_H_UNIT_PX`, `_V_UNIT_LINES`, `_H_BORDER_PX`, `_V_BORDER_LINES` | meaning of the start / size registers; set `_SENSOR_WINDOWING` to 0 to use the DCMI crop instead |
| OVM7692 timing | `GL_PROV_CAM_XVCLK_HZ`, `_RAIL_SETTLE_MS`, `_CLOCK_SETTLE_MS`, `_FRAME_PERIOD_MS`, `_SETTLE_FRAMES`, `GL_PROV_OV7692_RESET_TIMEOUT_MS` | power-up delays, frame rate at 12 MHz with reset clock settings, frames to settle |
| LCD | `GL_PROV_LCD_FPC_PIN_*` (10), `GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS`, `GL_PROV_LCD_ROW0_AT_FRONT`, `_COL0_AT_LEFT`, `_ACTIVE_CENTRE_Y_MM`, `_SPI_MAX_HZ`, `_VDD_MIN_MV`, `_SCS_SETUP_US`, `_SCS_HOLD_US`, `_SCS_LOW_US` | FPC pin order and pin-1 side (DESIGN_SPEC PROVISIONAL), EXTCOMIN period (547 ticks = 59.905 Hz, the divider rev C2 specifies; the generator reads it from the spec and a test compares the two), panel orientation, active-area offset, timing |
| MCU | `GL_PROV_LPTIM_PWM_RUNS_IN_STOP2`, `GL_PROV_USB_CRYSTALLESS_HSI48_CRS`, the 28 PROPOSED rows of `hal/stm32u5/gl_pins.h` | EXTCOMIN in Stop 2 (if 0 the application stays in idle sleep while the display is on), crystal-less USB, pin assignment |
| IMU | `GL_PROV_IMU_MARKER_{X,Y,Z}_AXIS`, `_SIGN`, `GL_PROV_IMU_WAKE_THRESHOLD_MG`, `GL_PROV_IMU_DRDY_PULSED` | mounting orientation on the PCB (identity is a placeholder), wake threshold, data-ready mode |
| Flash | `GL_PROV_MX25R_PROG_TIMEOUT_MS`, `_ERASE_TIMEOUT_MS`, `_DP_DELAY_US`, `_SPI_HZ` | timing |
| Grain | `GL_PROV_GRAIN_RED_ANODE_ON_LOW_PIN`, `_SETTLE_US`, `_ADC_AVG`, `_ADC_SAMPLE_US`, `_POWER_SETTLE_MS`, `_MOD_THRESHOLD_DEFAULT`, `_MAX_EQUIV_SLOPE`, `_HARMONIC_SIGN`, `_KAPPA_BENT`, `_KAPPA_POA`, `_KAPPA_BERMUDA` | charlieplex wiring (proposal), settling, and the unproven physics; the acceptance threshold used is always the one in the calibration record |
| Power | `GL_PROV_BATT_LOW_MV`, `_CRITICAL_MV`, `_FULL_MV`, `_EMPTY_MV`, `_DIVIDER_RATIO`, `GL_PROV_BATT_STORAGE_MV`, `GL_PROV_CHARGE_TEMP_MIN_C`, `_MAX_C`, `_HYST_C` (2 K), `_GUARD_C` (1.5 K), `_MAX_DISAGREE_C` (10 K) | cell thresholds (no cell datasheet), hysteresis, the guard band (from the tolerance budget computed in `test_drv_power.c`; it does not cover a cell-to-NTC gradient), how far the NTC may be from a die sensor |
| Cell NTC | `GL_PROV_NTC_R25_OHM` (10 k), `_B_K` (3380), `_SERIES_OHM` (10.0 k), `_SETTLE_US` (500), `_ADC_AVG` (8), `_ADC_SAMPLE_US` (20), `_OPEN_FRACTION` (0.98), `_SHORT_FRACTION` (0.02), `_IDLE_MAX_FRACTION` (0.05) | part values as specified in rev C2; settling time for the node (source impedance up to 10 kohm into the ADC's sampling capacitor and whatever capacitance the layout adds: the 500 us is a guess with margin, to be checked on the board); the detection thresholds |
| Estimates | `GL_PROV_SEATING_SIGMA_RAD`, `GL_PROV_STICK_TOTAL_HEIGHT_M`, `_IN_CUP_M`, `_HEIGHT_REL_SIGMA`, `_DIA_MIN_M`, `_DIA_MAX_M` (now used: the width a flagstick may have at its disparity), `GL_PROV_STEREO_CAL_SIGMA_PX` (0.05 px, added to every disparity sigma), `GL_PROV_LENS_BLUR_SIGMA_MIN_PX` / `_MAX_PX` (0.45-0.80 px) | not measurements; the blur range decides which posts are rejected as "too wide for their disparity" and must be replaced by the measured blur at EVT |

Tuning constants that are our own choices rather than hardware facts (gesture timing, repeat
counts, flash layout, the charge supervision period of 5 s and the 12 s staleness limit, the
confidence factors 0.6 / 0.6 / 0.7 and the caps 0.2 (best effort) and 0.09 (flag out), the
Survey's "at the ball" fraction 0.85, and from the phase-2 review the near-miss distance of
5 mm, the solve's budget of 300,000 RK4 steps and the shoulder ratio of 4) are in
`app/gl_app_cfg.h`; none has been tuned on hardware or with golfers.

Two assumptions that are not in DESIGN_SPEC and must be checked against the mechanical design:
the ball centre is taken at outer radius + ball radius = 23.0 + 21.335 = 44.335 mm ahead of the
marker centre (`GL_CFG_BALL_CENTRE_Y_MM`; 39.7 mm if the ball rests against the flat visor
face), and the grain LED azimuths are counter-clockwise from marker +x seen from above (now
stated in the rev C YAML).

## What is not done

* **No hardware run of anything, and no linked image.** The main file of the STM32 backend
  compiles against the vendor's headers (`make cross-hal`); its USB file is uncompiled; the
  HAL sources, start-up code, linker script and the USB board glue (`usbd_conf.c`,
  `usbd_desc.c`, VID / PID) do not exist here ("STM32U5 backend": what a flashable image
  takes). Timing on the target (vision run time, SCCB bit-bang, Stop 2 wake latency at 240 Hz)
  is unmeasured: every time in this file is the simulator's, with computation charged through
  an estimated factor (1.5 - 3 cycles per host instruction).
* **The compute-time model is not calibrated.** Not measured: the factor itself; the cost of
  the main loop, the drivers and the IMU filtering between the trace points (charged nothing);
  the PLL lock and voltage-range switch times; the instruction counts of the cross-compiled
  code (no instruction-set simulator was used). The supply currents behind the charge and
  battery-life figures are all provisional.
* **The solver on the target.** The port is tested on the host only; its run time on the
  Cortex-M33 is an estimate (see "Solver"), and newlib's single-precision libm has not been
  compared with the host's (open issue 26). The link probe of `make cross` shows which
  library functions a link against the installed newlib would bring in, not what they compute.
* **The specification's amendments E1, E11, E12, E13** (charger with its own temperature
  input and the opposite `CHG_INHIBIT` polarity; two level zeros; stored display rotation; no
  read above 60 C and a ship mode): not implemented ("DESIGN_SPEC amendments E1 to E16").
* **Nine findings of the phase-2 review are not fixed** (2, 9, 10, 19, 20, 27, 28, 32, 33:
  "Phase-2 review: what was fixed" and the open issues it names), and four only in part.
* **The rev C2 changes on the target.** Everything in "Charger and cell temperature" and "Board
  changes of rev C2" was run on the simulator, whose NTC, charger and clock models encode this
  project's reading of the specification. Not verified: the clock switch (PLL, voltage range,
  booster, flash latency: it compiles against the vendor's headers and has never run), that PH1 is an FT pin, ADC1_IN13 on PC4, the NTC
  settling time, the real part's R-T curve against the B-parameter equation, and the thermal
  coupling between the cell and the NTC.
* **Estimator results that no simulated read produces** (pace limited, straight fallback, a
  kept near miss, fit on its iteration limit, poor horizon): only their mapping to the screen
  is tested.
* **Grain as a solver option.** `use_grain` now follows the GRAIN setting, which ships OFF.
  With GRAIN ON the line moves by what the measured grain and the grass's coefficient say
  (4.7 mrad for bentgrass and 27 mrad for bermuda in the test scene), and nothing here shows
  that this is right: the coefficients and the optical principle are unproven
  (`GL_PROV_GRAIN_KAPPA_*`), and there is no on-device noise-floor procedure.
* **Camera exposure and clocking.** No exposure, gain, PLL or frame-rate register is written
  (no verified values): the sensors run on their reset settings. The sun-in-frame flag exists;
  nothing reacts to it beyond the confidence figure.
* **Factory calibration procedures** beyond six-face and grain white reference: camera
  intrinsics / extrinsics and the accelerometer temperature polynomial can only be written by a
  host tool (`SET_CAL`; `gl_tilt_tempco_fit()` exists in core); `CAM_HORIZON` and `GRAIN_FLOOR`
  answer `GL_ERR_UNSUPPORTED`. No host-side tool exists.
* **Grain** is wired through (measurement during the tilt read when enabled, estimate handed to
  the solver) but ships disabled and has no on-device noise-floor procedure.
* **Stimp by watching a rolled ball** (optional later feature in DESIGN_SPEC): not started.
* **Firmware update** other than the ROM DFU jump; no bootloader of our own, no image check.
  Once in the ROM bootloader there is no way back without a host or a power cycle (no time-out
  can be added from the application; the jump is gated by `UNLOCK`, by VBUS and by the charge
  gate), **and nothing watches the cell temperature there while the charger runs** (NOT MET,
  see "Charger and cell temperature").
* **Vision speed beyond the nominal read.** 58 million host instructions for the nominal read
  (145 before), but 72 - 87 million for a stick whose line is wider than 1.2 px (3 m and
  nearer in the bench scenes) and 88 million with a person behind the stick: the second pass
  of a wide line still measures every row afresh, and every extra REAL line costs a group of
  four strips (the stick's own shoulder no longer does); see "Run time". Nothing was tuned for the Cortex-M33
  itself (no fixed-point path, no CMSIS-DSP, no assembly).
* **Vision cases known not to work** (pinned by `tests/test_read.c`, listed under "Vision"):
  sticks under about 0.7 px at under 10 % contrast; a 0.8 px stick with a person, a post or a
  second pole within a few pixels; a low-contrast stick against strong tree trunks; following a
  thin stick into rough turf; the lowest point behind tall ragged grass; **and, with honest
  timing, a 1.5 px stick with a post 14 px beside it** (26 of 64 reads give a disparity; 34
  while computation was free). Also from the phase-2 review and not looked into here: at 2 to
  3 m on a putt that is level along its line the hole is read 3 to 5 mm low, and at 0.6 m the
  flagstick is refused (open issue 30).
* **Found by the honest timing and not fixed** (each pinned by a test as NOT MET): the result
  comes 4.4 s after the marker is at rest, not within the 4.0 s the end-to-end test once
  allowed (the specification, which said "about three seconds", now states 4.1 to 4.8 s from
  this model: amendment E15); a Survey fit loses its
  curvature when the base of the stick at a drop is within the 1.5-row margin of "visible"
  (`test_survey_second_drop`); a drift that reverses inside a group of four strips gives a
  disparity 0.04 px off under a claimed 0.05 px and is not noticed
  (`test_lrrl_timing_with_vision_run_time`).
* **Gesture tuning.** Thresholds are guesses; taps are detected in software from the 240 Hz
  stream (the IMU's embedded tap function is not used). The gesture maths is unit-tested, the
  thresholds are not field-tested.
* **Fuel gauging:** the percentage is a straight line between two provisional voltages.

## Open issues that need a decision

Hardware and system decisions first: none of them can be closed in firmware.

1. **Read time, and the charge of a read.** The vision is down from 145 to 58 million host
   instructions for the nominal read (bit-identical results), and the simulator charges
   computation its time: a Quick Read shows its result 4.1 - 4.8 s after the marker is at rest
   (4.4 s at the nominal factor; 6.0 s if the PLL does not lock) and the camera rail is on for
   2.2 - 2.8 s. DESIGN_SPEC now states exactly these figures (amendment E15; "about three
   seconds" before), so the specification follows the model; nothing has been measured.
   **Reads outside those figures after the phase-2 review:** a person behind the stick or two
   real lines in the band (rail on for 3.4 s at the nominal factor), and near sticks at the
   high factor (the review measured 2.99 s of rail and 5.0 s to the result at 1.5 m, factor
   3). The near-stick case the review found (a third of the reads between 2.25 and 4.5 m, 0.6
   s longer) is fixed. **The charge**: the review compared the model's 226 mAs per read (86 mA
   on the camera rail) with the battery budget of `docs/research/power.md` (40 mAs nominal,
   141 mAs worst case, with the cameras at 10.7 mA): 5.7 times the nominal budget. One of
   the two documents is wrong about the cameras' current, and only a measurement can say
   which. **To decide:** accept about 4.5 s; or shorten what is not computation (0.77 s to
   establish stillness, 1.08 s of tilt read - the cameras could be powered and the band taken
   DURING the tilt read, which would hide the 0.34 s of power-up and band and most of the
   band's analysis; fewer than 8 groups for an easy stick); or spend more on the remaining 0.8 s
   of computation. **Still open underneath:** the cycles-per-instruction factor is an estimate
   (not measured: no board, no instruction-set simulator); the backend's clock code compiles
   but has never run; the cost of each clock switch and the current at 160 MHz are unmeasured.
   1b. **The search allowance for sway grows with the compute time** (3 px per second since
   the band, `GL_APP_SWAY_ALLOW_PX_PER_S`): it was written when the band's analysis took no
   simulated time. With 0.18 s it lets a post 14 px beside the stick ruin many reads ("Vision":
   34 of 64 reads with a disparity fall to 26 at the nominal factor - 11 before the shoulders
   were dropped - and to 0 at the high factor; with the allowance at 0 the compute time made
   no difference in builder 3's scratch build). To decide: a fixed allowance, one that follows
   the measured sway, or analysing the band while the first strips are already being taken.
2. **Charger when the MCU is not in control.** Answered for the unpowered MCU by rev C2 (the
   charger runs by default). What remains is the other side of that default, and it is NOT MET
   in firmware: **in the ROM bootloader nothing can stop the charger** (the firmware only
   refuses to enter DFU outside the temperature window), and **a hung firmware is not
   supervised until the watchdog fires (32 s)**. If either matters for the cell's approval,
   it needs hardware: a charger with an NTC input, or a comparator on the NTC node that pulls
   `CHG_INHIBIT` by itself. Also for the schematic: `CHG_INHIBIT` must be on an FT pin (PH1 as
   remembered: verify), or the unpowered MCU clamps the gate and defeats the default.
   **The specification has since chosen the hardware answer (amendment E1: BQ25101 with its
   own thermistor input; `CHG_INHIBIT` push-pull, HIGH = stop).** This firmware still drives
   the rev C2 circuit (open drain, LOW = stop) because its brief says so; on an E1 board its
   stop does nothing. **To decide: which document rules for the next phase.** If E1: a new
   charger driver and simulator model, the cradle messages (the charger, not the firmware,
   then decides), and the two NOT MET rows become hardware-covered. Pinned meanwhile as NOT
   MET (`tests/test_pins.c`). Related, from the same review: with the start-up order fixed
   the watchdog bounds a hang AFTER `gl_hal_init()`; a hang before it (start-up code, RAM
   initialisation) is covered only by the hardware-watchdog option bit (issue 12).
3. **Both cameras on the shared bus at power-up.** Unless PWDN tri-states the OVM7692 pads
   (unconfirmed, `GL_PROV_OV7692_PWDN_TRISTATES_OUTPUTS` = 0), both sensors drive the eight data
   lines and the three sync lines against each other for 14.4 ms of every power-up (6.4 ms of it
   with one streaming) before the firmware can switch one off through SCCB. Writing register
   0x0C first does not shorten this, because the software reset re-enables the pads. Options
   for the hardware: confirm the PWDN behaviour on the bench, series resistors, a bus switch, or
   separate rail enables. The simulator measures the overlap and the driver test asserts it, so
   a change is visible.
4. **ROM-bootloader pins on camera nets.** PB9 (DCMI D7) and PA6 (PIXCLK) are pins the ROM
   bootloader may drive or sample (table from memory of AN2606: verify). In DFU mode the camera
   rail is off, so a driven pin back-feeds the sensors through their protection diodes. Either
   move the nets or accept and document the level; `tests/test_pins.c` prints the two rows.
   Also for the netlist: charger STAT (open drain) into PB0 needs its pull-up to a rail that is
   on whenever VBUS is; the LCD chip select needs a pull-down for the time before the MCU runs.
5. **Charge temperature.** The cell NTC is now the input, with the die sensors as a
   plausibility check (within 10 K of at least one). Decide: (a) whether the guard band of
   1.5 K, which covers the part tolerances and the ADC only, should be widened for the
   gradient between the cell and an NTC "within 1 mm of its edge", which nobody has measured,
   **and for the error of the one-B equation against the part's R-T table**: the budget uses
   0.90 K of the 1.5 K at 0 C and 1.09 K at 45 C, which leaves 0.6 K and 0.4 K for an error
   that is NOT VERIFIED (no data sheet table here; amendment E2 also changes the part to a
   Murata NCU15XH103F60RC, whose B value has not been checked against the 3380 K in
   `gl_provisional.h`). A table from the data sheet in `test_drv_power.c` would settle it;
   (b) whether "at least one die sensor agrees" is the wanted rule, or "both" (safer against a
   wrong NTC, but a warm MCU during USB would then stop a healthy charge); (c) whether a unit
   whose NTC is broken should refuse to charge for good, as it does now (it says `TEMP SENSOR`
   on the cradle screen), since such a unit eventually cannot be revived.
6. **Stereo calibration term.** `GL_PROV_STEREO_CAL_SIGMA_PX` = 0.05 px is a guess and it is
   now the largest part of the claimed range uncertainty on every clean scene (2.3 % at 6 m,
   3.8 % at 10 m). It has to come from the calibration fixture's repeatability.
7. **Lens blur.** The "too wide for its disparity" test needs the blur; until it is measured
   the range 0.45-0.80 px is assumed, which rejects a 3 px post at 25 m but would not reject a
   2 px one, and rejects a real stick seen through a smeared LEFT window.

Product decisions:

8. **The weaker tiers.** A read can end as "left camera only" (bearing and elevations, no
   disparity; the estimator ranges it from the angular height if top and base of the stick are
   visible, otherwise the dialled distance is applied along the measured bearing) or as
   "band-only bearing" (not used and not logged). Confirm that a single-camera stick, which cannot be checked against a disparity,
   should be aimed at; and whether `ambiguous` should block the result rather than lower the
   confidence figure (x 0.6). As built: both are aimed at with a solid line, a message (`1
   CAMERA`, `2 LINES SEEN`, or `NO RANGE` when the single camera could not range the stick) and
   0.6 of the confidence each.
9. **Base of the stick for ranging.** "At horizon" covers a base just visible on a flat green
   and one hidden behind a crown. For RANGE (and for learning the stick height) the application
   treats the lowest visible point as the base in both cases, with the read's own uncertainty
   for it (0.5-0.6 row at the turf edge, more with a hint of a continuation) on top of 0.3 row;
   for the SLOPE use the solver receives the strict flag. The estimator's owner should confirm.
10. **Pin assignment.** 28 pins are this firmware's proposal (table in `tools/gen_pins.py`),
    including bit-banged SCCB on PB5 / PB3 / PA10, the IMU wake line on PC13, PWDN on PH0 and
    PC12, `CHG_INHIBIT` on PH1, `NTC_SENSE` on PC4 and, because rev C2 needs 47 signals where
    the LQFP-64 has 46 I/O pads, **`NTC_BIAS` on PH3-BOOT0**. The schematic may choose
    differently (drop a signal, share one, or a larger package); only the generator changes.
11. **Raw-strip logging level ALL keeps the camera rail on for about 41 s per read** (48 s in
    all; about 1 mAh of a 43 mAh cell, and heat). Level FIRST costs 2.6 s. If ALL is wanted in
    the field it needs a different capture plan (cameras off between groups) or less data.
12. **Watchdog in Stop mode, and before `main()`.** The independent watchdog keeps running in
    Stop 2, so the sleeping device wakes every 16 s for a few microseconds. Freezing it in
    Stop by option byte would avoid that at the price of no supervision while asleep - and
    since the phase-2 review that wake-up is also what bounds a lost VBUS edge (15.5 s at
    worst), so it should stay. The watchdog is started by software, first thing in
    `gl_hal_init()`; a hang before that is covered only if the **hardware-watchdog option bit
    (`IWDG_SW` = 0)** is programmed in production. To decide, and to put into the production
    programming procedure; it cannot be set from here. Related: after 8 failed IMU
    recoveries the firmware deliberately lets the watchdog reset it; a unit with a dead IMU
    then resets every 32 s while awake. Decide whether it should give up and sleep instead.
13. **Idle camera kept awake** during L R R L (deviation from the letter of DESIGN_SPEC, see
    Drivers) and **OVM7692 reset output size** (the public driver's comments suggest 384 lines).
14. **Zeroing over USB** is refused rather than "armed for when the marker leaves the cradle".
    Since the review the other factory procedures also need `UNLOCK` (the zeroing and ABORT do
    not). If the factory wants to trigger zeroing from the fixture, a guarded transition has to
    be added.
15. **DESIGN_SPEC text:** the EXTCOMIN divider is corrected in rev C2 (547); still to correct:
    the register table's "INT pins pulsed" (latched is used and selected explicitly). These
    board changes were handed to the firmware as "rev C2" while the file's header now reads
    "rev D, EVT1, with amendments E1 to E16": one of the names should go, and the amendments
    that this firmware does not implement are issue 32.
16. **State name.** `CAL_FLIP` of the original state list is now `CAL_ZERO` (rev C wording); the
    storage fields `flip_bias_*` and `GL_CAL_TILT_FLAG_FLIP` keep their names because they are the
    record format. The read log record is unchanged: a left-camera-only read is a record with
    the stick flag set, zero disparity and zero repeats.
17. **Worst-case solve time: bounded now, by a budget that is this firmware's choice.** A
    typical putt estimate is a few milliseconds at 160 MHz (estimate). A read on a slope near
    the limit of what the green holds, where neither the fitted patch nor its secant plane can
    be solved, ran to 0.58 million RK4 steps on the host with the reference's limits alone
    (1.9-3.8 s at 160 MHz), and the loop counters bound it only at 3.8 million (13-25 s). The
    application now sets `max_steps` = 300,000 (1.0-2.0 s at 160 MHz, 3.3-6.6 s at 48 MHz;
    not in the reference), keeps the fast clock through SOLVE and refreshes the watchdog
    before it. A solve that runs out is shown as `NOT SOLVED`. **To decide:** whether 300,000
    is the right number (the costliest solve WITH a result among the vectors needs 208,952 in
    single precision; a smaller budget ends more hard putts unsolved, a larger one keeps the
    golfer waiting), and whether the reference should have the same option so that the two can
    be compared at the limit.
18. **Survey: where is the ball, and when is there a line.** The estimator needs the drop at
    the ball first; the specification's flow ("move the marker along the line") leaves the
    marker somewhere else at the end. As built: the ball is the stored drop farthest from the
    flagstick; the line is drawn only while the marker lies there (the newest drop is that one
    or within 0.85 of its range), otherwise the numbers and `PUT AT BALL`. That makes "walk
    from the hole side back to the ball" or "start at the ball and return to it" the working
    orders, and a Survey that ends near the hole shows no line. **The order the specification
    describes (ball, midpoint, about 1 m short of the hole: "Survey, three placements") ends
    without a line**; the review measured it: a line appears only with a fourth placement
    back at the ball, and a fifth placement is silently a plain Quick Read. Also measured by
    the review: with the ball at 6 m and a second drop at 5.3 m (0.88 of the range) the newer
    drop is taken as the ball and a line for a 5.3 m putt is shown as `D2` without a remark.
    Nothing of this was changed. The product owner should say in which order golfers are to
    survey; then either the last drop says what to do (`BACK TO BALL`) and the Survey stays
    open for the placement at the ball, or the result at the ball is drawn from the stored
    drops when the marker returns.
19. **A range that nobody measured or dialled.** When the flagstick is found but cannot be
    ranged and nothing is dialled, the estimator solves for its 3 m default. As built the
    screen shows `--`, `NO RANGE`, `BREAK ?` and a DASHED line. The alternative is to ask for
    the distance, as the no-flag case does. Decide which.
20. **Distance shown is the cameras' distance to the stick**, which is about 29 mm more than
    the ball's distance to the hole (the lenses sit behind the ball). Not corrected: it is
    about one 0.1 ft step of the display, and a known offset.
21. **Confidence: the factors, and what the bar means.** 0.6 (one camera), 0.6 (ambiguous),
    0.7 (fit not converged), the disparity-sigma factor and the caps (0.2 best effort, 0.09
    flag out) are this firmware's choices; nothing calibrates them against how often such
    reads are wrong. They need field data. **And the bar itself does not do what a golfer
    would expect of it** (phase-2 review): the estimator's confidence is essentially the
    chance of holing, so a clean read has 5 boxes at 1.5 m, 3 at 3 m, 1 at 4.5 to 6 m and
    none from 9 m on, and most fallbacks have the same 0 or 1 box. The specification asks for
    a "low-confidence indicator" in the flag-out mode; that case now has a dashed line and an
    empty bar, the others have their message. **To decide:** an indicator of the QUALITY of
    the read relative to what a clean read achieves at that distance (the ratio to the
    clean-read confidence, or the 1-sigma lateral error at the hole in cups), with the holing
    chance as a separate number if it is wanted; and, per fallback, whether its line stays
    solid (issue 8).

22. **The base of the stick near the margin of "visible"** (found by the honest timing). The
    read classes the base VISIBLE when the stick is followed at least 1.5 rows below the turf
    horizon. A flagstick 3 m away on a plane green ends 1.24 rows below it, and the class then
    flips with the noise (VISIBLE in 51 of 80 runs of the Survey scenario). The estimator takes
    the height of the hole from a visible base only, so the same putt gets a Survey fit with a
    curvature or without one (c = 0.0008 /m or 0.00001). Decide: a margin that follows the
    measured uncertainty of the lowest point instead of a constant, a soft weight in the
    estimator instead of a class, or showing which of the two was used. The phase-2 review
    measured the other side of the same switch (finding 9): with the flag flipped the aim of
    the same placement moves by more than a display step in 1.6 % of nominal Quick Reads.
    Since then the screen shows which of the two was used (`PLAYS n?` = base hidden); the
    switch itself is unchanged.
23. **Motion that is not uniform over a group.** The L R R L correction removes a steady
    drift exactly; a reversal inside the 0.13 s of a group leaves that group wrong by tenths
    of a pixel (0.039 px in the read against a claimed 0.05 px) and no check sees it: the two
    left strips and the two right strips of a group are not compared with what a uniform
    motion predicts. The instantaneous reversal of the test is harsher than a swaying stick
    (the sway rows under "Vision" stay within their claimed sigma), so this may be acceptable;
    it is not measured on anything real.

From the phase-2 review (the findings that were not, or not wholly, fixed):

24. **Near the critical slope the aim is not determined** (finding 2; "Solver"). A change of
    one microradian in an input flips the reference's aim by more than a display step in
    about 3 % of the reads there (the reviewer's figure), and a best-effort direction is an
    arbitrary iterate. The port follows the reference exactly and the brief forbids changing
    its numerical behaviour. For the estimator's owner: a search that is stable there (a
    continuation in the launch speed, or reporting the INTERVAL of aims that hole the putt),
    and whether a best-effort aim should be drawn at all - today it is drawn dashed.
25. **A solver tolerance that does not grow with the putt** (finding 3). In single precision
    `tol_miss_m` = 2e-4 m is inside the roll noise from 15 m on (1.08 x at 15-25 m, 13 x at
    25-40 m, pinned), so a long putt can end NO_CONVERGENCE for no other reason. A tolerance
    proportional to the distance would be a change of the contract with the reference.
    Decide whether putts beyond 15 m matter enough for it.
26. **newlib's libm on the target** (finding 8). The single-precision functions the solver
    and the vision call (`powf`, `sinf`, `cosf`, `tanf`, `logf`, `erff`, `hypotf`, `atan2f`,
    `asinf`, `sqrtf`) are newlib's on the target and glibc's in every test here. NOT
    VERIFIED: their last-bit differences against the host's, and with them every
    single-precision figure of "Solver", on the target. It needs the cross-compiled solver
    run on the vectors in an instruction-set simulator or on a board; neither was available.
27. **Method B2 with untidy horizons** (finding 10): nominal reads fall back, jump and differ
    between the precisions. Not changed; B2 is off by default and a poor horizon is now
    shown. Decide whether B2 stays selectable before it has been made robust.
28. **Charge termination, charge time, and the cradle state** (finding 19). The firmware has
    no charge timer and no "full" decision; the charger's STAT input is only displayed. In
    the cradle the MCU never enters Stop mode (USB is started on VBUS whether or not a host
    is there), with the IMU at 240 Hz and the display on, and that load sits on the cell's
    node. NOT VERIFIED (no data sheet here; the reviewer's recollection): the MCP73831 ends a
    charge only when the current falls to a few percent of the programmed 20 mA and has no
    safety timer, so with that load the charge may never terminate and the cell would float
    at 4.2 V for as long as the marker is docked. The E1 charger may behave differently.
    Firmware has the means (`CHG_INHIBIT`, STAT, the battery ADC: a maximum charge time, a
    "full, stop" state, Stop 2 between the 5 s checks when no host is connected); what the
    cell and the charger need is the hardware and product owners' call.
29. **Turning the marker back after a Precision spin** discards the `2X` result: it is a new
    placement and a new Quick Read (finding 22). The result screen is now upright for the
    golfer WITHOUT turning back, which removes the reason to do it; if the golfer is still
    expected to turn the marker back, the gyro's angle could carry the result over instead.
30. **Vision at short range** (finding 32): at 2 to 3 m on a putt that is level along its
    line the hole is read 3 to 5 mm low, which adds about 2 % to the break, and at 0.6 m the
    flagstick is refused (the strips hold a stick down to 0.8 m: `GL_APP_MIN_RANGE_M`). The
    reviewer's figures; neither was reproduced or looked into here. The first is a bias of
    the lowest-point estimate at the turf edge of the size the "Vision" tables show (-0.3 to
    -0.5 row); a putt of 0.6 m may simply not need the instrument.
31. **A result cannot be recalled** (finding 33): it is on the screen for 45 s, then only a
    new camera read shows a line again. Decide whether the last result should be shown again
    on wake-up while the marker has not been moved (the IMU can tell), at the price of a
    stale line if it has.
32. **The specification's amendments that this firmware does not implement** ("DESIGN_SPEC
    amendments E1 to E16"): E1 (charger and `CHG_INHIBIT` polarity; issue 2), E11 (two stored
    level zeros, base face and ball feet: one in firmware), E12 (the display's rotation in
    its pocket, up to about 1 degree = 17 mrad, measured at the factory and applied to the
    drawn line: not stored, not applied; the largest drawn-line error measured here is 3.8
    mrad, a quarter of that), E13 (no read above 60 C cell temperature; a ship mode: neither
    exists). Each is a calibration field, a few lines in `compose_view_()` or the read
    start, a protocol command and tests; none was in this phase's brief. To decide first:
    whether the specification file or the brief is the authority.

## The solver: decisions and open points

What phase 2 settled (builder 1: the port; builder 2: the application), and what is left to the
owner:

* **One range fusion feeds the aim: the estimator's** (the reference's `fuse_range`: fusion in
  range with one re-evaluation of the stereo sigma). The number shown, the number logged, the
  range of a Survey drop and the parallax correction of the bearing all come from it.
  `gl_range_fuse()` of phase 1 still runs, for learning the stick height and as a diagnostic
  field; its handling of sources that contradict each other has no counterpart in the
  estimator.
* **Gating happens before the estimator, by "not available".** `build_measurement_()` passes
  the disparity only if a stereo pair was read and it is at least 3 sigma
  (`GL_RANGE_MIN_DISPARITY_SNR`) above zero, otherwise not-a-number; the stick top only if it
  is in the frame and not in clutter (`top_valid`); the base flag strictly; the dialled
  distance always. A left-camera-only read is "flag found, range not available"
  (`range_missing`) unless top and base are visible, in which case the estimator ranges it
  from the angular height itself; its bearing is kept. **Not an estimator input:** the read's
  own disparity sigma (the reference assumes 0.08 px); the application uses it for the gate
  and for the confidence shown.
* **The bearing is referred to the ball** with the estimator's distance, a correction of
  3.4 mrad at 3 m for the left camera's 10 mm offset; the estimator's distance is the cameras'
  range to the stick, about 29 mm more than the ball's (the reference's device sits at the
  ball). The second one, about one 0.1 ft step of the display, is not corrected (open issue
  20).
* **Survey.** The reference takes the drops "ball first"; `gl_solver_estimate_survey()` takes
  `ball_index` and uses the other drops in array order (tested: the result does not depend on
  where the ball's drop sits). The application chooses the ball as the farthest drop and draws
  the line only when the marker lies there (Application / Survey; open issue 18).
* **Method.** B1 is the default; the setting METHOD switches B2 (anchored horizon fit, 5
  starts, about 1.4 million host instructions against 0.3 million) on. B0 and STRAIGHT are
  ported and tested but cannot be selected on the device. The grain option (`use_grain`)
  follows the GRAIN setting, which ships OFF (phase-2 review: the setting used to lengthen the
  read and change nothing).
* **Near miss of the patch solve** (phase-2 review; the one change to the reference, and
  additive). `EstimatorConfig.near_miss_keep` / `gl_solver_options_t.near_miss_m`: 0 by
  default in both, which is the behaviour of every earlier vector. With a positive value a
  patch solve that ends without a solution, but whose last iterate is a real launch that
  passes within that distance of the hole centre, is kept instead of the secant plane's or a
  best-effort aim; its confidence is scored as a fallback's. The application passes 5 mm
  (`GL_APP_NEAR_MISS_M`: a twentieth of the hole) and shows `APPROX`. Whether 5 mm is the
  right number, and whether the reference's own default should become positive, is the
  estimator owner's decision.
* **Step budget** (phase-2 review; firmware only). `gl_solver_options_t.max_steps`, 0 = none
  by default; the application passes 300,000 (open issue 17). The reference has no such
  option; inside the budget the results are identical (tested on all 340 estimator vectors).
* **`flag_base_visible` is passed strictly** (the stick was followed, with significance, more
  than 1.5 rows below the turf edge); with the base "at the horizon" the estimator uses the
  one-sided bound and does not range from the angular height (open issue 9 still applies to
  the application's own range).
* **Differences from the reference, all documented in `gl_solver.h`:** the single build's
  tolerances; C refuses camera constants and tilts that no placement produces
  (`GL_ERR_PARAM`), where the reference computes on; where the reference raises an exception
  or returns not-a-number, C returns `GL_ERR_RANGE` and a flagged record; an infinite distance
  sigma is reported as not-a-number; `gl_solver_solve_aim()` and `gl_solver_roll()` refuse a
  result that is not finite; a finite input whose square overflows is `GL_ERR_RANGE` (the
  reference raises `OverflowError` in double; in single precision the range is the float's);
  in the single build a fit step below the resolution of the parameters ends the fit as
  converged; the secant plane of a patch that is a plane is not solved a second time (same
  result, half the work). Not ported: the joint horizon fit and the other comparison-only
  switches of `EstimatorConfig`, grid surfaces, trajectories, batches.
* **For the next agent:** `gl_estimate_t` carries `n_rolls` and `n_steps` (the cost of the
  solve) and `gl_solver_work_t.fit` the whole fit record (covariance, range channels,
  stations, horizon diagnostics). The log now carries aim source, status, flags, method and
  `n_rolls` (`GL_APP_LOGEV_ESTIMATE`); the fit record and `n_steps` still reach neither the log
  nor the USB protocol.
