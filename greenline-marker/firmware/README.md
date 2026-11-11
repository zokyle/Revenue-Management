# GreenLine GL-1 firmware (phase 1)

Firmware for the GreenLine GL-1 electronic ball marker (`../design/DESIGN_SPEC.md` rev C,
`../design/master_params.yaml` rev C-EVT1).

## Status - read this first

* **Nothing here has run on hardware.** No board exists and no vendor SDK is available in the
  build environment. What exists is portable C99 that is built and unit-tested on the host
  against a simulator of the board, and cross-compiled (compile only, not linked) for the
  Cortex-M33 to check that it is clean and to measure its size.
* **`hal/stm32u5` has never been compiled.** It is written against the STM32Cube HAL API from
  memory of that API and of the reference manual. No target of the Makefile builds it; only its
  generated pin table (`gl_pins.h`, plain macros) is checked, by `tests/test_pins.c`. Treat it
  as unverified until it has been built against the real STM32CubeU5 package and run on a board.
* **The device models of the simulator encode this project's understanding of the parts**, the
  same understanding the drivers are written from. A passing driver test shows that driver and
  model agree and that the bus traffic is self-consistent and obeys the board rules; it does not
  show that the real part behaves that way. Every register and command of the IMU and the flash
  is in one table below, marked "from memory - verify against datasheet".
* **The putt solver is a stub.** `core/gl_solver.h` is the interface that phase 2 will implement
  by porting the Python reference (`../sim/greenline_sim`); `core/gl_solver_stub.c` returns
  `GL_ERR_NOT_IMPLEMENTED`. Until then the result screen shows a tilt-and-bearing line marked
  "TILT ONLY": the aim line points straight at the flagstick, with distance and slope, and no
  break.
* All accuracy figures below are **measured on synthetic data** (`tests/synth`). They say what
  the algorithms do on idealised images; they are not a prediction of field performance. In
  particular the renderer does not model the Bayer mosaic of the colour sensor.
* Hardware facts that DESIGN_SPEC marks PROVISIONAL, and the device facts the drivers had to
  assume, are named constants in `core/gl_provisional.h` and nowhere else (full list below).
* **A design review has been applied** (three reviewers: C safety, vision, hardware interface;
  32 findings). What was changed, what was handed to the hardware design and what remains open
  is in "Design review" below; the vision figures in this file are the ones measured after it,
  and several of them are worse - and truer - than the ones this file used to carry.
* **The vision's run time on the target is the largest known risk.** It has now been counted
  (about 145 million instructions per read on the host build) and does not fit the 1.6 s the read was
  designed around without a faster clock; see "Run time" under Memory and open issue 1.
* **Rev C.** `core/gl_config.h` is regenerated from the rev C YAML (stereo baseline 20.0 mm,
  cameras at x = +-10.0 mm). The user calibration is a **zeroing on any hard flat surface**
  (read, turn the marker 180 degrees in place, read again). It is never done in the cradle,
  which takes the marker one way round only: the UI state is `CAL_ZERO` (rev B: `CAL_FLIP`), it
  can be entered only from the settings dial, being put into the cradle abandons it, and the
  USB command that asks for it is answered with `GL_ERR_STATE`.

## Design review: what was done with the 32 findings

| Area | Findings | Outcome |
|---|---|---|
| Charge gate (2 findings, one critical) | fails open with a dead or silent IMU; trusts unvalidated bytes | **Fixed**: liveness-checked IMU temperature, MCU die sensor as second opinion, staleness limit, gate evaluated in every state; simulator rule "charger enabled at Stop entry". The cell still has no temperature sensor of its own (open issue 5). |
| IMU faults (3) | one bus error disables motion input until reset; lost interrupt latch stalls the loop (backend and application) | **Fixed** in the application (recovery with back-off, polling fallback, watchdog as last resort) and in the uncompiled backend (latch updated with interrupts masked). |
| Capture pipeline (1) | assumed the vision is faster than a frame | **Fixed** structurally (whole group captured, then analysed; frame-end times latched in the interrupt; progress-based time-out). **The run time itself is not fixed**: open issue 1. |
| Precision Read, SET_CAL, LOG_ERASE, store geometry, DFU gate, USB stop outside the cradle state, float-to-int conversions, integer drawing overflow (8) | as titled | **Fixed**, each with a regression test (`test_e2e_faults.c`, `test_log.c`, `test_proto.c`, `test_gfx.c`, `test_basics.c`). DFU has no way back without a host: stated, not fixable here. |
| Vision: trunk / post accepted, stronger object chosen (critical) | | **Fixed for the reviewers' cases**: 0 of 88 stick-free reads report a flagstick; the stick is read beside a stronger post 120 px away. **Not for every case**: a second thin pole 7 px from a 0.8 px stick is still taken in half the reads, with the ambiguity flag. |
| Vision: turf texture read as stick (critical) | | **Fixed**: only rows above the turf edge are fitted; below it the stick is followed only with significance against ghost lines. |
| Vision: sigma 3-20 times too small (major) | | **Fixed in kind**: static part estimated from the flanks, calibration term added; error within 1.2 claimed sigma rms on all but one scene (1.4). The calibration term is a guess. |
| Vision: faint sticks rejected, all-or-nothing read, lowest point and base class, flag over the tip, band false candidates with FPN, phase bias, accuracy table on an impossible scene (7) | | **Fixed or partly fixed**, see "Vision" for what is met and what is not; the reviewers' scenes are permanent tests. |
| Range fusion (1) | contradicting sources averaged; insignificant disparity | **Fixed** (`test_range.c`). |
| Camera bus at power-up (1) | depends on PWDN releasing the bus | **Not fixable in firmware**: measured, asserted, documented (open issue 3). |
| Backend: EXTCOMIN stop on an uninitialised handle (1) | | **Fixed by inspection only** (uncompiled); the rule "every stop is safe before its start" is in `gl_hal.h` and tested on the simulator. |
| Charger default-off with the MCU unpowered (1) | | **Escalated to hardware** (open issue 2). |
| Register table says "pulsed"; register 0x0C bit 4; EXTCOMIN 546 ticks; bootloader pins (4) | | **Fixed** in driver, table and generator; two SPEC pins remain a release gate (open issue 4). |

No finding was rejected as false. Two were closed only as far as firmware can (camera bus,
charger default), one only as far as an uncompiled file can (EXTCOMIN handle).

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
  |   gl_solver.h + stub (phase 2)         |  +------+---------------------------+---------+
  +----------------------------------------+         |                           |
                                            +--------v---------+   +-------------v-----------+
                                            | hal/host         |   | hal/stm32u5             |
                                            | board simulator  |   | STM32Cube HAL backend   |
                                            | (the unit tests) |   | NOT COMPILED HERE       |
                                            +------------------+   +-------------------------+
