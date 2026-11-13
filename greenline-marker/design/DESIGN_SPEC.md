# GreenLine GL-1 — master design specification (rev D, EVT1, with amendments E1 to E22)

This file records every architecture decision. `master_params.yaml` holds the numbers that the
mechanical CAD and the PCB layout must share; `check_layout.py` verifies them. Where this file
and the YAML disagree, the YAML wins and this file must be corrected.

Evidence levels used below:

- **VERIFIED** — confirmed in this project from a manufacturer or distributor source seen in a web search result, or from the installed KiCad library.
- **PROVISIONAL** — from engineering memory or an unconfirmed search extract. Must be checked against the manufacturer drawing or datasheet before boards are ordered. Every provisional item is repeated in `docs/RELEASE_GATES.md`.

Amendments after rev D (each is worked into the text below and marked with its number; the next revision letter is taken when the board layout is folded back in):

| # | Change | Why |
|---|---|---|
| E1 | Charger is a TI BQ25101 with a hardware battery-temperature input, replacing the MCP73831 | Charging outside the cell's temperature range must be stopped by hardware; the firmware review found two cases where firmware cannot do it (ROM USB loader running; firmware hung) |
| E2 | Two cell thermistors: one for the charger, one for the MCU; part changed to Murata NCU15XH103F60RC | The NCP15 part is flagged not recommended for new designs |
| E3 | Grain LED part numbers and real drive currents written down; near-infrared part changed | The SFH 4053 is on last-time buy; the research assumed 20 mA, the circuit gives about 6 and 10 mA |
| E4 | Top-side test points for VBAT, V2V8, V2V8_CAM and GND; board test powers the board through the cell-lead pads | A board without its cell could only be powered through the 20 mA charger |
| E5 | Lead-free assembly stated; no conformal coat at EVT | Was unstated |
| E6 | Cradle circuit written down (CC resistors, fuse, ESD) | Was only implied |
| E7 | The 0.10 mm track and gap is 3.94 mil; fabricator acceptance is a release gate | A "4 mil" tier is 0.1016 mm |
| E8 | Ball feet: 316 stainless or silicon nitride, not 440C | 440C rusts in wet fertilised turf |
| E9 | Quarter-wave film under the cover glass as an EVT trial | Polarised sunglasses can black out the display at some rotations |
| E10 | Base plate carries a printed legend (maker, model, required statements, serial box) | No place for the regulatory text existed |
| E11 | Factory level calibration on two seats: base face (used on turf) and ball feet (hard surface) | On turf the puck rests on its base face, not on the balls; the two planes differ by up to 1.6 mrad |
| E12 | Display rotation measured at the factory and stored | The glass can sit up to about 1 degree rotated in its pocket |
| E13 | No read above 60 C cell temperature; ship mode | Only charging was temperature-gated; the marker woke in the parcel |
| E14 | Sleep current and rail limits stated | No limits existed |
| E15 | Read time restated from the firmware timing model | "About three seconds" was older than the firmware |
| E16 | Baffle-ring tape 0.10 to 0.145 mm | No opaque black tape of exactly 0.13 mm was found |
| E17 | Guaranteed upward camera field restated as 14.0 degrees, defined at the loosest locating fit (0.125 mm: hole +0.05, spigot -0.05, spigots checked with a no-go gauge) with the roof at -10 C; the model gives 14.03 there. Test gate 2 bars move to +13.0 and -13.0 degrees. The stick top then enters the field at about 8.4 m on a worst-case unit (8.1 m before) | The 14.5 degree figure held only at the nominal 0.075 mm fit: the ordinary +0.05 mm hole tolerance alone took it to 14.496 |
| E18 | Legend print rules: line and space 0.15 mm or more, text 1.0 mm or more, ink 0.03 mm or less, none within dia 8.5 of a foot or 0.75 mm of the outline. Every fixture that takes the outer face as its reference bears on bare mask (gauge plate on three bosses, seat plate on three pads next to the feet, bridge depth gauge). Each statement block holds 88 characters; text that does not fit goes in the user guide and on the packaging | Legend ink under a flat plate would shift the ball protrusion by up to 0.03 mm and tilt the base-face zero by about 0.8 mrad |
| E19 | Quarter-wave trial film is dia 23.4 mm with a clocking flat (4.3 mm long at y 11.5), 0.11 mm or less with its adhesive | A round film carried no axis reference, and at dia 24.0 the placement chain could put it under the glass tape |
| E20 | Base-plate thickness accepted from 0.78 mm (FR-4) and 0.84 mm (PA12); ball diameter tolerance of grade 100 taken as +-0.0127 mm (to be confirmed against the ball standard) | An oversize ball left 0.007 mm of epoxy over its land at the old lower limits, against 0.02 required |
| E21 | Baffle-ring height = measured plate thickness + 0.15 - tape thickness; rings are printed 1.10 mm high and lapped | The earlier rule (plate + 0.02) was only right for one tape thickness |
| E22 | Display rotation in its pocket is up to about 1.2 degrees (computed 1.19); cell fixing adhesive 0.06 mm or less | Corrects E12's "about 1 degree"; no tape of 0.05 mm was found |

