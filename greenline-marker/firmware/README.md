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
* **Rev C.** `core/gl_config.h` is regenerated from the rev C YAML (stereo baseline 20.0 mm,
  cameras at x = +-10.0 mm). The user calibration is a **zeroing on any hard flat surface**
  (read, turn the marker 180 degrees in place, read again). It is never done in the cradle,
  which takes the marker one way round only: the UI state is `CAL_ZERO` (rev B: `CAL_FLIP`), it
  can be entered only from the settings dial, being put into the cradle abandons it, and the
  USB command that asks for it is answered with `GL_ERR_STATE`.

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
    left camera around its calibrated horizon row -> matched-line detector -> candidate
    -> 96 x 480 strips L R R L x 8, each refined while the next is captured -> segment fits
    over the lowest 0.4 m, timing correction, disparity accumulation -> camera rail off
    -> averaged base / top / horizon rows -> bearing and elevations relative to gravity
    -> range fusion (stereo + angular height), stick-height learning -> GL_EV_CAPTURE_DONE
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
| `tests/` | Host unit tests, one executable per `test_*.c`, with the tiny runner `gl_test.h`; `test_drv_*.c` check bus traffic, `test_e2e.c` runs the whole firmware on the simulator. |
| `tests/synth/` | Synthetic strip renderer (`gl_synth`) and simulated NOR flash with power cuts (`gl_simflash`). |
| `tools/` | `gen_config.py` (YAML -> `core/gl_config.h`), `gen_font.py` (-> `core/gl_font_data.c`), `gen_pins.py` (-> `hal/stm32u5/gl_pins.h`, cross-checked against DESIGN_SPEC), `cross_report.sh`. |

## Building and testing

