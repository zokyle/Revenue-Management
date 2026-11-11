# GreenLine GL-1 firmware (phase 1)

Firmware for the GreenLine GL-1 electronic ball marker (`../design/DESIGN_SPEC.md` rev B,
`../design/master_params.yaml`).

## Status - read this first

* **Nothing here has run on hardware.** No board exists and no vendor SDK is available in the
  build environment. What exists is portable C99 that is built and unit-tested on the host, and
  cross-compiled (compile only, not linked) for the Cortex-M33 to check that it is clean and to
  measure its size.
* **`hal/stm32u5` is not compiled by this build.** It is written against the STM32Cube HAL API
  from documentation and memory and must be treated as unverified until it is built against the
  real SDK and run on a board.
* **The putt solver is a stub.** `core/gl_solver.h` is the interface that phase 2 will implement
  by porting the Python reference (`../sim/greenline_sim`); `core/gl_solver_stub.c` returns
  `GL_ERR_NOT_IMPLEMENTED`. Until then the result screen shows a tilt-and-bearing-only line.
* All accuracy figures below are **measured on synthetic data** (`tests/synth`). They say what the
  algorithms do on idealised images; they are not a prediction of field performance. In
  particular the renderer does not model the Bayer mosaic of the colour sensor.
* Hardware facts that DESIGN_SPEC marks PROVISIONAL are named constants in
  `core/gl_provisional.h` and nowhere else.

## Layout

| Path | Content |
|---|---|
| `core/` | Portable core: pure computation, no HAL, no stdio, no heap. |
| `drivers/` | Device drivers written against `hal/gl_hal.h` (ov7692, ls013b7dh03, lsm6dsv16x, mx25r, grain_frontend, power). |
| `hal/gl_hal.h` | The only hardware interface: GPIO, SPI, SCCB, DCMI strip capture, ADC / op-amp, LPTIM, tick / RTC, USB CDC, sleep. |
| `hal/host/` | Host simulator behind `gl_hal.h`: records bus traffic, serves synthetic frames and sensor data. |
| `hal/stm32u5/` | STM32U585 backend and `gl_pins.h`. **Not compiled here.** |
| `app/` | Main loop and glue (`app/gl_main.c` holds `main()`). |
| `tests/` | Host unit tests, one executable per `test_*.c`, with the tiny runner `gl_test.h`. |
| `tests/synth/` | Synthetic strip renderer (`gl_synth`) and simulated NOR flash with power cuts (`gl_simflash`). |
| `tools/` | `gen_config.py` (YAML -> `core/gl_config.h`), `gen_font.py` (art -> `core/gl_font_data.c`), `cross_report.sh`. |

## Building

```
make test     # gcc -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror, runs all tests
make asan     # the same under -fsanitize=address,undefined,float-cast-overflow
make cross    # arm-none-eabi-gcc -mcpu=cortex-m33 -mfpu=fpv5-sp-d16 -mfloat-abi=hard -Os
              #   -ffunction-sections: compiles core, drivers, app; size table, stack frames,
              #   forbidden-symbol check
make config   # regenerate core/gl_config.h and core/gl_font_data.c
make V=1 ...  # show full compiler command lines
```

Needs `gcc`, `make`, `arm-none-eabi-gcc` (with newlib headers) and, for the staleness check of
the generated files, `python3` with PyYAML (skipped with a note if absent).