E17 to E22 come from the enclosure review of 2026-11-13. They are decided here and enter `master_params.yaml` and the CAD together at the next revision letter, so that the mechanical checks, which assert the YAML values, never run against a half-changed file. Until then the YAML still carries 14.5 degrees, [0.76, 0.90] / [0.83, 0.92], the plate + 0.02 ring rule and 0.05 mm, and the enclosure package records the same changes as proposals P1 to P9 (`mechanical/PROPOSED_PARAM_CHANGES.md`, part C). P6 (U11 0.2 mm inboard) is settled by the board placement.


## 1. What the product is

A self-contained electronic golf ball marker, a D-shaped puck 46.0 mm across and 7.6 mm thick.
The golfer sets it behind the ball with its flat "visor" face toward the hole, lifts the ball,
and about four to five seconds later (E15: firmware timing model, not measured) a line on the round display shows the start direction for the putt,
with the distance, slope and expected break.

It is a practice and training device. An electronic slope-reading ball marker is not permitted
during a round played under the Rules of Golf (Rule 4.3, and the Equipment Rules definition of an
alignment device). See `docs/research/rules-compliance.md`.

## 2. What it can and cannot measure (physics, not marketing)

A lens 5.6 mm above the turf sees the green edge-on. At that grazing angle the whole surface
beyond a couple of metres collapses into one or two pixel rows, so the cameras cannot produce a
contour map of the surface between ball and hole. The design therefore measures:

| Quantity | Sensor | Expected quality | Notes |
|---|---|---|---|
| Bearing to the hole | Forward cameras, flagstick detection | about 1 mrad | The most valuable camera output: it ties the aim line to the true hole direction. Flagstick must be in the hole. |
| Distance to the hole | Stereo pair (20.0 mm baseline, f = 657 px) fused with flagstick angular height (stick height learned per course) | Simulated fused error (random part only): 1 % at 1.5 m, 2 % at 3 m, 3.4 % at 6 m, 3.6 % at 9 m, 5 % at 12 m. Stereo alone: 5 % at 9 m, 7 % at 12 m. A stereo calibration drift of 0.1 px shifts the range by about 3 % | Aim angle is almost independent of distance, so 10 % is enough for the line; the tighter figure is for the displayed number and the pace advice. The stick top is inside the upward field (14.5 degrees guaranteed, 17.6 required nominal) only beyond about 7 to 8 m, and is usable on 52-59 % of long reads. |
| Mean slope ball-to-hole (uphill / downhill) | Elevation of the lowest visible point of the flagstick, referenced to gravity | 1-3 mrad when the base is visible; a one-sided bound when a crown hides it | Upper bound on the mean slope along the line. |
| Local slope vector and fall line at the ball | Puck tilt from the accelerometer | sensor about 0.5 mrad; seating on turf 2-5 mrad per placement (estimate, unmeasured) | Seating is the dominant error of the whole instrument. Reduced by a 180-degree spin-and-reread and by Survey mode. |
| Cross slope along the putt | Puck tilt only (one sample, or several in Survey mode) | 3-5 mrad single drop | No optical measurement of cross slope exists from this viewpoint. |
| Grain direction | Experimental photometric ring under the puck, plus a prior (grain tends to run down the fall line; strength from the grass type the user selects) | Unproven. Reviewer estimate 15-25 % chance the optical reading improves the line | Ships disabled until it passes the validation gates in `docs/research/grain-sensing.md`. |
| Green speed (Stimp) | Entered by the golfer (roll-to-set dial gesture) | golfer's estimate, about 7 % | Optional later feature: derive it by watching a rolled ball with the cameras. |

Operating modes:

1. **Quick Read** — one placement: tilt at the ball plus the flagstick-base height (method B1 of the simulator, the firmware default). Intended for putts to about 4.5 m; beyond that the median miss exceeds the hole radius in simulation.
2. **Precision Read** — place, read, spin the marker 180 degrees in place, read again. Cancels device bias and averages two seatings.
3. **Survey** — two to four placements along the line (ball, midpoint, about 1 m short of the hole). Each drop records tilt and its own range and bearing to the flagstick; the device fits a slope field through the samples. Intended for long or contoured putts.
4. **Flag-out fallback** — the golfer points the visor at the hole and dials in the distance; tilt-only read with a low-confidence indicator.

Simulated performance (`sim/results/REPORT.md`; synthetic greens, perfect stroke, grain reading off, 2.5 mrad seating noise assumed, 3600 putts from 1.5 to 12 m). Nothing here is a hardware measurement.

| Method | Holed, all lengths | Holed at 3 m | Holed at 6 m | Median miss |
|---|---|---|---|---|
| Aim straight at the flag | 8.9 % | 11 % | 4 % | 23.2 cm |
| Quick Read | 29.5 % | 44 % | 13 % | 9.9 cm |
| Precision Read | 31.6 % | 48 % | 14 % | 8.6 cm |
| Survey, three placements | 34.4 % | 52 % | 23 % | 7.1 cm |
| Golfer who reads cross slope to 0.5 % | 29.5 % | 42 % | 14 % | 9.5 cm |
| Golfer who reads cross slope to 1 % | 19.3 % | 25 % | 7 % | 16.4 cm |