```

Data flow of a Quick Read (DESIGN_SPEC section 6), as the end-to-end test runs it:

```
IMU INT1 (wake-on-motion) -> GL_EV_MOTION -> WAKE: display on, IMU 240 Hz
 -> flat and still for 0.5 s (4 blocks of 32 samples) -> GL_EV_STILL
 -> READ_TILT: 8 still blocks (1.07 s) -> temperature polynomial, 6-face matrix, slope,
    minus the zeroing bias -> GL_EV_TILT_DONE
 -> CAPTURE: camera rail on (pins handed over in the rule's order) -> 640 x 96 band of the
    left camera around its calibrated horizon row -> matched-line detector -> up to 4
    candidates (several: one L R R L group each, then the one that is a flagstick)
    -> 96 x 480 strips L R R L x 8: each group captured into four buffers, then refined
    strip by strip (rows above the turf edge only) -> segment fits over the lowest 0.4 m,
    timing correction, disparity accumulation -> camera rail off -> is it a flagstick
    (width, height, disparity)? -> base class, lowest point, top, horizon over the left
    strips -> bearing and elevations relative to gravity -> range fusion (stereo + angular
    height), stick-height learning -> GL_EV_CAPTURE_DONE
 -> SOLVE: gl_measurements_t -> gl_solver_estimate() [stub: NOT_IMPLEMENTED] -> view,
    log record -> GL_EV_SOLVE_DONE
 -> SHOW_RESULT: aim line through the ball position, distance, slope; MCU in Stop 2
    between IMU samples -> 45 s -> SLEEP: display off, IMU wake-on-motion, flash in deep
    power-down, Stop 2, a wake every 16 s for the watchdog
```

## Layout

| Path | Content |
|---|---|
| `core/` | Portable core: pure computation, no HAL, no stdio, no heap. |
| `drivers/` | Device drivers written against `hal/gl_hal.h`: `ov7692`, `ls013b7dh03`, `lsm6dsv16x`, `mx25r`, `grain_frontend`, `power`. |
| `hal/gl_hal.h` | The only hardware interface: GPIO, SPI, SCCB, DCMI strip capture, ADC / op-amp, LPTIM, tick / RTC, USB CDC, sleep. |
| `hal/host/` | Host simulator behind `gl_hal.h`: simulated time, pin and bus trace, models of the LCD, flash, IMU, two cameras, analog front end and USB; rule checkers. |
| `hal/stm32u5/` | STM32U585 backend (`gl_hal_stm32u5.c`, `gl_hal_stm32u5_usb.c`) and the generated pin map `gl_pins.h`. **Never compiled.** |
| `app/` | Main loop and glue: `gl_app`, `gl_motion`, `gl_read`, `gl_usb`, `gl_app_cfg.h` (tuning constants, flash layout), `gl_main.c` (`main()`). |
| `tests/` | Host unit tests, one executable per `test_*.c`, with the tiny runner `gl_test.h`; `test_drv_*.c` check bus traffic, `test_e2e.c` and `test_e2e_faults.c` run the whole firmware on the simulator (the second one with faults injected), `test_read.c` runs the camera part of a read on hard scenes. |
| `tests/synth/` | Synthetic strip renderer (`gl_synth`), the reviewers' independent, physically consistent scene generator (`gl_scene`, used by `test_read.c`) and simulated NOR flash with power cuts (`gl_simflash`). |
| `tools/` | `gen_config.py` (YAML -> `core/gl_config.h`), `gen_font.py` (-> `core/gl_font_data.c`), `gen_pins.py` (-> `hal/stm32u5/gl_pins.h`, cross-checked against DESIGN_SPEC), `cross_report.sh`. |

## Building and testing

```
make test     # gcc -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror, builds
              #   core + drivers + app + simulator and runs all 21 test executables
              #   (about 4.5 minutes, 2.5 of them the 920 reads of tests/test_read.c)
make asan     # the same under -fsanitize=address,undefined,float-cast-overflow
              #   (test_read.c with 3 instead of 8 reads per scene: its yield and accuracy
              #   assertions need the full count and are skipped there)
make cross    # arm-none-eabi-gcc -mcpu=cortex-m33 -mfpu=fpv5-sp-d16 -mfloat-abi=hard -Os
              #   -ffunction-sections: compiles core, drivers and app (NOT hal/stm32u5);
              #   size table, largest stack frames, forbidden-symbol check
make config   # regenerate core/gl_config.h, core/gl_font_data.c, hal/stm32u5/gl_pins.h
make V=1 ...  # show full compiler command lines
```

Needs `gcc`, `make`, `arm-none-eabi-gcc` (with newlib headers) and, for the staleness check of
the generated files, `python3` with PyYAML (skipped with a note if absent). `make test` fails
if a generated file is stale, which is how the rev C YAML change was caught.

Firmware code (core, drivers, app) is additionally compiled with `-Wdouble-promotion -Wvla
-Wmissing-prototypes -Wstrict-prototypes -Wundef`. `make cross` fails if any object references a
double-precision soft-float helper, a double-precision libm function, the heap or stdio, which is
how "single-precision float only, no dynamic allocation" is enforced rather than promised.
gcc reports different `-Wconversion` findings at `-O1` (asan) and `-O2` (test): both must be run.

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
| `gl_gfx`, `gl_font_data.c` | 1-bpp 128 x 128 framebuffer in LCD bit order, round clipping to 122 px, thick line from a real-valued angle and point, aim line through the off-screen ball position (also with the ball behind the marker after a Precision spin: `gl_gfx_aim_line_at`), 5x7 font, seven-segment large digits, icons, battery, confidence bar, arrows. |
| `gl_ui` | Explicit transition table over the 14 states (SLEEP, WAKE, WAIT_STILL, READ_TILT, CAPTURE, SOLVE, SHOW_RESULT, PRECISION_WAIT_SPIN, SURVEY_NEXT_DROP, SETTINGS_DIAL, CRADLE_USB, CAL_ZERO, ERROR, LOW_BATT), guards, timeouts, one screen per state. `CAL_ZERO` is the rev C zeroing (rev B: `CAL_FLIP`): entered only from the dial, never from the cradle state; a structural test checks that. |
| `gl_proto` | Framed binary USB protocol with CRC-16 and resynchronisation; command dispatch through callbacks. |
| `gl_log` | Power-fail-safe ring log on NOR flash and a small blob store (settings, calibration) on the same code; record formats. |
| `gl_settings`, `gl_cal`, `gl_fmt`, `gl_event`, `gl_crc`, `gl_buf.h` | Settings and the dial item table, calibration records, number formatting, event queue, CRC-16/CCITT-FALSE, bounded serialisation cursors. |
| `gl_solver.h`, `gl_solver_stub.c` | Phase-2 interface (mirrors `Measurements`, `Estimate`, `AimSolution` of the Python reference) and the stub. |

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
* **Flag-out distance.** The dialled manual distance stays in the settings; the application
  passes it to `gl_range_fuse()` only when no flagstick was found.
* **Range means horizontal distance.** Stereo disparity measures depth along the forward axis;
  the application passes `cos_bearing` so that `gl_range` works in distance (6 % difference at
  20 degrees off axis). A bearing measured by one camera is referred to the ball with
  `gl_range_from_ball_at()` (the 10.0 mm camera offset is 3.35 mrad at 3 m).
* **Over the repeats.** Each left strip gives its own lowest point, base class, top and horizon
  row. `gl_read` takes the base class most strips agree on (a tie goes to the less committal
  one), averages the lowest point over those strips and reports its uncertainty: the way it was
  found (0.5 row and more when it was placed at the turf edge; not reduced by averaging) plus
  the scatter of the mean. The top is offered for ranging only if it is in the frame and not in
  clutter (`gl_vis_angles_t.top_valid`).
* **What a disparity sigma contains.** `gl_read_result_t.disp.sigma_px` = frame noise (shrinks
  with the groups) + static part (does not) + `GL_PROV_STEREO_CAL_SIGMA_PX` (0.05 px, the same
  in every read of a unit). `gl_range` and the solver get this figure.

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
| `power` | Battery through the 2 x 1 Mohm divider (VDDA from VREFINT), percent, low / critical, VBUS and charger STAT, PROG-enable gate: charging only with VBUS and BOTH temperature sensors (IMU and MCU die sensor, which must agree within 10 K) inside 0-45 C, 2 K hysteresis, unknown or stale temperature = stop; `gl_power_charge_stop()`; PROG polarity from `GL_PROV_CHG_PROG_LOW_ALLOWS_CHARGE`; storage threshold. | Pin configuration (PROG open drain, released), the exact ADC sequence (on, one conversion, off), conversion at several cell voltages and a sagging rail, interrupts, and the PROG pin level over a sweep of temperature and VBUS. |

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

A model of the board as seen from the MCU pins, with **simulated time**: time passes only in
delays, in sleep and for the duration of bus transfers and conversions; computation takes zero
simulated time (so timing figures below do not include the vision's run time on the target).
Every pin change, bus transfer, register access and sleep is recorded in a trace (up to 262144
records, with the SPI bytes) that tests inspect.

It models: the LCD (decodes frames into a panel memory), the flash (8 MB, NOR semantics, busy
times, deep power-down), the IMU (register map, sample generator driven by a motion function of
the test, wake-up and data-ready interrupts, mounting, noise, bias, temperature), two cameras on
the shared bus (registers, reset, sleep, output enables, windows, free-running frame timing with
a phase offset between the sensors, frames from a scene callback), the battery divider, the
photodiode stage driven by the charlieplex pin states, and a USB host.

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
* power rules: USB started without VBUS when the MCU goes to sleep; the charger enabled on
  entry to Stop mode; EXTCOMIN outside 1-60 Hz (547..606 LSE ticks accepted).

It also MEASURES what it cannot forbid: the time both cameras' pads are enabled during power-up
(`cam_powerup_overlap_us`), and it can charge simulated time to the vision
(`gl_sim_set_compute_us()` per trace point), drop interrupt latches, fail SPI transfers and
glitch the IMU's supply, which is what `tests/test_e2e_faults.c` uses.

`tests/test_e2e.c` adds an **independent** check of the camera rail rule: it replays the
recorded pin trace with its own model and counts moments at which a camera-facing pin is neither
analog nor driven low while the rail is off, and bus accesses with the rail off.

### STM32U5 backend (`hal/stm32u5`) - never compiled

| File | Content |
|---|---|
| `gl_pins.h` | **Generated** by `tools/gen_pins.py`: logical pin -> port, pin, LQFP-64 pad, function, AF number, source. 19 rows are SPEC (DESIGN_SPEC section 4: the eleven DCMI pins, MCO, SPI1 MISO, USB D-/D+, LPTIM1_CH1, the three OPAMP1 pins); the generator parses the spec text and refuses to generate if a SPEC row disagrees. **26 rows are PROPOSED** by this firmware because no netlist exists: SPI1 SCK / MOSI (PA5 / PA7), SPI2 (PB13 / PB14 / PB15), chip selects, IMU INT1 on PC13 (WKUP2) and INT2 on PC5, the camera rail enable, PWDN and SCCB lines, the five charlieplex pins (PC0-PC4), VBAT sense on PA2, charger and VBUS pins. Pads outside the verified list come from the LQFP-64 pinout as remembered (it agrees with every pad that the BOM verification lists); AF5 for the SPI pins and ADC1_IN7 for PA2 are from memory. After the review the generator also carries the pins the ROM bootloader drives or samples (22 pins, **from memory of AN2606**, 6 of them driven) and refuses a PROPOSED camera-facing pin on any of them: the left camera's PWDN moved from PC10 (bootloader USART3 TX) to PH0. Two SPEC rows remain on such pins (PB9 = D7, PA6 = PIXCLK): a release gate for the netlist, see open issue 4. |
| `gl_hal_stm32u5.c` | Clocks (MSIS 48 MHz trimmed against LSE, no PLL; XVCLK = MSI / 4 on MCO), tick on LPTIM3 from LSE (runs through Stop 2), RTC seconds and RTC wake-up timer, GPIO from the pin table, EXTI sources, Stop 2 / sleep that returns only for an enabled source and cannot lose a wake-up, SPI1 / SPI2, **bit-banged SCCB** (two clock lines for two sensors at one address: no I2C peripheral can do that), DCMI snapshot with crop + byte select through GPDMA, ADC1 14-bit, OPAMP1 standalone, LPTIM1 PWM for EXTCOMIN, independent watchdog (32 s), unique id, reboot, jump to the ROM DFU bootloader through a backup-register flag (taken only if VBUS is present, so a marker in a pocket cannot be parked in the ROM). After the review: the interrupt latch is updated with interrupts masked (a lost IMU data-ready used to be possible), `gl_hal_extcomin_stop()` and the op-amp stop are safe before their start, the DCMI frame-end time is latched in the interrupt, the die temperature sensor is read, ICACHE is enabled. None of it compiled. |
| `gl_hal_stm32u5_usb.c` | CDC-ACM on ST's USB device library: HSI48 + clock recovery, VDDUSB supply-valid only after VBUS was seen, byte rings, flow control by NAK. |

To build it one needs, outside this repository: STM32CubeU5 (HAL, CMSIS, startup code, linker
script, `stm32u5xx_hal_conf.h`), ST's USB device library with the CDC class, and the board glue
`usbd_conf.c` / `usbd_desc.c` (with a VID / PID). The identifiers most likely to be wrong are
collected in an "identifier map" at the top of `gl_hal_stm32u5.c` so that each is a one-line fix.
Design points that the application relies on and that must be confirmed on hardware: LPTIM1 PWM
output in Stop 2, wake-up from Stop 2 on the IMU data-ready line at 240 Hz, DCMI crop and byte
select semantics, DMA block limit (both strip sizes, 61440 and 46080 bytes, are below 64 kB and
multiples of 4 by design; a compile-time check in `app/gl_read.c` keeps it that way).

## Application (`app/`)

* **Main loop** (`gl_app.c`). One object (`gl_app_t`, static), one loop, no RTOS, no heap, no
  second context. Sleep policy: Stop 2 whenever nothing needs fast clocks - asleep, and also
  between IMU samples while a result is shown; idle sleep while the camera rail is on or USB is
  running (the simulator counts any other combination as a violation).
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
  right pair along the left camera's own sway rate. **Which line:** with several band
  candidates each gets one group and a verdict before one is read in full. **Is it a
  flagstick:** a line is accepted only if its width fits its disparity (a 12.7-19 mm stick is
  0.64-0.95 x its disparity wide at any range with the 20 mm baseline), its height fits its
  disparity (1.0-3.2 m when both ends are in the strip), it is at least 60 times as tall as
  wide, it is within 40 m, and the background beside it does not put more than 0.5 px on its
  position. **Tiers:** stereo read; left camera only (bearing, elevations, monocular range if a
  stick height has been learned; otherwise the dialled distance along the measured bearing);
  band-only bearing (logged, not aimed at); nothing, with a reason.
* **Result without a solver.** `gl_solver_estimate()` is called with a fully filled
  `gl_measurements_t`; the stub's `GL_ERR_NOT_IMPLEMENTED` is shown as a tilt-only result, any
  other error as a failure. The mapping from `gl_estimate_t` to the screen for a real solver is
  written but cannot be exercised until phase 2.
* **Precision Read.** After the spin the marker faces away from the hole; the line is drawn
  through the ball position behind the marker (`gl_gfx_aim_line_at()`, added for this), with the
  spin angle from the gyro.
* **Zeroing** (rev C). From the dial item "ZERO": first read at rest, "TURN 180", gyro-measured
  turn, second read, `gl_tilt_flip_solve()`, bias stored with temperature and time. Refused
  with VBUS present; a turn more than 30 degrees from 180, a bias above 5 % or a disturbed read
  fails without storing.
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
  gate:** evaluated in every state, awake or in the cradle, from two sensors; a temperature
  older than 45 s, an IMU that does not answer or the two sensors disagreeing by more than 10 K
  stops the charge. **IMU supervision:** a bus error or a stall (no sample for 100 ms) starts a
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
between t = 1.0 and 1.6 s. Computation takes no simulated time in this table (what happens
when it does is measured further down).

| Quantity | Result |
|---|---|
| State sequence | SLEEP, WAKE (1.02 s), WAIT_STILL (1.82 s), READ_TILT (2.36 s), CAPTURE (3.42 s), SOLVE, SHOW_RESULT (5.03 s) |
| Result on the screen | 3.44 s after the marker came to rest (0.76 s until stillness is established, 1.07 s tilt read, 1.62 s camera part including power-up and settling) |
| Camera rail | on once, for 1557 ms; 33 captures, 87 SCCB writes; rail never on outside the CAPTURE state |
| Camera rail rule | simulator: 0 violations; independent replay of the 17673 trace records: 0 pin-rule violations, 0 bus accesses with the rail off |
| Slope | (1.202, -1.998) % against (1.200, -2.000) % |
| Disparity | 2.1991 px against 2.1985 px true; claimed sigma 0.054 px, of which 0.05 px is the (unmeasured) stereo calibration term |
| Range | 5.982 m +- 0.138 m against 5.984 m (stereo 5.982, angular height 5.982 with the prior stick height) |
| Bearing | 48.46 mrad against 48.46 mrad |
| Screen | panel memory identical to the framebuffer; the aim line passes through the predicted pixels |
| While the result is shown | MCU in Stop 2 for 99.5 % of the time (IMU at 240 Hz) |
| After 45 s | display off, IMU wake-on-motion, flash in deep power-down, Stop 2; at most 6 loop iterations in the next 60 s (watchdog refresh every 16 s) |
| Log | one boot event and one read record, decoded and compared with the result |

What the L R R L timing correction is worth (stick drifting steadily at 6 px/s = 0.2 px per
frame, 8 groups):

| Sensor phase offset | Disparity error, corrected | Uncorrected |
|---|---|---|
| 2 ms | +0.007 px | -0.003 px |
| 9 ms | +0.005 px | +0.053 px |
| 16 ms | -0.001 px | +0.005 px |
| 24 ms | -0.001 px | -0.043 px |
| 31 ms | +0.002 px | -0.082 px |

The same with the vision's run time charged to the simulated clock (per strip; eight times that
for the band), worst of the five phase offsets. The exposures of a group keep the sensors'
spacing whatever the run time, so the correction keeps working; what grows is the read:

| Run time per strip | Worst error, corrected | Capture state | Camera rail on |
|---|---|---|---|
| 0 ms | 0.007 px | 1.48 s | 1.56 s |
| 30 ms | 0.011 px | 2.76 s | 2.72 s |
| 60 ms | 0.008 px | 4.05 s | 3.89 s |
| 100 ms | 0.005 px | 5.47 s | 5.16 s |
| 200 ms | 0.008 px | 9.47 s | 8.76 s |
| 300 ms | 0.004 px | 13.47 s | 12.36 s |

No time-out at any of them. The measured cost of a strip is of the order of 0.1-0.2 s at 48 MHz
(see "Run time"): **the 200 ms row is the one to expect on the target without a faster clock.**

Other end-to-end scenarios, all with zero simulator violations:

* **DCMI-crop windowing** (the fallback if the sensor window registers do not mean what is
  assumed): stick at 3 m, range 2.981 m against 2.984 m.
* **Raw-strip logging.** Level FIRST: the first left and right strips arrive in the log byte
  for byte (2 x 48 records); the read takes 6.0 s instead of 3.4 s. Level ALL: 1600 records,
  1.6 MB, **47.2 s per read with the camera rail on for 40.1 s** - a bench mode, see open issues.
* **No flagstick:** the rail is on for 157 ms (band only), the UI asks for the distance; with a
  dialled distance a tilt-only result along the visor axis.
* **Bumped 0.4 s into the capture:** read aborted and rail off within one 133 ms block,
  re-read by itself.
* **Precision Read:** spin measured 176.08 degrees (true 176.00); a device bias of (0.4, -0.3) %
  cancels: combined slope (1.203, -2.000) % against (1.200, -2.000) %; no second camera read.
* **Survey:** second drop 3 m further along, both drops stored with their own range and slope.
* **Zeroing** on a table sloped (0.6, -1.1) % with a turn of -171 degrees: stored bias
  (3.496, -2.521) mrad against (3.500, -2.500) true, present after a power cycle; a 120 degree
  turn is refused; being put into the cradle abandons it; it cannot be started in the cradle.
* **Cradle:** protocol over the simulated CDC port (ping, info, status, settings, calibration,
  log dump, streams), charging enabled at 22 C, stopped at 47 C, re-enabled at 30 C, never Stop
  mode on USB, reboot to ROM DFU requested (after `UNLOCK`), asleep after removal.
* **Missing IMU / missing camera:** shown as an error, not fatal; rail off.
* **Battery:** at 3.45 V (low) the read runs; at 3.30 V (critical) the warning is shown and the
  device sleeps without ever powering the cameras; in the cradle it charges.
* **Spurious wake-up interrupt 50 ms after going to sleep:** ignored; a later one wakes.

Fault scenarios (`tests/test_e2e_faults.c`, 16 tests; each reproduces a review finding and
failed before its fix):

* **Charge gate.** One SPI error earlier, then 5 minutes in the cradle at a true 60 C: charging
  not allowed. IMU silent (its bytes read 0xFF, which used to decode as 25.0 C): temperature
  invalid, charging not allowed, fault shown. IMU says 22 C while the MCU die sensor says 50 C:
  not allowed. A fault acknowledged by a double tap in the cradle returns to the cradle state
  and the gate keeps running (10 minutes at 60 C: not allowed).
* **IMU supervision.** One failed SPI2 transfer: recovered (1 recovery), the read completes and
  15 later pick-up / put-down cycles all wake the device (it used to stay deaf until a reset).
  IMU absent only during boot: found later, 6 of 6 wakes. IMU dead for good: 12 failed
  recoveries, then the watchdog is left to expire (a reset on the target). 18 data-ready latches
  dropped during a read: longest gap without a sample 15 ms, bridged by polling.
* **Precision Read disturbed during the re-read:** a turn of 176 + 40 degrees is not shown as
  "Precision" (the angle is re-checked when the second read is done); 170 + 12 degrees is.
* **Lifted out of the cradle while a fault is shown:** USB stopped in the next loop pass (it
  used to stay started for 47 s).
* **SET_CAL with trailing bytes:** refused and nothing changed in RAM or flash. **LOG_ERASE
  with an append in between, then a reset:** 0 erased records come back.
* **Storage mode** at 3190 mV: IMU off, motion ignored, Stop mode 100.00 % of the time.
* **L R R L with vision run time:** the table above.


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
8 reads per scene, 6 per cell of the grid (920 reads in all); the claimed sigma includes the 0.05 px calibration term,
which these perfectly calibrated synthetic cameras do not exercise, so "rms / claimed" below 1
is expected on clean scenes and says nothing about the calibration term itself.

Flat green, width x contrast (6 reads per cell; reads that gave a disparity | disparity rms px;
bright sticks, dark ones are the same within the scatter):

| Width (range) | 5 % (3 x noise) | 10 % | 20 % | 40 % | 60 % |
|---|---|---|---|---|---|
| 0.5 px (19.7 m) | 0 of 6 | 0 of 6 | 6: 0.026 | 6: 0.018 | 6: 0.014 |
| 0.7 px (14.1 m) | 1 of 6 | 6: 0.036 | 6: 0.016 | 6: 0.009 | 6: 0.004 |
| 1.0 px (9.9 m) | 6: 0.038 | 6: 0.021 | 6: 0.013 | 6: 0.004 | 6: 0.003 |
| 1.5 px (6.6 m) | 6: 0.023 | 6: 0.013 | 6: 0.004 | 6: 0.002 | 6: 0.003 |
| 2.0 px (4.9 m) | 6: 0.017 | 6: 0.007 | 6: 0.005 | 6: 0.002 | 6: 0.003 |
| 3.0 px (3.3 m) | 6: 0.020 | 6: 0.008 | 6: 0.003 | 6: 0.003 | 6: 0.001 |

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
| Sway: drift 3 px/s; 0.5 px at 1.5 Hz; 1 px at 3 Hz (A); 2 px at 1 Hz (B) | 8 each | 0.004 / 0.051; 0.008 / 0.056; 0.040 / 0.179; 0.014 / 0.066 | fast sway shows up in the sigma through the scatter of the groups |
| Flag over the tip, bright or dark cloth (A, B) | 8 each | 0.003-0.010 / 0.051-0.053 | top flagged "in clutter" in 32 of 32 reads and never offered for ranging (it used to be ranged with: 19-23 % long) |
| Person 0.6 m beside, 2 m beside and nearer (A) | 8, 8 | 0.004 / 0.051, 0.005 / 0.051 | |
| Person 2 m behind, a leg right behind the stick (A) | 8 | 0.035 / 0.345 | static sigma 0.34 px: the background says so; all 8 flagged ambiguous |
| The same at 12 m (B) | **0** | - | **not met**: 5 nothing, 3 band-only bearing |
| Second pole 7 px beside, half as wide, twice as far (A) | 8 | 0.019 / 0.256 | |
| The same beside the 0.8 px stick (B) | 8 | - | **not met**: in 4 of 8 the far pole is taken (it too is a plausible flagstick); all 4 carry the ambiguity flag |
| Dark 4 px post 14 px beside (A / B) | 7 / **0** | 0.005 / 0.051 | B **not met** |
| Other line 120 px away: weaker stick; dark 3 px post (A, B) | 8 each | 0.004-0.012 / 0.051-0.054 | the post used to be chosen over the stick in 12 of 12 |
| Glare gradients, veiling glare, sun disc 25 px from the stick | 8 each | 0.005-0.011 / 0.051-0.054 | |
| Row gain 3 %; alternating-column gain 3 % | 8, 8 | 0.005 / 0.051; 0.005 / 0.121 | the column pattern is over-claimed 20-fold (it reads as background structure) |
| Column fixed pattern 0.5 / 1 / 2 grey rms (A) | 8 each | 0.031 / 0.058; 0.040 / 0.076; 0.079 / 0.126 | the error does not average out; the old code claimed 0.004-0.02 px here |
| PRNU 1 %; all sensor effects (A); FPN 1; all (B) | 8 each | 0.057 / 0.085; 0.063 / 0.083; 0.080 / 0.110; 0.128 / 0.116 | |
| Right window smeared: blur 1.2; 1.8 + veil; 2.5 + veil | 8 each | 0.007 / 0.052; 0.012 / 0.055; 0.037 / 0.077 | a smeared LEFT window fails the width test instead (not tested) |
| Tree line behind, white stick: mild trunks; strong trunks; isotropic foliage | 8 each | 0.037 / 0.071; **0.172 / 0.120**; 0.063 / 0.071 | strong trunks: worst read 0.31 px off, 1.4 claimed sigma rms |
| Tree line, stick only 36 grey brighter than trunks of 12 grey rms | **0** | - | **not met** |
| Everything at once (A / B) | 8 / 7 | 0.095 / 0.088; 0.145 / 0.198 | range error 5 % / 13 % rms = 1.1 / 0.7 of its claimed sigma |

No stick in the scene (88 reads: plain, tree line, a person, FPN 1 and 2 grey, glare, a 12 px
trunk at 40 m, a 3 px post at 25 m, column gain, PRNU, foliage + rough turf): **0 reads report a
flagstick**, in either tier; 1 read (glare) reports a band-only bearing. The trunk and the post
were ranged as flagsticks by the old code in most reads. Mean camera-rail time 0.6 s.

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
line leaves the aperture; a dashed parallel line and a side arrow are drawn instead.

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
| core | gl_vision | 16606 | 0 | 0 |
| core | gl_gfx | 4604 | 0 | 0 |
| core | gl_ui | 4378 | 0 | 0 |
| core | gl_log | 4102 | 0 | 0 |
| core | gl_tilt | 3264 | 0 | 0 |
| core | gl_range | 2276 | 0 | 0 |
| core | gl_proto | 2236 | 0 | 0 |
| core | gl_cal | 2160 | 0 | 0 |
| core | gl_grain | 1888 | 0 | 0 |
| core | gl_cam | 1504 | 0 | 0 |
| core | gl_math | 1440 | 0 | 0 |
| core | gl_settings | 1286 | 0 | 0 |
| core | gl_gesture | 970 | 0 | 0 |
| core | gl_font_data | 632 | 0 | 0 |
| core | gl_fmt | 477 | 0 | 0 |
| core | gl_solver_stub | 216 | 0 | 0 |
| core | gl_event | 148 | 0 | 0 |
| core | gl_crc | 100 | 0 | 0 |
| core | **total** | **48287** | **0** | **0** |
| drivers | ov7692 | 1941 | 0 | 0 |
| drivers | lsm6dsv16x | 1254 | 0 | 0 |
| drivers | mx25r | 870 | 0 | 0 |
| drivers | ls013b7dh03 | 674 | 0 | 0 |
| drivers | power | 616 | 0 | 0 |
| drivers | grain_frontend | 530 | 0 | 0 |
| drivers | **total** | **5885** | **0** | **0** |
| app | gl_app | 8612 | 0 | 1366 |
| app | gl_read | 4931 | 0 | 0 |
| app | gl_usb | 2018 | 0 | 388 |
| app | gl_motion | 860 | 0 | 0 |
| app | gl_main | 24 | 0 | 306600 |
| app | **total** | **16445** | **0** | **308354** |
| all | **total** | **70617** | **0** | **308354** |

RAM (ARM `sizeof`, from the same build; core and drivers have no `.data` / `.bss` of their own,
all state is in the application object):

| Object | Bytes | Note |
|---|---|---|
| `gl_app_t` (bss of `gl_main`) | 306600 | everything below is inside it |
| - strip buffers `gl_read_t.img` | 184320 | FOUR 96 x 480 strips, one L R R L group (was two: the review showed that analysing while capturing ties the exposure spacing to the vision's run time); the 640 x 96 band (61440) uses the same memory |
| - `gl_vis_band_work_t` | 42240 | band analysis, including the 5 kB of sampled path sums |
| - `gl_vis_stick_work_t` x 4 | 66576 | one per strip of a group (16644 each, of which 5760 are the stored flank pixels) |
| - LCD: `gl_gfx_t` + driver shadow | 2305 + 2060 | |
| - `gl_proto_t` | 2096 | two 1032-byte frame buffers |
| - solver inputs `gl_measurements_t` x 5 | about 2000 | the shown read + 4 Survey drops |
| - `gl_store_t` | 1084 | settings and calibration blobs |
| - everything else (UI, motion, tilt, survey, drivers, log, read state) | about 5900 | |
| static scratch in `gl_app.c` / `gl_usb.c` | 1754 | one raw-strip log record (978), two raw grain measurements (388 each) |
| STM32 backend (estimate, not compiled) | about 3000 | HAL handles, pin shadows, two 1 kB USB rings |
| main stack (recommended) | 4096 | see below |
| **total** | **about 316 kB of 786 kB** | |

Stack (`-fstack-usage`, `-Os`, bytes per frame): `gl_vis_band_analyse` 632, `measure_row_` 352,
`gl_app_run_once` 320, `gl_cam_model_init` 304, `gl_vis_stick_refine` 248, `gl_read_step` 240,
`do_actions_` 216, `gl_usb_service` 208, `gl_lcd_update` 200, `gl_store_mount` 200,
`gl_vis_stick_segment` 168, `measure_all_` 144. Worst chains:

| Chain | Bytes |
|---|---|
| run_once -> read step -> stick refinement -> measure_all_ -> measure_row_ (320 + 240 + 248 + 144 + 352) | about 1300 |
| run_once -> read step -> band analysis (320 + 240 + 632 + the sort) | about 1230 |
| run_once -> read step -> raw-strip hook -> log append -> flash driver | about 890 |
| run_once -> actions -> solve -> log append -> flash driver | about 810 |
| run_once -> USB service -> protocol -> log read -> log iterator -> flash driver | about 810 |
| init -> store mount -> log walk -> flash driver | about 500 |

Add the HAL's own frames below the drivers (not measured: not compiled) and interrupt frames
(104 bytes each with FPU state, handlers are short). A 4 kB main stack leaves a factor of two.
No function recurses.

### Run time

**Not measured on the target; counted on the host.** `valgrind --tool=callgrind` on the `-O2`
host build of one nominal read (band + 32 strips, `tests/test_read A_nominal 1`):

| Step | Host instructions | At 48 MHz, if one host instruction costs 1.5-3 cycles |
|---|---|---|
| Band analysis (once) | 35.2 million | 1.1-2.2 s |
| One strip refinement | 3.4 million (108 million for 32) | 0.11-0.21 s |
| A whole read | about 145 million | 4.5-9 s |
| A read with four band candidates (a person in view) | about 195 million | 6-12 s |

The cycles-per-instruction factor is a guess (single-precision FPU code, no cache misses on
this part, but more instructions per C statement than x86-64); the instruction counts are
measured. The earlier text of this file ("band about 3 million operations, a strip about 0.1
million, inside one frame period") was wrong by more than a factor of ten, and the two-buffer
pipeline that relied on it has been replaced (see Application / Read). What it means:

* a Quick Read at 48 MHz would take of the order of 8-12 s after the marker comes to rest
  instead of the 3.4 s of the simulator (which charges no computation), with the camera rail on
  for most of it (table under "End to end": 8.8 s at 200 ms per strip);
* the remedy is a hardware / clock decision (open issue 1): the PLL at 160 MHz during a read
  brings the same figures to about 1.4-2.7 s of computation; and the vision itself can be made
  cheaper (a quarter of a strip's cost is the sorting behind its medians, even after that sort
  was made 20 % cheaper in this round; the band tries 13 leans x 4 widths at full resolution).
  None of that optimisation has been done beyond the sort and the exponential table.

The firmware's own code is 70.6 kB of the 2 MB flash before libraries.

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
| LCD | `GL_PROV_LCD_FPC_PIN_*` (10), `GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS`, `GL_PROV_LCD_ROW0_AT_FRONT`, `_COL0_AT_LEFT`, `_ACTIVE_CENTRE_Y_MM`, `_SPI_MAX_HZ`, `_VDD_MIN_MV`, `_SCS_SETUP_US`, `_SCS_HOLD_US`, `_SCS_LOW_US` | FPC pin order and pin-1 side (DESIGN_SPEC PROVISIONAL), EXTCOMIN period (547 ticks = 59.905 Hz; the 546 of DESIGN_SPEC is 60.015 Hz, just outside the 1-60 Hz it quotes), panel orientation, active-area offset, timing |
| MCU | `GL_PROV_LPTIM_PWM_RUNS_IN_STOP2`, `GL_PROV_USB_CRYSTALLESS_HSI48_CRS`, the 26 PROPOSED rows of `hal/stm32u5/gl_pins.h` | EXTCOMIN in Stop 2 (if 0 the application stays in idle sleep while the display is on), crystal-less USB, pin assignment |
| IMU | `GL_PROV_IMU_MARKER_{X,Y,Z}_AXIS`, `_SIGN`, `GL_PROV_IMU_WAKE_THRESHOLD_MG`, `GL_PROV_IMU_DRDY_PULSED` | mounting orientation on the PCB (identity is a placeholder), wake threshold, data-ready mode |
| Flash | `GL_PROV_MX25R_PROG_TIMEOUT_MS`, `_ERASE_TIMEOUT_MS`, `_DP_DELAY_US`, `_SPI_HZ` | timing |
| Grain | `GL_PROV_GRAIN_RED_ANODE_ON_LOW_PIN`, `_SETTLE_US`, `_ADC_AVG`, `_ADC_SAMPLE_US`, `_POWER_SETTLE_MS`, `_MOD_THRESHOLD_DEFAULT`, `_MAX_EQUIV_SLOPE`, `_HARMONIC_SIGN`, `_KAPPA_BENT`, `_KAPPA_POA`, `_KAPPA_BERMUDA` | charlieplex wiring (proposal), settling, and the unproven physics; the acceptance threshold used is always the one in the calibration record |
| Power | `GL_PROV_BATT_LOW_MV`, `_CRITICAL_MV`, `_FULL_MV`, `_EMPTY_MV`, `_DIVIDER_RATIO`, `GL_PROV_CHARGE_TEMP_MIN_C`, `_MAX_C`, `_HYST_C`, `_MAX_DISAGREE_C`, `GL_PROV_CHG_PROG_LOW_ALLOWS_CHARGE`, `GL_PROV_BATT_STORAGE_MV` | cell thresholds (no cell datasheet), hysteresis, how far the two temperature sensors may disagree, which level of the PROG gate allows charging (open issue 2), storage threshold |
| Estimates | `GL_PROV_SEATING_SIGMA_RAD`, `GL_PROV_STICK_TOTAL_HEIGHT_M`, `_IN_CUP_M`, `_HEIGHT_REL_SIGMA`, `_DIA_MIN_M`, `_DIA_MAX_M` (now used: the width a flagstick may have at its disparity), `GL_PROV_STEREO_CAL_SIGMA_PX` (0.05 px, added to every disparity sigma), `GL_PROV_LENS_BLUR_SIGMA_MIN_PX` / `_MAX_PX` (0.45-0.80 px) | not measurements; the blur range decides which posts are rejected as "too wide for their disparity" and must be replaced by the measured blur at EVT |

Tuning constants that are our own choices rather than hardware facts (gesture timing, repeat
counts, flash layout) are in `app/gl_app_cfg.h`; none has been tuned on hardware.

Two assumptions that are not in DESIGN_SPEC and must be checked against the mechanical design:
the ball centre is taken at outer radius + ball radius = 23.0 + 21.335 = 44.335 mm ahead of the
marker centre (`GL_CFG_BALL_CENTRE_Y_MM`; 39.7 mm if the ball rests against the flat visor
face), and the grain LED azimuths are counter-clockwise from marker +x seen from above (now
stated in the rev C YAML).

## What is not done

* **No hardware run of anything.** The STM32 backend is uncompiled; startup code, linker script,
  HAL configuration and the USB board glue (`usbd_conf.c`, `usbd_desc.c`, VID / PID) do not exist
  here. Timing on the target (vision run time, SCCB bit-bang, Stop 2 wake latency at 240 Hz) is
  unmeasured.
* **The solver** (phase 2), and with it break, pace and the real confidence figure. The
  confidence shown now is a heuristic placeholder capped at one half. The Survey estimate calls
  the stub as well; which drop the line is drawn for (`ball_index`) is a phase-2 decision.
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
  can be added from the application; the jump is now gated by `UNLOCK` and by VBUS).
* **Vision speed.** Nothing has been optimised for the target beyond a lookup table for the
  exponential and a better sort; see "Run time".
* **Vision cases known not to work** (pinned by `tests/test_read.c`, listed under "Vision"):
  sticks under about 0.7 px at under 10 % contrast; a 0.8 px stick with a person, a post or a
  second pole within a few pixels; a low-contrast stick against strong tree trunks; following a
  thin stick into rough turf; the lowest point behind tall ragged grass.
* **Gesture tuning.** Thresholds are guesses; taps are detected in software from the 240 Hz
  stream (the IMU's embedded tap function is not used). The gesture maths is unit-tested, the
  thresholds are not field-tested.
* **Fuel gauging:** the percentage is a straight line between two provisional voltages.

## Open issues that need a decision

Hardware and system decisions first: none of them can be closed in firmware.

1. **Vision run time against the system clock.** About 145 million host instructions per read
   (measured), of the order of 4.5-9 s at 48 MHz; the read was designed around 1.6 s. Decide:
   PLL (160 MHz) during the capture state, with its wake-up and current cost, and / or an
   optimisation pass on `gl_vision` once it can be profiled on a board. Until then every timing
   figure in this file that involves the cameras is the simulator's, with free computation.
2. **Charger when the MCU is unpowered.** The firmware gates the MCP73832 through PROG, and the
   proposed circuit leaves the charger OFF unless the MCU drives the gate: a cell that has
   reached its protection cut-off can then never be recharged (no MCU, no charge). The fail-safe
   needs a hardware default-ON gate that the MCU can only ever switch OFF (plus an NTC, see
   below); `GL_PROV_CHG_PROG_LOW_ALLOWS_CHARGE` selects the polarity the firmware drives, and
   the firmware's storage mode (IMU off below 3250 mV) only delays the cut-off. **The schematic
   owner has to decide; nothing here fixes it.**
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
5. **Charge temperature.** The gate uses the IMU's die sensor with the MCU's die sensor as a
   second opinion (10 K agreement). Neither is a cell temperature, neither has a stated
   absolute accuracy here, and a raw reading of exactly 25.000 C is refused as "sensor not
   alive" (charging then pauses until the next reading). A cell NTC on the charger is the proper
   answer; decide whether the 0-45 C limits need a margin until then.
6. **Stereo calibration term.** `GL_PROV_STEREO_CAL_SIGMA_PX` = 0.05 px is a guess and it is
   now the largest part of the claimed range uncertainty on every clean scene (2.3 % at 6 m,
   3.8 % at 10 m). It has to come from the calibration fixture's repeatability.
7. **Lens blur.** The "too wide for its disparity" test needs the blur; until it is measured
   the range 0.45-0.80 px is assumed, which rejects a 3 px post at 25 m but would not reject a
   2 px one, and rejects a real stick seen through a smeared LEFT window.

Product decisions:

8. **The weaker tiers.** A read can now end as "left camera only" (bearing and elevations, no
   disparity; ranged from the angular height if a stick height has been learned, otherwise the
   dialled distance is applied along the measured bearing) or as "band-only bearing" (logged,
   not used). Confirm that a single-camera stick, which cannot be checked against a disparity,
   should be aimed at; and whether `ambiguous` should block the result rather than lower the
   confidence figure (x 0.6).
9. **Base of the stick for ranging.** "At horizon" covers a base just visible on a flat green
   and one hidden behind a crown. For RANGE (and for learning the stick height) the application
   treats the lowest visible point as the base in both cases, with the read's own uncertainty
   for it (0.5-0.6 row at the turf edge, more with a hint of a continuation) on top of 0.3 row;
   for the SLOPE use the solver receives the strict flag. The estimator's owner should confirm.
10. **Pin assignment.** 26 pins are this firmware's proposal (table in `tools/gen_pins.py`),
    including bit-banged SCCB on PB5 / PB3 / PA10, the IMU wake line on PC13 and the left
    camera's PWDN now on PH0. The schematic may choose differently; only the generator changes.
11. **Raw-strip logging level ALL keeps the camera rail on for about 40 s per read** (47 s in
    all; about 1 mAh of a 43 mAh cell, and heat). Level FIRST costs 2.6 s. If ALL is wanted in
    the field it needs a different capture plan (cameras off between groups) or less data.
12. **Watchdog in Stop mode.** The independent watchdog keeps running in Stop 2, so the sleeping
    device wakes every 16 s for a few microseconds. Freezing it in Stop by option byte would
    avoid that at the price of no supervision while asleep. Related: after 8 failed IMU
    recoveries the firmware deliberately lets the watchdog reset it; a unit with a dead IMU
    then resets every 32 s while awake. Decide whether it should give up and sleep instead.
13. **Idle camera kept awake** during L R R L (deviation from the letter of DESIGN_SPEC, see
    Drivers) and **OVM7692 reset output size** (the public driver's comments suggest 384 lines).
14. **Zeroing over USB** is refused rather than "armed for when the marker leaves the cradle".
    Since the review the other factory procedures also need `UNLOCK` (the zeroing and ABORT do
    not). If the factory wants to trigger zeroing from the fixture, a guarded transition has to
    be added.
15. **DESIGN_SPEC text to correct:** EXTCOMIN "546 ticks" is 60.015 Hz (547 is used); the
    register table's "INT pins pulsed" (latched is used and now selected explicitly).
16. **State name.** `CAL_FLIP` of the original state list is now `CAL_ZERO` (rev C wording); the
    storage fields `flip_bias_*` and `GL_CAL_TILT_FLAG_FLIP` keep their names because they are the
    record format. The read log record is unchanged: a left-camera-only read is a record with
    the stick flag set, zero disparity and zero repeats.

## Phase 2: the solver

`core/gl_solver.h` mirrors the Python reference one to one (`gl_measurements_t` <->
`Measurements`, `gl_estimate_t` <-> `Estimate`, `gl_aim_solution_t` <-> `AimSolution`, the same
status values). Phase 2 replaces `gl_solver_stub.c`. Two points to settle then:

* `gl_range_fuse()` fuses in inverse range; the reference `estimator.fuse_range()` fuses in
  range with one re-evaluation of the stereo sigma. They agree to first order. One of them
  should be chosen and tested against exported vectors.
* The reference takes the Survey drops "ball first"; the firmware passes a `ball_index`,
  because the line can only be drawn relative to the marker's current placement.
* The reference defines `flag_disparity` as f * baseline / range with range the distance to
  the stick. The rectified disparity measured here is f * baseline / depth; the application
  multiplies it by cos(bearing) when it fills `gl_measurements_t` (`build_measurement_()` in
  `app/gl_app.c`, which is the one place where firmware quantities become solver inputs).
* `flag_base_visible` is passed strictly (the stick was followed, with significance, more than
  1.5 rows below the turf edge); see open issue 9 for how the range fusion treats the other case.
* New since the review, for the estimator to use or ignore: the disparity uncertainty now has
  three parts (noise, static, calibration; `gl_read_result_t.disp` and `.cal_sigma_px`) and the
  solver is given their sum; `gl_read_result_t.tier`, `.why`, `.ambiguous` and
  `.bottom_sigma_rows` are not part of `gl_measurements_t`. `core/gl_solver.h` itself is
  unchanged: if phase 2 wants any of them, the struct and the Python `Measurements` have to
  grow together.
* A left-camera-only read has no disparity, and `gl_measurements_t` has no way to say so. If
  such a read has a range at all (from the angular height with a learned stick height),
  `build_measurement_()` passes that range as the disparity it corresponds to (f x baseline /
  range) with `flag_found` true; if it has none, the read is passed as "flag not found" with the
  dialled distance. Phase 2 should replace this with an explicit input.
* `gl_range_fuse()` no longer averages sources that contradict each other (chi-square above 9):
  it takes one (the learned angular height beyond 5 m of stereo range, the stereo otherwise),
  widens its sigma to half the gap and clears `consistent`; an insignificant or negative
  disparity is dropped instead of discarding the monocular range; nothing beyond 40 m is
  reported. The Python reference does none of this.
