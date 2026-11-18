# GreenLine GL-1 firmware (phase 3: the rev E board, the factory commands, the field log, the boot stub, and what a result looks like)

Firmware for the GreenLine GL-1 electronic ball marker (`../design/DESIGN_SPEC.md`, rev D
EVT1 with amendments E1 to E34, and `../design/master_params.yaml`). **The firmware targets
the rev E board only** (hardware revision 5, shown as "E"): the charger is a TI BQ25101 with
a thermistor of its own, and the pin map is the netlist's
(`../electrical/gl1_main/pinmap.json`). The board this file used to call **rev C2** (another
charger, `CHG_INHIBIT` of the opposite polarity) is not supported any more; where the name
still appears below it is history.

## Status - read this first

* **Phase 3, builder 3: what the golfer sees.** In: the three display states of E33 (a solid
  line with the confidence bar = a normal solution; a dashed line with the word APPROX in the
  bar's place = a fallback solution; a message without a line = no solution), proved over
  every aim source and solve status and read back from the frame buffer; "TOO STEEP" (E31)
  from a ratio of quantities the estimator already returns, its threshold chosen from a sweep
  against the Python reference; the Survey that finishes at the ball (E29: the placement the
  marker stands on is the ball, every result has its line, "PUT AT BALL" is gone); Recall
  (E30: a tap on a marker that has not been lifted shows the last result again with its age,
  no camera, nothing logged); a bound on the camera-rail time of a read with several lines in
  view (E15: the longest such read was 3.36 s, outside the specification's 2.8 s); the
  regulatory and information screen (the INFO item of the dial, its text a placeholder that
  fails a release build). **All of it is in the section "Phase 3, builder 3"**, with the
  runs. The numbers in that section, the memory tables, the test summary and the table under
  "Putt on the display" are no longer typed: they are generated from the logs of the final
  build and checked by `make readme-check`. **NOT MET, each pinned by a test:** a Survey
  walked from the ball toward the hole gets, at each stop, the putt from that stop made of
  the placements from there to the hole only (the estimator, which is frozen, has no station
  behind the ball); one reference vector is shown as a normal result where the reference at
  its own 1e-9 m tolerance keeps a near miss; and everything builders 1 and 2 pinned, below.
  **NOT VERIFIED:** that a tap wakes the real IMU, and how soon after the wake-up it delivers
  samples (a movement that is over before the first sample is not seen by the recall rule).
* **`make test` (33 test executables), `make asan`, `make cross`, `make cross-hal`, `make
  boot-cross`, `make diff`, `make appdiff` and `make tooltest` pass on the final tree**; the
  table of every executable with its checks is under "Building and testing".
* **Phase 3, builder 2: factory and calibration commands, calibration data, field log, PC
  tool, boot stub.** In: calibration records of version 2 with a CRC and migration from
  version 1 - the two level zeros of E11 (base face, ball feet), the display rotation of E12
  (applied to the drawn aim line; its sign and size proved from frame-buffer pixels), the
  camera horizon row, the grain floor and dark offset, the serial number; protocol version 3
  with 17 new commands, version negotiation, an unlock rule and a defined status for every
  bad argument; a field log that holds everything the estimator was handed and returned, so
  that a read can be replayed, plus tilt-only records and a download that resumes; the PC
  tool `tools/glctl` with a transport to the HOST SIMULATOR build of the firmware
  (`make tooltest`: every command, 504 checks) and the replay through the Python reference;
  the boot stub of E34 (`boot/`: portable decision logic with host tests, the STM32U585 part
  by inspection - it links, it has never run) with an image header, a stamping tool and USB
  ids as named placeholders that make a release build fail. **All of it is in the section
  "Phase 3, builder 2"**, with the command table, the record layouts, the log sizes, the
  station-test table and what is still missing. `GL_CMD_SHIP_MODE "SHIP"` now needs UNLOCK.
  (E29, E30, E31 and E33 came with builder 3, above.)
* **Phase 3, builder 1: the rev E board and its power behaviour.** In: the pin map generated
  from the netlist by one command (`make pins`; 20 signals moved, three of the four interrupt
  lines); the BQ25101 (`CHG_INHIBIT` push-pull, HIGH = stop; the firmware can only stop the
  charge) with the firmware's own supervision on the MCU's thermistor, a 6 h backstop and a
  status inferred for every case the one status line can show; no camera read above 60 C
  (E13); ship mode (E13); the cradle sleep (E32); the supply model for the rev E parts; the
  STM32 backend brought in line BY INSPECTION (it compiles; nothing of it has run). The
  sections "Charger and cell temperature (rev E)", "Cradle, ship mode and the hot cell",
  "Sleep and the supply model (rev E)" and "Pins of the rev E board" are new; they carry the
  figures of this phase. **NOT MET, each pinned by a test:** ship mode draws 12.9 uA in the
  supply model against the 5 uA required (the board's always-on parts alone are 9.6 uA);
  a host that leaves the USB bus running but says nothing for 30 s loses the marker until it
  is re-docked; without firmware (ROM loader, a hung firmware) the charger keeps its OWN
  window, 0 to 60 C, not the firmware's 0 to 45 C; and IF the charger's status line shows the
  first charge cycle only (not known: the model assumes it shows every cycle, a variant of
  the model shows the other reading) the 6 h backstop does not see a recharge that an awake
  marker keeps from ending. **Every statement about the charger with
  no firmware running is a statement about the simulator's MODEL of the chip** (thresholds
  PROVISIONAL, no data sheet read). (E11, E12 and E34 came with builder 2, E29 to E31 and E33
  with builder 3, above.)
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
  message for every fallback (phase 2 drew a dashed line for an aim that is not a solution
  and a solid one for most fallbacks; since phase 3 there are three states, "Result on the
  display"). Read
  sequence, vision, estimator and rendering are tested together on
  the simulator against the reference, with the direction of the drawn line measured from the
  panel's pixels ("Putt on the display"), and `make appdiff` repeats the comparison with the
  Python reference itself. Charger inhibit, cell NTC, EXTCOMIN divider, core-clock switching,
  chip-select states and the moved pins were implemented and tested on the simulator for the
  rev C2 board. Phase 2 pinned two requirements as NOT MET for that board: nothing supervised
  the charger while the ROM bootloader ran (600 s at 50 C in the test), and a hung firmware
  left it unsupervised until the watchdog reset it (33 s). **Phase 3 runs both tests again
  against the model of the rev E charger** ("Charger and cell temperature (rev E)"): the
  model's charger enforces its own 0 to 60 C window with its own thermistor whatever the MCU
  does; what remains NOT MET is the firmware's narrower 45 C limit in those two states.
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
  **4.1 - 4.8 s after the marker comes to rest** (4.4 s at the nominal factor; since builder 2
  of phase 3 writes the replay records before the result is posted it is 0.02 s more: 4.15,
  4.45 and 4.84 s in the final build, "End to end") and keeps the
  camera rail on for 2.2 - 2.8 s - not the 3.45 s and 1.56 s this file used to state, which
  charged no computation. DESIGN_SPEC said "about three seconds" then; its amendment E15 now
  states these figures, taken from this model. **They are a model and not a measurement**:
  the factor between a host instruction and an MCU clock cycle is an ESTIMATE (1.5 - 3,
  nominal 2), no board exists. A flagstick between 2.25 and 4.5 m used to take 0.6 s longer in
  a third of the reads (its own shoulder in the band was probed as a second line); the
  phase-2 review removed that (2.42 - 2.46 s of rail and at most 4.40 s to the result in a
  sweep of 21 reads). A read with a person behind the stick or with two real lines in the
  band used to keep the rail on for 3.4 s; **phase 3 bounds it** (the read has eight groups
  in all: "Read time: the rail-time bound"). **Still outside the stated figures:** a near
  stick at the high factor (the review measured 2.99 s of rail and 5.0 s to the result at
  1.5 m; not repeated here). A stick whose line is wider than 1.2 px (3 m and nearer in the bench scenes) costs
  72 to 87 million instructions instead of 58 to 60. Honest timing also changed three
  results, all pinned by tests as NOT MET: a second post 14 px from the stick defeats more
  than half the reads (26 of 64 give a disparity), a Survey fit hangs on a marginal
  classification of the stick's base, and a drift that reverses inside a group of four strips
  is not noticed ("End to end", "Vision").
* **Rev C and later.** `core/gl_config.h` is generated from `master_params.yaml`, which now
  reads rev D-EVT1 (`GL_CFG_PARAMS_REV`; the string will become E-EVT1, and no test
  writes it: `tests/test_basics.c` reads the expected string from the YAML itself); the values this firmware takes from it are the ones
  rev C set (stereo baseline 20.0 mm, cameras at x = +-10.0 mm). Where this file says "the rev
  C YAML" it means that change. The user calibration is a **zeroing on any hard flat surface**
  (read, turn the marker 180 degrees in place, read again). It is never done in the cradle,
  which takes the marker one way round only: the UI state is `CAL_ZERO` (rev B: `CAL_FLIP`), it
  can be entered only from the settings dial, being put into the cradle abandons it, and the
  USB command that asks for it is answered with `GL_ERR_STATE`.

## Phase 3, builder 2: factory commands, calibration data, field log, PC tool, boot stub

Everything in this section was built and run on the host and against the host simulator.
**Nothing was run on hardware; there is none.** The numbers quoted come from `make test`
(`tests/test_cal.c`, `test_fieldlog.c`, `test_factory.c`, `test_boot.c`, `test_log.c`,
`test_proto.c`) and from `make tooltest`, both run in this phase; the command and the test
that prints each number are named with it.

### Calibration records (version 2) - `core/gl_cal`

Five records, each one little-endian blob in the flash store (`gl_store`, the first 4 sectors
of the 8 MB chip), read with `GET_CAL`, written with `SET_CAL` or by the procedures below.
Byte 0 is the layout version (2), byte 1 the flags, the last two bytes a CRC-16/CCITT-FALSE
over everything before them. A blob whose CRC is wrong is refused (`GL_ERR_CRC`) whatever its
fields look like; behind the CRC every field is range-checked (`GL_ERR_RANGE`).

| Record (`GL_CAL_ID_*`, store id) | Bytes | Layout after version and flags | Flags |
|---|---|---|---|
| TILT (1, 0x11) | 120 | `offset_g[3]`, `tempco1[3]` g/K, `tempco2[3]` g/K^2, `t0_c`, `m[3][3]` (six-face), **ball-seat zero** `flip_bias_x/y`, `flip_temp_c`, `flip_time_s` (u32), `flip_scatter`, **base-face zero** `base_bias_x/y`, `base_temp_c`, `base_time_s` (u32), `base_scatter`, CRC | 0 FACTORY (six-face), 1 FLIP (ball seat), 2 BASE (base face), 3 TEMPCO, 4 BASE_DERIVED |
| CAM_L, CAM_R (2 / 3, 0x12 / 0x13) | 52 | `fx fy cx cy k1`, `pitch_up yaw_left roll` (rad), `pos_mm[3]`, **`horizon_row`** (CAM_HORIZON), CRC | 0 INTRINSICS, 1 EXTRINSICS, 2 HORIZON |
| GRAIN (4, 0x14) | 82 | `gain[16]`, `mod_threshold`, `noise_floor_mod` (GRAIN_FLOOR), `min_signal_counts`, `max_dark_drift_counts`, **`pd_dark_counts`** (u16, step 11a), CRC | 0 WHITE_REF, 1 NOISE_FLOOR, 2 DARK_OFFSET |
| DEVICE (5, 0x16) - new | 28 | **`display_rot_rad`** (E12), `unique_id[12]`, `serial` (u32), `time_s` (u32), CRC | 0 DISPLAY_ROT, 1 SERIAL |
| learned stick height (store id 0x15) | - | not a calibration record: `core/gl_range`, as before | - |

All floats are IEEE-754 single. The first 94 / 46 / 78 bytes of the tilt, camera and grain
records are the version-1 layouts of phases 1 and 2.

* **Migration.** `gl_cal_*_decode()` accepts version 1 (no CRC, the old lengths) and converts:
  the one zeroing bias of version 1 becomes the BALL-seat zero (it was taken on a hard flat
  surface), there is no base-face zero, the horizon row is the one the stored pitch implies,
  flag bits that did not exist are dropped, TEMPCO is read off the coefficients. Nothing is
  written in version 1 any more; `SET_CAL` accepts a version-1 blob (a phase-2 backup) and
  stores it as version 2. Tested byte for byte against records written field by field from
  the phase-2 layout (`test_version_1_records_are_migrated`), and over USB
  (`test_six_face_tempco_horizon_floor_serial`). The CRC: "tilt record, each of its 960 bits
  flipped in turn: 960 refused (952 by the CRC, the rest by the version byte)".
* **Two level zeros (E11) and which one a read uses.** `gl_cal_tilt_zero(cal, wanted, &bias)`:
  the zero of the wanted seat if it is stored, else the other one, else nothing. "Wanted" is
  the new setting **SURFACE** (`gl_settings_t.surface`, dial item and settings byte 10):
  `TURF` = base-face seat, the default; `HARD` = ball seat. **It is a setting, not a field of
  the calibration record** (the record holds both zeros; the choice is the golfer's). A unit
  that only has its user's zero (hard surface, ball seat) uses that one on turf as phase 2
  did. The user's zeroing from the menu writes the ball seat; if a base-face zero exists it
  is MOVED by the same amount and flagged BASE_DERIVED (what a later zeroing finds is sensor
  drift, common to both seats; the difference between the seats is mechanical). The read log
  records the seat that was used.
* **Display rotation (E12).** `display_rot_rad` is the angle the firmware TURNS THE DRAWN AIM
  LINE BY, counter-clockwise for a viewer looking down on the display, about the screen
  centre: `core/gl_ui.c` adds it to the line's direction AND to the direction of the ball
  position the line passes through (a pure direction change would leave the line 5 pixels off
  at 1.2 degrees: the ball centre is 246 pixels from the screen centre). Text is not turned.
  It is MINUS what the factory camera measures on the uncorrected reference line;
  `glctl display-rot --measured DEG` does the negation. Limit +-2 degrees (the glass can sit
  up to about 1.2). **Proved from frame-buffer pixels** (`test_display_rotation_from_pixels`,
  least-squares fit over the row centroids of the 96 middle rows): "reference line ...
  uncorrected -0.019 deg, with +1.200 deg stored +1.198 deg (turned +1.217 deg
  counter-clockwise)"; "aim line of -3.000 deg ... drawn at -2.972 deg; with +1.2 deg stored
  -1.787 deg (turned +1.184); with -1.2 deg stored -4.240 deg (turned -1.269); distance of the
  line from the screen centre -12.90, -12.90, -12.90 px"; and the result screen of a real read
  with +1.2 degrees stored is pixel for pixel the screen with aim and ball direction turned by
  hand. One pixel over the 96 rows measured is 0.60 degree; the test allows 0.1, the largest
  deviation printed is 0.07.
* **Serial number.** `gl_cal_serial_from_uid()` = CRC-32 (zlib) of the processor's 96-bit
  unique number; marked as 7 characters of Crockford base 32 (`gl_cal_serial_text`). It is
  DERIVED, not assigned: two units can share one (about 1.2 % that any two of 10 000 do); the
  unique number is the identity of record. `GL_CMD_SERIAL "SNUM"` stores number and serial in
  the device record; `GET_IDENT` says whether the stored number is this processor's (a board
  that carries another board's calibration is seen).
* **Settings are version 3** (`core/gl_settings`): byte 10 `surface`, byte 11 `tilt_log`
  (OFF / ON / ONLY), two more dial items (SURFACE, TILT LOG). Version 2 and 1 records are
  read and converted.
* **NOT done:** nothing on the unit shows a missing calibration (the header comment that
  promised a reduced confidence was never implemented and is gone); `GET_IDENT` reports the
  flags and one bit "calibration complete", and the final test must look at it.

### The protocol (version 3) - `core/gl_proto`, `app/gl_factory.c`

The framing is unchanged. A host sends `GET_IDENT` with its own version first; the answer
carries the unit's version, the version both speak and a 64-bit map of the command ids the
unit has. A unit of version 1 or 2 answers `GL_ERR_UNSUPPORTED` and the host falls back to
`GET_INFO` (glctl does this).

**Unlock - the rule.** `UNLOCK "GLFC"` unlocks, anything else locks. The unit locks itself
when USB goes (lifted out; cradle sleep after 30 s of host silence) and at every reset.
Locked, it refuses with `GL_ERR_STATE` every command marked U below. The four bytes guard
against accidents and stray bytes; **they are not a secret.** `SHIP_MODE "SHIP"` now needs
unlock (it did not after builder 1; open issue 37 is closed).

**Bad arguments.** Every command answers a status byte: `PARAM` (length or a field out of
range), `STATE` (locked, no VBUS, too hot for a camera), `BUSY` (a read or another procedure
has the device), `UNSUPPORTED`, `RANGE`, `CRC`, `EMPTY`, or the device's own error; an error
carries no data and changes nothing ("48 bad requests of the factory commands: each answered
its defined status, nothing stored, no camera powered", `test_bad_arguments`).

| Id | Command | U | Request -> response data | What it is for |
|---|---|---|---|---|
| 0x01 .. 0x0F | PING, GET_INFO, GET_STATUS, GET/SET_SETTINGS, GET/SET_CAL, START_CAL, LOG_INFO, LOG_READ, LOG_ERASE, STREAM, SET_TIME, UNLOCK, REBOOT | SET_CAL, START_CAL, LOG_ERASE, REBOOT "DFU!" | as in phases 1 and 2; settings 12 bytes version 3; records version 2 | - |
| 0x10 | SHIP_MODE | "SHIP" | "SHIP" / "STAY" -> armed (1) | ship mode (builder 1) |
| 0x11 | GET_POWER | | -> 16 bytes | charger, cradle (builder 1) |
| 0x12 | SET_CHARGE | U | 1 / 0 -> - | hold the charge stopped (NTC1 / TS test) |
| 0x13 | GET_IDENT | | [host version] -> 72: versions, model "GL-1", hw 5 'E', firmware, solver, calibration and log-layout versions, unique number, serial (derived, stored), 5 calibration flag bytes, flags, parameter revision, command map | identify; negotiate |
| 0x14 | GET_SENSORS | | -> 28: cell mV, 2.8 V rail mV (VDDA), NTC2 0.1 C + raw counts + fault, MCU die, IMU die, VBUS / USB supply / camera rail / charger pins, last sleep test | thermistor, temperatures, rails |
| 0x15 | CAM_ID | | camera -> camera, product id (2), 1 if the expected one | identity of EACH camera, also with the other dead |
| 0x16 | CAM_CAPTURE | | camera, kind (0 picture, 1 dark frame), x0, y0, w, h -> 26: window, bytes, min, max, mean x16, pixels above 32, CRC-32 | one exposure, at most 640 x 288 |
| 0x17 | CAM_DATA | | offset (4), length (2, <= 1000) -> offset + pixels | download, any order: resume at an offset |
| 0x18 | CAM_FIELD | | camera -> 20: rows of +13.0 / -13.0 deg, mean of 7 rows x 320 columns at each and at the centre, upper / lower x 1000 | test gate 2 |
| 0x19 | DISPLAY_TEST | | pattern, hold s (1..120) -> pattern, CRC-32 of the frame buffer, black pixels | white, black, 1- and 8-pixel chequer, rows, columns, orientation, reference line raw / corrected |
| 0x1A | GRAIN_TEST | STORE | mode (0 dark, 1 cycle, 2 store) -> 108: dark mean / min / max of 16 readings, full scale, stored offset, 16 x (dark, on, dark) | LEDs and photodiode; dark offset of step 11a |
| 0x1B | LEVEL_ZERO | ARM | op (0 status, 1 arm, 2 cancel), seat (0 base, 1 ball) -> 36: state, seat, status, attempts, bias x y, scatter, turn, plate slope x y, temperature, time | zero armed over USB, run on the plate |
| 0x1C | CAL_STATUS | | -> 80: faces captured, face being averaged, six raw means, temperature | six-face progress (steps: START_CAL SIX_FACE 0..5, 6) |
| 0x1D | TILT_TEMPCO | U | n (3..16), t0, n x (T, offset x y z) -> b0[3], b1[3], b2[3], RMS residual | fit and store the temperature terms |
| 0x1E | SET_CAM_HORIZON | U | camera, row, roll -> pitch_up_rad | CAM_HORIZON |
| 0x1F | SET_GRAIN_FLOOR | U | n (20..64), n x modulation -> floor, threshold | GRAIN_FLOOR |
| 0x20 | DISPLAY_ROT | write | 0 -> rotation, measured flag; 1 + rotation -> the same | E12 |
| 0x21 | SLEEP_TEST | U | wake mask (1 motion, 2 timer), seconds -> armed, mask | sleep-current test |
| 0x22 | LOG_SEEK | | sequence number -> - | resume a log download |
| 0x23 | SERIAL | "SNUM" | - or "SNUM" -> serial, 7 characters, stored flag | serial number |

Notes that decide whether a station works:

* **A whole frame is two exposures.** The unit's image memory (the read's, 184 320 bytes)
  holds 640 x 288; `glctl frame` takes 640 x 240 twice. Fine for a still target, not for
  anything that moves.
* **A dark frame is an ordinary exposure with statistics.** The driver writes no exposure
  register (no verified values): the sensor's own loop runs. A light-leak limit must be set on
  the first units; a fixed-exposure dark frame is **missing**.
* **CAM_FIELD rows follow the camera's calibration record** (nominal: +13.0 deg is row 88,
  -13.0 deg is row 391). Three 8-row exposures per call. "equal bars give ratio 1.000, an upper
  bar 25 % darker gives 0.750". The limit (proposed: not below 0.900) is the PC's.
  `mechanical/README.md` step 16 still says 13.5 degrees; DESIGN_SPEC E17 says 13.0, and that
  is what the firmware uses.
* **E13 holds for the factory**: no camera command above 60 C (`GL_ERR_STATE`).
* **LEVEL_ZERO ARM** survives the lift out of the fixture (RAM only: not a reset), runs where
  a read would start - the marker lying still out of the cradle - and takes the place of that
  read: read, "TURN 180", read, store, "SAVED". Three attempts (a wrong turn, a bump), ten
  minutes, then it gives up; nothing is stored unless the store acknowledged it. On the
  simulator, with the IMU reading (3.5, -2.5) mrad wrong on the base face and (4.7, -3.3) on
  the ball feet, on a plate sloped (4, -7) mrad: "BASE-FACE zero ... (3.481, -2.514) mrad ...
  scatter 0.144 mrad; turn 179.9 deg; plate slope found (4.03, -6.95)", "BALL-seat zero:
  (4.709, -3.349) mrad"; a read on turf with SURFACE = TURF then finds "(12.018, -19.988)
  mrad, true (12.000, -20.000)". The scatter is the RMS of the 133 ms block slopes about their
  mean, the worse of the two reads. **Only the 0 / 180 degree reversal exists**; the
  four-position zero of the manufacturing plan is missing.
* **SLEEP_TEST**: armed, the marker sleeps as soon as VBUS has gone; with the motion bit it is
  the product's sleep, without it the IMU is powered down and only the timer (or VBUS, always)
  wakes it; `GET_SENSORS` afterwards says how long it slept and what woke it. Supply MODEL:
  "wake on motion 23.73 uA at the cell (the product's sleep); wake on the timer only 21.72 uA".
  The MCU still wakes every 16 s to feed the watchdog, as in the product.
* **The update loader**: `REBOOT "DFU!"` (U; refused unless VBUS is present and the cell is
  inside the firmware's charge window) writes the request into a backup register and resets;
  the boot stub starts ST's loader.

### Station tests and the commands they use

From `docs/MANUFACTURING_PLAN.md` (4.5 electrical test list, 6 calibration, 7.1 final test) and
`mechanical/README.md` section 7 (steps 11a, 13, 16, 18, 19). "glctl" = the subcommand of
`tools/glctl`.

| Station test | Command (glctl) | Exists | Still missing, and why |
|---|---|---|---|
| Step 11a: photodiode dark offset on the bare board | GRAIN_TEST dark / store (`grain dark`, `grain store`) | yes | the pass limit (not defined anywhere); the amplifier's bias comes from the LCD_DISP line, so the firmware must have the display "on" - it is, in the cradle state, with or without a panel (PROVISIONAL) |
| Gate 1: both camera identities | CAM_ID (`cam-id 0`, `cam-id 1`) | yes | - |
| Gate 1: one frame per camera (prism centring) | CAM_CAPTURE + CAM_DATA (`frame`, `capture`) | yes | a frame is two exposures; centring limits are the station's |
| Gate 1: IMU | STREAM IMU; GET_SENSORS (IMU temperature) | partly | the IMU's built-in self-test is not used (not implemented in the driver) |
| Gate 1: charge current | GET_POWER + the station's meter | yes | the current itself is an instrument reading |
| Gate 1: grain LEDs and photodiode through the potting | GRAIN_TEST cycle (`grain cycle`) | yes | limits |
| Gate 1: NTC2 within 2 K of the room | GET_SENSORS (`sensors`) | yes | - |
| Gate 1: NTC1 plausible (charge starts, stops when TS is pulled low) | SET_CHARGE + GET_POWER (`charge stop`, `charge auto`) | yes | NTC1 itself cannot be read: it is wired to the charger only |
| Gate 1: serial number | SERIAL (`serial`, `serial --commit`) | yes | derived from the unique number; a freely assigned serial has no field |
| Gate 2: frames through the windows | `frame` | yes | - |
| Gate 2: bars at +13.0 / -13.0 degrees | CAM_FIELD (`cam-field`) | yes | the README of the enclosure still names 13.5 |
| Gate 2 and step 18: dark frames under side light | CAM_CAPTURE kind 1 (`capture --dark`) | partly | no fixed exposure; no limit |
| Gate 2: LCD | DISPLAY_TEST (`display PATTERN`) | yes | judged by eye or a camera |
| Step 19: soak until the cell thermistor is within 1 K of the room | GET_SENSORS | yes | only in the cradle (USB) |
| Step 19 / 6.2 A: six-face | START_CAL SIX_FACE + CAL_STATUS (`six-face N`, `six-face solve`) | yes | the fixture; a limit on the offsets |
| Step 19 / 6.2 B: level zero on two seats, nothing on the pads | LEVEL_ZERO arm / status (`zero arm base`, `zero status`) | yes | four-position zero; the result is fetched at the next docking |
| Step 19: display rotation | DISPLAY_TEST ref-raw, DISPLAY_ROT (`display ref-raw`, `display-rot --measured`, `display ref-corrected`) | yes | the camera fixture |
| 6.2 C: temperature compensation | TILT_TEMPCO (`tempco FILE`); data from STREAM IMU or tilt records | yes | the chamber fixture; judging on a second run is the PC's |
| 6.3: stereo calibration | `frame` / `capture`, SET_CAL, SET_CAM_HORIZON | partly | the procedure and the PC program that fits intrinsics and extrinsics from the pictures: not written |
| 6.4: grain white reference | START_CAL GRAIN_WHITE | yes (phase 1) | no glctl subcommand of its own (`Device.start_cal`) |
| 6.4: grain noise floor | SET_GRAIN_FLOOR (`grain-floor FILE`) | yes | the turf readings (grain values are in the read log) |
| 6.6: file every record | GET_CAL (`cal-get`), restore `cal-set` | yes | - |
| 4.5 #2, #5, #13: rails | GET_SENSORS: 2.8 V rail (VDDA), USB supply valid, camera rail on / off | partly | V2V8_CAM and VBUS have no ADC channel: a meter. The camera rail is on only during an exposure (0.2 s): a "hold the rail on" command is missing (it would hold the camera-facing pins un-parked; a decision) |
| 4.5 #4: program and verify | SWD; `tools/stamp_image.py`; later `update-loader` | partly | no linked application image exists |
| 4.5 #8: charger stops when told | SET_CHARGE | yes | - |
| 4.5 #9, #10: USB link, battery reading | PING, GET_IDENT, GET_SENSORS | yes | - |
| 4.5 #11: flash memory | SET_SETTINGS, REBOOT, GET_SETTINGS | partly | the chip's identity bytes are not reported |
| 4.5 #12: IMU flat and still | STREAM IMU | yes | self-test (above) |
| 4.5 #14 .. #17 | GRAIN_TEST, CAM_ID, `frame`, DISPLAY_TEST | yes | - |
| 4.5 #18, #19: sleep current, wake on motion | SLEEP_TEST (`sleep-test --motion`, `--timer N`) + GET_SENSORS | yes | the current is the bench supply's reading |
| 7.1 #3, #4: versions, all calibration flags | GET_IDENT (`ident`: `cal_flags`, `calibration_complete`) | yes | - |
| 7.1 #5: a complete read at a target | the read itself, then LOG_READ (`log-download`, `log-decode`) | yes | limits |
| 7.1 #9: clock, erase the log, defaults, lock | SET_TIME, LOG_ERASE, SET_SETTINGS, UNLOCK | yes | - |
| 7.1 #10: battery state for shipping; ship mode | GET_POWER, SET_CHARGE, SHIP_MODE (`ship`) | partly | setting a chosen state of charge is the PC watching the voltage and stopping the charge; no automatic command |

### Field log - `core/gl_fieldlog`, `core/gl_log`

A solved read writes four records with one read id (the 72-byte summary and the estimator
event of phase 2 are kept as they were):

| Record | Payload bytes | On flash (16-byte header) | Content |
|---|---|---|---|
| placement (`GL_LOG_REC_MEAS`, 5), one per placement handed to the estimator | 68 + 8 per horizon sample: 68 .. 396; 324 with the 32 samples of a read | 84 .. 412; 340 | the complete `gl_measurements_t`, bit for bit |
| summary (`GL_LOG_REC_READ`, 1) | 72 | 88 | as phase 2 |
| estimator event | 10 | 28 | as phase 2 |
| read (`GL_LOG_REC_READ2`, 6) | 684 | 700 | firmware / solver / calibration versions, flags and CRC of all five calibration records, the settings in force, the options of the call, seat used, both tilt readings of a Precision Read, up vector, gyro bias, block scatter and count of the tilt average, three temperatures, cell voltage, grain values (when the reader ran: red and infrared modulation and azimuth, reject bits, 16 LED signals), vision summary, stage times, what was shown, the whole `gl_estimate_t` and the whole fit record (coefficients, 5 x 5 covariance, range channels, stations, costs, iterations) |
| tilt (`GL_LOG_REC_TILT`, 7) | 80 | 96 | a placement without a camera read: raw and zeroed slope, uncalibrated mean acceleration, gyro bias, scatter, temperatures, seat, calibration CRC; kinds: placement, re-read, zero read 1 / 2, too hot, not solved |

* **Sizes, measured:** "one Quick Read in the log: placement record 324 bytes (32 horizon
  samples), summary 72, read record 684 ... the log grew by 1156 bytes, the estimator's event
  included" (`test_field_log_records_and_resume`). A Survey of four placements: 2176 bytes.
* **Capacity** (`test_log_capacity_and_wear`, arithmetic on the sizes above): the log region
  is 2044 sectors of 4096 bytes (8.37 MB): **7214 Quick Reads**, or 85 848 tilt records,
  before the oldest sector is dropped (phase 2: tens of thousands of the 72-byte summary).
  Raw strips, if switched on, cost what they did: 94 kB per read at level FIRST.
* **Wear:** the ring erases each sector once per 7214 reads. At 200 reads a day it turns once
  in 36 days; 100 000 erase cycles (PROVISIONAL: the endurance class of the flash family, no
  data sheet read) would last thousands of years. Wear is not a limit; retention of the
  oldest data is: 36 days at that rate.
* **Stage times** are milliseconds after the tilt average started: "tilt done 1075, camera
  rail on 1075, capture done 3569, solve 3614 .. 3620; rail on for 2424 ms" (the simulator's
  own rail-on time for that read: 2423.7 ms). The read record also carries milliseconds since
  boot: the time stamp finer than 1 s that the validation plan asked for.
* **Tilt-only records** (validation plan section 6, item 1). Setting TILT LOG = ON: every
  placement writes a tilt record, whatever becomes of the read. TILT LOG = ONLY: the cameras
  stay off and the placement is solved as a flag-out read ("TILT ONLY: result 1.86 s after the
  marker was put down, no camera powered, slope shown 2.33 % (true 2.33)"). Always logged,
  whatever the setting: both reads of a zeroing; a placement whose read was refused as too
  hot, found no flagstick or failed. **Not done:** logging at intervals while the marker lies
  untouched (a chamber test must lift and replace it, or stream over USB).
* **A read that could not be solved** (the estimator returned an error) still writes its
  placement records.
* **Download with resume.** `LOG_READ` as before (restart flag; "more" flag). New:
  `LOG_SEEK seq` puts the iterator on the sector that holds record `seq` (one 16-byte header
  read per sector, as at the mount) and the following `LOG_READ`s return the records from
  that number on. glctl keeps the dump on disk, finds its last complete record and continues
  after it. "log of 6 records downloaded twice, identical; resumed at record 3: the remaining
  4 records, byte for byte"; in `core`: "seek to each of 158 record numbers of a wrapped
  12-sector log: always the right first record".
* What the validation plan listed as missing, now: grain values - in; the two tilt readings
  of a Precision Read - in; the settings in force - in; the fit record and step count - in;
  a fine time stamp - in; **the turf-horizon profile - in** (it is part of the measurement
  record). A tilt logger - in, placement-triggered only.

### PC tool - `tools/glctl`

Python 3, standard library only. `python3 tools/glctl --help` lists the subcommands (one per
factory command, plus `log-download [--resume]`, `log-decode`, `replay`). Transports:
`--port DEVICE` (pyserial; without it: "the serial transport needs the 'pyserial' package,
which is not installed ...", exit 3; **pyserial is not installed in this environment, so the
serial transport has never been exercised**) and `--sim` (the host simulator build,
`build/host/glsim`: `tools/glsim_host.c` puts the whole firmware on the simulated board with
its USB port on stdin / stdout and a few "world" commands to dock, place and turn the marker).

`make tooltest` runs `tools/glctl/selftest.py`: every protocol command through glctl against
the simulator, the log download whole and resumed, the decoder against the values the firmware
held at each result (largest relative difference 4.3e-09: nine printed digits), the replay,
the image stamping tool against the boot stub's own check, the release gate. 504 checks.

**The replay path** (validation plan 3.3, check 1). `tools/glctl/logdec.py` joins each read
record with its placement records into the dictionary form of
`greenline_sim.measurements.Measurements`; `sim/greenline_sim/replay.py` (new, additive; 7
tests in `sim/tests/test_replay.py`) runs the reference estimator on it and compares with the
logged estimate under the rule of `make appdiff` (aim within 0.5 mrad, speed 0.1 %, break
0.01 cup, confidence 1e-4, flags and codes exact). On four reads made by the simulator, two of
them fallbacks (`make replay-demo` of the final build of phase 3; generated block):

<!-- readme-check:begin replay-demo -->
```
read    kind      source      |     fw aim    ref aim     diff |  fw dist ref dist | verdict
                              |     [mrad]     [mrad]   [mrad] |      [m]      [m] |
1       quick     patch       |    -28.539    -28.527    0.012 |    5.982    5.982 | agrees
2       quick     patch       |     -7.118     -7.114    0.004 |    3.983    3.983 | agrees
3       quick     patch*      |    -11.483    -11.479    0.003 |    3.000    3.000 | agrees  (fallback: range_missing)
4       tilt-only patch*      |    +65.686    +65.689    0.003 |    3.000    3.000 | agrees  (fallback: flag_missing)
4 reads replayed through the Python reference: 4 agree with the estimate the firmware logged, 0 do not; largest |firmware - reference| aim 0.012 mrad (limit 0.5)
```
<!-- readme-check:end replay-demo -->

A logged aim turned by 2 mrad on purpose is reported. Limits of the replay: the reference has
no step budget, so a read the firmware cut at 300 000 steps shows as a difference of class;
Survey reads were not among the four (the simulator host has no double-tap command; the
decoder joins several placements and `sim/tests/test_replay.py` covers the order).

The final build of phase 3, `make tooltest` (generated block; the release gate refuses for
two placeholders since builder 3: the USB ids and the regulatory text of the INFO screen):

<!-- readme-check:begin tooltest -->
```
    release-gate: REFUSED - the USB vendor and product ids are placeholders
    release-gate: REFUSED - the regulatory text of the INFO screen is the placeholder
4 reads replayed through the Python reference: 4 agree with the estimate the firmware logged, 0 do not; largest |firmware - reference| aim 0.012 mrad (limit 0.5)
== glctl selftest: 504 checks, 0 failed -> PASS
```
<!-- readme-check:end tooltest -->

### Boot stub (E34) - `boot/`

`boot/gl_boot.h` is the specification: flash layout (stub in page 0, 8 kB, write-protected;
application from 0x08002000 with a 32-byte image header at +0x400), the header (magic "GLIM",
header version, board revision, length, CRC-32 of the image, firmware version and build, a CRC
of the header itself), the rule, and what is retained across resets (backup register 0: the
update request; 3: the count of unconfirmed starts; 4: what the stub found, for the factory).

* **The rule** (`gl_boot_decide()`, 160 input combinations tested): update requested and VBUS
  present -> loader; image not valid -> loader if VBUS is present, else wait for VBUS in
  Shutdown (a loader without a host only empties the cell) and go to the loader then; valid
  image -> start the independent watchdog, count the start, jump.
* **A watchdog loop cannot hide a bad image.** The application clears the count when its main
  loop has run for 10 s (`gl_hal_boot_confirm()`, `GL_APP_BOOT_CONFIRM_MS`) and before every
  reset it makes on purpose. A start that was not confirmed and ended in a watchdog or
  software reset is a failed start; at three in a row the stub stops starting the image: "a
  valid image that never confirms: started 3 times, then the USB loader". A power-on, pin or
  wake-up reset clears the count.
* **The image check**: "image of 6000 bytes: each of its 48000 bits flipped in turn, 0
  accepted"; "update interrupted after each of 6000 byte counts: none of the partial images is
  accepted". `tools/stamp_image.py` stamps and checks images; `tools/boot_check.c` is the
  stub's C code as a host program; `make tooltest` runs both on stamped, cut and damaged files
  and they agree.
* **The STM32 part** (`boot/gl_boot_stm32u5.c`, `boot/gl_boot.ld`) is written by inspection
  against the device header: UCPD_DBDIS first, backup access, reset flags (read, not cleared),
  VBUS_SENSE, the decision, then the jump to the application (VTOR, stack pointer), to system
  memory at 0x0BF90000, or Shutdown with wake-up pin 2. It reads the write protection and
  records whether page 0 is protected; it does not write option bytes (the file lists them:
  WRP1A pages 0..0, nSWBOOT0 = 0 / nBOOT0 = 1, IWDG_SW = 1, RDP 0 at EVT, TZEN = 0).
  `make boot-cross STM32_HEADERS=<dir>` compiles and LINKS it with no library: "image: 1184
  bytes of 8192 (page 0); vector table: 20001000 08000089"; largest stack frame 56 bytes.
  **Linked is not run.**
* **USB ids.** `app/gl_usb_ids.h`: `GL_USB_VID_PLACEHOLDER` 0xFFFF, `GL_USB_PID_PLACEHOLDER`
  0x0000. `make RELEASE=1 ...` defines `GL_RELEASE_BUILD` for every compile and stops at an
  `#error` while they are placeholders; `make release-gate` asks the question alone
  ("release-gate: REFUSED - the USB vendor and product ids are placeholders").
* **Release gates - cannot be verified without hardware:** (1) the loader's entry: the
  address, that a jump from the stub (4 MHz MSI, nothing configured, UCPD_DBDIS set) starts
  it, and that it listens on USB with this board's pins (PA5 / PA7 are the IMU's interrupt
  lines and the loader's SPI1 inputs: the application powers the IMU down before the reset;
  a unit sent to the loader by the STUB - bad image, failed starts - has NOT done that, the
  IMU is in its reset state with its interrupts not routed: PROVISIONAL); (2) the flash write
  protection and every option byte, and that the loader does not write page 0; (3) the vector
  relocation: the application's start-up must set VTOR to 0x08002000 and be linked there with
  the header slot - **no linked application exists**, so no image has ever been stamped from
  real code; (4) backup registers and the watchdog across Shutdown and across the loader;
  (5) the time the CRC of a full image takes at 4 MHz (estimate: about 1.2 s for 400 kB, added
  to every start; not measured); (6) what a host sees: ST's DFU device with ST's ids, not the
  product's.

The final build of phase 3, `make boot-cross` with the vendor's device header (generated
block):

<!-- readme-check:begin boot-cross -->
```
   1184	      0	      0	   1184	    4a0	build/boot/gl_boot.elf
image: 1184 bytes of 8192 (page 0); vector table: 20001000 08000089; Reset_Handler at 0x08000088
largest stack frame of the stub: 56 bytes (its stack: 4096)
OK: the boot stub links without any library and fits its page.  LINKED IS NOT RUN: no hardware.
```
<!-- readme-check:end boot-cross -->

### NOT MET, PROVISIONAL and not verified (builder 2)

* **NOT MET (pinned).** `tests/test_e2e.c`, Survey from two placements at 3 m: this run is
  again one where the base of the stick is classed "at the horizon" and no curvature is
  fitted (it flips with the frame noise, 51 of 80 runs visible; the two extra log records of
  a read shifted the timing). The requirement was never met as a property; the pin was turned
  to what this run gives. (Builder 3: since E29 the second placement of this test is the
  ball, and the placement behind it is not handed to the estimator, so there is no curvature
  to lose there any more; the same flip of the base class now decides between `PLAYS n` and
  `PLAYS n?`, and the pin is on that.)
* **Not done:** fixed exposure for dark frames; four-position zero; the stereo calibration
  procedure and its PC program; IMU self-test; flash identity read-out; a "hold the camera
  rail on" command; logging tilt at intervals; any sign on the unit of a missing calibration;
  a `glctl` subcommand for the live streams and for the grain white reference; Survey reads in
  the replay demonstration.
* **PROVISIONAL:** everything in `boot/gl_boot_stm32u5.c` marked so (loader address, wake-up
  pin selection, write-protection register reading, option bytes); the flash endurance used
  for the wear figure; that the grain amplifier works on a bare board without a display.
* **Not verified:** the serial transport of glctl (no pyserial here, no unit); anything on
  hardware; `hal/stm32u5/gl_hal_stm32u5_usb.c` (changed: it takes the ids from
  `gl_usb_ids.h`; still not compiled by any target).

## Phase 3, builder 3: what a result looks like, the Survey, Recall, read time, the INFO screen

Where it is: `core/gl_ui.h` / `gl_ui.c` (the display states, the steepness ratio, the screens,
the transition table), `app/gl_app.c` (`classify_`, `survey_select_`, `recall_watch_` and its
neighbours, `info_view_`), `app/gl_read.c` (`probe_done_`: the group budget),
`app/gl_regulatory.h` (the text block), `app/gl_app_cfg.h` (the constants, each with its
reason). Tests: `tests/test_ui.c` (1541894 checks: every screen, the rule, the table),
`tests/test_e2e_recall.c` (344 checks: Recall and the INFO screen through the whole firmware),
`tests/test_e2e_putt.c` and `tests/test_e2e.c` (the Survey), `tests/test_solver.c` (the two
builds), `tests/test_read.c` (the rail time). Nothing here has run on hardware.

### The three display states (E33) and "TOO STEEP" (E31)

Every estimate maps to exactly one state (`gl_ui_classify()`, a pure function of what the
estimator returned plus two flags of the camera read; first match wins):

| State | The estimate | Message | On the screen |
|---|---|---|---|
| **NONE** | aim source 3 (straight), an aim source or a solve status that does not exist, status INVALID / NOT_RUN | `NO SOLUTION` | **no line**, no break, no confidence bar; the message in two lines of double-size letters; the distance and the slope with its fall-line arrow stay (they were measured) |
| **NONE** | aim source 2 (best effort: neither the patch nor its secant plane could be solved, or the step budget ran out) | `TOO STEEP` if the ratio below says so, else `NOT SOLVED` | the same |
| **APPROX** | flag missing (the flag-out fallback) | `NO FLAG` | **dashed line**; the word `APPROX` where the confidence bar would be; distance, plays-like, slope, break as computed |
| **APPROX** | range missing, or any result whose distance nobody measured or dialled | `NO RANGE` | the same (`--` and `BREAK ?` when there is no distance at all) |
| **APPROX** | steepness ratio 0.80 or more (E31), aim source 0 or 1 | `TOO STEEP` | the same |
| **APPROX** | aim source 1 (solved on the secant plane) | none (the word APPROX says it) | the same |
| **APPROX** | aim source 0 with status PACE_LIMITED | `PACE LIMIT` | the same |
| **APPROX** | aim source 0 with any other status but OK (a near miss of the patch solve, kept) | none | the same |
| **APPROX** | fit stopped on its iteration limit; poor horizon (method B2) | `FIT NOT DONE`; `POOR HORIZON` | the same |
| **NORMAL** | everything else: aim source 0, status OK, flag and range measured, fit converged, ratio below 0.80 | none, or `1 CAMERA`, or `2 LINES SEEN` | **solid line**, the five confidence boxes |

The three differ in three places of the frame buffer at once: the line (solid; gaps; absent),
the box at the bottom (five boxes; a word; nothing) and, for NONE, the whole layout. The
renderer takes the state from the view and can only be MORE cautious than it
(`gl_ui_view_show()`): a view marked NORMAL is not drawn as one unless the aim is a solution of
a putt with a known distance and a measured flagstick, and no line is drawn unless the aim is
a solution. **What changed for the golfer against phase 2:** a best-effort aim and the
straight fallback had a dashed line and now have none; the secant plane, a kept near miss,
`PACE LIMIT`, `FIT NOT DONE`, `POOR HORIZON` and a dialled distance (`NO RANGE`) had a SOLID
line and differed from a clean result by one word - they are dashed now; `1 CAMERA`, `2 LINES
SEEN` and a hidden base (`PLAYS n?`) stay normal results with their word or question mark:
they are weaker measurements, not fallbacks of the estimator (open issue 8).

**The proof** (`tests/test_ui.c`, `test_three_display_states_are_unmistakable` and
`test_every_estimate_maps_to_one_state`; `tests/test_solver.c`,
`test_display_state_is_the_same_in_both_builds`). The first renders result screens and reads
the state back FROM THE PIXELS ALONE (ink in the dashes of the line, ink in the gaps, what
stands where the bar is, and whether the picture changes when the aim does). The second runs
the rule over every aim source and solve status - the four and six that exist and values that
do not - with every combination of the flags and eight ratios, asserts a second, independent
statement of what a NORMAL result is, and renders each cell. The third runs every estimator
vector through the single-precision build and the double build with the firmware's options:

<!-- readme-check:begin display-states -->
```
1440 NORMAL, 1440 APPROX and 1440 NONE result screens (5 aims, 3 display rotations, every message, with and without the Survey / Precision / recall marks): the state read from the frame buffer alone is the state rendered in every one
ink in the gaps of the dash pattern: at least 100 % on a NORMAL screen, at most 0 % on an APPROX one
64512 combinations of aim source (0-3 and 3 values that do not exist), solve status (0-5, NOT_RUN and 2 others), 7 flags and 8 steepness ratios: each maps to exactly one state - 12 NORMAL, 10228 APPROX, 54272 NONE; NORMAL only for patch + OK with nothing missing
  aim source x solve status -> states reached (N normal, A approx, - none):
    source 0:  status 0 NA  status 1 A  status 2 A  status 3 A  status 4 A  status 5 -
    source 1:  status 0 A  status 1 A  status 2 A  status 3 A  status 4 A  status 5 -
    source 2:  status 0 -  status 1 -  status 2 -  status 3 -  status 4 -  status 5 -
    source 3:  status 0 -  status 1 -  status 2 -  status 3 -  status 4 -  status 5 -
TOO STEEP from 0.80 of the critical slope: 7.8 % at Stimp 8, 6.3 % at Stimp 10, 4.8 % at Stimp 13
cases whose (aim source, solve status) differs between the single and the double build, both with the firmware's tolerances, near miss 5 mm, 300,000 steps:
  (against the reference's tolerances) group 1 id  79: single APPROX "TOO STEEP", double at 1e-9 m NONE "TOO STEEP", ratio 1.633
  group 2 id   1: single source 0 status 4 -> APPROX "TOO STEEP" (ratio 0.915) | double source 0 status 1 -> APPROX "TOO STEEP" (ratio 0.915)
  group 2 id   3: single source 0 status 4 -> APPROX "TOO STEEP" (ratio 1.111) | double source 0 status 1 -> APPROX "TOO STEEP" (ratio 1.111)
  group 2 id   4: single source 0 status 4 -> APPROX "TOO STEEP" (ratio 0.883) | double source 0 status 1 -> APPROX "TOO STEEP" (ratio 0.883)
  group 2 id   9: single source 0 status 4 -> APPROX "TOO STEEP" (ratio 1.076) | double source 0 status 1 -> APPROX "TOO STEEP" (ratio 1.076)
  (against the reference's tolerances) group 2 id  13: single NORMAL "", double at 1e-9 m APPROX "APPROX", ratio 0.207
    NOT MET: NORMAL in the firmware (status OK at its tolerances), APPROX by the reference at 1e-9 m (status 4, a kept near miss); past 0.00 m; aim 56.599 against 56.599 mrad, speed 3.8657 against 3.8658 m/s
  (against the reference's tolerances) group 2 id  14: single APPROX "TOO STEEP", double at 1e-9 m NONE "TOO STEEP", ratio 0.844
  (against the reference's tolerances) group 2 id  15: single APPROX "TOO STEEP", double at 1e-9 m NONE "TOO STEEP", ratio 0.912
  group 2 id  16: single source 0 status 4 -> APPROX "TOO STEEP" (ratio 0.880) | double source 0 status 1 -> APPROX "TOO STEEP" (ratio 0.880)
  (against the reference's tolerances) group 2 id  17: single APPROX "TOO STEEP", double at 1e-9 m NONE "TOO STEEP", ratio 1.064
340 estimator vectors: the class differs in 5, the DISPLAY STATE in 0, the message in 0 (single build: 240 NORMAL, 87 APPROX, 13 NONE)
against the double build at the reference's own tolerances (1e-9 m) the state differs in 5: 4 are "TOO STEEP" in both (a dashed line in the one, no line in the other); 1 is NOT MET (near-miss case 13)
```
<!-- readme-check:end display-states -->

**The single- and double-precision cases of the phase-2 final check are settled.** The
near-miss vectors 1, 3, 4, 9 and 16 end NO_CONVERGENCE in the single build (the best iterate
kept as a near miss) and PACE_LIMITED in the double build with the same tolerances. Both are
aims on the fitted patch that go through the hole; the rule puts both in APPROX on purpose
(and all five are also `TOO STEEP`: ratios 0.88 to 1.11), so the two builds show the same
screen for each of the 340 vectors. **NOT MET against the reference at its own tolerances
(1e-9 m), pinned:** five vectors differ in state. Four are `TOO STEEP` in both, with a dashed
line in the firmware and no line by the reference (its plane solve fails where the
firmware's patch solve, at 0.2 mm, ends pace-limited or as a near miss). One, near-miss
vector 13, is NORMAL in the firmware: a putt asked to die at the hole (`past` 0; the PAST
setting can be 0), solved at the firmware's 1 mm pace tolerance where the reference cannot
meet 1e-9 m and keeps its best iterate; the two aims agree to the 0.001 mrad printed (the
"NOT MET" line of the block).

The same through whole reads and through the application's own composition of the view
(`tests/test_e2e_putt.c`; "Mapping only" = an estimate that no simulated read produces is put
into the application and the view composed from it):

<!-- readme-check:begin display-mapping -->
```
Mapping only: secant plane (aim_source 1)          APPROX  message "", line on 47 rows (solid: 77), break "4.4 CUP>"
Mapping only: pace limited on the patch            APPROX  message "PACE LIMIT", line on 39 rows (solid: 77), break "4.4 CUP>"
Mapping only: near miss kept (patch, NO_CONVERGENCE) APPROX  message "", line on 47 rows (solid: 77), break "4.4 CUP>"
Mapping only: best effort                          NONE    message "NOT SOLVED", line on 0 rows (solid: 77), break ""
Mapping only: straight (aim_source 3)              NONE    message "NO SOLUTION", line on 0 rows (solid: 77), break ""
Mapping only: fit stopped on its limit             APPROX  message "FIT NOT DONE", line on 39 rows (solid: 77), break "4.4 CUP>"
Mapping only: poor horizon (B2)                    APPROX  message "POOR HORIZON", line on 39 rows (solid: 77), break "4.4 CUP>"
Mapping only: solved, slope 0.85 of critical       APPROX  message "TOO STEEP", line on 39 rows (solid: 77), break "4.4 CUP>"
Mapping only: solved, slope 0.75 of critical       NORMAL  message "", line on 77 rows (solid: 77), break "4.4 CUP>"
Mapping only: best effort, slope 1.1 of critical   NONE    message "TOO STEEP", line on 0 rows (solid: 77), break ""
... shown as "TOO STEEP" without a line: steepness ratio 1.25 (limit 0.80)
... shown dashed, APPROX, "TOO STEEP": steepness ratio 1.06
aim line: dashed on 38 rows with 5 m dialled, dashed on 46 rows with nothing dialled (both are fallbacks: APPROX)
```
<!-- readme-check:end display-mapping -->

**"TOO STEEP": the rule.** `gl_ui_steep_ratio()` uses only what the estimator returns - the
fitted patch (a, b, c, d), the distance D and the rolling deceleration a_r:

    ratio = max( |(a, b)| , |(a + c D, b + d D)| ) / ( a_r / ((5/7) g) )

the slope of the fitted patch at the ball and at the hole (the gradient is linear along the
straight line between them, so its largest magnitude on that line is at one of its ends) over
the slope on which a ball no longer stops. A ratio that is not a number counts as steep. The
estimator is not changed and nothing is computed from its internals.

**The threshold, 0.80, was chosen from this sweep** (`make steep-sweep`, `tools/steep_sweep.py`;
random Quick Reads with a slope of 0.2 to 1.4 of critical; each read is estimated as measured
and four times with the tilt changed by one microradian; a read FLIPS when one of the four
lands in another (aim source, solve status) class or moves the aim by more than 8 mrad, half
the 16.4 mrad the reference's Monte Carlo uses as a display step):

<!-- readme-check:begin steep-sweep -->
```
random Quick Reads: slope 0.2 to 1.4 of critical, green speed 6 to 14, 1 to 10 m, true curvature sigma 0.0015 /m, seed 20261118

Python reference (estimator.estimate_batch, method B1, near_miss_keep 0.005): 20000 reads
  ratio bin      reads  flips   rate   | class changes | aim moved > 8 mrad | largest move, mrad
  0.00 - 0.30    1252      0   0.00 % |             0 |                  0 |     0.01
  0.30 - 0.40    1589      0   0.00 % |             0 |                  0 |     0.01
  0.40 - 0.50    1647      0   0.00 % |             0 |                  0 |     0.01
  0.50 - 0.55     800      0   0.00 % |             0 |                  0 |     0.02
  0.55 - 0.60     844      0   0.00 % |             0 |                  0 |     0.02
  0.60 - 0.65     812      0   0.00 % |             0 |                  0 |     0.02
  0.65 - 0.70     841      0   0.00 % |             0 |                  0 |     0.02
  0.70 - 0.75     811      0   0.00 % |             0 |                  0 |     0.02
  0.75 - 0.80     858      0   0.00 % |             0 |                  0 |     0.03
  0.80 - 0.85     872      0   0.00 % |             0 |                  0 |     0.03
  0.85 - 0.90     859      0   0.00 % |             0 |                  0 |     0.05
  0.90 - 0.95     861      1   0.12 % |             1 |                  1 |    21.95
  0.95 - 1.00     898     18   2.00 % |            13 |                 10 |   594.67
  1.00 - 1.05     864    113  13.08 % |            70 |                 85 |   950.00
  1.05 - 1.10     847    222  26.21 % |           133 |                176 |   970.06
  1.10 - 1.20    1660    561  33.80 % |           304 |                450 |  1073.68
  1.20 - 1.40    3242   1138  35.10 % |           554 |                883 |  1050.21
  cumulative: reads with a ratio BELOW the threshold (what would still be shown as a normal result)
    below 0.50:     0 flips in   4488 reads =  0.000 %
    below 0.55:     0 flips in   5288 reads =  0.000 %
    below 0.60:     0 flips in   6132 reads =  0.000 %
    below 0.65:     0 flips in   6944 reads =  0.000 %
    below 0.70:     0 flips in   7785 reads =  0.000 %
    below 0.75:     0 flips in   8596 reads =  0.000 %
    below 0.80:     0 flips in   9454 reads =  0.000 %
    below 0.85:     0 flips in  10326 reads =  0.000 %
    below 0.90:     0 flips in  11185 reads =  0.000 %
    below 1.00:    19 flips in  12944 reads =  0.147 %

firmware solver, single precision (gl_solver_estimate, near_miss_m 0.005, max_steps 300000): 100000 reads
  ratio bin      reads  flips   rate   | class changes | aim moved > 8 mrad | largest move, mrad
  0.00 - 0.30    6412      0   0.00 % |             0 |                  0 |     0.07
  0.30 - 0.40    7909      0   0.00 % |             0 |                  0 |     0.08
  0.40 - 0.50    8324      0   0.00 % |             0 |                  0 |     0.16
  0.50 - 0.55    4277      0   0.00 % |             0 |                  0 |     0.17
  0.55 - 0.60    4193      0   0.00 % |             0 |                  0 |     0.22
  0.60 - 0.65    4148      0   0.00 % |             0 |                  0 |     0.32
  0.65 - 0.70    4235      0   0.00 % |             0 |                  0 |     0.28
  0.70 - 0.75    4084      0   0.00 % |             0 |                  0 |     0.33
  0.75 - 0.80    4171      0   0.00 % |             0 |                  0 |     0.40
  0.80 - 0.85    4187      0   0.00 % |             0 |                  0 |     0.57
  0.85 - 0.90    4251      0   0.00 % |             0 |                  0 |     0.71
  0.90 - 0.95    4185     17   0.41 % |            17 |                  0 |     1.01
  0.95 - 1.00    4220    124   2.94 % |           110 |                 15 |   400.01
  1.00 - 1.05    4232    642  15.17 % |           332 |                372 |  1031.05
  1.05 - 1.10    4130   1338  32.40 % |           406 |                999 |  1198.61
  1.10 - 1.20    8359   4146  49.60 % |           941 |               3342 |  1199.16
  1.20 - 1.40   16463   9154  55.60 % |          1927 |               7353 |  1198.51
  cumulative: reads with a ratio BELOW the threshold (what would still be shown as a normal result)
    below 0.50:     0 flips in  22645 reads =  0.000 %
    below 0.55:     0 flips in  26922 reads =  0.000 %
    below 0.60:     0 flips in  31115 reads =  0.000 %
    below 0.65:     0 flips in  35263 reads =  0.000 %
    below 0.70:     0 flips in  39498 reads =  0.000 %
    below 0.75:     0 flips in  43582 reads =  0.000 %
    below 0.80:     0 flips in  47753 reads =  0.000 %
    below 0.85:     0 flips in  51940 reads =  0.000 %
    below 0.90:     0 flips in  56191 reads =  0.000 %
    below 1.00:   141 flips in  64596 reads =  0.218 %

GL_UI_STEEP_RATIO (core/gl_ui.h) = 0.80: at and above it the result is shown as TOO STEEP (dashed line)
```
<!-- readme-check:end steep-sweep -->

Neither the reference nor the firmware's solver flips below a ratio of 0.90; the first flips
come at 0.90 to 0.95, and from 1.05 a quarter to a half of the reads flip. 0.80 leaves 0.10
below the first flip for the error of the fitted slope itself: the tilt reading is good to
about 2 mrad, and the critical slope is 56 to 131 mrad for green speeds 14 to 6, so a
read at a true ratio of 0.90 is seen at 0.86 to 0.94. A second sweep on greens with four times
the curvature (`--curv 0.006 --seed 7`, 6000 reference and 40000 firmware reads, run in this
session and not kept as a log) gave the same picture: no flip below 0.90, 0.4 % and 0.3 % at
0.90 to 0.95. **What it costs:** TOO STEEP starts at a slope of 7.8 % at Stimp 8, 6.3 % at
Stimp 10 and 4.8 % at Stimp 13 (the line of the test in the block above); how often a putt
on a real green is that steep is not something this project has data on. The figure of the
phase-2 review quoted in `core/gl_solver.h`, "0.1 % of reads at 0.80 to 0.85 of critical",
comes from that review's own reads and its own measure of the slope along the path, neither
of which is in this repository; with this ratio it was not reproduced in either sweep. It is
the reason the threshold is not higher than 0.80. **NOT VERIFIED:** the sweeps are of Quick
Reads; Survey fits were not swept.

### Survey: it finishes at the ball (E29)

**The placement the marker stands on is the ball**, always. The Survey is started as before
(double tap on a result, double tap again: the shown read is placement 1); every further
placement is read with the cameras and, from the second on, its result is the putt from where
the marker lies, with its line, fitted to the placements so far: for example 1 m short of the
hole, the midpoint, then the ball. "PUT AT BALL" - the screen without a line that the old rule
(the ball is the placement farthest from the flagstick) showed at every other stop - does not
exist any more.

| What the golfer does | What happens |
|---|---|
| second, third, fourth placement | a result with its line each time; `D2`, `D3`, `D4` beside the bar |
| a FIFTH placement | the Survey is over; it is a new plain read (no `D` mark) |
| picks the marker up and does not put it down for 60 s | asleep; the Survey is gone; nothing to recall (it was lifted) |
| leaves a result alone for its 45 s | asleep; the Survey is over; that result can be recalled by a tap |
| double tap on a Survey result | the Survey is over; the result stays |
| a placement where no flagstick is seen | as in any read: the distance prompt, or the flag-out result if a distance is dialled; it is not stored |

**One thing E29 does not say, and what the firmware does about it.** The estimator - frozen -
puts every placement at a station `min(max(D - range, 0), D)` on the line from the ball to
the hole. A placement FARTHER from the hole than the ball has no station there: clamped to 0,
its tilt and its hole height would be taken as measured at the ball (in the end-to-end test,
two placements 3 m apart with tilts 0.5 % apart gave a fitted curvature of -0.011 /m that
way, where the two tilts imply +0.001 to +0.002 /m; that was a run of this session before the
gate existed, and is how the gate was found - it is not in the final logs). So the rule of the hand-over applies here too - gate, do not
synthesise (`survey_select_()`): a stored placement goes to the estimator with the ball's
unless it is clearly behind the ball (the ball's range below 0.85 of its own); one about as
far as the ball is another reading at the ball (station 0). **Consequence, NOT MET as far as
"fitted to all placements" goes:** a golfer who walks the old way - from the ball toward the
hole - gets at each stop the putt from that stop, made of the placements from there to the
hole only; `Dn` still counts the stops. Walking toward the ball, as E29 describes, every
placement is used.

**The same placements in the old and the new order give the same estimate.** After the third
placement of E29's example (2 m, 6 m, then the ball at 9 m) the test hands the same three
records to the estimator again, ball first - the order of the old rule and of the reference -
and in three more orders; and the reference is run ball first on the records of every row of
the table under "Putt on the display":

<!-- readme-check:begin survey -->
```
the 3 placements of the E29 example handed to the estimator in 5 orders (ball first = the old order, ball last = the new one, and 3 between): aim within 0.0000 mrad, speed within 0.0e+00, 3 of 5 bit-identical
old order (9 m ball first, 6 m, 2 m): aim 49.512 mrad, break 2.456 cups; new order (2 m, 6 m, 9 m ball last): aim 49.512 mrad, break 2.456 cups
result at the second placement (3 m; the first, 6 m, lies behind it and is not used): patch a -0.0151 b 0.0037 c -0.00038 d 0.00000, aim 21.7 mrad, status 0, aim source 0
NOT MET: the base of the stick at the ball (3 m) was classed AT THE HORIZON in this run (it ends 1.24 rows below the horizon, the margin is 1.5: the class flips with the frame noise)
```
<!-- readme-check:end survey -->

The last two lines are `tests/test_e2e.c`, which walks the old way round on purpose: at the
second placement (3 m) the result is that placement's alone; and the class of the stick's
base there still flips with the frame noise (open issue 22) - since E29 that placement is the
ball, so the flip decides between `PLAYS n` and `PLAYS n?`.

### Recall (E30)

A marker whose result has left the screen after its 45 s is asleep. **A tap wakes it** (the
IMU's wake-on-motion), and if it has not been lifted since that result was made, the result is
shown again for 45 s with its age (`45S AGO`, `12M AGO`, `5H AGO`) in a line of its own at the
bottom: no tilt read, no camera rail, no solve, and nothing is written to the log. It can be
recalled again after that, for 24 hours; a tap on an older result makes a new read.

**"Not lifted", from the motion data the firmware has** (`recall_watch_()`; the constants and
their reasons are in `app/gl_app_cfg.h`). The result is NOT shown again if any of these was
seen from the moment it came onto the screen:

* the gyro, integrated with the read's own bias while the result is on the screen and from
  the wake-up until the marker is at rest, turned by more than 2 degrees about any axis (a
  twist on the spot);
* a still 133 ms block whose mean gravity direction differs from the one the marker rested in
  at its read by more than 4 mg on an axis (4 mrad of tilt: a tenth of what a read calls
  motion while a result is shown);
* after the wake-up, a posture other than flat, or more than 3 moving blocks before the
  marker is at rest (a disturbance that lasts d leaves ceil(d / 133 ms) + 1 of them: a tap 2,
  a nudge of 0.2 s 3; picking the marker up and putting it down takes longer);
* the Precision spin was begun and given up (the marker may lie anywhere);
* anything else that happened in between: the cradle, the dial, an error, low battery, a
  reset (the transition table keeps the offer only on the path asleep - woken by motion -
  waiting for stillness: `gl_ui_t.recall`).

While the marker SLEEPS nothing is measured: a lift is seen because it wakes the marker and is
still going on when the samples start. The boundary, from both sides, with the whole firmware
on the simulator (`tests/test_e2e_recall.c`):

<!-- readme-check:begin recall -->
```
result back on the screen 0.88 s after the tap
age shown: "2M AGO" (the result was made 142 s before)
what happens to the sleeping marker          | outcome        | rail cycles |
a tap (60 ms)                                | RECALL         |           1 | 2 moving blocks after the wake-up (limit 3)
a nudge of 0.2 s                             | RECALL         |           1 | 3 moving blocks after the wake-up (limit 3)
a nudge, then lying 2 mrad differently       | RECALL         |           1 | 3 moving blocks after the wake-up (limit 3)
a tap and a twist of 1 degree                | RECALL         |           1 | 2 moving blocks after the wake-up (limit 3)
a shove of 0.6 s                             | a new read     |           2 |
a nudge, then lying 6 mrad differently       | a new read     |           2 |
a tap and a twist of 5 degrees               | a new read     |           2 |
a slow twist of 5 degrees (1.5 s)            | a new read     |           2 |
lifted for 1.2 s, back on the same spot      | a new read     |           2 |
lifted for 0.5 s, back on the same spot      | a new read     |           2 |
lifted for 4 s, back, turned by 0.5 degree   | a new read     |           2 |
twisted 10 degrees in 0.4 s while the result was shown, tapped after it slept: a new read
Precision spin begun and given up, tapped after it slept: a new read
Precision result recalled after a tap: aim -3102.53 mrad, drawn turned round as before
tapped 23 h 50 min after the result: 23H AGO
tapped 25 h after the result: a new read
```
<!-- readme-check:end recall -->

**NOT VERIFIED (no hardware):** that a tap trips the IMU's wake-on-motion at its provisional
threshold (`GL_PROV_IMU_WAKE_THRESHOLD_MG`, 62 mg); how long the IMU takes from that interrupt
to its first sample - in the simulator the samples start at once, on a board a turn or a
slide that is over before the first sample is not seen; the accelerometer's offset drift over
temperature against the 4 mg limit (data sheet figure from memory: PROVISIONAL); whether turf
lets a marker settle by more than 4 mrad in the minutes after a read (then a tap makes a new
read, which is the safe side).

### Read time: the rail-time bound (E15)

**Done: bounded, and the cost measured.** A read that finds several lines in the horizon band
gives each one L R R L group of its own before it follows one. Until phase 3 the line that
was followed then got all eight groups on top: 44 strips and 3.36 s of camera rail with a
person behind the stick, against the 2.2 to 2.8 s the specification states. Now the read has
eight groups IN ALL: two lines 2 + 6, three 3 + 5, four 4 + 4 (`GL_APP_PROBE_FREE_GROUPS` 0,
`GL_APP_MIN_FOLLOW_GROUPS` 4; with one group more the three-line read is at 2.82 s, still
outside). `make bench-vision`, one read of each scene at the nominal compute factor:

<!-- readme-check:begin bench-vision -->
```
one read of each scene on the simulator (cycles per instruction 2.0, 160 MHz):
  A       trace points: band 1, strip 32, group 8 | cost table: band 14.27 M, strips 45.36 M, groups 0.32 M, total 59.95 M instructions | rail on 2424 ms, compute 749 ms
  B       trace points: band 1, strip 32, group 8 | cost table: band 14.27 M, strips 45.36 M, groups 0.32 M, total 59.95 M instructions | rail on 2424 ms, compute 749 ms
  near3   trace points: band 1, strip 32, group 8 | cost table: band 14.27 M, strips 63.92 M, groups 0.32 M, total 78.51 M instructions | rail on 2658 ms, compute 981 ms
  near1   trace points: band 1, strip 32, group 8 | cost table: band 14.27 M, strips 63.92 M, groups 0.32 M, total 78.51 M instructions | rail on 2658 ms, compute 981 ms
  faint   trace points: band 1, strip 32, group 8 | cost table: band 14.27 M, strips 30.00 M, groups 0.32 M, total 44.59 M instructions | rail on 2224 ms, compute 557 ms
  faint2  trace points: band 1, strip 32, group 8 | cost table: band 14.27 M, strips 34.19 M, groups 0.32 M, total 48.78 M instructions | rail on 2225 ms, compute 610 ms
  person  trace points: band 1, strip 32, group 8 | cost table: band 14.27 M, strips 52.64 M, groups 0.32 M, total 67.23 M instructions | rail on 2558 ms, compute 840 ms
  none    trace points: band 1, strip 0, group 0 | cost table: band 14.27 M, strips 0.00 M, groups 0.00 M, total 14.27 M instructions | rail on 336 ms, compute 178 ms
```
<!-- readme-check:end bench-vision -->

So the nominal read (scene A): rail on 2424 ms; with a person behind the stick: 2558 ms of camera
rail where it was 3357.

**What it costs in accuracy**, on the vision test scenes that have several lines
(`tests/test_read.c`, `test_rail_time_is_bounded_with_several_lines`: each scene read 16
times with the bound and 16 times without, on the 160 MHz clock as in the application):

<!-- readme-check:begin rail-bound -->
```
16 reads per scene; rail = camera rail on, the longest read of the scene; d rms = disparity error rms, px; rng = fused range error rms, %
scene                | probed | bound ON: groups  strips  rail ms  d rms    rng %  stereo | bound OFF: strips  rail ms  d rms    rng %  stereo
A_nominal            |      0 |         0 + 8      32     2423  0.0033   0.15   16/16  |               32     2423  0.0033   0.15   16/16
A_person_behind      |      2 |         2 + 6      32     2491  0.0324   0.51   16/16  |               40     3024  0.0324   0.50   16/16
A_person_0.6m        |      3 |         3 + 5      32     2557  0.0072   0.32   16/16  |               44     3357  0.0039   0.17   16/16
A_person_2m          |      3 |         3 + 5      32     2557  0.0054   0.24   16/16  |               44     3357  0.0041   0.19   16/16
A_pole2_7px          |      2 |         2 + 6      32     2491  0.0209   0.54   16/16  |               40     3024  0.0191   0.52   16/16
A_pole2_far_weak     |      2 |         2 + 6      32     2490  0.0049   0.21   16/16  |               40     3024  0.0036   0.15   16/16
A_pole2_far_strong   |      2 |         2 + 6      32     2457  0.0073   0.34   16/16  |               40     2991  0.0066   0.30   16/16
B_pole2_far_weak     |      2 |         2 + 6      32     2491  0.0147   0.93   16/16  |               40     3024  0.0125   0.80   16/16
B_pole2_far_strong   |      2 |         2 + 6      32     2457  0.0148   0.95   16/16  |               40     2991  0.0119   0.78   16/16
A_glare_sun_in       |      2 |         2 + 6      32     2457  0.0093   0.42   16/16  |               40     2991  0.0068   0.31   16/16
A_combo              |      3 |         3 + 5      32     2590  0.0983   5.27   16/16  |               44     3391  0.0973   5.21   16/16
longest rail time: 2590 ms with the bound (limit 2800), 3391 ms without it (10 scenes over the limit)
cost, over the 9 scenes with several lines: disparity rms 0.0155 px with the bound, 0.0143 px without; range rms 0.56 % against 0.48 %
```
<!-- readme-check:end rail-bound -->

The longest read keeps the rail on for 2590 ms with the bound and for 3391 ms without it. Over the
nine scenes with several lines (the combination scene left out of the mean: it has 5 % of range
error either way): disparity error rms 0.0155 px with the bound against 0.0143 px without it; range
error rms 0.56 % with the bound against 0.48 % without. No read of a scene lost its disparity
and no other object was taken for the stick. **Why this was judged acceptable:** the part
of the disparity error that grows is the frame noise of five or six groups instead of eight;
the uncertainty the read CLAIMS is dominated by the stereo calibration term (0.05 px, open
issue 6) and by the static background term, neither of which shrinks with more groups; and a
read with a second line in view is flagged or weaker anyway. **What the bound does not
cover:** a near stick at the high compute factor (the review's 2.99 s at 1.5 m, factor 3;
not repeated), and the 2.66 s of the two near-stick scenes above is inside the figure only at
the nominal factor. Every time here is the simulator's model (open issue 1).

### The regulatory and information screen

The last item of the settings dial is `INFO` (hold the marker upright, double tap through the
items; it sets nothing; laying the marker flat leaves the dial as from any item). Page 1:
`GREENLINE`, `GL-1`, `PRACTICE DEVICE`, hardware revision letter and firmware version (`HW E
FW 0.3`), the serial number (the one stored at the factory, else the one derived from the
processor's unique number). Rolling the marker turns to the text pages.

**How many characters fit.** The display is round: a text page has 10 lines of 12, 15, 17, 19,
19, 20, 19, 18, 17 and 15 characters of the 5 x 7 font = **171 character cells**, and the
screen shows up to 4 text pages = **684 cells**. Words are not broken (a text needs a little
less than the cells), `\n` starts a new line, and the font has capitals, digits and
punctuation only. Each line is checked to hold its count whole and to cut one character more
(`tests/test_ui.c`); `gl_ui_info_fit()` says how many pages a text needs and how much of it
is shown.

<!-- readme-check:begin info-screen -->
```
regulatory text: 10 lines of 12/15/17/19/19/20/19/18/17/15 characters = 171 cells per page, 4 text pages = 684 cells (words are not broken, so a text needs a little less)
four statements of 88 characters (DESIGN_SPEC E18's legend block) need 3 of the 4 text pages
INFO screen: "GREENLINE", "GL-1", "PRACTICE DEVICE", "HW E  FW 0.3", "SN 0Z1HBQP" - on the panel, pixel for pixel
sizeof(gl_ui_t) 48, sizeof(gl_ui_view_t) 80
```
<!-- readme-check:end info-screen -->

**The text is a PLACEHOLDER** (`app/gl_regulatory.h`): which statements a GL-1 must show, and
their exact words, are for `docs/COMPLIANCE.md` to supply (its rows 5 and 33: the FCC part 15
statement if the screen is to serve as the label, the Canadian line, the practice-device
statement, the responsible party); none is frozen there, and a regulatory sentence copied
from memory into firmware would look official and might be wrong. `make release-gate` and
every `RELEASE=1` build fail while it is the placeholder, as they do for the USB ids.

### NOT MET, PROVISIONAL and not verified (builder 3)

* **The pin map changed during this work** (`../electrical/gl1_main/pinmap.json`, sha256
  37c034526369... to d33ff53f50f0..., re-issued by the electrical side at its layout stage).
  `make pins` was run: in `hal/stm32u5/gl_pins.h` the hash and comment lines changed (status
  LAYOUT STAGE, the notes on the charge inhibit and the EXTI numbers) and no pin definition;
  every figure in this file is from a clean build made after that.

* **NOT MET** (each pinned by a test, with its number): a Survey placement behind the ball
  is not used for the result at the ball (`test_survey_second_drop`: the result at 3 m is
  made of that placement alone); near-miss vector 13 is NORMAL in the firmware and APPROX by
  the reference at 1e-9 m (`test_display_state_is_the_same_in_both_builds`); four more
  vectors are `TOO STEEP` with a dashed line in the firmware and without a line by the
  reference at 1e-9 m; the class of the stick's base 3 m from the hole still flips with the
  frame noise (open issue 22, unchanged).
* **PROVISIONAL**: every constant of the recall rule (2 degrees, 4 mg, 3 blocks, 24 h); the
  0.80 of TOO STEEP (chosen from a simulation of the estimator, not from greens); the 0.85 of
  "behind the ball"; the regulatory text.
* **Not verified**: anything on hardware. The tap as a wake-up source and the IMU's start-up
  time. The legibility of any of these screens on the real panel. The rail times (a model).
  Survey fits in the TOO STEEP sweep.
* **Not done**: an on-unit sign of a missing calibration (open issue 49); a Survey that
  survives the 45 s of a result or a sleep; a display of how many placements a Survey result
  used (`Dn` counts the stops); note names in `tools/glctl/logdec.py` (the read record
  carries the note as a number: 11 = TOO STEEP is new; the SOLID_LINE flag of the record is
  now exactly "the NORMAL state").

## Design review: what was done with the 32 findings

| Area | Findings | Outcome |
|---|---|---|
| Charge gate (2 findings, one critical) | fails open with a dead or silent IMU; trusts unvalidated bytes | **Fixed**: liveness-checked IMU temperature, MCU die sensor as second opinion, staleness limit, gate evaluated in every state; simulator rule "charger enabled at Stop entry". **Superseded in phase 2:** rev C2 gives the cell an NTC and turns the charger's default round; gate, rules and tests were rewritten ("Charger and cell temperature"). |
| IMU faults (3) | one bus error disables motion input until reset; lost interrupt latch stalls the loop (backend and application) | **Fixed** in the application (recovery with back-off, polling fallback, watchdog as last resort) and in the STM32 backend (latch updated with interrupts masked; that file compiles against the vendor's headers and has never been linked or run). |
| Capture pipeline (1) | assumed the vision is faster than a frame | **Fixed** structurally (whole group captured, then analysed; frame-end times latched in the interrupt; progress-based time-out). **The run time itself is not fixed**: open issue 1. |
| Precision Read, SET_CAL, LOG_ERASE, store geometry, DFU gate, USB stop outside the cradle state, float-to-int conversions, integer drawing overflow (8) | as titled | **Fixed**, each with a regression test (`test_e2e_faults.c`, `test_log.c`, `test_proto.c`, `test_gfx.c`, `test_basics.c`). DFU has no way back without a host: stated, not fixable here. |
| Vision: trunk / post accepted, stronger object chosen (critical) | | **Fixed for the reviewers' cases**: 0 of 88 stick-free reads report a flagstick; the stick is read beside a stronger post 120 px away. **Not for every case** (the row as the final run of phase 3 has it, `B_pole2_7px` in the block under "Vision"): with a second thin pole 7 px from a 0.8 px stick only half the reads give a disparity; none of them takes the pole. (Before the phase-2 review the pole was taken in half the reads, with the ambiguity flag: that sentence stood here two phases too long.) |
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

**After phase 3** (the paragraph above and the table are the state at the end of phase 2):
five of the nine have been dealt with since. 19 (no limit on the charge) and 27 (the amended
specification) by builder 1: amendment E32 is implemented, the firmware targets the rev E
board. 28 (the Survey never shows a line) and 33 (a result cannot be recalled) by builder 3:
amendments E29 and E30. 2 (the aim is not determined near the critical slope) on the
DISPLAY, amendment E31 - the estimator's search is unchanged, as the brief demands. And 24,
fixed in part in phase 2 (fallbacks that look like a normal result), is closed as far as E33
goes: three display states; the indicator "relative to a clean read" that the finding also
asked for is still not there (open issue 21). **Still not fixed: 9, 10, 20, 32.**

| # | Finding (severity) | Outcome | Before -> after, and the test |
|---|---|---|---|
| 1 | The fallback order discards a near-solution of the patch and shows a secant-plane aim that misses the hole on the fitted patch (major) | **Fixed, additively in the reference too.** New `EstimatorConfig.near_miss_keep` (default 0: the old behaviour, and the old vectors are a byte-identical prefix of the regenerated file), ported as `gl_solver_options_t.near_miss_m` (default 0; the application sets 5 mm). A patch solve that ends without a solution but whose last iterate passes within that distance of the hole centre is kept (`aim_source` 0, its status), its confidence is scored like a fallback's and the screen says `APPROX` | 18 new reference cases (14 kept, 4 controls). In the 14 the kept aim passes at most 4.44 mm from the hole centre on the fitted patch; the aim it replaces misses by more than the hole's radius in 4 and does not reach the hole in 10; the aim moves by up to 159 mrad. `test_near_miss_cases`, `sim/tests/test_near_miss.py`, `make diff` |
| 2 | Near the critical slope a one-microradian input change flips the aim by more than a display step in about 3 % of reads; the best-effort direction is an arbitrary search iterate (major) | **Not a port error; the reference's search is not changed** (decision of the brief). The C double build follows the reference exactly there too (`make diff`: bit-identical aims on every random aim problem that ran). Stated in `gl_solver.h` and under "Solver"; on the screen a best-effort aim was dashed, `NOT SOLVED`, `BREAK ?`, one box at most. **Phase 3 (E31, E33):** it is not drawn at all, and a solved result from 0.80 of the critical slope is `TOO STEEP`, dashed | open issue 24 (the estimator's owner) |
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
| 13 | The costliest estimate blocks the main loop for seconds with no watchdog refresh, and only loop counters bound it (minor) | **Fixed**: `gl_solver_options_t.max_steps`, a budget on the RK4 steps of one estimate (firmware only; default none, as in the reference); the application sets 300,000 and refreshes the watchdog before the solve. A solve that runs out ends as a best-effort aim (phase 2: dashed, `NOT SOLVED`; phase 3: no line) | costliest case: 421 rolls / 575,247 steps -> 223 / 300,514 with the budget. `test_step_budget_and_the_plane_solved_once` |
| 14 | `build_measurement_()` clamps the horizon count to the solver's 41 but copies from arrays of 32 (minor) | **Fixed**, and a compile-time assertion ties the two sizes | `tests/test_app_handover.c`: counts of 33..255 reached the solver as 33..41 samples -> 32 |
| 15 | Test audit: one phase-1 safety expectation reversed, the application-level staleness test gone (minor) | **Staleness test restored** end to end. "One die sensor is enough" stays as built: open issue 5 | `test_stalled_supervision_stops_the_charge`: the charge is stopped when the last cell reading is 12.0 s old (before: never) |
| 16 | The simulator's power rules fire in two thirds of random VBUS-bounce scenarios (minor) | **The firmware was at fault, not the rules**: it could go to sleep on a VBUS level it had not acted on. Fixed with 11 | 300 random scenarios (4857 edges, 105 resets): 211 scenarios with 422 violations -> 0. `test_vbus_bounce_stress` |
| 17 | Backend, by inspection: wrong DFU comment, `clock_slow_()` ignores a failed switch, clock re-initialisation with the HAL tick suspended (minor) | **Fixed by inspection.** The contract is in `gl_hal.h` (a failed switch back returns `GL_ERR_IO` and the clock is still FAST), the simulator can fail the switch, and the application no longer believes it | three failed switches during a read: 482 "Stop mode with the fast clock" violations -> 0, `clock_fails` 3. `test_failed_switch_to_the_slow_clock_is_not_believed`, `test_board.c` |
| 18 | `make cross` checks the objects, not an image (minor) | **Fixed as a check**: `tools/cross_link_check.py` links a probe image against the installed newlib and walks the calls from the firmware's functions | figures under "Building and testing". Still no real image |
| 19 | No firmware limit on charge duration or termination; awake with USB for as long as it sits in the cradle (minor) | **Not fixed**: needs the charger's data sheet and a product decision | **Phase 3: answered by amendment E32 and implemented** (cradle sleep, 6 h backstop); open issues 28, 34, 39 |
| 20 | The 1.5 K guard band leaves 0.6 K at 0 C for the error of the one-B NTC equation (minor) | **Not verified**: no R-T table of the part here | open issue 5 |
| 21 | A second double tap after a Precision Read gives a `2X` result with zero slope and a straight line (**critical**) | **Fixed**: Precision once per placement; a double tap on a `2X` result goes on to the Survey like on any result | `test_double_tap_after_precision_starts_a_survey`, `test_ui.c` |
| 22 | The Precision result is drawn for a marker that faces away from the hole: text upside down, `<` / `>` mirrored for the golfer (major) | **Fixed**: with the ball behind the marker the whole result screen is drawn turned by 180 degrees. Turning the marker back is a new placement and a new read: as built, open issue 29 | the panel is pixel for pixel the upright picture turned round (0 of 16384 differ). `test_precision_result_is_upright_for_the_golfer`, `test_rotate_180` |
| 23 | A dialled distance never expires (major) | **Fixed**: it belongs to one hole. It is forgotten after a read that ranged a flagstick, when the marker goes to sleep and at start-up; a flag-out result is drawn dashed with an empty confidence bar | `test_dialled_distance_belongs_to_one_hole` |
| 24 | The confidence bar does not separate weak results from clean ones; several fallbacks look like a normal result (major) | **Fixed in part**: flag-out is tentative (23), a poor horizon and a kept near miss have messages, `PLAYS n?` marks a hidden base, and the table under "Result on the display" now says which results look normal. **Not done**: an indicator relative to what a clean read achieves at that distance | open issue 21 |
| 25 | Time to a line and camera-rail time exceed the specification's figures in a third of the reads between 2.25 and 4.5 m (major) | **Fixed for that cause, not in general.** The second "line" was the shoulder of the stick in the widest template: dropped. And a lone line that is not a flagstick is given up after its first group | 65 reads at 1.5-4.5 m: 23 with two candidates, rail up to 3.12 s, result up to 5.07 s -> 0, 2.42-2.46 s, at most 4.40 s. 88 stick-free reads: mean rail 1.65 s -> 1.02 s. `test_near_stick_is_one_candidate`, `test_no_flagstick`. Still slow: a person behind the stick, two real lines; the high compute factor; open issue 1 |
| 26 | The distance prompt after "no flagstick seen" is a dead end for 30 s (major) | **Fixed**: picking the marker up and putting it down again reads again; the prompt says so | `test_distance_prompt_re_placing_reads_again`, `test_ui.c` |
| 27 | DESIGN_SPEC has been amended (E1 to E16) since the builders' brief (major) | **Phase 2: not fixed, by the brief's decision. Phase 3: the firmware targets the rev E board ("DESIGN_SPEC amendments").** What follows is the phase-2 text. The generator now reads the charger sentence of the spec and a test pins the difference as NOT MET; the README's statements are corrected | `test_charger_of_the_specification_is_not_the_firmwares`; "DESIGN_SPEC amendments" (E1 to E34 now); open issue 2 |
| 28 | Survey in the order the specification gives never shows a line until a fourth placement back at the ball (minor) | Phase 2: not fixed (product decision). **Phase 3: fixed by amendment E29** - the placement the marker stands on is the ball; a line after every placement | `test_survey_two_three_and_four_drops`, `test_survey_e29_flow`; open issue 18 |
| 29 | A solved aim more than 13.5 degrees off the visor axis is drawn like a tentative one, with an arrow pointing away from the aim (minor) | **Fixed**: the parallel substitute is drawn in the style of the result (solid if solved) and the arrow is gone | aim +258.8 mrad: 0.46 of the solid core inked and 63 pixels of arrow -> 0.73 and 0. `test_solved_aim_off_the_screen_keeps_its_style`, `test_gfx.c` |
| 30 | `PLAYS` is the roll-out distance including the PAST setting (minor) | **Fixed**: `PLAYS` is the estimator's plays-like distance minus PAST | 6 m, dead flat, PAST 0 / 30 / 90 cm: `PLAYS 6.0M` each (estimator 5.98 / 6.28 / 6.88 m). `test_plays_like_is_the_flat_putt` |
| 31 | The GRAIN and GRASS dial items do not change the line (minor) | **Fixed for what exists**: GRAIN ON hands the measured grain to the solver (`use_grain`) with the grass's coefficient; GRAIN OFF measures nothing. GRASS has an effect only with GRAIN ON. The physics behind the coefficients is unproven (`gl_provisional.h`) | aim 109.26 / 113.96 / 136.31 mrad for OFF / ON bentgrass / ON bermuda. `test_grain_setting_reaches_the_solver` |
| 32 | At 2 to 3 m the hole is read 3 to 5 mm low; at 0.6 m the flagstick is refused (minor) | **Not fixed** (vision) | open issue 30 |
| 33 | A result cannot be recalled (minor) | Phase 2: not fixed (product decision). **Phase 3: fixed by amendment E30** (Recall) | `tests/test_e2e_recall.c`; open issue 31 |
| 34 | README statements that the code or the tests contradict (minor) | **Corrected**, all nine, from the final run; the stale comment in `gl_app.c` too. The band-only bearing is not logged: the claim is dropped | this file |

## DESIGN_SPEC amendments: where the firmware stands

`../design/DESIGN_SPEC.md` reads "rev D, EVT1, with amendments E1 to E34". This is all 34,
after the three builders of phase 3 (1: the rev E board and its power behaviour; 2:
calibration, factory commands, field log, boot stub; 3: what the golfer sees). "Unaffected"
means that no line of the firmware depends on the matter; it is a statement about the
firmware, not a check of the amendment. Nothing in the last column has been measured on
hardware.

| # | Specification | What the firmware does | Status, and what is missing |
|---|---|---|---|
| E1 | Charger BQ25101 with its own temperature input; `CHG_INHIBIT` push-pull, HIGH = stop | `drivers/power.c`: latch high, then push-pull, to stop; latch low, then ANALOG, to release. The simulator's charger is a model of the BQ25101 that follows its own thermistor whatever the MCU does | **implemented** (builder 1). Missing: the model's thresholds are PROVISIONAL (no data sheet read); the release gate "thresholds against the NTC curve" stands |
| E2 | Two cell thermistors, Murata NCU15XH103F60RC: NTC1 for the charger, NTC2 for the MCU | NTC2 through `NTC_BIAS` / `NTC_SENSE`, B equation with R25 = 10 kohm and B = 3380 K; error budget computed by a test. NTC1 cannot be read by the MCU | **implemented** (builder 1). Missing: the part's own R-T table (every R-T number is derived from the B equation and nothing else) |
| E3 | Grain LED parts and real drive currents | the white-reference calibration takes the LEDs as they are | **unaffected** |
| E4 | Top-side test points; board test powers the board through the cell-lead pads | `GL_CMD_GET_SENSORS` reads the rails the MCU can see | **unaffected** (the station's business). Missing for the station: no ADC on V2V8_CAM or VBUS |
| E5 | Lead-free assembly; no conformal coat | - | **unaffected** |
| E6 | Cradle circuit (CC resistors, fuse, ESD) | - | **unaffected** (the board's USB-C pads are released first thing after reset, pin-map note; backend by inspection) |
| E7 | 0.10 mm track and gap | - | **unaffected** |
| E8 | Ball feet of stainless steel or silicon nitride | - | **unaffected** |
| E9 | Quarter-wave film under the glass (trial) | - | **unaffected** |
| E10 | Printed legend on the base plate | the INFO screen is the firmware's place for the same statements (builder 3) | **unaffected**; which statements go where is `docs/COMPLIANCE.md`'s decision |
| E11 | Level zero on two seats; the base face is the default for a read | tilt record version 2 holds both, each with temperature, time and scatter; `gl_cal_tilt_zero()` picks by the SURFACE setting (TURF default, HARD = ball seat); `GL_CMD_LEVEL_ZERO` arms a zeroing for a named seat | **implemented** (builder 2). Missing: only the 0 / 180 degree reversal exists, not a four-position zero |
| E12 | Display rotation measured at the factory, stored, applied to the line | device record `display_rot_rad`; `core/gl_ui.c` turns the aim line by it about the screen centre, in every state that has a line; `GL_CMD_DISPLAY_TEST`, `GL_CMD_DISPLAY_ROT` | **implemented** (builder 2); the measuring fixture is the station's |
| E13 | No read above 60 C cell temperature; ship mode | refused above 60.0 C on NTC2, allowed again below 57.0 C; "TOO HOT" for 4 s, then sleep; the factory's camera commands obey it too. `GL_CMD_SHIP_MODE` arms; entered 1 s after the marker leaves the cradle: MCU in Shutdown, wake-up on VBUS | **implemented** (builder 1). **NOT MET** by the supply model: ship mode 12.9 uA against 5 uA |
| E14 | Sleep current no more than 25 uA at 3.8 V | supply model: 20.7 uA at the cell-lead pads with the underside dark | **met by the model only**; 25.9 uA with a lit underside (E27 excludes that case) |
| E15 | Read time 4.1 to 4.8 s, camera rail 2.2 to 2.8 s | the timing model; since builder 3 a read with several lines in view has eight groups in all | **agrees by the model** for the nominal read and for reads with several lines ("Read time: the rail-time bound"). Missing: a near stick at the high compute factor (2.99 s by the phase-2 review, not repeated); any measurement |
| E16 | Baffle-ring tape thickness | - | **unaffected** |
| E17 | Guaranteed upward field 14.0 degrees; test gate 2 bars at +13.0 and -13.0 degrees | `GL_CMD_CAM_FIELD` measures at +-13.0 degrees (`GL_PROTO_FIELD_ELEV_DEG`). No firmware constant holds the field itself | **implemented** for the gate (builder 2). `mechanical/README.md` step 16 still says 13.5 (open issue 48) |
| E18 | Legend print rules; a statement block holds 88 characters | the INFO screen's text block: 171 cells a page, 4 pages; four statements of 88 characters need 3 pages (test) | **unaffected** as a print rule |
| E19 | Quarter-wave film size and clocking flat | - | **unaffected** |
| E20 | Base-plate thickness limits; ball grade | - | **unaffected** |
| E21 | Baffle-ring height rule | - | **unaffected** |
| E22 | Display rotation up to about 1.2 degrees (computed 1.19); adhesive thickness | the stored rotation is limited to +-2 degrees; tested at +-1.2 | **implemented** with E12 |
| E23 | Battery-life and drop requirements | the supply model's figures ("Sleep and the supply model"); the field log and `GL_CMD_LEVEL_ZERO` give the validation plan what it needs to test them | **nothing to implement**; the requirements are tested on EVT units. Ship mode NOT MET by the model (E13) |
| E24 | Display connector moved 0.5 mm | - | **unaffected** |
| E25 | Ideal-diode switch in place of the Schottky; cradle fuse | the supply model follows it | **unaffected** in the firmware |
| E26 | The USB supply pin is powered only with VBUS AND the 2.8 V rail | `gl_hal_usb_supply_ok()`: VBUS_SENSE high AND the MCU's own monitor of that pin; USB is started only then and stopped when it is false | **implemented** on the simulator (builder 1); the backend by inspection. The regulator's enable pin is assumed to draw 2.8 uA for ever (NOT CONFIRMED, open issue 35) |
| E27 | VBUS divider 100 k : 100 k on the pad side; wake pull-up 150 kohm | the simulator's VBUS_SENSE lags the pad by up to 22 ms on removal; 5.2 uA more asleep with a lit underside | **implemented** in the model (builder 1) |
| E28 | LCD connector pin order mirrored by the fold of the tail | the pin map names signals, not connector pads | **unaffected**; a wrong guess in hardware would mirror all ten pins (PROVISIONAL there) |
| E29 | Survey finishes at the ball; a line after every placement from the second on | the placement the marker stands on is the ball; `survey_select_()` hands over the placements that are not behind it; "PUT AT BALL" removed | **implemented** (builder 3). **NOT MET in one respect:** a placement farther from the hole than the ball is not used (the frozen estimator has no station for it) |
| E30 | Recall: a single tap on a marker that has not been lifted shows the last result for 45 s with its age; no camera read | the tap is the IMU's wake-up; "not lifted" from the gyro, the gravity direction and the moving blocks after the wake-up; 24 h limit | **implemented** (builder 3). NOT VERIFIED: that a tap wakes the real IMU, and its start-up time |
| E31 | "TOO STEEP" and a dashed line when the fitted slope is close to the critical one | `gl_ui_steep_ratio()` from the patch, the distance and the deceleration the estimator returns; 0.80 from a sweep against the reference | **implemented** (builder 3). The estimator is unchanged. Survey fits were not swept |
| E32 | Asleep in the cradle 30 s after the host fell silent or with no host; 6 h backstop | UI states `CRADLE_USB` (30 s without host activity) and `CRADLE_SLEEP`; `GL_PROV_CHARGE_MAX_MS` | **implemented** (builder 1). **NOT MET, pinned:** a silent host on a running bus loses the marker until it is re-docked; the backstop does not see a recharge if the charger's status line shows the first cycle only (open issue 39) |
| E33 | Three display states; the solve limited to 300,000 integration steps | `gl_ui_classify()` / `gl_ui_view_show()`; `GL_APP_SOLVE_MAX_STEPS` | **implemented** (builder 3; the step budget since the phase-2 review). NOT MET against the reference at 1e-9 m in 1 of 340 vectors (pinned) |
| E34 | Boot stub; SWD recovery; USB ids a release gate | `boot/`: image header, `gl_boot_decide()`, `tools/stamp_image.py`; `app/gl_usb_ids.h` placeholders, `make RELEASE=1` / `make release-gate` fail | **implemented as far as a host can take it** (builder 2): the logic is tested, the STM32 part links and has NEVER RUN; six release gates in "Boot stub" |

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
| `app/` | Main loop and glue: `gl_app`, `gl_motion`, `gl_read`, `gl_usb`, `gl_factory` (phase 3: the factory and calibration commands), `gl_usb_ids.h` (USB ids: named placeholders), `gl_regulatory.h` (phase 3, builder 3: the text block of the INFO screen, a named placeholder), `gl_app_cfg.h` (tuning constants, flash layout), `gl_main.c` (`main()`). |
| `boot/` | The boot stub of E34, a program of its own in page 0 of the flash: `gl_boot.h` (layout, image header, the rule), `gl_boot_logic.c` (portable: image check, decision; in the host test library), `gl_boot_stm32u5.c` and `gl_boot.ld` (by inspection; `make boot-cross` compiles and links them, nothing has run). |
| `tests/` | Host unit tests, one executable per `test_*.c` (33; new in phase 3: `test_e2e_power.c` - the hot cell, ship mode, the cradle, the sleep current -, builder 2's `test_cal.c`, `test_fieldlog.c`, `test_factory.c`, `test_boot.c`, and builder 3's `test_e2e_recall.c` - Recall and the INFO screen), with the tiny runner `gl_test.h`; `test_drv_*.c` check bus traffic, `test_e2e.c` and `test_e2e_faults.c` run the whole firmware on the simulator (the second one with faults injected), `test_e2e_putt.c` runs whole reads on rendered scenes and compares the line on the panel and the numbers shown with the reference, `test_e2e_review.c` holds the regression tests of the phase-2 review that need the whole firmware (product behaviour, charger supervision with lost VBUS edges, 300 random VBUS-bounce scenarios), `test_app_handover.c` calls the application's hand-over to the solver directly, `test_board.c` checks the rev C2 board rules (chip selects through reset, core-clock calls, EXTCOMIN) and, as a check of the source text, the order of the backend's start-up, `test_read.c` runs the camera part of a read on hard scenes, `test_vision_equiv.c` compares the vision bit for bit with the frozen phase-1 version, `test_solver.c` runs the solver against the reference vectors in both precisions. |
| `tests/vision_ref/` | The vision of phase 1, frozen (`gl_vision_p1_body.inc`, verbatim; built with its symbols renamed `glp1_*`): the oracle of `test_vision_equiv.c`. Host only. |
| `tests/solver/` | `gl_solver_vectors.c` (**generated** from `../sim/results/reference_vectors.json`, 1.06 MB of C data, host only), its hand-written header, `gl_solver_run.c`, the harness that is compiled once per precision, and `gl_solver_ref.c`, the double-precision build of the solver behind a plain-C interface (`gl_ref_estimate`), which the end-to-end putt test uses as its reference. |
| `tests/synth/` | Synthetic strip renderer (`gl_synth`), the reviewers' independent, physically consistent scene generator (`gl_scene`, used by `test_read.c`) and simulated NOR flash with power cuts (`gl_simflash`). |
| `tools/glctl/` | **The PC tool** (phase 3, builder 2; Python 3, standard library only): `proto.py` (framing, records), `transport.py` (serial port with pyserial if installed; the host simulator), `device.py` (one method per command), `logdec.py` (log dump -> JSON), `replay.py` (logged reads through the Python reference), `__main__.py` (the command line), `selftest.py` (`make tooltest`). |
| `tools/` (phase 3) | `glsim_host.c` (the firmware on the simulator as a program glctl talks to: `build/host/glsim`), `stamp_image.py` (stamps and checks the image header of the boot stub), `boot_check.c` (the stub's own image check as a host program), `boot_cross.sh` (`make boot-cross`). |
| `tools/` (phase 3, builder 3) | `readme_check.py` (the figures of this file against the logs of the final build: `make readme-check`), `steep_sweep.py` (the sweep behind the "TOO STEEP" threshold: `make steep-sweep`), `cross_sizes.c` (not firmware: `sizeof` of the application object and its parts as the cross compiler lays them out, for the RAM table). |
| `tools/` | `gen_config.py` (YAML -> `core/gl_config.h`), `gen_font.py` (-> `core/gl_font_data.c`), `gen_pins.py` (-> `hal/stm32u5/gl_pins.h`, cross-checked against DESIGN_SPEC), `gen_vectors.py` (reference vectors -> `tests/solver/gl_solver_vectors.c`), `cross_report.sh` and `cross_link_check.py` (`make cross`: sizes, stack frames, forbidden symbols, fused instructions, the link probe); host-only solver tools: `diff_solver.py` + `diff_solver_abi.c` (`make diff`), `solver_bench.c` (`make bench`), `app_diff.py` (`make appdiff`: the estimator inputs the application produced, run through the Python reference); run-time tools: `vision_bench.c` (`make bench-vision`), `vision_cost.sh` (`make profile`); `cross_hal.sh` and `cross_hal_report.sh` (`make cross-hal`). |

## Building and testing

```
make test     # gcc -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror, builds
              #   core + drivers + app + simulator and runs all 33 test executables
              #   (several minutes, most of them the reads of tests/test_read.c)
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
make boot-cross [STM32_HEADERS=<dir>]
              # the boot stub (boot/): its portable part with the cross flags (also the last
              #   step of `make cross`); with the vendor's device header it is compiled and
              #   LINKED (no library, no start-up file) and must fit its 8 kB page
make tooltest # NOT part of `make test` (it needs the Python reference's environment for the
              #   replay): builds build/host/glsim (the firmware on the simulator with its USB
              #   port on stdin / stdout) and runs tools/glctl/selftest.py - every protocol
              #   command through the PC tool, log download with resume, decoder, replay
              #   through sim/greenline_sim, image stamping against the stub's check, release
              #   gate.  About 5 s
make replay-demo
              # the replay part of it alone
make release-gate
              # exit 1 while the USB ids in app/gl_usb_ids.h or the regulatory text of the
              #   INFO screen in app/gl_regulatory.h are placeholders (both are);
              #   `make RELEASE=1 <target>` defines GL_RELEASE_BUILD and fails the same way
make steep-sweep
              # NOT part of make test: the sweep the "TOO STEEP" threshold was chosen from
              #   (tools/steep_sweep.py: the Python reference and the firmware's solver;
              #   about 8 minutes)
make readme-logs [STM32_HEADERS=<dir>]
              # runs test, cross, appdiff, tooltest, bench-vision, bench, diff, steep-sweep
              #   and asan (and cross-hal, boot-cross with the headers) and keeps each
              #   output in build/readme/ (about 45 minutes)
make readme-check
              # tools/readme_check.py: every generated block of this file and every figure
              #   the script binds must be what those logs say; exit 1 on a difference
              #   (`python3 tools/readme_check.py --update` rewrites the blocks,
              #   `--audit` lists numbers of this file that occur in no log)
make pins     # regenerate hal/stm32u5/gl_pins.h from ../electrical/gl1_main/pinmap.json, its
              #   SINGLE input.  The layout may still exchange pins: this one command (and
              #   `make test`) follows it.  Nothing in the firmware names a pad by hand
make pins-check
              # fails if gl_pins.h is stale against pinmap.json, and if the generator has
              #   stopped refusing the 31 defects its self-test seeds into a copy of the pin
              #   map.  Part of config-check, and with it of every test and cross build
make config   # `make pins`, then regenerate core/gl_config.h, core/gl_font_data.c and
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

**The final build of phase 3** (`make clean`, then `make readme-logs`; generated by
`tools/readme_check.py` from `build/readme/test.log` and `asan.log`):

<!-- readme-check:begin test-summary -->
| Test executable | tests | checks (`make test`) | failed | checks (`make asan`) | failed |
|---|---|---|---|---|---|
| `tests/test_app_handover.c` | 2 | 522 | 0 | 522 | 0 |
| `tests/test_basics.c` | 11 | 7135 | 0 | 7135 | 0 |
| `tests/test_board.c` | 7 | 303 | 0 | 303 | 0 |
| `tests/test_boot.c` | 3 | 959 | 0 | 959 | 0 |
| `tests/test_cal.c` | 5 | 130 | 0 | 130 | 0 |
| `tests/test_cam.c` | 5 | 789 | 0 | 789 | 0 |
| `tests/test_drv_cam.c` | 11 | 375 | 0 | 375 | 0 |
| `tests/test_drv_flash.c` | 7 | 107 | 0 | 107 | 0 |
| `tests/test_drv_grain.c` | 7 | 1188 | 0 | 1188 | 0 |
| `tests/test_drv_imu.c` | 10 | 166 | 0 | 166 | 0 |
| `tests/test_drv_lcd.c` | 10 | 115 | 0 | 115 | 0 |
| `tests/test_drv_power.c` | 16 | 39319 | 0 | 39319 | 0 |
| `tests/test_e2e.c` | 14 | 3103 | 0 | 3103 | 0 |
| `tests/test_e2e_faults.c` | 18 | 1992 | 0 | 1992 | 0 |
| `tests/test_e2e_power.c` | 11 | 412 | 0 | 412 | 0 |
| `tests/test_e2e_putt.c` | 10 | 1927 | 0 | 1927 | 0 |
| `tests/test_e2e_recall.c` | 5 | 344 | 0 | 344 | 0 |
| `tests/test_e2e_review.c` | 14 | 366 | 0 | 366 | 0 |
| `tests/test_factory.c` | 13 | 1453 | 0 | 1453 | 0 |
| `tests/test_fieldlog.c` | 4 | 181 | 0 | 181 | 0 |
| `tests/test_gesture.c` | 4 | 82 | 0 | 82 | 0 |
| `tests/test_gfx.c` | 13 | 50697 | 0 | 50697 | 0 |
| `tests/test_grain.c` | 8 | 946 | 0 | 946 | 0 |
| `tests/test_log.c` | 15 | 15716 | 0 | 15716 | 0 |
| `tests/test_pins.c` | 12 | 4673 | 0 | 4673 | 0 |
| `tests/test_proto.c` | 14 | 813 | 0 | 813 | 0 |
| `tests/test_range.c` | 12 | 287 | 0 | 287 | 0 |
| `tests/test_read.c` | 9 | 4858 | 0 | 2021 | 0 |
| `tests/test_solver.c` | 17 | 2860 | 0 | 2860 | 0 |
| `tests/test_tilt.c` | 10 | 3549 | 0 | 3549 | 0 |
| `tests/test_ui.c` | 30 | 1541894 | 0 | 1541894 | 0 |
| `tests/test_vision.c` | 14 | 2080 | 0 | 2080 | 0 |
| `tests/test_vision_equiv.c` | 3 | 12 | 0 | 12 | 0 |
| **33 executables** | **344** | **1689353** | **0** | **1686516** | **0** |

`make test`: "33 test executables, 0 failed". `make asan`: "33 test executables, 0 failed" (fewer checks: `test_read.c` runs 3 reads per scene there instead of 8).
<!-- readme-check:end test-summary -->

**Where the numbers of this file come from** (phase 3; the phase-2 final check found figures
here that no run produced any more). Two kinds of text are checked against the logs by `make
readme-check`: the blocks between `readme-check:begin` and `readme-check:end` comment lines,
which the script GENERATES (tables built from a log, or log lines quoted verbatim), and
single figures in sentences that the script binds with a regular expression (its `CHECKS`
table). Everything else in this file is prose that a person wrote: where it carries a number
from an earlier phase, that number was true of that phase's run and is not checked now -
`python3 tools/readme_check.py --audit` lists the candidates. The older sections say "this
session" for the session they were written in.

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
instruction (`vfma`, `vfms`, `vfnma`, `vfnms`); the count of `vmla` / `vmls`, which multiply,
round, add and round - as written -, is in the block below.

**The link probe** (phase-2 review: the object check says nothing about what the C library
brings into an image). `tools/cross_link_check.py` links the cross-compiled objects against
the installed toolchain's libm and libc - a probe, not an image: no start-up code, no linker
script, every `gl_hal_*` symbol unresolved, nothing run -, builds the graph of direct calls
and takes EVERY firmware function as a starting point. The final build: probe text 130412
bytes, 568 functions of which 483 are the firmware's; the firmware reaches 45 library
functions by direct calls (single-precision libm and its kernels, `memcpy` and friends,
`__aeabi_ldivmod`, `__errno`); **17 double-precision helpers are PRESENT in the probe and
none is reachable from firmware code** (newlib's `erff` shares an object with `erfcf`, and
its error helpers with their double twins: "called only from `__math_check_oflow`,
`__math_check_uflow`, `__math_divzero`, `__math_invalid`, `erfcf`, `xflow`"); no heap, no
stdio. The check fails if any of them becomes reachable. What it does not show: another C
library (newlib-nano, a vendor toolchain), calls through pointers inside the library, or
anything about the HAL sources, which are not here. `errno` IS reachable (`__errno`,
`with_errnof`): newlib's single-precision functions set it; the firmware never reads it.

The checks of `make cross`, as the final build printed them:

<!-- readme-check:begin cross-checks -->
```
OK: no double-precision helpers, no double libm calls, no heap, no stdio
OK: no fused instruction; 354 vmla / vmls (multiply, round, add, round - as written)
probe linked (no start-up code, no HAL, never run): text 130412 bytes; 568 functions, 483 of them the firmware's
library functions the firmware's code can reach by direct calls (45):
PRESENT in the image but NOT reachable from firmware code: 17 forbidden functions the linker kept (dead code):
OK: nothing double-precision, no heap and no stdio is reachable from firmware code in the linked probe
OK: boot/gl_boot_logic.c references no external symbol (no library, no helper call)
```
<!-- readme-check:end cross-checks -->

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
| `power` | Rev E. Battery through the 2 x 1 Mohm divider (VDDA from VREFINT), percent, low / critical / storage; VBUS and the charger's CHG line (inputs WITHOUT an internal pull). **Cell temperature from the MCU's thermistor NTC2** (`NTC_BIAS` - 10.0 kohm - `NTC_SENSE` - NTC 10 kohm, B 3380 K - ground): one conversion with the bias released (must read near ground, else `STUCK`), bias driven push-pull high, 500 us to settle, 8 conversions, bias back to analog; ratiometric B-equation conversion; open above 98 % and short below 2 % of full scale. **The firmware's charge gate** (`gl_power_charge_gate`): the BQ25101 charges by itself; `CHG_INHIBIT` is driven push-pull HIGH (stop) unless the NTC2 reading is fresh and passed its checks, at least one live die sensor (IMU, MCU) is within 10 K of it, and it is inside 0..45 C narrowed by a 1.5 K guard band, with 2 K of hysteresis; also after 6 h of continuous charging (E32) and by command; without VBUS the pin is released (analog). **Charger status** (`gl_power_charger_status`): one of seven states inferred from CHG, VBUS, the firmware's own stop, the cell voltage and NTC2. **Read gate** (`gl_power_read_allowed`, E13): no camera read above 60 C, 3 K of hysteresis. `gl_power_init()` does not touch `CHG_INHIBIT` or `NTC_BIAS`. | That init leaves both pins as reset left them; the B-equation conversion against a table computed in the test in double precision (-40..85 C in 0.5 C steps: worst error 0.011 K; the simulator's NTC model agrees with the same table to 2e-12 counts); the tolerance budget; the exact pin and ADC sequence of a measurement (`NTC_BIAS` driven for 684 us); open, short and stuck-high detection; the gate over a sweep of -10..60 C and back (not stopped 3.5..43.5 C rising, 1.5..41.5 C falling); unknown, stale, faulty and implausible temperatures; the 6 h limit, its release and its latch for a cell that never came up; the stop by command; the status inference; the read gate; the simulator's charger rules; the hardware model alone over temperature and at the end of a charge. |
| `grain_frontend` (rev E addition) | The amplifier's mid-rail bias is a divider fed from `LCD_DISP` (from the always-on rail it would draw 14 uA for ever). `gl_grain_fe_power(true)` returns `GL_ERR_STATE` with the display off and waits 35 ms (was 25) otherwise. | Refused, with nothing powered and no LED lit, while DISP is low; with the display switched on at the last moment the first conversion comes 35.7 ms after DISP went high. |

Notes for the hardware review that came out of writing the drivers:

* **Grain LED current.** With the 2.8 V rail and two 68 ohm resistors in the path the LED
  current is about (2.8 - 2.0) / 136 = 6 mA for red and about 10 mA for NIR, not the 20 mA that
  `docs/research/grain-sensing.md` assumes.
* **Charlieplex wiring** (the firmware's proposal, which the rev E netlist has adopted:
  `tests/test_pins.c` compares the driver's table with the pin map's 16 LEDs): pair k on the pin pairs (0,1) (0,2)
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
photodiode stage driven by the charlieplex pin states (its bias divider fed from `LCD_DISP`,
as on the rev E board), a USB host (absent, active, suspended; the USB supply of the MCU and a
VBUS_SENSE pin that lags the pad on removal), the MCU's thermistor NTC2 and its divider (cell
temperature set by the test, part tolerances, open / short / stuck faults, a conversion sees
the divider only while `NTC_BIAS` is driven and settled), and for rev E:

* **the charger: a model of the BQ25101 with its OWN thermistor NTC1 on the cell.** It charges
  whenever VBUS is present, its own temperature window allows it and `CHG_INHIBIT` is not
  DRIVEN high - with the MCU in reset, in the ROM loader, hung or in ship mode exactly as with
  firmware running. JEITA zones (no charge below 0 C and above 60 C, half current below 10 C,
  4.06 V above 45 C), termination at 10 % of 19.8 mA of OUTPUT current, recharge 100 mV below
  the regulation voltage, a 10 h safety timer, CHG as an open-drain status, TS low = disabled,
  TS open (NTC1 broken off) = no window, no timer, no termination. **Every one of these is
  PROVISIONAL** (`GL_PROV_BQ25101_*`: the specification's text, web-search extracts quoted in
  the netlist notes, or memory of the family); the model proves nothing about the chip;
* an optional **cell** (43 mAh, an open-circuit curve and 1.5 ohm, both guesses), so that a
  charge tapers and the charger can, or cannot, see its termination current;
* the board's resistors from the generated pin map (`GL_PINS_RESET_TABLE`), an MCU reset
  (`gl_sim_mcu_reset`: every pin back to analog), the **ROM loader** (`gl_sim_mcu_enter_rom`)
  and **Shutdown = ship mode** (every pin released, nothing runs, only VBUS on its wake-up
  pin restarts the MCU), and the core clock as a recorded state.

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
* charger rules (rev E): Stop mode, or ship mode, with `CHG_INHIBIT` driven high and no VBUS
  (a stop left behind by a sleeping MCU); Stop mode in the cradle with no wake-up source due
  within 10 s (nobody would be watching the cell); the charger running for more than 10 s
  outside the FIRMWARE's 0..45 C while the firmware runs; `CHG_INHIBIT` in a mode that stops
  nothing or half opens the MOSFET (open drain, an internal pull); `CHG_STAT` as anything but
  an input without a pull (it is a USB Type-C CC pad); USB started or left on without its
  supply; a reboot to the ROM loader with an IMU interrupt still routed (the two lines are the
  loader's SPI inputs); ship mode entered with the display, the camera rail, USB, the ADC,
  the op-amp, a chip select or `NTC_BIAS` still on; a grain conversion with `LCD_DISP` low or
  high for less than 35 ms (its bias divider hangs on that line); an internal pull enabled
  against a board pull;
* NTC rules: a conversion of the NTC channel less than 300 us after the bias was driven;
  `NTC_BIAS` still driven at Stop entry;
* clock rules: Stop mode with the core clock fast; and it counts vision and solver trace points
  that ran at the slow clock (`heavy_while_slow`, asserted to be 0 by the end-to-end tests).

It also MEASURES what it cannot forbid: the time both cameras' pads are enabled during power-up
(`cam_powerup_overlap_us`), how long the charger ran in all, outside the firmware's window
(total and longest stretch), with no firmware (reset, ROM loader, ship mode), outside its OWN
window (0 unless NTC1 is open), in its WARM and COOL zones, how many charges it terminated,
what the board drew from the charger's node while docked, the time in ship mode, how long
`CHG_INHIBIT` was held and `NTC_BIAS` driven, the number of clock switches and the time at the fast clock, the computation charged per stage
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
| `gl_pins.h` | **Generated** by `tools/gen_pins.py` from `../electrical/gl1_main/pinmap.json`, its single input (`make pins`; "Pins of the rev E board" below has the table and the rules). The file holds no pin of its own. One X-macro row per signal of `gl_pin_t`: port, pin, LQFP-64 pad, function kind, AF number, internal pull, board circuit, EXTI line, state with the camera rail off, state asleep, source; then the ROM-loader pins, the USB Type-C CC pads, the interrupt and wake-up lines, the ADC channels, the reset levels, the lines that float in reset, the grain LED wiring, and the 17 firmware notes of the pin map with the place in the firmware that acts on each. |
| `gl_hal_stm32u5.c` | Clocks (MSIS 48 MHz trimmed against LSE; **rev C2: `gl_hal_clock_set()` switches SYSCLK to PLL1 at 160 MHz and back** - PLL1 from MSIS / 3 x 20 / 2; up: voltage range 1 with the EPOD booster, PLL locked, then SYSCLK with flash latency 4; down: SYSCLK back to MSIS, PLL off, then the lower voltage range; a PLL that does not lock leaves the slow clock and is not an error; SPI1, SPI2 and the ADC take their kernel clock from MSIK so that their timing does not move; `gl_hal_delay_us()` scales with the clock; Stop mode is refused (idle sleep instead) while the clock is fast; XVCLK = MSI / 4 on MCO), tick on LPTIM3 from LSE (runs through Stop 2), RTC seconds and RTC wake-up timer, GPIO from the pin table, EXTI sources, Stop 2 / sleep that returns only for an enabled source and cannot lose a wake-up, SPI1 / SPI2, **bit-banged SCCB** (two clock lines for two sensors at one address: no I2C peripheral can do that), DCMI snapshot with crop + byte select through GPDMA, ADC1 14-bit, OPAMP1 standalone, LPTIM1 PWM for EXTCOMIN, independent watchdog (32 s), unique id, reboot, jump to the ROM DFU bootloader through a backup-register flag (taken only if VBUS is present, so a marker in a pocket cannot be parked in the ROM). After the review: the interrupt latch is updated with interrupts masked (a lost IMU data-ready used to be possible), `gl_hal_extcomin_stop()` and the op-amp stop are safe before their start, the DCMI frame-end time is latched in the interrupt, the die temperature sensor is read, ICACHE is enabled. Rev C2: the NTC channel (ADC1_IN13), `CHG_INHIBIT` and `NTC_BIAS` left analog by `gl_hal_init()`, the chip selects taken over at the level of their pulls (output latch written before the mode). **Phase-2 review, by inspection** (it compiles; a test checks the order in the source text; none of it has run): the independent watchdog is the FIRST thing `gl_hal_init()` starts, the function has ONE return, and a failure of a later step is remembered and returned at the end with the watchdog running (it used to return before the watchdog was started, and the application's error loop then ran for ever with the charger on); a crystal that does not start is survived on LSI (tick, RTC and EXTCOMIN about 2.4 % off and untrimmed MSIS: reported as `GL_ERR_TIMEOUT`); the way back from the fast clock returns a status (`GL_ERR_IO`, still fast, if SYSCLK will not switch); `gl_hal_delay_ms()` / `_us()` are bounded loops; the HAL tick is resumed BEFORE the clocks are re-initialised after Stop 2 (the HAL's time-outs need it); the comment about DFU and the charger says what the code does. The PLL / booster / latency sequence in particular is written from memory of the reference manual. **Phase 3, rev E, by inspection** (it compiles warning-free; `tests/test_board.c` checks the order in the source text; NONE of it has run): `UCPD_DBDIS` is the first statement of `gl_hal_init()` (PA15 and PB15 are USB Type-C CC pads of the MCU); the pins in the order floating lines LOW / lines a resistor holds taken over at their level / everything else analog / inputs without an internal pull (`CHG_STAT` had a pull-up); SCK and MOSI of both buses stay GPIO LOW until `gl_hal_spi_configure()` has enabled the peripheral that holds them; the MISO pull-downs come from the pin map; the four EXTI vectors, NVIC lines and pin masks are BUILT from the generated `GL_PINS_EXTI_*` (7, 5, 13, 15), with compile-time checks that they agree with the table and are distinct; `gl_hal_usb_supply_ok()` = VBUS_SENSE AND the VDDUSB monitor, whose interrupt and the VBUS_SENSE falling edge both clear the supply-valid bit in the handler; `gl_hal_ship_mode_enter()` = Shutdown with the wake-up pin of VBUS_SENSE, a marker in a backup register, Shutdown pull-downs on the lines without a board pull, LSE and RTC off, and `gl_hal_init()` going straight back when a reset finds the marker without VBUS; Stop 1 instead of Stop 2 while the USB device is in standby; LSE drive medium-low. |
| `gl_hal_stm32u5_usb.c` | CDC-ACM on ST's USB device library: HSI48 + clock recovery, byte rings, flow control by NAK. Rev E, **never compiled**: the supply-valid bit only while `gl_hal_usb_supply_ok()`; the core's VBUS sensing off and the session declared valid by the override bits (its VBUS pad carries a grain LED line); `gl_hal_usb_bus()` (none / suspended / active) and `gl_hal_usb_standby()` for the cradle sleep, which need two calls from the project's `usbd_conf.c` (the file's header says which). |

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
* The EXTI vectors and the ADC channels follow the generated pin table (phase 3): a moved
  interrupt pin is followed by `make pins` alone - the handler names, NVIC lines and pin
  masks are built from `GL_PINS_EXTI_*`. One identifier still names a pad, and the compiler
  guards it: the HAL's name for the ship-mode wake-up pin (`PWR_WAKEUP_PIN2_HIGH_1`, whose
  comment in ST's header reads "PC13 : Wakeup pin 2 (high polarity)").
* The final build of phase 3, `make cross-hal` with the phase-2 header set (generated block):

<!-- readme-check:begin cross-hal -->
```
   text    data     bss  object
   7662       5    1059  build/cross-hal/gl_hal_stm32u5.o
OK: no double-precision helpers, no double libm calls, no heap, no stdio
```
<!-- readme-check:end cross-hal -->

* Phase 3 (run in this phase with the phase-2 header set): the object is 7634 bytes of text
  after builder 1 and 7662 after builder 2 (`gl_hal_boot_confirm()`, the stub's count cleared
  before a deliberate reset, the compile-time check against `boot/gl_boot.h`),
  needs 84 HAL functions (listed by `make cross-hal`) and `SystemCoreClockUpdate` of the
  system file plus `glh_usb_in_standby` of the USB file (which no target compiles), and
  defines the handlers
  `DCMI_PSSI_IRQHandler`, `EXTI5/7/13/15_IRQHandler`, `GPDMA1_Channel0_IRQHandler`,
  `LPTIM3_IRQHandler`, `PVD_PVM_IRQHandler`, `RTC_IRQHandler`, `SysTick_Handler` - names
  that a link against the start-up file's vector table would confirm or refute. **Not
  confirmed.**
* **What phase 3 could not exercise** (everything it added to this file): the effect of
  `UCPD_DBDIS`; Shutdown, its wake-up pin, what survives it, whether the watchdog runs in
  it, the Shutdown pull-downs; the VDDUSB monitor (its flag, its start-up time, its
  interrupt, whether it wakes the core from Stop); Stop 1 and the USB resume; the LSE drive
  setting; that an SPI pin switched to its alternate function after `HAL_SPI_Init` does not
  glitch. `gl_hal_stm32u5_usb.c` (bus state, standby, session override) is not even
  compiled.

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
   the device header states them). The firmware's static data is 0.33 MB (`gl_app_t` is 322984
   bytes; the generated table is under "Memory"): it does NOT fit SRAM1 + SRAM2, so `.bss` must reach into SRAM3 (the three
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
  sensors free-run (43 / 33 / 57 ms with a 9 ms phase offset in the first group of the test, 42 / 34 / 57 in the
  second; an earlier version of this line had 42 / 33 / 58); the frame-end time of every strip
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

  **Three display states (phase 3, DESIGN_SPEC E33).** A result is NORMAL (solid line and
  the confidence bar), APPROX (dashed line, the word `APPROX` in place of the bar, the reason
  as the message) or NONE (the message in large letters, no line, no break, no bar). The
  rule, what each state looks like and the proof are in "Phase 3, builder 3". The table that
  stood here listed which abnormal results "look normal but for the message": the secant
  plane, a kept near miss, `PACE LIMIT`, `FIT NOT DONE`, `POOR HORIZON` and a dialled
  distance with `NO RANGE` did, with a solid line. None of them does any more: they are
  APPROX. A best-effort aim and the straight fallback, which were drawn dashed, are not drawn
  at all. What still differs from a clean result by a word or a mark only, on purpose: a
  hidden base of the flagstick (`PLAYS n?`), a read by the left camera only (`1 CAMERA`), a
  second line in view (`2 LINES SEEN`) - weaker measurements, not fallbacks (open issue 8).
  With no flagstick and nothing dialled there is no result: the UI shows the distance item
  of the dial under `NO FLAG`, with `OR PLACE AGAIN`. If the estimator refuses (`GL_ERR_PARAM`,
  `GL_ERR_RANGE`): the error screen.

  The one message is the most serious condition, in the order of the rule: `NO SOLUTION`,
  `TOO STEEP` / `NOT SOLVED` (no solution), `NO FLAG`, `NO RANGE`, `TOO STEEP`, `PACE LIMIT`,
  `FIT NOT DONE`, `POOR HORIZON` (approximate), `1 CAMERA`, `2 LINES SEEN` (normal). A line
  more than about 13.5 degrees off the visor axis leaves the aperture: its parallel through
  the centre replaces it, in the style of the result's state.

  **Confidence shown** (`shown_confidence_()`): the estimator's confidence, x 0.6 if the
  flagstick was measured by the left camera only, x 0.6 if another line in view also passed as
  a flagstick, x clamp(0.08 px / the read's disparity sigma, 0.5, 1) (the estimator assumes
  0.08 px whatever the read claims), x 0.7 if the fit did not converge; capped at 0.2 for a
  best-effort aim and at 0.09 for a flag-out result; 0 for the straight fallback. Boxes =
  round(5 x confidence). **Since phase 3 the bar is drawn in the NORMAL state only**; the
  number is still computed and logged for every result. Measured: 0.204 with both cameras against 0.076 with the left one
  only and 5 m dialled; 0.155 against 0.093 with a second flagstick in view; 0.24 with the
  flagstick at 4.5 m against 0.09 (no box) with the flag out and 4.5 m dialled. **What the
  bar does not do** (review, open issue 21): the estimator's confidence is essentially the
  chance of holing, so a CLEAN read shows 5 boxes at 1.5 m, 3 at 3 m, 1 at 4.5 and 6 m and
  none at 9 and 12 m (table under "Putt on the display") - the same 0 or 1 box as most
  fallbacks at those distances. Beyond about 4 m the bar does not separate a weak result
  from a clean one; only the message and the line style do.
* **Survey** (phase 3, DESIGN_SPEC E29). Each placement is stored as its own
  `gl_measurements_t`. **The placement the marker stands on is the ball**: the newest
  placement defines the putt, and every result of a Survey has its line. The estimator takes
  the ball's record wherever it is in the array (tested); the application hands over the
  stored placements that are not behind the ball and the ball's last (`survey_select_()`:
  the estimator has no station for a placement farther from the hole than the ball). Two to
  four placements; a fifth is a new plain read. Details, the flow table and the runs: "Phase
  3, builder 3". (Until phase 3 the ball was the placement farthest from the flagstick, and at
  any other placement the screen said `PUT AT BALL` without a line.)
* **Recall** (phase 3, DESIGN_SPEC E30). A tap on a sleeping marker that has not been lifted
  since its last result shows that result again with its age; the application keeps the
  composed view, watches the gyro and the gravity direction while the result is shown and
  after the wake-up, and tells the UI (`GL_EV_LIFTED`) when the result is no longer true.
* **INFO** (phase 3). The last dial item: model, `PRACTICE DEVICE`, versions, serial number,
  and the pages of the regulatory text (`app/gl_regulatory.h`, a placeholder).
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
  supervision** (rev E; rules in `drivers/power.h`, state table under "Charger and cell
  temperature (rev E)"): the BQ25101 starts by itself whenever VBUS appears and its own
  thermistor allows it; the firmware measures NTC2 and both die sensors at once on the VBUS
  edge (also when that edge is what woke it, and at boot in the cradle), then every 5 s while
  VBUS is present, awake or asleep in the cradle (a timed wake-up; one measurement is 1.1 ms
  of simulated bus and conversion time, `NTC_BIAS` driven for 0.68 ms of it), and drives
  `CHG_INHIBIT` HIGH when its gate says stop. It then looks at what the charger does: a
  charge that ended by itself (`DONE`), and a charger that does not do what the firmware
  expects for 30 s (`NOT_CHARGING`: input too low, its timer, NTC1 shorted, the part dead;
  `STOP_FAILED`: charging although the firmware holds the stop), are shown on the cradle
  screens and logged. **The LEVEL of VBUS decides, not its edge** (phase-2 review): every loop
  pass compares the pin with the level the firmware last acted on (`vbus_acted`), and so does
  the last step before every sleep, which is abandoned if they differ; phase 3 adds a last
  check there that releases a stop when VBUS has gone meanwhile (the bounce stress found one
  sleep entered with the pin high and VBUS gone). An edge whose interrupt latch is lost is
  acted on at the next wake-up of any kind, at the latest the 16 s housekeeping wake-up:
  asleep and put into a cradle at 50 C with the edge lost, the charger ran for 15.5 s at
  worst before the firmware stopped it (in the model it runs in its WARM zone there); lifted
  out with the falling edge lost, the marker is asleep a second later. A cell temperature
  older than 12 s counts as unknown and stops the charge, also when it is the supervision
  itself that stalled (the stop pulls the charger's status line, that edge starts a fresh
  measurement, and the charge goes on from it). `CHG_INHIBIT` is released when VBUS goes,
  before every sleep without VBUS and before ship mode. The cradle screens say `TOO COLD`,
  `TOO HOT`, `TEMP SENSOR`, `TIME LIMIT`, `CHARGE OFF` (by command), `NOT CHARGING` or
  `CHARGER WAITS` (the charger's own window holds it) when no charge runs, and `FULL` when
  it has ended. The jump to the ROM bootloader is refused unless VBUS is present and the gate
  is satisfied at that moment; before the jump the IMU is powered down (its two interrupt
  lines are the loader's SPI inputs on the rev E board). **The cradle (E32), ship mode and
  the read's temperature gate (E13)** are described with their figures under "Cradle, ship
  mode and the hot cell". **IMU supervision:** a bus error or a stall (no sample for 100 ms) starts a
  recovery (re-probe, re-configure) with a back-off of 1..64 s; a lost data-ready latch is
  bridged by polling after 10 ms; after 8 failed recoveries in a row (and no USB session) the
  watchdog is deliberately left to expire. **Storage mode:** below `GL_PROV_BATT_STORAGE_MV` (3250 mV) the IMU is switched
  off and the device only wakes for the watchdog and for VBUS. Wake-up interrupts of the IMU are ignored for 300 ms after the device went to
  sleep, in case the sensor's slope detector trips on its own mode change (behaviour unknown;
  without the hold-off a spurious wake would repeat for ever).

## Measured results (host, synthetic data)

These are copied from `make test`; re-run it to reproduce them.

### The output of the end-to-end tests in the final build of phase 3

Generated blocks: everything `tests/test_e2e.c`, `test_e2e_faults.c`, `test_e2e_power.c` and
`test_e2e_review.c` print in `make test`. **These are the figures of the final build.** The
tables and sentences of the sections that follow were typed by the builders of the phase
they describe, from that phase's run. Since then the frames of many reads fall at other
moments (the cell temperature is measured before the cameras start; the replay records are
written before a result is posted), which moves measured values in their last digits and
adds 0.02 s to "rest to result" and to the capture state. Where a typed figure and a block
differ, the block is the run; the differences that were found when this section was added
have been corrected in place, and `python3 tools/readme_check.py --audit` lists numbers of
this file that occur in no log.

`tests/test_e2e.c`:

<!-- readme-check:begin out-e2e -->
```
    states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s READ_TILT@2.37s CAPTURE@3.45s SHOW_RESULT@5.99s
    marker at rest at 1.60 s; result on the screen at 6.05 s (4.45 s after coming to rest); camera part 2.60 s
    camera rail: on once for 2424 ms; 87 SCCB writes, 33 captures; independent replay of 19266 trace records: 0 pin-rule violations, 0 bus accesses with the rail off
    tilt: slope (1.202, -1.997) %, true (1.200, -2.000) %
    stereo: disparity 2.2036 px (true 2.1985, claimed sigma 0.0532) with the stick swaying +-0.3 px at 1.5 Hz and a 9 ms sensor phase offset
    range 5.972 m +- 0.136 (true 5.984; stereo 5.970, by angular height 5.987), bearing 48.48 mrad (true from the left camera 48.46)
    estimate: aim -78.90 mrad from the line to the hole (-4.37 cups), launch 2.277 m/s, distance 5.970 m, hole -122.3 mm above the ball, confidence 0.16; 6 trial rolls, 1267 RK4 steps, 2 fit iterations
    LCD: 6 frames, 258 lines written in 5027 ms of display-on time
    result shown: MCU in Stop mode 99.5 % of the time (IMU at 240 Hz)
  [ ok ] test_complete_quick_read
    Quick Read, flagstick at 6 m (60.4 million instructions by the cost table); clock 160 MHz during the read unless stated:
    computation                          |   rest->  capture     rail | compute   band strips  solve render |   charge  cameras      MCU |    cycle
                                         | result s  state s     on s |      ms     ms     ms     ms     ms |      mAs      mAs      mAs |      mAs
    computation for nothing (phase 1)    |     3.47     1.60     1.56 |       0      0      0    0.0    0.0 |    143.5    133.9      6.4 |    177.4
    low: 1.5 cycles per instruction      |     4.15     2.25     2.16 |     598    134    428    4.6   31.4 |    201.4    185.5     12.2 |    235.2
    nominal: 2.0                         |     4.45     2.54     2.42 |     797    178    571    6.1   41.9 |    226.7    208.4     14.3 |    260.5
    high: 3.0                            |     4.84     2.91     2.76 |    1196    268    857    9.1   62.9 |    259.3    237.1     18.0 |    293.1
    nominal, PLL does not lock (48 MHz)  |     6.03     4.10     3.82 |    2567    595   1903   20.2   48.8 |    342.9    328.8      9.0 |    376.7
    (charge: from the wake-up to the result on the screen; cycle: plus the 45 s the result is shown and falling asleep.  Supply model of the simulator: PROVISIONAL currents, see gl_sim.h)
    asleep afterwards: 23.7 uA mean (model)
    with a 43 mAh cell (listed, unverified) and nothing else drawing: 658 / 594 / 528 read cycles per charge (low / nominal / high); 10 % of the cell lasts 8 days asleep
  [ ok ] test_quick_read_time_and_charge_with_computation
    stick drifting 6 px/s, disparity error (px) by sensor phase offset:
    phase ms        corrected  uncorrected
    2                 +0.0021      -0.0082
    9                 -0.0011      +0.0469
    16                +0.0041      +0.0098
    24                +0.0029      -0.0396
    31                +0.0034      -0.0814
    worst: 0.0041 px corrected, 0.0814 px uncorrected
  [ ok ] test_lrrl_timing_correction
    DCMI-crop windowing, stick at 3 m, 4.6 deg right: range 2.980 m (true 2.984), bearing -83.79 mrad, top in frame: no, sources 0x1
    lines in the band: 1, captures 33, camera rail on 2.43 s
  [ ok ] test_quick_read_with_dcmi_crop_windowing
    raw log level FIRST: 48 + 48 chunks of 960 pixels, read took 7.05 s (4.43 s without logging)
    raw log level ALL: 1600 chunks (64 of the band), 1601.3 kB of flash, read took 48.1 s, camera rail on 40.8 s
  [ ok ] test_raw_strip_logging
    states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s READ_TILT@2.37s CAPTURE@3.45s SETTINGS_DIAL@3.79s
    no stick: camera rail on for 335 ms (band only), 32 horizon samples kept
    dialled 4.5 m, no flag: aim -82.0 mrad from the visor axis, confidence 0.21
  [ ok ] test_no_flagstick_falls_back
    states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s READ_TILT@2.37s CAPTURE@3.45s WAIT_STILL@4.09s READ_TILT@4.90s CAPTURE@5.98s SHOW_RESULT@8.52s
  [ ok ] test_bump_during_capture_aborts_and_rereads
    single read: slope (1.602, -2.298) % with a device bias of (0.4, -0.3) %; true (1.200, -2.000) %
    states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s READ_TILT@2.37s CAPTURE@3.45s SHOW_RESULT@5.99s PRECISION_WAIT_SPIN@6.05s READ_TILT@8.60s SHOW_RESULT@9.68s
    spin measured 176.11 deg (true 176.00); combined slope (1.206, -1.997) %, true (1.200, -2.000) %
  [ ok ] test_precision_read_spin_and_reread
    states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s READ_TILT@2.37s CAPTURE@3.45s SHOW_RESULT@5.99s PRECISION_WAIT_SPIN@6.05s SURVEY_NEXT_DROP@6.15s READ_TILT@9.00s CAPTURE@10.08s SHOW_RESULT@12.64s
    NOT MET: the base of the stick at the ball (3 m) was classed AT THE HORIZON in this run (it ends 1.24 rows below the horizon, the margin is 1.5: the class flips with the frame noise)
    result at the second placement (3 m; the first, 6 m, lies behind it and is not used): patch a -0.0151 b 0.0037 c -0.00038 d 0.00000, aim 21.7 mrad, status 0, aim source 0
  [ ok ] test_survey_second_drop
    states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s CAL_ZERO@1.83s WAIT_STILL@8.62s
    zeroing on a table sloped (0.6, -1.1) %, turn of -171 deg: stored bias (3.487, -2.519) mrad, true (3.500, -2.500)
  [ ok ] test_zeroing_on_a_table_top
    cradle at 47 C: the charger ran for 4.26 s before the firmware stopped it (supervision period 5 s)
  [ ok ] test_cradle_usb_charging_and_dfu
    states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s READ_TILT@2.37s ERROR@3.45s
  [ ok ] test_missing_devices_are_reported_not_fatal
    states: SLEEP@0.00s WAKE@1.02s LOW_BATT@1.03s SLEEP@5.04s
  [ ok ] test_low_and_critical_battery
  [ ok ] test_spurious_wake_right_after_sleep_is_ignored
tests/test_e2e.c: 14 tests, 3103 checks, 0 failed checks -> PASS
```
<!-- readme-check:end out-e2e -->

`tests/test_e2e_faults.c`:

<!-- readme-check:begin out-e2e-faults -->
```
    one SPI error earlier, cell at 60 C on the cradle for 5 min: the charger ran for 1.2 ms before the firmware stopped it; NTC 60.0 C, IMU 60.0 C (valid 0), charging: no
  [ ok ] test_charge_gate_after_an_imu_bus_error
    IMU silent in the cradle at a true 60 C: imu_ok=0 temp_valid=0 NTC 60.0 C, charging: no (6), error shown: NOT_FOUND
  [ ok ] test_charge_gate_with_a_silent_imu
    in the cradle: 12 NTC conversions in 60 s, NTC_BIAS driven for 10.3 ms of them
    NTC 22.0 C, IMU 22.0 C, MCU die 50.0 C: charging: YES
    NTC 22.0 C, IMU 50.0 C, MCU die 50.0 C: charging: no (implausible)
    gate reasons logged: 0 4 0 6 0 6 5 0 3 0 3 0 3 0
    14 charge events in the log (2 too hot, 3 NTC fault)
  [ ok ] test_charge_gate_ntc_faults_and_plausibility
    MODEL, MCU in reset in the cradle: -5 C COLD, 22 C charging, -5 C COLD again - the charger's own thermistor, no firmware
    boot in the cradle at -5 C: CHG_INHIBIT high 88.3 ms after gl_hal_init (the charger ran for 0.0 ms of that: its own window had it off already)
    watchdog reset while inhibited at 50 C: MODEL charger in its WARM zone for 3.0 ms of reset and 1.2 ms of boot, then stopped by the firmware again
    asleep, put into the cradle at 50 C: charger ran for 1.22 ms before the firmware stopped it
    hung firmware, cell at 50 C: MODEL charger went on in its WARM zone (to 4060 mV) for 33 s, until the watchdog period (32 s) was over - NOT MET for the firmware's 45 C limit, inside the charger's own window
    hung firmware, cell at 65 C: MODEL charger stopped by its own thermistor, charged for 0.0 ms of 33 s; time charged outside the charger's 0..60 C window: 0 ms (a statement about the MODEL, not about the chip)
  [ ok ] test_charger_state_table
    MODEL, ROM loader, cell at 50 C: the charger went on for 600 s in its WARM zone (to 4060 mV) - NOT MET for the firmware's 45 C limit, which nothing enforces here
    MODEL, ROM loader, cell at 65 C: charged for 0.0 ms of 600 s (its own thermistor: HOT); at -5 C: COLD, charged for 0.0 ms of 600 s.  Time charged outside the charger's 0..60 C window in the whole test: 0 ms
  [ ok ] test_rom_dfu_and_the_charger
    after one failed SPI2 transfer: imu_ok=1, state SHOW_RESULT, recoveries 1
    15 pick-up / put-down cycles afterwards: woke 15 times
  [ ok ] test_one_imu_bus_error_is_not_permanent
    IMU absent only during gl_app_init(): 6 pick-up cycles afterwards woke the device 6 times
  [ ok ] test_imu_absent_at_boot_only
  [ ok ] test_imu_reset_while_asleep_is_repaired
    IMU dead while asleep: 12 failed recoveries, then the watchdog is left to expire: simulator reports 2 watchdog expiry (a reset on the target)
  [ ok ] test_dead_imu_ends_in_a_watchdog_reset
    20 data-ready latches dropped during a read: longest time without a sample 19 ms, 20 samples fetched by polling, state SHOW_RESULT
  [ ok ] test_a_lost_data_ready_interrupt_does_not_stall
    states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s READ_TILT@2.37s CAPTURE@3.45s SHOW_RESULT@5.99s PRECISION_WAIT_SPIN@6.05s READ_TILT@8.59s PRECISION_WAIT_SPIN@9.00s SHOW_RESULT@29.00s
    turned 176 + 40 = 216 deg: yaw used -143.7 deg, shown as Precision: no, slope error 0.003 % of slope
    states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s READ_TILT@2.37s CAPTURE@3.45s SHOW_RESULT@5.99s PRECISION_WAIT_SPIN@6.05s READ_TILT@8.59s PRECISION_WAIT_SPIN@9.00s READ_TILT@10.08s SHOW_RESULT@11.16s
    turned 170 + 12 = 182 deg: yaw used -177.9 deg, shown as Precision: YES, slope error 0.010 % of slope
  [ ok ] test_precision_reread_with_a_second_turn
    A: lifted out of the cradle: USB stopped in the next main-loop pass (it used to stay started for 47 s)
    B: 10 min in the cradle at 60 C after fault + double tap: state CRADLE_SLEEP, charging allowed: no
  [ ok ] test_fault_and_double_tap_in_the_cradle
  [ ok ] test_vbus_bounce
  [ ok ] test_the_power_rules_of_the_simulator_fire
    SET_CAL with trailing bytes: PARAM, fx in RAM unchanged (657), nothing stored; the exact record: stored and adopted (fx 700)
  [ ok ] test_set_cal_that_fails_changes_nothing
    LOG_ERASE with a calibration event in between, then a reset: 0 'erased' records back, 4 event records (3 after the erase + 1 boot)
  [ ok ] test_log_erase_with_an_event_in_between
    storage mode at 3190 mV: IMU off, motion ignored, MCU in Stop mode 100.00 % of the time
  [ ok ] test_storage_mode_for_a_nearly_empty_cell
    stick drifting 6 px/s, 5 sensor phases; vision run time charged per strip:
    (free: computation for nothing; cost model: the simulator's model at its nominal factor, drift not reversing;
     model, turn: the same with the drift reversing inside a group - NOT MET)
    per strip   worst |err| corrected   worst |err| uncorrected   capture       camera rail on
    free        0.0071                  0.0812                     1.50 s       1.56 s
    cost model  0.0041                  0.0814                     2.45 s       2.42 s
     30 ms      0.0054                  -                          2.80 s       2.72 s
     60 ms      0.0047                  -                          4.09 s       3.89 s
    100 ms      0.0062                  0.0221                     5.51 s       5.16 s
    200 ms      0.0106                  -                          9.51 s       8.76 s
    300 ms      0.0062                  -                         13.51 s       12.36 s
    model, turn 0.0387                  0.0671                     2.45 s       2.42 s
  [ ok ] test_lrrl_timing_with_vision_run_time
tests/test_e2e_faults.c: 18 tests, 1992 checks, 0 failed checks -> PASS
```
<!-- readme-check:end out-e2e-faults -->

`tests/test_e2e_power.c`:

<!-- readme-check:begin out-e2e-power -->
```
    states: SLEEP@0.00s WAKE@1.02s TOO_HOT@1.04s
    cell at 61.5 C: TOO HOT 58 ms after the wake-up (the cell is measured when the marker wakes, before the tilt read), no camera powered; asleep 3.98 s later
  [ ok ] test_no_camera_read_from_a_hot_cell
    states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s READ_TILT@10.78s TOO_HOT@11.85s
    (a) cell at 63 C when the tilt read ended, last reading 22 C from the wake-up 10.9 s before: measured again at the camera start (1 conversion, NTC_BIAS driven 0.68 ms), read refused
    (b) the same jump during the tilt read of a marker put straight down: NOT seen, the read ran on the wake-up reading of 22.0 C (the gate accepts a reading up to 5 s old)
  [ ok ] test_read_gate_measures_before_the_cameras
    ship mode, supply model at 3.9 V: 12.93 uA at the cell = MCU in Shutdown 0.20 + IMU powered down 3.0 + flash 0.1 + the board's always-on parts 9.62 (regulator 1.6, battery divider 1.95, protection circuit 3.0, charger leakage 0.075, camera regulator off 0.2, USB regulator's enable pin 2.8)
    NOT MET: the requirement is 5 uA; the model gives 12.9 uA, of which the firmware controls 3.3 (MCU, IMU, flash).  30 % of the cell (12.9 mAh) lasts 42 days there, not 3 months (every figure PROVISIONAL, nothing measured)
  [ ok ] test_ship_mode_entry_and_wake_on_vbus
  [ ok ] test_ship_mode_disarm_bounce_and_asleep_in_the_cradle
  [ ok ] test_ship_mode_rules_of_the_simulator
    wall charger: awake in the cradle state the marker draws 3.35 mA from the node the charger feeds (termination threshold 1.98 mA): the charge could not end.  Asleep in the cradle, from 30.1 s after docking: 98.6 uA (Stop mode 99.98 % of the time, cell measured every 5 s)
    ... and the charge terminated by itself 0.31 h after docking at 99.7 % (from 90 %; the cell is a guess); symbol FULL; the firmware's 6 h backstop was not needed
  [ ok ] test_cradle_sleep_on_a_wall_charger_lets_the_charge_end
    a host that keeps talking (the marker awake, as it always was before phase 3): mean draw 3.35 mA; after 3 h the cell is at 100.0 % and the charger still delivers 3.34 mA (threshold 1.98 mA): no termination, the symbol says CHARGING
    ... stopped by the firmware 6.000 h after docking (CHG_INHIBIT high, reason TIME LIMIT)
    ... and released 2.62 h later, when the awake marker had run the cell down to 4031 mV (80.0 %): charging again
  [ ok ] test_awake_in_the_cradle_the_charge_never_ends_until_the_backstop
    VARIANT of the model (CHG low in the first cycle only): first cycle ended asleep in the cradle; awake under a talking host the recharge started 1.17 h later at 4136 mV with CHG released - the firmware says FULL (status DONE) while 19.8 mA flow
    ... NOT MET for this variant: 7.0 h later the charger still delivers 5.21 mA (cell at 100.0 %), the 6 h backstop has counted 0 ms: it only counts while CHG is low
  [ ok ] test_charger_whose_status_shows_the_first_cycle_only
    host suspended: asleep in the cradle with USB in standby, 179.4 uA (the MCU in Stop 1 there, GL_PROV_USB_WAKE_FROM_STOP2 = 0: 70 uA + 20 uA for the USB core, both from memory / guessed); threshold 1982 uA
    host resumed the bus: back in the cradle state 21 ms later
    host silent on a running bus: detached and asleep after 30 s; a command sent then is NOT answered (the marker is off the bus) - NOT MET: reachable again only by re-docking
  [ ok ] test_cradle_sleep_under_a_host_standby_resume_and_silence
    asleep in the cradle, cell to 50 C: the charger ran 4.80 s in its WARM zone before the firmware stopped it
  [ ok ] test_cradle_sleep_supervises_the_charge
    asleep out of the cradle, supply model at 3.8 V, underside DARK: 23.68 uA at the cell
      MCU in Stop 2 9.0, IMU in wake-on-motion 5.0, flash in deep power-down 0.1,
      2.8 V regulator 1.6, battery divider 1.90, cell protection circuit 3.0, charger leakage 0.075,
      camera regulator (off) 0.2, USB regulator's enable pin 2.8 (E26, NOT CONFIRMED), housekeeping 0.01;
      both thermistors 0 (NTC1 is biased by the charger from VBUS only; NTC_BIAS analog but for 3.42 ms in the hour), wake pull-up 150 kohm 0 in the dark
    underside LIT: 28.88 uA at the cell (+5.20 through the 150 kohm wake pull-up)
    E14 limit 25 uA, measured through the cell-lead pads (the protection circuit is not in that path): model 20.68 uA dark -> MET (model); 25.88 uA lit -> NOT MET (E27: the limit is for a dark underside).  Every figure PROVISIONAL, nothing measured
    standby from a full cell (43 mAh) at 23.7 uA: 76 days to empty; from 30 %: 23 days (ship mode exists for that)
  [ ok ] test_sleep_current_dark_and_lit_against_25_microamps
tests/test_e2e_power.c: 11 tests, 412 checks, 0 failed checks -> PASS
```
<!-- readme-check:end out-e2e-power -->

`tests/test_e2e_review.c`:

<!-- readme-check:begin out-e2e-review -->
```
    Quick Read                               SHOW_RESULT        [6.0M | PLAYS 6.0M? | - | 2.0% | <6.1 CUP | 1/5 ] phi +109.26 mrad, aim +139.49 mrad, slope used (-0.0200, -0.0006)
    Precision Read (spun 180 degrees)        SHOW_RESULT        [6.0M | PLAYS 6.0M? | - | 2.0% | <6.1 CUP | 1/5 2X] phi +109.37 mrad, aim -3003.41 mrad, slope used (-0.0200, -0.0006)
    second tap-tap on the "2X" result: state SURVEY_NEXT_DROP, drops stored 1
    after the 2nd tap-tap and the turn back  SHOW_RESULT        [6.0M | PLAYS 6.0M? | - | 2.0% | <6.1 CUP | 1/5 D2] phi +109.23 mrad, aim +139.47 mrad, slope used (-0.0200, -0.0007)
  [ ok ] test_double_tap_after_precision_starts_a_survey
    Precision result on a marker turned by -179.9 degrees: 0 of 16384 panel pixels differ from the upright picture turned round (1000 black pixels in it)
  [ ok ] test_precision_result_is_upright_for_the_golfer
    no flagstick seen, nothing dialled: at 7.0 s the UI is in SETTINGS_DIAL (distance prompt 1)
    picked up at 8.0 s, down again at 9.5 s: at 14.0 s the UI is in SHOW_RESULT, camera rail cycles 2
    the second read                          SHOW_RESULT        [6.0M | PLAYS 6.0M? | - | 1.5% | <4.6 CUP | 1/5 ] phi +81.98 mrad, aim +132.36 mrad, slope used (-0.0150, -0.0009)
  [ ok ] test_distance_prompt_re_placing_reads_again
    flag out, 4.5 m dialled                  SHOW_RESULT        [4.5M? | PLAYS 4.5M | NO FLAG | 1.5% | <3.3 CUP | 0/5 ] phi +78.35 mrad, aim +78.35 mrad, slope used (-0.0150, +0.0000)
    the flag-out line: 0.05 of the dash-gap pixels are inked (solid > 0.45, dashed < 0.15); confidence 0.090 -> 0 of 5 boxes
    asleep at 64.8 s: DIST setting 0 cm (stored copy 0 cm)
    next placement, flagstick not seen: the UI is in SETTINGS_DIAL (distance prompt 1)
    flag in, 4.5 m left in DIST              SHOW_RESULT        [6.0M | PLAYS 6.0M? | - | 1.5% | <4.5 CUP | 1/5 ] phi +81.52 mrad, aim +131.90 mrad, slope used (-0.0150, -0.0007)
  [ ok ] test_dialled_distance_belongs_to_one_hole
    6 m, dead flat, PAST 30 cm: shown [6.0M | PLAYS 6.0M?], estimator roll-out 6.283 m
    6 m, dead flat, PAST 90 cm: shown [6.0M | PLAYS 6.0M?], estimator roll-out 6.883 m
    6 m, dead flat, PAST  0 cm: shown [6.0M | PLAYS 6.0M?], estimator roll-out 5.983 m
    5 m, 2 % uphill, PAST 30 cm: shown [5.0M | PLAYS 6.3M?]
  [ ok ] test_plays_like_is_the_flat_putt
    spin abandoned at a quarter turn         SHOW_RESULT        [6.0M | PLAYS 6.0M? | - | 2.0% | <6.1 CUP | 1/5 ] phi +109.26 mrad, aim -1435.37 mrad, slope used (-0.0200, -0.0006)
    the half turn completed                  SHOW_RESULT        [6.0M | PLAYS 6.0M? | - | 2.0% | <6.1 CUP | 1/5 2X] phi +109.50 mrad, aim -3007.54 mrad, slope used (-0.0200, -0.0006)
  [ ok ] test_spin_abandoned_then_completed
    3 m, rises LEFT 2 %, visor 9 deg right of the hole SHOW_RESULT        [3.0M | PLAYS 2.9M | - | 2.0% | <2.8 CUP | 3/5 ] phi +99.33 mrad, aim +258.76 mrad, slope used (-0.0197, -0.0031)
    aim +258.8 mrad (14.8 degrees LEFT): 0.72 of the core of a solid parallel through the screen centre is inked (labels cover the rest); black pixels where the arrow to the RIGHT used to be: 0
  [ ok ] test_solved_aim_off_the_screen_keeps_its_style
    GRAIN OFF (default)    solver use_grain 0, grain used |kappa| 0.0000, phi +109.259 mrad, grain ADC conversions 0
    GRAIN ON, bentgrass    solver use_grain 1, grain used |kappa| 0.0100, phi +114.203 mrad, grain ADC conversions 192
    GRAIN ON, bermuda      solver use_grain 1, grain used |kappa| 0.0600, phi +136.608 mrad, grain ADC conversions 192
  [ ok ] test_grain_setting_reaches_the_solver
    three switches back to the slow clock fail during a Quick Read: clock_fails 3, core clock now SLOW, simulator 'clock' violations (Stop mode with the fast clock) 0, switches up / down 1 / 1
  [ ok ] test_failed_switch_to_the_slow_clock_is_not_believed
    21 Quick Reads of a flagstick 2.25 to 3.75 m away (2.6 to 4.4 px wide): 13 band shoulders dropped; every read took 33 captures; camera rail on 2.42 to 2.46 s, result at most 4.40 s after the marker came to rest (the review measured 3.02 to 3.12 s and 4.94 to 5.07 s on the reads with a shoulder)
  [ ok ] test_near_stick_is_one_candidate
    asleep, into a cradle at 50 C   0.5 s after a housekeeping wake-up, the VBUS edge latch lost: charger ran  15.50 s of 600 s outside 0..45 C; then UI CRADLE_SLEEP, awake 0, CHG_INHIBIT HIGH (stop), charger stopped
    asleep, into a cradle at 50 C   4.5 s after a housekeeping wake-up, the VBUS edge latch lost: charger ran  11.50 s of 600 s outside 0..45 C; then UI CRADLE_SLEEP, awake 0, CHG_INHIBIT HIGH (stop), charger stopped
    asleep, into a cradle at 50 C   8.5 s after a housekeeping wake-up, the VBUS edge latch lost: charger ran   7.50 s of 600 s outside 0..45 C; then UI CRADLE_SLEEP, awake 0, CHG_INHIBIT HIGH (stop), charger stopped
    asleep, into a cradle at 50 C  12.5 s after a housekeeping wake-up, the VBUS edge latch lost: charger ran   3.50 s of 600 s outside 0..45 C; then UI CRADLE_SLEEP, awake 0, CHG_INHIBIT HIGH (stop), charger stopped
    worst of the four: 15.50 s (bound: the 16 s housekeeping period)
  [ ok ] test_vbus_rising_edge_lost_while_asleep
    lifted out of the cradle, the VBUS edge latch lost: one second later the UI is in SLEEP, awake 0, usb_on 0, power.vbus 0
    the hour after: Stop mode 3600.0 s, idle sleep 0.0 s, 0.0237 mAh from the cell (supply model, all currents provisional)
  [ ok ] test_vbus_falling_edge_lost_in_the_cradle
    supervision stalled in the cradle at 22 C: the charger was stopped; last cell reading 12.0 s old then; reason 2
    ... with the status edge alive: 3 fresh measurements in 40 s although the supervision never came round; oldest reading behind a running charge 12.00 s (limit 12 s)
  [ ok ] test_stalled_supervision_stops_the_charge
    300 random scenarios, 4857 VBUS edges, 105 MCU resets, 55 reads completed: 0 scenarios with a simulator rule violation (0 violations), 0 with an inconsistent end state, 0 left with the fast clock; longest charging outside 0..45 C: 4.96 s
  [ ok ] test_vbus_bounce_stress
tests/test_e2e_review.c: 14 tests, 366 checks, 0 failed checks -> PASS
```
<!-- readme-check:end out-e2e-review -->

### End to end (`tests/test_e2e.c`, the whole firmware on the simulator)

Scene: green sloped (1.2, -2.0) %, flagstick 6.0 m away and 2.9 degrees to the left, 15 mm
wide (1.6 px), SNR 20, swaying +-0.3 px at 1.5 Hz; sensors 9 ms out of phase; marker put down
between t = 1.0 and 1.6 s. **Computation is charged its time at the nominal factor** (2.0
cycles per host instruction, 160 MHz during the read); the low and the high case follow.

| Quantity | Result |
|---|---|
| State sequence | SLEEP, WAKE (1.02 s), WAIT_STILL (1.82 s), READ_TILT (2.37 s), CAPTURE (3.45 s), SOLVE, SHOW_RESULT (5.99 s; on the screen at 6.05 s) |
| Result on the screen | **4.45 s after the marker came to rest** (0.77 s until stillness is established, 1.08 s tilt read, 2.60 s camera part including power-up, settling and 0.80 s of computation; 4.43 s and 2.58 s until builder 2 of phase 3, whose replay records are written before the result is posted). DESIGN_SPEC said "about three seconds" when this test was written; its amendment E15 now restates the figure from this model (4.1 to 4.8 s). NOT MET: the 4.0 s bound this test had while computation was free (3.45 s then) |
| Camera rail | on once, for 2424 ms (1557 ms with computation for nothing); 33 captures, 87 SCCB writes; rail never on outside the CAPTURE state |
| Camera rail rule | simulator: 0 violations; independent replay of the 19266 trace records: 0 pin-rule violations, 0 bus accesses with the rail off |
| Slope | (1.202, -1.997) % against (1.200, -2.000) % |
| Disparity | 2.2036 px against 2.1985 px true; claimed sigma 0.053 px, of which 0.05 px is the (unmeasured) stereo calibration term |
| Range | 5.972 m +- 0.136 m against 5.984 m (stereo 5.970, angular height 5.987 with the prior stick height) |
| Bearing | 48.48 mrad against 48.46 mrad |
| Putt estimate (method B1, single precision) | aim 78.9 mrad right of the line to the hole (-4.37 cups), launch speed 2.277 m/s, distance 5.970 m, hole 122 mm below the ball, confidence 0.16; aim source 0, status OK; 6 trial rolls, 1267 RK4 steps, 2 fit iterations |
| Screen | panel memory identical to the framebuffer; the aim line (bearing from the ball + aim angle) passes through the predicted pixels |
| While the result is shown | MCU in Stop 2 for 99.5 % of the time (IMU at 240 Hz) |
| After 45 s | display off, IMU wake-on-motion, flash in deep power-down, Stop 2; at most 6 loop iterations in the next 60 s (watchdog refresh every 16 s) |
| Log | one boot event, one read record (range = the estimator's distance, solve status, launch speed, aim offset) and its estimate event (aim source, status, flags, method, tier, rolls), decoded and compared with the result; since builder 2 of phase 3 also the placement and the replay record ("Field log") |

The lines of this test in the final build of phase 3, and the table of the next test
(generated block; the typed tables above and below it were made from earlier runs and are
corrected where they differed):

<!-- readme-check:begin quick-read -->
```
states: SLEEP@0.00s WAKE@1.02s WAIT_STILL@1.82s READ_TILT@2.37s CAPTURE@3.45s SHOW_RESULT@5.99s
marker at rest at 1.60 s; result on the screen at 6.05 s (4.45 s after coming to rest); camera part 2.60 s
camera rail: on once for 2424 ms; 87 SCCB writes, 33 captures; independent replay of 19266 trace records: 0 pin-rule violations, 0 bus accesses with the rail off
tilt: slope (1.202, -1.997) %, true (1.200, -2.000) %
stereo: disparity 2.2036 px (true 2.1985, claimed sigma 0.0532) with the stick swaying +-0.3 px at 1.5 Hz and a 9 ms sensor phase offset
range 5.972 m +- 0.136 (true 5.984; stereo 5.970, by angular height 5.987), bearing 48.48 mrad (true from the left camera 48.46)
estimate: aim -78.90 mrad from the line to the hole (-4.37 cups), launch 2.277 m/s, distance 5.970 m, hole -122.3 mm above the ball, confidence 0.16; 6 trial rolls, 1267 RK4 steps, 2 fit iterations
LCD: 6 frames, 258 lines written in 5027 ms of display-on time
result shown: MCU in Stop mode 99.5 % of the time (IMU at 240 Hz)
Quick Read, flagstick at 6 m (60.4 million instructions by the cost table); clock 160 MHz during the read unless stated:
computation                          |   rest->  capture     rail | compute   band strips  solve render |   charge  cameras      MCU |    cycle
                                     | result s  state s     on s |      ms     ms     ms     ms     ms |      mAs      mAs      mAs |      mAs
computation for nothing (phase 1)    |     3.47     1.60     1.56 |       0      0      0    0.0    0.0 |    143.5    133.9      6.4 |    177.4
low: 1.5 cycles per instruction      |     4.15     2.25     2.16 |     598    134    428    4.6   31.4 |    201.4    185.5     12.2 |    235.2
nominal: 2.0                         |     4.45     2.54     2.42 |     797    178    571    6.1   41.9 |    226.7    208.4     14.3 |    260.5
high: 3.0                            |     4.84     2.91     2.76 |    1196    268    857    9.1   62.9 |    259.3    237.1     18.0 |    293.1
nominal, PLL does not lock (48 MHz)  |     6.03     4.10     3.82 |    2567    595   1903   20.2   48.8 |    342.9    328.8      9.0 |    376.7
(charge: from the wake-up to the result on the screen; cycle: plus the 45 s the result is shown and falling asleep.  Supply model of the simulator: PROVISIONAL currents, see gl_sim.h)
asleep afterwards: 23.7 uA mean (model)
with a 43 mAh cell (listed, unverified) and nothing else drawing: 658 / 594 / 528 read cycles per charge (low / nominal / high); 10 % of the cell lasts 8 days asleep
```
<!-- readme-check:end quick-read -->

(The measured values differ in the last digits from the ones this table carried before: the
frames are exposed at other moments, so the noise and the sway in them are other samples.)

**Time and charge of this read, with its computation**
(`test_quick_read_time_and_charge_with_computation`; the same scene at four compute factors
and with a PLL that does not lock). Times are measured on the simulator; the factor is an
estimate (see "Run time"); the charge comes from the simulator's supply model, whose currents
are all PROVISIONAL:

The table is in the block above (columns: rest to result, CAPTURE state, camera rail on,
in seconds; computation in all and by band, strips, estimate and rendering, in ms; the charge
from the wake-up to the result, of which cameras and MCU; the charge of a whole cycle). **The
result comes 4.15 s (low factor), 4.45 s (nominal) and 4.84 s (high) after the marker is at rest**,
6.03 s if the PLL does not lock; the camera rail is on for 2.16, 2.42 and 2.76 s. Until builder
2 of phase 3 these were 4.13, 4.43 and 4.82 s - the figures DESIGN_SPEC E15 took its "4.1 to
4.8 s" from; the 0.02 s are the replay records, which are written to the flash before the
result is posted. At the one decimal the specification gives, the high end still reads 4.8 and
the low end now reads 4.2; nothing was changed to win the 0.02 s back (the records could be
written after the screen is drawn: not done).

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
5 uA for the IMU's wake-on-motion mode, 9.6 uA for the always-on parts of the rev E board;
the cell's 43 mAh is the listed figure, unverified; self-discharge, the usable part of the
capacity above the cut-off voltage and the cell's low-temperature behaviour are not
modelled). Run again in phase 3 (`tests/test_e2e.c`, `test_quick_read_time_and_charge_with_computation`):

The figures are in the block above: the charge from the wake-up to the result, the charge
of a whole cycle (the result shown for 45 s, falling asleep) and the last line, read cycles per
43 mAh at the low, nominal and high factor (658 / 594 / 528; they were 659 / 595 / 528 before
the replay records).

The charge of a read, wake-up to result, is 226.7 mAs over about 5 s; with the cameras
on it is about 96 mA (86 for the cameras, 9.5 for the MCU). Asleep, the model now draws
**23.7 uA at the cell** (20.6 before: the rev E board has 3.1 uA more of always-on parts,
"Sleep and the supply model (rev E)"): 0.57 mAh per day, 76 days from a full cell with no
read at all; a round of 40 read cycles is 2.9 mAh at the nominal factor, the equivalent of 5
days asleep. A read with several lines in the band keeps the rail on longer (about 3.4 s
with a person behind the stick, "Run time"): by the same arithmetic about 0.09 mAh per
cycle.

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
| none (computation for nothing) | 0.007 px | 1.50 s | 1.56 s |
| the cost model (about 17 ms, band 178 ms) | 0.004 px | 2.45 s | 2.42 s |
| 30 ms | 0.005 px | 2.80 s | 2.72 s |
| 60 ms | 0.005 px | 4.09 s | 3.89 s |
| 100 ms | 0.006 px | 5.51 s | 5.16 s |
| 200 ms | 0.011 px | 9.51 s | 8.76 s |
| 300 ms | 0.006 px | 13.51 s | 12.36 s |
| **the cost model, the drift REVERSING inside a group: NOT MET** | **0.039 px** | 2.45 s | 2.42 s |

(The capture-state column is 0.02 s longer than this table had it until phase 3: the replay
records are written before the state is left. The camera-rail column is unchanged.)

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
* **Precision Read:** spin measured 176.11 degrees (true 176.00); a device bias of (0.4, -0.3) %
  cancels: combined slope (1.206, -1.997) % against (1.200, -2.000) %; no second camera read;
  the estimator is told `tilt_reads` = 2.
* **Survey** (`test_survey_second_drop`; phase 3, DESIGN_SPEC E29): a second placement 3 m
  further along, both stored with their own range and slope. The marker now lies 3 m from the
  hole and that placement is the ball: the result is the 3 m putt from there, with its line
  (until phase 3: the first placement was the ball and the screen said `PUT AT BALL`). This
  test walks the old way round on purpose - the first placement lies BEHIND the present ball -
  so the estimator is handed the second placement alone (`solve_drops` 1; "Phase 3, builder
  3" says why). **NOT MET, pinned, unchanged in kind:** the base of the stick 3 m away ends
  1.24 rows below the turf horizon, inside the 1.5-row margin of the class VISIBLE, and the
  class flips with the noise of the frames (VISIBLE in 51 of 80 runs of this scenario with
  the read shifted in time, phase 2). In the final build it is AT THE HORIZON; since E29 that
  decides between `PLAYS n` and `PLAYS n?` for this result, where it used to decide whether
  the Survey fit got a curvature. The Survey walked toward the ball, with every placement
  used, is in `tests/test_e2e_putt.c` ("Putt on the display").
* **Zeroing** on a table sloped (0.6, -1.1) % with a turn of -171 degrees: stored bias
  (3.487, -2.519) mrad against (3.500, -2.500) true, present after a power cycle; a 120 degree
  turn is refused; being put into the cradle abandons it; it cannot be started in the cradle.
* **Cradle:** protocol over the simulated CDC port (ping, info, status, settings, calibration,
  log dump, streams; GET_INFO reports hardware revision 5 = "E"), charging at 22 C, stopped
  by the firmware at 47 C (`CHG_INHIBIT` high; the charger ran for 4.30 s of the 5 s
  supervision period first), released again at 30 C, never Stop mode while the host talks
  (the test's host sends a PING every 10 s; a silent one would send the marker to sleep
  after 30 s), reboot to ROM DFU requested (after `UNLOCK`) and refused while the cell is too
  hot, asleep after removal with `CHG_INHIBIT` released (analog).
* **Missing IMU / missing camera:** shown as an error, not fatal; rail off.
* **Battery:** at 3.45 V (low) the read runs; at 3.30 V (critical) the warning is shown and the
  device sleeps without ever powering the cameras; in the cradle it charges.
* **Spurious wake-up interrupt 50 ms after going to sleep:** ignored; a later one wakes.

Fault scenarios (`tests/test_e2e_faults.c`, 18 tests; the IMU, Precision, USB, calibration and
storage ones each reproduce a review finding and failed before its fix; the charger ones were
rewritten for rev C2 and again, in phase 3, for the model of the rev E charger):

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
pixels. The table is `make appdiff` of the final build of phase 3, as the tool prints it
(generated block: the Python reference on the records the application handed to the
estimator; "ref true" is the reference on the true scene; the last column is what the screen
shows - distance, plays-like, break, slope, the message, then the confidence boxes of a
NORMAL result or the word `APPROX`, then the Survey or Precision mark):

<!-- readme-check:begin appdiff -->
```
scene                                                        |   ref aim  ref true |  firmware |     drawn |  dr-ref | shown (distance, plays-like, break, slope, note, boxes)
                                                             |    [mrad]    [mrad] |    [mrad] |    [mrad] |  [mrad] |
Quick 3 m, rises LEFT 2 %, level                             |   +129.22   +127.58 |   +129.28 |   +129.08 |   -0.13 | 9.8FT, PLAYS 9.7FT, <2.7 CUP, 2.0%, 3/5
Quick 3 m, rises RIGHT 2 %, uphill 1.5 %                     |   -103.47   -102.27 |   -103.46 |   -102.97 |   +0.50 | 9.8FT, PLAYS 11.6FT, 2.3 CUP>, 2.5%, 3/5
Quick 6 m, rises RIGHT 1.2 %, downhill 2 %                   |    -28.65    -28.71 |    -28.66 |    -27.97 |   +0.68 | 19.6FT, PLAYS 14.5FT?, 4.4 CUP>, 2.3%, 1/5
Quick 6 m, rises LEFT 1 %, uphill 1.5 %                      |     +8.43     +8.56 |     +8.43 |     +8.37 |   -0.06 | 19.6FT, PLAYS 23.3FT?, <2.7 CUP, 1.8%, 1/5
Quick 9 m, rises LEFT 0.8 %, downhill 1 %                    |    +72.74    +72.80 |    +72.74 |    +72.95 |   +0.20 | 29.5FT, PLAYS 25.8FT?, <4.4 CUP, 1.3%, 0/5
Quick 1.5 m, rises RIGHT 1.5 %, uphill 0.5 %                 |    -59.73    -58.56 |    -59.69 |    -59.33 |   +0.40 | 4.9FT, PLAYS 5.1FT, 0.8 CUP>, 1.6%, 5/5
Quick 12 m, rises RIGHT 0.6 %, uphill 1 %                    |    -59.40    -59.33 |    -59.40 |    -59.07 |   +0.34 | 39.8FT, PLAYS 44.9FT?, 3.3 CUP>, 1.2%, 0/5
Quick 4.5 m, level green                                     |    +10.02    +10.10 |    +10.02 |     +9.52 |   -0.51 | 14.7FT, PLAYS 14.7FT?, STRAIGHT, 0.0%, 1/5
Precision 6 m, rises LEFT 1.2 %, uphill 1.6 %, spun 176 deg  |   +103.02   +101.00 |   +103.02 |   +102.98 |   -0.04 | 19.6FT, PLAYS 23.0FT?, <2.9 CUP, 2.0%, 1/5, 2X
Survey 2: 3 m short of the hole, then the ball at 6 m        |    +54.13    +54.03 |    +54.12 |    +53.90 |   -0.23 | 19.6FT, PLAYS 14.6FT?, <1.3 CUP, 2.2%, 1/5, D2
Survey, old order: 6 m, then 3 m (the putt from 3 m, alone)  |     +1.41     +1.25 |     +1.42 |     +2.33 |   +0.92 | 9.8FT, PLAYS 7.8FT?, <0.6 CUP, 1.6%, 2/5, D2
Survey 3: 6 m, 3 m, 6 m again                                |    +39.73    +39.64 |    +39.74 |    +39.49 |   -0.24 | 19.6FT, PLAYS 14.4FT?, <0.5 CUP, 2.3%, 1/5, D3
Survey, E29 order, placement 1 (2 m): a Quick Read           |    +62.04         - |    +62.05 |    +61.07 |   -0.98 | 6.5FT, PLAYS 8.1FT, <0.2 CUP, 2.0%, 4/5
Survey, E29 order, placement 2 (6 m)                         |    +20.89    +20.90 |    +20.89 |    +20.89 |   +0.00 | 19.7FT, PLAYS 23.6FT?, <1.2 CUP, 1.8%, 1/5, D2
Survey, E29 order, placement 3: the ball at 9 m              |    +49.51    +49.57 |    +49.51 |    +49.75 |   +0.23 | 29.6FT, PLAYS 34.3FT?, <2.5 CUP, 1.6%, 1/5, D3
Survey 4: 2 m, 6 m, 9 m, 9 m again                           |    +19.47    +19.63 |    +19.47 |    +19.76 |   +0.28 | 29.4FT, PLAYS 34.1FT?, <2.4 CUP, 1.6%, 1/5, D4
after a Survey of 4: the fifth placement is a plain read     |    +48.75         - |    +48.75 |    +49.42 |   +0.67 | 29.5FT, PLAYS 34.1FT?, <4.1 CUP, 1.6%, 0/5
Flag out, dialled 4.5 m, rises LEFT 1.5 %, uphill 1 %        |    +70.12    +70.21 |    +70.12 |    +72.71 dashed |   +2.59 | 14.8FT?, PLAYS 16.7FT, <2.9 CUP, 1.8%, NO FLAG, APPROX
Left camera only, 5 m dialled, rises RIGHT 1.4 %             |    -11.28    -11.20 |    -11.28 |    -11.70 dashed |   -0.42 | 5.0M?, PLAYS 5.3M, 3.3 CUP>, 1.5%, NO RANGE, APPROX
Left camera only, nothing dialled (3 m assumed)              |     -4.04     -5.48 |     -4.04 |     -4.05 dashed |   -0.02 | --, no plays-like, BREAK ?, 1.5%, NO RANGE, APPROX
Ambiguous: a second flagstick in view                        |    -28.53    -28.71 |    -28.54 |    -27.68 |   +0.85 | 19.6FT, PLAYS 14.5FT?, 4.4 CUP>, 2.3%, 2 LINES SEEN, 0/5
Best effort: 7 % cross slope at Stimp 14 (not solvable)      |   +847.02   +797.72 |   +847.02 |   no line |       - | 13.1FT, no plays-like, 7.0%, TOO STEEP
Best effort: 6.5 % downhill at Stimp 14 (no bracket)         |   +975.19   +976.82 |   +975.19 |   no line |       - | 9.7FT, no plays-like, 6.5%, TOO STEEP
Secant plane: twisted green, Survey of 3 drops, Stimp 8      |   -417.50   -415.37 |   -417.46 |         - |       - | 16.3FT, PLAYS 18.0FT?, 20.5 CUP>, 6.2%, TOO STEEP, APPROX, D3
Method B2 (setting), 45 cm past, paces                       |    -23.29    -23.35 |    -23.30 |    -22.80 |   +0.48 | 6.5P, PLAYS 4.8P?, 4.1 CUP>, 2.3%, 1/5
25 estimator calls of the application: 25 agree with the Python reference, 0 do not
largest |C double - reference| of a solved aim: 2.5e-13 mrad; largest |firmware - reference|: 0.062 mrad; largest |drawn - reference|: 2.59 mrad (0.15 deg)
```
<!-- readme-check:end appdiff -->

* 25 estimator calls of the application agree with the Python reference: flags and codes
  exactly; the C double build within 1e-4 relative; the firmware within 0.5 mrad of aim, 0.1 %
  of launch speed, 0.01 cup and 1e-4 of confidence (largest |firmware - reference| of a solved
  aim 0.062 mrad); the drawn line within 6.5 mrad; and **the display state** - normal,
  approximate, none - as a rule written a second time in `tools/app_diff.py` gives it from the
  reference's estimate, the dashes measured in the pixels included.
* Largest |drawn - reference| of a line on the screen: **2.59 mrad** (the flag-out row; the
  test allows 6.5 mrad). The free-line figure of the display is 0.28 degree worst
  ("Display"); the labels of the result screen cover parts of this line, which is what the
  larger rows show.
* **The 7 % row, and a sentence of this file that had it the wrong way round.** Of a failed
  solve only the class (`aim_source`, `solve_status`) is defined and compared; its "aim" is
  the last iterate of a search. For this scene that iterate is +847.02 mrad on the record the
  application built - in the firmware AND in the reference run on that record - and +797.72
  mrad for the reference on the TRUE scene (an earlier version of the "Solver" section gave
  the two numbers as "firmware" and "reference"). Until phase 3 `make appdiff`
  showed a third number here, +797.02 mrad for the Python reference on the application's
  record: the test wrote the pace to the tool with nine significant digits (0.299999982
  where the firmware's single-precision 0.30 is 0.29999998211860657), and on this knife-edge
  solve the reference's last iterate depends on that difference (run again in this session on
  the dumped record with both values: +847.020 with the exact pace, +797.020 with the rounded
  one). The options are now written with 17 digits and taken as written.
* What phase 3 changed in this table: three states instead of solid / dashed; the Survey rows
  (every placement has a line; the old "not at the ball" rows are gone; the E29 order is
  there, 2 m, 6 m, 9 m); the rows that had `NOT SOLVED` with a dashed parallel have no line
  and say `TOO STEEP`; the secant-plane row is dashed; the frames of several reads fall at
  other moments than in phase 2 (the cell temperature is measured before the cameras start,
  the field log is written), which moves aims on the application's record in the last digits.

**What these tests do not reach, and how it is covered instead.** `PACE_LIMITED`, the straight
fallback (`aim_source` 3), a kept near miss, a fit that stops on its iteration limit and a
poor horizon are not produced by any read the simulator's scenes could be made to give
(pace-limited and the near miss are knife edges in cross slope; the others need inputs the
vision does not deliver). Their MAPPING to the screen is tested by overwriting the estimate of
a real read and re-composing the view (`gl_app_recompose_view()`): state, message, line,
break, what stands in the bar's place (the "Mapping only" lines, quoted in "Phase 3, builder
3"; among them a solved result at 0.85 and at 0.75 of the critical slope, either side of the
`TOO STEEP` threshold).
The secant-plane result of a real read has its aim far off the visor axis, so what is on
the screen there is the off-screen parallel; a dashed line ON the screen is seen in the
mapping test, in the two left-camera-only reads and in the flag-out read. The best-effort
results of real reads have no line (phase 3). The synthetic
green is a plane or a twisted plane. **Both branches of the base-of-the-stick logic are
exercised by whole reads**: the base is classed VISIBLE in the two 3 m scenes, the 1.5 m scene
and several Survey drops (their rows have no question mark after `PLAYS`) and at the horizon
from 4.5 m on (`base_hidden` true). An earlier version of this paragraph said that only
`tests/test_solver.c` reached the visible-base branch; the dumped records show otherwise.

### Charger and cell temperature (rev E; `tests/test_drv_power.c`, `tests/test_e2e_faults.c`, `tests/test_e2e_power.c`)

**Which hardware this is.** The rev E board (DESIGN_SPEC E1, E2; `../electrical/gl1_main`):
a TI BQ25101 that charges on its own whenever VBUS is present, enforces the cell's
temperature window ITSELF through its own thermistor (NTC1 on its TS pin) and terminates at
10 % of 19.8 mA. **The firmware can only STOP it**: `CHG_INHIBIT` is a push-pull output on
the gate of an N-MOSFET that pulls TS to ground; HIGH = stop; analog (the reset state), low
or unpowered = the charger is free. `CHG_STAT` is the charger's open-drain status (low while
a charge runs) with a 100 kohm pull-up. The MCU has a thermistor of its own (NTC2) on
`NTC_BIAS` / `NTC_SENSE`.

**No data sheet of the BQ25101 was read.** What the driver and the simulator's model assume
about it is in ONE place, `core/gl_provisional.h` (`GL_PROV_BQ25101_*`), each constant with
its source: the specification's text, the web-search extracts quoted in the netlist notes,
or memory of the family. **Every row below in which no firmware runs is a statement about
that MODEL.** It shows what this project believes the hardware does; it proves nothing about
the chip.

Why the firmware stops a charge (`gl_chg_reason_t`), in the order in which a reason is named:

| Reason | When | Released |
|---|---|---|
| `TEMP_UNKNOWN`, `NTC_FAULT`, `IMPLAUSIBLE` | NTC2 not measured for 12 s; open, shorted or stuck; contradicted by every die sensor that is alive (more than 10 K), or no die sensor to check it against | when a fresh, plausible reading is inside the window |
| `TOO_COLD`, `TOO_HOT` | NTC2 reads below 1.5 C or above 43.5 C (0..45 C narrowed by the 1.5 K guard band) | above 3.5 C / below 41.5 C (2 K of hysteresis) |
| `FORCED` | `GL_CMD_SET_CHARGE` 1 (factory: assembly step 13 proves NTC1 and the MOSFET with it) | the command with 0, VBUS removed, a reset |
| `TIME_LIMIT` | E32: 6 h of continuous charging (CHG low at every gate call) | VBUS removed; or the cell, having been at or above 4.00 V with the limit in force, has fallen below it. A cell that is still under 4.00 V after 6 h of charging gets no second 6 h: stopped until the marker is lifted out |

The firmware's window (0..45 C) is NARROWER than the charger's own (0..60 C, with 4.06 V
above 45 C): with firmware running a charge stops at 43.5 C; without it the charger's window
alone decides. Whether the cell may be charged at 4.06 V between 45 and 60 C is the cell data
sheet's answer (release gate).

**What the charger does, as far as the firmware can tell** (`gl_chg_status_t`, from CHG, VBUS,
the firmware's own stop, the cell voltage and NTC2; the charger has one status line and
everything beyond "a charge is running" is an inference):

| Status | Inferred from | Firmware's reaction |
|---|---|---|
| `NO_INPUT` | no VBUS | stop released |
| `CHARGING` | CHG low | supervise; count toward the 6 h limit |
| `DONE` | CHG released, nothing holding the charger, cell at or above 4.04 V | symbol "FULL"; logged once |
| `INHIBITED` | CHG released and the firmware holds the stop | the reason on the cradle screen |
| `TEMP_HOLD` | CHG released, not stopped, NTC2 outside 0..60 C | "CHARGER WAITS" |
| `NOT_CHARGING` | CHG released although nothing known holds the charger and the cell is not full (input too low for it, its safety timer, NTC1 shorted, the part dead; also the moment after docking) | a fault when it has lasted 30 s: "NOT CHARGING", logged |
| `STOP_FAILED` | CHG LOW although the firmware holds the stop (the MOSFET or its gate) | a fault after 30 s, logged |

One more inference, a flag (`ntc1_suspect`, GET_POWER bit 6, logged): a charge was running
with NTC2, believed by a die sensor, more than 3 K outside the charger's OWN window. The
charger's thermistor is then not doing its job - by the search extract quoted in the netlist
notes an OPEN NTC1 puts the part into a mode with no temperature monitoring, no timer and no
termination. The firmware's gate stops that charge while it runs; with no firmware nothing
does (last row of the table).

**State table.** Who holds `CHG_INHIBIT`, whether the charger runs, who watches the cell.
"MODEL" = the simulator's BQ25101; figures are from this phase's runs.

| State | `CHG_INHIBIT` | Charger with VBUS (MODEL) | Who enforces a temperature window | Measured on the simulator |
|---|---|---|---|---|
| MCU unpowered, held in reset, or start-up before the first measurement | analog; the 100 kohm on the gate keeps the stop off | follows its own thermistor: off below 0 C and above 60 C, half current below 10 C, 4.06 V above 45 C | the charger, 0..60 C | in reset in the cradle: no charge at -5 C, charging at 22 C, no charge again at -5 C. Alone over temperature: COLD at -20 and -0.5 C, COOL at 0.5 and 9.5 C, FAST at 10.5, 25 and 44.5 C, WARM at 45.5 and 59.5 C, HOT at 60.5 and 85 C |
| Boot in the cradle | driven HIGH by the first gate evaluation if the firmware has a reason | as the firmware and its own window allow | both | boot at -5 C: `CHG_INHIBIT` high 88.3 ms after `gl_hal_init()`; the charger had not run (its own window) |
| Awake or asleep in the cradle, temperature permitted | analog | on, until it terminates | the firmware (NTC2 + die sensors every 5 s, 0..45 C) and the charger | not stopped 3.5..43.5 C rising, 1.5..41.5 C falling |
| The same, firmware has a reason | **HIGH** | **off** (TS at ground) | the firmware | cradle at 47 C, awake: stopped 4.30 s after the cell got there (5 s period); asleep in the cradle, to 50 C: 4.80 s; every NTC2 fault stops |
| Asleep (Stop 2), no VBUS; ship mode | **analog** before the sleep | nothing to charge; starts by itself at the next cradle | the charger; the firmware from the VBUS edge on | simulator rule: Stop or ship mode with the pin high and no VBUS is a violation (none; a test of the rule makes it fire). Asleep, into a cradle at 50 C: the charger ran 1.22 ms in its WARM zone before the firmware stopped it |
| The same, the VBUS edge's interrupt latch lost | analog | on by its own rules | the charger; the firmware from the next wake-up of any kind (16 s at the latest) | cradle at 50 C, edge lost 0.5 / 4.5 / 8.5 / 12.5 s after a housekeeping wake-up: 15.5 / 11.5 / 7.5 / 3.5 s in the WARM zone before the firmware stopped it |
| VBUS removed | analog in the loop pass that sees it, and at the latest before the next sleep | - | - | the bounce stress: 300 scenarios, 0 violations (below) |
| Supervision stalled | HIGH when the last reading is 12 s old | off | "unknown is stop" | stopped with the reading 12.0 s old; with the charger's status edge alive that stop itself starts a fresh measurement (3 in 40 s of a stalled supervision), and the charge never ran on a reading older than 12.00 s |
| Watchdog reset | analog again from the reset | on by its own rules until the firmware has measured again | the charger, then both | reset while the firmware held the stop at -5 C: the charger stayed off (its own window). At 50 C: 3.0 ms of reset and 1.2 ms of boot in its WARM zone, then stopped by the firmware again |
| **Firmware hung** (phase 2, old charger: "unsupervised for 33 s", NOT MET) | whatever it was | **MODEL: on by its own rules** | **the charger, 0..60 C. The firmware's 45 C limit: nobody, for up to one watchdog period** | hung at 50 C: the charger went on in its WARM zone (to 4060 mV) for 33 s, until the watchdog. **NOT MET for the firmware's 45 C limit.** Hung at 65 C: stopped by its own thermistor, charged for 0.0 ms of 33 s |
| **ROM loader** (phase 2: "600 s at 50 C, nothing could stop it", NOT MET) | analog (PH1 is no ROM-loader pin: pin list PROVISIONAL) | **MODEL: on by its own rules** | **the charger, 0..60 C. The firmware's 45 C limit, its 6 h limit and a termination: nobody** | cell at 50 C: 600 s of 600 s in the WARM zone (**NOT MET for the 45 C limit**). At 65 C: 0.0 ms of 600 s. At -5 C: 0.0 ms of 600 s. Time charged outside the charger's 0..60 C in the whole test: 0 ms |
| The charger's thermistor NTC1 OPEN, no firmware | analog | **MODEL: charges with NO window, no timer, no termination** (extract: "floating TS ... puts part in TTDM") | **nobody** | cell at 70 C, MCU in reset: charged for 60 of 60 s. **NOT MET in hardware alone.** With firmware running its gate on NTC2 stops it and sets `ntc1_suspect`. Board test must prove NTC1 (the SET_CHARGE command is for that) |

**The end of a charge** (the reason for E32). The charger terminates when its OUTPUT current
falls below 1.98 mA, and the board hangs on the same node as the cell. MODEL, cell from 90 %
(the cell's curve and resistance are guesses: good for "does it end", not for a time):

| Who is on the node | Load | Result |
|---|---|---|
| MCU held in reset | 17.7 uA (+28 uA of CHG's pull-up while charging) | terminates after 0.32 h at 99.7 % |
| Asleep in the cradle (E32), wall charger | 98.6 uA | terminates 0.31 h after docking; the status edge wakes the marker, symbol "FULL" |
| Awake in the cradle, a host that keeps talking - **and every docked marker before phase 3** | 3.35 mA | **never terminates**: after 3 h the cell is at 100.0 % and the charger still delivers 3.34 mA. The firmware's backstop stops it 6.000 h after docking; 2.62 h later the awake marker has run the cell down to 4.0 V (80 %) and the charge starts again |
| ROM loader | 4.0 mA (a guess) | **never terminates**; after 10 h the charger's own safety timer ends it - IF it has one (from memory of the family, PROVISIONAL). NOT MET in hardware alone |

**If the status line shows the first cycle only** (`test_charger_whose_status_shows_the_first_cycle_only`).
`GL_PROV_BQ25101_CHG_LOW_ON_RECHARGE` = 1 assumes that CHG goes low again when the charger
starts a recharge after a termination. That is from memory and NOT CONFIRMED; the family may
signal the first charge cycle only. The simulator's model has that reading as a variant
(`gl_sim_charger_stat_first_cycle_only()`), and on it: the first cycle ends asleep in the
cradle as before ("FULL"); awake under a talking host the cell runs down to the recharge
threshold in 1.17 h and the recharge runs with CHG released - **the firmware says FULL
(status `DONE`) while 19.8 mA flow**, and nothing is called a fault; **NOT MET, pinned: 7 h
later the charger is still on and the 6 h backstop has counted 0 ms**, because it counts the
time CHG is low. The first cycle, and every cycle after a stop of the firmware's own (a stop
through TS restarts the charger's cycle in the model), are counted; the temperature gate works
whatever the status line shows. Open issue 39.

**Random plugging and unplugging** (`test_vbus_bounce_stress`; no fault is injected): 300
scenarios of VBUS edges singly and in bursts, temperature jumps between -8 and 55 C, MCU
resets and reads in progress - 4857 edges, 105 resets, 55 completed reads. 0 simulator
violations, 0 inconsistent end states (UI state, USB, `CHG_INHIBIT` and the VBUS level all
agree), 0 left with the fast clock; the longest stretch of charging outside 0..45 C was
4.96 s (the supervision period; the rule allows 10 s). During this phase the stress found
one scenario in which the firmware entered Stop mode with `CHG_INHIBIT` high and VBUS just
gone (VBUS fell during the millisecond the measurement before the gate takes); fixed in
`sleep_()`, which now releases the stop as its last act.

Cell temperature, as built and as tested:

* **Conversion.** Ratiometric (bias from the ADC's reference rail): R = 10.0 kohm x x / (1 - x),
  T = 1 / (1/298.15 + ln(R / 10 kohm) / 3380) - 273.15. Against a table computed independently
  in the test in double precision, -40..85 C in 0.5 C steps: worst error 0.011 K (at -39.5 C;
  one ADC count is 0.006 K at 25 C and 0.025 K at -40 C).
* **Tolerances and the guard band.** NTC 1 %, B 1 %, series resistor 1 % in their worst
  combination: 0.67 K at 0 C, 0.81 K at 45 C, 1.05 K at 60 C; with an ADC error of 0.2 % of
  full scale 0.90 K, 1.09 K and 1.43 K (computed by the test; the output resistance of the
  bias pin adds 0.11 to 0.16 K by the netlist notes, not in the test). The window is therefore narrowed by `GL_PROV_CHARGE_TEMP_GUARD_C` = 1.5 K on
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

### Cradle, ship mode and the hot cell (`tests/test_e2e_power.c`, `tests/test_ui.c`)

**The cradle (DESIGN_SPEC E32).** Two UI states. `CRADLE_USB`: awake, display on with the USB
screen, USB started. Its time limit is 30 s WITHOUT HOST ACTIVITY: the application restarts
it whenever a host has sent something, is being sent a stream it asked for, or a log erase or
six-face calibration it started is running. When it runs out - on a wall charger at once, 30 s
after docking - the marker goes to `CRADLE_SLEEP`: MCU in Stop mode, IMU and flash powered
down, the display ON with a STATIC picture (a battery with a bolt = charging, with a tick and
"FULL", or a warning sign and the reason no charge runs; the memory LCD keeps the picture
and its polarity signal EXTCOMIN keeps running from the low-power timer). It is drawn when
the state is entered and again only when what it says changes.

| Out of `CRADLE_SLEEP` by | What happens | Measured |
|---|---|---|
| the host resumes the bus (it had SUSPENDED it: the USB device stayed attached, in standby) | back to `CRADLE_USB`, USB running again, no new enumeration | 21 ms after the resume |
| VBUS goes (lifted out) | the ordinary sleep: display off, IMU in wake-on-motion, `CHG_INHIBIT` released - or ship mode if armed | asleep 0.5 s later; reads when put down |
| the charger's status changes | awake for one loop pass: measure, gate, draw the new picture, asleep again | charge ended -> "FULL" on the panel |
| the 5 s supervision timer | NTC2, die sensor, cell voltage, the gate; nothing drawn unless something changed | 110 to 130 conversions in 600 s (asserted), no frame sent to the panel; the firmware's stop at 50 C came 4.80 s after the cell got there |
| NOT by motion, taps, a low cell or a bouncing VBUS | | the cradle knocked about for 3 s: nothing |

What USB does when the 30 s run out: under a host that has suspended the bus, standby (wake
on resume); under a host that keeps the bus running but says nothing, and with no host at
all, the device detaches (a device may not sleep under a running bus). **Pinned as NOT MET
("the host can always reach the marker"): after that detach nothing the host does wakes the
marker - a command sent then is not answered - and only taking the marker out and putting
it back brings it back.** A host that wants a docked marker has to talk at least every 30 s
(any command) or suspend the bus instead of going silent. Whether real hosts suspend an idle
CDC device was not tested: there is no hardware.

The marker's draw in the cradle (supply model; "the node the charger feeds" = the cell's
node, the charger has no power path), against the charger's termination threshold of
1.98 mA:

| State | Draw | |
|---|---|---|
| Awake in `CRADLE_USB` (what a docked marker ALWAYS was before phase 3) | **3.35 mA** | above the threshold: the charge cannot end (table "The end of a charge" above) |
| `CRADLE_SLEEP`, USB off (wall charger, silent host) | **98.6 uA** while charging | 5 % of the threshold; Stop 2 for 99.98 % of the time. Parts: MCU 9, IMU off 3, flash 0.1, display 6, DISP pull-down 28, grain bias divider on DISP 14, CHG pull-up 28 (while the charger holds it low), always-on parts 9.5, the 5 s measurement about 1 |
| `CRADLE_SLEEP`, USB in standby (suspended host) | **179.4 uA** | Stop 1 instead of Stop 2 (70 uA, from memory, low confidence) and 20 uA for the USB core (a guess), because it is not known that the U585 wakes on USB from Stop 2 (`GL_PROV_USB_WAKE_FROM_STOP2` = 0) |

**Ship mode (E13).** `GL_CMD_SHIP_MODE` with "SHIP" arms it (since builder 2 of phase 3 it
needs UNLOCK, as every command that arms or writes something does); "STAY" disarms; a reset disarms. Armed, the marker behaves as usual while docked - also
asleep in the cradle. When it is lifted out it does not go to wake-on-motion (lifting IS
motion): IMU and flash powered down, display off, USB off, ADC and op-amp off,
`CHG_INHIBIT` and `NTC_BIAS` analog, and `GL_APP_SHIP_SETTLE_MS` = 1 s after VBUS went
(spring-pin bounce must be over: the way back is a rising edge of VBUS) the last log record
of this life is written and the MCU enters its lowest-power state.

* **Which mode.** STM32U585 **Shutdown**, with the PWR wake-up pin of VBUS_SENSE (PC13 =
  WKUP2, rising edge). The netlist chose PC13 for this.
* **What is retained.** Nothing but the backup domain: one backup register carries the
  "in ship mode" marker. No RAM, no peripheral register, no pin state: every pin is
  high-impedance; the board's resistors hold the chip selects, DISP, the camera rail enable
  and the gate of the charger's stop (charger ON), and the backend applies the MCU's
  Shutdown pull-downs to the six lines that have no resistor and to the two MISO lines. The
  low-speed oscillator and the RTC are stopped: the clock reads "not set" afterwards. No
  watchdog runs.
* **The way out is a reset** through the wake-up pin: `gl_hal_init()` runs, the boot record
  in the log carries `GL_RESET_SHIP_WAKE`. A reset from any other cause with VBUS absent
  goes straight back to Shutdown inside `gl_hal_init()`.
* **Tested on the simulator:** not entered 0.3 s after the lift, entered 1.2 s after it; the pin and device
  states above; a minute of handling and a level forced onto the IMU's interrupt line do not
  wake it and no firmware runs (no watchdog refresh, no watchdog expiry); a reset without
  VBUS goes back; VBUS wakes it, and the charger of the model has started by then without
  any firmware; afterwards an ordinary sleep with wake-on-motion and a read; "STAY"; a lift
  of 0.3 s does not enter; armed and left to sleep in the cradle for an hour it is entered
  from there; a stop the firmware held (cell at 50 C) is released on the way in.
* **Expected current, and the requirement.** Data-sheet figures FROM MEMORY, all
  PROVISIONAL: Shutdown without RTC 0.11 to 0.21 uA (0.2 in the model); IMU powered down
  3.0 uA; flash in deep power-down 0.1 uA; the board's always-on parts 9.6 uA at 3.9 V
  (2.8 V regulator 1.6, battery divider 1.95, cell protection circuit 3.0, charger leakage
  0.075, camera regulator disabled 0.2, the enable pin of the E26 USB regulator 2.8).
  **Model: 12.93 uA at the cell. The requirement of DESIGN_SPEC section 6 is 5 uA and three
  months from a 30 % charge: NOT MET, pinned** - 30 % of the cell (12.9 mAh) lasts 42 days
  there. The firmware controls 3.3 uA of the 12.9; the rest is the board. What would have to
  change is hardware (the 2 Mohm battery divider alone is 1.95 uA and the regulator 1.6; the
  2.8 uA of the regulator's enable pin is from memory of its data sheet and NOT CONFIRMED - if
  that part has no pull-down there, every sleep figure here is 2.8 uA lower) or the
  requirement.

**No camera read from a hot cell (E13).** `gl_power_read_allowed()`: a read is refused while
NTC2 READS above `GL_PROV_READ_TEMP_MAX_C` = 60.0 C, and until it has fallen
`GL_PROV_READ_TEMP_HYST_C` = 3.0 K below (our choice: about twice the reading's worst-case
error of 1.43 K at 60 C, so that a cell at the limit does not flicker). The limit is applied
to the reading, as the specification words it. If NTC2 has no valid reading the hotter of
the die sensors that are alive stands in; with no temperature at all the read is allowed.
The cell is measured when the marker wakes (a hot marker says so 58 ms after the wake-up,
before the tilt read) and again where the cameras would start if the last reading is older
than 5 s. The UI shows `TOO_HOT` (a thermometer, "TOO HOT / NO READ / LET IT COOL") for 4 s
and sleeps; the event is logged with the temperature. A result that is already on the
screen, the settings dial, the zeroing and the cradle are left alone.

| Scenario (simulator) | Result |
|---|---|
| board at 61.5 C, marker put down | `TOO_HOT`, no camera powered, no frame; asleep 3.98 s later |
| cooled to 58.5 C (inside the hysteresis) | still refused |
| cooled to 56.5 C | the read runs |
| 59.5 C coming from below; 60.5 C | the read runs; refused |
| NTC2 broken off, board at 66 C; at 30 C | refused on the die sensors; the read runs |
| woken at 22 C, carried for 9 s while the cell goes to 63 C | measured again at the camera start (one conversion, `NTC_BIAS` driven 0.68 ms): refused |
| the same jump inside the 5 s the last reading is accepted for | NOT seen: the read ran on the 22 C reading (pinned; no cell heats by 40 K in 5 s) |

### Sleep and the supply model (rev E) (`tests/test_e2e_power.c`, `hal/host/gl_sim.h`)

**Every current is a data-sheet figure FROM MEMORY, a figure of `docs/research` (unverified
there), a PROVISIONAL figure of the netlist notes, or a plain guess - each line of
`hal/host/gl_sim.h` (`GL_SIM_I_*`) says which. None is a measurement: no board exists.**

Asleep out of the cradle (Stop 2, IMU in wake-on-motion, flash in deep power-down, display
off), cell at 3.8 V, 1 h of simulated time:

| Part | uA | Source |
|---|---|---|
| MCU, Stop 2 with RAM, RTC, LSE, LPTIM | 9.0 | `docs/research`, reviewer's recollection |
| IMU, accelerometer low-power, wake-on-motion | 5.0 | memory |
| flash, deep power-down | 0.1 | memory |
| 2.8 V regulator (MCP1700), quiescent | 1.6 | `docs/research` |
| battery divider, 2 x 1 Mohm | 1.90 | computed at 3.8 V |
| cell protection circuit | 3.0 | `docs/research/power.md`; NOT in the path of a bench supply on the cell-lead pads |
| charger, leakage out of the cell with no input | 0.075 | netlist notes 4.12 (the title of a data-sheet copy seen in a search) |
| camera regulator (LP5907), disabled | 0.2 | memory (1 uA at most) |
| USB regulator of E26 (LP5907), enable pin held at 2.8 V: its internal 1 Mohm pull-down | 2.8 | memory of the part's data sheet, **NOT CONFIRMED**; netlist notes section 11 state the same figure, also from memory |
| NTC1 (charger's thermistor) | 0 | biased by the charger, from VBUS only |
| NTC2 (MCU's thermistor) | 0 | `NTC_BIAS` analog; driven 0.68 ms every 11 minutes for the housekeeping's cell measurement (3.42 ms in the hour) |
| 150 kohm wake pull-up on the op-amp output, underside DARK | 0 | netlist notes 4.10 |
| housekeeping (a wake-up every 16 s) | 0.01 | model |
| **Sum at the cell, dark** | **23.68** | measured on the simulator |
| ... through the cell-lead pads (without the protection circuit), dark | **20.68** | **E14 limit 25 uA: MET by the model** |
| 150 kohm wake pull-up, underside LIT (the photodiode conducts, op-amp off) | +5.2 | netlist notes 4.10: 4.5 to 5.2 |
| **Sum at the cell, lit** | **28.88** | 25.88 at the pads: above 25 uA. E27 defines the limit for a dark underside; a marker asleep face-up on a sunny bench is not that case |

Phase 2 stated 20.6 uA at the cell (9 + 5 + 0.1 + 6.5 for "regulator, divider and protection
circuit"). The difference of 3.1 uA is the rev E board: charger leakage, the disabled camera
regulator, and the enable pin of the new USB regulator (2.8 of it, NOT CONFIRMED).

| State | At the cell (model) | Lasts |
|---|---|---|
| Read (wake-up to result, nominal factor) | 226.7 mAs = 0.063 mAh; about 96 mA while the camera rail is on (2.42 s) | 594 read cycles per 43 mAh (cycle = read + 45 s of result + falling asleep, 260.4 mAs) |
| Asleep, dark / lit | 23.7 / 28.9 uA | 76 days from a full cell; 23 days from 30 % |
| Asleep in the cradle, charging (the charger supplies it) | 98.6 uA; 179.4 uA with USB in standby | - |
| Ship mode | 12.9 uA (requirement 5: **NOT MET**) | 42 days from 30 % (requirement: 3 months) |
| Storage mode (cell below 3.25 V: IMU off) | not measured again in this phase | - |

### Pins of the rev E board (`tools/gen_pins.py`, `tests/test_pins.c`, `tests/test_board.c`)

**The pin map is the netlist's.** `../electrical/gl1_main/pinmap.json` is exported by the
netlist (which proves every row against ST's open pin data) and is the ONLY place where a
pin is assigned. `make pins` generates `hal/stm32u5/gl_pins.h` from it; `make pins-check`
(part of every test and cross build) fails when the header is stale. **The board layout is
still being routed and may exchange pins: the procedure is then `make pins` and `make
test`, nothing else** - no file of the firmware names a port, a pin number, a pad or an
alternate function by hand (the one identifier of the STM32 backend that names a pad, the
HAL's name of the ship-mode wake-up pin, is guarded by a compile-time check). It happened
once during this phase: the pin map changed under the build (a firmware note was reworded
for E25, no pin moved), `pins-check` stopped the build, `make pins` followed.

What the generator holds is not a pin assignment: the signals of `gl_pin_t` in their order
(the simulator's trace format), how the pin map's words become table columns, and one rule
per FIRMWARE NOTE of the pin map. A note it does not know stops the generation: somebody
has to read it, act on it and add it. The 17 notes of the present map and where the
firmware acts on each are listed at the end of the generated header.

The generator REFUSES (and `tests/test_pins.c` checks the same on the generated table, after
reading `pinmap.json` again with a scanner of its own): a signal of `gl_pin_t` missing from
the map or a map signal the firmware does not know (the old `CHG_PROG_EN` is one of the 31
defects its self-test seeds); two signals on one pin or pad (one declared exception: the
BOOT0 strap shares its pad with ONE output that rests low or analog - `CAM_R_PWDN`); two
interrupt signals on one EXTI line; a camera PWDN line on a pin the ROM loader drives;
`CHG_INHIBIT`, `NTC_BIAS`, `NTC_SENSE` or `CAM_PWR_EN` on ANY ROM-loader pin; a camera-facing
signal that is not SPEC on a pin the loader drives; anything but an input or an
alternate-function output on a USB Type-C CC pad; an AF row without its AF number, an ADC
signal without its channel, `IMU_INT1` or `VBUS_SENSE` off a PWR wake-up pin; a pin map whose
own verification did not pass.

The table as generated (pin map sha256 d33ff53f50f0... since the end of phase 3, when the
electrical side re-issued `pinmap.json` at its layout stage and `make pins` was run again: the
header's pin definitions did not change, only its hash and comments; printed by
`build/host/tests/test_pins`; **a snapshot - `make pins` is the truth**):

```
signal        pin   pad mode     AF  pull  board         EXTI  rail off  asleep     source
CAM_PWR_EN    PH0   5   OUT_PP   -   -     to GND        -     -         low        CHANGED
CAM_L_PWDN    PC2   10  OUT_PP   -   -     series        -     parked    analog/low CHANGED
CAM_R_PWDN    PH3   60  OUT_PP   -   -     to GND        -     parked    analog/low CHANGED
CAM_SCCB_SDA  PC1   9   SCCB_OD  -   -     to V2V8_CAM   -     parked    analog/low CHANGED
CAM_L_SCL     PC3   11  SCCB_OD  -   -     to V2V8_CAM   -     parked    analog/low CHANGED
CAM_R_SCL     PC0   8   SCCB_OD  -   -     to V2V8_CAM   -     parked    analog/low CHANGED
CAM_XVCLK     PA8   41  AF       0   -     -             -     parked    analog/low SPEC
CAM_D0        PC6   37  AF       10  -     -             -     parked    analog/low SPEC
CAM_D1        PC7   38  AF       10  -     -             -     parked    analog/low SPEC
CAM_D2        PC8   39  AF       10  -     -             -     parked    analog/low SPEC
CAM_D3        PC9   40  AF       4   -     -             -     parked    analog/low SPEC
CAM_D4        PC11  52  AF       10  -     -             -     parked    analog/low SPEC
CAM_D5        PB6   58  AF       10  -     -             -     parked    analog/low SPEC
CAM_D6        PB8   61  AF       10  -     -             -     parked    analog/low SPEC
CAM_D7        PB9   62  AF       10  -     -             -     parked    analog/low SPEC
CAM_PIXCLK    PA6   22  AF       4   -     -             -     parked    analog/low SPEC
CAM_HREF      PA4   20  AF       10  -     -             -     parked    analog/low SPEC
CAM_VSYNC     PB7   59  AF       10  -     -             -     parked    analog/low SPEC
LCD_SCS       PB10  29  OUT_PP   -   -     to GND        -     -         low        PROPOSED
LCD_DISP      PB12  33  OUT_PP   -   -     to GND        -     -         low        CHANGED
LCD_EXTCOMIN  PB2   28  AF       1   -     -             -     -         low        SPEC
SPI1_SCK      PB3   55  AF       5   -     -             -     -         low        CHANGED
SPI1_MOSI     PB5   57  AF       5   -     -             -     -         low        CHANGED
SPI1_MISO     PB4   56  AF       5   down  -             -     -         input      SPEC
SPI2_SCK      PB13  34  AF       5   -     -             -     -         low        PROPOSED
SPI2_MOSI     PB15  36  AF       5   -     -             -     -         low        PROPOSED
SPI2_MISO     PB14  35  AF       5   down  -             -     -         input      PROPOSED
FLASH_CS      PA10  43  OUT_PP   -   -     to V2V8       -     -         high       CHANGED
IMU_CS        PB1   27  OUT_PP   -   -     to V2V8       -     -         high       CHANGED
IMU_INT1      PA7   23  EXTI     -   -     -             7     -         input      CHANGED
IMU_INT2      PA5   21  EXTI     -   -     -             5     -         input      CHANGED
GRAIN_CP0     PA9   42  OUT_PP   -   -     series        -     -         analog     CHANGED
GRAIN_CP1     PB0   26  OUT_PP   -   -     series        -     -         analog     CHANGED
GRAIN_CP2     PC12  53  OUT_PP   -   -     series        -     -         analog     CHANGED
GRAIN_CP3     PD2   54  OUT_PP   -   -     series        -     -         analog     CHANGED
GRAIN_CP4     PC10  51  OUT_PP   -   -     series        -     -         analog     PROPOSED
OPAMP_VINP    PA0   14  ANALOG   -   -     -             -     -         analog     SPEC
OPAMP_VINM    PA1   15  ANALOG   -   -     -             -     -         analog     SPEC
OPAMP_VOUT    PA3   17  ANALOG   -   -     to V2V8       -     -         analog     SPEC
VBAT_SENSE    PA2   16  ANALOG   -   -     -             -     -         analog     PROPOSED
CHG_STAT      PA15  50  EXTI     -   -     to V2V8       15    -         input      CHANGED
CHG_INHIBIT   PH1   6   OUT_PP   -   -     to GND        -     -         analog/low PROPOSED
VBUS_SENSE    PC13  2   EXTI     -   -     VBUS divider  13    -         input      CHANGED
USB_DM        PA11  44  AF       10  -     -             -     -         analog     SPEC
USB_DP        PA12  45  AF       10  -     -             -     -         analog     SPEC
NTC_BIAS      PC5   25  OUT_PP   -   -     -             -     -         analog     CHANGED
NTC_SENSE     PC4   24  ANALOG   -   -     -             -     -         analog     PROPOSED
```

Against the rev C2 header 20 signals moved (the pin map lists each with its reason); gone:
nothing but the old meaning of two pins; new meaning: `CHG_INHIBIT` push-pull HIGH = stop,
`CHG_STAT` = the BQ25101's open-drain CHG on PA15. Interrupt lines: IMU_INT1 PA7 = EXTI7
(WKUP8), IMU_INT2 PA5 = EXTI5, VBUS_SENSE PC13 = EXTI13 (WKUP2), CHG_STAT PA15 = EXTI15 -
three of the four moved. ADC1: grain 8, battery 7, NTC2 13.

What the firmware does about the pin map's notes (each is tested on the simulator, or is in
the STM32 backend by inspection only, as marked):

| Note | Firmware | Checked |
|---|---|---|
| PA15 and PB15 are USB Type-C CC pads of the MCU; PB5 and PB14 their dead-battery control pads (what they do: PROVISIONAL) | `UCPD_DBDIS` is the first statement of `gl_hal_init()`, before any pin is configured and before the ROM hand-over; a CC pad carries an input (`CHG_STAT`, never driven, no internal pull) or an alternate-function output (`SPI2_MOSI`) | generator and `test_pins.c` for the pads; backend BY INSPECTION (`test_board.c` checks the order in its text) |
| PH3 is BOOT0 and `CAM_R_PWDN` (10 kohm to ground) | the PWDN line rests low or analog, so the strap reads 0 at every reset; 0.28 mA while it is driven high, in the supply model | generator rule; simulator's rail rule |
| USB-supply-valid bit: VBUS_SENSE AND the MCU's own monitor of the supply pin; cleared on the falling edge of either | `gl_hal_usb_supply_ok()`; the application starts USB only when it is true, checks it at every loop pass and stops USB when it is false; `GL_IRQ_VBUS_CHANGE` also for the supply | simulator: VBUS_SENSE lags the pad by up to 22 ms on removal, USB left on without its supply is a violation; backend BY INSPECTION |
| PA9 is the USB core's VBUS pad and carries a grain LED line | VBUS sensing off, session valid by override | uncompiled USB file only |
| Lines without a board pull float in reset: EXTCOMIN, SCK and MOSI of both buses, `CAM_L_PWDN` | driven LOW first in `gl_hal_init()`; internal pull-downs on the two MISO lines | simulator: the first 12 pin records of `gl_hal_init()` are these 6 lines, written low and then made outputs; backend BY INSPECTION |
| Chip selects, DISP, rail enable, gate of the charger's stop: held by board resistors | taken over at that level (latch before mode); `CHG_INHIBIT` not touched | simulator: no record of reset + init leaves one of them away from its level; an internal pull against a board pull is a violation |
| Before a jump to the ROM loader the IMU's INT lines must be static (the loader's SPI inputs) | the IMU is powered down before `gl_hal_reboot(GL_REBOOT_ROM_DFU)` | simulator rule, made to fire by a test |
| The grain bias divider hangs on `LCD_DISP`: 35 ms of display-on time before a measurement | `gl_grain_fe_power()` refuses with the display off and waits 35 ms | simulator rule; 35.7 ms measured |
| PA3 (op-amp output) is held high by 150 kohm: leave it analog while the op-amp is off | analog; 19 uA in the model if driven low, 5.2 uA with light on the photodiode | supply model |
| PA15, PB3, PB4 away from JTAG; LSE drive medium-low | the mode write of each pin; `__HAL_RCC_LSEDRIVE_CONFIG` | backend BY INSPECTION |
| EXTCOMIN divider 547 | `GL_PINS_EXTCOMIN_LSE_TICKS` from the pin map; `GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS` must equal it | simulator: 32768 / 547 = 59.905 Hz |

Still PROVISIONAL about the pins, and stated so by the pin map itself: the list of pins the
ROM loader drives or listens on (memory of AN2606), what the UCPD pads do, and the
electrical limits of the pins. Two SPEC rows remain on pins the loader drives (PB9 = D7,
PA6 = PIXCLK, behind their 220 ohm resistors): a release gate.

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
labels of the result screen over it the drawn line is within 2.59 mrad of the reference in
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

**All 525 reference vectors in the double build, the final build of phase 3** (generated
block: `make diff` runs the 492 estimator and solver cases through the shared library against
the comparison rule - double precision, then single precision with the firmware's tolerances,
then 20000 random reads and 20000 random aim problems each, "RESULT" - and `tests/test_solver.c`
the 33 roll cases):

<!-- readme-check:begin diff -->
```
estimator_cases: 240 cases, worst difference 3.55e-06 x allowed (patch[4] of case 9)
solver_cases: 120 cases, 0 status mismatches, worst difference 2.12e-12 x allowed (aim_offset of case 8)
fallback_estimator_cases: 82 cases, worst difference 2.73e-12 x allowed (confidence of case 15)
fallback_solver_cases: 32 cases, 0 status mismatches, worst difference 0 x allowed ()
near_miss_estimator_cases: 18 cases, worst difference 0 x allowed ()
estimator_cases: 240 cases in single precision with the firmware tolerances; largest difference of the aim direction 0.132 mrad (bounds are asserted by tests/test_solver.c)
fallback_estimator_cases: 82 cases in single precision with the firmware tolerances; largest difference of the aim direction 0.099 mrad (bounds are asserted by tests/test_solver.c)
near_miss_estimator_cases: 18 cases in single precision with the firmware tolerances; largest difference of the aim direction 2.950 mrad (bounds are asserted by tests/test_solver.c)
RESULT: agreement
RESULT: agreement
    double, roll_cases: 33 rolls (stopped 27, time limit 2, out of bounds 2, stopped on capture 2; 13 holed), 0 differ; status, capture, side and step count exact, largest difference 0.0e+00
```
<!-- readme-check:end diff -->

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
the best iterate of the unsolvable 7 % scene is +847.02 mrad in the firmware, in the C double
build and in the Python reference on the same record (`make appdiff`); and the single build
differs from the reference by up to 123 mrad on the hostile reads above. (This sentence used
to give +797 mrad for the firmware and +847 for the reference. The two were the wrong way
round, and the difference was not the estimators': `tools/app_diff.py` received the pace
with nine significant digits - 0.299999982 where the firmware's single-precision 0.30 is
0.29999998211860657 - and on this knife-edge solve the reference's last iterate then is
+797.02 mrad. Run again in this session on the dumped record with both values: +847.020 with
the exact pace, +797.020 with the rounded one. The test now writes the options with 17
digits. The +797.72 of the table's "true scene" column is a third number: the reference on
the TRUE scene.) **What the firmware does about it since phase 3** (DESIGN_SPEC E31, E33):
an aim that is not a solution is not drawn at all (`NOT SOLVED` or `TOO STEEP`, no line), and
a SOLVED result on a slope of 0.80 of the critical one or more is shown as `TOO STEEP` with a
dashed line; the threshold comes from a sweep with this session's ratio in which nothing
flips below 0.90 ("Phase 3, builder 3"). A near miss of the patch is kept in preference to a
secant-plane aim that misses (finding 1). What it does not do: stabilise the search. That is
the estimator owner's (open issue 24).

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

**The tables of this section are the test's own output from the final build of phase 3**
(generated blocks). They replace tables that were typed from earlier runs; the phase-2 final
check found six cells of the grid and one figure of the base table that no run produced any
more. Flat green, width x contrast, 6 reads per cell - reads that gave a disparity, the
disparity error rms in px, the mean claimed sigma in px; bright sticks, then dark ones:

<!-- readme-check:begin vision-grid -->
```
flat green, 15 mm stick 1.96 m tall, noise 2 grey rms, 6 reads per cell;
columns: Weber contrast of the stick against the sky (5 % = 6 grey = 3 x noise)
BRIGHT stick  reads with a disparity (of 6)    | disparity rms px                        | mean claimed sigma px
width px  range m |    5%   10%   20%   40%   60% |      5%     10%     20%     40%     60% |      5%     10%     20%     40%     60%
0.5       19.7    |     0     0     6     6     6 |  0.0000  0.0000  0.0258  0.0177  0.0138 |  0.0000  0.0000  0.0774  0.0586  0.0547
0.7       14.1    |     1     6     6     6     6 |  0.0765  0.0356  0.0166  0.0097  0.0057 |  0.2134  0.0918  0.0614  0.0540  0.0527
1.0       9.9     |     6     6     6     6     6 |  0.0382  0.0214  0.0131  0.0039  0.0031 |  0.1106  0.0619  0.0531  0.0517  0.0516
1.5       6.6     |     6     6     6     6     6 |  0.0228  0.0133  0.0030  0.0027  0.0036 |  0.0696  0.0544  0.0514  0.0515  0.0515
2.0       4.9     |     6     6     6     6     6 |  0.0170  0.0067  0.0046  0.0019  0.0021 |  0.0583  0.0519  0.0510  0.0513  0.0515
3.0       3.3     |     6     6     6     6     6 |  0.0206  0.0076  0.0026  0.0029  0.0013 |  0.0557  0.0514  0.0512  0.0515  0.0515
DARK stick    reads with a disparity (of 6)    | disparity rms px                        | mean claimed sigma px
width px  range m |    5%   10%   20%   40%   60% |      5%     10%     20%     40%     60% |      5%     10%     20%     40%     60%
0.5       19.7    |     0     0     6     6     6 |  0.0000  0.0000  0.0314  0.0215  0.0136 |  0.0000  0.0000  0.0798  0.0577  0.0546
0.7       14.1    |     1     6     6     6     6 |  0.1254  0.0308  0.0154  0.0110  0.0066 |  0.2243  0.0882  0.0619  0.0532  0.0522
1.0       9.9     |     6     6     6     6     6 |  0.0897  0.0158  0.0128  0.0043  0.0036 |  0.1008  0.0643  0.0533  0.0518  0.0516
1.5       6.6     |     6     6     6     6     6 |  0.0246  0.0140  0.0065  0.0046  0.0018 |  0.0656  0.0545  0.0512  0.0514  0.0514
2.0       4.9     |     6     6     6     6     6 |  0.0169  0.0103  0.0049  0.0049  0.0024 |  0.0613  0.0518  0.0510  0.0513  0.0515
3.0       3.3     |     6     6     6     6     6 |  0.0142  0.0059  0.0024  0.0021  0.0015 |  0.0572  0.0515  0.0512  0.0515  0.0515
```
<!-- readme-check:end vision-grid -->

The claimed sigma is 0.051-0.054 px wherever the stick is easy and rises to 0.06-0.22 px in the
faint cells; no cell has an error above 1.5 claimed sigma rms. **Not met:** sticks of 0.5-0.7 px
at 5-10 % contrast (14-20 m, 3-6 x noise) are mostly not read (the old code, in the reviewers' run of the same grid, read none of the 5 % and 10 % cells
at any width up to 1.5 px, none of 0.7 px at 20 % and almost none of 0.5 px below 60 %; the
matched significance test and averaging 4 or 16 rows along the line are what recover the cells
that now work).

Named scenes, 8 reads each. Columns: `ste` reads with a disparity, `lft` left camera only,
`brg` band-only bearing, `non` nothing, `wrg` another object taken for the stick, `amb`
flagged ambiguous; `d bias`, `d rms` disparity error in px (of the reads within 0.5 px),
`sigma` the mean claimed uncertainty, `z rms` error over claimed sigma, `max|d|`; `b bias`,
`b rms` lowest visible point in rows, `b z` over its claimed sigma, `V/H/U` base classed
visible / at the horizon / unknown; `top`, `clu` tops offered for ranging and tops flagged
"in clutter", `t rms` in rows; `rng %` and `rng z` the fused range error. A = 1.5 px stick
(6.6 m), B = 0.8 px (12.3 m):

<!-- readme-check:begin vision-scenes -->
```
  case                     N ste lft brg non wrg amb |  d bias   d rms   sigma z rms max|d| | b bias  b rms   b z V/H/U    | top clu  t rms |  rng % rng z
  A_nominal                8   8   0   0   0   0   0 | -0.0007  0.0039  0.0515  0.08  0.008 |  -0.52   0.53  0.76 0/8/0    |   8   0   0.05 |   0.18  0.07
  B_nominal                8   8   0   0   0   0   0 | -0.0106  0.0148  0.0534  0.28  0.022 |  -0.29   0.29  0.46 0/8/0    |   8   0   0.10 |   0.98  0.24
  A_slant+1                8   8   0   0   0   0   0 | +0.0030  0.0052  0.0511  0.10  0.008 |  -0.47   0.52  0.75 0/8/0    |   8   0   0.04 |   0.22  0.09
  A_slant+2                8   8   0   0   0   0   0 | -0.0002  0.0039  0.0503  0.08  0.007 |  -0.55   0.55  0.90 0/8/0    |   8   0   0.03 |   0.17  0.07
  A_slant+3                8   8   0   0   0   0   0 | -0.0003  0.0046  0.0503  0.09  0.010 |  -0.40   0.57  0.87 0/8/0    |   8   0   0.04 |   0.20  0.08
  B_slant-3                8   8   0   0   0   0   0 | +0.0083  0.0146  0.0531  0.27  0.030 |  -0.28   0.28  0.48 0/8/0    |   8   0   0.08 |   0.87  0.22
  A_sway_lin3              8   8   0   0   0   0   0 | +0.0018  0.0044  0.0513  0.09  0.010 |  -0.52   0.52  0.60 0/8/0    |   8   0   0.04 |   0.18  0.08
  A_sway_0.5@1.5Hz         8   8   0   0   0   0   0 | -0.0021  0.0087  0.0562  0.16  0.014 |  -0.53   0.53  0.81 0/8/0    |   8   0   0.03 |   0.39  0.15
  A_sway_1.0@3Hz           8   8   0   0   0   0   0 | +0.0009  0.0562  0.1757  0.32  0.082 |  -0.52   0.52  0.66 0/8/0    |   8   0   0.06 |   1.11  0.20
  B_sway_2.0@1Hz           8   8   0   0   0   0   0 | +0.0032  0.0207  0.0650  0.31  0.034 |  -0.31   0.31  0.49 0/8/0    |   8   0   0.06 |   1.07  0.23
[ ok ] test_flat_green_lean_and_sway
  case                     N ste lft brg non wrg amb |  d bias   d rms   sigma z rms max|d| | b bias  b rms   b z V/H/U    | top clu  t rms |  rng % rng z
  A_basevis6               8   8   0   0   0   0   0 | -0.0016  0.0042  0.0513  0.08  0.007 |  +0.26   0.33  1.09 8/0/0    |   8   0   0.06 |   0.18  0.07
  B_basevis6               8   8   0   0   0   0   0 | -0.0007  0.0096  0.0540  0.18  0.020 |  +0.26   0.40  1.18 8/0/0    |   8   0   0.11 |   0.61  0.15
  A_grass1.5               8   8   0   0   0   0   0 | -0.0031  0.0049  0.0514  0.09  0.010 |  +0.36   0.39  1.30 8/0/0    |   8   0   0.03 |   0.27  0.11
  A_grass3                 8   8   0   0   0   0   0 | -0.0029  0.0059  0.0513  0.12  0.013 |  +0.29   0.37  1.21 8/0/0    |   8   0   0.03 |   0.38  0.15
  A_grass6                 8   8   0   0   0   0   0 | +0.0014  0.0053  0.0516  0.10  0.010 |  +0.65   1.05  3.02 7/1/0    |   8   0   0.03 |   0.38  0.15
  A_turf_tex10             8   8   0   0   0   0   0 | +0.0018  0.0065  0.0513  0.13  0.009 |  -0.52   0.52  0.90 0/8/0    |   8   0   0.04 |   0.28  0.12
  A_turf_tex10_vis         8   8   0   0   0   0   0 | +0.0009  0.0066  0.0512  0.13  0.011 |  +0.29   0.55  1.14 8/0/0    |   8   0   0.03 |   0.31  0.13
  B_turf_tex10             8   8   0   0   0   0   0 | -0.0021  0.0110  0.0534  0.20  0.017 |  -0.26   0.27  0.47 0/8/0    |   8   0   0.08 |   0.71  0.17
  B_turf_tex10_vis         8   8   0   0   0   0   0 | +0.0001  0.0103  0.0544  0.19  0.017 |  -4.63   5.44  0.92 2/6/0    |   8   0   0.09 |   1.30  0.27
  A_stripe_low0.3m         8   8   0   0   0   0   0 | -0.0014  0.0075  0.0511  0.15  0.014 |  +0.00   0.00  0.00 0/0/8    |   8   0   0.04 |   0.37  0.15
  A_stripe_mid             8   8   0   0   0   0   0 | -0.0001  0.0032  0.0514  0.06  0.005 |  +0.00   0.00  0.00 0/0/8    |   8   0   0.04 |   0.16  0.06
[ ok ] test_lowest_point_and_base_class
  case                     N ste lft brg non wrg amb |  d bias   d rms   sigma z rms max|d| | b bias  b rms   b z V/H/U    | top clu  t rms |  rng % rng z
  A_flag_bright            8   8   0   0   0   0   0 | -0.0013  0.0033  0.0512  0.07  0.005 |  -0.55   0.55  0.80 0/8/0    |   0   8   0.00 |   0.17  0.07
  A_flag_dark              8   8   0   0   0   0   0 | -0.0021  0.0065  0.0511  0.13  0.011 |  -0.45   0.53  0.85 0/8/0    |   0   8   0.00 |   0.32  0.13
  B_flag_bright            8   8   0   0   0   0   0 | -0.0078  0.0100  0.0531  0.19  0.018 |  -0.30   0.30  0.49 0/8/0    |   0   8   0.00 |   0.95  0.19
  B_flag_dark              8   8   0   0   0   0   0 | +0.0011  0.0092  0.0529  0.17  0.019 |  -0.29   0.30  0.51 0/8/0    |   0   8   0.00 |   0.85  0.17
[ ok ] test_flag_over_the_tip
  case                     N ste lft brg non wrg amb |  d bias   d rms   sigma z rms max|d| | b bias  b rms   b z V/H/U    | top clu  t rms |  rng % rng z
  A_person_behind          8   8   0   0   0   0   8 | -0.0309  0.0355  0.3447  0.11  0.056 |  -0.61   0.62  1.06 0/8/0    |   8   0   0.04 |   0.52  0.08
  A_person_0.6m            8   8   0   0   0   0   0 | +0.0004  0.0056  0.0510  0.11  0.010 |  -0.53   0.53  0.76 0/8/0    |   8   0   0.05 |   0.25  0.10
  A_person_2m              8   8   0   0   0   0   0 | -0.0020  0.0060  0.0515  0.12  0.013 |  -0.56   0.56  0.67 0/8/0    |   8   0   0.05 |   0.28  0.11
  B_person_behind          8   0   0   2   6   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  A_pole2_7px              8   8   0   0   0   0   0 | -0.0137  0.0209  0.2559  0.08  0.035 |  -0.54   0.54  0.70 0/8/0    |   8   0   0.35 |   0.55  0.09
  A_pole2_14px_post        8   4   1   1   2   0   5 | +0.0054  0.0070  0.0507  0.14  0.013 |  -0.24   0.46  0.71 0/5/0    |   5   0   0.04 |   0.32  0.14
  NOT MET with compute time: A_pole2_14px_post gives a disparity in 26 of 64 reads (50 % demanded); 4 of the first 8
  A_pole2_far_weak         8   8   0   0   0   0   5 | +0.0001  0.0061  0.0512  0.12  0.011 |  -0.47   0.50  0.67 0/8/0    |   8   0   0.05 |   0.27  0.11
  A_pole2_far_strong       8   8   0   0   0   0   0 | +0.0013  0.0067  0.0514  0.13  0.012 |  -0.51   0.52  0.83 0/8/0    |   8   0   0.07 |   0.29  0.12
  B_pole2_7px              8   4   1   3   0   0   0 | -0.0039  0.0119  0.2519  0.05  0.015 |  -0.31   0.31  0.53 0/5/0    |   5   0   0.43 |   0.69  0.10
  B_pole2_14px_post        8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  B_pole2_far_weak         8   8   0   0   0   0   4 | +0.0013  0.0123  0.0544  0.23  0.025 |  -0.29   0.29  0.49 0/8/0    |   8   0   0.09 |   0.76  0.18
  B_pole2_far_strong       8   8   0   0   0   0   0 | -0.0036  0.0156  0.0536  0.29  0.031 |  -0.30   0.31  0.52 0/8/0    |   8   0   0.09 |   1.00  0.24
[ ok ] test_other_objects
  case                     N ste lft brg non wrg amb |  d bias   d rms   sigma z rms max|d| | b bias  b rms   b z V/H/U    | top clu  t rms |  rng % rng z
  A_glare_gx0.15           8   8   0   0   0   0   0 | -0.0021  0.0080  0.0512  0.16  0.013 |  -0.54   0.55  0.71 0/8/0    |   8   0   0.04 |   0.36  0.15
  A_glare_gx0.35           8   8   0   0   0   0   0 | -0.0034  0.0105  0.0523  0.19  0.025 |  -0.55   0.56  0.77 0/8/0    |   8   0   0.06 |   0.47  0.18
  A_glare_veil             8   8   0   0   0   0   0 | +0.0008  0.0067  0.0518  0.13  0.013 |  -0.45   0.48  0.67 0/8/0    |   8   0   0.06 |   0.30  0.12
  A_glare_sun_in           8   8   0   0   0   0   0 | -0.0056  0.0091  0.0547  0.16  0.018 |  -0.44   0.50  0.74 0/8/0    |   8   0   0.05 |   0.41  0.16
  A_rowgain3%              8   8   0   0   0   0   0 | +0.0008  0.0045  0.0512  0.09  0.008 |  -0.55   0.55  0.70 0/8/0    |   8   0   0.04 |   0.20  0.08
  A_fpn0.5                 8   8   0   0   0   0   0 | +0.0080  0.0308  0.0578  0.53  0.060 |  -0.55   0.55  0.64 0/8/0    |   8   0   0.04 |   1.29  0.50
  A_fpn1.0                 8   8   0   0   0   0   0 | +0.0023  0.0400  0.0756  0.56  0.080 |  -0.53   0.53  0.77 0/8/0    |   8   0   0.08 |   1.59  0.49
  A_fpn2.0                 8   8   0   0   0   0   0 | -0.0376  0.0790  0.1256  0.66  0.122 |  -0.56   0.56  0.55 0/8/0    |   8   0   0.18 |   2.38  0.51
  A_prnu1%                 8   8   0   0   0   0   0 | -0.0383  0.0573  0.0847  0.70  0.083 |  -0.45   0.48  0.59 0/8/0    |   8   0   0.11 |   2.27  0.60
  A_altcol3%               8   8   0   0   0   0   0 | +0.0015  0.0049  0.1209  0.04  0.006 |  -0.48   0.50  0.79 0/8/0    |   8   0   0.05 |   0.15  0.03
  A_sensor_all             8   8   0   0   0   0   0 | -0.0183  0.0625  0.0827  0.77  0.113 |  -0.51   0.52  0.61 0/8/0    |   8   0   0.13 |   2.44  0.66
  B_fpn1.0                 8   8   0   0   0   0   0 | +0.0155  0.0804  0.1099  0.80  0.138 |  -0.30   0.30  0.49 0/8/0    |   8   0   0.11 |   2.72  0.49
  B_sensor_all             8   8   0   0   0   0   0 | -0.0512  0.1280  0.1164  1.14  0.202 |  -0.32   0.32  0.54 0/8/0    |   8   0   0.21 |   3.87  0.68
  A_dirtyR_1.2             8   8   0   0   0   0   0 | -0.0014  0.0067  0.0518  0.13  0.014 |  -0.39   0.50  0.78 0/8/0    |   8   0   0.05 |   0.29  0.12
  A_dirtyR_1.8v            8   8   0   0   0   0   0 | +0.0031  0.0115  0.0552  0.21  0.020 |  -0.49   0.50  0.80 0/8/0    |   8   0   0.05 |   0.49  0.19
  A_dirtyR_2.5v            8   8   0   0   0   0   0 | -0.0069  0.0372  0.0767  0.50  0.064 |  -0.37   0.44  0.39 0/8/0    |   8   0   0.03 |   1.49  0.44
[ ok ] test_glare_sensor_and_windows
  case                     N ste lft brg non wrg amb |  d bias   d rms   sigma z rms max|d| | b bias  b rms   b z V/H/U    | top clu  t rms |  rng % rng z
  A_trees_mild_white       8   8   0   0   0   0   0 | -0.0234  0.0365  0.0712  0.56  0.069 |  +0.22   0.71  1.97 1/7/0    |   8   0   0.02 |   1.50  0.49
  A_trees_strong_white     8   8   0   0   0   0   0 | +0.0021  0.1715  0.1201  1.37  0.306 |  -0.02   0.55  1.35 1/6/1    |   8   0   0.02 |   5.37  1.16
  A_trees_strong_weak      8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  A_foliage_iso_white      8   8   0   0   0   0   0 | +0.0424  0.0626  0.0709  0.91  0.116 |  +0.17   0.44  1.04 4/4/0    |   8   0   0.02 |   2.44  0.86
  A_combo                  8   8   0   0   0   0   0 | -0.0370  0.0953  0.0888  1.18  0.221 |  -0.09   0.31  0.38 0/8/0    |   0   8   0.00 |   5.19  1.08
  B_combo                  8   7   0   0   1   0   0 | +0.0402  0.1423  0.1988  0.67  0.234 |  +0.08   0.22  0.29 0/6/1    |   0   7   0.00 |  12.21  0.70
[ ok ] test_trees_and_combination
  case                     N ste lft brg non wrg amb |  d bias   d rms   sigma z rms max|d| | b bias  b rms   b z V/H/U    | top clu  t rms |  rng % rng z
  none_plain               8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  none_trees               8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  none_person              8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  none_fpn1                8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  none_fpn2                8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  none_glare               8   0   0   1   7   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  none_trunk12             8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  none_post3               8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  none_altcol3%            8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  none_prnu1%              8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  none_foliage_turf        8   0   0   0   8   0   0 | +0.0000  0.0000  0.0000  0.00  0.000 |  +0.00   0.00  0.00 0/0/0    |   0   0   0.00 |   0.00  0.00
  88 stick-free reads: 0 reported a flagstick (left camera only: 0), 1 a band-only bearing; mean camera-rail time 1017 ms
```
<!-- readme-check:end vision-scenes -->

What the rows say (the notes that stood beside the typed table; the figures are in the
block):

* **Sway**: fast sway shows up in the claimed sigma through the scatter of the groups
  (`A_sway_1.0@3Hz`), and is worse with honest timing than with computation for nothing,
  because the groups are spread over a longer time.
* **Flag over the tip**: the top is flagged "in clutter" in every read and never offered for
  ranging (it used to be ranged with: 19 to 23 % long).
* **A person 2 m behind, a leg right behind the stick** (`A_person_behind`): the static sigma
  says so (0.34 px claimed); all eight are flagged ambiguous. **The same at 12 m
  (`B_person_behind`): not met** - no read gives a disparity.
* **A second pole 7 px beside** (`A_pole2_7px`: read; `B_pole2_7px`: **not met**, half the reads
  give a disparity, none of them takes the pole). **A dark 4 px post 14 px beside**
  (`A_pole2_14px_post`): **NOT MET with honest timing**, pinned on 64 reads (the line of the
  block: 26 of 64 where the test demands half); `B_pole2_14px_post`: not read.
* **Another line 120 px away** (`pole2_far_*`): read; the post used to be chosen over the
  stick in 12 of 12.
* **Sensor patterns**: an alternating-column gain is over-claimed many-fold (it reads as
  background structure); a column fixed pattern does not average out (`A_fpn*`).
* **A smeared right window** (`A_dirtyR_*`): read with a larger claimed sigma; a smeared LEFT
  window fails the width test instead (not tested).
* **A tree line behind**: with strong trunks the worst read is 0.3 px off at 1.4 claimed sigma
  rms; a stick only 36 grey brighter than trunks of 12 grey rms is **not met** (not read).
* **Everything at once** (`A_combo`, `B_combo`): range errors of 5 % and 12 % rms, about their
  claimed sigma.
* **Phase 3 changed the rows of the scenes with several lines** (the person scenes, the
  second poles, the sun in the strip, the combination): the line that is followed gets five
  or six groups instead of eight ("Read time: the rail-time bound").

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

Lowest visible point and base class (truth: the scene's lowest visible stick row; this
table is typed from the `b bias`, `b rms`, `b z` and `V/H/U` columns of the block above - its
first row read -0.51, 0.52 for a run that gives -0.52, 0.53):

| Scene | Class (visible / at horizon / unknown) | Bias, rms (rows) | rms / claimed |
|---|---|---|---|
| Flat green (base 0.3-0.6 row below the turf edge), A / B | 0 / 8 / 0 each | -0.52, 0.53 / -0.29, 0.29 | 0.8 / 0.5 |
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
and the USB library - is not included; generated from the final build's size table):

<!-- readme-check:begin flash-table -->
| Group | Module | text | data | bss |
|---|---|---|---|---|
| core | gl_vision | 19640 | 0 | 0 |
| core | gl_ui | 7556 | 0 | 0 |
| core | gl_solver_fit | 6942 | 0 | 0 |
| core | gl_gfx | 4762 | 0 | 0 |
| core | gl_log | 4258 | 0 | 0 |
| core | gl_solver_roll | 4242 | 0 | 0 |
| core | gl_proto | 4220 | 0 | 0 |
| core | gl_solver_aim | 4028 | 0 | 0 |
| core | gl_cal | 3565 | 0 | 0 |
| core | gl_tilt | 3264 | 0 | 0 |
| core | gl_solver | 2623 | 0 | 0 |
| core | gl_fieldlog | 2342 | 0 | 0 |
| core | gl_range | 2276 | 0 | 0 |
| core | gl_grain | 1888 | 0 | 0 |
| core | gl_math | 1772 | 0 | 0 |
| core | gl_settings | 1659 | 0 | 0 |
| core | gl_cam | 1504 | 0 | 0 |
| core | gl_gesture | 970 | 0 | 0 |
| core | gl_font_data | 632 | 0 | 0 |
| core | gl_fmt | 477 | 0 | 0 |
| core | gl_crc | 226 | 0 | 0 |
| core | gl_event | 148 | 0 | 0 |
| core | **total** | **78994** | **0** | **0** |
| drivers | ov7692 | 2123 | 0 | 0 |
| drivers | power | 1890 | 0 | 0 |
| drivers | lsm6dsv16x | 1254 | 0 | 0 |
| drivers | mx25r | 870 | 0 | 0 |
| drivers | ls013b7dh03 | 674 | 0 | 0 |
| drivers | grain_frontend | 648 | 0 | 0 |
| drivers | **total** | **7459** | **0** | **0** |
| app | gl_app | 15958 | 0 | 2050 |
| app | gl_factory | 5503 | 0 | 1156 |
| app | gl_read | 5241 | 0 | 0 |
| app | gl_usb | 2928 | 0 | 388 |
| app | gl_motion | 868 | 0 | 0 |
| app | gl_main | 24 | 0 | 322984 |
| app | **total** | **30522** | **0** | **326578** |
| all | **total** | **116975** | **0** | **326578** |
<!-- readme-check:end flash-table -->

**Phase 3, builder 3 added 2698 bytes of code and 1688 bytes of RAM** (114277 -> 116975 text,
324890 -> 326578 bss): `gl_ui` +1756 (the three states, the rule and the ratio, the INFO
screen and its layout, the recall rows), `gl_app` +898 (the recall watch, the Survey's
selection, the classification), `gl_read` +62 (the group budget), `gl_factory` -10, `gl_usb`
-8; `gl_app_t` grew by 1688 bytes, of which 1600 are the four records the Survey hands to the
estimator.

**Phase 3, builder 2 added 15690 bytes of code and 2168 bytes of RAM** (98587 -> 114277 text,
322722 -> 324890 bss; `make cross` of this phase): `gl_factory` 5513 (new; 1156 bytes of
static scratch), `gl_app` +3492 (the replay records, tilt statistics, seats, the armed
zeroing; +684 bss: one log record being assembled), `gl_fieldlog` 2342 (new), `gl_proto` +1650,
`gl_cal` +1405 (version 2, migration, CRC), `gl_usb` +370, `gl_settings` +216, `ov7692` +182,
`gl_log` +156, `gl_crc` +126 (CRC-32), `grain_frontend` +114, `gl_ui` +98, `power` +26;
`gl_app_t` grew by 328 bytes (320968 -> 321296). The boot stub is a program of its own and
is not in this table: 1184 bytes linked (`make boot-cross`).

Builder 1 of phase 3 (rev E) had added 3817 bytes of code: `gl_app` +1776 (cradle sleep, ship mode, the read's
temperature gate, charger status and its log events), `gl_ui` +633 (two states, the cradle
symbols, "TOO HOT"), `power` +558, `gl_usb` +520 and `gl_proto` +326 (three commands),
`grain_frontend` +4; and 48 bytes of RAM in `gl_app_t`.

RAM (ARM `sizeof`; core and drivers have no `.data` / `.bss` of their own, all state is in
the application object). **This table is generated and adds up by construction** (phase 3):
`make cross` compiles `tools/cross_sizes.c` with the firmware's cross flags and reads
`sizeof` of `gl_app_t` and of its parts from the object's symbol table; "everything else" is
the object less the parts listed. (The table that stood here was typed, and its rows summed
to 1.5 kB more than the object they were said to be inside.)

<!-- readme-check:begin ram-table -->
| Object | Bytes | Note |
|---|---|---|
| **`gl_app_t`** (bss of `gl_main`) | **322984** | the sum of the rows down to "everything else" |
| - camera pipeline `gl_read_t` | 303348 | the next four rows |
| - - strip buffers `img` | 184320 | FOUR 96 x 480 strips, one L R R L group; the 640 x 96 band uses the same memory |
| - - `gl_vis_band_work_t` | 47360 | band analysis |
| - - `gl_vis_stick_work_t` x 4 | 69520 | one per strip of a group (17380 each) |
| - - the rest of `gl_read_t` | 2148 | band result (380), sequence state, accumulators, the result |
| - LCD: `gl_gfx_t` + driver `gl_lcd_t` | 2305 + 2060 | frame buffer and clip table; the driver's shadow copy |
| - `gl_proto_t` | 2096 | two frame buffers |
| - solver inputs `gl_measurements_t` x 9 | 3600 | the read shown (400), 4 stored Survey placements (1600), the up to 4 handed to the estimator (1600; phase 3: placements behind the ball are left out) |
| - `gl_solver_work_t` | 6160 | work area of the patch fit and its record (`gl_patch_fit_t`, 224); the aim solve needs none |
| - `gl_store_t` | 1092 | settings and calibration blobs |
| - `gl_motion_t`, `gl_ui_t`, `gl_ui_view_t`, `gl_estimate_t`, `gl_factory_t`, `gl_log_t` | 344 + 48 + 76 + 112 + 112 + 44 | |
| - everything else | 1587 | drivers' state, calibration records, settings, survey, tilt, zeroing, recall, field-log bookkeeping, padding: `gl_app_t` less the rows above |
| static scratch in `gl_app.c` + `gl_factory.c` + `gl_usb.c` | 2050 + 1156 + 388 = 3594 | one raw-strip log record, one field-log record being assembled; the factory's buffers; two raw grain measurements |
| **all `.bss` of core, drivers and app** | **326578** | = `gl_app_t` + static scratch (the size table of `make cross`); core and drivers have none |
<!-- readme-check:end ram-table -->

Not in that table: the STM32 backend (`gl_hal_stm32u5.o` as compiled by `make cross-hal`: the
block under "STM32U5 backend"; its USB file, compiled by no target, is estimated at two 1 kB
rings and a packet buffer; the vendor HAL's own data is not counted) and the main stack (4096
bytes recommended, below). **The total is about 334 kB of 786 kB** and does not fit SRAM1 +
SRAM2 (256 kB): see "STM32U5 backend", linker script.

The largest stack frames of the final build (`-fstack-usage`, `-Os`, bytes; generated):

<!-- readme-check:begin stack-frames -->
```
672  gl_vis_band_analyse                static
464  gls_fit_patch                      static
432  tempco_.constprop                  static
376  gl_factory_cmd                     static
336  gl_app_run_once                    static
328  centroid_row_                      static
304  gls_roll                           static
304  gl_cam_model_init                  static
304  fieldlog_read_.constprop           static
296  gl_vis_stick_refine                static
280  set_cal_                           static
272  gls_solve_kernel                   static
248  tilt_log_                          static
248  measure_all_                       static
240  gl_read_step                       static
240  fit_lm_                            static
224  estimate_                          static
224  do_actions_.part.0                 static
216  gl_usb_service                     static
216  gl_cal_tilt_decode                 static
200  gl_store_mount                     static
200  gl_solver_roll                     static
200  gl_lcd_update                      static
192  gl_tilt_tempco_fit                 static
```
<!-- readme-check:end stack-frames -->

The frames the chains below are made of (from the block, and from the `.su` files of the
same build for the ones that are not among its 24): `gl_vis_band_analyse` 672, `gls_fit_patch`
464, `tempco_` 432, `gl_factory_cmd` 376, `gl_app_run_once` 336, `centroid_row_` 328,
`gls_roll` 304, `fieldlog_read_` 304, `gl_vis_stick_refine` 296, `gls_solve_kernel` 272,
`measure_all_` 248, `gl_read_step` 240, `fit_lm_` 240, `estimate_` 224, `do_actions_` 224,
`gl_usb_service` 216, `gl_tilt_tempco_fit` 192, `screen_result_` 152, `gl_ui_render` 128.
Phase 3 moved `gl_app_run_once` from 312 to 336, `do_actions_` from 216 to 224 and the result
screen from 128 to 152 (three layouts); the temperature fit of the factory commands is a new
deep chain. Worst chains (sums made by hand from those frames; libm and the HAL not included):

| Chain | Bytes |
|---|---|
| run_once -> actions -> estimate (Survey entry) -> estimate -> aim solve on the patch -> kernel -> pace solve -> trial -> roll -> acceleration (336 + 224 + 40 + 224 + 80 + 272 + 104 + 112 + 304 + 40) | **1736** (the deepest; 1704 at the end of phase 2) |
| run_once -> actions -> estimate -> patch fit -> Levenberg-Marquardt -> residuals (336 + 224 + 40 + 224 + 464 + 240 + 112) | 1640 |
| run_once -> USB service -> protocol -> factory command -> temperature fit -> least squares (336 + 216 + 88 + 376 + 432 + 192) | 1640 (in the cradle only) |
| run_once -> read step -> stick refinement -> measure_all_ -> centroid_row_ (336 + 240 + 296 + 248 + 328) | 1448 |
| run_once -> read step -> band analysis -> selection (336 + 240 + 672 + 24 + 28) | 1300 |
| run_once -> actions -> solve -> replay record -> encode -> log append -> flash driver (336 + 224 + 304 + 56 + 88 + 40) | 1048 |
| run_once -> read step -> raw-strip hook -> log append -> flash driver | about 900 |
| run_once -> draw -> render -> result screen -> text and line primitives (336 + 128 + 152 + under 250) | under 870 |
| run_once -> charge supervision -> temperature measurement (336 + 24 + 24) and the HAL below | about 390 + HAL |
| init -> store mount -> log walk -> flash driver | about 500 |

Add the HAL's own frames below the drivers (not measured: the HAL's sources were not compiled) and interrupt frames
(104 bytes each with FPU state, handlers are short; the backend's own frames, as compiled:
`clocks_init_` 248 and below it `clocks_osc_` 112, at start-up and after every Stop 2;
`gl_hal_clock_set` 144; everything else 64 or less). A 4 kB main stack leaves a factor of 2.4
over the deepest chain (1736 bytes, the solver's), before libm and the HAL.
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
683,040 rows - 1,497,340 values, **0 differ**; 960 more refinements on strips of only 2 to 4
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
| **a person behind the stick** (three lines probed; phase 3: 3 + 5 groups) | 32 (44 until phase 3) | 197,913,409 | 88,052,456 | 88,050,771 with 44 strips (phase 2; not profiled again with 32) | 67.23; 2.56 s (84.03; 3.36 s until phase 3) |
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

* **a Quick Read shows its result 4.1 - 4.8 s after the marker comes to rest** (4.4 s nominal; 4.15 / 4.45 / 4.84 s
  in the final build of phase 3, "End to end"),
  with the camera rail on for 2.2 - 2.8 s. These are the figures DESIGN_SPEC now states
  (amendment E15, taken from this model; "about three seconds" before). Of
  the 4.4 s, 1.85 s are stillness and the tilt read, 1.6 s the cameras' power-up, settling
  and 33 frames, and 1.0 s the computation (0.8 s) with the frame periods the captures wait
  for it. The vision of phase 1 would have needed 1.4 - 2.7 s of computation for the same read
  by the same arithmetic instead of 0.5 - 1.1 s (not simulated);
* a near stick: rail on for 2.4 - 2.7 s at the nominal factor (2.66 s in `make bench-vision`
  for the 3 m and the 1.5 m scene; 2.42 - 2.46 s in the end-to-end sweep of 2.25 to 3.75 m),
  where it was 3.0 - 3.3 s before the stick's shoulder stopped being probed; **several real
  lines no longer lengthen the read** (phase 3): each probed line costs a group, and the line
  that is followed gets what is left of eight - 2.56 s with a person behind the stick, where
  it was 3.36 s, outside the 2.2 - 2.8 s the specification states ("Read time: the rail-time
  bound" has the runs and the cost in accuracy);
* without the PLL (it failed to lock, or the backend's clock code does not work as written:
  **not verified**) the same read takes 6.0 s with the rail on for 3.8 s;
* the putt estimate is 0.5 % of a read, but a slope near the limit of what the green holds can
  cost seconds. The application now gives the solve a budget of 300,000 RK4 steps (plus the
  roll in progress): 105 million instructions by the cost table, **1.3 s at 160 MHz and the
  nominal factor, 1.0 - 2.0 s over the range** (4.4 s at 48 MHz), after which the result is
  "no solution" (`NOT SOLVED` or `TOO STEEP`, no line: phase 3). Without the budget the costliest estimate found needs
  575,247 steps (202 million instructions, 1.9 - 3.8 s) and the loop counters bound it only at
  1.35e9 instructions ("Solver"). In `tests/test_e2e_putt.c` the 7 % cross slope at Stimp 14
  took 137 trial rolls and 55,471 RK4 steps: 19.5 million instructions by the cost table,
  0.24 s.

The firmware's own code is 116975 bytes of the 2 MB flash before libraries, and 326578 bytes of `.bss`, of which `gl_app_t` is 322984 bytes ("Memory"; 94.8 kB of code at the end of phase 2, 98.6 kB after builder 1 of phase 3, 114.3 kB after builder 2). In phase 2, builder 2 added 2.2 kB: result screen, charge gate and NTC, settings, hand-over; builder 3 added 3.5 kB: the faster vision is 3.0 kB larger, the selection 0.3 kB; the phase-2 review added 1.5 kB: 0.7 kB in the solver, 0.4 kB in the UI and graphics, 0.5 kB in the application), plus 6.7 kB for the STM32 backend as compiled by `make cross-hal` and the vendor's HAL and USB library, which were not compiled. The link probe of `make cross` (firmware objects + newlib's libm and libc, no HAL, no start-up code) has 107,244 bytes of text.

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
| MCU | `GL_PROV_LPTIM_PWM_RUNS_IN_STOP2`, `GL_PROV_USB_CRYSTALLESS_HSI48_CRS`, `GL_PROV_SHIP_MODE_IS_SHUTDOWN`, `GL_PROV_USB_WAKE_FROM_STOP2` (0) | EXTCOMIN in Stop 2 (if 0 the application stays in idle sleep while the display is on - also in the cradle sleep, which then draws about 1 mA: still under the termination threshold, not measured); crystal-less USB; what survives Shutdown and what wakes from it; whether a USB resume wakes the core from Stop 2 (0: Stop 1 while USB is in standby). The pin assignment is no longer the firmware's: it is the netlist's pin map, whose own PROVISIONAL statements (ROM-loader pin list, UCPD pads, electrical limits) travel in the generated header |
| IMU | `GL_PROV_IMU_MARKER_{X,Y,Z}_AXIS`, `_SIGN`, `GL_PROV_IMU_WAKE_THRESHOLD_MG`, `GL_PROV_IMU_DRDY_PULSED` | mounting orientation on the PCB (identity is a placeholder), wake threshold, data-ready mode |
| Flash | `GL_PROV_MX25R_PROG_TIMEOUT_MS`, `_ERASE_TIMEOUT_MS`, `_DP_DELAY_US`, `_SPI_HZ` | timing |
| Grain | `GL_PROV_GRAIN_RED_ANODE_ON_LOW_PIN`, `_SETTLE_US`, `_ADC_AVG`, `_ADC_SAMPLE_US`, `_POWER_SETTLE_MS`, `_MOD_THRESHOLD_DEFAULT`, `_MAX_EQUIV_SLOPE`, `_HARMONIC_SIGN`, `_KAPPA_BENT`, `_KAPPA_POA`, `_KAPPA_BERMUDA` | charlieplex wiring (proposal), settling, and the unproven physics; the acceptance threshold used is always the one in the calibration record |
| Power | `GL_PROV_BATT_LOW_MV`, `_CRITICAL_MV`, `_FULL_MV`, `_EMPTY_MV`, `_DIVIDER_RATIO`, `GL_PROV_BATT_STORAGE_MV` | cell thresholds (no cell data sheet) |
| Charger BQ25101 (E1) | `GL_PROV_BQ25101_ICHG_UA` (19820), `_TERM_FRACTION` (0.10), `_VREG_MV` (4200), `_VREG_WARM_MV` (4060), `_RECHARGE_DROP_MV` (100), `_T_COLD_C` / `_T_COOL_C` / `_T_WARM_C` / `_T_HOT_C` (0 / 10 / 45 / 60), `_TS_LOW_DISABLES` (1), `_TS_OPEN_IS_TTDM` (1), `_SAFETY_TIMER_H` (10), `_CHG_LOW_ON_RECHARGE` (1), `_VIN_MIN_MV` (4450) | **no data sheet was read**: the specification's text (current, termination, JEITA behaviour), the search extracts quoted in the netlist notes (TS low disables, TS open = test mode), memory of the family (recharge threshold, safety timer, CHG on a recharge). The simulator's charger model and the status inference use these and nothing else. The temperature corners are the usual JEITA degrees; the part's real thresholds are voltages on TS and depend on its bias current against this NTC: release gate |
| The firmware's charge supervision | `GL_PROV_CHARGE_TEMP_MIN_C`, `_MAX_C` (0, 45), `_GUARD_C` (1.5 K), `_HYST_C` (2 K), `_MAX_DISAGREE_C` (10 K), `GL_PROV_CHARGE_MAX_MS` (6 h, E32), `_RESTART_MV` (4000), `_DONE_MIN_MV` (4040) | the window the specification gave the cell; the guard band (from the tolerance budget computed in `test_drv_power.c`; it does not cover a cell-to-NTC gradient or the part's real R-T curve); our choices for hysteresis, restart and "done" |
| E13 | `GL_PROV_READ_TEMP_MAX_C` (60), `_HYST_C` (3 K) | the specification's limit, applied to the reading; our hysteresis |
| Cell NTC2 (E2) | `GL_PROV_NTC_R25_OHM` (10 k), `_B_K` (3380), `_SERIES_OHM` (10.0 k), `_SETTLE_US` (500), `_ADC_AVG` (8), `_ADC_SAMPLE_US` (20), `_OPEN_FRACTION` (0.98), `_SHORT_FRACTION` (0.02), `_IDLE_MAX_FRACTION` (0.05) | Murata NCU15XH103F60RC, nominal R25 and B(25/50), both taken as 1 %: **every R-T number in the firmware and in its tests is derived from the one-B equation with these two constants; no R-T table of the part has been read**. The netlist puts no capacitor on the node; the 500 us are margin. The detection thresholds are ours |
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

Rewritten at the end of phase 3. Every item is marked with what it waits for:
**[NEEDS HARDWARE]** a board or a measurement; **[NEEDS A DATA SHEET]** a document nobody here
has read; **[OWNER DECISION]** a choice that is the product's, the hardware's or the
estimator's owner's; **[NOT MET]** a requirement this firmware does not meet, pinned by a test
with the measured number. The numbered decisions are in the next section; this list is what
does not exist or has not been shown.

**Nothing has run on hardware**

* **[NEEDS HARDWARE] No hardware run of anything, and no linked application image.** The main
  file of the STM32 backend compiles against the vendor's headers (`make cross-hal`); its USB
  file is compiled by no target; the HAL sources, start-up code, linker script and the USB
  board glue (`usbd_conf.c`, `usbd_desc.c`) do not exist here ("STM32U5 backend": what a
  flashable image takes). The boot stub links and has never run. Timing on the target
  (vision run time, SCCB bit-bang, Stop 2 wake latency at 240 Hz) is unmeasured: every time
  in this file is the simulator's, with computation charged through an estimated factor
  (1.5 to 3 cycles per host instruction).
* **[NEEDS HARDWARE] The compute-time model is not calibrated**: the factor itself; the cost
  of the main loop, the drivers and the IMU filtering between the trace points (charged
  nothing); the PLL lock and voltage-range switch times; instruction counts of the
  cross-compiled code (no instruction-set simulator was used).
* **[NEEDS HARDWARE] The solver on the target.** Tested on the host only; its run time on the
  Cortex-M33 is an estimate, and newlib's single-precision libm has not been compared with
  the host's (open issue 26).
* **[NEEDS HARDWARE] [NEEDS A DATA SHEET] The rev E power behaviour.** The charger is a model
  with provisional thresholds; every supply current is a data-sheet figure from memory or a
  guess; Shutdown, the wake-up pin, the VDDUSB monitor, `UCPD_DBDIS`, Stop 1 under a suspended
  USB bus and the session override exist in the backend by inspection only. Not verified
  either: the clock switch (PLL, voltage range, booster, flash latency), that PH1 is an FT
  pin, ADC1_IN13 on PC4, the NTC's settling time, the real part's R-T curve against the
  B-parameter equation, the thermal coupling between the cell and the NTC.
* **[NEEDS HARDWARE] The boot stub's six release gates** ("Boot stub"): loader entry, write
  protection and option bytes, vector relocation with a linked application, backup registers
  and the watchdog across Shutdown and the loader, CRC time, what the host sees.
* **[NEEDS HARDWARE] Recall's wake-up.** That a tap trips the IMU's wake-on-motion at the
  provisional threshold; how long the IMU takes from that interrupt to its first sample (a
  movement that is over before it is not seen by the recall rule); the accelerometer's offset
  drift against the 4 mg limit.
* **[NEEDS HARDWARE] Gestures.** Thresholds are guesses; taps are detected in software from
  the 240 Hz stream. The gesture maths is unit-tested, the thresholds are not field-tested.
* **[NEEDS HARDWARE] Fuel gauging:** the percentage is a straight line between two
  provisional voltages.

**Shown not to work, or not to meet a requirement (each pinned by a test)**

* **[NOT MET] Ship mode current:** 12.9 uA in the supply model against 5 uA (open issue 33).
* **[NOT MET] A silent host on a running USB bus loses the marker** until it is re-docked
  (open issue 34).
* **[NOT MET] The firmware's 45 C charge limit when no firmware runs** (ROM loader, a hung
  firmware): the model's charger keeps its own 0 to 60 C window (open issue 2); with NTC1
  open and no firmware there is no window at all.
* **[NOT MET] The 6 h backstop does not see a recharge** if the charger's status line shows
  the first cycle only (a variant of the model; open issue 39).
* **[NOT MET] Sleep current with a lit underside:** 25.9 uA at the pads (E27 defines the limit
  with the underside dark).
* **[NOT MET] Survey: a placement behind the ball is not used** for the result at the ball
  (open issue 18).
* **[NOT MET] One reference vector in 340** is shown as a normal result where the reference
  at its own tolerance keeps a near miss; four more are `TOO STEEP` with a dashed line where
  the reference has no line ("Phase 3, builder 3").
* **[NOT MET] Vision cases** (pinned by `tests/test_read.c`, the block under "Vision"):
  sticks under about 0.7 px at under 10 % contrast; a 0.8 px stick with a person, a post or a
  second pole within a few pixels; a low-contrast stick against strong tree trunks;
  following a thin stick into rough turf; the lowest point behind tall ragged grass; and,
  with honest timing, a 1.5 px stick with a post 14 px beside it (26 of 64 reads give a
  disparity). From the phase-2 review and not looked into: at 2 to 3 m on a putt that is
  level along its line the hole is read 3 to 5 mm low, and at 0.6 m the flagstick is refused
  (open issue 30).
* **[NOT MET] Found by the honest timing:** the result comes 4.45 s after the marker is at
  rest, not within the 4.0 s the end-to-end test once allowed (the specification now states
  4.1 to 4.8 s from this model, E15; the final build gives 4.15 to 4.84 s); the class of the
  stick's base at the margin of "visible" flips with the frame noise (open issue 22); a
  drift that reverses inside a group of four strips gives a disparity 0.04 px off under a
  claimed 0.05 px and is not noticed (open issue 23).
* **[NOT MET] Solver tolerance on long putts:** beyond 15 m the single-precision roll noise is
  inside `tol_miss_m` (open issue 25).
* **[NOT MET] Read time at the high compute factor for a near stick** (the review's 2.99 s of
  rail at 1.5 m, factor 3; not repeated). Reads with several lines are bounded since phase 3.

**Not implemented**

* **[OWNER DECISION] Camera exposure and clocking.** No exposure, gain, PLL or frame-rate
  register is written (no verified values): the sensors run on their reset settings; dark
  frames are ordinary exposures (open issue 44). **[NEEDS A DATA SHEET]** for the values.
* **[OWNER DECISION] Factory procedures beyond what "Station tests" lists as existing:** a
  four-position level zero; the stereo calibration procedure and its PC fit; an IMU
  self-test; the flash's identity read-out; a "hold the camera rail on" command;
  fixed-exposure dark frames; tilt logging at intervals.
* **[OWNER DECISION] An on-unit sign of a missing calibration** (open issue 49).
* **[OWNER DECISION] The regulatory text** of the INFO screen: a placeholder
  (`docs/COMPLIANCE.md` supplies it; a release build fails until then), like the USB ids.
* **[OWNER DECISION] Grain.** Wired through and off by default; with GRAIN ON the line moves
  by what the measured grain and the grass's coefficient say, and nothing here shows that
  this is right (`GL_PROV_GRAIN_KAPPA_*`); no on-device noise-floor procedure.
* **[OWNER DECISION] Stimp by watching a rolled ball** (optional in DESIGN_SPEC): not started.
* **[OWNER DECISION] Signed firmware images**; an update path other than ST's loader (open
  issue 47).
* **Estimator results that no simulated read produces** (pace limited, the straight fallback,
  a kept near miss, a fit on its iteration limit, a poor horizon): only their mapping to the
  screen is tested, by composing the view from such an estimate. [NEEDS HARDWARE] in the
  sense that only field reads will show how often they occur.
* **Vision speed beyond the nominal read**: a stick whose line is wider than 1.2 px costs 72
  to 87 million host instructions where the nominal read costs 58; nothing was tuned for the
  Cortex-M33 itself (no fixed-point path, no CMSIS-DSP, no assembly). [NEEDS HARDWARE] to
  know whether it matters.
* **Four findings of the phase-2 review are not fixed** (9, 10, 20, 32) and five in part (2,
  3, 8, 24, 25): "Phase-2 review: what was fixed" and the open issues it names.

## Open issues that need a decision

Rewritten at the end of phase 3. The numbers are the ones this file has always used (other
sections refer to them), so closed issues keep theirs and are marked **[CLOSED]** with what
closed them. Every other item says what it waits for: **[NEEDS HARDWARE]** a board or a
measurement, **[NEEDS A DATA SHEET]** a document nobody here has read, **[OWNER DECISION]** a
choice of the product's, the hardware's, the specification's or the estimator's owner,
**[NOT MET]** a requirement that is not met, pinned by a test with the measured number. 52 to
58 are new in phase 3 (builder 3).

Hardware and system decisions first: none of them can be closed in firmware.

1. **[NEEDS HARDWARE] [OWNER DECISION]** **Read time, and the charge of a read.** The vision is down from 145 to 58 million host
   instructions for the nominal read (bit-identical results), and the simulator charges
   computation its time: a Quick Read shows its result 4.1 - 4.8 s after the marker is at rest
   (4.4 s at the nominal factor; 6.0 s if the PLL does not lock; 4.15 / 4.45 / 4.84 and 6.03 s
   in the final build of phase 3, 0.02 s more than the run E15 was taken from) and the camera rail is on for
   2.2 - 2.8 s. DESIGN_SPEC now states exactly these figures (amendment E15; "about three
   seconds" before), so the specification follows the model; nothing has been measured.
   **Reads outside those figures:** near sticks at the high factor (the review measured
   2.99 s of rail and 5.0 s to the result at 1.5 m, factor 3; not repeated). A person behind
   the stick or two real lines in the band (3.4 s of rail until phase 3) are bounded now: the
   read has eight groups in all (issue 56 is the decision that hides in that). The near-stick
   case the review found (a third of the reads between 2.25 and 4.5 m, 0.6 s longer) is fixed. **The charge**: the review compared the model's 226 mAs per read (86 mA
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
2. **[NOT MET] [NEEDS A DATA SHEET]** **Charger when the MCU is not in control.** ANSWERED IN HARDWARE by amendment E1, and the
   firmware now drives that hardware (phase 3): the BQ25101 enforces its own temperature
   window with its own thermistor, whatever the MCU does. What is left, each pinned by a test
   against the MODEL of the charger ("Charger and cell temperature (rev E)"):
   (a) **the firmware's window is 0..45 C, the charger's own 0..60 C** (4.06 V above 45 C).
   In the ROM loader and with a hung firmware a cell between 45 and 60 C is charged, to
   4.06 V: 600 s of 600 s and 33 s in the tests. Whether the cell allows that is its data
   sheet's answer; if not, the charger's thresholds have to move (its TS network), not the
   firmware. (b) **An open NTC1 removes the hardware window silently** (search extract: the
   part's test mode); the firmware notices and stops only while it runs. Board test must
   prove NTC1; `GL_CMD_SET_CHARGE` exists for the station that does it. (c) **In the ROM
   loader the charge never terminates** (the loader draws more than 2 mA): what ends it is
   the charger's own safety timer, if it has one (from memory). (d) Every threshold of the
   model is PROVISIONAL: the release gate "BQ25101 thresholds against the NTC curve" stands.
3. **[NEEDS HARDWARE]** **Both cameras on the shared bus at power-up.** Unless PWDN tri-states the OVM7692 pads
   (unconfirmed, `GL_PROV_OV7692_PWDN_TRISTATES_OUTPUTS` = 0), both sensors drive the eight data
   lines and the three sync lines against each other for 14.4 ms of every power-up (6.4 ms of it
   with one streaming) before the firmware can switch one off through SCCB. Writing register
   0x0C first does not shorten this, because the software reset re-enables the pads. Options
   for the hardware: confirm the PWDN behaviour on the bench, series resistors, a bus switch, or
   separate rail enables. The simulator measures the overlap and the driver test asserts it, so
   a change is visible.
4. **[NEEDS A DATA SHEET]** **ROM-bootloader pins on camera nets.** PB9 (DCMI D7) and PA6 (PIXCLK) are pins the ROM
   bootloader may drive or sample (table from memory of AN2606: verify). In DFU mode the camera
   rail is off, so a driven pin back-feeds the sensors through their protection diodes. Either
   move the nets or accept and document the level; `tests/test_pins.c` prints the two rows.
   **Rev E: answered by the netlist** (NETLIST_NOTES 3.5: both nets end on unpowered camera
   pins through 220 ohm, about 6 mA expected, 19.5 mA bound; the levels are PROVISIONAL). The
   charger's status line has its 100 kohm pull-up to V2V8 and sits on PA15, the LCD chip select
   has its pull-down (`GL_PINS_RESET_TABLE`).
5. **[NEEDS A DATA SHEET] [OWNER DECISION]** **Charge temperature.** The cell NTC is now the input, with the die sensors as a
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
6. **[NEEDS HARDWARE]** **Stereo calibration term.** `GL_PROV_STEREO_CAL_SIGMA_PX` = 0.05 px is a guess and it is
   now the largest part of the claimed range uncertainty on every clean scene (2.3 % at 6 m,
   3.8 % at 10 m). It has to come from the calibration fixture's repeatability.
7. **[NEEDS HARDWARE]** **Lens blur.** The "too wide for its disparity" test needs the blur; until it is measured
   the range 0.45-0.80 px is assumed, which rejects a 3 px post at 25 m but would not reject a
   2 px one, and rejects a real stick seen through a smeared LEFT window.

Product decisions:

8. **[OWNER DECISION]** **The weaker tiers.** A read can end as "left camera only" (bearing and elevations, no
   disparity; the estimator ranges it from the angular height if top and base of the stick are
   visible, otherwise the dialled distance is applied along the measured bearing) or as
   "band-only bearing" (not used and not logged). Confirm that a single-camera stick, which cannot be checked against a disparity,
   should be aimed at; and whether `ambiguous` should block the result rather than lower the
   confidence figure (x 0.6). As built since phase 3: `1 CAMERA` and `2 LINES SEEN` are NORMAL
   results (solid line, the bar at 0.6 of the confidence each) with their message - they are
   weaker measurements, not fallbacks of the estimator; a single camera that could not range
   the stick is `NO RANGE`, which is APPROX (dashed). Whether the first two should be APPROX
   as well is this decision.
9. **[OWNER DECISION]** **Base of the stick for ranging.** "At horizon" covers a base just visible on a flat green
   and one hidden behind a crown. For RANGE (and for learning the stick height) the application
   treats the lowest visible point as the base in both cases, with the read's own uncertainty
   for it (0.5-0.6 row at the turf edge, more with a hint of a continuation) on top of 0.3 row;
   for the SLOPE use the solver receives the strict flag. The estimator's owner should confirm.
10. **[OWNER DECISION] [NEEDS A DATA SHEET]** **Pin assignment: closed for the firmware by the netlist (rev E).** The firmware no longer
    proposes pins: `hal/stm32u5/gl_pins.h` is generated from `../electrical/gl1_main/pinmap.json`
    by `make pins` (20 signals moved against the rev C2 proposal; the firmware's own choice of
    `NTC_BIAS` on PH3-BOOT0 was replaced by `CAM_R_PWDN` there, `NTC_BIAS` is on PC5). There is
    **no spare MCU pin** (51 signals and the BOOT0 strap on 51 pads). Still open, and not
    firmware's to close: the layout step may exchange PROPOSED / CHANGED pins (then `make pins`
    and nothing else); the ROM-loader pin list, the UCPD pad behaviour and the pins' electrical
    limits are PROVISIONAL in the pin map (6 statements, quoted in the header).
11. **[OWNER DECISION]** **Raw-strip logging level ALL keeps the camera rail on for about 41 s per read** (48 s in
    all; about 1 mAh of a 43 mAh cell, and heat). Level FIRST costs 2.6 s. If ALL is wanted in
    the field it needs a different capture plan (cameras off between groups) or less data.
12. **[OWNER DECISION]** **Watchdog in Stop mode, and before `main()`.** The independent watchdog keeps running in
    Stop 2, so the sleeping device wakes every 16 s for a few microseconds. Freezing it in
    Stop by option byte would avoid that at the price of no supervision while asleep - and
    since the phase-2 review that wake-up is also what bounds a lost VBUS edge (15.5 s at
    worst), so it should stay. The watchdog is started by software, first thing in
    `gl_hal_init()`; a hang before that is covered only if the **hardware-watchdog option bit
    (`IWDG_SW` = 0)** is programmed in production. To decide, and to put into the production
    programming procedure; it cannot be set from here. Related: after 8 failed IMU
    recoveries the firmware deliberately lets the watchdog reset it; a unit with a dead IMU
    then resets every 32 s while awake. Decide whether it should give up and sleep instead.
13. **[NEEDS A DATA SHEET] [OWNER DECISION]** **Idle camera kept awake** during L R R L (deviation from the letter of DESIGN_SPEC, see
    Drivers) and **OVM7692 reset output size** (the public driver's comments suggest 384 lines).
14. **[CLOSED]** **Zeroing over USB.** Closed by builder 2 of phase 3: `GL_CMD_LEVEL_ZERO` arms a zeroing
    for a named seat, which runs by itself once the marker lies still out of the cradle and
    whose result is fetched at the next docking. `START_CAL ZERO` in the cradle still answers
    `GL_ERR_STATE`; the user's zeroing is still started from the dial.
15. **[OWNER DECISION]** **DESIGN_SPEC text:** still to correct: the register table's "INT pins pulsed" (latched is
    used and selected explicitly). The rail table of section 4 still names the series Schottky
    and the MCP1700-3.3 for VDDUSB, which E25 / E26 replace (the supply model follows the
    amendments); `pinmap.json` stated "amendments E1 to E16" as its specification until it was
    re-issued at the end of phase 3 (now "E1 to E34 (in the netlist: E1 to E4 and E24 to E28)",
    quoted as it is in the generated header). `mechanical/README.md` step 16 still says
    13.5 degrees for test gate 2 (issue 48). `sim/results/REPORT.md` said "hardware revision C"
    and described the display as stepping in 0.94 degree: corrected in its generator in phase
    3, without a new run (issue 58).
16. **[CLOSED]** **State name.** `CAL_FLIP` of the original state list is now `CAL_ZERO` (rev C wording); the
    storage fields `flip_bias_*` and `GL_CAL_TILT_FLAG_FLIP` keep their names because they are the
    record format. The read log record is unchanged: a left-camera-only read is a record with
    the stick flag set, zero disparity and zero repeats.
17. **[OWNER DECISION]** **Worst-case solve time: bounded now, by a budget that is this firmware's choice.** A
    typical putt estimate is a few milliseconds at 160 MHz (estimate). A read on a slope near
    the limit of what the green holds, where neither the fitted patch nor its secant plane can
    be solved, ran to 0.58 million RK4 steps on the host with the reference's limits alone
    (1.9-3.8 s at 160 MHz), and the loop counters bound it only at 3.8 million (13-25 s). The
    application now sets `max_steps` = 300,000 (1.0-2.0 s at 160 MHz, 3.3-6.6 s at 48 MHz;
    not in the reference), keeps the fast clock through SOLVE and refreshes the watchdog
    before it. A solve that runs out has no solution: `NOT SOLVED` (or `TOO STEEP`), no line
    (DESIGN_SPEC E33, which also states the 300,000). **To decide:** whether 300,000
    is the right number (the costliest solve WITH a result among the vectors needs 208,952 in
    single precision; a smaller budget ends more hard putts unsolved, a larger one keeps the
    golfer waiting), and whether the reference should have the same option so that the two can
    be compared at the limit.
18. **[OWNER DECISION] [NOT MET]** **Survey: where is the ball, and when is there a line.** DECIDED by amendment E29 and
    implemented (phase 3): the placement the marker stands on is the ball; a line after
    every placement; `PUT AT BALL` is gone. **What is left, NOT MET and pinned
    (`test_survey_second_drop`):** the estimator has no station for a placement farther from
    the hole than the ball (it clamps stations to the line from the ball to the hole), so the
    application does not hand such a placement over, and a golfer who walks from the ball
    toward the hole gets at each stop the putt from that stop, made of the placements from
    there to the hole. E29's own order (toward the ball) uses every placement. To decide,
    for the estimator's owner: stations behind the ball (an extrapolation of the same
    plane-plus-curvature model), so that "fitted to all placements" holds in any order; and
    for the product owner: whether `Dn` should count the placements USED instead of the
    stops, whether a fifth placement should say that the Survey is over (it is silently a
    plain read), and whether a Survey should survive the 45 s of a result (it ends when the
    marker sleeps).
19. **[OWNER DECISION]** **A range that nobody measured or dialled.** When the flagstick is found but cannot be
    ranged and nothing is dialled, the estimator solves for its 3 m default. As built the
    screen shows `--`, `NO RANGE`, `BREAK ?`, a DASHED line and `APPROX` (the APPROX state). The alternative is to ask for
    the distance, as the no-flag case does. Decide which.
20. **[OWNER DECISION]** **Distance shown is the cameras' distance to the stick**, which is about 29 mm more than
    the ball's distance to the hole (the lenses sit behind the ball). Not corrected: it is
    about one 0.1 ft step of the display, and a known offset.
21. **[OWNER DECISION] [NEEDS HARDWARE]** **Confidence: the factors, and what the bar means.** 0.6 (one camera), 0.6 (ambiguous),
    0.7 (fit not converged), the disparity-sigma factor and the caps (0.2 best effort, 0.09
    flag out) are this firmware's choices; nothing calibrates them against how often such
    reads are wrong. They need field data. **And the bar itself does not do what a golfer
    would expect of it** (phase-2 review): the estimator's confidence is essentially the
    chance of holing, so a clean read has 5 boxes at 1.5 m, 3 at 3 m, 1 at 4.5 to 6 m and
    none from 9 m on, and most fallbacks have the same 0 or 1 box. The specification asks for
    a "low-confidence indicator" in the flag-out mode. Since phase 3 the bar is drawn for
    NORMAL results only (every fallback has `APPROX` in its place and a dashed line), so the
    bar no longer has to tell a fallback from a clean read; what it still does not do is
    tell a GOOD clean read from a poor one at the same distance. **To decide:** an indicator of the QUALITY of
    the read relative to what a clean read achieves at that distance (the ratio to the
    clean-read confidence, or the 1-sigma lateral error at the hole in cups), with the holing
    chance as a separate number if it is wanted.

22. **[NOT MET] [OWNER DECISION]** **The base of the stick near the margin of "visible"** (found by the honest timing). The
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
    switch itself is unchanged. Since E29 the placement this was found on (3 m from the hole)
    is the BALL of its result, so the flip decides between `PLAYS n` and `PLAYS n?` there.
23. **[NOT MET] [NEEDS HARDWARE]** **Motion that is not uniform over a group.** The L R R L correction removes a steady
    drift exactly; a reversal inside the 0.13 s of a group leaves that group wrong by tenths
    of a pixel (0.039 px in the read against a claimed 0.05 px) and no check sees it: the two
    left strips and the two right strips of a group are not compared with what a uniform
    motion predicts. The instantaneous reversal of the test is harsher than a swaying stick
    (the sway rows under "Vision" stay within their claimed sigma), so this may be acceptable;
    it is not measured on anything real.

From the phase-2 review (the findings that were not, or not wholly, fixed):

24. **[OWNER DECISION]** **Near the critical slope the aim is not determined** (finding 2; "Solver"). A change of
    one microradian in an input flips the reference's aim by more than a display step in
    about 3 % of the reads there (the reviewer's figure), and a best-effort direction is an
    arbitrary iterate. The port follows the reference exactly and the brief forbids changing
    its numerical behaviour. **The display deals with it since phase 3** (E31, E33): from 0.80
    of the critical slope a solved result is `TOO STEEP` with a dashed line, and a
    best-effort aim is not drawn at all. Still for the estimator's owner: a search that is
    stable there (a continuation in the launch speed, or reporting the INTERVAL of aims that
    hole the putt).
25. **[NOT MET] [OWNER DECISION]** **A solver tolerance that does not grow with the putt** (finding 3). In single precision
    `tol_miss_m` = 2e-4 m is inside the roll noise from 15 m on (1.08 x at 15-25 m, 13 x at
    25-40 m, pinned), so a long putt can end NO_CONVERGENCE for no other reason. A tolerance
    proportional to the distance would be a change of the contract with the reference.
    Decide whether putts beyond 15 m matter enough for it.
26. **[NEEDS HARDWARE]** **newlib's libm on the target** (finding 8). The single-precision functions the solver
    and the vision call (`powf`, `sinf`, `cosf`, `tanf`, `logf`, `erff`, `hypotf`, `atan2f`,
    `asinf`, `sqrtf`) are newlib's on the target and glibc's in every test here. NOT
    VERIFIED: their last-bit differences against the host's, and with them every
    single-precision figure of "Solver", on the target. It needs the cross-compiled solver
    run on the vectors in an instruction-set simulator or on a board; neither was available.
27. **[OWNER DECISION]** **Method B2 with untidy horizons** (finding 10): nominal reads fall back, jump and differ
    between the precisions. Not changed; B2 is off by default and a poor horizon is now
    shown. Decide whether B2 stays selectable before it has been made robust.
28. **[CLOSED]** **Charge termination, charge time, and the cradle state** (finding 19). ANSWERED by
    amendment E32 and implemented (phase 3): asleep in the cradle 30 s after the host fell
    silent or with none, where the model's charge terminates; a 6 h backstop for a host that
    never stops talking; "FULL" from the charger's status and the cell voltage. Left open:
    issue 34.
29. **[OWNER DECISION]** **Turning the marker back after a Precision spin** discards the `2X` result: it is a new
    placement and a new Quick Read (finding 22). The result screen is now upright for the
    golfer WITHOUT turning back, which removes the reason to do it; if the golfer is still
    expected to turn the marker back, the gyro's angle could carry the result over instead.
30. **[NOT MET]** **Vision at short range** (finding 32): at 2 to 3 m on a putt that is level along its
    line the hole is read 3 to 5 mm low, which adds about 2 % to the break, and at 0.6 m the
    flagstick is refused (the strips hold a stick down to 0.8 m: `GL_APP_MIN_RANGE_M`). The
    reviewer's figures; neither was reproduced or looked into here. The first is a bias of
    the lowest-point estimate at the turf edge of the size the "Vision" tables show (-0.3 to
    -0.5 row); a putt of 0.6 m may simply not need the instrument.
31. **[CLOSED]** **A result cannot be recalled** (finding 33). Closed by amendment E30 and implemented
    (phase 3, "Recall"). What it left to decide is issue 53.
32. **[CLOSED]** **The specification's amendments that this firmware does not implement yet.** Closed:
    all 34 are implemented or do not concern the firmware ("DESIGN_SPEC amendments" says
    which, and what is missing under each).
33. **[NOT MET] [OWNER DECISION]** **Ship mode draws 12.9 uA in the supply model; the requirement is 5 uA** (and three
    months from a 30 % charge: 42 days). The firmware has switched off everything it can
    (MCU in Shutdown 0.2, IMU powered down 3.0, flash 0.1); the board's always-on parts are
    9.6 uA: the 2.8 V regulator 1.6, the battery divider 1.95, the cell's protection
    circuit 3.0, the enable pin of the E26 regulator 2.8 (NOT CONFIRMED), the rest 0.3. To
    decide, for the hardware and the specification owners: a load switch in front of the
    divider and the regulator, an IMU supply the MCU can switch, or a requirement that
    matches the board. And to measure first: every one of these figures is from memory.
34. **[NOT MET] [OWNER DECISION]** **A silent host on a running USB bus loses the marker** (E32 as specified: "idle or
    absent for 30 s"). The marker detaches and sleeps; nothing the host does afterwards
    reaches it; only re-docking does. A PC program that talks at least every 30 s, or a
    host that suspends an idle device, never sees this. Alternatives, none implemented
    because the brief names the wake-up sources (USB resume, VBUS removal, charger status):
    stay awake while the bus runs and rely on the 6 h backstop (the charge then does not
    terminate under any PC that does not suspend); a tap on the docked marker as a fourth
    wake-up source (the IMU in wake-on-motion costs 2 uA more); a re-attach every few
    minutes. Whether Windows, macOS and Linux suspend an idle CDC device by default is NOT
    VERIFIED here.
35. **[NEEDS A DATA SHEET]** **The 2.8 uA of the E26 regulator's enable pin** is an assumption (an LP5907 with its
    enable at the 2.8 V rail: an internal 1 Mohm pull-down, from memory of the data sheet).
    The netlist notes (section 11) state the same figure, also from memory; nobody has read
    it. If it is wrong the sleep figure is 20.9 uA at the cell instead of 23.7 and ship mode
    10.1 instead of 12.9. To be read in the data sheet, or measured.
36. **[NEEDS HARDWARE]** **Rev E facts the STM32 backend takes from memory**: what survives Shutdown, that the
    wake-up pin leaves it through a reset, that no watchdog runs in it, the Shutdown
    pull-downs, the VDDUSB monitor and its start-up time, UCPD_DBDIS, the USB resume from
    Stop 1 ("STM32U5 backend"). None can be exercised without a board; each is a line in
    the bring-up plan.
37. **[CLOSED]** **CLOSED in phase 3, builder 2: `GL_CMD_SHIP_MODE "SHIP"` needs UNLOCK** (the brief:
    commands that enter ship mode are guarded). "STAY" does not. The packing station sends
    the four bytes "GLFC" first, as for every guarded command; they are a guard against
    accidents, not a secret (issue 43).
38. **[OWNER DECISION]** **The read's temperature gate accepts a reading up to 5 s old** (and the wake-up
    measurement usually is that reading). A cell cannot heat by kelvins in 5 s, so this is
    a choice, not a gap; it is pinned by a test so that it is not forgotten. The limit is
    applied to the READING (60.0 C), whose worst-case error at 60 C is 1.43 K by the
    tolerance budget, plus what the one-B equation and the cell-to-thermistor gradient add
    (not quantified).
39. **[NEEDS A DATA SHEET] [NOT MET]** **Does the charger's status line show a recharge?** Not known (no data sheet read;
    `GL_PROV_BQ25101_CHG_LOW_ON_RECHARGE`). If it shows the first cycle only, a recharge is
    invisible to the firmware: "FULL" stays on the screen while current flows, and the 6 h
    backstop of E32 does not count a recharge that an awake marker (a host that keeps
    talking) keeps from terminating - pinned as NOT MET for that variant of the model. To
    read in TI SLUSBV8. If the answer is "first cycle only", choose: accept (the cell is then
    held at 4.2 V for as long as a PC talks to a docked marker that had already been full
    once); or let the firmware restart the charger's cycle through `CHG_INHIBIT` at
    intervals while a host keeps it awake, so that the status line speaks again (not
    implemented: it rests on one more unread fact, that a stop through TS restarts the
    cycle); or count docked-and-awake time instead of CHG-low time.

40. **[OWNER DECISION]** **Which level zero a read uses is a SETTING (SURFACE: TURF / HARD), not a field of the
    calibration record.** The record holds both zeros. Say if the factory must be able to fix
    the choice per unit.
41. **[OWNER DECISION]** **The serial number is derived from the processor's unique number** (CRC-32, 7 base-32
    characters): nothing to assign, nothing to get wrong at the station, but two units can
    share one (about 1.2 % for any pair among 10 000) and it cannot follow a numbering scheme.
    The unique number is the identity of record.
42. **[OWNER DECISION]** **The user's zeroing on a hard surface MOVES the factory's base-face zero** by the same
    amount (flag BASE_DERIVED), on the argument that the difference between the two seats is
    mechanical. If the seats drift apart (wear of the ball feet) that is wrong by the drift.
43. **[OWNER DECISION]** **The unlock word is not a secret** and is the same for every unit. Anything that must
    not be possible for the owner of a cradle (overwriting calibration, erasing the log,
    ship mode, the update loader) needs something else: a decision for production.
44. **[NEEDS A DATA SHEET] [OWNER DECISION]** **Dark frames are ordinary exposures.** The camera driver writes no exposure register
    (no verified values): the sensor's own loop decides. A light-leak limit set on such
    frames depends on that loop.
45. **[OWNER DECISION]** **A camera frame from the factory commands is two exposures** (640 x 240 each): the image
    memory holds 640 x 288. One exposure of a whole frame needs 123 kB more RAM or a
    download from the camera in passing.
46. **[NEEDS HARDWARE]** **A unit sent to the loader BY THE STUB has not powered its IMU down.** Pin-map note 11:
    the IMU's interrupt lines are the loader's SPI1 inputs and must be static. After a reset
    the IMU routes no interrupt (PROVISIONAL: its reset state), but a unit that came there
    through a watchdog reset has an IMU that was never reset: its data-ready line may toggle
    at 240 Hz. Whether the loader then mistakes SPI for its interface is a release gate.
47. **[OWNER DECISION]** **Boot stub, production choices:** WRP with UNLOCK = 1 (the protection can be lifted by
    SWD; permanent protection would also make a faulty stub permanent), RDP level, signed
    images (the CRC guards against a broken image, not a forged one).
48. **[OWNER DECISION]** **Test gate 2 at 13.0 or 13.5 degrees?** DESIGN_SPEC E17 says 13.0 and the firmware uses
    13.0 (`GL_PROTO_FIELD_ELEV_DEG`); `mechanical/README.md` step 16 still says 13.5.
49. **[OWNER DECISION]** **Nothing on the unit shows a missing calibration.** `GET_IDENT` carries the flags and a
    "calibration complete" bit; the display does not change (builder 3 did not change it
    either: the specification names three display states and none of them is "uncalibrated").
    To decide: whether a unit without its factory records should show every result as APPROX,
    or refuse to read, or say so on the INFO screen only.
50. **[OWNER DECISION]** **The 72-byte read summary and the estimator event are still written** next to the new
    read record that contains them (116 of the 1156 bytes of a Quick Read). They can go when
    nothing reads them any more (`docs/VALIDATION_PLAN.md` 3.2 describes them).
51. **[OWNER DECISION]** **Tilt is logged per placement, not at intervals.** A chamber run with an untouched
    marker gets nothing into the log; it has to stream over USB (in the cradle) or the marker
    has to be lifted and replaced.

New in phase 3, builder 3:

52. **[OWNER DECISION]** **"TOO STEEP" from 0.80 of the critical slope.** The number is this
    firmware's, chosen from a simulation of the estimator (no flip below 0.90 in either
    sweep; 0.10 of margin for the error of the fitted slope). It makes every putt on a slope
    of 6.3 % at Stimp 10 (4.8 % at Stimp 13) a dashed line. To decide: the threshold; whether
    the margin should follow the green speed (the tilt error is a larger part of a smaller
    critical slope); and whether Survey fits, which were not swept, need their own.
53. **[NEEDS HARDWARE] [OWNER DECISION]** **Recall: the rule's constants and the tap.** 2
    degrees of turn, 4 mg of tilt, 3 moving blocks and 24 hours are guesses that no marker
    on turf has tested; whether a tap wakes the IMU at its provisional threshold, and what
    the IMU misses while it starts, are bring-up measurements. To decide: whether a result
    older than some minutes should be recalled at all (the green does not change; the hole
    may have been moved overnight - hence 24 h); whether the recalled screen needs more than
    its age line to be told from a fresh one.
54. **[OWNER DECISION]** **`PACE LIMIT` is a fallback (APPROX), `1 CAMERA` and `2 LINES SEEN`
    are not.** The first because the two builds of the solver end the same knife-edge putts
    as "pace limited" or as a kept near miss, and those must look the same; the others
    because the estimator solved a measured putt. E33 names the three states, not which
    estimate belongs to which: the table in "Phase 3, builder 3" is this firmware's reading.
55. **[OWNER DECISION]** **Without a solution there is no line at all.** E33 says so
    ("message without a line"). Until phase 3 a best-effort aim was drawn dashed; on a slope
    the green cannot hold the golfer now gets `TOO STEEP`, the distance and the slope, and
    nothing to aim along. Said here because it is a visible change of behaviour.
56. **[OWNER DECISION]** **Eight groups per read in all.** A read with two, three or four
    lines in view follows its line for six, five or four groups instead of eight, to keep
    the camera rail inside 2.8 s. Measured cost on the test scenes: disparity error rms up
    by about a twelfth, range error rms 0.56 % against 0.48 %. To decide: this, or a rail
    time of 3.0 to 3.4 s for such reads and a specification that says so. One group more
    (nine in all) is 2.82 s for three lines by the model.
57. **[OWNER DECISION]** **The regulatory text and what the INFO screen is for.**
    `docs/COMPLIANCE.md` (row 5) leaves open whether the statement is printed on the base
    plate, shown on a screen, or carried by manual and packaging. The screen exists and
    holds 684 character cells in four pages; its text is a placeholder that fails a release
    build. To decide: the route; then the words, from the regulation's current text.
58. **[OWNER DECISION]** **The simulation is of hardware revision C.** `sim/results/REPORT.md`
    now says so, and that the cameras' upward field it uses (17.6 degrees) is guaranteed
    only to 14.0 (E17). Its display model (direction steps of 0.94 degree) is coarser than
    the firmware's renderer (0.05 degree rms). To decide: a re-run with the revision E
    figures and a display model that matches the firmware.

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
  where the ball's drop sits). Since phase 3 (DESIGN_SPEC E29) the application takes the
  NEWEST placement as the ball, hands it over last, and leaves out stored placements that lie
  behind it: the estimator clamps stations to the line from the ball to the hole, so such a
  placement would be read as a second measurement AT the ball (Application / Survey; open
  issue 18). Whether the estimator should take stations behind the ball is its owner's.
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
  (`GL_APP_NEAR_MISS_M`: a twentieth of the hole) and shows the APPROX state (dashed line;
  the same state as `PACE LIMIT`, which is what the other build makes of some of these putts). Whether 5 mm is the
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