Firmware code (core, drivers, app) is additionally compiled with `-Wdouble-promotion -Wvla
-Wmissing-prototypes -Wstrict-prototypes -Wundef`. `make cross` fails if any object references a
double-precision soft-float helper, a double-precision libm function, the heap or stdio, which is
how "single-precision float only, no dynamic allocation" is enforced rather than promised.

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
| `gl_vision` | Flagstick on 8-bit luminance strips: horizon-band analysis (per-column edge energy, matched vertical-line detector for leans of +-3 degrees at 4 widths, turf-horizon samples); sub-pixel line fit on the tall strip (per-row centroid, both polarities, trimmed / reweighted least squares, outlier rows); ends of the stick; segment fit; stereo disparity over the L R R L repeats with uncertainty; quality metrics. |
| `gl_cam` | Camera model: intrinsics with one radial term, extrinsics to the marker frame, pixel <-> bearing / elevation relative to gravity, rectification, calibrated horizon row. |
| `gl_range` | Stereo + angular-height + manual range, inverse-variance fusion in inverse range, per-course learned stick height, camera-to-ball geometry. |
| `gl_tilt` | Exact integer block averaging with stillness gating, 6-face + cross-axis calibration, temperature polynomial, slope vector / fall line, gyro rotation integrator, flip calibration with measured yaw, Precision Read combining, Survey store. |
| `gl_gesture` | Posture (flat / upright), roll-to-set dial, double tap, half-turn spin. |
| `gl_grain` | Grain front-end maths: dark / on / dark differencing with drift rejection, white-reference gains, first-harmonic vector per colour, validity against a *calibrated* threshold, running average, estimate handed to the solver (zero while grain is disabled, the default). |
| `gl_gfx`, `gl_font_data.c` | 1-bpp 128 x 128 framebuffer in LCD bit order, round clipping to 122 px, thick line from a real-valued angle and point, aim line through the off-screen ball position, 5x7 font, seven-segment large digits, icons, battery, confidence bar, arrows. |
| `gl_ui` | Explicit transition table over the 14 states, guards, timeouts, and one screen per state. |
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
  `gl_range_from_ball_at()` (the 10.2 mm camera offset is 3.4 mrad at 3 m).
* **Averaging over the repeats.** Each strip gives its own lowest point, top and horizon row;
  the application should average them over the 32 strips of a read before classifying the base
  (`GL_VIS_BASE_MARGIN_ROWS`) and converting to elevations.

## Measured results (host, synthetic data)

These are copied from `make test`; re-run it to reproduce them.

### Vision

Definitions: SNR = |stick level - background level| / noise sigma (the contrast of a fully
resolved stick; a sub-pixel stick has a proportionally lower peak). Lens blur is a Gaussian PSF
of sigma 0.6 px unless stated. One row = one left/right pair, 120 trials with random position,
disparity and sub-pixel phase; disparity is taken over the lowest 40 rows unless stated.
"Claimed" is the mean uncertainty the code reports.

| Condition | RMS px | Bias px | Worst px | Claimed px | Refused |
|---|---|---|---|---|---|
| 1.5 px, SNR 20, vertical | 0.0154 | -0.0004 | 0.051 | 0.0171 | 0 |
| 1.5 px, SNR 20, leaning 2 deg | 0.0157 | -0.0015 | 0.039 | 0.0172 | 0 |
| 1.5 px, SNR 20, dark on bright | 0.0155 | +0.0027 | 0.041 | 0.0172 | 0 |
| 1.5 px, SNR 20, 26 rows (0.4 m at 10 m) | 0.0226 | +0.0033 | 0.082 | 0.0214 | 0 |
| 1.5 px, SNR 20, textured background | 0.0458 | -0.0053 | 0.180 | 0.0379 | 0 |
| 1.5 px, SNR 10 | 0.0310 | -0.0011 | 0.071 | 0.0354 | 0 |
| 1.5 px, SNR 20, lens blur 1.0 px | 0.0226 | -0.0022 | 0.053 | 0.0254 | 0 |
| 0.7 px, SNR 20, vertical | 0.0349 | -0.0024 | 0.082 | 0.0342 | 0 |
| 0.7 px, SNR 20, leaning 0.6 deg | 0.0303 | -0.0030 | 0.111 | 0.0344 | 0 |
| 0.7 px, SNR 20, 26 rows | 0.0385 | +0.0022 | 0.088 | 0.0434 | 0 |
| 0.7 px, SNR 20, textured background | 0.1107 | -0.0046 | 0.329 | 0.0958 | 0 |
| 0.7 px, SNR 20, lens blur 0.4 px | 0.0404 | +0.0043 | 0.099 | 0.0295 | 0 |
| 0.5 px, SNR 20, 26 rows | 0.0708 | +0.0020 | 0.192 | 0.0696 | 8 of 120 |
| 4 px (3 m), SNR 20, 100 rows | 0.0087 | +0.0008 | 0.025 | 0.0092 | 0 |
| 8 px (1.5 m), SNR 20, 200 rows | 0.0078 | -0.0009 | 0.026 | 0.0089 | 0 |

Against the targets:

| Target | Result |
|---|---|
| Disparity RMS <= 0.08 px, 1.5 px stick, SNR 20 | **Met**: 0.015-0.023 px (0.046 px on a textured background). |
| Disparity RMS <= 0.15 px, 0.7 px stick, SNR 20 | **Met**: 0.030-0.039 px; 0.111 px on a textured background, where single pairs were off by up to 0.33 px. |
| No bias across sub-pixel phase beyond 0.03 px | **Met at the design blur**: largest mean error over 20 phase combinations of exactly vertical sticks 0.005 px (1.5 px stick) and 0.011 px (0.7 px stick). **Not met for a sharper lens**: 0.041 px for a 0.7 px stick at blur 0.4 px. |
| Both polarities | Dark-on-bright as good as bright-on-dark; a stick whose polarity flips half way (bright against trees, dark against a bright wall) is fitted through both parts. |
| Graceful failure with no stick | 0 false sticks in 60 stick-free tall strips, 0 false candidates in 60 stick-free bands, 0 of 5 edges of a person / wall / tree trunk accepted. A fit is refused with `GL_ERR_NO_STICK`; nothing is returned as a measurement. |

Other figures:

* **L R R L**: with the stick swaying 0.20 px per frame, 8 groups give a mean error of +0.001 px
  (rms 0.004 px); pairing each L only with the next R gives -0.209 px.
* **Outliers**: flag cloth, a person crossing behind and a parallel rail: worst axis error
  0.024 px over 30 scenes; the fraction of rows used drops to 0.70, which is what the quality
  metric is for.
* **Lowest visible point** (single strip, SNR 20): bias +0.00 / RMS 0.08 row when the base is 8
  rows below the turf horizon (1.5 px stick), RMS 0.18 row for a 0.7 px stick. **When the stick
  ends at the turf horizon the result is biased by +0.26 to +0.29 row** (and +0.14 row 3 rows
  below it), because the last partly covered row is seen against turf while the reference rows
  are seen against the far background. This cannot be corrected without knowing the stick's own
  brightness.
* **Base flag**: "visible" when the stick continues more than 1.5 rows below the local turf
  horizon, else "at horizon": 60/60 correct in both synthetic cases. Physical caveat: on a
  planar green the base lies only (lens height / distance) below the horizon, 0.7 px at 5 m, so
  "at horizon" covers both "base just visible on a flat green" and "base hidden behind a crown".
* **Top of the stick**: RMS 0.13 row; angular height RMS 0.25 mrad.
* **Band detection** (640 x 96, SNR 20, lean -3..+3 deg, widths 0.7-10 px): 24/24 detected at
  each width, column RMS 0.13-0.16 px, lean RMS 0.6-0.8 deg.
* **Full chain** through the camera models with a mis-mounted right camera (4-6 mrad): range
  error -0.03 % at 3 m, +0.01 % at 6 m, -0.25 % at 10 m; bearing error below 0.03 mrad.
* **Sharpness match** between the cameras: 0.98 with clean windows, 0.46 with one window smeared.

Things the synthetic tests do **not** cover: Bayer / YUV artefacts on sub-pixel lines, lens
distortion inside the strip, rolling shutter, non-Gaussian blur, real scenery, striped sticks,
flags flapping across the stick, heat shimmer.

### Display

Rasterised lines, direction recovered by a least-squares fit of the lit pixels:

| Case | RMS deg | Worst deg |
|---|---|---|
| 7 px wide, all 1800 angles (0.1 deg steps), plain edges | 0.032 | 0.58 |
| 7 px wide, all 1800 angles, dithered edges | 0.038 | 0.32 |
| 7 px wide, -1..+1 deg in 0.01 deg steps, plain edges | 0.205 | 0.60 |
| 7 px wide, -1..+1 deg in 0.01 deg steps, dithered edges | 0.034 | 0.15 |
| Aim line through the ball (246 px off-screen), -13..+13 deg, 2601 angles | 0.050 | 0.28 |

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
  mount: 0 failures (every id holds its last acknowledged value or the one in flight).
* A first version that relied on CRC-16 alone accepted a torn record 13 times in 1.2 million
  randomly torn cuts, as a 16-bit check must; records now carry a commit word programmed last,
  so an interrupted append is rejected by construction.

### Tilt, range, grain, protocol

* 1 s average at 240 Hz with 1 mg rms noise: worst error 0.22 mg (0.22 mrad) over 200 trials.
* Six-face solve: residual 3e-7 g. Temperature polynomial: residual 1e-8 g over -5..50 C.
* Flip calibration, end to end with noise, 174 degree turn measured by the gyro: bias recovered
  to 0.1 mrad. Ignoring the measured yaw on a 172 degree flip in a cradle sloped 1 % would cost
  0.70 mrad.