```
make test     # gcc -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror, builds
              #   core + drivers + app + simulator and runs all 19 test executables
make asan     # the same under -fsanitize=address,undefined,float-cast-overflow
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
| `gl_vision` | Flagstick on 8-bit luminance strips: horizon-band analysis (per-column edge energy, matched vertical-line detector for leans of +-3 degrees at 4 widths, turf-horizon samples); sub-pixel line fit on the tall strip (per-row centroid, both polarities, trimmed / reweighted least squares, outlier rows); ends of the stick; segment fit; stereo disparity over the L R R L repeats with uncertainty; quality metrics. |
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
* **Averaging over the repeats.** Each strip gives its own lowest point, top and horizon row;
  the application averages them over the left-camera strips of a read before classifying the base
  (`GL_VIS_BASE_MARGIN_ROWS`) and converting to elevations.

## Drivers

Every driver includes only `hal/gl_hal.h` and core headers, keeps its state in a caller-provided
structure, and is tested against the simulator for its exact bus traffic.

| Driver | What it does | What its test checks (`tests/test_drv_*.c`) |
|---|---|---|
| `ov7692` | The two OVM7692 cubes on the shared parallel bus. Power-up: rail enable, settle, PWDN asserted, XVCLK, buses to their peripherals, then one camera at a time: PWDN released, software reset, **bus released at once** (register 0x0C), product id, MIPI off, YUV422, sleep. Power-down: capture and clock stopped, every camera-facing pin analog or driven low, then the rail. Break-before-make bus ownership; strip window on the sensor (default) or by DCMI crop; Y-only capture through the DCMI byte select. Any error during power-up ends with the rail off. | The pin and register sequence of power-up and power-down record by record; no camera-facing pin moves before the rail has settled; nothing but the rail enable moves after it; 21 power cycles without a rule violation; register values of both window modes; pixel-exact strip contents from both cameras in both modes; settle frames; L R R L timing with unsynchronised sensors; missing camera, wrong product id, reset that never completes, capture time-out: rail off and pins parked every time. |
| `ls013b7dh03` | Sharp memory LCD: SPI mode 0, chip select active HIGH, LSB first, 1 MHz; mode byte, per line address + 16 bytes + 8 dummy bits, 8 more dummy bits; only lines that differ from a shadow copy are sent; DISP and the LPTIM1 EXTCOMIN timer (on: clear, timer, DISP; off: DISP, timer). Both panel mountings (row / column order) selectable. | The exact bytes of a frame for a known image (hand-written expectation), frame length 1 + 18 k + 1, full frame 2306 bytes in 18.5 ms, only changed lines sent, all four mountings pixel by pixel on random images, a UI screen reaching the panel inside the round aperture, on / off order, and that the model catches MSB-first, a clock that is too fast, a bad frame length, DISP without EXTCOMIN and a missing chip-select set-up time. |
| `lsm6dsv16x` | IMU on SPI2, mode 3: WHO_AM_I probe, software reset, BDU + IF_INC; MEASURE mode (accel +-2 g high-performance and gyro +-1000 dps at 240 Hz, data-ready on INT2); WAKE mode (accel low-power 15 Hz, gyro off, wake-up on INT1); samples mapped into marker axes; temperature. | The exact bytes of init; register values of both modes; scale factors; every axis mapping; 240 data-ready interrupts per second; wake-on-motion latency; absent device; the driver's samples through `gl_tilt` to a slope. |
| `mx25r` | SPI NOR: JEDEC id, read, page program split at 256-byte boundaries with WREN and status polling, 4 kB sector erase, deep power-down with automatic wake; `gl_flash_if_t` for `gl_log` / `gl_store`. | The exact command bytes; page splitting; WREN before every program and erase; deep power-down; the ring log and the blob store running on the driver (3237 page programs, 19 erases, no non-blank byte programmed). |
| `grain_frontend` | 16 LEDs charlieplexed on 5 pins (anode push-pull high, cathode push-pull low, the other three analog; all analog = off; break before make), OPAMP1 + ADC power sequence, dark / on / dark per LED, scan order alternating red / NIR and reversed on odd cycles. | **The pin states of all 16 LEDs** against a table written out independently in the test, the 9 pin operations of each switch in order, that exactly one LED of the model's netlist lights; a sneak-path analysis of the proposed wiring (30 two-LED paths, none NIR-only beside a lit red LED); the ADC sequence with the lit-LED mask of every conversion; values through `gl_grain` (modulation 0.400, azimuth -30.0 deg recovered); drift, motion, threshold from the calibration record. |
| `power` | Battery through the 2 x 1 Mohm divider (VDDA from VREFINT), percent, low / critical, VBUS and charger STAT, PROG-enable gate: charging only with VBUS and 0-45 C, 2 K hysteresis, unknown temperature = stop. | Pin configuration (PROG open drain, released), the exact ADC sequence (on, one conversion, off), conversion at several cell voltages and a sagging rail, interrupts, and the PROG pin level over a sweep of temperature and VBUS. |

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
  not refreshed for 32 s; a sleep that nothing could ever end.

`tests/test_e2e.c` adds an **independent** check of the camera rail rule: it replays the
recorded pin trace with its own model and counts moments at which a camera-facing pin is neither
analog nor driven low while the rail is off, and bus accesses with the rail off.

### STM32U5 backend (`hal/stm32u5`) - never compiled

| File | Content |
|---|---|
| `gl_pins.h` | **Generated** by `tools/gen_pins.py`: logical pin -> port, pin, LQFP-64 pad, function, AF number, source. 19 rows are SPEC (DESIGN_SPEC section 4: the eleven DCMI pins, MCO, SPI1 MISO, USB D-/D+, LPTIM1_CH1, the three OPAMP1 pins); the generator parses the spec text and refuses to generate if a SPEC row disagrees. **26 rows are PROPOSED** by this firmware because no netlist exists: SPI1 SCK / MOSI (PA5 / PA7), SPI2 (PB13 / PB14 / PB15), chip selects, IMU INT1 on PC13 (WKUP2) and INT2 on PC5, the camera rail enable, PWDN and SCCB lines, the five charlieplex pins (PC0-PC4), VBAT sense on PA2, charger and VBUS pins. Pads outside the verified list come from the LQFP-64 pinout as remembered (it agrees with every pad that the BOM verification lists); AF5 for the SPI pins and ADC1_IN7 for PA2 are from memory. |
| `gl_hal_stm32u5.c` | Clocks (MSIS 48 MHz trimmed against LSE, no PLL; XVCLK = MSI / 4 on MCO), tick on LPTIM3 from LSE (runs through Stop 2), RTC seconds and RTC wake-up timer, GPIO from the pin table, EXTI sources, Stop 2 / sleep that returns only for an enabled source and cannot lose a wake-up, SPI1 / SPI2, **bit-banged SCCB** (two clock lines for two sensors at one address: no I2C peripheral can do that), DCMI snapshot with crop + byte select through GPDMA, ADC1 14-bit, OPAMP1 standalone, LPTIM1 PWM for EXTCOMIN, independent watchdog (32 s), unique id, reboot, jump to the ROM DFU bootloader through a backup-register flag. |
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
* **Read** (`gl_read.c`). A step machine that never waits for a frame. Two strip buffers: strip
  k is analysed while strip k + 1 is captured by DMA. The rail is switched off when the last
  strip is in memory, before it is analysed, and on every error or abort. **Timing of L R R L:**
  the two sensors free-run, so the four strips are not equally spaced (42 / 33 / 58 ms with a
  9 ms phase offset) and the mean time of the L pair differs from that of the R pair by up to
  about 14 ms; the completion time of every strip is recorded and the left positions are moved
  to the mean time of the right pair along the left camera's own measured sway rate. Base, top
  and horizon rows are averaged over the left strips before the base is classified.
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
  tilt, power, grain). Calibration procedures: six-face (one still average per face, then solve
  and store) and grain white reference are implemented; `GRAIN_FLOOR` and `CAM_HORIZON` answer
  `GL_ERR_UNSUPPORTED`; `ZERO` answers `GL_ERR_STATE` (never in the cradle).
* **Storage.** 4 sectors of blob store (settings, calibration, learned stick height) and 2044
  sectors of ring log on the 8 MB flash. One 72-byte record per read; raw strips as 978-byte
  records (18-byte header + 960 pixels) so that each fits one USB log response.
* **Power.** Battery measured at wake-up and every 30 s (not during a read); below the LOW
  threshold the battery symbol shows it, below CRITICAL the warning screen is shown and the
  device sleeps (no camera read from a cell that the camera rail could brown out); the charge
  gate follows the IMU temperature. Wake-up interrupts of the IMU are ignored for 300 ms after the device went to
  sleep, in case the sensor's slope detector trips on its own mode change (behaviour unknown;
  without the hold-off a spurious wake would repeat for ever).

## Measured results (host, synthetic data)

These are copied from `make test`; re-run it to reproduce them.

### End to end (`tests/test_e2e.c`, the whole firmware on the simulator)

Scene: green sloped (1.2, -2.0) %, flagstick 6.0 m away and 2.9 degrees to the left, 15 mm
wide (1.6 px), SNR 20, swaying +-0.3 px at 1.5 Hz; sensors 9 ms out of phase; marker put down
between t = 1.0 and 1.6 s. Computation takes no simulated time.

| Quantity | Result |
|---|---|
| State sequence | SLEEP, WAKE (1.02 s), WAIT_STILL (1.82 s), READ_TILT (2.36 s), CAPTURE (3.42 s), SOLVE, SHOW_RESULT (5.03 s) |
| Result on the screen | 3.44 s after the marker came to rest (0.76 s until stillness is established, 1.07 s tilt read, 1.62 s camera part including power-up and settling) |
| Camera rail | on once, for 1556 ms; 33 captures, 85 SCCB writes; rail never on outside the CAPTURE state |
| Camera rail rule | simulator: 0 violations; independent replay of the 17.6 k trace records: 0 pin-rule violations, 0 bus accesses with the rail off |
| Slope | (1.200, -2.007) % against (1.200, -2.000) % |
| Disparity | 2.1991 px against 2.1985 px true (claimed sigma 0.016 px with the sway) |
| Range | 5.982 m against 5.984 m (stereo 5.982, angular height 5.971 with the prior stick height) |
| Bearing | 48.46 mrad against 48.46 mrad |
| Screen | panel memory identical to the framebuffer; the aim line passes through the predicted pixels |
| While the result is shown | MCU in Stop 2 for 99.5 % of the time (IMU at 240 Hz) |
| After 45 s | display off, IMU wake-on-motion, flash in deep power-down, Stop 2; at most 6 loop iterations in the next 60 s (watchdog refresh every 16 s) |
| Log | one boot event and one read record, decoded and compared with the result |

What the L R R L timing correction is worth (stick drifting steadily at 6 px/s = 0.2 px per
frame, 8 groups):

| Sensor phase offset | Disparity error, corrected | Uncorrected |
|---|---|---|
| 2 ms | +0.008 px | -0.002 px |
| 9 ms | +0.002 px | +0.050 px |
| 16 ms | +0.001 px | +0.007 px |
| 24 ms | +0.005 px | -0.038 px |
| 31 ms | +0.002 px | -0.082 px |

Other end-to-end scenarios, all with zero simulator violations:

* **DCMI-crop windowing** (the fallback if the sensor window registers do not mean what is
  assumed): stick at 3 m, range 2.981 m against 2.984 m.
* **Raw-strip logging.** Level FIRST: the first left and right strips arrive in the log byte
  for byte (2 x 48 records); the read takes 5.9 s instead of 3.4 s. Level ALL: 1600 records,
  1.6 MB, **45.9 s per read with the camera rail on for 42.7 s** - a bench mode, see open issues.
* **No flagstick:** the rail is on for 157 ms (band only), the UI asks for the distance; with a
  dialled distance a tilt-only result along the visor axis.
* **Bumped 0.4 s into the capture:** read aborted and rail off within one 133 ms block,
  re-read by itself.
* **Precision Read:** spin measured 176.03 degrees (true 176.00); a device bias of (0.4, -0.3) %
  cancels: combined slope (1.199, -2.003) % against (1.200, -2.000) %; no second camera read.
* **Survey:** second drop 3 m further along, both drops stored with their own range and slope.
* **Zeroing** on a table sloped (0.6, -1.1) % with a turn of -171 degrees: stored bias
  (3.524, -2.508) mrad against (3.500, -2.500) true, present after a power cycle; a 120 degree
  turn is refused; being put into the cradle abandons it; it cannot be started in the cradle.
* **Cradle:** protocol over the simulated CDC port (ping, info, status, settings, calibration,
  log dump, streams), charging enabled at 22 C, stopped at 47 C, re-enabled at 30 C, never Stop
  mode on USB, reboot to ROM DFU requested, asleep after removal.
* **Missing IMU / missing camera:** shown as an error, not fatal; rail off.
* **Battery:** at 3.45 V (low) the read runs; at 3.30 V (critical) the warning is shown and the
  device sleeps without ever powering the cameras; in the cradle it charges.
* **Spurious wake-up interrupt 50 ms after going to sleep:** ignored; a later one wakes.


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
  error -0.03 % at 3 m, -0.03 % at 6 m, -0.36 % at 10 m (rev C baseline of 20.0 mm); bearing error
  below 0.03 mrad.
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
  mount: 0 failures (every id holds its last acknowledged value or the one in flight).
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
| core | gl_vision | 10810 | 0 | 0 |
| core | gl_ui | 4366 | 0 | 0 |
| core | gl_gfx | 4100 | 0 | 0 |
| core | gl_log | 3934 | 0 | 0 |
| core | gl_tilt | 3264 | 0 | 0 |
| core | gl_proto | 2188 | 0 | 0 |
| core | gl_cal | 2160 | 0 | 0 |
| core | gl_grain | 1888 | 0 | 0 |
| core | gl_range | 1880 | 0 | 0 |
| core | gl_cam | 1504 | 0 | 0 |
| core | gl_math | 1412 | 0 | 0 |
| core | gl_settings | 1242 | 0 | 0 |
| core | gl_gesture | 970 | 0 | 0 |
| core | gl_font_data | 632 | 0 | 0 |
| core | gl_fmt | 477 | 0 | 0 |
| core | gl_solver_stub | 216 | 0 | 0 |
| core | gl_event | 148 | 0 | 0 |
| core | gl_crc | 100 | 0 | 0 |
| core | **total** | **41291** | **0** | **0** |
| drivers | ov7692 | 1901 | 0 | 0 |
| drivers | lsm6dsv16x | 960 | 0 | 0 |
| drivers | mx25r | 870 | 0 | 0 |
| drivers | ls013b7dh03 | 674 | 0 | 0 |
| drivers | grain_frontend | 530 | 0 | 0 |
| drivers | power | 430 | 0 | 0 |
| drivers | **total** | **5365** | **0** | **0** |
| app | gl_app | 7010 | 0 | 1366 |
| app | gl_read | 2364 | 0 | 0 |
| app | gl_usb | 1846 | 0 | 388 |
| app | gl_motion | 830 | 0 | 0 |
| app | gl_main | 24 | 0 | 184512 |
| app | **total** | **12074** | **0** | **186266** |
| all | **total** | **58730** | **0** | **186266** |

RAM (ARM `sizeof`, from the same build; core and drivers have no `.data` / `.bss` of their own,
all state is in the application object):

| Object | Bytes | Note |
|---|---|---|
| `gl_app_t` (bss of `gl_main`) | 184512 | everything below is inside it |
| - strip buffers `gl_read_t.img` | 92160 | two 96 x 480 strips; the 640 x 96 band (61440) uses the same memory |
| - `gl_vis_band_work_t` | 37120 | band analysis |
| - `gl_vis_stick_work_t` x 4 | 42240 | one per strip of an L R R L group |
| - LCD: `gl_gfx_t` + driver shadow | 2305 + 2060 | |
| - `gl_proto_t` | 2096 | two 1032-byte frame buffers |
| - solver inputs `gl_measurements_t` x 5 | about 2000 | the shown read + 4 Survey drops |
| - `gl_store_t` | 1084 | settings and calibration blobs |
| - everything else (UI, motion, tilt, survey, drivers, log) | under 3000 | |
| static scratch in `gl_app.c` / `gl_usb.c` | 1754 | one raw-strip log record (978), two raw grain measurements (388 each) |
| STM32 backend (estimate, not compiled) | about 3000 | HAL handles, pin shadows, two 1 kB USB rings |
| main stack (recommended) | 4096 | see below |
| **total** | **about 195 kB of 786 kB** | |

Stack (`-fstack-usage`, `-Os`, bytes per frame): `gl_app_run_once` 312, `gl_read_step` 208,
`do_actions_` 240, `gl_usb_service` 208, `gl_lcd_update` 200, `gl_store_mount` 200,
`gl_vis_band_analyse` 528, `measure_row_` 368. Worst chains:

| Chain | Bytes |
|---|---|
| run_once -> read step -> stick refinement (176 + 104 + 368) | about 1170 |
| run_once -> read step -> band analysis (640 with callees) | about 1160 |
| run_once -> read step -> raw-strip hook -> log append -> flash driver | about 850 |
| run_once -> actions -> solve -> log append -> flash driver | about 800 |
| run_once -> USB service -> protocol -> log read -> log iterator -> flash driver | about 800 |
| init -> store mount -> log walk -> flash driver | about 500 |

Add the HAL's own frames below the drivers (not measured: not compiled) and interrupt frames
(104 bytes each with FPU state, handlers are short). A 4 kB main stack leaves a factor of two.
No function recurses.

Run time on the target has not been measured. From operation counts the band analysis is about
3 million single-precision operations (of the order of 0.2-0.4 s at 48 MHz, during which the
camera rail is on) and one strip refinement about 0.1 million (of the order of 10 ms, inside one
frame period, which the two-buffer pipeline needs). If the first figure is too slow on hardware
the options are a PLL clock during the read or a narrower search; see open issues.

The firmware's own code is 58.7 kB of the 2 MB flash before libraries.

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
| LSM6DSV16X | CTRL3 0x12 | bit 6 BDU, bit 2 IF_INC (address auto-increment), bit 0 SW_RESET; reset value 0x44 | reset, 0x44 | from memory - verify against datasheet |
| LSM6DSV16X | CTRL6 0x15 | [3:0] gyro full scale: 3 = +-1000 dps | 0x03 | from memory - verify against datasheet |
| LSM6DSV16X | CTRL8 0x17 | [1:0] accel full scale: 0 = +-2 g | 0x00 | from memory - verify against datasheet |
| LSM6DSV16X | STATUS_REG 0x1E | bit 0 XLDA, bit 1 GDA, bit 2 TDA | data-ready poll | from memory - verify against datasheet |
| LSM6DSV16X | OUT_TEMP 0x20-0x21 | int16 little-endian, 256 LSB per K, 0 = 25 C | charge gate, tilt compensation | from memory - verify against datasheet |
| LSM6DSV16X | OUTX_L_G 0x22 .. OUTZ_H_A 0x2D | gyro X Y Z then accel X Y Z, int16 little-endian, one 12-byte burst | samples | from memory - verify against datasheet |
| LSM6DSV16X | Sensitivities | 0.061 mg/LSB at +-2 g; 35 mdps/LSB at +-1000 dps | scale factors handed to `gl_tilt` | from memory - verify against datasheet |
| LSM6DSV16X | WAKE_UP_SRC 0x45 | bit 3 WU_IA; reading clears the latch | wake cause | from memory - verify against datasheet |
| LSM6DSV16X | FUNCTIONS_ENABLE 0x50 | bit 7 INTERRUPTS_ENABLE | wake-on-motion | from memory - verify against datasheet |
| LSM6DSV16X | TAP_CFG0 0x56 | 0x00: slope filter (bit 4 SLOPE_FDS = 0), interrupts not latched | wake-on-motion | from memory - verify against datasheet |
| LSM6DSV16X | WAKE_UP_THS 0x5B | [5:0] threshold, 7.8125 mg per LSB at the reset threshold weight | 62 mg -> code 8 | from memory - verify against datasheet |
| LSM6DSV16X | WAKE_UP_DUR 0x5C | 0x00: one sample over threshold wakes | wake-on-motion | from memory - verify against datasheet |
| LSM6DSV16X | MD1_CFG 0x5E | bit 5 = wake-up event on INT1 | 0x20 | from memory - verify against datasheet |
| LSM6DSV16X | Behaviour | temperature output valid while the accelerometer runs; software reset completes within 1 ms; INT pins push-pull, active high, pulsed | driver sequences | from memory - verify against datasheet |
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
| 0x0C | bit 7 vertical flip, bit 6 horizontal mirror, YU/YV swap, reset value 0x16 | **bits 2 and 1 = output drive, 1 = driven** (`GL_PROV_OV7692_REG0C_BIT_SET_MEANS_DRIVEN`; meaning from the OV7690 datasheet, polarity inferred from the reset value) |
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
| OVM7692 bus | `GL_PROV_OV7692_REG0C_BIT_SET_MEANS_DRIVEN`, `_PWDN_ACTIVE_HIGH`, `_PWDN_TRISTATES_OUTPUTS`, `GL_PROV_CAM_SLEEP_IDLE_ON_EVERY_SWITCH`, `GL_PROV_OV7692_SCCB_ACKS` | tri-state bit polarity (DESIGN_SPEC PROVISIONAL), PWDN polarity, whether PWDN frees the bus (not relied on), idle-camera policy, the 9th SCCB bit |
| OVM7692 image | `GL_PROV_CAM_SENSOR_VFLIP`, `_HMIRROR`, `GL_PROV_OV7692_Y_IS_FIRST_BYTE`, `_VSYNC_ACTIVE_HIGH`, `_HREF_ACTIVE_HIGH`, `_PCLK_RISING`, `_PID`, `_ENFORCE_PID` | orientation behind the prism, byte order, sync polarities, product id value |
| OVM7692 window | `GL_PROV_OV7692_SENSOR_WINDOWING`, `_HSTART_FULL`, `_VSTART_FULL`, `_H_UNIT_PX`, `_V_UNIT_LINES`, `_H_BORDER_PX`, `_V_BORDER_LINES` | meaning of the start / size registers; set `_SENSOR_WINDOWING` to 0 to use the DCMI crop instead |
| OVM7692 timing | `GL_PROV_CAM_XVCLK_HZ`, `_RAIL_SETTLE_MS`, `_CLOCK_SETTLE_MS`, `_FRAME_PERIOD_MS`, `_SETTLE_FRAMES`, `GL_PROV_OV7692_RESET_TIMEOUT_MS` | power-up delays, frame rate at 12 MHz with reset clock settings, frames to settle |
| LCD | `GL_PROV_LCD_FPC_PIN_*` (10), `GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS`, `GL_PROV_LCD_ROW0_AT_FRONT`, `_COL0_AT_LEFT`, `_ACTIVE_CENTRE_Y_MM`, `_SPI_MAX_HZ`, `_VDD_MIN_MV`, `_SCS_SETUP_US`, `_SCS_HOLD_US`, `_SCS_LOW_US` | FPC pin order and pin-1 side (DESIGN_SPEC PROVISIONAL), EXTCOMIN range, panel orientation, active-area offset, timing |
| MCU | `GL_PROV_LPTIM_PWM_RUNS_IN_STOP2`, `GL_PROV_USB_CRYSTALLESS_HSI48_CRS`, the 26 PROPOSED rows of `hal/stm32u5/gl_pins.h` | EXTCOMIN in Stop 2 (if 0 the application stays in idle sleep while the display is on), crystal-less USB, pin assignment |
| IMU | `GL_PROV_IMU_MARKER_{X,Y,Z}_AXIS`, `_SIGN`, `GL_PROV_IMU_WAKE_THRESHOLD_MG` | mounting orientation on the PCB (identity is a placeholder), wake threshold |
| Flash | `GL_PROV_MX25R_PROG_TIMEOUT_MS`, `_ERASE_TIMEOUT_MS`, `_DP_DELAY_US`, `_SPI_HZ` | timing |
| Grain | `GL_PROV_GRAIN_RED_ANODE_ON_LOW_PIN`, `_SETTLE_US`, `_ADC_AVG`, `_ADC_SAMPLE_US`, `_POWER_SETTLE_MS`, `_MOD_THRESHOLD_DEFAULT`, `_MAX_EQUIV_SLOPE`, `_HARMONIC_SIGN`, `_KAPPA_BENT`, `_KAPPA_POA`, `_KAPPA_BERMUDA` | charlieplex wiring (proposal), settling, and the unproven physics; the acceptance threshold used is always the one in the calibration record |
| Power | `GL_PROV_BATT_LOW_MV`, `_CRITICAL_MV`, `_FULL_MV`, `_EMPTY_MV`, `_DIVIDER_RATIO`, `GL_PROV_CHARGE_TEMP_MIN_C`, `_MAX_C`, `_HYST_C` | cell thresholds (no cell datasheet), hysteresis |
| Estimates | `GL_PROV_SEATING_SIGMA_RAD`, `GL_PROV_STICK_TOTAL_HEIGHT_M`, `_IN_CUP_M`, `_HEIGHT_REL_SIGMA`, `_DIA_MIN_M`, `_DIA_MAX_M`, `GL_PROV_DISPARITY_SIGMA_PX` | not measurements |

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
* **Gesture tuning.** Thresholds are guesses; taps are detected in software from the 240 Hz
  stream (the IMU's embedded tap function is not used). The gesture maths is unit-tested, the
  thresholds are not field-tested.
* **Fuel gauging:** the percentage is a straight line between two provisional voltages.

## Open issues that need a decision

1. **Base of the stick for ranging.** `gl_vision` reports "at horizon" both for a base just
   visible on a flat green and for one hidden behind a crown. For RANGE (and for learning the
   stick height) the application treats the lowest visible point as the base in both cases and
   widens the elevation uncertainty from 0.3 to 0.8 row; otherwise the angular-height range
   would never be used on a flat green. For the SLOPE use the solver receives the strict flag.
   The estimator's owner should confirm or change this.
2. **Pin assignment.** 26 pins are this firmware's proposal (table in `tools/gen_pins.py`),
   including bit-banged SCCB on PB5 / PB3 / PA10 and the IMU wake line on PC13. The schematic
   may choose differently; only the generator table changes.
3. **Raw-strip logging level ALL keeps the camera rail on for about 43 s per read** (about 1 mAh
   of a 43 mAh cell, and heat), because only two strips fit in RAM beside the work areas and each
   takes half a second to write. It also suspends motion detection while a strip is written.
   Level FIRST costs 2.5 s. If ALL is wanted in the field, it needs a different capture plan
   (power the cameras down between groups) or less data.
4. **System clock 48 MHz without PLL** was chosen for simple, fast wake-up from Stop 2. If the
   band analysis (estimated 0.2-0.4 s with the rail on) is too slow, run from the PLL during a
   read.
5. **Watchdog in Stop mode.** The independent watchdog keeps running in Stop 2, so the sleeping
   device wakes every 16 s for a few microseconds. Freezing it in Stop by option byte would
   avoid that at the price of no supervision while asleep.
6. **Idle camera kept awake** during L R R L (deviation from the letter of DESIGN_SPEC, see
   Drivers) and **OVM7692 reset output size** (the public driver's comments suggest 384 lines).
7. **Zeroing over USB** is refused rather than "armed for when the marker leaves the cradle".
   If the factory wants to trigger it from the fixture, a guarded transition has to be added.
8. **State name.** `CAL_FLIP` of the original state list is now `CAL_ZERO` (rev C wording); the
   storage fields `flip_bias_*` and `GL_CAL_TILT_FLAG_FLIP` keep their names because they are the
   record format.
9. The open points of the core package still stand: phase bias of 0.041 px for a lens sharper
   than the design blur, +0.26..0.29 row bias of the lowest point when the stick ends at the
   turf horizon, and synthetic data that does not model the Bayer mosaic.

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
* `flag_base_visible` is passed strictly (base more than 1.5 rows below the turf horizon); see
  open issue 1 for how the range fusion treats the other case.