The Quick Read is statistically level with a golfer who reads slope to 0.5 % and well ahead of one who reads to 1 %. That standing depends on inputs nobody has measured: seating repeatability on turf (the Quick Read falls 5 points behind the 0.5 % reader at 5 mrad), how accurately a golfer copies the displayed line (0.5 degrees assumed), and metre-scale relief of real greens. Measuring seating repeatability is the first task for a prototype.

## 3. System architecture

```
                 +--------------------------- always-on 2.8 V (MCP1700) ---------------------------+
 LiPo 3.7 V ---->|                                                                                 |
 2x10x30 mm      |   STM32U585RIT6  <--SPI2-->  LSM6DSV16X IMU (wake-on-motion, tilt, gyro)        |
   ^             |   Cortex-M33                                                                    |
   | BQ25101     |   2 MB / 786 kB  <--SPI1-->  LS013B7DH03 memory LCD 128x128 (LPTIM 60 Hz VCOM)  |
   | 20 mA       |                  <--SPI1-->  SPI NOR flash (raw-frame logging)                  |
 VBUS 5 V        |                  <--USB FS-> pogo pads D+/D- (settings, logs, ROM DFU)          |
 (cradle pogo)   |                  <--OPAMP1+ADC-- photodiode   --> 16 LEDs charlieplexed (grain) |
                 +--------+----------------------------------------------------------------------+
                          | DCMI 8-bit (shared bus), MCO clock, 2x SCCB, 2x PWDN
                 switched 2.8 V (LP5907, EN from MCU)
                          |
                 OVM7692 cube L          OVM7692 cube R        each with a 2 mm fold prism on top
```

Decisions and reasons:

- **One microcontroller, no radio.** The brief asks for a self-contained device. Dropping Bluetooth removes a module (140 mm2 and 2.1 mm tall), the antenna keep-out, the intentional-radiator work and the Bluetooth SIG listing fee (reported at about $12k, PROVISIONAL). Settings are made on the device; logs, calibration and firmware updates go through the charging cradle as a USB full-speed device (the STM32 ROM bootloader provides USB DFU). A Bluetooth variant is a later option.
- **STM32U585RIT6 (LQFP-64).** Hardware camera port (DCMI) with DMA and crop, 786 kB RAM (two VGA strips fit easily), single-precision FPU, Stop-mode current of a few microamps, crystal-less USB, and a pin map that is in the installed KiCad library (VERIFIED source of pad numbers). LQFP-64 is routable with ordinary 5/5 mil rules; the WLCSP and 0.5 mm BGA variants would need an HDI board.
- **OVM7692-RYAA camera cubes, mounted flat, each with a 2 mm aluminised right-angle prism bonded on top.** The cube is 2.95 x 3.47 x 2.76 mm (VERIFIED: OmniVision product brief via search; DigiKey 884-1027-1-ND, in stock). Mounting it flat keeps both cameras and the accelerometer on one rigid FR-4 board, which the stereo and gravity-reference budgets need (a printed shell moves by milliradians with temperature). The prism turns the view to horizontal and puts the optical axis 5.6 mm above the turf. Two small flat windows on the visor face close the openings, so the optics stay dry and are mechanically isolated from the shell.
- **20.0 mm stereo baseline.** Set by the display: the 26.6 x 30.3 mm LCD glass leaves room for the cubes only in front of its forward edge. Stereo covers short and medium putts; flagstick angular height covers long ones.
- **Tilt sensing.** LSM6DSV16X 6-axis IMU (VERIFIED pin-compatible with the LSM6DSM symbol in the KiCad library; LGA-14L 2.5 x 3.0 x 0.83 mm), with per-unit factory temperature compensation and a user zeroing routine on any hard flat surface (read, turn the marker 180 degrees in place, read again: the reversal cancels the surface's own tilt). Factory calibration is done on a granite surface plate. Target 0.5-1 mrad. A precision inclinometer (ST IIS2ICLX) was considered and left off this board: its pin map and footprint could not be verified from any reachable source, it costs about $28 and is 1.7 mm tall, and turf seating (2-5 mrad), not sensor error, is expected to dominate. It remains a documented option for a later revision.
- **Display.** Sharp LS013B7DH03, 1.28 inch 128 x 128 reflective memory LCD (outline 26.6 x 30.3 x 0.746 mm VERIFIED from Sharp's brochure via search; DigiKey 425-2903-ND). Sunlight readable, about 15 microwatts static. Seen through a 22 mm round aperture under a 28 mm mineral-glass watch crystal. The smaller LS010B7DH04 would allow a smaller puck but has no US distributor listing.
- **Power.** PowerStream GM201030-PCB lithium-polymer cell, 2 x 10 x 30 mm, about 43 mAh (VERIFIED listing; capacity, protection-board size and safety certificates still to be obtained), charged at 20 mA from cradle VBUS by a TI BQ25101 linear charger (E1: 6-ball 1.6 x 0.9 mm package, 10 to 250 mA, with a thermistor input that enforces the JEITA charge-temperature profile in hardware and an open-drain charge-status output; VERIFIED from TI data-sheet extracts via search, ball map PROVISIONAL). Microchip MCP1700-2.8 (1.6 uA quiescent) feeds the always-on 2.8 V rail; TI LP5907-2.8 with enable feeds the cameras only during a read, so MCU and camera logic levels match. A second MCP1700 (3.3 V) fed from VBUS powers only the MCU's independent VDDUSB pin, because USB needs at least 3.0 V there and is only used in the cradle. No coin cell (Reese's Law / UL 4200A obligations and height).
- **Grain sensor.** Eight red and eight near-infrared 0402 LEDs on a 5.2 mm radius and one low-profile photodiode, all on the PCB underside inside a 13 mm opening in the base. The photodiode current is amplified by the MCU's internal op-amp and sampled by its ADC with LED-on minus LED-off differencing. Experimental (section 2).
- **Charging and data contacts.** Seven flush gold pads on the PCB underside, reached through one slot in the base by spring pins in the cradle: VBUS, D-, D+, GND, SWDIO, SWCLK, NRST. The consumer cradle fits the first four pins only; the factory fixture fits all seven. The cradle accepts the marker in one orientation and holds it down against the pin force (about 0.6 N per pin against a marker weight of 0.11 N).

## 4. Electrical design rules for the netlist

Rails:

| Rail | Source | Loads | Notes |
|---|---|---|---|
| VBUS | cradle pad, 5 V | BQ25101 IN, VBUS-sense divider | USBLC6-2SC6 clamps VBUS, D+, D-. Series Schottky from pad to charger. |
| VBAT | cell + PCM, 3.0-4.2 V | MCP1700-2.8 in, LP5907 in, battery divider | 2 x 1 Mohm divider with 100 nF to an ADC pin. The grain LEDs are driven from MCU pins on the 2.8 V rail, not from VBAT. |
| V2V8 | MCP1700T-2802E/TT | MCU VDD/VDDA/VBAT pin, IMU, LCD VDD/VDDA, flash | 1 uF in, 1 uF out ceramic. 100 nF per MCU supply pin plus 4.7 uF bulk; VDDA through 10 ohm with 1 uF + 10 nF. LCD VDD range 2.7-3.3 V (PROVISIONAL). |
| VDDUSB | MCP1700T-3302E/TT fed from VBUS (after the Schottky) | MCU VDDUSB pin only | Present only in the cradle. Firmware sets the USB-supply-valid bit only when VBUS is detected. 1 uF in, 1 uF out. |
| V2V8_CAM | LP5907MFX-2.8/NOPB, EN from MCU with 100k pull-down | both camera AVDD and DOVDD | 1 uF in, 1 uF out. Camera DVDD pin: 1 uF to ground each (internal 1.5 V regulator). |

Rules the firmware must honour and the schematic must make possible:

- Every MCU pin that faces a camera (data, PCLK, HREF, VSYNC, XVCLK, SCCB, PWDN) must be driven low or left analog while V2V8_CAM is off, to avoid back-powering the sensors through their protection diodes. SCCB pull-ups (2.2 kohm) go to V2V8_CAM, not V2V8.
- The two cameras share the 8 data lines, PCLK, HREF and VSYNC. Only one drives the bus at a time: the idle camera has its outputs tri-stated through register 0x0C bits 2 and 1 (register address and default 0x16 VERIFIED from the public Analog Devices OV7692 driver; the bit meanings are PROVISIONAL) and is held in sleep. Each camera has its own SCCB clock line and its own PWDN line; SCCB data is shared. Every camera output (D0-D7, PCLK, HREF, VSYNC) joins the shared bus through a 220 ohm series resistor placed at that camera (three 4-element 0402-in-0804 arrays per camera, for example Panasonic EXB-28V221JX, PROVISIONAL stock). Reason: both cameras' output pads are enabled together for about 14 ms at every power-up unless PWDN tri-states them, which is unconfirmed; the resistors limit that contention to about 6 mA per line, and they also limit the current into an unpowered camera from pins the ROM bootloader drives (PB9 = D7, PA6 = PIXCLK). XVCLK has a 33 ohm series resistor at the MCU. Each PWDN line has a 1 kohm series resistor and must not use a pin that the ROM bootloader drives as an output (the USART transmit pins PA9, PA2 and PC10, PROVISIONAL from memory of ST AN2606; verify).
- XVCLK comes from the MCU MCO pin (PA8), nominally 12 MHz.
- DCMI pin assignment on LQFP-64 (VERIFIED against ST's open pin data: pad numbers and alternate functions): D0 PC6 pad 37 AF10, D1 PC7 pad 38 AF10, D2 PC8 pad 39 AF10, D3 PC9 pad 40 AF4, D4 PC11 pad 52 AF10 (not AF4, which is D2 on that pin), D5 PB6 pad 58 AF10, D6 PB8 pad 61 AF10, D7 PB9 pad 62 AF10, PIXCLK PA6 pad 22 AF4, HSYNC PA4 pad 20 AF10, VSYNC PB7 pad 59 AF10. MCO PA8 pad 41. Because PA6 is PIXCLK, SPI1 MISO for the flash must be PB4 (pad 56, AF5). The pin data is at raw.githubusercontent.com/STMicroelectronics/STM32_open_pin_data (mcu/STM32U585RITx.xml and mcu/IP/GPIO-STM32U5x_gpio_v1_0_Modes.xml); use it for every alternate-function choice.
- USB: PA11 = D- (pad 44), PA12 = D+ (pad 45), crystal-less (HSI48 with clock recovery; PROVISIONAL). VDDUSB (pad 48) from its own 3.3 V regulator as above.
- LCD: SPI clock and data plus an active-high chip select; DISP on a GPIO with pull-down; EXTCOMIN from LPTIM1 or LPTIM3 (they run in Stop 2; LPTIM2 does not), for example LPTIM1_CH1 on PB2 (pad 28), at 59.9 Hz (32768 / 547; 546 would give 60.015 Hz, just outside the 1-60 Hz range), which is inside both frequency ranges Sharp publishes (54-65 Hz and 1-60 Hz); EXTMODE tied high. J1 is a TOP-contact connector (Hirose FH12A-10S-0.5SH(55), 2.0 mm high, on the FH12 land pattern) because the LCD tail makes one U-fold under the glass, which turns its contacts upward. Which end of the tail is pin 1 is PROVISIONAL and must be read from the Sharp drawing: a wrong guess mirrors all ten pins. LCD connector pin order (PROVISIONAL, from the Sharp datasheet as remembered and consistent with public drivers): 1 SCLK, 2 SI, 3 SCS, 4 EXTCOMIN, 5 DISP, 6 VDDA, 7 VDD, 8 EXTMODE, 9 VSS, 10 VSSA.
- IMU on its own SPI bus; INT1 (latched) to a wake-capable pin, INT2 to a second GPIO.
- Pin map: `firmware/hal/stm32u5/gl_pins.h` holds the firmware's proposal for every pin the lines above do not fix. The netlist may change proposed pins for routing; the netlist then wins and exports the final map, from which the firmware header is regenerated. Every alternate function must be checked against the KiCad symbol or ST's open pin data.
- Clocks: no high-speed crystal. The MCU runs from its internal oscillators; during a read the PLL raises the core clock to 160 MHz (the vision code needs about 145 million instructions per read), otherwise it runs slowly or sleeps in Stop 2. USB uses the internal 48 MHz oscillator with clock recovery.
- Grain LEDs: 16 LEDs charlieplexed on 5 MCU pins with one series resistor per pin (5 x 68 ohm), red and NIR LED of each pair antiparallel where possible. Parts (E3): red Vishay VLMS1500-GS08 (0402); near-infrared ams OSRAM SFH 4053B (0402, the successor of the SFH 4053, which is on last-time buy; PROVISIONAL until its data sheet is read), alternative Inolux IN-S42CTQIR (850 nm, 0402). Two 68 ohm resistors are in series with every LED, so the drive is about 6 mA red and 10 mA infrared on the 2.8 V rail (within the MCU pin rating), not the 20 mA the early research assumed; the firmware integrates longer instead. Photodiode cathode to the op-amp inverting input, 470 kohm + 10 pF feedback, non-inverting input at a mid-rail bias from a 2 x 100 kohm divider with 100 nF. With 470 kohm the amplifier saturates at about 3 microamps of photocurrent; the feedback resistor is an ordinary 0402 so that it can be lowered if the sunlight-leak test (validation plan L2) shows saturation.
- Charger (E1): TI BQ25101YFP (4.20 V, DSBGA-6, 0.4 mm ball pitch, all six balls on the perimeter). IN from VBUS after the Schottky with 1 uF; OUT to the cell with 1 uF. ISET resistor 6.81 kohm 1 % to ground (K = 135 A-ohm, so 19.8 mA, about half the cell capacity per hour); the part terminates at 10 % of that. TS to a 10 kohm NTC at the cell (below): the charger halves the current when cold, lowers the charge voltage to 4.06 V when hot and does not charge outside its window (JEITA profile; thresholds PROVISIONAL until the data sheet table is read against the NTC curve). This works with the MCU unpowered, held in reset, hung or in the ROM USB loader, and a cell at its protection cut-off is recharged with no firmware. CHG (open drain, low while charging) to an MCU input with a 100 kohm pull-up to V2V8. Firmware stop: CHG_INHIBIT is an MCU push-pull output to the gate of a small N-MOSFET (for example onsemi BSS138, gate pulled down with 100 kohm) that pulls TS to ground, which the charger reads as "too hot"; with the MCU off the MOSFET is off and cannot disturb TS. Fallback on the same footprint: BQ25100YFP, where the same ball is a pre-charge / termination programming input instead of the status output; the board carries an unpopulated resistor position from that ball to ground for it. The ball map is PROVISIONAL and is kept in one marked table in the netlist.
- Cell temperature (E2): two 10 kohm NTCs (Murata NCU15XH103F60RC, 0402, B 3380 K; it replaces the NCP15XH103F03RC, which Murata flags as not recommended for new designs; PROVISIONAL stock) on the top side within 1 mm of the cell edge, each thermally joined to the cell with a dab of thermal adhesive. NTC1 goes from the charger TS ball to ground and belongs to the charger alone. NTC2 is the MCU's: divider with 10.0 kohm 1 % from a GPIO (NTC_BIAS, driven only while measuring) to an ADC pin (NTC_SENSE). The firmware uses NTC2 for its own charge supervision, for the no-read-above-60 C rule (section 6) and for the display; the IMU and MCU die temperatures are plausibility checks only.
- Defined states during reset: 100 kohm pull-down on the LCD chip select (active high) and on DISP; 100 kohm pull-ups to V2V8 on the flash and IMU chip selects.
- 32.768 kHz crystal on PC14/PC15: Abracon ABS07-120-32.768KHZ-T (6 pF load, lower drive requirement than the 12.5 pF part) with load capacitors sized for 6 pF; no high-speed crystal.
- BOOT0 (PH3) pulled down with 10 kohm; NRST with 100 nF.
- Test and service pads on the underside: VBUS, D-, D+, GND, SWDIO, SWCLK, NRST, in that order from x = -7.62 to +7.62 mm seen from above (seen from below, with the visor away from you, VBUS is on the right).
- Test points on the top side (E4), 1.0 mm bare round pads reachable by spring probes before the unit is closed: VBAT, V2V8, V2V8_CAM, GND. Board test before the cell is soldered powers the board through the two cell-lead pads from a bench supply with a current meter, which is also where sleep current is measured (limit below).
- Limits for board test (E14, PROPOSED until measured): V2V8 2.8 V +-3 %, V2V8_CAM 2.8 V +-3 % under camera load, VDDUSB 3.3 V +-3 %; sleep current at 3.8 V no more than 25 microamps (firmware model 20.6).
- Assembly (E5): lead-free (SAC305) reflow, RoHS-compliant parts. No conformal coating at EVT: the top side is inside a sealed, vented cavity and the wetted underside areas are potted or covered by the adhesive sheet; the underside is cleaned of flux before lamination because it carries the photodiode input.
- Cradle board (E6): USB-C receptacle (USB 2.0), 5.1 kohm from CC1 and from CC2 to ground (without them a C-to-C charger supplies nothing), a resettable fuse in VBUS (hold about 0.2 A, trip about 0.5 A, PROPOSED; it protects against a hard short at the pins, not against a wet slot), USBLC6-2SC6 on VBUS / D+ / D-, four spring pins fitted (VBUS, D-, D+, GND) and three service positions (SWDIO, SWCLK, NRST) for the factory fixture. The series Schottky on the marker is a 30 V 0.5 A SOD-323 class part (Diodes B0530WS-7-F, PROVISIONAL).
- No copper pours or vias under the IMU body on the top layer; keep it away from the charger and regulators.

PCB: 4 layers, 0.8 mm, ENIG, D-shaped outline (radius 21.1 mm, flat at y = 17.3 mm) with two non-plated locating holes at (14.35, 10.8) and (-14.35, 10.8, a 1.15 x 2.2 mm slot along x) that take spigots on the tub, through vias only,
0.25 mm drill, default 0.15 mm tracks with 0.127 mm clearance, and a fine net class of 0.10 mm track /
0.10 mm clearance used only to escape the camera BGAs (provisional 5 x 5 footprint, 0.5 mm pitch, 0.20 mm
pads). E7: 0.100 mm is 3.94 mil, a hair under the 4 mil (0.1016 mm) tier, and track plus two gaps between 0.20 mm pads at 0.5 mm pitch uses the whole 0.300 mm; the chosen fabricator must accept 0.100 / 0.100 mm in writing on the layers that carry the fine class (or the board is quoted at a 3 mil tier), which is a release gate. 4 mil features are reported as a standard tier at Sierra Circuits and Bay Area Circuits (PROVISIONAL: one of them may offer it on outer layers only); OSH Park has no
0.8 mm 4-layer service. Vias tented and plugged on the underside (the underside is a wetted surface inside the grain opening and
the pad slot), and no via at all inside the grain opening or the pad slot. Layer 2 solid ground. The top side must respect `tub_keepouts` in the YAML: no part taller than 2.55 mm anywhere (cameras excepted), six 1.6 mm and two 2.2 mm post-foot keep-outs, nothing taller than 0.95 mm under each camera hood except the camera, nothing taller than 0.7 mm under the LCD flex tail behind the connector (provisional until the Sharp tail drawing is in hand), and no soldered part above a ball foot or within 0.3 mm of its zone. Under each ball foot the bottom side has a 2.5 mm circle with no via and no track and an unmasked 1.6 mm copper land that the ball bears on. Two solder pads for the cell leads sit in the strip beyond the protection-board end of the cell. Parts on the top side except the grain LEDs, photodiode and
contact pads. The cameras, the LCD connector and the battery are fixed mechanical interfaces; every other part may be placed where routing needs it, and the YAML part list is then regenerated from the board.

## 5. Mechanical design rules

Stack at the centre, bottom to top (mm above the base plane):

| From | To | Item |
|---|---|---|
| 0.00 | 0.80 | Base plate (0.80 mm FR-4 from the PCB fabricator), with three 1.0 mm balls (E8: 316 stainless, grade 100 or better, or silicon nitride; not 440C, which rusts in wet fertilised turf) protruding 0.10 mm as hard feet (through holes; balls set on a gauge plate and potted) |
| 0.80 | 1.00 | Die-cut adhesive sheet (3M 93020LE class, 0.20 mm) that laminates the PCB to the base plate and seals the pad slot and the grain opening |
| 1.00 | 1.80 | PCB |
| 1.80 | 3.80 | Battery (2.0 mm) |
| 3.80 | 4.20 | Swelling allowance |
| 4.35 | 4.65 | Foam pad |
| 4.65 | 5.40 | LCD glass |
| 5.40 | 5.55 | Adhesive frame bonding the LCD under the roof ledge |
| 5.55 | 6.35 | Roof ledge (0.80 mm) around the 22 mm aperture |
| 6.35 | 7.60 | Cover-glass recess: 0.13 mm tape ring and 1.0 mm mineral-glass crystal, 0.12 mm below flush |

Stack at the cameras: base 0.80, adhesive 0.20, PCB 0.80, cube 2.76, bond 0.05, prism 2.00 (top at 6.61), 0.19 clearance, roof 0.80 (underside at 6.80), top at 7.60. Optical axis 5.61 mm above the base plane.

Every printed wall is at least 0.8 mm (one recorded exception: 0.525 mm behind each window recess) and every drop-in fit has 0.25 mm nominal clearance, because US Multi Jet Fusion bureaus state minimum walls of 0.76-1.0 mm and tolerances of +-0.2 to 0.3 mm. A tighter-tolerance process (Carbon DLS epoxy) could take about 0.3 mm off the thickness.

Parts:

1. **Tub (top shell)** — HP Multi Jet Fusion PA12, dyed black, vapor smoothed. Side wall 1.0 mm ending 0.25 mm above the base plane (so the three ball feet are always the seat), roof 0.8 mm, D-shaped with a flat visor face at y = 18.4 mm that carries two straight camera openings 4.0 mm wide, each closed by a small flat window (5.0 x 3.25 x 0.4 mm borosilicate) seated on the floor of a recess on the visor face, 0.15 mm below the face and the top, and sealed by a frame of non-slumping adhesive round its edge with nothing behind the glass (the prisms stay dry inside; adhesive is never wicked, because it would reach the roof edge of the opening where the light bundle has 0.054 mm). Inside: the LCD pocket and ledge, the cover-glass recess, two prism bays with light hoods (the slit above each cube at the rear is closed by a black gasket bead cured on the tub before assembly), two spigots on the outer front posts that locate the PCB (the cameras lie between them; the feet of those two posts are 1.9 x 2.2 mm so that the LCD glass can pass between them), support posts that carry load from the roof to the PCB without loading the LCD or the battery, an inward ledge near the bottom that seats on the base-plate seal, and a raised pad for the pressure-equalisation vent with drain grooves on the top face. The LCD adhesive frame has a vent channel so the space under the cover glass breathes into the vented cavity.
2. **Base plate** — routed from 0.80 mm FR-4 with black solder mask and no copper, ordered from the PCB fabricator. It has the 13 mm grain opening, one 17.44 x 2.2 mm slot over the seven pads (separate 2.2 mm holes would leave 0.34 mm webs), three 1.10 mm drilled holes for the ball feet, and the seal land round the edge. Reason for FR-4: the plate is laminated to the PCB that carries the level sensor, the cameras and the feet. A nylon plate there acts like a bimetal strip (nylon expands roughly seven times more than FR-4 with temperature and also swells with humidity), and the review estimated 0.04 to 0.3 mrad of tilt error per kelvin; an FR-4 plate has the same expansion as the PCB, is flatter (hole positions to 0.05 mm) and makes the laminate about as stiff as a 1.8 mm board under a footstep. A printed PA12 plate of the same outline (0.87 mm with a 0.13 mm sheet, integral baffle, not vapor smoothed) remains the documented alternative for an all-printed build and is compared at EVT. The balls are set to 0.10 mm protrusion on a gauge plate and potted with a dual-cure or two-part epoxy; each ball bears on a copper land on the PCB. E10: the outer face carries a legend printed by the fabricator in white on the black mask (or laser-marked): maker and model, "Practice device", the statements the compliance checklist requires for an unintentional radiator and for the battery, and a box for the serial number. The legend keeps 1 mm clear of the ball feet, the grain opening and the pad slot.
3. **Grain baffle and fill** — a printed black PA12 ring (8.2 mm outside, 6.6 mm inside) bonded to the PCB round the photodiode shades it from direct LED light. The ring is 0.82 mm high for the 0.80 mm plate, matched to the measured plate lot (plate thickness + 0.02 mm), and sits on an opaque black double-coated tape (E16: 0.10 to 0.145 mm as available; the ring height is matched to the plate lot and the tape actually used). The grain opening is then filled with a clear, hard, low-fluorescence potting so mud and dew cannot reach the LEDs and the photodiode. The potting surface must never come closer to the base plane than 0.05 mm; it is aimed at 0.10 mm inside the opening and accepted to 0.20 mm (about 93 mm3, measured wet and trimmed before cure). Whether a fill by volume holds that window, and what the potted disc does to the level reading, are EVT test items.
4. **Cover glass** — 28.0 x 1.0 mm flat mineral-glass watch crystal for EVT on a 0.13 mm tape ring (28 / 25 mm), 0.12 mm below flush. The EVT crystal is NOT step-proof (review estimate: it breaks at 100 to 200 N on a 20 mm patch). Production: chemically strengthened glass or sapphire specified by strength (ring-on-ring 600 MPa or more) with a printed black border; if step tests fail, 0.2 mm more puck thickness above the LCD is the reserved remedy. E9: a quarter-wave retarder film (about 0.1 mm, laminated to the underside of the cover glass with its axis at 45 degrees to the display polariser) is an EVT trial, because a reflective LCD can go dark through polarised sunglasses at some rotations and the marker is viewed at any rotation; there is 1.08 mm of air between the display and the glass, so nothing else moves. Note for production: 1.0 mm is reported as not a stocked thickness for chemically strengthened glass (0.8 and 1.1 mm are); the recess depth or the tape is re-fitted to the glass chosen at DVT.
5. **Prisms** — two Edmund Optics 32-526 (VERIFIED: 2.00 mm legs, N-BK7, aluminised hypotenuse, $105 each at 1-5; a volume source such as Tower Optical must be quoted for production). Bonded to the cube top at the four corners with UV-cure adhesive, leaving an air gap over the lens. They are not part of the seal: the visor windows close the openings, so shell strain does not reach the optics.
6. **Charging and data cradle** — printed nest (60 x 60 mm, 22.6 mm high overall) that accepts the marker one way round, with a drained floor, Mill-Max 0914-series long-stroke spring pins soldered into a small 2-layer board with a USB-C receptacle (four pins fitted for charging and USB, seven in the factory fixture), and a hold-down: a fixed lip over the front edge between the camera windows and a sprung latch with a thumb tab at the rear (calculated retention 6 times the seven-pin force; to be proven by cycle, creep and pull tests on first articles). Calibration does not use the cradle. Contact pads are ENIG at EVT and selective hard gold in production; the marker must be dry before docking.

Field of view: the enclosure leaves the cameras 26 degrees each side, 17.6 degrees up and 8 degrees down. The upper edge clears the roof by only 0.054 mm: the model gives 18.6 degrees nominal, 15.0 with the optics 0.2 mm high, and 14.6 with the 0.075 mm spigot play against it as well, so the guaranteed figure is 14.5 degrees. This is accepted (on a worst-case unit it delays the range-from-stick-height measurement from 6.6 m to about 8.1 m and nothing else).

Sealing: bonded construction (no O-ring; a standard gland does not fit). Seal qualification loads and the vent requirement are in `docs/research/enclosure-manufacturing.md`.

## 6. Firmware and algorithm

The Python package in `sim/greenline_sim` is the reference. The embedded core is a portable C99
port tested against vectors exported from the reference. Sequence for a Quick Read:

1. IMU wake-on-motion, then stillness detected for 0.5 s.
2. Average the accelerometer for 1 s: gravity vector, tilt, temperature-compensated.
3. Power the camera rail; capture interleaved left-right-right-left strips (a horizontal band round the horizon, then a vertical strip round the flagstick candidate).
4. Detect the flagstick; measure bearing, disparity, lowest visible point, and angular height.
5. Fuse range (stereo, stick-height prior), fit the slope model (method B1: tilt plus flag-base height; the turf-horizon fit B2 stays an option that is off by default because it only helps on greens without a fringe), solve the putt, score confidence.
6. Draw the aim line through the ball position, with distance, slope percent, break in cup widths and a confidence bar.

Read time (E15): the firmware timing model gives a result 4.1 to 4.8 s after the marker comes to rest (camera rail on for 2.2 to 2.8 s, about 96 mA during a read, about 600 reads per charge, about 21 microamps asleep). Every one of these figures is a model built from data-sheet currents; none is measured.

Calibration and limits the firmware must support:

- Level zero on two seats (E11). On a hard plate the marker stands on its three ball feet; on turf it floats on the grass on its whole base face, and the ball heights (+-0.02 mm over a 24.5 mm triangle) let those two planes differ by up to 1.6 mrad. The factory therefore measures the zero twice: on a plain granite plate (ball seat, used for bench checks and for user zeroing on a hard surface) and on a plate with three clearance pockets for the balls so that the base face seats (turf seat, the default for a read). Both are stored. The Precision Read (turn the marker 180 degrees in place) still removes whatever is left.
- Display rotation (E12). The LCD glass can sit up to about 1 degree rotated in its pocket, which is more than the 0.5 degree the aim-line budget allows for transfer. The factory measures the drawn line against the marker's visor flat and stores the angle; the firmware rotates the drawn line by it.
- Temperature (E13). No read is started when the cell thermistor reads above 60 C (the marker shows a "too hot" symbol); charging limits are enforced by the charger itself (E1) and supervised by firmware.
- Ship mode (E13). A command through the cradle puts the marker into its lowest state with wake-on-motion off; it wakes when VBUS appears. Units are shipped and stored in this mode.
- Factory commands still to be written (they gate the build, see `docs/MANUFACTURING_PLAN.md`): camera identity and frame download, display test pattern, dark frames, starting a zero and the six-face calibration from the PC, the temperature fit, and a field log that records tilt, grain values and the fit so that a read can be replayed in the simulator.

## 7. Release gates (summary)

Nothing here has been built or tested. Before boards and parts are ordered a person must close the
provisional items: the OVM7692 ball map, ball pitch and image orientation from the registered
OmniVision datasheet (the Analog Devices MAX78000FTHR schematic uses the same part), the LCD tail
geometry and pin-1 side, the battery protection-board size and certificates, every distributor
stock check, and the mechanical first-article fit. The full list is kept in `docs/RELEASE_GATES.md`. Added by the amendments: the BQ25101 ball map and its temperature thresholds against the chosen NTC; the fabricator's written acceptance of 0.100 mm track and gap (E7); a USB vendor and product ID; the legend text from the compliance checklist; and the factory commands listed in section 6.