* Precision Read: device bias cancels exactly; the two seating errors average.
* Range fusion Monte Carlo (4000 trials, 2-12 m): normalised error mean -0.02, rms 1.00, i.e.
  the reported sigma is honest. Stick height learned from a 9 cm wrong prior to 2 cm in 18 holes.
* Grain: the white-reference step removes a false modulation of 0.098 caused by a +-30 % LED
  spread; the acceptance threshold is read from the calibration record in every code path.
* Protocol: every single-bit corruption of a frame is rejected; 500 of 500 valid frames found in
  1 MB of protocol-like noise with no false frame.

## Memory

Flash (`make cross`, `-Os`, text bytes; core has no `.data` and no `.bss`):

| Module | Text | Module | Text |
|---|---|---|---|
| gl_vision | 10810 | gl_range | 1880 |
| gl_ui | 4342 | gl_cam | 1504 |
| gl_gfx | 4044 | gl_math | 1412 |
| gl_log | 3934 | gl_settings | 1242 |
| gl_tilt | 3264 | gl_gesture | 970 |
| gl_proto | 2188 | gl_font_data | 632 |
| gl_cal | 2168 | gl_fmt | 477 |
| gl_grain | 1888 | gl_solver_stub, gl_event, gl_crc | 464 |
| | | **core total** | **41219** |

RAM the application must provide for the core (ARM `sizeof`):

| Object | Bytes | Note |
|---|---|---|
| `gl_vis_band_work_t` | 37120 | band analysis work area |
| `gl_vis_stick_work_t` x 4 | 42240 | one per strip of an L R R L group (2 suffice if segments are fitted pair by pair) |
| horizon band image | 61440 | 640 x 96 |
| stick strip images x 4 | 184320 | 96 x 480 each (1 suffices if each strip is refined before the next capture) |
| `gl_gfx_t` + LCD shadow | 2305 + 2048 | |
| `gl_proto_t` | 2096 | |
| `gl_store_t` | 1084 | |
| everything else (UI, tilt, grain, range, log, queue) | under 2000 | |

Worst-case stack of core call chains (`-fstack-usage`, `-Os`): 650 bytes (stick refinement:
176 + 104 + 368), 640 bytes (band analysis), 450 bytes plus the flash callbacks (store mount).
A 2 kB main stack covers the core with margin for the drivers.

Run time on the target has not been measured. From operation counts the band analysis is about
3 million single-precision operations and one strip refinement about 0.1 million.

## Provisional and unverified items

See `core/gl_provisional.h`. In short: OV7692 register 0x0C bit polarity, PWDN polarity, image
orientation after the prism, camera power-up delays; LCD FPC pin order / pin-1 side, EXTCOMIN
frequency range, LPTIM output in Stop 2, panel orientation, supply range; crystal-less USB;
battery thresholds; and, as estimates rather than facts, seating error, flagstick height and
width, grain strengths and the default grain threshold.

One assumption of this firmware is not in DESIGN_SPEC and must be checked against the PCB
layout: `gl_grain` takes "LED k at azimuth 22.5 + 45 k degrees in the marker frame" to mean the
angle `atan2(y, x)` of the LED position about the ring centre, counter-clockwise from marker +x
seen from above.

A second one must be checked against the mechanical design: the ball centre is taken at
outer radius + ball radius = 23.0 + 21.335 = 44.335 mm ahead of the marker centre
(`GL_CFG_BALL_CENTRE_Y_MM`), as specified for this work. If the ball in fact rests against the
flat visor face (18.4 mm from the centre) the value is 39.7 mm; only the generator constant
changes.

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
  the stick. The rectified disparity measured here is f * baseline / depth; multiply it by
  cos(bearing) when filling `gl_measurements_t`.

## Drivers, HAL backends, application

This section is completed by the driver / HAL work package. It must contain:

* a statement that `hal/stm32u5` is written against the STM32Cube HAL API and is not compiled
  here;
* **one table of every device register and command used for the LSM6DSV16X and the MX25R6435F,
  each marked "from memory - verify against datasheet"**;
* the sources used for OVM7692 register addresses (public Analog Devices msdk driver);
* what the host simulator checks (camera rail rule, LCD frame bytes, charlieplex pin states).
